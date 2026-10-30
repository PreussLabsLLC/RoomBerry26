# @(#)roomberry_localization_test.py 2.3.16 2026/10/28 21:00:00
import unittest
from unittest.mock import patch

from roomberry_localization import AprilTagLocalizer


IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def landmark(x_m, y_m):
    transform = [list(row) for row in IDENTITY]
    transform[0][3] = x_m
    transform[1][3] = y_m
    return transform


def detection(tag_id, x_m, y_m, z_m, error=0.1, margin=50.0, hamming=0):
    return {
        'family': 'tag16h5',
        'id': tag_id,
        'hamming': hamming,
        'decision_margin': margin,
        'tag_pose_camera': {
            'rotation': IDENTITY[:3],
            'translation_m': (x_m, y_m, z_m),
            'error': error,
        },
    }


class AprilTagLocalizerTest(unittest.TestCase):
    def localizer(self):
        return AprilTagLocalizer(
            {
                ('tag16h5', 1): landmark(1.0, 0.0),
                ('tag16h5', 2): landmark(0.0, 1.0),
                ('tag16h5', 3): landmark(5.0, 5.0),
            },
            IDENTITY,
        )

    def test_room_bounds_and_tag_mounting_side_reject_impossible_fixes(self):
        import json
        from pathlib import Path
        config = json.loads((Path(__file__).resolve().parents[2] / 'autonomy.json').read_text())
        tags = {(x['family'], x['id']): x['world_from_tag'] for x in config['landmarks']}
        localizer = AprilTagLocalizer(tags, config['camera_from_robot'],
                                      room_bounds_mm=(-1000,0,9000,8000))
        def observation(x, y):
            robot = landmark(x,y)
            camera_tag = localizer._multiply(config['camera_from_robot'],
                         localizer._multiply(localizer._inverse(robot), tags[('tag16h5',2)]))
            item = detection(2, camera_tag[0][3], camera_tag[1][3], camera_tag[2][3])
            item['tag_pose_camera']['rotation'] = [row[:3] for row in camera_tag[:3]]
            return item
        self.assertIsNone(localizer.update([observation(3.1,-.3)],0,0))
        self.assertIn('outside room',localizer.last_rejected[0][1])
        self.assertIsNone(localizer.update([observation(-.5,.5)],0,0))
        self.assertIn('behind tag',localizer.last_rejected[0][1])
        pose = localizer.update([observation(.5,.5)],0,0)
        self.assertEqual(pose['accepted_tag_ids'],(('tag16h5',2),))

    def test_old_pose_needs_repeated_consistent_large_correction(self):
        from math import pi
        localizer = self.localizer()
        localizer.confirm_large_relocations = True
        localizer._pose = dict(x_mm=0,y_mm=0,heading_rad=0)
        localizer._last_tag_time = 0
        localizer._last_odometry = (0,0)
        candidate = dict(x_mm=2000,y_mm=1000,heading_rad=0,
                         key=('tag16h5',2),weight=1,error=.1,range_m=1)
        with patch('roomberry_localization.monotonic',return_value=100):
            estimates,rejected = localizer._consistent_estimates([candidate],[])
            self.assertEqual(estimates,[])
            self.assertIn('another consistent scan',rejected[0][1])
            # A 30-degree view change must also advance the pending hypothesis.
            localizer.update([],0,30,new_detections=False)
            turned = dict(candidate,heading_rad=pi/6)
            estimates,_ = localizer._consistent_estimates([turned],[])
            self.assertEqual(estimates,[turned])
            self.assertIsNone(localizer._pending_relocation)

    def test_rejected_frame_does_not_reuse_previous_acceptance(self):
        localizer = self.localizer()
        accepted = localizer.update([detection(2, 0.1, 0.2, 0.4)],
                                    0.0, 0.0, new_detections=True)
        self.assertEqual(accepted['accepted_tag_ids'], (('tag16h5', 2),))
        rejected = localizer.update([detection(2, 0.1, 0.2, 0.4, error=1137.77)],
                                    0.0, 0.0, new_detections=True)
        self.assertEqual(rejected['accepted_tag_ids'], ())
        self.assertEqual(rejected['tag_ids'], (('tag16h5', 2),))

    def test_invalidation_requires_a_new_tag_after_carry(self):
        localizer=self.localizer()
        self.assertIsNotNone(localizer.update([detection(2,.1,.2,.4)],0,0,new_detections=True))
        localizer.invalidate_pose()
        self.assertIsNone(localizer.update([],500,45,new_detections=False))
        self.assertIsNotNone(localizer.update([detection(2,.1,.2,.4)],500,45,new_detections=True))

    def test_rejects_large_reprojection_error(self):
        localizer = self.localizer()

        pose = localizer.update(
            [detection(2, 0.1, 0.2, 0.4, error=1137.77)],
            0.0, 0.0, new_detections=True,
        )

        self.assertIsNone(pose)
        self.assertEqual(localizer.last_rejected[0][0], ('tag16h5', 2))
        self.assertIn('reprojection error', localizer.last_rejected[0][1])

    def test_rejects_implausible_tag_range(self):
        localizer = self.localizer()

        pose = localizer.update(
            [detection(1, 0.0, 0.0, 0.02)],
            0.0, 0.0, new_detections=True,
        )

        self.assertIsNone(pose)
        self.assertIn('range', localizer.last_rejected[0][1])

    def test_rejects_jump_from_odometry_predicted_pose(self):
        localizer = self.localizer()
        first = localizer.update(
            [detection(1, 0.1, 0.2, 0.5)], 0.0, 0.0, new_detections=True,
        )
        self.assertAlmostEqual(first['x_mm'], 900.0)

        second = localizer.update(
            [detection(1, 1.1, 0.2, 0.5)], 0.0, 0.0, new_detections=True,
        )

        self.assertAlmostEqual(second['x_mm'], 900.0)
        self.assertIn('jump', localizer.last_rejected[0][1])

    def test_stale_odometry_allows_jump_correction(self):
        localizer = self.localizer()
        with patch('roomberry_localization.monotonic', return_value=100.0):
            first = localizer.update(
                [detection(1, 0.1, 0.2, 0.5)], 0.0, 0.0,
                new_detections=True,
            )
        self.assertAlmostEqual(first['x_mm'], 900.0)

        stale_time = 100.0 + localizer.max_pose_jump_age + 1.0
        with patch('roomberry_localization.monotonic', return_value=stale_time):
            second = localizer.update(
                [detection(1, 1.1, 0.2, 0.5)], 0.0, 0.0,
                new_detections=True,
            )

        self.assertAlmostEqual(second['x_mm'], -100.0)
        self.assertEqual(localizer.last_rejected, ())

    def test_rejects_outlier_tag_when_other_tags_agree(self):
        localizer = self.localizer()
        # Tags 1 and 2 both put the robot at the origin. Tag 3 has an equally
        # good reported error but proposes a large move; the agreeing pair wins.
        pose = localizer.update(
            [
                detection(1, 1.0, 0.0, 0.5, error=0.1),
                detection(2, 0.0, 1.0, 0.5, error=0.1),
                detection(3, 1.0, 1.0, 0.5, error=0.1),
            ],
            0.0, 0.0, new_detections=True,
        )

        self.assertAlmostEqual(pose['x_mm'], 0.0)
        self.assertAlmostEqual(pose['y_mm'], 0.0)
        self.assertEqual(pose['tag_ids'], (('tag16h5', 1), ('tag16h5', 2)))
        self.assertIn('disagrees', localizer.last_rejected[0][1])

    def test_weak_margin_is_rejected(self):
        localizer = self.localizer()
        pose = localizer.update(
            [detection(1, 1.0, 0.0, 0.5, margin=2.0)],
            0.0, 0.0, new_detections=True,
        )

        self.assertIsNone(pose)
        self.assertIn('weak margin', localizer.last_rejected[0][1])


if __name__ == '__main__':
    unittest.main()
