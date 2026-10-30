# @(#)roomberry_mapper_test.py 2.5 2026/10/25
import json
import os
import unittest
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


if __name__ == '__main__':
    unittest.main()
