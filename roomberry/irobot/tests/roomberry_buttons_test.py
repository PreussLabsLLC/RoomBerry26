# @(#)roomberry_buttons_test.py 2.3.10 2026/10/28 17:00:00
import logging
import unittest
from time import monotonic
from types import SimpleNamespace

from roomberry_control import RobotCommandArbiter


class RobotButtonSnapshotTest(unittest.TestCase):
    def test_encoder_deltas_override_bad_distance_packet_and_count_reverse_positive(self):
        logger = logging.getLogger("EncoderOdometryRobot")
        sensors = SimpleNamespace(
            buttons=SimpleNamespace(schedule=False, clock=False),
            distance=145, angle=0,
            left_encoder_counts=10000, right_encoder_counts=10000,
            battery_charge=100, battery_capacity=100,
            charging_sources=SimpleNamespace(home_base=False),
            bumps_and_wheel_drops=SimpleNamespace(
                bump_left=False, bump_right=False,
                wheel_drop_left=False, wheel_drop_right=False,
            ),
            light_bumper=SimpleNamespace(
                left=False, front_left=False, center_left=False,
                center_right=False, front_right=False, right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
            oi_mode=2,
        )
        robot = SimpleNamespace(logger=logger, sensor_group100=sensors)
        control = RobotCommandArbiter(
            None, 0, logging.getLogger("EncoderOdometryTest"), robot=robot,
        )

        control._poll_sensors()
        sensors.left_encoder_counts = 7300
        sensors.right_encoder_counts = 7300
        control._poll_sensors()

        state = control.snapshot()
        self.assertAlmostEqual(state["distance"], -1200.3, delta=1.0)
        self.assertAlmostEqual(state["travelled_distance"], 1200.3, delta=1.0)
    def test_sensor_poll_latches_clock_and_counts_reverse_as_positive(self):
        logger = logging.getLogger("ButtonPollRobot")
        sensors = SimpleNamespace(
            buttons=SimpleNamespace(schedule=False, clock=True),
            distance=-25, angle=0, battery_charge=100, battery_capacity=100,
            charging_sources=SimpleNamespace(home_base=False),
            bumps_and_wheel_drops=SimpleNamespace(
                bump_left=False, bump_right=False,
                wheel_drop_left=False, wheel_drop_right=False,
            ),
            light_bumper=SimpleNamespace(
                left=False, front_left=False, center_left=False,
                center_right=False, front_right=False, right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
            oi_mode=2,
        )
        robot = SimpleNamespace(logger=logger, sensor_group100=sensors)
        control = RobotCommandArbiter(
            None, 0, logging.getLogger("ButtonPollTest"), robot=robot,
        )

        with self.assertLogs(control.logger, level="DEBUG") as captured:
            control._poll_sensors()

        state = control.snapshot()
        self.assertEqual(state["distance"], -25)
        self.assertEqual(state["travelled_distance"], 25)
        self.assertTrue(control.consume_clock_button_press())
        self.assertTrue(any("Clock button pressed" in line for line in captured.output))
    def test_clock_press_latch_is_consumed_once(self):
        robot = SimpleNamespace(logger=logging.getLogger("ButtonLatchRobot"))
        control = RobotCommandArbiter(
            None, 0, logging.getLogger("ButtonLatchTest"), robot=robot,
        )
        control._clock_press_pending = True

        self.assertTrue(control.consume_clock_button_press())
        self.assertFalse(control.consume_clock_button_press())
    def test_snapshot_exposes_clock_button_state(self):
        robot = SimpleNamespace(logger=logging.getLogger("ButtonSnapshotRobot"))
        control = RobotCommandArbiter(
            None, 0, logging.getLogger("ButtonSnapshotTest"), robot=robot,
        )
        control._sensors = SimpleNamespace(
            buttons=SimpleNamespace(schedule=False, clock=True),
        )
        control._button_state = dict(schedule=False, clock=True)
        control._sensor_time = monotonic()
        control._travelled_distance = 145

        state = control.snapshot()

        self.assertFalse(state["schedule_button"])
        self.assertTrue(state["clock_button"])
        self.assertEqual(state["travelled_distance"], 145)


if __name__ == "__main__":
    unittest.main()
