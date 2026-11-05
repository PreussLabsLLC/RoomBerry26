"""Measured local pad moves, retained trace, cancellation and safety guards."""
# @(#)roomberry_manual_step_test.py 3.1.grout.19 2026/11/05
import math
import unittest
from unittest.mock import patch
import roomberry_gridrunner_test as fixture


class ManualStepTest(unittest.TestCase):
    def setUp(self):
        self.g = fixture.GridDriveTest('test_line_end_brakes_outbound_then_reverses_without_docking')
        self.g.setUp()
        self.addCleanup(self.g.doCleanups)
        self.m, self.state = self.g.m, self.g.f.state
        self.m.set_mode('idle')
        self.wheels = (0,0)
        self.hook = None
        self.elapsed = 0.
        self.stationary = False
        self.reverse = False
        self.shutdown = False
        self.m._shutdown.is_set = lambda: self.shutdown
        self.m._shutdown.wait = self.advance
        self.m.robot_control.execute.side_effect = self.execute
        p = patch('roomberry_manual_step.monotonic', side_effect=lambda: self.g.f.now)
        p.start(); self.addCleanup(p.stop)

    def execute(self, operation, **kwargs):
        if operation == 'drive_direct':
            self.wheels = kwargs['left_velocity'], kwargs['right_velocity']
        elif operation in ('stop', 'soft_stop'):
            # Physical-run fixture: encoder lag/braking added about 12.5 mm
            # to translations and 3.2 degrees to in-place turns after stop.
            left, right = self.wheels
            sign = -1 if self.reverse else 1
            if left == right and left:
                self.state['distance'] += sign*(12.5 if left > 0 else -12.5)
            elif left*right < 0:
                self.state['angle'] += sign*(3.2 if right > left else -3.2)
            self.wheels = (0,0)

    def advance(self, seconds):
        self.g.f.now += seconds
        self.elapsed += seconds
        if self.elapsed >= .1-1e-9:
            left, right = self.wheels
            scale = -1 if self.reverse else 1
            if not self.stationary:
                self.state['distance'] += scale*(left+right)/2*self.elapsed
                self.state['angle'] += scale*math.degrees((right-left)/235*self.elapsed)
            self.elapsed = 0.
        if self.hook is not None:
            self.hook()
        return self.shutdown

    def test_four_directions_are_measured_and_braked(self):
        for direction, axis, target in [('forward','distance',50), ('backward','distance',-50),
                                         ('left','angle',5), ('right','angle',-5)]:
            with self.subTest(direction=direction):
                result = self.m.manual_step(direction)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['axis'], axis)
                self.assertLessEqual(abs(result['measured']-target), 2 if axis=='angle' else 6)
                self.assertEqual(self.wheels, (0,0))
                self.assertEqual(self.m._mode, 'idle')
                self.assertIsNone(self.m._manual_step)
                self.m.robot_control.end_motion_lease.assert_called()

    def test_stop_can_cancel_without_holding_coordinator_lock_for_entire_move(self):
        def stop():
            self.hook = None
            self.m.set_mode('idle')
        self.hook = stop
        result = self.m.manual_step('forward')
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.wheels, (0,0))
        self.assertEqual(self.m._mode, 'idle')

    def test_half_metre_steps_are_measured_and_stopped(self):
        for direction,target in (('forward_500',500),('backward_500',-500)):
            start=self.state['distance']
            result=self.m.manual_step(direction)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(result['target'],target)
            self.assertLess(abs(self.state['distance']-start-target),12)
            self.assertEqual(self.wheels,(0,0))
            self.assertIsNone(self.m._manual_step)

    def test_stop_can_interrupt_half_metre_step(self):
        def stop_after_progress():
            if self.elapsed > .05 or abs(self.state['distance']) > 30:
                self.hook=None
                self.m.set_mode('idle')
        self.hook=stop_after_progress
        result=self.m.manual_step('forward_500')
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(self.wheels,(0,0))

    def test_other_manual_command_takes_over_without_old_cleanup_stopping_it(self):
        def replace():
            self.hook = None
            self.m.take_manual_control()
            self.m.robot_control.execute('drive_direct', left_velocity=60, right_velocity=60)
        self.hook = replace
        result = self.m.manual_step('forward')
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.wheels, (60,60))

    def test_duplicate_step_is_rejected(self):
        def duplicate():
            self.hook = None
            with self.assertRaisesRegex(RuntimeError, 'already running'):
                self.m.manual_step('left')
        self.hook = duplicate
        self.assertEqual(self.m.manual_step('forward')['status'], 'complete')

    def test_trace_tracks_manual_movement_and_return_can_resume(self):
        self.m.set_mode('gridrunner')
        self.g.g = self.m.gridrunner
        self.g.begin_return()
        run = self.m.gridrunner
        before = dict(run.pose)
        self.m.manual_step('forward')
        self.assertGreater(run.pose['x_mm'], before['x_mm']+40)
        self.assertAlmostEqual(run.odom[0], self.state['distance'])
        self.m.manual_step('left')
        self.assertGreater(run.pose['heading_rad'], before['heading_rad']+.07)
        self.g.refresh()
        self.m.return_to_tag15()
        self.assertEqual(self.m.gridrunner.pose, run.pose)
        self.assertEqual(self.m.gridrunner.kind, 'return_to_tag15')
        self.assertEqual(self.m.gridrunner.stage, 'scanning')

    def test_explicit_restart_discards_trace_and_waits_for_ready_sensors(self):
        self.m.set_mode('gridrunner')
        self.g.g = self.m.gridrunner
        self.g.begin_return()
        self.state.update(oi_stopped=True,ready=False)
        self.m.restart_oi()
        self.assertEqual(self.m._mode, 'idle')
        self.assertIsNone(self.m.gridrunner)
        self.m.robot_control.execute.assert_any_call('restart_oi')
        with self.assertRaises(RuntimeError):
            self.m.start_gridrunner()
        self.state.update(oi_stopped=False,ready=True)
        self.m.start_gridrunner()
        self.assertEqual(self.m._mode, 'gridrunner')
        self.assertEqual(self.m.gridrunner.stage, 'waiting')

    def test_unsafe_start_and_active_scan_never_drive(self):
        self.state['age'] = 1
        with self.assertRaises(RuntimeError):
            self.m.manual_step('forward')
        self.state['age'] = 0
        self.m._scan_active = True
        with self.assertRaises(RuntimeError):
            self.m.manual_step('left')
        self.assertEqual(self.wheels, (0,0))

    def test_sensor_loss_odometry_reset_and_bumper_during_move_brake(self):
        for hazard in ('stale','epoch','bumper'):
            with self.subTest(hazard=hazard):
                self.state.update(age=0,odometry_epoch=1)
                self.state['sensors'].bumps_and_wheel_drops.bump_left = False
                def change():
                    self.hook = None
                    if hazard=='stale':self.state['age'] = 1
                    elif hazard=='epoch':self.state['odometry_epoch'] = 2
                    else:self.state['sensors'].bumps_and_wheel_drops.bump_left = True
                self.hook = change
                with self.assertRaises(RuntimeError):
                    self.m.manual_step('forward')
                self.assertEqual(self.wheels, (0,0))
                self.assertEqual(self.m._mode, 'idle')

    def test_no_progress_and_wrong_direction_brake(self):
        self.stationary = True
        with self.assertRaisesRegex(RuntimeError, 'No wheel progress'):
            self.m.manual_step('forward')
        self.assertEqual(self.wheels, (0,0))
        self.stationary = False
        self.reverse = True
        with self.assertRaisesRegex(RuntimeError, 'opposite'):
            self.m.manual_step('left')
        self.assertEqual(self.wheels, (0,0))

    def test_brake_failure_keeps_independent_motion_lease(self):
        original = self.execute
        def fail_brake(operation, **kwargs):
            if operation == 'stop' and self.m._manual_step is not None:
                raise RuntimeError('serial unavailable')
            return original(operation, **kwargs)
        self.m.robot_control.execute.side_effect = fail_brake
        self.m.robot_control.end_motion_lease.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'serial unavailable'):
            self.m.manual_step('forward')
        self.m.robot_control.end_motion_lease.assert_not_called()
        self.assertIsNone(self.m._manual_step)
