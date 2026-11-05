"""Standalone tag-15 homing from a fresh fix or a still-valid wheel trace."""
# @(#)roomberry_tag_return.py 3.1.grout.17 2026/11/05
import math
from time import monotonic, time
from roomberry_gridrunner import GridDrive, GRID_PIVOT_SPEED


class Tag15Return(GridDrive):
    kind = 'return_to_tag15'

    def __init__(self, mission, state, prior=None):
        super().__init__(mission)
        row = self._row('latest_grid_observation')
        if row is not None and 0 <= monotonic()-row.get('received_monotonic', -1e9) <= .5:
            self.target_offset_mm = float(row['lens_left_mm'])
        elif prior is not None:
            self.target_offset_mm = prior.target_offset_mm
        self._seed_pose()  # Read the surveyed target, without assuming our location.
        if self.tag is None:
            raise RuntimeError('Tag 15 has no surveyed position')
        self.pose = None
        self.identity = ('tag15-return', 0)
        self.origin = self.last_distance = float(state['distance'])
        self.initial_heading = self.hold_heading = self.progress_heading = float(state['angle'])
        self.epoch = state.get('odometry_epoch')
        self.odom = (float(state['distance']), float(state['angle']))
        self.outbound_mm = 0.
        self.checkpoints = []
        self.all_tag_localizer = None
        self.route = []
        self.fix_candidate = None
        self.fix_attempts = 0
        self.scan_purpose = 'localize'
        self.search_origin = float(state['angle'])
        self.search_index = 0
        self.search_target = None
        self.distance_at_scan = float(state['distance'])
        self.distance_at_fix = float(state['distance'])
        self.turning = False
        self.turn_control.reset()
        self.phone_identity = self.phone_bumps = None
        self.grout_source = None
        self.line_frames = 0
        self.line_seq = None
        self.prior_valid = False
        if (prior is not None and prior.pose is not None and prior.epoch == self.epoch
                and prior.odom is not None and abs(state['distance']-prior.odom[0]) <= 150
                and abs(math.radians(state['angle']-prior.odom[1])) <= .3):
            self.pose = dict(prior.pose)
            delta = state['distance']-prior.odom[0]
            yaw = math.radians(state['angle']-prior.odom[1])
            middle = self.pose['heading_rad']+yaw/2
            self.pose['x_mm'] += delta*math.cos(middle)
            self.pose['y_mm'] += delta*math.sin(middle)
            self.pose['heading_rad'] = self._wrap(self.pose['heading_rad']+yaw)
            self.prior_valid = True

    def _resume_visible_line(self, state, health, scan_active):
        row = self._row('latest_grid_observation')
        now = monotonic()
        known_homeward = (self.pose is not None and
            abs(self._wrap(self.pose['heading_rad']-self.tag['heading'])) <= .35)
        if self.grout_source is not None and self.grout_source.initial_heading is not None:
            known_homeward = known_homeward or abs(self._wrap(math.radians(
                state['angle']-self.grout_source.initial_heading))) <= .35
        good = (not scan_active and self.stage != 'scanning' and self.pose is not None
                and (self.tag_fix_applied or self.prior_valid)
                and known_homeward
                and row is not None and row['flags'] == 3 and row['confidence'] >= .75
                and row['direction'] == -1
                and (row['session'],row['calibration']) == (health['session'],health['calibration'])
                and 0 <= now-row['received_monotonic'] <= .5
                and 0 <= now-row['frame_monotonic'] <= .25)
        if not good:
            self.line_frames = 0
            self.line_seq = None
            return False
        if row['seq'] != self.line_seq:
            self.line_seq = row['seq']
            self.line_frames += 1
        if self.line_frames < 3:
            if self.line_frames == 1:
                self.mission._send_stop('qualifying visible homeward grout line', force=True)
                self.turn_control.reset()
            self.mission.robot_control.renew_motion_lease(.6)
            return True
        self._pause('Tag homing stopped to resume grout line')
        source = self.grout_source
        if source is None:
            source = GridDrive(self.mission)
            source.origin = float(state['distance'])
            source.started = self.started
            source.observation_started = self.started
        source.resume_line_return(self, state, row, health)
        return True

    def start(self):
        self._request_fix('localize')

    def _request_fix(self, purpose):
        self._pause('Return to tag 15 stationary '+purpose+' scan')
        if purpose != self.scan_purpose:
            self.fix_candidate = None
            self.fix_attempts = 0
            self._relocation_pending = False
        self.scan_purpose = purpose
        self.stage = 'scanning'
        self.fix_attempts += 1
        self.scan_started, self.scan_wall = monotonic(), time()
        self.mission.camera.request_scan()

    def _fix(self, detections):
        if self.scan_purpose == 'final':
            return self._tag_fix(detections)
        from roomberry_localization import AprilTagLocalizer
        source = self.mission.localizer
        if not isinstance(getattr(source, 'landmarks', None), dict):
            return None
        if self.all_tag_localizer is None:
            self.all_tag_localizer = AprilTagLocalizer(source.landmarks, source.camera_from_robot,
                max_tag_distance_m=2.5, max_reprojection_error=source.max_reprojection_error,
                min_decision_margin=source.min_decision_margin, room_bounds_mm=source.room_bounds_mm)
        self.all_tag_localizer.invalidate_pose()
        return self.all_tag_localizer.update(tuple(detections), 0, 0)

    def _scan_result(self, state):
        captured = self.mission.camera.last_detection_time
        if not isinstance(captured, (float, int)) or captured < self.scan_wall:
            if monotonic()-self.scan_started > 30:
                self.abort('return localization scan timed out; robot remains stopped')
            return
        pose = self._fix(self.mission.camera.latest_detections)
        valid = pose is not None and bool(pose.get('accepted_tag_ids'))
        innovation = None
        if valid and self.tag_fix_applied and self.pose is not None:
            innovation = (math.hypot(pose['x_mm']-self.pose['x_mm'], pose['y_mm']-self.pose['y_mm']),
                          abs(self._wrap(pose['heading_rad']-self.pose['heading_rad'])))
        if innovation is not None and (innovation[0] > 200 or innovation[1] > math.radians(8)):
            self._relocation_pending = True
        consistent = (valid and self.fix_candidate is not None and
            math.hypot(pose['x_mm']-self.fix_candidate['x_mm'], pose['y_mm']-self.fix_candidate['y_mm']) <= 75 and
            abs(self._wrap(pose['heading_rad']-self.fix_candidate['heading_rad'])) <= math.radians(4))
        reason = 'confirmed' if consistent else 'confirming pose' if valid else 'no reliable mapped tag'
        if consistent and getattr(self, '_relocation_pending', False):
            reason = 'stationary relocation confirmed despite odometry discrepancy'
        self.records.append(dict(purpose=self.scan_purpose, attempt=self.fix_attempts,
            accepted=bool(consistent), pose=pose, reason=reason, innovation=innovation))
        self.mission.logger.info('Return to tag 15 scan: %s', self.records[-1])
        self.mission._button_beep('happy' if consistent else 'neutral' if valid else 'unhappy')
        self.mission._shutdown.wait(.35)
        self.fix_candidate = dict(pose) if valid else None
        if consistent:
            self.pose = {key:float(pose[key]) for key in ('x_mm','y_mm','heading_rad')}
            self.tag_fix_applied = True
            self.prior_valid = True
            self._relocation_pending = False
            self.odom = (float(state['distance']), float(state['angle']))
            self.distance_at_scan = float(state['distance'])
            self.distance_at_fix = float(state['distance'])
            self.fix_attempts = 0
            self.fix_candidate = None
            if self.scan_purpose == 'final':
                h = self.tag['heading']
                dx, dy = self.tag['x']-self.pose['x_mm'], self.tag['y']-self.pose['y_mm']
                gap = dx*math.cos(h)+dy*math.sin(h)
                lateral = -dx*math.sin(h)+dy*math.cos(h)
                if gap < self.tag['radius']-50 or abs(lateral-self.target_offset_mm) > 150:
                    self.abort('tag pose is outside the final approach corridor; reposition before retrying')
                    return
                self.final_fix = True
                self.last_tag_distance = float(state['distance'])
                self.stage = 'approach'
            else:
                self.stage = 'return'
                self._plan_route()
                if self.result is not None:
                    return
            self._begin_motion(state)
            return
        if self.fix_attempts < 3 and (valid or getattr(self, '_relocation_pending', False) or self.scan_purpose == 'final'):
            self._request_fix(self.scan_purpose)
            return
        # A known, continuous trace can bridge a distant/out-of-view tag. A
        # carried/restarted robot cannot use that fallback.
        if getattr(self, '_relocation_pending', False):
            self.abort('stationary relocation could not be confirmed; robot remains stopped')
            return
        if self.scan_purpose != 'final' and self.prior_valid and not valid:
            if self.tag_fix_applied and abs(state['distance']-self.distance_at_fix) >= 1200:
                self.abort('tag return lost localization after 1200 mm without a new fix')
                return
            self.stage = 'return'
            self.fix_attempts = 0
            self._plan_route()
            if self.result is None:
                self.distance_at_scan = float(state['distance'])
                self._begin_motion(state)
            return
        if self.scan_purpose == 'final' or valid:
            self.abort('no consistent return localization; robot remains stopped')
            return
        if self.search_index >= 7:
            self.abort('no mapped tag found after a full heading search; reposition for a visible tag')
            return
        self.search_index += 1
        self.search_target = self.search_origin+45*self.search_index
        self.fix_attempts = 0
        self.fix_candidate = None
        self.stage = 'searching'
        self._begin_motion(state)

    def _begin_motion(self, state):
        self.progress_at = monotonic()
        self.last_distance = float(state['distance'])
        self.progress_heading = float(state['angle'])
        self.turning = False
        self.turn_control.reset()
        self.mission.robot_control.begin_motion_lease(.6)

    def _target(self, gap):
        h, offset = self.tag['heading'], self.target_offset_mm
        return (self.tag['x']-gap*math.cos(h)+offset*math.sin(h),
                self.tag['y']-gap*math.sin(h)-offset*math.cos(h))

    def _plan_route(self):
        goal = self._target(self.tag['radius']+400)
        # Already in the front approach corridor: acquire a final tag-15 fix.
        h = self.tag['heading']
        dx, dy = self.tag['x']-self.pose['x_mm'], self.tag['y']-self.pose['y_mm']
        gap = dx*math.cos(h)+dy*math.sin(h)
        lateral = -dx*math.sin(h)+dy*math.cos(h)
        if self.tag['radius']-50 <= gap <= 750 and abs(lateral-self.target_offset_mm) <= 150:
            self.route = []
            return
        self.mission.mapper.update_pose(self.pose['x_mm'], self.pose['y_mm'],
                                         self.pose['heading_rad'], localized=True, persist=False)
        plan = self.mission.mapper.plan_to(*goal)
        if not isinstance(plan, dict) or not plan.get('path'):
            self.abort('no clear mapped route to tag 15 approach point')
            return
        self.route = [self.mission.mapper.cell_center(cell) for cell in plan['path'][1:]]
        if self.route:
            self.route[-1] = goal
        else:
            self.route = [goal]
        # The cell-count planner may choose diagonal zigzags in open space.
        # Shortcut only segments whose complete swept footprint checks clear.
        remaining, route = self.route, []
        anchor = dict(self.pose)
        while remaining:
            chosen = 0
            for index in range(len(remaining)-1, 0, -1):
                x, y = remaining[index]
                distance = math.hypot(x-anchor['x_mm'], y-anchor['y_mm'])
                heading = math.atan2(y-anchor['y_mm'], x-anchor['x_mm'])
                if self.mission.mapper.motion_is_clear(dict(anchor, heading_rad=heading),
                        50, 0, max(.01,distance/50)) is True:
                    chosen = index
                    break
            point = remaining[chosen]
            route.append(point)
            anchor.update(x_mm=point[0], y_mm=point[1])
            remaining = remaining[chosen+1:]
        self.route = route
        self.mission.logger.info('Tag return planned route: pose=%s goal=%s waypoints=%s', self.pose, goal, route)

    def tick(self, state, scan_active=False):
        now = monotonic()
        self.mission._set_cleaning_motors(False)
        sensors = state.get('sensors')
        if (not state.get('ready') or state.get('age') is None or not 0 <= state['age'] <= .5
                or sensors is None or state.get('oi_stopped') or self.mission._hard_hazard_reasons(state)):
            self.abort('return blocked by stale sensors or a hard safety stop')
            return
        if not self._integrate(state):
            return
        bumps = sensors.bumps_and_wheel_drops
        if (bumps.bump_left or bumps.bump_right) and self._expected_contact():
            self.stage = 'complete'
            self.result = dict(status='complete', reason='tag 15 front bumper contact', final_pose=dict(self.pose))
            self.mission.set_mode('idle')
            return
        if (bumps.bump_left or bumps.bump_right or state.get('safety_latched')
                or state.get('motion_lease_expired') or state.get('battery_status') in ('low','critical','charging')):
            self.abort('return blocked by bumper, safety latch, motion lease or battery state')
            return
        if now-self.started > 600:
            self.abort('return to tag 15 timed out')
            return
        health = self._row('latest_health_observation')
        if health is not None and 0 <= now-health.get('received_monotonic', -1e9) <= .5:
            identity = (health['session'], health['calibration'])
            event = self.bump_policy.observe(health, self._ignore_speed_bump)
            if event is not None:
                self.mission.logger.info('Tag return phone impact policy: %s', dict(event,stage=self.stage))
            if event is not None and event['action'] == 'react':
                self.mission.robot_control.set_bump_indicator(True)
                self.abort('phone impact detected during tag return')
                return
            self.phone_identity, self.phone_bumps = identity, health['bump_count']
            if self._resume_visible_line(state, health, scan_active):
                return
        if self.stage == 'scanning':
            if not scan_active:
                self._scan_result(state)
            elif now-self.scan_started > 30:
                self.abort('return localization scan timed out')
            return
        if scan_active:
            self.abort('unexpected camera scan interrupted tag return')
            return
        if (abs(state['distance']-self.last_distance) >= 2 or
                abs(state['angle']-self.progress_heading) >= .5):
            self.progress_at, self.last_distance, self.progress_heading = now, state['distance'], state['angle']
        elif now-self.progress_at > 3:
            self.abort('no wheel progress during tag return')
            return
        if self.stage == 'searching':
            error = math.radians(self.search_target-state['angle'])
            if abs(error) <= math.radians(2):
                self._request_fix('localize')
                return
            speed = 0
            self.turning = True
        elif self.stage == 'aiming':
            desired = math.atan2(self.tag['y']-self.pose['y_mm'], self.tag['x']-self.pose['x_mm'])
            error = self._wrap(desired-self.pose['heading_rad'])
            if abs(error) <= math.radians(2):
                self._request_fix('final')
                return
            speed = 0
            self.turning = True
        else:
            if self.stage == 'return':
                if (abs(state['distance']-self.distance_at_scan) >= 400 or
                        (self.tag_fix_applied and abs(state['distance']-self.distance_at_fix) >= 1200)):
                    self._request_fix('localize')
                    return
                while self.route and math.hypot(self.route[0][0]-self.pose['x_mm'], self.route[0][1]-self.pose['y_mm']) < 60:
                    self.route.pop(0)
                if not self.route:
                    self.stage = 'aiming'
                    self.turning = True
                    return
                target = self.route[0]
            else:
                target = self._target(self.tag['radius'])
                if self._range(state) < self.tag['radius']-50 or state['distance']-self.last_tag_distance > 750:
                    self.abort('tag return final approach exceeded its bounded travel')
                    return
            dx, dy = target[0]-self.pose['x_mm'], target[1]-self.pose['y_mm']
            desired = self.tag['heading'] if self.stage == 'approach' and math.hypot(dx,dy) <= 50 else math.atan2(dy,dx)
            error = self._wrap(desired-self.pose['heading_rad'])
            speed = 20 if self.stage == 'approach' else 50
        self.turning = abs(error) > math.radians(2 if self.turning else 5)
        if self.turning:
            sign = 1 if error > 0 else -1
            left, right, speed = -sign*GRID_PIVOT_SPEED, sign*GRID_PIVOT_SPEED, 0
            action = dict(kind='turn', velocity=GRID_PIVOT_SPEED, steering=sign)
        else:
            left = right = speed
            action = dict(kind='drive', velocity=speed, steering=0)
        if self.pose is not None and (self.stage != 'approach' or self._range(state) > self.tag['radius']+200):
            clear = self.mission.mapper.motion_is_clear(self.pose, speed,
                (right-left)/235., .6)
            if clear is not True:
                self.abort('mapped obstacle blocks return motion')
                return
        turn_sign = (1 if error > 0 else -1) if self.turning else None
        ready = self.turn_control.prepare(state, turn_sign, error)
        if self.turn_control.error:
            self.abort('tag return '+self.turn_control.error)
            return
        if not ready:
            left = right = speed = 0
        self.last = dict(stage=self.stage, tracking='tag return', steering_mode='settling' if not ready else 'pivot' if self.turning else 'straight',
            heading_error_rad=error, velocity_mm_s=speed, left_velocity_mm_s=left,
            right_velocity_mm_s=right, wheel_distance_mm=state['distance']-self.origin,
            wheel_heading_deg=state['angle'], tag_distance_mm=None if self.pose is None else self._range(state),
            offset_mm=None, tracking_error_mm=None, correction=0, tag_fix_applied=self.tag_fix_applied)
        self.mission.logger.info('Return to tag 15 sample: %s', self.last)
        try:
            self.mission.robot_control.renew_motion_lease(.6)
        except RuntimeError:
            self.abort('tag return motion lease expired')
            return
        if ready:
            self.mission._dispatch(dict(action,reason='Return to tag 15 '+self.stage,
                                        continuous=True,max_duration_s=.6), None)
            if self.mission._active_command is not None:
                self.turn_control.dispatched(turn_sign)
