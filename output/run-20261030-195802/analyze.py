# @(#)analyze.py 2.3.analysis.7 2026/10/30 17:25:00
"""Latest ride-along: receipt-delay correction and measured camera lever arm."""
import ast
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_navlink import PACKET,FIELDS
def stamp(t):return datetime.fromtimestamp(t).strftime('%H:%M:%S')
def epoch(s):return datetime.strptime('2026-10-30 '+s,'%Y-%m-%d %H:%M:%S').timestamp()
def wrap(a):return (a+np.pi)%(2*np.pi)-np.pi
def rotation(a):return np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
for dest,source in [('mission.log','roomberry.log'),('map-state.json','map-state-reset-20261030-01.json'),('map.png','map.png')]:
    if not (OUT/dest).exists():(OUT/dest).write_bytes((ROOT/'roomberry/logs'/source).read_bytes())
b=(ROOT/'roomberry/logs/navlink/roomberry-navlink-20261030-195802-0000.bin').read_bytes()
nav=[]
for i in range(16,len(b)-143,144):
    r=dict(zip(FIELDS,PACKET.unpack(b[i+16:i+144])));r['receipt_s']=int.from_bytes(b[i:i+8],'little')/1e9;nav.append(r)
def nf(k):return np.array([r[k]for r in nav])
send=nf('send_us')/1e6;receipt=nf('receipt_s');offset=min(receipt-send)
nt=nf('frame_us')/1e6+offset;assembly=send+offset
valid=nf('flags').astype(int)&1!=0
xy=np.array([nf('x_mm'),nf('y_mm')]).T;heading=np.unwrap(nf('heading_rad'))
sensor=list(csv.DictReader(open(ROOT/'roomberry/logs/sensors/roomberry-sensors-20261030-195802.csv')))
def sf(k):return np.array([float(r[k]or 0)for r in sensor])
st=sf('epoch_s');distance=sf('distance_mm');angle=sf('angle_deg')
k=5;dd=np.interp(nt,st,distance)[k:]-np.interp(nt,st,distance)[:-k]
da=np.interp(nt,st,angle)[k:]-np.interp(nt,st,angle)[:-k];delta=xy[k:]-xy[:-k]
ok=(abs(dd)>20)&(abs(da)<2)&valid[k:]&valid[:-k]&(nt[k:]-nt[:-k]<.7)&(nt[k:]<epoch('20:07:35'))
mount_offsets=wrap(np.arctan2(delta[:,1],delta[:,0])-heading[:-k]-np.where(dd<0,np.pi,0))
mount_yaw=np.radians(93.6)  # Keep the deployed mounting calibration fixed across runs.
body_heading=heading+mount_yaw
lever=np.array([rotation(a)@np.array([-145.,-22.])for a in body_heading])
axle=xy-lever
poses=[]
lines=(OUT/'mission.log').read_text().splitlines()
for line in lines:
    m=re.search(r"pose=(\{'x_mm':.*?\})",line)
    if m:poses.append((datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp(),ast.literal_eval(m[1]),line))
stop=epoch('20:07:30')+.810
stop_p=poses[-1][1]
poses.sort(key=lambda r:r[0])
anchor_t,anchor,_=next(v for v in poses if 'Discovery retreat_scan:' in v[2])
ai=np.argmin(abs(nt-anchor_t));rot=anchor['heading_rad']-body_heading[ai]
aligned=(axle-axle[ai])@rotation(rot).T+[anchor['x_mm'],anchor['y_mm']]
aligned_h=body_heading+rot
rows=[]
for t,p,line in poses:
    if not epoch('19:58:25')<t<epoch('20:07:35'):continue
    i=np.argmin(abs(nt-t))
    if not valid[i]or abs(nt[i]-t)>.2:continue
    rows.append(dict(time=stamp(t),epoch_s=t,room_x_mm=p['x_mm'],room_y_mm=p['y_mm'],
        room_heading_deg=np.degrees(p['heading_rad']),phone_x_mm=aligned[i,0],phone_y_mm=aligned[i,1],
        separation_mm=np.linalg.norm(aligned[i]-[p['x_mm'],p['y_mm']]),
        roomba_travelled_cm=(np.interp(t,st,sf('travelled_distance_mm'))-sf('travelled_distance_mm')[0])/10,
        heading_difference_deg=np.degrees(wrap(p['heading_rad']-aligned_h[i])),
        tag_age_s=p['localization_age'],features=int(nf('feature_count')[i]),event=line.split(' - ')[-1].split('pose=')[0]))
for row in rows:
    travel_mm = row['roomba_travelled_cm'] * 10
    row['disagreement_pct'] = (100 * row['separation_mm'] / travel_mm
                               if travel_mm > 0 else None)
with (OUT/'pose-comparison.csv').open('w')as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
changes=[];last=None
for r,t in zip(nav,assembly):
    pair=(r['battery_pct'],r['battery_state'])
    if pair!=last:changes.append(dict(time=stamp(t),level=pair[0],state=pair[1]));last=pair
summary=dict(records=len(nav),valid_pose_packets=int(sum(valid)),feature_median=float(np.median(nf('feature_count')[valid])),
    mount_yaw_deg=float(np.degrees(mount_yaw)),yaw_fit_windows=int(sum(ok)),coverage=[stamp(receipt[0]),stamp(receipt[-1])],
    max_excess_receipt_delay_s=float(max(receipt-send-offset)),battery_changes=changes,
    stop_robot_xy_mm=[stop_p['x_mm'],stop_p['y_mm']],stop_phone_xy_mm=aligned[np.argmin(abs(nt-stop))].tolist())
step=np.linalg.norm(np.diff(axle,axis=0),axis=1)
motion_ok=valid[:-1]&valid[1:]&(np.diff(nt)<.2)&(nt[1:]<stop)&(nt[:-1]>=anchor_t)
summary['max_valid_axle_step_mm']=float(max(step[motion_ok]))
summary['sequence_discontinuities']=int(sum(np.diff(nf('seq'))!=1))
gaps=[]
start=None
for i,usable in enumerate(valid):
    if not usable and start is None:start=i
    if usable and start is not None:
        gaps.append(dict(start=stamp(nt[start]),end=stamp(nt[i]),duration_s=float(nt[i]-nt[start]),
                         tracking=int(nav[start]['tracking']),reason=int(nav[start]['reason'])))
        start=None
if start is not None:
    gaps.append(dict(start=stamp(nt[start]),end=stamp(nt[-1]),duration_s=float(nt[-1]-nt[start]),
                     tracking=int(nav[start]['tracking']),reason=int(nav[start]['reason'])))
summary['tracking_gaps']=gaps
summary['sessions']=len(set(r['session'] for r in nav))
summary['alignments']=len(set(r['alignment'] for r in nav))
summary['stop_roomba_travelled_cm'] = float((np.interp(stop,st,sf('travelled_distance_mm'))-sf('travelled_distance_mm')[0])/10)
summary['stop_separation_mm'] = float(np.linalg.norm(np.array(summary['stop_phone_xy_mm'])-summary['stop_robot_xy_mm']))
travel_mm = summary['stop_roomba_travelled_cm'] * 10
summary['stop_disagreement_pct'] = 100 * summary['stop_separation_mm'] / travel_mm if travel_mm > 0 else None
(OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
table = ['| Point in run | Roomba travel (cm) | Position disagreement (cm) | Disagreement (%) |',
         '|---|---:|---:|---:|']
selected = {'19:59:06': 'Approaching tag 2', '19:59:21': 'After tag 2 fix', '19:59:44': '19:59:44', '20:02:12': '20:02:12', '20:02:47': 'Before tag 15 fix', '20:03:14': 'After first tag 15 fix', '20:03:38': 'After second tag 15 fix', '20:04:17': 'Blocked and stationary'}
for row in rows:
    if row['time'] in selected:
        percentage = '—' if row['disagreement_pct'] is None else f"{row['disagreement_pct']:.1f}%"
        table.append(f"| {selected[row['time']]} | {row['roomba_travelled_cm']:.1f} | {row['separation_mm']/10:.1f} | {percentage} |")
percentage = '—' if summary['stop_disagreement_pct'] is None else f"{summary['stop_disagreement_pct']:.1f}%"
table.append(f"| Before pickup | {summary['stop_roomba_travelled_cm']:.1f} | {summary['stop_separation_mm']/10:.1f} | {percentage} |")
(OUT/'comparison.md').write_text('\n'.join(table) + '\n\nDisagreement (%) = 100 × position separation / cumulative Roomba travel. '
                                'Travel includes forward and reverse movement from the start of recording. '
                                'Percentage is undefined at zero travel. Positions use the retreat tag fix as their alignment anchor; '
                                'this is relative disagreement, not surveyed accuracy.\n')
for r in rows:print(r['time'],round(r['separation_mm']),round(r['heading_difference_deg'],1),'feature',r['features'],r['event'][:85])
font=lambda size:ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',size)
im=Image.new('RGB',(1450,950),'white');d=ImageDraw.Draw(im)
d.text((50,25),'October 30, 19:58 run — corrected iPhone axle trajectory',font=font(31),fill='#182536')
d.text((50,75),'Lens offset: 145 mm rearward, 22 mm rightward. Fixed room alignment at retreat tag fix.',font=font(21),fill='#526175')
select=valid&(nt>=anchor_t)&(nt<=stop)
pts=np.vstack([aligned[select],[[r['room_x_mm'],r['room_y_mm']]for r in rows],[[3100,1450],[3100,950]]])/1000
lo=pts.min(axis=0)-.2;hi=pts.max(axis=0)+.2;scale=min(1220/(hi[0]-lo[0]),620/(hi[1]-lo[1]))
def pixel(p):
    p=np.asarray(p)/1000
    return(105+(p[0]-lo[0])*scale,760-(p[1]-lo[1])*scale)
for axis in(0,1):
    for v in np.arange(np.ceil(lo[axis]*2)/2,hi[axis],.5):
        a=lo.copy();z=hi.copy();a[axis]=z[axis]=v
        d.line([pixel(a*1000),pixel(z*1000)],fill='#e4e8ee')
        q=pixel(a*1000);d.text((q[0],785)if axis==0 else(75,q[1]),f'{v:g}',font=font(18),fill='#526175',anchor='mt'if axis==0 else'rm')
d.line([pixel((r['room_x_mm'],r['room_y_mm']))for r in rows],fill='#c43c26',width=4)
indices=np.where(select)[0]
for a,b in zip(indices,indices[1:]):
    if b==a+1 and nt[b]-nt[a]<=.3:
        d.line([pixel(aligned[a]),pixel(aligned[b])],fill='#1769aa',width=4)
for label,p in [('Tag 16',(3100,950)),('Tag 16 parking goal',(3100,1450))]:
    q=pixel(p);d.ellipse((q[0]-5,q[1]-5,q[0]+5,q[1]+5),fill='#222');d.text((q[0]-12,q[1]-15),label,font=font(18),anchor='rm',fill='#222')
for label,p,color in [('Phone at stop',summary['stop_phone_xy_mm'],'#1769aa'),('Robot at stop',summary['stop_robot_xy_mm'],'#c43c26')]:
    q=pixel(p);d.ellipse((q[0]-6,q[1]-6,q[0]+6,q[1]+6),fill=color);d.text((q[0]+10,q[1]+10),label,font=font(18),fill=color)
d.text((50,840),'Blue: corrected phone center. Red: sparse robot poses, including tag corrections. Axes in metres.',font=font(21),fill='#182536')
d.text((50,885),'Alignment and AR accuracy remain uncertain. Neither trace is surveyed ground truth.',font=font(20),fill='#526175')
im.save(OUT/'trajectory.png')
