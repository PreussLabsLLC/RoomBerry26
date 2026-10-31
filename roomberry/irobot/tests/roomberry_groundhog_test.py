# @(#)roomberry_groundhog_test.py 3.1 2026/10/31 11:30:00
"""Cross-language wire, packet loss, continuity, and floor geometry checks."""
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

from roomberry_navlink import (GROUND_PACKET, GROUND_FIELDS, NavLinkReceiver,
                               decode_packet, export_csv)


def ground(**changes):
    row = dict(zip(GROUND_FIELDS, [0]*len(GROUND_FIELDS)))
    row.update(magic=b'NVLK', version=1, type=2, length=128,
               session=0x0102030405060708, calibration=23, seq=42,
               flags=7, tracking=2, reason=0, start_us=1000000,
               end_us=1033333, send_us=1040000, continuity=3,
               accepted_frames=100, rejected_frames=2,
               segment_x_mm=100, segment_y_mm=200, segment_yaw_rad=0,
               delta_forward_mm=3, delta_left_mm=4, delta_yaw_rad=.01,
               residual_mm=.25, height_mm=200, path_mm=300, valid_seconds=4,
               forward_mm_s=90, left_mm_s=120, inliers=40, candidates=50,
               battery_pct=87, battery_state=2, processing_us=5000)
    row.update(changes)
    return GROUND_PACKET.pack(*(row[k] for k in GROUND_FIELDS))


class GroundHogTest(unittest.TestCase):
    def test_validation(self):
        data = ground()
        self.assertEqual(len(data), 128)
        self.assertEqual(data[:8], b'NVLK\x01\x02\x80\x00')
        self.assertEqual(decode_packet(data)[2], 2)
        self.assertEqual(struct.unpack_from('<f', data, 68)[0], 100)
        for change in (dict(session=0), dict(calibration=0), dict(flags=8),
                       dict(flags=1), dict(flags=4), dict(start_us=0),
                       dict(end_us=999999), dict(send_us=1000000),
                       dict(send_us=2000000), dict(segment_x_mm=math.nan),
                       dict(residual_mm=-1), dict(inliers=51), dict(inliers=2),
                       dict(battery_pct=254), dict(battery_state=4), dict(reserved=1)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_packet(ground(**change))
        decode_packet(ground(flags=2, tracking=1, reason=7))

    def test_loss_recovery_duplicate_order_and_segment_break(self):
        r = NavLinkReceiver()
        def observe(**kw):
            r._observe(decode_packet(ground(**kw)), 10)
            return r.latest_ground_observation()
        self.assertIsNone(observe()['recovered_delta'])
        # Missing UDP sequence 43 is recovered from cumulative transform.
        row = observe(seq=44, end_us=1100000, start_us=1066667, send_us=1110000,
                      accepted_frames=102, segment_x_mm=110, segment_y_mm=220)
        self.assertEqual(row['recovered_delta'], (10,20,0))
        observe(seq=43, segment_x_mm=999)
        self.assertEqual(r.latest_ground_observation()['seq'],44)
        # New emission of the same captured frame contributes no motion.
        self.assertIsNone(observe(seq=45,end_us=1100000,start_us=1066667,send_us=1111000,
                                  accepted_frames=102,segment_x_mm=110,segment_y_mm=220)['recovered_delta'])
        self.assertIsNone(observe(seq=46,continuity=4,segment_x_mm=1)['recovered_delta'])
        self.assertIsNone(observe(seq=47,flags=2,tracking=1,reason=7)['recovered_delta'])
        self.assertIsNone(observe(seq=48,continuity=5)['recovered_delta'])
        self.assertIsNone(r.latest_observation())  # never enters AR pose aiding
        self.assertIsNone(observe(session=99)['recovered_delta'])
        observe(seq=100,session=0x0102030405060708)
        self.assertEqual(r.latest_ground_observation()['session'],99)

    def test_rotated_recovery(self):
        r = NavLinkReceiver()
        r._observe(decode_packet(ground(segment_yaw_rad=math.pi/2)),10)
        r._observe(decode_packet(ground(seq=43,start_us=1033333,end_us=1066666,
                   send_us=1070000,accepted_frames=101,segment_yaw_rad=math.pi/2,
                   segment_x_mm=100,segment_y_mm=210)),10.1)
        delta = r.latest_ground_observation()['recovered_delta']
        self.assertAlmostEqual(delta[0],10,places=5)
        self.assertAlmostEqual(delta[1],0,places=5)

    def test_udp_log_and_mixed_csv(self):
        from roomberry_navlink_test import packet
        with TemporaryDirectory() as directory:
            r = NavLinkReceiver(directory, '127.0.0.1',0)
            self.assertTrue(r.start())
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                    for data in (packet(),ground(),ground(seq=43,flags=2,tracking=1,reason=7)):
                        sender.sendto(data,('127.0.0.1',r.port))
                deadline=time.monotonic()+3
                while r.received < 3 and time.monotonic()<deadline: time.sleep(.01)
                self.assertEqual(r.received,3)
                self.assertEqual(r.latest_observation()['type'],1)
                self.assertEqual(r.latest_ground_observation()['type'],2)
            finally: r.close()
            out=io.StringIO(); export_csv(r.path,out)
            rows=list(csv.DictReader(io.StringIO(out.getvalue())))
            self.assertEqual([x['type'] for x in rows],['1','2','2'])
            self.assertEqual(rows[1]['segment_x_mm'],'100.0')
            self.assertEqual(rows[0]['segment_x_mm'],'')
            self.assertEqual(rows[2]['reason'],'7')

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'requires macOS Vision')
    def test_actual_vision_flow_direction(self):
        source = Path(__file__).resolve().parents[3]/'ios-app/GroundHog/tests/OpticalFlowCheck.swift'
        with TemporaryDirectory() as directory:
            executable = str(Path(directory)/'vision-check')
            result = subprocess.run(['swiftc','-module-cache-path',str(Path(directory)/'cache'),
                                     str(source),'-o',executable],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result = subprocess.run([executable],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('direction verified',result.stdout)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'requires macOS Swift')
    def test_swift_wire_and_geometry(self):
        source=Path(__file__).resolve().parents[3]/'ios-app/GroundHog/GroundHog/GroundMotion.swift'
        with TemporaryDirectory() as directory:
            main=Path(directory)/'main.swift'
            main.write_text('''import Foundation
import simd
var p = GroundPacket()
p.session = 0x0102030405060708; p.calibration = 23; p.sequence = 42
p.flags = 7; p.state = 2; p.reason = 0
p.startUS = 1000000; p.endUS = 1033333; p.sendUS = 1040000
p.continuity = 3; p.accepted = 100; p.rejected = 2
p.values = [100,200,0,3,4,0.01,0.25,200,300,4,90,120]
p.inliers = 40; p.candidates = 50; p.battery = 87; p.batteryState = 2; p.processingUS = 5000
print(p.encoded().map { String(format: "%02x", $0) }.joined())
var mount = MountCalibration(heightMM: 200,yawDegrees: 0,lensForwardMM: -145,lensLeftMM: -22,identity: 23)
let r = SIMD2(mount.lensForwardMM,mount.lensLeftMM)
let yaw = 0.2
let arc = PlanarTransform.rotate(r,yaw)-r
assert(simd_length(PlanarTransform.centerDelta(camera: arc,yaw: yaw,mount: mount)) < 1e-9)
assert(simd_length(mount.robot(SIMD2(0,10))-SIMD2(10,0)) < 1e-9)
var t = PlanarTransform(); t.append(SIMD2(100,0),yaw: .pi/2); t.append(SIMD2(100,0),yaw: 0)
assert(simd_length(t.position-SIMD2(100,100)) < 1e-8)
let k = simd_double3x3(columns: (SIMD3(400,0,0),SIMD3(0,400,0),SIMD3(240,320,1)))
let a = FloorGeometry.point(pixel: SIMD2(240,320),intrinsics: k,gravity: SIMD3(0,0,-1),height: 200)!
let b = FloorGeometry.point(pixel: SIMD2(260,320),intrinsics: k,gravity: SIMD3(0,0,-1),height: 200)!
assert(simd_length(a) < 1e-8 && abs(b.x-10) < 1e-8)
assert(FloorGeometry.point(pixel: SIMD2(240,320),intrinsics: k,gravity: SIMD3(0,0,1),height: 200) == nil)
let candidates = (0..<40).map { _ in SIMD2<Double>(3,4) } + (0..<8).map { _ in SIMD2<Double>(100,100) }
let fit = FloorGeometry.fit(candidates)!
assert(fit.inliers == 40 && simd_length(fit.delta-SIMD2(3,4)) < 1e-8)
assert(FloorGeometry.fit(Array(candidates.prefix(10))) == nil)
''')
            exe=str(Path(directory)/'check')
            result=subprocess.run(['swiftc','-module-cache-path',str(Path(directory)/'cache'),str(source),str(main),'-o',exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(bytes.fromhex(result.stdout.strip()),ground())


if __name__ == '__main__': unittest.main()
