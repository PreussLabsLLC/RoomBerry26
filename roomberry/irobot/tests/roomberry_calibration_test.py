# @(#)roomberry_calibration_test.py 3.1.threshold.2 2026/11/03 09:20:00
"""Scan-free calibration route, GroundHog steering, and failure stops."""
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
        self.camera.request_scan.assert_not_called()
        self.assertEqual(self.c.stage,'reverse')

    def move_to(self,target,phone_scale=1):
        direction=1 if target>self.state['distance'] else -1
        while abs(target-self.state['distance'])>.01:
            self.tick(delta=direction*min(10,abs(target-self.state['distance'])),phone_scale=phone_scale)
            self.assertEqual(self.m._mode,MODE_CALIBRATION)

    def test_phone_segment_rotation_is_removed_at_initial_anchor(self):
        self.ground['segment_yaw_rad']=pi/2
        self.start()
        self.ground.update(segment_x_mm=0,segment_y_mm=-500)
        phone, reason=self.c._phone_pose()
        self.assertIsNone(reason)
        self.assertAlmostEqual(phone['x_mm'],-500)
        self.assertAlmostEqual(phone['y_mm'],0)
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

    def test_stationary_poll_delay_waits_for_fresh_sensors(self):
        self.state['age']=.583
        self.tick(pose=self.pose(),new=True)
        self.assertEqual(self.m._mode,MODE_CALIBRATION)
        self.assertEqual(self.c.stage,'phone_anchor')
        self.assertTrue(self.m.status_snapshot()['calibration']['waiting_for_sensors'])
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))
        self.state['age']=.02
        self.tick()  # begin with a fresh local baseline
        self.assertEqual(self.c.stage,'reverse')
        self.assertIsNone(self.c.records[0]['tag_pose'])
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

    def test_stale_transport_is_unavailable_without_inventing_a_position(self):
        self.start()
        self.ground['received_monotonic']=self.now-2
        self.assertIsNone(self.c._phone_pose()[0])

    def test_hazards_reset_drift_and_impacts_stop(self):
        initial=deepcopy(self.state)
        for change in ('cliff','stale','epoch','heading','latch'):
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

    def test_return_small_bump_is_recorded_without_stopping(self):
        self.start()
        self.move_to(-100)
        self.c._move('return',self.state)
        self.health.update(bump_count=1,last_bump_peak_mm_s2=3383.3125)
        self.tick(delta=10)
        self.assertEqual(self.c.stage,'return')
        self.assertEqual(self.c.phone_bumps[0]['action'],'record-only')
        self.assertAlmostEqual(self.c.phone_bumps[0]['peak_mm_s2'],3383.3125)
        self.tick(delta=10)
        self.assertEqual(len(self.c.phone_bumps),1)
        self.c._record('sample',self.state,None,None)
        self.assertEqual(self.c.records[-1]['phone_bumps'][0]['count'],1)

    def test_refined_bump_peak_can_still_stop(self):
        self.start()
        self.move_to(-100)
        self.c._move('return',self.state)
        self.health.update(bump_count=1,last_bump_peak_mm_s2=3383)
        self.tick(delta=10)
        self.health['last_bump_peak_mm_s2']=6000
        self.tick(delta=10)
        self.assertEqual(self.m._mode,'idle')
        self.assertEqual(len(self.c.phone_bumps),1)
        self.assertEqual(self.c.phone_bumps[0]['action'],'stop')

    def test_large_bump_stops_and_old_events_do_not_retrigger(self):
        self.health.update(bump_count=3,last_bump_peak_mm_s2=6000)
        self.start(); self.tick(delta=-10)
        self.assertEqual(self.c.stage,'reverse')
        self.c.stage='return'
        self.health['bump_count']=4
        self.tick(delta=-10)
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('phone reported an impact',self.c.result['reason'])

    def test_endpoint_approach_keeps_usable_drive_speed(self):
        self.start()
        self.move_to(-self.c.distance_mm+20)
        self.tick()
        calls=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertTrue(calls)
        self.assertLessEqual(calls[-1].kwargs['left_velocity'],-25)
        self.assertLessEqual(calls[-1].kwargs['right_velocity'],-25)
        self.assertEqual(self.c.stage,'reverse')

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

    def test_clock_release_and_second_press_restarts_after_cancel(self):
        self.start()
        old = self.c
        self.state['clock_button']=True
        self.assertTrue(self.m._handle_clock(self.state))
        self.assertEqual(old.result['status'],'aborted')
        self.state['clock_button']=False
        self.assertFalse(self.m._handle_clock(self.state))
        self.state['clock_button']=True
        self.assertTrue(self.m._handle_clock(self.state))
        self.assertIsNot(self.m.calibration,old)
        self.c=self.m.calibration
        self.tick()
        self.assertEqual(self.c.stage,'reverse')
        self.camera.request_scan.assert_not_called()

    def test_tracking_abort_restores_passive_before_idle_feedback(self):
        from irobot.openinterface.constants import MODES
        self.start()
        self.robot.execute.reset_mock()
        self.ground.update(continuity=2,rejected_frames=52,reason=0)
        self.tick(delta=-10)
        self.assertIn('continuity changed',self.c.result['reason'])
        self.assertIn('rejected_frames=52',self.c.result['reason'])
        self.robot.execute.assert_any_call('_change_mode',mode=MODES.PASSIVE)
        self.assertEqual(self.m._mode,'idle')
        self.assertEqual(self.c.result['status'],'aborted')
        # The next physical rising edge can start a new baseline.
        self.state['clock_button']=True
        self.assertTrue(self.m._handle_clock(self.state))
        self.c=self.m.calibration
        self.tick()
        self.assertEqual(self.c.stage,'reverse')
        self.assertEqual(self.c.phone_anchor['identity'][2],2)

    def test_calibration_exit_does_not_rearm_oi_stop(self):
        self.start()
        self.robot.execute.reset_mock()
        self.state['oi_stopped']=True
        self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertFalse(any(c.args[0]=='_change_mode' for c in self.robot.execute.call_args_list))

    def test_calibration_completion_restores_passive(self):
        from irobot.openinterface.constants import MODES
        self.start()
        self.robot.execute.reset_mock()
        self.c._finish(self.state)
        self.robot.execute.assert_any_call('_change_mode',mode=MODES.PASSIVE)
        self.assertEqual(self.c.result['status'],'complete')

    def test_scan_is_skipped_during_motion_and_led_remains_cal(self):
        self.start()
        self.assertFalse(self.m.scan_pause())
        self.move_to(-500)
        self.assertFalse(self.m.scan_pause())
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

    def test_continuous_five_metre_route_one_hold_and_no_scans(self):
        self.m._send_stop=Mock(wraps=self.m._send_stop)
        self.start()
        self.assertAlmostEqual(self.c.distance_mm, 5000)
        self.move_to(-self.c.distance_mm)
        self.assertEqual(self.c.stage, 'turnaround')
        self.assertFalse(self.m.scan_pause())
        calls=len(self.robot.execute.call_args_list)
        self.tick(); self.tick()
        self.assertEqual(self.c.stage, 'turnaround')
        self.assertEqual(len(self.robot.execute.call_args_list), calls)
        self.now+=1
        self.tick()
        self.assertEqual(self.c.stage, 'return')
        # Stop within the existing 15 mm tolerance of the origin.
        self.move_to(-20)
        self.tick(delta=10)
        self.assertEqual(self.c.stage, 'complete')
        reasons=[c.args[0] for c in self.m._send_stop.call_args_list]
        self.assertEqual(reasons.count('calibration turnaround'),1)
        self.assertEqual(self.m._mode, 'idle')
        self.assertEqual([r['checkpoint'] for r in self.c.records],
                         ['start','turnaround','finish'])
        self.camera.request_scan.assert_not_called()
        self.assertTrue(all(r['tag_pose'] is None for r in self.c.records))
        self.assertFalse(any(c.args[0] in ('spin_left','spin_right','seek_dock')
                             for c in self.robot.execute.call_args_list))

    def test_groundhog_controls_heading_in_both_directions(self):
        self.start()
        self.ground['segment_yaw_rad']=.05
        self.tick(delta=-10)
        calls=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertEqual(calls[-1].kwargs, dict(right_velocity=-59,left_velocity=-40))
        self.assertAlmostEqual(self.c.wheels['heading_rad'],0)
        self.c._move('return',self.state)
        # Stay away from the return endpoint while testing the opposite sign.
        self.state['distance']=-100
        self.c.progress=-100
        self.tick()
        calls=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertGreater(calls[-1].kwargs['left_velocity'],calls[-1].kwargs['right_velocity'])

    def test_groundhog_limit_and_steering_clamp(self):
        self.start()
        self.ground['segment_yaw_rad']=.2
        self.tick(delta=-10)
        calls=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertEqual(calls[-1].kwargs,dict(right_velocity=-67,left_velocity=-32))
        self.ground['segment_yaw_rad']=.31
        self.tick()
        self.assertIn('heading drift',self.c.result['reason'])

    def test_groundhog_loss_stops_in_motion_and_hold(self):
        for stage in ('reverse','turnaround'):
            for change in ('continuity','session','calibration','flags','stale','frame','nonfinite'):
                with self.subTest(stage=stage,change=change):
                    self.m.set_mode('idle')
                    self.m.set_mode(MODE_CALIBRATION); self.c=self.m.calibration
                    self.ground.update(flags=7,segment_yaw_rad=0)
                    self.start()
                    self.c.stage=stage
                    self.c.hold_until=self.now+1
                    if change=='stale': self.ground['received_monotonic']=self.now-2
                    elif change=='nonfinite': self.ground['segment_yaw_rad']=float('nan')
                    elif change=='frame': self.ground['end_us']=self.ground['send_us']-600000
                    else: self.ground[change]+=1
                    if change=='flags': self.ground['flags']=2
                    self.c.tick(self.state,None,False,None)
                    self.assertEqual(self.c.result['status'],'aborted')
                    self.assertEqual(self.m._mode,'idle')

    def test_inflight_tag_pose_is_ignored(self):
        self.tick(pose=self.pose(dx=900,heading=pi/2),new=True)
        self.assertEqual(self.c.stage,'reverse')
        self.assertEqual(self.c.origin['heading_rad'],0)
        self.assertIsNone(self.c.records[0]['tag_pose'])
        self.camera.request_scan.assert_not_called()

    def test_unexpected_bumper_aborts(self):
        self.start()
        self.state['sensors'].bumps_and_wheel_drops.bump_left=True
        self.tick()
        self.assertIn('unexpected physical bumper',self.c.result['reason'])

    def test_reverse_bump_stops_then_returns_without_retriggering(self):
        self.health.update(bump_count=3,last_bump_peak_mm_s2=6000)
        self.start()
        self.move_to(-4700)
        self.health.update(bump_count=4,last_bump_peak_mm_s2=100)
        self.tick(delta=-5)
        self.assertEqual(self.c.stage,'turnaround')
        self.assertEqual(self.c.turnaround_reason,'phone bump')
        self.assertEqual(self.c.phone_bumps[-1]['action'],'threshold-stop')
        self.assertEqual(self.c.records[-1]['wheel_distance_from_start_mm'],-4705)
        self.health['last_bump_peak_mm_s2']=6000
        self.tick()
        self.assertEqual(self.c.stage,'turnaround')
        self.now+=1
        self.tick()
        self.assertEqual(self.c.stage,'return')
        self.move_to(-20)
        self.tick(delta=10)
        self.assertEqual(self.c.stage,'complete')
        self.camera.request_scan.assert_not_called()

    def test_reverse_bump_without_peak_still_ends_leg(self):
        self.start()
        self.health['bump_count']=1
        self.tick(delta=-10)
        self.assertEqual(self.c.stage,'turnaround')

    def test_cruise_speed_is_50_mm_s(self):
        self.start(); self.tick(delta=-10)
        self.assertEqual(self.robot.execute.call_args.kwargs['left_velocity'],-50)
        self.assertEqual(self.robot.execute.call_args.kwargs['right_velocity'],-50)

    def test_distance_configuration_and_invalid_values(self):
        from roomberry_calibration import CalibrationDrive
        with patch.dict('os.environ',{'ROOMBERRY_CALIBRATION_DISTANCE_MM':'5000',
                                      'ROOMBERRY_CALIBRATION_HOLD_S':'1.5'}):
            run=CalibrationDrive(self.m)
            self.assertEqual(run.distance_mm,5000)
            self.assertEqual(run.hold_s,1.5)
        for value in ('nan','inf','-10','5001'):
            with patch.dict('os.environ',{'ROOMBERRY_CALIBRATION_DISTANCE_MM':value}):
                with self.assertRaises(ValueError): CalibrationDrive(self.m)

if __name__=='__main__': unittest.main()
