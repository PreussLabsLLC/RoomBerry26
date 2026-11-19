#!/usr/bin/env python3
# @(#)analyze_camera_calibration.py 3.2.calibration.3 2026/11/12 21:15:00
"""Fit uploaded 16h5 board captures without modifying measurements.

Requires numpy, opencv-contrib-python-headless. Coordinates in the original
x_tiles/y_tiles columns are explicitly interpreted as user-entered millimetres.
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np


def object_corners(tag):
    x = (tag % 4 - 1.5) * 66.801
    y = (tag // 4 - 1) * 67.31
    h = 41.91 / 2
    return np.array([[x-h, y-h, 0], [x+h, y-h, 0],
                     [x+h, y+h, 0], [x-h, y+h, 0]], np.float32)


def pose_result(view, matrix, distortion):
    ok, rotation, translation = cv2.solvePnP(view['object'], view['pixels'], matrix, distortion)
    if not ok:
        raise ValueError('Pose failed for ' + view['image'])
    R = cv2.Rodrigues(rotation)[0]
    centre = -R.T @ translation.reshape(3)
    forward = R.T[:, 2]
    projected = cv2.projectPoints(view['object'], rotation, translation, matrix, distortion)[0].reshape(-1, 2)
    error = np.linalg.norm(projected-view['pixels'], axis=1)
    # Match the user's observed coordinate signs: left station has negative y.
    return dict(x_mm=float(-centre[2]), y_mm=float(centre[0]),
                camera_height_relative_to_board_mm=float(-centre[1]),
                yaw_deg=float(np.degrees(np.arctan2(forward[0], forward[2]))),
                pitch_deg=float(np.degrees(np.arctan2(-forward[1], np.hypot(forward[0], forward[2])))),
                reprojection_rms_px=float(np.sqrt(np.mean(error**2))),
                reprojection_max_px=float(error.max()))


MODELS = {
    'pinhole': cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3,
    'radial1': cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3,
    'radial2': cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K3,
    'brown4': cv2.CALIB_FIX_K3,
}


def fit(views, model):
    return cv2.calibrateCameraExtended(
        [v['object'] for v in views], [v['pixels'] for v in views], (820, 616),
        None, None, flags=MODELS[model],
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-9))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('roomberry/tools/camera-calibration'))
    parser.add_argument('--output', type=Path, default=Path('output/camera-calibration-20261112'))
    parser.add_argument('--refinement', choices=['subpix', 'apriltag'], default='apriltag')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.input/'captures.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    normalized = [dict(image=r['image'], measured_x_mm=float(r['x_tiles']),
                       measured_y_mm=float(r['y_tiles']), measured_z_mm=float(r['z_mm']),
                       entered_yaw_deg=float(r['yaw_deg']), note=r['note'],
                       warning='possible 892-to-92 typo; not corrected' if float(r['x_tiles'])==92 else '') for r in rows]
    with (args.output/'normalized-measurements.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(normalized[0]))
        writer.writeheader(); writer.writerows(normalized)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = (cv2.aruco.CORNER_REFINE_APRILTAG if args.refinement == 'apriltag'
                                         else cv2.aruco.CORNER_REFINE_SUBPIX)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_16h5), parameters)
    cache_path = args.output/('detections-' + args.refinement + '.json')
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for row in rows:
        if row['image'] not in cache:
            gray = cv2.imread(str(args.input/row['image']), cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.shape != (616, 820):
                raise ValueError('Missing image or unexpected resolution: ' + row['image'])
            corners, ids, _ = detector.detectMarkers(gray)
            markers = [] if ids is None else [dict(id=int(i), corners=c.reshape(4, 2).tolist())
                       for c, i in zip(corners, ids.ravel()) if 0 <= i < 12]
            cache[row['image']] = markers
            print(row['image'], len(markers), 'tags', flush=True)
    cache_path.write_text(json.dumps(cache, indent=2)+'\n')
    # Regenerate evidence from the selected cache, including on repeated runs.
    for row in rows:
        markers = cache[row['image']]
        overlay = cv2.imread(str(args.input/row['image']))
        if markers:
            cv2.aruco.drawDetectedMarkers(overlay,
                [np.array(m['corners'], np.float32).reshape(1,4,2) for m in markers],
                np.array([[m['id']] for m in markers], np.int32))
        cv2.imwrite(str(args.output/(Path(row['image']).stem+'-corners.jpg')), overlay)
    views = []
    excluded = []
    for index, row in enumerate(rows):
        markers = cache[row['image']]
        if len(markers) < 3:
            excluded.append(dict(image=row['image'], tags=len(markers), note=row['note'],
                                 reason='fewer than three complete detected tags; no reliable board pose'))
            continue
        views.append(dict(image=row['image'], row=row, index=index,
                          object=np.concatenate([object_corners(m['id']) for m in markers]),
                          pixels=np.concatenate([np.array(m['corners'], np.float32) for m in markers])))
    # First image of each stationary pair; distant frames held out of lens fit.
    train = [v for v in views if v['index'] % 2 == 0 and
             (float(v['row']['x_tiles']) < 1500 or 'stool' in v['row']['note'])]
    train_images = {v['image'] for v in train}
    validation = [v for v in views if v['index'] % 2 == 0 and
                  float(v['row']['x_tiles']) >= 1500 and v['image'] not in train_images]
    # All orientations with the same measured lens position stay in one fold.
    def station(view):
        return tuple(float(view['row'][k]) for k in ('x_tiles', 'y_tiles', 'z_mm'))
    stations = list(dict.fromkeys(station(v) for v in train))
    assignments = {key: i % 3 for i, key in enumerate(stations)}
    models = {}
    for name in MODELS:
        result = fit(train, name)
        rms, K, D = result[:3]
        # Leave groups out rather than testing on near-identical paired frames.
        folds = []
        for fold in range(3):
            training = [v for v in train if assignments[station(v)] != fold]
            testing = [v for v in train if assignments[station(v)] == fold]
            fitted = fit(training, name)
            errors = [pose_result(v, fitted[1], fitted[2])['reprojection_rms_px'] for v in testing]
            folds.append(dict(matrix=fitted[1].tolist(), distortion=fitted[2].ravel().tolist(),
                              training_images=[v['image'] for v in training],
                              testing_images=[v['image'] for v in testing],
                              rms_px=float(np.sqrt(np.mean(np.square(errors))))))
        models[name] = dict(rms_px=float(rms), matrix=K.tolist(), distortion=D.ravel().tolist(),
                            intrinsic_stddev=result[5].ravel().tolist(), cross_validation=folds,
                            distant_validation=[dict(image=v['image'], **pose_result(v,K,D)) for v in validation])
        print(name, 'RMS', rms, 'K', K.tolist(), 'D', D.ravel().tolist(), flush=True)
    (args.output/'models.json').write_text(json.dumps(models, indent=2)+'\n')
    # Conservative radial2 candidate; retain all alternatives for review.
    chosen = 'radial2'
    K = np.array(models[chosen]['matrix']); D = np.array(models[chosen]['distortion'])
    corrected = []
    for view in views:
        row = view['row']
        p = pose_result(view,K,D)
        measured_x, measured_y = float(row['x_tiles']), float(row['y_tiles'])
        corrected.append(dict(image=view['image'], note=row['note'], tags=len(cache[view['image']]),
                    measured_x_mm=measured_x, measured_y_mm=measured_y,
                    measured_z_mm=float(row['z_mm']),
                    entered_yaw_deg=float(row['yaw_deg']), **p,
                    implied_board_centre_height_mm=float(row['z_mm'])-p['camera_height_relative_to_board_mm'],
                    delta_x_mm=p['x_mm']-measured_x, delta_y_mm=p['y_mm']-measured_y,
                    yaw_correction_deg=p['yaw_deg']-float(row['yaw_deg']),
                    quality=('stool pose; remeasure lens after tilting before metric validation' if 'stool' in row['note']
                             else 'long-range ambiguous; do not use as a survey correction' if measured_x>=1500
                             else 'partial single-row board; limited pose geometry' if len(cache[view['image']])<6
                             else 'usable candidate; nominal print geometry'),
                    coordinate_warning='possible 892-to-92 typo; preserved' if measured_x==92 else ''))
    with (args.output/'corrected-poses.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(corrected[0])); writer.writeheader(); writer.writerows(corrected)
    (args.output/'excluded-images.json').write_text(json.dumps(excluded,indent=2)+'\n')
    candidate = dict(status='offline candidate; not installed', model=chosen, image_size=[820,616],
                     matrix=K.tolist(), distortion=D.tolist(),
                     coordinate_convention='x away from board; y negative at user left stations; yaw signs match entered guesses',
                     assumptions=['nominal PDF geometry; print dimensions not independently measured',
                                  'board axes follow printed layout; fitted image roll is approximately 180 degrees',
                                  'x_tiles/y_tiles entries interpreted as millimetres; source preserved'],
                     training_images=[v['image'] for v in train])
    (args.output/'candidate-calibration.json').write_text(json.dumps(candidate,indent=2)+'\n')
    print('Wrote',args.output,flush=True)


if __name__ == '__main__':
    main()
