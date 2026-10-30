__author__ = 'Daniel Macías Perea (dani.macias.perea@gmail.com)'

# @(#)roomberry.py 2.3.16 2026/10/28 21:00:00
import xml.etree.ElementTree as ET
import logging
import traceback
import json
from ast import literal_eval
from socketserver import ThreadingMixIn
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse, quote
from os import remove, path, makedirs, stat, walk
from os.path import join, isdir, islink
from time import time, strftime, localtime
from roomberry_camera import CameraService
from roomberry_camera import AprilTagDetector
from roomberry_control import RobotCommandArbiter
from roomberry_localization import AprilTagLocalizer
from roomberry_mapper import RoomberryMapper
from roomberry_mission import RoomberryMission
from roomberry_navigation import NavigationCoordinator
from roomberry_sensor_log import SensorCsvRecorder
from irobot.openinterface.constants import MODES

CAM_RESOLUTION = (1296, 972)
SNAP_RESOLUTION = (640, 480)
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
SNAP_QUALITY = 60
CAPTURE_QUALITY = 80
CAM_FRAMERATE = 30
CAM_ROTATION = 0
BATTERY_WATCHDOG_SLEEP_TIME = 600
IFTTT_KEY = ''
BATTERY_CRITICAL_LEVEL = 0.1
BATTERY_LOW_LEVEL = 0.3
PORT_NUMBER = 8080
PORT_SERIAL = '/dev/serial0'
BRC_GPIO = 0  # BRC is not wired on the current serial interface.
LOCK_TIMEOUT = 15
ANNOTATE_TEXT_SIZE = 30
ANNOTATE_TEXT = 'Roomberry %d-%m-%Y %H:%M:%S'
ANNOTATE_FOREGROUND_COLOR = '#ffffff'
ANNOTATE_BACKGROUND_COLOR = '#808080'
PATH_TO_WWW='/dev/shm/tmp'
PATH_TO_ROOMBA='/roomba/'
PATH_TO_CAM='/cam/'
PATH_TO_MEDIA='/media'
PATH_TO_ROOMBA_XML = PATH_TO_ROOMBA + 'roomba.xml'
PATH_TO_CAM_XML = PATH_TO_CAM + 'cam.xml'
PATH_TO_MEDIA_XML = PATH_TO_CAM + 'media.xml'
PATH_TO_SNAP = PATH_TO_CAM + 'snap.jpg'
PATH_TO_LOG = '/var/log/roomberry.log'
AUTONOMY_CONFIG_PATH = Path(__file__).with_name('autonomy.json')
DEFAULT_ROOM_WIDTH_MM = 8000.0
DEFAULT_ROOM_HEIGHT_MM = 8000.0

CAM_XML_TAGS = [ ('annotate_background'), ('annotate_foreground'), ( 'annotate_text_size'), ('awb_mode'), ('brightness'), ('contrast'), ('drc_strength'), \
    ('exposure_compensation'), ('exposure_mode'), ('framerate', 'numerator'), ('hflip'), ('image_denoise'), ('image_effect'), ('iso'), \
    ('local','annotate_text'), ('local','snap_resolution_height'), ('local','snap_resolution_width'), ('local','snap_quality'), \
    ('local','capture_quality'), ('recording'), ('resolution', 'width'), ('resolution', 'height'), ('rotation'), ('saturation'), \
    ('sharpness'), ('vflip'), ('video_denoise'), ('video_stabilization')]

# Web controls send these directly to the arbiter rather than through the
# mission. Cancel an active autonomous mission first, and tell the mission so
# its idle-mode scan pause does not brake an ongoing manual drive.
MANUAL_ROOMBA_OPERATIONS = frozenset((
    '_change_mode', 'drive', 'drive_direct', 'drive_pwm',
))
REMOTE_MOTION_OPERATIONS = frozenset(('drive', 'drive_direct', 'drive_pwm'))
MANUAL_MOTION_KEYS = (
    'velocity', 'right_velocity', 'left_velocity', 'right_pwm', 'left_pwm',
)
    
ROOMBA_XML_TAGS = [('bumps_and_wheel_drops','bump_left'), ('bumps_and_wheel_drops','bump_right'), ('bumps_and_wheel_drops','wheel_drop_left'), \
    ('bumps_and_wheel_drops','wheel_drop_right'), ('cliff_left_sensor'), ('cliff_front_left_sensor'), ('cliff_front_right_sensor'), \
    ('cliff_right_sensor'), ('virtual_wall_sensor'), ('dirt_detect_sensor'), ('ir_character_left'), ('ir_character_right'), \
    ('distance'), ('angle'), ('charging_state'), ('voltage'), ('current'), ('temperature'), ('battery_charge'), ('battery_capacity'), \
    ('cliff_left_signal'), ('cliff_front_left_signal'), ('cliff_front_right_signal'), ('cliff_right_signal'), \
    ('charging_sources', 'internal_charger'), ('charging_sources', 'home_base'), ('oi_mode'), ('requested_velocity'), ('requested_radius'), \
    ('requested_left_velocity'), ('requested_right_velocity'), ('left_encoder_counts'), ('right_encoder_counts'), ('light_bumper', 'left'), \
    ('light_bumper', 'front_left'), ('light_bumper', 'center_left'), ('light_bumper', 'center_right'), ('light_bumper', 'front_right'), \
    ('light_bumper', 'right'), ('light_bump_left_signal'), ('light_bump_front_left_signal'), ('light_bump_center_left_signal'), \
    ('light_bump_center_right_signal'), ('light_bump_front_right_signal'), ('light_bump_right_signal'), ('left_motor_current'), ('right_motor_current'), \
    ('main_brush_motor_current'), ('side_brush_motor_current'), ('stasis', 'toggling'), ('stasis', 'disabled')]
    
class RoomberryServer(ThreadingMixIn, HTTPServer):

    def __init__(self, server_address, server_handler, serial_port, brc_pin,
                 autonomy_config=None):
        super().__init__(server_address, server_handler)
        self.logger = logging.getLogger('Roomberry')
        self.autonomy_config = autonomy_config
        camera_config = (autonomy_config or {}).get('camera', {})
        dock_waypoint = (autonomy_config or {}).get('dock_waypoint_mm')
        sensor_log = SensorCsvRecorder.from_config(
            (autonomy_config or {}).get('sensor_log'), self.logger,
        )
        self.roomba_control = RobotCommandArbiter(
            serial_port, brc_pin, self.logger,
            auto_seek_dock=dock_waypoint is None,
            sensor_log=sensor_log,
            motion_ramp=(autonomy_config or {}).get('motion_ramp'),
            reverse_current_monitor=(autonomy_config or {}).get('reverse_current_monitor'),
        )
        self.mission = None
        self.mapper = None
        self.map_tags_mm = []
        detector = None
        scan_pause = None
        scan_complete = None
        if autonomy_config is not None:
            robot_radius = autonomy_config['robot_radius_mm']
            map_config = autonomy_config.get('map', {})
            default_cell_size = robot_radius / 2.0
            map_width = float(map_config.get('width_mm', DEFAULT_ROOM_WIDTH_MM))
            map_height = float(map_config.get('height_mm', DEFAULT_ROOM_HEIGHT_MM))
            cell_size = map_config.get('cell_size_mm')
            if cell_size is None:
                if 'cols' not in map_config and 'rows' not in map_config:
                    cols = max(1, round(map_width / default_cell_size))
                    rows = max(1, round(map_height / default_cell_size))
                    # Keep the default room extent exact while preserving the
                    # intended half-radius cookie spacing to within rounding.
                    cell_size = min(map_width / cols, map_height / rows)
                else:
                    # Explicit grid dimensions retain the mapper's ordinary
                    # half-radius cell spacing unless the user sets a pitch.
                    cell_size = default_cell_size
                    cols = int(map_config.get('cols', max(
                        1, round(map_width / cell_size)
                    )))
                    rows = int(map_config.get('rows', max(
                        1, round(map_height / cell_size)
                    )))
            else:
                cols = int(map_config.get('cols', max(
                    1, round(map_width / float(cell_size))
                )))
                rows = int(map_config.get('rows', max(
                    1, round(map_height / float(cell_size))
                )))
            mapper = RoomberryMapper(
                cols, rows, robot_radius,
                origin=map_config.get('origin_mm', (0.0, 0.0)),
                cell_size_mm=cell_size,
                cleaning_radius_mm=map_config.get('cleaning_radius_mm'),
                persist_interval_s=map_config.get('persist_interval_s', 30.0),
            )
            self.mapper = mapper
            state_path = map_config.get('state_path', str(Path(__file__).with_name('map-state.json')))
            mapper.state_path = state_path
            if mapper.load_state(state_path):
                self.logger.info('Restored saved map from %s', state_path)
            self.map_tags_mm = [
                (float(item['world_from_tag'][0][3]) * 1000.0,
                 float(item['world_from_tag'][1][3]) * 1000.0,
                 item['id'])
                for item in autonomy_config['landmarks']
            ]
            navigation = NavigationCoordinator(robot_radius)
            camera_intrinsics = camera_config['intrinsics']
            if isinstance(camera_intrinsics, dict):
                camera_intrinsics = tuple(
                    camera_intrinsics[key] for key in ('fx', 'fy', 'cx', 'cy')
                )
            landmarks = {
                (item.get('family', camera_config.get('family', 'tag16h5')),
                 item['id']): item['world_from_tag']
                for item in autonomy_config['landmarks']
            }
            if not landmarks:
                raise ValueError('Autonomy requires at least one surveyed AprilTag landmark')
            tag_filter = autonomy_config.get('tag_filter', {})
            localizer = AprilTagLocalizer(
                landmarks,
                autonomy_config['camera_from_robot'],
                room_bounds_mm=(mapper.origin_x, mapper.origin_y,
                                mapper.origin_x + map_width, mapper.origin_y + map_height),
                confirm_large_relocations=True,
                max_localization_age=autonomy_config.get('max_localization_age', 60.0),
                max_pose_jump_age=tag_filter.get('max_pose_jump_age', 30.0),
                min_decision_margin=autonomy_config.get('min_decision_margin', 10.0),
                max_reprojection_error=tag_filter.get('max_reprojection_error', 10.0),
                min_tag_distance_m=tag_filter.get('min_tag_distance_m', 0.08),
                max_tag_distance_m=tag_filter.get('max_tag_distance_m', 8.0),
                max_pose_jump_mm=tag_filter.get('max_pose_jump_mm', 500.0),
                max_heading_jump_rad=tag_filter.get('max_heading_jump_rad', 0.6),
                consensus_distance_mm=tag_filter.get('consensus_distance_mm', 250.0),
                consensus_heading_rad=tag_filter.get('consensus_heading_rad', 0.35),
                discover_unknown_tags=autonomy_config.get('discover_unknown_tags', True),
                discovery_save_path=autonomy_config.get('discovered_tags_path') or str(Path(__file__).with_name('discovered-tags.json')),
            )
            self.mission = RoomberryMission(
                self.roomba_control, None, mapper, navigation, localizer,
                self.logger, dock_waypoint_mm=dock_waypoint,
                wall_follow=autonomy_config.get('wall_follow'),
                period=autonomy_config.get('mission_period', 0.2),
                landmarks=autonomy_config['landmarks'],
            )
            detector = AprilTagDetector(
                family=camera_config.get('family', 'tag16h5'),
                max_dimension=camera_config.get('max_dimension', 0),
                tag_size_m=camera_config['tag_size_m'],
                camera_intrinsics=camera_intrinsics, logger=self.logger,
            )
            if camera_config.get('pause_for_detection', False):
                scan_pause = self.mission.scan_pause
                scan_complete = self.mission.scan_complete

        self.camera_service = CameraService(
            self.logger,
            detector=detector,
            snapshot_interval=camera_config.get('snapshot_interval', 20),
            snapshot_root=join(PATH_TO_MEDIA, PATH_TO_CAM.lstrip('/')),
            pause_for_detection=bool(camera_config.get('pause_for_detection', False)),
            scan_pause=scan_pause,
            scan_complete=scan_complete,
            scan_settle_seconds=camera_config.get('scan_settle_seconds', 1.0),
            capture_resolution=camera_config.get('capture_resolution'),
        )
        if self.mission is not None:
            self.mission.camera = self.camera_service
        self.camera_service.set_highest_resolution(
            camera_config.get('highest_resolution', True)
        )
        self.last_camera_operation = time()

    def start(self):
        self.logger.info('Roomberry Server correctly started.')
        self.roomba_control.start()
        self.camera_service.start()
        if self.mission is not None:
            start_mode = self.autonomy_config.get('start_mode', 'idle')
            self.mission.start(start_mode)
            self.logger.info('Autonomy coordinator started in %s mode.', start_mode)
        self.serve_forever()
        
    def stop(self):
        self.logger.info('Roomberry Server correctly stopped.')
        try:
            self.server_close()
        finally:
            try:
                if self.mission is not None:
                    self.mission.close()
            finally:
                try:
                    self.camera_service.close()
                finally:
                    self.roomba_control.close()

    def handle_error(self, request, client_address):
        self.logger.info('Exception happened during processing of request from %s', client_address, exc_info=True)        
        
class RoomberryHandler(BaseHTTPRequestHandler):
    
    def __init__(self, request, client_address, server):
        self.logger = logging.getLogger('Roomberry')
        super(RoomberryHandler, self).__init__(request, client_address, server)
        
    def create_cam_xml(self):
        root = ET.Element("cam")
        for tag in CAM_XML_TAGS:
            if type(tag) is tuple:
                ET.SubElement(root, '-'.join(tag) )
            else:
                ET.SubElement(root, tag)
        tree = ET.ElementTree(root)        
        return tree
    
    def get_cam_xml(self):
        xml_file = Path(PATH_TO_WWW + PATH_TO_CAM_XML)
        if xml_file.exists():
           tree = ET.parse(PATH_TO_WWW + PATH_TO_CAM_XML)
        else:
           tree = self.create_cam_xml()
        
        root = tree.getroot()       
        
        for i in range(len(CAM_XML_TAGS)):
            tag = CAM_XML_TAGS[i]
            if type(tag) is tuple:
                if tag[0] == 'local':
                    root[i].text = str(self.server.camera_service.get_local_setting(tag[1]))
                elif tag[0] == 'framerate':
                    root[i].text = str(self.server.camera_service.framerate)
                elif tag[0] == 'resolution':
                    size = self.server.camera_service.resolution
                    root[i].text = str(size[0] if tag[1] == 'width' else size[1])
                else:
                    root[i].text = str(self.server.camera_service.get_control(tag[1]))
            else:
                if tag == 'resolution_width':
                    root[i].text = str(self.server.camera_service.resolution[0])
                elif tag == 'resolution_height':
                    root[i].text = str(self.server.camera_service.resolution[1])
                elif tag == 'framerate':
                    root[i].text = str(self.server.camera_service.framerate)
                elif tag == 'recording':
                    root[i].text = str(self.server.camera_service.recording)
                else:
                    root[i].text = str(self.server.camera_service.get_control(tag))

        tree.write(PATH_TO_WWW + PATH_TO_CAM_XML)  
        return
        
    def create_roomba_xml(self):
        root = ET.Element("roomba")
        for tag in ROOMBA_XML_TAGS:
            if type(tag) is tuple:
                ET.SubElement(root, '-'.join(tag) )
            else:
                ET.SubElement(root, tag)
        tree = ET.ElementTree(root)        
        return tree
    
    def get_roomba_xml(self):
        xml_file = Path(PATH_TO_WWW + PATH_TO_ROOMBA_XML)
        if xml_file.exists():
           tree = ET.parse(PATH_TO_WWW + PATH_TO_ROOMBA_XML)
        else:
           tree = self.create_roomba_xml()
        
        root = tree.getroot()       
        
        snapshot = self.server.roomba_control.snapshot()
        sensor_group100 = snapshot['sensors']
        
        for i in range(len(ROOMBA_XML_TAGS)):
            if sensor_group100 is None:
                root[i].text = 'unknown'
                continue
            if ROOMBA_XML_TAGS[i] == "distance":
                root[i].text = str(snapshot['distance'])
            elif ROOMBA_XML_TAGS[i] == "angle":
                root[i].text = str(snapshot['angle'])
            elif type(ROOMBA_XML_TAGS[i]) is tuple:
                root[i].text = str(getattr(getattr(sensor_group100, ROOMBA_XML_TAGS[i][0]), ROOMBA_XML_TAGS[i][1])) 
            else:
                root[i].text = str(getattr(sensor_group100, ROOMBA_XML_TAGS[i]))                               
        tree.write(PATH_TO_WWW + PATH_TO_ROOMBA_XML)        
        return

    def get_media_xml(self):
        xml_file = Path(PATH_TO_WWW + PATH_TO_MEDIA_XML)   
        if xml_file.exists():
           remove(PATH_TO_WWW + PATH_TO_MEDIA_XML)
        
        media_dictionary = {}
        for dirpath, dirs, files in walk(PATH_TO_MEDIA + '/' + PATH_TO_CAM):            
            if files:
                media_dictionary[dirpath] = sorted(files, reverse=True) 
        
        root = ET.Element("files")

        for k, v in sorted(media_dictionary.items(), key=lambda item: (item[1], item[0]), reverse=True):
            aux = ET.SubElement(root, "folder", day = k.split('/')[-1])
            for file in v: 
                if file.endswith('.jpg'):
                    ET.SubElement(aux, "file", type = "capture", path = file)
                elif file.endswith('.h264'):
                    ET.SubElement(aux, "file", type = "record", path = file)

        tree = ET.ElementTree(root)      
        tree.write(PATH_TO_WWW + PATH_TO_MEDIA_XML)   
      
    def update_cam_snap(self):
        self.server.camera_service.capture_snapshot(PATH_TO_WWW + PATH_TO_SNAP)

    def cam_record(self, duration):
        year, month, day, hour, minute, second = strftime("%Y,%m,%d,%H,%M,%S", localtime(time())).split(',')
        self._create_day_folder(year, month, day)
        filepath = PATH_TO_MEDIA + '/' + PATH_TO_CAM + '/' + year + month + day + '/' + year + month + day + '-' + hour + minute + second + '.h264'
        self.server.camera_service.capture_recording(filepath, duration)

    def cam_capture(self):
        year, month, day, hour, minute, second = strftime("%Y,%m,%d,%H,%M,%S", localtime(time())).split(',')
        self._create_day_folder(year, month, day)
        filepath = PATH_TO_MEDIA + '/' + PATH_TO_CAM + '/' + year + month + day + '/' + year + month + day + '-' + hour + minute + second + '.jpg'
        self.server.camera_service.capture_snapshot(filepath, resize=False)

    def send_reply(self, basePath=PATH_TO_WWW, mimetype=None):          
        self.send_response(200)
        self.send_header('Content-type', mimetype)
        self.send_header('Cache-Control', 'no-store')
        if mimetype != None:
            f = open(basePath + self.path, 'rb')
            statinfo = stat(basePath + self.path)
            self.send_header("Content-length", statinfo.st_size)
            self.end_headers()
            self.wfile.write(f.read())
            f.close()
        else:
            self.end_headers()
            
    def send_error_reply(self, error_message):
        self.send_error(400, error_message)

    def reset_roomba_distance_angle(self):
        self.server.roomba_control.reset_odometry()

    def _take_manual_control(self, operation, kwargs):
        """Tell the mission that a web motion/mode command is taking over."""
        mission = getattr(self.server, 'mission', None)
        if mission is None:
            return
        moving = operation != '_change_mode' and any(
            int(kwargs.get(key, 0) or 0) for key in MANUAL_MOTION_KEYS
        )
        try:
            mission.take_manual_control(moving=moving)
        except Exception:
            self.server.logger.exception(
                'Unable to hand control to the web command %s.', operation,
            )

    def _ensure_remote_drive_mode(self, kwargs):
        """Restore Safe mode so a direct web drive command cannot be ignored."""
        if not any(int(kwargs.get(key, 0) or 0) for key in MANUAL_MOTION_KEYS):
            return
        try:
            state = self.server.roomba_control.snapshot()
            sensors = state.get('sensors') if isinstance(state, dict) else None
            if sensors is not None and getattr(sensors, 'oi_mode', None) == MODES.SAFE:
                return
            self.server.roomba_control.execute('_change_mode', mode=MODES.SAFE)
        except Exception:
            self.server.logger.exception(
                'Unable to enter Safe mode for remote-control motion.',
            )
            
    def _serve_vision(self):
        parsed = urlparse(self.path)
        if parsed.path == '/status.json':
            state = self.server.roomba_control.snapshot()
            keys = ('firmware_version', 'firmware_release', 'age', 'ready', 'oi_stopped', 'sensor_fault', 'battery_status',
                    'hard_hazard_reasons', 'button_diagnostics', 'reverse_current_monitor',
                    'applied_left_velocity_mm_s', 'applied_right_velocity_mm_s')
            payload = json.dumps({key: state.get(key) for key in keys}, allow_nan=False).encode('utf-8')
            content_type = 'application/json'
        elif parsed.path in ('/cam/tags.json', '/cam/scans.json'):
            try:
                limit = int(parse_qs(parsed.query).get('limit', ['20'])[0])
                if not 1 <= limit <= 200:
                    raise ValueError()
            except ValueError:
                self.send_error(400, 'limit must be between 1 and 200')
                return True
            payload = json.dumps({'scans': self.server.camera_service.recent_scans(
                limit, tags_only=parsed.path == '/cam/tags.json',
            )}, allow_nan=False).encode('utf-8')
            content_type = 'application/json'
        elif parsed.path.startswith('/cam/scans/'):
            filename = self.server.camera_service.scan_archive_file(parsed.path[len('/cam/scans/'):])
            if filename is None:
                self.send_error(404, 'Scan archive file not found')
                return True
            payload = filename.read_bytes()
            content_type = 'image/jpeg' if filename.suffix == '.jpg' else 'application/json'
        else:
            return False
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)
        return True

    def do_GET(self):      
        try:
            if self._serve_vision():
                return
            if urlparse(self.path).path == '/map.png':
                if self.server.mapper is None:
                    self.send_error(404, 'Mapping is not configured')
                    return
                from roomberry_map_image import render_map
                payload = render_map(self.server.mapper.snapshot(), self.server.map_tags_mm)
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            elif self.path.startswith(PATH_TO_CAM):
                if self.path == PATH_TO_CAM_XML:
                    self.get_cam_xml()             
                    self.send_reply(mimetype='text/xml')
                elif self.path == PATH_TO_MEDIA_XML:
                    self.get_media_xml()             
                    self.send_reply(mimetype='text/xml')                    
                elif self.path == PATH_TO_SNAP:
                    self.update_cam_snap()
                    self.send_reply(mimetype='image/jpg')
                elif self.path.endswith('.jpg'):
                    self.send_reply(PATH_TO_MEDIA,'image/jpg')
                elif self.path.endswith('.h264'):
                    self.send_reply(PATH_TO_MEDIA,'video/H264')
                else:
                    dict_qs = parse_qs(urlparse(self.path).query)
                    operation = dict_qs['op'][0]
                    dict_qs = dict([key, value[0]] for key, value in dict_qs.items() if key!='op')

                    if operation == 'cam':
                        for key, value in dict_qs.items():
                            if key.startswith('local-'):
                                setting = key.split('-', 1)[1]
                                if setting != 'annotate_text':
                                    value = int(value)
                                self.server.camera_service.set_local_setting(setting, value)
                            else:
                                if value in ('True', 'False'):
                                    value = self._bool_convert(value)
                                elif self._is_int(value):
                                    value = int(value)
                                self.server.camera_service.set_controls({key: value})
                    else:
                        getattr(self, operation)(**dict_qs)
                            
                    self.send_reply()                   
                self.server.last_camera_operation = time()
                    
            elif self.path.startswith(PATH_TO_ROOMBA):
                if self.path == PATH_TO_ROOMBA_XML:
                    self.get_roomba_xml()                
                    self.send_reply(mimetype='text/xml')
                else:               
                    dict_qs = parse_qs(urlparse(self.path).query)
                    operation = dict_qs['op'][0]
                    dict_qs = dict([key, self._dictionary_Parser(key,value[0])] for key, value in dict_qs.items() if key!='op')
                    
                    if operation == 'reset_roomba_distance_angle':
                        self.reset_roomba_distance_angle()
                    else:
                        if operation in MANUAL_ROOMBA_OPERATIONS:
                            self._take_manual_control(operation, dict_qs)
                        if operation in REMOTE_MOTION_OPERATIONS:
                            self._ensure_remote_drive_mode(dict_qs)
                        self.server.roomba_control.execute(operation, **dict_qs)
                    
                    self.send_reply()                    
            else: 
                self.server.logger.error('error: bad parsed request.')
                self.send_error_reply('Bad parsed request')
        
        except Exception as e:
            self.server.logger.error('error: bad parsed request: ' + str(e) + '\n' +traceback.format_exc())
            self.send_error_reply(str(e))
            return

    def log_message(self, format, *args):
        self.logger.debug("%s - - %s" % (self.address_string(), format % args))

    @staticmethod     
    def _is_int(v):
        try:     i = int(v)
        except:  return False
        return True
    
    @staticmethod
    def _bool_convert(s):
        return s == "True"
   
    @staticmethod        
    def _dictionary_Parser(key, value):
        if key == 'notes':
            return literal_eval('['+(value)+']')
        else:
            return int(value)

    @staticmethod 
    def _create_day_folder(year, month, day):        
        if not path.isdir(PATH_TO_MEDIA + '/' + PATH_TO_CAM + '/' + year + month + day):
            makedirs(PATH_TO_MEDIA + '/' + PATH_TO_CAM + '/' + year + month + day)
          
def run(http_port=PORT_NUMBER, serial_port=PORT_SERIAL, brc_pin=BRC_GPIO,
        autonomy_config=None):
    logger = logging.getLogger('Roomberry')
    hdlr = logging.FileHandler(PATH_TO_LOG)
    formatter = logging.Formatter(LOG_FORMAT)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr) 
    logger.setLevel(logging.DEBUG)    
    
    if not path.exists(PATH_TO_WWW + PATH_TO_CAM):
        makedirs(PATH_TO_WWW + PATH_TO_CAM)
    if path.isfile(PATH_TO_WWW + PATH_TO_CAM_XML):
        remove(PATH_TO_WWW + PATH_TO_CAM_XML)
    if not path.exists(PATH_TO_WWW + PATH_TO_ROOMBA):
        makedirs(PATH_TO_WWW + PATH_TO_ROOMBA)
    if path.isfile(PATH_TO_WWW + PATH_TO_ROOMBA_XML):
        remove(PATH_TO_WWW + PATH_TO_ROOMBA_XML)
            
    if autonomy_config is None and AUTONOMY_CONFIG_PATH.is_file():
        with AUTONOMY_CONFIG_PATH.open('r') as config_file:
            autonomy_config = json.load(config_file)
    httpd = RoomberryServer(
        ('', http_port), RoomberryHandler, serial_port, brc_pin,
        autonomy_config=autonomy_config,
    )

    try:
        httpd.start()
    finally:
        httpd.stop()

if __name__ == "__main__":
    from sys import argv

    if len(argv) == 4:
        run(http_port=int(argv[1]), serial_port=argv[2], brc_pin=int(argv[3]))
    else:
        run()
