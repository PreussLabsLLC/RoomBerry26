"""NavLink v1 UDP recorder for pose, relative motion and phone health observations."""
# @(#)roomberry_navlink.py 3.1.compass.1 2026/10/31 12:10:00

import argparse
import csv
import logging
import math
from pathlib import Path
import socket
import struct
import sys
import threading
import time


PACKET = struct.Struct('<4sBBHQQIHBBQQQ14fHHIBB6s')
RECEIPT = struct.Struct('<QQ')
LOG_HEADER = struct.Struct('<8sHHI')
LOG_MAGIC = b'NVLLOG1\0'
FIELDS = (
    'magic', 'version', 'type', 'length', 'session', 'alignment', 'seq',
    'flags', 'tracking', 'reason', 'frame_us', 'send_us', 'imu_us',
    'x_mm', 'y_mm', 'z_mm', 'heading_rad', 'roll_rad', 'pitch_rad',
    'forward_mm_s', 'left_mm_s', 'yaw_rad_s',
    'ax_mm_s2', 'ay_mm_s2', 'az_mm_s2',
    'accel_peak_mm_s2', 'accel_rms_mm_s2', 'feature_count',
    'imu_samples', 'frame_age_us', 'battery_pct', 'battery_state', 'reserved',
)


GROUND_PACKET = struct.Struct('<4sBBHQQIHBBQQQIII12fHHBBHI')
GROUND_FIELDS = (
    'magic', 'version', 'type', 'length', 'session', 'calibration', 'seq',
    'flags', 'tracking', 'reason', 'start_us', 'end_us', 'send_us',
    'continuity', 'accepted_frames', 'rejected_frames',
    'segment_x_mm', 'segment_y_mm', 'segment_yaw_rad',
    'delta_forward_mm', 'delta_left_mm', 'delta_yaw_rad',
    'residual_mm', 'height_mm', 'path_mm', 'valid_seconds',
    'forward_mm_s', 'left_mm_s', 'inliers', 'candidates',
    'battery_pct', 'battery_state', 'reserved', 'processing_us',
)


def decode_ground_packet(data):
    if len(data) != GROUND_PACKET.size:
        raise ValueError('length')
    v = GROUND_PACKET.unpack(data)
    row = dict(zip(GROUND_FIELDS, v))
    if v[:4] != (b'NVLK', 1, 2, 128):
        raise ValueError('header')
    if not row['session'] or row['flags'] & ~7 or row['tracking'] > 3 or row['reason'] > 7:
        raise ValueError('identity/flags/state')
    if not row['start_us'] <= row['end_us'] <= row['send_us']:
        raise ValueError('time order')
    if not all(math.isfinite(n) for n in v[16:28]):
        raise ValueError('nonfinite')
    if any(row[k] < 0 for k in ('residual_mm', 'height_mm', 'path_mm', 'valid_seconds')):
        raise ValueError('diagnostics')
    if row['inliers'] > row['candidates'] or row['reserved']:
        raise ValueError('counts/reserved')
    if row['flags'] & 2 and (not row['calibration'] or not 50 <= row['height_mm'] <= 1500):
        raise ValueError('calibration')
    if row['flags'] & 1 and (row['flags'] != 7 or row['tracking'] != 2 or row['reason'] != 0
                             or not 0 < row['start_us'] < row['end_us']
                             or row['end_us'] - row['start_us'] > 150000
                             or row['send_us'] - row['end_us'] > 250000
                             or row['inliers'] < 24 or row['valid_seconds'] <= 0):
        raise ValueError('valid interval')
    if row['flags'] & 4 and not row['flags'] & 2:
        raise ValueError('uncalibrated tally')
    if row['battery_pct'] not in range(101) and row['battery_pct'] != 255:
        raise ValueError('battery')
    if row['battery_state'] > 3:
        raise ValueError('battery state')
    return v


HEALTH_PACKET = struct.Struct('<4sBBHQQIHBBQQQIHBB12fQHHI')
HEALTH_FIELDS = (
    'magic', 'version', 'type', 'length', 'session', 'calibration', 'seq',
    'flags', 'thermal_state', 'battery_state', 'send_us', 'imu_us',
    'bump_us', 'bump_count', 'imu_samples', 'battery_pct', 'reserved',
    'device_ax_mm_s2', 'device_ay_mm_s2', 'device_az_mm_s2',
    'device_wx_rad_s', 'device_wy_rad_s', 'device_wz_rad_s',
    'gravity_x_g', 'gravity_y_g', 'gravity_z_g',
    'interval_accel_peak_mm_s2', 'last_bump_peak_mm_s2', 'app_cpu_pct',
    'app_footprint_bytes', 'image_width', 'image_height', 'resource_age_ms',
)


def decode_health_packet(data):
    if len(data) != HEALTH_PACKET.size:
        raise ValueError('length')
    v = HEALTH_PACKET.unpack(data)
    r = dict(zip(HEALTH_FIELDS,v))
    if v[:4] != (b'NVLK', 1, 3, 128):
        raise ValueError('header')
    if not r['session'] or not r['calibration'] or r['flags'] & ~127 or r['reserved']:
        raise ValueError('identity/flags/reserved')
    if r['thermal_state'] not in (0, 1, 2, 3, 255) or r['battery_state'] > 3:
        raise ValueError('state')
    if r['battery_pct'] not in range(101) and r['battery_pct'] != 255:
        raise ValueError('battery')
    if bool(r['flags'] & 32) != (r['battery_pct'] <= 100):
        raise ValueError('battery validity')
    if not all(math.isfinite(n) for n in v[17:29]):
        raise ValueError('nonfinite')
    if any(r[k] < 0 for k in ('interval_accel_peak_mm_s2', 'last_bump_peak_mm_s2', 'app_cpu_pct')):
        raise ValueError('diagnostics')
    if r['imu_us'] > r['send_us'] or r['bump_us'] > r['send_us']:
        raise ValueError('time order')
    if r['flags'] & 1 and (not r['imu_us'] or r['send_us']-r['imu_us'] > 100000):
        raise ValueError('IMU age')
    if bool(r['flags'] & 2) != bool(r['imu_samples']):
        raise ValueError('interval validity')
    if bool(r['flags'] & 16) != bool(r['bump_count']):
        raise ValueError('bump validity')
    if r['bump_count'] and (not r['bump_us'] or not r['last_bump_peak_mm_s2']):
        raise ValueError('bump event')
    if not r['bump_count'] and (r['bump_us'] or r['last_bump_peak_mm_s2']):
        raise ValueError('absent bump')
    if r['flags'] & 12 and r['resource_age_ms'] > 2000:
        raise ValueError('resource age')
    if bool(r['flags'] & 64) != bool(r['image_width'] and r['image_height']):
        raise ValueError('image validity')
    if r['image_width'] > 8192 or r['image_height'] > 8192:
        raise ValueError('image dimensions')
    return v


COMPASS_PACKET = struct.Struct('<4sBBHQQIHBBQQ8fQ40s')
COMPASS_FIELDS = (
    'magic', 'version', 'type', 'length', 'session', 'calibration', 'seq',
    'flags', 'compass_state', 'reserved', 'send_us', 'compass_us',
    'phone_magnetic_bearing_rad', 'robot_magnetic_bearing_rad',
    'heading_accuracy_rad', 'magnetic_x_ut', 'magnetic_y_ut', 'magnetic_z_ut',
    'magnetic_magnitude_ut', 'mount_yaw_rad', 'compass_epoch_us', 'padding',
)


def decode_compass_packet(data):
    if len(data) != COMPASS_PACKET.size:
        raise ValueError('length')
    v = COMPASS_PACKET.unpack(data)
    r = dict(zip(COMPASS_FIELDS,v))
    if v[:4] != (b'NVLK', 1, 4, 128):
        raise ValueError('header')
    if not r['session'] or not r['calibration'] or r['flags'] & ~7 or r['reserved'] or r['padding'] != bytes(40):
        raise ValueError('identity/flags/reserved')
    if r['compass_state'] > 5 or r['compass_us'] > r['send_us']:
        raise ValueError('state/time')
    if not all(math.isfinite(n) for n in v[12:20]):
        raise ValueError('nonfinite')
    if not all(0 <= r[k] <= 2*math.pi+1e-6 for k in ('phone_magnetic_bearing_rad', 'robot_magnetic_bearing_rad')):
        raise ValueError('bearing')
    if r['magnetic_magnitude_ut'] < 0 or abs(r['mount_yaw_rad']) > 2*math.pi+1e-6:
        raise ValueError('diagnostics')
    if r['flags']:
        if not r['compass_us'] or not r['compass_epoch_us'] or r['send_us']-r['compass_us'] > 1000000:
            raise ValueError('compass age')
    if r['flags'] & 5:
        if r['flags'] & 5 != 5 or r['compass_state'] != 2 or not 0 <= r['heading_accuracy_rad'] <= math.radians(20)+1e-6:
            raise ValueError('heading validity')
    elif r['compass_state'] == 2:
        raise ValueError('heading state')
    if r['compass_state'] in (0, 1, 4, 5) and r['flags']:
        raise ValueError('unavailable')
    return v


def packet_fields(values):
    return {1: FIELDS, 2: GROUND_FIELDS, 3: HEALTH_FIELDS, 4: COMPASS_FIELDS}[values[2]]


def decode_packet(data):
    """Validate framing and representation; this does not qualify navigation."""
    if len(data) != PACKET.size:
        raise ValueError('length')
    if data[5] == 2:
        return decode_ground_packet(data)
    if data[5] == 3:
        return decode_health_packet(data)
    if data[5] == 4:
        return decode_compass_packet(data)
    v = PACKET.unpack(data)
    if v[:4] != (b'NVLK', 1, 1, PACKET.size):
        raise ValueError('header')
    if not v[4] or v[7] & ~0x7f or v[8] > 3 or v[9] > 7:
        raise ValueError('identity/flags/state')
    if v[11] < v[10] or v[12] > v[11]:
        raise ValueError('time order')
    if not all(math.isfinite(n) for n in v[13:27]):
        raise ValueError('nonfinite')
    if v[25] < 0 or v[26] < 0:
        raise ValueError('diagnostics')
    if v[30] not in range(101) and v[30] != 255:
        raise ValueError('battery')
    if v[31] > 3 or v[32] != bytes(6):
        raise ValueError('reserved/state')
    return v


class NavLinkReceiver:
    """Record valid wire packets, including duplicates and tracking failures.

    Recording retains sequence and timestamp history verbatim. Optional
    localization aiding reads a separate ordered observation snapshot.
    """

    def __init__(self, directory='/var/log/roomberry-navlink', host='0.0.0.0',
                 port=5010, flush_interval_s=10, max_files=20,
                 max_file_bytes=16 * 1024 * 1024, allowed_source=None,
                 logger=None):
        self.directory = Path(directory)
        self.host = host
        self.port = int(port)
        self.flush_interval_s = max(0.1, float(flush_interval_s))
        self.max_files = max(1, int(max_files))
        self.max_file_bytes = max(160, int(max_file_bytes))
        # Optional literal IPv4 address; never resolve DNS for every packet.
        self.allowed_source = allowed_source
        self.logger = logger or logging.getLogger('Roomberry.NavLink')
        self.received = 0
        self.rejected = 0
        self.path = None
        self._socket = None
        self._file = None
        self._thread = None
        self._stop = threading.Event()
        self._bytes = 0
        self._last_flush = 0
        self._observation_lock = threading.Lock()
        self._observation = None
        self._observation_identity = None
        self._observation_seq = None
        self._clock_offset = None
        self._ground = None
        self._ground_identity = None
        self._ground_seq = None
        self._ground_baseline = None
        self._ground_retired = []
        self._health = None
        self._health_identity = None
        self._health_retired = []
        self._compass = None
        self._compass_identity = None
        self._compass_retired = []

    def _observe(self, values, received_at):
        """Keep ordered observations separately from the unfiltered recording."""
        if values[2] == 4:
            self._observe_compass(values, received_at)
            return
        if values[2] == 3:
            self._observe_health(values, received_at)
            return
        if values[2] == 2:
            self._observe_ground(values, received_at)
            return
        row = dict(zip(FIELDS, values))
        identity = (row['session'], row['alignment'])
        with self._observation_lock:
            if identity != self._observation_identity:
                self._observation_identity = identity
                self._observation_seq = None
                self._clock_offset = None
            if self._observation_seq is not None:
                advance = (row['seq'] - self._observation_seq) & 0xffffffff
                if not 0 < advance < 0x80000000:
                    return
            self._observation_seq = row['seq']
            offset = received_at - row['send_us'] / 1e6
            self._clock_offset = offset if self._clock_offset is None else min(self._clock_offset, offset)
            row['frame_monotonic'] = row['frame_us'] / 1e6 + self._clock_offset
            self._observation = row

    def latest_observation(self):
        with self._observation_lock:
            return None if self._observation is None else dict(self._observation)

    def _observe_ground(self, values, received_at):
        row = dict(zip(GROUND_FIELDS, values))
        identity = (row['session'], row['calibration'])
        with self._observation_lock:
            if identity in self._ground_retired:
                return
            if identity != self._ground_identity:
                if self._ground_identity is not None:
                    self._ground_retired.append(self._ground_identity)
                    self._ground_retired = self._ground_retired[-32:]
                self._ground_identity = identity
                self._ground_seq = None
                self._ground_baseline = None
            if self._ground_seq is not None:
                advance = (row['seq'] - self._ground_seq) & 0xffffffff
                if not 0 < advance < 0x80000000:
                    return
            self._ground_seq = row['seq']
            row['received_monotonic'] = received_at
            row['recovered_delta'] = None
            old = self._ground_baseline
            usable = row['flags'] == 7
            if usable and old is not None and row['continuity'] == old['continuity']:
                # Repeated frame snapshots must never apply movement twice.
                if row['end_us'] > old['end_us'] and row['accepted_frames'] > old['accepted_frames']:
                    x = row['segment_x_mm'] - old['segment_x_mm']
                    y = row['segment_y_mm'] - old['segment_y_mm']
                    c, s = math.cos(old['segment_yaw_rad']), math.sin(old['segment_yaw_rad'])
                    row['recovered_delta'] = (c*x+s*y, -s*x+c*y,
                                              row['segment_yaw_rad']-old['segment_yaw_rad'])
                elif row['end_us'] < old['end_us']:
                    return
            self._ground_baseline = row if usable else None
            self._ground = row

    def latest_ground_observation(self):
        """Relative telemetry only; no automatic navigation fusion or clock claim."""
        with self._observation_lock:
            return None if self._ground is None else dict(self._ground)

    def _observe_health(self, values, received_at):
        row = dict(zip(HEALTH_FIELDS,values))
        identity = (row['session'],row['calibration'])
        with self._observation_lock:
            if identity in self._health_retired:
                return
            old = self._health
            if identity != self._health_identity:
                if self._health_identity is not None:
                    self._health_retired.append(self._health_identity)
                    self._health_retired = self._health_retired[-32:]
                self._health_identity = identity
                old = None
            if old is not None:
                advance = (row['seq']-old['seq']) & 0xffffffff
                if not 0 < advance < 0x80000000 or row['bump_count'] < old['bump_count']:
                    return
            row['received_monotonic'] = received_at
            row['new_bumps'] = row['bump_count']-old['bump_count'] if old is not None else 0
            self._health = row

    def latest_health_observation(self):
        """Ordered sensor snapshot; callers must deduplicate sequence reads."""
        with self._observation_lock:
            return None if self._health is None else dict(self._health)

    def _observe_compass(self, values, received_at):
        row = dict(zip(COMPASS_FIELDS,values))
        row.pop('padding')
        identity = (row['session'],row['calibration'])
        with self._observation_lock:
            if identity in self._compass_retired:
                return
            old = self._compass
            if identity != self._compass_identity:
                if self._compass_identity is not None:
                    self._compass_retired.append(self._compass_identity)
                    self._compass_retired = self._compass_retired[-32:]
                self._compass_identity = identity
                old = None
            if old is not None:
                advance = (row['seq']-old['seq']) & 0xffffffff
                if not 0 < advance < 0x80000000:
                    return
            row['received_monotonic'] = received_at
            self._compass = row

    def latest_compass_observation(self):
        """Magnetic diagnostics only; no navigation correction is implied."""
        with self._observation_lock:
            return None if self._compass is None else dict(self._compass)

    @classmethod
    def from_config(cls, config, logger=None):
        if not config or not config.get('enabled', False):
            return None
        return cls(**{k: config[k] for k in (
            'directory', 'host', 'port', 'flush_interval_s', 'max_files',
            'max_file_bytes', 'allowed_source',
        ) if k in config}, logger=logger)

    def _open_log(self):
        if self._file is not None:
            self._file.close()
            self._file = None
        self.directory.mkdir(parents=True, exist_ok=True)
        # Exclusive create avoids overwriting another receiver's run.
        stamp = time.strftime('%Y%m%d-%H%M%S')
        for index in range(10000):
            candidate = self.directory / (
                'roomberry-navlink-{}-{:04d}.bin'.format(stamp, index)
            )
            try:
                self._file = candidate.open('xb', buffering=64 * 1024)
                self.path = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError('Unable to allocate NavLink log filename')
        self._file.write(LOG_HEADER.pack(LOG_MAGIC, 1, 144, 128))
        self._file.flush()
        self._bytes = LOG_HEADER.size
        self._last_flush = time.monotonic()
        files = sorted(self.directory.glob('roomberry-navlink-*.bin'),
                       key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for old in files[self.max_files:]:
            if old != self.path:
                old.unlink()
        self.logger.info('Recording NavLink to %s', self.path)

    def start(self):
        if self._thread is not None:
            return False
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind((self.host, self.port))
            self.port = self._socket.getsockname()[1]
            self._socket.settimeout(0.5)
            self._open_log()
        except OSError:
            self.logger.warning('Unable to start NavLink recording', exc_info=True)
            self._close_resources()
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='NavLink', daemon=True)
        self._thread.start()
        self.logger.info('NavLink listening on %s:%d (recording enabled)', self.host, self.port)
        return True

    def _run(self):
        try:
            while not self._stop.is_set():
                self._flush_if_due()
                try:
                    # 129 detects any oversize datagram, including truncation.
                    data, source = self._socket.recvfrom(PACKET.size + 1)
                    wall_ns, monotonic_ns = time.time_ns(), time.monotonic_ns()
                except socket.timeout:
                    continue
                if self.allowed_source and source[0] != self.allowed_source:
                    self.rejected += 1
                    continue
                try:
                    values = decode_packet(data)
                except ValueError:
                    self.rejected += 1
                    continue
                if self._bytes + 144 > self.max_file_bytes:
                    self._open_log()
                self._file.write(RECEIPT.pack(wall_ns, monotonic_ns) + data)
                self._observe(values, monotonic_ns / 1e9)
                self._bytes += 144
                self.received += 1
        except OSError:
            if not self._stop.is_set():
                self.logger.warning('NavLink recording stopped after I/O error', exc_info=True)
        finally:
            self._close_resources()
            self.logger.info('NavLink stopped: %d recorded, %d rejected',
                             self.received, self.rejected)

    def _flush_if_due(self):
        now = time.monotonic()
        if now - self._last_flush >= self.flush_interval_s:
            self._file.flush()
            self._last_flush = now

    def _close_resources(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                self.logger.warning('Unable to close NavLink log', exc_info=True)
            self._file = None

    def close(self):
        self._stop.set()
        if self._thread is not None:
            # Socket timeout bounds shutdown without a cross-thread socket close.
            self._thread.join()
            self._thread = None


def export_csv(path, output):
    """Stream a binary recording to CSV; tolerate an incomplete final record."""
    writer = csv.writer(output)
    columns = list(FIELDS[4:-1]) + ['type']
    for fields in (GROUND_FIELDS, HEALTH_FIELDS, COMPASS_FIELDS):
        columns += [k for k in fields[4:] if k not in ('reserved', 'padding') and k not in columns]
    writer.writerow(('receive_epoch_ns', 'receive_monotonic_ns') + tuple(columns))
    with Path(path).open('rb') as source:
        if source.read(LOG_HEADER.size) != LOG_HEADER.pack(LOG_MAGIC, 1, 144, 128):
            raise ValueError('Unsupported NavLink log header')
        while True:
            record = source.read(144)
            if not record:
                break
            if len(record) != 144:
                logging.warning('Ignoring incomplete final NavLink record')
                break
            values = decode_packet(record[RECEIPT.size:])
            row = dict(zip(packet_fields(values), values))
            writer.writerow(RECEIPT.unpack(record[:RECEIPT.size]) + tuple(row.get(k, '') for k in columns))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='/var/log/roomberry-navlink')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5010)
    parser.add_argument('--csv', metavar='BINARY_LOG', help='export a log to stdout')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.csv:
        export_csv(args.csv, sys.stdout)
        return
    receiver = NavLinkReceiver(args.directory, args.host, args.port)
    if not receiver.start():
        raise SystemExit(1)
    try:
        while receiver._thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.close()


if __name__ == '__main__':
    main()
