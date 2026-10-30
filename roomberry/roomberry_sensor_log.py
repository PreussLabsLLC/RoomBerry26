"""Buffered CSV recording of Roomba sensor group 100 samples."""
# @(#)roomberry_sensor_log.py 2.3.18 2026/10/28 21:40:00

import csv
from collections import deque
from datetime import datetime
from pathlib import Path
from time import monotonic, time


SENSOR_LOG_INTERVAL_S = 0.1
SENSOR_LOG_FLUSH_INTERVAL_S = 10.0
SENSOR_LOG_MAX_FILES = 20
SENSOR_LOG_FILENAME_PREFIX = 'roomberry-sensors'
CURRENT_AVERAGE_WINDOWS = (1.0, 5.0)


class SensorCsvRecorder:
    """Write one CSV per service run without fsyncing every sample.

    Rows are kept in the normal Python file buffer and only flushed to the
    operating system at ``flush_interval_s``. The kernel then decides when to
    write the dirty pages to the SD card, so a 10 Hz test run costs the same
    media wear as any other buffered file of the same size. No ``fsync`` is
    used. Old run files are pruned to ``max_files`` on startup.
    """

    COLUMNS = (
        'timestamp', 'epoch_s', 'elapsed_s',
        'battery_status', 'charging_state', 'home_base', 'oi_mode', 'ready',
        'safety_latched', 'hazards_suppressed', 'hard_hazard',
        'distance_mm', 'travelled_distance_mm', 'angle_deg',
        'distance_delta_mm', 'angle_delta_deg', 'odometry_epoch',
        'raw_distance_mm', 'raw_angle_deg',
        'left_encoder_counts', 'right_encoder_counts',
        'battery_voltage_v', 'battery_current_a', 'battery_power_w',
        'battery_current_avg_1s_a', 'battery_current_avg_5s_a',
        'battery_charge_mah', 'battery_capacity_mah', 'battery_percent',
        'temperature_c',
        'left_motor_current_a', 'right_motor_current_a',
        'main_brush_motor_current_a', 'side_brush_motor_current_a',
        'left_motor_current_avg_1s_a', 'left_motor_current_avg_5s_a',
        'right_motor_current_avg_1s_a', 'right_motor_current_avg_5s_a',
        'requested_velocity_mm_s', 'requested_radius_mm',
        'requested_left_velocity_mm_s', 'requested_right_velocity_mm_s',
        'bump_left', 'bump_right', 'wheel_drop_left', 'wheel_drop_right',
        'wall_sensor', 'virtual_wall_sensor', 'wall_signal',
        'cliff_left_sensor', 'cliff_front_left_sensor',
        'cliff_front_right_sensor', 'cliff_right_sensor',
        'cliff_left_signal', 'cliff_front_left_signal',
        'cliff_front_right_signal', 'cliff_right_signal',
        'light_bumper_left', 'light_bumper_front_left',
        'light_bumper_center_left', 'light_bumper_center_right',
        'light_bumper_front_right', 'light_bumper_right',
        'light_bump_left_signal', 'light_bump_front_left_signal',
        'light_bump_center_left_signal', 'light_bump_center_right_signal',
        'light_bump_front_right_signal', 'light_bump_right_signal',
        'wheel_overcurrent_left', 'wheel_overcurrent_right',
        'wheel_overcurrent_main_brush', 'wheel_overcurrent_side_brush',
        'dirt_detect', 'stasis_toggling', 'stasis_disabled',
        'ir_char_omni', 'ir_character_left', 'ir_character_right',
        'applied_left_velocity_mm_s', 'applied_right_velocity_mm_s',
        'button_group_mask', 'button_dedicated_mask', 'button_source',
        'reverse_monitor_mode', 'reverse_current_candidate', 'reverse_current_reasons',
        'reverse_current_events', 'reverse_left_threshold_a', 'reverse_right_threshold_a',
    )

    def __init__(self, directory, logger=None,
                 interval_s=SENSOR_LOG_INTERVAL_S,
                 flush_interval_s=SENSOR_LOG_FLUSH_INTERVAL_S,
                 max_files=SENSOR_LOG_MAX_FILES,
                 filename_prefix=SENSOR_LOG_FILENAME_PREFIX,
                 time_function=time, monotonic_function=monotonic):
        self.directory = Path(directory)
        self.logger = logger
        self.interval_s = max(0.0, float(interval_s))
        self.flush_interval_s = max(0.0, float(flush_interval_s))
        self.max_files = max(0, int(max_files))
        self.filename_prefix = str(filename_prefix)
        self._time = time_function
        self._monotonic = monotonic_function
        self.enabled = True
        self.path = None
        self._file = None
        self._writer = None
        self._started_at = None
        self._last_sample_at = None
        self._last_flush_at = None
        self._last_distance = None
        self._last_angle = None
        self._last_odometry_epoch = None
        self._history = deque()

    @classmethod
    def from_config(cls, config, logger=None):
        """Create a recorder from an autonomy ``sensor_log`` section."""
        if config is None:
            return None
        if not bool(config.get('enabled', True)):
            return None
        return cls(
            config.get('directory', '/var/log/roomberry-sensors'),
            logger=logger,
            interval_s=config.get('interval_s', SENSOR_LOG_INTERVAL_S),
            flush_interval_s=config.get(
                'flush_interval_s', SENSOR_LOG_FLUSH_INTERVAL_S
            ),
            max_files=config.get('max_files', SENSOR_LOG_MAX_FILES),
            filename_prefix=config.get(
                'filename_prefix', SENSOR_LOG_FILENAME_PREFIX
            ),
        )

    def start(self):
        """Open a new run file and write its header."""
        if not self.enabled or self._file is not None:
            return False
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._prune_old_files()
            self.path = self._unique_path()
            self._file = self.path.open(
                'w', newline='', encoding='utf-8', buffering=64 * 1024
            )
            self._writer = csv.writer(self._file)
            self._writer.writerow(self.COLUMNS)
            self._started_at = self._monotonic()
            self._last_flush_at = self._started_at
            self._file.flush()
            self._log(
                'info', 'Recording Roomba sensors to %s', self.path,
            )
            return True
        except OSError:
            self._disable('Unable to start Roomba sensor recording', exc_info=True)
            return False

    def record(self, snapshot, sensors=None, timestamp=None):
        """Append one sample if the configured interval has elapsed."""
        if not self.enabled or self._writer is None:
            return False
        snapshot = snapshot or {}
        if sensors is None:
            sensors = snapshot.get('sensors')
        if sensors is None:
            return False

        now = self._monotonic()
        if (self._last_sample_at is not None and
                now - self._last_sample_at < self.interval_s):
            return False

        wall_time = self._time() if timestamp is None else float(timestamp)
        row = self._build_row(snapshot, sensors, wall_time, now)
        try:
            self._writer.writerow([row.get(column, '') for column in self.COLUMNS])
            self._last_sample_at = now
            if (self._last_flush_at is None or
                    now - self._last_flush_at >= self.flush_interval_s):
                self._file.flush()
                self._last_flush_at = now
            return True
        except Exception:
            self._disable('Unable to write Roomba sensor sample', exc_info=True)
            return False

    def close(self):
        if self._file is None:
            return
        path = self.path
        file_object = self._file
        self._file = None
        self._writer = None
        try:
            file_object.flush()
            file_object.close()
            self._log('info', 'Roomba sensor recording closed: %s', path)
        except Exception:
            self._disable('Unable to close Roomba sensor recording', exc_info=True)

    def _build_row(self, snapshot, sensors, wall_time, now):
        def value(obj, name, default=None):
            if obj is None:
                return default
            try:
                return getattr(obj, name)
            except Exception:
                return default

        def flag(current):
            return '' if current is None else int(bool(current))

        def number(current, digits=None):
            if current is None:
                return ''
            if digits is None:
                return current
            return round(float(current), digits)

        def amps(current_ma):
            return None if current_ma is None else float(current_ma) / 1000.0

        bumps = value(sensors, 'bumps_and_wheel_drops')
        light = value(sensors, 'light_bumper')
        overcurrents = value(sensors, 'wheel_overcurrents')
        stasis = value(sensors, 'stasis')

        voltage_v = amps(value(sensors, 'voltage'))
        current_a = amps(value(sensors, 'current'))
        left_current_a = amps(value(sensors, 'left_motor_current'))
        right_current_a = amps(value(sensors, 'right_motor_current'))
        power_w = (
            None if voltage_v is None or current_a is None
            else voltage_v * current_a
        )
        charge = value(sensors, 'battery_charge')
        capacity = value(sensors, 'battery_capacity')
        battery_percent = (
            None if not capacity else float(charge or 0) / float(capacity) * 100.0
        )

        distance = snapshot.get('distance')
        angle = snapshot.get('angle')
        odometry_epoch = snapshot.get('odometry_epoch')
        distance_delta = None
        angle_delta = None
        if (odometry_epoch is not None and
                self._last_odometry_epoch is not None and
                odometry_epoch != self._last_odometry_epoch):
            distance_delta = 0.0
            angle_delta = 0.0
        else:
            if distance is not None and self._last_distance is not None:
                distance_delta = float(distance) - float(self._last_distance)
            if angle is not None and self._last_angle is not None:
                angle_delta = float(angle) - float(self._last_angle)
        self._last_distance = distance
        self._last_angle = angle
        self._last_odometry_epoch = odometry_epoch

        self._history.append((now, current_a, left_current_a, right_current_a))
        cutoff = now - max(CURRENT_AVERAGE_WINDOWS)
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        def average(index, window):
            values = [
                sample[index] for sample in self._history
                if sample[index] is not None and sample[0] >= now - window
            ]
            return None if not values else sum(values) / len(values)

        return {
            'timestamp': datetime.fromtimestamp(wall_time).isoformat(
                timespec='milliseconds'
            ),
            'epoch_s': round(wall_time, 3),
            'elapsed_s': (
                '' if self._started_at is None
                else round(now - self._started_at, 3)
            ),
            'battery_status': snapshot.get('battery_status', ''),
            'charging_state': value(sensors, 'charging_state', ''),
            'home_base': flag(snapshot.get('home_base')),
            'oi_mode': value(sensors, 'oi_mode', ''),
            'ready': flag(snapshot.get('ready')),
            'safety_latched': flag(snapshot.get('safety_latched')),
            'hazards_suppressed': flag(snapshot.get('hazards_suppressed')),
            'hard_hazard': flag(snapshot.get('hard_hazard')),
            'distance_mm': number(distance, 1),
            'travelled_distance_mm': number(
                snapshot.get('travelled_distance'), 1
            ),
            'angle_deg': number(angle, 2),
            'distance_delta_mm': number(distance_delta, 1),
            'angle_delta_deg': number(angle_delta, 2),
            'odometry_epoch': '' if odometry_epoch is None else odometry_epoch,
            'raw_distance_mm': value(sensors, 'distance', ''),
            'raw_angle_deg': value(sensors, 'angle', ''),
            'left_encoder_counts': value(sensors, 'left_encoder_counts', ''),
            'right_encoder_counts': value(sensors, 'right_encoder_counts', ''),
            'battery_voltage_v': number(voltage_v, 3),
            'battery_current_a': number(current_a, 3),
            'battery_power_w': number(power_w, 3),
            'battery_current_avg_1s_a': number(average(1, 1.0), 3),
            'battery_current_avg_5s_a': number(average(1, 5.0), 3),
            'battery_charge_mah': value(sensors, 'battery_charge', ''),
            'battery_capacity_mah': value(sensors, 'battery_capacity', ''),
            'battery_percent': number(battery_percent, 1),
            'temperature_c': value(sensors, 'temperature', ''),
            'left_motor_current_a': number(left_current_a, 3),
            'right_motor_current_a': number(right_current_a, 3),
            'main_brush_motor_current_a': number(
                amps(value(sensors, 'main_brush_motor_current')), 3
            ),
            'side_brush_motor_current_a': number(
                amps(value(sensors, 'side_brush_motor_current')), 3
            ),
            'left_motor_current_avg_1s_a': number(average(2, 1.0), 3),
            'left_motor_current_avg_5s_a': number(average(2, 5.0), 3),
            'right_motor_current_avg_1s_a': number(average(3, 1.0), 3),
            'right_motor_current_avg_5s_a': number(average(3, 5.0), 3),
            'requested_velocity_mm_s': value(sensors, 'requested_velocity', ''),
            'requested_radius_mm': value(sensors, 'requested_radius', ''),
            'requested_left_velocity_mm_s': value(
                sensors, 'requested_left_velocity', ''
            ),
            'requested_right_velocity_mm_s': value(
                sensors, 'requested_right_velocity', ''
            ),
            'bump_left': flag(value(bumps, 'bump_left')),
            'bump_right': flag(value(bumps, 'bump_right')),
            'wheel_drop_left': flag(value(bumps, 'wheel_drop_left')),
            'wheel_drop_right': flag(value(bumps, 'wheel_drop_right')),
            'wall_sensor': flag(value(sensors, 'wall_sensor')),
            'virtual_wall_sensor': flag(value(sensors, 'virtual_wall_sensor')),
            'wall_signal': value(sensors, 'wall_signal', ''),
            'cliff_left_sensor': flag(value(sensors, 'cliff_left_sensor')),
            'cliff_front_left_sensor': flag(value(
                sensors, 'cliff_front_left_sensor'
            )),
            'cliff_front_right_sensor': flag(value(
                sensors, 'cliff_front_right_sensor'
            )),
            'cliff_right_sensor': flag(value(sensors, 'cliff_right_sensor')),
            'cliff_left_signal': value(sensors, 'cliff_left_signal', ''),
            'cliff_front_left_signal': value(
                sensors, 'cliff_front_left_signal', ''
            ),
            'cliff_front_right_signal': value(
                sensors, 'cliff_front_right_signal', ''
            ),
            'cliff_right_signal': value(sensors, 'cliff_right_signal', ''),
            'light_bumper_left': flag(value(light, 'left')),
            'light_bumper_front_left': flag(value(light, 'front_left')),
            'light_bumper_center_left': flag(value(light, 'center_left')),
            'light_bumper_center_right': flag(value(light, 'center_right')),
            'light_bumper_front_right': flag(value(light, 'front_right')),
            'light_bumper_right': flag(value(light, 'right')),
            'light_bump_left_signal': value(sensors, 'light_bump_left_signal', ''),
            'light_bump_front_left_signal': value(
                sensors, 'light_bump_front_left_signal', ''
            ),
            'light_bump_center_left_signal': value(
                sensors, 'light_bump_center_left_signal', ''
            ),
            'light_bump_center_right_signal': value(
                sensors, 'light_bump_center_right_signal', ''
            ),
            'light_bump_front_right_signal': value(
                sensors, 'light_bump_front_right_signal', ''
            ),
            'light_bump_right_signal': value(
                sensors, 'light_bump_right_signal', ''
            ),
            'wheel_overcurrent_left': flag(value(
                overcurrents, 'left_wheel_overcurrent'
            )),
            'wheel_overcurrent_right': flag(value(
                overcurrents, 'right_wheel_overcurrent'
            )),
            'wheel_overcurrent_main_brush': flag(value(
                overcurrents, 'main_brush_overcurrent'
            )),
            'wheel_overcurrent_side_brush': flag(value(
                overcurrents, 'side_brush_overcurrent'
            )),
            # Driver group-100 accessor uses offset 9 (unused); packet 17 is byte 10.
            'ir_char_omni': (sensors._data[10] if len(value(sensors, '_data', b'')) == 80
                             else value(sensors, 'ir_char_omni_sensor', '')),
            'ir_character_left': value(sensors, 'ir_character_left', ''),
            'ir_character_right': value(sensors, 'ir_character_right', ''),
            'dirt_detect': value(sensors, 'dirt_detect_sensor', ''),
            'stasis_toggling': flag(value(stasis, 'toggling')),
            'stasis_disabled': flag(value(stasis, 'disabled')),
            'applied_left_velocity_mm_s': snapshot.get('applied_left_velocity_mm_s', ''),
            'applied_right_velocity_mm_s': snapshot.get('applied_right_velocity_mm_s', ''),
            'button_group_mask': snapshot.get('button_diagnostics', {}).get('group_mask', ''),
            'button_dedicated_mask': snapshot.get('button_diagnostics', {}).get('dedicated_mask', ''),
            'button_source': snapshot.get('button_diagnostics', {}).get('source', ''),
            'reverse_monitor_mode': snapshot.get('reverse_current_monitor', {}).get('mode', ''),
            'reverse_current_candidate': flag(snapshot.get('reverse_current_monitor', {}).get('candidate')),
            'reverse_current_reasons': '|'.join(snapshot.get('reverse_current_monitor', {}).get('reasons', [])),
            'reverse_current_events': snapshot.get('reverse_current_monitor', {}).get('event_count', ''),
            'reverse_left_threshold_a': snapshot.get('reverse_current_monitor', {}).get('threshold_a', ['', ''])[0],
            'reverse_right_threshold_a': snapshot.get('reverse_current_monitor', {}).get('threshold_a', ['', ''])[1],
        }

    def _prune_old_files(self):
        if self.max_files <= 0:
            return

        def modified_at(path):
            try:
                return path.stat().st_mtime
            except OSError:
                return 0

        files = sorted(
            self.directory.glob(self.filename_prefix + '-*.csv'),
            key=modified_at,
            reverse=True,
        )
        for old_path in files[max(0, self.max_files - 1):]:
            try:
                old_path.unlink()
            except OSError:
                self._log(
                    'warning', 'Unable to remove old sensor log %s', old_path,
                )

    def _unique_path(self):
        stamp = datetime.fromtimestamp(self._time()).strftime('%Y%m%d-%H%M%S')
        base = '{}-{}'.format(self.filename_prefix, stamp)
        path = self.directory / (base + '.csv')
        index = 1
        while path.exists():
            path = self.directory / '{}-{:02d}.csv'.format(base, index)
            index += 1
        return path

    def _disable(self, message, exc_info=False):
        self.enabled = False
        file_object = self._file
        self._file = None
        self._writer = None
        if file_object is not None:
            try:
                file_object.close()
            except Exception:
                pass
        self._log('warning', message, exc_info=exc_info)

    def _log(self, level, message, *args, exc_info=False):
        if self.logger is not None:
            getattr(self.logger, level)(message, *args, exc_info=exc_info)
