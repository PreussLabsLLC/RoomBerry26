# @(#)roomberry_control_test.py 2.3.13 2026/10/28 20:00:00
import csv
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

from irobot.openinterface.constants import DRIVE, MODES
from roomberry_control import (
    BUTTON_BEEP_SONG, RobotCommandArbiter, STARTUP_SENSOR_SAMPLES,
)
from roomberry_sensor_log import SensorCsvRecorder


class FakeRobot:
    def __init__(self):
        self.logger = logging.getLogger('FakeRobot')
        self.packet = self._packet(distance=12, angle=-3)
        self.sensor_reads = 0
        self.sensor_read_event = Event()
        self.drive_commands = []
        self.scheduling_leds = []
        self.songs = {}
        self.played_songs = []
        self.mode = None

    @staticmethod
    def _packet(distance=0, angle=0):
        return SimpleNamespace(
            distance=distance,
            angle=angle,
            requested_velocity=0,
            requested_radius=DRIVE.STRAIGHT,
            requested_left_velocity=0,
            requested_right_velocity=0,
            oi_mode=2,
            battery_charge=100,
            battery_capacity=100,
            voltage=14000,
            current=-500,
            temperature=22,
            charging_state=0,
            charging_sources=SimpleNamespace(home_base=False),
            left_motor_current=100,
            right_motor_current=-100,
            main_brush_motor_current=0,
            side_brush_motor_current=0,
            wall_sensor=False,
            virtual_wall_sensor=False,
            wall_signal=0,
            cliff_left_signal=0,
            cliff_front_left_signal=0,
            cliff_front_right_signal=0,
            cliff_right_signal=0,
            light_bump_left_signal=0,
            light_bump_front_left_signal=0,
            light_bump_center_left_signal=0,
            light_bump_center_right_signal=0,
            light_bump_front_right_signal=0,
            light_bump_right_signal=0,
            dirt_detect_sensor=0,
            wheel_overcurrents=SimpleNamespace(
                left_wheel_overcurrent=False,
                right_wheel_overcurrent=False,
                main_brush_overcurrent=False,
                side_brush_overcurrent=False,
            ),
            stasis=SimpleNamespace(toggling=False, disabled=False),
            bumps_and_wheel_drops=SimpleNamespace(
                bump_left=False,
                bump_right=False,
                wheel_drop_left=False,
                wheel_drop_right=False,
            ),
            cliff_left_sensor=False,
            cliff_front_left_sensor=False,
            cliff_front_right_sensor=False,
            cliff_right_sensor=False,
            light_bumper=SimpleNamespace(
                left=False,
                front_left=False,
                center_left=False,
                center_right=False,
                front_right=False,
                right=False,
            ),
        )

    @property
    def oi_mode(self):
        return self.packet.oi_mode

    @property
    def sensor_group100(self):
        self.sensor_reads += 1
        self.sensor_read_event.set()
        return self.packet

    def drive(self, velocity, radius):
        self.drive_commands.append(('drive', velocity, radius))

    def drive_direct(self, right_velocity, left_velocity):
        self.drive_commands.append(('drive_direct', right_velocity, left_velocity))

    def drive_straight(self, velocity):
        self.drive_commands.append(('drive_straight', velocity))

    def seek_dock(self):
        self.drive_commands.append(('seek_dock',))

    def _change_mode(self, mode):
        self.mode = mode

    def set_scheduling_leds(self, **kwargs):
        self.scheduling_leds.append(kwargs)

    def set_song(self, song_number, notes):
        self.songs[song_number] = notes

    def play_song(self, song_number):
        self.played_songs.append(song_number)

    def stop(self):
        pass


class RobotCommandArbiterTest(unittest.TestCase):
    def setUp(self):
        self.robot = FakeRobot()
        self.controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryTest'), robot=self.robot, motion_ramp={'enabled': False},
            poll_interval=0.01,
        )
        self.controller.start()
        self.assertTrue(self._wait_for(
            lambda: self.controller._startup_sensor_samples >= STARTUP_SENSOR_SAMPLES
        ))

    def tearDown(self):
        self.controller.close()

    def test_polls_and_accumulates_signed_odometry(self):
        self.assertTrue(self._wait_for(lambda: self.robot.sensor_reads >= 2))
        state = self.controller.snapshot()
        self.assertGreaterEqual(state['distance'], 24)
        self.assertLessEqual(state['angle'], -6)
        self.assertLess(state['age'], 0.5)

    def test_allows_legacy_mode_change_but_rejects_other_private_operations(self):
        self.controller.execute('_change_mode', mode=2)
        self.assertEqual(self.robot.mode, 2)
        with self.assertRaisesRegex(ValueError, 'Invalid Roomba mode'):
            self.controller.execute('_change_mode', mode=4)
        with self.assertRaisesRegex(ValueError, 'Invalid Roomba operation'):
            self.controller.execute('_run')

    def test_hazard_brakes_and_blocks_motion_until_clear(self):
        previous_reads = self.robot.sensor_reads
        self.robot.packet.bumps_and_wheel_drops.bump_left = True
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and self.controller._safety_latched
        ))
        self.assertEqual(self.robot.drive_commands[-1], ('drive', 0, DRIVE.STRAIGHT))
        with self.assertRaises(RuntimeError):
            self.controller.execute('drive_straight', velocity=100)
        with self.assertRaises(RuntimeError):
            self.controller.execute('drive_pwm', right_pwm=100, left_pwm=100)
        with self.assertRaises(RuntimeError):
            self.controller.execute('set_motors', vacuum=True)
        self.controller.execute('drive_straight', velocity=-80)
        self.assertEqual(self.robot.drive_commands[-1], ('drive_straight', -80))
        with self.assertRaises(RuntimeError):
            self.controller.execute('drive_straight', velocity=-101)

        previous_reads = self.robot.sensor_reads
        self.robot.packet.bumps_and_wheel_drops.bump_left = False
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and not self.controller._safety_latched
        ))
        # The permitted recovery reverse continues after the hazard clears.
        self.assertEqual(self.robot.drive_commands[-1], ('drive_straight', -80))
        self.controller.execute('drive_straight', velocity=100)
        self.assertEqual(self.robot.drive_commands[-1], ('drive_straight', 100))

        previous_reads = self.robot.sensor_reads
        self.robot.packet.bumps_and_wheel_drops.wheel_drop_left = True
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and self.controller._safety_latched
        ))
        with self.assertRaises(RuntimeError):
            self.controller.execute('drive_straight', velocity=-80)

    def test_hazard_clear_brakes_without_active_recovery(self):
        previous_reads = self.robot.sensor_reads
        self.robot.packet.bumps_and_wheel_drops.bump_left = True
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and self.controller._safety_latched
        ))
        brakes = self.robot.drive_commands.count(('drive', 0, DRIVE.STRAIGHT))

        previous_reads = self.robot.sensor_reads
        self.robot.packet.bumps_and_wheel_drops.bump_left = False
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and not self.controller._safety_latched
        ))
        self.assertEqual(
            self.robot.drive_commands.count(('drive', 0, DRIVE.STRAIGHT)),
            brakes + 1,
        )

    def test_button_beep_programs_and_plays_tone(self):
        self.controller.execute('_change_mode', mode=MODES.SAFE)
        self.controller.beep()

        self.assertEqual(self.robot.played_songs, [BUTTON_BEEP_SONG])
        self.assertIn(BUTTON_BEEP_SONG, self.robot.songs)
        notes = self.robot.songs[BUTTON_BEEP_SONG]
        self.assertTrue(notes)
        self.assertTrue(all(31 <= note[0] <= 127 for note in notes))

    def test_operation_leds_hold_a_brief_sensor_trigger(self):
        robot = FakeRobot()
        controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryLedTest'), robot=robot, motion_ramp={'enabled': False},
        )
        controller.set_operation_indicators(True)
        robot.packet.cliff_left_sensor = True
        controller._update_operation_leds(robot.packet)
        self.assertTrue(robot.scheduling_leds[-1]['sun'])

        writes = len(robot.scheduling_leds)
        robot.packet.cliff_left_sensor = False
        controller._update_operation_leds(robot.packet)
        self.assertEqual(len(robot.scheduling_leds), writes)

        controller._scheduling_led_hold_until[0] = monotonic() - 1.0
        controller._update_operation_leds(robot.packet)
        self.assertFalse(robot.scheduling_leds[-1]['sun'])

    def test_operation_leds_show_light_bumper_proximity(self):
        robot = FakeRobot()
        controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryLedTest'), robot=robot, motion_ramp={'enabled': False},
        )
        controller.set_operation_indicators(True)
        robot.packet.light_bump_front_right_signal = 120
        controller._update_operation_leds(robot.packet)
        leds = robot.scheduling_leds[-1]
        self.assertTrue(leds['wed'])
        self.assertFalse(leds['sun'])
        self.assertFalse(leds['thurs'])

        robot.packet.light_bump_front_right_signal = 0
        robot.packet.light_bump_center_left_signal = 120
        controller._update_operation_leds(robot.packet)
        self.assertTrue(robot.scheduling_leds[-1]['tues'])

    def test_operation_leds_ignore_light_bumper_carpet_noise(self):
        robot = FakeRobot()
        controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryLedTest'), robot=robot, motion_ramp={'enabled': False},
        )
        controller.set_operation_indicators(True)
        robot.packet.light_bump_front_right_signal = 20
        controller._update_operation_leds(robot.packet)

        self.assertFalse(robot.scheduling_leds[-1]['wed'])

    def test_safety_warning_includes_sensor_details(self):
        robot = FakeRobot()
        robot.packet.bumps_and_wheel_drops.bump_left = True
        logger = logging.getLogger('RoomberrySensorLogTest')
        controller = RobotCommandArbiter(None, 0, logger, robot=robot)
        controller._startup_sensor_samples = STARTUP_SENSOR_SAMPLES

        with self.assertLogs(logger, level='WARNING') as captured:
            controller._poll_sensors()

        self.assertIn('bump_left=True', captured.output[0])
        self.assertIn('cliff_left_sensor=False (signal=0)', captured.output[0])

    def test_transient_startup_hazard_does_not_latch(self):
        robot = FakeRobot()
        robot.packet.bumps_and_wheel_drops.wheel_drop_left = True
        controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryStartupTest'), robot=robot, motion_ramp={'enabled': False},
        )
        try:
            controller._poll_sensors()
            self.assertFalse(controller._safety_latched)
            self.assertEqual(robot.drive_commands[-1], ('drive', 0, DRIVE.STRAIGHT))
            with self.assertRaisesRegex(RuntimeError, 'sensors are initializing'):
                controller._check_motion_allowed('drive_straight', {'velocity': 50})

            robot.packet.bumps_and_wheel_drops.wheel_drop_left = False
            for _ in range(STARTUP_SENSOR_SAMPLES - 1):
                controller._poll_sensors()
            self.assertEqual(
                controller._startup_sensor_samples, STARTUP_SENSOR_SAMPLES,
            )
            self.assertFalse(controller._safety_latched)
            controller._check_motion_allowed('drive_straight', {'velocity': 50})
        finally:
            controller._shutdown.set()

    def test_stationary_dock_hazard_is_suppressed(self):
        robot = FakeRobot()
        robot.packet.charging_sources.home_base = True
        robot.packet.cliff_left_sensor = True
        controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RoomberryDockTest'), robot=robot, motion_ramp={'enabled': False},
        )
        controller._startup_sensor_samples = STARTUP_SENSOR_SAMPLES
        try:
            controller._poll_sensors()

            state = controller.snapshot()
            self.assertFalse(controller._safety_latched)
            self.assertTrue(state['home_base'])
            self.assertTrue(state['hazards_suppressed'])
            self.assertEqual(state['hard_hazard_reasons'], [])

            robot.packet.requested_velocity = 50
            controller._poll_sensors()
            self.assertTrue(controller._safety_latched)
            self.assertFalse(controller.snapshot()['hazards_suppressed'])
        finally:
            controller._shutdown.set()

    def test_wheel_drop_sends_oi_stop_and_blocks_motion_after_setdown(self):
        from unittest.mock import Mock
        robot = FakeRobot()
        robot.stop = Mock()
        controller = RobotCommandArbiter(None, 0, logging.getLogger('DropTest'), robot=robot)
        controller._startup_sensor_samples = STARTUP_SENSOR_SAMPLES
        robot.packet.bumps_and_wheel_drops.wheel_drop_left = True
        controller._poll_sensors()
        robot.stop.assert_called_once_with()
        robot.packet.bumps_and_wheel_drops.wheel_drop_left = False
        robot.packet.charging_sources.home_base = True
        controller._poll_sensors()
        with self.assertRaisesRegex(RuntimeError, 'after wheel drop'):
            controller._check_motion_allowed('drive_straight', {'velocity': 50})
        self.assertTrue(controller._wheel_drop_stopped)

    def test_scan_sounds_are_distinct_and_silent_after_wheel_drop(self):
        from unittest.mock import Mock
        robot = FakeRobot()
        controller = RobotCommandArbiter(None, 0, logging.getLogger('SoundTest'), robot=robot)
        controller.execute = Mock()
        sounds = []
        for event in ('neutral', 'happy', 'unhappy', 'mode_change'):
            controller.beep(event=event)
            sounds.append(controller.execute.call_args_list[-1].kwargs['notes'])
        self.assertEqual(len({str(notes) for notes in sounds}), 4)
        self.assertEqual(len(sounds[3]), 4)
        controller.set_drive_display('discovery', 'bump')
        self.assertEqual(controller._drive_display, 'bUMP')
        self.assertEqual(sounds[1], [list(note) for note in ((79, 8), (84, 12))])
        controller.execute.reset_mock()
        controller._wheel_drop_stopped = True
        controller.beep(event='happy')
        controller.execute.assert_not_called()

    def test_low_battery_seeks_dock_and_blocks_other_motion(self):
        previous_reads = self.robot.sensor_reads
        self.robot.packet.battery_charge = 20
        self.assertTrue(self._wait_for(
            lambda: self.robot.sensor_reads > previous_reads and
            ('seek_dock',) in self.robot.drive_commands
        ))
        with self.assertRaises(RuntimeError):
            self.controller.execute('drive_straight', velocity=100)
        self.controller.execute('seek_dock')

    def test_polled_sensors_are_written_to_csv(self):
        with TemporaryDirectory() as directory:
            robot = FakeRobot()
            recorder = SensorCsvRecorder(
                directory, logger=logging.getLogger('RoomberrySensorLogTest'),
                interval_s=0.0, flush_interval_s=0.0,
            )
            controller = RobotCommandArbiter(
                None, 0, logging.getLogger('RoomberrySensorLogTest'), robot=robot, motion_ramp={'enabled': False},
                poll_interval=0.01, sensor_log=recorder,
            )
            try:
                controller.start()
                self.assertTrue(self._wait_for(lambda: robot.sensor_reads >= 2))
            finally:
                controller.close()

            files = list(Path(directory).glob('roomberry-sensors-*.csv'))
            self.assertEqual(len(files), 1)
            with files[0].open(newline='') as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0]['battery_voltage_v'], '14.0')
            self.assertEqual(rows[0]['battery_current_a'], '-0.5')
            self.assertEqual(rows[0]['battery_power_w'], '-7.0')
            self.assertEqual(rows[0]['left_motor_current_a'], '0.1')
            self.assertIn('battery_current_avg_5s_a', rows[0])

    @staticmethod
    def _wait_for(predicate, timeout=1):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if predicate():
                return True
            sleep(0.005)
        return predicate()



class WheelRampTest(unittest.TestCase):
    """Deterministic I/O-thread ticks, without sleeping or physical hardware."""

    def setUp(self):
        self.robot = FakeRobot()
        self.controller = RobotCommandArbiter(
            None, 0, logging.getLogger('RampTest'), robot=self.robot,
            motion_ramp={'enabled': True, 'acceleration_mm_s2': 100,
                         'deceleration_mm_s2': 200})
        self.controller._startup_sensor_samples = STARTUP_SENSOR_SAMPLES
        self.controller._poll_sensors()
        self.now = self.controller._ramp_time

    def command(self, operation, **kwargs):
        command = dict(operation=operation, kwargs=kwargs, result=[], done=Event(),
                       expires_at=monotonic()+5)
        self.controller._run_command(command)
        if len(command['result']) == 2:
            raise command['result'][1]
        self.now = max(self.now, self.controller._ramp_time)
        return command

    def tick(self, count=1, dt=.05):
        for _ in range(count):
            self.now += dt
            self.controller._advance_ramp(self.now)

    def test_start_and_stop_follow_limits_and_stop_waits_for_zero(self):
        self.command('drive_straight', velocity=50)
        self.assertEqual(self.robot.drive_commands, [])
        self.tick()
        self.assertAlmostEqual(self.controller._ramp_current[0], 5, places=4)
        self.tick(10)
        self.assertEqual(self.controller._ramp_current, (50, 50))
        stop = self.command('soft_stop')
        self.assertFalse(stop['done'].is_set())
        self.tick()
        self.assertAlmostEqual(self.controller._ramp_current[0], 40, places=4)
        self.tick(5)
        self.assertTrue(stop['done'].is_set())
        self.assertEqual(self.robot.drive_commands[-1], ('drive_direct', 0, 0))

    def test_reversal_reaches_zero_before_opposite_motion(self):
        self.command('drive_direct', left_velocity=40, right_velocity=20)
        self.tick(9)
        self.assertEqual(self.controller._ramp_current, (40, 20))
        self.command('drive_direct', left_velocity=-40, right_velocity=-20)
        points=[]
        for _ in range(15):
            self.tick()
            points.append(self.controller._ramp_current)
        self.assertIn((0.0, 0.0), points)
        first_negative = next(i for i,v in enumerate(points) if v[0] < 0)
        self.assertEqual(points[first_negative-1], (0.0, 0.0))
        for left,right in points:
            self.assertAlmostEqual(left, 2*right)

    def test_heartbeat_does_not_restart_acceleration(self):
        self.command('drive_straight', velocity=50)
        self.tick(4)
        previous=self.controller._ramp_current
        self.command('drive_straight', velocity=50)
        self.assertEqual(self.controller._ramp_current, previous)
        self.tick()
        self.assertGreater(self.controller._ramp_current[0], previous[0])

    def test_emergency_cancels_pending_motion_and_deferred_stop(self):
        self.command('drive_straight', velocity=50)
        self.tick(5)
        pending=self.command('soft_stop')
        self.command('emergency_stop')
        self.assertTrue(pending['done'].is_set())
        self.assertEqual(self.robot.drive_commands[-1], ('drive', 0, DRIVE.STRAIGHT))
        self.assertEqual(self.controller._ramp_target, (0,0))
        self.tick(5)
        self.assertEqual(self.robot.drive_commands[-1], ('drive', 0, DRIVE.STRAIGHT))

    def test_cliff_interrupts_ramp_and_does_not_resume(self):
        self.command('drive_straight', velocity=50)
        self.tick(3)
        self.robot.packet.cliff_left_sensor=True
        self.controller._poll_sensors()
        self.assertEqual(self.controller._ramp_target, (0,0))
        self.robot.packet.cliff_left_sensor=False
        self.controller._poll_sensors()
        self.tick(5)
        self.assertEqual(self.controller._ramp_current, (0,0))

    def test_stale_sensors_abort_even_a_soft_stop(self):
        self.command('drive_straight', velocity=50)
        self.tick(4)
        pending=self.command('soft_stop')
        self.controller._sensor_time=monotonic()-1
        self.tick()
        self.assertTrue(pending['done'].is_set())
        self.assertEqual(self.robot.drive_commands[-1], ('drive', 0, DRIVE.STRAIGHT))
        self.assertEqual(self.controller._ramp_target, (0,0))

    def test_large_worker_delay_does_not_jump_to_full_speed(self):
        self.command('drive_straight', velocity=500)
        self.tick(dt=4)
        self.assertLessEqual(self.controller._ramp_current[0], 10.001)

    def test_mode_change_cancels_ramp(self):
        self.command('drive_straight', velocity=50)
        self.tick(3)
        self.command('_change_mode', mode=1)
        self.assertEqual(self.controller._ramp_target, (0,0))
        self.tick(4)
        self.assertEqual(self.controller._ramp_current, (0,0))

    def test_target_validation_and_arc_conversion(self):
        for velocity in (501, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.command('drive_straight', velocity=velocity)
        target=self.controller._wheel_target('drive', dict(velocity=50, radius=500))
        self.assertGreater(target[1], target[0])
        self.assertEqual(self.controller._wheel_target('drive',dict(velocity=50,radius=-1)),(50,-50))
        self.assertEqual(self.controller._wheel_target('drive',dict(velocity=0,radius=0)),(0,0))
        self.assertEqual(self.controller._ramp_target,(0,0))

    def test_web_zero_velocity_waits_and_new_motion_cannot_override_stop(self):
        self.command('drive_straight', velocity=50)
        self.tick(7)
        stop=self.command('drive',velocity=0,radius=0)
        self.assertFalse(stop['done'].is_set())
        with self.assertRaisesRegex(RuntimeError,'soft stop'):
            self.command('drive_straight',velocity=40)
        self.tick(5)
        self.assertTrue(stop['done'].is_set())
        self.assertEqual(self.controller._ramp_target,(0,0))

    def test_reverse_ramp_is_permitted_to_release_front_bumper(self):
        self.robot.packet.bumps_and_wheel_drops.bump_left=True
        self.controller._poll_sensors()
        self.command('drive_straight',velocity=-40)
        self.tick(4)
        self.assertLess(self.controller._ramp_current[0],0)
        self.assertGreaterEqual(self.controller._ramp_current[0],-40)

    def test_wheel_drop_cancels_target_and_sends_oi_stop(self):
        from unittest.mock import Mock
        self.robot.stop=Mock()
        self.command('drive_straight',velocity=50)
        self.tick(4)
        self.robot.packet.bumps_and_wheel_drops.wheel_drop_left=True
        self.controller._poll_sensors()
        self.robot.stop.assert_called_once_with()
        self.assertEqual(self.controller._ramp_current,(0,0))
        self.assertEqual(self.controller._ramp_target,(0,0))
        self.assertTrue(self.controller._wheel_drop_stopped)

    def test_soft_stop_deadline_escalates_to_immediate_brake(self):
        self.command('drive_straight',velocity=50)
        self.tick(4)
        stop=self.command('soft_stop')
        stop['expires_at']=monotonic()-1
        self.tick()
        self.assertTrue(stop['done'].is_set())
        self.assertEqual(self.robot.drive_commands[-1],('drive',0,DRIVE.STRAIGHT))

    def test_invalid_ramp_configuration_is_rejected(self):
        for rate in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                RobotCommandArbiter(None,0,logging.getLogger('InvalidRamp'),robot=FakeRobot(),
                                    motion_ramp={'acceleration_mm_s2':rate})

    def test_real_worker_soft_stop_keeps_polling(self):
        self.controller.poll_interval=.01
        self.controller.start()
        try:
            self.controller.execute('drive_straight', velocity=40)
            deadline=monotonic()+2
            while self.controller._ramp_current[0] < 39 and monotonic()<deadline:
                sleep(.01)
            self.assertGreaterEqual(self.controller._ramp_current[0],39)
            before=self.robot.sensor_reads
            self.controller.execute('soft_stop')
            self.assertGreater(self.robot.sensor_reads,before+2)
            self.assertEqual(self.controller._ramp_current,(0,0))
        finally:
            self.controller.close()


if __name__ == '__main__':
    unittest.main()
