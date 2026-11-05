"""Standalone homing across mission states, localization search and safe routing."""
# @(#)roomberry_tag_return_test.py 3.1.grout.17 2026/11/05
import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import roomberry_calibration_test as fixture
from roomberry_tag_return import Tag15Return


class TagReturnTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CalibrationTest('test_cruise_speed_is_50_mm_s')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.m, self.state = self.f.m, self.f.state
        self.m.mapper.robot_radius_mm = 174
        self.m.mapper.cell_size_mm = 87
        self.m.mapper.motion_is_clear.return_value = True
        self.m.mapper.plan_to.side_effect = lambda x,y: {'path':[(0,0),(x,y)]}
        self.m.mapper.cell_center.side_effect = lambda cell: cell
        self.m._shutdown.wait = Mock(return_value=False)
        self.m.navlink = None
        for module in ('roomberry_tag_return','roomberry_gridrunner'):
            for function, value in [('monotonic', lambda:self.f.now),
                                    ('time', lambda:1700000000+self.f.now)]:
                p = patch(module+'.'+function, side_effect=value)
                p.start(); self.addCleanup(p.stop)

    def tick(self, capture=False):
        self.f.now += .2
        if capture:
            self.m.camera.last_detection_time = self.run.scan_wall+.01
            self.m.camera.latest_detections = ()
        self.run.tick(self.state, scan_active=self.m._scan_active)

    def start(self):
        self.m.return_to_tag15()
        self.run = self.m.gridrunner
        self.assertIsInstance(self.run, Tag15Return)
        return self.run

    def test_speed_change_bump_is_consumed_during_homing(self):
        self.start()
        health=dict(session=1,calibration=1,bump_count=0)
        self.m.navlink=SimpleNamespace(latest_health_observation=lambda:dict(
            health,received_monotonic=self.f.now))
        self.tick()
        self.f.robot.phone_bump_speed_change.return_value=dict(at=self.f.now,delay_ms=95)
        health['bump_count']=1
        self.tick()
        self.assertIsNone(self.run.result)
        self.f.robot.phone_bump_speed_change.return_value=None
        self.tick()
        self.assertIsNone(self.run.result)
        health['bump_count']=2
        self.tick()
        self.assertIn('phone impact',self.run.result['reason'])

    def test_explicit_homing_prefers_stable_homeward_grout(self):
        from roomberry_gridrunner import GridDrive
        self.start()
        self.run.pose=self.fixed_pose()
        self.run.tag_fix_applied=True
        self.run.stage='return'
        self.run.route=[(self.run.pose['x_mm']+500,self.run.pose['y_mm']+500)]
        row=dict(session=1,calibration=1,seq=1,flags=3,confidence=1,direction=-1,
                 gain=2,correction_limit=.25,lens_left_mm=26,height_mm=85)
        health=dict(session=1,calibration=1,bump_count=0)
        self.m.navlink=SimpleNamespace(
            latest_grid_observation=lambda:dict(row,received_monotonic=self.f.now,frame_monotonic=self.f.now),
            latest_health_observation=lambda:dict(health,received_monotonic=self.f.now))
        for seq in (1,2):
            row['seq']=seq;self.tick()
            self.assertIs(self.m.gridrunner,self.run)
            self.assertIsNone(self.run.last)  # Qualification holds zero, no map turn.
        row['seq']=3;self.tick()
        self.assertIsInstance(self.m.gridrunner,GridDrive)
        self.assertNotIsInstance(self.m.gridrunner,Tag15Return)
        self.assertEqual(self.m.gridrunner.stage,'return')
        # Real-run regression: completion after explicit homing has no outbound
        # metadata, but bumper arrival must still report success rather than crash.
        grid=self.m.gridrunner
        grid.stage='approach';grid.final_fix=True
        grid.pose.update(x_mm=grid.tag['x']-grid.tag['radius'],
                         y_mm=grid.tag['y']-26,heading_rad=0)
        self.state['sensors'].bumps_and_wheel_drops.bump_left=True
        self.state['sensors'].bumps_and_wheel_drops.bump_right=True
        grid.tick(self.state)
        self.assertEqual(grid.result['status'],'complete')
        self.assertIsNone(grid.result['outbound_mm'])
        self.assertEqual(self.m._mode,'idle')

    def test_original_homeward_heading_can_qualify_line_despite_tag_yaw_bias(self):
        from roomberry_gridrunner import GridDrive
        self.start()
        self.run.pose=self.fixed_pose(heading=1.)
        self.run.tag_fix_applied=True;self.run.stage='return'
        source=GridDrive(self.m);source.initial_heading=self.state['angle']
        self.run.grout_source=source
        row=dict(session=1,calibration=1,seq=1,flags=3,confidence=1,direction=-1,
                 received_monotonic=self.f.now,frame_monotonic=self.f.now)
        self.m.navlink=SimpleNamespace(latest_grid_observation=lambda:row)
        self.assertTrue(self.run._resume_visible_line(self.state,dict(session=1,calibration=1),False))

    def test_mapped_route_shortcut_checks_entire_segment(self):
        self.start()
        self.run.pose=self.fixed_pose(gap=1600)
        self.m.mapper.plan_to.side_effect=None
        self.m.mapper.plan_to.return_value=dict(path=[(0,0),(10,10),(20,-20),(30,0)])
        self.m.mapper.cell_center.side_effect=lambda p:p
        self.m.mapper.motion_is_clear.return_value=True
        self.run._plan_route()
        self.assertEqual(len(self.run.route),1)
        self.assertEqual(self.run.route[0],self.run._target(self.run.tag['radius']+400))
        self.assertGreater(self.m.mapper.motion_is_clear.call_args.args[3],.6)

    def test_visible_line_cannot_send_unknown_pose_or_backwards_robot_home(self):
        self.start()
        row=dict(session=1,calibration=1,seq=1,flags=3,confidence=1,direction=-1,
                 received_monotonic=self.f.now,frame_monotonic=self.f.now)
        self.m.navlink=SimpleNamespace(latest_grid_observation=lambda:row)
        health=dict(session=1,calibration=1,bump_count=0)
        self.assertFalse(self.run._resume_visible_line(self.state,health,False))
        self.run.pose=self.fixed_pose(heading=3.14);self.run.tag_fix_applied=True
        self.run.stage='return'
        self.assertFalse(self.run._resume_visible_line(self.state,health,False))

    def fixed_pose(self, gap=1200, heading=0, lateral=0):
        return dict(x_mm=self.run.tag['x']-gap, y_mm=self.run.tag['y']+lateral,
                    heading_rad=heading, accepted_tag_ids=(('tag16h5',15),))

    def confirm(self, pose):
        self.run._fix = lambda detections: dict(pose)
        self.tick(capture=True)
        self.tick(capture=True)

    def test_every_mission_mode_can_start_without_phone_or_threshold(self):
        for mode in ('idle','remote_control','calibration','discovery','clean','return_to_base','gridrunner'):
            with self.subTest(mode=mode):
                self.m.set_mode(mode)
                self.start()
                self.assertEqual(self.run.stage, 'scanning')
                self.assertFalse(self.run.final_fix)
                self.assertIsNone(self.run.threshold)
                self.assertIsNone(self.run.pose)

    def test_takeover_force_stops_and_waits_for_post_transition_sensor_poll(self):
        self.state['age'] = .8
        def fresh_poll(seconds):
            self.state['age'] = 0
            return False
        self.m._shutdown.wait.side_effect = fresh_poll
        self.start()
        self.assertEqual(self.run.stage, 'scanning')
        self.m.robot_control.execute.assert_any_call('stop', timeout=2)
        self.m._shutdown.wait.assert_any_call(.02)

    def test_valid_trace_before_threshold_can_bridge_a_missing_tag(self):
        self.m.gridrunner = SimpleNamespace(pose=dict(x_mm=6400,y_mm=1154,heading_rad=0),
            epoch=self.state['odometry_epoch'], odom=(0,0), target_offset_mm=26)
        self.start()
        self.run._fix = lambda detections: None
        self.tick(capture=True)
        self.assertEqual(self.run.stage, 'return')
        self.assertIsNone(self.run.threshold)
        self.assertTrue(self.run.route)
        self.tick()
        self.assertGreater(self.run.last['velocity_mm_s'], 0)

    def test_reset_or_unobserved_movement_cannot_reuse_old_trace(self):
        self.m.gridrunner = SimpleNamespace(pose=dict(x_mm=6400,y_mm=1154,heading_rad=0),
            epoch=self.state['odometry_epoch']-1, odom=(-500,0), target_offset_mm=26)
        self.start()
        self.assertIsNone(self.run.pose)
        self.run._fix = lambda detections: None
        self.tick(capture=True)
        self.assertEqual(self.run.stage, 'searching')
        self.tick()
        self.assertEqual(self.run.last['velocity_mm_s'], 0)

    def test_return_after_oi_restart_requires_no_retained_run(self):
        self.m.restart_oi()
        self.state['odometry_epoch'] += 1
        self.assertIsNone(self.m.gridrunner)
        self.start()
        self.assertEqual(self.run.epoch, self.state['odometry_epoch'])
        self.assertEqual(self.run.stage, 'scanning')

    def test_later_discrepant_fixes_require_stationary_confirmation(self):
        self.start()
        self.confirm(self.fixed_pose())
        previous = dict(self.run.pose)
        self.run._request_fix('localize')
        self.run._fix = lambda detections: dict(previous, x_mm=previous['x_mm']+300,
            accepted_tag_ids=(('tag16h5',15),))
        self.tick(capture=True)
        self.assertEqual(self.run.pose, previous)
        self.assertEqual(self.run.stage, 'scanning')
        self.tick(capture=True)
        self.assertAlmostEqual(self.run.pose['x_mm'], previous['x_mm']+300)
        self.assertTrue(self.run.records[-1]['accepted'])
        self.assertIn('relocation confirmed', self.run.records[-1]['reason'])

    def test_disagreeing_stationary_scans_never_replace_pose(self):
        self.start()
        self.confirm(self.fixed_pose())
        previous = dict(self.run.pose)
        self.run._request_fix('localize')
        offsets = iter((300, 600, 900))
        self.run._fix = lambda detections: dict(previous, x_mm=previous['x_mm']+next(offsets),
            accepted_tag_ids=(('tag16h5',15),))
        for _ in range(3):
            self.tick(capture=True)
        self.assertEqual(self.run.pose, previous)
        self.assertIn('could not be confirmed', self.run.result['reason'])

    def test_missing_scan_breaks_relocation_confirmation(self):
        self.start()
        self.confirm(self.fixed_pose())
        previous = dict(self.run.pose)
        self.run._request_fix('localize')
        corrected = dict(previous, x_mm=previous['x_mm']+600,
            accepted_tag_ids=(('tag16h5',15),))
        poses = iter((corrected, None, corrected))
        self.run._fix = lambda detections: next(poses)
        for _ in range(3):
            self.tick(capture=True)
        self.assertEqual(self.run.pose, previous)
        self.assertIsNotNone(self.run.result)

    def test_scan_already_active_queues_fresh_result_instead_of_rejecting(self):
        self.m._scan_active = True
        self.start()
        self.m.camera.last_detection_time = self.run.scan_wall-1
        self.tick()
        self.assertEqual(self.run.stage, 'scanning')
        self.m._scan_active = False
        self.confirm(self.fixed_pose())
        self.assertEqual(self.run.stage, 'return')

    def test_unknown_location_searches_in_place_and_never_translates(self):
        self.start()
        self.run._fix = lambda detections: None
        self.tick(capture=True)
        self.assertEqual(self.run.stage, 'searching')
        self.tick()
        self.assertEqual(self.run.last['velocity_mm_s'], 0)
        self.assertEqual(self.run.last['left_velocity_mm_s'], -self.run.last['right_velocity_mm_s'])
        self.assertIsNone(self.run.pose)
        for _ in range(350):
            if self.run.result is not None:break
            if self.run.stage == 'scanning':
                self.tick(capture=True)
            else:
                self.tick()
                if self.run.stage == 'searching':
                    left, right = self.run.last['left_velocity_mm_s'], self.run.last['right_velocity_mm_s']
                    self.state['angle'] += math.degrees((right-left)/235*.2)
        self.assertEqual(self.state['distance'], 0)
        self.assertIn('no mapped tag', self.run.result['reason'])

    def test_safety_stop_is_not_bypassed_and_previous_mission_is_stopped(self):
        self.state['oi_stopped'] = True
        with self.assertRaisesRegex(RuntimeError, 'Restart OI'):
            self.m.return_to_tag15()
        self.assertEqual(self.m._mode, 'idle')

    def test_bad_final_pose_stays_stopped(self):
        self.start()
        self.confirm(self.fixed_pose(gap=600))
        self.tick()  # Corridor -> aim camera.
        self.tick()  # Already facing tag -> final scan.
        self.assertEqual(self.run.scan_purpose, 'final')
        self.run._fix = lambda detections: None
        for _ in range(3):self.tick(capture=True)
        self.assertEqual(self.m._mode, 'idle')
        self.assertFalse(self.run.final_fix)
        self.assertIn('no consistent', self.run.result['reason'])

    def test_blocked_map_aborts_before_drive(self):
        self.start()
        self.m.mapper.motion_is_clear.return_value = False
        self.confirm(self.fixed_pose())
        self.tick()
        self.assertIn('mapped obstacle', self.run.result['reason'])

    def test_no_route_aborts_without_blind_direct_fallback(self):
        self.start()
        self.m.mapper.plan_to.side_effect = None
        self.m.mapper.plan_to.return_value = None
        self.confirm(self.fixed_pose())
        self.assertIn('no clear mapped route', self.run.result['reason'])

    def test_epoch_reset_during_return_stops(self):
        self.start()
        self.confirm(self.fixed_pose())
        self.state['odometry_epoch'] += 1
        self.tick()
        self.assertIn('odometry invalid or reset', self.run.result['reason'])

    def test_repeat_press_keeps_current_return(self):
        self.start()
        previous = self.run
        self.m.return_to_tag15()
        self.assertIs(self.m.gridrunner, previous)

    def test_full_homing_from_large_heading_without_phone(self):
        from roomberry_mapper import RoomberryMapper
        self.m.mapper = RoomberryMapper(104, 92, 174, cell_size_mm=87)
        self.start()
        actual = dict(x_mm=self.run.tag['x']-1400, y_mm=self.run.tag['y']-250,
                      heading_rad=math.radians(120))
        def camera_fix(detections):
            bearing = math.atan2(self.run.tag['y']-actual['y_mm'], self.run.tag['x']-actual['x_mm'])
            if abs(self.run._wrap(bearing-actual['heading_rad'])) > math.radians(55):
                return None
            return dict(actual, accepted_tag_ids=(('tag16h5',15),))
        self.run._fix = camera_fix
        self.state['angle'] = 120
        self.run.odom = (0,120)
        self.run.search_origin = 120
        for _ in range(2000):
            previous = self.run.last
            self.tick(capture=self.run.stage=='scanning')
            if self.run.result is not None:break
            if self.run.stage == 'scanning' or self.run.last is None or self.run.last is previous:continue
            row = self.run.last
            left, right = row['left_velocity_mm_s'], row['right_velocity_mm_s']
            delta = (left+right)/2*.2
            yaw = (right-left)/235*.2
            actual['x_mm'] += delta*math.cos(actual['heading_rad']+yaw/2)
            actual['y_mm'] += delta*math.sin(actual['heading_rad']+yaw/2)
            actual['heading_rad'] = self.run._wrap(actual['heading_rad']+yaw)
            self.state['distance'] += delta
            self.state['angle'] += math.degrees(yaw)
            if self.run.tag['x']-actual['x_mm'] <= 174:
                self.state['sensors'].bumps_and_wheel_drops.bump_left = True
        self.assertEqual(self.run.result['status'], 'complete', self.run.result)
        self.assertLess(abs(actual['y_mm']-self.run.tag['y']), 75)
        self.assertLess(abs(actual['heading_rad']), .2)
        self.assertGreater(self.run.search_index, 0)

    def test_localization_uses_real_survey_geometry_at_large_heading(self):
        import json
        from pathlib import Path
        from roomberry_localization import AprilTagLocalizer as L
        config = json.loads((Path(__file__).resolve().parents[2]/'autonomy.json').read_text())
        landmark = next(x for x in config['landmarks'] if x['id']==15)
        tag = landmark['world_from_tag']
        self.m.discovery_landmarks = {15:landmark}
        self.m.localizer = L({('tag16h5',15):tag}, config['camera_from_robot'])
        self.start()
        heading = -.45
        world_robot = [[math.cos(heading),-math.sin(heading),0,tag[0][3]-1],
                       [math.sin(heading),math.cos(heading),0,tag[1][3]],
                       [0,0,1,0],[0,0,0,1]]
        camera_tag = L._multiply(config['camera_from_robot'], L._multiply(L._inverse(world_robot),tag))
        detection = dict(family='tag16h5',id=15,hamming=0,decision_margin=100,
            tag_pose_camera=dict(rotation=[r[:3] for r in camera_tag[:3]],
                translation_m=[r[3] for r in camera_tag[:3]],error=0))
        fix = self.run._fix([detection])
        self.assertAlmostEqual(fix['heading_rad'], heading)
        self.assertAlmostEqual(fix['x_mm'], (tag[0][3]-1)*1000)
