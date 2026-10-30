# @(#)roomberry_mission_test.py 2.3.18 2026/10/28 21:40:00
import json
import logging
import unittest
from math import pi
from pathlib import Path
from time import monotonic, time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from irobot.openinterface.constants import MODES
from roomberry_mission import (
    CONTACT_INSET_MM, CONTINUOUS_REISSUE_SECONDS,
    DISCOVERY_AVOID_FORWARD_MM, DISCOVERY_AVOID_FORWARD_TIMEOUT_SECONDS,
    DISCOVERY_AVOID_REVERSE_MM, DISCOVERY_AVOID_SPEED,
    DISCOVERY_AVOID_TURN_RAD,
    DISCOVERY_DOCK_HAZARD_GRACE_SECONDS,
    DISCOVERY_PARK_DISTANCE_MM,
    DISCOVERY_PROXIMITY_CONFIRM_TICKS,
    MODE_REMOTE,
    RELEASE_MAX_DISTANCE_MM, RELEASE_MIN_DISTANCE_MM,
    VISIT_RETRY_LATERAL_OFFSETS_MM,
    RoomberryMission,
)
from roomberry_navigation import (
    DRIVE, GO_TO_WAYPOINT, MODE_CLEAN, MODE_DISCOVERY, MODE_IDLE,
)

class RoomberryMissionTest(unittest.TestCase):
    def setUp(self):
        self.robot = Mock()
        self.mapper = Mock()
        self.navigation = Mock()
        self.localizer = Mock()
        self.camera = Mock()
        self.logger = logging.getLogger("RoomberryMissionTest")
        self.robot.consume_clock_button_press.return_value = False
        self.mission = RoomberryMission(self.robot, self.camera, self.mapper, self.navigation, self.localizer, self.logger)

    def test_idle_startup_runs_multiple_mission_loops_with_display(self):
        mission = self.mission
        self.assertIsNone(mission._discovery_stage)
        mission._tick = Mock()
        iterations = []
        def wait(timeout):
            iterations.append(timeout)
            if len(iterations) == 2:
                mission._shutdown.set()
        with patch.object(mission._shutdown, 'wait', side_effect=wait):
            mission._run()
        self.assertEqual(mission._tick.call_count, 2)
        self.assertEqual(self.robot.set_drive_display.call_count, 2)
        self.robot.set_drive_display.assert_called_with(MODE_IDLE, None, False)

    def test_failed_display_does_not_kill_mission_loop(self):
        mission = self.mission
        mission._tick = Mock()
        self.robot.set_drive_display.side_effect = RuntimeError('display unavailable')
        iterations = []
        def wait(timeout):
            iterations.append(timeout)
            if len(iterations) == 2:
                mission._shutdown.set()
        with patch.object(mission._shutdown, 'wait', side_effect=wait), \
                patch.object(mission.logger, 'exception') as logged:
            mission._run()
        self.assertEqual(mission._tick.call_count, 2)
        self.assertEqual(logged.call_count, 2)

    def test_targeted_scan_aims_then_tries_thirty_degree_offsets(self):
        config = json.loads((Path(__file__).resolve().parents[2] / 'autonomy.json').read_text())
        mission = self.mission
        mission.discovery_landmarks = {x['id']: x for x in config['landmarks']}
        self.localizer.camera_from_robot = config['camera_from_robot']
        pose = dict(x_mm=3100, y_mm=1450, heading_rad=0, localized=True)
        self.assertEqual(mission._choose_scan_heading(pose)[0], 16)
        self.assertAlmostEqual(mission._choose_scan_heading(pose)[1], -pi/2)
        mission.set_mode(MODE_DISCOVERY)
        mission._discovery_stage = 'visit_approach'
        mission._scan_pose = pose
        self.assertFalse(mission.scan_pause())
        self.assertTrue(mission._aim_scan_pending)
        state = dict(sensors=self.discovery_sensors(), age=0, angle=0)
        mission._discovery_tick(state, pose, False, None)
        self.camera.request_scan.assert_not_called()
        self.assertFalse(mission.scan_pause())
        state['angle'] = -90
        mission._discovery_tick(state, pose, False, None)
        self.camera.request_scan.assert_called_once()
        for angle in (-60, -120):
            recovery = mission._localization_recovery
            mission._discovery_tick(state, pose, True, recovery['captured_after'] + 1)
            self.assertAlmostEqual(recovery['target'] * 180/pi, angle)
            state['angle'] = angle
            mission._discovery_tick(state, pose, False, None)
        recovery = mission._localization_recovery
        mission._discovery_tick(state, pose, True, recovery['captured_after'] + 1)
        self.assertFalse(mission._aim_scan_pending)
        self.assertEqual(mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.camera.request_scan.call_count, 3)
        self.assertFalse(any(c.args[0] in ('drive_straight', 'drive_direct')
                             for c in self.robot.execute.call_args_list))

    def test_target_choice_excludes_back_of_wall_tag_and_accounts_for_camera_yaw(self):
        mission = self.mission
        mission.discovery_landmarks = {15: dict(world_from_tag=
            [[0,0,1,7.73],[-1,0,0,1.52],[0,-1,0,.16],[0,0,0,1]])}
        self.assertIsNone(mission._choose_scan_heading(dict(x_mm=8000,y_mm=1520,heading_rad=0)))
        self.localizer.camera_from_robot = [[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]
        tag, heading = mission._choose_scan_heading(dict(x_mm=7000,y_mm=1520,heading_rad=0))
        self.assertEqual(tag,15)
        self.assertAlmostEqual(heading,-pi/2)

    def test_scan_debug_names_target_and_planned_heading(self):
        mission = self.mission
        mission.set_mode(MODE_DISCOVERY)
        mission._scan_pose = dict(x_mm=3100,y_mm=1450,heading_rad=-pi/2,localized=True)
        mission._localization_recovery = dict(tag_id=16,index=2,phase='scan',target=-pi/2)
        self.robot.snapshot.return_value = dict(angle=-90,oi_stopped=False)
        with self.assertLogs(self.logger,level='DEBUG') as logs:
            self.assertTrue(mission.scan_pause())
        joined = '\n'.join(logs.output)
        self.assertIn('target_tag=16',joined)
        self.assertIn('view=2',joined)
        self.assertIn('target_heading_deg=-90.0',joined)

    def test_pending_relocation_rechecks_same_view_before_turning(self):
        mission = self.mission
        mission.set_mode(MODE_DISCOVERY)
        mission._aim_scan_pending = True
        mission._localization_recovery = dict(origin=0,target=0,index=0,phase='scan',
                                              captured_after=0,deadline=monotonic()+180,tag_id=2)
        pose = dict(localized=False,x_mm=1000,y_mm=500,heading_rad=0,
            rejected_tags=((('tag16h5',2),'large relocation needs another consistent scan'),))
        state=dict(angle=0,sensors=self.discovery_sensors())
        self.robot.execute.reset_mock()
        mission._localization_recovery_tick(state,pose,True,time())
        self.camera.request_scan.assert_called_once()
        self.assertTrue(mission._localization_recovery['confirming'])
        self.assertEqual(mission._localization_recovery['index'],0)
        self.robot.execute.assert_not_called()

    def test_destination_log_repeats_after_one_minute_during_detour(self):
        mission = self.mission
        mission._mode = MODE_DISCOVERY
        mission._discovery_stage = 'avoid_forward'
        mission._discovery_waypoint = (3100.0, 450.0)
        mission._discovery_visit_tag = 16
        mission._discovery_visit_tags = [16, 15]
        mission._discovery_visit_index = 0
        pose = dict(x_mm=2100, y_mm=450, localized=True, localization_age=120)
        with patch.object(mission.logger, 'info') as info:
            with patch('roomberry_mission.monotonic', side_effect=[100, 159.9, 160]):
                mission._log_destination(pose)
                mission._log_destination(pose)
                mission._log_destination(pose)
            self.assertEqual(info.call_count, 2)
            args = info.call_args.args
            self.assertEqual(args[1:7],
                             (MODE_DISCOVERY, 'avoid_forward', 16,
                              (3100.0, 450.0), 1000.0, [16, 15]))

    @staticmethod
    def discovery_sensors(bump_left=False, bump_right=False,
                          light_signals=None):
        signals = light_signals or {}
        return SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
                bump_left=bump_left, bump_right=bump_right,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
            light_bumper=SimpleNamespace(
                left=False, front_left=False, center_left=False,
                center_right=False, front_right=False, right=False,
            ),
            **{
                'light_bump_' + zone + '_signal': int(
                    signals.get(zone, 0)
                )
                for zone in ('left', 'front_left', 'center_left',
                             'center_right', 'front_right', 'right')
            },
        )

    @staticmethod
    def visit_landmarks():
        return {
            1: {
                "family": "tag16h5", "id": 1, "surface": "carpet",
                "world_from_tag": [
                    [-1, 0, 0, 1.06], [0, 0, -1, 0.0],
                    [0, -1, 0, 0.16], [0, 0, 0, 1],
                ],
            },
            2: {
                "family": "tag16h5", "id": 2, "surface": "carpet",
                "world_from_tag": [
                    [0, 0, -1, 0.0], [1, 0, 0, 0.535],
                    [0, -1, 0, 0.16], [0, 0, 0, 1],
                ],
            },
            16: {
                "family": "tag16h5", "id": 16, "surface": "carpet",
                "world_from_tag": [
                    [1, 0, 0, 3.10], [0, 0, 1, 0.95],
                    [0, -1, 0, 0.16], [0, 0, 0, 1],
                ],
            },
            15: {
                "family": "tag16h5", "id": 15, "surface": "hard_floor",
                "world_from_tag": [
                    [0, 0, -1, 7.73], [1, 0, 0, 1.52],
                    [0, -1, 0, 0.16], [0, 0, 0, 1],
                ],
            },
        }

    def use_visit_landmarks(self):
        self.mission.discovery_landmarks = self.visit_landmarks()
        self.mission.set_mode(MODE_DISCOVERY)

    def test_discovery_mode_initializes_state_before_first_tick(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, "initial_scan")
        self.assertIsNone(self.mission._discovery_pose)
        self.assertIsNone(self.mission._discovery_scan_time)
        self.assertIsNone(self.mission._discovery_waypoint)
        self.assertEqual(self.mission._discovery_logged_tags, set())
        self.robot.execute.assert_any_call("_change_mode", mode=MODES.SAFE)
        self.robot.execute.assert_any_call("set_motors", main_brush_on=False, side_brush=False, vacuum=False)
        self.robot.execute.assert_any_call("wake")

    def test_schedule_button_edge_enters_discovery_mode(self):
        sensors = SimpleNamespace(bumps_and_wheel_drops=SimpleNamespace(wheel_drop_left=False, wheel_drop_right=False), cliff_left_sensor=False, cliff_front_left_sensor=False, cliff_front_right_sensor=False, cliff_right_sensor=False)
        self.robot.snapshot.return_value = {"schedule_button": True, "sensors": sensors, "ready": True, "age": 0.0}
        self.mission._tick()
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, "initial_scan")

    def test_discovery_initial_scan_requests_capture_and_waits(self):
        self.mission.set_mode(MODE_DISCOVERY)
        sensors = SimpleNamespace(bumps_and_wheel_drops=SimpleNamespace(wheel_drop_left=False, wheel_drop_right=False), cliff_left_sensor=False, cliff_front_left_sensor=False, cliff_front_right_sensor=False, cliff_right_sensor=False)
        self.mission._discovery_tick({"sensors": sensors, "age": 0.0}, None, False, None)
        self.camera.request_scan.assert_called_once_with()
        self.assertEqual(self.mission._discovery_stage, "initial_scan")
        self.assertIsNotNone(self.mission._discovery_scan_time)

    def test_clock_button_redirects_discovery_to_dock_staging(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._active_command = ('drive_straight', (('velocity', -50),))
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        self.mission._discovery_start_travelled = 100
        self.robot.consume_clock_button_press.return_value = True
        self.robot.snapshot.return_value = {
            "schedule_button": False, "clock_button": False,
            "travelled_distance": 450,
            "sensors": sensors, "ready": True, "age": 0.0,
        }

        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._tick()

        self.assertIn("returning to dock staging", captured.output[-1])
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, 'dock_approach')
        self.assertEqual(self.mission._discovery_waypoint, (1060.0, 560.0))
        self.robot.execute.assert_any_call("stop", timeout=2)

    def test_discovery_tick_preserves_start_travelled(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_start_travelled = 100.0
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 450.0,
        }

        self.mission._discovery_tick(state, None, False, None)

        self.assertEqual(self.mission._discovery_start_travelled, 100.0)

    def test_stale_sensor_packet_waits_for_fresh_data_without_aborting(self):
        self.mission.set_mode(MODE_DISCOVERY)
        stale = {"sensors": None, "age": None}
        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(stale, None, False, None)

        self.assertIn("waiting for fresh sensor data", captured.output[0])
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.camera.request_scan.assert_not_called()

        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        self.mission._discovery_tick({"sensors": sensors, "age": 0.0}, None, False, None)
        self.camera.request_scan.assert_called_once_with()
    def test_retreat_ends_after_500_mm_of_odometry_despite_pose_error(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._discovery_waypoint = (1060.0, 760.0)
        self.mission._discovery_retreat_start_distance = 0
        self.mission._active_command = ("drive_straight", (("velocity", -50),))
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
                bump_left=False, bump_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        pose = {"localized": True, "x_mm": 1044.0, "y_mm": -236.0}
        state = {"sensors": sensors, "age": 0.0, "distance": -500}

        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertTrue(any("500 mm" in line for line in captured.output))
        self.assertEqual(self.mission._discovery_stage, "retreat_scan")
        self.robot.execute.assert_any_call("stop", timeout=2)
    def test_new_bumper_contact_stops_reverse_retreat(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._discovery_waypoint = (1060.0, 760.0)
        self.mission._discovery_retreat_start_distance = 0
        self.mission._discovery_retreat_bumper_cleared = True
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
                bump_left=False, bump_right=True,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        pose = {"localized": True, "x_mm": 1000.0, "y_mm": 500.0}
        state = {"sensors": sensors, "age": 0.0, "distance": -120}

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertIn("bumper contact after clearing dock", captured.output[0])
        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.robot.execute.assert_any_call("stop", timeout=2)
    def test_tag_approach_waypoint_offsets_along_room_facing_normal(self):
        world_from_tag = [
            [0, 0, -1, 0.0],
            [1, 0, 0, 0.535],
            [0, -1, 0, 0.16],
            [0, 0, 0, 1],
        ]

        waypoint = self.mission._tag_approach_waypoint(world_from_tag, 500)

        self.assertEqual(waypoint, (500.0, 535.0))
    def test_tag2_contact_turns_toward_configured_wall_normal(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "tag2_contact"
        self.mission.discovery_landmarks[2] = {
            "world_from_tag": [
                [0, 0, -1, 0.0],
                [1, 0, 0, 0.535],
                [0, -1, 0, 0.16],
                [0, 0, 0, 1],
            ],
        }
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
                bump_left=False, bump_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
            light_bumper=SimpleNamespace(
                left=False, front_left=False, center_left=False,
                center_right=False, front_right=False, right=False,
            ),
        )
        state = {"sensors": sensors, "age": 0.0}
        pose = {"localized": True, "heading_rad": -1.57}

        self.mission._discovery_tick(state, pose, False, None)

        self.robot.execute.assert_any_call("spin_right", velocity=50)
    def test_retreat_scan_heads_directly_to_tag2_approach_waypoint(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.robot.execute.reset_mock()
        self.mission.discovery_landmarks[2] = {
            "world_from_tag": [
                [0, 0, -1, 0.0],
                [1, 0, 0, 0.535],
                [0, -1, 0, 0.16],
                [0, 0, 0, 1],
            ],
        }
        self.mission._discovery_stage = "retreat_scan"
        self.mission._discovery_scan_time = 1.0
        self.camera.latest_detections = ({"id": 1},)
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=False,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        state = {"sensors": sensors, "age": 0.0, "distance": -500}
        pose = {
            "localized": True, "x_mm": 1047.0, "y_mm": 716.0,
            "heading_rad": -1.65,
        }

        self.mission._discovery_tick(state, pose, True, 2.0)
        self.assertEqual(self.mission._discovery_stage, "tag2_approach")
        self.assertEqual(self.mission._discovery_waypoint, (500.0, 535.0))
        self.robot.execute.assert_not_called()

        # The approach point is only about 67 degrees clockwise from the retreat
        # heading, so the robot should turn right toward it instead of making a
        # full U-turn first.
        self.mission._discovery_tick(state, pose, False, None)
        self.assertTrue(self.mission._discovery_turning)
        self.robot.execute.assert_any_call("spin_right", velocity=50)

        aligned_pose = dict(pose, heading_rad=-2.82)
        self.mission._discovery_tick(state, aligned_pose, False, None)
        self.assertFalse(self.mission._discovery_turning)
        self.robot.execute.assert_any_call("drive_straight", velocity=60)
    def test_stopped_continuous_stage_requests_recovery_scan(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._active_command = ("drive_straight", (("velocity", -50),))
        sensors = self.discovery_sensors()
        state = {"sensors": sensors, "age": 0.0, "travelled_distance": 40.0}

        self.mission._discovery_tick(state, None, False, None)

        self.robot.execute.assert_any_call("stop", timeout=2)
        self.camera.request_scan.assert_called_with()

    def test_scan_pause_flushes_map_while_stopped(self):
        self.mission.scan_pause()

        self.robot.execute.assert_any_call("soft_stop", timeout=5)
        self.mapper.flush.assert_called_once_with()
        self.assertTrue(self.mission._scan_active)

    def test_scan_pause_does_not_interrupt_continuous_discovery_motion(self):
        self.mission.set_mode(MODE_DISCOVERY)

        for stage in ("retreat", "tag2_contact", "release_contact"):
            self.mission._discovery_stage = stage
            self.mission._active_command = ("drive_straight", (("velocity", -50),))
            self.mission._active_until = monotonic() + 1.0
            self.assertFalse(self.mission.scan_pause())
            self.assertFalse(self.mission._scan_active)
        self.mapper.flush.assert_not_called()

    def test_scan_pause_allows_recovery_scan_when_continuous_stage_stops(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._active_command = None
        self.mission._active_until = 0.0

        self.assertTrue(self.mission.scan_pause())

        self.robot.execute.assert_any_call("stop", timeout=2)
        self.mapper.flush.assert_called_once_with()
        self.assertTrue(self.mission._scan_active)

    def test_manual_control_cancels_mission_and_enters_remote_mode(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.robot.reset_mock()

        self.mission.take_manual_control()

        self.assertEqual(self.mission._mode, MODE_REMOTE)
        self.robot.execute.assert_any_call("_change_mode", mode=MODES.SAFE)
        self.assertGreater(self.mission._manual_motion_until, monotonic())

        self.robot.reset_mock()
        self.mission.take_manual_control()

        self.robot.execute.assert_not_called()

    def test_remote_scan_pause_skips_only_while_manually_moving(self):
        self.mission.set_mode(MODE_REMOTE)
        self.mission._manual_motion_until = monotonic() + 1.0
        self.robot.reset_mock()

        self.assertFalse(self.mission.scan_pause())
        self.robot.execute.assert_not_called()
        self.mapper.flush.assert_not_called()

        self.mission._manual_motion_until = 0.0
        self.robot.snapshot.return_value = {
            "sensors": SimpleNamespace(
                requested_left_velocity=0, requested_right_velocity=0,
            ),
        }
        self.robot.reset_mock()

        self.assertTrue(self.mission.scan_pause())
        self.mapper.flush.assert_called_once_with()
        self.assertTrue(self.mission._scan_active)

    def test_remote_mode_keeps_odometry_and_tag_updates_but_not_navigation(self):
        self.mission.set_mode(MODE_REMOTE)
        pose = {
            "x_mm": 100.0, "y_mm": 200.0, "heading_rad": 0.5,
            "localized": True, "localization_age": 1.0,
        }
        self.localizer.update.return_value = pose
        self.camera.last_detection_time = 10.0
        self.camera.latest_detections = [{"family": "tag16h5", "id": 1}]
        self.robot.snapshot.return_value = {
            "schedule_button": False, "clock_button": False,
            "sensors": self.discovery_sensors(), "ready": True, "age": 0.0,
            "distance": 321.0, "angle": 12.0, "travelled_distance": 321.0,
            "odometry_epoch": 1, "battery_status": "discharging",
        }
        self.robot.reset_mock()
        self.navigation.decide.reset_mock()

        self.mission._tick()

        self.assertEqual(self.localizer.update.call_args.args[1:3], (321.0, 12.0))
        self.mapper.update_pose.assert_called_once_with(
            100.0, 200.0, 0.5, localized=True,
        )
        self.assertIs(self.mission._scan_pose, pose)
        self.assertIsNone(self.mission._last_pose)
        self.navigation.decide.assert_not_called()
        self.robot.execute.assert_not_called()

    def test_remote_mode_requests_scan_when_manual_motion_stops(self):
        self.mission.set_mode(MODE_REMOTE)
        self.mission._remote_was_moving = True
        self.localizer.update.return_value = None
        self.camera.last_detection_time = None
        self.camera.latest_detections = ()
        self.robot.snapshot.return_value = {
            "schedule_button": False, "clock_button": False,
            "sensors": SimpleNamespace(
                requested_left_velocity=0, requested_right_velocity=0,
            ),
            "ready": True, "age": 0.0,
            "distance": 10.0, "angle": 0.0, "travelled_distance": 10.0,
            "odometry_epoch": 1, "battery_status": "discharging",
        }

        self.mission._tick()

        self.camera.request_scan.assert_called_once_with()
        self.assertFalse(self.mission._remote_was_moving)

    def test_schedule_button_edge_beeps(self):
        sensors = self.discovery_sensors()
        self.robot.snapshot.return_value = {
            "schedule_button": True, "clock_button": False,
            "sensors": sensors, "ready": True, "age": 0.0,
        }

        self.mission._tick()

        self.robot.beep.assert_called_once_with()
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)

    def test_schedule_beep_plays_after_entering_discovery_mode(self):
        sensors = self.discovery_sensors()
        self.robot.snapshot.return_value = {
            "schedule_button": True, "clock_button": False,
            "sensors": sensors, "ready": True, "age": 0.0,
        }
        modes = []
        self.robot.beep.side_effect = lambda: modes.append(self.mission._mode)

        self.mission._tick()

        self.assertEqual(modes, [MODE_DISCOVERY])

    def test_scan_pause_does_not_consume_detour_timeout(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_avoid_deadline = 108
        with patch('roomberry_mission.monotonic', return_value=100):
            self.assertTrue(self.mission.scan_pause())
        with patch('roomberry_mission.monotonic', return_value=106):
            self.mission.scan_complete()
        self.assertEqual(self.mission._discovery_avoid_deadline, 114)

    def test_idle_ignores_stale_requested_wheel_velocities(self):
        self.robot.snapshot.return_value = {'sensors': SimpleNamespace(
            requested_left_velocity=43, requested_right_velocity=43)}
        self.assertTrue(self.mission.scan_pause())

    def test_clock_is_processed_during_active_scan_and_remote_control(self):
        self.mission.set_mode(MODE_REMOTE)
        self.mission._scan_active = True
        self.robot.snapshot.return_value = {'clock_button': True}
        self.mission._shutdown = Mock()
        self.mission._shutdown.is_set.side_effect = [False, True]
        self.mission._run()
        self.assertTrue(self.mission._scan_active)
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, 'dock_approach')
        self.assertEqual(self.mission._discovery_waypoint, (1060, 560))

    def test_clock_button_edge_beeps(self):
        sensors = self.discovery_sensors()
        self.robot.snapshot.return_value = {
            "schedule_button": False, "clock_button": True,
            "sensors": sensors, "ready": True, "age": 0.0,
        }

        self.mission._tick()

        self.robot.beep.assert_called_once_with(event='unhappy')
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)

    @staticmethod
    def _waypoint_action(waypoint=(1000.0, 0.0)):
        return {
            "kind": GO_TO_WAYPOINT, "reason": "test waypoint",
            "max_duration_s": 1.0, "waypoint": waypoint,
        }

    def test_repeated_continuous_command_extends_without_stopping(self):
        self.mission._mode = MODE_DISCOVERY
        pose = {
            "localized": True, "x_mm": 0.0, "y_mm": 0.0, "heading_rad": 0.0,
        }
        action = self._waypoint_action()

        self.mission._dispatch(action, pose)
        first_deadline = self.mission._active_until
        self.mission._dispatch(action, pose)

        self.assertGreater(self.mission._active_until, first_deadline)
        self.robot.execute.assert_called_once_with("drive_straight", velocity=60)

    def test_continuous_command_reissues_after_heartbeat(self):
        self.mission._mode = MODE_DISCOVERY
        pose = {
            "localized": True, "x_mm": 0.0, "y_mm": 0.0, "heading_rad": 0.0,
        }
        action = self._waypoint_action()

        with patch("roomberry_mission.monotonic", return_value=100.0):
            self.mission._dispatch(action, pose)
        self.assertEqual(self.robot.execute.call_count, 1)

        with patch(
            "roomberry_mission.monotonic",
            return_value=100.0 + CONTINUOUS_REISSUE_SECONDS + 0.01,
        ):
            self.mission._dispatch(action, pose)

        self.assertEqual(self.robot.execute.call_count, 2)
        operations = [
            call.args[0] for call in self.robot.execute.call_args_list
            if call.args
        ]
        self.assertNotIn("stop", operations)

    def test_expired_continuous_command_stops_before_restarting(self):
        pose = {
            "localized": True, "x_mm": 0.0, "y_mm": 0.0, "heading_rad": 0.0,
        }
        action = self._waypoint_action()
        self.mission._dispatch(action, pose)
        self.mission._active_until = 0.0

        self.mission._dispatch(action, pose)

        self.robot.execute.assert_any_call("stop", timeout=2)
        self.assertIsNone(self.mission._active_command)

    def test_speed_only_drive_change_keeps_motion_running(self):
        action = {
            "kind": DRIVE, "reason": "slow down", "velocity": 50,
            "steering": 0.0, "max_duration_s": 1.0, "continuous": True,
        }
        self.mission._dispatch(action, None)
        action["velocity"] = 25
        self.mission._dispatch(action, None)

        self.robot.execute.assert_any_call(
            "drive_direct", right_velocity=50, left_velocity=50,
        )
        self.robot.execute.assert_any_call(
            "drive_direct", right_velocity=25, left_velocity=25,
        )
        stopped = [
            call for call in self.robot.execute.call_args_list
            if call.args and call.args[0] == "stop"
        ]
        self.assertEqual(stopped, [])

    def test_contact_mapping_is_gated_to_active_mission_stages(self):
        state = {"ready": True, "battery_status": "normal"}
        self.mission._mode = MODE_IDLE
        self.mission._discovery_stage = "tag2_contact"
        self.assertFalse(self.mission._contact_mapping_allowed(state))

        self.mission._mode = MODE_CLEAN
        self.assertTrue(self.mission._contact_mapping_allowed(state))
        self.assertFalse(self.mission._contact_mapping_allowed(
            {"ready": True, "battery_status": "charging"}
        ))

        self.mission._mode = MODE_DISCOVERY
        self.mission._discovery_stage = "retreat"
        self.assertFalse(self.mission._contact_mapping_allowed(state))
        self.mission._discovery_stage = "tag2_contact"
        self.assertTrue(self.mission._contact_mapping_allowed(state))

    def test_contact_obstacle_uses_bumper_radius_not_extra_cells(self):
        self.mapper.robot_radius_mm = 174.0
        self.mapper.cell_size_mm = 87.0
        pose = {"x_mm": 174.0, "y_mm": 535.0, "heading_rad": 3.141592653589793}
        observation = {
            "bumper": {"left": True, "right": True},
            "light_bumper": {
                "left": False, "front_left": False, "center_left": False,
                "center_right": False, "front_right": False, "right": False,
            },
        }

        self.mission._record_contact_obstacle(pose, observation)

        x_mm, y_mm = self.mapper.mark_obstacle.call_args.args
        self.assertAlmostEqual(x_mm, CONTACT_INSET_MM)
        self.assertAlmostEqual(y_mm, 535.0)

    def test_approach_point_aligns_with_tag_before_scan(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission.discovery_landmarks[2] = {
            "world_from_tag": [
                [0, 0, -1, 0.0],
                [1, 0, 0, 0.535],
                [0, -1, 0, 0.16],
                [0, 0, 0, 1],
            ],
        }
        self.mission._discovery_stage = "tag2_approach"
        self.mission._discovery_waypoint = (500.0, 535.0)
        sensors = self.discovery_sensors()
        state = {"sensors": sensors, "age": 0.0}
        pose = {
            "localized": True, "x_mm": 500.0, "y_mm": 535.0,
            "heading_rad": -2.384,
        }

        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "tag2_align")

        self.mission._discovery_tick(state, pose, False, None)
        self.robot.execute.assert_any_call("spin_right", velocity=50)

        aligned = dict(pose, heading_rad=3.141592653589793)
        self.mission._discovery_tick(state, aligned, False, None)
        self.assertEqual(self.mission._discovery_stage, "tag2_approach_scan")
        self.camera.request_scan.assert_not_called()

        self.mission._discovery_tick(state, aligned, False, None)
        self.camera.request_scan.assert_called_once_with()

    def test_tag2_missing_scan_retries_left_and_right_then_restores_heading(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission.discovery_landmarks[2] = {'world_from_tag': [
            [0, 0, -1, 0.0], [1, 0, 0, 0.535],
            [0, -1, 0, 0.16], [0, 0, 0, 1],
        ]}
        self.mission._discovery_stage = 'tag2_approach_scan'
        self.mission._discovery_scan_time = 1.0
        self.camera.latest_detections = []
        pose = dict(localized=True, x_mm=500.0, y_mm=535.0, heading_rad=3.14)
        state = dict(sensors=self.discovery_sensors(), age=0.0)
        for attempt, offset in enumerate((0.5, -0.5), 1):
            self.mission._discovery_tick(state, pose, True, 2.0)
            self.assertEqual(self.mission._discovery_stage, 'tag2_approach')
            self.assertEqual(self.mission._tag2_heading_offset, offset)
            self.mission._discovery_stage = 'tag2_approach_scan'
            self.mission._discovery_scan_time = 1.0
        pose['heading_rad'] = 2.64
        self.mission._discovery_tick(state, pose, True, 2.0)
        self.assertEqual(self.mission._discovery_stage, 'tag2_approach')
        self.assertEqual(self.mission._discovery_waypoint, (500.0, 535.0))

    def test_tag2_contact_does_not_scan_and_starts_reverse(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mapper.robot_radius_mm = 174.0
        self.mapper.cell_size_mm = 87.0
        self.mission._discovery_stage = "tag2_contact"
        self.mission.discovery_landmarks[2] = {
            "world_from_tag": [
                [0, 0, -1, 0.0],
                [1, 0, 0, 0.535],
                [0, -1, 0, 0.16],
                [0, 0, 0, 1],
            ],
        }
        sensors = self.discovery_sensors(bump_left=True, bump_right=True)
        state = {"sensors": sensors, "age": 0.0, "travelled_distance": 512.0}
        pose = {
            "localized": True, "x_mm": 174.0, "y_mm": 535.0,
            "heading_rad": 3.141592653589793,
        }

        self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "release_contact")
        self.assertEqual(self.mission._discovery_release_start_travelled, 512.0)
        self.camera.request_scan.assert_not_called()
        self.mapper.mark_obstacle.assert_called_once()

    def test_release_contact_ignores_light_bumpers_after_minimum_distance(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "release_contact"
        self.mission._discovery_release_started = None
        self.mission._discovery_release_start_travelled = 0.0
        self.mission._discovery_release_deadline = None
        self.mission._discovery_release_clear_since = None
        sensors = self.discovery_sensors(bump_left=True)
        state = {"sensors": sensors, "age": 0.0, "travelled_distance": 20.0}
        pose = {
            "localized": True, "x_mm": 174.0, "y_mm": 535.0,
            "heading_rad": 3.141592653589793,
        }

        with patch.object(self.mission, "_dispatch") as dispatch:
            self.mission._discovery_tick(state, pose, False, None)
        action = dispatch.call_args.args[0]
        self.assertEqual(action["kind"], "back_up")
        self.assertGreater(action["max_duration_s"], 0.5)
        self.assertEqual(self.mission._discovery_stage, "release_contact")

        # The physical bumper clears, but the reflective tag keeps the light
        # bumpers active while the robot is still too close.
        sensors.bumps_and_wheel_drops.bump_left = False
        sensors.light_bumper.center_left = True
        sensors.light_bumper.center_right = True
        state["travelled_distance"] = RELEASE_MIN_DISTANCE_MM / 2.0
        with patch.object(self.mission, "_dispatch") as dispatch:
            self.mission._discovery_tick(state, pose, False, None)
        self.assertTrue(dispatch.called)
        self.assertEqual(self.mission._discovery_stage, "release_contact")

        state["travelled_distance"] = RELEASE_MIN_DISTANCE_MM
        self.mission._discovery_release_clear_since = 0.0
        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "return")
        self.assertTrue(any("150 mm" in line for line in captured.output))
        self.assertTrue(
            any("light bumpers still report" in line for line in captured.output)
        )

    def test_release_contact_stops_at_max_distance_if_still_blocked(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "release_contact"
        self.mission._discovery_release_start_travelled = 0.0
        self.mission._discovery_release_deadline = None
        sensors = self.discovery_sensors(bump_left=True)
        state = {
            "sensors": sensors, "age": 0.0,
            "travelled_distance": RELEASE_MAX_DISTANCE_MM,
        }
        pose = {
            "localized": True, "x_mm": 174.0, "y_mm": 535.0,
            "heading_rad": 3.141592653589793,
        }

        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.assertTrue(any("250 mm" in line for line in captured.output))
        self.robot.execute.assert_any_call("stop", timeout=2)

    def test_discovery_visit_order_excludes_dock_and_contact_tags(self):
        self.use_visit_landmarks()

        self.assertEqual(self.mission._discovery_visit_order(), [16, 15])

    def test_autonomy_config_uses_corrected_tag15_and_surfaces(self):
        config_path = Path(__file__).resolve().parents[2] / "autonomy.json"
        config = json.loads(config_path.read_text())
        landmarks = {int(item["id"]): item for item in config["landmarks"]}

        self.assertEqual(
            [int(item["id"]) for item in config["landmarks"]],
            [1, 2, 16, 15],
        )
        self.assertEqual(landmarks[1]["surface"], "carpet")
        self.assertEqual(landmarks[2]["surface"], "carpet")
        self.assertEqual(landmarks[16]["surface"], "carpet")
        self.assertEqual(landmarks[15]["surface"], "hard_floor")
        tag15 = landmarks[15]["world_from_tag"]
        self.assertEqual((tag15[0][2], tag15[1][2]), (1, 0))
        self.assertEqual(
            self.mission._tag_approach_waypoint(tag15, 500),
            (7230.0, 1520.0),
        )
        self.assertAlmostEqual(self.mission._tag_normal_heading(tag15), 0)

    def test_release_contact_starts_tag16_visit(self):
        self.use_visit_landmarks()
        self.mission._discovery_stage = "release_contact"
        self.mission._discovery_release_start_travelled = 0.0
        self.mission._discovery_release_deadline = None
        self.mission._discovery_release_clear_since = 0.0
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 160.0,
        }
        pose = {
            "localized": True, "x_mm": 332.0, "y_mm": 535.0,
            "heading_rad": 0.0,
        }

        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertEqual(self.mission._discovery_visit_tag, 16)
        self.assertEqual(
            self.mission._discovery_waypoint,
            (3100.0, 450.0),
        )
        self.assertTrue(any(
            "tag 16" in line and "carpet" in line for line in captured.output
        ))

    def test_rejected_transit_tag_repositions_and_resumes_wall_survey(self):
        self.use_visit_landmarks()
        self.mission._discovery_stage = 'wall_follow'
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.camera.latest_detections = [dict(id=15, family='tag16h5', hamming=0,
                                             decision_margin=50)]
        pose = dict(localized=True, x_mm=7000, y_mm=1000, heading_rad=0,
                    accepted_tag_ids=(), tag_ids=(('tag16h5', 15),))
        state = dict(sensors=self.discovery_sensors(), age=0.0, travelled_distance=5000)
        self.mission._discovery_tick(state, pose, True, 2.0)
        self.assertEqual(self.mission._discovery_stage, 'visit_approach')
        self.assertEqual(self.mission._discovery_visit_tag, 15)
        self.assertEqual(self.mission._discovery_waypoint, (8230.0, 1520.0))
        self.mission._begin_discovery_visit()
        self.assertEqual(self.mission._discovery_stage, 'wall_follow')
        self.assertEqual(self.mission._discovery_waypoint, (3100.0, 450.0))
        self.mission._discovery_tick(state, pose, True, 3.0)
        self.assertEqual(self.mission._discovery_stage, 'wall_follow')

    def test_scan_result_sound_uses_fresh_acceptance(self):
        self.mission.set_mode(MODE_REMOTE)
        self.camera.pause_for_detection = False
        self.camera.latest_detections = [dict(family='tag16h5', id=2)]
        self.robot.snapshot.return_value = dict(
            schedule_button=False, clock_button=False, sensors=self.discovery_sensors(),
            ready=True, age=0.0, distance=0.0, angle=0.0, travelled_distance=0.0,
            battery_status='normal')
        for accepted, event in (((('tag16h5', 2),), 'happy'), ((), 'unhappy')):
            self.camera.last_detection_time = time()
            self.localizer.update.return_value = dict(x_mm=500, y_mm=500,
                heading_rad=0, localized=True, tag_ids=(('tag16h5', 2),),
                accepted_tag_ids=accepted)
            self.robot.beep.reset_mock()
            self.mission._tick()
            if event == 'happy':
                self.robot.beep.assert_called_once_with()
            else:
                self.robot.beep.assert_called_once_with(event='unhappy')

    def test_scan_start_plays_neutral_tone(self):
        self.mission.scan_pause()
        self.robot.beep.assert_called_once_with(event='neutral')

    def test_visit_alignment_then_scan_advances_to_tag15(self):
        self.use_visit_landmarks()
        self.mission._discovery_visit_tags = [16, 15]
        self.mission._discovery_visit_index = 0
        self.mission._discovery_visit_tag = 16
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 5000.0,
        }
        pose = {
            "localized": True, "x_mm": 3100.0, "y_mm": 450.0,
            "heading_rad": 0.0,
        }

        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "visit_align")
        self.mission._discovery_tick(state, pose, False, None)
        self.robot.execute.assert_any_call("spin_left", velocity=50)

        aligned = dict(pose, heading_rad=pi / 2.0)
        self.mission._discovery_tick(state, aligned, False, None)
        self.assertEqual(self.mission._discovery_stage, "visit_scan")
        self.camera.request_scan.assert_not_called()

        self.mission._discovery_tick(state, aligned, False, None)
        self.camera.request_scan.assert_called_once_with()
        self.assertEqual(
            self.mission._discovery_visit_arrival_pose["x_mm"], 3100.0,
        )

        self.camera.latest_detections = [{"id": 16}]
        corrected = dict(aligned, x_mm=3125.0, y_mm=470.0, heading_rad=1.52,
                         accepted_tag_ids=(('tag16h5', 16),))
        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(
                state, corrected, True, self.mission._discovery_scan_time + 1.0,
            )

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertEqual(self.mission._discovery_visit_tag, 15)
        self.assertEqual(
            self.mission._discovery_waypoint,
            (8230.0, 1520.0),
        )
        self.assertTrue(any(
            "odometry_deviation_mm" in line for line in captured.output
        ))
        self.assertTrue(any(
            "tag 16" in line and "carpet" in line for line in captured.output
        ))

    def test_missing_visit_tag_retries_then_continues(self):
        self.use_visit_landmarks()
        self.mission._discovery_visit_tags = [16, 15]
        self.mission._discovery_visit_index = 0
        self.mission._discovery_visit_tag = 16
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_scan"
        self.mission._discovery_scan_time = 1.0
        pose = {
            "localized": True, "x_mm": 3100.0, "y_mm": 450.0,
            "heading_rad": pi / 2.0,
        }
        self.mission._discovery_visit_arrival_pose = dict(pose)
        self.camera.latest_detections = []
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 5000.0,
        }

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, True, 2.0)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertNotEqual(self.mission._discovery_waypoint, (3100.0, 450.0))
        self.assertEqual(self.mission._discovery_visit_retry_index, 1)
        self.assertAlmostEqual(self.mission._discovery_waypoint[0],
                               3100.0 - VISIT_RETRY_LATERAL_OFFSETS_MM[0])
        self.assertTrue(any("lateral offset" in line for line in captured.output))

        self.mission._discovery_stage = "visit_scan"
        self.mission._discovery_scan_time = 1.0
        self.mission._discovery_visit_retry_index = len(
            VISIT_RETRY_LATERAL_OFFSETS_MM
        )
        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, True, 2.0)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertEqual(self.mission._discovery_visit_tag, 15)
        self.assertTrue(any(
            "continuing with surveyed geometry" in line
            for line in captured.output
        ))

    def test_return_route_uses_earlier_visit_parking_then_retreat(self):
        self.use_visit_landmarks()
        self.mission._discovery_visit_tags = [16, 15]

        self.assertEqual(
            self.mission._discovery_return_route(),
            [(3100.0, 450.0), (1060.0, 760.0)],
        )

    def test_return_stage_advances_checkpoints_then_completes(self):
        self.use_visit_landmarks()
        self.mission._discovery_stage = "return"
        self.mission._discovery_return_waypoints = [
            (3100.0, 450.0), (1060.0, 760.0),
        ]
        self.mission._discovery_return_index = 0
        self.mission._discovery_waypoint = (3100.0, 450.0)
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 9000.0,
        }
        pose = {
            "localized": True, "x_mm": 3100.0, "y_mm": 450.0,
            "heading_rad": 0.0,
        }

        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "return")
        self.assertEqual(self.mission._discovery_return_index, 1)
        self.assertEqual(self.mission._discovery_waypoint, (1060.0, 760.0))
        self.assertTrue(any(
            "return checkpoint" in line for line in captured.output
        ))

        retreat = dict(pose, x_mm=1060.0, y_mm=760.0)
        self.mission._discovery_tick(state, retreat, False, None)

        self.assertEqual(self.mission._discovery_stage, "dock_approach")
        self.assertEqual(self.mission._discovery_waypoint, (1060.0, 300.0))
        dock_app = dict(pose, x_mm=1060.0, y_mm=300.0)
        self.mission._discovery_tick(state, dock_app, False, None)
        self.assertEqual(self.mission._discovery_stage, "dock_align")
        import math
        dock_aligned = dict(pose, x_mm=1060.0, y_mm=300.0, heading_rad=-math.pi/2)
        self.mission._discovery_tick(state, dock_aligned, False, None)
        self.assertEqual(self.mission._discovery_stage, "complete")
        self.robot.execute.assert_any_call('_change_mode', mode=MODES.PASSIVE)
        self.navigation.set_mode.assert_called_with(MODE_IDLE)
        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.mapper.flush.assert_called_once_with()

    def test_passive_failure_does_not_report_discovery_complete(self):
        self.use_visit_landmarks()
        self.mission._discovery_stage = 'dock_align'
        self.robot.execute.side_effect = lambda operation, **kwargs: (
            (_ for _ in ()).throw(RuntimeError('mode failed'))
            if operation == '_change_mode' else None
        )
        state = {'sensors': self.discovery_sensors(), 'age': 0.0}
        pose = {'localized': True, 'x_mm': 1060.0, 'y_mm': 300.0,
                'heading_rad': -pi / 2}
        with self.assertLogs(self.logger, level='ERROR'):
            self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.assertEqual(self.mission._discovery_stage, 'passive_failed')
        self.mapper.flush.assert_called_once_with()

    def test_visit_ir_proximity_slows_without_reversing(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = 'visit_approach'
        sensors = self.discovery_sensors(light_signals={'front_right': 620})
        state = dict(sensors=sensors, age=0.0, travelled_distance=1000.0)
        pose = dict(localized=True, x_mm=2140.0, y_mm=450.0, heading_rad=0.0)
        for _ in range(DISCOVERY_PROXIMITY_CONFIRM_TICKS + 1):
            self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, 'visit_approach')
        self.assertEqual(self.mission._discovery_avoid_attempts, 0)
        calls = self.robot.execute.call_args_list
        drive = [c for c in calls if c.args[0] == 'drive_straight']
        self.assertTrue(drive)
        self.assertEqual(drive[-1].kwargs['velocity'], 40)

    def test_single_proximity_spike_does_not_start_detour(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        self.mission._discovery_avoid_grace_start = 0.0
        spike = self.discovery_sensors(light_signals={"front_left": 50})
        quiet = self.discovery_sensors()
        state = {
            "sensors": spike, "age": 0.0, "travelled_distance": 1000.0,
        }
        pose = {
            "localized": True, "x_mm": 1100.0, "y_mm": 650.0,
            "heading_rad": 0.0,
        }

        for _ in range(DISCOVERY_PROXIMITY_CONFIRM_TICKS - 1):
            self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "visit_approach")

        state["sensors"] = quiet
        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_proximity_ticks, 0)

        state["sensors"] = spike
        for _ in range(DISCOVERY_PROXIMITY_CONFIRM_TICKS - 1):
            self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertEqual(self.mission._discovery_avoid_attempts, 0)

    def test_light_bumper_bit_does_not_replace_physical_contact(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        self.mission._discovery_avoid_grace_start = 0.0
        sensors = self.discovery_sensors()
        sensors.light_bumper.center_right = True
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 1000.0,
        }
        pose = {
            "localized": True, "x_mm": 2000.0, "y_mm": 450.0,
            "heading_rad": 0.0,
        }

        self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")

    def test_stale_localization_logs_rejection_once(self):
        self.mission._discovery_stage = "visit_approach"
        state = {
            "sensors": self.discovery_sensors(), "age": 0.0,
            "travelled_distance": 1000.0,
        }
        pose = {
            "localized": False, "localization_age": 601.0,
            "tag_ids": (("tag16h5", 2),),
            "rejected_tags": ((("tag16h5", 2), "weak margin=2.0"),),
        }

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, False, None)
            self.mission._discovery_tick(state, pose, False, None)

        messages = [
            line for line in captured.output
            if "localization unavailable" in line
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("weak margin", messages[0])
        self.robot.execute.assert_any_call("stop", timeout=2)

    def test_obstacle_detour_forward_timeout_covers_parallel_leg(self):
        self.assertGreater(
            DISCOVERY_AVOID_FORWARD_TIMEOUT_SECONDS,
            DISCOVERY_AVOID_FORWARD_MM / DISCOVERY_AVOID_SPEED + 2.0,
        )

    def test_physical_bumper_overrides_opposite_ir_and_varies_detours(self):
        from unittest.mock import patch
        self.mission.set_mode(MODE_DISCOVERY)
        sensors = self.discovery_sensors(bump_right=True,
                                          light_signals={'front_left': 1500})
        state = dict(sensors=sensors, age=0.0, travelled_distance=1000.0)
        pose = dict(localized=True, x_mm=2000, y_mm=600, heading_rad=0)
        targets = []
        for sample in ((80, 100, pi / 7), (120, 220, pi / 3)):
            with patch('roomberry_mission.uniform', side_effect=sample):
                self.mission._begin_discovery_avoid('visit_approach', sensors,
                                                    pose, state, source='contact')
            self.assertEqual(self.mission._discovery_avoid_side, 'right')
            targets.append(self.mission._discovery_avoid_turn_target)
            self.assertGreater(targets[-1], 0)
        self.assertNotEqual(targets[0], targets[1])

    def test_stale_localization_can_reverse_but_not_turn_or_drive(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = 'wall_follow'
        sensors = self.discovery_sensors(bump_left=True)
        state = dict(sensors=sensors, age=0.0, travelled_distance=1000.0)
        pose = dict(localized=False, x_mm=2000, y_mm=600, heading_rad=0)
        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, 'avoid_back')
        self.robot.execute.reset_mock()
        self.mission._discovery_tick(state, pose, False, None)
        self.robot.execute.assert_any_call('drive_straight', velocity=-40)
        state['travelled_distance'] = 1125
        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, 'avoid_turn')
        self.robot.execute.reset_mock()
        self.mission._discovery_tick(state, pose, False, None)
        self.assertFalse(any(c.args[0].startswith('spin') for c in self.robot.execute.call_args_list))

    def test_hard_hazard_prevents_blind_reverse(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = 'avoid_back'
        sensors = self.discovery_sensors()
        sensors.bumps_and_wheel_drops.wheel_drop_left = True
        state = dict(sensors=sensors, age=0.0, travelled_distance=1000.0)
        self.robot.execute.reset_mock()
        self.mission._discovery_tick(state, None, False, None)
        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.assertFalse(any(c.args[0] == 'drive_straight' for c in self.robot.execute.call_args_list))

    def test_wall_contact_skips_forward_detour_leg(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = 'avoid_turn'
        self.mission._discovery_avoid_return_stage = 'wall_follow'
        self.mission._discovery_avoid_turn_target = 0.0
        self.mission._discovery_avoid_deadline = None
        state = dict(sensors=self.discovery_sensors(), age=0.0, travelled_distance=1000.0)
        pose = dict(localized=True, x_mm=2000, y_mm=600, heading_rad=0)
        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, 'wall_follow')

    def test_assumed_boundary_traverses_with_wall_on_right(self):
        self.mapper.cols = 90
        self.mapper.rows = 80
        self.mapper.cell_size_mm = 100
        self.mapper.origin_x = 0
        self.mapper.origin_y = 0
        self.mapper.robot_radius_mm = 174
        mission = self.mission
        goal = mission._wall_boundary_waypoint(dict(x_mm=400, y_mm=3000))
        self.assertEqual(goal, (274, 3000))
        goal = mission._wall_boundary_waypoint(dict(x_mm=274, y_mm=3000))
        self.assertEqual(goal, (274, 274))
        goal = mission._wall_boundary_waypoint(dict(x_mm=274, y_mm=274))
        self.assertEqual(goal, (8726, 274))
        goal = mission._wall_boundary_waypoint(dict(x_mm=8726, y_mm=274))
        self.assertEqual(goal, (8726, 7726))
        goal = mission._wall_boundary_waypoint(dict(x_mm=8726, y_mm=7726))
        self.assertEqual(goal, (274, 7726))
        goal = mission._wall_boundary_waypoint(dict(x_mm=274, y_mm=7726))
        self.assertEqual(goal, (274, 274))

    def test_localization_recovery_changes_viewpoint_and_requests_once(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage='wall_follow'
        self.robot.execute.reset_mock()
        state=dict(sensors=self.discovery_sensors(),age=0.0,angle=0.0,travelled_distance=1000)
        pose=dict(localized=False,x_mm=8000,y_mm=1500,heading_rad=0)
        self.mission._discovery_tick(state,pose,False,None)
        self.mission._discovery_tick(state,pose,False,None)
        self.camera.request_scan.assert_called_once_with()
        recovery=self.mission._localization_recovery
        self.mission._discovery_tick(state,pose,True,recovery['captured_after']+1)
        self.robot.execute.assert_any_call('spin_left',velocity=50)
        self.assertEqual(recovery['phase'],'turn')
        state['angle']=30
        self.mission._discovery_tick(state,pose,False,None)
        self.assertEqual(recovery['phase'],'scan')
        self.assertEqual(self.camera.request_scan.call_count,2)
        self.assertFalse(any(c.args[0] in ('drive_straight','drive_direct') for c in self.robot.execute.call_args_list))

    def test_localization_recovery_exhaustion_is_bounded(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage='wall_follow'
        state=dict(sensors=self.discovery_sensors(),age=0.0,angle=0.0,travelled_distance=1000)
        pose=dict(localized=False,x_mm=8000,y_mm=1500,heading_rad=0)
        self.mission._discovery_tick(state,pose,False,None)
        for _ in range(11):
            recovery=self.mission._localization_recovery
            self.mission._discovery_tick(state,pose,True,recovery['captured_after']+1)
            state['angle']=recovery['target']*180/pi
            self.mission._discovery_tick(state,pose,False,None)
        recovery=self.mission._localization_recovery
        self.mission._discovery_tick(state,pose,True,recovery['captured_after']+1)
        self.assertEqual(self.mission._mode,MODE_IDLE)
        self.assertIsNone(self.mission._localization_recovery)
        self.assertEqual(self.camera.request_scan.call_count,12)

    def test_localization_recovery_timeout_stops(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage='wall_follow'
        state=dict(sensors=self.discovery_sensors(),age=0.0,angle=0.0,travelled_distance=1000)
        pose=dict(localized=False,x_mm=8000,y_mm=1500,heading_rad=0)
        self.mission._discovery_tick(state,pose,False,None)
        self.mission._localization_recovery['deadline']=monotonic()-1
        self.mission._discovery_tick(state,pose,False,None)
        self.assertEqual(self.mission._mode,MODE_IDLE)

    def test_wall_avoidance_clears_forward_before_boundary_reacquisition(self):
        from unittest.mock import patch
        self.mission.set_mode(MODE_DISCOVERY)
        mission=self.mission
        mission._discovery_stage='avoid_turn'
        mission._discovery_avoid_return_stage='wall_follow'
        mission._discovery_avoid_turn_target=0.0
        mission._discovery_avoid_deadline=None
        state=dict(sensors=self.discovery_sensors(),age=0.0,angle=0.0,travelled_distance=1000)
        pose=dict(localized=True,x_mm=8000,y_mm=1500,heading_rad=0)
        mission._discovery_tick(state,pose,False,None)
        self.robot.execute.reset_mock()
        with patch.object(mission,'_wall_boundary_waypoint',return_value=(7000,1500)) as boundary:
            mission._discovery_tick(state,pose,False,None)
            boundary.assert_not_called()
            self.robot.execute.assert_any_call('drive_direct',right_velocity=50,left_velocity=50)
            state['travelled_distance']=1181
            mission._discovery_tick(state,pose,False,None)
            boundary.assert_called_once_with(pose)

    def test_oi_stop_prevents_buttons_and_camera_from_rearming(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.robot.execute.reset_mock()
        self.robot.snapshot.return_value=dict(oi_stopped=True,clock_button=True,schedule_button=True)
        self.mission._tick()
        self.assertEqual(self.mission._mode,MODE_IDLE)
        self.assertFalse(self.mission.scan_pause())
        self.assertFalse(any(c.args[0]=='_change_mode' for c in self.robot.execute.call_args_list))

    def test_restart_discards_capture_from_before_carry_even_if_recently_processed(self):
        self.robot.snapshot.return_value=dict(restart_generation=1,sensors=self.discovery_sensors(),
            ready=True,age=0.0,distance=0,angle=0,travelled_distance=0,battery_status='normal')
        self.localizer.update.return_value=None
        self.navigation.decide.return_value=dict(kind='wait',reason='no mission',max_duration_s=0)
        self.camera.pause_for_detection=True
        self.camera.last_detection_time=time()-5
        self.camera.last_detection_ready_time=time()
        self.camera.latest_detections=[dict(family='tag16h5',id=15)]
        self.mission._tick()
        self.assertFalse(self.localizer.update.call_args.kwargs['new_detections'])
        self.assertEqual(self.localizer.update.call_args.args[0],())
        self.camera.last_detection_time=self.mission._detections_after_restart+.01
        self.mission._tick()
        self.assertTrue(self.localizer.update.call_args.kwargs['new_detections'])

    def test_interface_restart_invalidates_old_localization_once(self):
        self.robot.snapshot.return_value=dict(restart_generation=1,sensors=None,ready=False)
        self.mission._tick()
        self.mission._tick()
        self.localizer.invalidate_pose.assert_called_once_with()
        self.camera.request_scan.assert_called_once_with()

    def test_obstacle_detour_reverses_turns_and_rejoins_route(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_avoid_return_stage = "visit_approach"
        self.mission._discovery_avoid_turn_target = pi / 2.0
        self.mission._discovery_avoid_start_travelled = 1000.0
        self.mission._discovery_stage = "avoid_back"
        sensors = self.discovery_sensors()
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 1000.0,
        }
        pose = {
            "localized": True, "x_mm": 2140.0, "y_mm": 440.0,
            "heading_rad": 0.0,
        }

        self.mission._discovery_tick(state, pose, False, None)
        self.robot.execute.assert_any_call("drive_straight", velocity=-40)

        state["travelled_distance"] = (
            1000.0 + DISCOVERY_AVOID_REVERSE_MM
        )
        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "avoid_turn")

        self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._discovery_stage, "avoid_turn")
        self.robot.execute.assert_any_call("spin_left", velocity=50)

        aligned = dict(pose, heading_rad=pi / 2.0)
        self.mission._discovery_tick(state, aligned, False, None)
        self.assertEqual(self.mission._discovery_stage, "avoid_forward")

        state["travelled_distance"] = (
            1000.0 + DISCOVERY_AVOID_REVERSE_MM + DISCOVERY_AVOID_FORWARD_MM
        )
        with self.assertLogs(self.logger, level="INFO") as captured:
            self.mission._discovery_tick(state, aligned, False, None)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertTrue(any(
            "resuming visit_approach" in line for line in captured.output
        ))

    def test_visit_proximity_is_ignored_right_after_tag_two_release(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        self.mission._discovery_avoid_grace_start = 0.0
        sensors = self.discovery_sensors(light_signals={"center_right": 500})
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 100.0,
        }
        pose = {
            "localized": True, "x_mm": 800.0, "y_mm": 550.0,
            "heading_rad": 0.0,
        }

        self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._discovery_stage, "visit_approach")
        self.assertEqual(self.mission._discovery_avoid_attempts, 0)

    def test_unexpected_bumper_contact_starts_detour(self):
        self.use_visit_landmarks()
        self.mission._discovery_visit_tags = [16, 15]
        self.mission._discovery_visit_index = 0
        self.mission._discovery_visit_tag = 16
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        self.mapper.robot_radius_mm = 174.0
        self.mapper.cell_size_mm = 87.0
        sensors = self.discovery_sensors(bump_right=True)
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 1000.0,
        }
        pose = {
            "localized": True, "x_mm": 1633.0, "y_mm": 571.0,
            "heading_rad": 0.0,
        }

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, "avoid_back")
        self.assertEqual(self.mission._discovery_avoid_attempts, 1)
        self.assertEqual(self.mission._discovery_avoid_side, "right")
        self.assertGreaterEqual(self.mission._discovery_avoid_turn_target, pi / 7)
        self.assertLessEqual(self.mission._discovery_avoid_turn_target, pi / 3)
        self.assertTrue(any(
            "bumper contact during visit_approach" in line
            for line in captured.output
        ))
        self.mapper.mark_obstacle.assert_called_once()
        self.robot.execute.assert_any_call("stop", timeout=2)

    def test_repeated_bumper_contact_starts_another_detour(self):
        self.use_visit_landmarks()
        self.mission._discovery_waypoint = (3100.0, 450.0)
        self.mission._discovery_stage = "visit_approach"
        self.mission._discovery_avoid_attempts = 100
        self.mapper.robot_radius_mm = 174.0
        self.mapper.cell_size_mm = 87.0
        sensors = self.discovery_sensors(bump_right=True)
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 2000.0,
        }
        pose = {
            "localized": True, "x_mm": 2500.0, "y_mm": 450.0,
            "heading_rad": 0.0,
        }

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertEqual(self.mission._discovery_stage, 'avoid_back')
        self.assertEqual(self.mission._discovery_avoid_attempts, 101)
        self.mapper.flush.assert_not_called()

    def test_bumper_during_parallel_detour_retries_original_destination(self):
        self.use_visit_landmarks()
        mission = self.mission
        mission._discovery_stage = 'avoid_forward'
        mission._discovery_avoid_return_stage = 'visit_approach'
        mission._discovery_waypoint = (3100.0, 450.0)
        mission._discovery_route_step = (2300.0, 600.0)
        self.mapper.robot_radius_mm = 174.0
        self.mapper.cell_size_mm = 87.0
        sensors = self.discovery_sensors(bump_left=True)
        state = dict(sensors=sensors, age=0.0, travelled_distance=2000.0)
        pose = dict(localized=True, x_mm=2000, y_mm=600, heading_rad=0)
        mission._discovery_tick(state, pose, False, None)
        self.assertEqual(mission._mode, MODE_DISCOVERY)
        self.assertEqual(mission._discovery_stage, 'avoid_back')
        self.assertEqual(mission._discovery_avoid_return_stage, 'visit_approach')
        self.assertEqual(mission._discovery_waypoint, (3100.0, 450.0))
        self.assertIsNone(mission._discovery_route_step)
        self.mapper.mark_obstacle.assert_called_once()

    def test_parallel_detour_continues_on_sustained_ir_proximity(self):
        self.use_visit_landmarks()
        mission = self.mission
        mission._discovery_stage = 'avoid_forward'
        mission._discovery_avoid_return_stage = 'visit_approach'
        mission._discovery_avoid_deadline = None
        mission._discovery_avoid_start_travelled = 0
        sensors = self.discovery_sensors(light_signals={'front_left': 300})
        pose = dict(localized=True, x_mm=2000, y_mm=600, heading_rad=0)
        state = dict(sensors=sensors, age=0.0, travelled_distance=10)
        for _ in range(DISCOVERY_PROXIMITY_CONFIRM_TICKS):
            mission._discovery_avoid_tick('avoid_forward', state, pose, sensors)
        self.assertEqual(mission._discovery_stage, 'avoid_forward')
        self.assertEqual(mission._discovery_avoid_return_stage, 'visit_approach')

    def test_discovery_route_follows_map_without_cutting_corner(self):
        self.use_visit_landmarks()
        mission = self.mission
        mission._discovery_avoid_attempts = 1
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
        self.mapper.plan_to.return_value = {'path': path}
        self.mapper.cell_center.return_value = (250, 50)
        pose = dict(x_mm=50, y_mm=50)
        self.assertEqual(mission._discovery_route_target((250, 250), pose), (250, 50))
        self.mapper.cell_center.assert_called_once_with((2, 0))
        mission._discovery_route_target((250, 250), pose)
        self.mapper.plan_to.assert_called_once()

    def test_discovery_no_map_path_starts_alternative_detour(self):
        self.use_visit_landmarks()
        mission = self.mission
        mission._discovery_stage = 'visit_approach'
        mission._discovery_waypoint = (3100, 450)
        mission._discovery_avoid_attempts = 1
        mission._discovery_avoid_side = 'left'
        self.mapper.plan_to.return_value = None
        sensors = self.discovery_sensors()
        state = dict(sensors=sensors, age=0.0, travelled_distance=2000)
        pose = dict(localized=True, x_mm=2000, y_mm=600, heading_rad=0)
        mission._discovery_tick(state, pose, False, None)
        self.assertEqual(mission._mode, MODE_DISCOVERY)
        self.assertEqual(mission._discovery_stage, 'wall_follow')
        for _ in range(5):
            mission._discovery_tick(state, pose, False, None)
        self.mapper.plan_to.assert_called_once()
        self.assertEqual(mission._discovery_stage, 'wall_follow')

    def test_discovery_reaches_goal_around_real_mapped_obstacle(self):
        from roomberry_mapper import RoomberryMapper
        mapper = RoomberryMapper(20, 20, 100, cell_size_mm=100)
        mapper.mark_obstacle(850, 550)
        mission = self.mission
        mission.mapper = mapper
        mission._discovery_avoid_attempts = 1
        pose = dict(x_mm=250, y_mm=550)
        goal = (1550, 550)
        route = []
        for _ in range(20):
            mapper.update_pose(pose['x_mm'], pose['y_mm'], 0, localized=True)
            step = mission._discovery_route_target(goal, pose)
            self.assertIsNotNone(step)
            # Verify the entire driven segment respects obstacle clearance.
            for i in range(101):
                fraction = i / 100
                x = pose['x_mm'] + (step[0] - pose['x_mm']) * fraction
                y = pose['y_mm'] + (step[1] - pose['y_mm']) * fraction
                self.assertTrue(mapper._is_traversable(mapper.world_to_cell(x, y)))
            route.append(step)
            pose.update(x_mm=step[0], y_mm=step[1])
            if step == goal:
                break
        self.assertEqual(route[-1], goal)
        self.assertTrue(any(y != 550 for x, y in route))

    def test_tag_range_records_miss_and_accepted_sighting(self):
        self.use_visit_landmarks()
        mission = self.mission
        mission._discovery_visit_tag = 15
        mission._discovery_stage = 'visit_approach'
        pose = dict(x_mm=2000, y_mm=600, heading_rad=0, localized=True,
                    localization_age=5, tag_ids=(), rejected_tags=())
        with self.assertLogs(self.logger, level='INFO') as logs:
            mission._log_tag_ranges(pose, (), 100)
        self.assertIn('tag=15', logs.output[0])
        self.assertIn('result=not_detected', logs.output[0])
        self.assertIn('survey_distance_mm=', logs.output[0])
        detection = dict(family='tag16h5', id=15, distance_mm=3000,
                         decision_margin=25, hamming=0, tag_pose_camera={'error': 1})
        pose['tag_ids'] = (('tag16h5', 15),)
        pose['accepted_tag_ids'] = (('tag16h5', 15),)
        with self.assertLogs(self.logger, level='INFO') as logs:
            mission._log_tag_ranges(pose, (detection,), 101)
        self.assertIn('result=accepted', logs.output[0])
        self.assertIn('camera_distance_mm=3000', logs.output[0])
        pose['rejected_tags'] = ((('tag16h5', 15), 'hamming=1'),)
        with self.assertLogs(self.logger, level='INFO') as logs:
            mission._log_tag_ranges(pose, (detection,), 102)
        self.assertIn('result=accepted', logs.output[0])
        pose['accepted_tag_ids'] = ()
        with self.assertLogs(self.logger, level='INFO') as logs:
            mission._log_tag_ranges(pose, (detection,), 103)
        self.assertIn('result=rejected: hamming=1', logs.output[0])

    def test_dock_departure_tolerates_transient_cliff_reading(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._discovery_waypoint = (1060.0, 760.0)
        self.mission._discovery_retreat_start_travelled = 0.0
        sensors = self.discovery_sensors()
        sensors.cliff_front_right_sensor = True
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 35.0,
        }
        pose = {"localized": True, "x_mm": 1050.0, "y_mm": 300.0}

        with patch("roomberry_mission.monotonic", return_value=100.0):
            with self.assertLogs(self.logger, level="WARNING") as captured:
                self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.assertTrue(any("dock departure" in line for line in captured.output))
        self.robot.execute.assert_any_call("stop", timeout=2)

        # The dock ramp reading clears on the next poll; retreat resumes.
        sensors.cliff_front_right_sensor = False
        state["travelled_distance"] = 40.0
        self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_DISCOVERY)
        self.robot.execute.assert_any_call("drive_straight", velocity=-50)

    def test_dock_departure_aborts_if_hazard_persists(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mission._discovery_stage = "retreat"
        self.mission._discovery_waypoint = (1060.0, 760.0)
        self.mission._discovery_retreat_start_travelled = 0.0
        sensors = self.discovery_sensors()
        sensors.cliff_front_right_sensor = True
        state = {
            "sensors": sensors, "age": 0.0, "travelled_distance": 35.0,
        }
        pose = {"localized": True, "x_mm": 1050.0, "y_mm": 300.0}

        with patch("roomberry_mission.monotonic", return_value=100.0):
            self.mission._discovery_tick(state, pose, False, None)
        self.assertEqual(self.mission._mode, MODE_DISCOVERY)

        with patch(
            "roomberry_mission.monotonic",
            return_value=100.0 + DISCOVERY_DOCK_HAZARD_GRACE_SECONDS + 0.1,
        ):
            with self.assertLogs(self.logger, level="WARNING") as captured:
                self.mission._discovery_tick(state, pose, False, None)

        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.assertTrue(any("aborted by hard safety" in line for line in captured.output))
        self.robot.set_operation_indicators.assert_called_with(False)

    def test_hard_safety_abort_logs_stage_and_triggering_sensor(self):
        self.mission.set_mode(MODE_DISCOVERY)
        sensors = SimpleNamespace(
            bumps_and_wheel_drops=SimpleNamespace(
                wheel_drop_left=False, wheel_drop_right=False,
                bump_left=False, bump_right=False,
            ),
            cliff_left_sensor=False, cliff_front_left_sensor=True,
            cliff_front_right_sensor=False, cliff_right_sensor=False,
        )
        state = {"sensors": sensors, "age": 0.0}

        with self.assertLogs(self.logger, level="WARNING") as captured:
            self.mission._discovery_tick(state, None, False, None)

        self.assertIn("stage=initial_scan", captured.output[0])
        self.assertIn("cliff_front_left_sensor", captured.output[0])
        self.assertIn("bump_left=False", captured.output[0])
        self.assertEqual(self.mission._mode, MODE_IDLE)
        self.robot.set_operation_indicators.assert_called_with(False)
        self.mapper.flush.assert_called_once_with()

    def test_close_forces_map_flush(self):
        self.mission.close()

        self.mapper.flush.assert_called_once_with()

    def test_leaving_active_mode_flushes_map(self):
        self.mission.set_mode(MODE_DISCOVERY)
        self.mapper.flush.assert_not_called()

        self.mission.set_mode(MODE_IDLE)

        self.mapper.flush.assert_called_once_with()

    def test_leaving_clean_mode_flushes_map(self):
        self.mission.set_mode(MODE_CLEAN)
        self.mapper.flush.assert_not_called()

        self.mission.set_mode(MODE_IDLE)

        self.mapper.flush.assert_called_once_with()

    def test_map_flush_failure_is_logged_without_escaping(self):
        self.mapper.flush.side_effect = OSError("disk full")

        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.mission.set_mode(MODE_DISCOVERY)
            self.mission.set_mode(MODE_IDLE)

        self.assertIn("leaving active mode", captured.output[0])


if __name__ == "__main__":
    unittest.main()

