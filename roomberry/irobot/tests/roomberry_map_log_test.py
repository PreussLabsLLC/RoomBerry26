# @(#)roomberry_map_log_test.py 2.3.map-log.1 2026/10/30 18:30:00
import csv
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from roomberry_map_log import MapPngRecorder
from roomberry_mapper import RoomberryMapper


class MapPngRecorderTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.mapper = RoomberryMapper(10, 10, 40, cell_size_mm=100)
        self.mapper.update_pose(450, 450, 0)
        self.recorder = MapPngRecorder(self.mapper, directory=self.directory.name)
        self.addCleanup(self.recorder.close)

    def rows(self):
        with (self.recorder.path / 'index.csv').open() as index:
            return list(csv.DictReader(index))

    def test_writes_timestamped_png_and_final_index_before_close_returns(self):
        self.recorder.start()
        self.recorder.request('mission shutdown', mode='idle', force=True)
        self.recorder.close()
        rows = self.rows()
        self.assertEqual(rows[-1]['reason'], 'mission shutdown')
        self.assertEqual(rows[-1]['mode'], 'idle')
        for row in rows:
            self.assertTrue(row['filename'].startswith('map-'))
            self.assertGreater(float(row['epoch_s']), 0)
            self.assertIn('T', row['timestamp'])
            image = Image.open(BytesIO((self.recorder.path / row['filename']).read_bytes()))
            image.verify()
        self.assertFalse(list(self.recorder.path.glob('*.tmp')))
        self.assertFalse(self.recorder.request('after shutdown', force=True))

    def test_periodic_recording_is_throttled_but_stop_is_immediate(self):
        with patch('roomberry_map_log.monotonic', return_value=100):
            self.recorder.start()
            self.assertFalse(self.recorder.request())
        with patch('roomberry_map_log.monotonic', return_value=129):
            self.assertFalse(self.recorder.request())
        with patch('roomberry_map_log.monotonic', return_value=130):
            self.assertTrue(self.recorder.request())
            self.assertTrue(self.recorder.request('leaving active mode', force=True))
        self.recorder.close()
        self.assertEqual(self.rows()[-1]['reason'], 'leaving active mode')

    def test_slow_render_does_not_block_requests_and_keeps_latest_snapshot(self):
        entered, release = Event(), Event()
        states = []
        def render(state, tags, caption):
            states.append(state)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test did not release renderer')
            return b'png test'
        with patch('roomberry_map_log.render_map', side_effect=render):
            self.recorder.start()
            try:
                self.assertTrue(entered.wait(2))
                self.mapper.update_pose(550, 450, 0)
                self.assertTrue(self.recorder.request('intermediate', force=True))
                self.mapper.update_pose(650, 450, 0)
                self.assertTrue(self.recorder.request('final', force=True))
                self.mapper.update_pose(750, 450, 0)
            finally:
                release.set()
                self.recorder.close()
        self.assertEqual([r['reason'] for r in self.rows()], ['service startup', 'final'])
        self.assertEqual(states[-1]['pose']['x_mm'], 650)

    def test_unwritable_directory_disables_only_recording(self):
        self.recorder.logger = Mock()
        with patch.object(Path, 'mkdir', side_effect=PermissionError('permission denied')):
            self.recorder.start()
        self.assertFalse(self.recorder.request(force=True))
        self.recorder.logger.exception.assert_called_once()

    def test_server_drains_map_recorder_even_if_mission_close_fails(self):
        from types import SimpleNamespace
        from roomberry import RoomberryServer
        server = SimpleNamespace(logger=Mock(), map_log=Mock(), navlink=Mock(),
            mission=Mock(), roomba_control=Mock(), camera_service=Mock(),
            autonomy_config={}, serve_forever=Mock(), server_close=Mock())
        RoomberryServer.start(server)
        server.map_log.start.assert_called_once_with()
        server.mission.close.side_effect = OSError('mission close failed')
        with self.assertRaises(OSError):
            RoomberryServer.stop(server)
        server.map_log.close.assert_called_once_with()
        server.camera_service.close.assert_called_once_with()
        server.roomba_control.close.assert_called_once_with()
        server.navlink.close.assert_called_once_with()

    def test_missing_or_disabled_configuration_creates_no_recorder(self):
        self.assertIsNone(MapPngRecorder.from_config(None, self.mapper))
        self.assertIsNone(MapPngRecorder.from_config(dict(enabled=False), self.mapper))
