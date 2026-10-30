# @(#)roomberry_camera_test.py 2.3.18 2026/10/28 21:40:00
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import logging
import unittest

from PIL import Image

from roomberry_camera import CameraService


class FakeCamera:
    camera_controls = {}

    def __init__(self):
        self.controls = []

    def set_controls(self, controls):
        self.controls.append(controls)


class CameraServiceTest(unittest.TestCase):
    def setUp(self):
        self.camera = FakeCamera()
        self.service = CameraService(logging.getLogger('CameraServiceTest'), camera=self.camera)

    def test_annotation_settings_are_local_and_rendered(self):
        self.service.set_controls({
            'annotate_background': '#123456',
            'annotate_foreground': 'ffffff',
            'annotate_text_size': 12,
        })
        self.assertEqual(self.camera.controls, [])
        self.assertEqual(self.service.get_control('annotate_background'), '#123456')
        self.assertEqual(self.service.get_control('annotate_foreground'), '#ffffff')

        self.service.annotate_text = 'T'
        image = Image.new('RGB', (120, 40), 'black')
        self.service._annotate_image(image, 0)
        self.assertEqual(image.getpixel((0, 0)), (18, 52, 86))
        self.assertTrue(any(
            image.getpixel((x, y)) == (255, 255, 255)
            for x in range(image.width)
            for y in range(image.height)
        ))

    def test_camera_controls_are_forwarded(self):
        self.service.set_controls({'Brightness': 0.2})
        self.assertEqual(self.camera.controls, [{'Brightness': 0.2}])


class VisionArchiveTest(unittest.TestCase):
    def test_full_resolution_color_archive_and_report_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = Mock()
            pixels = np.zeros((972, 1296, 3), dtype=np.uint8)
            pixels[:, :, 0] = 240
            camera.capture_array.return_value = pixels
            detector = Mock()
            detector.last_timings_ms = {'native_detect': 12.5}
            detector.detect.return_value = [{'id': 15, 'distance_mm': 500.0}]
            complete = Mock()
            service = CameraService(Mock(), camera=camera, detector=detector,
                                    snapshot_root=directory, pause_for_detection=True,
                                    scan_pause=lambda: True, scan_complete=complete,
                                    scan_settle_seconds=0)
            service._capture_scan(True)
            report, = service.recent_scans(tags_only=True)
            self.assertEqual(report['tags'][0]['distance_mm'], 500.0)
            self.assertEqual(report['image_size'], [1296, 972])
            self.assertFalse(report['detection_skipped'])
            for name in ('pause', 'settle', 'camera_lock', 'capture', 'detect', 'image_save'):
                self.assertGreaterEqual(report['timings_ms'][name], 0)
            image_file = service.scan_archive_file(report['image_url'].removeprefix('/cam/scans/'))
            with Image.open(image_file) as image:
                self.assertEqual(image.size, (1296, 972))
                red, green, blue = image.getpixel((0, 0))
                self.assertGreater(red, 230)
                self.assertLess(blue, 10)
            report_file = service.scan_archive_file(report['report_url'].removeprefix('/cam/scans/'))
            self.assertEqual(json.loads(report_file.read_text())['tags'][0]['id'], 15)
            self.assertIsNotNone(service.last_detection_ready_time)
            complete.assert_called_once_with()
            self.assertIsNone(service.scan_archive_file('../autonomy.json'))
            self.assertIsNone(service.scan_archive_file('20261027/../../autonomy.json'))

    def test_moving_frame_is_saved_without_detection_or_mission_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = Mock()
            camera.capture_array.return_value = np.zeros((24, 32, 3), dtype=np.uint8)
            detector, complete = Mock(), Mock()
            service = CameraService(Mock(), camera=camera, detector=detector,
                                    snapshot_root=directory, pause_for_detection=True,
                                    scan_pause=lambda: False, scan_complete=complete)
            service._capture_scan()
            report, = service.recent_scans()
            self.assertTrue(report['detection_skipped'])
            self.assertFalse(report['paused'])
            self.assertEqual(service.recent_scans(tags_only=True), [])
            self.assertIsNone(service.last_detection_time)
            detector.detect.assert_not_called()
            complete.assert_not_called()
            self.assertEqual(len(list(Path(directory).glob('*/*.jpg'))), 1)

    def test_detection_failure_saves_image_and_releases_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = Mock()
            camera.capture_array.return_value = np.zeros((24, 32, 3), dtype=np.uint8)
            detector, complete = Mock(), Mock()
            detector.detect.side_effect = RuntimeError('bad detector')
            service = CameraService(Mock(), camera=camera, detector=detector,
                                    snapshot_root=directory, pause_for_detection=True,
                                    scan_pause=lambda: True, scan_complete=complete,
                                    scan_settle_seconds=0)
            service._capture_scan()
            report, = service.recent_scans()
            self.assertEqual(report['detector_error'], 'bad detector')
            self.assertIsNone(service.last_detection_time)
            complete.assert_called_once_with()

    def test_explicit_scan_request_wakes_after_first_capture(self):
        service = CameraService(Mock(), snapshot_interval=20)
        service._scan_requested = Mock()
        service._scan_requested.wait.side_effect = [True, True]
        requests = []
        def capture(requested):
            requests.append(requested)
            if len(requests) == 1:
                service.request_scan()
            else:
                service._shutdown.set()
        service._capture_scan = capture
        service._periodic_capture()
        self.assertEqual(requests, [True, True])
        self.assertEqual(service._scan_requested.wait.call_args_list,
                         [unittest.mock.call(20), unittest.mock.call(20)])
        self.assertEqual(service._scan_requested.clear.call_count, 2)

    def test_configured_capture_resolution_scales_intrinsics_without_compounding(self):
        camera = Mock()
        detector = Mock()
        detector.camera_intrinsics = (1000, 1000, 648, 486)
        service = CameraService(Mock(), camera=camera, detector=detector,
                                capture_resolution=(1640, 1232))
        service.set_highest_resolution(False)
        from unittest.mock import patch
        with patch('roomberry_camera.Thread'):
            service.start()
            service.start()
        camera.create_still_configuration.assert_called_with(
            main={'size': (1640, 1232), 'format': 'BGR888'}, queue=False)
        np.testing.assert_allclose(detector.camera_intrinsics,
                                   (1000 * 1640 / 1296, 1000 * 1232 / 972, 820, 616))

    def test_camera_start_uses_sensor_resolution_rgb_and_no_queued_frame(self):
        camera = Mock()
        camera.sensor_resolution = (2592, 1944)
        camera.create_still_configuration.side_effect = lambda **kwargs: kwargs
        detector = Mock()
        detector.camera_intrinsics = (1000, 1000, 648, 486)
        service = CameraService(Mock(), camera=camera, detector=detector)
        service._shutdown.set()
        from unittest.mock import patch
        with patch('roomberry_camera.Thread'):
            service.start()
            service.start()
        camera.create_still_configuration.assert_called_with(
            main={'size': (2592, 1944), 'format': 'BGR888'}, queue=False)
        self.assertEqual(detector.camera_intrinsics, (2000, 2000, 1296, 972))


if __name__ == '__main__':
    unittest.main()
