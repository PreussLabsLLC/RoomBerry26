# @(#)roomberry_queued_control_test.py 2.3.18 2026/10/28 21:40:00
import logging
from threading import Event
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from roomberry_control import RobotCommandArbiter, STARTUP_SENSOR_SAMPLES
from irobot.tests.roomberry_control_test import FakeRobot


class QueuedControlTest(unittest.TestCase):
    def setUp(self):
        self.robot=FakeRobot()
        self.controller=RobotCommandArbiter(None,0,logging.getLogger('QueuedControl'),
                                          robot=self.robot,motion_ramp={'enabled':False})
        self.controller._startup_sensor_samples=STARTUP_SENSOR_SAMPLES
        self.controller._poll_sensors()

    def command(self, operation, **kwargs):
        cmd=dict(operation=operation,kwargs=kwargs,result=[],done=Event(),expires_at=monotonic()+5)
        self.controller._run_command(cmd)
        self.assertTrue(cmd['done'].is_set())
        if len(cmd['result'])==2:raise cmd['result'][1]
        return cmd

    def pickup(self):
        self.robot.stop=Mock()
        self.robot.auto_wake=True
        self.robot.packet.bumps_and_wheel_drops.wheel_drop_left=True
        self.controller._poll_sensors()

    def test_pickup_suspends_polls_wake_and_all_actuation(self):
        self.pickup()
        reads=self.robot.sensor_reads
        outputs=list(self.robot.drive_commands)
        for _ in range(5):self.controller._poll_sensors()
        self.controller.beep()
        self.assertEqual(self.robot.sensor_reads,reads)
        self.assertEqual(self.robot.drive_commands,outputs)
        self.robot.stop.assert_called_once_with()
        self.assertFalse(self.robot.auto_wake)
        self.assertTrue(self.controller.snapshot()['oi_stopped'])
        for op,kwargs in [('_change_mode',{'mode':2}),('drive_straight',{'velocity':40}),('set_song',{})]:
            with self.assertRaisesRegex(RuntimeError,'restart_oi'):self.command(op,**kwargs)
        self.controller.close()
        self.robot.stop.assert_called_once_with()

    def test_explicit_restart_requires_fresh_startup_and_restores_wake(self):
        self.pickup()
        generation=self.controller.snapshot()['restart_generation']
        self.robot.packet.bumps_and_wheel_drops.wheel_drop_left=False
        self.robot.start=Mock(side_effect=lambda:setattr(self.robot.packet,'oi_mode',1))
        self.command('restart_oi')
        self.robot.start.assert_called_once_with()
        state=self.controller.snapshot()
        self.assertFalse(state['oi_stopped'])
        self.assertFalse(state['ready'])
        self.assertIsNone(state['sensors'])
        self.assertEqual(state['restart_generation'],generation+1)
        self.assertTrue(self.robot.auto_wake)
        with self.assertRaisesRegex(RuntimeError,'initializing'):
            self.command('drive_straight',velocity=40)
        self.controller._poll_sensors()
        self.assertEqual(self.controller.snapshot()['sensors'].oi_mode,1)

    def test_invalid_packet_is_not_published_or_recorded_or_monitored(self):
        self.controller.sensor_log=Mock()
        before=self.controller._sensor_time
        self.robot.packet.oi_mode=57
        self.robot.packet.left_motor_current=29556
        with self.assertLogs('QueuedControl',level='ERROR'):
            self.controller._poll_sensors()
        self.assertEqual(self.controller._sensor_time,before)
        self.assertIsNotNone(self.controller.snapshot()['sensor_fault'])
        self.assertFalse(self.controller.snapshot()['ready'])
        self.assertEqual(self.controller._reverse_monitor.event_count,0)
        self.controller.sensor_log.record.assert_not_called()
        self.assertEqual(self.robot.drive_commands[-1],('drive',0,32768))
        with self.assertRaisesRegex(RuntimeError,'latest sensor poll failed'):
            self.command('drive_straight',velocity=40)

    def test_dedicated_buttons_override_stale_group_and_latch_brief_press(self):
        self.robot.packet.buttons=SimpleNamespace(schedule=True,clock=False)
        self.robot.buttons=SimpleNamespace(schedule=False,clock=True)
        self.controller._poll_sensors()
        self.robot.buttons.clock=False
        self.controller._poll_sensors()
        self.assertTrue(self.controller.consume_clock_button_press())
        self.assertFalse(self.controller.consume_clock_button_press())
        self.assertFalse(self.controller.snapshot()['schedule_button'])
        self.assertEqual(self.controller.snapshot()['button_diagnostics']['source'],'packet18')

    def test_schedule_press_is_latched_across_release(self):
        self.robot.buttons=SimpleNamespace(schedule=True,clock=False)
        self.controller._poll_sensors()
        self.robot.buttons.schedule=False
        self.controller._poll_sensors()
        self.assertTrue(self.controller.consume_schedule_button_press())
        self.assertFalse(self.controller.consume_schedule_button_press())

    def test_report_only_current_candidate_never_brakes_or_changes_target(self):
        self.command('drive_straight',velocity=-40)
        self.robot.packet.left_motor_current=700
        before=list(self.robot.drive_commands)
        self.controller._poll_sensors()
        self.assertEqual(self.robot.drive_commands,before)
        self.assertEqual(self.controller._applied_wheels,(-40,-40))
        state=self.controller.snapshot()['reverse_current_monitor']
        self.assertEqual(state['mode'],'report_only')
        self.assertTrue(state['candidate'])
        self.assertEqual(state['event_count'],1)
        self.robot.packet.left_motor_current=7000
        self.controller._poll_sensors()
        self.assertEqual(self.robot.drive_commands,before)
        self.assertIsNone(self.controller.snapshot()['sensor_fault'])

    def test_packet_shape_validation(self):
        for raw in (bytes(79),bytes([255])+bytes(79)):
            with self.assertRaises(ValueError):
                self.controller._validate_sensors(SimpleNamespace(_data=raw))

    def test_pickup_does_not_query_dedicated_button_packet(self):
        class Robot(FakeRobot):
            @property
            def buttons(self):
                raise AssertionError('Button read after wheel-drop packet')
        self.robot=Robot()
        self.controller=RobotCommandArbiter(None,0,logging.getLogger('DropPriority'),robot=self.robot)
        self.controller._startup_sensor_samples=STARTUP_SENSOR_SAMPLES
        self.robot.stop=Mock()
        self.robot.packet.bumps_and_wheel_drops.wheel_drop_left=True
        self.controller._poll_sensors()
        self.robot.stop.assert_called_once_with()
        self.assertTrue(self.controller._wheel_drop_stopped)

    def test_held_button_reports_once_without_repeated_stuck_warning(self):
        from unittest.mock import patch
        self.robot.packet.buttons = SimpleNamespace(_data=64)
        self.robot.buttons = SimpleNamespace(_data=64)
        self.robot.packet.oi_mode = 2
        self.controller._last_button_mask = 64
        self.controller._button_changed_at = 0
        with patch('roomberry_control.monotonic', return_value=100), \
                patch.object(self.controller.logger,'info') as info, \
                patch.object(self.controller.logger,'warning') as warning:
            self.controller._read_buttons(self.robot.packet)
            self.controller._read_buttons(self.robot.packet)
        self.assertEqual(info.call_count,1)
        self.assertIn('firmware-latched',info.call_args.args[0])
        warning.assert_not_called()
