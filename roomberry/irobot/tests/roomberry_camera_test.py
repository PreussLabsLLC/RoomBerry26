# @(#)roomberry_camera_test.py 3.2.trails.1 2026/11/10 13:54:11
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
            min(image.getpixel((x, y))) >= 240  # Antialiased fallback fonts can peak at 254.
            for x in range(image.width)
            for y in range(image.height)
        ))

    def test_camera_controls_are_forwarded(self):
        self.service.set_controls({'Brightness': 0.2})
        self.assertEqual(self.camera.controls, [{'Brightness': 0.2}])


class VisionArchiveTest(unittest.TestCase):
    def test_cooloffs_keep_pause_and_free_locks_until_result_publication(self):
        trace = []
        held = [False]
        camera, detector = Mock(), Mock()
        pixels = np.zeros((8, 8, 3), dtype=np.uint8)
        camera.capture_array.side_effect = lambda: (trace.append('capture') or pixels)
        detector.detect.side_effect = lambda image: (trace.append('detect') or [{'id':16}])
        detector.last_timings_ms = {}
        def pause():
            held[0] = True; trace.append('pause'); return True
        def complete():
            self.assertTrue(held[0]); held[0] = False; trace.append('complete')
        service = CameraService(Mock(), camera=camera, detector=detector, snapshot_root='mocked',
                                pause_for_detection=True, scan_pause=pause, scan_complete=complete)
        service._save_periodic_snapshot = lambda *args: trace.append('archive')
        def wait(seconds):
            self.assertTrue(held[0])
            self.assertIsNone(service.last_detection_ready_time)
            for lock in (service._lock, service._detection_lock):
                self.assertTrue(lock.acquire(blocking=False)); lock.release()
            trace.append(('wait', seconds)); return False
        service._shutdown.wait = wait
        def announce(report):
            self.assertTrue(held[0])
            self.assertIsNotNone(service.last_detection_ready_time)
            for name in ('cooloff_after_capture', 'cooloff_after_detect', 'cooloff_after_archive'):
                self.assertIn(name, report['timings_ms'])
            trace.append('announce')
        service.scan_result = announce
        service._capture_scan(True)
        self.assertEqual(trace, ['pause', ('wait',1.0), 'capture', ('wait',0.5), 'detect',
                                 ('wait',0.5), 'archive', ('wait',0.5), 'announce', 'complete'])
        self.assertFalse(held[0])

    def test_shutdown_interrupts_each_cooloff_without_publishing_or_speaking(self):
        for cancel_at in (2, 3, 4):  # Settle is wait1; the three cool-offs follow.
            with self.subTest(cancel_at=cancel_at):
                camera, detector, complete, announce = Mock(), Mock(), Mock(), Mock()
                camera.capture_array.return_value = np.zeros((8,8,3), dtype=np.uint8)
                detector.detect.return_value = [{'id':16}]; detector.last_timings_ms = {}
                service = CameraService(Mock(), camera=camera, detector=detector, snapshot_root='mocked',
                                        pause_for_detection=True, scan_pause=lambda:True,
                                        scan_complete=complete, scan_result=announce)
                service._save_periodic_snapshot = Mock()
                count = [0]
                def wait(seconds):
                    count[0] += 1; return count[0] == cancel_at
                service._shutdown.wait = wait
                service._capture_scan(True)
                self.assertIsNone(service.last_detection_ready_time)
                announce.assert_not_called()
                complete.assert_called_once_with()

    def test_speech_callback_failure_does_not_lose_detection_or_pause_cleanup(self):
        camera, detector, complete = Mock(), Mock(), Mock()
        camera.capture_array.return_value = np.zeros((8,8,3), dtype=np.uint8)
        detector.detect.return_value = [{'id':16}]; detector.last_timings_ms = {}
        service = CameraService(Mock(), camera=camera, detector=detector,
                                pause_for_detection=True, scan_pause=lambda:True,
                                scan_complete=complete, scan_settle_seconds=0, scan_cooloff_seconds=0,
                                scan_result=Mock(side_effect=RuntimeError('speech unavailable')))
        service._capture_scan(True)
        self.assertEqual(service.latest_detections[0]['id'], 16)
        complete.assert_called_once_with()

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
                                    scan_settle_seconds=0, scan_cooloff_seconds=0)
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
                                    scan_settle_seconds=0, scan_cooloff_seconds=0)
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
                         [unittest.mock.call(), unittest.mock.call()])
        self.assertEqual(service._scan_requested.clear.call_count, 2)

    def test_no_scan_without_explicit_request(self):
        service = CameraService(Mock(), snapshot_interval=0)
        service._scan_requested = Mock()
        service._capture_scan = Mock()
        wakes = iter((False, True))
        def wait():
            requested = next(wakes)
            if requested:
                service._shutdown.set()
            return requested
        service._scan_requested.wait.side_effect = wait
        service._periodic_capture()
        service._capture_scan.assert_not_called()
        self.assertEqual(service._scan_requested.wait.call_count, 2)
        service._scan_requested.wait.assert_called_with()

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
