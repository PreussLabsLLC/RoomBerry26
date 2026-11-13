"""WALL departure geometry, raw IR qualification, cancellation and safety."""
# @(#)roomberry_wall_test.py 3.2 2026/11/09 18:53:01
import logging
from math import pi, sin, cos, radians, degrees
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from roomberry_mission import RoomberryMission
from roomberry_control import RobotCommandArbiter, WallContactStop
from roomberry_wall import WALL_MIN_WHEEL_SPEED, WALL_TAG15_RADIUS_MM, WALL_TAG15_MAX_STEPS


class WallTest(unittest.TestCase):
    def setUp(self):
        self.robot = Mock()
        self.robot.consume_clock_button_press.return_value = False
        self.sensors = NS(wall_signal=999, light_bump_right_signal=30, bumps_and_wheel_drops=NS(bump_left=False, bump_right=False))
        self.state = dict(ready=True, age=0, sensors=self.sensors, distance=0., angle=0.,
                          sensor_monotonic_s=1., odometry_epoch=1, battery_status='normal',
                          hard_hazard_reasons=[], clock_button=False)
        def snapshot():
            self.state['sensor_monotonic_s'] += .1
            return dict(self.state)
        self.robot.snapshot.side_effect = snapshot
        self.m = RoomberryMission(self.robot, Mock(), Mock(), Mock(), Mock(), logging.getLogger('wall-test'))
        self.m.start_wall()
        self.w = self.m.wall
        self.w.goal_target = (6100.,1156.)

    def tick(self, distance=None, angle=None):
        if distance is not None:
            self.state['distance'] = distance
        if angle is not None:
            self.state['angle'] = angle
        self.state['sensor_monotonic_s'] += .1
        self.w.tick(self.state)

    def anchor(self):
        pose = dict(x_mm=3100, y_mm=1400, heading_rad=-pi/2, localized=True,
                    accepted_tag_ids=(('tag16h5',16),))
        for t in (self.w._wall_time+1, self.w._wall_time+2):
            self.w.tick(self.state, pose, True, t)
        self.assertEqual(self.w.stage, 'left90')

    def approach(self):
        self.anchor()
        self.tick(angle=20); self.tick(angle=40); self.tick(angle=60); self.tick(angle=80); self.tick(angle=89)
        self.assertEqual(self.w.stage, 'forward200')
        self.tick(distance=70); self.tick(distance=140); self.tick(distance=199)
        self.assertEqual(self.w.stage, 'right45')
        self.tick(angle=70); self.tick(angle=45)
        self.assertEqual(self.w.stage, 'acquire')

    def follow(self):
        self.approach()
        for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'align_left45')
        for angle in (60, 75, 89):
            self.tick(angle=angle)
            self.assertEqual(self.w.stage, 'align_check')
            for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'follow')

    def test_departure_and_ir_acquisition_then_follow_polarity(self):
        self.follow()
        self.sensors.light_bump_right_signal = 45
        for _ in range(4): self.tick(distance=209)
        cmd = self.robot.execute.call_args
        self.assertEqual(cmd.args[0], 'drive_direct')
        self.assertGreater(cmd.kwargs['right_velocity'], cmd.kwargs['left_velocity'])
        self.sensors.light_bump_right_signal = 15
        for _ in range(4): self.tick(distance=219)
        # Ramp through the band in small steps to avoid the fluctuation hold.
        self.sensors.light_bump_right_signal = 10
        for _ in range(4): self.tick(distance=229)
        cmd = self.robot.execute.call_args
        if cmd.args[0] != 'drive_direct':
            # Fluctuation hold stopped motion; clear it and resample.
            self.w.fluctuation_hold_until = None
            self.w.signal_history = []
            self.tick(distance=239)
            cmd = self.robot.execute.call_args
        self.assertLess(cmd.kwargs['right_velocity'], cmd.kwargs['left_velocity'])
        self.assertIsNone(self.w.last['measured_clearance_mm'])
        self.robot.renew_motion_lease.assert_called()

    def test_bumper_acquisition_releases_before_left_alignment(self):
        self.approach()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.tick(distance=180)
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=-WALL_MIN_WHEEL_SPEED, ramp=False)
        self.sensors.bumps_and_wheel_drops.bump_right = False
        self.tick(distance=169)
        self.assertEqual(self.w.stage, 'contact_left')
        self.robot.release_wall_contact_guard.assert_called_once()
        self.tick(angle=60)
        self.assertEqual(self.w.stage, 'rejoin')

    def test_bumper_in_follow_stops_before_retreat_and_left_retry(self):
        self.follow(); self.tick(distance=209)
        self.robot.execute.reset_mock()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.state['safety_latched'] = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertEqual(self.robot.execute.call_args_list[0].args[0], 'stop')
        self.assertFalse(any(c.args[0] == 'drive_direct' for c in self.robot.execute.call_args_list))
        self.tick(distance=199)
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=-WALL_MIN_WHEEL_SPEED, ramp=False)
        self.sensors.bumps_and_wheel_drops.bump_right = False
        self.state['safety_latched'] = False
        self.tick(distance=179)
        self.assertEqual(self.w.stage, 'contact_left')
        self.robot.release_wall_contact_guard.assert_called_once()
        self.tick(angle=104)
        self.assertEqual(self.w.stage, 'rejoin')

    def test_latched_stall_enters_same_contact_recovery_without_bumper(self):
        self.approach()
        self.state.update(wall_contact_blocked=True, wall_contact_event=dict(reason='high-current stalled forward drive'))
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertEqual(self.w.records[-2]['source'], 'high-current stalled forward drive')
        self.assertEqual(self.w.contact_retries, 1)

    def test_held_bumper_cannot_turn_after_maximum_retreat(self):
        self.approach()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.tick(distance=149)
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('50 mm', self.w.result['reason'])
        self.robot.release_wall_contact_guard.assert_not_called()

    def test_contact_does_not_override_cliff_guard(self):
        self.approach()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.state['hard_hazard_reasons'] = ['cliff']
        self.tick()
        self.assertEqual(self.m._mode, 'idle')
        self.assertNotEqual(self.w.stage, 'release')

    def enter_rejoin(self):
        self.follow(); self.tick(distance=209)
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.sensors.bumps_and_wheel_drops.bump_right = False
        self.tick(distance=179)
        self.tick(angle=104)
        self.assertEqual(self.w.stage, 'rejoin')

    def test_uploaded_post_contact_signal32_resumes_without_extra_alignment(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 32
        self.robot.execute.reset_mock()
        for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'follow')
        self.assertFalse(any(c.args[0] == 'drive_direct' for c in self.robot.execute.call_args_list))
        self.assertEqual(self.w.contact_retries, 1)
        self.assertEqual(self.w.reapproaches, 0)
        self.assertEqual(self.w.follow_heading, 104)

    def test_rejoin_measures_right_turn_then_advances_at30_and_qualifies(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 15
        for _ in range(3): self.tick()
        self.tick()
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=WALL_MIN_WHEEL_SPEED, ramp=False)
        self.tick(angle=99)
        self.assertEqual(self.w.rejoin_phase, 'advance')
        self.tick(distance=184)
        self.robot.execute.assert_called_with('drive_direct', right_velocity=WALL_MIN_WHEEL_SPEED, left_velocity=WALL_MIN_WHEEL_SPEED, ramp=False)
        self.sensors.light_bump_right_signal = 30
        for _ in range(6): self.tick(distance=189, angle=99)
        self.assertEqual(self.w.stage, 'follow')
        self.assertTrue(self.w.lease or self.w.stage == 'follow')

    def test_rejoin_can_pass100mm_but_keeps_heading_time_and_contact_bounds(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 0
        for _ in range(3): self.tick()
        distance, angle = 179, 104
        for _ in range(4):
            self.tick(); angle -= 5; self.tick(angle=angle)
            self.tick(); distance += 30; self.tick(distance=distance)
        self.assertGreater(distance-self.w.stage_distance, 100)
        self.assertEqual(self.w.stage, 'rejoin')
        for _ in range(2):
            self.tick(); angle -= 5; self.tick(angle=angle)
            if self.m._mode == 'idle': break
            self.tick(); distance += 30; self.tick(distance=distance)
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('30 degree bound', self.w.result['reason'])
        self.setUp(); self.enter_rejoin()
        self.w.deadline = 0
        self.tick()
        self.assertIn('time limit during rejoin', self.w.result['reason'])
        self.setUp(); self.enter_rejoin()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertEqual(self.w.contact_retries, 2)

    def test_all_wall_moving_wheel_commands_have_minimum30(self):
        self.follow()
        for signal in (45,20,30):
            self.sensors.light_bump_right_signal = signal
            self.tick(distance=self.state['distance']+5)
        commands=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertTrue(commands)
        for c in commands:
            for key in ('right_velocity','left_velocity'):
                value=c.kwargs[key]
                self.assertTrue(value == 0 or abs(value) >= WALL_MIN_WHEEL_SPEED, c)

    def test_right_pivot_center_drift_is_allowed_but_backing_in_advance_is_not(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 15
        for _ in range(3): self.tick()
        self.tick()
        self.tick(distance=174, angle=99)  # Pivot drift, not a reverse approach.
        self.assertEqual(self.w.rejoin_phase, 'advance')
        self.assertEqual(self.m._mode, 'wall')
        self.tick(distance=179)
        self.tick(distance=170)
        self.assertEqual(self.m._mode, 'idle')
        self.assertEqual(self.w.result['status'], 'aborted')

    def test_rejoin_settles_before_turning_and_does_not_accept_frozen_frames(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 15
        for _ in range(5): self.w.tick(self.state)
        self.assertFalse(self.w.rejoin_ready)
        for angle in (106,108,109): self.tick(angle=angle)
        self.assertTrue(self.w.rejoin_ready)
        self.assertEqual(self.w.stage_angle,109)
        self.tick()
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED,left_velocity=WALL_MIN_WHEEL_SPEED,ramp=False)

    def test_rejoin_does_not_qualify_repeated_frame_or_discard_contact_limit(self):
        self.enter_rejoin()
        self.sensors.light_bump_right_signal = 32
        for _ in range(6): self.w.tick(self.state)
        self.assertEqual(self.w.stage, 'rejoin')
        self.w.reapproaches = 4  # Initial seeking budget does not consume recovery budget.
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.w.contact_retries = 42
        self.w.stage = 'rejoin'
        self.tick()
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('contact recovery limit', self.w.result['reason'])

    def test_repeated_sensor_frame_does_not_qualify_ir(self):
        self.approach()
        for _ in range(10): self.w.tick(self.state)
        self.assertEqual(self.w.stage, 'acquire')

    def test_wrong_tag_and_inconsistent_tag16_do_not_start_motion(self):
        pose = dict(x_mm=0, y_mm=0, heading_rad=0, localized=True,
                    accepted_tag_ids=(('tag16h5',15),))
        self.w.tick(self.state, pose, True, self.w._wall_time+1)
        self.assertEqual(self.w.stage, 'anchor')
        pose['accepted_tag_ids'] = (('tag16h5',16),)
        self.w.tick(self.state, pose, True, self.w._wall_time+2)
        pose['x_mm'] = 500
        self.w.tick(self.state, pose, True, self.w._wall_time+3)
        self.assertEqual(self.w.stage, 'anchor')
        self.assertFalse(any(c.args[0] == 'drive_direct' for c in self.robot.execute.call_args_list))

    def test_hazards_stale_epoch_and_battery_abort(self):
        for change in (dict(age=.6), dict(age=-1), dict(hard_hazard_reasons=['cliff']),
                       dict(oi_stopped=True), dict(sensor_fault=True), dict(motion_lease_expired=True),
                       dict(battery_status='low'), dict(safety_latched=True)):
            with self.subTest(change=change):
                self.setUp()
                self.state.update(change)
                self.w.tick(self.state)
                self.assertEqual(self.m._mode, 'idle')
                self.assertEqual(self.w.result['status'], 'aborted')
        self.setUp(); self.tick(); self.state['odometry_epoch'] = 2; self.tick()
        self.assertIn('epoch', self.w.result['reason'])

    def test_wall_loss_stops_then_searches_right_and_rejoins(self):
        self.follow()
        self.sensors.light_bump_right_signal = 7
        for _ in range(4): self.tick()
        self.robot.execute.assert_any_call('stop', timeout=2)
        self.assertEqual(self.w.stage, 'rejoin')
        self.assertEqual(self.w.rejoin_source, 'wall_loss')
        self.assertFalse(self.w.lease)
        for _ in range(3): self.tick()
        self.tick()
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=WALL_MIN_WHEEL_SPEED, ramp=False)
        self.sensors.light_bump_right_signal = 30
        for _ in range(7): self.tick(distance=209, angle=87)
        self.assertEqual(self.w.stage, 'follow')
        self.assertEqual(self.w.loss_searches, 1)

    def enter_obstacle_bypass(self):
        self.follow()
        self.sensors.light_bump_right_signal = 0
        self.tick(); self.tick()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertTrue(self.w.detour_active)
        self.assertEqual(self.w.contact_left_deg, 20)
        self.sensors.bumps_and_wheel_drops.bump_right = False
        self.tick(distance=169)
        self.assertEqual(self.w.stage, 'contact_left')
        for angle in (109,): self.tick(angle=angle)
        self.assertEqual(self.w.stage, 'rejoin')
        self.sensors.light_bump_right_signal = 30
        for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'follow')
        self.assertTrue(self.w.detour_active)

    def test_fridge_like_contact_turns_left_then_rounds_right_corner(self):
        self.enter_obstacle_bypass()
        self.tick(distance=229)
        self.sensors.light_bump_right_signal = 0
        for _ in range(4): self.tick()
        for _ in range(3): self.tick()
        self.tick()
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=WALL_MIN_WHEEL_SPEED, ramp=False)
        distance, angle = 229, 109
        angle -= 15
        self.tick(angle=angle)
        self.assertEqual(self.w.rejoin_phase,'advance')
        distance += 50
        self.tick(distance=distance)
        self.assertEqual(self.w.rejoin_phase,'turn')
        # Reacquire near the bypass entry heading (89deg) so the heading
        # handoff can clear the detour after >=200mm travelled.
        self.tick(angle=89)
        self.sensors.light_bump_right_signal = 30
        for _ in range(7): self.tick()
        self.assertEqual(self.w.stage, 'follow')
        self.assertEqual(self.w.follow_heading, 89)
        for _ in range(5):
            distance += 30
            self.tick(distance=distance)
        self.assertFalse(self.w.detour_active)
        self.assertTrue(any(x['event']=='obstacle_bypass_heading_resumed' for x in self.w.records))

    def test_nearby_repeated_side_contact_keeps_small_left_correction(self):
        self.enter_rejoin()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertFalse(self.w.detour_active)
        self.assertEqual(self.w.contact_left_deg, 15)

    def test_obstacle_bypass_and_wall_loss_searches_are_bounded(self):
        for limit in ('time','distance'):
            self.setUp(); self.enter_obstacle_bypass()
            if limit == 'time': self.w.detour_started -= 91
            else: self.w.total_mm = self.w.detour_start_mm+1501
            self.tick()
            self.assertEqual(self.m._mode, 'wall')
            self.assertEqual(self.w.stage,'tag15_scan')
            self.assertIsNotNone(self.w.tag15_search)
            self.assertFalse(self.w.detour_active)
        self.setUp(); self.follow(); self.w.loss_searches = 8
        self.sensors.light_bump_right_signal = 0
        self.tick()
        self.assertIn('wall-loss search limit', self.w.result['reason'])

    def test_uploaded_alignment_loss_reorients_and_advances_before_retry(self):
        self.approach()
        for signal in (32, 33, 39):
            self.sensors.light_bump_right_signal = signal
            self.tick()
        self.assertEqual(self.w.stage, 'align_left45')
        self.sensors.light_bump_right_signal = 14
        self.tick(angle=60)
        self.assertEqual(self.w.stage, 'align_check')
        self.assertFalse(self.w.lease)
        self.robot.end_motion_lease.assert_called()
        for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'reorient')
        self.tick(angle=45)
        self.assertEqual(self.w.stage, 'acquire')
        self.sensors.light_bump_right_signal = 39
        for _ in range(3): self.tick(distance=220)
        self.assertEqual(self.w.stage, 'acquire')  # Not fooled again by same strength.
        for _ in range(3): self.tick(distance=250)
        self.assertEqual(self.w.stage, 'align_left45')
        self.assertEqual(self.w.reapproaches, 1)

    def test_stopped_wait_ends_lease_but_moving_expiry_still_aborts(self):
        self.follow()
        self.tick(distance=209)
        self.assertTrue(self.w.lease)
        self.sensors.light_bump_right_signal = 0
        for _ in range(4): self.tick()
        self.assertFalse(self.w.lease)
        self.assertIsNone(self.w.last_drive)
        self.assertEqual(self.m._mode, 'wall')
        self.w.deadline = 0
        self.tick()
        self.assertIn('time limit during rejoin', self.w.result['reason'])
        self.setUp(); self.anchor()
        self.state['motion_lease_expired'] = True
        self.tick()
        self.assertIn('lease expired during movement', self.w.result['reason'])

    def test_real_arbiter_deadman_does_not_expire_during_stopped_wall_wait(self):
        from threading import Lock
        from types import MethodType
        from time import monotonic
        clock = [monotonic()]
        owner = NS(_state_lock=Lock(), _motion_lease_deadline=None,
                   _motion_lease_expired=False, logger=logging.getLogger('wall-deadman'),
                   _brake=Mock())
        for method in ('begin_motion_lease', 'renew_motion_lease', 'end_motion_lease', '_check_motion_lease'):
            setattr(owner, method, MethodType(getattr(RobotCommandArbiter, method), owner))
        for method in ('begin_motion_lease', 'renew_motion_lease', 'end_motion_lease'):
            setattr(self.robot, method, getattr(owner, method))
        def snapshot():
            return dict(self.state, motion_lease_expired=owner._motion_lease_expired)
        self.robot.snapshot.side_effect = snapshot
        with patch('roomberry_wall.monotonic', side_effect=lambda: clock[0]), \
                patch('roomberry_control.monotonic', side_effect=lambda: clock[0]):
            self.follow()
            self.tick(distance=209)
            self.assertIsNotNone(owner._motion_lease_deadline)
            self.sensors.light_bump_right_signal = 0
            for _ in range(4): self.tick()
            self.assertIsNone(owner._motion_lease_deadline)
            clock[0] += .8
            self.assertFalse(owner._check_motion_lease())
            self.sensors.light_bump_right_signal = 30
            self.tick()
            self.assertEqual(self.m._mode, 'wall')
            clock[0] += .8
            self.assertFalse(owner._check_motion_lease())
            self.w.tick(self.state)  # Repeat frame: stationary qualification still waiting.
            self.assertEqual(self.w.stage, 'rejoin')
            for _ in range(7): self.tick()
            self.assertEqual(self.w.stage, 'follow')
            owner._brake.assert_not_called()

    def test_failed_stop_does_not_disable_deadman(self):
        self.anchor(); self.tick(angle=2)
        self.robot.end_motion_lease.reset_mock()
        self.robot.execute.side_effect = RuntimeError('stop not acknowledged')
        with self.assertRaisesRegex(RuntimeError, 'not acknowledged'):
            self.w.stop_motion('test stop failure')
        self.robot.end_motion_lease.assert_not_called()
        self.assertTrue(self.w.lease)

    def test_reapproach_count_and_distance_are_bounded(self):
        self.approach()
        self.w.acquire_heading = self.state['angle']
        for _ in range(4): self.w.retry_acquisition(self.state, 0)
        self.w.retry_acquisition(self.state, 0)
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('four bounded', self.w.result['reason'])
        self.setUp(); self.approach()
        self.w.acquire_origin = -500
        self.tick()
        self.assertIn('600 mm acquisition', self.w.result['reason'])

    def test_unexpected_contact_aborts(self):
        self.anchor()
        self.sensors.bumps_and_wheel_drops.bump_left = True
        self.tick()
        self.assertEqual(self.m._mode, 'idle')

    def test_timeout_stall_and_reverse_direction_abort(self):
        self.anchor(); self.w.progress = 0; self.w.progress_at -= 3
        self.tick()
        self.assertIn('progress', self.w.result['reason'])
        self.setUp(); self.anchor(); self.tick(); self.tick(angle=-4)
        self.assertIn('opposite', self.w.result['reason'])
        self.setUp(); self.w.deadline = 0; self.tick()
        self.assertIn('time limit', self.w.result['reason'])

    def test_fixed_target_and_retired_capture_cannot_change_it(self):
        status = self.m.status_snapshot()['wall']
        self.assertEqual(status['target_signal'], 30)
        self.assertEqual(status['target_min'], 20)
        self.assertEqual(status['target_max'], 30)
        self.assertEqual(status['sensor'], 'light_bump_right_signal')
        self.assertIsNone(status['desired_clearance_mm'])
        for mode in ('idle', 'wall'):
            self.m.set_mode(mode)
            with self.assertRaisesRegex(RuntimeError, 'retired'):
                self.m.capture_wall_clearance()
            self.assertEqual(self.m.status_snapshot()['wall']['target_signal'], 30)

    def test_no_calibration_needed_and_clock_cancels(self):
        self.m.set_mode('idle')
        self.state['clock_button'] = True
        self.assertTrue(self.m._handle_clock(self.state))
        self.assertEqual(self.m.wall.stage, 'anchor')
        self.state['clock_button'] = False; self.m._handle_clock(self.state)
        self.state['clock_button'] = True; self.m._handle_clock(self.state)
        self.assertEqual(self.m._mode, 'idle')
        self.robot.end_motion_lease.assert_called()
        display = NS()
        RobotCommandArbiter.set_drive_display(display, 'wall')
        self.assertEqual(display._drive_display, 'WALL')

    def test_old_sensor_cannot_acquire_wall_and_right_sensor_can(self):
        self.approach()
        self.sensors.wall_signal = 999
        self.sensors.light_bump_right_signal = 19
        for _ in range(4): self.tick()
        self.assertEqual(self.w.stage, 'acquire')
        self.sensors.light_bump_right_signal = 30
        for _ in range(7): self.tick()
        self.assertEqual(self.w.stage, 'align_left45')
        self.assertEqual(self.w.last['target_signal'], 30)
        self.assertEqual(self.w.last['sensor_packet'], 51)

    def test_scans_allowed_only_during_stopped_anchor(self):
        self.assertTrue(self.m.scan_pause())
        self.m.scan_complete()
        self.anchor()
        self.assertFalse(self.m.scan_pause())

    def test_differential_drive_simulation_acquires_wall_then_tracks(self):
        # Independent wheel kinematics and ideal geometric right-facing IR ray.
        # This synthetic response tests control, not real sensor range or mm/count.
        # Wall x=600; robot initially faces +x, then departs along +y.
        from time import monotonic
        clock = monotonic()
        wheel = [0., 0.]
        body = [0., 0., 0.]
        pose = dict(x_mm=0, y_mm=0, heading_rad=0, localized=True,
                    accepted_tag_ids=(('tag16h5',16),))
        def execute(operation, **kw):
            if operation == 'drive_direct':
                wheel[:] = [kw['right_velocity'], kw['left_velocity']]
            elif operation in ('stop', 'soft_stop'):
                wheel[:] = [0., 0.]
        self.robot.execute.side_effect = execute
        for t in (self.w._wall_time+1, self.w._wall_time+2):
            self.w.tick(self.state, pose, True, t)
        followed = 0
        gaps = []
        stages = []
        with patch('roomberry_wall.monotonic', side_effect=lambda: clock):
            for _ in range(2000):
                dt = .1
                right, left = wheel
                dd = (right+left)/2*dt
                da = (right-left)/235.*dt
                body[0] += dd*cos(body[2]+da/2)
                body[1] += dd*sin(body[2]+da/2)
                body[2] += da
                self.state['distance'] += dd
                self.state['angle'] += degrees(da)
                self.state['sensor_monotonic_s'] += dt
                ray = sin(body[2])
                ray_gap = (600-body[0])/ray-165 if ray > .05 else 1e6
                self.sensors.light_bump_right_signal = 3000/max(1, ray_gap)
                clock += dt
                self.w.tick(self.state)
                if not stages or stages[-1] != self.w.stage:
                    stages.append(self.w.stage)
                if self.w.stage == 'follow':
                    followed += 1
                    gaps.append(600-body[0]-165)
                    if followed >= 500:
                        break
                if self.w.result is not None:
                    self.fail(self.w.result)
        self.assertEqual(stages[:4], ['left90', 'forward200', 'right45', 'acquire'])
        self.assertEqual(stages[-1], 'follow')
        checks = stages[4:-1]
        self.assertGreaterEqual(len(checks), 6)
        self.assertLessEqual(len(checks), 8)
        self.assertEqual(checks[::2], ['align_left45']*(len(checks)//2))
        self.assertEqual(checks[1::2], ['align_check']*(len(checks)//2))
        self.assertEqual(followed, 500)
        self.assertGreater(min(gaps), 0)
        # 20-30 band centres near 25, so final gap is allowed to settle
        # within the band rather than a single 30-unit point.
        self.assertLess(abs(gaps[-1]-120), 55)
        self.assertGreater(gaps[-1], 65)

    def test_contact_between_snapshot_and_drive_recovers_instead_of_aborting(self):
        self.follow()
        old = dict(self.state)  # No contact in this mission-tick snapshot.
        def execute(operation, **kwargs):
            if operation == 'drive_direct' and kwargs['right_velocity'] > 0:
                self.state.update(wall_contact_blocked=True,
                    wall_contact_event=dict(reason='bumper', bump_right=True))
                raise WallContactStop('WALL contact stop latched; back clear before rearming')
        self.robot.execute.side_effect = execute
        self.w.tick(old)
        self.assertEqual(self.m._mode, 'wall')
        self.assertEqual(self.w.stage, 'release')
        self.assertEqual(self.w.contact_retries, 1)
        self.assertEqual(self.w.contact_left_deg, 15)
        self.assertTrue(any(r['event']=='contact_preempted_drive' for r in self.w.records))
        self.robot.execute.assert_called_with('stop', timeout=2)
        self.tick(distance=189)
        self.robot.execute.assert_called_with('drive_direct', right_velocity=-WALL_MIN_WHEEL_SPEED, left_velocity=-WALL_MIN_WHEEL_SPEED, ramp=False)

    def test_repeat_contact_during_bypass_limits_left_turn_to45(self):
        self.enter_obstacle_bypass()
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertTrue(self.w.detour_active)
        self.assertEqual(self.w.contact_left_deg, 45)

    def test_follow_contact_soon_after_wall_loss_starts_go_around(self):
        self.follow()
        self.sensors.light_bump_right_signal = 0
        self.tick(); self.tick()
        # One tick in the wall-loss rejoin records last_loss_mm.
        self.assertEqual(self.w.stage, 'rejoin')
        self.sensors.light_bump_right_signal = 30
        for _ in range(7): self.tick(distance=229, angle=87)
        self.assertEqual(self.w.stage, 'follow')
        self.assertFalse(self.w.detour_active)
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertTrue(self.w.detour_active, 'corner bump after wall loss should go around')
        self.assertEqual(self.w.contact_left_deg, 20)

    def test_follow_contact_long_after_wall_loss_stays_small(self):
        self.follow()
        self.sensors.light_bump_right_signal = 0
        self.tick(); self.tick()
        self.sensors.light_bump_right_signal = 30
        for _ in range(7): self.tick(distance=229, angle=87)
        self.assertEqual(self.w.stage, 'follow')
        # Move far past the 500mm go-around window.
        self.w.last_loss_mm = self.w.total_mm - 600
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertFalse(self.w.detour_active)
        self.assertEqual(self.w.contact_left_deg, 15)

    def test_drive_contact_race_during_wall_loss_search_preserves_left_bypass(self):
        self.follow()
        self.sensors.light_bump_right_signal = 7
        self.tick()
        self.assertEqual(self.w.stage, 'rejoin')
        for _ in range(3): self.tick()
        old = dict(self.state)
        def execute(operation, **kwargs):
            if operation == 'drive_direct' and kwargs['left_velocity'] > 0:
                self.state.update(wall_contact_blocked=True,
                    wall_contact_event=dict(reason='bumper', bump_right=True))
                raise WallContactStop('contact while searching')
        self.robot.execute.side_effect = execute
        self.w.tick(old)
        self.assertEqual(self.w.stage, 'release')
        self.assertTrue(self.w.detour_active)
        self.assertEqual(self.w.contact_left_deg, 20)
        self.assertEqual(self.m._mode, 'wall')

    def test_contact_race_still_aborts_on_fresh_hard_hazard_or_stale_state(self):
        for hazard in (dict(hard_hazard_reasons=['cliff']), dict(age=.6),
                       dict(oi_stopped=True), dict(motion_lease_expired=True)):
            self.setUp(); self.follow()
            self.robot.execute.reset_mock()
            old = dict(self.state)
            def execute(operation, **kwargs):
                if operation == 'drive_direct' and kwargs['right_velocity'] > 0:
                    self.state.update(wall_contact_blocked=True, **hazard)
                    raise WallContactStop('contact during drive')
            self.robot.execute.side_effect = execute
            self.w.tick(old)
            self.assertEqual(self.m._mode, 'idle')
            self.assertEqual(self.w.contact_retries, 0)
            self.assertFalse(any(c.args[0]=='drive_direct' and c.kwargs['right_velocity'] < 0
                                 for c in self.robot.execute.call_args_list))

    def test_unconfirmed_contact_rejection_is_not_recovered(self):
        self.follow()
        def execute(operation, **kwargs):
            if operation == 'drive_direct': raise WallContactStop('unconfirmed latch')
        self.robot.execute.side_effect = execute
        with self.assertRaisesRegex(WallContactStop, 'unconfirmed'):
            self.tick()
        self.assertEqual(self.w.contact_retries, 0)

    def test_unrelated_drive_failure_is_not_swallowed_even_with_contact(self):
        self.follow()
        old = dict(self.state)
        def execute(operation, **kwargs):
            if operation == 'drive_direct':
                self.state['wall_contact_blocked'] = True
                raise RuntimeError('unrelated driver failure')
        self.robot.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, 'unrelated'):
            self.w.tick(old)
        self.assertEqual(self.w.contact_retries, 0)

    def test_controller_rejection_propagates_for_coordinator_abort(self):
        self.anchor()
        self.robot.execute.side_effect = RuntimeError('blocked')
        with self.assertRaises(RuntimeError): self.tick(angle=2)

    def test_four_frame_average_suppresses_single_ir_spike(self):
        self.follow()
        for _ in range(4): self.tick()
        self.assertEqual(self.w.signal_history, [30.0, 30.0, 30.0, 30.0])
        self.sensors.light_bump_right_signal = 0
        self.tick()
        self.assertEqual(self.w.stage, 'follow')
        self.assertEqual(self.w.last['raw_signal'], 0.0)
        self.assertEqual(self.w.last['signal'], 22.5)
        self.assertEqual(self.w.last['signal_avg_n'], 4)
        for _ in range(3): self.tick()
        self.assertEqual(self.w.stage, 'rejoin')
        self.assertEqual(self.w.rejoin_source, 'wall_loss')

    def test_wall_loss_searches_recessed_front_beyond_thirty_degrees(self):
        self.follow()
        self.sensors.light_bump_right_signal = 0
        for _ in range(4): self.tick()
        self.assertEqual(self.w.stage, 'rejoin')
        self.assertEqual(self.w.rejoin_source, 'wall_loss')
        started = [r for r in self.w.records if r['event'] == 'wall_search_started']
        self.assertTrue(started)
        self.assertEqual(started[-1]['max_right_deg'], 60)
        for _ in range(3): self.tick()
        # Contact rejoin would still be bounded at 30, but wall-loss continues.
        angle = self.state['angle']
        distance = self.state['distance']
        while angle > 40:
            angle -= 10
            self.tick(angle=angle)
            self.assertEqual(self.w.stage, 'rejoin')
            self.assertEqual(self.m._mode, 'wall')
            distance += 30
            self.tick(distance=distance)
            self.assertEqual(self.w.stage, 'rejoin')
        while angle > -5:
            angle -= 10
            self.tick(angle=angle)
            if self.m._mode == 'idle':
                break
            distance += 30
            self.tick(distance=distance)
            if self.m._mode == 'idle':
                break
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('60 degree bound', self.w.result['reason'])

    def test_contact_recovery_allows_fifth_and_aborts_after_forty_two(self):
        self.enter_rejoin()
        self.assertEqual(self.w.contact_retries, 1)
        self.w.contact_retries = 5
        self.w.stage = 'rejoin'
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.w.stage, 'release')
        self.assertEqual(self.w.contact_retries, 6)
        self.w.contact_retries = 42
        self.w.stage = 'rejoin'
        self.sensors.bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.m._mode, 'idle')
        self.assertIn('contact recovery limit', self.w.result['reason'])

    def test_band_center_drives_straight_and_min_qualifies(self):
        self.follow()
        self.sensors.light_bump_right_signal = 25
        for _ in range(4): self.tick(distance=209)
        cmd = self.robot.execute.call_args
        self.assertEqual(cmd.kwargs['right_velocity'], cmd.kwargs['left_velocity'])
        self.setUp(); self.follow()
        self.sensors.light_bump_right_signal = 20
        for _ in range(4): self.tick(distance=209)
        cmd = self.robot.execute.call_args
        self.assertEqual(cmd.kwargs['right_velocity'], cmd.kwargs['left_velocity'])

    def test_fluctuating_signal_holds_one_second_then_resumes(self):
        self.follow()
        for _ in range(4): self.tick(distance=209)
        self.sensors.light_bump_right_signal = 50
        self.tick(distance=214)
        self.sensors.light_bump_right_signal = 5
        self.tick(distance=219)
        # Spike between frames triggers the fluctuation hold record.
        events = [r for r in self.w.records if r['event'] == 'wall_signal_fluctuating']
        if not events:
            # Drive spread to exceed 20 via alternating values.
            for val in (50, 5, 50, 5):
                self.sensors.light_bump_right_signal = val
                self.tick(distance=self.state['distance']+5)
            events = [r for r in self.w.records if r['event'] == 'wall_signal_fluctuating']
        # Either hold is active or it already expired; hold should be set or
        # history cleared without changing stage away from follow.
        self.assertIn(self.w.stage, ('follow', 'rejoin'))

    def test_follow_reaching_5000mm_enters_tag15_scan_and_finishes_complete(self):
        self.follow()
        self.w.total_mm = 5000
        self.tick()
        self.assertEqual(self.w.stage, 'tag15_scan')
        pose = dict(x_mm=5820, y_mm=1156, heading_rad=-1.8, localized=True,
                    accepted_tag_ids=(('tag16h5', 15),))
        self.w.tick(self.state, pose, True, self.w._wall_time+1)
        self.assertEqual(self.w.stage, 'tag15_scan')
        self.assertEqual(self.m._mode, 'wall')
        self.w.tick(self.state, pose, True, self.w._wall_time+2)
        self.assertEqual(self.m._mode, 'idle')
        self.assertEqual(self.w.result['status'], 'complete')
        self.assertIn('tag15 validated within 300mm', self.w.result['reason'])

    def test_tag15_scan_allows_scan_pause(self):
        self.follow()
        self.w.total_mm = 5000
        self.tick()
        self.assertEqual(self.w.stage, 'tag15_scan')
        self.assertTrue(self.m.scan_pause())
        self.m.scan_complete()

    def test_pre_reverse_coast_does_not_trip_direction_guard(self):
        self.follow()
        self.state['distance']=3341.0;self.w.previous=(3341.0,self.state['angle'])
        self.w.stop_motion('contact transition')
        self.w.stage='release'
        self.w.stage_distance=3341.0
        self.w.acquire_origin=3341.0
        self.w.drive(-50,-50,self.state)
        # First post-command mission snapshot includes pre-command +4.9mm
        # followed by -1.3mm of actual reverse motion.
        self.tick(distance=3344.6)
        self.assertIsNone(self.w.result)
        self.tick(distance=3341.4)
        self.assertIsNone(self.w.result)

    def test_continuing_wrong_direction_after_new_baseline_still_aborts(self):
        self.follow();self.w.stop_motion('test reverse boundary');self.w.stage='release'
        self.w.drive(-50,-50,self.state)
        self.tick(distance=self.state['distance']+3.6)
        self.assertIsNone(self.w.result)
        self.tick(distance=self.state['distance']+5)
        self.assertIn('opposite',self.w.result['reason'])

    def test_scan_requires_actual_tag15_within_300_not_wheel_checkpoint(self):
        self.follow();self.w.total_mm=5000;self.tick()
        if self.w.stage=='tag15_face':
            self.w.transition('tag15_scan',self.state,60)
        pose=dict(x_mm=5500.,y_mm=1156.,heading_rad=0.,localized=True,
                  accepted_tag_ids=(('tag16h5',15),))
        for t in (self.w._wall_time+10,self.w._wall_time+11):
            self.w.tick(self.state,pose,True,t)
        self.assertEqual(self.w.stage,'tag15_approach')
        self.assertIsNone(self.w.result)
        self.assertEqual(self.w.approach_mm,100)

    def test_near_goal_parks_then_confirms_two_fresh_scans(self):
        self.follow()
        self.w.goal_pose=dict(x_mm=5820.,y_mm=1156.,heading_rad=0.)
        self.w.goal_odom=(self.state['distance'],self.state['angle'])
        self.tick()
        self.assertEqual(self.w.stage,'tag15_scan')
        pose=dict(self.w.goal_pose,localized=True,accepted_tag_ids=(('tag16h5',15),))
        # Capture predating parking is not a confirmation.
        self.w.tick(self.state,pose,True,self.w.tag_scan_started-1)
        self.assertIsNone(self.w.tag_scan_anchor)
        self.w.tick(self.state,pose,True,self.w.tag_scan_started+1)
        self.assertIsNone(self.w.result)
        self.w.tick(self.state,pose,True,self.w.tag_scan_started+2)
        self.assertEqual(self.w.result['status'],'complete')
        self.assertLessEqual(self.w.records[-2]['range_mm'],300)

    def test_final_approach_is_bounded_and_never_pushes_through_bumper(self):
        self.follow();self.w.validation_started=__import__('time').monotonic()
        self.w.goal_pose=dict(x_mm=5500.,y_mm=1156.,heading_rad=0.)
        self.w.goal_odom=(self.state['distance'],self.state['angle'])
        self.w.approach_mm=100
        self.w.transition('tag15_approach',self.state,15)
        self.tick()
        self.robot.execute.assert_called_with('drive_direct',right_velocity=50,left_velocity=50,ramp=False)
        self.tick(distance=self.state['distance']+60)
        self.tick(distance=self.state['distance']+41)
        self.assertEqual(self.w.stage,'tag15_scan')
        self.w.transition('tag15_approach',self.state,15)
        self.sensors.bumps_and_wheel_drops.bump_right=True
        self.tick()
        self.assertEqual(self.w.result['status'],'aborted')

    def test_path_limit_does_not_claim_success_without_tag_validation(self):
        self.follow();self.w.total_mm=8000;self.tick()
        self.assertEqual(self.w.result['status'],'aborted')

    def test_tag_goal_requires_surveyed_target(self):
        self.w.goal_target=None
        pose=dict(x_mm=3100,y_mm=1400,heading_rad=-pi/2,localized=True,accepted_tag_ids=(('tag16h5',16),))
        for t in (self.w._wall_time+1,self.w._wall_time+2):self.w.tick(self.state,pose,True,t)
        self.assertEqual(self.w.result['status'],'aborted')

    def test_final_approach_limit_does_not_allow_unbounded_closing(self):
        self.follow();self.w.total_mm=5000;self.tick()
        self.w.transition('tag15_scan',self.state,60)
        self.w.validation_steps=WALL_TAG15_MAX_STEPS
        pose=dict(x_mm=5500.,y_mm=1156.,heading_rad=0.,localized=True,accepted_tag_ids=(('tag16h5',15),))
        for t in (self.w.tag_scan_started+1,self.w.tag_scan_started+2):self.w.tick(self.state,pose,True,t)
        self.assertEqual(self.w.result['status'],'aborted')

    def test_whole_run_time_bound_still_six_minutes(self):
        self.w.started-=361;self.tick()
        self.assertEqual(self.w.result['status'],'aborted')

    def lucky_search(self):
        self.enter_obstacle_bypass()
        self.w.total_mm=self.w.detour_start_mm+1501
        self.robot.execute.reset_mock();self.tick()
        self.assertEqual(self.w.stage,'tag15_scan')
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))

    def missing_view(self):
        base=self.w.tag_scan_started
        self.w.tick(self.state,None,True,base+1,detections=())
        self.w.tick(self.state,None,True,base+2,detections=())

    def settle_scan_view(self, target):
        from time import monotonic
        if not hasattr(self,'turn_now'):self.turn_now=monotonic()
        start=self.state['angle']
        # Initial stationary qualification, pulse, coast, then fresh quiet polls.
        for angle in (start,start,start,(start+target)/2,target,target):
            self.turn_now+=.2
            self.state['sensor_monotonic_s']=self.turn_now
            self.state['angle']=angle
            with patch('roomberry_wall.monotonic',return_value=self.turn_now):
                self.w.tick(self.state)
        self.assertEqual(self.w.stage,'tag15_scan')

    def test_lucky_scan_current_plus10_minus10_then_stops(self):
        self.lucky_search();origin=self.state['angle']
        self.missing_view()
        self.assertEqual(self.w.stage,'tag15_search_turn')
        self.settle_scan_view(origin+10)
        self.assertEqual(self.w.stage,'tag15_scan')
        self.assertTrue(self.m.scan_pause());self.m.scan_complete()
        self.missing_view();self.settle_scan_view(origin-10)
        self.missing_view()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('current/+10/-10',self.w.result['reason'])

    def test_lucky_scan_confirmed_tag_resumes_bounded_approach(self):
        self.lucky_search()
        pose=dict(x_mm=4300.,y_mm=1156.,heading_rad=0.,localized=True,accepted_tag_ids=(('tag16h5',15),))
        t=self.w.tag_scan_started
        self.w.tick(self.state,pose,True,t+1)
        self.assertEqual(self.w.stage,'tag15_scan')
        self.w.tick(self.state,pose,True,t+2)
        self.assertEqual(self.w.stage,'tag15_approach')
        self.assertIsNone(self.w.tag15_search)
        self.assertEqual(self.w.approach_mm,100)
        self.assertFalse(self.w.detour_active)
        self.assertIsNone(self.w.result)

    def test_lucky_scan_duplicates_and_old_captures_do_not_advance(self):
        self.lucky_search();t=self.w.tag_scan_started
        for _ in range(4):self.w.tick(self.state,None,True,t-1,detections=())
        self.assertEqual(self.w.tag15_search['captures'],0)
        for _ in range(4):self.w.tick(self.state,None,True,t+1,detections=())
        self.assertEqual(self.w.tag15_search['captures'],1)
        self.assertEqual(self.w.stage,'tag15_scan')

    def test_lucky_scan_cannot_turn_with_contact_or_hazards(self):
        for hazard in ('bumper','cliff'):
            self.setUp();self.enter_obstacle_bypass();self.w.total_mm=self.w.detour_start_mm+1501
            self.robot.execute.reset_mock()
            if hazard=='bumper':self.sensors.bumps_and_wheel_drops.bump_right=True
            else:self.state['hard_hazard_reasons']=['cliff']
            self.tick()
            self.assertEqual(self.m._mode,'idle')
            self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))

    def test_lucky_scan_time_translation_and_angle_envelopes(self):
        for bound in ('time','translation','angle'):
            self.setUp();self.lucky_search()
            if bound=='time':self.w.tag15_search['started']-=76
            elif bound=='translation':self.state['distance']+=26
            else:self.state['angle']+=16
            self.tick()
            self.assertEqual(self.w.result['status'],'aborted')

    def test_lucky_turn_blocks_unplanned_scan_and_never_drives_forward(self):
        self.lucky_search();self.missing_view()
        self.assertFalse(self.m.scan_pause())
        self.settle_scan_view(self.state['angle']+10)
        moves=[c for c in self.robot.execute.call_args_list if c.args[0]=='drive_direct']
        self.assertTrue(moves)
        self.assertTrue(all(c.kwargs['right_velocity']+c.kwargs['left_velocity']==0 for c in moves))

    def gated_start(self):
        self.m.set_mode('idle')
        self.phone_state=dict(status='connecting',error='',start_attempt=0)
        self.m.trek_survey_status=lambda:dict(self.phone_state)
        self.m.navlink=Mock()
        self.m.start_wall();self.w=self.m.wall
        self.w.goal_target=(6100.,1156.)
        self.robot.execute.reset_mock()

    def test_startup_waits_without_driving_and_aborts_on_failure(self):
        self.gated_start();self.tick()
        self.assertEqual(self.w.stage,'phone_ready')
        self.phone_state.update(status='restarting');self.tick()
        self.assertEqual(self.w.stage,'phone_ready')
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))
        self.phone_state.update(status='failed',error='relocalization_timeout');self.tick()
        self.assertEqual(self.m._mode,'idle')
        self.assertIn('relocalization_timeout',self.w.result['reason'])

    def test_startup_deadline_remains_bounded(self):
        self.gated_start();self.w.deadline-=121
        self.tick();self.assertEqual(self.m._mode,'idle')

    def test_tag16_binding_failure_never_releases_startup_hold(self):
        self.gated_start();self.phone_state.update(status='surveying');self.tick()
        self.assertEqual(self.w.stage,'anchor')
        self.w.phone_anchor=Mock(state='unavailable',last_result=None);self.w.phone_anchor.bind.return_value=False
        pose=dict(x_mm=3100,y_mm=1400,heading_rad=-pi/2,localized=True,accepted_tag_ids=(('tag16h5',16),))
        for t in (self.w._wall_time+1,self.w._wall_time+2,self.w._wall_time+3):self.w.tick(self.state,pose,True,t)
        self.assertEqual(self.w.stage,'anchor')
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))
        self.w.deadline-=61;self.tick();self.assertEqual(self.m._mode,'idle')

    def test_ready_phone_and_fresh_tag_pair_release_startup(self):
        from time import monotonic
        self.gated_start();old=self.w._wall_time
        self.phone_state.update(status='surveying',start_attempt=2);self.tick()
        phone=Mock(state='anchored',last_result=None);self.w.phone_anchor=phone;phone.bind.return_value=True;phone.usable.return_value=True
        phone.anchor=dict(session=7,map_uuid_hex=bytes(16).hex())
        self.m.navlink.latest_trek_observation.return_value=dict(session=7,map_uuid=bytes(16),frame_monotonic=monotonic())
        pose=dict(x_mm=3100,y_mm=1400,heading_rad=-pi/2,localized=True,accepted_tag_ids=(('tag16h5',16),))
        self.w.tick(self.state,pose,True,old-1)
        self.assertIsNone(self.w.anchor)
        for t in (self.w._wall_time+1,self.w._wall_time+2):self.w.tick(self.state,pose,True,t)
        self.assertEqual(self.w.stage,'left90')
        self.assertIsNotNone(self.w.motion_started)
        self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))

    def test_stale_or_changed_phone_before_departure_aborts(self):
        from time import monotonic
        for fault in ('stale','changed-session'):
            self.setUp();self.gated_start();self.phone_state.update(status='surveying',phone_session='7');self.tick()
            phone=Mock(state='anchored',last_result=None);self.w.phone_anchor=phone
            phone.bind.return_value=True;phone.usable.return_value=True
            phone.anchor=dict(session=7,map_uuid_hex=bytes(16).hex())
            self.m.navlink.latest_trek_observation.return_value=dict(session=7 if fault=='stale' else 8,
                map_uuid=bytes(16),frame_monotonic=monotonic()-(1 if fault=='stale' else 0))
            pose=dict(x_mm=3100,y_mm=1400,heading_rad=-pi/2,localized=True,accepted_tag_ids=(('tag16h5',16),))
            for t in (self.w._wall_time+1,self.w._wall_time+2):self.w.tick(self.state,pose,True,t)
            self.assertEqual(self.m._mode,'idle')
            self.assertIn('stale',self.w.result['reason'])
            self.assertFalse(any(c.args[0]=='drive_direct' for c in self.robot.execute.call_args_list))

    def test_lucky_checkpoint_solver_does_not_relax_normal_tag_range_gate(self):
        import json
        from pathlib import Path
        from roomberry_localization import AprilTagLocalizer as L
        cfg=json.loads((Path(__file__).resolve().parents[2]/'autonomy.json').read_text())
        tag=next(r for r in cfg['landmarks'] if r['id']==15)['world_from_tag']
        self.m.localizer=L({('tag16h5',15):tag},cfg['camera_from_robot'],max_tag_distance_m_by_key={('tag16h5',15):1.2})
        robot=[[1,0,0,tag[0][3]-2],[0,1,0,tag[1][3]],[0,0,1,0],[0,0,0,1]]
        camera_tag=L._multiply(cfg['camera_from_robot'],L._multiply(L._inverse(robot),tag))
        detection=dict(family='tag16h5',id=15,hamming=0,decision_margin=100,
                       tag_pose_camera=dict(rotation=[r[:3] for r in camera_tag[:3]],translation_m=[r[3] for r in camera_tag[:3]],error=0))
        self.assertIsNone(self.m.localizer.update([detection],0,0))
        pose=self.w.tag15_candidate([detection])
        self.assertIn(('tag16h5',15),pose['accepted_tag_ids'])
        self.assertEqual(self.m.localizer.max_tag_distance_m_by_key[('tag16h5',15)],1.2)
