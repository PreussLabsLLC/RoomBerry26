# @(#)roomberry_apriltag_test.py 3.2.rollup.1 2026/11/13 19:43:59
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


class GILHoldingDetector:
    def detect(self, gray):
        # Reproduce a native binding that holds the GIL throughout detection.
        import ctypes
        ctypes.PyDLL(None).usleep(800000)
        return []


class FixedMetricDetector:
    """Picklable native-binding stand-in for the real isolated worker."""
    def detect(self, gray):
        return [dict(id=15, center=(10, 10), corners=((0,0),(20,0),(20,20),(0,20)), margin=40)]

    def estimate_tag_pose(self, detection, size, fx, fy, cx, cy):
        return dict(R=np.eye(3), t=(.3, 0, .4), error=.1)


class AprilTagProcessTest(unittest.TestCase):
    def test_native_gil_hold_does_not_starve_sensor_polling(self):
        import logging
        from roomberry_control import RobotCommandArbiter
        from roomberry_control_test import FakeRobot
        from time import monotonic
        class PollingRobot(FakeRobot):
            def __init__(self):
                super().__init__()
                self.poll_times = []

            @property
            def sensor_group100(self):
                self.poll_times.append(monotonic())
                return super().sensor_group100

        robot = PollingRobot()
        control = RobotCommandArbiter(None, 0, logging.getLogger('isolated-detector'),
                                      robot=robot, poll_interval=.02)
        self.addCleanup(control.close)
        control.start()
        detector = AprilTagDetector(detector=GILHoldingDetector(), isolate_process=True)
        self.addCleanup(detector.close)
        before = robot.sensor_reads
        self.assertEqual(detector.detect(np.zeros((24,32,3), dtype=np.uint8)), [])
        self.assertGreater(robot.sensor_reads-before, 10)
        self.assertLess(control.snapshot()['age'], .5)
        self.assertLess(max(b-a for a,b in zip(robot.poll_times, robot.poll_times[1:])), .5)
        self.assertGreaterEqual(detector.last_timings_ms['native_detect'], 750)

    def test_process_preserves_pose_geometry_and_reuses_worker(self):
        detector = AprilTagDetector(detector=DetectorWithoutPoseMethod(), isolate_process=True,
                                    tag_size_m=.1, camera_intrinsics=(500,500,320,240))
        self.addCleanup(detector.close)
        pixels = np.zeros((480,640,3), dtype=np.uint8)
        result = detector.detect(pixels)
        pid = detector._process.pid
        expected = AprilTagDetector(detector=DetectorWithoutPoseMethod(), tag_size_m=.1,
                                    camera_intrinsics=(500,500,320,240)).detect(pixels)
        again = detector.detect(pixels)
        for detections in (result, expected, again):
            for row in detections:
                row.pop('pose_ms', None)
        self.assertEqual(result, expected)
        self.assertEqual(again, expected)
        self.assertEqual(detector._process.pid, pid)

    def test_timeout_terminates_worker_and_leaves_it_restartable(self):
        detector = AprilTagDetector(detector=GILHoldingDetector(), isolate_process=True)
        self.addCleanup(detector.close)
        with patch('roomberry_camera.DETECTOR_TIMEOUT_SECONDS', .1):
            with self.assertRaises(TimeoutError):
                detector.detect(np.zeros((24,32,3), dtype=np.uint8))
        self.assertIsNone(detector._process)
        self.assertIsNone(detector._connection)


class AprilTagPoseFallbackTest(unittest.TestCase):
    def test_native_binding_disables_internal_decimation(self):
        constructor = Mock()
        with patch.dict('sys.modules', {'apriltag': SimpleNamespace(apriltag=constructor)}):
            AprilTagDetector()._load_detector()
        constructor.assert_called_once_with('tag16h5', decimate=1.0)

    def test_tag15_ten_percent_translation_preserves_raw_and_other_tags(self):
        native = FixedMetricDetector()
        native.detect = lambda image: [dict(id=i, family=family, center=(10,10),
            corners=((0,0),(20,0),(20,20),(0,20)), margin=40)
            for family,i in [('tag16h5',15),('tag16h5',16),('tag25h9',15)]]
        detector = AprilTagDetector(detector=native, tag_size_m=.0575,
            camera_intrinsics=(100,100,10,10), pose_translation_scales={'tag16h5:15':1.10})
        for _ in range(2):
            corrected, other, other_family = detector.detect(np.zeros((30,30,3),dtype=np.uint8))
            self.assertAlmostEqual(corrected['distance_mm'],550)
            self.assertAlmostEqual(corrected['depth_mm'],440)
            self.assertEqual(corrected['raw_tag_pose_camera']['translation_m'],(.3,0,.4))
            self.assertEqual(corrected['raw_distance_mm'],500)
            self.assertEqual(corrected['raw_depth_mm'],400)
            self.assertEqual(corrected['pose_translation_scale'],1.10)
            np.testing.assert_allclose(corrected['tag_pose_camera']['translation_m'],(.33,0,.44))
            self.assertEqual(corrected['tag_pose_camera']['rotation'],corrected['raw_tag_pose_camera']['rotation'])
            self.assertEqual(corrected['tag_pose_camera']['error'],.1)
            for row in (other,other_family):
                self.assertEqual(row['distance_mm'],500)
                self.assertNotIn('pose_translation_scale',row)

    def test_global_twelve_percent_scales_every_tag_without_pilot_compounding(self):
        native=FixedMetricDetector()
        native.detect=lambda image:[dict(id=i,family=family,center=(10,10),
            corners=((0,0),(20,0),(20,20),(0,20)),margin=40)
            for family,i in [('tag16h5',15),('tag16h5',16),('tag25h9',1)]]
        detector=AprilTagDetector(detector=native,tag_size_m=.0575,
            camera_intrinsics=(100,100,10,10),pose_translation_scale=1.12)
        for _ in range(2):
            for row in detector.detect(np.zeros((30,30,3),dtype=np.uint8)):
                self.assertAlmostEqual(row['distance_mm'],560)
                self.assertAlmostEqual(row['depth_mm'],448)
                self.assertEqual(row['raw_distance_mm'],500)
                self.assertEqual(row['pose_translation_scale'],1.12)

    def test_global_factor_reaches_isolated_worker(self):
        detector=AprilTagDetector(detector=FixedMetricDetector(),tag_size_m=.0575,
            camera_intrinsics=(100,100,10,10),pose_translation_scale=1.12,isolate_process=True)
        self.addCleanup(detector.close)
        for _ in range(2):
            row,=detector.detect(np.zeros((30,30,3),dtype=np.uint8))
            self.assertAlmostEqual(row['distance_mm'],560)
            self.assertEqual(row['raw_distance_mm'],500)

    def test_global_factor_configuration_is_validated(self):
        for value in (True,0,float('nan'),float('inf'),3,'1.12'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                AprilTagDetector(pose_translation_scale=value)

    def test_translation_scale_rejects_invalid_configuration(self):
        for scales in ([], {'tag16h5:15':True}, {'tag16h5:15':float('nan')},
                       {'tag16h5:15':float('inf')}, {'tag16h5:15':0},
                       {'tag16h5:15':3}, {'15':1.1}):
            with self.subTest(scales=scales), self.assertRaises(ValueError):
                AprilTagDetector(pose_translation_scales=scales)

    def test_isolated_worker_applies_translation_scale_once(self):
        detector = AprilTagDetector(detector=FixedMetricDetector(), tag_size_m=.0575,
            camera_intrinsics=(100,100,10,10), isolate_process=True,
            pose_translation_scales={'tag16h5:15':1.10})
        self.addCleanup(detector.close)
        for _ in range(2):
            row, = detector.detect(np.zeros((30,30,3),dtype=np.uint8))
            self.assertAlmostEqual(row['distance_mm'],550)
            self.assertEqual(row['raw_distance_mm'],500)

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
