# @(#)analyze-run.py 3.2 2026/11/09 17:54:20
import ast,csv,json,math,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'roomberry')
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
from roomberry_trek_anchor import TrekTagAnchor
out=Path('output/tag16-comparison-20261109-1739');meta=json.loads((out/'metrics.json').read_text());anchor=meta['anchor'];lines=Path('roomberry/logs/roomberry.log').read_text().splitlines()
s=list(csv.DictReader(open('roomberry/logs/sensors/roomberry-sensors-20261109-173919.csv')));s=[r for r in s if int(r['odometry_epoch'])==anchor['odometry_epoch']]
t=np.array([float(r['epoch_s']) for r in s]);d=np.array([float(r['distance_mm']) for r in s]);a=np.radians([float(r['angle_deg']) for r in s]);base=anchor['wheel_odometry_at_anchor'];h=a-math.radians(base['angle_deg'])+anchor['tag_robot_pose']['heading_rad'];p=np.zeros((len(t),2))
for i in range(1,len(t)):
 mid=(h[i]+h[i-1])/2;p[i]=p[i-1]+(d[i]-d[i-1])*np.array([math.cos(mid),math.sin(mid)])
# Anchor is stationary between tag capture and binding; use actual capture time.
at=anchor['tag_captured_epoch'];p-=np.array([np.interp(at,t,p[:,j]) for j in (0,1)]);p+=np.array([anchor['tag_robot_pose']['x_mm'],anchor['tag_robot_pose']['y_mm']])
rows=[]
with open('roomberry/logs/navlink/roomberry-navlink-20261109-173919-0000.bin','rb') as f:
 f.read(16)
 while r:=f.read(144):
  v=decode_packet(r[16:]);z=dict(zip(packet_fields(v),v));z['epoch'],z['mono']=[n/1e9 for n in RECEIPT.unpack(r[:16])];rows.append(z)
session=[r for r in rows if r['session']==anchor['session']];clock=min(r['mono']-r['send_us']/1e6 for r in session);epochoff=np.median([r['epoch']-r['mono'] for r in session]);normal=[r for r in session if TrekTagAnchor.usable(r,'optical_forward')];pt=np.array([r['frame_us']/1e6+clock+epochoff for r in normal]);transform=TrekTagAnchor(None,None);transform.anchor=anchor;phone=[transform.transform(r) for r in normal];ph=np.array([[r['x_mm'],r['y_mm']] for r in phone])
fixes=[];cap=None
for l in lines:
 if 'id=15 distance_mm=' in l:cap=float(l.split('captured_at=')[1].rstrip('.'))
 event=None
 if 'WALL event: ' in l:
  z=json.loads(l.split('WALL event: ')[1]);
  if z['event']=='tag15_lucky_found':event=dict(pose=z['pose'],purpose='WALL first confirmed tag15',accepted=True)
 elif 'Return to tag 15 scan: ' in l:event=ast.literal_eval(l.split('Return to tag 15 scan: ')[1])
 if event:
  pose=event['pose'];xy=np.array([pose['x_mm'],pose['y_mm']]);wheel=np.array([np.interp(cap,t,p[:,j]) for j in (0,1)]);dh=math.degrees(math.atan2(math.sin(pose['heading_rad']-np.interp(cap,t,h)),math.cos(pose['heading_rad']-np.interp(cap,t,h))))
  f=dict(capture_epoch=cap,purpose=event['purpose'],confirmed=event['accepted'],tag_x_mm=xy[0],tag_y_mm=xy[1],tag_range_mm=float(np.linalg.norm(xy-np.array([7730,790]))),wheel_x_mm=wheel[0],wheel_y_mm=wheel[1],wheel_vs_tag_mm=float(np.linalg.norm(wheel-xy)),tag_minus_wheel_heading_deg=dh,local_innovation=event.get('innovation'))
  if pt[0]<=cap<=pt[-1]:
   phxy=np.array([np.interp(cap,pt,ph[:,j]) for j in (0,1)]);f.update(phone_x_mm=phxy[0],phone_y_mm=phxy[1],phone_vs_tag_mm=float(np.linalg.norm(phxy-xy)),phone_vs_wheel_mm=float(np.linalg.norm(phxy-wheel)))
  fixes.append(f)
(out/'tag-checks.json').write_text(json.dumps(fixes,indent=2)+'\n');print(json.dumps(fixes,indent=2))
c=list(csv.DictReader(open(out/'disagreement.csv')))
for tt in [1794274908.411,1794275039.759]:
 z=min(c,key=lambda r:abs(float(r['seconds_from_tag16'])+anchor['tag_captured_epoch']-tt));print('AT',tt,z,'separation',math.hypot(float(z['dx_mm']),float(z['dy_mm'])))
print('final headingmax',max(abs(float(r['heading_delta_deg'])) for r in c))
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axs=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
use=(t>=at)&(t<=fixes[-1]['capture_epoch'])
axs[0].plot(p[use,0]/1000,p[use,1]/1000,label='Pure wheels, including commanded return')
axs[0].plot(ph[:,0]/1000,ph[:,1]/1000,label='iPhone: WALL session only')
accepted=[r for r in fixes if r['confirmed']]
axs[0].scatter([r['tag_x_mm']/1000 for r in accepted],[r['tag_y_mm']/1000 for r in accepted],label='Measured tag15 robot positions',c='green')
axs[0].scatter([7.73],[.79],marker='s',c='black',label='Tag15')
for r in accepted:
 axs[0].plot([r['wheel_x_mm']/1000,r['tag_x_mm']/1000],[r['wheel_y_mm']/1000,r['tag_y_mm']/1000],ls=':',c='gray')
axs[0].axis('equal');axs[0].set(xlabel='Room X (m)',ylabel='Room Y (m)',title='Tag16 reference; no path/scale fitting');axs[0].legend(fontsize=7)
xx=[r['capture_epoch']-at for r in accepted]
axs[1].plot(xx,[r['wheel_vs_tag_mm'] for r in accepted],'o-',label='Pure wheel error vs measured tags')
local=[r for r in accepted if r['local_innovation'] is not None]
axs[1].plot([r['capture_epoch']-at for r in local],[r['local_innovation'][0] for r in local],'o-',label='Controller correction since recent tag fix')
axs[1].set(xlabel='Seconds since tag16',ylabel='Position difference (mm)',title='Independent trace vs corrected controller');axs[1].legend(fontsize=8)
for ax in axs:ax.grid(alpha=.3)
fig.suptitle('WALL + commanded return: wheel, iPhone and tag15 checks (new iPhone return session is not aligned)')
fig.savefig(out/'tag-checks.png',dpi=160);fig.savefig(out/'tag-checks.pdf')
