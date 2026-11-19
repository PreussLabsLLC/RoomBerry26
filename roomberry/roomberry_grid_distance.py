"""Crossing-paced tag-15 range survey, independent of navigation pose fusion."""
# @(#)roomberry_grid_distance.py 3.2.return.3 2026/11/19 12:38:26
import json
import math
from time import monotonic, time
from roomberry_gridrunner import GridDrive, grid_correction, TILE_MM
from roomberry_wheel_speed import MIN_WHEEL_SPEED


LINE_REACQUIRE_SECONDS = 3.0
LINE_RETRACE_STEP_MM = 50
LINE_RETRACE_MAX_STEPS = 2
LINE_RETRACE_TIMEOUT_SECONDS = 4.0


class GridDistanceDrive(GridDrive):
    kind = 'tag15_distance'

    def __init__(self, mission, start_mm, tile_mm=TILE_MM, autonomous=False):
        super().__init__(mission)
        self.start_mm, self.tile_mm = start_mm, tile_mm
        self.autonomous = autonomous
        self.first_crossing_distance = None
        self.confidence_retries = 0
        self.confidence_return_to = None
        self.confidence_hold = False
        self.crossing_retries = 0
        self.skipped_crossings = 0
        self.search_limit_mm = self.tile_mm + 30
        self.recovery_origin = None
        self.line_loss_started = self.line_reacquire_frame = None
        self.line_recheck_at = self.line_retrace_target = None
        self.line_retrace_steps = 0
        self.configured_start_mm = start_mm
        self.sensor_wait_started = None
        self.sensor_wait_pose = None
        self.stop_reason = None
        self.step_origin = self.step_count = None
        self.station = 0
        self.station_distance = None
        self.measured = False
        self.station_at = self.started

    def _announce(self, text):
        self.mission.logger.info(text, extra=dict(speech_code='SCAN_RESULT', speech_detail=text, speech_announce=True))

    def _begin_scan(self):
        self._pause('GridRunner distance stationary scan')
        self.stage = 'settling'
        self.station_at = monotonic()
        self.station_distance = None
        self.measured = False

    def measure(self, tape_mm):
        recording_after_stop = self.stage == 'stopped'
        if self.stage not in ('awaiting_measure', 'stopped') or not self.records:
            raise ValueError('Wait for a completed station scan before recording tape distance')
        rec = self.records[-1]
        if recording_after_stop:
            rec['recorded_after_stop'] = True
        rec['tape_mm'] = tape_mm
        if self.station == 0 and not recording_after_stop:
            rec['configured_expected_mm'] = rec['expected_mm']
            self.start_mm = tape_mm
            rec['expected_mm'] = tape_mm
        value = rec.get('camera_distance_mm')
        rec['error_mm'] = None if value is None else value-tape_mm
        rec['error_pct'] = None if value is None else 100*(value/tape_mm-1)
        self.measured = True
        if self.last is not None:
            self.last["measured"] = True
        self.mission.logger.info('GridRunner distance measurement: %s', json.dumps(rec, sort_keys=True))
        if recording_after_stop:
            return  # Keep the safety stop and result; recording never rearms motion.
        if tape_mm >= 5000:
            self.stop_reason = '5 m tape distance reached'
        if self.stop_reason:
            self.stage = 'complete'
            self.result = dict(status='complete', reason=self.stop_reason, stations=self.records)
            self.mission.set_mode('idle')

    def advance(self):
        if self.sensor_wait_started is not None:
            raise ValueError('Wait for fresh Roomba sensors before requesting another tile')
        if self.stage != 'awaiting_measure' or (not self.measured and not self.autonomous) or self.stop_reason:
            raise ValueError('Record the tape measurement at a clear station before moving')
        if (self.start_mm + self.origin - float(self.mission.robot_control.snapshot()['distance'])
                if self.autonomous else self.records[-1]['tape_mm']) + self.tile_mm > 5000:
            self.stop_reason = 'next tile would exceed 5 m'
            self.stage = 'complete'
            self.result = dict(status='complete', reason=self.stop_reason, stations=self.records)
            self.mission.set_mode('idle')
            return
        state = self.mission.robot_control.snapshot()
        age = state.get('age')
        if (not state.get('ready') or age is None or not 0 <= age <= .5
                or state.get('oi_stopped') or state.get('safety_latched')
                or self.mission._hard_hazard_reasons(state)):
            raise ValueError('Fresh, safe Roomba sensors required before another tile')
        self.step_origin = float(state['distance'])
        row = self._row('latest_grid_observation')
        self.step_count = row.get('crossing_count', 0) if row else 0
        self.stage = 'stepping'
        self.confidence_retries = 0
        self.confidence_return_to = None
        self.confidence_hold = False
        self.crossing_retries = 0
        self.search_limit_mm = self.tile_mm + 30
        self.recovery_origin = None
        self.line_loss_started = self.line_reacquire_frame = None
        self.line_retrace_steps = 0
        self.station_at = monotonic()
        self.mission.robot_control.begin_motion_lease(.6)

    def rescan(self):
        if self.stage != 'awaiting_measure':
            raise ValueError('Rescan requires a stopped station')
        self.stop_reason = None
        self._begin_scan()

    def abort(self, reason):
        super().abort(reason)
        self.result['stations'] = self.records

    def _drive_tile(self, velocity, steering, reason):
        try:
            self.mission.robot_control.renew_motion_lease(.6)
        except RuntimeError:
            self.abort('motor lease expired')
            return
        self.mission._dispatch(dict(kind='drive', velocity=velocity, steering=steering,
                                    continuous=True, max_duration_s=.6, ramp=False,
                                    speed_steps=True, reason=reason), None)

    def _recover_lost_line(self, row, state, now, line_visible, low_confidence):
        distance = float(state['distance'])
        if self.line_loss_started is None:
            self._pause('GridRunner distance lost grout line')
            self.line_loss_started = self.line_recheck_at = now
            self._announce('Grout line lost. Holding position while the phone looks for it.')
        self.last.update(tracking='waiting for grout line', velocity_mm_s=0)
        if self.line_retrace_target is not None:
            if distance >= self.line_retrace_target:
                self._pause('Grout line retrace step complete')
                self.line_retrace_target = None
                self.line_recheck_at = now
                self.step_count = row.get('crossing_count', 0)
            elif now - self.line_recheck_at >= LINE_RETRACE_TIMEOUT_SECONDS:
                self.abort('grout line retrace step exceeded its movement timeout')
            else:
                self.last.update(tracking='retracing to find grout line', velocity_mm_s=MIN_WHEEL_SPEED)
                self._drive_tile(MIN_WHEEL_SPEED, 0, 'GridRunner distance grout line retrace')
            return
        if line_visible and not low_confidence and row['frame_monotonic'] >= self.line_recheck_at:
            frame = row['frame_monotonic']
            if self.line_reacquire_frame is None:
                self.line_reacquire_frame = frame
            elif frame > self.line_reacquire_frame:
                self.station_at += now-self.line_loss_started
                self.line_loss_started = self.line_reacquire_frame = None
                self.mission.robot_control.begin_motion_lease(.6)
                self._announce('Grout line reacquired. Continuing the distance survey.')
                return
        else:
            self.line_reacquire_frame = None
        if now - self.line_recheck_at < LINE_REACQUIRE_SECONDS:
            return
        target = min(distance + LINE_RETRACE_STEP_MM, self.step_origin)
        if self.line_retrace_steps >= LINE_RETRACE_MAX_STEPS or target <= distance:
            self.abort('phone lost the grout line and did not reacquire it within the retrace limit')
            return
        self.line_retrace_steps += 1
        self.line_retrace_target = target
        self.line_recheck_at = now
        self.line_reacquire_frame = None
        self.recovery_origin = None
        self.mission.robot_control.begin_motion_lease(.6)
        self._announce('Retracing {:.0f} millimetres to find the grout line. Step {} of {}.'.format(
            target-distance, self.line_retrace_steps, LINE_RETRACE_MAX_STEPS))

    def tick(self, state, scan_active=False):
        now = monotonic()
        self.mission._set_cleaning_motors(False)
        sensors = state.get('sensors')
        contact = sensors is not None and (sensors.bumps_and_wheel_drops.bump_left or sensors.bumps_and_wheel_drops.bump_right)
        age = state.get('age')
        hard_stop = (state.get('oi_stopped') or self.mission._hard_hazard_reasons(state)
                     or contact or state.get('safety_latched') or state.get('motion_lease_expired')
                     or state.get('battery_status') in ('low', 'critical', 'charging'))
        transient = not state.get('ready') or age is None or not 0 <= age <= .5
        if transient and not hard_stop and self.stage in ('settling', 'scanning', 'awaiting_measure'):
            position = (state.get('odometry_epoch'), float(state['distance']), float(state['angle']))
            if self.sensor_wait_started is None:
                self.sensor_wait_started = now
                self.sensor_wait_pose = position
                self._pause('GridRunner parked sensor requalification')
            baseline = self.sensor_wait_pose
            if (now-self.sensor_wait_started <= 1.0 and position[0] == baseline[0]
                    and abs(position[1]-baseline[1]) <= 10 and abs(position[2]-baseline[2]) <= 1):
                self.last = dict(stage=self.stage, sensor_wait=True, measured=self.measured,
                                 tracking='waiting for fresh Roomba sensors', velocity_mm_s=0)
                return
        if hard_stop or transient:
            reasons = []
            if state.get('oi_stopped'): reasons.append('Roomba Open Interface is stopped; restart OI')
            reasons.extend(r.replace('_', ' ') for r in self.mission._hard_hazard_reasons(state))
            if contact:
                sides = [side for side in ('left', 'right') if getattr(sensors.bumps_and_wheel_drops, 'bump_'+side)]
                reasons.append(' and '.join(sides)+' bumper pressed')
            if state.get('safety_latched'): reasons.append('Roomba safety stop is latched')
            if state.get('motion_lease_expired'): reasons.append('motor command lease expired')
            if state.get('battery_status') in ('low', 'critical', 'charging'):
                reasons.append('Roomba battery status is '+state['battery_status'])
            if not state.get('ready'): reasons.append('Roomba sensors are not ready')
            if age is None: reasons.append('Roomba sensor age is unavailable')
            elif not 0 <= age <= .5: reasons.append('Roomba sensor age {:.2f} seconds exceeds 0.50 second limit'.format(age))
            self.abort('; '.join(reasons))
            return
        if self.sensor_wait_started is not None:
            baseline = self.sensor_wait_pose
            if now-self.sensor_wait_started > 1.0:
                self.abort('parked sensor requalification exceeded one second')
                return
            if (state.get('odometry_epoch') != baseline[0]
                    or abs(float(state['distance'])-baseline[1]) > 10
                    or abs(float(state['angle'])-baseline[2]) > 1):
                self.abort('robot moved or odometry reset during parked sensor requalification')
                return
            self.sensor_wait_started = self.sensor_wait_pose = None
        if now-self.started > 3600:
            self.abort('distance survey exceeded one hour')
            return
        row, health = self._row('latest_grid_observation'), self._row('latest_health_observation')
        # A callback may deliver either snapshot after the tick began. Sample
        # time after both reads; otherwise a new packet looks 'from the future'
        # and fails the nonnegative age guard during an otherwise healthy stream.
        now = monotonic()
        fresh = (row is not None and health is not None
                 and 0 <= now-row['received_monotonic'] <= .5
                 and 0 <= now-row['frame_monotonic'] <= .25
                 and 0 <= now-health['received_monotonic'] <= .5
                 and row['flags'] in (2, 3) and row['reason'] in (0, 1)
                 and (row['session'], row['calibration']) == (health['session'], health['calibration']))
        if not fresh:
            self._pause('GridRunner distance waiting for telemetry')
            if self.stage == 'waiting' and now-self.started < 10:
                return
            details = []
            if row is None: details.append('no GridRunner line telemetry')
            else:
                details.extend(['line receipt age {:.2f} seconds'.format(now-row['received_monotonic']),
                                'camera frame age {:.2f} seconds'.format(now-row['frame_monotonic']),
                                'tracking flags {}, reason {}'.format(row['flags'], row['reason'])])
            if health is None: details.append('no phone health telemetry')
            else: details.append('phone health age {:.2f} seconds'.format(now-health['received_monotonic']))
            if row is not None and health is not None and (row['session'],row['calibration']) != (health['session'],health['calibration']):
                details.append('line and health sessions or calibrations do not match')
            self.abort('phone telemetry invalid: '+ '; '.join(details))
            return
        identity = (row['session'], row['calibration'], row['direction'], row['gain'], row['correction_limit'], row['lens_left_mm'], row['height_mm'])
        if self.identity is None:
            if row['direction'] != -1 or row['flags'] != 3 or row['confidence'] < .65:
                if now-self.started > 10:
                    self.abort('reverse direction and clear grout line required')
                return
            self.identity = identity
            self.epoch = state['odometry_epoch']
            self.origin = float(state['distance'])
            self.initial_heading = float(state['angle'])
            self.odom = self.origin, self.initial_heading
            self.bump_count = health['bump_count']
            self.bump_policy.baseline(health)
            self._begin_scan()
        if (self.stage in ('scanning', 'awaiting_measure') and self.station_distance is not None
                and abs(float(state['distance'])-self.station_distance) > 10):
            self.abort('robot moved during stationary measurement')
            return
        if identity != self.identity or state['odometry_epoch'] != self.epoch:
            self.abort('phone configuration/session or odometry changed')
            return
        event = self.bump_policy.observe(health, self._ignore_speed_bump)
        self.bump_count = health['bump_count']
        if event is not None:
            self.mission.logger.info('Distance survey phone impact policy: %s', dict(event, stage=self.stage))
            if event['action'] == 'react':
                self.abort('phone impact during distance survey')
                return
        if not self._integrate(state):
            return
        if abs(float(state['angle'])-self.initial_heading) > 10:
            self.abort('heading deviated more than 10 degrees')
            return
        self.last = dict(stage=self.stage, station=self.station,
                         wheel_distance_mm=float(state['distance'])-self.origin,
                         tiles=row.get('crossing_count', 0), measured=self.measured,
                         confidence_retries=self.confidence_retries, confidence_hold=self.confidence_hold,
                         crossing_retries=self.crossing_retries, skipped_crossings=self.skipped_crossings, recovering=self.recovery_origin is not None)
        if self.stage == 'settling':
            if now-self.station_at >= 1:
                self.station_distance = float(state['distance'])
                self.stage = 'scanning'
                self.scan_wall, self.scan_started = time(), now
                self.mission.camera.request_scan()
            return
        if self.stage == 'scanning':
            captured = self.mission.camera.last_detection_time
            if isinstance(captured, (int, float)) and captured >= self.scan_wall and not scan_active:
                tags = [r for r in self.mission.camera.latest_detections if r.get('id') == 15 and r.get('family', 'tag16h5') == 'tag16h5']
                tag = max(tags, key=lambda r:r.get('decision_margin', 0), default={})
                margin = tag.get('decision_margin', 0)
                error = (tag.get('tag_pose_camera') or {}).get('error', float('inf'))
                distance = tag.get('distance_mm')
                clear = (tag.get('hamming') == 0 and margin >= 20 and 0 <= error <= 5
                         and isinstance(distance, (int, float)) and math.isfinite(distance) and distance > 0)
                if clear and self.pose is None:
                    pose = self._tag_fix([tag])
                    if pose and pose.get('accepted_tag_ids'):
                        self.pose = {key: float(pose[key]) for key in ('x_mm', 'y_mm', 'heading_rad')}
                        self.mission.logger.info('Distance survey map anchored at station %d: %s',
                                                 self.station, self.pose)
                rec = dict(station=self.station, captured_at=captured, clear=clear,
                           camera_distance_mm=distance, depth_mm=tag.get('depth_mm'),
                           raw_camera_distance_mm=tag.get('raw_distance_mm', distance),
                           pose_translation_scale=tag.get('pose_translation_scale', 1.0),
                           tag=tag, wheel_distance_mm=float(state['distance'])-self.origin,
                           wheel_heading_deg=float(state['angle']),
                           crossing_count=row.get('crossing_count', 0), tape_mm=None,
                           expected_mm=(None if self.autonomous else self.start_mm+self.station*self.tile_mm),
                           autonomous=self.autonomous,
                           skipped_crossings=self.skipped_crossings,
                           crossing_relative_mm=(None if self.first_crossing_distance is None or self.skipped_crossings else
                               (self.station-1)*self.tile_mm),
                           crossing_pitch_min_mm=305.2, crossing_pitch_max_mm=305.7)
                self.records.append(rec)
                self.mission.logger.info('GridRunner distance station: %s', json.dumps(rec, sort_keys=True))
                self.stop_reason = self.stop_reason or (None if clear else 'tag 15 missing or no longer clear')
                self.stage = 'awaiting_measure'
                if self.autonomous:
                    if self.stop_reason:
                        self.stage = 'complete'
                        self.result = dict(status='complete', reason=self.stop_reason, stations=self.records)
                        self.mission.set_mode('idle')
                    else:
                        try:
                            self.advance()
                        except ValueError as error:
                            self.abort(str(error))
                    return
                self._announce('Station {}. {} Please record the tape distance.'.format(self.station, 'Tag fifteen clear.' if clear else 'Tag fifteen unclear. Survey ending.'))
            elif now-self.scan_started > 20:
                self.abort('tag scan timeout')
            return
        if self.stage != 'stepping':
            return
        line_visible = row['flags'] == 3
        low_confidence = row['confidence'] < .65
        if not line_visible and not self.autonomous:
            self.abort('phone lost the grout line; tracking flags {}, reason {}'.format(row['flags'], row['reason']))
            return
        if not line_visible or self.line_loss_started is not None:
            self._recover_lost_line(row, state, now, line_visible, low_confidence)
            return
        travel = self.step_origin-float(state['distance'])
        total = self.origin-float(state['distance'])
        crossing = (row.get('crossing_count', 0)-self.step_count) & 0xffffffff
        if self.autonomous and total+self.start_mm >= 5000:
            self.abort('5 m wheel estimate reached')
            return
        if self.confidence_hold:
            if low_confidence:
                return  # Remain stopped, retaining this run and its evidence.
            self.confidence_hold = False
            self.confidence_retries = 0
            self.confidence_return_to = None
            self.station_at = now
            self.mission.robot_control.begin_motion_lease(.6)
            self._announce('Grout line confidence recovered. Continuing the calibration run.')
        if (self.autonomous and row['flags'] == 3 and low_confidence
                and self.recovery_origin is None
                and (self.confidence_return_to is None or float(state['distance']) <= self.confidence_return_to)):
            detail = 'Grout line confidence {:.3f} is below required 0.650'.format(row['confidence'])
            self._pause(detail)
            self.station_at = now
            if self.confidence_retries >= 2:
                self.confidence_hold = True
                self._announce(detail+'. Two fifty millimetre retries completed. Holding position until line confidence recovers; the run is still active.')
                return
            self.confidence_retries += 1
            self.confidence_return_to = float(state['distance'])
            self.recovery_origin = float(state['distance'])
            self.mission.robot_control.begin_motion_lease(.6)
            self._announce(detail+'. Moving forward fifty millimetres, then retrying slowly in reverse. Attempt {} of two.'.format(self.confidence_retries))
            return
        if self.autonomous and self.confidence_return_to is None and self.recovery_origin is None and travel > self.search_limit_mm and crossing == 0:
            self._pause('Missed crossing: stop before 50 mm forward recovery')
            if self.crossing_retries >= 2:
                self.skipped_crossings += 1
                self.search_limit_mm += self.tile_mm
                self.crossing_retries = 0
                self.station_at = now
                self.mission.logger.info('GridRunner skipping missed crossing: %s', self.skipped_crossings)
                self._announce('Crossing still missing after two retries. Skipping it and continuing to the next crossing.')
                self.mission.robot_control.begin_motion_lease(.6)
                return
            self.crossing_retries += 1
            self._announce('Crossing not detected. Moving forward fifty millimetres, then retrying in reverse. Attempt {} of two.'.format(self.crossing_retries))
            self.recovery_origin = float(state['distance'])
            self.station_at = now
            self.mission.robot_control.begin_motion_lease(.6)
            return
        recovering = self.recovery_origin is not None
        if recovering and float(state['distance']) - self.recovery_origin >= 50:
            self._pause('50 mm recovery complete: reverse to recheck crossing')
            self.recovery_origin = None
            self.station_at = now
            # Ignore counts from the forward recovery leg; the next reverse
            # crossing must be observed afresh by the phone state machine.
            self.step_count = row.get('crossing_count', 0)
            self.mission.robot_control.begin_motion_lease(.6)
            return
        if not recovering and (total+self.start_mm >= 5000 or 0 < crossing < 0x80000000
                or (not self.autonomous and travel >= self.tile_mm)):
            if self.autonomous and crossing == 0:
                self.abort('5 m wheel estimate reached before crossing')
                return
            if self.autonomous and 1 < crossing < 0x80000000:
                self.skipped_crossings += crossing - 1
            if self.first_crossing_distance is None:
                self.first_crossing_distance = float(state['distance'])
            self.station += 1
            self._begin_scan()
            if total+self.start_mm >= 5000:
                self.stop_reason = '5 m wheel estimate reached'
            return
        confidence_recovery = self.confidence_return_to is not None
        if travel < -20 and not recovering and not confidence_recovery:
            self.abort('wrong travel direction: {:.0f} millimetres forward from reverse step start'.format(-travel))
            return
        if now-self.station_at > 20:
            self.abort('crossing search timed out after 20 seconds; reverse travel {:.0f} millimetres'.format(travel))
            return
        if low_confidence and not (self.autonomous and (recovering or confidence_recovery)):
            self.abort('grout line confidence {:.3f} is below required 0.650; reverse travel {:.0f} millimetres'.format(row['confidence'], travel))
            return
        direction = 1 if recovering else -1
        correction = grid_correction(row['offset_mm'], row['line_angle_rad'], direction,
                                     2*row['gain'], min(.35, row['correction_limit']), row['lens_left_mm'])
        if low_confidence:
            correction = 0.0  # Never steer from an unreliable visual line in the bounded retrace.
        elif not recovering:
            self.confidence_return_to = None
        speed = MIN_WHEEL_SPEED if recovering else -MIN_WHEEL_SPEED if self.crossing_retries or self.confidence_retries else -70
        self._drive_tile(speed, correction, 'GridRunner distance tile step')
