"""Fuse Create 2 incremental odometry with surveyed AprilTag landmarks."""
# @(#)roomberry_localization.py 2.3.16 2026/10/28 21:00:00

from math import atan2, cos, hypot, isfinite, sin, sqrt
from time import monotonic, time
import json
from pathlib import Path


class AprilTagLocalizer:
    """Maintain a planar robot pose from odometry and calibrated tag poses.

    ``landmarks`` maps ``(family, id)`` to a 4x4 ``world_from_tag`` transform.
    ``camera_from_robot`` is the calibrated 4x4 transform from robot-frame
    coordinates into camera-frame coordinates. AprilTag's ``tag_pose_camera``
    is interpreted as ``camera_from_tag``. Matrices are ordinary nested lists
    and translations use meters; the public pose is returned in millimeters.

    Tag estimates are filtered before they can move the pose. Hamming errors,
    weak decision margins, implausible range, high reprojection error, and
    jumps that disagree with the odometry-predicted pose are rejected. Multiple
    consistent tags are combined by quality-weighted translation and circular
    heading averages.
    """

    def __init__(self, landmarks, camera_from_robot,
                 max_localization_age=60.0, max_pose_jump_age=30.0,
                 min_decision_margin=10.0, max_reprojection_error=10.0,
                 min_tag_distance_m=0.08, max_tag_distance_m=8.0,
                 max_pose_jump_mm=500.0, max_heading_jump_rad=0.6,
                 consensus_distance_mm=250.0, consensus_heading_rad=0.35,
                 discover_unknown_tags=False, discovery_save_path=None,
                 room_bounds_mm=None, confirm_large_relocations=False):
        self.landmarks = {
            (str(family), int(tag_id)): self._validate_transform(transform)
            for (family, tag_id), transform in landmarks.items()
        }
        self.camera_from_robot = self._validate_transform(camera_from_robot)
        self.room_bounds_mm = room_bounds_mm
        self.confirm_large_relocations = bool(confirm_large_relocations)
        self.max_localization_age = float(max_localization_age)
        self.max_pose_jump_age = float(max_pose_jump_age)
        self.min_decision_margin = float(min_decision_margin)
        self.max_reprojection_error = float(max_reprojection_error)
        self.min_tag_distance_m = float(min_tag_distance_m)
        self.max_tag_distance_m = float(max_tag_distance_m)
        self.max_pose_jump_mm = float(max_pose_jump_mm)
        self.max_heading_jump_rad = float(max_heading_jump_rad)
        self.consensus_distance_mm = float(consensus_distance_mm)
        self.consensus_heading_rad = float(consensus_heading_rad)
        self.discover_unknown_tags = bool(discover_unknown_tags)
        self.discovery_save_path = Path(discovery_save_path) if discovery_save_path else None
        self._pending_relocation = None
        self._pose = None
        self._last_tag_time = None
        self._last_odometry = None
        self._last_odometry_epoch = None
        self._last_tag_ids = ()
        self._last_rejected = ()
        self._discovered_tags = {}
        self._discovered_tags_log = []

    def invalidate_pose(self):
        """A carried/restarted robot must reacquire a tag before global navigation."""
        self._pending_relocation = None
        self._pose = None
        self._last_tag_time = None
        self._last_tag_ids = ()
        self._last_rejected = ()
        self._last_odometry = None
        self._last_odometry_epoch = None

    def update(self, detections, distance_mm, angle_degrees, new_detections=True,
               detection_timestamp=None, odometry_epoch=None):
        """Integrate cumulative OI deltas; correct pose on fresh known tags."""
        distance_mm = float(distance_mm)
        angle_degrees = float(angle_degrees)
        epoch_changed = (self._last_odometry_epoch is not None and
                         odometry_epoch != self._last_odometry_epoch)
        if (not epoch_changed and self._last_odometry is not None and
                self._pose is not None):
            delta_distance = distance_mm - self._last_odometry[0]
            delta_angle = (angle_degrees - self._last_odometry[1]) * 3.141592653589793 / 180.0
            middle_heading = self._pose['heading_rad'] + delta_angle * 0.5
            self._pose['x_mm'] += delta_distance * cos(middle_heading)
            self._pose['y_mm'] += delta_distance * sin(middle_heading)
            self._pose['heading_rad'] = self._wrap(self._pose['heading_rad'] + delta_angle)
            if self._pending_relocation is not None:
                pending = self._pending_relocation
                heading = pending['heading_rad'] + delta_angle * .5
                pending['x_mm'] += delta_distance * cos(heading)
                pending['y_mm'] += delta_distance * sin(heading)
                pending['heading_rad'] = self._wrap(pending['heading_rad'] + delta_angle)
        self._last_odometry = (distance_mm, angle_degrees)
        self._last_odometry_epoch = odometry_epoch

        accepted = ()
        if new_detections:
            # Try to discover unknown tags
            if self.discover_unknown_tags and self._pose is not None and detections:
                for det in detections:
                    try:
                        key = (str(det.get('family', '')), int(det.get('id', -1)))
                        if key not in self.landmarks and key not in self._discovered_tags:
                            self._discover_unknown_tag(det, self._pose)
                    except Exception:
                        pass
            estimates, rejected = self._tag_pose_estimates(detections or ())
            estimates, rejected = self._consistent_estimates(estimates, rejected)
            self._last_rejected = tuple(rejected)
            if estimates:
                count = sum(item['weight'] for item in estimates)
                x_mm = sum(item['weight'] * item['x_mm'] for item in estimates) / count
                y_mm = sum(item['weight'] * item['y_mm'] for item in estimates) / count
                heading = atan2(
                    sum(item['weight'] * sin(item['heading_rad']) for item in estimates),
                    sum(item['weight'] * cos(item['heading_rad']) for item in estimates),
                )
                self._pending_relocation = None
                self._pose = {'x_mm': x_mm, 'y_mm': y_mm,
                              'heading_rad': self._wrap(heading)}
                processing_time = monotonic()
                capture_age = (0.0 if detection_timestamp is None else
                               max(0.0, time() - float(detection_timestamp)))
                self._last_tag_time = processing_time - capture_age
                self._last_tag_ids = tuple(item['key'] for item in estimates)
                accepted = self._last_tag_ids

        age = None if self._last_tag_time is None else monotonic() - self._last_tag_time
        localized = age is not None and age <= self.max_localization_age
        if self._pose is None:
            return None
        return dict(
            self._pose,
            localized=localized,
            localization_age=age,
            tag_ids=self._last_tag_ids,
            accepted_tag_ids=accepted,
            rejected_tags=self._last_rejected,
        )

    @property
    def last_rejected(self):
        """Return (tag key, reason) entries rejected by the most recent update."""
        return self._last_rejected

    def get_discovered_tags_log(self):
        return list(self._discovered_tags_log)

    def _save_discovered_tags(self):
        if self.discovery_save_path is None:
            return
        try:
            self.discovery_save_path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for key, info in self._discovered_tags.items():
                data.append({
                    'family': key[0],
                    'id': key[1],
                    'world_from_tag': info['world_from_tag'],
                    'observations': info.get('observations', 0),
                    'last_seen': info.get('last_seen'),
                })
            with self.discovery_save_path.open('w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def add_discovered_tag(self, family, tag_id, world_from_tag, pose=None):
        key = (str(family), int(tag_id))
        if key in self.landmarks or key in self._discovered_tags:
            return False
        self._discovered_tags[key] = {
            'world_from_tag': world_from_tag,
            'observations': 1,
            'last_seen': time(),
            'pose': pose,
        }
        self._save_discovered_tags()
        return True

    def _discover_unknown_tag(self, detection, robot_pose):
        if not self.discover_unknown_tags:
            return
        if robot_pose is None:
            return
        key = (str(detection.get('family', '')), int(detection.get('id', -1)))
        if key in self.landmarks or key in self._discovered_tags:
            return
        tag_pose = detection.get('tag_pose_camera')
        if tag_pose is None:
            return
        try:
            translation = [float(value) for value in tag_pose['translation_m']]
            if int(detection.get('hamming', 1)) != 0:
                return
            if float(detection.get('decision_margin', 0.0)) < self.min_decision_margin:
                return
            error = float(tag_pose.get('error', float('inf')))
            if not isfinite(error) or error > self.max_reprojection_error:
                return
            range_m = sqrt(sum(value * value for value in translation))
            if not self.min_tag_distance_m <= range_m <= self.max_tag_distance_m:
                return
            camera_from_tag = self._transform(tag_pose['rotation'], translation)
            # Compute world_from_tag from known robot pose
            # world_from_tag * inverse(camera_from_tag) * camera_from_robot^-1?
            # Or: world_from_tag = world_from_robot * inverse(camera_from_robot) * camera_from_tag
            world_from_camera = self._multiply(
                self._pose_matrix_from_pose(robot_pose), self.camera_from_robot
            )
            world_from_tag = self._multiply(world_from_camera, camera_from_tag)
            # Convert to meters for storage
            world_from_tag_m = [[float(v) for v in row] for row in world_from_tag]
            self._discovered_tags[key] = {
                'world_from_tag': world_from_tag_m,
                'observations': self._discovered_tags.get(key, {}).get('observations', 0) + 1,
                'last_seen': time(),
                'pose_at_discovery': dict(robot_pose),
            }
            self._save_discovered_tags()
        except Exception:
            pass

    def _pose_matrix_from_pose(self, pose):
        x = pose.get('x_mm', 0.0) / 1000.0
        y = pose.get('y_mm', 0.0) / 1000.0
        th = pose.get('heading_rad', 0.0)
        c = cos(th)
        s = sin(th)
        return [
            [c, -s, 0.0, x],
            [s, c, 0.0, y],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

    def _tag_pose_estimates(self, detections):
        estimates = []
        rejected = []
        for detection in detections:
            key = (str(detection.get('family', '')), int(detection.get('id', -1)))
            world_from_tag = self.landmarks.get(key)
            tag_pose = detection.get('tag_pose_camera')
            reason = None
            if world_from_tag is None:
                reason = 'unknown landmark'
            elif tag_pose is None:
                reason = 'missing camera pose'
            elif int(detection.get('hamming', 1)) != 0:
                reason = 'hamming={}'.format(detection.get('hamming'))
            elif float(detection.get('decision_margin', 0.0)) < self.min_decision_margin:
                reason = 'weak margin={:.1f}'.format(
                    float(detection.get('decision_margin', 0.0))
                )

            translation = None
            range_m = None
            error = None
            if reason is None:
                try:
                    translation = [float(value) for value in tag_pose['translation_m']]
                    range_m = sqrt(sum(value * value for value in translation))
                    error = float(tag_pose.get('error', float('inf')))
                except (KeyError, TypeError, ValueError):
                    reason = 'malformed camera pose'
                else:
                    if not all(isfinite(value) for value in translation):
                        reason = 'non-finite camera pose'
                    elif not isfinite(error) or error > self.max_reprojection_error:
                        reason = 'reprojection error={:.1f}'.format(error)
                    elif not self.min_tag_distance_m <= range_m <= self.max_tag_distance_m:
                        reason = 'implausible range={:.3f} m'.format(range_m)
            if reason is not None:
                rejected.append((key, reason))
                continue

            try:
                camera_from_tag = self._transform(tag_pose['rotation'], translation)
            except (KeyError, TypeError, ValueError):
                rejected.append((key, 'malformed camera rotation'))
                continue
            world_from_camera = self._multiply(
                world_from_tag, self._inverse(camera_from_tag),
            )
            world_from_robot = self._multiply(world_from_camera, self.camera_from_robot)
            if self.room_bounds_mm is not None:
                x, y = world_from_robot[0][3] * 1000, world_from_robot[1][3] * 1000
                xmin, ymin, xmax, ymax = self.room_bounds_mm
                if not (xmin <= x <= xmax and ymin <= y <= ymax):
                    rejected.append((key, 'outside room bounds'))
                    continue
                dx = world_from_tag[0][3] * 1000 - x
                dy = world_from_tag[1][3] * 1000 - y
                if dx * world_from_tag[0][2] + dy * world_from_tag[1][2] <= 0:
                    rejected.append((key, 'behind tag mounting plane'))
                    continue
            rotation = world_from_robot
            # Pose error is in squared pixels; tag range contributes a milder
            # uncertainty term because distant tags have less stable corners.
            weight = 1.0 / ((1.0 + error) * (1.0 + 0.1 * range_m))
            estimates.append({
                'x_mm': rotation[0][3] * 1000.0,
                'y_mm': rotation[1][3] * 1000.0,
                'heading_rad': atan2(rotation[1][0], rotation[0][0]),
                'key': key,
                'error': error,
                'range_m': range_m,
                'weight': weight,
            })
        return estimates, rejected

    def _consistent_estimates(self, estimates, rejected):
        """Reject jumps and outliers before they can move the fused pose."""
        if not estimates:
            return estimates, rejected
        candidates = estimates
        prior = self._pose
        prior_age = (None if self._last_tag_time is None or prior is None else
                     monotonic() - self._last_tag_time)
        # Only trust the odometry prediction as a jump reference for a short
        # window. After that, drift can exceed the allowed jump and otherwise
        # reject every correction, leaving the pose stale until it expires.
        if prior_age is not None and prior_age <= self.max_pose_jump_age:
            filtered = []
            for estimate in candidates:
                distance = hypot(
                    estimate['x_mm'] - prior['x_mm'],
                    estimate['y_mm'] - prior['y_mm'],
                )
                heading = abs(self._wrap(
                    estimate['heading_rad'] - prior['heading_rad']
                ))
                if (distance > self.max_pose_jump_mm or
                        heading > self.max_heading_jump_rad):
                    rejected.append((
                        estimate['key'],
                        'jump {:.0f} mm / {:.2f} rad from predicted pose'.format(
                            distance, heading,
                        ),
                    ))
                else:
                    filtered.append(estimate)
            candidates = filtered
        if (self.confirm_large_relocations and prior_age is not None and
                prior_age > self.max_pose_jump_age and candidates):
            reference = max(candidates, key=lambda item: item['weight'])
            large = (hypot(reference['x_mm'] - prior['x_mm'],
                           reference['y_mm'] - prior['y_mm']) > self.max_pose_jump_mm or
                     abs(self._wrap(reference['heading_rad'] - prior['heading_rad'])) > self.max_heading_jump_rad)
            if large:
                pending = self._pending_relocation
                confirmed = (pending is not None and monotonic() - pending['time'] < 90 and
                    hypot(reference['x_mm'] - pending['x_mm'],
                          reference['y_mm'] - pending['y_mm']) <= self.consensus_distance_mm and
                    abs(self._wrap(reference['heading_rad'] - pending['heading_rad'])) <= self.consensus_heading_rad)
                if not confirmed:
                    self._pending_relocation = dict(reference, time=monotonic())
                    rejected.extend((item['key'], 'large relocation needs another consistent scan')
                                    for item in candidates)
                    return [], rejected
            self._pending_relocation = None
        if len(candidates) <= 1:
            return candidates, rejected

        # Pick the largest agreeing group rather than the single best tag. A
        # plausible-looking outlier must not discard several tags that agree.
        best_cluster = []
        best_score = None
        for reference in candidates:
            cluster = []
            for estimate in candidates:
                distance = hypot(
                    estimate['x_mm'] - reference['x_mm'],
                    estimate['y_mm'] - reference['y_mm'],
                )
                heading = abs(self._wrap(
                    estimate['heading_rad'] - reference['heading_rad']
                ))
                if (distance <= self.consensus_distance_mm and
                        heading <= self.consensus_heading_rad):
                    cluster.append(estimate)
            score = (len(cluster), sum(item['weight'] for item in cluster))
            if best_score is None or score > best_score:
                best_cluster = cluster
                best_score = score

        reference = max(best_cluster, key=lambda item: item['weight'])
        for estimate in candidates:
            if estimate in best_cluster:
                continue
            distance = hypot(
                estimate['x_mm'] - reference['x_mm'],
                estimate['y_mm'] - reference['y_mm'],
            )
            heading = abs(self._wrap(
                estimate['heading_rad'] - reference['heading_rad']
            ))
            rejected.append((
                estimate['key'],
                'disagrees with other tags by {:.0f} mm / {:.2f} rad'.format(
                    distance, heading,
                ),
            ))
        return best_cluster, rejected

    @staticmethod
    def _transform(rotation, translation):
        matrix = [[float(value) for value in row] + [0.0] for row in rotation]
        for index in range(3):
            matrix[index][3] = float(translation[index])
        matrix.append([0.0, 0.0, 0.0, 1.0])
        return matrix

    @staticmethod
    def _validate_transform(transform):
        if len(transform) != 4 or any(len(row) != 4 for row in transform):
            raise ValueError('Transforms must be 4x4 homogeneous matrices')
        matrix = [[float(value) for value in row] for row in transform]
        if any(not isfinite(value) for row in matrix for value in row):
            raise ValueError('Transform values must be finite')
        if any(abs(matrix[3][index] - expected) > 1e-6
               for index, expected in enumerate((0.0, 0.0, 0.0, 1.0))):
            raise ValueError('Transform must have homogeneous bottom row [0, 0, 0, 1]')
        for row in range(3):
            for other in range(3):
                dot = sum(matrix[row][axis] * matrix[other][axis]
                          for axis in range(3))
                expected = 1.0 if row == other else 0.0
                if abs(dot - expected) > 0.02:
                    raise ValueError('Transform rotation must be orthonormal')
        rotation = [row[:3] for row in matrix[:3]]
        determinant = (
            rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1]) -
            rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0]) +
            rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
        )
        if abs(determinant - 1.0) > 0.02:
            raise ValueError('Transform rotation must be right-handed')
        return matrix

    @staticmethod
    def _multiply(left, right):
        return [[sum(left[row][k] * right[k][col] for k in range(4))
                 for col in range(4)] for row in range(4)]

    @staticmethod
    def _inverse(transform):
        rotation = [[transform[row][col] for col in range(3)] for row in range(3)]
        translation = [transform[row][3] for row in range(3)]
        inverse = [[rotation[col][row] for col in range(3)] for row in range(3)]
        inverse_translation = [
            -sum(inverse[row][col] * translation[col] for col in range(3))
            for row in range(3)
        ]
        result = [inverse[row] + [inverse_translation[row]] for row in range(3)]
        result.append([0.0, 0.0, 0.0, 1.0])
        return result

    @staticmethod
    def _wrap(angle):
        return (angle + 3.141592653589793) % (2.0 * 3.141592653589793) - 3.141592653589793

