# @(#)roomberry_server_test.py 2.3.tag-facing.3 2026/10/30 16:10:00
import unittest
import io
import json
from math import cos, sin
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from irobot.openinterface.constants import MODES
from roomberry import RoomberryHandler, map_tag_markers


class MapTagFacingTest(unittest.TestCase):
    def test_configured_faces_point_into_room_not_robot_viewing_heading(self):
        config = json.loads((Path(__file__).resolve().parents[2]/'autonomy.json').read_text())
        markers = {m[2]: m for m in map_tag_markers(config['landmarks'])}
        for tag_id, vector in {1:(0,1),2:(1,0),15:(-1,0),16:(0,1)}.items():
            with self.subTest(tag_id=tag_id):
                self.assertAlmostEqual(cos(markers[tag_id][3]),vector[0])
                self.assertAlmostEqual(sin(markers[tag_id][3]),vector[1])


class RoomberryManualControlTest(unittest.TestCase):
    def setUp(self):
        self.mission = Mock()
        self.roomba_control = Mock()
        self.roomba_control.snapshot.return_value = {
            'sensors': SimpleNamespace(oi_mode=MODES.SAFE),
        }
        self.server = SimpleNamespace(
            mission=self.mission,
            roomba_control=self.roomba_control,
            logger=Mock(),
        )
        self.handler = RoomberryHandler.__new__(RoomberryHandler)
        self.handler.server = self.server

    def test_drive_command_takes_manual_control_as_motion(self):
        self.handler._take_manual_control('drive', {'velocity': 100})

        self.mission.take_manual_control.assert_called_once_with(moving=True)

    def test_zero_velocity_drive_takes_control_without_motion(self):
        self.handler._take_manual_control(
            'drive_direct', {'right_velocity': 0, 'left_velocity': 0},
        )

        self.mission.take_manual_control.assert_called_once_with(moving=False)

    def test_mode_command_takes_control_without_motion(self):
        self.handler._take_manual_control('_change_mode', {'mode': MODES.SAFE})

        self.mission.take_manual_control.assert_called_once_with(moving=False)

    def test_drive_restores_safe_mode_when_open_interface_is_passive(self):
        self.roomba_control.snapshot.return_value = {
            'sensors': SimpleNamespace(oi_mode=MODES.PASSIVE),
        }

        self.handler._ensure_remote_drive_mode({'velocity': 150})

        self.roomba_control.execute.assert_called_once_with(
            '_change_mode', mode=MODES.SAFE,
        )

    def test_drive_leaves_safe_mode_alone(self):
        self.handler._ensure_remote_drive_mode({'velocity': 150})

        self.roomba_control.execute.assert_not_called()

    def test_zero_drive_does_not_change_mode(self):
        self.roomba_control.snapshot.return_value = {
            'sensors': SimpleNamespace(oi_mode=MODES.PASSIVE),
        }

        self.handler._ensure_remote_drive_mode({'velocity': 0})

        self.roomba_control.snapshot.assert_not_called()
        self.roomba_control.execute.assert_not_called()

    def test_missing_sensor_snapshot_still_attempts_safe_mode(self):
        self.roomba_control.snapshot.return_value = {'sensors': None}

        self.handler._ensure_remote_drive_mode({'velocity': 150})

        self.roomba_control.execute.assert_called_once_with(
            '_change_mode', mode=MODES.SAFE,
        )


class VisionDownloadTest(unittest.TestCase):
    def setUp(self):
        self.camera = Mock()
        self.handler = RoomberryHandler.__new__(RoomberryHandler)
        self.handler.server = SimpleNamespace(camera_service=self.camera)
        self.handler.wfile = io.BytesIO()
        for name in ('send_response', 'send_header', 'end_headers', 'send_error'):
            setattr(self.handler, name, Mock())

    def test_recent_tags_json(self):
        self.camera.recent_scans.return_value = [{'tags': [{'id': 15, 'distance_mm': 500}]}]
        self.handler.path = '/cam/tags.json?limit=5'
        self.assertTrue(self.handler._serve_vision())
        self.camera.recent_scans.assert_called_once_with(5, tags_only=True)
        self.assertEqual(json.loads(self.handler.wfile.getvalue())['scans'][0]['tags'][0]['id'], 15)
        self.handler.send_header.assert_any_call('Content-Type', 'application/json')

    def test_live_status_is_read_only_and_reports_monitor_mode(self):
        self.handler.server.roomba_control=Mock()
        self.handler.server.roomba_control.snapshot.return_value=dict(
            oi_stopped=False,ready=True,reverse_current_monitor=dict(mode='report_only',candidate=True))
        self.handler.path='/status.json'
        self.assertTrue(self.handler._serve_vision())
        status=json.loads(self.handler.wfile.getvalue())
        self.assertEqual(status['reverse_current_monitor']['mode'],'report_only')
        self.assertTrue(status['reverse_current_monitor']['candidate'])
        self.handler.server.roomba_control.execute.assert_not_called()

    def test_zero_detection_scans_can_be_listed(self):
        self.camera.recent_scans.return_value = []
        self.handler.path = '/cam/scans.json'
        self.handler._serve_vision()
        self.camera.recent_scans.assert_called_once_with(20, tags_only=False)

    def test_invalid_limit_is_rejected(self):
        for limit in ('0', '201', 'nope'):
            self.handler.path = '/cam/tags.json?limit=' + limit
            self.handler._serve_vision()
        self.assertEqual(self.handler.send_error.call_count, 3)
        self.camera.recent_scans.assert_not_called()

    def test_archive_download_and_missing_file(self):
        filename = Mock()
        filename.suffix = '.jpg'
        filename.read_bytes.return_value = b'jpeg'
        self.camera.scan_archive_file.return_value = filename
        self.handler.path = '/cam/scans/20261027/20261027-120000-123456.jpg'
        self.handler._serve_vision()
        self.assertEqual(self.handler.wfile.getvalue(), b'jpeg')
        self.camera.scan_archive_file.assert_called_with('20261027/20261027-120000-123456.jpg')
        self.camera.scan_archive_file.return_value = None
        self.handler._serve_vision()
        self.handler.send_error.assert_called_once_with(404, 'Scan archive file not found')


if __name__ == '__main__':
    unittest.main()
