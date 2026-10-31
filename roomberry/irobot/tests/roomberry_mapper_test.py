# @(#)roomberry_mapper_test.py 2.3.recovery.1 2026/10/30 17:25:00
import json
import os
import unittest
from math import atan2,hypot
from tempfile import TemporaryDirectory

from roomberry_mapper import BLOCKED, RoomberryMapper


class RoomberryMapperPersistenceTest(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self.state_path = os.path.join(self._temp.name, "map-state.json")
        self.mapper = RoomberryMapper(
            20, 20, 174, cell_size_mm=87, persist_interval_s=3600,
        )
        self.mapper.state_path = self.state_path

    def tearDown(self):
        self._temp.cleanup()

    def _saved(self):
        with open(self.state_path) as state_file:
            return json.load(state_file)

    def test_local_reset_restores_route_and_keeps_distant_obstacles(self):
        mapper = self.mapper
        mapper.update_pose(600, 600, 0)
        mapper.mark_obstacle(800, 600)
        mapper.mark_obstacle(1400, 1400)
        self.assertFalse(mapper.motion_is_clear(
            dict(x_mm=600, y_mm=600, heading_rad=0), 50, 0, 1))
        self.assertEqual(mapper.clear_nearby_obstacles(600, 600, 500), 1)
        self.assertTrue(mapper.motion_is_clear(
            dict(x_mm=600, y_mm=600, heading_rad=0), 50, 0, 1))
        self.assertEqual(mapper.cell_state(*mapper.world_to_cell(1400, 1400))['occupancy'], BLOCKED)
        mapper.flush()
        self.assertEqual(self._saved_blocked(), 1)
        self.assertEqual(mapper.clear_nearby_obstacles(600, 600, 500), 0)

    def _saved_blocked(self):
        return sum(
            cell == BLOCKED
            for row in self._saved()["occupancy"]
            for cell in row
        )

    def test_persist_is_throttled_and_flush_forces_a_save(self):
        self.assertTrue(self.mapper.mark_obstacle(87, 87))
        self.assertEqual(self._saved_blocked(), 1)

        self.assertTrue(self.mapper.mark_obstacle(87 * 6, 87 * 6))
        self.assertEqual(self._saved_blocked(), 1)

        self.assertTrue(self.mapper.flush())
        self.assertEqual(self._saved_blocked(), 2)

    def test_zero_interval_saves_each_change(self):
        self.mapper.persist_interval_s = 0.0

        self.mapper.mark_obstacle(87, 87)
        self.assertEqual(self._saved_blocked(), 1)
        self.mapper.mark_obstacle(87 * 6, 87 * 6)
        self.assertEqual(self._saved_blocked(), 2)

    def test_pose_trail_is_throttled_until_flush(self):
        self.mapper.update_pose(100, 100, 0.0)
        self.assertEqual(len(self._saved()["trail"]), 1)

        self.mapper.update_pose(200, 100, 0.0)
        self.assertEqual(len(self._saved()["trail"]), 1)

        self.mapper.flush()
        self.assertEqual(len(self._saved()["trail"]), 2)

    def test_loading_keeps_history_separate_from_new_session(self):
        self.mapper.update_pose(200, 200, 0)
        self.mapper.update_pose(300, 200, 0)
        self.mapper.flush()
        self.assertEqual(self._saved()['trail_session_start'], 0)
        loaded = RoomberryMapper(20, 20, 174, cell_size_mm=87, persist_interval_s=3600)
        loaded.load_state(self.state_path)
        self.assertEqual(loaded.snapshot()['trail_session_start'], 2)
        # The first pose of this run is retained even at the previous endpoint.
        loaded.update_pose(300, 200, 0)
        loaded.flush()
        self.assertEqual(loaded.snapshot()['trail_session_start'], 2)
        self.assertEqual(len(loaded.snapshot()['trail']), 3)
        self.assertEqual(self._saved()['trail_session_start'], 2)

    def test_whole_current_session_survives_old_two_thousand_point_limit(self):
        mapper = RoomberryMapper(20, 20, 50, cell_size_mm=50)
        for i in range(2100):
            mapper.update_pose(100+(i%2)*50, 100, 0)
        snapshot = mapper.snapshot()
        self.assertEqual(snapshot['trail_session_start'], 0)
        self.assertEqual(len(snapshot['trail']), 2100)
        self.assertEqual(snapshot['trail'][0], (100.0, 100.0))


class RoomberryMapperMotionTest(unittest.TestCase):
    def setUp(self):
        self.mapper = RoomberryMapper(40, 40, 70, cell_size_mm=50)
        self.pose = dict(x_mm=1000, y_mm=1000, heading_rad=0)

    def test_clear_forward_and_curved_motion(self):
        self.assertTrue(self.mapper.motion_is_clear(self.pose, 200, 0, 1))
        self.assertTrue(self.mapper.motion_is_clear(self.pose, 200, 1.2, 1))

    def test_curve_checks_footprint_away_from_straight_centerline(self):
        self.mapper.mark_obstacle(1200, 1150)
        self.assertTrue(self.mapper.motion_is_clear(self.pose, 200, 0, 1))
        self.assertFalse(self.mapper.motion_is_clear(self.pose, 200, 1.2, 1))

    def test_checks_entire_path_not_only_endpoint(self):
        self.mapper.mark_obstacle(1150, 1000)
        self.assertFalse(self.mapper.motion_is_clear(self.pose, 400, 0, 1))

    def test_rejects_room_edge_footprint_and_invalid_values(self):
        self.assertFalse(self.mapper.motion_is_clear(dict(self.pose, x_mm=1850), 200, 0, 1))
        self.assertFalse(self.mapper.motion_is_clear(self.pose, 200, float('nan'), 1))
        self.assertFalse(self.mapper.motion_is_clear(self.pose, 200, 0, 0))

    def test_recorded_stop_can_move_away_from_only_extra_padding(self):
        mapper = RoomberryMapper(103, 92, 174, cell_size_mm=87)
        mapper.mark_obstacle(27.5*87, 6.5*87)
        pose = dict(x_mm=2491.738, y_mm=803.436, heading_rad=0.869638)
        self.assertTrue(mapper.motion_is_clear(pose, 55, -0.008, 1))
        self.assertFalse(mapper.motion_is_clear(dict(pose, heading_rad=0.869638+3.141593), 55, 0, 1))

    def test_padding_escape_still_rejects_actual_footprint_overlap(self):
        self.mapper.mark_obstacle(1200, 1000)
        pose = dict(self.pose, x_mm=1150, heading_rad=3.141593)
        self.assertFalse(self.mapper.motion_is_clear(pose, 100, 0, 1))

    def test_route_excludes_recorded_impossible_boundary_waypoint(self):
        mapper = RoomberryMapper(103, 92, 174, cell_size_mm=87)
        mapper.mark_obstacle(1497,46)
        mapper.update_pose(1300,313,0)
        plan = mapper.plan_to(2600,950)
        self.assertIsNotNone(plan)
        for cell in plan['path']:
            x,y=mapper.cell_center(cell)
            self.assertGreaterEqual(min(x,y,103*87-x,92*87-y),204.875)
        self.assertIsNone(mapper.plan_to(1783.5,130.5))

    def test_recorded_boundary_padding_allows_escape_not_outward_motion(self):
        mapper = RoomberryMapper(103, 92, 174, cell_size_mm=87)
        pose = dict(x_mm=1750.823,y_mm=202.858,heading_rad=1.570796)
        self.assertTrue(mapper.motion_is_clear(pose,40,0,1))
        self.assertFalse(mapper.motion_is_clear(dict(pose,heading_rad=-1.570796),40,0,1))
        self.assertFalse(mapper.motion_is_clear(dict(pose,y_mm=170),40,0,1))

    def test_route_segments_and_motion_guard_agree_on_obstacle_footprint(self):
        mapper=RoomberryMapper(40,30,174,cell_size_mm=87)
        mapper.mark_obstacle(1000,600)
        mapper.update_pose(750,600,0)
        plan=mapper.plan_to(1800,600)
        self.assertIsNotNone(plan)
        for a,b in zip(plan['path'],plan['path'][1:]):
            x,y=mapper.cell_center(a);xx,yy=mapper.cell_center(b)
            pose=dict(x_mm=x,y_mm=y,heading_rad=atan2(yy-y,xx-x))
            self.assertTrue(mapper.motion_is_clear(pose,hypot(xx-x,yy-y),0,1),(a,b))


if __name__ == '__main__':
    unittest.main()
