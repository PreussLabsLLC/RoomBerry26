"""Read-only local dashboard data and a command index from the shipped driver."""
# @(#)roomberry_web.py 3.2.imu.1 2026/11/12 15:16:02
import ast
from functools import lru_cache
from pathlib import Path
from time import monotonic

from roomberry_calibration import HEADING_LIMIT_RAD, ENDPOINT_TOLERANCE_MM

ASSET_ROOT = Path(__file__).with_name('web')
ASSETS = {'/': ('index.html','text/html; charset=utf-8'),
          '/index.html': ('index.html','text/html; charset=utf-8'),
          '/ui/': ('index.html','text/html; charset=utf-8'),
          '/ui/app.js': ('app.js','application/javascript; charset=utf-8'),
          '/ui/speech.js': ('speech.js','application/javascript; charset=utf-8'),
          '/ui/maps.js': ('maps.js','application/javascript; charset=utf-8'),
          '/ui/maps.css': ('maps.css','text/css; charset=utf-8'),
          '/ui/style.css': ('style.css','text/css; charset=utf-8')}


@lru_cache(maxsize=1)
def command_index():
    commands = []
    def add(group, name, url, description, mutates=False, aliases=()):
        commands.append(dict(group=group,name=name,url=url,description=description,
                             mutates=mutates,aliases=list(aliases),parameters=[]))
    add('Mission','wall','/roomba/?op=wall','Start WALL: qualify tag 16, turn left 90 degrees, forward 200 mm, right 45 degrees, acquire and follow the right wall toward tag15. Stop and validate within300mm using two fresh scans. Cruise80mm/s; moving wheel minimum50mm/s. Clock starts/cancels. Uses right light-bumper target 30 raw units; no distance calibration required.',True)
    add('Mission','gridrunner','/roomba/?op=gridrunner','Reverse along grout; stop and confirm its end, then return through tag-15 scan checkpoints and front contact. Start from this dashboard; Clock now starts WALL.',True,('grid',))
    add('Mission','return_to_tag15','/roomba/?op=return_to_tag15','Stop the current mission, localize with mapped tags or a valid trace, and home to tag 15. No threshold run or phone stream required.',True)
    for direction, amount in (('left','5 degrees'),('right','5 degrees'),
                              ('left_15','15 degrees'),('right_15','15 degrees'),
                              ('left_30','30 degrees'),('right_30','30 degrees'),
                              ('forward','50 mm'),('backward','50 mm'),
                              ('forward_500','500 mm'),('backward_500','500 mm')):
        add('Steering pad','step_'+direction,'/roomba/?op=step_'+direction,
            'Pause the mission and move '+direction.split('_', 1)[0]+' by '+amount+' using wheel odometry, then stop.',True)
    for mode in ('clean','return_to_base','remote_control'):
        add('Mission',mode,'/roomba/?op='+mode,'Select '+mode+' mission mode.',True)
    add('Roomba','reset','/roomba/?op=reset','Send the standard driver reset command (requires a responsive robot).',True)
    add('Mission','calibrate','/roomba/?op=calibrate','Run scan-free out-and-back calibration from manual alignment at tag 15.',True,('cal','calibration'))
    add('Mission','discovery','/roomba/?op=discovery','Start the surveyed landmark discovery route.',True,('discover',))
    add('Mission','idle','/roomba/?op=idle','Stop motion and return to idle.',True,('cancel_calibration',))
    add('Mission','stop','/roomba/?op=stop','Brake immediately and cancel the active mission.',True,('emergency_stop',))
    for name,url,desc in (
        ('status','/status.json','Robot status, calibration progress and result.'),
        ('GroundHog','/groundhog.json','Relative motion, phone health, IMU and compass.'),
        ('commands','/commands.json','This command index as JSON.'),
        ('recent tag scans','/cam/tags.json?limit=20','Recent archived scans containing detections.'),
        ('all recent scans','/cam/scans.json?limit=20','Includes missing tags, skipped scans and detector errors.'),
        ('map','/map.png','Current map image.'),
        ('Roomba XML','/roomba/roomba.xml','Detailed robot sensors.'),
        ('camera XML','/cam/cam.xml','Camera configuration.'),
        ('snapshot','/cam/snap.jpg','Capture a current camera snapshot.'),
        ('media XML','/cam/media.xml','Archived media index.')):
        add('Read',name,url,desc)
    add('Camera','request_scan','/cam/?op=request_scan','Request a scan; calibration skips scans throughout the run.',True)
    add('Camera','cam_capture','/cam/?op=cam_capture','Save a full camera snapshot.',True)
    add('Camera','cam_record','/cam/?op=cam_record&duration=5','Record video; duration is in seconds.',True)
    commands[-1]['parameters']=[dict(name='duration',required=True,default=None)]
    add('Camera','cam','/cam/?op=cam&local-annotate_text=Roomberry','Set camera controls or local annotation settings.',True)
    add('Roomba','reset_roomba_distance_angle','/roomba/?op=reset_roomba_distance_angle',
        'Reset odometry counters; ends any calibration using that epoch.',True)
    for name,desc in (('soft_stop','Ramp to zero once; an active mission can issue motion again. Use Stop/idle to cancel it.'),('restart_oi','Explicitly restart OI after a stop; requires grounded sensors.')):
        add('Roomba',name,'/roomba/?op='+name,desc,True)
    add('Roomba','_change_mode','/roomba/?op=_change_mode&mode=2','Set OI mode: 1 Passive, 2 Safe, 3 Full.',True)
    commands[-1]['parameters']=[dict(name='mode',required=True,default=None)]
    # Parse signatures without importing GPIO or opening the robot. Properties
    # are sensors/settings, not callable HTTP operations.
    source = Path(__file__).parent/'irobot/robots/create2.py'
    text = source.read_text()
    driver = next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='Create2')
    already = {c['name'] for c in commands}
    for node in driver.body:
        if not isinstance(node,ast.FunctionDef) or node.name.startswith('_') or node.decorator_list or node.name in already:
            continue
        params = node.args.args[1:]
        defaults = [None]*(len(params)-len(node.args.defaults))+list(node.args.defaults)
        add('Roomba',node.name,'/roomba/?op='+node.name,
            'Direct Open Interface command; parameters below. Stop autonomous driving first.',True)
        commands[-1]['parameters']=[dict(name=p.arg,required=default is None,
            default=None if default is None else ast.get_source_segment(text,default)) for p,default in zip(params,defaults)]
    return dict(commands=commands,calibration_acceptance=dict(
        heading_rad=HEADING_LIMIT_RAD,endpoint_tolerance_mm=ENDPOINT_TOLERANCE_MM,
        scans=False,manual_start_alignment=True))


def groundhog_snapshot(receiver, now=None):
    result = dict(enabled=receiver is not None,received=0,rejected=0,
                  motion=None,health=None,compass=None)
    if receiver is None:
        return result
    result.update(received=receiver.received,rejected=receiver.rejected)
    for name,method,ttl in (('motion','latest_ground_observation',1.0),
                            ('health','latest_health_observation',1.0),
                            ('compass','latest_compass_observation',2.5)):
        row = getattr(receiver,method)()
        if row is None:
            continue
        # Framing bytes are not JSON; string identities retain all 64 bits in JS.
        data = {k:(str(v) if k in ('session','calibration','alignment') else v)
                for k,v in row.items() if k not in ('magic','reserved','padding')}
        received = row.get('received_monotonic')
        age = None if received is None else (monotonic() if now is None else now)-received
        data['receive_age_s'] = age
        data['fresh'] = age is not None and 0 <= age <= ttl
        data['usable'] = data['fresh'] and (row['flags']==7 if name=='motion' else
                                           bool(row['flags'] & 1) if name=='compass' else True)
        result[name] = data
    return result


def speech_snapshot(receiver, sender, now=None):
    """Diagnostic snapshot; raw telemetry never implies an authenticated speech peer."""
    now = monotonic() if now is None else now
    relay = None if receiver is None else receiver.trek_control
    configured = relay is not None and sender is not None
    peer_age = None if relay is None or relay.peer is None else max(0, now-relay.last_peer)
    peer_fresh = peer_age is not None and peer_age <= 10
    running = receiver is not None and receiver._thread is not None and receiver._thread.is_alive()
    worker_running = sender is not None and sender._thread is not None and sender._thread.is_alive()
    if not configured:
        detail = 'Speech disabled: configure navlink.command_key_file and the same Documents/NavLink.key in RoomTrek, then restart both.'
    elif not running:
        detail = 'NavLink receiver is not running.'
    elif not worker_running:
        detail = 'Speech worker is not running.'
    elif not peer_fresh:
        detail = 'No fresh authenticated RoomTrek peer. Open RoomTrek in foreground, enable NavLink, and check the matching key and Wi-Fi destination.'
    else:
        detail = 'Authenticated RoomTrek peer ready. Test Speech waits for a phone completion acknowledgment.'
    health = None if receiver is None else receiver.latest_health_observation()
    imu_age = None if health is None else max(0, now-health['received_monotonic'])
    return dict(configured=configured, ready=configured and running and worker_running and peer_fresh,
                worker_running=worker_running,
                detail=detail, peer_age_s=peer_age,
                peer=None if relay is None or relay.peer is None else '{}:{}'.format(*relay.peer),
                received=0 if receiver is None else receiver.received,
                rejected=0 if receiver is None else receiver.rejected,
                imu_received=health is not None and bool(health['flags'] & 1),
                imu_age_s=imu_age)
