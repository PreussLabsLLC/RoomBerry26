# @(#)roomberry_overhead_test.py 1.0.overhead.1 2026/11/02 19:20:00
import csv
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from roomberry_overhead import (
    DEFAULT_TILE_MM, apply_homography, color_mask, compare_tracks,
    connected_components, detect_marker, grid_homography, homography_from_points,
    iter_frames, load_homography, marker_pose, probe_video, reference_frame,
    reprojection_rms, save_homography, track_legs, write_track_csv,
)


class HomographyTest(unittest.TestCase):
    def test_square_maps_exactly(self):
        source = [[0, 0], [100, 0], [100, 100], [0, 100]]
        destination = [[0, 0], [304.8, 0], [304.8, -304.8], [0, -304.8]]
        transform = homography_from_points(source, destination)
        mapped = apply_homography(transform, source)
        np.testing.assert_allclose(mapped, destination, atol=1e-9)
        self.assertAlmostEqual(
            reprojection_rms(transform, source, destination), 0.0, places=9)

    def test_perspective_round_trip(self):
        source = [[10, 20], [410, 60], [380, 300], [40, 260]]
        destination = [[0, 0], [1219.2, 0], [1219.2, -914.4], [0, -914.4]]
        transform = homography_from_points(source, destination)
        np.testing.assert_allclose(
            apply_homography(transform, source), destination, atol=1e-6)
        inverse = np.linalg.inv(transform)
        np.testing.assert_allclose(
            apply_homography(inverse, destination), source, atol=1e-6)

    def test_grid_uses_imperial_pitch(self):
        points = [[0, 0], [600, 0], [600, 400], [0, 400]]
        transform = grid_homography(points, (6, 4))
        self.assertAlmostEqual(DEFAULT_TILE_MM, 304.8)
        # 600 px spans six tiles, so one tile is 100 px on this synthetic grid.
        one_tile = apply_homography(transform, [[100.0, 0]])[0]
        self.assertAlmostEqual(one_tile[0], DEFAULT_TILE_MM, places=6)
        one_down = apply_homography(transform, [[0, 100.0]])[0]
        self.assertAlmostEqual(one_down[1], -DEFAULT_TILE_MM, places=6)

    def test_degenerate_points_are_rejected(self):
        with self.assertRaises(ValueError):
            homography_from_points([[0, 0], [1, 1], [2, 2], [3, 3]],
                                   [[0, 0], [1, 0], [1, 1], [0, 1]])
        with self.assertRaises(ValueError):
            grid_homography([[0, 0], [1, 0], [1, 1], [0, 1]], (0, 4))

    def test_save_and_load(self):
        transform = grid_homography([[0, 0], [600, 0], [600, 400], [0, 400]], (6, 4))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'grid.json'
            save_homography(path, transform, {'frame_width': 640, 'span_tiles': [6, 4]})
            loaded, metadata = load_homography(path)
            np.testing.assert_allclose(loaded, transform, atol=1e-12)
            self.assertEqual(metadata['frame_width'], 640)
            self.assertEqual(metadata['span_tiles'], [6, 4])


class MarkerDetectionTest(unittest.TestCase):
    @staticmethod
    def scene():
        image = Image.new('RGB', (400, 300), (200, 200, 200))
        draw = ImageDraw.Draw(image)
        draw.rectangle((90, 140, 110, 160), fill=(230, 30, 30))
        draw.rectangle((190, 140, 210, 160), fill=(30, 200, 60))
        return image

    def test_colour_mask_isolates_a_preset(self):
        image = self.scene()
        red = color_mask(image, 'red')
        green = color_mask(image, 'green')
        self.assertEqual(int(red.sum()), 21 * 21)
        self.assertEqual(int(green.sum()), 21 * 21)
        self.assertEqual(int((red & green).sum()), 0)

    def test_components_are_sorted_by_area(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[1:4, 1:4] = True
        mask[10:18, 10:18] = True
        blobs = connected_components(mask)
        self.assertEqual([blob['area'] for blob in blobs], [64, 9])
        self.assertAlmostEqual(blobs[0]['cx'], 13.5)
        self.assertAlmostEqual(blobs[0]['cy'], 13.5)

    def test_pose_reports_position_heading_and_baseline(self):
        image = self.scene()
        # 100 px per tile over a 2x2 tile square.
        transform = grid_homography([[0, 0], [609.6, 0], [609.6, 609.6], [0, 609.6]],
                                    (2, 2))
        pose = marker_pose(image, transform, 'green', 'red',
                           min_area=20, baseline_mm=100.0)
        self.assertIsNotNone(pose)
        self.assertAlmostEqual(pose['x_mm'], 150.0, places=2)
        self.assertAlmostEqual(pose['y_mm'], -150.0, places=2)
        self.assertAlmostEqual(pose['heading_rad'], 0.0, places=3)
        self.assertAlmostEqual(pose['baseline_mm'], 100.0, places=2)
        self.assertAlmostEqual(pose['baseline_error_mm'], 0.0, places=1)

    def test_single_marker_still_gives_position(self):
        image = Image.new('RGB', (200, 200), (200, 200, 200))
        ImageDraw.Draw(image).rectangle((40, 40, 60, 60), fill=(30, 200, 60))
        transform = grid_homography([[0, 0], [200, 0], [200, 200], [0, 200]], (2, 2))
        pose = marker_pose(image, transform, 'red', 'green', min_area=20)
        self.assertIsNotNone(pose)
        self.assertIsNone(pose['heading_rad'])
        self.assertAlmostEqual(pose['x_mm'], 152.4, places=1)

    def test_missing_markers_return_none(self):
        image = Image.new('RGB', (100, 100), (200, 200, 200))
        transform = grid_homography([[0, 0], [100, 0], [100, 100], [0, 100]], (2, 2))
        self.assertIsNone(marker_pose(image, transform, 'red', 'green'))
        self.assertIsNone(detect_marker(image, 'red'))

    def test_roi_offsets_coordinates(self):
        image = self.scene()
        found = detect_marker(image, 'green', roi=(150, 100, 260, 200), min_area=20)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found['px'][0], 200.0, places=1)
        self.assertAlmostEqual(found['px'][1], 150.0, places=1)


class CompareTest(unittest.TestCase):
    def test_recovers_time_offset_and_scale(self):
        # Overhead track: starts at t=10 s, 0.5 s stationary, 2 s at 500 mm/s,
        # then 0.5 s stationary. 1000 mm total. The Pi log starts at 0 s with
        # 950 mm of encoder travel, so the video must shift by -10 s and the
        # wheels read 5 % short.
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            track_path = folder / 'track.csv'
            rows = []
            for index in range(0, 31):
                time_s = 10.0 + index * 0.1
                travelled = min(1000.0, max(0.0, (time_s - 10.5) * 500.0))
                rows.append({'frame': index, 'time_s': time_s,
                             'x_mm': travelled, 'y_mm': 0.0,
                             'heading_rad': 0.0, 'baseline_mm': 300.0,
                             'front_x': None, 'front_y': None,
                             'rear_x': None, 'rear_y': None})
            write_track_csv(track_path, rows)

            sensor_path = folder / 'sensors.csv'
            with sensor_path.open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['timestamp', 'elapsed_s', 'travelled_distance_mm',
                                 'distance_mm', 'angle_deg', 'distance_delta_mm',
                                 'angle_delta_deg', 'odometry_epoch',
                                 'raw_distance_mm', 'raw_angle_deg'])
                for index in range(0, 51):
                    time_s = index * 0.1
                    travelled = min(950.0, max(0.0, (time_s - 0.5) * 475.0))
                    writer.writerow([time_s, time_s, travelled, travelled,
                                     0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            result = compare_tracks(track_path, sensor_path, max_offset_s=30.0)
            self.assertAlmostEqual(result['offset_s'], -10.0, delta=0.6)
            self.assertAlmostEqual(result['path_ratio'], 1000.0 / 950.0, delta=0.05)
            self.assertGreater(result['correlation'], 0.7)
            self.assertGreater(result['aligned_samples'], 5)

    def test_flat_tracks_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            track_path = folder / 'track.csv'
            write_track_csv(track_path, [
                {'frame': i, 'time_s': i * 0.1, 'x_mm': 0.0, 'y_mm': 0.0}
                for i in range(10)])
            sensor_path = folder / 'sensors.csv'
            with sensor_path.open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['elapsed_s', 'travelled_distance_mm', 'distance_mm'])
                for i in range(10):
                    writer.writerow([i * 0.1, 0.0, 0.0])
            with self.assertRaises(ValueError):
                compare_tracks(track_path, sensor_path)


class LegsTest(unittest.TestCase):
    @staticmethod
    def rows(stations):
        """Build a 10 Hz track from (hold_s, move_s, dx_mm) segments."""
        rows = []
        time_s = 0.0
        x = 0.0
        index = 0
        for hold_s, move_s, dx in stations:
            steps = max(1, int(round(hold_s * 10)))
            for _ in range(steps):
                rows.append({'frame': index, 'time_s': time_s, 'x_mm': x, 'y_mm': 0.0})
                index += 1
                time_s += 0.1
            steps = max(1, int(round(move_s * 10)))
            for step in range(1, steps + 1):
                rows.append({'frame': index, 'time_s': time_s,
                             'x_mm': x + dx * step / steps, 'y_mm': 0.0})
                index += 1
                time_s += 0.1
            x += dx
        return rows

    def test_each_stop_starts_a_leg(self):
        rows = self.rows([(1.0, 1.0, 304.8), (1.0, 1.0, 304.8), (1.0, 0.0, 0.0)])
        legs = track_legs(rows)
        self.assertEqual(len(legs), 2)
        for leg in legs:
            self.assertAlmostEqual(leg['distance_mm'], 304.8, delta=1.0)
            self.assertAlmostEqual(leg['tiles'], 1.0, delta=0.01)
            self.assertGreater(leg['dx_mm'], 0)
            self.assertAlmostEqual(leg['dy_mm'], 0.0, delta=1e-6)

    def test_reverse_leg_has_negative_dx(self):
        rows = self.rows([(1.0, 1.0, 304.8), (1.0, 1.0, -304.8), (1.0, 0.0, 0.0)])
        legs = track_legs(rows)
        self.assertEqual(len(legs), 2)
        self.assertGreater(legs[0]['dx_mm'], 300)
        self.assertLess(legs[1]['dx_mm'], -300)

    def test_brief_dip_does_not_split_a_leg(self):
        rows = self.rows([(1.0, 2.0, 609.6), (1.0, 0.0, 0.0)])
        # Insert a 0.1 s hesitation halfway through the move.
        for row in rows:
            if 1.9 < row['time_s'] < 2.1:
                row['x_mm'] = 304.8
        legs = track_legs(rows)
        self.assertEqual(len(legs), 1)
        self.assertAlmostEqual(legs[0]['distance_mm'], 609.6, delta=1.0)

    def test_short_middle_stop_is_ignored(self):
        rows = self.rows([(1.0, 1.0, 304.8), (0.2, 1.0, 304.8), (1.0, 0.0, 0.0)])
        legs = track_legs(rows)
        self.assertEqual(len(legs), 1)
        self.assertAlmostEqual(legs[0]['distance_mm'], 609.6, delta=1.0)

    def test_short_track_returns_no_legs(self):
        self.assertEqual(track_legs([]), [])
        self.assertEqual(track_legs([
            {'time_s': 0.0, 'x_mm': 0.0, 'y_mm': 0.0},
            {'time_s': 0.1, 'x_mm': 0.0, 'y_mm': 0.0}]), [])


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / 'tools' / 'overhead-track.py'
        spec = importlib.util.spec_from_file_location('overhead_track_cli', path)
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def test_help_renders(self):
        # argparse treats a bare % as a format character in help strings.
        text = self.cli.build_parser().format_help()
        for command in ('frame', 'calibrate', 'check', 'swatch', 'track',
                        'legs', 'compare'):
            self.assertIn(command, text)

    def test_subcommands_parse(self):
        parser = self.cli.build_parser()
        for argv in (['frame', '--video', 'v.mov', '--output', 'f.png'],
                     ['calibrate', '--frame', 'f.png', '--output', 'g.json'],
                     ['check', '--frame', 'f.png', '--grid', 'g.json',
                      '--output', 'c.png'],
                     ['swatch', '--frame', 'f.png'],
                     ['track', '--video', 'v.mov', '--grid', 'g.json',
                      '--output', 't.csv'],
                     ['legs', '--track', 't.csv'],
                     ['compare', '--track', 't.csv', '--sensors', 's.csv']):
            args = parser.parse_args(argv)
            self.assertTrue(callable(args.func), argv[0])

    def test_picker_clicks_selects_and_nudges(self):
        import tkinter as tk

        frame = Image.new('RGB', (960, 540), (200, 200, 200))
        original = tk.Tk.mainloop

        def scripted_mainloop(root, *args, **kwargs):
            root.after(5000, root.destroy)  # never hang the suite
            root.update()
            canvas = root.winfo_children()[0]
            scale = min(1.0, (root.winfo_screenwidth() - 80) / 960.0,
                        (root.winfo_screenheight() - 160) / 540.0)

            def click(x, y):
                canvas.event_generate('<Button-1>', x=int(round(x * scale)),
                                      y=int(round(y * scale)), when='now')

            click(30, 40)
            click(630, 40)
            click(630, 440)
            click(30, 440)
            for _ in range(10):  # ten half-pixel nudges on point 4
                canvas.event_generate('<Right>', when='now')
            canvas.event_generate('<Key-bracketleft>', when='now')
            canvas.event_generate('<Down>', when='now')
            canvas.event_generate('<Key-s>', when='now')

        tk.Tk.mainloop = scripted_mainloop
        try:
            points = self.cli._pick_points(frame, (6, 4), 304.8)
        except tk.TclError as error:
            self.skipTest('no display: {}'.format(error))
        finally:
            tk.Tk.mainloop = original
        self.assertEqual(len(points), 4)
        self.assertAlmostEqual(points[0][0], 30.0, delta=1.0)
        self.assertAlmostEqual(points[0][1], 40.0, delta=1.0)
        # Point 4 moved 10 x 0.5 px to the right.
        self.assertAlmostEqual(points[3][0], 35.0, delta=1.0)
        # `[` selected point 3, then Down moved it 0.5 px.
        self.assertAlmostEqual(points[2][1], 440.5, delta=1.0)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'ffmpeg is required for video decoding')
class VideoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.video = Path(cls.folder.name) / 'clip.mp4'
        subprocess.run([
            'ffmpeg', '-v', 'error', '-y',
            '-f', 'lavfi', '-i', 'color=c=gray:s=320x240:d=1:r=10',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_probe_and_reference_frame(self):
        probe = probe_video(self.video)
        self.assertEqual((probe['width'], probe['height']), (320, 240))
        self.assertAlmostEqual(probe['fps'], 10.0, delta=0.5)
        self.assertGreater(probe['duration_s'], 0.5)
        frame = reference_frame(self.video, 0.2, width=160)
        self.assertEqual(frame.size, (160, 120))

    def test_iter_frames_rescales_to_requested_width(self):
        frames = list(iter_frames(self.video, fps=5, width=160))
        self.assertGreaterEqual(len(frames), 4)
        index, time_s, frame = frames[1]
        self.assertEqual(index, 1)
        self.assertGreater(time_s, 0.0)
        self.assertEqual(frame.shape, (120, 160, 3))
        self.assertEqual(frame.dtype, np.uint8)


if __name__ == '__main__':
    unittest.main()
