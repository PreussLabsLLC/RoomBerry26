"""Read-only local dashboard data and a command index from the shipped driver."""
# @(#)roomberry_web.py 3.1.web.1 2026/10/31 14:00:00
import ast
from functools import lru_cache
from pathlib import Path
from time import monotonic

from roomberry_calibration import (HEADING_LIMIT_RAD, LATERAL_LIMIT_MM,
    RETURN_ERROR_LIMIT_MM, START_GAP_MIN_MM, START_GAP_MAX_MM)

ASSET_ROOT = Path(__file__).with_name('web')
ASSETS = {'/': ('index.html','text/html; charset=utf-8'),
          '/index.html': ('index.html','text/html; charset=utf-8'),
          '/ui/': ('index.html','text/html; charset=utf-8'),
          '/ui/app.js': ('app.js','application/javascript; charset=utf-8'),
          '/ui/style.css': ('style.css','text/css; charset=utf-8')}


@lru_cache(maxsize=1)
def command_index():
    commands = []
    def add(group, name, url, description, mutates=False, aliases=()):
        commands.append(dict(group=group,name=name,url=url,description=description,
                             mutates=mutates,aliases=list(aliases),parameters=[]))
    add('Mission','calibrate','/roomba/?op=calibrate','Run tag-15 out-and-back calibration.',True,('cal','calibration'))
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
    add('Camera','request_scan','/cam/?op=request_scan','Request a scan; moving calibration stages skip scans.',True)
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
        heading_rad=HEADING_LIMIT_RAD,lateral_mm=LATERAL_LIMIT_MM,
        return_error_mm=RETURN_ERROR_LIMIT_MM,start_gap_mm=[START_GAP_MIN_MM,START_GAP_MAX_MM]))


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
