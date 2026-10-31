"""Stationary tag / independent wheel / GroundHog comparison on tag 15's axis."""
# @(#)roomberry_calibration.py 3.1.web.1 2026/10/31 14:00:00

import json
from math import cos, sin, hypot, isfinite, pi
from time import monotonic, time


MODE_CALIBRATION = 'calibration'
TAG_ID = 15
STEP_MM = 500.0
SCAN_TIMEOUT_S = 120.0
HEADING_LIMIT_RAD = 0.30
TAG_FACE_LIMIT_RAD = 0.10
START_GAP_MIN_MM = 100.0
START_GAP_MAX_MM = 1600.0
LATERAL_LIMIT_MM = 200.0
RETURN_ERROR_LIMIT_MM = 400.0
PHONE_RECEIPT_MAX_AGE_S = 1.0
PHONE_FRAME_MAX_AGE_US = 500000


class CalibrationDrive:
    """A bounded straight out-and-back experiment; no gain changes or fusion."""
    def __init__(self, mission):
        self.mission = mission
        self.stage = 'start_scan'
        self.started = monotonic()
        self.deadline = self.started + SCAN_TIMEOUT_S
        self.requested_after = None
        self.step = 0
        self.origin = self.wheels = None
        self.last_odom = None
        self.epoch = None
        self.phone_anchor = None
        self.phone_lost = None
        self.pending_start = None
        self.start_captured_at = None
        self.phone_wait_logged = False
        self.health_baseline = None
        self.records = []
        self.result = None
        self.progress = None
        self.progress_at = self.started
        self.contact_start = None
        self.contact_limit = None
        self.contact_expected = None
        self.sensor_wait_since = None
        self.pending_scan = None

    @property
    def moving(self):
        return self.stage in ('reverse', 'return', 'contact')

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
            self.phone_lost = 'GroundHog session/calibration/continuity changed'
        if self.phone_lost:
            return None, self.phone_lost
        age = monotonic() - row.get('received_monotonic', -1e9)
        if not (0 <= age <= PHONE_RECEIPT_MAX_AGE_S and row['flags'] == 7 and
                0 <= row['send_us']-row['end_us'] <= PHONE_FRAME_MAX_AGE_US):
            return None, 'GroundHog stale or tracking invalid'
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
        self.mission._send_stop('calibration gentle bumper contact')
        self._record('contact', state, None, None)
        self.result = dict(status='complete', checkpoints=len(self.records))
        self.stage = 'complete'
        self.mission.logger.info('Calibration complete: %s', json.dumps(self.result, sort_keys=True))
        self.mission.set_mode('idle')

    def guard(self, state):
        """Also called during a slow stationary scan: no safety/timeout blind spot."""
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
        if contact and self.stage != 'contact':
            self.abort('unexpected physical bumper contact during ' + self.stage)
            return False
        health = self._row('latest_health_observation')
        if health is not None and 0 <= now-health.get('received_monotonic', -1e9) <= .5:
            identity = (health['session'], health['calibration'])
            old = self.health_baseline
            if old is not None and old[0] == identity and health['bump_count'] > old[1]:
                if not (self.stage == 'contact' and contact):
                    self.abort('phone reported an impact during ' + self.stage)
                    return False
            self.health_baseline = (identity, health['bump_count'])
        self._phone()  # Notice invalid continuity even between checkpoints.
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
        record = dict(checkpoint=label, tag_id=TAG_ID, wall_time=time(), captured_at=captured_at,
                      target_reverse_mm=self.step*STEP_MM if label.startswith('reverse_') else 0,
                      wheel_distance_from_start_mm=distance,
                      tag_pose=compact(tag_pose), wheels_pose=compact(self.wheels),
                      contact_expected_mm=self.contact_expected,
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

    def _scan(self, stage):
        self.mission._send_stop('calibration stationary checkpoint')
        self.stage = stage
        self.requested_after = None
        self.pending_scan = None
        self.deadline = monotonic()+SCAN_TIMEOUT_S

    def _move(self, stage, state):
        self.stage = stage
        self.progress = float(state['distance'])
        self.progress_at = monotonic()
        self.deadline = monotonic()+60

    def _valid_start(self, pose):
        tag = self.mission.discovery_landmarks.get(TAG_ID)
        if tag is None:
            return False
        world = tag['world_from_tag']
        gap = float(world[0][3])*1000-pose['x_mm']
        lateral = abs(float(world[1][3])*1000-pose['y_mm'])
        return (abs(self.mission._wrap(pose['heading_rad'])) <= HEADING_LIMIT_RAD
                and abs(self.mission._tag_normal_heading(world)) < TAG_FACE_LIMIT_RAD
                and START_GAP_MIN_MM <= gap <= START_GAP_MAX_MM and lateral <= LATERAL_LIMIT_MM)

    def tick(self, state, pose, new_detections, captured_at):
        self.mission._set_cleaning_motors(False)
        if (new_detections and self.stage.endswith('_scan') and self.requested_after is not None
                and captured_at is not None and captured_at > self.requested_after):
            self.pending_scan = (None if pose is None else dict(pose),captured_at)
        if not self.guard(state) or not self._integrate(state):
            return
        if self.pending_scan is not None and self.stage.endswith('_scan'):
            pose,captured_at = self.pending_scan
            new_detections = True
            self.pending_scan = None
        now = monotonic()
        tag_pose = (pose if new_detections and pose and pose.get('localized') and
                    any(int(key[1]) == TAG_ID for key in pose.get('accepted_tag_ids', ())) else None)
        if self.stage.endswith('_scan'):
            self.mission._send_stop('calibration waiting for scan')
            if self.requested_after is None:
                self.requested_after = time()
                self.mission.camera.request_scan()
                return
            if not new_detections or captured_at is None or captured_at <= self.requested_after:
                return
            if self.stage == 'start_scan':
                if tag_pose is None or not self._valid_start(tag_pose):
                    tag = self.mission.discovery_landmarks.get(TAG_ID)
                    detail = 'no fresh accepted tag 15'
                    if tag_pose is not None and tag is not None:
                        detail = 'heading {:.1f} deg, gap {:.0f} mm, lateral {:.0f} mm'.format(
                            tag_pose['heading_rad']*180/pi,
                            float(tag['world_from_tag'][0][3])*1000-tag_pose['x_mm'],
                            float(tag['world_from_tag'][1][3])*1000-tag_pose['y_mm'])
                    self.mission.logger.warning('Calibration start rejected: %s; tag_pose=%s rejected_tags=%s.',
                        detail,tag_pose,None if pose is None else pose.get('rejected_tags'))
                    self.abort('start verification failed: '+detail+
                               '; require tag 15, heading within +/-17.2 deg of +X, '
                               '100–1600 mm from its plane and within 200 mm laterally')
                    return
                self.pending_start = dict(tag_pose)
                self.start_captured_at = captured_at
                self.stage = 'phone_anchor'
                self.deadline = now+10
            else:
                label = 'return' if self.stage == 'return_scan' else 'reverse_{}'.format(self.step)
                self._record(label,state,tag_pose,captured_at)
                if self.stage == 'return_scan':
                    if (tag_pose is None or not self._valid_start(tag_pose) or
                            hypot(tag_pose['x_mm']-self.origin['x_mm'],
                                  tag_pose['y_mm']-self.origin['y_mm']) > RETURN_ERROR_LIMIT_MM):
                        self.abort('return scan did not verify tag 15 near the starting point')
                        return
                    tag = self.mission.discovery_landmarks[TAG_ID]['world_from_tag']
                    self.contact_expected = (float(tag[0][3])*1000-tag_pose['x_mm']-
                                             self.mission.navigation.robot_radius_mm)
                    self.contact_limit = min(START_GAP_MAX_MM-self.mission.navigation.robot_radius_mm+30,
                                             self.contact_expected+30)
                    self.contact_start = float(state['distance'])
                    if self.contact_limit <= 0:
                        self.abort('no safe contact approach distance')
                        return
                    self._move('contact',state)
                    self.deadline = now+self.contact_limit/15+10
                elif self.step == 3:
                    self._move('return',state)
                else:
                    self.step += 1
                    self._move('reverse',state)
                return
        if self.stage == 'phone_anchor':
            row, reason = self._phone()
            if row is None:
                if not self.phone_wait_logged:
                    self.mission.logger.warning('Calibration waiting for phone baseline: %s', reason)
                    self.phone_wait_logged = True
                return  # Ten-second bounded wait; wheels remain stopped.
            self.origin = {k: self.pending_start[k] for k in ('x_mm','y_mm','heading_rad')}
            self.origin['distance'] = float(state['distance'])
            self.wheels = {k: self.origin[k] for k in ('x_mm','y_mm','heading_rad')}
            self.epoch = state.get('odometry_epoch')
            self.phone_anchor = dict(identity=(row['session'],row['calibration'],row['continuity']),
                                     x=row['segment_x_mm'],y=row['segment_y_mm'],
                                     yaw=row['segment_yaw_rad'],end_us=row['end_us'])
            self._record('start',state,self.pending_start,self.start_captured_at)
            self.step = 1
            self._move('reverse',state)
            return
        if not self.moving:
            return
        distance = float(state['distance'])
        error = self.mission._wrap(self.origin['heading_rad']-self.wheels['heading_rad'])
        if abs(error) > HEADING_LIMIT_RAD:
            self.abort('heading drift exceeds straight calibration envelope')
            return
        if self.stage == 'contact':
            bumps = state['sensors'].bumps_and_wheel_drops
            if bumps.bump_left or bumps.bump_right:
                if distance-self.contact_start < max(0,self.contact_expected-50):
                    self.abort('bumper contact before verified tag approach envelope')
                else:
                    self._finish(state)
                return
            remaining = self.contact_limit-(distance-self.contact_start)
            if remaining <= 0:
                self.abort('gentle contact distance limit reached without bumper contact')
                return
            speed = 15
        else:
            target = self.origin['distance']-(self.step*STEP_MM if self.stage == 'reverse' else 0)
            remaining = distance-target if self.stage == 'reverse' else target-distance
            if remaining <= 0:
                self._scan('reverse_scan' if self.stage == 'reverse' else 'return_scan')
                return
            speed = min(50,max(10,int(remaining/2)))
            if self.stage == 'reverse':
                speed = -speed
        if abs(distance-self.progress) >= 3:
            # Wrong-way motion is never counted as progress.
            if (distance-self.progress)*speed < 0:
                self.abort('wheel movement opposite to commanded direction')
                return
            self.progress = distance
            self.progress_at = now
        elif now-self.progress_at > 3:
            self.abort('no wheel progress for three seconds')
            return
        steering = max(-.15,min(.15,error*2)) * (1 if speed > 0 else -1)
        self.mission._dispatch(dict(kind='drive',reason='calibration '+self.stage,
                                    velocity=speed,steering=steering,
                                    continuous=True,max_duration_s=1.0),self.wheels)
