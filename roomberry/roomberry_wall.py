"""Bounded right-wall survey drive; regulate right light-bumper intensity in a 20-30 band."""
# @(#)roomberry_wall.py 3.2 2026/11/09 18:53:01
import json
import uuid
from math import isfinite, hypot, cos, sin, radians, atan2, pi
from time import monotonic, time
from types import SimpleNamespace
from roomberry_turn_guard import SettledTurn
from roomberry_control import WallContactStop
from roomberry_trek_anchor import TrekTagAnchor

MODE_WALL = 'wall'
WALL_TARGET_SIGNAL = 30.
WALL_TARGET_MIN = 20.
WALL_TARGET_MAX = 30.
WALL_TARGET_CENTER = 25.
WALL_FLUCTUATION_MAX = 20.
WALL_FLUCTUATION_HOLD_S = 1.0
WALL_MAX_REAPPROACHES = 4
WALL_MAX_CONTACT_RECOVERIES = 42
WALL_SIGNAL_AVG_N = 4
WALL_REAPPROACH_MM = 50.
WALL_REJOIN_MAX_RIGHT_DEG = 30.
WALL_WALL_LOSS_MAX_RIGHT_DEG = 60.
WALL_WALL_LOSS_TURN_STEP_DEG = 10.
WALL_MIN_WHEEL_SPEED = 50
WALL_CRUISE_SPEED = 80
WALL_TAG15_RADIUS_MM = 300.
WALL_TAG15_ACQUIRE_MAX_MM = 2500.
WALL_TAG15_MAX_STEPS = 24
WALL_TAG15_LOOK_OFFSETS_DEG = (0.,10.,-10.)
WALL_TAG15_LOOK_MAX_S = 75.
WALL_MAX_PATH_MM = 8000.
WALL_DETOUR_MAX_MM = 1500.
WALL_DETOUR_MAX_S = 90.
WALL_BYPASS_FIRST_LEFT_DEG = 20.
WALL_BYPASS_LEFT_DEG = 45.
WALL_GO_AROUND_WINDOW_MM = 500.
WALL_SENSOR_LOSS_SEARCHES = 8
WALL_TAG_SCAN_MM = 5000.
WALL_CONTACT_BACKOFF_MM = 30.
WALL_CONTACT_MAX_BACKOFF_MM = 50.
WALL_SENSOR = 'light_bump_right_signal'


class WallDrive:
    def __init__(self, mission):
        self.mission = mission
        self.phone_status = mission.trek_survey_status
        self.stage = 'phone_ready' if self.phone_status is not None else 'anchor'
        self.started = monotonic()
        self._wall_time = time()
        self.startup_deadline = self.started + 120
        self.motion_started = None
        self._startup_reported_status = None
        self._startup_stop_confirmed = False
        self.deadline = self.startup_deadline if self.phone_status is not None else self.started + 60
        self.result = None
        self.last = None
        self.epoch = None
        self.previous = None
        self.origin = None
        self.anchor = None
        self.anchor_capture = None
        self.last_scan_request = 0
        self.stage_distance = self.stage_angle = 0
        self.total_mm = 0
        self.progress = None
        self.progress_at = self.started
        self.signal_count = 0
        self.follow_signal = None
        self.sensor_sample = None
        self.signal_history = []
        self.signal_history_sample = None
        self.lease = False
        self.last_drive = None
        self.records = []
        self.acquire_origin = None
        self.acquire_deadline = None
        self.acquire_heading = None
        self.reapproaches = 0
        self.contact_retries = 0
        self.follow_heading = None
        self.loss_searches = 0
        self.rejoin_source = None
        self.rejoin_ready = False
        self.rejoin_settle_frames = 0
        self.rejoin_phase = None
        self.rejoin_step_angle = None
        self.rejoin_advance_distance = None
        self.contact_left_deg = 15.
        self.detour_active = False
        self.detour_started = None
        self.detour_start_mm = None
        self.detour_heading = None
        self.acquire_min_distance = None
        self.alignment_origin = None
        self.alignment_values = []
        self.fluctuation_hold_until = None
        self.last_loss_mm = None
        self.tag_scan_anchor = None
        self.tag_scan_capture = None
        self.tag_scan_started = None
        self.goal_pose = None
        self.goal_odom = None
        self.direction_reference = None
        self.direction_sample = None
        self.direction_pending = False
        self.validation_started = None
        self.validation_steps = 0
        self.approach_mm = None
        self.tag15_search = None
        self.tag15_search_used = False
        self.tag15_localizer = None
        # Stop through WALL's acknowledged-stop/lease owner, not the shared
        # mission helper that deliberately catches actuator exceptions.
        adapter = SimpleNamespace(logger=mission.logger,
            _send_stop=lambda reason, **kwargs: self.stop_motion(reason))
        self.scan_turn = SettledTurn(adapter, lambda: monotonic(), max_pulse_s=.12)
        target = self.mission.discovery_landmarks.get(15, {}).get('world_from_tag')
        self.goal_target = None if target is None else (float(target[0][3])*1000, float(target[1][3])*1000)
        config = self.mission.trek_alignment_config
        self.phone_anchor = None
        if self.mission.navlink is not None and config.get('enabled', True):
            self.phone_anchor = TrekTagAnchor(self.mission.navlink,self.mission.logger,
                                             **{k:config[k] for k in ('mount_yaw_deg','mount_pitch_deg','heading_basis','lens_x_mm','lens_y_mm') if k in config})

    def start_tag15_search(self, state):
        bumps=state['sensors'].bumps_and_wheel_drops
        if (self.tag15_search_used or bumps.bump_left or bumps.bump_right
                or state.get('wall_contact_blocked') or state.get('safety_latched')):
            self.abort('bypass bound reached; tag15 look unavailable with contact/safety latch or repeated attempt')
            return
        self.stop_motion('bypass bound; one stopped tag15 look before abort')
        self.tag15_search_used=True
        self.detour_active=False  # bypass ends here; no further wall following
        self.validation_started=monotonic()
        self.tag15_search=dict(origin_angle=state['angle'],origin_distance=state['distance'],
                               index=0,captures=0,last_capture=None,started=monotonic())
        self.record('tag15_lucky_started',offsets_deg=WALL_TAG15_LOOK_OFFSETS_DEG,
                    max_seconds=WALL_TAG15_LOOK_MAX_S,travelled_mm=self.total_mm)
        self.transition('tag15_scan',state,30)
        self.last_scan_request=0

    def advance_tag15_view(self, state):
        search=self.tag15_search
        if search['index']+1>=len(WALL_TAG15_LOOK_OFFSETS_DEG):
            self.abort('tag15 not confirmed at current/+10/-10 degrees; robot remains stopped')
            return
        search['index']+=1;search['captures']=0;search['last_capture']=None
        self.record('tag15_lucky_view',offset_deg=WALL_TAG15_LOOK_OFFSETS_DEG[search['index']])
        self.scan_turn.reset()
        self.transition('tag15_search_turn',state,8)

    def tag15_candidate(self, detections):
        # Same stopped checkpoint solver pattern as GridRunner: expand range
        # only here, preserving normal navigation's existing1.2m range gate.
        from roomberry_localization import AprilTagLocalizer
        source=self.mission.localizer
        if not isinstance(getattr(source,'landmarks',None),dict): return None
        if self.tag15_localizer is None:
            self.tag15_localizer=AprilTagLocalizer(
                {k:v for k,v in source.landmarks.items() if k[1]==15},source.camera_from_robot,
                max_tag_distance_m=WALL_TAG15_ACQUIRE_MAX_MM/1000,
                min_decision_margin=source.min_decision_margin,
                max_reprojection_error=source.max_reprojection_error,room_bounds_mm=source.room_bounds_mm)
        self.tag15_localizer.invalidate_pose()
        return self.tag15_localizer.update(tuple(r for r in detections if int(r.get('id',-1))==15),0,0)

    def goal_range(self, pose=None):
        pose = self.goal_pose if pose is None else pose
        if self.goal_target is None or pose is None: return None
        return hypot(pose['x_mm']-self.goal_target[0], pose['y_mm']-self.goal_target[1])

    def record(self, event, **values):
        row = dict(event=event, stage=self.stage, wall_time=time(), **values)
        self.records.append(row)
        self.records = self.records[-100:]
        speech = {'tag16_anchor':'ANCHOR_OK', 'wall_ir_candidate':'WALL_FOUND',
                  'wall_ir_lost':'WALL_LOST', 'wall_search_started':'SEARCH_WALL',
                  'wall_rejoined':'WALL_BACK', 'left_obstacle_bypass_started':'FRIDGE_AROUND',
                  'contact_stop':'CONTACT_CLEAR', 'obstacle_bypass_heading_resumed':'BYPASS_DONE',
                  'wall_signal_fluctuating':'IR_UNSTEADY', 'tag_scan_triggered':'NEAR_TAG15',
                  'tag15_approach':'TAG15_APPROACH', 'tag15_scan':'TAG15_VALIDATED',
                  'phone_wait':'RECOVER', 'tag15_lucky_started':'NEAR_TAG15', 'tag15_lucky_view':'NEAR_TAG15'}
        code = speech.get(event, 'RUN_DONE' if event == 'finish' and self.result['status']=='complete'
                          else 'RUN_STOPPED' if event == 'finish' else 'STATUS')
        self.mission.logger.info('WALL event: %s', json.dumps(row, sort_keys=True),
                                 extra=dict(speech_code=code, speech_announce=code!='STATUS'))

    def finish(self, reason, status='aborted'):
        self.stage = status
        self.result = dict(status=status, reason=reason, travelled_mm=self.total_mm)
        self.record('finish', **self.result)
        self.mission.set_mode('idle', wake_robot=False)

    def abort(self, reason):
        self.finish(reason)

    def stop_motion(self, reason):
        """Disarm a moving lease only after an acknowledged physical stop."""
        control = self.mission.robot_control
        if self.lease or not self.mission._stop_sent:
            control.execute('stop', timeout=2)
            if self.lease and control.snapshot().get('motion_lease_expired'):
                raise RuntimeError('WALL motion lease expired before acknowledged stop')
        control.end_motion_lease()
        self.lease = False
        self.last_drive = None
        self.direction_reference = None
        self.direction_pending = False
        self.mission._active_command = None
        self.mission._active_until = 0.
        self.mission._stop_sent = True
        self.mission.logger.debug('WALL stopped with motion lease ended: %s', reason)

    def transition(self, stage, state, timeout):
        self.stop_motion('stage transition to '+stage)
        self.stage = stage
        self.deadline = monotonic() + timeout
        self.stage_distance, self.stage_angle = state['distance'], state['angle']
        self.progress = None
        self.progress_at = monotonic()
        self.signal_count = 0
        self.sensor_sample = state.get('sensor_monotonic_s')
        self.signal_history = []
        self.signal_history_sample = state.get('sensor_monotonic_s')
        self.alignment_values = []
        self.fluctuation_hold_until = None
        if stage == 'tag15_scan':
            self.tag_scan_started = time()
            self.tag_scan_anchor = None
            self.tag_scan_capture = None
        if stage == 'acquire' and self.acquire_origin is None:
            self.acquire_origin = float(state['distance'])
            self.acquire_deadline = monotonic()+90
            self.acquire_min_distance = float(state['distance'])
        if stage == 'rejoin':
            self.rejoin_ready = False
            self.rejoin_settle_frames = 0
            self.rejoin_phase = 'turn'
            self.rejoin_step_angle = None
            self.rejoin_advance_distance = None
        if stage == 'follow':
            self.follow_signal = None
            self.follow_heading = float(state['angle'])
        if stage == 'align_left45':
            self.alignment_origin = float(state['angle'])
            self.acquire_heading = float(state['angle'])
        self.record('stage', distance_mm=state['distance'], angle_deg=state['angle'])

    def retry_acquisition(self, state, signal):
        if self.reapproaches >= WALL_MAX_REAPPROACHES:
            self.abort('wall alignment failed after four bounded re-approaches')
            return
        self.reapproaches += 1
        self.record('alignment_signal_lost', signal=signal, retry=self.reapproaches,
                    return_heading_deg=self.acquire_heading,
                    advance_before_signal_mm=WALL_REAPPROACH_MM)
        self.acquire_min_distance = float(state['distance'])+WALL_REAPPROACH_MM
        self.transition('reorient', state, 12)

    def start_rejoin(self, state, source):
        if source == 'wall_loss':
            if self.loss_searches >= WALL_SENSOR_LOSS_SEARCHES:
                self.abort('wall-loss search limit reached')
                return
            self.loss_searches += 1
            self.last_loss_mm = self.total_mm
        self.rejoin_source = source
        timeout = 25 if self.detour_active else 20 if source == 'wall_loss' else 10
        self.transition('rejoin', state, timeout)
        # A new local search has its own limits, independent of the old anchor seek.
        self.acquire_origin = float(state['distance'])
        self.acquire_deadline = monotonic()+timeout+1
        max_right_deg = (90 if self.detour_active
                         else WALL_WALL_LOSS_MAX_RIGHT_DEG if source == 'wall_loss'
                         else WALL_REJOIN_MAX_RIGHT_DEG)
        self.record('wall_search_started', source=source, detour=self.detour_active,
                    max_mm=None, min_wheel_speed=WALL_MIN_WHEEL_SPEED,
                    max_right_deg=max_right_deg)

    def contact_recovery(self, state):
        """Stop first, then back clear and change the next approach heading."""
        self.stop_motion('bumper/contact recovery')
        if self.contact_retries >= WALL_MAX_CONTACT_RECOVERIES:
            self.abort('contact recovery limit reached')
            return
        self.contact_retries += 1
        corner_after_loss = (self.stage == 'follow'
                             and self.loss_searches > 0
                             and self.last_loss_mm is not None
                             and self.total_mm - self.last_loss_mm <= WALL_GO_AROUND_WINDOW_MM)
        obstacle = (self.detour_active
                    or (self.stage == 'rejoin' and self.rejoin_source == 'wall_loss')
                    or corner_after_loss)
        if obstacle:
            # In front of the dishwasher close to the fridge a single 90deg
            # left turn overshoots the recessed front. Try a smaller left
            # turn first; cap repeat-contact turns at45deg to avoid overshoot.
            # Corner contacts in follow soon after a wall-loss search mean
            # the robot hit the cabinet corner head-on and should go
            # around (left-first) instead of retrying the same face.
            self.contact_left_deg = (WALL_BYPASS_LEFT_DEG if self.detour_active
                                     else WALL_BYPASS_FIRST_LEFT_DEG)
        else:
            self.contact_left_deg = 15.
        if obstacle and not self.detour_active:
            self.detour_active = True
            self.detour_started = monotonic()
            self.detour_start_mm = self.total_mm
            self.detour_heading = float(state['angle'])
            self.record('left_obstacle_bypass_started', heading_deg=self.detour_heading,
                        next_left_deg=self.contact_left_deg,
                        corner_after_loss=corner_after_loss,
                        max_path_mm=WALL_DETOUR_MAX_MM, max_seconds=WALL_DETOUR_MAX_S)
        event = state.get('wall_contact_event') or {}
        self.record('contact_stop', source=event.get('reason', 'bumper'),
                    contact_event=event, retry=self.contact_retries, next_left_deg=self.contact_left_deg)
        if self.acquire_origin is None or self.stage in ('follow', 'rejoin'):
            self.acquire_origin = float(state['distance'])
            self.acquire_deadline = monotonic()+(60 if obstacle else 30)
        self.transition('release', state, 5)

    def drive(self, right, left, state):
        # Keep every moving wheel out of the poorly responding low-speed range.
        right, left = (0 if int(v) == 0 else (1 if v > 0 else -1)*max(WALL_MIN_WHEEL_SPEED, abs(int(v)))
                       for v in (right, left))
        axis = 'angle' if right * left < 0 else 'distance'
        value = state[axis]
        if self.progress is None or abs(value-self.progress) >= (.3 if axis == 'angle' else 2):
            self.progress, self.progress_at = value, monotonic()
        elif monotonic()-self.progress_at > 2:
            self.abort('no wheel progress for two seconds')
            return
        control = self.mission.robot_control
        if not self.lease:
            control.begin_motion_lease(.6)
            self.lease = True
        else:
            control.renew_motion_lease(.6)
        self.mission._stop_sent = False
        try:
            control.execute('drive_direct', right_velocity=int(right), left_velocity=int(left), ramp=False)
        except WallContactStop as error:
            # Contact can arrive after tick's snapshot but before the owner runs
            # this command. Re-check every guard before any retreat is permitted.
            fresh = control.snapshot()
            if not fresh.get('wall_contact_blocked'):
                raise
            self.record('contact_preempted_drive', error=str(error))
            if self.guard(fresh):
                self.contact_recovery(fresh)
            return
        signature = lambda pair: tuple(0 if v==0 else (1 if v>0 else -1) for v in pair)
        if self.last_drive is None or signature(self.last_drive) != signature((right,left)):
            self.direction_pending = True
            self.direction_sample = state.get('sensor_monotonic_s')
            self.direction_reference = None
        self.last_drive = (right, left)
        if self.last is not None:
            self.last.update(right_velocity_mm_s=int(right), left_velocity_mm_s=int(left))
            self.mission.logger.info('WALL drive: %s', json.dumps(dict(self.last, wall_time=time())))

    def guard(self, state):
        age = state.get('age')
        if state.get('motion_lease_expired'):
            self.abort('WALL motion lease expired during movement')
            return False
        if (not state.get('ready') or age is None or not 0 <= age <= .5
                or state.get('oi_stopped') or state.get('sensor_fault')
                or self.mission._hard_hazard_reasons(state)
                or state.get('battery_status') in ('low', 'critical', 'charging')):
            self.abort('unsafe, stale or unavailable Roomba sensors')
            return False
        drive_start = self.motion_started if self.motion_started is not None else self.started
        if monotonic() > self.deadline or monotonic()-drive_start > 360:
            self.abort('time limit during '+self.stage)
            return False
        if not all(isinstance(state.get(k), (int, float)) and isfinite(state[k])
                   for k in ('distance', 'angle')) or not isinstance(state.get('odometry_epoch'), int):
            self.abort('invalid wheel odometry')
            return False
        if self.epoch is None:
            self.epoch = state['odometry_epoch']
        elif self.epoch != state['odometry_epoch']:
            self.abort('wheel odometry epoch changed')
            return False
        if self.previous is not None:
            dd, da = state['distance']-self.previous[0], state['angle']-self.previous[1]
            if abs(dd) > 100 or abs(da) > 25:
                self.abort('wheel odometry discontinuity')
                return False
            if self.last_drive is not None and state.get('sensor_monotonic_s') != self.direction_sample:
                # The first fresh sample after a command/sign change may span
                # braking/coast and the new command. Establish its baseline;
                # subsequent samples must agree with the current direction.
                if not self.direction_pending and self.direction_reference is not None:
                    move = state['distance']-self.direction_reference[0]
                    turn = state['angle']-self.direction_reference[1]
                    right, left = self.last_drive
                    if ((right+left)*move < -150 or (right-left)*turn < -100):
                        self.abort('wheel motion opposite commanded direction')
                        return False
                self.direction_pending = False
                self.direction_reference = (state['distance'],state['angle'])
                self.direction_sample = state.get('sensor_monotonic_s')
            self.total_mm += abs(dd)
        self.previous = state['distance'], state['angle']
        if self.tag15_search is not None:
            if monotonic()-self.tag15_search['started']>WALL_TAG15_LOOK_MAX_S:
                self.abort('bounded tag15 look timed out'); return False
            if (abs(state['distance']-self.tag15_search['origin_distance'])>25
                    or abs(state['angle']-self.tag15_search['origin_angle'])>15):
                self.abort('tag15 stopped look exceeded translation/angular envelope'); return False
        if self.validation_started is not None and monotonic()-self.validation_started > 180:
            self.abort('tag15 validation approach exceeded 180 seconds'); return False
        if self.detour_active and (monotonic()-self.detour_started > WALL_DETOUR_MAX_S
                                   or self.total_mm-self.detour_start_mm > WALL_DETOUR_MAX_MM):
            self.start_tag15_search(state)
            return False
        if self.stage in ('acquire', 'align_left45', 'align_check', 'reorient', 'release', 'contact_left'):
            if self.acquire_deadline is not None and monotonic() > self.acquire_deadline:
                self.abort('wall acquisition/re-alignment exceeded 90 seconds')
                return False
            if self.acquire_origin is not None and state['distance']-self.acquire_origin > 600:
                self.abort('wall not aligned within 600 mm acquisition bound')
                return False
        if self.total_mm >= WALL_MAX_PATH_MM:
            self.abort('eight metre bound reached without tag15 validation')
            return False
        bumps = state['sensors'].bumps_and_wheel_drops
        contact = bool(bumps.bump_left or bumps.bump_right)
        recoverable = self.stage in ('acquire', 'release', 'align_left45', 'align_check',
                                     'reorient', 'follow', 'contact_left', 'rejoin')
        if (contact or state.get('wall_contact_blocked')) and not recoverable:
            self.abort('unexpected bumper contact during '+self.stage)
            return False
        if state.get('safety_latched') and not (recoverable and (contact or state.get('wall_contact_blocked'))):
            self.abort('Roomba safety stop latched')
            return False
        return True

    def tick(self, state, pose=None, new_detections=False, captured_at=None, detections=None):
        if not self.guard(state):
            return
        now = monotonic()
        if self.goal_pose is not None and self.goal_odom is not None:
            delta = state['distance']-self.goal_odom[0]
            yaw = radians(state['angle']-self.goal_odom[1])
            middle = self.goal_pose['heading_rad']+yaw/2
            self.goal_pose['x_mm'] += delta*cos(middle)
            self.goal_pose['y_mm'] += delta*sin(middle)
            self.goal_pose['heading_rad'] = self.mission._wrap(self.goal_pose['heading_rad']+yaw)
            self.goal_odom = (state['distance'], state['angle'])
        if self.phone_anchor is not None and self.goal_pose is not None:
            try: self.phone_anchor.compare(state,now)
            except Exception:
                self.mission.logger.exception('RoomTrek diagnostic comparison disabled for this run', extra=dict(speech_announce=False))
                self.phone_anchor = None
        sensors = state['sensors']
        bumps = sensors.bumps_and_wheel_drops
        if self.stage != 'release' and (bumps.bump_left or bumps.bump_right or state.get('wall_contact_blocked')):
            self.contact_recovery(state)
            return
        raw_signal = getattr(sensors, WALL_SENSOR, None)
        if not isinstance(raw_signal, (float, int)) or not isfinite(raw_signal) or not 0 <= raw_signal <= 4095:
            self.abort('invalid right light-bumper IR signal')
            return
        sample_id = state.get('sensor_monotonic_s')
        if sample_id != self.signal_history_sample:
            self.signal_history.append(float(raw_signal))
            del self.signal_history[:-WALL_SIGNAL_AVG_N]
            self.signal_history_sample = sample_id
        signal = (sum(self.signal_history)/len(self.signal_history)
                  if self.signal_history else float(raw_signal))
        target = WALL_TARGET_SIGNAL
        target_min = WALL_TARGET_MIN
        self.last = dict(stage=self.stage, signal=signal, raw_signal=float(raw_signal),
                         signal_avg_n=len(self.signal_history), target_signal=target,
                         target_min=target_min, target_max=WALL_TARGET_MAX,
                         target_center=WALL_TARGET_CENTER,
                         sensor=WALL_SENSOR, sensor_packet=51,
                         desired_clearance_mm=None, measured_clearance_mm=None,
                         reapproaches=self.reapproaches, contact_retries=self.contact_retries,
                         last_follow_heading_deg=self.follow_heading,
                         wall_loss_searches=self.loss_searches, rejoin_source=self.rejoin_source,
                         detour_active=self.detour_active,
                         travelled_mm=self.total_mm, distance_mm=state['distance'], angle_deg=state['angle'],
                         phone_alignment_state=None if self.phone_anchor is None else self.phone_anchor.state,
                         phone_separation_mm=None if self.phone_anchor is None or self.phone_anchor.state!='anchored'
                             or self.phone_anchor.last_result is None else self.phone_anchor.last_result['separation_mm'],
                         tag15_estimated_range_mm=self.goal_range(), tag15_validation_radius_mm=WALL_TAG15_RADIUS_MM,
                         min_wheel_speed_mm_s=WALL_MIN_WHEEL_SPEED, cruise_speed_mm_s=WALL_CRUISE_SPEED)
        self.mission.logger.info('WALL sample: %s', json.dumps(dict(self.last, wall_time=time())))
        if self.stage == 'phone_ready':
            if not self._startup_stop_confirmed:
                self.mission._stop_sent = False  # require a fresh acknowledged stop
            self.stop_motion('waiting for RoomTrek relocalization before tag16')
            self._startup_stop_confirmed = True
            status = self.phone_status()
            if status.get('status') != self._startup_reported_status:
                self._startup_reported_status = status.get('status')
                self.record('phone_wait', status=status.get('status'), attempt=status.get('start_attempt'))
            if status.get('status') in ('failed', 'unknown', 'unavailable'):
                self.abort('RoomTrek startup failed: '+status.get('error', 'readiness unavailable')); return
            if status.get('status') == 'surveying':
                if self.phone_anchor is None:
                    self.abort('RoomTrek startup requires enabled phone/tag16 alignment'); return
                self.record('phone_ready', attempt=status.get('start_attempt'))
                self._wall_time = time()  # reject captures made before readiness
                self.transition('anchor', state, min(60, self.startup_deadline-now))
                self.last_scan_request = 0
            return
        if self.stage == 'anchor':
            if self.phone_status is not None and self.phone_status().get('status') != 'surveying':
                self.abort('RoomTrek readiness lost before tag16 pairing'); return
            self.stop_motion('waiting for tag 16')
            accepted = pose.get('accepted_tag_ids', ()) if isinstance(pose, dict) else ()
            if (new_detections and isinstance(captured_at, (float, int))
                    and captured_at >= self._wall_time
                    and pose and pose.get('localized') and any(int(key[1]) == 16 for key in accepted)):
                current = {k: pose[k] for k in ('x_mm', 'y_mm', 'heading_rad')}
                if self.anchor is not None and captured_at != self.anchor_capture:
                    delta = self.mission._wrap(current['heading_rad']-self.anchor['heading_rad'])
                    if hypot(current['x_mm']-self.anchor['x_mm'], current['y_mm']-self.anchor['y_mm']) <= 75 and abs(delta) <= .1:
                        if self.goal_target is None:
                            self.abort('surveyed tag15 position is required for 300mm validation goal'); return
                        self.origin = current
                        self.goal_pose = dict(current)
                        self.goal_odom = (state['distance'],state['angle'])
                        if self.phone_anchor is not None:
                            try:
                                bound = self.phone_anchor.bind(current,captured_at,state.get('odometry_epoch'),wheel_state=state)
                            except Exception:
                                self.mission.logger.exception('RoomTrek tag16 alignment failed', extra=dict(speech_announce=False))
                                if self.phone_status is not None:
                                    self.abort('RoomTrek tag16 alignment failed; robot remains stopped'); return
                                bound = False
                            if self.phone_status is not None and not bound:
                                # Retry with fresh captures after the phone is
                                # ready; never depart on a diagnostic failure.
                                self.anchor, self.anchor_capture = current, captured_at
                                if now-self.last_scan_request >= 2:
                                    self.mission.camera.request_scan(); self.last_scan_request = now
                                return
                        if self.phone_status is not None:
                            status = self.phone_status()
                            row = self.mission.navlink.latest_trek_observation()
                            parent = status.get('parent_map_id')
                            expected_map = uuid.UUID(parent).bytes if parent else bytes(16)
                            if (status.get('status') != 'surveying' or not isinstance(row,dict)
                                    or not self.phone_anchor.usable(row,self.phone_anchor.heading_basis)
                                    or not 0 <= now-row['frame_monotonic'] <= .25
                                    or row['map_uuid'] != expected_map
                                    or (status.get('phone_session') is not None and str(row['session']) != status['phone_session'])
                                    or row['session'] != self.phone_anchor.anchor['session']
                                    or row['map_uuid'].hex() != self.phone_anchor.anchor['map_uuid_hex']):
                                self.abort('RoomTrek session changed or became stale before departure'); return
                        self.motion_started = now
                        self.record('tag16_anchor', pose=current)
                        self.transition('left90', state, 15)
                        return
                self.anchor, self.anchor_capture = current, captured_at
            if now-self.last_scan_request >= 2:
                self.mission.camera.request_scan()
                self.last_scan_request = now
            return
        if self.stage == 'tag15_scan':
            self.stop_motion('waiting for tag 15')
            fresh=(new_detections and isinstance(captured_at,(float,int))
                   and captured_at >= (self.tag_scan_started or self._wall_time))
            if fresh and detections is not None:
                pose=self.tag15_candidate(detections)
            search=self.tag15_search
            if search is not None and fresh and captured_at!=search['last_capture']:
                search['captures']+=1;search['last_capture']=captured_at
            accepted = pose.get('accepted_tag_ids', ()) if isinstance(pose, dict) else ()
            if (new_detections and isinstance(captured_at, (float, int))
                    and captured_at >= (self.tag_scan_started or self._wall_time)
                    and pose and pose.get('localized') and any(int(key[1]) == 15 for key in accepted)):
                current = {k: pose[k] for k in ('x_mm', 'y_mm', 'heading_rad')}
                if self.tag_scan_anchor is not None and captured_at != self.tag_scan_capture:
                    delta = self.mission._wrap(current['heading_rad']-self.tag_scan_anchor['heading_rad'])
                    if hypot(current['x_mm']-self.tag_scan_anchor['x_mm'], current['y_mm']-self.tag_scan_anchor['y_mm']) <= 75 and abs(delta) <= .1:
                        distance = self.goal_range(current)
                        if distance is None: self.abort('tag15 target is unavailable'); return
                        predicted = None if self.goal_pose is None else dict(self.goal_pose)
                        self.goal_pose = dict(current)
                        self.goal_odom = (state['distance'],state['angle'])
                        if self.tag15_search is not None:
                            self.record('tag15_lucky_found',range_mm=distance,pose=current)
                            self.tag15_search=None
                        if distance <= WALL_TAG15_RADIUS_MM:
                            self.record('tag15_scan', pose=current, range_mm=distance, validation_radius_mm=WALL_TAG15_RADIUS_MM,
                                        wheel_predicted_pose=predicted,
                                        wheel_vs_tag_mm=None if predicted is None else hypot(current['x_mm']-predicted['x_mm'],current['y_mm']-predicted['y_mm']))
                            self.finish('tag15 validated within 300mm', status='complete'); return
                        if self.validation_steps >= WALL_TAG15_MAX_STEPS or distance > WALL_TAG15_ACQUIRE_MAX_MM:
                            self.abort('tag15 remains outside 300mm bounded validation approach'); return
                        self.validation_steps += 1
                        self.approach_mm = min(100.,distance-280.)
                        self.record('tag15_approach', range_mm=distance, advance_mm=self.approach_mm, attempt=self.validation_steps)
                        self.transition('tag15_approach',state,15); return
                self.tag_scan_anchor, self.tag_scan_capture = current, captured_at
            if search is not None and fresh:
                accepted_candidate=(pose and pose.get('localized') and any(int(key[1])==15 for key in accepted))
                if search['captures'] >= (4 if accepted_candidate else 2):
                    self.record('tag15_lucky_no_fix',offset_deg=WALL_TAG15_LOOK_OFFSETS_DEG[search['index']],
                                captures=search['captures'],candidate=bool(accepted_candidate))
                    self.advance_tag15_view(state); return
            if now-self.last_scan_request >= 2:
                self.mission.camera.request_scan()
                self.last_scan_request = now
            return
        if self.stage == 'tag15_search_turn':
            search=self.tag15_search
            target=search['origin_angle']+WALL_TAG15_LOOK_OFFSETS_DEG[search['index']]
            error=target-state['angle']
            sign=None if abs(error)<=3 else (1 if error>0 else -1)
            ready=self.scan_turn.prepare(state,sign,radians(error))
            if self.scan_turn.error:
                self.abort('tag15 scan '+self.scan_turn.error); return
            if not ready:
                self.stop_motion('tag15 pivot waiting for measured settling'); return
            if sign is None:
                self.transition('tag15_scan',state,30);self.last_scan_request=0
            else:
                speed=WALL_MIN_WHEEL_SPEED*sign
                self.drive(speed,-speed,state)
                if self.lease: self.scan_turn.dispatched(sign)
            return
        contact = sensors.bumps_and_wheel_drops
        if self.stage in ('left90', 'right45', 'align_left45', 'reorient', 'contact_left'):
            desired = (90 if self.stage == 'left90' else -45 if self.stage == 'right45'
                       else self.contact_left_deg if self.stage == 'contact_left'
                       else self.acquire_heading-self.stage_angle if self.stage == 'reorient'
                       else min(15., 45.-(self.stage_angle-self.alignment_origin)))
            moved = state['angle']-self.stage_angle
            sign = 1 if desired > 0 else -1
            if moved*sign < -2:
                self.abort('turn moved in opposite direction')
            elif moved*sign >= abs(desired)-2:
                next_stage = {'left90': ('forward200', 12), 'right45': ('acquire', 25),
                              'align_left45': ('align_check', 2), 'reorient': ('acquire', 25),
                              'contact_left': ('rejoin', 10)}[self.stage]
                if next_stage[0] == 'rejoin':
                    self.start_rejoin(state, 'obstacle_contact' if self.detour_active else 'contact')
                else:
                    self.transition(next_stage[0], state, next_stage[1])
            else:
                speed = WALL_MIN_WHEEL_SPEED
                self.drive(sign*speed, -sign*speed, state)
        elif self.stage == 'forward200':
            moved = state['distance']-self.stage_distance
            if moved < -3:
                self.abort('forward offset moved backwards')
            elif moved >= 195:
                self.transition('right45', state, 12)
            else:
                self.drive(35, 35, state)
        elif self.stage == 'acquire':
            sample = state.get('sensor_monotonic_s')
            if sample != self.sensor_sample:
                self.signal_count = (self.signal_count+1
                    if signal >= target_min and state['distance'] >= self.acquire_min_distance else 0)
                self.sensor_sample = sample
            if self.signal_count >= 3:
                self.record('wall_ir_candidate', sensor=WALL_SENSOR, signal=signal, target_signal=target,
                            target_min=target_min, target_max=WALL_TARGET_MAX)
                self.transition('align_left45', state, 12)
            elif state['distance']-self.stage_distance > 600:
                self.abort('wall not acquired within 600 mm')
            else:
                self.drive(WALL_MIN_WHEEL_SPEED, WALL_MIN_WHEEL_SPEED, state)
        elif self.stage == 'align_check':
            self.stop_motion('qualifying alignment signal while stopped')
            sample = state.get('sensor_monotonic_s')
            if sample != self.sensor_sample:
                self.alignment_values.append(signal)
                self.sensor_sample = sample
            if len(self.alignment_values) >= 3:
                values = self.alignment_values[-3:]
                if min(values) < target*.5:
                    self.retry_acquisition(state, signal)
                elif state['angle']-self.alignment_origin >= 43:
                    self.record('alignment_qualified', samples=values,
                                turned_deg=state['angle']-self.alignment_origin)
                    self.transition('follow', state, 180)
                else:
                    # Continue the left alignment in another bounded 15deg step.
                    origin = self.alignment_origin
                    approach_heading = self.acquire_heading
                    self.transition('align_left45', state, 12)
                    self.alignment_origin = origin
                    self.acquire_heading = approach_heading
        elif self.stage == 'release':
            reversed_mm = self.stage_distance-state['distance']
            if reversed_mm >= WALL_CONTACT_BACKOFF_MM and not (contact.bump_left or contact.bump_right) and not state.get('safety_latched'):
                self.stop_motion('backed clear of contact')
                self.mission.robot_control.release_wall_contact_guard()
                self.record('contact_released', reversed_mm=reversed_mm, next_left_deg=self.contact_left_deg)
                self.acquire_min_distance = float(state['distance'])
                self.transition('contact_left', state, 15 if self.contact_left_deg == 90 else 8)
            elif reversed_mm >= WALL_CONTACT_MAX_BACKOFF_MM:
                self.abort('bumper/safety did not release within 50 mm')
            else:
                self.drive(-30, -30, state)
        elif self.stage == 'rejoin':
            moved = state['distance']-self.stage_distance
            turned_right = self.stage_angle-state['angle']
            max_right_deg = (90. if self.detour_active
                             else WALL_WALL_LOSS_MAX_RIGHT_DEG if self.rejoin_source == 'wall_loss'
                             else WALL_REJOIN_MAX_RIGHT_DEG)
            if signal >= target_min:
                self.stop_motion('confirming wall signal after recovery')
                sample = state.get('sensor_monotonic_s')
                if sample != self.sensor_sample:
                    self.signal_count += 1
                    self.sensor_sample = sample
                if self.signal_count >= 3:
                    self.record('wall_rejoined', signal=signal, moved_mm=moved,
                                right_turn_deg=turned_right)
                    self.transition('follow', state, 180)
                return
            self.signal_count = 0
            sample = state.get('sensor_monotonic_s')
            if not self.rejoin_ready:
                self.stop_motion('settling before measured right search')
                if sample != self.sensor_sample:
                    self.rejoin_settle_frames += 1
                    self.sensor_sample = sample
                if self.rejoin_settle_frames >= 3:
                    self.rejoin_ready = True
                    self.stage_angle = self.rejoin_step_angle = float(state['angle'])
                    self.stage_distance = float(state['distance'])
                    self.record('right_search_settled', heading_deg=state['angle'])
                return
            backing_during_advance = (self.rejoin_phase == 'advance'
                and state['distance']-self.rejoin_advance_distance < -3)
            if backing_during_advance or turned_right < -3:
                self.abort('wall rejoin moved opposite the measured right search')
                return
            if turned_right >= max_right_deg:
                self.abort('wall rejoin reached {} degree bound without target signal'.format(int(max_right_deg)))
                return
            if self.rejoin_phase == 'turn':
                step = (15. if self.detour_active
                        else WALL_WALL_LOSS_TURN_STEP_DEG if self.rejoin_source == 'wall_loss'
                        else 5.)
                goal = min(step, max_right_deg-(self.stage_angle-self.rejoin_step_angle))
                if self.rejoin_step_angle-state['angle'] >= goal-1:
                    self.stop_motion('measured right step complete')
                    self.rejoin_phase = 'advance'
                    self.rejoin_advance_distance = float(state['distance'])
                    self.record('right_search_advance', step_mm=50 if self.detour_active else 30)
                else:
                    self.drive(-30, 30, state)
            else:
                step_mm = 50. if self.detour_active else 30.
                if state['distance']-self.rejoin_advance_distance >= step_mm:
                    self.stop_motion('right search advance complete')
                    self.rejoin_phase = 'turn'
                    self.rejoin_step_angle = float(state['angle'])
                else:
                    self.drive(WALL_MIN_WHEEL_SPEED, WALL_MIN_WHEEL_SPEED, state)
        elif self.stage in ('tag15_face', 'tag15_approach'):
            distance = self.goal_range()
            if distance is None: self.abort('tag15 approach has no pose'); return
            if self.stage == 'tag15_approach' and (distance <= 280 or state['distance']-self.stage_distance >= self.approach_mm):
                self.transition('tag15_scan',state,60); return
            bearing = atan2(self.goal_target[1]-self.goal_pose['y_mm'],self.goal_target[0]-self.goal_pose['x_mm'])
            error = self.mission._wrap(bearing-self.goal_pose['heading_rad'])
            if abs(error) > radians(8):
                speed = WALL_MIN_WHEEL_SPEED if error > 0 else -WALL_MIN_WHEEL_SPEED
                self.drive(speed,-speed,state)
            elif self.stage == 'tag15_face': self.transition('tag15_scan',state,60)
            else: self.drive(WALL_MIN_WHEEL_SPEED,WALL_MIN_WHEEL_SPEED,state)
        elif self.stage == 'follow':
            remaining = self.goal_range()
            if (remaining is not None and remaining <= WALL_TAG15_RADIUS_MM) or self.total_mm >= WALL_TAG_SCAN_MM:
                self.record('tag_scan_triggered', travelled_mm=self.total_mm, range_mm=remaining, validation_radius_mm=WALL_TAG15_RADIUS_MM)
                self.validation_started = now
                bearing = atan2(self.goal_target[1]-self.goal_pose['y_mm'], self.goal_target[0]-self.goal_pose['x_mm'])
                if abs(self.mission._wrap(bearing-self.goal_pose['heading_rad'])) > radians(8):
                    self.transition('tag15_face', state, 15)
                else: self.transition('tag15_scan', state, 60)
                return
            if signal < max(5, target*.25):
                self.stop_motion('IR wall lost; start bounded right search')
                self.record('wall_ir_lost', signal=signal, last_heading_deg=self.follow_heading)
                self.start_rejoin(state, 'wall_loss')
                return
            # If the recent IR window fluctuates too much, stop for a second
            # and resample instead of chasing noisy steering corrections.
            if self.fluctuation_hold_until is not None:
                if now < self.fluctuation_hold_until:
                    self.stop_motion('fluctuation hold settling')
                    return
                self.fluctuation_hold_until = None
            if len(self.signal_history) >= WALL_SIGNAL_AVG_N:
                spread = max(self.signal_history)-min(self.signal_history)
                if spread > WALL_FLUCTUATION_MAX:
                    self.stop_motion('IR fluctuating; stable resample')
                    self.record('wall_signal_fluctuating', signal=signal,
                                spread=spread, hold_s=WALL_FLUCTUATION_HOLD_S)
                    self.fluctuation_hold_until = now + WALL_FLUCTUATION_HOLD_S
                    self.signal_history = []
                    self.signal_history_sample = state.get('sensor_monotonic_s')
                    self.follow_signal = None
                    return
            if self.detour_active:
                near_heading = (self.total_mm-self.detour_start_mm >= 200 and signal >= target_min
                    and abs((state['angle']-self.detour_heading+180)%360-180) <= 20)
                sample = state.get('sensor_monotonic_s')
                if near_heading and sample != self.sensor_sample:
                    self.signal_count += 1
                elif not near_heading:
                    self.signal_count = 0
                self.sensor_sample = sample
                if self.signal_count >= 3:
                    self.record('obstacle_bypass_heading_resumed', heading_deg=state['angle'],
                                travelled_mm=self.total_mm-self.detour_start_mm)
                    self.detour_active = False
            slope = 0.
            if self.follow_signal is not None:
                old_time, old_signal = self.follow_signal
                dt = now-old_time
                if .02 <= dt <= .5:
                    slope = (signal-old_signal)/dt
            self.follow_signal = now, signal
            if WALL_TARGET_MIN <= signal <= WALL_TARGET_MAX:
                steering = 0.
            else:
                center = WALL_TARGET_CENTER
                steering = max(-.35, min(.35, (signal-center)/center*.3 + slope/center*.35))
            self.drive(WALL_CRUISE_SPEED*(1+steering), WALL_CRUISE_SPEED*(1-steering), state)
