# @(#)roomberry_health_test.py 3.1.health.1 2026/10/31 12:00:00
"""Health wire compatibility, retained impact counters, and detector behavior."""
import csv
import io
import math
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from roomberry_navlink import HEALTH_PACKET, HEALTH_FIELDS, decode_packet, NavLinkReceiver, export_csv


def health(**changes):
    r = dict(zip(HEALTH_FIELDS, [0]*len(HEALTH_FIELDS)))
    r.update(magic=b'NVLK', version=1, type=3, length=128,
             session=0x0102030405060708,calibration=23,seq=42,flags=127,
             thermal_state=1,battery_state=2,send_us=1040000,imu_us=1030000,
             bump_us=1020000,bump_count=3,imu_samples=10,battery_pct=87,
             app_footprint_bytes=123456789,image_width=480,image_height=640,resource_age_ms=250)
    for key,value in zip(HEALTH_FIELDS[17:29],range(1,13)): r[key]=float(value)
    r.update(changes)
    return HEALTH_PACKET.pack(*(r[k] for k in HEALTH_FIELDS))


class HealthTest(unittest.TestCase):
    def test_validation(self):
        data=health(); self.assertEqual(len(data),128)
        self.assertEqual(data[:8],b'NVLK\x01\x03\x80\x00')
        self.assertEqual(decode_packet(data)[2],3)
        for change in (dict(session=0),dict(calibration=0),dict(flags=128),dict(reserved=1),
                       dict(thermal_state=4),dict(battery_state=4),dict(battery_pct=101),
                       dict(battery_pct=255),dict(imu_us=1050000),dict(imu_us=1),
                       dict(bump_us=1050000),dict(bump_count=0),dict(bump_us=0),
                       dict(last_bump_peak_mm_s2=0),dict(imu_samples=0),
                       dict(app_cpu_pct=math.nan),dict(app_cpu_pct=-1),dict(resource_age_ms=2001),
                       dict(image_width=0),dict(image_height=9000)):
            with self.subTest(change=change),self.assertRaises(ValueError): decode_packet(health(**change))
        # Unavailable fields must carry clear validity; sensor history may be stale.
        decode_packet(health(flags=0,imu_us=0,imu_samples=0,battery_pct=255,
                             bump_count=0,bump_us=0,last_bump_peak_mm_s2=0,
                             image_width=0,image_height=0,resource_age_ms=0xffffffff))
        decode_packet(health(app_cpu_pct=180))  # percent of one CPU core

    def test_cumulative_bumps_and_ordering(self):
        r=NavLinkReceiver()
        def observe(**kw):
            r._observe(decode_packet(health(**kw)),10)
            return r.latest_health_observation()
        self.assertEqual(observe()['new_bumps'],0)
        self.assertEqual(observe(seq=45,bump_count=5)['new_bumps'],2)  # lost event datagrams
        observe(seq=44,bump_count=4)
        self.assertEqual(r.latest_health_observation()['seq'],45)
        observe(seq=45,bump_count=5)
        self.assertEqual(r.latest_health_observation()['seq'],45)
        self.assertEqual(observe(seq=46,bump_count=5)['new_bumps'],0)
        observe(seq=47,bump_count=4)  # a decreasing cumulative counter is invalid
        self.assertEqual(r.latest_health_observation()['seq'],46)
        self.assertEqual(observe(session=99,bump_count=3)['new_bumps'],0)
        observe(seq=100)
        self.assertEqual(r.latest_health_observation()['session'],99)
        self.assertIsNone(r.latest_observation()); self.assertIsNone(r.latest_ground_observation())

    def test_mixed_udp_and_csv(self):
        from roomberry_navlink_test import packet
        from roomberry_groundhog_test import ground
        with TemporaryDirectory() as directory:
            receiver=NavLinkReceiver(directory,'127.0.0.1',0)
            self.assertTrue(receiver.start())
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                    for data in (packet(),ground(),health(),health(seq=43,bump_count=4)):
                        sender.sendto(data,('127.0.0.1',receiver.port))
                deadline=time.monotonic()+3
                while receiver.received<4 and time.monotonic()<deadline: time.sleep(.01)
                self.assertEqual(receiver.received,4)
                self.assertEqual(receiver.latest_health_observation()['new_bumps'],1)
            finally: receiver.close()
            output=io.StringIO(); export_csv(receiver.path,output)
            rows=list(csv.DictReader(io.StringIO(output.getvalue())))
            self.assertEqual([r['type'] for r in rows],['1','2','3','3'])
            self.assertEqual(rows[2]['app_footprint_bytes'],'123456789')
            self.assertEqual(rows[2]['image_width'],'480')
            self.assertEqual(rows[3]['bump_count'],'4')

    @unittest.skipUnless(sys.platform=='darwin' and shutil.which('swiftc'),'requires Swift/Darwin')
    def test_swift_wire_detector_and_resource_counters(self):
        source=Path(__file__).resolve().parents[3]/'ios-app/GroundHog/GroundHog'
        with TemporaryDirectory() as directory:
            main=Path(directory)/'main.swift'
            main.write_text('''import Foundation
import simd
import Darwin
var p = HealthPacket()
p.session = 0x0102030405060708; p.calibration = 23; p.sequence = 42; p.flags = 127
p.thermal = 1; p.batteryState = 2; p.sendUS = 1040000; p.imuUS = 1030000
p.bumpUS = 1020000; p.bumps = 3; p.samples = 10; p.battery = 87
p.values = (1...12).map { Float($0) }; p.footprintBytes = 123456789
p.width = 480; p.height = 640; p.resourceAgeMS = 250
print(p.encoded().map { String(format: "%02x", $0) }.joined())
var detector = BumpDetector()
for i in 0...40 { assert(!detector.sample(time: 1+Double(i)*0.01,acceleration: SIMD3(0.08,0,0))) }
assert(detector.sample(time: 1.41,acceleration: SIMD3(0.8,0,0)))
assert(!detector.sample(time: 1.42,acceleration: SIMD3(1.6,0,0)))
assert(detector.count == 1 && detector.lastPeakG == 1.6)
for i in 43...90 { assert(!detector.sample(time: 1+Double(i)*0.01,acceleration: SIMD3(0,0,0))) }
assert(detector.sample(time: 1.91,acceleration: SIMD3(0,0.8,0)))
assert(detector.count == 2)
assert(!detector.sample(time: 1.90,acceleration: SIMD3(0,2,0))) // reordered IMU
assert(!detector.sample(time: 3.0,acceleration: SIMD3(0,2,0))) // gap
assert(!detector.sample(time: .nan,acceleration: SIMD3(0,0,0)))
var smooth = BumpDetector()
for i in 0...200 { assert(!smooth.sample(time: 1+Double(i)*0.01,acceleration: SIMD3(Double(i)*0.002,0,0))) }
assert(smooth.count == 0) // smooth acceleration / centrifugal load
var metrics = ProcessMetrics()
let initial = metrics.read()
assert(initial.cpu == nil && (initial.footprint ?? 0) > 0)
let began = ProcessInfo.processInfo.systemUptime
var sum = 0.0
while ProcessInfo.processInfo.systemUptime-began < 0.2 { sum += sin(sum+1) }
let busy = metrics.read()
assert((busy.cpu ?? 0) > 10 && (busy.footprint ?? 0) > 0)
assert(sum.isFinite)
''')
            exe=str(Path(directory)/'check')
            result=subprocess.run(['swiftc','-module-cache-path',str(Path(directory)/'cache'),
                                   str(source/'HealthPacket.swift'),str(source/'ProcessMetrics.swift'),str(main),'-o',exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(bytes.fromhex(result.stdout.strip()),health())


if __name__=='__main__': unittest.main()
