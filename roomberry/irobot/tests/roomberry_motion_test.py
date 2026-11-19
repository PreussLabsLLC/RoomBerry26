# @(#)roomberry_motion_test.py 3.2.nudge.1 2026/11/12 18:01:48
import csv
import io
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from roomberry_motion import MOTION_PACKET, MOTION_FIELDS, decode_motion_packet, MotionComparison
from roomberry_navlink import NavLinkReceiver, decode_packet, packet_fields, export_csv, LOG_HEADER, LOG_MAGIC, RECEIPT


def wire(**changes):
    row=dict(zip(MOTION_FIELDS,(b'NVLK',1,7,128,42,1,1,2,0,1000000,1010000,
        0,0,0,1, 0,0,.5, 0,0,0, 0,0,-1, 1.25,10000,3,bytes(24))))
    row.update(changes)
    return MOTION_PACKET.pack(*(row[k] for k in MOTION_FIELDS))


class MotionWireTest(unittest.TestCase):
    def test_packet_roundtrip_and_existing_export(self):
        values=decode_packet(wire());self.assertEqual(packet_fields(values),MOTION_FIELDS)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'motion.bin'
            path.write_bytes(LOG_HEADER.pack(LOG_MAGIC,1,144,128)+RECEIPT.pack(123,456)+wire())
            out=io.StringIO();export_csv(path,out)
            r=list(csv.DictReader(io.StringIO(out.getvalue())))[0]
            self.assertEqual(r['type'],'7');self.assertEqual(r['integrated_yaw_rad'],'1.25')

    def test_invalid_values_and_stale_validity_are_rejected(self):
        for changes in [dict(flags=2),dict(motion_state=1),dict(sample_age_us=20),
            dict(send_us=1300000,sample_age_us=300000),dict(motion_qw=2),dict(gravity_z_g=0),
            dict(gyro_x_rad_s=float('nan')),dict(padding=b'x'+bytes(23)),dict(session=0)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):decode_motion_packet(wire(**changes))
        decode_motion_packet(wire(flags=0,motion_state=0,sample_us=0,sample_age_us=0xffffffff))

    def test_ordering_wrap_reset_and_retired_generation(self):
        receiver=NavLinkReceiver(logger=Mock())
        receiver._observe(decode_packet(wire(seq=0xffffffff)),10)
        receiver._observe(decode_packet(wire(seq=0)),10.1)
        self.assertEqual(receiver.latest_motion_observation()['seq'],0)
        receiver._observe(decode_packet(wire(seq=0xffffffff)),10.2)
        self.assertEqual(receiver.latest_motion_observation()['seq'],0)
        receiver._observe(decode_packet(wire(seq=1,motion_generation=4)),10.3)
        receiver._observe(decode_packet(wire(seq=2)),10.4)
        self.assertEqual(receiver.latest_motion_observation()['motion_generation'],4)
        self.assertIsNone(receiver.latest_trek_observation())


class MotionComparisonTest(unittest.TestCase):
    def setUp(self):
        self.receiver=Mock()
        self.m=dict(zip(MOTION_FIELDS,decode_motion_packet(wire())))
        self.m.update(frame_monotonic=10)
        self.ar=dict(session=42,frame_monotonic=10,frame_us=1000000,tracking=2,reason=0,
                     frame_age_us=0,qx=0,qy=math.sin(-math.pi/4),qz=0,qw=math.cos(-math.pi/4),map_uuid=bytes(16))
        self.receiver.latest_motion_observation.side_effect=lambda:dict(self.m)
        self.receiver.trek_history.side_effect=lambda:[dict(self.ar)]
        self.w=dict(ready=True,age=0,sensor_monotonic_s=10,angle=0,odometry_epoch=1)
        self.compare=MotionComparison(Mock())

    def test_common_baseline_and_signed_relative_turns(self):
        self.compare.update(self.receiver,self.w,10)
        self.m.update(seq=2,integrated_yaw_rad=1.75)
        self.w['angle']=math.degrees(.6)
        # Rotate mapped optical forward CCW by .4rad using a Z-world quaternion.
        a=.4/2; y=-math.pi/4
        self.ar.update(qx=-math.sin(a)*math.sin(y), qy=math.cos(a)*math.sin(y),
                       qz=math.sin(a)*math.cos(y),qw=math.cos(a)*math.cos(y))
        self.compare.update(self.receiver,self.w,10)
        r=self.compare.last
        self.assertAlmostEqual(r['gyro_turn_deg'],math.degrees(.5))
        self.assertAlmostEqual(r['wheel_minus_gyro_deg'],math.degrees(.1))
        self.assertAlmostEqual(r['ar_turn_deg'],math.degrees(.4))
        self.assertAlmostEqual(r['ar_minus_gyro_deg'],math.degrees(-.1))

    def test_unavailable_mismatched_and_stale_pairs_do_not_compare(self):
        self.m['session']=99
        self.compare.update(self.receiver,self.w,10);self.assertIsNone(self.compare.last)
        self.m['session']=42;self.w['sensor_monotonic_s']=9
        self.compare.update(self.receiver,self.w,10);self.assertIsNone(self.compare.last)
        self.w['sensor_monotonic_s']=10
        self.compare.update(self.receiver,self.w,11);self.assertIsNone(self.compare.last)
        self.ar['tracking']=1
        self.compare.update(self.receiver,self.w,10);self.assertIsNone(self.compare.last)

    def test_unavailable_ar_hides_recent_comparison(self):
        with patch('roomberry_motion.monotonic', return_value=10):
            self.compare.update(self.receiver,self.w,10)
            self.assertTrue(self.compare.snapshot()['fresh'])
            self.ar['tracking']=1
            self.compare.update(self.receiver,self.w,10)
            self.assertFalse(self.compare.snapshot()['fresh'])

    def test_generation_and_wheel_reset_start_new_baselines(self):
        self.compare.update(self.receiver,self.w,10)
        for key,target in [('motion_generation',self.m),('odometry_epoch',self.w)]:
            target[key]+=1;self.m['seq']+=1;self.m['integrated_yaw_rad']+=.5;self.w['angle']+=30
            self.compare.update(self.receiver,self.w,10)
            self.assertEqual(self.compare.last['gyro_turn_deg'],0)
            self.assertEqual(self.compare.last['wheel_turn_deg'],0)


class GyroNudgeTest(unittest.TestCase):
    def setUp(self):
        from roomberry_motion import GyroHeadingNudge
        self.nudge=GyroHeadingNudge(Mock())
        self.pose=dict(x_mm=100,y_mm=200,heading_rad=0.)
        self.w=dict(ready=True,age=0.,sensor_monotonic_s=10.,angle=0.,odometry_epoch=1)
        self.row=dict(session=42,motion_generation=1,flags=1,motion_state=2,seq=2,
                      sample_us=1000000,integrated_yaw_rad=.4,frame_monotonic=10.)
        self.history=[dict(self.row,frame_monotonic=t) for t in (9.9,10.)]
        self.receiver=Mock()
        self.receiver.latest_motion_observation.side_effect=lambda:dict(self.row)
        self.receiver.motion_history.side_effect=lambda:[dict(r) for r in self.history]
        self.assertTrue(self.nudge.bind(self.pose,self.w,self.receiver,1000.,now=10.,now_epoch=1000.))

    def advance(self, delta=.2):
        self.row['seq']+=1
        self.row['frame_monotonic']+=delta
        self.w['sensor_monotonic_s']=self.row['frame_monotonic']
        return self.row['frame_monotonic']

    def test_small_nudge_is_rate_limited_and_changes_only_local_heading(self):
        self.row['integrated_yaw_rad']+=math.radians(4)
        now=self.advance()
        step=self.nudge.update(self.pose,self.w,self.receiver,now)
        self.assertAlmostEqual(math.degrees(step),.2)
        self.assertEqual((self.pose['x_mm'],self.pose['y_mm'],self.w['angle']),(100,200,0))
        self.assertEqual(self.nudge.update(self.pose,self.w,self.receiver,now+.1),0)

    def test_total_budget_and_long_gap_never_accumulate_rate_budget(self):
        self.row['integrated_yaw_rad']+=math.radians(8)
        now=self.advance(10)
        self.assertLessEqual(abs(math.degrees(self.nudge.update(self.pose,self.w,self.receiver,now))),.250001)
        for _ in range(100):
            self.nudge.update(self.pose,self.w,self.receiver,self.advance())
        self.assertAlmostEqual(math.degrees(self.nudge.total),5)
        self.assertAlmostEqual(math.degrees(self.pose['heading_rad']),5)

    def test_stale_pair_and_large_innovation_do_not_nudge(self):
        self.row['integrated_yaw_rad']+=math.radians(4)
        self.assertEqual(self.nudge.update(self.pose,self.w,self.receiver,11),0)
        now=self.advance();self.w['sensor_monotonic_s']=now-.2
        self.assertEqual(self.nudge.update(self.pose,self.w,self.receiver,now),0)
        self.w['sensor_monotonic_s']=now;self.row['integrated_yaw_rad']+=math.radians(20)
        self.assertEqual(self.nudge.update(self.pose,self.w,self.receiver,now),0)
        self.assertEqual(self.nudge.state,'innovation_rejected')
        self.assertEqual(self.pose['heading_rad'],0)

    def test_session_generation_or_wheel_epoch_requires_a_new_tag(self):
        for target,key in [(self.row,'session'),(self.row,'motion_generation'),(self.w,'odometry_epoch')]:
            self.assertTrue(self.nudge.bind(self.pose,self.w,self.receiver,1000.,now=10.,now_epoch=1000.))
            target[key]+=1
            self.assertEqual(self.nudge.update(self.pose,self.w,self.receiver,10.),0)
            self.assertIsNone(self.nudge.anchor)
            self.assertEqual(self.nudge.state,'new_tag_fix_required')
            target[key]-=1

    def test_capture_pairing_and_moving_capture_rejection(self):
        self.row['integrated_yaw_rad']=1.
        self.assertTrue(self.nudge.bind(self.pose,self.w,self.receiver,1000.,now=10.,now_epoch=1000.))
        self.assertEqual(self.nudge.anchor['gyro'],.4) # Capture history, not delayed latest value.
        self.history[0]['integrated_yaw_rad']+=.1
        self.assertFalse(self.nudge.bind(self.pose,self.w,self.receiver,1000.,now=10.,now_epoch=1000.))
        self.assertEqual(self.nudge.state,'moving_during_tag_capture')

    def test_disable_and_invalid_limits(self):
        from roomberry_motion import GyroHeadingNudge
        disabled=GyroHeadingNudge(Mock(),dict(enabled=False))
        self.assertFalse(disabled.bind(self.pose,self.w,self.receiver,1000.,now=10.,now_epoch=1000.))
        self.assertEqual(disabled.update(self.pose,self.w,self.receiver,10.),0)
        for config in [dict(gain=2),dict(max_total_deg=90),dict(max_rate_deg_s=float('nan'))]:
            with self.assertRaises(ValueError):GyroHeadingNudge(Mock(),config)

    def test_wrap_boundary_takes_small_correction(self):
        self.nudge.anchor['heading']=math.pi-.01
        self.pose['heading_rad']=-math.pi+.01
        self.row['integrated_yaw_rad']+=.03
        step=self.nudge.update(self.pose,self.w,self.receiver,self.advance())
        self.assertGreater(step,0)
        self.assertLess(step,math.radians(.25))
