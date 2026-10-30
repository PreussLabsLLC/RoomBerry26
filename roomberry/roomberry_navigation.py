"""Local navigation behaviors between the mission planner and Roomba I/O.

The mapper chooses destinations; this layer chooses the next bounded local
action. It does not issue serial commands itself. A caller translates returned
actions to RobotCommandArbiter operations and must enforce ``max_duration_s``
with a stop command. All velocities are millimeters per second.

This is an initial behavior outline: pose and waypoint tracking are supplied by
the caller, and charger alignment is intentionally left to a dedicated docking
routine once a physical dock pose and sensor strategy are configured.
"""
# @(#)roomberry_navigation.py 2.3 2026/10/24 19:38:52

from math import atan2


STOP = 'stop'
DRIVE = 'drive'
TURN = 'turn'
BACK_UP = 'back_up'
FOLLOW_WALL = 'follow_wall'
GO_TO_WAYPOINT = 'go_to_waypoint'
SEEK_DOCK = 'seek_dock'
DOCK = 'dock'
WAIT = 'wait'

MODE_IDLE = 'idle'
MODE_CLEAN = 'clean'
MODE_RETURN_TO_BASE = 'return_to_base'
MODE_DISCOVERY = 'discovery'
MODE_RECOVERY = 'recovery'

DEFAULT_BACKUP_SPEED = 80
DEFAULT_BACKUP_SECONDS = 0.35
DEFAULT_TURN_SECONDS = 0.45
DEFAULT_DRIVE_SPEED = 100
MAX_ACTION_SECONDS = 1.0


class NavigationCoordinator:
    """Prioritize safety, local recovery, then the active mission waypoint.

    ``decide`` accepts a plain dictionary so sensor adapters and simulation
    fixtures can provide observations without depending on the Open Interface
    parser classes. Expected keys include ``localized``, ``pose`` (x_mm,
    y_mm, heading_rad), ``hard_hazard``, ``bumper``, ``light_bumper``,
    ``wall_signal``, ``waypoint`` and optionally ``dock_visible``.

    Returned action dictionaries have ``kind``, ``reason`` and a duration cap.
    Motor commands should be issued only by the controller/arbiter adapter.
    """

    def __init__(self, robot_radius_mm, backup_speed=DEFAULT_BACKUP_SPEED,
                 backup_seconds=DEFAULT_BACKUP_SECONDS):
        if float(robot_radius_mm) <= 0:
            raise ValueError('Robot radius must be positive')
        if not 0 < float(backup_speed) <= 100:
            raise ValueError('Recovery speed must be between 1 and 100 mm/s')
        if not 0 < float(backup_seconds) <= MAX_ACTION_SECONDS:
            raise ValueError('Recovery duration must be at most one second')
        self.robot_radius_mm = float(robot_radius_mm)
        self.backup_speed = float(backup_speed)
        self.backup_seconds = float(backup_seconds)
        self.mode = MODE_IDLE
        self._last_wall_side = 'right'
        self._recovery_attempts = 0
        self._resume_mode = MODE_CLEAN
        self._stuck_attempts = 0

    def set_mode(self, mode):
        if mode not in (MODE_IDLE, MODE_CLEAN, MODE_RETURN_TO_BASE):
            raise ValueError('Unknown navigation mode: ' + str(mode))
        self.mode = mode
        if mode != MODE_RECOVERY:
            self._recovery_attempts = 0
            self._stuck_attempts = 0

    def decide(self, observation):
        """Choose one next action from current state and sensor observations."""
        if observation.get('hard_hazard'):
            self.mode = MODE_IDLE
            return self._action(STOP, 'cliff, wheel drop, stale sensors, or other hard safety stop')

        bumper = observation.get('bumper') or {}
        light = observation.get('light_bumper') or {}
        contact_side = self._contact_side(bumper, light)
        if contact_side:
            if self.mode == MODE_IDLE:
                return self._action(STOP, 'bumper contact while mission is idle')
            if self.mode != MODE_RECOVERY:
                self._resume_mode = self.mode
                self._recovery_attempts += 1
            self.mode = MODE_RECOVERY
            if self._recovery_attempts > 3:
                self.mode = MODE_IDLE
                return self._action(STOP, 'repeated contact; request replanning or human help')
            return self._action(
                BACK_UP,
                'clear {} bumper contact before turning'.format(contact_side),
                velocity=-self.backup_speed,
                max_duration_s=self.backup_seconds,
            )

        if observation.get('progress'):
            self._stuck_attempts = 0
        if observation.get('stuck') and self.mode != MODE_IDLE:
            if self.mode != MODE_RECOVERY:
                self._resume_mode = self.mode
                self._stuck_attempts += 1
            self.mode = MODE_RECOVERY
            if self._stuck_attempts > 3:
                self.mode = MODE_IDLE
                return self._action(STOP, 'repeated no-progress recovery; request replanning or help')
            return self._action(
                BACK_UP, 'no odometry progress; backtrack and retry',
                velocity=-self.backup_speed,
                max_duration_s=self.backup_seconds,
            )

        if self.mode == MODE_RECOVERY:
            # Let the arbiter observe a clear sensor cycle before asking it to
            # move forward or turn. A caller can call decide again next tick.
            self.mode = self._resume_mode
            self._recovery_attempts = 0
            return self._action(STOP, 'contact cleared; allow safety latch to reset')

        if self.mode == MODE_RETURN_TO_BASE:
            if observation.get('dock_visible'):
                return self._action(DOCK, 'dock acquired; hand off to docking controller')
            return self._waypoint_action(observation, 'return to base')

        if not observation.get('localized', False):
            return self._action(STOP, 'localization unavailable; do not navigate blindly')

        if self.mode == MODE_CLEAN:
            wall_signal = observation.get('wall_signal')
            if wall_signal is not None and observation.get('follow_wall', False):
                return self._follow_wall(wall_signal)
            if observation.get('obstacle_leg'):
                return self._circle_obstacle(observation)
            return self._waypoint_action(observation, 'cleaning waypoint')

        return self._action(WAIT, 'no active mission')

    def _waypoint_action(self, observation, reason):
        waypoint = observation.get('waypoint')
        if waypoint is None:
            if self.mode == MODE_RETURN_TO_BASE:
                return self._action(SEEK_DOCK, 'no mapped dock route; use Roomba dock-seeking behavior')
            return self._action(WAIT, 'no reachable cookie waypoint')
        return self._action(
            GO_TO_WAYPOINT, reason, waypoint=waypoint,
            max_duration_s=MAX_ACTION_SECONDS,
        )

    def _follow_wall(self, signal):
        """Simple wall-distance response; calibration supplies target/thresholds."""
        target = float(signal.get('target', 300))
        measured = float(signal.get('value', 0))
        error = measured - target
        self._last_wall_side = signal.get('side', self._last_wall_side)
        # Keep this a low-speed steering hint; do not use an uncalibrated wall
        # sensor as a collision or cliff safety mechanism.
        side_sign = 1.0 if self._last_wall_side == 'right' else -1.0
        steering = max(-0.35, min(0.35,
                                  side_sign * error / max(target, 1.0) * 0.25))
        return self._action(
            FOLLOW_WALL, 'maintain calibrated wall offset',
            velocity=70, steering=steering, side=self._last_wall_side,
            max_duration_s=0.25,
        )

    def _circle_obstacle(self, observation):
        """Emit a cautious arc step around a newly detected furniture leg."""
        side = observation.get('obstacle_side', 'right')
        turn = -0.25 if side == 'left' else 0.25
        return self._action(
            DRIVE, 'short arc around obstacle; reobserve before continuing',
            velocity=60, steering=turn, max_duration_s=0.25,
        )

    @staticmethod
    def waypoint_heading(pose, waypoint):
        """Return desired world-frame heading to a (x_mm, y_mm) waypoint."""
        return atan2(float(waypoint[1]) - float(pose['y_mm']),
                     float(waypoint[0]) - float(pose['x_mm']))

    @staticmethod
    def _contact_side(bumper, light):
        left = bool(bumper.get('left') or light.get('left') or
                    light.get('front_left') or light.get('center_left'))
        right = bool(bumper.get('right') or light.get('right') or
                     light.get('front_right') or light.get('center_right'))
        if left and right:
            return 'both'
        if left:
            return 'left'
        if right:
            return 'right'
        return None

    @staticmethod
    def _action(kind, reason, **values):
        action = {
            'kind': kind,
            'reason': reason,
            'max_duration_s': 0.0 if kind in (STOP, WAIT) else MAX_ACTION_SECONDS,
        }
        action.update(values)
        return action

