# @(#)roomberry_navlink_test.py 2.3.navlink.1 2026/10/30 09:51:08
import csv
import io
import math
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from roomberry_navlink import (
    PACKET, RECEIPT, LOG_HEADER, LOG_MAGIC, NavLinkReceiver, decode_packet, export_csv,
)


def packet():
    return PACKET.pack(b'NVLK', 1, 1, 128, 0x0102030405060708, 0, 42,
                       0x6f, 2, 0, 1000000, 1010000, 1009000,
                       *[float(n) for n in range(1, 15)],
                       321, 5, 10000, 87, 2, bytes(6))


class NavLinkTest(unittest.TestCase):
    def test_roomberry_lifecycle_and_cleanup_after_serial_close_failure(self):
        from roomberry import RoomberryServer
        server = SimpleNamespace(
            logger=Mock(), navlink=Mock(), roomba_control=Mock(),
            camera_service=Mock(), mission=None, serve_forever=Mock(),
            server_close=Mock(),
        )
        RoomberryServer.start(server)
        server.navlink.start.assert_called_once_with()
        server.serve_forever.assert_called_once_with()
        server.roomba_control.close.side_effect = OSError('serial disconnected')
        with self.assertRaises(OSError):
            RoomberryServer.stop(server)
        server.navlink.close.assert_called_once_with()

    def test_offsets_and_invalid_packets(self):
        data = packet()
        self.assertEqual(len(data), 128)
        self.assertEqual(data[:8], b'NVLK\x01\x01\x80\x00')
        self.assertEqual(data[8:16], bytes.fromhex('0807060504030201'))
        self.assertEqual(struct.unpack_from('<f', data, 56)[0], 1)
        self.assertEqual(data[120:122], bytes((87, 2)))
        self.assertEqual(decode_packet(data)[6], 42)
        bad_float = bytearray(data)
        struct.pack_into('<f', bad_float, 56, math.nan)
        future_frame = bytearray(data)
        struct.pack_into('<Q', future_frame, 32, 2000000)
        for invalid in (data[:-1], data + b'x', b'BAD!' + data[4:],
                        data[:4] + b'\x02' + data[5:], bytes(bad_float),
                        bytes(future_frame), data[:-1] + b'\x01',
                        data[:120] + b'\xfe' + data[121:]):
            with self.subTest(data=invalid[:8]):
                with self.assertRaises(ValueError):
                    decode_packet(invalid)

    def test_udp_recording_and_csv_preserve_failed_tracking_and_duplicates(self):
        with TemporaryDirectory() as directory:
            receiver = NavLinkReceiver(directory, '127.0.0.1', 0, flush_interval_s=0.1)
            self.assertTrue(receiver.start())
            self.assertFalse(receiver.start())
            status = bytearray(packet())
            status[28:32] = bytes((0x20, 0, 3, 5))
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for data in (packet(), packet(), bytes(status), b'bad', packet() + bytes(4096)):
                        sender.sendto(data, ('127.0.0.1', receiver.port))
                deadline = time.monotonic() + 3
                while receiver.received + receiver.rejected < 5 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual((receiver.received, receiver.rejected), (3, 2))
                # A quiet stream still flushes on the receive timeout.
                time.sleep(0.6)
                self.assertEqual(receiver.path.stat().st_size, 16 + 3 * 144)
            finally:
                receiver.close()
            raw = receiver.path.read_bytes()
            self.assertEqual(raw[:16], LOG_HEADER.pack(LOG_MAGIC, 1, 144, 128))
            self.assertEqual(raw[32:160], packet())
            wall, mono = RECEIPT.unpack(raw[16:32])
            self.assertGreater(wall, 0)
            self.assertGreater(mono, 0)
            out = io.StringIO()
            export_csv(receiver.path, out)
            rows = list(csv.DictReader(io.StringIO(out.getvalue())))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]['battery_pct'], '87')
            self.assertEqual(rows[2]['tracking'], '3')
            self.assertEqual(rows[2]['flags'], '32')

    def test_rotation_retention_and_partial_tail(self):
        with TemporaryDirectory() as directory:
            receiver = NavLinkReceiver(directory, '127.0.0.1', 0,
                                       max_file_bytes=160, max_files=2)
            self.assertTrue(receiver.start())
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for _ in range(4):
                        sender.sendto(packet(), ('127.0.0.1', receiver.port))
                deadline = time.monotonic() + 3
                while receiver.received < 4 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(receiver.received, 4)
            finally:
                receiver.close()
            self.assertEqual(len(list(Path(directory).glob('*.bin'))), 2)
            with receiver.path.open('ab') as file:
                file.write(b'torn record')
            out = io.StringIO()
            with self.assertLogs(level='WARNING'):
                export_csv(receiver.path, out)
            self.assertEqual(len(list(csv.DictReader(io.StringIO(out.getvalue())))), 1)

    def test_bind_failure_and_disabled_config(self):
        self.assertIsNone(NavLinkReceiver.from_config(None))
        self.assertIsNone(NavLinkReceiver.from_config({'enabled': False}))
        with TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.1', 0))
            receiver = NavLinkReceiver(directory, '127.0.0.1', occupied.getsockname()[1])
            with self.assertLogs(level='WARNING'):
                self.assertFalse(receiver.start())
            receiver.close()

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'requires macOS Swift')
    def test_actual_swift_encoder_matches_python_byte_for_byte(self):
        root = Path(__file__).resolve().parents[3]
        encoder = root / 'ios-app/StarLock/StarLock/NavLinkPacket.swift'
        with TemporaryDirectory() as directory:
            main = Path(directory) / 'main.swift'
            main.write_text('''import Foundation
var p = NavLinkPacket()
p.session = 0x0102030405060708
p.sequence = 42
p.flags = 0x6f
p.tracking = 2
p.frameUS = 1000000
p.sendUS = 1010000
p.imuUS = 1009000
p.measurements = (1...14).map { Float($0) }
p.features = 321
p.imuSamples = 5
p.frameAgeUS = 10000
p.batteryPercent = 87
p.batteryState = 2
print(p.encoded().map { String(format: "%02x", $0) }.joined())
''')
            executable = str(Path(directory) / 'wire-check')
            subprocess.run(['swiftc', '-module-cache-path', str(Path(directory) / 'cache'),
                            str(encoder), str(main), '-o', executable],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([executable], check=True, capture_output=True, text=True)
            self.assertEqual(bytes.fromhex(result.stdout.strip()), packet())


if __name__ == '__main__':
    unittest.main()
