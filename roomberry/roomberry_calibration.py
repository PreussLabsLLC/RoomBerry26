"""Scan-free threshold out-and-back following the initial GroundHog line."""
# @(#)roomberry_calibration.py 3.1.line.1 2026/11/03 14:30:00

import json
import os
from math import atan2, cos, sin, hypot, isfinite, pi
from time import monotonic, time


MODE_CALIBRATION = 'calibration'
# Reverse until a new phone bump detects the threshold, or this travel limit.
DEFAULT_DISTANCE_MM = 5000.0
MAX_MOVE_SPEED_MM_S = 50
DEFAULT_TURNAROUND_HOLD_S = 1.0
PHONE_BUMP_RECORD_ONLY_MAX_MM_S2 = 0.5 * 9806.65
ENDPOINT_TOLERANCE_MM = 15.0
MIN_MOVE_SPEED_MM_S = 25
HEADING_LIMIT_RAD = 0.30
HEADING_GAIN = 4.0
MAX_STEERING = 0.35
LINE_LOOKAHEAD_MM = 600.0
MAX_LINE_HEADING_RAD = 0.10
PHONE_RECEIPT_MAX_AGE_S = 1.0
PHONE_FRAME_MAX_AGE_US = 500000


def line_heading_target(lateral_mm, direction):
    """Face toward y=0 looking ahead along travel; direction is +1/-1.

    In reverse a positive heading moves the robot right, so the heading
    target must reverse sign while the original reference line stays fixed.
    """
    target = -direction * atan2(lateral_mm, LINE_LOOKAHEAD_MM)
    return max(-MAX_LINE_HEADING_RAD, min(MAX_LINE_HEADING_RAD, target))


class CalibrationDrive:
    """Wheel endpoints with GroundHog heading and lateral line feedback."""
    def __init__(self, mission):
        self.mission = mission
        self.stage = 'phone_anchor'
        self.started = monotonic()
        self.deadline = self.started + 10.0
        self.distance_mm = float(os.environ.get('ROOMBERRY_CALIBRATION_DISTANCE_MM', DEFAULT_DISTANCE_MM))
        self.hold_s = float(os.environ.get('ROOMBERRY_CALIBRATION_HOLD_S', DEFAULT_TURNAROUND_HOLD_S))
        if not isfinite(self.distance_mm) or not 100 <= self.distance_mm <= 5000:
            raise ValueError('Calibration distance must be finite and between 100 and 5000 mm')
        if not isfinite(self.hold_s) or not 0 <= self.hold_s <= 30:
            raise ValueError('Calibration turnaround hold must be between 0 and 30 seconds')
        self.hold_until = None
        self.origin = self.wheels = None
        self.last_odom = None
        self.epoch = None
        self.phone_anchor = None
        self.phone_lost = None
        self.phone_wait_logged = False
        self.health_baseline = None
        self.phone_bumps = []
        self.pending_impact = None
        self.threshold_bump = False
        self.turnaround_reason = None
        self.records = []
        self.result = None
        self.progress = None
        self.progress_at = self.started
        self.sensor_wait_since = None

    @property
    def moving(self):
        return self.stage in ('reverse', 'return')

    def _row(self, method):
        receiver = self.mission.navlink
        getter = getattr(receiver, method, None) if receiver is not None else None
        row = getter() if callable(getter) else None
        return row if isinstance(row, dict) else None

    def _phone(self):
        row = self._row('latest_ground_observation')
        if row is None:
            return None, 'GroundHog unavailable'
        identity = (row['session'], row['calibration'], row['continuity'])
        if self.phone_anchor is not None and identity != self.phone_anchor['identity']:
            self.phone_lost = ('GroundHog session/calibration/continuity changed: '
                               '{} -> {}; seq={} flags={} tracking={} reason={} rejected_frames={}'
                               .format(self.phone_anchor['identity'], identity, row.get('seq'),
                                       row.get('flags'), row.get('tracking'), row.get('reason'),
                                       row.get('rejected_frames')))
        if self.phone_lost:
            return None, self.phone_lost
        age = monotonic() - row.get('received_monotonic', -1e9)
        if not (0 <= age <= PHONE_RECEIPT_MAX_AGE_S and row['flags'] == 7 and
                0 <= row['send_us']-row['end_us'] <= PHONE_FRAME_MAX_AGE_US):
            return None, 'GroundHog stale or tracking invalid'
        if not all(isfinite(row[key]) for key in ('segment_x_mm', 'segment_y_mm', 'segment_yaw_rad')):
            return None, 'GroundHog nonfinite pose'
        return row, None

    def _phone_pose(self):
        row, reason = self._phone()
        if row is None or self.phone_anchor is None:
            return None, reason or 'GroundHog not anchored'
        anchor = self.phone_anchor
        if row['end_us'] < anchor['end_us']:
            return None, 'GroundHog capture precedes anchor'
        dx, dy = row['segment_x_mm']-anchor['x'], row['segment_y_mm']-anchor['y']
        a = self.origin['heading_rad']-anchor['yaw']
        return dict(x_mm=self.origin['x_mm']+cos(a)*dx-sin(a)*dy,
                    y_mm=self.origin['y_mm']+sin(a)*dx+cos(a)*dy,
                    heading_rad=self.mission._wrap(self.origin['heading_rad']+
                                                  row['segment_yaw_rad']-anchor['yaw']),
                    session=row['session'], calibration=row['calibration'],
                    continuity=row['continuity'], seq=row['seq'], end_us=row['end_us'],
                    timing='arrival freshness only; phone/Pi clocks unsynchronized'), None

    def abort(self, reason):
        self.result = dict(status='aborted', reason=reason, checkpoints=len(self.records))
        self.stage = 'aborted'
        self.mission.logger.warning('Calibration aborted: %s', reason)
        self.mission.set_mode('idle')

    def _finish(self, state):
        self.mission._send_stop('calibration complete')
        self._record('finish', state, None, None)
        self.result = dict(status='complete', checkpoints=len(self.records))
        self.stage = 'complete'
        self.mission.logger.info('Calibration complete: %s', json.dumps(self.result, sort_keys=True))
        self.mission.set_mode('idle')

    def guard(self, state):
        """Also called while the coordinator waits: no safety/timeout blind spot."""
        now = monotonic()
        reasons = self.mission._hard_hazard_reasons(state)
        if (not state.get('ready') or state.get('age') is None
                or state.get('oi_stopped') or reasons):
            self.abort('unsafe/stale Roomba sensors: {}'.format(reasons or state.get('age')))
            return False
        if state.get('battery_status') in ('low', 'critical', 'charging'):
            self.abort('battery is ' + state['battery_status'])
            return False
        if now > self.deadline or now-self.started > 900:
            self.abort('timeout during ' + self.stage)
            return False
        if self.origin is not None and state.get('odometry_epoch') != self.epoch:
            self.abort('wheel odometry epoch changed')
            return False
        sensors = state['sensors']
        bumps = sensors.bumps_and_wheel_drops
        contact = bool(bumps.bump_left or bumps.bump_right)
        if state.get('safety_latched') and not contact:
            self.abort('Roomba safety stop latched')
            return False
        if contact:
            self.abort('unexpected physical bumper contact during ' + self.stage)
            return False
        health = self._row('latest_health_observation')
        if health is not None and 0 <= now-health.get('received_monotonic', -1e9) <= .5:
            identity = (health['session'], health['calibration'])
            old = self.health_baseline
            if old is None or old[0] != identity:
                self.pending_impact = None
            elif health['bump_count'] > old[1]:
                event = dict(session=identity[0], calibration=identity[1],
                             count=health['bump_count'], stage=self.stage,
                             wall_time=time(), peak_mm_s2=health.get('last_bump_peak_mm_s2'))
                self.phone_bumps.append(event)
                self.pending_impact = (identity, health['bump_count'], event)
                if self.stage == 'reverse':
                    event['action'] = 'threshold-stop'
                    self.threshold_bump = True
                    self.mission._send_stop('calibration threshold phone bump')
                    self.mission.logger.info('Calibration phone bump: %s', json.dumps(event, sort_keys=True))
            pending = self.pending_impact
            if pending is not None and pending[:2] == (identity, health['bump_count']):
                event = pending[2]
                peak = health.get('last_bump_peak_mm_s2')
                known = isinstance(peak, (int,float)) and isfinite(peak) and peak > 0
                previous_action = event.get('action')
                if known:
                    event['peak_mm_s2'] = max(event.get('peak_mm_s2') or 0, peak)
                if event.get('action') != 'threshold-stop':
                    event['action'] = ('record-only' if known and
                        event['peak_mm_s2'] <= PHONE_BUMP_RECORD_ONLY_MAX_MM_S2 else 'stop')
                if event['action'] != previous_action:
                    self.mission.logger.info('Calibration phone bump: %s', json.dumps(event, sort_keys=True))
                # The phone refines the event peak for 150 ms after onset.
                # Recheck the same counter so a small first report cannot mask
                # an event that subsequently grows above the stop threshold.
                if event['action'] == 'stop':
                    self.abort('phone reported an impact during ' + self.stage)
                    return False
            self.health_baseline = (identity, health['bump_count'])
        phone, reason = self._phone()
        if self.phone_anchor is not None and phone is None:
            self.abort(reason)
            return False
        if state['age'] > .5:
            self.mission._send_stop('calibration waiting for fresh stationary sensors')
            if self.moving or state['age'] > 5 or (self.sensor_wait_since is not None and now-self.sensor_wait_since > 5):
                self.abort('stale Roomba sensors during {}: {:.3f} s'.format(self.stage,state['age']))
            elif self.sensor_wait_since is None:
                self.sensor_wait_since = now
                self.mission.logger.warning('Calibration holding stationary for a fresh sensor poll: '
                                            'stage=%s age_s=%.3f.',self.stage,state['age'])
            return False
        if self.sensor_wait_since is not None:
            self.mission.logger.info('Calibration fresh sensors restored after %.3f s; resuming %s.',
                                     now-self.sensor_wait_since,self.stage)
            self.sensor_wait_since = None
        return True

    def _integrate(self, state):
        d, a = float(state['distance']), float(state['angle'])
        if not isfinite(d) or not isfinite(a):
            self.abort('invalid wheel odometry')
            return False
        if self.wheels is not None and self.last_odom is not None:
            dd, da = d-self.last_odom[0], (a-self.last_odom[1])*pi/180
            if abs(dd) > 150 or abs(da) > .3:
                self.abort('wheel odometry discontinuity')
                return False
            h = self.wheels['heading_rad']+da/2
            self.wheels['x_mm'] += dd*cos(h)
            self.wheels['y_mm'] += dd*sin(h)
            self.wheels['heading_rad'] = self.mission._wrap(self.wheels['heading_rad']+da)
        self.last_odom = (d,a)
        return True

    def _record(self, label, state, tag_pose, captured_at):
        phone, unavailable = self._phone_pose()
        distance = float(state['distance'])-self.origin['distance']
        def compact(p):
            return None if p is None else {k: p[k] for k in ('x_mm', 'y_mm', 'heading_rad')}
        def residual(p, reference):
            if p is None or reference is None:
                return None
            dx, dy = p['x_mm']-reference['x_mm'], p['y_mm']-reference['y_mm']
            return dict(dx_mm=dx, dy_mm=dy, distance_mm=hypot(dx,dy),
                        heading_rad=self.mission._wrap(p['heading_rad']-reference['heading_rad']))
        record = dict(checkpoint=label, wall_time=time(), monotonic_s=monotonic(), captured_at=captured_at,
                      frame='local start: x forward, y left', distance_target_mm=self.distance_mm,
                      turnaround_reason=self.turnaround_reason,
                      line_control=dict(lookahead_mm=LINE_LOOKAHEAD_MM,
                                        max_target_heading_rad=MAX_LINE_HEADING_RAD),
                      phone_bumps=[dict(event) for event in self.phone_bumps],
                      target_reverse_mm=self.distance_mm if label == 'turnaround' else 0,
                      wheel_distance_from_start_mm=distance,
                      tag_pose=compact(tag_pose), wheels_pose=compact(self.wheels),
                      bumper=dict(left=bool(state['sensors'].bumps_and_wheel_drops.bump_left),
                                  right=bool(state['sensors'].bumps_and_wheel_drops.bump_right)),
                      iphone_pose=phone, iphone_unavailable=unavailable,
                      wheels_minus_tag=residual(self.wheels, tag_pose),
                      iphone_minus_tag=residual(phone, tag_pose),
                      iphone_minus_wheels=residual(phone, self.wheels),
                      tag_rejections=None if tag_pose is not None else
                          (None if self.mission._scan_pose is None else self.mission._scan_pose.get('rejected_tags')))
        self.records.append(record)
        self.mission.logger.info('Calibration checkpoint: %s', json.dumps(record, sort_keys=True, allow_nan=False))

    def _move(self, stage, state):
        self.stage = stage
        self.progress = float(state['distance'])
        self.progress_at = monotonic()
        self.deadline = monotonic() + self.distance_mm / MIN_MOVE_SPEED_MM_S + 15

    def _turnaround(self, state, reason):
        self.mission._send_stop('calibration turnaround')
        self.turnaround_reason = reason
        self._record('turnaround', state, None, None)
        self.stage = 'turnaround'
        self.hold_until = monotonic() + self.hold_s
        self.deadline = self.hold_until + 5

    def tick(self, state, pose, new_detections, captured_at):
        # Tag results, including a scan already in flight, never anchor this run.
        self.mission._set_cleaning_motors(False)
        if not self.guard(state) or not self._integrate(state):
            return
        now = monotonic()
        if self.stage == 'reverse' and self.threshold_bump:
            self._turnaround(state, 'phone bump')
            return
        if self.stage == 'phone_anchor':
            self.mission._send_stop('calibration waiting for GroundHog baseline')
            row, reason = self._phone()
            if row is None:
                if not self.phone_wait_logged:
                    self.mission.logger.warning('Calibration waiting for phone baseline: %s', reason)
                    self.phone_wait_logged = True
                return
            self.origin = dict(x_mm=0.0, y_mm=0.0, heading_rad=0.0,
                               distance=float(state['distance']))
            self.wheels = dict(x_mm=0.0, y_mm=0.0, heading_rad=0.0)
            self.epoch = state.get('odometry_epoch')
            self.phone_anchor = dict(identity=(row['session'], row['calibration'], row['continuity']),
                                     x=row['segment_x_mm'], y=row['segment_y_mm'],
                                     yaw=row['segment_yaw_rad'], end_us=row['end_us'])
            self._record('start', state, None, None)
            self._move('reverse', state)
            return
        phone, reason = self._phone_pose()
        if phone is None:
            self.abort(reason)
            return
        if abs(phone['heading_rad']) > HEADING_LIMIT_RAD or abs(self.wheels['heading_rad']) > HEADING_LIMIT_RAD:
            self.abort('heading drift exceeds straight calibration envelope')
            return
        if self.stage == 'turnaround':
            if now < self.hold_until:
                return
            self._move('return', state)
        if not self.moving:
            return
        distance = float(state['distance'])
        target = self.origin['distance'] - (self.distance_mm if self.stage == 'reverse' else 0)
        remaining = distance-target if self.stage == 'reverse' else target-distance
        if remaining <= ENDPOINT_TOLERANCE_MM:
            if self.stage == 'return':
                self._finish(state)
            else:
                self._turnaround(state, 'distance limit')
            return
        speed = min(MAX_MOVE_SPEED_MM_S, max(MIN_MOVE_SPEED_MM_S, int(remaining/2)))
        if self.stage == 'reverse':
            speed = -speed
        if abs(distance-self.progress) >= 3:
            if (distance-self.progress)*speed < 0:
                self.abort('wheel movement opposite to commanded direction')
                return
            self.progress = distance
            self.progress_at = now
        elif now-self.progress_at > 3:
            self.abort('no wheel progress for three seconds')
            return
        direction = 1 if speed > 0 else -1
        target_heading = line_heading_target(phone['y_mm'], direction)
        error = self.mission._wrap(target_heading-phone['heading_rad'])
        steering = max(-MAX_STEERING, min(MAX_STEERING, error*HEADING_GAIN)) * direction
        self.mission.logger.info('Calibration sample: %s', json.dumps(dict(
            wall_time=time(), monotonic_s=now, stage=self.stage,
            wheel_distance_from_start_mm=distance-self.origin['distance'],
            wheels_pose=dict(self.wheels), iphone_pose=phone,
            cross_track_mm=phone['y_mm'], target_heading_rad=target_heading,
            heading_error_rad=error, velocity_mm_s=speed, steering=steering,
            right_velocity_mm_s=int(speed*(1+steering)),
            left_velocity_mm_s=int(speed*(1-steering))), sort_keys=True, allow_nan=False))
        self.mission._dispatch(dict(kind='drive', reason='calibration '+self.stage,
                                    velocity=speed, steering=steering,
                                    continuous=True, max_duration_s=1.0), self.wheels)
