# @(#)roomberry_run_trails_test.py 3.2.trails.1 2026/11/10 13:54:11
import unittest
from unittest.mock import Mock, patch
from roomberry_mapper import RoomberryMapper
from roomberry_run_trails import RunTrails
from roomberry_map_image import render_map, IPHONE_TRAIL_COLOR, TRAIL_NEWEST_COLOR
from PIL import Image
from io import BytesIO


class RunTrailsTest(unittest.TestCase):
    def setUp(self):
        self.mapper = RoomberryMapper(20, 20, 100, cell_size_mm=100)
        self.trace = RunTrails(self.mapper, None, Mock(), {})
        self.state = dict(distance=0, angle=0, odometry_epoch=1, ready=True, age=0)
        self.pose = dict(x_mm=200, y_mm=200, heading_rad=0, localized=True)

    def test_wheel_trail_survives_coverage_clear_and_ignores_later_tag_fixes(self):
        self.trace.anchor(self.pose, 0, self.state)
        self.state['distance'] = 100
        self.trace.update(self.state)
        self.mapper.clear_coverage()
        self.trace.anchor(dict(self.pose, x_mm=1500), 1, self.state)
        self.state['distance'] = 200
        self.trace.update(self.state)
        self.assertEqual(self.mapper.snapshot()['run_trails']['wheel'],
                         [(200,200), (300,200), (400,200)])

    def test_epoch_change_breaks_trace_and_requires_new_anchor(self):
        self.trace.anchor(self.pose, 0, self.state)
        self.state.update(distance=100, odometry_epoch=2)
        self.trace.update(self.state)
        self.assertIsNone(self.trace.pose)
        self.trace.anchor(dict(self.pose, x_mm=1000), 1, self.state)
        self.assertEqual(self.trace.wheel, [(200,200), None, (1000,200)])

    def test_phone_loss_breaks_line_and_session_change_is_not_transformed(self):
        phone = Mock()
        phone.anchor = dict(session=1, map_uuid_hex=bytes(16).hex())
        phone.usable.return_value = True
        phone.transform.return_value = dict(x_mm=300, y_mm=300)
        row = dict(session=1, map_uuid=bytes(16), frame_monotonic=10, seq=1)
        phone.receiver.latest_trek_observation.return_value = row
        self.trace.phone = phone
        with patch('roomberry_run_trails.monotonic', return_value=10):
            self.trace.anchor(self.pose, 0, self.state)
            phone.usable.return_value = False
            self.trace.update(self.state)
            phone.usable.return_value = True
            row.update(seq=2, session=2)
            self.trace.update(self.state)
            phone.transform.assert_called_once()
            row.update(seq=3, session=1)
            phone.transform.return_value = dict(x_mm=400, y_mm=300)
            self.trace.update(self.state)
        self.assertEqual(self.trace.iphone, [(300,300), None, (400,300)])

    def test_map_renders_both_current_traces_and_hides_saved_history(self):
        state = self.mapper.snapshot()
        state.update(trail=[(200,600),(400,600)],
                     run_trails=dict(wheel=[(200,200),(400,200)],
                                     iphone=[(200,400),(400,400)]))
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        def pixel(x,y): return image.getpixel((int(56+x/100*12), int(42+(20-y/100)*12)))
        self.assertEqual(pixel(300,200), TRAIL_NEWEST_COLOR)
        self.assertEqual(pixel(300,400), IPHONE_TRAIL_COLOR)
        self.assertNotEqual(pixel(300,600), TRAIL_NEWEST_COLOR)
