# @(#)roomberry_map_image_test.py 2.3.map-log.1 2026/10/30 18:30:00
import unittest
from io import BytesIO
from math import pi

from PIL import Image

from roomberry_map_image import (
    TRAIL_GAP_MM, TRAIL_NEWEST_COLOR, TRAIL_OLDEST_COLOR, _fade_color,
    render_map, trail_segments,
    TAG_FACING_COLOR,
)


class RoomberryTrailRenderingTest(unittest.TestCase):
    @staticmethod
    def state():
        return dict(cols=10, rows=10, cell_size_mm=100.0, origin_x=0, origin_y=0,
                    occupancy=[['free']*10 for _ in range(10)],
                    cookies=[['pending']*10 for _ in range(10)],pose=None)

    @staticmethod
    def pixel(image, x, y):
        return image.getpixel((int(56+x/100*12), int(42+(10-y/100)*12)))

    def test_single_leg_clearance_is_distinct_from_disconnected_space(self):
        state = self.state()
        state['robot_radius_mm'] = 174
        state['occupancy'][5][5] = 'blocked'
        state['pose'] = dict(cell=[1,1], x_mm=150, y_mm=150, heading_rad=0)
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        from roomberry_map_image import COLORS
        self.assertEqual(self.pixel(image, 550, 550), COLORS['blocked'])
        self.assertEqual(self.pixel(image, 750, 550), COLORS['clearance'])
        self.assertEqual(self.pixel(image, 850, 850), COLORS['pending'])

    def test_pose_inside_clearance_does_not_mark_whole_room_unreachable(self):
        state = self.state()
        state['occupancy'][5][5] = 'blocked'
        state['occupancy'][2][8] = 'blocked'
        state['pose'] = dict(cell=[4,5], x_mm=450, y_mm=550, heading_rad=0)
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        from roomberry_map_image import COLORS
        self.assertEqual(self.pixel(image, 850, 850), COLORS['pending'])
        self.assertEqual(self.pixel(image, 850, 250), COLORS['blocked'])

    def test_reachable_start_still_marks_disconnected_cells_unreachable(self):
        state = self.state()
        state['robot_radius_mm'] = 40
        for y in range(10):
            state['occupancy'][y][5] = 'blocked'
        state['pose'] = dict(cell=[2,5], x_mm=250, y_mm=550, heading_rad=0)
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        from roomberry_map_image import COLORS
        self.assertEqual(self.pixel(image, 850, 850), COLORS['unreachable'])
        self.assertEqual(self.pixel(image, 250, 850), COLORS['pending'])

    def test_entire_current_session_has_same_full_visibility(self):
        state = self.state()
        state.update(trail=[(x,100) for x in range(100,801,100)],trail_session_start=0)
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        self.assertEqual(self.pixel(image,150,100),TRAIL_NEWEST_COLOR)
        self.assertEqual(self.pixel(image,750,100),TRAIL_NEWEST_COLOR)

    def test_previous_session_fades_and_session_boundary_has_no_bridge(self):
        state = self.state()
        state.update(trail=[(x,100) for x in range(100,701,100)],trail_session_start=3)
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        background = Image.open(BytesIO(render_map(self.state()))).convert('RGB')
        self.assertNotEqual(self.pixel(image,150,100),TRAIL_NEWEST_COLOR)
        self.assertEqual(self.pixel(image,450,100),TRAIL_NEWEST_COLOR)
        self.assertEqual(self.pixel(image,350,100),self.pixel(background,350,100))

    def test_legacy_snapshot_without_session_metadata_stays_visible(self):
        state = self.state()
        state['trail'] = [(100,100),(200,100),(300,100)]
        image = Image.open(BytesIO(render_map(state))).convert('RGB')
        self.assertEqual(self.pixel(image,150,100),TRAIL_NEWEST_COLOR)

    def test_tag_arrows_render_all_four_world_directions(self):
        for heading,dx,dy in [(0,1,0),(pi/2,0,-1),(pi,-1,0),(-pi/2,0,1)]:
            with self.subTest(heading=heading):
                image=Image.open(BytesIO(render_map(self.state(),[(500,500,16,heading)]))).convert('RGB')
                cx,cy=116,102
                self.assertEqual(image.getpixel((cx+dx*32,cy+dy*32)),TAG_FACING_COLOR)
                self.assertNotEqual(image.getpixel((cx-dx*32,cy-dy*32)),TAG_FACING_COLOR)

    def test_legacy_position_only_tag_markers_still_render(self):
        self.assertTrue(render_map(self.state(),[(500,500,1)]).startswith(b'\x89PNG'))

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
