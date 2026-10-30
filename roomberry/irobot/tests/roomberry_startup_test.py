# @(#)roomberry_startup_test.py 2.3.14 2026/10/28 20:30:00
"""Serial startup checks without robot hardware."""
import importlib.util
import itertools
import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StartupTest(unittest.TestCase):
    def test_reset_captures_split_version_and_closes_serial(self):
        import roomberry_startup as startup
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.__enter__.return_value = connection
        chunks = iter([b'boot\r\nr3_robot/tags/release-3.2.', b'6:4975 CLEAN\r\n'])
        connection.read.side_effect = lambda size: next(chunks, b'')
        factory = Mock(return_value=connection)
        ticks = itertools.count(0, .25)
        with patch.object(startup, 'sleep'), \
                patch.object(startup, 'monotonic', side_effect=lambda: next(ticks)):
            identity = startup.reset_and_identify('/fake', logging.getLogger('StartupTest'),
                                                  serial_factory=factory)
        self.assertEqual([c.args[0] for c in connection.write.call_args_list], [b'\x80', b'\x07'])
        self.assertEqual(identity['firmware_version'], 'r3_robot/tags/release-3.2.6:4975 CLEAN')
        self.assertEqual(identity['firmware_release'], '3.2.6')
        connection.__exit__.assert_called_once()

    def test_utility_preserves_identity_and_unknown_is_explicit(self):
        utility = load_module('version_utility', ROOT / 'utils/version.py')
        result = utility.parse_firmware((ROOT / 'utils/version.txt').read_bytes())
        self.assertEqual(result['firmware_release'], '3.2.6')
        self.assertEqual(result['firmware_version'], 'r3_robot/tags/release-3.2.6:4975 CLEAN')
        self.assertIsNone(utility.parse_firmware(b'unknown\xff')['firmware_version'])

    def test_feedback_cannot_rearm_passive_robot(self):
        from irobot.tests.roomberry_queued_control_test import QueuedControlTest
        fixture = QueuedControlTest()
        fixture.setUp()
        fixture.robot.packet.oi_mode = 1
        fixture.robot._change_mode = Mock()
        for operation in ('set_song', 'play_song'):
            with self.assertRaisesRegex(RuntimeError, 'Safe mode'):
                fixture.command(operation)
        fixture.robot._change_mode.assert_not_called()
        self.assertEqual(fixture.robot.played_songs, [])

    def test_connection_requests_reset_then_verifies_safe(self):
        from roomberry_control import RobotCommandArbiter
        driver = Mock()
        robot = driver.Create2.return_value
        robot.boot_firmware_version = 'r3_robot/tags/release-3.2.6:4975 CLEAN'
        robot.firmware_release = '3.2.6'
        controller = RobotCommandArbiter.__new__(RobotCommandArbiter)
        controller.logger = logging.getLogger('StartupTest')
        with patch.dict(sys.modules, {'irobot.robots.create2': driver}), \
                patch('roomberry_control.reset_and_identify', return_value={
                    'boot_message': 'boot', 'firmware_version': 'release-test',
                    'firmware_release': '3.2.6'}) as reset:
            result = controller._connect_robot('/fake', 0)
        self.assertIs(result, robot)
        reset.assert_called_once_with('/fake', controller.logger)
        driver.Create2.assert_called_once_with('/fake', 0, timeout=.05, enable_quirks=False)
        self.assertEqual(robot.boot_firmware_version, 'release-test')
        self.assertEqual([call.args[0] for call in robot._change_mode.call_args_list], [2, 1])

    def test_utility_checks_safe_after_boot_capture(self):
        utility = load_module('version_utility_safe', ROOT / 'utils/version.py')
        serial_port = Mock()
        serial_port.in_waiting = 0
        serial_port.read.side_effect = [b'r3_robot/tags/release-3.2.6:4975 CLEAN\r\n', b'\x02']
        serial_port.__enter__ = Mock(return_value=serial_port)
        serial_port.__exit__ = Mock(return_value=False)
        with patch.object(utility.serial, 'Serial', return_value=serial_port), \
                patch.object(utility.time, 'sleep'), \
                patch.object(utility.time, 'monotonic', side_effect=[0, 0, 16]), \
                patch('builtins.print'):
            result = utility.capture_firmware_version('/fake')
        self.assertEqual(result['firmware_release'], '3.2.6')
        self.assertEqual(result['oi_mode'], 2)
        self.assertEqual([c.args[0] for c in serial_port.write.call_args_list],
                         [b'\x80', b'\x07', b'\x80', b'\x83', b'\x8e\x23'])

    def test_incompatible_driver_error_is_not_retried_as_sleep(self):
        from roomberry_control import RobotCommandArbiter
        driver = Mock()
        driver.Create2.side_effect = TypeError('unsupported argument')
        controller = RobotCommandArbiter.__new__(RobotCommandArbiter)
        controller.logger = Mock()
        with patch.dict(sys.modules, {'irobot.robots.create2': driver}), \
                patch('roomberry_control.reset_and_identify', return_value={}), \
                patch('roomberry_control.sleep') as sleep:
            with self.assertRaises(TypeError):
                controller._connect_robot('/fake', 0)
        sleep.assert_not_called()
        driver.Create2.assert_called_once()

    def test_idle_feedback_restores_passive_after_tone_and_failure(self):
        from irobot.tests.roomberry_queued_control_test import QueuedControlTest
        fixture = QueuedControlTest()
        fixture.setUp()
        fixture.robot.packet.oi_mode = 1
        events = []
        fixture.robot._change_mode = Mock(side_effect=lambda mode: events.append(('mode', mode)))
        fixture.robot.set_song = Mock(side_effect=lambda **kw: events.append(('song',)))
        fixture.robot.play_song = Mock(side_effect=lambda **kw: events.append(('play',)))
        with patch('roomberry_control.sleep'):
            fixture.command('_feedback_beep', notes=[[79, 8]])
        self.assertEqual(events, [('mode', 2), ('song',), ('play',), ('mode', 1)])
        fixture.robot.play_song.side_effect = IOError('play failed')
        with self.assertRaises(IOError):
            fixture.command('_feedback_beep', notes=[[79, 8]])
        self.assertEqual(events[-1], ('mode', 1))
        fixture.controller.set_operation_indicators(True)
        events.clear()
        with self.assertRaisesRegex(RuntimeError, 'rearm'):
            fixture.command('_feedback_beep', notes=[[79, 8]])
        self.assertEqual(events, [])

    def test_drive_display_changes_only_and_stays_off_after_pickup(self):
        from irobot.tests.roomberry_queued_control_test import QueuedControlTest
        fixture = QueuedControlTest()
        fixture.setUp()
        robot, control = fixture.robot, fixture.controller
        robot.set_ascii_leds = Mock()
        for mode, stage, scan, label in [
                ('idle', None, False, 'IdLE'),
                ('discovery', 'wall_follow', False, 'WALL'),
                ('discovery', 'wall_follow', True, 'SCAn'),
                ('discovery', 'avoid_back', False, 'bACK'),
                ('discovery', 'dock_approach', False, 'HOME'),
                ('remote_control', None, False, 'rEM ')]:
            control.set_drive_display(mode, stage, scan)
            control._update_drive_display(robot.packet)
            self.assertEqual(''.join(chr(robot.set_ascii_leds.call_args.kwargs['char'+str(i)])
                                     for i in range(1,5)), label)
        count = robot.set_ascii_leds.call_count
        control._update_drive_display(robot.packet)
        self.assertEqual(robot.set_ascii_leds.call_count, count)
        fixture.pickup()
        control.set_drive_display('idle')
        control._update_drive_display(robot.packet)
        self.assertEqual(robot.set_ascii_leds.call_count, count)
