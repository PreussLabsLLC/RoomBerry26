"""Camera ownership, periodic snapshots, and AprilTag 3 detection."""
# @(#)roomberry_camera.py 2.3.18 2026/10/28 21:40:00

from threading import Event, Lock, Thread
import json
import re
from math import sqrt
from pathlib import Path
from time import localtime, monotonic, sleep, strftime, time


CAM_RESOLUTION = (1296, 972)
SNAP_RESOLUTION = (640, 480)
SNAP_QUALITY = 60
CAPTURE_QUALITY = 95
CAM_FRAMERATE = 30
ANNOTATE_TEXT = 'Roomberry %d-%m-%Y %H:%M:%S'
ANNOTATE_TEXT_SIZE = 30
ANNOTATE_FOREGROUND_COLOR = '#ffffff'
ANNOTATE_BACKGROUND_COLOR = '#808080'
SNAPSHOT_INTERVAL = 20
APRILTAG_FAMILY = 'tag16h5'
DETECTION_MAX_DIMENSION = 0
SCAN_SETTLE_SECONDS = 1.0
ANNOTATION_SETTINGS = frozenset((
    'annotate_background', 'annotate_foreground', 'annotate_text_size',
))


class AprilTagDetector:
    """Thin AprilTag 3 adapter returning plain, image-frame detections.

    Install the official AprilTag 3 Python binding before enabling this
    detector. Detection runs on a grayscale copy scaled to at most
    ``max_dimension`` when nonzero (zero preserves full resolution); corner and center coordinates are scaled back to the
    original frame. Camera-relative tag pose is estimated only when both the
    physical tag size and calibrated camera intrinsics are provided. A further
    camera-to-robot transform is still required for room localization.
    """

    def __init__(self, family=APRILTAG_FAMILY,
                 max_dimension=DETECTION_MAX_DIMENSION, detector=None,
                 tag_size_m=None, camera_intrinsics=None, logger=None):
        self.logger = logger
        self.last_timings_ms = {}
        self.family = family
        self.max_dimension = int(max_dimension)
        if self.max_dimension < 0:
            raise ValueError('Detection image dimension must be nonnegative (0 means full resolution)')
        self.tag_size_m = None if tag_size_m is None else float(tag_size_m)
        self.camera_intrinsics = camera_intrinsics
        if self.tag_size_m is not None and self.tag_size_m <= 0:
            raise ValueError('Tag size must be positive')
        if camera_intrinsics is not None:
            if len(camera_intrinsics) != 4:
                raise ValueError('Camera intrinsics must be (fx, fy, cx, cy)')
            if float(camera_intrinsics[0]) <= 0 or float(camera_intrinsics[1]) <= 0:
                raise ValueError('Camera focal lengths must be positive')
        self._detector = detector

    def _load_detector(self):
        if self._detector is None:
            try:
                from apriltag import apriltag
            except ImportError as error:
                raise RuntimeError(
                    'AprilTag 3 Python bindings are required for tag detection'
                ) from error
            self._detector = apriltag(self.family, decimate=1.0)
        return self._detector

    @staticmethod
    def _estimate_pose_from_homography(detection, tag_size, fx, fy, cx, cy):
        """Recover the AprilTag pose when the binding omits its pose method."""
        import numpy as np

        homography = detection.get('homography')
        if homography is None:
            corners = detection.get('lb-rb-rt-lt', detection.get('corners'))
            if corners is None:
                raise RuntimeError(
                    'AprilTag binding has no pose method, homography, or corners'
                )
            image_points = np.asarray(corners, dtype=float).reshape(4, 2)
            tag_points = np.array((
                (-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0),
            ), dtype=float)
            equations = []
            for (x, y), (u, v) in zip(tag_points, image_points):
                equations.append((-x, -y, -1.0, 0.0, 0.0, 0.0, u*x, u*y, u))
                equations.append((0.0, 0.0, 0.0, -x, -y, -1.0, v*x, v*y, v))
            _, _, vt = np.linalg.svd(np.asarray(equations, dtype=float))
            homography = vt[-1].reshape(3, 3)
        h = np.asarray(homography, dtype=float).reshape(3, 3)

        # AprilTag's homography maps its normalized tag plane into the image.
        # Convert it to camera pose using the same camera-axis convention as
        # the upstream AprilTag homography pose estimator.
        camera_fx = float(fx)
        fx = -camera_fx
        fy = float(fy)
        cx = float(cx)
        cy = float(cy)
        r20, r21, tz = h[2, 0], h[2, 1], h[2, 2]
        r00, r01 = (h[0, 0] - cx * r20) / fx, (h[0, 1] - cx * r21) / fx
        tx = (h[0, 2] - cx * tz) / fx
        r10, r11 = (h[1, 0] - cy * r20) / fy, (h[1, 1] - cy * r21) / fy
        ty = (h[1, 2] - cy * tz) / fy
        length1 = float(np.sqrt(r00 * r00 + r10 * r10 + r20 * r20))
        length2 = float(np.sqrt(r01 * r01 + r11 * r11 + r21 * r21))
        if length1 <= 0 or length2 <= 0:
            raise RuntimeError('Degenerate AprilTag homography')
        factor = 1.0 / np.sqrt(length1 * length2)
        if tz > 0:
            factor = -factor
        r20, r21, tz = r20 * factor, r21 * factor, tz * factor
        r00, r01, tx = r00 * factor, r01 * factor, tx * factor
        r10, r11, ty = r10 * factor, r11 * factor, ty * factor
        rotation = np.array((
            (r00, r01, r10 * r21 - r20 * r11),
            (r10, r11, r20 * r01 - r00 * r21),
            (r20, r21, r00 * r11 - r10 * r01),
        ), dtype=float)
        u, _, vt = np.linalg.svd(rotation)
        rotation = u @ vt
        if np.linalg.det(rotation) < 0:
            u[:, -1] *= -1
            rotation = u @ vt
        axis_fix = np.diag((1.0, -1.0, -1.0))
        rotation = axis_fix @ rotation
        translation = axis_fix @ np.array((tx, ty, tz), dtype=float)
        translation *= float(tag_size) / 2.0

        error = 0.0
        corners = detection.get('lb-rb-rt-lt', detection.get('corners'))
        if corners is not None:
            half = float(tag_size) / 2.0
            object_points = np.array((
                (-half, half, 0.0), (half, half, 0.0),
                (half, -half, 0.0), (-half, -half, 0.0),
            ), dtype=float)
            camera_points = (rotation @ object_points.T).T + translation
            if np.all(camera_points[:, 2] > 1e-9):
                projected = np.column_stack((
                    camera_fx * camera_points[:, 0] / camera_points[:, 2] + cx,
                    fy * camera_points[:, 1] / camera_points[:, 2] + cy,
                ))
                observed = np.asarray(corners, dtype=float).reshape(4, 2)
                error = float(np.mean(np.sum((projected - observed) ** 2, axis=1)))

        return {'R': rotation, 't': translation, 'error': error}
    def detect(self, image):
        import numpy as np
        from PIL import Image

        started = monotonic()
        stage = monotonic()
        source = Image.fromarray(image).convert('L')
        timings = {'grayscale': (monotonic() - stage) * 1000.0}
        stage = monotonic()
        original_width, original_height = source.size
        scale = min(1.0, float(self.max_dimension) /
                    max(original_width, original_height)) if self.max_dimension else 1.0
        if scale < 1.0:
            size = (max(1, int(round(original_width * scale))),
                    max(1, int(round(original_height * scale))))
            resampling = getattr(Image, 'Resampling', Image)
            source = source.resize(size, resampling.BILINEAR)
        timings['resize'] = (monotonic() - stage) * 1000.0
        stage = monotonic()
        gray = np.ascontiguousarray(source, dtype=np.uint8)
        timings['array'] = (monotonic() - stage) * 1000.0
        stage = monotonic()
        native = self._load_detector()
        timings['detector_load'] = (monotonic() - stage) * 1000.0
        stage = monotonic()
        raw_detections = native.detect(gray)
        timings['native_detect'] = (monotonic() - stage) * 1000.0
        stage = monotonic()
        pose_ms = 0.0
        observations = []
        inverse_scale = 1.0 / scale
        for detection in raw_detections:
            center = detection.get('center')
            corners = detection.get('lb-rb-rt-lt', detection.get('corners'))
            if center is None or corners is None:
                continue
            family = detection.get('family', self.family)
            if isinstance(family, bytes):
                family = family.decode('ascii', errors='replace')
            observation = {
                'family': str(family),
                'id': int(detection['id']),
                'hamming': int(detection.get('hamming', 0)),
                'decision_margin': float(detection.get(
                    'margin', detection.get('decision_margin', 0.0)
                )),
                'center_px': tuple(float(value) * inverse_scale for value in center),
                'corners_px': tuple(
                    tuple(float(value) * inverse_scale for value in corner)
                    for corner in corners
                ),
                'image_size': (original_width, original_height),
            }
            if self.tag_size_m is not None and self.camera_intrinsics is not None:
                pose_started = monotonic()
                fx, fy, cx, cy = self.camera_intrinsics
                pose_detector = self._load_detector()
                pose_estimator = getattr(pose_detector, 'estimate_tag_pose', None)
                if callable(pose_estimator):
                    pose = pose_estimator(
                        detection, self.tag_size_m,
                        float(fx) * scale, float(fy) * scale,
                        float(cx) * scale, float(cy) * scale,
                    )
                else:
                    pose = self._estimate_pose_from_homography(
                        detection, self.tag_size_m,
                        float(fx) * scale, float(fy) * scale,
                        float(cx) * scale, float(cy) * scale,
                    )
                observation['tag_pose_camera'] = {
                    'rotation': tuple(
                        tuple(float(value) for value in row)
                        for row in pose['R']
                    ),
                    'translation_m': tuple(
                        float(value) for value in np.asarray(pose['t']).reshape(-1)
                    ),
                    'error': float(pose['error']),
                }
                translation = observation['tag_pose_camera']['translation_m']
                observation['distance_mm'] = sqrt(sum(value * value for value in translation)) * 1000.0
                observation['depth_mm'] = translation[2] * 1000.0
                observation['pose_ms'] = (monotonic() - pose_started) * 1000.0
                pose_ms += observation['pose_ms']
            observations.append(observation)
        timings['observations'] = (monotonic() - stage) * 1000.0
        timings['pose'] = pose_ms
        timings['total'] = (monotonic() - started) * 1000.0
        self.last_timings_ms = timings
        if self.logger is not None:
            self.logger.debug('AprilTag pipeline: source=%dx%d detector=%dx%d timings_ms=%s',
                              original_width, original_height, gray.shape[1], gray.shape[0], timings)
        return observations


class CameraService:
    def __init__(self, logger, camera=None, detector=None,
                 snapshot_interval=SNAPSHOT_INTERVAL, snapshot_root=None,
                 pause_for_detection=False, scan_pause=None, scan_complete=None,
                 scan_settle_seconds=SCAN_SETTLE_SECONDS, capture_resolution=None):
        self.logger = logger
        self._camera = camera
        self.detector = detector if detector is not None else AprilTagDetector()
        self.snapshot_interval = snapshot_interval
        self.highest_resolution = True
        self._scan_requested = Event()
        self.snapshot_root = snapshot_root
        self.pause_for_detection = bool(pause_for_detection)
        self.scan_pause = scan_pause
        self.scan_complete = scan_complete
        self.scan_settle_seconds = max(0.0, float(scan_settle_seconds))
        if self.pause_for_detection and (
                self.scan_pause is None or self.scan_complete is None):
            raise ValueError(
                'scan_pause and scan_complete callbacks are required for stationary scans'
            )
        self._lock = Lock()
        self._detection_lock = Lock()
        self._shutdown = Event()
        self._worker = None
        self.annotate_text = ANNOTATE_TEXT
        self.annotate_text_size = ANNOTATE_TEXT_SIZE
        self.annotate_foreground = ANNOTATE_FOREGROUND_COLOR
        self.annotate_background = ANNOTATE_BACKGROUND_COLOR
        self.snap_quality = SNAP_QUALITY
        self.capture_quality = CAPTURE_QUALITY
        self.resolution = tuple(capture_resolution) if capture_resolution is not None else CAM_RESOLUTION
        self.framerate = CAM_FRAMERATE
        self.snap_resolution_height = SNAP_RESOLUTION[1]
        self.snap_resolution_width = SNAP_RESOLUTION[0]
        self.recording = False
        self.last_capture_time = None
        self._latest_detections = ()
        self._last_detection_time = None
        self._last_detection_duration = None
        self._last_detection_ready_time = None
        self._detector_error = None
        self._last_detector_error_logged = None

    @property
    def latest_detections(self):
        """Immutable shallow snapshot of detections from the most recent scan."""
        with self._detection_lock:
            return tuple(dict(item) for item in self._latest_detections)

    @property
    def last_detection_time(self):
        with self._detection_lock:
            return self._last_detection_time

    @property
    def detector_error(self):
        with self._detection_lock:
            return self._detector_error

    @property
    def last_detection_duration(self):
        """Elapsed detector time in seconds for the most recent successful scan."""
        with self._detection_lock:
            return self._last_detection_duration

    @property
    def last_detection_ready_time(self):
        with self._detection_lock:
            return self._last_detection_ready_time

    @property
    def camera(self):
        return self._camera

    @property
    def started(self):
        return bool(self._camera and self._camera.started)

    @property
    def camera_controls(self):
        return self._camera.camera_controls

    def start(self):
        if self._camera is None:
            from picamera2 import Picamera2
            self._camera = Picamera2()
        intrinsics = getattr(self.detector, 'camera_intrinsics', None)
        if not hasattr(self, '_base_intrinsics'):
            self._base_intrinsics = intrinsics
        if self.highest_resolution:
            self.resolution = tuple(self._camera.sensor_resolution)
        intrinsics = self._base_intrinsics
        if intrinsics is not None:
            sx = self.resolution[0] / float(CAM_RESOLUTION[0])
            sy = self.resolution[1] / float(CAM_RESOLUTION[1])
            fx, fy, cx, cy = intrinsics
            self.detector.camera_intrinsics = (fx * sx, fy * sy, cx * sx, cy * sy)
        config = self._camera.create_still_configuration(main={'size': self.resolution, 'format': 'BGR888'}, queue=False)
        self._camera.configure(config)
        self._camera.start()
        self.logger.info("Vision capture configured: resolution=%s format=BGR888 (RGB array) detection_max_dimension=%s",
                         self.resolution, getattr(self.detector, "max_dimension", None))
        self._shutdown.clear()
        self._worker = Thread(target=self._periodic_capture, name='camera-capture', daemon=True)
        self._worker.start()

    def set_highest_resolution(self, enabled):
        self.highest_resolution = bool(enabled)

    def request_scan(self):
        self._scan_requested.set()

    def close(self):
        self._shutdown.set()
        self._scan_requested.set()
        if self._worker is not None:
            self._worker.join(timeout=2)
        if self._camera is not None:
            with self._lock:
                if self._camera.started:
                    self._camera.stop()
                self._camera.close()

    def get_control(self, name):
        if name in ANNOTATION_SETTINGS:
            return getattr(self, name)
        return self.camera_controls.get(name, '')

    def set_controls(self, controls):
        local_settings = {
            name: value for name, value in controls.items()
            if name in ANNOTATION_SETTINGS
        }
        camera_controls = {
            name: value for name, value in controls.items()
            if name not in ANNOTATION_SETTINGS
        }
        with self._lock:
            for name, value in local_settings.items():
                if name in ('annotate_background', 'annotate_foreground'):
                    value = self._normalize_color(value)
                setattr(self, name, value)
            if camera_controls:
                self._camera.set_controls(camera_controls)

    def set_local_setting(self, name, value):
        if name not in (
            'annotate_text', 'snap_resolution_height', 'snap_resolution_width',
            'snap_quality', 'capture_quality', *ANNOTATION_SETTINGS,
        ):
            raise ValueError('Unknown local camera setting: ' + name)
        with self._lock:
            setattr(self, name, value)

    def get_local_setting(self, name):
        return getattr(self, name)

    def capture_snapshot(self, filepath, resize=True):
        from PIL import Image
        with self._lock:
            image = Image.fromarray(self._camera.capture_array())
            self._annotate_image(image, time())
            if resize:
                image = image.resize((self.snap_resolution_width, self.snap_resolution_height))
            image.save(filepath, quality=self.snap_quality)
            self.last_capture_time = time()

    def capture_recording(self, filepath, duration):
        with self._lock:
            self.recording = True
            try:
                self._camera.start_recording(filepath)
                sleep(int(duration))
                self._camera.stop_recording()
            finally:
                self.recording = False

    def _periodic_capture(self):
        while not self._shutdown.is_set():
            requested = self._scan_requested.wait(self.snapshot_interval)
            self._scan_requested.clear()
            if self._shutdown.is_set():
                break
            self._capture_scan(requested)
            # Explicit requests wake the next capture, including requests that
            # arrive while archiving. Periodic intervals never accumulate.

    def _capture_scan(self, requested=False):
        """Archive every frame; only run stationary detection when pause permits."""
        started = monotonic()
        timings = {}
        paused = False
        detect_allowed = True
        captured_at = None
        image = None
        detections = ()
        error_text = None
        try:
            stage = monotonic()
            if self.pause_for_detection:
                paused = self.scan_pause() is not False
                detect_allowed = paused
            timings['pause'] = (monotonic() - stage) * 1000.0
            stage = monotonic()
            if paused and self._shutdown.wait(self.scan_settle_seconds):
                return
            timings['settle'] = (monotonic() - stage) * 1000.0
            stage = monotonic()
            with self._lock:
                timings['camera_lock'] = (monotonic() - stage) * 1000.0
                stage = monotonic()
                image = self._camera.capture_array()
                captured_at = time()
                self.last_capture_time = captured_at
            timings['capture'] = (monotonic() - stage) * 1000.0
            if detect_allowed:
                stage = monotonic()
                try:
                    detections = tuple(dict(item, captured_at=captured_at)
                                       for item in self.detector.detect(image))
                    timings['detector_stages'] = dict(getattr(self.detector, 'last_timings_ms', {}))
                    with self._detection_lock:
                        self._detector_error = None
                except Exception as error:
                    error_text = str(error)
                    with self._detection_lock:
                        self._detector_error = error_text
                    self.logger.exception('AprilTag detection failed.')
                timings['detect'] = (monotonic() - stage) * 1000.0
                for item in detections:
                    self.logger.debug(
                        'AprilTag detected: family=%s id=%s distance_mm=%s depth_mm=%s '
                        'margin=%s hamming=%s pose_error=%s pose_ms=%s captured_at=%.6f.',
                        item.get('family'), item.get('id'), item.get('distance_mm'),
                        item.get('depth_mm'), item.get('decision_margin'), item.get('hamming'),
                        (item.get('tag_pose_camera') or {}).get('error'), item.get('pose_ms'), captured_at,
                    )
            report = {
                'captured_at': captured_at, 'image_size': [int(image.shape[1]), int(image.shape[0])],
                'color': 'RGB', 'paused': paused, 'requested': bool(requested),
                'detection_skipped': not detect_allowed, 'detector_error': error_text,
                'tags': list(detections), 'timings_ms': timings,
            }
            if self.snapshot_root is not None:
                try:
                    self._save_periodic_snapshot(image, captured_at, report)
                except Exception:
                    self.logger.exception('Vision archive could not be saved.')
            timings['total'] = (monotonic() - started) * 1000.0
            # Publish after archiving so slow full-resolution detection/storage
            # cannot make a stationary result expire before the mission sees it.
            if detect_allowed and error_text is None:
                with self._detection_lock:
                    self._latest_detections = detections
                    self._last_detection_time = captured_at
                    self._last_detection_ready_time = time()
                    self._last_detection_duration = timings['detect'] / 1000.0
            self.logger.debug('Vision scan: tags=%d paused=%s skipped=%s image=%s timings_ms=%s',
                              len(detections), paused, not detect_allowed, image.shape, timings)
        except Exception:
            self.logger.exception('Vision capture failed.')
        finally:
            if paused and self.scan_complete is not None:
                stage = monotonic()
                try:
                    self.scan_complete()
                except Exception:
                    self.logger.exception('Unable to signal completion of AprilTag scan.')
                self.logger.debug('Vision resume callback: %.3f ms; end-to-end %.3f ms.',
                                  (monotonic() - stage) * 1000.0, (monotonic() - started) * 1000.0)

    def _save_periodic_snapshot(self, image_array, timestamp=None, report=None):
        """Save an unannotated, full-resolution color JPEG and scan metadata."""
        from PIL import Image
        started = monotonic()
        now = time() if timestamp is None else timestamp
        day = strftime('%Y%m%d', localtime(now))
        stem = strftime('%Y%m%d-%H%M%S', localtime(now)) + '-%06d' % (int(now * 1000000) % 1000000)
        folder = Path(self.snapshot_root) / day
        folder.mkdir(parents=True, exist_ok=True)
        filepath = folder / (stem + '.jpg')
        temporary = filepath.with_suffix('.jpg.tmp')
        Image.fromarray(image_array).convert('RGB').save(
            str(temporary), format='JPEG', quality=self.capture_quality, subsampling=0,
        )
        temporary.replace(filepath)
        if report is not None:
            report['image_url'] = '/cam/scans/' + day + '/' + filepath.name
            report['report_url'] = '/cam/scans/' + day + '/' + stem + '.json'
            report['timings_ms']['image_save'] = (monotonic() - started) * 1000.0
            report['timings_ms']['through_image_save'] = sum(
                report['timings_ms'].get(key, 0.0)
                for key in ('pause', 'settle', 'camera_lock', 'capture', 'detect', 'image_save')
            )
            report_path = filepath.with_suffix('.json')
            temporary = report_path.with_suffix('.json.tmp')
            stage = monotonic()
            temporary.write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
            temporary.replace(report_path)
            self.logger.debug('Vision report save: %.3f ms path=%s',
                              (monotonic() - stage) * 1000.0, report_path)
        return filepath

    def recent_scans(self, limit=20, tags_only=False):
        """Read durable reports newest first, including scans with no detections."""
        if self.snapshot_root is None:
            return []
        reports = []
        for filename in sorted(Path(self.snapshot_root).glob('[0-9]*/????????-??????-??????.json'), reverse=True):
            try:
                report = json.loads(filename.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if tags_only and not report.get('tags'):
                continue
            reports.append(report)
            if len(reports) >= limit:
                break
        return reports

    def scan_archive_file(self, relative):
        """Resolve only generated archive filenames beneath the camera root."""
        if self.snapshot_root is None or not re.fullmatch(
                r'[0-9]{8}/[0-9]{8}-[0-9]{6}-[0-9]{6}\.(jpg|json)', relative):
            return None
        root = Path(self.snapshot_root).resolve()
        candidate = (root / relative).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return None
        return candidate

    def _annotate_image(self, image, timestamp):
        from PIL import ImageDraw, ImageFont

        text = strftime(self.annotate_text, localtime(timestamp))
        if not text:
            return
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('DejaVuSans.ttf', size=int(self.annotate_text_size))
        except OSError:
            try:
                font = ImageFont.load_default(size=int(self.annotate_text_size))
            except TypeError:
                font = ImageFont.load_default()
        bounds = draw.textbbox((0, 0), text, font=font)
        padding = 4
        draw.rectangle(
            (0, 0, bounds[2] + padding * 2, bounds[3] + padding * 2),
            fill=self.annotate_background,
        )
        draw.text(
            (padding, padding), text, fill=self.annotate_foreground, font=font,
        )

    @staticmethod
    def _normalize_color(value):
        if isinstance(value, str) and len(value) in (3, 4, 6, 8):
            if all(character in '0123456789abcdefABCDEF' for character in value):
                return '#' + value
        return value
