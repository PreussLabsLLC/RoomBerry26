# @(#)roomberry_calibration_test.py 3.1.web.1 2026/10/31 14:00:00
"""Cal drive sequence, independent estimates, scan boundaries and failure stops."""
import logging
from copy import deepcopy
from math import pi
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from roomberry_mission import RoomberryMission, MODE_CALIBRATION
from roomberry_control import RobotCommandArbiter


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        for target in ('roomberry_calibration.monotonic','roomberry_mission.monotonic'):
            p=patch(target,side_effect=lambda: self.now); p.start(); self.addCleanup(p.stop)
        for target in ('roomberry_calibration.time','roomberry_mission.time'):
            p=patch(target,side_effect=lambda: 1700000000+self.now); p.start(); self.addCleanup(p.stop)
        self.robot=Mock(); self.robot.consume_clock_button_press.return_value=False
        self.robot.consume_schedule_button_press.return_value=False
        bumps=SimpleNamespace(bump_left=False,bump_right=False,wheel_drop_left=False,wheel_drop_right=False)
        sensors=SimpleNamespace(bumps_and_wheel_drops=bumps,cliff_left_sensor=False,
            cliff_front_left_sensor=False,cliff_front_right_sensor=False,cliff_right_sensor=False,
            light_bumper=SimpleNamespace(left=False,front_left=False,center_left=False,
                                        center_right=False,front_right=False,right=False))
        self.state=dict(ready=True,age=0,sensors=sensors,distance=0,angle=0,odometry_epoch=1,
                        battery_status='normal',clock_button=False,schedule_button=False)
        self.robot.snapshot.return_value=self.state
        self.camera=Mock(); self.camera.last_detection_time=None
        self.navigation=Mock(); self.navigation.robot_radius_mm=174
        self.localizer=Mock()
        self.m=RoomberryMission(self.robot,self.camera,Mock(),self.navigation,self.localizer,
            logging.getLogger('CalibrationTest'),landmarks=[dict(id=15,world_from_tag=
                [[0,0,1,7.73],[-1,0,0,1.18],[0,-1,0,.16],[0,0,0,1]])])
        self.ground=dict(session=11,calibration=22,continuity=0,flags=7,seq=1,
            received_monotonic=self.now,send_us=1000000,end_us=1000000,
            segment_x_mm=0,segment_y_mm=0,segment_yaw_rad=0)
        self.health=dict(session=11,calibration=22,bump_count=0,received_monotonic=self.now)
        self.m.navlink=SimpleNamespace(latest_ground_observation=lambda: self.ground,
                                     latest_health_observation=lambda: self.health)
        self.m.set_mode(MODE_CALIBRATION)
        self.c=self.m.calibration

    def pose(self,dx=0,heading=0):
        return dict(x_mm=7430+dx,y_mm=1180,heading_rad=heading,localized=True,
                    accepted_tag_ids=(('tag16h5',15),),rejected_tags=())

    def tick(self,delta=0,pose=None,new=False,heading_delta=0,phone_scale=1):
        self.now += .2
        self.state['distance'] += delta; self.state['angle'] += heading_delta
        self.ground.update(received_monotonic=self.now,seq=self.ground['seq']+1,
            send_us=int(self.now*1e6),end_us=int(self.now*1e6),
            segment_x_mm=self.state['distance']*phone_scale)
        self.health['received_monotonic']=self.now
        self.c.tick(self.state,pose,new,1700000000+self.now if new else None)

    def start(self):
        self.tick()
        self.camera.request_scan.assert_called_once()
        self.tick(pose=self.pose(),new=True)
        self.assertEqual(self.c.stage,'reverse')

    def move_to(self,target,phone_scale=1):
        direction=1 if target>self.state['distance'] else -1
        while abs(target-self.state['distance'])>.01:
            self.tick(delta=direction*min(10,abs(target-self.state['distance'])),phone_scale=phone_scale)
            self.assertEqual(self.m._mode,MODE_CALIBRATION)

    def scan(self,pose=None,phone_scale=1):
        self.tick(phone_scale=phone_scale)  # request after the stop
        self.tick(pose=pose,new=True,phone_scale=phone_scale)

    def return_to_start(self):
        self.start()
        for step in (1,2,3):
            self.move_to(-500*step)
            self.scan(self.pose(-500*step) if step<3 else None)
        self.move_to(0)
        self.scan(self.pose())
        self.assertEqual(self.c.stage,'contact')

    def test_full_sequence_missing_far_tag_return_scan_and_gentle_contact(self):
        self.return_to_start()
        self.assertEqual([r['checkpoint'] for r in self.c.records],
                         ['start','reverse_1','reverse_2','reverse_3','return'])
        self.assertIsNone(self.c.records[3]['tag_pose'])
        self.assertAlmostEqual(self.c.records[3]['wheels_pose']['x_mm'],5930)
        self.assertAlmostEqual(self.c.records[3]['iphone_pose']['x_mm'],5930)
        self.assertEqual(self.camera.request_scan.call_count,5)
        self.move_to(120)
        self.state['sensors'].bumps_and_wheel_drops.bump_left=True
        self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertEqual(self.c.result['status'],'complete')
        self.assertEqual(self.c.records[-1]['checkpoint'],'contact')
        self.assertTrue(self.c.records[-1]['bumper']['left'])
        self.assertFalse(any(c.args[0] in ('spin_left','spin_right','seek_dock')
                             for c in self.robot.execute.call_args_list))
        velocities=[dict(c.kwargs) for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertTrue(any(v['left_velocity']<0 for v in velocities))
        self.assertTrue(any(v['left_velocity']>0 for v in velocities))
        self.assertLessEqual(max(max(abs(v['left_velocity']),abs(v['right_velocity'])) for v in velocities),50)

    def test_estimates_do_not_reset_wheels_at_each_tag_fix(self):
        self.start(); self.move_to(-500,phone_scale=.96)
        self.scan(self.pose(-480),phone_scale=.96)
        record=self.c.records[-1]
        self.assertAlmostEqual(record['wheels_pose']['x_mm'],6930)
        self.assertAlmostEqual(record['iphone_pose']['x_mm'],6950)
        self.assertAlmostEqual(record['wheels_minus_tag']['dx_mm'],-20)
        self.move_to(-1000,phone_scale=.96)
        self.scan(self.pose(-960),phone_scale=.96)
        self.assertAlmostEqual(self.c.records[-1]['wheels_minus_tag']['dx_mm'],-40)

    def test_missing_initial_tag_and_wrong_heading_never_move(self):
        for pose in (None,self.pose(heading=pi/2)):
            self.m.set_mode(MODE_CALIBRATION); self.c=self.m.calibration
            self.tick(); self.tick(pose=pose,new=True)
            self.assertEqual(self.m._mode,'idle')
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))

    def test_phone_segment_rotation_is_removed_at_initial_anchor(self):
        self.ground['segment_yaw_rad']=pi/2
        self.start()
        self.ground.update(segment_x_mm=0,segment_y_mm=-500)
        phone, reason=self.c._phone_pose()
        self.assertIsNone(reason)
        self.assertAlmostEqual(phone['x_mm'],6930)
        self.assertAlmostEqual(phone['y_mm'],1180)
        self.assertAlmostEqual(phone['heading_rad'],0)

    def test_wrong_way_motion_aborts(self):
        self.start(); self.tick(delta=5)
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('opposite',self.c.result['reason'])

    def test_motion_stage_timeout_aborts(self):
        self.start(); self.c.deadline=self.now-1; self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('timeout',self.c.result['reason'])

    def test_scan_guard_exception_stops_without_losing_mission_thread(self):
        self.m._scan_active=True
        self.c.guard=Mock(side_effect=RuntimeError('receiver failure'))
        self.m._shutdown=Mock(); self.m._shutdown.is_set.side_effect=[False,True]
        self.m._run()
        self.assertEqual(self.m._mode,'idle')
        self.assertEqual(self.c.result['reason'],'mission update error')

    def test_stationary_scan_poll_delay_preserves_result_until_fresh_sensors(self):
        self.tick()  # request scan
        self.state['age']=.583
        self.tick(pose=self.pose(),new=True)
        self.assertEqual(self.m._mode,MODE_CALIBRATION)
        self.assertEqual(self.c.stage,'start_scan')
        self.assertIsNotNone(self.c.pending_scan)
        self.assertTrue(self.m.status_snapshot()['calibration']['waiting_for_sensors'])
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))
        self.state['age']=.02
        self.tick()  # no second tag capture required
        self.assertEqual(self.c.stage,'reverse')
        self.assertEqual(self.c.records[0]['tag_pose']['x_mm'],7430)
        self.assertIsNone(self.c.sensor_wait_since)

    def test_persistent_stationary_poll_stall_aborts(self):
        self.state['age']=.6
        self.tick()
        self.assertEqual(self.m._mode,MODE_CALIBRATION)
        self.now+=5.1
        self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('stale Roomba sensors',self.c.result['reason'])

    def test_hazard_is_not_ignored_during_stationary_poll_delay(self):
        self.state['age']=.6
        self.state['sensors'].cliff_left_sensor=True
        self.tick()
        self.assertEqual(self.m._mode,'idle')

    def test_reported_twelve_degree_heading_is_accepted_with_doubled_limit(self):
        self.tick(); self.tick(pose=self.pose(heading=-.223909),new=True)
        self.assertEqual(self.c.stage,'reverse')

    def test_doubled_heading_limit_still_rejects_outside_envelope(self):
        self.tick(); self.tick(pose=self.pose(heading=-.31),new=True)
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('17.2 deg',self.c.result['reason'])

    def test_doubled_lateral_range_and_gap_acceptance(self):
        pose=self.pose(dx=-1000,heading=.29)
        pose['y_mm']=1370
        self.assertTrue(self.c._valid_start(pose))
        pose['y_mm']=1381
        self.assertFalse(self.c._valid_start(pose))
        pose=self.pose(dx=200)
        self.assertTrue(self.c._valid_start(pose))
        pose['x_mm']=7640
        self.assertFalse(self.c._valid_start(pose))

    def test_doubled_return_error_accepts_three_hundred_mm(self):
        self.start()
        for step in (1,2,3):
            self.move_to(-500*step);self.scan(None)
        self.move_to(0);self.scan(self.pose(-300))
        self.assertEqual(self.c.stage,'contact')

    def test_calibration_does_not_block_sensor_polls_with_wake(self):
        self.assertFalse(any(c.args[0]=='wake' for c in self.robot.execute.call_args_list))

    def test_web_start_is_idempotent_and_respects_oi_stop(self):
        self.start()
        run=self.m.calibration
        self.m.start_calibration()
        self.assertIs(self.m.calibration,run)
        self.state['oi_stopped']=True
        with self.assertRaisesRegex(RuntimeError,'no safety stop'):
            self.m.start_calibration()
        self.m.set_mode('idle')
        self.state['oi_stopped']=False
        self.m.start_calibration()
        self.assertEqual(self.m._mode,MODE_CALIBRATION)
        self.assertIsNot(self.m.calibration,run)

    def test_phone_required_at_start_and_timeout(self):
        self.ground['flags']=2
        self.tick(); self.tick(pose=self.pose(),new=True)
        self.assertEqual(self.c.stage,'phone_anchor')
        self.now+=11; self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('timeout',self.c.result['reason'])

    def test_scan_results_predating_request_cannot_advance(self):
        self.tick()
        self.c.tick(self.state,self.pose(),True,self.c.requested_after-1)
        self.assertEqual(self.c.stage,'start_scan')
        self.assertIsNone(self.c.origin)

    def test_lost_phone_segment_is_never_stitched(self):
        self.start(); self.move_to(-250)
        self.ground['continuity']=1
        self.move_to(-500); self.scan(self.pose(-500))
        self.assertIsNone(self.c.records[-1]['iphone_pose'])
        self.assertIn('continuity changed',self.c.records[-1]['iphone_unavailable'])
        self.assertEqual(self.c.stage,'reverse')

    def test_stale_transport_is_unavailable_without_inventing_a_position(self):
        self.start()
        self.ground['received_monotonic']=self.now-2
        self.assertIsNone(self.c._phone_pose()[0])

    def test_return_tag_required_before_contact(self):
        self.start()
        for step in (1,2,3):
            self.move_to(-500*step); self.scan(None)
        self.move_to(0); self.scan(None)
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('return scan',self.c.result['reason'])
        self.assertIsNone(self.c.contact_start)

    def test_contact_is_bounded_and_rejects_early_obstacle(self):
        self.return_to_start()
        self.state['sensors'].bumps_and_wheel_drops.bump_left=True
        self.tick()
        self.assertEqual(self.c.result['status'],'aborted')
        self.assertIn('before verified tag',self.c.result['reason'])

    def test_contact_distance_limit_without_touch_stops(self):
        self.return_to_start()
        self.move_to(self.c.contact_limit-1)
        self.tick(delta=2)
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('distance limit',self.c.result['reason'])

    def test_hazards_reset_drift_and_impacts_stop(self):
        initial=deepcopy(self.state)
        for change in ('cliff','stale','epoch','heading','impact','latch'):
            with self.subTest(change=change):
                self.state.clear(); self.state.update(deepcopy(initial))
                self.health['bump_count']=0
                self.m.set_mode(MODE_CALIBRATION); self.c=self.m.calibration
                self.camera.request_scan.reset_mock()
                self.start()
                if change=='cliff': self.state['sensors'].cliff_left_sensor=True
                if change=='stale': self.state['age']=1
                if change=='epoch': self.state['odometry_epoch']=2
                if change=='impact': self.health['bump_count']=1
                if change=='latch': self.state['safety_latched']=True
                if change=='heading': self.tick(heading_delta=10)
                self.tick(heading_delta=10 if change=='heading' else 0)
                self.assertEqual(self.m._mode,'idle')
                self.assertEqual(self.c.result['status'],'aborted')

    def test_no_progress_and_wrong_way_stop(self):
        self.start(); self.now+=4; self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('no wheel progress',self.c.result['reason'])

    def test_clock_cancels_and_remote_takeover_cancels(self):
        self.start(); self.state['clock_button']=True
        self.assertTrue(self.m._handle_clock(self.state))
        self.assertEqual(self.m._mode,'idle')
        self.m.set_mode(MODE_CALIBRATION)
        run=self.m.calibration
        self.m.take_manual_control()
        self.assertEqual(run.result['status'],'cancelled')
        self.assertEqual(self.m._mode,'remote_control')

    def test_scan_is_skipped_during_motion_and_led_remains_cal(self):
        self.start()
        self.assertFalse(self.m.scan_pause())
        self.move_to(-500)
        self.assertTrue(self.m.scan_pause())
        display=SimpleNamespace()
        RobotCommandArbiter.set_drive_display(display,'calibration',scanning=True)
        self.assertEqual(display._drive_display,'CAL ')

    def test_scan_deadline_and_hazard_guard_run_while_camera_busy(self):
        self.m._scan_active=True
        self.c.deadline=self.now-1
        self.m._shutdown=Mock(); self.m._shutdown.is_set.side_effect=[False,True]
        self.m._run()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('timeout',self.c.result['reason'])

    def test_calibration_filters_other_tags_and_disables_old_phone_aiding(self):
        self.m.phone_position=Mock()
        self.localizer.update.return_value=self.pose()
        self.camera.last_detection_time=1700000000+self.now+1
        self.camera.last_detection_ready_time=1700000000+self.now
        self.camera.pause_for_detection=True
        self.camera.latest_detections=[dict(id=1),dict(id=15)]
        self.m._tick()
        self.assertEqual(self.localizer.update.call_args.args[0],({'id':15},))
        self.m.phone_position.apply.assert_not_called()


if __name__=='__main__': unittest.main()
