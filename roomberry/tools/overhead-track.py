#!/usr/bin/env python3
# @(#)overhead-track.py 1.0.overhead.1 2026/11/02 19:10:00
"""Calibrate and track the robot from a fixed overhead phone video.

The kitchen floor is a metric ruler: 1 ft (304.8 mm) tiles with grout lines.
Four tile intersections give a pixel-to-millimetre homography, and two coloured
markers on the robot give its floor pose. The resulting track is independent
ground truth for the wheel odometry.

Typical session::

    # 1. Pull one frame and click four tile intersections.
    tools/overhead-track.py frame --video run.mov --output run.png
    tools/overhead-track.py calibrate --frame run.png \\
        --span 6 4 --output run-grid.json

    # 2. Verify the grid overlay before trusting it.
    tools/overhead-track.py check --frame run.png \\
        --grid run-grid.json --output run-grid-check.png

    # 3. Track the markers and compare with the Pi sensor log.
    tools/overhead-track.py track --video run.mov --grid run-grid.json \\
        --front red --rear green --output run-track.csv
    tools/overhead-track.py legs --track run-track.csv --expected-tiles 1
    tools/overhead-track.py compare --track run-track.csv \\
        --sensors roomberry-sensors-20261102-160100.csv

Run ``compare --help`` for the time-window options. The video and the Pi log
have no shared clock, so the tool aligns them by cross-correlating speed.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roomberry_overhead import (  # noqa: E402
    DEFAULT_TILE_MM, DEFAULT_WIDTH, MARKER_PRESETS, apply_homography,
    grid_homography, load_homography, load_track, probe_video,
    reference_frame, save_homography, track_video, compare_tracks,
    detect_marker, track_legs, write_json,
)


def _fmt(value, unit='', digits=1):
    if value is None:
        return 'n/a'
    return '{:.{d}f}{u}'.format(value, d=digits, u=unit)


def command_frame(args):
    probe = probe_video(args.video)
    image = reference_frame(args.video, args.time, args.width)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    print('video   {}x{} @ {:.2f} fps, {:.1f} s'.format(
        probe['width'], probe['height'], probe['fps'], probe['duration_s']))
    print('frame   {} at t={:.3f}s, {}x{} px'.format(
        output, args.time, image.width, image.height))
    print('click   four tile intersections in clockwise order, starting at '
          'the top-left of the rectangle you will drive across')


def _pick_points(image, span, tile_mm, count=4):
    """Open a click-to-pick window with a magnifier; return source pixels."""
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title('Click {} tile intersections (clockwise). '
               'u=undo r=reset s=save q=quit'.format(count))

    # Fit the frame on screen while keeping a copy for the magnifier.
    screen_w = root.winfo_screenwidth() - 80
    screen_h = root.winfo_screenheight() - 160
    scale = min(1.0, screen_w / image.width, screen_h / image.height)
    shown = image if scale >= 1.0 else image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.LANCZOS)
    photo = ImageTk.PhotoImage(shown)

    canvas = tk.Canvas(root, width=shown.width, height=shown.height,
                       highlightthickness=0, cursor='crosshair')
    canvas.pack()
    canvas.create_image(0, 0, image=photo, anchor='nw')
    status = tk.Label(root, anchor='w', justify='left', font=('Menlo', 11))
    status.pack(fill='x')

    mag_size = 220
    mag_zoom = 6
    points = []
    state = {'cursor': (0, 0), 'saved': False, 'magnifier': True,
             'selected': None}
    overlays = []
    mag_photo = None

    def redraw_message():
        if len(points) < count:
            text = ('click point {}/{}   |   u undo, r reset, '
                    's save, q quit'.format(len(points) + 1, count))
        else:
            text = ('all {} points picked   |   [ ] select point, arrows nudge '
                    '(shift = fine), u undo, r reset, s save'.format(count))
        status.configure(text=text)

    def refresh_magnifier():
        nonlocal mag_photo
        if not state['magnifier']:
            return
        if state['selected'] is not None and points:
            sx, sy = points[state['selected']]
        else:
            sx, sy = state['cursor']
        span_px = max(4, int(round(mag_size / mag_zoom)))
        left = int(max(0, min(image.width - span_px,
                              round(sx - span_px / 2.0))))
        top = int(max(0, min(image.height - span_px,
                             round(sy - span_px / 2.0))))
        crop = image.crop((left, top, left + span_px, top + span_px))
        crop = crop.resize((mag_size, mag_size), Image.NEAREST)
        draw = ImageDraw.Draw(crop)
        # The crosshair tracks the crop origin, which is clamped at the edges.
        zoom_x = mag_size / span_px
        cx = (sx - left) * zoom_x
        cy = (sy - top) * zoom_x
        draw.line((cx, 0, cx, mag_size), fill=(0, 255, 255))
        draw.line((0, cy, mag_size, cy), fill=(0, 255, 255))
        # Mark the source pixel under the crosshair so the nudge is visible.
        draw.rectangle((cx - 2, cy - 2, cx + 2, cy + 2),
                       outline=(255, 210, 0))
        mag_photo = ImageTk.PhotoImage(crop)
        canvas.delete('mag')
        x0 = shown.width - mag_size - 8
        canvas.create_image(x0, 8, image=mag_photo, anchor='nw', tags='mag')
        canvas.create_rectangle(x0, 8, x0 + mag_size, 8 + mag_size,
                                outline='#00ffff', tags='mag')

    def draw_magnifier(event):
        state['cursor'] = (event.x / scale, event.y / scale)
        refresh_magnifier()

    def draw_point(source_x, source_y, index):
        x, y = source_x * scale, source_y * scale
        tag = 'p{}'.format(index)
        selected = state['selected'] == index - 1
        colour = '#00ffff' if selected else '#ffd200'
        size = 14 if selected else 10
        canvas.create_line(x - size, y, x + size, y, fill=colour, width=2,
                           tags=tag)
        canvas.create_line(x, y - size, x, y + size, fill=colour, width=2,
                           tags=tag)
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, outline=colour,
                           width=2, tags=tag)
        canvas.create_text(x + 12, y - 12, text=str(index), fill=colour,
                           font=('Menlo', 12, 'bold'), tags=tag)

    def redraw_points():
        for index in range(1, count + 1):
            canvas.delete('p{}'.format(index))
        for index, (source_x, source_y) in enumerate(points, start=1):
            draw_point(source_x, source_y, index)

    def draw_grid_preview():
        for item in overlays:
            canvas.delete(item)
        overlays.clear()
        if len(points) != count:
            return
        try:
            transform = grid_homography(points, span, tile_mm)
        except ValueError as error:
            status.configure(text='grid error: {}'.format(error))
            return
        inverse = np.linalg.inv(transform)
        span_x, span_y = span
        for i in range(span_x + 1):
            a = apply_homography(inverse, [[i * tile_mm, 0]])[0]
            b = apply_homography(inverse,
                                 [[i * tile_mm, -span_y * tile_mm]])[0]
            overlays.append(canvas.create_line(
                a[0] * scale, a[1] * scale, b[0] * scale, b[1] * scale,
                fill='#ff00ff', width=1))
        for j in range(span_y + 1):
            a = apply_homography(inverse, [[0, -j * tile_mm]])[0]
            b = apply_homography(inverse,
                                 [[span_x * tile_mm, -j * tile_mm]])[0]
            overlays.append(canvas.create_line(
                a[0] * scale, a[1] * scale, b[0] * scale, b[1] * scale,
                fill='#ff00ff', width=1))

    def redraw_all():
        redraw_points()
        draw_grid_preview()
        redraw_message()
        refresh_magnifier()

    def on_click(event):
        if len(points) >= count:
            return
        points.append((event.x / scale, event.y / scale))
        if len(points) == count:
            state['selected'] = count - 1
        redraw_all()

    def undo(_event=None):
        if points:
            points.pop()
        state['selected'] = len(points) - 1 if points else None
        redraw_all()

    def reset(_event=None):
        points.clear()
        state['selected'] = None
        redraw_all()

    def nudge(dx, dy):
        if state['selected'] is None or not points:
            return
        x, y = points[state['selected']]
        points[state['selected']] = (x + dx, y + dy)
        redraw_all()

    def step_from(event):
        # 0.1 source pixels with Shift, 0.5 otherwise.
        return 0.1 if (event.state & 0x0001) else 0.5

    def select(offset):
        if not points:
            return
        current = state['selected'] if state['selected'] is not None else 0
        state['selected'] = (current + offset) % len(points)
        redraw_all()

    def save(_event=None):
        if len(points) != count:
            return
        state['saved'] = True
        root.destroy()

    def toggle_magnifier(_event=None):
        state['magnifier'] = not state['magnifier']
        if not state['magnifier']:
            canvas.delete('mag')
        else:
            refresh_magnifier()

    canvas.bind('<Button-1>', on_click)
    canvas.bind('<Motion>', draw_magnifier)
    root.bind('<Key-u>', undo)
    root.bind('<Key-r>', reset)
    root.bind('<Key-s>', save)
    root.bind('<Key-q>', lambda _event: root.destroy())
    root.bind('<Key-m>', toggle_magnifier)
    root.bind('<Key-bracketleft>', lambda event: select(-1))
    root.bind('<Key-bracketright>', lambda event: select(1))
    root.bind('<Left>', lambda event: nudge(-step_from(event), 0))
    root.bind('<Right>', lambda event: nudge(step_from(event), 0))
    root.bind('<Up>', lambda event: nudge(0, -step_from(event)))
    root.bind('<Down>', lambda event: nudge(0, step_from(event)))

    canvas.focus_set()
    redraw_message()
    root.mainloop()
    if not state['saved']:
        raise SystemExit('calibration cancelled')
    return points


def command_calibrate(args):
    frame = Image.open(args.frame).convert('RGB')
    width = args.width or frame.width
    if width != frame.width:
        frame = frame.resize((width, int(round(frame.height * width / frame.width))),
                             Image.LANCZOS)
    span = tuple(args.span_xy)
    if args.points:
        values = [float(v) for v in args.points.replace(',', ' ').split()]
        if len(values) != 8:
            raise SystemExit('--points needs eight numbers: x1 y1 x2 y2 x3 y3 x4 y4')
        points = list(zip(values[0::2], values[1::2]))
    else:
        points = _pick_points(frame, span, args.tile_mm)

    transform = grid_homography(points, span, args.tile_mm)
    metadata = {
        'frame_width': frame.width,
        'frame_height': frame.height,
        'span_tiles': list(span),
        'tile_mm': args.tile_mm,
        'points_px': [list(p) for p in points],
        'source': str(args.frame),
        'note': 'origin at first clicked intersection; +X along the first '
                'edge, +Y away from the camera',
    }
    save_homography(args.output, transform, metadata)
    inverse = np.linalg.inv(transform)
    a = apply_homography(inverse, [[0, 0]])[0]
    bx = apply_homography(inverse, [[args.tile_mm, 0]])[0]
    by = apply_homography(inverse, [[0, -args.tile_mm]])[0]
    pixels_across = float(np.hypot(*(bx - a)))
    pixels_down = float(np.hypot(*(by - a)))
    diagonal = math.hypot(span[0], span[1]) * args.tile_mm
    print('grid    {} tiles, {:.1f} mm diagonal'.format(
        'x'.join(str(v) for v in span), diagonal))
    print('scale   {:.1f} px / {:.0f} mm across, {:.1f} px / {:.0f} mm down '
          '(frame width {})'.format(pixels_across, args.tile_mm, pixels_down,
                                    args.tile_mm, frame.width))
    print('saved   {}'.format(args.output))
    print('next    tools/overhead-track.py check --frame {} --grid {} '
          '--output grid-check.png'.format(args.frame, args.output))


def command_check(args):
    frame = Image.open(args.frame).convert('RGB')
    transform, metadata = load_homography(args.grid)
    if int(metadata.get('frame_width', frame.width)) != frame.width:
        raise SystemExit(
            'frame is {} px wide but the grid was calibrated at {} px; '
            're-extract the frame at the calibration width'.format(
                frame.width, metadata.get('frame_width')))
    draw = ImageDraw.Draw(frame)
    span_x, span_y = metadata['span_tiles']
    tile = metadata['tile_mm']
    colour = (255, 0, 255)
    # grid_homography maps pixels to floor millimetres, so drawing needs the
    # inverse: floor millimetres back to pixels.
    inverse = np.linalg.inv(transform)
    for i in range(span_x + 1):
        a = apply_homography(inverse, [[i * tile, 0]])[0]
        b = apply_homography(inverse, [[i * tile, -span_y * tile]])[0]
        draw.line((a[0], a[1], b[0], b[1]), fill=colour, width=2)
    for j in range(span_y + 1):
        a = apply_homography(inverse, [[0, -j * tile]])[0]
        b = apply_homography(inverse, [[span_x * tile, -j * tile]])[0]
        draw.line((a[0], a[1], b[0], b[1]), fill=colour, width=2)
    for corner in ((0, 0), (span_x * tile, 0),
                   (span_x * tile, -span_y * tile), (0, -span_y * tile)):
        x, y = apply_homography(inverse, [corner])[0]
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(0, 255, 255), width=2)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.save(output)
    span_x, span_y = metadata['span_tiles']
    tile = metadata['tile_mm']
    inverse = np.linalg.inv(transform)
    a = apply_homography(inverse, [[0, 0]])[0]
    b = apply_homography(inverse, [[tile, 0]])[0]
    pixels = float(np.hypot(*(b - a)))
    if pixels > 0:
        print('scale   {:.2f} mm/px across the first tile edge '
              '({:.1f} px per tile)'.format(tile / pixels, pixels))
    print('overlay {}'.format(output))
    print('check   every magenta line should sit on a grout line and cyan '
          'rings should mark the four clicked intersections')


def command_swatch(args):
    frame = Image.open(args.frame).convert('RGB')
    roi = None
    if args.roi:
        roi = tuple(int(v) for v in args.roi.replace(',', ' ').split())
        if len(roi) != 4:
            raise SystemExit('--roi needs x0,y0,x1,y1')
    print('marker presets:')
    for name in MARKER_PRESETS:
        found = detect_marker(frame, name, roi=roi, min_area=args.min_area,
                              max_area=args.max_area)
        if found is None:
            print('  {:<8s} none'.format(name))
        else:
            print('  {:<8s} area {:6d} px at ({:.1f}, {:.1f})'.format(
                name, found['area'], found['px'][0], found['px'][1]))
    print('pick the two presets with the largest areas; tape matte paper, '
          'not glossy, to avoid specular holes')


def command_track(args):
    transform, metadata = load_homography(args.grid)
    roi = None
    if args.roi:
        roi = tuple(int(v) for v in args.roi.replace(',', ' ').split())
    rows, summary = track_video(
        args.video, transform, metadata, front=args.front, rear=args.rear,
        fps=args.fps, width=args.width or metadata.get('frame_width', DEFAULT_WIDTH),
        roi=roi, min_area=args.min_area, max_area=args.max_area,
        output_csv=args.output, max_frames=args.max_frames,
        debug_path=args.debug, debug_every=args.debug_every)
    print('frames  {} decoded, {} solved, {} missed'.format(
        summary['frames'], summary['solved'], summary['missed']))
    if args.debug:
        print('debug   {} frames written'.format(summary['debug_frames']))
    if rows:
        solved = [row for row in rows if row.get('x_mm') is not None]
        if solved:
            xs = [row['x_mm'] for row in solved]
            ys = [row['y_mm'] for row in solved]
            print('track   x {:.0f}..{:.0f} mm, y {:.0f}..{:.0f} mm'.format(
                min(xs), max(xs), min(ys), max(ys)))
        baselines = [row['baseline_mm'] for row in solved
                     if row.get('baseline_mm') is not None]
        if baselines:
            print('baseline median {:.1f} mm (spread {:.1f} mm); compare with '
                  'the tape distance between marker centres'.format(
                      float(np.median(baselines)),
                      float(np.max(baselines) - np.min(baselines))))
    print('saved   {}'.format(args.output))


def command_legs(args):
    rows = load_track(args.track)
    legs = track_legs(rows, tile_mm=args.tile_mm,
                      speed_threshold=args.speed_threshold,
                      min_stop_s=args.min_stop)
    if not legs:
        raise SystemExit('no stop-to-stop legs found; lower --speed-threshold '
                         'or shorten --min-stop')
    print('leg  start..end s      dur s   distance mm   tiles    dx mm'
          '    dy mm   speed mm/s')
    distances = []
    for leg in legs:
        distances.append(leg['distance_mm'])
        print('{:3d}  {:7.2f}..{:6.2f}  {:6.2f}  {:11.1f}  {:6.3f}  '
              '{:+7.1f}  {:+7.1f}  {:8.1f}'.format(
                  leg['index'], leg['start_s'], leg['end_s'],
                  leg['duration_s'], leg['distance_mm'], leg['tiles'],
                  leg['dx_mm'], leg['dy_mm'],
                  leg['mean_speed_mm_s'] or 0.0))
    median = float(np.median(distances))
    spread = float(np.max(distances) - np.min(distances))
    deviation = float(np.std(distances))
    print('summary {} legs: median {:.1f} mm ({:.3f} tiles), '
          'range {:.1f} mm, sd {:.1f} mm'.format(
              len(legs), median, median / args.tile_mm, spread, deviation))
    if args.expected_tiles:
        expected = float(args.expected_tiles) * args.tile_mm
        ratios = [distance / expected for distance in distances]
        print('expected {:.3f} tiles = {:.1f} mm: ratio median {:.4f}, '
              'min {:.4f}, max {:.4f}'.format(
                  args.expected_tiles, expected, float(np.median(ratios)),
                  min(ratios), max(ratios)))
        print('this is grid distance / intended distance, not the wheel scale; '
              'use compare for the wheel scale')
    if args.output:
        write_json(args.output, {
            'tile_mm': args.tile_mm,
            'speed_threshold_mm_s': args.speed_threshold,
            'min_stop_s': args.min_stop,
            'expected_tiles': args.expected_tiles,
            'legs': legs,
            'median_mm': median,
            'spread_mm': spread,
            'sd_mm': deviation,
        })
        print('saved   {}'.format(args.output))


def command_compare(args):
    result = compare_tracks(
        args.track, args.sensors, sensor_start=args.sensor_start,
        sensor_end=args.sensor_end, max_offset_s=args.max_offset,
        sample_dt=args.sample_dt)
    print('aligned at {:+.2f} s (speed correlation {:.3f}, {} samples)'.format(
        result['offset_s'], result['correlation'], result['aligned_samples']))
    print('path    overhead {:8.1f} mm   wheels {:8.1f} mm   ratio {:.4f}'.format(
        result['track_path_mm'], result['sensor_path_mm'],
        result['path_ratio'] or float('nan')))
    print('displacement {:6.1f} mm vs {:6.1f} mm   ratio {:.4f}'.format(
        result['track_displacement_mm'], result['sensor_displacement_mm'],
        result['displacement_ratio'] or float('nan')))
    if result['path_ratio']:
        print('odometry scale correction = {:.4f}  (multiply distance_mm)'.format(
            result['path_ratio']))
        print('overhead-wheels separation = {:+.1f} mm over {:.0f} mm'.format(
            result['path_correction_mm'], result['sensor_path_mm']))
    verdict = 'PASS' if (result['path_ratio'] and
                         abs(result['path_ratio'] - 1.0) <= args.tolerance) else 'CHECK'
    print('verdict {} (tolerance {:.1%})'.format(verdict, args.tolerance))
    if args.output:
        payload = dict(result)
        payload['tolerance'] = args.tolerance
        payload['verdict'] = verdict
        Path(args.output).write_text(json.dumps(payload, indent=2) + '\n')
        print('saved   {}'.format(args.output))


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('frame', help='extract one frame for calibration')
    p.add_argument('--video', required=True)
    p.add_argument('--time', type=float, default=0.0,
                   help='seconds into the video (default 0)')
    p.add_argument('--width', type=int, default=DEFAULT_WIDTH)
    p.add_argument('--output', required=True)
    p.set_defaults(func=command_frame)

    p = sub.add_parser('calibrate', help='click four tile intersections')
    p.add_argument('--frame', required=True)
    p.add_argument('--width', type=int, default=None,
                   help='resize the frame before clicking (default: native)')
    p.add_argument('--span', nargs=2, type=int, default=(6, 4),
                   metavar=('ACROSS', 'DOWN'), dest='span_xy')
    p.add_argument('--tile-mm', type=float, default=DEFAULT_TILE_MM)
    p.add_argument('--points', default=None,
                   help='skip the GUI: x1 y1 x2 y2 x3 y3 x4 y4')
    p.add_argument('--output', required=True)
    p.set_defaults(func=command_calibrate)

    p = sub.add_parser('check', help='draw the grid on a frame')
    p.add_argument('--frame', required=True)
    p.add_argument('--grid', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(func=command_check)

    p = sub.add_parser('swatch', help='report visible marker colours')
    p.add_argument('--frame', required=True)
    p.add_argument('--roi', default=None, help='x0,y0,x1,y1')
    p.add_argument('--min-area', type=int, default=20)
    p.add_argument('--max-area', type=int, default=None)
    p.set_defaults(func=command_swatch)

    p = sub.add_parser('track', help='follow the two markers')
    p.add_argument('--video', required=True)
    p.add_argument('--grid', required=True)
    p.add_argument('--front', default='red')
    p.add_argument('--rear', default='green')
    p.add_argument('--fps', type=float, default=10.0)
    p.add_argument('--width', type=int, default=None)
    p.add_argument('--roi', default=None, help='x0,y0,x1,y1 in frame pixels')
    p.add_argument('--min-area', type=int, default=20)
    p.add_argument('--max-area', type=int, default=None)
    p.add_argument('--max-frames', type=int, default=None)
    p.add_argument('--debug', default=None,
                   help='write annotated frames; use {index} in the name')
    p.add_argument('--debug-every', type=int, default=30)
    p.add_argument('--output', required=True)
    p.set_defaults(func=command_track)

    p = sub.add_parser('legs', help='stop-to-stop distances from a track')
    p.add_argument('--track', required=True)
    p.add_argument('--tile-mm', type=float, default=DEFAULT_TILE_MM)
    p.add_argument('--speed-threshold', type=float, default=40.0,
                   help='speed below this counts as stopped (mm/s)')
    p.add_argument('--min-stop', type=float, default=0.4,
                   help='shortest stop that becomes a station (s)')
    p.add_argument('--expected-tiles', type=float, default=None,
                   help='intended tiles per leg, for a grid/intent ratio')
    p.add_argument('--output', default=None, help='write the legs as JSON')
    p.set_defaults(func=command_legs)

    p = sub.add_parser('compare', help='compare overhead and wheel odometry')
    p.add_argument('--track', required=True)
    p.add_argument('--sensors', required=True)
    p.add_argument('--sensor-start', type=float, default=None,
                   help='seconds to skip at the start of the sensor log')
    p.add_argument('--sensor-end', type=float, default=None)
    p.add_argument('--max-offset', type=float, default=20.0,
                   help='largest video/log time offset to search (s)')
    p.add_argument('--sample-dt', type=float, default=0.1)
    p.add_argument('--tolerance', type=float, default=0.01,
                   help='accepted absolute path-ratio error (default 1%%)')
    p.add_argument('--output', default=None, help='write the result as JSON')
    p.set_defaults(func=command_compare)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
