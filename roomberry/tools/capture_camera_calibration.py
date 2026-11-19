#!/usr/bin/env python3
# @(#)capture_camera_calibration.py 3.2.calibration.1 2026/11/12 20:10:00
"""Interactive stationary Picamera2 captures; see docs/tile-camera-calibration.md."""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import time

POSE_FIELDS = ['x_tiles', 'y_tiles', 'z_mm', 'yaw_deg', 'pitch_deg', 'note']
FIELDS = ['image', 'captured_utc', *POSE_FIELDS, 'x_mm', 'y_mm',
          'tile_pitch_mm', 'width', 'height', 'exposure_us', 'analogue_gain']


def parse_pose(line):
    values = next(csv.reader([line]))
    if len(values) != len(POSE_FIELDS):
        raise ValueError('Enter six CSV fields: x_tiles,y_tiles,z_mm,yaw_deg,pitch_deg,note')
    result = dict(zip(POSE_FIELDS, values))
    for key in POSE_FIELDS[:-1]:
        result[key] = float(result[key])
        if not math.isfinite(result[key]):
            raise ValueError('Coordinates and angles must be finite')
    if result['x_tiles'] <= 0 or result['z_mm'] <= 0:
        raise ValueError('Lens distance x and height z must be positive')
    return result


def save_capture(camera, folder, pose, tile_pitch, grayscale):
    from PIL import Image, PngImagePlugin
    request = camera.capture_request()
    try:
        array = request.make_array('main').copy()
        metadata = request.get_metadata()
    finally:
        request.release()
    now = datetime.now(timezone.utc)
    stem = now.strftime('%Y%m%dT%H%M%S%fZ')
    # Picamera2 BGR888 arrays have RGB byte order, as in Roomberry's pipeline.
    image = Image.fromarray(array).convert('RGB')
    width, height = image.size
    row = dict(image=stem + '.png', captured_utc=now.isoformat(), **pose,
               x_mm=pose['x_tiles'] * tile_pitch, y_mm=pose['y_tiles'] * tile_pitch,
               tile_pitch_mm=tile_pitch, width=width, height=height,
               exposure_us=metadata.get('ExposureTime', ''),
               analogue_gain=metadata.get('AnalogueGain', ''))
    record = dict(schema_version=1, coordinates='lens; x away from board plane; y left when facing board; z above floor; yaw positive left from facing board; pitch positive up',
                  capture=row, camera_metadata=metadata,
                  camera_configuration=camera.camera_configuration())
    encoded = json.dumps(record, indent=2, default=str, allow_nan=False)
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text('RoomberryCalibration', encoded)
    # Exclusive creation prevents accidental replacement of an existing image.
    with (folder / row['image']).open('xb') as stream:
        image.save(stream, format='PNG', pnginfo=png_info)
    (folder / (stem + '.json')).write_text(encoded + '\n')
    if grayscale:
        image.convert('L').save(folder / (stem + '-gray.png'))
    csv_path = folder / 'captures.csv'
    exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open('a', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('camera-calibration'))
    parser.add_argument('--tile-mm', type=float, default=304.8)
    parser.add_argument('--gray', action='store_true', help='Also save a grayscale PNG')
    parser.add_argument('--plan', type=Path, help='CSV with header: ' + ','.join(POSE_FIELDS))
    parser.add_argument('--settle', type=float, default=2.0)
    args = parser.parse_args()
    if not math.isfinite(args.tile_mm) or args.tile_mm <= 0:
        parser.error('--tile-mm must be positive and finite')
    if not math.isfinite(args.settle) or args.settle < 0:
        parser.error('--settle must be nonnegative and finite')
    plan = None
    if args.plan:
        with args.plan.open(newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != POSE_FIELDS:
                parser.error('--plan header must be ' + ','.join(POSE_FIELDS))
            plan = []
            for row in reader:
                buffer = io.StringIO()
                csv.writer(buffer).writerow([row[k] for k in POSE_FIELDS])
                plan.append(parse_pose(buffer.getvalue()))
    from picamera2 import Picamera2
    args.output.mkdir(parents=True, exist_ok=True)
    camera = Picamera2()
    try:
        camera.configure(camera.create_still_configuration(
            main={'size': (820, 616), 'format': 'BGR888'}, queue=False))
        camera.start()
        time.sleep(2)
        print('Stationary capture only. This script does not move Rosie.')
        print('Enter x_tiles,y_tiles,z_mm,yaw_deg,pitch_deg,note; q quits.')
        index = 0
        while True:
            if plan is not None:
                if index >= len(plan):
                    break
                pose = plan[index]
                if input(f'Place lens at {pose}. Enter to capture; q quits: ').strip().lower() == 'q':
                    break
            else:
                line = input('pose> ').strip()
                if line.lower() == 'q':
                    break
                try:
                    pose = parse_pose(line)
                except (ValueError, csv.Error) as error:
                    print(error)
                    continue
            time.sleep(args.settle)
            row = save_capture(camera, args.output, pose, args.tile_mm, args.gray)
            print(f"Saved {row['image']} ({row['width']}x{row['height']})")
            index += 1
    finally:
        camera.close()


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nCapture ended.')
