# @(#)roomberry_compass_test.py 3.1.compass.1 2026/10/31 12:10:00
"""Magnetic bearing wire, quality/freshness and ordered telemetry checks."""
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
from roomberry_navlink import COMPASS_PACKET, COMPASS_FIELDS, decode_packet, NavLinkReceiver, export_csv


def compass(**changes):
    r = dict(zip(COMPASS_FIELDS,[0]*len(COMPASS_FIELDS)))
    r.update(magic=b'NVLK',version=1,type=4,length=128,session=123,calibration=23,
             seq=42,flags=7,compass_state=2,send_us=1100000,compass_us=1000000,
             phone_magnetic_bearing_rad=math.pi/2,robot_magnetic_bearing_rad=math.pi,
             heading_accuracy_rad=math.radians(5),magnetic_x_ut=10,magnetic_y_ut=20,
             magnetic_z_ut=-30,magnetic_magnitude_ut=math.sqrt(1400),mount_yaw_rad=math.pi/2,
             compass_epoch_us=1650000000000000,padding=bytes(40))
    r.update(changes)
    return COMPASS_PACKET.pack(*(r[k] for k in COMPASS_FIELDS))


class CompassTest(unittest.TestCase):
    def test_validation(self):
        data=compass(); self.assertEqual(len(data),128)
        self.assertEqual(data[:8],b'NVLK\x01\x04\x80\x00'); self.assertEqual(decode_packet(data)[2],4)
        for change in (dict(session=0),dict(calibration=0),dict(flags=8),dict(flags=1),dict(reserved=1),
                       dict(padding=b'x'+bytes(39)),dict(compass_state=6),dict(compass_state=4),
                       dict(compass_us=1200000),dict(compass_us=0),dict(send_us=2000001),dict(compass_epoch_us=0),
                       dict(phone_magnetic_bearing_rad=math.nan),dict(robot_magnetic_bearing_rad=-1),
                       dict(heading_accuracy_rad=-1),dict(heading_accuracy_rad=math.radians(30)),
                       dict(magnetic_magnitude_ut=-1),dict(mount_yaw_rad=8)):
            with self.subTest(change=change),self.assertRaises(ValueError): decode_packet(compass(**change))
        decode_packet(compass(flags=2,compass_state=3,heading_accuracy_rad=-1))
        decode_packet(compass(flags=0,compass_state=4,send_us=3000000))
        decode_packet(compass(flags=0,compass_state=0,compass_us=0,compass_epoch_us=0))

    def test_ordering_and_session(self):
        r=NavLinkReceiver()
        def observe(**kw):
            r._observe(decode_packet(compass(**kw)),10)
            return r.latest_compass_observation()
        self.assertEqual(observe()['seq'],42)
        self.assertEqual(observe(seq=44)['seq'],44)
        self.assertEqual(observe(seq=43)['seq'],44)
        self.assertEqual(observe(seq=44)['seq'],44)
        self.assertEqual(observe(seq=45,flags=0,compass_state=4)['compass_state'],4)
        self.assertEqual(observe(session=99)['session'],99)
        self.assertEqual(observe(seq=100)['session'],99)
        self.assertIsNone(r.latest_observation()); self.assertIsNone(r.latest_ground_observation())
        self.assertIsNone(r.latest_health_observation())

    def test_mixed_udp_csv(self):
        from roomberry_navlink_test import packet
        from roomberry_groundhog_test import ground
        from roomberry_health_test import health
        with TemporaryDirectory() as directory:
            r=NavLinkReceiver(directory,'127.0.0.1',0)
            self.assertTrue(r.start())
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                    for data in (packet(),ground(),health(),compass()): sender.sendto(data,('127.0.0.1',r.port))
                deadline=time.monotonic()+3
                while r.received<4 and time.monotonic()<deadline: time.sleep(.01)
                self.assertEqual(r.received,4)
                self.assertEqual(r.latest_compass_observation()['seq'],42)
            finally: r.close()
            output=io.StringIO(); export_csv(r.path,output)
            rows=list(csv.DictReader(io.StringIO(output.getvalue())))
            self.assertEqual([x['type'] for x in rows],['1','2','3','4'])
            self.assertAlmostEqual(float(rows[3]['robot_magnetic_bearing_rad']),math.pi,places=6)
            self.assertNotIn('padding',rows[3])

    @unittest.skipUnless(sys.platform=='darwin' and shutil.which('swiftc'),'requires Swift')
    def test_swift_wire_and_heading_quality(self):
        source=Path(__file__).resolve().parents[3]/'ios-app/GroundHog/GroundHog/CompassPacket.swift'
        with TemporaryDirectory() as directory:
            main=Path(directory)/'main.swift'
            main.write_text('''import Foundation
import simd
var p = CompassPacket()
p.session = 123; p.calibration = 23; p.sequence = 42
p.update(magneticDegrees: 90,accuracyDegrees: 5,field: SIMD3(10,20,-30),sampleUS: 1000000,epochUS: 1650000000000000,mountYawDegrees: 90)
p.prepare(nowUS: 1100000)
assert(p.flags == 7 && p.state == 2)
print(p.encoded().map { String(format: "%02x", $0) }.joined())
assert(abs(CompassPacket.bearing(-90)-3*Double.pi/2) < 1e-8)
assert(abs(CompassPacket.bearing(370)-Double.pi/18) < 1e-8)
p.prepare(nowUS: 2000001); assert(p.flags == 0 && p.state == 4)
p.update(magneticDegrees: 350,accuracyDegrees: 5,field: SIMD3(10,20,-30),sampleUS: 2100000,epochUS: 1650000000100000,mountYawDegrees: 20)
p.prepare(nowUS: 2200000); assert(abs(Double(p.values[1])-Double.pi/18) < 1e-6)
p.update(magneticDegrees: 90,accuracyDegrees: -1,field: SIMD3(10,20,-30),sampleUS: 2300000,epochUS: 1650000000200000,mountYawDegrees: 0)
p.prepare(nowUS: 2400000); assert(p.flags == 2 && p.state == 3)
p.update(magneticDegrees: 90,accuracyDegrees: 30,field: SIMD3(10,20,-30),sampleUS: 2500000,epochUS: 1650000000300000,mountYawDegrees: 0)
p.prepare(nowUS: 2600000); assert(p.flags == 2 && p.state == 3)
p.update(magneticDegrees: .nan,accuracyDegrees: .nan,field: SIMD3(Double.nan,0,0),sampleUS: 2700000,epochUS: 1650000000400000,mountYawDegrees: 0)
p.prepare(nowUS: 2800000); assert(p.flags == 0 && p.state == 3 && p.values.allSatisfy { $0.isFinite })
p.fail(); p.prepare(nowUS: 3000000); assert(p.state == 5 && p.flags == 0 && p.sampleUS == 0)
''')
            exe=str(Path(directory)/'check')
            result=subprocess.run(['swiftc','-module-cache-path',str(Path(directory)/'cache'),str(source),str(main),'-o',exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(bytes.fromhex(result.stdout.strip()),compass())


if __name__=='__main__': unittest.main()
