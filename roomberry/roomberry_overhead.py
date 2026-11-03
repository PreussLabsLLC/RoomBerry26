"""Offline overhead-camera tracking against the kitchen's 1-foot tile grid.

The phone is stationary above the run and records 4K video. Four tile-grid
intersections define a homography from image pixels to floor millimetres; two
coloured markers on the robot give its position and heading. The result is an
independent ground-truth track that can be compared with wheel odometry.

This module deliberately depends only on numpy and Pillow. Video decoding is
delegated to the ``ffmpeg`` command so it works without OpenCV.
"""
# @(#)roomberry_overhead.py 3.1.overhead.1 2026/11/02 18:00:00

from __future__ import annotations

import json
import math
import subprocess
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

DEFAULT_TILE_MM = 304.8
DEFAULT_WIDTH = 960
DEFAULT_FPS = 10.0

# Hue ranges are in Pillow's 0..255 HSV scale. Red wraps around zero.
MARKER_PRESETS = {
    'red': {'hue': ((0, 18), (235, 255)), 'sat': 120, 'val': 70},
    'green': {'hue': ((45, 125),), 'sat': 100, 'val': 60},
    'blue': {'hue': ((130, 185),), 'sat': 110, 'val': 60},
    'magenta': {'hue': ((195, 240),), 'sat': 110, 'val': 60},
    'cyan': {'hue': ((120, 175),), 'sat': 110, 'val': 60},
    'yellow': {'hue': ((22, 50),), 'sat': 120, 'val': 80},
    'orange': {'hue': ((10, 32),), 'sat': 130, 'val': 90},
}


def _normalise(points):
    """Hartley-normalise a point set for a stable DLT solve."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 4:
        raise ValueError('a homography needs at least four point pairs')
    centroid = pts.mean(axis=0)
    shifted = pts - centroid
    mean_distance = float(np.hypot(shifted[:, 0], shifted[:, 1]).mean())
    scale = math.sqrt(2.0) / mean_distance if mean_distance > 1e-12 else 1.0
    transform = np.array([
        [scale, 0.0, -scale * centroid[0]],
        [0.0, scale, -scale * centroid[1]],
        [0.0, 0.0, 1.0],
    ])
    return transform, shifted * scale


def homography_from_points(source, destination):
    """Return the 3x3 homography mapping source pixels to destination points."""
    source = np.asarray(source, dtype=float).reshape(-1, 2)
    destination = np.asarray(destination, dtype=float).reshape(-1, 2)
    if len(source) != len(destination):
        raise ValueError('source and destination must have the same length')
    if len(source) < 4:
        raise ValueError('a homography needs at least four point pairs')

    source_t, source_n = _normalise(source)
    destination_t, destination_n = _normalise(destination)

    rows = []
    for (x, y), (u, v) in zip(source_n, destination_n):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    matrix = np.asarray(rows, dtype=float)
    if np.linalg.matrix_rank(matrix) < 8:
        raise ValueError('point pairs are degenerate; choose four distinct intersections')
    _, _, vt = np.linalg.svd(matrix)
    normalised = vt[-1].reshape(3, 3)
    if abs(normalised[2, 2]) < 1e-15:
        raise ValueError('degenerate homography')
    normalised /= normalised[2, 2]
    result = np.linalg.inv(destination_t) @ normalised @ source_t
    if abs(result[2, 2]) < 1e-15:
        raise ValueError('degenerate homography')
    return result / result[2, 2]


def apply_homography(transform, points):
    """Map one or more (x, y) points through a 3x3 homography."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    homogeneous = np.column_stack((pts, np.ones(len(pts))))
    mapped = homogeneous @ np.asarray(transform, dtype=float).T
    denominator = mapped[:, 2]
    if np.any(np.abs(denominator) < 1e-12):
        raise ValueError('point maps to infinity')
    return mapped[:, :2] / denominator[:, None]


def reprojection_rms(transform, source, destination):
    """Root-mean-square error of a homography on its calibration points."""
    mapped = apply_homography(transform, source)
    target = np.asarray(destination, dtype=float).reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum((mapped - target) ** 2, axis=1))))


def grid_homography(points, span, tile_mm=DEFAULT_TILE_MM, origin=(0.0, 0.0)):
    """Build a pixel-to-floor homography from four tile intersections.

    ``points`` are the pixel coordinates of four intersections in clockwise
    order from the top-left corner of the chosen rectangle. ``span`` is the
    number of tiles across and down. Floor +X follows the first edge and +Y
    points away from the image bottom, so the mapped corners are::

        (0, 0), (nx*pitch, 0), (nx*pitch, -ny*pitch), (0, -ny*pitch)

    The origin is the top-left intersection.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) != 4:
        raise ValueError('grid_homography needs exactly four intersections')
    across, down = (int(span[0]), int(span[1]))
    if across <= 0 or down <= 0:
        raise ValueError('span must be positive in both directions')
    pitch = float(tile_mm)
    ox, oy = float(origin[0]), float(origin[1])
    destination = np.array([
        [ox, oy],
        [ox + across * pitch, oy],
        [ox + across * pitch, oy - down * pitch],
        [ox, oy - down * pitch],
    ])
    return homography_from_points(pts, destination)


def color_mask(image, preset, saturation=None, value=None):
    """Return a boolean mask for one of the named high-contrast colours."""
    if preset not in MARKER_PRESETS:
        raise ValueError('unknown colour preset: {}'.format(preset))
    spec = MARKER_PRESETS[preset]
    hsv = np.asarray(image.convert('HSV'))
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    selected = np.zeros(hue.shape, dtype=bool)
    for low, high in spec['hue']:
        selected |= (hue >= low) & (hue <= high)
    minimum_sat = spec['sat'] if saturation is None else int(saturation)
    minimum_val = spec['val'] if value is None else int(value)
    return selected & (sat >= minimum_sat) & (val >= minimum_val)


def connected_components(mask):
    """Label runs in a boolean mask; return area, centroid and bounding box.

    Row-run union-find keeps this fast enough for a 960x540 frame without
    scipy or OpenCV. Results are sorted by descending area.
    """
    mask = np.asarray(mask, dtype=bool)
    height, width = mask.shape
    parent = []
    areas = []
    sum_x = []
    sum_y = []
    min_x = []
    max_x = []
    min_y = []
    max_y = []

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first, second):
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    previous = []
    for y in range(height):
        row = mask[y]
        if not row.any():
            previous = []
            continue
        edges = np.diff(row.astype(np.int8))
        starts = list(np.flatnonzero(edges == 1) + 1)
        ends = list(np.flatnonzero(edges == -1) + 1)
        if row[0]:
            starts.insert(0, 0)
        if row[-1]:
            ends.append(width)
        current = []
        for x0, x1 in zip(starts, ends):
            index = len(parent)
            parent.append(index)
            count = x1 - x0
            areas.append(count)
            sum_x.append((x0 + x1 - 1) * count / 2.0)
            sum_y.append(y * count)
            min_x.append(x0)
            max_x.append(x1 - 1)
            min_y.append(y)
            max_y.append(y)
            current.append((x0, x1, index))
        i = j = 0
        while i < len(previous) and j < len(current):
            p0, p1, pi = previous[i]
            c0, c1, ci = current[j]
            if p1 <= c0:
                i += 1
            elif c1 <= p0:
                j += 1
            else:
                union(pi, ci)
                if p1 < c1:
                    i += 1
                else:
                    j += 1
        previous = current

    totals = {}
    for index in range(len(parent)):
        root = find(index)
        area = totals.get(root)
        if area is None:
            totals[root] = [areas[index], sum_x[index], sum_y[index],
                            min_x[index], max_x[index], min_y[index], max_y[index]]
        else:
            area[0] += areas[index]
            area[1] += sum_x[index]
            area[2] += sum_y[index]
            area[3] = min(area[3], min_x[index])
            area[4] = max(area[4], max_x[index])
            area[5] = min(area[5], min_y[index])
            area[6] = max(area[6], max_y[index])

    blobs = []
    for area, sx, sy, x0, x1, y0, y1 in totals.values():
        blobs.append({
            'area': int(area),
            'cx': sx / area,
            'cy': sy / area,
            'bbox': (int(x0), int(y0), int(x1), int(y1)),
        })
    blobs.sort(key=lambda blob: blob['area'], reverse=True)
    return blobs


def detect_marker(image, preset, roi=None, min_area=20, max_area=None,
                  saturation=None, value=None):
    """Return the largest matching colour blob in the requested region."""
    x0 = y0 = 0
    working = image
    if roi is not None:
        x0, y0, x1, y1 = (int(v) for v in roi)
        if x1 <= x0 or y1 <= y0:
            raise ValueError('invalid ROI')
        working = image.crop((x0, y0, x1, y1))
    blobs = connected_components(color_mask(working, preset, saturation, value))
    for blob in blobs:
        if blob['area'] < min_area:
            continue
        if max_area is not None and blob['area'] > max_area:
            continue
        return {
            'px': (blob['cx'] + x0, blob['cy'] + y0),
            'area': blob['area'],
            'bbox': (blob['bbox'][0] + x0, blob['bbox'][1] + y0,
                     blob['bbox'][2] + x0, blob['bbox'][3] + y0),
        }
    return None


def marker_pose(image, transform, front_preset='red', rear_preset='green',
                roi=None, min_area=20, max_area=None, baseline_mm=None):
    """Locate the two markers and return a floor pose.

    The front marker defines +heading relative to the rear marker. The reported
    position is the midpoint of the two floor points, which should be the
    robot's reference point. A missing marker still yields a position but no
    heading.
    """
    front = detect_marker(image, front_preset, roi, min_area, max_area)
    rear = detect_marker(image, rear_preset, roi, min_area, max_area)
    if front is None and rear is None:
        return None
    result = {
        'front_px': None if front is None else front['px'],
        'rear_px': None if rear is None else rear['px'],
        'front_area': 0 if front is None else front['area'],
        'rear_area': 0 if rear is None else rear['area'],
        'x_mm': None,
        'y_mm': None,
        'heading_rad': None,
        'baseline_mm': None,
    }
    points = []
    labels = []
    if front is not None:
        points.append(front['px'])
        labels.append('front')
    if rear is not None:
        points.append(rear['px'])
        labels.append('rear')
    floor = apply_homography(transform, points)
    by_label = dict(zip(labels, floor))
    if 'front' in by_label and 'rear' in by_label:
        fx, fy = by_label['front']
        rx, ry = by_label['rear']
        result['x_mm'] = (fx + rx) / 2.0
        result['y_mm'] = (fy + ry) / 2.0
        result['heading_rad'] = math.atan2(fy - ry, fx - rx)
        result['baseline_mm'] = math.hypot(fx - rx, fy - ry)
    elif 'front' in by_label:
        result['x_mm'], result['y_mm'] = by_label['front']
    else:
        result['x_mm'], result['y_mm'] = by_label['rear']
    if baseline_mm is not None and result['baseline_mm'] is not None:
        result['baseline_error_mm'] = result['baseline_mm'] - float(baseline_mm)
    return result


def probe_video(path):
    """Read basic video metadata with ffprobe."""
    command = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries',
        'stream=width,height,avg_frame_rate,duration:format=duration,size:format_tags=creation_time',
        '-of', 'json', str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError('ffprobe failed: {}'.format(completed.stderr.strip()))
    payload = json.loads(completed.stdout or '{}')
    stream = (payload.get('streams') or [{}])[0]
    container = payload.get('format') or {}
    rate = stream.get('avg_frame_rate') or '0/1'
    try:
        numerator, denominator = rate.split('/')
        fps = float(numerator) / float(denominator) if float(denominator) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        'width': int(stream.get('width') or 0),
        'height': int(stream.get('height') or 0),
        'fps': fps,
        'duration_s': float(stream.get('duration') or container.get('duration') or 0.0),
        'creation_time': container.get('creation_time'),
        'size_bytes': int(container.get('size') or 0),
    }


def reference_frame(video, time_s=0.0, width=DEFAULT_WIDTH):
    """Extract one frame, scaled to ``width``, with ffmpeg autorotation."""
    command = [
        'ffmpeg', '-v', 'error', '-ss', '{:.3f}'.format(max(0.0, float(time_s))),
        '-i', str(video), '-frames:v', '1',
        '-vf', 'scale={}:-2'.format(int(width)),
        '-f', 'image2pipe', '-vcodec', 'png', '-',
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError('ffmpeg could not extract a frame: {}'.format(
            completed.stderr.decode('utf-8', 'replace').strip()))
    return Image.open(BytesIO(completed.stdout)).convert('RGB')


def iter_frames(video, fps=DEFAULT_FPS, width=DEFAULT_WIDTH, start=0.0, end=None):
    """Yield ``(index, time_s, RGB numpy array)`` from a video.

    Frames are decoded by ffmpeg, scaled so the width is ``width``, and read
    through a pipe so 4K recordings do not fill the disk with PNGs.
    """
    fps = float(fps)
    if fps <= 0:
        raise ValueError('fps must be positive')
    start = max(0.0, float(start or 0.0))
    probe = probe_video(video)
    duration = probe['duration_s']
    if end is None:
        end = duration
    duration = max(0.0, min(float(end), duration) - start) if duration else None

    # Measure the output size once so raw frames can be reshaped.
    sample = reference_frame(video, start, width)
    frame_width, frame_height = sample.size
    command = [
        'ffmpeg', '-v', 'error', '-ss', '{:.3f}'.format(start),
        '-i', str(video),
    ]
    if duration is not None:
        command += ['-t', '{:.3f}'.format(duration)]
    command += [
        '-vf', 'fps={:.6f},scale={}:-2'.format(fps, int(width)),
        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-',
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=frame_width * frame_height * 3)
    frame_bytes = frame_width * frame_height * 3
    index = 0
    try:
        while True:
            payload = process.stdout.read(frame_bytes)
            if len(payload) < frame_bytes:
                break
            frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                frame_height, frame_width, 3)
            yield index, start + index / fps, frame
            index += 1
    finally:
        process.stdout.close()
        error = process.stderr.read().decode('utf-8', 'replace')
        process.stderr.close()
        process.wait()
        if process.returncode not in (0, None) and index == 0:
            raise RuntimeError('ffmpeg failed to decode frames: {}'.format(error.strip()))


def _track_arrays(rows):
    """Sort tracked rows by time and return time and position arrays."""
    ordered = sorted(rows, key=lambda row: row['time_s'])
    times = np.array([row['time_s'] for row in ordered], dtype=float)
    points = np.array([[row['x_mm'], row['y_mm']] for row in ordered], dtype=float)
    return ordered, times, points


def track_legs(rows, tile_mm=DEFAULT_TILE_MM, speed_threshold=40.0,
               min_stop_s=0.4):
    """Split a track into stop-to-stop legs.

    Every sustained stop is a station. The displacement between consecutive
    station positions is one leg, which is what a one-tile-per-stop calibration
    run produces. Brief speed dips shorter than ``min_stop_s`` do not create a
    station, so noise in the tracker does not split a leg.
    """
    ordered, times, points = _track_arrays(rows)
    if len(times) < 4:
        return []
    dt = np.diff(times)
    valid = dt > 1e-6
    if valid.sum() < 3:
        return []
    step = np.hypot(np.diff(points[:, 0]), np.diff(points[:, 1]))
    speed = np.divide(step, dt, out=np.zeros_like(step), where=valid)

    stopped = speed <= float(speed_threshold)
    windows = []
    start = None
    for index, flag in enumerate(stopped):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            windows.append((start, index - 1))
            start = None
    if start is not None:
        windows.append((start, len(stopped) - 1))

    stations = []
    for first, last in windows:
        begin = times[first]
        finish = times[last + 1]
        duration = finish - begin
        touches_edge = first == 0 or last == len(stopped) - 1
        if duration < float(min_stop_s) and not touches_edge:
            continue
        inside = (times >= begin) & (times <= finish)
        if not inside.any():
            continue
        position = np.median(points[inside], axis=0)
        stations.append({'arrive_s': float(begin), 'depart_s': float(finish),
                         'x_mm': float(position[0]),
                         'y_mm': float(position[1]),
                         'duration_s': float(duration)})

    legs = []
    for index in range(1, len(stations)):
        before = stations[index - 1]
        after = stations[index]
        start_s = before['depart_s']
        end_s = after['arrive_s']
        mask = (times >= start_s) & (times <= end_s)
        path = float(np.hypot(np.diff(points[mask, 0]),
                              np.diff(points[mask, 1])).sum()) if mask.sum() > 1 else 0.0
        dx = after['x_mm'] - before['x_mm']
        dy = after['y_mm'] - before['y_mm']
        distance = float(math.hypot(dx, dy))
        duration = max(0.0, end_s - start_s)
        legs.append({
            'index': index,
            'start_s': start_s,
            'end_s': end_s,
            'duration_s': duration,
            'x_mm': before['x_mm'],
            'y_mm': before['y_mm'],
            'dx_mm': dx,
            'dy_mm': dy,
            'distance_mm': distance,
            'path_mm': path,
            'tiles': distance / float(tile_mm) if tile_mm else None,
            'mean_speed_mm_s': distance / duration if duration > 1e-6 else None,
        })
    return legs


def load_track(path):
    """Read a track CSV written by ``write_track_csv``."""
    return _read_track_csv(path)


def write_json(path, payload):
    """Write a JSON report with sorted keys."""
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def load_homography(path):
    """Load a JSON calibration saved by the CLI."""
    payload = json.loads(Path(path).read_text())
    transform = np.asarray(payload['homography'], dtype=float)
    if transform.shape != (3, 3):
        raise ValueError('homography must be a 3x3 matrix')
    return transform, payload


def save_homography(path, transform, metadata=None):
    """Write a homography and its metadata for later tracking runs."""
    payload = dict(metadata or {})
    payload['homography'] = np.asarray(transform, dtype=float).tolist()
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def _track_rows(video, transform, metadata, front, rear, fps, width,
                roi, min_area, max_area, max_frames, debug_path, debug_every):
    rows = []
    missed = 0
    solved = 0
    debug_written = 0
    expected_width = metadata.get('frame_width')
    if expected_width is not None and int(expected_width) != int(width):
        raise ValueError(
            'homography was calibrated at width {} but tracking at width {}'.format(
                expected_width, width))
    for index, time_s, frame in iter_frames(video, fps=fps, width=width):
        if max_frames is not None and index >= int(max_frames):
            break
        image = Image.fromarray(frame)
        pose = marker_pose(image, transform, front, rear, roi, min_area, max_area)
        if pose is None or pose['x_mm'] is None:
            missed += 1
            rows.append({'frame': index, 'time_s': time_s})
        else:
            solved += 1
            rows.append({
                'frame': index,
                'time_s': time_s,
                'x_mm': pose['x_mm'],
                'y_mm': pose['y_mm'],
                'heading_rad': pose['heading_rad'],
                'baseline_mm': pose['baseline_mm'],
                'front_x': None if pose['front_px'] is None else pose['front_px'][0],
                'front_y': None if pose['front_px'] is None else pose['front_px'][1],
                'rear_x': None if pose['rear_px'] is None else pose['rear_px'][0],
                'rear_y': None if pose['rear_px'] is None else pose['rear_px'][1],
            })
        if debug_path is not None and index % max(1, int(debug_every)) == 0:
            debug = image.copy()
            draw = ImageDraw.Draw(debug)
            for key, colour in (('front_px', (255, 0, 0)), ('rear_px', (0, 200, 0))):
                point = pose.get(key) if pose else None
                if point is not None:
                    draw.ellipse((point[0] - 8, point[1] - 8,
                                  point[0] + 8, point[1] + 8), outline=colour, width=3)
            if pose and pose['x_mm'] is not None:
                draw.text((8, 8), 'x={:.0f} y={:.0f} mm h={:.1f} deg'.format(
                    pose['x_mm'], pose['y_mm'],
                    math.degrees(pose['heading_rad'] or 0.0)), fill=(255, 255, 255))
            debug.save(str(debug_path).format(index=index))
            debug_written += 1
    return rows, {'frames': len(rows), 'solved': solved, 'missed': missed,
                  'debug_frames': debug_written}


def write_track_csv(path, rows):
    """Write tracked poses in a spreadsheet-friendly form."""
    fields = ['frame', 'time_s', 'x_mm', 'y_mm', 'heading_rad', 'baseline_mm',
              'front_x', 'front_y', 'rear_x', 'rear_y']
    with Path(path).open('w', newline='') as handle:
        import csv
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ('' if row.get(key) is None else row.get(key))
                             for key in fields})


def track_video(video, transform, metadata, front='red', rear='green',
                fps=DEFAULT_FPS, width=DEFAULT_WIDTH, roi=None, min_area=20,
                max_area=None, output_csv=None, max_frames=None,
                debug_path=None, debug_every=30):
    """Track the two markers through a video and optionally write a CSV."""
    rows, summary = _track_rows(
        video, transform, metadata, front, rear, fps, width, roi, min_area,
        max_area, max_frames, debug_path, debug_every)
    if output_csv is not None:
        write_track_csv(output_csv, rows)
    return rows, summary


def _read_track_csv(path):
    import csv
    rows = []
    with Path(path).open(newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                time_s = float(row['time_s'])
            except (KeyError, ValueError):
                continue
            try:
                x = float(row['x_mm'])
                y = float(row['y_mm'])
            except (KeyError, ValueError):
                continue
            rows.append({'time_s': time_s, 'x_mm': x, 'y_mm': y})
    return rows


def _read_sensor_csv(path, start=None, end=None):
    import csv
    rows = []
    with Path(path).open(newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                time_s = float(row['elapsed_s'])
            except (KeyError, ValueError):
                continue
            if start is not None and time_s < start:
                continue
            if end is not None and time_s > end:
                continue
            try:
                travelled = float(row['travelled_distance_mm'])
            except (KeyError, ValueError):
                continue
            try:
                signed = float(row['distance_mm'])
            except (KeyError, ValueError):
                signed = None
            rows.append({'time_s': time_s, 'travelled_mm': travelled,
                         'signed_mm': signed})
    rows.sort(key=lambda item: item['time_s'])
    return rows


def _speed_profile(times, positions, sample_dt=0.1, smooth_s=0.5):
    times = np.asarray(times, dtype=float)
    positions = np.asarray(positions, dtype=float)
    if len(times) < 2:
        return np.array([]), np.array([])
    dt = np.diff(times)
    valid = dt > 1e-6
    if not valid.any():
        return np.array([]), np.array([])
    step = np.hypot(np.diff(positions[:, 0]), np.diff(positions[:, 1]))
    speed = np.divide(step, dt, out=np.zeros_like(step), where=valid)
    mid = (times[:-1] + times[1:]) / 2.0
    # Resample to a uniform grid so two recordings can be correlated.
    grid = np.arange(mid[0], mid[-1] + sample_dt, sample_dt)
    if len(grid) < 2:
        return np.array([]), np.array([])
    values = np.interp(grid, mid[valid], speed[valid])
    window = max(1, int(round(smooth_s / sample_dt)))
    if window > 1:
        kernel = np.ones(window) / window
        values = np.convolve(values, kernel, mode='same')
    return grid, values


def _correlation(first, second):
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if len(first) < 3 or len(second) < 3:
        return 0.0
    first = first - first.mean()
    second = second - second.mean()
    denominator = float(np.sqrt((first ** 2).sum() * (second ** 2).sum()))
    if denominator < 1e-12:
        return 0.0
    return float((first * second).sum() / denominator)


def compare_tracks(track_csv, sensor_csv, sensor_start=None, sensor_end=None,
                   max_offset_s=20.0, sample_dt=0.1):
    """Align overhead and wheel tracks by their speed profiles and compare paths.

    The video has no shared clock with the Pi. Cross-correlating the speed
    profiles finds the time offset; the ratio of path lengths is the wheel
    scale correction (1.05 means odometry is 5 % short).
    """
    track = _read_track_csv(track_csv)
    sensors = _read_sensor_csv(sensor_csv, sensor_start, sensor_end)
    if len(track) < 3 or len(sensors) < 3:
        raise ValueError('need at least three valid samples in each track')

    track_t = np.array([row['time_s'] for row in track])
    track_p = np.array([[row['x_mm'], row['y_mm']] for row in track])
    sensor_t = np.array([row['time_s'] for row in sensors])
    sensor_p = np.array([[row['travelled_mm'], 0.0] for row in sensors])

    track_grid, track_speed = _speed_profile(track_t, track_p, sample_dt)
    sensor_grid, sensor_speed = _speed_profile(sensor_t, sensor_p, sample_dt)
    if len(track_grid) < 3 or len(sensor_grid) < 3:
        raise ValueError('not enough motion to align the tracks')

    best = None
    for offset in np.arange(-max_offset_s, max_offset_s + sample_dt / 2, sample_dt / 2):
        shifted = track_grid + offset
        mask = (shifted >= sensor_grid[0]) & (shifted <= sensor_grid[-1])
        if mask.sum() < 10:
            continue
        sensor_values = np.interp(shifted[mask], sensor_grid, sensor_speed)
        score = _correlation(track_speed[mask], sensor_values)
        if best is None or score > best['correlation']:
            best = {'offset_s': float(offset), 'correlation': float(score)}
    if best is None:
        raise ValueError('could not align the tracks; check the time windows')

    shifted = track_grid + best['offset_s']
    mask = (shifted >= sensor_grid[0]) & (shifted <= sensor_grid[-1])
    if mask.sum() < 2:
        raise ValueError('aligned tracks do not overlap')
    aligned_track_time = track_grid[mask]
    aligned_sensor_time = shifted[mask]

    # Path length over the overlapping window only.
    window = (track_t >= aligned_track_time[0]) & (track_t <= aligned_track_time[-1])
    window_t = track_t[window]
    window_p = track_p[window]
    if len(window_t) < 2:
        raise ValueError('aligned tracks do not overlap')
    track_path = float(np.hypot(np.diff(window_p[:, 0]),
                                np.diff(window_p[:, 1])).sum())

    # Cumulative travelled distance is a true positive path length; the signed
    # distance is reset by the Roomba and is only used for displacement.
    travelled = np.array([row['travelled_mm'] for row in sensors])
    sensor_path = float(np.interp(aligned_sensor_time[-1], sensor_t, travelled) -
                        np.interp(aligned_sensor_time[0], sensor_t, travelled))
    track_start = np.array([np.interp(aligned_track_time[0], track_t, track_p[:, 0]),
                            np.interp(aligned_track_time[0], track_t, track_p[:, 1])])
    track_end = np.array([np.interp(aligned_track_time[-1], track_t, track_p[:, 0]),
                          np.interp(aligned_track_time[-1], track_t, track_p[:, 1])])
    track_displacement = float(np.hypot(*(track_end - track_start)))
    signed_values = np.array([row['signed_mm'] if row['signed_mm'] is not None
                              else row['travelled_mm'] for row in sensors])
    sensor_displacement = float(abs(
        np.interp(aligned_sensor_time[-1], sensor_t, signed_values) -
        np.interp(aligned_sensor_time[0], sensor_t, signed_values)))

    return {
        'offset_s': best['offset_s'],
        'correlation': best['correlation'],
        'track_path_mm': track_path,
        'sensor_path_mm': sensor_path,
        'path_ratio': track_path / sensor_path if sensor_path > 1e-6 else None,
        'path_correction_mm': track_path - sensor_path,
        'track_displacement_mm': track_displacement,
        'sensor_displacement_mm': sensor_displacement,
        'displacement_ratio': (track_displacement / sensor_displacement
                               if sensor_displacement > 1e-6 else None),
        'track_samples': len(track),
        'sensor_samples': len(sensors),
        'aligned_samples': int(mask.sum()),
    }
