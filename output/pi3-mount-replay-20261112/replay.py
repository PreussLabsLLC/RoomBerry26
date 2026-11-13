# @(#)replay.py 3.2.mount.2 2026/11/12 12:53:19
"""Replay immutable recorded tracks with old/new extrinsics; no trajectory fitting."""
import ast, csv, json, math, os, sys
from pathlib import Path
from datetime import datetime
os.environ.setdefault('MPLCONFIGDIR', '/tmp/roomberry-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OLD=ROOT/'output/pi3-roundtrip-20261112-122222'
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_map_image import render_map
config=json.loads((OUT/'replay-config.json').read_text())
metrics=json.loads((OLD/'metrics.json').read_text())
rows=list(csv.DictReader((OLD/'comparison.csv').open()))
ts=np.array([float(r['epoch_s']) for r in rows])
wheel=np.array([[float(r['wheel_x_mm']),float(r['wheel_y_mm'])] for r in rows])
phone=np.array([[float(r['phone_x_mm']),float(r['phone_y_mm'])] for r in rows])
valid=np.array([r['usable']=='True' for r in rows])
rot=lambda h:np.array([[math.cos(h),-math.sin(h)],[math.sin(h),math.cos(h)]])
wrap=lambda h:math.atan2(math.sin(h),math.cos(h))
interp=lambda t,v: np.array([np.interp(t,ts,v[:,i]) for i in range(v.shape[1])]) if v.ndim==2 else np.interp(t,ts,v)
log=(OUT/'capture-evidence.txt').read_text()
live_anchor=None
fixes=[]
for line in log.splitlines():
    if line[:19]<'2026-11-12 12:22:22': continue
    if 'RoomTrek tag16 alignment: ' in line:
        live_anchor=json.loads(line.split('RoomTrek tag16 alignment: ',1)[1])
    if 'Idle AprilTag localization: pose={' not in line: continue
    p,tail=line.split('pose=',1)[1].split(' detections=',1)
    pose=ast.literal_eval(p)
    if not pose['accepted_tag_ids']: continue
    tag=pose['accepted_tag_ids'][0][1]
    detection=next(d[2] for d in ast.literal_eval(tail.split(' rejected=',1)[0]) if d[1]==tag)
    # Pair to original recorded capture time; log publication is delayed.
    oldfix=min((f for f in metrics['tag_fixes'] if f['tag']==tag), key=lambda f:abs(f['log_t']-datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()))
    world_tag=np.array(next(x['world_from_tag'] for x in config['landmarks'] if x['id']==tag))
    camera_tag=np.eye(4);camera_tag[:3,:3]=detection['rotation'];camera_tag[:3,3]=detection['translation_m']
    world_camera=world_tag@np.linalg.inv(camera_tag)
    world_robot=world_camera@np.array(config['camera_from_robot'])
    new_pose=dict(x_mm=float(world_robot[0,3]*1000),y_mm=float(world_robot[1,3]*1000),heading_rad=math.atan2(world_robot[1,0],world_robot[0,0]))
    fixes.append(dict(tag=tag,t=oldfix['t'],old=pose,new=new_pose))
assert live_anchor and len(fixes)==3
initial=fixes[0]
a=initial['old'];b=initial['new']
old_origin=np.array([a['x_mm'],a['y_mm']]);new_origin=np.array([b['x_mm'],b['y_mm']])
old_lens=np.array(live_anchor['lens_offset_mm']);new_lens=np.array([config['roomtrek_alignment']['lens_x_mm'],config['roomtrek_alignment']['lens_y_mm']])
sensors=list(csv.DictReader((ROOT/'roomberry/logs/sensors/roomberry-sensors-20261112-122222.csv').open()))
st=np.array([float(r['epoch_s']) for r in sensors]);angles=np.radians([float(r['angle_deg']) for r in sensors])
wheel_heading=np.interp(ts,st,angles)+a['heading_rad']-np.interp(initial['t'],st,angles)
phone_heading=np.unwrap(wheel_heading+np.radians([float(r['phone_minus_wheel_heading_deg']) for r in rows]))
new_heading=phone_heading+b['heading_rad']-a['heading_rad']
delta=b['heading_rad']-a['heading_rad']-math.radians(config['roomtrek_alignment']['mount_yaw_deg'])+live_anchor['mount_yaw_rad']
old_camera_delta=phone+np.array([rot(h)@old_lens for h in phone_heading])-old_origin-rot(a['heading_rad'])@old_lens
updated_phone=old_camera_delta@rot(delta).T+new_origin+rot(b['heading_rad'])@new_lens-np.array([rot(h)@new_lens for h in new_heading])
updated_wheel=(wheel-old_origin)@rot(b['heading_rad']-a['heading_rad']).T+new_origin
for f in fixes:
    t=f['t'];oldxy=np.array([f['old']['x_mm'],f['old']['y_mm']]);newxy=np.array([f['new']['x_mm'],f['new']['y_mm']])
    f.update(old_phone_error_mm=float(np.linalg.norm(interp(t,phone)-oldxy)),new_phone_error_mm=float(np.linalg.norm(interp(t,updated_phone)-newxy)),old_wheel_error_mm=float(np.linalg.norm(interp(t,wheel)-oldxy)),new_wheel_error_mm=float(np.linalg.norm(interp(t,updated_wheel)-newxy)),tag_shift_mm=float(np.linalg.norm(oldxy-newxy)))
state=json.loads((ROOT/'roomberry/logs/map-state-reset-20261031-01.json').read_text());state['pose']=None
markers=[(x['world_from_tag'][0][3]*1000,x['world_from_tag'][1][3]*1000,x['id'],math.atan2(-x['world_from_tag'][1][2],-x['world_from_tag'][0][2])) for x in config['landmarks']]
mask=(ts>=initial['t'])&(ts<=fixes[-1]['t'])&valid
for name,p,w,label in [('map-before.png',phone,wheel,'Previous mount values'),('map.png',updated_phone,updated_wheel,'Remeasured mounts; replay of run122222')]:
    state['run_trails']=dict(wheel=w[mask].tolist(),iphone=p[mask].tolist())
    (OUT/name).write_bytes(render_map(state,markers,caption=label))
summary=dict(old_mount=dict(lens_mm=old_lens.tolist(),mount_yaw_deg=math.degrees(live_anchor['mount_yaw_rad'])),new_mount=config['roomtrek_alignment'],translation_rotation_change_deg=math.degrees(delta),fixes=fixes)
(OUT/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axs=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
for ax,p,w,key,title in [(axs[0],phone,wheel,'old','Previous measurements'),(axs[1],updated_phone,updated_wheel,'new','Remeasured mounts')]:
    ax.plot(w[mask,0]/1000,w[mask,1]/1000,label='Wheels',color='#1964d2')
    ax.plot(p[mask,0]/1000,p[mask,1]/1000,label='iPhone',color='#9b2db9')
    for f in fixes:
        ax.scatter(f[key]['x_mm']/1000,f[key]['y_mm']/1000,c='black',marker='x');ax.annotate('scan '+str(f['tag']),(f[key]['x_mm']/1000,f[key]['y_mm']/1000))
    ax.set(title=title,xlabel='Room X (m)',ylabel='Room Y (m)',xlim=(2.8,8),ylim=(-.7,max(float(wheel[mask,1].max()),float(updated_wheel[mask,1].max()))/1000+.15));ax.set_aspect('equal');ax.grid(alpha=.3);ax.legend()
fig.savefig(OUT/'comparison.png',dpi=160);fig.savefig(OUT/'comparison.pdf');plt.close(fig)
print(json.dumps(summary,indent=2))

# Update the previously linked preview, retaining its original rendering.
previous=OLD/'map.png'
preserved=OLD/'map-before-remeasurement.png'
if previous.exists() and not preserved.exists(): preserved.write_bytes(previous.read_bytes())
previous.write_bytes((OUT/'map.png').read_bytes())
