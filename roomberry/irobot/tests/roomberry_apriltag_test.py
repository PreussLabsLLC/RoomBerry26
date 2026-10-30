# @(#)roomberry_apriltag_test.py 2.3.3 2026/10/27 18:40:00
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import numpy as np

from roomberry_camera import AprilTagDetector


class DetectorWithoutPoseMethod:
    def detect(self, gray):
        return [{
            "id": 2,
            "center": (320.0, 240.0),
            "lb-rb-rt-lt": (
                (820.0, 740.0), (-180.0, 740.0),
                (-180.0, -260.0), (820.0, -260.0),
            ),
            "homography": ((500.0, 0.0, 320.0),
                           (0.0, -500.0, 240.0),
                           (0.0, 0.0, -1.0)),
        }]


class AprilTagPoseFallbackTest(unittest.TestCase):
    def test_native_binding_disables_internal_decimation(self):
        constructor = Mock()
        with patch.dict('sys.modules', {'apriltag': SimpleNamespace(apriltag=constructor)}):
            AprilTagDetector()._load_detector()
        constructor.assert_called_once_with('tag16h5', decimate=1.0)

    def test_full_resolution_grayscale_and_distance_telemetry(self):
        native = Mock()
        native.detect.return_value = [{
            'id': 15, 'center': (500, 400),
            'corners': ((0, 0), (10, 0), (10, 10), (0, 10)), 'margin': 30.0,
        }]
        native.estimate_tag_pose.return_value = {'R': np.eye(3), 't': (0.3, 0, 0.4), 'error': 0.1}
        detector = AprilTagDetector(detector=native, tag_size_m=0.0575,
                                    camera_intrinsics=(1000, 1000, 648, 486), logger=Mock())
        pixels = np.zeros((972, 1296, 3), dtype=np.uint8)
        pixels[:, :, 0] = 255
        result, = detector.detect(pixels)
        gray = native.detect.call_args.args[0]
        self.assertEqual(gray.shape, (972, 1296))
        self.assertEqual(gray.dtype, np.uint8)
        self.assertTrue(gray.flags.c_contiguous)
        self.assertEqual(int(gray[0, 0]), 76)
        self.assertAlmostEqual(result['distance_mm'], 500.0)
        self.assertAlmostEqual(result['depth_mm'], 400.0)
        self.assertEqual(result['center_px'], (500.0, 400.0))
        for name in ('grayscale', 'resize', 'array', 'detector_load', 'native_detect', 'pose', 'observations', 'total'):
            self.assertGreaterEqual(detector.last_timings_ms[name], 0)

    def test_binding_without_pose_method_uses_homography(self):
        detector = AprilTagDetector(
            detector=DetectorWithoutPoseMethod(), tag_size_m=0.1,
            camera_intrinsics=(500.0, 500.0, 320.0, 240.0),
        )

        detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))

        self.assertEqual(len(detections), 1)
        pose = detections[0]["tag_pose_camera"]
        self.assertEqual(len(pose["rotation"]), 3)
        self.assertEqual(len(pose["translation_m"]), 3)
        self.assertGreater(pose["translation_m"][2], 0.0)
        self.assertTrue(np.isfinite(pose["error"]))

    def test_missing_pose_method_homography_and_corners_reports_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "no pose method, homography, or corners"):
            AprilTagDetector._estimate_pose_from_homography(
                {}, 0.1, 500.0, 500.0, 320.0, 240.0,
            )


if __name__ == "__main__":
    unittest.main()
