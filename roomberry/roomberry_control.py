"""Single-owner Roomba command and sensor-polling service."""
# @(#)roomberry_control.py 3.1.cal.1 2026/10/31 12:30:00

from math import isfinite
from roomberry_reverse_monitor import ReverseCurrentMonitor
from roomberry_startup import reset_and_identify
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic, sleep

from irobot.openinterface.constants import DRIVE, MODES, ROBOT


SENSOR_POLL_INTERVAL = 0.1
SENSOR_MAX_AGE = 0.5
# The Roomba can briefly report false cliffs and wheel drops immediately after
# the Open Interface wakes. Require 1.5 seconds of settled readings.
STARTUP_SENSOR_SAMPLES = 15
LOW_BATTERY_LEVEL = 0.3
CRITICAL_BATTERY_LEVEL = 0.1
PERFORMANCE_LOG_INTERVAL = 10.0
ROBOT_CONNECT_RETRY_INITIAL_SECONDS = 5
ROBOT_CONNECT_RETRY_MAX_SECONDS = 30
# Keep operation LEDs lit long enough to see after a brief sensor trigger.
LED_HOLD_SECONDS = 2.0
# The Create 2 light-bumper contact bits assert only at close range, but the
# raw signal rises well before that. Carpet clutter stays below roughly 25, so
# this threshold gives an earlier heads-up on the operation LEDs and lets the
# mission react before the bumper touches an obstacle.
LIGHT_BUMPER_PROXIMITY_THRESHOLD = 45
# Two-note chirp programmed into song slot 0 for button feedback. Notes are
# MIDI numbers (G5, C6) and durations are 1/64-second units; keep each note
# long enough to be clearly audible over the robot's fan.
BUTTON_BEEP_SONG = 0
BUTTON_BEEP_NOTES = ((79, 8), (84, 12))

MOTION_OPERATIONS = frozenset((
    'drive', 'drive_direct', 'drive_pwm', 'drive_straight', 'spin_left',
    'spin_right', 'clean', 'clean_max', 'clean_spot', 'seek_dock',
    'set_motors', 'set_motors_pwm',
))


class RobotCommandArbiter:
    """Serialize all robot I/O and expose a periodically refreshed snapshot."""

    def __init__(self, serial_port, brc_pin, logger, robot=None,
                 poll_interval=SENSOR_POLL_INTERVAL, auto_seek_dock=True,
                 sensor_log=None, motion_ramp=None, reverse_current_monitor=None):
        self.logger = logger
        self._reverse_monitor = ReverseCurrentMonitor(logger, reverse_current_monitor)
        self._sensor_fault = None
        self._applied_wheels = (0, 0)
        self._button_state = dict(schedule=False, clock=False)
        self._button_diagnostics = dict(source='unread', group_mask=0, dedicated_mask=None, held_s=0.0)
        self._button_changed_at = monotonic()
        self._button_held_reported = False
        self._button_warning_at = float('-inf')
        self._last_button_mask = 0
        self._schedule_press_pending = False
        self._saved_auto_wake = None
        self._restart_generation = 0
        ramp = motion_ramp or {}
        self._ramp_enabled = bool(ramp.get('enabled', True))
        self._acceleration = float(ramp.get('acceleration_mm_s2', 100.0))
        self._deceleration = float(ramp.get('deceleration_mm_s2', 200.0))
        if not all(isfinite(rate) and rate > 0 for rate in (self._acceleration, self._deceleration)):
            raise ValueError('Wheel acceleration and deceleration must be finite and positive')
        self._ramp_current = (0.0, 0.0)
        self._ramp_target = (0.0, 0.0)
        self._ramp_sent = (0, 0)
        self._ramp_time = monotonic()
        self._ramp_stops = []
        if robot is None:
            robot = self._connect_robot(serial_port, brc_pin)
        self.robot = robot
        self.robot.logger.disabled = True
        self.poll_interval = poll_interval
        self.auto_seek_dock = bool(auto_seek_dock)
        self.sensor_log = sensor_log
        self._returning_home = False
        self._commands = Queue()
        self._shutdown = Event()
        self._state_lock = Lock()
        self._thread = Thread(target=self._run, name='roomba-io', daemon=True)
        self._sensors = None
        self._sensor_time = None
        self._distance = 0
        self._travelled_distance = 0
        self._clock_press_pending = False
        self._angle = 0
        self._odometry_epoch = 0
        self._last_encoder_counts = None
        self._safety_latched = False
        self._wheel_drop_stopped = False
        self._recovery_active = False
        self._startup_sensor_samples = 0
        self._startup_braked = False
        self._stale_braked = False
        self._home_base = False
        self._hazards_suppressed = False
        self._hard_hazard_reasons = []
        self._battery_status = 'unknown'
        self._drive_display = 'IdLE'
        self._last_drive_display = None
        self._operation_indicators_active = False
        self._last_scheduling_leds = None
        self._scheduling_led_hold_until = [0.0] * 7
        self._last_schedule_pressed = False
        self._last_clock_pressed = False
        self._dock_requested = False
        self._critical_braked = False
        self._poll_perf_started = monotonic()
        self._poll_perf_count = 0
        self._poll_perf_total = 0.0
        self._poll_perf_max = 0.0
        self._poll_perf_failures = 0

    def _connect_robot(self, serial_port, brc_pin):
        from irobot.robots.create2 import Create2

        delay = ROBOT_CONNECT_RETRY_INITIAL_SECONDS
        attempt = 0
        while True:
            attempt += 1
            try:
                identity = reset_and_identify(serial_port, self.logger)
                robot = Create2(
                    serial_port, brc_pin, timeout=0.05, enable_quirks=False
                )
                robot.boot_message = identity['boot_message']
                robot.boot_firmware_version = identity['firmware_version']
                robot.firmware_release = identity['firmware_release']
                robot._change_mode(MODES.SAFE)
                self.logger.info('Roomba startup verified Safe mode before feedback.')
                robot._change_mode(MODES.PASSIVE)
                self.logger.info('Roomba startup restored Passive mode for idle button input.')
                if attempt > 1:
                    self.logger.info(
                        'Roomba connection established on attempt %d.', attempt
                    )
                return robot
            except (TypeError, AttributeError):
                self.logger.exception('Roomba startup failed due to a driver compatibility error.')
                raise
            except Exception as error:
                self.logger.warning(
                    'Unable to connect to Roomba (attempt %d): %s. It may be asleep; '
                    'retrying in %d seconds. Press the Roomba time button if needed.',
                    attempt, error, delay,
                )
                sleep(delay)
                delay = min(delay * 2, ROBOT_CONNECT_RETRY_MAX_SECONDS)

    def start(self):
        if self.sensor_log is not None:
            try:
                self.sensor_log.start()
            except Exception:
                self.logger.exception('Unable to start Roomba sensor recording.')
        if not self._thread.is_alive():
            self._thread.start()

    def close(self):
        try:
            if self._thread.is_alive():
                try:
                    self.execute('stop', timeout=2)
                except Exception:
                    self.logger.exception('Unable to brake Roomba during shutdown.')
                self._shutdown.set()
                self._thread.join(timeout=2)
        finally:
            # Send OI STOP (0xAD) after the I/O worker has shut down as a final
            # safeguard against leaving the robot's interface active.
            try:
                if not self._wheel_drop_stopped:
                    self.robot.stop()
            except Exception:
                self.logger.exception('Unable to send final Roomba STOP (0xAD).')
            finally:
                if self.sensor_log is not None:
                    try:
                        self.sensor_log.close()
                    except Exception:
                        self.logger.exception(
                            'Unable to close Roomba sensor recording.'
                        )

    def execute(self, operation, timeout=5, **kwargs):
        """Run a legacy operation on the I/O thread and return its result."""
        if not operation or (operation.startswith('_') and operation not in ('_change_mode', '_feedback_beep')):
            raise ValueError('Invalid Roomba operation')

        command = {
            'operation': operation,
            'kwargs': kwargs,
            'result': [],
            'done': Event(),
            'expires_at': monotonic() + timeout,
        }
        self._commands.put(command)
        if not command['done'].wait(timeout):
            raise TimeoutError('Timed out waiting for Roomba operation')
        if len(command['result']) == 2:
            raise command['result'][1]
        return command['result'][0] if command['result'] else None

    def snapshot(self):
        with self._state_lock:
            age = None if self._sensor_time is None else monotonic() - self._sensor_time
            return {
                'firmware_version': getattr(self.robot, 'boot_firmware_version', None),
                'firmware_release': getattr(self.robot, 'firmware_release', None),
                'sensors': self._sensors,
                'distance': self._distance,
                'travelled_distance': self._travelled_distance,
                'angle': self._angle,
                'odometry_epoch': self._odometry_epoch,
                'age': age,
                'battery_status': self._battery_status,
                'home_base': self._home_base,
                'charging': self._battery_status == 'charging',
                'safety_latched': self._safety_latched,
                'hazards_suppressed': self._hazards_suppressed,
                'hard_hazard_reasons': list(self._hard_hazard_reasons) + (['oi_stopped'] if self._wheel_drop_stopped else []) + (['sensor_fault'] if self._sensor_fault else []),
                'hard_hazard': (
                    True if self._sensors is None else bool(self._hard_hazard_reasons or self._wheel_drop_stopped or self._sensor_fault)
                ),
                'schedule_button': self._button_state['schedule'],
                'clock_button': self._button_state['clock'],
                'oi_stopped': self._wheel_drop_stopped,
                'restart_generation': self._restart_generation,
                'sensor_fault': self._sensor_fault,
                'button_diagnostics': dict(self._button_diagnostics),
                'reverse_current_monitor': self._reverse_monitor.status(),
                'applied_left_velocity_mm_s': None if self._applied_wheels is None else self._applied_wheels[0],
                'applied_right_velocity_mm_s': None if self._applied_wheels is None else self._applied_wheels[1],
                'ready': not self._wheel_drop_stopped and not self._sensor_fault and self._startup_sensor_samples >= STARTUP_SENSOR_SAMPLES,
            }

    def consume_clock_button_press(self):
        """Return and clear the latched Clock press event."""
        with self._state_lock:
            pressed = self._clock_press_pending
            self._clock_press_pending = False
            return pressed

    def consume_schedule_button_press(self):
        with self._state_lock:
            pressed = self._schedule_press_pending
            self._schedule_press_pending = False
            return pressed

    def reset_odometry(self):
        with self._state_lock:
            self._distance = 0
            self._travelled_distance = 0
            self._angle = 0
            self._odometry_epoch += 1
            self._last_encoder_counts = None

    def set_operation_indicators(self, active):
        active = bool(active)
        if active and not self._operation_indicators_active:
            self._last_scheduling_leds = None
            self._scheduling_led_hold_until = [0.0] * 7
        self._operation_indicators_active = active

    def beep(self, event='happy'):
        """Play a short button-feedback tone; failures must not stop a mission."""
        notes = {'happy': BUTTON_BEEP_NOTES,
                 'unhappy': ((84, 8), (79, 12)),
                 'neutral': ((79, 8),),
                 'mode_change': ((72, 8), (76, 8), (79, 12), (84, 16))}[event]
        if self._wheel_drop_stopped:
            return
        try:
            self.execute('_feedback_beep', notes=[list(note) for note in notes], timeout=3)
        except Exception:
            self.logger.exception('Unable to play button feedback beep.')

    def set_drive_display(self, mode, stage=None, scanning=False):
        """Publish a display label; only the I/O owner writes the serial port."""
        label = {'idle': 'IdLE', 'discovery': 'dISC', 'clean': 'CLn ',
                 'return_to_base': 'HOME', 'remote_control': 'rEM ', 'calibration': 'CAL '}.get(mode, 'IdLE')
        if mode == 'discovery':
            if stage == 'bump':
                label = 'bUMP'
            elif stage in ('return', 'dock_approach'):
                label = 'HOME'
            elif stage == 'wall_follow':
                label = 'WALL'
            elif stage in ('avoid_back', 'retreat', 'release_contact'):
                label = 'bACK'
            elif stage == 'avoid_turn':
                label = 'turn'
        self._drive_display = 'SCAn' if scanning and mode != 'calibration' else label

    def _update_drive_display(self, sensors):
        label = self._drive_display
        key = (sensors.oi_mode, label)
        if self._wheel_drop_stopped or key == self._last_drive_display:
            return
        display = getattr(self.robot, 'set_ascii_leds', None)
        if not callable(display):
            return
        try:
            display(**{'char' + str(i + 1): ord(char)
                       for i, char in enumerate(label)})
            self._last_drive_display = key
        except Exception:
            self.logger.exception('Unable to update drive-mode display.')

    def _update_operation_leds(self, sensors):
        active = self._operation_indicators_active
        if not active and self._last_scheduling_leds is None:
            return
        now = monotonic()
        light = getattr(sensors, 'light_bumper', None)

        def proximity(*zones):
            for zone in zones:
                if light is not None and bool(getattr(light, zone, False)):
                    return True
                signal = getattr(
                    sensors, 'light_bump_' + zone + '_signal', 0,
                )
                if int(signal or 0) >= LIGHT_BUMPER_PROXIMITY_THRESHOLD:
                    return True
            return False

        readings = (
            sensors.cliff_left_sensor or proximity('left'),
            sensors.cliff_front_left_sensor or proximity('front_left'),
            sensors.wall_sensor or proximity('center_left', 'center_right'),
            sensors.cliff_front_right_sensor or proximity('front_right'),
            sensors.cliff_right_sensor or proximity('right'),
            False, False,
        )
        for index, reading in enumerate(readings):
            if reading:
                self._scheduling_led_hold_until[index] = now + LED_HOLD_SECONDS
        values = tuple(
            bool(active and now < hold_until)
            for hold_until in self._scheduling_led_hold_until
        )
        if values == self._last_scheduling_leds:
            return
        try:
            self.robot.set_scheduling_leds(
                sun=values[0], mon=values[1], tues=values[2], wed=values[3],
                thurs=values[4], fri=values[5], sat=values[6],
                schedule=False, clock=False, am=False, pm=False, colon=False,
            )
            self._last_scheduling_leds = values
        except Exception:
            self.logger.exception('Unable to update operation sensor LEDs.')
    def set_returning_home(self, returning_home):
        """Permit low-battery motion only while following a configured dock route."""
        self._returning_home = bool(returning_home)

    def _run(self):
        next_poll = monotonic()
        while not self._shutdown.is_set():
            timeout = max(0, min(0.05, next_poll - monotonic()))
            try:
                command = self._commands.get(timeout=timeout)
            except Empty:
                command = None

            if command is not None:
                self._run_command(command)

            now = monotonic()
            if now >= next_poll:
                self._poll_sensors()
                next_poll = monotonic() + self.poll_interval
            try:
                self._advance_ramp()
            except Exception:
                self.logger.exception('Wheel ramp failed; braking immediately.')
                self._brake()

        while True:
            try:
                command = self._commands.get_nowait()
            except Empty:
                break
            command['result'].append(RuntimeError('Roomba service is stopping'))
            command['done'].set()
        try:
            self._brake()
            if not self._wheel_drop_stopped:
                self.robot.stop()
        except Exception:
            self.logger.exception('Unable to stop Roomba Open Interface.')

    def _run_command(self, command):
        command_started = monotonic()
        try:
            if monotonic() > command['expires_at']:
                raise TimeoutError('Roomba operation expired before execution')

            operation = command['operation']
            if self._wheel_drop_stopped and operation not in ('restart_oi', 'stop', 'soft_stop', 'emergency_stop'):
                raise RuntimeError('OI is stopped; use restart_oi explicitly before rearming')
            if operation == 'restart_oi':
                if command['kwargs']:
                    raise ValueError('restart_oi takes no arguments')
                self._brake()
                try:
                    self.robot.start()  # OI Start is the only permitted restart, into Passive.
                except Exception:
                    self._wheel_drop_stopped = True
                    raise
                self._wheel_drop_stopped = False
                if self._saved_auto_wake is not None:
                    self.robot.auto_wake = self._saved_auto_wake
                    self._saved_auto_wake = None
                with self._state_lock:
                    self._sensors, self._sensor_time = None, None
                    self._sensor_fault = None
                    self._startup_sensor_samples = 0
                    self._last_encoder_counts = None
                    self._odometry_epoch += 1
                    self._restart_generation += 1
                    self._clock_press_pending = self._schedule_press_pending = False
                    self._button_state = dict(schedule=False, clock=False)
                    self._last_schedule_pressed = self._last_clock_pressed = False
                self._reverse_monitor.reset_episode()
                self.logger.info('OI explicitly restarted in Passive mode; fresh sensor startup required.')
                command['result'].append(None)
                return
            if operation == 'soft_stop':
                if command['kwargs']:
                    raise ValueError('Soft stop takes no arguments')
                if self._ramp_enabled and self._ramp_current != (0.0, 0.0):
                    self._ramp_target = (0.0, 0.0)
                    command['ramp_deferred'] = True
                    self._ramp_stops.append(command)
                    return
                result = self._brake()
            elif operation in ('stop', 'emergency_stop'):
                self._recovery_active = False
                result = self._brake()
            elif operation == '_feedback_beep':
                original_mode = self.robot.oi_mode
                passive_feedback = original_mode == MODES.PASSIVE
                if original_mode != MODES.SAFE and not (
                        passive_feedback and not self._operation_indicators_active):
                    raise RuntimeError('Feedback cannot rearm an active or stopped robot')
                try:
                    if passive_feedback:
                        self._brake()
                        self.robot._change_mode(MODES.SAFE)  # Driver verifies packet 35.
                        # Passive firmware may ignore display writes: refresh in Safe.
                        self._update_drive_display(self.robot)
                    self.robot.set_song(song_number=BUTTON_BEEP_SONG,
                                        notes=command['kwargs']['notes'])
                    result = self.robot.play_song(song_number=BUTTON_BEEP_SONG)
                    if passive_feedback:
                        # Let playback finish before leaving its required OI mode.
                        sleep(sum(note[1] for note in command['kwargs']['notes']) / 64.0)
                finally:
                    if passive_feedback:
                        self.robot._change_mode(MODES.PASSIVE)
            elif operation == '_change_mode':
                if set(command['kwargs']) != {'mode'}:
                    raise ValueError('Mode change requires only a mode value')
                mode = int(command['kwargs']['mode'])
                if mode not in (MODES.PASSIVE, MODES.SAFE, MODES.FULL):
                    raise ValueError('Invalid Roomba mode')
                if self._wheel_drop_stopped:
                    sensors = self._sensors
                    if (sensors is None or self._sensor_time is None or
                            monotonic() - self._sensor_time > SENSOR_MAX_AGE or
                            sensors.bumps_and_wheel_drops.wheel_drop_left or
                            sensors.bumps_and_wheel_drops.wheel_drop_right):
                        raise RuntimeError('Cannot rearm after wheel drop until fresh grounded sensors arrive')
                self._brake()
                result = self.robot._change_mode(mode)
                self._wheel_drop_stopped = False
            else:
                if operation in ('set_song', 'play_song') and self.robot.oi_mode != MODES.SAFE:
                    raise RuntimeError('Feedback requires Safe mode; refusing to rearm for a beep')
                wheels = self._wheel_target(operation, command['kwargs'])
                if operation in MOTION_OPERATIONS:
                    self._check_motion_allowed(operation, command['kwargs'])
                if self._ramp_enabled and wheels is not None:
                    if self._ramp_stops and wheels != (0.0, 0.0):
                        raise RuntimeError('Motion rejected while a soft stop is finishing')
                    if self._ramp_current == self._ramp_target == (0.0, 0.0):
                        self._ramp_time = monotonic()
                    self._ramp_target = wheels
                    self.logger.log(5, 'Wheel ramp target: left=%.1f right=%.1f mm/s.', *wheels)
                    if wheels == (0.0, 0.0) and self._ramp_current != wheels:
                        command['ramp_deferred'] = True
                        self._ramp_stops.append(command)
                    else:
                        command['result'].append(None)
                    return
                if self._ramp_enabled and operation in ('drive_pwm', 'clean', 'clean_max', 'clean_spot', 'seek_dock'):
                    self._brake()  # Never let a queued ramp fight another controller.
                method = getattr(self.robot, operation, None)
                if method is None or not callable(method):
                    raise ValueError('Unknown Roomba operation: ' + operation)
                result = method(**command['kwargs'])
                if wheels is not None:
                    self._applied_wheels = tuple(int(v) for v in wheels)
                elif operation in ('drive_pwm', 'clean', 'clean_max', 'clean_spot', 'seek_dock'):
                    self._applied_wheels = None
            command['result'].append(result)
        except Exception as error:
            command['result'].append(None)
            command['result'].append(error)
        finally:
            if not command.get('ramp_deferred'):
                command['done'].set()
            self.logger.debug(
                'Roomba operation %s completed in %.1f ms%s',
                command['operation'],
                (monotonic() - command_started) * 1000.0,
                ' with error' if len(command['result']) == 2 else '',
            )

    def _check_motion_allowed(self, operation, kwargs):
        if self._is_zero_motion(operation, kwargs):
            self._recovery_active = False
            return
        if self._sensor_fault:
            raise RuntimeError('Motion rejected because the latest sensor poll failed')
        if self._wheel_drop_stopped:
            raise RuntimeError('Motion rejected after wheel drop; explicitly rearm the Open Interface')
        if self._startup_sensor_samples < STARTUP_SENSOR_SAMPLES:
            raise RuntimeError('Motion rejected while Roomba sensors are initializing')
        state = self.snapshot()
        if state['sensors'] is None or state['age'] is None or state['age'] > SENSOR_MAX_AGE:
            raise RuntimeError('Motion rejected because Roomba sensor data is stale')
        oi_mode = getattr(state['sensors'], 'oi_mode', None)
        if oi_mode is not None and oi_mode != MODES.SAFE:
            raise RuntimeError('Motion rejected because the Open Interface is not in Safe mode')
        recovery = False
        if self._safety_latched:
            if not self._is_recovery_motion(
                    operation, kwargs, state['sensors']):
                raise RuntimeError('Motion rejected while a safety stop is active')
            recovery = True
        if state['battery_status'] == 'critical':
            raise RuntimeError('Motion rejected because the battery is critical')
        if (state['battery_status'] == 'low' and operation != 'seek_dock' and
                not self._returning_home):
            raise RuntimeError('Motion rejected while the Roomba is returning to its dock')
        self._recovery_active = recovery

    @staticmethod
    def _is_zero_motion(operation, kwargs):
        if operation == 'drive_direct':
            return int(kwargs.get('right_velocity', 0)) == 0 and int(kwargs.get('left_velocity', 0)) == 0
        if operation == 'drive_pwm':
            return int(kwargs.get('right_pwm', 0)) == 0 and int(kwargs.get('left_pwm', 0)) == 0
        if operation == 'drive_straight':
            return int(kwargs.get('velocity', 0)) == 0
        if operation == 'drive':
            return int(kwargs.get('velocity', 0)) == 0
        if operation == 'set_motors':
            return not any(kwargs.values())
        if operation == 'set_motors_pwm':
            return not any(int(value) for value in kwargs.values())
        return False

    @staticmethod
    def _is_recovery_motion(operation, kwargs, sensors):
        bumps = sensors.bumps_and_wheel_drops
        hard_hazard = (
            bumps.wheel_drop_left or bumps.wheel_drop_right or
            sensors.cliff_left_sensor or sensors.cliff_front_left_sensor or
            sensors.cliff_front_right_sensor or sensors.cliff_right_sensor
        )
        light_bumper = sensors.light_bumper
        bumper_contact = (
            bumps.bump_left or bumps.bump_right or any((
                light_bumper.left, light_bumper.front_left,
                light_bumper.center_left, light_bumper.center_right,
                light_bumper.front_right, light_bumper.right,
            ))
        )
        # Only allow the narrowly bounded reverse escape for physical contact.
        # A cliff or wheel drop must never be interpreted as a bumper recovery.
        if hard_hazard or not bumper_contact:
            return False
        if operation in ('drive', 'drive_straight'):
            velocity = int(kwargs.get('velocity', 0))
            return -100 <= velocity < 0
        if operation == 'drive_direct':
            right = int(kwargs.get('right_velocity', 0))
            left = int(kwargs.get('left_velocity', 0))
            return -100 <= right < 0 and -100 <= left < 0
        if operation == 'drive_pwm':
            right = int(kwargs.get('right_pwm', 0))
            left = int(kwargs.get('left_pwm', 0))
            return -50 <= right < 0 and -50 <= left < 0
        return False

    def _odometry_deltas(self, sensors):
        left_count = getattr(sensors, 'left_encoder_counts', None)
        right_count = getattr(sensors, 'right_encoder_counts', None)
        if left_count is None or right_count is None:
            return float(sensors.distance), float(sensors.angle)

        counts = (int(left_count) & 0xFFFF, int(right_count) & 0xFFFF)
        previous = self._last_encoder_counts
        self._last_encoder_counts = counts
        if previous is None:
            return 0.0, 0.0

        def signed_count_delta(current, prior):
            return ((current - prior + 0x8000) & 0xFFFF) - 0x8000

        left_delta = signed_count_delta(counts[0], previous[0])
        right_delta = signed_count_delta(counts[1], previous[1])
        if max(abs(left_delta), abs(right_delta)) > 4096:
            return 0.0, 0.0

        left_mm = left_delta * ROBOT.TICK_TO_DISTANCE
        right_mm = right_delta * ROBOT.TICK_TO_DISTANCE
        distance_mm = (left_mm + right_mm) / 2.0
        angle_degrees = (
            (right_mm - left_mm) / ROBOT.WHEEL_BASE * 180.0 / 3.141592653589793
        )
        return distance_mm, angle_degrees
    @staticmethod
    def _validate_sensors(sensors):
        """Reject malformed packets before odometry, buttons, LEDs or safety use."""
        raw = getattr(sensors, '_data', None)
        if raw is not None:
            if len(raw) != 80 or any(raw[i] not in (0, 1) for i in range(1, 7)):
                raise ValueError('Malformed group-100 packet length or boolean fields')
            if raw[0] & 0xe0 or raw[56] & 0xc0:
                raise ValueError('Malformed group-100 reserved bits')
        ranges = {'oi_mode': (0, 3), 'charging_state': (0, 5),
                  'voltage': (0, 25000), 'current': (-32768, 32767),
                  'temperature': (-40, 100), 'battery_charge': (0, 20000),
                  'battery_capacity': (1, 20000), 'requested_velocity': (-500, 500),
                  'requested_left_velocity': (-500, 500), 'requested_right_velocity': (-500, 500),
                  'left_motor_current': (-32768, 32767), 'right_motor_current': (-32768, 32767),
                  'main_brush_motor_current': (-32768, 32767), 'side_brush_motor_current': (-32768, 32767)}
        for name, (low, high) in ranges.items():
            value = getattr(sensors, name, None)
            if value is not None and (not isinstance(value, (int, float)) or
                                      not isfinite(value) or not low <= value <= high):
                raise ValueError('Invalid sensor %s=%r' % (name, value))

    @staticmethod
    def _buttons_mask(buttons):
        raw = getattr(buttons, '_data', None)
        if raw is not None:
            if not isinstance(raw, int) or not 0 <= raw <= 255:
                raise ValueError('Invalid button packet')
            return raw
        return sum((1 << bit) for bit, name in enumerate(
            ('clean', 'spot', 'dock', 'minute', 'hour', 'day', 'schedule', 'clock'))
            if getattr(buttons, name, False))

    def _read_buttons(self, sensors):
        group = self._buttons_mask(getattr(sensors, 'buttons', None))
        dedicated = None if self._wheel_drop_stopped else getattr(self.robot, 'buttons', None)
        mask = group if dedicated is None else self._buttons_mask(dedicated)
        now = monotonic()
        if mask != self._last_button_mask:
            self._button_held_reported = False
            self._button_changed_at = now
            self._last_button_mask = mask
            self.logger.info('Button packet: group=0x%02x dedicated=%s mode=%s.',
                             group, None if dedicated is None else hex(mask), sensors.oi_mode)
        held = now - self._button_changed_at if mask else 0.0
        self._button_diagnostics = dict(source='group' if dedicated is None else 'packet18',
            group_mask=group, dedicated_mask=None if dedicated is None else mask, held_s=round(held, 2))
        if dedicated is not None and group != mask and now - self._button_warning_at >= 10:
            self.logger.warning('Button packet disagreement: %s.', self._button_diagnostics)
            self._button_warning_at = now
        if held >= 3 and not self._button_held_reported:
            self.logger.info('Button mask 0x%02x unchanged for %.1f s in OI mode %s; '
                             'may be held or firmware-latched, not proof of a stuck button. '
                             'Reporting once until mask changes.', mask, held, sensors.oi_mode)
            self._button_held_reported = True
        self._button_state = dict(schedule=bool(mask & 0x40), clock=bool(mask & 0x80))
        return self._button_state

    def _poll_sensors(self):
        if self._wheel_drop_stopped:
            return
        poll_started = monotonic()
        succeeded = False
        try:
            sensors = self.robot.sensor_group100
            self._validate_sensors(sensors)
            drops = sensors.bumps_and_wheel_drops
            if (self._startup_sensor_samples + 1 >= STARTUP_SENSOR_SAMPLES and
                    (drops.wheel_drop_left or drops.wheel_drop_right) and
                    not self._wheel_drop_stopped):
                # Latch before I/O so a failed STOP cannot permit queued motion.
                self._wheel_drop_stopped = True
                if hasattr(self.robot, 'auto_wake'):
                    self._saved_auto_wake = self.robot.auto_wake
                    self.robot.auto_wake = False
                self._cancel_ramp()
                self._recovery_active = False
                try:
                    self.robot.drive(0, DRIVE.STRAIGHT)
                finally:
                    self.robot.stop()
                self._complete_ramp_stops()
                self.logger.warning('Wheel drop: OI STOP sent; explicit rearm required.')

            buttons = self._read_buttons(sensors)
            schedule_pressed, clock_pressed = buttons['schedule'], buttons['clock']
            if schedule_pressed != self._last_schedule_pressed:
                self.logger.debug('Schedule button %s (OI mode=%s).',
                                  'pressed' if schedule_pressed else 'released', sensors.oi_mode)
                if schedule_pressed:
                    self._schedule_press_pending = True
                self._last_schedule_pressed = schedule_pressed
            if clock_pressed != self._last_clock_pressed:
                self.logger.debug('Clock button %s (OI mode=%s).',
                                  'pressed' if clock_pressed else 'released', sensors.oi_mode)
                if clock_pressed:
                    self._clock_press_pending = True
                self._last_clock_pressed = clock_pressed
            self._sensor_fault = None
            if not self._wheel_drop_stopped:
                self._update_operation_leds(sensors)
                self._update_drive_display(sensors)
            self._startup_sensor_samples += 1
            with self._state_lock:
                distance_delta, angle_delta = self._odometry_deltas(sensors)
                self._distance += distance_delta
                self._travelled_distance += abs(distance_delta)
                self._angle += angle_delta
                self._sensors = sensors
                self._sensor_time = monotonic()
                battery_capacity = sensors.battery_capacity
                battery_level = (sensors.battery_charge / battery_capacity) if battery_capacity else 0
                home_base = bool(sensors.charging_sources.home_base)
                self._home_base = home_base
                if home_base:
                    self._battery_status = 'charging'
                    self._dock_requested = False
                elif battery_level < CRITICAL_BATTERY_LEVEL:
                    self._battery_status = 'critical'
                elif battery_level < LOW_BATTERY_LEVEL:
                    self._battery_status = 'low'
                else:
                    self._battery_status = 'normal'
                battery_status = self._battery_status

            hard_reasons = self._sensor_hard_hazard_reasons(sensors)
            suppressed = self._stationary_on_home_base(sensors, home_base)
            if suppressed != self._hazards_suppressed:
                if suppressed:
                    self.logger.info(
                        'Robot is stationary on the home base; suppressing '
                        'dock safety-sensor readings until it moves.'
                    )
                elif home_base:
                    self.logger.info(
                        'Robot is moving on the home base; dock hazard '
                        'suppression is no longer active.'
                    )
            self._hazards_suppressed = suppressed
            self._hard_hazard_reasons = [] if suppressed else list(hard_reasons)
            hazard = False if suppressed else self._has_hazard(sensors)
            if self._startup_sensor_samples < STARTUP_SENSOR_SAMPLES:
                if hazard and not self._startup_braked:
                    self.logger.info('Startup safety sensor active; braking while readings settle.')
                    self._brake()
                    self._startup_braked = True
            elif hazard:
                if not self._safety_latched:
                    self.logger.warning(
                        'Roomba safety sensor triggered; braking. Readings: %s',
                        self._format_safety_sensor_details(sensors),
                    )
                    self._brake()
                self._safety_latched = True
            else:
                if self._safety_latched and not self._recovery_active:
                    self._brake()
                self._safety_latched = False
                self._recovery_active = False

            if battery_status == 'critical':
                if not self._critical_braked:
                    self._brake()
                self._critical_braked = True
            else:
                self._critical_braked = False
            if (self.auto_seek_dock and battery_status == 'low' and
                    not self._dock_requested and not hazard and
                    not self._wheel_drop_stopped):
                self.logger.warning('Roomba battery low; seeking dock.')
                self._brake()
                self.robot.seek_dock()
                self._applied_wheels = None
                self._dock_requested = True

            self._stale_braked = False
            succeeded = True
            with self._state_lock:
                self._reverse_monitor.update(sensors, self._applied_wheels, distance_delta, monotonic())
            self._record_sensor_sample()
        except Exception as error:
            self._sensor_fault = str(error)
            self.logger.exception('Roomba sensor poll failed.')
            state = self.snapshot()
            if not self._stale_braked:
                try:
                    self._brake()
                    self._stale_braked = True
                except Exception:
                    self.logger.exception('Unable to brake with stale sensor data.')
        finally:
            self._record_poll_performance(monotonic() - poll_started, succeeded)

    def _record_sensor_sample(self):
        if self.sensor_log is None:
            return
        try:
            self.sensor_log.record(self.snapshot())
        except Exception:
            self.logger.exception('Unable to record Roomba sensor sample.')

    def _record_poll_performance(self, duration, succeeded):
        self._poll_perf_count += 1
        self._poll_perf_total += duration
        self._poll_perf_max = max(self._poll_perf_max, duration)
        if not succeeded:
            self._poll_perf_failures += 1
        now = monotonic()
        if now - self._poll_perf_started >= PERFORMANCE_LOG_INTERVAL:
            count = max(1, self._poll_perf_count)
            self.logger.debug(
                'Roomba I/O performance: polls=%d failures=%d average=%.1f ms '
                'max=%.1f ms configured_period=%.1f ms',
                self._poll_perf_count, self._poll_perf_failures,
                self._poll_perf_total / count * 1000.0,
                self._poll_perf_max * 1000.0,
                self.poll_interval * 1000.0,
            )
            self._poll_perf_started = now
            self._poll_perf_count = 0
            self._poll_perf_total = 0.0
            self._poll_perf_max = 0.0
            self._poll_perf_failures = 0

    @staticmethod
    def _sensor_hard_hazard_reasons(sensors):
        bumps = sensors.bumps_and_wheel_drops
        reasons = []
        for name in (
            'wheel_drop_left', 'wheel_drop_right',
            'cliff_left_sensor', 'cliff_front_left_sensor',
            'cliff_front_right_sensor', 'cliff_right_sensor',
        ):
            value = (getattr(bumps, name) if name.startswith('wheel_drop')
                     else getattr(sensors, name))
            if value:
                reasons.append(name)
        return reasons

    @staticmethod
    def _stationary_on_home_base(sensors, home_base):
        if not home_base:
            return False
        for name in (
            'requested_velocity', 'requested_left_velocity',
            'requested_right_velocity',
        ):
            value = getattr(sensors, name, 0)
            if value is not None and abs(int(value)) > 0:
                return False
        return True

    @staticmethod
    def _has_hazard(sensors):
        bumps = sensors.bumps_and_wheel_drops
        return bool(
            bumps.bump_left or bumps.bump_right or
            RobotCommandArbiter._sensor_hard_hazard_reasons(sensors)
        )

    @staticmethod
    def _format_safety_sensor_details(sensors):
        bumps = sensors.bumps_and_wheel_drops
        light_bumper = sensors.light_bumper
        details = [
            '{}={}'.format(name, getattr(bumps, name))
            for name in (
                'bump_left', 'bump_right', 'wheel_drop_left', 'wheel_drop_right',
            )
        ]
        for sensor, signal in (
            ('cliff_left_sensor', 'cliff_left_signal'),
            ('cliff_front_left_sensor', 'cliff_front_left_signal'),
            ('cliff_front_right_sensor', 'cliff_front_right_signal'),
            ('cliff_right_sensor', 'cliff_right_signal'),
        ):
            details.append('{}={} (signal={})'.format(
                sensor, getattr(sensors, sensor), getattr(sensors, signal, 'unknown'),
            ))
        for position in (
            'left', 'front_left', 'center_left', 'center_right', 'front_right', 'right',
        ):
            details.append('light_bumper.{}={} (signal={})'.format(
                position,
                getattr(light_bumper, position),
                getattr(sensors, 'light_bump_{}_signal'.format(position), 'unknown'),
            ))
        return '; '.join(details)

    @staticmethod
    def _wheel_target(operation, kwargs):
        """Convert velocity commands to left/right mm/s, preserving validation."""
        if operation not in ('drive', 'drive_straight', 'drive_direct', 'spin_left', 'spin_right'):
            return None
        if operation == 'drive_direct':
            left, right = float(kwargs['left_velocity']), float(kwargs['right_velocity'])
            expected = {'left_velocity', 'right_velocity'}
        else:
            velocity = float(kwargs['velocity'])
            if not isfinite(velocity) or abs(velocity) > 500:
                raise ValueError('Velocity must be between -500 and 500 mm/s')
            expected = {'velocity', 'radius'} if operation == 'drive' else {'velocity'}
            radius = int(kwargs['radius']) if operation == 'drive' else DRIVE.STRAIGHT
            if operation == 'spin_left' or radius == DRIVE.TURN_IN_PLACE_CCW:
                left, right = -velocity, velocity
            elif operation == 'spin_right' or radius in (-1, DRIVE.TURN_IN_PLACE_CW):
                left, right = velocity, -velocity
            elif radius in (DRIVE.STRAIGHT, DRIVE.STRAIGHT_ALT, -32768) or operation == 'drive_straight':
                left = right = velocity
            elif radius == 0 and velocity == 0:
                left = right = 0.0  # Legacy web Stop can send radius zero.
            elif radius == 0 or abs(radius) > 2000:
                raise ValueError('Invalid drive radius')
            else:
                left = velocity * (radius - ROBOT.WHEEL_BASE / 2.0) / radius
                right = velocity * (radius + ROBOT.WHEEL_BASE / 2.0) / radius
                scale = max(1.0, abs(left) / 500, abs(right) / 500)
                left, right = left / scale, right / scale
        if set(kwargs) != expected:
            raise ValueError('Unexpected wheel command arguments')
        if not all(isfinite(v) and abs(v) <= 500 for v in (left, right)):
            raise ValueError('Wheel velocities must be between -500 and 500 mm/s')
        return (left, right)

    def _complete_ramp_stops(self, error=None):
        pending, self._ramp_stops = self._ramp_stops, []
        for command in pending:
            command['result'].append(None)
            if error is not None:
                command['result'].append(error)
            command['done'].set()

    def _cancel_ramp(self):
        self._applied_wheels = (0, 0)
        self._ramp_current = self._ramp_target = (0.0, 0.0)
        self._ramp_sent = (0, 0)
        self._ramp_time = monotonic()
        self.logger.log(5, 'Wheel ramp cancelled for immediate brake.')

    def _advance_ramp(self, now=None):
        """One nonblocking I/O-thread step; poll safety between successive steps."""
        now = monotonic() if now is None else now
        if not self._ramp_enabled or self._ramp_current == self._ramp_target:
            self._ramp_time = now
            self._complete_ramp_stops()
            return
        dt = min(0.1, max(0.0, now - self._ramp_time))
        self._ramp_time = now
        if dt == 0:
            return
        try:
            if any(monotonic() > command['expires_at'] for command in self._ramp_stops):
                raise RuntimeError('Soft stop deadline reached; braking immediately')
            if self._sensor_time is None or monotonic() - self._sensor_time > SENSOR_MAX_AGE:
                raise RuntimeError('Ramp aborted because sensors are stale')
            probe = self._ramp_target if self._ramp_target != (0.0, 0.0) else self._ramp_current
            self._check_motion_allowed('drive_direct',
                {'left_velocity': int(probe[0]), 'right_velocity': int(probe[1])})
        except Exception:
            self._brake()
            return
        # Sign reversals stop BOTH wheels first. Keep paired wheel proportions
        # during each phase so straight drives and in-place spins stay symmetric.
        target = self._ramp_target
        if any(a * b < 0 for a, b in zip(self._ramp_current, target)):
            target = (0.0, 0.0)
        fraction = 1.0
        for actual, desired in zip(self._ramp_current, target):
            delta = abs(desired - actual)
            if delta:
                rate = self._acceleration if abs(desired) > abs(actual) else self._deceleration
                fraction = min(fraction, rate * dt / delta)
        updated = tuple(a + (b - a) * fraction for a, b in zip(self._ramp_current, target))
        sent = tuple(int(round(v)) for v in updated)
        if sent != self._ramp_sent:
            self.robot.drive_direct(right_velocity=sent[1], left_velocity=sent[0])
            self._ramp_sent = sent
            self._applied_wheels = sent
            self.logger.log(5, 'Wheel ramp applied: left=%d right=%d mm/s.', *sent)
        self._ramp_current = updated
        if updated == (0.0, 0.0):
            self._recovery_active = False
            self._complete_ramp_stops()

    def _brake(self):
        self._cancel_ramp()
        try:
            if not self._wheel_drop_stopped:
                result = self.robot.drive(0, DRIVE.STRAIGHT)
                self.logger.log(5, 'Wheel ramp applied: left=0 right=0 mm/s (immediate brake).')
            else:
                result = None
        except Exception as error:
            self._complete_ramp_stops(error)
            raise
        self._complete_ramp_stops()
        return result
