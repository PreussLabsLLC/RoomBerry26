"""NavLink v1 observation-only UDP receiver and buffered binary recorder."""
# @(#)roomberry_navlink.py 2.3.navlink.1 2026/10/30 09:51:08

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


def decode_packet(data):
    """Validate framing and representation; this does not qualify navigation."""
    if len(data) != PACKET.size:
        raise ValueError('length')
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

    No motor, mapper or localization consumer receives these observations.
    Sequence and timestamp history is retained verbatim for offline analysis.
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
        self.logger.info('NavLink listening on %s:%d (record only)', self.host, self.port)
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
                    decode_packet(data)
                except ValueError:
                    self.rejected += 1
                    continue
                if self._bytes + 144 > self.max_file_bytes:
                    self._open_log()
                self._file.write(RECEIPT.pack(wall_ns, monotonic_ns) + data)
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
    writer.writerow(('receive_epoch_ns', 'receive_monotonic_ns') + FIELDS[4:-1])
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
            writer.writerow(RECEIPT.unpack(record[:RECEIPT.size]) + values[4:-1])


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
