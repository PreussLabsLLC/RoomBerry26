# @(#)roomberry_sensor_log_test.py 2.3.18 2026/10/28 21:40:00
import csv
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from roomberry_sensor_log import SensorCsvRecorder


class FakeClock:
    def __init__(self):
        self.wall = 1700000000.0
        self.monotonic = 100.0

    def tick(self, seconds):
        self.wall += seconds
        self.monotonic += seconds


def sensor_packet():
    return SimpleNamespace(
        voltage=14000,
        current=-1000,
        temperature=22,
        battery_charge=1800,
        battery_capacity=2600,
        charging_state=0,
        oi_mode=2,
        requested_velocity=0,
        requested_radius=32768,
        requested_left_velocity=0,
        requested_right_velocity=0,
        distance=12,
        angle=-3,
        bumps_and_wheel_drops=SimpleNamespace(
            bump_left=False,
            bump_right=False,
            wheel_drop_left=False,
            wheel_drop_right=False,
        ),
        light_bumper=SimpleNamespace(
            left=False,
            front_left=False,
            center_left=False,
            center_right=False,
            front_right=False,
            right=False,
        ),
        charging_sources=SimpleNamespace(home_base=False),
        left_motor_current=100,
        right_motor_current=-100,
        main_brush_motor_current=0,
        side_brush_motor_current=0,
        wheel_overcurrents=SimpleNamespace(
            left_wheel_overcurrent=False,
            right_wheel_overcurrent=False,
            main_brush_overcurrent=False,
            side_brush_overcurrent=False,
        ),
        stasis=SimpleNamespace(toggling=False, disabled=False),
    )


def sensor_snapshot(packet, distance=100.0, angle=5.0):
    return {
        'sensors': packet,
        'distance': distance,
        'travelled_distance': distance + 50.0,
        'angle': angle,
        'odometry_epoch': 1,
        'battery_status': 'normal',
        'home_base': False,
        'ready': True,
        'safety_latched': False,
        'hazards_suppressed': False,
        'hard_hazard': False,
    }


class SensorCsvRecorderTest(unittest.TestCase):
    def test_report_only_monitor_and_applied_commands_are_recorded(self):
        with TemporaryDirectory() as directory:
            recorder=SensorCsvRecorder(directory)
            recorder.start()
            snapshot=dict(sensors=sensor_packet(),age=0,ready=True,
                applied_left_velocity_mm_s=-40,applied_right_velocity_mm_s=-40,
                button_diagnostics=dict(group_mask=64,dedicated_mask=128,source='packet18'),
                reverse_current_monitor=dict(mode='report_only',candidate=True,
                    reasons=['left_high_current'],event_count=1,threshold_a=[.4,.4]))
            snapshot['sensors'].ir_char_omni_sensor = 0  # Broken driver accessor.
            raw = bytearray(80)
            raw[10] = 172  # Packet 17, not reserved byte 9.
            snapshot['sensors']._data = bytes(raw)
            snapshot['sensors'].ir_character_left = 164
            snapshot['sensors'].ir_character_right = 168
            recorder.record(snapshot)
            recorder.close()
            with next(Path(directory).glob('*.csv')).open() as recorded:
                row=list(csv.DictReader(recorded))[0]
            self.assertEqual(row['reverse_monitor_mode'],'report_only')
            self.assertEqual(row['reverse_current_reasons'],'left_high_current')
            self.assertEqual(row['applied_left_velocity_mm_s'],'-40')
            self.assertEqual(row['button_dedicated_mask'],'128')
            self.assertEqual([row[k] for k in ('ir_char_omni','ir_character_left','ir_character_right')],
                             ['172','164','168'])

    def test_writes_units_and_rolling_current_averages(self):
        clock = FakeClock()
        with TemporaryDirectory() as directory:
            recorder = SensorCsvRecorder(
                directory,
                interval_s=0.0,
                flush_interval_s=0.0,
                time_function=lambda: clock.wall,
                monotonic_function=lambda: clock.monotonic,
            )
            self.assertTrue(recorder.start())
            packet = sensor_packet()

            recorder.record(sensor_snapshot(packet))
            clock.tick(0.2)
            packet.current = -2000
            packet.voltage = 13800
            recorder.record(sensor_snapshot(packet, distance=120.0, angle=7.0))
            clock.tick(6.0)
            packet.current = -3000
            recorder.record(sensor_snapshot(packet, distance=140.0, angle=8.0))
            recorder.close()

            with recorder.path.open(newline='') as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['battery_voltage_v'], '14.0')
        self.assertEqual(rows[0]['battery_current_a'], '-1.0')
        self.assertEqual(rows[0]['battery_power_w'], '-14.0')
        self.assertEqual(rows[0]['battery_percent'], '69.2')
        self.assertEqual(rows[1]['battery_voltage_v'], '13.8')
        self.assertEqual(rows[1]['battery_current_avg_1s_a'], '-1.5')
        self.assertEqual(rows[1]['battery_current_avg_5s_a'], '-1.5')
        self.assertEqual(rows[1]['distance_delta_mm'], '20.0')
        self.assertEqual(rows[1]['angle_delta_deg'], '2.0')
        self.assertEqual(rows[2]['battery_current_avg_1s_a'], '-3.0')
        self.assertEqual(rows[2]['battery_current_avg_5s_a'], '-3.0')
        self.assertEqual(rows[2]['left_motor_current_avg_5s_a'], '0.1')

    def test_old_run_files_are_pruned_to_max_files(self):
        clock = FakeClock()
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            for index, modified in ((1, 100), (2, 200), (3, 300)):
                path = directory / (
                    'roomberry-sensors-2020010{}-000000.csv'.format(index)
                )
                path.write_text('old\n')
                os.utime(path, (modified, modified))

            recorder = SensorCsvRecorder(
                directory, max_files=2,
                time_function=lambda: clock.wall,
                monotonic_function=lambda: clock.monotonic,
            )
            self.assertTrue(recorder.start())
            recorder.close()

            files = sorted(path.name for path in directory.glob('*.csv'))
            self.assertEqual(len(files), 2)
            self.assertIn('roomberry-sensors-20200103-000000.csv', files)
            self.assertNotIn('roomberry-sensors-20200101-000000.csv', files)

    def test_disabled_configuration_does_not_create_a_recorder(self):
        self.assertIsNone(SensorCsvRecorder.from_config(None))
        self.assertIsNone(SensorCsvRecorder.from_config({'enabled': False}))


if __name__ == '__main__':
    unittest.main()
