# @(#)analyze.py 2.3.analysis.2 2026/10/30 15:25:00
"""Ride-along comparison with the measured rear/right camera lever arm."""
import ast
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT/'roomberry'))
from roomberry_navlink import PACKET, FIELDS

def stamp(t): return datetime.fromtimestamp(t).strftime('%H:%M:%S')
def epoch(s): return datetime.strptime('2026-10-30 '+s, '%Y-%m-%d %H:%M:%S').timestamp()
def wrap(v): return (v+np.pi) % (2*np.pi)-np.pi
def rotation(a): return np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])

# Preserve the mission/map input before a future log download replaces them.
for dest, src in [('mission.log','roomberry.log'),('map-state.json','map-state-reset-20261030-01.json')]:
    if not (OUT/dest).exists(): (OUT/dest).write_bytes((ROOT/'roomberry/logs'/src).read_bytes())
b = (ROOT/'roomberry/logs/navlink/roomberry-navlink-20261030-151054-0000.bin').read_bytes()
records=[]
for i in range(16,len(b)-143,144):
    row=dict(zip(FIELDS,PACKET.unpack(b[i+16:i+144])))
    row['receipt_s']=int.from_bytes(b[i:i+8],'little')/1e9
    records.append(row)
def nf(k): return np.array([r[k] for r in records])
receipt=nf('receipt_s');send=nf('send_us')/1e6
clock_offset=min(receipt-send)
nt=nf('frame_us')/1e6+clock_offset
assembly=send+clock_offset
valid=(nf('flags').astype(int)&1)!=0
xy=np.array([nf('x_mm'),nf('y_mm')]).T
heading=np.unwrap(nf('heading_rad'))
sensors=list(csv.DictReader(open(ROOT/'roomberry/logs/sensors/roomberry-sensors-20261030-151054.csv')))
def sf(k): return np.array([float(r[k] or 0) for r in sensors])
st=sf('epoch_s');distance=sf('distance_mm');angle=sf('angle_deg')

# Fit only the unknown mounting yaw from straight, signed wheel translation.
# Translation offset itself is the user's measurement, never fitted to the map.
k=5
dd=np.interp(nt,st,distance)[k:]-np.interp(nt,st,distance)[:-k]
da=np.interp(nt,st,angle)[k:]-np.interp(nt,st,angle)[:-k]
delta=xy[k:]-xy[:-k]
ok=(abs(dd)>20)&(abs(da)<2)&valid[k:]&valid[:-k]&(nt[k:]-nt[:-k]<.7)&(nt[k:]<epoch('15:14:21'))
offsets=wrap(np.arctan2(delta[:,1],delta[:,0])-heading[:-k]-np.where(dd<0,np.pi,0))
mount_yaw=np.angle(np.mean(np.exp(1j*offsets[ok])))
forward=heading+mount_yaw
# Robot axes: X forward, Y left. The camera is 145 mm aft and 22 mm right.
camera_offset=np.array([-145.,-22.])
lever=np.array([rotation(a)@camera_offset for a in forward])
axle_session=xy-lever
poses=[]
for line in (OUT/'mission.log').read_text().splitlines():
    m=re.search(r"pose=(\{'x_mm':.*?\})",line)
    if m:
        p=ast.literal_eval(m[1]);t=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()
        poses.append((t,p,line))
stop_pose=next(v[1] for v in poses if '15:14:22,039' in v[2])
poses.append((epoch('15:14:21')+.171,stop_pose,'Discovery stopped: stationary pose logged 0.87 s later pose='))
poses.sort(key=lambda item:item[0])

anchors=[next(v for v in poses if 'Discovery retreat_scan:' in v[2]),
         next(v for v in poses if 'Stationary AprilTag scan requested:' in v[2] and '15:13:33' in v[2])]
# The second comparison anchor is the last accepted tag-1 fix. Its full pose
# is not printed at acceptance, so recover it from the later stationary pose
# using the same wheel integration as the localizer, inverted sample by sample.
later_t,later_p,_=anchors[1]
fix_line=next(l for l in (OUT/'mission.log').read_text().splitlines() if '15:13:12,978' in l)
fix_t=datetime.strptime(fix_line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()
# Keep this auxiliary estimate separate from the directly logged anchor.
rev=dict(later_p)
ix0=np.argmin(abs(st-fix_t));ix1=np.argmin(abs(st-later_t))
for j in range(ix1,ix0,-1):
    d=distance[j]-distance[j-1];a=np.radians(angle[j]-angle[j-1])
    middle=rev['heading_rad']-a/2
    rev['x_mm']-=d*np.cos(middle);rev['y_mm']-=d*np.sin(middle)
    rev['heading_rad']-=a
anchors[1]=(fix_t,rev,'reconstructed last tag-1 fix')

def align(anchor):
    t,p,_=anchor;i=np.argmin(abs(nt-t));assert valid[i]
    yaw=p['heading_rad']-forward[i]
    positions=(axle_session-axle_session[i])@rotation(yaw).T+[p['x_mm'],p['y_mm']]
    return positions,heading+mount_yaw+yaw
aligned,aligned_heading=align(anchors[0])
recent,recent_heading=align(anchors[1])
comparison=[]
for t,p,line in poses:
    if not epoch('15:11:41')<=t<=epoch('15:14:22'):continue
    i=np.argmin(abs(nt-t))
    if not valid[i] or abs(nt[i]-t)>.2:continue
    point=np.array([p['x_mm'],p['y_mm']])
    comparison.append(dict(time=stamp(t),epoch_s=t,room_x_mm=point[0],room_y_mm=point[1],
        phone_axle_x_mm=aligned[i,0],phone_axle_y_mm=aligned[i,1],
        separation_mm=np.linalg.norm(aligned[i]-point),
        separation_since_last_fix_mm=np.linalg.norm(recent[i]-point),
        heading_difference_deg=np.degrees(wrap(p['heading_rad']-aligned_heading[i])),
        recent_heading_difference_deg=np.degrees(wrap(p['heading_rad']-recent_heading[i])),
        tag_age_s=p['localization_age'],event=line.split(' - ')[-1].split('pose=')[0]))
with (OUT/'pose-comparison.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=comparison[0].keys());w.writeheader();w.writerows(comparison)

changes=[];last=None
for r,t in zip(records,assembly):
    pair=(r['battery_pct'],r['battery_state'])
    if pair!=last:
        changes.append(dict(time=stamp(t),battery_pct=pair[0],battery_state=pair[1]));last=pair
metrics=dict(records=len(records),mount_yaw_deg=float(np.degrees(mount_yaw)),yaw_fit_intervals=int(sum(ok)),
    valid_pose_packets=int(sum(valid)),invalid_pose_packets=int(sum(~valid)),
    feature_median=float(np.median(nf('feature_count')[valid])),battery_changes=changes,
    coverage=[stamp(receipt[0]),stamp(receipt[-1])],
    extra_receipt_delay_max_s=float(max(receipt-send-clock_offset)))
(OUT/'summary.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics,indent=2))
for r in comparison:
    print(r['time'],round(r['separation_mm']),round(r['heading_difference_deg'],1),
          'since last fix',round(r['separation_since_last_fix_mm']),round(r['recent_heading_difference_deg'],1),r['event'][:90])

# Export a standalone plot; omit invalid poses and stop at the mission halt.
font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
def font(n):return ImageFont.truetype(font_path,n)
im=Image.new('RGB',(1500,1000),'white');d=ImageDraw.Draw(im)
d.text((55,25),'iPhone axle estimate versus Roomberry — October 30, 15:10 run',font=font(31),fill='#182536')
d.text((55,75),'Camera offset corrected: 145 mm rearward, 22 mm rightward. Fixed alignment at retreat tag fix.',font=font(21),fill='#526175')
plotted=valid&(nt>=anchors[0][0])&(nt<=epoch('15:14:22'))
pts=np.vstack([aligned[plotted],[[r['room_x_mm'],r['room_y_mm']]for r in comparison],[[3100,1450],[3100,950]]])/1000
lo=pts.min(axis=0)-.25;hi=pts.max(axis=0)+.25
scale=min(1270/(hi[0]-lo[0]),650/(hi[1]-lo[1]))
def pixel(p):
    p=np.asarray(p)/1000
    return (110+(p[0]-lo[0])*scale,800-(p[1]-lo[1])*scale)
for axis in (0,1):
    for v in np.arange(np.ceil(lo[axis]*2)/2,hi[axis],.5):
        a=lo.copy();z=hi.copy();a[axis]=z[axis]=v
        d.line([pixel(a*1000),pixel(z*1000)],fill='#e4e8ee',width=1)
        q=pixel(a*1000)
        d.text((q[0],825)if axis==0 else (75,q[1]),f'{v:g}',font=font(19),fill='#526175',anchor='mt'if axis==0 else 'rm')
d.line([pixel([r['room_x_mm'],r['room_y_mm']])for r in comparison],fill='#c43c26',width=4)
indices=np.where(plotted)[0];segment=[];last_i=None
for i in indices:
    if last_i is not None and (i!=last_i+1 or nt[i]-nt[last_i]>.3):
        if len(segment)>1:d.line(segment,fill='#1769aa',width=4)
        segment=[]
    segment.append(pixel(aligned[i]));last_i=i
if len(segment)>1:d.line(segment,fill='#1769aa',width=4)
for name,p in [('Tag 16',(3100,950)),('Tag 16 parking goal',(3100,1450))]:
    q=pixel(p);d.ellipse((q[0]-6,q[1]-6,q[0]+6,q[1]+6),fill='#222')
    d.text((q[0]-15,q[1]-20),name,font=font(19),anchor='rm',fill='#222')
for col,row in [(x,y)for y,line in enumerate(json.loads((OUT/'map-state.json').read_text())['occupancy'])for x,v in enumerate(line)if v=='blocked']:
    q=pixel(((col+.5)*87,(row+.5)*87));d.rectangle((q[0]-6,q[1]-6,q[0]+6,q[1]+6),fill='#111')
d.text((55,880),'Blue: corrected phone axle trajectory. Red: sparse logged robot poses, including tag corrections.',font=font(22),fill='#182536')
d.text((55,925),'Axes in metres. Phone tracking quality and room alignment remain uncertain; neither path is surveyed truth.',font=font(21),fill='#526175')
im.save(OUT/'trajectory.png')

im=Image.new('RGB',(1500,650),'white');d=ImageDraw.Draw(im)
d.text((65,25),'iPhone battery — latest run',font=font(34),fill='#182536')
x=lambda t:120+(t-assembly[0])/(assembly[-1]-assembly[0])*1240
y=lambda b:490-(b-70)/30*340
for v in range(70,101,5):
    d.line((120,y(v),1360,y(v)),fill='#dce2e9',width=1)
    d.text((100,y(v)),f'{v}%',font=font(21),fill='#526175',anchor='rm')
start=None
for i,state in enumerate(nf('battery_state')):
    if state==2 and start is None:start=i
    if start is not None and (state!=2 or i==len(records)-1):
        d.rectangle((x(assembly[start]),150,x(assembly[i]),490),fill='#e7f4e9');start=None
points=[]
for i,t in enumerate(assembly):
    if i:points.append((x(t),y(records[i-1]['battery_pct'])))
    points.append((x(t),y(records[i]['battery_pct'])))
d.line(points,fill='#1769aa',width=4)
for minute in range(6):
    t=epoch('15:11:00')+minute*60
    if assembly[0]<=t<=assembly[-1]:d.text((x(t),510),stamp(t)[:5],font=font(21),fill='#526175',anchor='mt')
d.text((65,575),'82% at start → 83% at end. Green: reported charging; white: reported unplugged.',font=font(25),fill='#182536')
im.save(OUT/'battery.png')
