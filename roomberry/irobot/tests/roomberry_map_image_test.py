# @(#)roomberry_map_image_test.py 1.0 2026/10/26
import unittest
from io import BytesIO

from PIL import Image

from roomberry_map_image import (
    TRAIL_GAP_MM, TRAIL_NEWEST_COLOR, TRAIL_OLDEST_COLOR, _fade_color,
    render_map, trail_segments,
)


class RoomberryTrailRenderingTest(unittest.TestCase):
    def test_large_localization_jump_splits_the_trail(self):
        trail = [(100, 100), (200, 100), (900, 900), (950, 900)]

        segments = trail_segments(trail, gap_mm=TRAIL_GAP_MM)

        self.assertEqual(
            segments,
            [[(100.0, 100.0), (200.0, 100.0)],
             [(900.0, 900.0), (950.0, 900.0)]],
        )

    def test_single_point_segments_are_not_drawn(self):
        self.assertEqual(trail_segments([(0, 0), (500, 0)], gap_mm=100), [])

    def test_fade_runs_from_old_to_new_color(self):
        self.assertEqual(_fade_color(0.0), TRAIL_OLDEST_COLOR)
        self.assertEqual(_fade_color(1.0), TRAIL_NEWEST_COLOR)

    def test_render_does_not_connect_across_a_localization_jump(self):
        state = {
            'cols': 10,
            'rows': 10,
            'cell_size_mm': 100.0,
            'origin_x': 0.0,
            'origin_y': 0.0,
            'occupancy': [['free'] * 10 for _ in range(10)],
            'cookies': [['pending'] * 10 for _ in range(10)],
            'pose': None,
            'trail': [(100.0, 100.0), (900.0, 900.0)],
        }

        payload = render_map(state)
        image = Image.open(BytesIO(payload)).convert('RGB')

        # This pixel would sit on the line if the two poses were joined.
        red, green, blue = image.getpixel((107, 111))
        self.assertTrue(payload.startswith(b'\x89PNG'))
        self.assertLess(blue, 150, (red, green, blue))


if __name__ == '__main__':
    unittest.main()
