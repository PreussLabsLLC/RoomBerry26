"""GridRunner packets and a grout-line-end out-and-back with tag checkpoints."""
# @(#)roomberry_gridrunner.py 3.1.tiles.10 2026/11/06
import json
import math
import struct
from roomberry_turn_guard import SettledTurn
from roomberry_phone_bumps import PhoneBumpPolicy
from time import monotonic, time

MODE_GRIDRUNNER = 'gridrunner'
GRID_PACKET = struct.Struct('<4sBBHQQIHbBQQ12fHHBBHIQfff')
GRID_FIELDS = ('magic','version','type','length','session','calibration','seq','flags',
               'direction','reason','frame_us','send_us','scan1_x','scan1_y','scan2_x','scan2_y',
               'offset_mm','line_angle_rad','confidence','correction','gain','correction_limit',
               'lens_left_mm','height_mm','image_width','image_height',
               'crossing_magic','crossing_version','crossing_flags','crossing_count',
               'crossing_us','crossing_y','crossing_confidence','crossing_interval_s')
GRID_CROSSING_MAGIC = 0xc7
GRID_CROSSING_VERSION = 1
GRID_SPEED = 100
# Pit-stop bench: firmware raises anything below ~40 mm/s to ~40, so 30 was
# fictional. Slow/approach/pivot are 40; I/O steps go 40 -> 70 -> 100.
GRID_SLOW_SPEED = 40
GRID_APPROACH_SPEED = GRID_SLOW_SPEED
GRID_MAX_STEERING = .35
GRID_LOOKAHEAD_MM = 600.
GRID_FRAME_MAX_AGE_S = .25
GRID_RECEIPT_MAX_AGE_S = .5
GRID_STEERING_MULTIPLIER = 2.0
GRID_PIVOT_SPEED = GRID_SLOW_SPEED
GRID_ALIGN_ENTER_RAD = math.radians(5)
GRID_ALIGN_EXIT_RAD = math.radians(2)
GRID_MIN_CONFIDENCE = .65
GRID_REACQUIRE_CONFIDENCE = .75
GRID_LINE_END_CONFIRM_S = 1.0
GRID_THRESHOLD_CLEARANCE_MM = 150.
# Return/approach line-loss grace before handing to tag recovery: the stripe
# flickers at the search edge right after turnaround, so allow up to 3 s of
# slow travel on the last-good line heading before a scan handoff.
GRID_RETURN_LOSS_GRACE_S = 3.0
GRID_LAST_GOOD_STEER_S = 1.5
# PID on the line tracking error; previously proportional-only, which
# overshot into a weave. Integral is clamped; derivative is kept small.
GRID_PID_KI = 0.15
GRID_PID_KD = 0.08
GRID_PID_I_LIMIT = 150.
TILE_MM = 304.8  # nominal kitchen tile pitch; one crossing = one tile span




def build_crossing_report(crossings, tile_mm=TILE_MM):
    """Per-tile wheel-vs-tile calibration rows from recorded crossings.

    Crossings are in recording order. ``count`` is monotonic per phone
    session, so the tile span since the previous recorded crossing is
    ``advance * tile_mm`` where ``advance`` is the count difference
    (1 + missed). Wheel travel is the absolute encoder distance between
    the two crossings. The first crossing of a leg (direction change or
    stage change) has no predecessor, so its delta fields are None:
    its absolute distance is still reported via ``tile_mm_total``.
    Pure/observation-only: never steers or stops the robot.
    """
    rows = []
    prev = None
    prev_leg = None
    first_count = None
    for rec in crossings:
        count = int(rec['count'])
        leg = 'out' if rec.get('stage') == 'driving' else (
            'back' if rec.get('stage') in ('return', 'approach', 'threshold_clearance', 'turnaround')
            else rec.get('stage'))
        if leg != prev_leg:
            prev = None
            first_count = count
        advance = ((count - int(prev['count'])) & 0xffffffff) if prev is not None else None
        tile_span = advance * tile_mm if advance is not None else None
        wheel_delta = (abs(float(rec['wheel_distance_mm']) - float(prev['wheel_distance_mm']))
                       if prev is not None else None)
        error = (wheel_delta - tile_span) if wheel_delta is not None else None
        rows.append(dict(
            count=count, missed=int(rec.get('missed', 0)),
            crossing_us=int(rec.get('crossing_us', 0)),
            interval_s=rec.get('interval_s'), y=rec.get('y'),
            confidence=rec.get('confidence'),
            session=rec.get('session'), calibration=rec.get('calibration'),
            stage=rec.get('stage'), direction=rec.get('direction'),
            wheel_distance_mm=rec.get('wheel_distance_mm'),
            wheel_heading_deg=rec.get('wheel_heading_deg'),
            tag_distance_mm=rec.get('tag_distance_mm'),
            tile_mm_total=(count - first_count) * tile_mm,
            tile_mm_span=tile_span, wheel_delta_mm=wheel_delta,
            error_mm=error,
            error_pct=(100.0 * error / tile_span
                       if error is not None and tile_span else None)))
        prev = rec
        prev_leg = leg
    deltas = [r['error_mm'] for r in rows if r['error_mm'] is not None]
    ratios = [r['wheel_delta_mm'] / r['tile_mm_span'] for r in rows
              if r['wheel_delta_mm'] is not None and r['tile_mm_span']]
    summary = dict(
        tile_mm=tile_mm, crossings=len(rows),
        missed=sum(int(r.get('missed', 0)) for r in rows),
        mean_error_mm=(sum(deltas) / len(deltas)) if deltas else None,
        median_ratio=(sorted(ratios)[len(ratios) // 2] if ratios else None),
        total_tile_mm=sum(r['tile_mm_span'] for r in rows if r['tile_mm_span']),
        total_wheel_ratio=(sum(r['wheel_delta_mm'] for r in rows if r['wheel_delta_mm'] is not None)
                           / sum(r['tile_mm_span'] for r in rows if r['tile_mm_span'])
                           if any(r['tile_mm_span'] for r in rows) else None))
    return dict(rows=rows, summary=summary)


def grid_correction(offset, angle, direction, gain, limit, target_offset=0.):
    # Positive offset means grout left of the robot. Offset correction has the
    # same wheel polarity in reverse; the angle term reverses wheel polarity.
    return max(-limit, min(limit, gain*((offset-target_offset)/GRID_LOOKAHEAD_MM+direction*angle)))


def decode_grid_packet(data):
    if len(data) != 128:
        raise ValueError('grid length')
    values = GRID_PACKET.unpack(data)
    r = dict(zip(GRID_FIELDS,values))
    if values[:4] != (b'NVLK',1,5,128):
        raise ValueError('grid header')
    if not r['session'] or not r['calibration'] or r['flags'] & ~3 or r['direction'] not in (-1,1):
        raise ValueError('grid identity/flags/direction')
    if r['reason'] > 6 or not r['frame_us'] <= r['send_us']:
        raise ValueError('grid reason/time')
    if data[-28:] == bytes(28):
        pass  # Legacy app: reserved trailer was all zero.
    elif (r['crossing_magic'] != GRID_CROSSING_MAGIC
          or r['crossing_version'] != GRID_CROSSING_VERSION or r['crossing_flags'] & ~1):
        raise ValueError('grid crossing header')
    else:
        if not math.isfinite(r['crossing_y']) or not 0 <= r['crossing_y'] <= 1:
            raise ValueError('grid crossing row')
        if not math.isfinite(r['crossing_confidence']) or not 0 <= r['crossing_confidence'] <= 1:
            raise ValueError('grid crossing confidence')
        if not math.isfinite(r['crossing_interval_s']) or not 0 <= r['crossing_interval_s'] <= 600:
            raise ValueError('grid crossing interval')
        if r['crossing_count']:
            if not r['crossing_us'] or r['crossing_us'] > r['send_us']:
                raise ValueError('grid crossing time')
        elif r['crossing_us'] or r['crossing_interval_s']:
            raise ValueError('grid crossing count')
        if r['crossing_flags'] & 1 and not 0 < r['crossing_y'] < 1:
            raise ValueError('grid crossing state')
    if not all(math.isfinite(v) for v in values[12:24]):
        raise ValueError('grid nonfinite')
    if not (0.1 <= r['gain'] <= 8 and 0 < r['correction_limit'] <= GRID_MAX_STEERING
            and abs(r['lens_left_mm']) <= 1000 and 50 <= r['height_mm'] <= 1500
            and 0 <= r['confidence'] <= 1 and abs(r['offset_mm']) <= 2000
            and abs(r['line_angle_rad']) <= .5 and abs(r['correction']) <= r['correction_limit']+1e-6
            and 0 < r['image_width'] <= 4096 and 0 < r['image_height'] <= 4096):
        raise ValueError('grid limits')
    if r['flags'] & 1:
        if (r['reason'] != 0 or not r['frame_us'] or r['send_us']-r['frame_us'] > 250000
                or r['confidence'] < .45 or not all(0 <= r[k] <= 1 for k in ('scan1_x','scan1_y','scan2_x','scan2_y'))
                or not r['scan1_y'] < r['scan2_y']):
            raise ValueError('grid invalid detection')
        expected = grid_correction(r['offset_mm'],r['line_angle_rad'],r['direction'],r['gain'],r['correction_limit'],r['lens_left_mm'])
        # Version-1 archives and older apps advertised robot-center correction.
        # Accept either contract; live steering is always recomputed on the Pi.
        legacy = grid_correction(r['offset_mm'],r['line_angle_rad'],r['direction'],r['gain'],r['correction_limit'])
        if min(abs(expected-r['correction']), abs(legacy-r['correction'])) > 1e-5:
            raise ValueError('grid inconsistent correction')
    elif r['correction'] != 0:
        raise ValueError('grid invalid frame must request zero correction')
    return values


class GridDrive:
    """Reverse to a confirmed grout-line end, then return via tag-15 checkpoints."""
    def __init__(self, mission):
        self.mission = mission
        self.started = monotonic()
        self.observation_started = self.started
        self.stage = 'waiting'
        self.result = self.identity = self.direction = self.config = None
        self.origin = self.last = self.last_distance = self.bump_count = self.epoch = None
        self.outbound_mm = None  # Explicit homing may have no outbound leg.
        self.progress_at = self.started
        self.initial_heading = self.hold_heading = None
        self.lost_at = self.lost_distance = None
        self.good_frames = 0
        self.good_seq = None
        self.hold_until = None
        # Scan-free return: no periodic tag checkpoints or scans; the line
        # alone steers home and the front bumper ends the approach.
        self.checkpoints = []
        self.records = []
        self.pose = None
        self.odom = None
        self.tag_localizer = None
        self.tag = None
        self.scan_started = self.scan_wall = None
        self.scan_attempts = 0
        self.scan_checkpoint = None
        self.final_fix = False
        self.last_tag_distance = None
        self.threshold = None
        self.tag_fix_applied = False
        self.target_offset_mm = 0.
        self.low_speed_pivot = False
        self.turn_control = SettledTurn(mission, lambda:monotonic())
        self.progress_heading = None
        self.scan_candidate = None
        self.scan_pause_started = None
        self.bump_policy = PhoneBumpPolicy()
        self.recovery_attempts = 0
        self.line_end_started = None
        self.line_end_seq = None
        self.line_end_frames = 0
        self.line_end_good_frames = 0
        self.crossing_identity = None
        self.crossing_count = 0
        self.crossings = []
        self.last_good_line = None
        self._pid_i = 0.0
        self._pid_e = None
        self._pid_at = None
        self.stale_since = None

    def _tile_report(self):
        """Durable per-tile calibration table; observation only."""
        report = build_crossing_report(self.crossings)
        self.mission.logger.info('GridRunner crossing report: %s',
                                 json.dumps(report, sort_keys=True))
        return report

    def abort(self, reason):
        self.stage = 'stopped'
        self.result = dict(status='stopped', reason=reason,
                           tiles=self.crossing_count,
                           crossings=list(self.crossings),
                           crossing_report=self._tile_report())
        self.mission.logger.warning('GridRunner stopped: %s', reason)
        self.mission.set_mode('idle')

    def _row(self, method):
        getter = getattr(self.mission.navlink, method, None)
        row = getter() if callable(getter) else None
        return row if isinstance(row, dict) else None

    @staticmethod
    def _wrap(angle):
        return (angle+math.pi) % (2*math.pi)-math.pi

    def _pause(self, reason):
        self.mission._send_stop(reason, force=True, smooth='scan' in reason.lower())
        self.mission.robot_control.end_motion_lease()
        self.low_speed_pivot = False
        self.turn_control.reset()

    def _recover_tags(self, state, reason):
        if self.recovery_attempts >= 3:
            self.abort('return recovery exhausted after three tag searches: '+reason)
            return
        from roomberry_tag_return import Tag15Return
        self._pause('GridRunner stationary tag recovery scan')
        self.recovery_attempts += 1
        run = Tag15Return(self.mission, state, prior=self)
        run.grout_source = self
        run.bump_policy = self.bump_policy
        self.mission.gridrunner = run
        self.mission.logger.info('Grout return handed to mapped-tag recovery: attempt=%d reason=%s',
                                 self.recovery_attempts, reason)
        run.start()

    def resume_line_return(self, homing, state, row, health):
        self.pose = dict(homing.pose)
        self.tag = dict(homing.tag)
        self.tag_fix_applied = homing.tag_fix_applied or homing.prior_valid
        self.odom = (float(state['distance']), float(state['angle']))
        self.epoch = state['odometry_epoch']
        self.initial_heading = self.hold_heading = float(state['angle'])
        self.identity = (row['session'], row['calibration'])
        self.direction = row['direction']
        self.config = (row['gain'],row['correction_limit'],row['lens_left_mm'],row['height_mm'])
        self.target_offset_mm = row['lens_left_mm']
        self.bump_count = health['bump_count']
        self.bump_policy = homing.bump_policy
        self.final_fix = self.final_fix or homing.final_fix
        if self.final_fix:
            self.last_tag_distance = float(state['distance'])
        self.stage = 'approach' if self.final_fix else 'return'
        self.lost_at = self.lost_distance = None
        self.good_frames = 0
        self.last_distance = float(state['distance'])
        self.progress_heading = float(state['angle'])
        self.progress_at = monotonic()
        self.low_speed_pivot = False
        self.turn_control.reset()
        self.scan_attempts = 0
        self.scan_candidate = self.scan_pause_started = None
        remaining = self._range(state)
        self.checkpoints = [] if self.final_fix else [c for c in (2000.,1500.,1000.,500.) if c <= remaining+10]
        self.mission.gridrunner = self
        self.mission.robot_control.begin_motion_lease(.6)
        self.mission.logger.info('Mapped-tag recovery resumed visible grout-line return: range_mm=%.1f', remaining)

    def _ignore_speed_bump(self, health):
        getter = getattr(self.mission.robot_control, 'phone_bump_speed_change', None)
        context = getter(health) if callable(getter) else None
        if not isinstance(context, dict):
            return False
        self.mission.logger.info('Phone bump ignored after speed change: %s', json.dumps(dict(
            bump_count=health['bump_count'], peak_mm_s2=health.get('last_bump_peak_mm_s2'),
            stage=self.stage, **context), sort_keys=True))
        return True

    def _seed_pose(self):
        landmark = self.mission.discovery_landmarks.get(15)
        if landmark is None:
            return
        t = landmark['world_from_tag']
        heading = math.atan2(t[1][2], t[0][2])
        radius = float(self.mission.mapper.robot_radius_mm)
        self.tag = dict(x=1000*t[0][3], y=1000*t[1][3], heading=heading, radius=radius)
        self.pose = dict(x_mm=self.tag['x']-radius*math.cos(heading)+self.target_offset_mm*math.sin(heading),
                         y_mm=self.tag['y']-radius*math.sin(heading)-self.target_offset_mm*math.cos(heading),
                         heading_rad=heading)
        # Anchor: the run traverses along the tag-15 heading line; lateral
        # drift away from this y is heading drift, corrected in steering.
        self.anchor_y_mm = self.pose['y_mm']

    def _integrate(self, state):
        distance, angle = float(state['distance']), float(state['angle'])
        if not math.isfinite(distance) or not math.isfinite(angle) or state.get('odometry_epoch') != self.epoch:
            self.abort('wheel odometry invalid or reset')
            return False
        if self.odom is not None:
            delta, yaw = distance-self.odom[0], math.radians(angle-self.odom[1])
            if abs(delta) > 150 or abs(yaw) > .3:
                self.abort('wheel odometry discontinuity')
                return False
            if self.pose is not None:
                middle = self.pose['heading_rad']+yaw/2
                self.pose['x_mm'] += delta*math.cos(middle)
                self.pose['y_mm'] += delta*math.sin(middle)
                self.pose['heading_rad'] = self._wrap(self.pose['heading_rad']+yaw)
        self.odom = distance, angle
        return True

    def _range(self, state):
        if self.pose is not None:
            return math.hypot(self.tag['x']-self.pose['x_mm'], self.tag['y']-self.pose['y_mm'])
        return max(0., self.origin-float(state['distance']))+174.

    def _record_crossing(self, row, state):
        """Log each new transverse-grout count with the matching wheel state.

        The phone count is monotonic per session; a skipped count is recorded
        as missed rather than inventing a crossing time.
        """
        if row.get('crossing_magic') != GRID_CROSSING_MAGIC:
            return
        identity = (row['session'], row['calibration'])
        count = int(row['crossing_count'])
        if identity != self.crossing_identity:
            # A fresh GridDrive in an ongoing phone session first sees a
            # nonzero count: crossings that predate it are not new events
            # and must not be logged as a missed span. A count of 1 is a
            # genuine first crossing of a fresh session; record normally.
            self.crossing_identity = identity
            self.crossing_count = count
            if count > 1:
                return
            self.crossing_count = 0
        advance = (count-self.crossing_count) & 0xffffffff
        if not 0 < advance < 0x80000000:
            return
        self.crossing_count = count
        distance = float(state['distance'])
        record = dict(
            count=count, missed=max(0, advance-1),
            crossing_us=int(row['crossing_us']),
            y=round(row['crossing_y'], 4),
            confidence=round(row['crossing_confidence'], 3),
            interval_s=round(row['crossing_interval_s'], 3),
            session=row['session'], calibration=row['calibration'],
            stage=self.stage, direction=self.direction,
            wheel_distance_mm=distance-(self.origin if self.origin is not None else 0.),
            wheel_heading_deg=float(state['angle']),
            tag_distance_mm=self._range(state))
        self.crossings.append(record)
        self.mission.logger.info('GridRunner crossing: %s', json.dumps(record, sort_keys=True))

    def _fuse_line_heading(self, row):
        """Pull pose heading toward the grout-stripe direction.

        Previously pose heading was wheel-yaw integration only, so a
        persistent left/right imbalance integrated into a +y drift
        (several degrees over one run) that the map trace showed as a
        bend away from the tag-15 anchor line. The stripe's world
        direction is the tag heading; GridRunner reports the line angle
        relative to the body (modelled as -body heading error), so the
        observation is tag_heading - line_angle. Weak per-tick fusion
        keeps wheel integration for dynamics but bounds the drift.
        """
        if self.pose is None or self.tag is None:
            return
        if row.get('flags') != 3 or row.get('confidence', 0) < .65:
            return
        observed = self._wrap(float(self.tag['heading']) - float(row['line_angle_rad']))
        innovation = self._wrap(observed - self.pose['heading_rad'])
        self.pose['heading_rad'] = self._wrap(
            self.pose['heading_rad'] + 0.02 * innovation)
        return innovation

    def _expected_contact(self):
        if self.stage not in ('return', 'approach') or self.pose is None:
            return False
        dx, dy = self.tag['x']-self.pose['x_mm'], self.tag['y']-self.pose['y_mm']
        heading = self.tag['heading']
        gap = dx*math.cos(heading)+dy*math.sin(heading)
        lateral = -dx*math.sin(heading)+dy*math.cos(heading)
        return (self.tag['radius']-100 <= gap <= self.tag['radius']+75
                and abs(lateral) <= 75
                and abs(self._wrap(self.pose['heading_rad']-heading)) <= .2)

    def _scan(self, checkpoint):
        self._pause('GridRunner tag 15 checkpoint scan')
        self.low_speed_pivot = False
        self.turn_control.reset()
        if self.scan_pause_started is None:
            self.scan_pause_started = monotonic()
        if self.scan_checkpoint != checkpoint or self.scan_attempts == 0:
            self.scan_candidate = None
            self.scan_relocation_pending = False
        self.stage = 'scanning'
        self.scan_checkpoint = checkpoint
        self.scan_attempts += 1
        self.scan_started, self.scan_wall = monotonic(), time()
        self.mission.camera.request_scan()

    def _tag_fix(self, detections):
        from roomberry_localization import AprilTagLocalizer
        source = self.mission.localizer
        if self.tag_localizer is None:
            if not isinstance(getattr(source, 'landmarks', None), dict):
                return None
            landmarks = {k:v for k,v in source.landmarks.items() if k[1] == 15}
            self.tag_localizer = AprilTagLocalizer(
                landmarks, source.camera_from_robot, max_tag_distance_m=2.5,
                max_reprojection_error=source.max_reprojection_error,
                min_decision_margin=source.min_decision_margin,
                room_bounds_mm=source.room_bounds_mm)
        # Per-checkpoint solver: existing quality/plane checks, expanded range
        # only here. No modification of normal navigation's 1.2 m tag gate.
        self.tag_localizer.invalidate_pose()
        return self.tag_localizer.update(
            tuple(r for r in detections if int(r.get('id', -1)) == 15), 0, 0)

    def _scan_tick(self, state):
        captured = self.mission.camera.last_detection_time
        if isinstance(captured, (float, int)) and captured >= self.scan_wall:
            pose = self._tag_fix(self.mission.camera.latest_detections)
            accepted = pose is not None and bool(pose.get('accepted_tag_ids'))
            reason = 'accepted' if accepted else 'tag 15 missing or rejected by quality checks'
            pending = False
            position_innovation = heading_innovation = None
            if accepted:
                if abs(self._wrap(pose['heading_rad']-self.tag['heading'])) > .35:
                    accepted, reason = False, 'tag heading exceeds straight approach envelope'
                discrepant = False
                if accepted and self.pose is not None:
                    position_innovation = math.hypot(pose['x_mm']-self.pose['x_mm'], pose['y_mm']-self.pose['y_mm'])
                    heading_innovation = abs(self._wrap(pose['heading_rad']-self.pose['heading_rad']))
                    discrepant = (position_innovation > 500 or (self.tag_fix_applied and
                        (position_innovation > 200 or heading_innovation > math.radians(8))))
                if discrepant:
                    self.scan_relocation_pending = True
                if accepted and (discrepant or getattr(self, 'scan_relocation_pending', False) or self.scan_checkpoint == 500):
                    previous = self.scan_candidate
                    consistent = (previous is not None and
                        math.hypot(pose['x_mm']-previous['x_mm'], pose['y_mm']-previous['y_mm']) <= 75 and
                        abs(self._wrap(pose['heading_rad']-previous['heading_rad'])) <= math.radians(4))
                    self.scan_candidate = dict(pose)
                    if not consistent:
                        accepted, pending = False, True
                        reason = 'inconsistent prediction; confirming stationary relocation' if discrepant else 'final tag fix needs a second consistent stationary scan'
                    elif discrepant:
                        reason = 'stationary relocation confirmed despite odometry discrepancy'
            if not accepted and not pending:
                self.scan_candidate = None
            self.records.append(dict(checkpoint_mm=self.scan_checkpoint, attempt=self.scan_attempts,
                                     accepted=accepted, reason=reason, pose=pose,
                                     pending_confirmation=pending, position_innovation_mm=position_innovation,
                                     heading_innovation_rad=heading_innovation,
                                     rejections=[] if self.tag_localizer is None else self.tag_localizer.last_rejected))
            self.mission.logger.info('GridRunner tag checkpoint: %s', json.dumps(self.records[-1], sort_keys=True))
            # This dedicated path bypasses generic localization feedback.
            # Keep feedback stationary, before the moving lease is restarted.
            self.mission._button_beep('neutral' if pending else 'happy' if accepted else 'unhappy')
            # Do not replace this song immediately with the next scan/mode tone.
            # Waiting here leaves the serial owner polling and the robot braked.
            self.mission._shutdown.wait(.15 if pending else .35)
            if accepted:
                self.pose = {k:float(pose[k]) for k in ('x_mm','y_mm','heading_rad')}
                self.tag_fix_applied = True
                self.last_tag_distance = float(state['distance'])
                self.mission._run_map = dict(pose=dict(self.pose, localized=True),
                    distance=float(state['distance']), angle=float(state['angle']), epoch=self.epoch)
            elif getattr(self, 'scan_relocation_pending', False) and self.scan_attempts >= (3 if self.scan_checkpoint == 500 else 2):
                self._recover_tags(state, 'stationary relocation could not be confirmed')
                return
            elif self.scan_checkpoint == 500 or self.scan_attempts < 2:
                if self.scan_attempts < (3 if self.scan_checkpoint == 500 else 2):
                    self._scan(self.scan_checkpoint)
                else:
                    self._recover_tags(state, 'final tag 15 checkpoint localization failed')
                return
            if self.scan_checkpoint == 500:
                self.final_fix = True
                self.checkpoints = []
            # Consume only a processed checkpoint. An abort during capture must
            # leave it pending, including the mandatory final localization.
            if self.checkpoints and self.checkpoints[0] == self.scan_checkpoint:
                self.checkpoints.pop(0)
            self.scan_attempts = 0
            if self.lost_at is not None and self.scan_pause_started is not None:
                self.lost_at += monotonic()-self.scan_pause_started
            self.scan_pause_started = None
            self.stage = 'approach' if self.final_fix else 'return'
            self.progress_at = monotonic()
            self.last_distance = float(state['distance'])
            self.progress_heading = float(state['angle'])
            self.low_speed_pivot = False
            self.turn_control.reset()
            self.mission.robot_control.begin_motion_lease(.6)
        elif monotonic()-self.scan_started > 20:
            self.abort('tag 15 scan timeout')

    def tick(self, state, scan_active=False):
        now = monotonic()
        self.mission._set_cleaning_motors(False)
        sensors = state.get('sensors')
        contact = sensors is not None and (sensors.bumps_and_wheel_drops.bump_left or sensors.bumps_and_wheel_drops.bump_right)
        # A verified near-target front contact is the intended return endpoint.
        safe = (state.get('ready') and state.get('age') is not None and 0 <= state['age'] <= .5
                and not state.get('oi_stopped') and not self.mission._hard_hazard_reasons(state))
        if not safe:
            # A asleep Roomba at launch is not fatal: wait for fresh sensors
            # (serial hiccups settle) until the waiting timeout.
            if self.stage == 'waiting' and now-self.started <= 10:
                self.mission._send_stop('GridRunner waiting for fresh Roomba sensors')
                return
            self.abort('unsafe/stale Roomba sensors or bumper contact')
            return
        if self.identity is not None and not self._integrate(state):
            return
        if contact and self._expected_contact():
            self.stage = 'complete'
            self.result = dict(status='complete', reason='tag 15 front bumper contact',
                               outbound_mm=self.outbound_mm, checkpoints=self.records,
                               tiles=self.crossing_count, crossings=list(self.crossings),
                               crossing_report=self._tile_report(),
                               final_pose=dict(self.pose))
            self.mission._update_run_map(state)
            self.mission.set_mode('idle')
            return
        if contact or state.get('motion_lease_expired') or state.get('safety_latched'):
            self.abort('unsafe/stale Roomba sensors or bumper contact')
            return
        if state.get('battery_status') in ('low','critical','charging'):
            self.abort('battery is '+state['battery_status'])
            return
        if now-self.started > (10 if self.stage == 'waiting' else 600):
            self.abort('waiting timeout' if self.stage == 'waiting' else 'run timeout')
            return
        row, health = self._row('latest_grid_observation'), self._row('latest_health_observation')
        fresh = (row is not None and row['received_monotonic'] >= self.observation_started
                 and 0 <= now-row['received_monotonic'] <= .5
                 and 0 <= now-row['frame_monotonic'] <= .25)
        health_ok = (health is not None and row is not None
                     and (health['session'],health['calibration']) == (row['session'],row['calibration'])
                     and 0 <= now-health['received_monotonic'] <= .5)
        usable = fresh and row['flags'] == 3 and row['confidence'] >= GRID_MIN_CONFIDENCE
        if fresh:
            self.stale_since = None
        if self.stage == 'waiting' and not (usable and health_ok):
            self.last = dict(tracking='waiting for fresh line/health (line confidence ≥65%)',
                             confidence=0 if row is None else row['confidence'],
                             velocity_mm_s=0, offset_mm=None, tracking_error_mm=None, correction=None)
            self.mission._send_stop('GridRunner waiting for fresh line and phone health')
            return
        if not fresh or not health_ok or row['flags'] not in (2,3) or (row['flags'] == 2 and row['reason'] != 1):
            # A single stale frame (reason 2, e.g. a 400 ms hiccup mid-run)
            # no longer aborts: brake and hold for up to 1 s, abort after.
            stale_frame = row is not None and row['flags'] == 2 and row['reason'] == 2
            if stale_frame and health_ok and self.identity is not None:
                if getattr(self, 'stale_since', None) is None:
                    self.stale_since = now
                    self._pause('GridRunner stale frame brake')
                if now - self.stale_since < 1.0:
                    self.last = dict(stage=self.stage, tracking='holding for fresh frame',
                                     tiles=self.crossing_count, velocity_mm_s=0,
                                     confidence=row['confidence'], offset_mm=None)
                    return
            self.abort('line lost, stopped, or line/phone telemetry stale')
            return
        identity = (row['session'],row['calibration'])
        config = (row['gain'],row['correction_limit'],row['lens_left_mm'],row['height_mm'])
        if self.identity is None:
            if row['direction'] != -1:
                self.abort('out-and-back requires reverse phone direction')
                return
            self.identity, self.direction, self.config = identity, row['direction'], config
            self.target_offset_mm = row['lens_left_mm']
            self.origin = self.last_distance = float(state['distance'])
            self.initial_heading = self.hold_heading = float(state['angle'])
            self.progress_heading = float(state['angle'])
            self.epoch, self.bump_count = state.get('odometry_epoch'), health['bump_count']
            self.bump_policy.baseline(health)
            self.odom = self.origin, self.initial_heading
            self._seed_pose()
            if self.tag is None:
                self.abort('tag 15 survey unavailable; cannot arm out-and-back')
                return
            self.stage = 'driving'
            self.progress_at = now
            self.mission.robot_control.begin_motion_lease(.6)
        elif identity != self.identity or row['direction'] != self.direction or config != self.config:
            self.abort('phone session/configuration/direction changed; restart explicitly')
            return
        self._record_crossing(row, state)
        self._fuse_line_heading(row)
        event = self.bump_policy.observe(health, self._ignore_speed_bump)
        self.bump_count = health['bump_count']
        if event is not None:
            self.mission.logger.info('GridRunner phone impact policy: %s', json.dumps(dict(event, stage=self.stage)))
        if event is not None and event['action'] == 'react':
            self.mission.robot_control.set_bump_indicator(True)
            self.abort('phone impact detected during outbound' if self.stage == 'driving'
                       else 'phone impact detected during return')
            return
        if self.stage == 'driving':
            explicit_loss = row['flags'] == 2 and row['reason'] == 1
            if explicit_loss and self.line_end_started is None:
                self._pause('GridRunner outbound grout-line end check')
                self.line_end_started = now
                self.line_end_frames = self.line_end_good_frames = 0
                self.line_end_loss_total = self.line_end_good_total = 0
                self.line_end_seq = None
                self.mission.logger.info('GridRunner line-end brake: outbound_mm=%.1f seq=%s',
                                         self.origin-float(state['distance']), row['seq'])
            if self.line_end_started is not None:
                if row['seq'] != self.line_end_seq:
                    self.line_end_seq = row['seq']
                    if explicit_loss:
                        self.line_end_frames += 1
                        self.line_end_good_frames = 0
                        self.line_end_loss_total = getattr(self, 'line_end_loss_total', 0) + 1
                    elif usable and row['confidence'] >= GRID_REACQUIRE_CONFIDENCE:
                        self.line_end_good_frames += 1
                        self.line_end_frames = 0
                        self.line_end_good_total = getattr(self, 'line_end_good_total', 0) + 1
                    else:
                        self.line_end_frames = self.line_end_good_frames = 0
                self.last = dict(stage=self.stage, tracking='checking grout-line end',
                    tiles=self.crossing_count,
                    velocity_mm_s=0, left_velocity_mm_s=0, right_velocity_mm_s=0,
                    confidence=row['confidence'], wheel_distance_mm=float(state['distance'])-self.origin,
                    frame_age_s=now-row['frame_monotonic'], line_lost_s=now-self.line_end_started,
                    seq=row['seq'], steering_mode='stopped', offset_mm=None,
                    correction=0, target_offset_mm=self.target_offset_mm)
                # Confirm on 3 losses within the window even if flicker
                # interleaves good frames (they only cancel at 3 total).
                if (self.line_end_frames >= 3 or (getattr(self, 'line_end_loss_total', 0) >= 3
                        and getattr(self, 'line_end_good_total', 0) < 3)) \
                        and now-self.line_end_started >= GRID_LINE_END_CONFIRM_S:
                    self.outbound_mm = self.origin-float(state['distance'])
                    self.threshold = dict(wall_time=time(), reason='grout-line end',
                        wheel_distance_mm=self.outbound_mm, confirmation_s=now-self.line_end_started,
                        loss_frames=self.line_end_frames)
                    self.stage, self.hold_until = 'turnaround', now
                    self.mission.logger.info('GridRunner threshold line end: %s', json.dumps(self.threshold, sort_keys=True))
                    return
                if self.line_end_good_frames >= 3:
                    self.line_end_started = None
                    self.lost_at = self.lost_distance = None
                    self.last_distance, self.progress_at = float(state['distance']), now
                    self.hold_heading = self.progress_heading = float(state['angle'])
                    self.mission.robot_control.begin_motion_lease(.6)
                    self.mission.logger.info('GridRunner line-end check cancelled: three fresh good frames')
                elif now-self.line_end_started > 3.:
                    self.abort('grout-line end could not be confirmed; robot remains stopped')
                    return
                else:
                    return
        if (abs(float(state['angle'])-self.initial_heading) > math.degrees(.35)
                and (self.stage == 'driving' or not usable)):
            if self.stage in ('return','approach'):
                self.abort('return heading envelope exceeded (scan-free)')
            else:
                self.abort('heading exceeds straight run envelope')
            return
        if self.stage == 'scanning':
            if not scan_active:
                self._scan_tick(state)
            elif now-self.scan_started > 20:
                self.abort('tag 15 scan timeout')
            return
        if self.stage == 'turnaround':
            if now < self.hold_until:
                return
            self.mission.robot_control.execute('_change_mode', mode=2)
            self.outbound_mm = self.origin-float(state['distance'])
            self.threshold['settled_distance_mm'] = self.outbound_mm
            self.mission.logger.info('GridRunner threshold settled: %s', json.dumps(self.threshold, sort_keys=True))
            self.stage = 'threshold_clearance'
            self.clearance_origin = float(state['distance'])
            self.clearance_started = now
            self.clearance_progress_at = now
            self.clearance_last_distance = self.clearance_origin
            self.clearance_stopped_at = None
            self.clearance_good_frames = 0
            self.clearance_seq = None
            self.lost_at = self.lost_distance = None
            self.good_frames = 0
            self.last_distance, self.progress_at = float(state['distance']), now
            self.mission.robot_control.begin_motion_lease(.6)
        if self.stage == 'threshold_clearance':
            distance = float(state['distance'])
            travelled = distance-self.clearance_origin
            if travelled < -3:
                self.abort('wheel travel opposite threshold clearance direction')
                return
            if distance-self.clearance_last_distance >= 1:
                self.clearance_last_distance, self.clearance_progress_at = distance, now
            if now-self.clearance_started > 12:
                self.abort('threshold clearance timed out')
                return
            if row['seq'] != self.clearance_seq:
                self.clearance_seq = row['seq']
                self.clearance_good_frames = self.clearance_good_frames+1 if usable and row['confidence'] >= GRID_REACQUIRE_CONFIDENCE else 0
            complete = travelled >= GRID_THRESHOLD_CLEARANCE_MM
            if complete and self.clearance_stopped_at is None:
                self._pause('GridRunner threshold clearance complete')
                self.clearance_stopped_at = now
                self.last.update(velocity_mm_s=0, left_velocity_mm_s=0, right_velocity_mm_s=0,
                                 tracking='qualifying grout after threshold clearance')
                self.threshold['clearance_mm'] = travelled
                self.mission.logger.info('GridRunner threshold clearance: measured_mm=%.1f good_line_frames=%d',
                                         travelled, self.clearance_good_frames)
            if complete and self.clearance_good_frames >= 3:
                self.stage = 'return'
                self.return_origin = distance
                self.lost_at = self.lost_distance = None
                self.good_frames = 0
                self.last_distance, self.progress_at = distance, now
                self.mission.robot_control.begin_motion_lease(.6)
            elif complete:
                if now-self.clearance_stopped_at >= 1.:
                    self.abort('no stable grout line after 150 mm threshold clearance (scan-free)')
                return
            else:
                if now-self.clearance_progress_at > 3:
                    self.abort('no wheel progress during threshold clearance')
                    return
                self.last = dict(stage=self.stage, tracking='clearing threshold', steering_mode='straight',
                    tiles=self.crossing_count,
                    velocity_mm_s=GRID_SLOW_SPEED, left_velocity_mm_s=GRID_SLOW_SPEED,
                    right_velocity_mm_s=GRID_SLOW_SPEED, clearance_mm=travelled,
                    wheel_distance_mm=distance-self.origin, confidence=row['confidence'],
                    tag_distance_mm=self._range(state), frame_age_s=now-row['frame_monotonic'])
                self.mission.logger.info('GridRunner sample: %s', json.dumps(self.last, sort_keys=True))
                try:
                    self.mission.robot_control.renew_motion_lease(.6)
                except RuntimeError:
                    self.abort('GridRunner motion lease expired during threshold clearance')
                    return
                self.mission._dispatch(dict(kind='drive', velocity=GRID_SLOW_SPEED, steering=0,
                    reason='GridRunner threshold clearance', continuous=True, max_duration_s=.6,
                    ramp=False, speed_steps=True), None)
                return
        distance = float(state['distance'])
        direction = -1 if self.stage == 'driving' else 1
        if self.stage == 'driving' and self.origin-distance >= 5000:
            self.abort('5000 mm travel limit reached without grout-line end')
            return
        if self.stage in ('return','approach'):
            remaining = self._range(state)
            # Only a full-length outbound from tag 15 yields a trustworthy
            # seeded pose. A short/zero-length outbound (re-run already at
            # the grout end) seeds the pose at the tag, so range lies:
            # stay in 'return' and finish on contact instead of tripping
            # the approach bound instantly.
            if (self.stage == 'return' and remaining <= 510
                    and self.outbound_mm is not None and self.outbound_mm >= 1000):
                self.stage = 'approach'
                self.last_tag_distance = distance
                self.mission.logger.info('GridRunner scan-free approach: range_mm=%.1f', remaining)
            if self.stage == 'approach' and (remaining < self.tag['radius']-50
                    or distance-self.last_tag_distance > 650):
                self.abort('approach position/travel bound without contact (scan-free)')
                return
            if (self.stage == 'return' and self.outbound_mm is not None
                    and distance-getattr(self, 'return_origin', distance) > self.outbound_mm + 5000):
                self.abort('return travel bound without contact (scan-free)')
                return
        if abs(distance-self.last_distance) >= 3:
            if (distance-self.last_distance)*direction < 0:
                self.abort('wheel travel opposite commanded direction')
                return
            self.last_distance, self.progress_at = distance, now
            self.progress_heading = float(state['angle'])
        elif self.low_speed_pivot and abs(float(state['angle'])-self.progress_heading) >= .5:
            self.progress_heading, self.progress_at = float(state['angle']), now
        elif now-self.progress_at > 3:
            self.abort('no wheel progress for three seconds')
            return
        if not usable:
            if self.lost_at is None:
                self.lost_at, self.lost_distance = now, distance
            self.good_frames = 0
        elif self.lost_at is not None and row['confidence'] < GRID_REACQUIRE_CONFIDENCE:
            self.good_frames = 0
            self.good_seq = None
        elif self.lost_at is not None and row['seq'] != self.good_seq:
            self.good_frames += 1
            self.good_seq = row['seq']
            if self.good_frames >= 3:
                self.lost_at = self.lost_distance = None
        degraded = self.lost_at is not None
        # Return/approach with no line: dead-reckon on the fused wheel pose
        # toward the surveyed tag 15. It should come back into view; only
        # the outer 30 s / 750 mm slow-travel bound aborts (clamped below).
        if degraded and self.stage in ('driving','return','approach') and (now-self.lost_at > 30 or abs(distance-self.lost_distance) > 750):
            self.abort('line absent beyond 30 seconds or 750 mm slow-travel allowance')
            return
        speed = direction*(GRID_APPROACH_SPEED if self.stage == 'approach' else
                           GRID_SLOW_SPEED if degraded else GRID_SPEED)
        line_correction = tag_correction = None
        line_heading_error = None
        if usable and not (self.stage == 'driving' and degraded):
            line_heading_error = (row['line_angle_rad']+direction*math.atan2(
                row['offset_mm']-self.target_offset_mm, GRID_LOOKAHEAD_MM))
            err = (row['offset_mm']-self.target_offset_mm)/GRID_LOOKAHEAD_MM \
                + direction*row['line_angle_rad']
            prev_at = self._pid_at if self._pid_at is not None else now - 0.1
            dt = max(0.02, min(0.5, now - prev_at))
            self._pid_i = max(-GRID_PID_I_LIMIT, min(GRID_PID_I_LIMIT,
                getattr(self, '_pid_i', 0.0) + err * dt))
            d = (err - (self._pid_e if self._pid_e is not None else err)) / dt
            self._pid_e, self._pid_at = err, now
            raw = row['gain']*GRID_STEERING_MULTIPLIER*(err + GRID_PID_KI*self._pid_i + GRID_PID_KD*d)
            line_correction = max(-min(row['correction_limit'],GRID_MAX_STEERING),
                                  min(min(row['correction_limit'],GRID_MAX_STEERING), raw))
            if self.stage == 'driving' and row['confidence'] >= GRID_REACQUIRE_CONFIDENCE:
                self.hold_heading = float(state['angle'])
            self.last_good_line = dict(correction=line_correction,
                                       heading_error=line_heading_error,
                                       at=now, offset_mm=row['offset_mm'],
                                       angle=row['line_angle_rad'])
        # While the stripe flickers at the search edge, steer briefly on the
        # last-good line heading instead of snapping to heading hold.
        if degraded and self.stage in ('return','approach') and self.last_good_line is not None \
                and now-self.lost_at < GRID_LAST_GOOD_STEER_S:
            buffered = self.last_good_line
            line_correction = buffered['correction']
            line_heading_error = buffered['heading_error']
        if self.stage == 'driving' and line_correction is not None:
            correction = line_correction
        else:
            target = self.hold_heading if self.stage == 'driving' else self.initial_heading
            error = math.radians(target-float(state['angle']))
            if direction == 1 and self.pose is not None:
                h, radius = self.tag['heading'], self.tag['radius']
                dx = self.tag['x']-radius*math.cos(h)+self.target_offset_mm*math.sin(h)-self.pose['x_mm']
                dy = self.tag['y']-radius*math.sin(h)-self.target_offset_mm*math.cos(h)-self.pose['y_mm']
                desired = h if dx*math.cos(h)+dy*math.sin(h) <= 50 else math.atan2(dy,dx)
                desired = h+max(-.2,min(.2,self._wrap(desired-h)))
                error = self._wrap(desired-self.pose['heading_rad'])
            tag_correction = max(-.25,min(.25,direction*4*error))
            correction = tag_correction
            if line_correction is not None:
                # A visible grout line owns steering even after a tag fix.
                correction = line_correction
                if direction == 1 and self.pose is not None and getattr(self, 'anchor_y_mm', None) is not None:
                    dy = max(-150., min(150., self.anchor_y_mm - self.pose['y_mm']))
                    if abs(self.anchor_y_mm - self.pose['y_mm']) > 120:
                        correction += max(-.1, min(.1, 2. * math.atan2(dy, 600.)))
        steering_mode = 'differential'
        physical_error = (line_heading_error if line_correction is not None else error)
        if abs(speed) < GRID_SPEED:
            limit = GRID_ALIGN_EXIT_RAD if self.low_speed_pivot else GRID_ALIGN_ENTER_RAD
            self.low_speed_pivot = abs(physical_error) > limit
            if self.low_speed_pivot:
                sign = 1 if physical_error > 0 else -1
                steering_mode = 'pivot'
                left_velocity, right_velocity = -sign*GRID_PIVOT_SPEED, sign*GRID_PIVOT_SPEED
                applied_speed = 0
                action = dict(kind='turn', velocity=GRID_PIVOT_SPEED, steering=sign)
            else:
                steering_mode = 'straight'
                left_velocity = right_velocity = applied_speed = speed
                action = dict(kind='drive', velocity=speed, steering=0)
        else:
            self.low_speed_pivot = False
            left_velocity, right_velocity = int(speed*(1-correction)), int(speed*(1+correction))
            applied_speed = speed
            action = dict(kind='drive', velocity=speed, steering=correction)
        turn_sign = (1 if right_velocity > left_velocity else -1) if steering_mode == 'pivot' else None
        ready = self.turn_control.prepare(state, turn_sign, physical_error)
        if self.turn_control.error:
            self.abort(self.turn_control.error)
            return
        if not ready:
            steering_mode = 'settling'
            left_velocity = right_velocity = applied_speed = 0
        self.last = dict(seq=row['seq'], stage=self.stage, tracking='slow' if degraded else 'locked',
            tiles=self.crossing_count,
            tag_distance_mm=self._range(state),
            line_lost_s=0 if not degraded else now-self.lost_at,
            last_good_line_age_s=(None if self.last_good_line is None else now-self.last_good_line['at']),
            scan1=[row['scan1_x'],row['scan1_y']] if usable else None,
            scan2=[row['scan2_x'],row['scan2_y']] if usable else None,
            offset_mm=row['offset_mm'] if usable else None, line_angle_rad=row['line_angle_rad'] if usable else None,
            target_offset_mm=self.target_offset_mm,
            tracking_error_mm=row['offset_mm']-self.target_offset_mm if usable else None,
            confidence=row['confidence'],correction=correction,direction=direction,velocity_mm_s=applied_speed,
            steering_mode=steering_mode, heading_error_rad=physical_error,
            line_correction=line_correction, tag_correction=tag_correction,
            tag_fix_applied=self.tag_fix_applied,
            steering_multiplier=GRID_STEERING_MULTIPLIER,wheel_distance_mm=distance-self.origin,
            wheel_heading_deg=state['angle'],frame_age_s=now-row['frame_monotonic'],
            left_velocity_mm_s=left_velocity, right_velocity_mm_s=right_velocity)
        self.mission.logger.info('GridRunner sample: %s',json.dumps(self.last,sort_keys=True,allow_nan=False))
        try:
            self.mission.robot_control.renew_motion_lease(.6)
        except RuntimeError:
            self.abort('GridRunner motion lease expired')
            return
        if ready:
            self.mission._dispatch(dict(action,reason='GridRunner '+self.stage,
                                        continuous=True,max_duration_s=.6,ramp=False,speed_steps=True),None)
            if self.mission._active_command is not None:
                self.turn_control.dispatched(turn_sign)
