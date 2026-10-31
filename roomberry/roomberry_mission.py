"""Connect localization, cookie mapping, navigation, and Roomba control."""
# @(#)roomberry_mission.py 3.1.cal.2 2026/10/31 13:00:00

from math import atan2, cos, hypot, pi, sin
from random import uniform, choice
from threading import Event, RLock, Thread
from time import monotonic, time

from irobot.openinterface.constants import MODES, ROBOT

from roomberry_calibration import CalibrationDrive, MODE_CALIBRATION
from roomberry_control import LIGHT_BUMPER_PROXIMITY_THRESHOLD
from roomberry_navigation import (
    BACK_UP, DOCK, DRIVE, FOLLOW_WALL, GO_TO_WAYPOINT, MODE_CLEAN,
    MODE_DISCOVERY, MODE_IDLE, MODE_RETURN_TO_BASE, SEEK_DOCK, STOP, TURN, WAIT,
)


MODE_REMOTE = 'remote_control'
MISSION_PERIOD = 0.2
PERFORMANCE_LOG_INTERVAL = 10.0
NO_PROGRESS_SECONDS = 2.0
MIN_PROGRESS_MM = 20.0
NAVIGATION_SPEED = 80
TURN_SPEED = 60
HEADING_TOLERANCE_RAD = 0.25
# Cruise with both wheels forward; pivot only for large heading changes.
# Separate entry/exit angles avoid alternating between a pivot and an arc.
WAYPOINT_PIVOT_ENTER_RAD = pi / 3.0
WAYPOINT_PIVOT_EXIT_RAD = pi / 4.0
WAYPOINT_NEAR_MM = 200.0
WAYPOINT_NEAR_PIVOT_ENTER_RAD = 0.55
WAYPOINT_NEAR_PIVOT_EXIT_RAD = 0.35
WAYPOINT_LOOKAHEAD_MM = 250.0
# At 80 mm/s outside-wheel speed, this keeps the inner wheel above 30 mm/s.
WAYPOINT_MAX_STEERING = 0.45
WAYPOINT_HEADING_DEADBAND_RAD = 0.03
MIN_TURN_SPEED = 30
BUMP_GO_SECONDS = 120.0
BLOCKED_RETRY_SECONDS = 10.0
BLOCKED_VIEW_SEARCHES = 2
# Watchdogs for a repeated continuous command. The mission loop extends them on
# every tick, so they only fire when the coordinator stops refreshing motion.
SPIN_WATCHDOG_SECONDS = 0.6
DRIVE_WATCHDOG_SECONDS = 1.0
# Re-send continuous commands periodically. The command arbiter may brake on a
# safety sensor without the coordinator noticing; a heartbeat lets the next
# send either resume the same motion or fail visibly instead of stalling.
CONTINUOUS_REISSUE_SECONDS = 0.5
MAX_TAG_PROCESSING_AGE = 5.0
DISCOVERY_SPEED = 80
# Keep these discovery stages uninterrupted while a continuous command is
# active; a stationary scan would brake a smooth reverse or turn and invite
# wheel slip. If motion has stopped, a scan is allowed so localization can
# recover instead of expiring in a skip-scan loop.
DISCOVERY_CONTINUOUS_STAGES = frozenset((
    'retreat', 'tag2_contact', 'release_contact',
    'avoid_back', 'avoid_turn', 'avoid_forward',
))
DOCK_X_MM = 1060.0
DOCK_Y_MM = 260.0
DOCK_HEADING_RAD = -pi / 2.0
RETREAT_MM = 500.0
DOCK_APPROACH_MM = 300.0
# The dock ramp and its shadow can briefly trip a front cliff sensor as the
# robot reverses clear. Ignore short departure readings within this envelope,
# but abort if they persist, which indicates a real drop-off.
DISCOVERY_DOCK_ESCAPE_MM = 150.0
DISCOVERY_DOCK_HAZARD_GRACE_SECONDS = 2.0
DISCOVERY_INITIAL_TAG_ID = 1
DISCOVERY_TAG_ID = 2
# Tags 1 and 2 use their existing dock/contact sequence. Additional surveyed
# landmarks are visited from a parking point that keeps the bumper away from an
# unknown obstacle while still presenting the tag face to the camera.
DISCOVERY_PARK_DISTANCE_MM = 500.0
# Retry from alternate parking points along the surveyed tag face.
VISIT_RETRY_LATERAL_OFFSETS_MM = (150.0, -150.0, 300.0, -300.0)
# IR proximity slows transit; physical bumper contact starts a reverse, turn,
# and parallel leg before rejoining the surveyed route.
# Continue detouring for subsequent obstacles without a per-leg count limit.
# Each maneuver still has its own timeout and safety checks.
DISCOVERY_REVERSE_SPEED = 50
DISCOVERY_TURN_SPEED = 50
WALL_FOLLOW_SPEED = 50
DISCOVERY_AVOID_SPEED = 40
DISCOVERY_AVOID_REVERSE_MM = 35.0
DISCOVERY_AVOID_FORWARD_MM = 90.0
DISCOVERY_AVOID_TURN_RAD = pi / 4.0
DISCOVERY_AVOID_TURN_TOLERANCE_RAD = 0.06
DISCOVERY_AVOID_STAGE_TIMEOUT_SECONDS = 8.0
# The parallel leg is much longer than the reverse or turn, so give it enough
# time for the full distance at detour speed plus odometry and turn-in slack.
DISCOVERY_AVOID_FORWARD_TIMEOUT_SECONDS = (
    DISCOVERY_AVOID_FORWARD_MM / DISCOVERY_AVOID_SPEED + 4.0
)
# Raw light-bumper samples occasionally spike for a single poll, especially
# around motion changes, even though the carpet baseline is under 25. Require a
# sustained reading before diverting; the recorded collision ramps lasted well
# over a second, so a few mission ticks still leave time to react.
DISCOVERY_PROXIMITY_CONFIRM_TICKS = 3
# A fresh visit starts next to tag 2, whose white face can keep the light
# bumpers asserted after the intentional contact release. Ignore proximity
# until the robot has moved clear so the detour does not chase the old reading.
DISCOVERY_AVOID_GRACE_MM = 250.0
DISCOVERY_AVOID_STAGES = ('avoid_back', 'avoid_turn', 'avoid_forward')
# Transit stages that can recover from physical bumper contact with the same
# detour used for IR proximity. A blocked parallel leg starts another detour
# while retaining the original destination.
DISCOVERY_DETOUR_STAGES = frozenset((
    'tag2_approach', 'tag2_align', 'visit_approach', 'visit_align', 'return',
))
TAG2_ALIGN_TOLERANCE_RAD = 0.12
RELEASE_CLEAR_HOLD_SECONDS = 0.4
RELEASE_MIN_DISTANCE_MM = 150.0
RELEASE_MAX_DISTANCE_MM = 250.0
RELEASE_TIMEOUT_SECONDS = 10.0
CONTACT_INSET_MM = 1.0
# Manual web/button motion is not tracked as a mission command, so keep a short
# hold-off around recent commands and also trust the robot's requested wheel
# velocities. This prevents an idle-mode localization scan from braking a user
# who is still driving with the web controls.
MANUAL_MOTION_HOLD_SECONDS = 1.0


class RoomberryMission:
    """Periodic coordinator; camera, map, and arbiter remain separate owners.

    The mission starts idle. Call ``set_mode(MODE_CLEAN)`` only after mapping
    and calibration have been configured. Navigation actions are translated
    into short Open Interface commands and stopped at their duration limit.
    """

    def __init__(self, robot_control, camera, mapper, navigation, localizer,
                 logger, dock_waypoint_mm=None, wall_follow=None,
                 period=MISSION_PERIOD, landmarks=None):
        self.robot_control = robot_control
        self.camera = camera
        self.mapper = mapper
        self.navigation = navigation
        self.localizer = localizer
        self.phone_position = None
        self.navlink = None
        self.calibration = None
        self._announced_mode = None
        self.logger = logger
        self.dock_waypoint_mm = dock_waypoint_mm
        self.wall_follow = wall_follow or {'enabled': False}
        self.discovery_landmarks = {int(item['id']): item for item in (landmarks or [])}
        self.period = float(period)
        if self.period <= 0:
            raise ValueError('Mission period must be positive')
        self._shutdown = Event()
        self._thread = Thread(target=self._run, name='roomberry-mission', daemon=True)
        self._coord_lock = RLock()
        self._scan_active = False
        self._scan_started_at = None
        self._aim_scan_pending = False
        self._aim_scan_cooldown = 0.0
        self._localization_recovery = None
        self.map_log = None
        self._blocked_waypoint = None
        self._restart_generation = 0
        self._detections_after_restart = 0.0
        self._wall_clear_start = None
        self._wall_clear_deadline = None
        self._discovery_stage = None
        self._mode = MODE_IDLE
        self._schedule_button_was_pressed = False
        self._clock_button_was_pressed = False
        self._last_detection_time = None
        self._last_destination_log = None
        self._discovery_route_step = None
        self._discovery_route_goal = None
        self._discovery_stale_logged = False
        self._discovery_localization_stale_logged = False
        self._discovery_start_travelled = None
        self._discovery_turning = False
        self._discovery_retreat_scan_failures = 0
        self._discovery_hazard_since = None
        self._discovery_proximity_ticks = 0
        self._scan_pose = None
        self._last_pose = None
        self._last_contact = False
        self._circumvent_pending = False
        self._circumvent_side = 'right'
        self._active_command = None
        self._active_until = 0.0
        self._active_reissue_at = 0.0
        self._manual_motion_until = 0.0
        self._remote_was_moving = False
        self._progress_anchor_distance = None
        self._progress_since = monotonic()
        self._stuck_latched = False
        self._stop_sent = False
        self._cleaning_motors_on = False
        self._perf_start = monotonic()
        self._perf_loops = 0
        self._perf_total = 0.0
        self._perf_max = 0.0
        self._perf_plan_total = 0.0
        self._perf_dispatch_total = 0.0
        self._last_action_signature = None

    def start(self, mode=MODE_IDLE):
        self.set_mode(mode)
        if not self._thread.is_alive():
            self._thread.start()

    def close(self):
        self._shutdown.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        with self._coord_lock:
            self._send_stop('mission shutdown')
            self._flush_map('mission shutdown')

    def set_mode(self, mode, wake_robot=True):
        if mode not in (MODE_IDLE, MODE_CLEAN, MODE_RETURN_TO_BASE,
                        MODE_DISCOVERY, MODE_REMOTE, MODE_CALIBRATION):
            raise ValueError('Unsupported mission mode: ' + str(mode))
        with self._coord_lock:
            self._send_stop('mission mode transition')
            leaving_active = (
                mode in (MODE_IDLE, MODE_REMOTE) and
                self._mode not in (MODE_IDLE, MODE_REMOTE)
            )
            self._aim_scan_pending = False
            self._localization_recovery = None
            self._blocked_waypoint = None
            if self._mode == MODE_CALIBRATION and mode != MODE_CALIBRATION and self.calibration.result is None:
                self.calibration.result = dict(status='cancelled', reason='mode changed to '+mode)
                self.calibration.stage = 'cancelled'
                self.logger.info('Calibration cancelled by mode change to %s.', mode)
            self._mode = mode
            if mode == MODE_CALIBRATION:
                self.calibration = CalibrationDrive(self)
                self._manual_motion_until = 0.0
                self.localizer.invalidate_pose()
                self._detections_after_restart = time()
                if self.phone_position is not None:
                    self.phone_position.reset()
            if mode == MODE_DISCOVERY:
                self._localization_recovery = None
                self._wall_clear_start = None
                self._discovery_stage = 'initial_scan'
                self._discovery_pose = None
                self._discovery_scan_time = None
                self._discovery_waypoint = None
                self._discovery_retreat_start_distance = None
                self._discovery_retreat_start_travelled = None
                self._discovery_retreat_bumper_cleared = False
                self._discovery_release_started = None
                self._discovery_release_start_travelled = None
                self._discovery_release_clear_since = None
                self._discovery_release_deadline = None
                self._discovery_retreat_scan_failures = 0
                self._discovery_scan_resume = None
                self._discovery_repositioned_tags = set()
                self._discovery_logged_tags = set()
                self._discovery_stale_logged = False
                self._discovery_localization_stale_logged = False
                self._discovery_start_travelled = None
                self._discovery_turning = False
                self._discovery_hazard_since = None
                self._discovery_visit_tags = None
                self._discovery_visit_index = 0
                self._discovery_visit_tag = None
                self._discovery_visit_heading_offset = 0.0
                self._discovery_visit_retry_index = 0
                self._discovery_visit_arrival_pose = None
                self._discovery_return_waypoints = []
                self._discovery_return_index = 0
                self._discovery_avoid_return_stage = None
                self._discovery_avoid_side = None
                self._discovery_avoid_attempts = 0
                self._discovery_avoid_start_travelled = None
                self._discovery_avoid_turn_target = None
                self._discovery_avoid_deadline = None
                self._discovery_avoid_grace_start = None
                self._discovery_proximity_ticks = 0
            self.navigation.set_mode(
                MODE_IDLE if mode in (MODE_DISCOVERY, MODE_REMOTE, MODE_CALIBRATION) else mode
            )
            if mode != MODE_CLEAN:
                self._circumvent_pending = False
            self.robot_control.set_returning_home(
                mode == MODE_RETURN_TO_BASE and self.dock_waypoint_mm is not None
            )
            self.robot_control.set_operation_indicators(mode != MODE_IDLE)
            if mode != MODE_IDLE:
                try:
                    self.robot_control.execute('_change_mode', mode=MODES.SAFE)
                    self.logger.info('Roomba Open Interface entered Safe mode for %s.', mode)
                except Exception:
                    self.logger.exception('Unable to enter Safe mode; motion remains inhibited.')
            if mode in (MODE_DISCOVERY, MODE_CALIBRATION):
                self.robot_control.execute('set_motors', main_brush_on=False,
                                           side_brush=False, vacuum=False)
                self._cleaning_motors_on = False
                if wake_robot and mode == MODE_DISCOVERY:
                    self.robot_control.execute('wake')

            self.logger.info('Mission mode changed to %s', mode)
            if leaving_active:
                self._flush_map('leaving active mode')
            self._announce_mode()

    def start_calibration(self):
        """Web entry point: idempotent while running; never rearm an OI stop."""
        with self._coord_lock:
            state = self.robot_control.snapshot()
            if state.get('oi_stopped') or self._hard_hazard_reasons(state) or not state.get('ready'):
                raise RuntimeError('Calibration requires grounded, ready Roomba sensors and no safety stop')
            if self._mode != MODE_CALIBRATION:
                self.set_mode(MODE_CALIBRATION, wake_robot=False)

    def status_snapshot(self):
        """Read-only mission state for HTTP diagnostics."""
        with self._coord_lock:
            run = self.calibration
            return dict(mission_mode=self._mode, calibration=None if run is None else dict(
                stage=run.stage, result=run.result, checkpoints=len(run.records),
                waiting_for_sensors=run.sensor_wait_since is not None,
                latest_checkpoint=run.records[-1] if run.records else None))

    def _announce_mode(self):
        """Announce real mode transitions, including the bump-and-go submode."""
        bump = (self._mode == MODE_DISCOVERY and self._blocked_waypoint is not None
                and self._blocked_waypoint.get('wander') is not None)
        display_stage = 'bump' if bump else self._discovery_stage
        identity = (self._mode, bool(bump))
        self.robot_control.set_drive_display(self._mode, display_stage, self._scan_active)
        if identity != self._announced_mode:
            self._announced_mode = identity
            self.logger.info('Navigation mode: %s.', 'bump-and-go' if bump else self._mode)
            self._button_beep('mode_change')

    def _flush_map(self, reason):
        """Persist pending map changes without letting a write block shutdown."""
        try:
            self.mapper.flush()
        except Exception:
            self.logger.exception('Unable to persist map state while %s.', reason)
        if self.map_log is not None:
            self.map_log.request(reason, mode=self._mode, force=True)

    def take_manual_control(self, moving=True):
        """Enter remote-control mode when a web/manual command arrives.

        Manual commands go straight to the command arbiter, so the mission must
        relinquish its active mode before they can move the robot. Remote mode
        keeps the mission from replanning or braking for localization scans while
        the operator drives. When already remote this only refreshes the motion
        marker, so repeated joystick updates cannot inject stops between them.
        """
        with self._coord_lock:
            if self._mode != MODE_REMOTE:
                if self._mode != MODE_IDLE:
                    self.logger.info(
                        'Remote control took over; cancelling %s mission.',
                        self._mode,
                    )
                self.set_mode(MODE_REMOTE)
            if moving:
                self._manual_motion_until = monotonic() + MANUAL_MOTION_HOLD_SECONDS

    def _manual_motion_active(self):
        """Return True while the web controls have the robot moving in idle."""
        if monotonic() < self._manual_motion_until:
            return True
        if self._mode != MODE_REMOTE:
            return False
        try:
            state = self.robot_control.snapshot()
        except Exception:
            return False
        if not isinstance(state, dict):
            return False
        sensors = state.get('sensors')
        if sensors is None:
            return False

        def wheel_velocity(name):
            try:
                return abs(int(getattr(sensors, name, 0)))
            except (TypeError, ValueError):
                return 0

        return bool(wheel_velocity('requested_left_velocity') or
                    wheel_velocity('requested_right_velocity'))

    def scan_pause(self):
        """Camera callback: synchronously stop before the stationary capture.

        Returns ``False`` only while a continuous discovery command is actually
        running or the user is manually driving in idle mode; the camera then
        skips that scan instead of braking the robot. If motion has stopped, the
        scan is allowed so localization can recover from a safety pause or
        stale pose. While the robot is stopped, pending map changes are written
        so the ~350 ms JSON fsync no longer stalls a motion tick.
        """
        with self._coord_lock:
            if self.robot_control.snapshot().get('oi_stopped') is True:
                return False
            moving = (self._active_command is not None and
                      monotonic() < self._active_until)
            if (self._mode in (MODE_IDLE, MODE_REMOTE) and
                    self._manual_motion_active()):
                self.logger.debug(
                    'Skipping AprilTag scan: wheel motion is reported in %s mode.',
                    self._mode,
                )
                return False
            if (self._mode == MODE_DISCOVERY and moving and
                    (self._discovery_stage in DISCOVERY_CONTINUOUS_STAGES or
                     (self._blocked_waypoint is not None and
                      self._blocked_waypoint.get('wander') is not None))):
                self.logger.debug(
                    'Skipping AprilTag scan during continuous discovery stage %s.',
                    self._discovery_stage,
                )
                return False
            if self._mode == MODE_CALIBRATION and not self.calibration.stage.endswith('_scan'):
                return False  # Calibration scans only at explicit stopped checkpoints.
            recovery = self._localization_recovery
            if self._mode == MODE_DISCOVERY and recovery is not None and recovery['phase'] != 'scan':
                return False
            if (self._mode == MODE_DISCOVERY and recovery is None and
                    self._blocked_waypoint is None and
                    self._discovery_stage in ('visit_approach', 'wall_follow', 'return') and
                    monotonic() >= self._aim_scan_cooldown and
                    self._choose_scan_heading(self._scan_pose) is not None):
                self._aim_scan_pending = True
                return False  # Coordinator aims first; camera never commands a turn.
            blocked = self._blocked_waypoint
            if self._mode == MODE_DISCOVERY and blocked is not None:
                pose = self._scan_pose
                view = None if pose is None else tuple(pose[k] for k in ('x_mm', 'y_mm', 'heading_rad'))
                last = blocked.get('scan_view')
                unchanged = (view == last if view is None or last is None else
                    hypot(view[0]-last[0], view[1]-last[1]) < 100 and
                    abs(self._wrap(view[2]-last[2])) < pi/12)
                if (recovery is None and not self._aim_scan_pending and unchanged and
                        blocked.get('view_scans', 0) >= 2):
                    self.logger.debug('Skipping repeated blocked-route scan at unchanged viewpoint.')
                    return False
                blocked['view_scans'] = blocked.get('view_scans', 0)+1 if unchanged else 1
                blocked['scan_view'] = view
            self._scan_active = True
            self._scan_started_at = monotonic()
            self._send_stop('AprilTag scan pause', smooth=True)
            self._flush_map('stationary AprilTag scan')
            self._button_beep('neutral')
            pose = self._scan_pose
            target_id = (recovery.get('tag_id') if recovery is not None else
                         getattr(self, '_discovery_visit_tag', None) if self._mode == MODE_DISCOVERY else None)
            if recovery is None and self._mode == MODE_DISCOVERY:
                if self._discovery_stage in ('initial_scan', 'retreat', 'retreat_scan', 'dock_approach', 'dock_scan'):
                    target_id = DISCOVERY_INITIAL_TAG_ID
                elif self._discovery_stage and self._discovery_stage.startswith('tag2'):
                    target_id = DISCOVERY_TAG_ID
            if self._mode == MODE_CALIBRATION:
                target_id = 15
            target_heading = None
            if recovery is not None and recovery.get('target') is not None and pose is not None:
                target_heading = self._wrap(pose['heading_rad'] + recovery['target'] -
                    float(self.robot_control.snapshot().get('angle', 0)) * pi / 180) * 180 / pi
            self.logger.debug('Stationary AprilTag scan requested: target_tag=%s '
                              'stage=%s view=%s target_heading_deg=%s pose=%s.',
                              target_id, self._discovery_stage,
                              None if recovery is None else recovery['index'],
                              target_heading, pose)
        return True

    def _button_beep(self, event='happy'):
        """Give audible feedback for a physical button press."""
        beeper = getattr(self.robot_control, 'beep', None)
        if not callable(beeper):
            return
        try:
            if event == 'happy':
                beeper()
            else:
                beeper(event=event)
        except Exception:
            self.logger.exception('Unable to beep for button feedback.')

    def scan_complete(self):
        """Camera callback: allow the next mission tick to process and replan."""
        with self._coord_lock:
            if self._scan_started_at is not None:
                paused = monotonic() - self._scan_started_at
                for name in ('_discovery_avoid_deadline', '_discovery_release_deadline', '_wall_clear_deadline'):
                    deadline = getattr(self, name, None)
                    if deadline is not None:
                        setattr(self, name, deadline + paused)
            recovery = self._localization_recovery
            if self._scan_started_at is not None and recovery and recovery['phase'] == 'turn':
                recovery['turn_deadline'] += monotonic() - self._scan_started_at
            self._scan_started_at = None
            self._scan_active = False
            self.logger.debug('AprilTag scan complete; mission will re-localize and replan.')

    def _run(self):
        while not self._shutdown.is_set():
            started = monotonic()
            try:
                with self._coord_lock:
                    if self._scan_active:
                        state = self.robot_control.snapshot()
                        self._handle_clock(state)
                        if self._mode == MODE_CALIBRATION:
                            self.calibration.guard(self.robot_control.snapshot())
                    else:
                        self._tick()
                        if self.map_log is not None and self._mode != MODE_IDLE:
                            self.map_log.request(mode=self._mode)
            except Exception:
                self.logger.exception('Mission update failed; stopping the robot.')
                with self._coord_lock:
                    self._send_stop('mission update error')
                    if self._mode == MODE_CALIBRATION:
                        self.calibration.abort('mission update error')
            try:
                self._announce_mode()
            except Exception:
                self.logger.exception('Drive display update failed; mission remains active.')
            elapsed = monotonic() - started
            self._record_performance(elapsed)
            self._shutdown.wait(max(0.0, self.period - elapsed))

    def _handle_clock(self, state):
        """Start/cancel calibration on Clock, including during a stationary scan."""
        if state.get('oi_stopped') is True:
            return False
        pressed = bool(state.get('clock_button', False))
        edge = pressed and not self._clock_button_was_pressed
        self._clock_button_was_pressed = pressed
        consume = getattr(self.robot_control, 'consume_clock_button_press', None)
        latched = bool(consume()) if callable(consume) else False
        if not (edge or latched):
            return False
        if self._mode == MODE_CALIBRATION:
            self.calibration.abort('Clock button cancelled calibration')
        else:
            self.set_mode(MODE_CALIBRATION)
            self.logger.info('Clock button pressed; starting tag 15 calibration: '
                             'three 500 mm reverse legs, return scan and gentle bumper touch.')
        return True

    def _tick(self):
        state = self.robot_control.snapshot()
        generation = state.get('restart_generation', 0)
        if isinstance(generation, int) and generation != self._restart_generation:
            self._restart_generation = generation
            self._detections_after_restart = time()
            self.localizer.invalidate_pose()
            if self.phone_position is not None:
                self.phone_position.reset()
            self._localization_recovery = None
            if self._mode != MODE_IDLE:
                self.set_mode(MODE_IDLE)
            self.camera.request_scan()
        if state.get('oi_stopped') is True:
            if self.phone_position is not None:
                self.phone_position.reset()
            if self._mode != MODE_IDLE:
                self.set_mode(MODE_IDLE)
            return
        schedule_pressed = state.get('schedule_button', False)
        schedule_edge = schedule_pressed and not self._schedule_button_was_pressed
        self._schedule_button_was_pressed = schedule_pressed
        if self._handle_clock(state):
            return
        consume_schedule = getattr(self.robot_control, 'consume_schedule_button_press', None)
        schedule_edge = schedule_edge or (callable(consume_schedule) and consume_schedule() is True)
        if schedule_edge and self._mode != MODE_DISCOVERY:
            self.logger.info('Schedule button pressed; starting discovery mode.')
            self.set_mode(MODE_DISCOVERY, wake_robot=False)
            self._discovery_start_travelled = state.get('travelled_distance')
            # set_mode announces after the OI mode change has completed.
            return
        sensors = state['sensors']
        if not state.get('ready') or sensors is None:
            if self._mode == MODE_CALIBRATION:
                self.calibration.abort('Roomba sensors not ready')
                return
            self._send_stop('waiting for Roomba sensor startup')
            return
        if state.get('battery_status') == 'low' and self._mode == MODE_CLEAN:
            next_mode = MODE_RETURN_TO_BASE
            self.logger.warning('Battery low; mission mode changing to %s.', next_mode)
            self.set_mode(next_mode)
        elif (state.get('battery_status') == 'charging' and
                self._mode not in (MODE_IDLE, MODE_DISCOVERY, MODE_REMOTE)):
            self.logger.info('Dock charging detected; ending active mission.')
            self.set_mode(MODE_IDLE)
        detections = ()
        detection_timestamp = None
        new_detections = False
        localization_timestamp = None
        if self.camera is not None:
            detection_timestamp = self.camera.last_detection_time
            if detection_timestamp is not None and detection_timestamp != self._last_detection_time:
                detections = self.camera.latest_detections
                self._last_detection_time = detection_timestamp
                new_detections = True
                ready_at = getattr(self.camera, 'last_detection_ready_time', None)
                # A stationary capture remains valid through slow processing;
                # preserve captured_at for localization and scan correlation.
                freshness_time = (ready_at if self.camera.pause_for_detection is True
                                  and isinstance(ready_at, (float, int)) else detection_timestamp)
                localization_timestamp = freshness_time
                detection_age = max(0.0, time() - freshness_time)
                if detection_timestamp < self._detections_after_restart:
                    self.logger.info('Discarding pre-restart AprilTag capture.')
                    detections = ()
                    new_detections = False
                elif detection_age > MAX_TAG_PROCESSING_AGE:
                    self.logger.warning(
                        'Ignoring AprilTag result %.1f seconds old.', detection_age,
                    )
                    detections = ()
                    new_detections = False

        if self._mode == MODE_CALIBRATION:
            detections = tuple(item for item in detections if int(item.get('id', -1)) == 15)
        pose = None
        if sensors is not None:
            pose = self.localizer.update(
                detections, state['distance'], state['angle'],
                new_detections=new_detections,
                detection_timestamp=localization_timestamp,
                odometry_epoch=state.get('odometry_epoch'),
            )
        if self.phone_position is not None and self._mode != MODE_CALIBRATION:
            pose = self.phone_position.apply(
                self.localizer, pose, monotonic(), state.get('odometry_epoch'),
                enabled=(self._mode in (MODE_DISCOVERY, MODE_CLEAN, MODE_RETURN_TO_BASE)
                         and state.get('age') is not None and state['age'] <= .5))
        self._scan_pose = pose
        if new_detections:
            self._button_beep('happy' if pose and pose.get('accepted_tag_ids') else 'unhappy')
        if self._mode in (MODE_IDLE, MODE_REMOTE) and new_detections:
            raw_tags = [
                (item.get('family'), item.get('id'), item.get('tag_pose_camera'))
                for item in detections
            ]
            self.logger.info(
                '%s AprilTag localization: pose=%s detections=%s rejected=%s',
                'Remote-control' if self._mode == MODE_REMOTE else 'Idle',
                pose, raw_tags,
                None if pose is None else pose.get('rejected_tags'),
            )
        if pose is not None:
            self.mapper.update_pose(
                pose['x_mm'], pose['y_mm'], pose['heading_rad'],
                localized=pose['localized'],
            )
            if self._mode == MODE_CLEAN and pose.get('localized'):
                if self._cleaning_motors_on:
                    self._record_coverage(self._last_pose, pose)
                self._last_pose = pose
            else:
                self._last_pose = None

        self._log_destination(pose)
        if self._mode == MODE_DISCOVERY and new_detections:
            self._log_tag_ranges(pose, detections, detection_timestamp)

        if self._mode == MODE_REMOTE:
            # The HTTP command handler owns motion in remote mode. The mission
            # still updates odometry, localization, and the map above, but must
            # not plan, brake, or run cleaning motors while the operator drives.
            self._set_cleaning_motors(False)
            moving = self._manual_motion_active()
            if self._remote_was_moving and not moving and self.camera is not None:
                # The periodic scan is skipped during manual motion. Request one
                # as soon as the operator stops so a new tag can be registered
                # without waiting for the next camera interval.
                self.logger.debug(
                    'Manual motion stopped; requesting an AprilTag scan.',
                )
                self.camera.request_scan()
            self._remote_was_moving = moving
            return

        if self._mode == MODE_CALIBRATION:
            self.calibration.tick(state, pose, new_detections, detection_timestamp)
            return

        if self._mode == MODE_DISCOVERY:
            self._discovery_tick(state, pose, new_detections, detection_timestamp)
            return

        observation = self._navigation_observation(state, pose)
        stuck, progress = self._progress_status(state)
        observation['stuck'] = stuck
        observation['progress'] = progress
        contact_present = any(observation['bumper'].values()) or any(
            observation['light_bumper'].values()
        )
        if (self._mode == MODE_RETURN_TO_BASE and self.dock_waypoint_mm is not None
                and pose and pose.get('localized')):
            observation['dock_visible'] = hypot(
                pose['x_mm'] - self.dock_waypoint_mm[0],
                pose['y_mm'] - self.dock_waypoint_mm[1],
            ) <= 250.0
        if (self._mode == MODE_CLEAN and pose and pose.get('localized')
                and not observation['hard_hazard'] and not contact_present):
            self._set_cleaning_motors(True)
        else:
            self._set_cleaning_motors(False)
        if observation['hard_hazard'] and self._mode != MODE_IDLE:
            self.logger.warning('Hard safety condition; mission set to idle.')
            self._mode = MODE_IDLE
            self.navigation.set_mode(MODE_IDLE)
            self.robot_control.set_returning_home(False)
            self.robot_control.set_operation_indicators(False)
            self._flush_map('hard safety stop')
        contact = bool(observation['bumper'] and any(observation['bumper'].values())) or bool(
            observation['light_bumper'] and any(observation['light_bumper'].values())
        )
        if (contact and not self._last_contact and pose and pose.get('localized')
                and self._contact_mapping_allowed(state)):
            self._record_contact_obstacle(pose, observation)
            if self._mode == MODE_CLEAN:
                self._circumvent_pending = True
                left_contact = (observation['bumper'].get('left') or
                                observation['light_bumper'].get('left') or
                                observation['light_bumper'].get('front_left') or
                                observation['light_bumper'].get('center_left'))
                self._circumvent_side = 'left' if left_contact else 'right'
        self._last_contact = contact
        if (self._circumvent_pending and not contact and
                self.navigation.mode != 'recovery'):
            observation['obstacle_leg'] = True
            observation['obstacle_side'] = self._circumvent_side

        plan_started = monotonic()
        if self._mode == MODE_CLEAN:
            plan = self.mapper.plan_next()
        elif self._mode == MODE_RETURN_TO_BASE and self.dock_waypoint_mm is not None:
            plan = self.mapper.plan_to(*self.dock_waypoint_mm)
        else:
            plan = None
        plan_duration = monotonic() - plan_started
        observation['waypoint'] = None if plan is None else plan['waypoint_mm']

        action = self.navigation.decide(observation)
        if action['kind'] == DRIVE and action['reason'].startswith('short arc around obstacle'):
            self._circumvent_pending = False
        dispatch_started = monotonic()
        self._dispatch(action, pose)
        dispatch_duration = monotonic() - dispatch_started
        action_signature = (action['kind'], action['reason'], action.get('waypoint'))
        if action_signature != self._last_action_signature:
            self.logger.debug(
                'Navigation decision changed: mode=%s localized=%s tag_age=%s '
                'waypoint=%s action=%s reason=%s',
                self._mode, bool(pose and pose.get('localized')),
                None if not pose else pose.get('localization_age'),
                observation['waypoint'], action['kind'], action['reason'],
            )
            self._last_action_signature = action_signature
        self._perf_plan_total += plan_duration
        self._perf_dispatch_total += dispatch_duration

    def _log_destination(self, pose):
        """Repeat the mission destination once per minute, including detours."""
        now = monotonic()
        if (self._last_destination_log is not None and
                now - self._last_destination_log < 60.0):
            return
        self._last_destination_log = now
        stage = None
        tag_id = None
        remaining_tags = []
        waypoint = None
        if self._mode == MODE_DISCOVERY:
            stage = self._discovery_stage
            waypoint = self._discovery_waypoint
            if stage.startswith('visit') or stage.startswith('avoid'):
                tag_id = self._discovery_visit_tag
            elif stage.startswith('tag2') or stage == 'release_contact':
                tag_id = DISCOVERY_TAG_ID
            elif stage == 'initial_scan' or stage.startswith('dock'):
                tag_id = DISCOVERY_INITIAL_TAG_ID
            tags = self._discovery_visit_tags
            if tags is None:
                tags = self._discovery_visit_order()
            remaining_tags = tags[self._discovery_visit_index:]
        elif self._mode == MODE_RETURN_TO_BASE:
            waypoint = self.dock_waypoint_mm
        distance = None
        if waypoint is not None and pose is not None:
            distance = round(hypot(waypoint[0] - pose['x_mm'],
                                   waypoint[1] - pose['y_mm']), 1)
        self.logger.info(
            'Mission destination: mode=%s stage=%s target_tag=%s '
            'waypoint_mm=%s distance_mm=%s remaining_tags=%s '
            'localized=%s localization_age_s=%s scan_active=%s.',
            self._mode, stage, tag_id, waypoint, distance, remaining_tags,
            bool(pose and pose.get('localized')),
            None if pose is None else pose.get('localization_age'),
            self._scan_active,
        )

    def _log_tag_ranges(self, pose, detections, captured_at):
        """Record sightings and misses against surveyed range at each scan."""
        expected = self._discovery_visit_tag
        rejected = dict(() if pose is None else pose.get('rejected_tags', ()))
        accepted = () if pose is None else pose.get('accepted_tag_ids', ())
        tags = {int(item['id']) for item in detections}
        samples = list(detections)
        if expected is not None and expected not in tags:
            samples.append({'id': expected, 'family': 'tag16h5'})
        for item in samples:
            tag_id = int(item['id'])
            landmark = self.discovery_landmarks.get(tag_id)
            if landmark is None:
                continue
            key = (str(item.get('family', 'tag16h5')), tag_id)
            transform = landmark['world_from_tag']
            distance = bearing = None
            if pose is not None:
                dx = float(transform[0][3]) * 1000 - pose['x_mm']
                dy = float(transform[1][3]) * 1000 - pose['y_mm']
                distance = round(hypot(dx, dy), 1)
                bearing = round(self._wrap(atan2(dy, dx) - pose['heading_rad']), 3)
            visible = tag_id in tags
            reason = rejected.get(key)
            result = ('not_detected' if not visible else
                      'accepted' if key in accepted else
                      'rejected: ' + reason if reason else 'detected')
            tag_pose = item.get('tag_pose_camera') or {}
            self.logger.info(
                'Discovery tag range: captured_at=%s stage=%s tag=%d surface=%s '
                'result=%s survey_distance_mm=%s bearing_error_rad=%s '
                'camera_distance_mm=%s margin=%s hamming=%s pose_error=%s '
                'localized=%s localization_age_s=%s robot_heading_rad=%s.',
                captured_at, self._discovery_stage, tag_id,
                self._landmark_surface(tag_id), result, distance, bearing,
                item.get('distance_mm'), item.get('decision_margin'),
                item.get('hamming'), tag_pose.get('error'),
                bool(pose and pose.get('localized')),
                None if pose is None else pose.get('localization_age'),
                None if pose is None else pose.get('heading_rad'),
            )

    def _wall_boundary_waypoint(self, pose):
        """Seek the nearest inset map edge, then traverse it with wall on right."""
        names = ('cols', 'rows', 'cell_size_mm', 'origin_x', 'origin_y', 'robot_radius_mm')
        values = [getattr(self.mapper, name, None) for name in names]
        if not all(isinstance(value, (int, float)) for value in values):
            return None
        cols, rows, pitch, ox, oy, radius = values
        inset = radius + 100.0
        xmin, xmax = ox + inset, ox + cols * pitch - inset
        ymin, ymax = oy + inset, oy + rows * pitch - inset
        if xmin >= xmax or ymin >= ymax:
            return None
        x, y = pose['x_mm'], pose['y_mm']
        corners = ((xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin))
        goal = getattr(self, '_wall_boundary_goal', None)
        if goal is None:
            candidates = ((xmin, min(ymax, max(ymin, y))),
                          (min(xmax, max(xmin, x)), ymax),
                          (xmax, min(ymax, max(ymin, y))),
                          (min(xmax, max(xmin, x)), ymin))
            skip = getattr(self, '_wall_boundary_skip_edge', None)
            edge = ((skip - 1) % 4 if skip is not None else
                    min(range(4), key=lambda i: hypot(candidates[i][0] - x, candidates[i][1] - y)))
            self._wall_boundary_skip_edge = None
            self._wall_boundary_edge = edge
            goal = candidates[edge]
        if hypot(goal[0] - x, goal[1] - y) < 70:
            edge = getattr(self, '_wall_boundary_edge', 0)
            next_corner = corners[edge]
            if goal == next_corner:
                edge = (edge - 1) % 4
            self._wall_boundary_edge = edge
            goal = corners[edge]
        self._wall_boundary_goal = goal
        return goal

    def _discovery_route_target(self, target, pose):
        """Follow mapped free cells after an obstacle, keeping the final goal."""
        if self._discovery_avoid_attempts == 0:
            return target
        step = self._discovery_route_step
        if (step is not None and self._discovery_route_goal == target and
                hypot(step[0] - pose['x_mm'], step[1] - pose['y_mm']) > 35):
            return step
        plan = self.mapper.plan_to(*target)
        if not isinstance(plan, dict) or not plan.get('path'):
            return None
        path = plan['path']
        if len(path) <= 2:
            step = target
        else:
            # Use the end of the first straight section. Never cut across
            # a corner, which could cross an inflated obstacle cell.
            direction = (path[1][0] - path[0][0], path[1][1] - path[0][1])
            end = 1
            while end + 1 < len(path):
                delta = (path[end + 1][0] - path[end][0],
                         path[end + 1][1] - path[end][1])
                if delta != direction:
                    break
                end += 1
            step = self.mapper.cell_center(path[end])
        self._discovery_route_goal = target
        self._discovery_route_step = step
        self.logger.info('Discovery mapped route: goal_mm=%s next_waypoint_mm=%s cells=%d.',
                         target, step, len(path))
        return step

    @staticmethod
    def _tag_approach_waypoint(world_from_tag, offset_mm):
        """Return a staging point offset from the tag face into the room."""
        tag = world_from_tag
        return (
            float(tag[0][3]) * 1000.0 - float(tag[0][2]) * offset_mm,
            float(tag[1][3]) * 1000.0 - float(tag[1][2]) * offset_mm,
        )
    @staticmethod
    def _tag_normal_heading(world_from_tag):
        """Return heading toward the tag from its inward-facing normal."""
        return atan2(float(world_from_tag[1][2]),
                     float(world_from_tag[0][2]))
    @staticmethod
    def _turn_action(reason, error):
        """Build a continuous in-place turn toward a positive angular error."""
        return {
            'kind': TURN,
            'reason': reason,
            'steering': 1.0 if error > 0 else -1.0,
            'velocity': min(DISCOVERY_TURN_SPEED,
                            max(MIN_TURN_SPEED, int(abs(error) * ROBOT.WHEEL_BASE))),
            'max_duration_s': SPIN_WATCHDOG_SECONDS,
            'continuous': True,
        }
    def _discovery_travelled_mm(self, state):
        current = state.get('travelled_distance')
        if current is None:
            return 0.0
        if self._discovery_start_travelled is None:
            self._discovery_start_travelled = float(current)
            return 0.0
        return max(
            0.0,
            float(current) - float(self._discovery_start_travelled),
        )
    def _discovery_visit_order(self):
        """Return configured visit landmarks after the tag 1 departure scan."""
        excluded = {DISCOVERY_INITIAL_TAG_ID, DISCOVERY_TAG_ID}
        return [
            int(tag_id) for tag_id in self.discovery_landmarks
            if int(tag_id) not in excluded
        ]
    def _landmark_surface(self, tag_id):
        target = self.discovery_landmarks.get(tag_id) or {}
        return str(target.get('surface', 'unknown'))
    def _discovery_return_route(self):
        """Return directly toward tag 1's retreat point using mapped routes."""
        return [(DOCK_X_MM, DOCK_Y_MM + RETREAT_MM)]
    def _begin_discovery_visit(self):
        """Start the next parking-and-scan visit, or return to the retreat point."""
        resume = getattr(self, '_discovery_scan_resume', None)
        if resume is not None:
            for name, value in resume.items():
                setattr(self, name, value)
            self._discovery_scan_resume = None
            self._discovery_route_step = None
            self._discovery_scan_time = None
            return
        if self._discovery_visit_tags is None:
            self._discovery_visit_tags = self._discovery_visit_order()
        while self._discovery_visit_index < len(self._discovery_visit_tags):
            tag_id = self._discovery_visit_tags[self._discovery_visit_index]
            target = self.discovery_landmarks.get(tag_id) or {}
            world_from_tag = target.get('world_from_tag')
            if world_from_tag is not None:
                self._discovery_visit_tag = tag_id
                self._discovery_visit_heading_offset = 0.0
                self._discovery_visit_retry_index = 0
                self._discovery_visit_arrival_pose = None
                self._discovery_avoid_attempts = 0
                self._discovery_avoid_grace_start = None
                self._discovery_proximity_ticks = 0
                self._discovery_waypoint = self._tag_approach_waypoint(
                    world_from_tag, DISCOVERY_PARK_DISTANCE_MM,
                )
                self._discovery_stage = 'visit_approach'
                self._discovery_turning = False
                self.logger.info(
                    'Discovery visiting tag %d (%s) at %s; parking %.0f mm '
                    'from the tag face.',
                    tag_id, self._landmark_surface(tag_id),
                    self._discovery_waypoint, DISCOVERY_PARK_DISTANCE_MM,
                )
                return
            self.logger.error(
                'Discovery visit tag %d has no world_from_tag; skipping.', tag_id,
            )
            self._discovery_visit_index += 1
        self._discovery_stage = 'return'
        self._discovery_return_waypoints = self._discovery_return_route()
        self._discovery_return_index = 0
        self._discovery_waypoint = self._discovery_return_waypoints[0]
        self._discovery_turning = False
        self._discovery_avoid_attempts = 0
        self._discovery_avoid_grace_start = None
        self._discovery_proximity_ticks = 0
        self.logger.info(
            'Discovery tag visits complete; returning via %s.',
            self._discovery_return_waypoints,
        )
    def _unexpected_bumper_contact(self, stage, sensors, pose, state):
        """Recover from transit contact with another local detour."""
        if (stage in ('retreat', 'tag2_contact', 'release_contact',
                      'avoid_back', 'avoid_turn') or
                stage.endswith('_scan')):
            return False
        bumps = sensors.bumps_and_wheel_drops
        bump_left = bool(getattr(bumps, 'bump_left', False))
        bump_right = bool(getattr(bumps, 'bump_right', False))
        if not (bump_left or bump_right):
            return False
        if pose and pose.get('localized'):
            # The IR array misses some thin or low obstacles, but the bumper
            # still gives a precise contact point worth remembering.
            self._record_contact_obstacle(
                pose, self._contact_observation(sensors),
            )
        if stage != 'avoid_forward' and stage not in DISCOVERY_DETOUR_STAGES:
            self.logger.warning(
                'Discovery stopped on unexpected bumper contact: stage=%s '
                'bump_left=%s bump_right=%s pose=%s.',
                stage, bump_left, bump_right, pose,
            )
            self._stop_discovery_for_recovery(
                'discovery unexpected bumper contact',
            )
            return True
        side = self._light_bumper_side(sensors)
        if side is None:
            side = 'left' if bump_left else 'right'
        self.logger.warning(
            'Discovery bumper contact during %s: bump_left=%s bump_right=%s '
            'pose=%s; reversing and detouring away from the %s.',
            stage, bump_left, bump_right, pose, side,
        )
        return self._begin_discovery_avoid(
            stage, sensors, pose, state, side=side, source='contact',
        )
    def _log_discovery_visit_scan(self, state, pose, tag_id, ids):
        """Record the odometry correction and physical parking error at a visit."""
        target = self.discovery_landmarks.get(tag_id) or {}
        arrival = self._discovery_visit_arrival_pose
        waypoint = self._discovery_waypoint
        waypoint_error = None
        odometry_deviation = None
        heading_deviation = None
        facing_error = None
        distance_to_tag = None
        if pose is not None:
            if waypoint is not None:
                waypoint_error = hypot(
                    pose['x_mm'] - waypoint[0], pose['y_mm'] - waypoint[1],
                )
            if arrival is not None:
                odometry_deviation = hypot(
                    pose['x_mm'] - arrival['x_mm'],
                    pose['y_mm'] - arrival['y_mm'],
                )
                heading_deviation = self._wrap(
                    pose['heading_rad'] - arrival['heading_rad'],
                )
            world_from_tag = target.get('world_from_tag')
            if world_from_tag is not None:
                facing_error = self._wrap(
                    pose['heading_rad'] -
                    self._tag_normal_heading(world_from_tag)
                )
                distance_to_tag = hypot(
                    pose['x_mm'] - float(world_from_tag[0][3]) * 1000.0,
                    pose['y_mm'] - float(world_from_tag[1][3]) * 1000.0,
                )
        self.logger.info(
            'Discovery visit tag %d (%s) attempt %d: tags=%s expected=%d '
            'note=%s yaw_offset_rad=%.2f waypoint_error_mm=%s '
            'odometry_deviation_mm=%s heading_deviation_rad=%s '
            'facing_error_rad=%s distance_to_tag_mm=%s travelled_mm=%.0f '
            'arrival_pose=%s pose=%s',
            tag_id, self._landmark_surface(tag_id),
            self._discovery_visit_retry_index + 1, ids, tag_id,
            'expected tag visible' if tag_id in ids else 'expected tag missing',
            self._discovery_visit_heading_offset,
            None if waypoint_error is None else round(waypoint_error, 1),
            None if odometry_deviation is None else round(odometry_deviation, 1),
            None if heading_deviation is None else round(heading_deviation, 4),
            None if facing_error is None else round(facing_error, 4),
            None if distance_to_tag is None else round(distance_to_tag, 1),
            self._discovery_travelled_mm(state), arrival, pose,
        )
    @staticmethod
    def _light_bumper_levels(sensors):
        """Return raw light-bumper signals keyed by bumper zone."""
        names = ('left', 'front_left', 'center_left',
                 'center_right', 'front_right', 'right')
        return {
            name: int(getattr(
                sensors, 'light_bump_' + name + '_signal', 0,
            ) or 0)
            for name in names
        }
    @staticmethod
    def _light_bumper_contact(sensors):
        """Return True when any light-bumper contact bit is asserted."""
        light = getattr(sensors, 'light_bumper', None)
        if light is None:
            return False
        return any(
            bool(getattr(light, name, False))
            for name in ('left', 'front_left', 'center_left',
                         'center_right', 'front_right', 'right')
        )
    def _light_bumper_side(self, sensors):
        """Return the side with an early obstacle proximity reading."""
        levels = self._light_bumper_levels(sensors)
        light = getattr(sensors, 'light_bumper', None)
        def active(names):
            for name in names:
                if light is not None and bool(getattr(light, name, False)):
                    return True
                if levels[name] >= LIGHT_BUMPER_PROXIMITY_THRESHOLD:
                    return True
            return False
        left_zones = ('left', 'front_left', 'center_left')
        right_zones = ('center_right', 'front_right', 'right')
        left = active(left_zones)
        right = active(right_zones)
        if left and right:
            left_level = max(levels[name] for name in left_zones)
            right_level = max(levels[name] for name in right_zones)
            return 'left' if left_level >= right_level else 'right'
        if left:
            return 'left'
        if right:
            return 'right'
        return None
    def _stop_discovery_for_recovery(self, reason):
        self._blocked_waypoint = None
        self._send_stop(reason)
        self.logger.warning('Discovery ended; mission set to idle: %s.', reason)
        self._mode = MODE_IDLE
        self.navigation.set_mode(MODE_IDLE)
        self.robot_control.set_operation_indicators(False)
        self._flush_map(reason)
    def _begin_discovery_avoid(self, stage, sensors, pose, state,
                               side=None, source='proximity'):
        """Stop on proximity or contact and start a bounded local detour."""
        bumps = sensors.bumps_and_wheel_drops
        if bumps.bump_left != bumps.bump_right:
            side = 'left' if bumps.bump_left else 'right'
        elif bumps.bump_left and bumps.bump_right:
            side = choice(('left', 'right'))
        else:
            side = side or self._light_bumper_side(sensors)
        if side is None:
            return False
        levels = self._light_bumper_levels(sensors)
        light = getattr(sensors, 'light_bumper', None)
        bits = {
            name: bool(getattr(light, name, False))
            for name in ('left', 'front_left', 'center_left',
                         'center_right', 'front_right', 'right')
        } if light is not None else {}
        label = 'contact' if source == 'contact' else 'proximity'
        self._send_stop('discovery obstacle ' + label)
        self._discovery_avoid_attempts += 1
        if stage != 'avoid_forward':
            self._discovery_avoid_return_stage = stage
        self._discovery_route_step = None
        self._discovery_avoid_side = side
        self._discovery_avoid_start_travelled = state.get('travelled_distance')
        self._discovery_avoid_reverse_mm = uniform(30.0, 40.0)
        self._discovery_avoid_forward_mm = uniform(60.0, 120.0)
        turn = uniform(pi / 18, pi / 9)
        heading = (pose['heading_rad'] if pose is not None else
                   float(state.get('angle', 0)) * pi / 180.0)
        self.logger.info('Detour geometry: reverse_mm=%.0f turn_rad=%.3f forward_mm=%.0f.',
                         self._discovery_avoid_reverse_mm, turn,
                         self._discovery_avoid_forward_mm)
        # Obstacles on the right call for a left turn, and vice versa.
        direction = 1.0 if side == 'right' else -1.0
        self._discovery_avoid_turn_target = self._wrap(
            heading + direction * turn
        )
        self._discovery_stage = 'avoid_back'
        self._discovery_turning = False
        self._discovery_avoid_deadline = (
            monotonic() + DISCOVERY_AVOID_STAGE_TIMEOUT_SECONDS
        )
        self._discovery_proximity_ticks = 0
        self.logger.warning(
            'Discovery obstacle %s on the %s; stage=%s signals=%s bits=%s '
            'attempt=%d pose=%s; stopping to detour.',
            label, side, stage, levels, bits,
            self._discovery_avoid_attempts, pose,
        )
        return True
    def _discovery_avoid_tick(self, stage, state, pose, sensors):
        """Advance the reverse, turn, and parallel-leg obstacle detour."""
        now = monotonic()
        deadline = self._discovery_avoid_deadline
        if deadline is not None and now >= deadline:
            self.logger.error(
                'Discovery obstacle detour timed out during %s; mission '
                'stopped for recovery. pose=%s.', stage, pose,
            )
            self._stop_discovery_for_recovery(
                'discovery obstacle detour timeout',
            )
            return
        travelled = state.get('travelled_distance')
        start = self._discovery_avoid_start_travelled
        reverse_mm = getattr(self, '_discovery_avoid_reverse_mm', DISCOVERY_AVOID_REVERSE_MM)
        forward_mm = getattr(self, '_discovery_avoid_forward_mm', DISCOVERY_AVOID_FORWARD_MM)
        if stage == 'avoid_back':
            cleared = 0.0
            if travelled is not None and start is not None:
                cleared = max(0.0, float(travelled) - float(start))
            if cleared >= reverse_mm:
                self._send_stop('discovery obstacle reverse complete', smooth=True)
                self._discovery_stage = 'avoid_turn'
                self._discovery_avoid_deadline = (
                    monotonic() + DISCOVERY_AVOID_STAGE_TIMEOUT_SECONDS
                )
                self.logger.info(
                    'Discovery obstacle detour reversed %.0f mm; turning away.',
                    cleared,
                )
                return
            remaining = max(0.0, reverse_mm - cleared)
            self._dispatch({
                'kind': BACK_UP,
                'reason': 'reverse away from discovered obstacle',
                'velocity': -DISCOVERY_AVOID_SPEED,
                'max_duration_s': min(
                    DRIVE_WATCHDOG_SECONDS,
                    max(0.2, remaining / DISCOVERY_AVOID_SPEED + 0.1),
                ),
                'continuous': True,
            }, pose)
            return
        if stage == 'avoid_turn':
            target = self._discovery_avoid_turn_target
            if target is None:
                self._stop_discovery_for_recovery(
                    'discovery obstacle turn target missing',
                )
                return
            error = self._wrap(target - pose['heading_rad'])
            if abs(error) <= DISCOVERY_AVOID_TURN_TOLERANCE_RAD:
                self._send_stop('discovery obstacle turn complete', smooth=True)
                if self._discovery_avoid_return_stage == 'wall_follow':
                    self._discovery_stage = 'wall_follow'
                    self._discovery_avoid_deadline = None
                    self._wall_seen = False
                    self._wall_lost_at = None
                    self._wall_clear_start = travelled
                    self._wall_clear_deadline = monotonic() + 8
                    self._wall_clear_heading = pose['heading_rad']
                    self._wall_boundary_skip_edge = getattr(self, '_wall_boundary_edge', None)
                    self._wall_boundary_goal = None
                    return
                self._discovery_stage = 'avoid_forward'
                self._discovery_avoid_start_travelled = travelled
                self._discovery_avoid_deadline = (
                    monotonic() + DISCOVERY_AVOID_FORWARD_TIMEOUT_SECONDS
                )
                self.logger.info(
                    'Discovery turned away from the obstacle; driving a short '
                    'parallel leg before rejoining the route.',
                )
                return
            self._dispatch(
                self._turn_action(
                    'discovery turn away from obstacle', error,
                ), pose,
            )
            return
        if stage == 'avoid_forward':
            advanced = 0.0
            if travelled is not None and start is not None:
                advanced = max(0.0, float(travelled) - float(start))
            if advanced >= forward_mm:
                self._send_stop('discovery obstacle detour complete', smooth=True)
                return_stage = (
                    self._discovery_avoid_return_stage or 'visit_approach'
                )
                self._discovery_stage = return_stage
                self._discovery_turning = False
                self._discovery_avoid_deadline = None
                self.logger.info(
                    'Discovery detoured %.0f mm around the obstacle on the %s; '
                    'resuming %s toward %s.', advanced,
                    self._discovery_avoid_side, return_stage,
                    self._discovery_waypoint,
                )
                return
            self._dispatch({
                'kind': DRIVE,
                'reason': 'drive parallel to discovered obstacle',
                'velocity': DISCOVERY_AVOID_SPEED,
                'steering': 0.0,
                'max_duration_s': DRIVE_WATCHDOG_SECONDS,
                'continuous': True,
            }, pose)
            return
        self._stop_discovery_for_recovery(
            'discovery unknown obstacle detour stage',
        )
    def _choose_scan_heading(self, pose):
        """Aim the optical axis at a surveyed tag from its visible side."""
        if pose is None:
            return None
        camera = getattr(self.localizer, 'camera_from_robot', None)
        # Camera +Z is the optical axis, expressed in robot coordinates.
        yaw = 0.0
        if isinstance(camera, (tuple, list)):
            yaw = atan2(float(camera[2][1]), float(camera[2][0]))
        choices = []
        for tag_id, item in self.discovery_landmarks.items():
            tag = item['world_from_tag']
            dx = float(tag[0][3]) * 1000 - pose['x_mm']
            dy = float(tag[1][3]) * 1000 - pose['y_mm']
            distance = hypot(dx, dy)
            if not 250 <= distance <= 4000:
                continue
            # In our OI tag convention local +Z points into the mounting wall.
            toward_face = dx * float(tag[0][2]) + dy * float(tag[1][2])
            if toward_face / distance < .3:
                continue
            heading = self._wrap(atan2(dy, dx) - yaw)
            score = distance + 500 * abs(self._wrap(heading - pose['heading_rad']))
            choices.append((score, tag_id, heading))
        return None if not choices else min(choices)[1:]

    def _localization_recovery_tick(self, state, pose, new_detections, detection_timestamp):
        """Try bounded in-place viewpoints using encoder yaw, never blind transit."""
        now = monotonic()
        recovery = self._localization_recovery
        targeted = self._aim_scan_pending
        offsets = ((pi / 6, -pi / 6) if targeted else
                   tuple(i * pi / 6 for i in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6)))
        if recovery is None:
            self._send_stop('localization recovery initial scan')
            recovery = dict(origin=float(state.get('angle', 0)) * pi / 180,
                            index=0, phase='scan', captured_after=time(), deadline=now + 180)
            self._localization_recovery = recovery
            log = self.logger.info if targeted else self.logger.warning
            log('Targeted tag-view search: rejected=%s.' if targeted else
                'Discovery localization unavailable: rejected=%s; starting bounded tag-view search.',
                None if pose is None else pose.get('rejected_tags'))
            aimed = self._choose_scan_heading(pose)
            if aimed is None:
                self.camera.request_scan()
                return
            recovery['tag_id'], heading = aimed
            recovery['origin'] += self._wrap(heading - pose['heading_rad'])
            recovery.update(target=recovery['origin'], phase='turn', turn_deadline=now + 12)
            self.logger.info('Aiming tag search at tag %s heading %.1f degrees; 30-degree steps.',
                             recovery['tag_id'], heading * 180 / pi)
        if now >= recovery['deadline'] or (recovery['phase'] == 'turn' and now >= recovery['turn_deadline']):
            self._localization_recovery = None
            self._aim_scan_pending = False
            if self._blocked_waypoint is not None:
                self._blocked_waypoint['next_try'] = now + BLOCKED_RETRY_SECONDS
                self._send_stop('blocked-route tag search timed out; discovery remains paused')
            else:
                self._stop_discovery_for_recovery('localization viewpoint recovery timed out')
            return
        if recovery['phase'] == 'scan':
            if not new_detections or detection_timestamp is None or detection_timestamp < recovery['captured_after']:
                return
            needs_confirmation = pose is not None and any(
                'large relocation needs another consistent scan' in reason
                for key, reason in pose.get('rejected_tags', ()))
            if needs_confirmation and not recovery.get('confirming'):
                recovery.update(confirming=True, captured_after=time())
                self.logger.debug('Tag scan confirmation: target_tag=%s view=%d; '
                                  'holding heading for a second relocation scan.',
                                  recovery.get('tag_id'), recovery['index'])
                self.camera.request_scan()
                return
            recovery.pop('confirming', None)
            if recovery['index'] >= len(offsets):
                self._localization_recovery = None
                if targeted:
                    self._aim_scan_pending = False
                    self._aim_scan_cooldown = now + 20
                    self._send_stop('targeted views exhausted; resume route')
                else:
                    self._stop_discovery_for_recovery('localization viewpoints exhausted')
                return
            recovery['target'] = recovery['origin'] + offsets[recovery['index']]
            recovery['index'] += 1
            recovery['phase'] = 'turn'
            recovery['turn_deadline'] = now + 12
            self.logger.debug('Tag scan retry: target_tag=%s view=%d offset_deg=%.1f encoder_target_deg=%.1f.',
                recovery.get('tag_id'), recovery['index'], offsets[recovery['index']-1]*180/pi,
                recovery['target']*180/pi)
        bumps = state['sensors'].bumps_and_wheel_drops
        if bumps.bump_left or bumps.bump_right:
            self._send_stop('viewpoint turn blocked by contact')
            return
        error = self._wrap(recovery['target'] - float(state.get('angle', 0)) * pi / 180)
        if abs(error) <= .05:
            self._send_stop('localization viewpoint reached', smooth=True)
            recovery.update(phase='scan', captured_after=time())
            self.logger.debug('Tag scan aimed and stopped: target_tag=%s view=%d heading_deg=%s.',
                recovery.get('tag_id'), recovery['index'],
                None if pose is None else round(pose['heading_rad']*180/pi,1))
            self.camera.request_scan()
            return
        self._dispatch(self._turn_action('bounded localization viewpoint turn', error), pose)

    def _begin_blocked_waypoint_recovery(self, waypoint):
        """Preserve the mission goal and start bounded bump-and-go exploration."""
        self._send_stop('waypoint blocked; pause and replan')
        if self._blocked_waypoint is None:
            goal = (self._discovery_waypoint if self._discovery_stage in
                    ('tag2_approach','visit_approach','return','dock_approach')
                    and self._discovery_waypoint is not None else waypoint)
            self._blocked_waypoint = dict(goal=goal, searches=0, next_try=monotonic(),
                wander=dict(until=monotonic()+BUMP_GO_SECONDS, phase='choose'))
            self._aim_scan_pending = False
            self._localization_recovery = None
            self.logger.warning('Waypoint footprint blocked; discovery remains active. '
                                'Exploring for two minutes before retrying %s.', goal)
            self._announce_mode()
        self._discovery_route_step = None
        self._discovery_route_goal = None
        self._discovery_avoid_attempts = max(1,getattr(self,'_discovery_avoid_attempts',0))

    def _bump_go_tick(self, state, pose, roam):
        """Bounded straight exploration; encoder turns, contact retreat, no aiming."""
        now = monotonic()
        bumps = state['sensors'].bumps_and_wheel_drops
        contact = bumps.bump_left or bumps.bump_right
        angle = float(state.get('angle', 0)) * pi / 180
        distance = float(state.get('distance', 0))
        phase = roam['phase']
        if phase == 'scan':
            captured = self.camera.last_detection_time
            if ((isinstance(captured, (int, float)) and captured >= roam['scan_after'])
                    or now >= roam['scan_deadline']):
                roam.update(phase='choose', next_scan=now+20)
            return True
        if contact and phase not in ('back', 'release'):
            self._send_stop('bump and go contact')
            if pose and pose.get('localized') and state.get('battery_status') != 'charging':
                self._record_contact_obstacle(pose, self._contact_observation(state['sensors']))
            roam.update(phase='back', distance=distance, deadline=now+2,
                        contact_side=1 if bumps.bump_right and not bumps.bump_left else
                        -1 if bumps.bump_left and not bumps.bump_right else choice((-1, 1)))
            phase = 'back'
        if phase == 'back':
            if abs(distance-roam['distance']) >= 35 or now >= roam['deadline']:
                self._send_stop('bump and go retreat complete')
                roam['phase'] = 'release' if contact else 'choose'
            else:
                self._dispatch(dict(kind=BACK_UP, reason='bump and go retreat',
                    velocity=-30, max_duration_s=DRIVE_WATCHDOG_SECONDS,
                    continuous=True), pose)
            return True
        if phase == 'release':
            self._send_stop('bump and go waiting for bumper release')
            if not contact:
                roam['phase'] = 'choose'
            return True
        if now >= roam['until']:
            self._send_stop('bump and go complete; retry original target')
            self.logger.info('Bump and go complete; returning to %s.',
                             self._blocked_waypoint['goal'])
            return False
        if not pose or not pose.get('localized'):
            self._send_stop('bump and go waiting for localization')
            return True
        roam.setdefault('next_scan', now+20)
        if phase in ('choose', 'drive') and now >= roam['next_scan']:
            self._send_stop('bump and go periodic localization scan')
            roam.update(phase='scan', scan_after=time(), scan_deadline=now+12)
            self.camera.request_scan()
            return True
        if phase == 'choose':
            # Randomize a full circle, then prefer headings with a long clear ray.
            side = roam.get('contact_side')
            if side is not None:
                # A contact calls for a small correction away from that side.
                headings = [pose['heading_rad']+side*a*pi/180 for a in (10, 15, 20)]
            else:
                origin = uniform(-pi, pi)
                headings = [origin+i*2*pi/24 for i in range(24)]
            heading = None
            for horizon in ((150, 60) if side is not None else (600, 200)):
                clear = [h for h in headings if self.mapper.motion_is_clear(
                    dict(pose, heading_rad=h), DISCOVERY_SPEED, 0,
                    horizon / DISCOVERY_SPEED)]
                if clear:
                    heading = choice(clear)
                    break
            if heading is None and side is not None:
                # A fridge face needs a wider escape turn when small turns fail.
                headings = [pose['heading_rad']+side*a*pi/180 for a in (45, 60, 90, 120, 150, 180)]
                clear = [h for h in headings if self.mapper.motion_is_clear(
                    dict(pose, heading_rad=h), DISCOVERY_SPEED, 0, 150 / DISCOVERY_SPEED)]
                if clear:
                    heading = choice(clear)
            if heading is None:
                self._send_stop('bump and go no clear heading')
                return True
            roam.pop('contact_side', None)
            roam.update(phase='turn', target=angle+self._wrap(heading-pose['heading_rad']),
                        deadline=now+12)
            phase = 'turn'
        if phase == 'turn':
            error = self._wrap(roam['target']-angle)
            if abs(error) <= 0.05:
                self._send_stop('bump and go heading selected')
                roam.update(phase='drive', progress=distance, progress_at=now)
            elif now >= roam['deadline']:
                self._send_stop('bump and go turn timeout')
                roam['phase'] = 'choose'
            else:
                self._dispatch(self._turn_action('bump and go choose heading', error), pose)
            return True
        if not self.mapper.motion_is_clear(pose, DISCOVERY_SPEED, 0, DRIVE_WATCHDOG_SECONDS):
            self._send_stop('bump and go mapped obstacle')
            roam['phase'] = 'choose'
            return True
        if abs(distance-roam['progress']) >= 10:
            roam.update(progress=distance, progress_at=now)
        elif now-roam['progress_at'] > 3:
            self._send_stop('bump and go no forward progress')
            roam['phase'] = 'choose'
            return True
        self._dispatch(dict(kind=DRIVE, reason='bump and go straight exploration',
            velocity=DISCOVERY_SPEED, steering=0, max_duration_s=DRIVE_WATCHDOG_SECONDS,
            continuous=True), pose)
        return True

    def _blocked_waypoint_tick(self, state, pose, new_detections):
        blocked = self._blocked_waypoint
        if blocked is None:
            return False
        if blocked.get('wander') is not None:
            roam = blocked['wander']
            now = monotonic()
            roam.setdefault('next_route_try', now+10)
            bumps = state['sensors'].bumps_and_wheel_drops
            if (roam['phase'] in ('choose', 'drive') and now >= roam['next_route_try']
                    and pose and pose.get('localized') and not (bumps.bump_left or bumps.bump_right)):
                roam['next_route_try'] = now+10
                self._discovery_route_step = self._discovery_route_goal = None
                target = self._discovery_route_target(blocked['goal'], pose)
                action = dict(kind=GO_TO_WAYPOINT, reason='route available during bump and go',
                              waypoint=target, max_duration_s=DRIVE_WATCHDOG_SECONDS)
                if target is not None and self._command_for(action, pose) is not None:
                    self._send_stop('route available; leave bump and go')
                    blocked.pop('wander')
                    blocked['next_try'] = 0.0
                    self._announce_mode()
                    self._dispatch(action, pose)
                    return True
            if self._bump_go_tick(state, pose, blocked['wander']):
                return True
            blocked.pop('wander')
            self._announce_mode()
            blocked['next_try'] = 0.0
            self._discovery_route_step = self._discovery_route_goal = None
        bumps = state['sensors'].bumps_and_wheel_drops
        if bumps.bump_left or bumps.bump_right:
            # Keep the saved goal through contacts while retrying it as well.
            self._aim_scan_pending = False
            self._localization_recovery = None
            blocked['wander'] = dict(until=monotonic(), phase='choose')
            self._announce_mode()
            self._bump_go_tick(state, pose, blocked['wander'])
            return True
        if self._aim_scan_pending:
            return False  # Existing bounded viewpoint state machine owns this tick.
        now = monotonic()
        fresh_fix = bool(new_detections and pose and pose.get('accepted_tag_ids'))
        if now < blocked['next_try'] and not fresh_fix:
            self._send_stop('waiting to retry blocked route')
            return True
        if fresh_fix:
            self._discovery_route_step = self._discovery_route_goal = None
        if pose and pose.get('localized'):
            goal = blocked['goal']
            if hypot(goal[0]-pose['x_mm'],goal[1]-pose['y_mm']) <= 35:
                self._blocked_waypoint = None
                return False
            target = self._discovery_route_target(goal,pose)
            if target is not None:
                action = dict(kind=GO_TO_WAYPOINT,reason='recover blocked discovery route',
                              waypoint=target,max_duration_s=DRIVE_WATCHDOG_SECONDS)
                if self._command_for(action,pose) is not None:
                    blocked['next_try'] = 0.0
                    self._dispatch(action,pose)
                    return True
        self._send_stop('blocked route needs localization or another plan')
        self._discovery_route_step = self._discovery_route_goal = None
        blocked['next_try'] = now + BLOCKED_RETRY_SECONDS
        if blocked['searches'] < BLOCKED_VIEW_SEARCHES:
            blocked['searches'] += 1
            self._aim_scan_pending = True
            self._localization_recovery = None
            self.logger.info('Blocked-route localization search %d/%d; goal remains %s.',
                             blocked['searches'],BLOCKED_VIEW_SEARCHES,blocked['goal'])
            return False
        if pose and pose.get('localized'):
            blocked.update(searches=0, next_try=0.0,
                           wander=dict(until=now+BUMP_GO_SECONDS, phase='choose'))
            self.logger.warning('No route to %s; restarting bump-and-go with mapped obstacles preserved.',
                                blocked['goal'])
            self._announce_mode()
            return True
        # After bounded aiming attempts, remain stopped in discovery. Continue
        # occasional stationary captures/replans without random reverse loops.
        self.logger.info('Discovery paused: no clear route to %s; retrying in %.0f s.',
                         blocked['goal'],BLOCKED_RETRY_SECONDS)
        self.camera.request_scan()
        return True

    def _discovery_tick(self, state, pose, new_detections, detection_timestamp):
        self._set_cleaning_motors(False)
        sensors = state['sensors']
        self._discovery_ir_proximity = bool(sensors is not None and self._light_bumper_side(sensors))
        if sensors is None or state['age'] is None or state['age'] > 0.5:
            if not self._discovery_stale_logged:
                self.logger.warning(
                    'Discovery waiting for fresh sensor data: stage=%s age=%s.',
                    self._discovery_stage, state.get('age'),
                )
                self._discovery_stale_logged = True
            self._send_stop('discovery waiting for fresh sensors')
            return
        self._discovery_stale_logged = False
        if self._discovery_start_travelled is None:
            self._discovery_start_travelled = state.get('travelled_distance')
        stage = self._discovery_stage
        hazard_reasons = self._hard_hazard_reasons(state)
        bumps = sensors.bumps_and_wheel_drops
        if hazard_reasons:
            retreat_mm = None
            if (stage == 'retreat' and
                    self._discovery_retreat_start_travelled is not None and
                    state.get('travelled_distance') is not None):
                retreat_mm = max(
                    0.0,
                    float(state['travelled_distance']) -
                    float(self._discovery_retreat_start_travelled),
                )
            dock_departure = (
                retreat_mm is not None and
                retreat_mm < DISCOVERY_DOCK_ESCAPE_MM
            )
            if dock_departure:
                now = monotonic()
                if self._discovery_hazard_since is None:
                    self._discovery_hazard_since = now
                    self.logger.warning(
                        'Discovery pausing on a dock departure safety reading: '
                        'stage=%s travelled=%.0f mm age=%s reasons=%s.',
                        stage, retreat_mm, state.get('age'), hazard_reasons,
                    )
                if (now - self._discovery_hazard_since <
                        DISCOVERY_DOCK_HAZARD_GRACE_SECONDS):
                    self._send_stop('discovery dock departure safety pause')
                    return
            bump_left = bump_right = None
            light_bumpers = None
            if sensors is not None:
                bump_left = bumps.bump_left
                bump_right = bumps.bump_right
                light = getattr(sensors, 'light_bumper', None)
                if light is not None:
                    light_bumpers = {
                        name: bool(getattr(light, name))
                        for name in ('left', 'front_left', 'center_left',
                                     'center_right', 'front_right', 'right')
                    }
            self.logger.warning(
                'Discovery aborted by hard safety condition: stage=%s age=%s '
                'reasons=%s bump_left=%s bump_right=%s light_bumpers=%s',
                stage, state.get('age'), hazard_reasons,
                bump_left, bump_right, light_bumpers,
            )
            self._send_stop('discovery hard safety condition')
            self._mode = MODE_IDLE
            self._blocked_waypoint = None
            self.navigation.set_mode(MODE_IDLE)
            self.robot_control.set_operation_indicators(False)
            self._flush_map('discovery hard safety stop')
            return
        self._discovery_hazard_since = None
        if (self._aim_scan_pending and (bumps.bump_left or bumps.bump_right)
                and stage in ('visit_approach', 'return', 'dock_approach')
                and pose and pose.get('localized') and self._discovery_waypoint is not None):
            # A held bumper prevents the scan turn; retreat instead of timing out.
            self._aim_scan_pending = False
            self._localization_recovery = None
            self._begin_blocked_waypoint_recovery(self._discovery_waypoint)
        if self._blocked_waypoint_tick(state,pose,new_detections):
            return
        if self._aim_scan_pending:
            if new_detections and pose and pose.get('accepted_tag_ids'):
                self._aim_scan_pending = False
                self._localization_recovery = None
                self._aim_scan_cooldown = monotonic() + 20
                self.logger.info('Targeted tag search accepted %s.', pose['accepted_tag_ids'])
                if self._blocked_waypoint is not None:
                    self._blocked_waypoint['next_try'] = 0.0
                    self._discovery_route_step = self._discovery_route_goal = None
                    return  # Next tick replans the preserved goal through recovery.
            else:
                self._localization_recovery_tick(state, pose, new_detections, detection_timestamp)
                return
        if (new_detections and pose and pose.get('localized') and
                not pose.get('accepted_tag_ids') and
                stage in ('wall_follow', 'visit_approach', 'return') and
                getattr(self, '_discovery_scan_resume', None) is None):
            accepted = set(pose.get('accepted_tag_ids', ()))
            rejected = dict(pose.get('rejected_tags', ()))
            tried = getattr(self, '_discovery_repositioned_tags', set())
            for detection in self.camera.latest_detections:
                tag_id = int(detection['id'])
                key = (detection.get('family', 'tag16h5'), tag_id)
                reason = rejected.get(key, '')
                # Translation recovery is only for a geometrically usable
                # pose that disagrees with odometry. Bad image geometry is
                # not evidence that we should drive to the apparent landmark.
                pose_jump = (reason.startswith('jump ') or
                             reason == 'large relocation needs another consistent scan')
                completed_dock_tag = (tag_id in (DISCOVERY_INITIAL_TAG_ID, DISCOVERY_TAG_ID) and
                                      self._discovery_visit_tags is not None)
                if (tag_id not in self.discovery_landmarks or key in accepted or
                        not pose_jump or completed_dock_tag or
                        tag_id in tried or detection.get('hamming', 1) != 0 or
                        detection.get('decision_margin', 0) < 10):
                    continue
                self._discovery_repositioned_tags = tried | {tag_id}
                names = ('_discovery_stage', '_discovery_waypoint',
                         '_discovery_visit_tag', '_discovery_visit_index',
                         '_discovery_visit_retry_index', '_discovery_visit_heading_offset')
                self._discovery_scan_resume = {name: getattr(self, name, None) for name in names}
                self._discovery_visit_tag = tag_id
                self._discovery_visit_retry_index = 0
                self._discovery_visit_heading_offset = 0.0
                self._discovery_visit_arrival_pose = None
                self._discovery_waypoint = self._tag_approach_waypoint(
                    self.discovery_landmarks[tag_id]['world_from_tag'], DISCOVERY_PARK_DISTANCE_MM)
                self._discovery_route_step = None
                self._discovery_stage = 'visit_approach'
                self._send_stop('reposition for rejected tag scan', smooth=True)
                self.logger.info('Repositioning for rejected tag %d using its surveyed face.', tag_id)
                return
        if stage == 'avoid_back':
            self._discovery_avoid_tick(stage, state, pose, sensors)
            return
        if stage == 'wall_follow':
            if pose and pose.get('localized'):
                self._localization_recovery = None
            if new_detections and pose and pose.get('accepted_tag_ids'):
                self.logger.info('Wall-follow accepted tags: %s', pose['accepted_tag_ids'])
            bumps = sensors.bumps_and_wheel_drops
            if bumps.bump_left or bumps.bump_right:
                self._begin_discovery_avoid(stage, sensors, pose, state,
                    side='right' if bumps.bump_right else 'left', source='contact')
                return
            if pose is None or not pose.get('localized'):
                self._localization_recovery_tick(state, pose, new_detections, detection_timestamp)
                return
            if self._wall_clear_start is not None:
                travelled = state.get('travelled_distance')
                cleared = 0 if travelled is None else float(travelled) - self._wall_clear_start
                if cleared < 180 and monotonic() >= self._wall_clear_deadline:
                    self._stop_discovery_for_recovery('wall clearance made no progress')
                    return
                if cleared < 180:
                    error = self._wrap(self._wall_clear_heading - pose['heading_rad'])
                    self._dispatch({'kind': DRIVE, 'reason': 'clear wall contact before boundary seeking',
                        'velocity': WALL_FOLLOW_SPEED, 'steering': max(-.15, min(.15, error)),
                        'continuous': True, 'max_duration_s': 1.0}, pose)
                    return
                self._wall_clear_start = None
            target = float(self.wall_follow.get('target_signal', 300))
            signal = float(getattr(sensors, 'wall_signal', 0))
            steering = max(-0.3, min(0.3, (signal - target) / max(target, 1) * 0.25))
            visible = bool(getattr(sensors, 'wall_sensor', False)) or signal >= target * 0.3
            if visible:
                self._wall_seen = True
                self._wall_lost_at = None
            elif not getattr(self, '_wall_seen', False):
                steering = 0.0  # Acquire a wall by driving forward, not circling.
            else:
                if getattr(self, '_wall_lost_at', None) is None:
                    self._wall_lost_at = monotonic()
                if monotonic() - self._wall_lost_at > 20.0:
                    self._wall_seen = False
                    self._wall_lost_at = None
                    steering = 0.0

            if not visible and not getattr(self, '_wall_seen', False):
                boundary = self._wall_boundary_waypoint(pose)
                if boundary is not None:
                    self._dispatch({'kind': GO_TO_WAYPOINT,
                        'reason': 'seek assumed map outline wall', 'waypoint': boundary,
                        'continuous': True, 'max_duration_s': 1.0}, pose)
                    return
            self._dispatch({'kind': FOLLOW_WALL, 'reason': 'discovery right wall survey',
                'velocity': WALL_FOLLOW_SPEED, 'steering': steering, 'continuous': True,
                'max_duration_s': 1.0}, pose)
            return
        if self._unexpected_bumper_contact(stage, sensors, pose, state):
            return
        if stage.endswith('_scan'):
            self._send_stop('discovery stationary scan', smooth=True)
            if self._discovery_scan_time is None:
                self._discovery_scan_time = time()
                if stage == 'visit_scan':
                    self._discovery_visit_arrival_pose = (
                        None if pose is None else dict(pose)
                    )
                self.camera.request_scan()
                return
            if not new_detections or detection_timestamp is None or detection_timestamp < self._discovery_scan_time:
                return
            ids = sorted({int(key[1]) for key in
                          (() if pose is None else pose.get('accepted_tag_ids', ()))})
            if stage == 'visit_scan':
                expected = self._discovery_visit_tag
            elif stage in ('initial_scan', 'retreat_scan'):
                expected = DISCOVERY_INITIAL_TAG_ID
            else:
                expected = DISCOVERY_TAG_ID
            if stage == 'visit_scan':
                self._log_discovery_visit_scan(state, pose, expected, ids)
            else:
                discrepancy = ('expected tag missing' if expected not in ids
                               else 'expected tag visible')
                if stage == 'initial_scan' and pose is not None:
                    discrepancy += '; dock pose error {:.0f} mm'.format(
                        hypot(pose['x_mm'] - DOCK_X_MM, pose['y_mm'] - DOCK_Y_MM)
                    )
                self.logger.info(
                    'Discovery %s: tags=%s expected=%d surface=%s note=%s pose=%s',
                    stage, ids, expected, self._landmark_surface(expected),
                    discrepancy, pose,
                )
            self._discovery_logged_tags.add(stage)
            self._discovery_scan_time = None
            if stage == 'initial_scan':
                self._discovery_retreat_start_distance = state.get('distance')
                self._discovery_retreat_start_travelled = state.get('travelled_distance')
                self._discovery_retreat_bumper_cleared = False
                self._discovery_stage = 'retreat'
                self._discovery_waypoint = (DOCK_X_MM, DOCK_Y_MM + RETREAT_MM)
            elif stage == 'retreat_scan':
                if not ids:
                    self._discovery_retreat_scan_failures += 1
                    if self._discovery_retreat_scan_failures >= 3:
                        self._stop_discovery_for_recovery(
                            'no accepted surveyed tag after retreat; reacquire localization before landmark visits')
                    else:
                        self._send_stop('retreat scan needs a fresh tag fix', smooth=True)
                        self.logger.warning(
                            'Retreat scan has no accepted tag (%d/3); holding position for another scan.',
                            self._discovery_retreat_scan_failures)
                        # Leave scan_time clear; the scan-state handler requests
                        # the next capture on the next tick without moving.
                    return
                self._discovery_retreat_scan_failures = 0
                self.logger.info('Discovery departure localized; skipping tag 2 and starting landmark visits.')
                self._begin_discovery_visit()
            elif stage == 'tag2_approach_scan':
                retry = getattr(self, '_tag2_retry_index', 0)
                if DISCOVERY_TAG_ID not in ids and retry < 2:
                    self._tag2_heading_offset = (0.5, -0.5)[retry]
                    self._tag2_retry_index = retry + 1
                    self._discovery_stage = 'tag2_align'
                    self.logger.warning(
                        'Tag 2 scan has no accepted fix; retrying in place at yaw offset %+.2f rad.',
                        self._tag2_heading_offset)
                    return
                self._tag2_heading_offset = 0.0
                if DISCOVERY_TAG_ID not in ids:
                    self._stop_discovery_for_recovery(
                        'tag 2 not accepted after three stationary views; no blind contact approach')
                    return
                # Restore the surveyed heading before intentional contact.
                if abs(self._wrap(self._tag_normal_heading(
                        self.discovery_landmarks[DISCOVERY_TAG_ID]['world_from_tag']
                ) - pose['heading_rad'])) > TAG2_ALIGN_TOLERANCE_RAD:
                    self._discovery_stage = 'tag2_contact_align'
                else:
                    self._discovery_stage = 'tag2_contact'
            elif stage == 'visit_scan':
                if expected in ids:
                    self.logger.info(
                        'Discovery tag %d visit scan complete; recorded %s '
                        'parking data.',
                        expected, self._landmark_surface(expected),
                    )
                    self._discovery_visit_index += 1
                    self._begin_discovery_visit()
                elif (self._discovery_visit_retry_index <
                        len(VISIT_RETRY_LATERAL_OFFSETS_MM)):
                    offset = VISIT_RETRY_LATERAL_OFFSETS_MM[
                        self._discovery_visit_retry_index
                    ]
                    self._discovery_visit_retry_index += 1
                    self._discovery_visit_heading_offset = 0.0
                    tag = self.discovery_landmarks[expected]['world_from_tag']
                    base = self._tag_approach_waypoint(tag, DISCOVERY_PARK_DISTANCE_MM)
                    heading = self._tag_normal_heading(tag)
                    shift = offset
                    self._discovery_waypoint = (base[0] - sin(heading) * shift,
                                                base[1] + cos(heading) * shift)
                    self._discovery_route_step = None
                    self._discovery_stage = 'visit_approach'
                    self.logger.warning(
                        'Discovery tag %d was not visible at the visit point; '
                        'repositioning for scan %d with lateral offset %+.0f mm.',
                        expected, self._discovery_visit_retry_index, offset,
                    )
                else:
                    self.logger.warning(
                        'Discovery tag %d was not visible after %d visit scans; '
                        'continuing with surveyed geometry.',
                        expected, self._discovery_visit_retry_index + 1,
                    )
                    self._discovery_visit_index += 1
                    self._begin_discovery_visit()
            return
        if pose is None or not pose.get('localized'):
            self._localization_recovery_tick(state, pose, new_detections, detection_timestamp)
            return
        self._localization_recovery = None
        self._discovery_localization_stale_logged = False
        if stage in DISCOVERY_AVOID_STAGES:
            self._discovery_avoid_tick(stage, state, pose, sensors)
            return
        if stage == 'retreat':
            target = self._discovery_waypoint
            retreat_start = self._discovery_retreat_start_distance
            current_distance = state.get('distance')
            retreat_travelled_start = self._discovery_retreat_start_travelled
            travelled_now = state.get('travelled_distance')
            if retreat_travelled_start is not None and travelled_now is not None:
                encoder_retreat = max(
                    0.0, float(travelled_now) - float(retreat_travelled_start)
                )
            else:
                encoder_retreat = (
                    None if retreat_start is None or current_distance is None else
                    abs(float(current_distance) - float(retreat_start))
                )
            bumps = sensors.bumps_and_wheel_drops
            if not bumps.bump_left and not bumps.bump_right:
                self._discovery_retreat_bumper_cleared = True
            elif self._discovery_retreat_bumper_cleared:
                self.logger.warning(
                    'Discovery retreat stopped on bumper contact after clearing dock: '
                    'odometry_delta_mm=%s bump_left=%s bump_right=%s.',
                    None if encoder_retreat is None else round(encoder_retreat),
                    bumps.bump_left, bumps.bump_right,
                )
                self._send_stop('obstacle contacted during dock retreat')
                self._mode = MODE_IDLE
                self.navigation.set_mode(MODE_IDLE)
                self.robot_control.set_operation_indicators(False)
                self._flush_map('dock retreat contact')
                return
            pose_reached = hypot(
                target[0] - pose['x_mm'], target[1] - pose['y_mm']
            ) <= 35
            if ((encoder_retreat is not None and encoder_retreat >= RETREAT_MM)
                    or (encoder_retreat is None and pose_reached)):
                self.logger.info(
                    'Discovery reverse distance by Roomba odometry: %.0f mm (target %.0f mm).',
                    encoder_retreat if encoder_retreat is not None else RETREAT_MM,
                    RETREAT_MM,
                )
                self._send_stop('50 cm reverse retreat complete', smooth=True)
                self._discovery_stage = 'retreat_scan'
                return
            self._dispatch({
                'kind': BACK_UP, 'reason': 'reverse out of charging dock',
                'velocity': -DISCOVERY_REVERSE_SPEED,
                'max_duration_s': DRIVE_WATCHDOG_SECONDS,
                'continuous': True,
            }, pose)
            return
        if stage in ('tag2_approach', 'visit_approach', 'return', 'dock_approach'):
            target = self._discovery_waypoint
            dx, dy = target[0] - pose['x_mm'], target[1] - pose['y_mm']
            distance = hypot(dx, dy)
            if distance <= 35:
                self._send_stop('discovery waypoint reached', smooth=True)
                if stage == 'return':
                    self._discovery_return_index += 1
                    remaining = self._discovery_return_waypoints[
                        self._discovery_return_index:
                    ]
                    if remaining:
                        self._discovery_waypoint = remaining[0]
                        self._discovery_turning = False
                        self._discovery_avoid_attempts = 0
                        self._discovery_proximity_ticks = 0
                        self.logger.info(
                            'Discovery return checkpoint reached; next '
                            'waypoint %s.', self._discovery_waypoint,
                        )
                        return
                    # After reaching the retreat point, approach the dock
                    self._discovery_stage = 'dock_approach'
                    self._discovery_waypoint = (
                        self._tag_approach_waypoint(
                            self.discovery_landmarks[DISCOVERY_INITIAL_TAG_ID]['world_from_tag'],
                            DOCK_APPROACH_MM,
                        ) if DISCOVERY_INITIAL_TAG_ID in self.discovery_landmarks
                        else (DOCK_X_MM, DOCK_Y_MM + DOCK_APPROACH_MM)
                    )
                    self._discovery_turning = False
                    self._discovery_avoid_attempts = 0
                    self._discovery_proximity_ticks = 0
                    self._discovery_scan_time = None
                    self.logger.info(
                        'Discovery returning to dock; approaching to within '
                        '%.0f mm in front of dock.',
                        DOCK_APPROACH_MM,
                    )
                    return
                if stage == 'dock_approach':
                    self._discovery_stage = 'dock_align'
                    self._discovery_turning = False
                    self.logger.info(
                        'Discovery reached dock approach point; aligning to face dock.',
                    )
                    return
                next_stage = {
                    'tag2_approach': 'tag2_align',
                    'visit_approach': 'visit_align',
                }[stage]
                self._discovery_stage = next_stage
                self._discovery_turning = False
                if next_stage == 'complete':
                    self.logger.info(
                        'Discovery sequence complete at 50 cm retreat point: '
                        'travelled_mm=%.0f localization_age=%s pose=%s.',
                        self._discovery_travelled_mm(state),
                        pose.get('localization_age'), pose,
                    )
                    self._mode = MODE_IDLE
                    self.robot_control.set_operation_indicators(False)
                    self._flush_map('discovery complete')
                elif next_stage == 'visit_align':
                    self._discovery_scan_time = None
                    self.logger.info(
                        'Discovery reached tag %d parking point; aligning to '
                        'the configured tag normal.', self._discovery_visit_tag,
                    )
                return
            if stage in ('tag2_approach', 'visit_approach', 'return'):
                route_target = self._discovery_route_target(target, pose)
                if route_target is None:
                    self._begin_blocked_waypoint_recovery(target)
                    return
                target = route_target
            self._dispatch({'kind': GO_TO_WAYPOINT, 'reason': 'discovery ' + stage,
                            'max_duration_s': DRIVE_WATCHDOG_SECONDS,
                            'waypoint': target}, pose)
            self._discovery_turning = bool(
                self._active_command and self._active_command[0] in ('spin_left', 'spin_right'))
            return
        if stage == 'dock_align':
            heading = (
                self._tag_normal_heading(self.discovery_landmarks[DISCOVERY_INITIAL_TAG_ID]['world_from_tag'])
                if DISCOVERY_INITIAL_TAG_ID in self.discovery_landmarks else DOCK_HEADING_RAD
            )
            error = self._wrap(heading - pose['heading_rad'])
            if abs(error) <= TAG2_ALIGN_TOLERANCE_RAD:
                self._send_stop('facing dock', smooth=True)
                self._mode = MODE_IDLE
                self.navigation.set_mode(MODE_IDLE)
                self.robot_control.set_operation_indicators(False)
                try:
                    self.robot_control.execute('_change_mode', mode=MODES.PASSIVE)
                except Exception:
                    self._discovery_stage = 'passive_failed'
                    self.logger.exception('Discovery stopped at staging point; unable to enter Passive mode.')
                    self._flush_map('discovery passive mode failed')
                    return
                self._discovery_stage = 'complete'
                self.logger.info(
                    'Discovery facing tag 1 at heading %.2f rad; Passive mode, ready for operator parking.',
                    heading,
                )
                self._flush_map('discovery complete')
                return
            self._dispatch(self._turn_action('discovery align to dock', error), pose)
            return
        if stage in ('tag2_align', 'tag2_contact_align'):
            target = self.discovery_landmarks.get(DISCOVERY_TAG_ID)
            if target is None:
                self._send_stop('tag 2 orientation is not configured')
                self.logger.error('Discovery requires surveyed AprilTag %d.', DISCOVERY_TAG_ID)
                self._mode = MODE_IDLE
                self._flush_map('discovery missing tag')
                return
            target_heading = self._tag_normal_heading(target['world_from_tag'])
            if stage == 'tag2_align':
                tag = target['world_from_tag']
                target_heading = self._wrap(
                    atan2(float(tag[1][3]) * 1000 - pose['y_mm'],
                          float(tag[0][3]) * 1000 - pose['x_mm']) +
                    getattr(self, '_tag2_heading_offset', 0.0))
            error = self._wrap(target_heading - pose['heading_rad'])
            if abs(error) <= TAG2_ALIGN_TOLERANCE_RAD:
                if stage == 'tag2_contact_align':
                    self._send_stop('tag 2 contact heading restored', smooth=True)
                    self._discovery_stage = 'tag2_contact'
                    return
                self._send_stop('tag 2 aligned for approach scan', smooth=True)
                self._discovery_stage = 'tag2_approach_scan'
                self.logger.info(
                    'Discovery aligned to face tag %d at heading %.2f rad; '
                    'requesting approach scan.', DISCOVERY_TAG_ID, target_heading,
                )
                return
            self._dispatch(self._turn_action('discovery align to tag 2', error), pose)
            return
        if stage == 'visit_align':
            tag_id = self._discovery_visit_tag
            target = self.discovery_landmarks.get(tag_id)
            if target is None or target.get('world_from_tag') is None:
                self._send_stop('visit tag orientation is not configured')
                self.logger.error(
                    'Discovery visit tag %s has no world_from_tag; skipping.',
                    tag_id,
                )
                self._discovery_visit_index += 1
                self._begin_discovery_visit()
                return
            target_heading = self._wrap(
                self._tag_normal_heading(target['world_from_tag']) +
                self._discovery_visit_heading_offset
            )
            error = self._wrap(target_heading - pose['heading_rad'])
            if abs(error) <= TAG2_ALIGN_TOLERANCE_RAD:
                self._send_stop('visit tag aligned for scan', smooth=True)
                self._discovery_stage = 'visit_scan'
                self._discovery_scan_time = None
                self.logger.info(
                    'Discovery aligned to visit tag %d at heading %.2f rad '
                    '(yaw offset %+.2f); requesting scan.',
                    tag_id, target_heading,
                    self._discovery_visit_heading_offset,
                )
                return
            self._dispatch(
                self._turn_action(
                    'discovery align to visit tag %d' % tag_id, error,
                ), pose,
            )
            return
        if stage == 'release_contact':
            now = monotonic()
            if self._discovery_release_deadline is None:
                self._discovery_release_deadline = now + RELEASE_TIMEOUT_SECONDS
            travelled = state.get('travelled_distance')
            if self._discovery_release_start_travelled is None:
                self._discovery_release_start_travelled = travelled
            if travelled is None or self._discovery_release_start_travelled is None:
                reversed_mm = 0.0
            else:
                reversed_mm = max(
                    0.0,
                    float(travelled) - float(self._discovery_release_start_travelled),
                )
            bumps = sensors.bumps_and_wheel_drops
            light = sensors.light_bumper
            light_contact = any((
                light.left, light.front_left, light.center_left,
                light.center_right, light.front_right, light.right,
            ))
            contact = bumps.bump_left or bumps.bump_right
            if contact:
                self._discovery_release_clear_since = None
            elif self._discovery_release_clear_since is None:
                self._discovery_release_clear_since = now

            clear_since = self._discovery_release_clear_since
            clear_held = (
                not contact and
                reversed_mm >= RELEASE_MIN_DISTANCE_MM and
                clear_since is not None and
                now - clear_since >= RELEASE_CLEAR_HOLD_SECONDS
            )
            if clear_held:
                self._send_stop('discovery reverse cleared the tag', smooth=True)
                if light_contact:
                    self.logger.info(
                        'Discovery tag %d light bumpers still report proximity '
                        'after %.0f mm; using the physical separation.',
                        DISCOVERY_TAG_ID, reversed_mm,
                    )
                self.logger.info(
                    'Discovery contact released after %.0f mm and %.1f s of '
                    'reverse; starting the remaining tag visits.',
                    reversed_mm, now - (self._discovery_release_started or now),
                )
                self._begin_discovery_visit()
                return
            if reversed_mm >= RELEASE_MAX_DISTANCE_MM:
                self._send_stop('discovery contact release distance reached', smooth=True)
                self.logger.error(
                    'Discovery could not separate from tag %d within %.0f mm '
                    'of reverse; mission stopped for recovery.',
                    DISCOVERY_TAG_ID, RELEASE_MAX_DISTANCE_MM,
                )
                self._mode = MODE_IDLE
                self.navigation.set_mode(MODE_IDLE)
                self.robot_control.set_operation_indicators(False)
                self._flush_map('discovery contact release distance reached')
                return
            if now >= self._discovery_release_deadline:
                self._send_stop('discovery could not clear contact')
                self.logger.error(
                    'Discovery could not separate from tag %d after %.1f s; '
                    'mission stopped for recovery.',
                    DISCOVERY_TAG_ID, RELEASE_TIMEOUT_SECONDS,
                )
                self._mode = MODE_IDLE
                self.navigation.set_mode(MODE_IDLE)
                self.robot_control.set_operation_indicators(False)
                self._flush_map('discovery contact release timeout')
                return
            remaining_mm = max(0.0, RELEASE_MAX_DISTANCE_MM - reversed_mm)
            duration = max(0.2, remaining_mm / DISCOVERY_REVERSE_SPEED + 0.1)
            self._dispatch({
                'kind': BACK_UP,
                'reason': 'reverse to separate from tag 2',
                'velocity': -DISCOVERY_REVERSE_SPEED,
                'max_duration_s': duration,
                'continuous': True,
            }, pose)
            return
        if stage == 'tag2_contact':
            bumps = sensors.bumps_and_wheel_drops
            if bumps.bump_left or bumps.bump_right:
                self._send_stop('tag 2 front bumper contact')
                if pose and pose.get('localized'):
                    self._record_contact_obstacle(
                        pose, self._contact_observation(sensors),
                    )
                self._discovery_stage = 'release_contact'
                self._discovery_release_started = monotonic()
                self._discovery_release_start_travelled = state.get('travelled_distance')
                self._discovery_release_deadline = (
                    self._discovery_release_started + RELEASE_TIMEOUT_SECONDS
                )
                self._discovery_release_clear_since = None
                self.logger.info(
                    'Discovery tag %d contact; reversing to separate from the tag.',
                    DISCOVERY_TAG_ID,
                )
                return
            target = self.discovery_landmarks.get(DISCOVERY_TAG_ID)
            if target is None:
                self._send_stop('tag 2 orientation is not configured')
                self._mode = MODE_IDLE
                self._flush_map('discovery missing tag')
                return
            target_heading = self._tag_normal_heading(target['world_from_tag'])
            heading_error = self._wrap(target_heading - pose['heading_rad'])
            if abs(heading_error) > HEADING_TOLERANCE_RAD:
                self._dispatch(
                    self._turn_action('discovery approach tag 2 heading',
                                      heading_error),
                    pose,
                )
                return
            heads_up = self._light_bumper_side(sensors) is not None
            speed = 25 if heads_up else DISCOVERY_SPEED
            self._dispatch({
                'kind': DRIVE,
                'reason': 'discovery approach tag 2',
                'velocity': speed,
                'steering': 0.0,
                'max_duration_s': DRIVE_WATCHDOG_SECONDS,
                'continuous': True,
            }, pose)
            return
        self._send_stop('discovery waiting')
    @classmethod
    def _hard_hazard_reasons(cls, state):
        """Return effective cliff/wheel-drop hazards from a controller snapshot."""
        if 'hard_hazard_reasons' in state:
            return list(state.get('hard_hazard_reasons') or ())
        sensors = state.get('sensors')
        if sensors is None:
            return ['sensors unavailable']
        bumps = sensors.bumps_and_wheel_drops
        reasons = []
        for name in ('wheel_drop_left', 'wheel_drop_right',
                     'cliff_left_sensor', 'cliff_front_left_sensor',
                     'cliff_front_right_sensor', 'cliff_right_sensor'):
            value = (getattr(bumps, name) if name.startswith('wheel_drop')
                     else getattr(sensors, name))
            if value:
                reasons.append(name)
        return reasons

    def _navigation_observation(self, state, pose):
        sensors = state['sensors']
        if sensors is None:
            return {
                'localized': False, 'pose': pose, 'hard_hazard': True,
                'bumper': {}, 'light_bumper': {},
            }
        bumps = sensors.bumps_and_wheel_drops
        light = sensors.light_bumper
        hard_hazard = (
            state.get('age') is None or state.get('age') > 0.5 or
            bool(self._hard_hazard_reasons(state))
        )
        return {
            'localized': bool(pose and pose.get('localized')),
            'pose': pose,
            'hard_hazard': hard_hazard,
            'bumper': {'left': bumps.bump_left, 'right': bumps.bump_right},
            'light_bumper': {
                'left': light.left, 'front_left': light.front_left,
                'center_left': light.center_left,
                'center_right': light.center_right,
                'front_right': light.front_right, 'right': light.right,
            },
            'wall_signal': {
                'value': float(getattr(sensors, 'wall_signal', 0)),
                'target': float(self.wall_follow.get('target_signal', 300)),
                'side': self.wall_follow.get('side', 'right'),
            } if (self.wall_follow.get('enabled') and
                  getattr(sensors, 'wall_sensor', False)) else None,
            'follow_wall': bool(self.wall_follow.get('enabled') and
                                getattr(sensors, 'wall_sensor', False)),
        }

    def _progress_status(self, state):
        signature = self._active_command
        if signature is None:
            self._progress_anchor_distance = None
            self._progress_since = monotonic()
            self._stuck_latched = False
            return False, False
        operation, kwargs = signature
        values = dict(kwargs)
        forward = (
            operation == 'drive_straight' and int(values.get('velocity', 0)) > 0
        ) or (
            operation == 'drive_direct' and
            int(values.get('right_velocity', 0)) > 0 and
            int(values.get('left_velocity', 0)) > 0
        )
        if not forward:
            self._progress_anchor_distance = None
            self._progress_since = monotonic()
            self._stuck_latched = False
            return False, False
        distance = float(state['distance'])
        now = monotonic()
        if self._progress_anchor_distance is None:
            self._progress_anchor_distance = distance
            self._progress_since = now
            return False, False
        if abs(distance - self._progress_anchor_distance) >= MIN_PROGRESS_MM:
            self._progress_anchor_distance = distance
            self._progress_since = now
            was_stuck = self._stuck_latched
            self._stuck_latched = False
            return False, was_stuck
        if not self._stuck_latched and now - self._progress_since >= NO_PROGRESS_SECONDS:
            self._stuck_latched = True
            self.logger.warning(
                'No wheel-odometry progress for %.1f seconds; requesting backtrack.',
                now - self._progress_since,
            )
            return True, False
        return False, False

    def _dispatch(self, action, pose):
        command = self._command_for(action, pose)
        if command is None:
            if (self._mode == MODE_DISCOVERY and action['kind'] == GO_TO_WAYPOINT
                    and pose and pose.get('localized') and
                    hypot(action['waypoint'][0] - pose['x_mm'],
                          action['waypoint'][1] - pose['y_mm']) > 35.0):
                self._begin_blocked_waypoint_recovery(action['waypoint'])
                return
            self._send_stop(action['reason'])
            return
        operation, kwargs, duration = command
        if self._mode == MODE_DISCOVERY:
            if getattr(self, '_discovery_ir_proximity', False):
                # IR scatter slows approach; only physical contact starts a detour.
                kwargs = dict(kwargs)
                for key in ('velocity', 'right_velocity', 'left_velocity'):
                    if operation in ('drive_straight', 'drive_direct') and kwargs.get(key, 0) > 40:
                        kwargs[key] = 40
        signature = (operation, tuple(sorted(kwargs.items())))
        continuous = bool(action.get('continuous',
                                     action.get('kind') == GO_TO_WAYPOINT))
        now = monotonic()
        if continuous and self._active_command is not None and now >= self._active_until:
            self._send_stop('continuous action watchdog expired', disable_cleaning=False)
            return
        reissue = False
        if signature == self._active_command:
            if continuous:
                # Refresh the watchdog instead of braking. The mission loop
                # refreshes this every tick, so stopping at the cap would turn
                # a smooth move into 0.2 s stop/start chunks.
                self._active_until = now + max(0.0, duration)
                if now < self._active_reissue_at:
                    return
                # Re-send periodically. If the arbiter braked for a safety
                # sensor and then cleared, this resumes the same motion; if it
                # is still blocked, the rejection clears _active_command so the
                # next tick can retry instead of pretending to move forever.
                reissue = True
            elif now < self._active_until:
                return
            else:
                self._send_stop('bounded action duration expired',
                                disable_cleaning=False, smooth=True)
                return
        if self._active_command is not None and not reissue:
            previous_operation, previous_kwargs = self._active_command
            previous_sign = self._drive_sign(previous_operation, dict(previous_kwargs))
            retune_same_drive = (
                continuous and
                ((previous_sign is not None and
                  previous_sign == self._drive_sign(operation, kwargs)) or
                 (previous_operation == operation and operation in ('spin_left', 'spin_right')))
            )
            if not retune_same_drive:
                self._send_stop('bounded action ended or changed',
                                disable_cleaning=False, smooth=True)
        started = monotonic()
        try:
            self.robot_control.execute(operation, **kwargs)
        except Exception:
            self._active_command = None
            self._active_until = 0.0
            self._active_reissue_at = 0.0
            self.logger.exception('Rejected navigation command %s %s', operation, kwargs)
            return
        elapsed = monotonic() - started
        self._active_command = signature
        self._stop_sent = False
        self._active_until = monotonic() + max(0.0, duration)
        self._active_reissue_at = (
            monotonic() + CONTINUOUS_REISSUE_SECONDS if continuous else 0.0
        )
        self.logger.debug(
            'Actuator command %s %s accepted in %.1f ms; duration cap %.2f s',
            operation, kwargs, elapsed * 1000.0, duration,
        )

    @staticmethod
    def _drive_sign(operation, kwargs):
        """Return 1/-1 when both wheels drive forward/reverse, else ``None``."""
        if operation == 'drive_straight':
            values = (int(kwargs.get('velocity', 0)),)
        elif operation == 'drive_direct':
            values = (int(kwargs.get('right_velocity', 0)),
                      int(kwargs.get('left_velocity', 0)))
        else:
            return None
        if any(value == 0 for value in values):
            return None
        signs = {(value > 0) - (value < 0) for value in values}
        return signs.pop() if len(signs) == 1 else None

    def _command_for(self, action, pose):
        kind = action['kind']
        duration = float(action.get('max_duration_s', 0.0))
        if kind == STOP or kind == WAIT:
            return None
        if kind == DOCK:
            return 'seek_dock', {}, float('inf')
        if kind == BACK_UP:
            return 'drive_straight', {'velocity': int(action['velocity'])}, duration
        if kind == SEEK_DOCK:
            return 'seek_dock', {}, float('inf')
        if kind == TURN:
            operation = ('spin_left' if float(action.get('steering', 0.0)) > 0
                         else 'spin_right')
            return operation, {'velocity': int(action['velocity'])}, duration
        if kind == GO_TO_WAYPOINT:
            return self._waypoint_command(action, pose, duration)
        if kind == FOLLOW_WALL:
            velocity = int(action['velocity'])
            steering = float(action['steering'])
            right = int(velocity * (1.0 + steering))
            left = int(velocity * (1.0 - steering))
            return 'drive_direct', {'right_velocity': right, 'left_velocity': left}, duration
        if kind == DRIVE:
            velocity = int(action['velocity'])
            steering = float(action.get('steering', 0.0))
            right = int(velocity * (1.0 + steering))
            left = int(velocity * (1.0 - steering))
            return 'drive_direct', {'right_velocity': right, 'left_velocity': left}, duration
        return None

    def _waypoint_command(self, action, pose, duration):
        """Steer toward a waypoint without stopping for ordinary corrections."""
        if not pose or not pose.get('localized'):
            return None
        dx = action['waypoint'][0] - pose['x_mm']
        dy = action['waypoint'][1] - pose['y_mm']
        distance = hypot(dx, dy)
        if distance <= 35.0:
            return None
        error = self._wrap(atan2(dy, dx) - pose['heading_rad'])
        was_turning = bool(self._active_command and
                           self._active_command[0] in ('spin_left', 'spin_right'))
        near = distance < WAYPOINT_NEAR_MM
        enter = WAYPOINT_NEAR_PIVOT_ENTER_RAD if near else WAYPOINT_PIVOT_ENTER_RAD
        leave = WAYPOINT_NEAR_PIVOT_EXIT_RAD if near else WAYPOINT_PIVOT_EXIT_RAD
        pivot = abs(error) > (leave if was_turning else enter)
        max_speed = DISCOVERY_SPEED if self._mode == MODE_DISCOVERY else NAVIGATION_SPEED
        if self._mode == MODE_DISCOVERY and getattr(self, '_discovery_ir_proximity', False):
            max_speed = min(max_speed, 40)
        if not pivot:
            # Pure-pursuit curvature, bounded so neither wheel reverses. Slow
            # down on bends and near the goal instead of overshooting it.
            steering = (ROBOT.WHEEL_BASE * sin(error) /
                        max(WAYPOINT_LOOKAHEAD_MM, distance))
            if abs(error) <= WAYPOINT_HEADING_DEADBAND_RAD:
                steering = 0.0
            steering = max(-WAYPOINT_MAX_STEERING, min(WAYPOINT_MAX_STEERING, steering))
            speed = max(25.0, min(max_speed * max(0.5, cos(error)), distance * 0.8))
            if not near and not getattr(self, '_discovery_ir_proximity', False):
                speed = max(speed, 30.0 / (1.0-abs(steering)))
            # Keep the outside wheel at or below the normal transit speed.
            speed = min(speed, max_speed / (1.0 + abs(steering)))
            right, left = int(speed * (1.0 + steering)), int(speed * (1.0 - steering))
            speed = (right + left) / 2.0
            yaw = (right - left) / ROBOT.WHEEL_BASE
            cap = min(duration, DRIVE_WATCHDOG_SECONDS, distance / max(speed, 1))
            if self.mapper.motion_is_clear(pose, speed, yaw, cap):
                if right == left:
                    return 'drive_straight', {'velocity': right}, cap
                return 'drive_direct', {'right_velocity': right, 'left_velocity': left}, cap
            # A curve cannot fit here. Align in place, then recheck forward
            # clearance next tick; never substitute an unchecked straight leg.
            if abs(error) <= TAG2_ALIGN_TOLERANCE_RAD:
                self.logger.debug('Waypoint motion blocked by mapped footprint; holding position.')
                return None
        operation = 'spin_left' if error > 0 else 'spin_right'
        limit = DISCOVERY_TURN_SPEED if self._mode == MODE_DISCOVERY else TURN_SPEED
        speed = min(limit, max(MIN_TURN_SPEED, int(abs(error) * ROBOT.WHEEL_BASE)))
        return operation, {'velocity': speed}, min(duration, SPIN_WATCHDOG_SECONDS)

    def _record_coverage(self, previous, current):
        if previous is None or not current.get('localized'):
            return
        distance = hypot(current['x_mm'] - previous['x_mm'],
                         current['y_mm'] - previous['y_mm'])
        spacing = max(20.0, self.mapper.cell_size_mm * 0.5)
        samples = max(1, int(distance / spacing) + 1)
        for sample in range(samples + 1):
            fraction = float(sample) / samples
            x = previous['x_mm'] + fraction * (current['x_mm'] - previous['x_mm'])
            y = previous['y_mm'] + fraction * (current['y_mm'] - previous['y_mm'])
            self.mapper.record_cleaned_sweep(x, y)

    @staticmethod
    def _contact_observation(sensors):
        bumps = sensors.bumps_and_wheel_drops
        light = sensors.light_bumper
        return {
            'bumper': {'left': bumps.bump_left, 'right': bumps.bump_right},
            'light_bumper': {
                name: bool(getattr(light, name))
                for name in ('left', 'front_left', 'center_left',
                             'center_right', 'front_right', 'right')
            },
        }

    def _contact_mapping_allowed(self, state):
        """Only map intentional mission motion, never idle/manual contact."""
        if self._mode == MODE_IDLE or not state.get('ready', True):
            return False
        if state.get('battery_status') == 'charging':
            return False
        if self._mode == MODE_DISCOVERY:
            # The retreat starts on the dock and can slip there. Intentional
            # tag-2 contact is recorded here; unexpected transit contacts are
            # mapped by _unexpected_bumper_contact before starting a detour.
            return self._discovery_stage in ('tag2_approach', 'tag2_contact')
        return True

    def _record_contact_obstacle(self, pose, observation):
        heading = pose['heading_rad']
        # The bumper face is one robot radius ahead of the pose origin. Mark
        # its immediate cell, not a point two extra cells into the obstacle.
        forward = max(0.0, self.mapper.robot_radius_mm - CONTACT_INSET_MM)
        left_contact = (observation['bumper'].get('left') or
                        observation['light_bumper'].get('left') or
                        observation['light_bumper'].get('front_left') or
                        observation['light_bumper'].get('center_left'))
        right_contact = (observation['bumper'].get('right') or
                         observation['light_bumper'].get('right') or
                         observation['light_bumper'].get('front_right') or
                         observation['light_bumper'].get('center_right'))
        if left_contact and right_contact:
            lateral = 0.0
        elif left_contact or right_contact:
            lateral = self.mapper.robot_radius_mm * 0.5 + self.mapper.cell_size_mm
            if right_contact:
                lateral = -lateral
        else:
            lateral = 0.0
        x = (pose['x_mm'] + cos(heading) * forward - sin(heading) * lateral)
        y = (pose['y_mm'] + sin(heading) * forward + cos(heading) * lateral)
        self.mapper.mark_obstacle(x, y)
        self.logger.info('Mapped bumper contact as obstacle near (%.0f, %.0f) mm.', x, y)

    def _send_stop(self, reason, disable_cleaning=True, smooth=False):
        if self._active_command is None and self._stop_sent:
            if disable_cleaning:
                self._set_cleaning_motors(False)
            return
        try:
            started = monotonic()
            self.robot_control.execute('soft_stop' if smooth else 'stop', timeout=5 if smooth else 2)
            elapsed = monotonic() - started
            self.logger.debug('Stop command completed in %.1f ms (%s).', elapsed * 1000.0, reason)
        except Exception:
            self.logger.exception('Unable to stop for %s.', reason)
        self._active_command = None
        self._active_until = 0.0
        self._stop_sent = True
        if disable_cleaning:
            self._set_cleaning_motors(False)

    def _set_cleaning_motors(self, enabled):
        enabled = bool(enabled)
        if enabled == self._cleaning_motors_on:
            return
        try:
            self.robot_control.execute(
                'set_motors', main_brush_on=enabled,
                side_brush=enabled, vacuum=enabled,
            )
            self._cleaning_motors_on = enabled
            self.logger.info('Cleaning motors %s.', 'enabled' if enabled else 'disabled')
        except Exception:
            self.logger.exception('Unable to %s cleaning motors.',
                                  'enable' if enabled else 'disable')

    def _record_performance(self, duration):
        self._perf_loops += 1
        self._perf_total += duration
        self._perf_max = max(self._perf_max, duration)
        now = monotonic()
        if now - self._perf_start >= PERFORMANCE_LOG_INTERVAL:
            count = max(1, self._perf_loops)
            self.logger.debug(
                'Mission performance: loops=%d average=%.1f ms max=%.1f ms '
                'planner_average=%.1f ms dispatch_average=%.1f ms period=%.1f ms',
                self._perf_loops,
                self._perf_total / count * 1000.0,
                self._perf_max * 1000.0,
                self._perf_plan_total / count * 1000.0,
                self._perf_dispatch_total / count * 1000.0,
                self.period * 1000.0,
            )
            self._perf_start = now
            self._perf_loops = 0
            self._perf_total = 0.0
            self._perf_max = 0.0
            self._perf_plan_total = 0.0
            self._perf_dispatch_total = 0.0

    @staticmethod
    def _wrap(angle):
        return (angle + pi) % (2.0 * pi) - pi

