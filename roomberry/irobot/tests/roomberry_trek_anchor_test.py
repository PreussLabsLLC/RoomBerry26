"""Tag16 rigid frame alignment, mounting correction and invalidation."""
# @(#)roomberry_trek_anchor_test.py 3.2 2026/11/09 18:14:49
import math
import unittest
from unittest.mock import Mock
from roomberry_trek_anchor import TrekTagAnchor
from roomberry_navlink import NavLinkReceiver, decode_packet, TREK_PACKET


def row(t=10., seq=1, angle=0., **kwargs):
    result=dict(session=7,map_uuid=bytes(16),seq=seq,tracking=2,reason=0,frame_age_us=10000,
                frame_monotonic=t,frame_us=int(t*1e6),x_m=2.,y_m=3.,qx=0.,qy=0.,
                qz=math.sin(angle/2),qw=math.cos(angle/2),yaw_rad=-123.)
    result.update(kwargs)
    return result


def dashboard_row(t=10., seq=1, yaw_deg=20., pitch_deg=15., **kwargs):
    def multiply(a,b):
        x,y,z,w=a;X,Y,Z,W=b
        return (w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z)
    # Native camera +X right, +Y up, -Z optical forward. Build it looking
    # robot-forward, then tilt upward and yaw left in the mapped survey frame.
    yaw,pitch=math.radians(yaw_deg),math.radians(pitch_deg)
    base=(.5,-.5,-.5,.5)
    q=multiply((0,0,math.sin(yaw/2),math.cos(yaw/2)),multiply((0,-math.sin(pitch/2),0,math.cos(pitch/2)),base))
    return row(t=t,seq=seq,qx=q[0],qy=q[1],qz=q[2],qw=q[3],yaw_rad=yaw,**kwargs)


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.receiver=Mock()
        self.receiver.trek_history.return_value=[row(t=9.9,seq=1),row(t=10.,seq=2),row(t=10.1,seq=3)]
        self.anchor=TrekTagAnchor(self.receiver,Mock(),mount_yaw_deg=-90,lens_x_mm=-145,lens_y_mm=-22,heading_basis='camera_y',mount_pitch_deg=0)
        self.pose=dict(x_mm=1000.,y_mm=2000.,heading_rad=math.pi/2)

    def bind(self):
        self.assertTrue(self.anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.,wheel_state=dict(distance=0.,angle=0.)))

    def test_stationary_capture_pair_uses_capture_not_processing_time(self):
        self.bind()
        self.assertEqual(self.anchor.anchor['phone_frame_us'],10000000)
        result=self.anchor.transform(row())
        self.assertAlmostEqual(result['x_mm'],1000.)
        self.assertAlmostEqual(result['y_mm'],2000.)
        self.assertAlmostEqual(result['heading_rad'],math.pi/2)

    def test_loaded_map_needs_relocalization_before_tag16_binding(self):
        history=[row(t=9.9,seq=1,map_uuid=b'x'*16,flags=0,relocalization=1),
                 row(t=10.,seq=2,map_uuid=b'x'*16,flags=0,relocalization=1),
                 row(t=10.1,seq=3,map_uuid=b'x'*16,flags=0,relocalization=1)]
        self.receiver.trek_history.return_value=history
        self.assertFalse(self.anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.))
        for sample in history:sample.update(flags=1,relocalization=2)
        self.assertTrue(self.anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.))

    def test_rigid_room_translation_no_scale_fit(self):
        self.bind()
        result=self.anchor.transform(row(x_m=3.))
        self.assertAlmostEqual(result['x_mm'],1000.)
        self.assertAlmostEqual(result['y_mm'],3000.)
        self.assertEqual(self.anchor.anchor['scale'],1.)

    def test_pivot_compensates_camera_lens_arc(self):
        self.bind()
        result=self.anchor.transform(row(x_m=2.167,y_m=2.877,angle=math.pi/2))
        self.assertAlmostEqual(result['x_mm'],1000.)
        self.assertAlmostEqual(result['y_mm'],2000.)
        self.assertAlmostEqual(abs(result['heading_rad']),math.pi)

    def test_independent_disagreement_preserved_and_deduplicated(self):
        self.bind();before=dict(self.anchor.anchor)
        self.receiver.latest_trek_observation.return_value=row(t=11.,seq=4,x_m=3.)
        result=self.anchor.compare(dict(odometry_epoch=4,sensor_monotonic_s=11.,distance=0.,angle=0.),now=11.1)
        self.assertAlmostEqual(result['separation_mm'],1000.)
        self.assertEqual(self.anchor.anchor,before)
        self.assertIsNone(self.anchor.compare(dict(odometry_epoch=4,distance=0.,angle=0.),now=11.1))
        self.assertFalse(self.anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.))

    def test_session_map_or_wheel_reset_permanently_invalidates(self):
        for field,value in [('session',8),('map_uuid',b'x'*16),('epoch',5)]:
            self.setUp();self.bind()
            self.receiver.latest_trek_observation.return_value=row(t=11.,seq=4,**({field:value} if field!='epoch' else {}))
            state=dict(odometry_epoch=value if field=='epoch' else 4,distance=0.,angle=0.)
            self.assertIsNone(self.anchor.compare(state,now=11.1))
            self.assertEqual(self.anchor.state,'invalidated')
            self.receiver.latest_trek_observation.return_value=row(t=11.,seq=5)
            self.assertIsNone(self.anchor.compare(dict(odometry_epoch=4,distance=0.,angle=0.),now=11.1))

    def test_stale_tracking_gap_rejects_without_rebinding(self):
        self.bind();before=dict(self.anchor.anchor)
        self.receiver.latest_trek_observation.return_value=row(t=11.,seq=4)
        self.assertIsNone(self.anchor.compare(dict(odometry_epoch=4,distance=0.,angle=0.),now=12.))
        self.assertEqual(self.anchor.anchor,before)
        self.assertIsNotNone(self.anchor.compare(dict(odometry_epoch=4,distance=0.,angle=0.),now=11.1))

    def test_bad_geometry_motion_and_missing_capture_history_fail_binding(self):
        for history in ([row(t=15.)], [row(t=10.)],
                        [row(t=9.9),row(t=10.),row(t=10.1,x_m=2.1)],
                        [row(t=9.9,tracking=1),row(t=10.,tracking=1),row(t=10.1,tracking=1)]):
            self.setUp();self.receiver.trek_history.return_value=history
            self.assertFalse(self.anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.))
            self.assertIsNone(self.anchor.anchor)
        with self.assertRaises(ValueError):TrekTagAnchor.camera_y_heading(row(qw=0,qz=0))
        with self.assertRaises(ValueError):TrekTagAnchor.camera_y_heading(row(qx=2**-.5,qw=2**-.5))

    def test_type6_history_order_clock_rebase_and_session_retirement(self):
        receiver=NavLinkReceiver()
        def packet(seq,session=7):
            return TREK_PACKET.pack(b'NVLK',1,6,128,session,seq,0,2,0,
                                    10000000+seq*100000,10010000+seq*100000,bytes(16),
                                    2,3,0,0,0,0,1,0,10000,3,0,0,bytes(32))
        receiver._observe(decode_packet(packet(1)),100.2)
        receiver._observe(decode_packet(packet(2)),100.25)
        receiver._observe(decode_packet(packet(1)),100.3)
        history=receiver.trek_history()
        self.assertEqual([r['seq'] for r in history],[1,2])
        self.assertAlmostEqual(history[-1]['frame_monotonic'],100.24)
        receiver._observe(decode_packet(packet(0,session=8)),101.)
        receiver._observe(decode_packet(packet(3,session=7)),101.1)
        self.assertEqual(receiver.latest_trek_observation()['session'],8)
        self.assertEqual(len(receiver.trek_history()),1)
        self.assertIsNone(receiver.latest_observation())  # no legacy fusion

    def test_qualified_wall_anchor_binds_capture_and_diagnostic_failure_does_not_stop_run(self):
        import roomberry_wall_test
        fixture=roomberry_wall_test.WallTest();fixture.setUp()
        phone=Mock();phone.state='waiting_for_tag16';phone.last_result=None
        fixture.w.phone_anchor=phone
        fixture.anchor()
        args=phone.bind.call_args
        self.assertEqual(args.args[1],fixture.w._wall_time+2)
        self.assertEqual(args.args[2],1)
        self.assertEqual(args.kwargs['wheel_state']['distance'],fixture.state['distance'])
        phone.compare.side_effect=RuntimeError('diagnostic failure')
        fixture.tick()
        self.assertIsNone(fixture.w.phone_anchor)
        self.assertEqual(fixture.m._mode,'wall')

    def test_wheel_trace_does_not_follow_mutations_of_original_tag_pose(self):
        self.bind()
        self.pose['x_mm']=99999
        self.receiver.latest_trek_observation.return_value=row(t=11.,seq=4)
        result=self.anchor.compare(dict(odometry_epoch=4,distance=100.,angle=0.),now=11.1)
        self.assertAlmostEqual(result['wheel_pose']['x_mm'],1000.)
        self.assertAlmostEqual(result['wheel_pose']['y_mm'],2100.)
        self.assertAlmostEqual(result['separation_mm'],100.)

    def test_dashboard_mount_heading_position_and_pivot(self):
        receiver=Mock()
        receiver.trek_history.return_value=[dashboard_row(t=9.9),dashboard_row(t=10.),dashboard_row(t=10.1)]
        anchor=TrekTagAnchor(receiver,Mock())
        self.assertTrue(anchor.bind(self.pose,100.,4,now_epoch=105.,now_monotonic=15.))
        self.assertEqual(anchor.anchor['heading_basis'],'optical_forward')
        self.assertEqual(anchor.anchor['lens_offset_mm'],[10.,180.])
        self.assertAlmostEqual(anchor.anchor['mount_pitch_rad'],math.radians(15))
        self.assertAlmostEqual(anchor.anchor['rotation_rad'],math.pi/2)
        initial=anchor.transform(dashboard_row())
        self.assertAlmostEqual(initial['x_mm'],1000.)
        self.assertAlmostEqual(initial['y_mm'],2000.)
        self.assertAlmostEqual(initial['heading_rad'],math.pi/2)
        # Left pivot: lens arc from(+10,+180)mm must disappear at body centre.
        # At room heading north, camera=(820,2010); west =>(990,1820).
        pivot=anchor.transform(dashboard_row(yaw_deg=110,x_m=1.810,y_m=2.830))
        self.assertAlmostEqual(pivot['x_mm'],1000.)
        self.assertAlmostEqual(pivot['y_mm'],2000.)
        self.assertAlmostEqual(abs(pivot['heading_rad']),math.pi)

    def test_optical_yaw_uses_horizontal_projection_with_upward_pitch(self):
        for pitch in (0,15,35):
            sample=dashboard_row(pitch_deg=pitch)
            heading=TrekTagAnchor.axis_heading(sample,'optical_forward')
            self.assertAlmostEqual(math.degrees(heading),20.)
            self.assertTrue(TrekTagAnchor.usable(sample))
        with self.assertRaises(ValueError):
            TrekTagAnchor.axis_heading(dashboard_row(pitch_deg=90),'optical_forward')

    def test_legacy_record_transform_uses_its_original_basis_and_offset(self):
        self.bind()
        self.anchor.anchor['heading_basis']='quaternion camera +Y plus mount yaw'
        original=self.anchor.transform(row())
        self.assertAlmostEqual(original['x_mm'],1000.)
        self.assertAlmostEqual(original['y_mm'],2000.)


if __name__=='__main__': unittest.main()
