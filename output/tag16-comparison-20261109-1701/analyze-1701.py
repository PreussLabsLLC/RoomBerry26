# @(#)analyze-1701.py 3.2 2026/11/09 17:13:08
import ast,csv,json,math,os,re,sys
from pathlib import Path
from datetime import datetime
from collections import Counter
import numpy as np
os.environ['MPLCONFIGDIR']='/tmp/roomberry-matplotlib'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,'roomberry')
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
out=Path('output/tag16-comparison-20261109-1701')
lines=Path('roomberry/logs/roomberry.log').read_text().splitlines()
anchor=next(json.loads(l.split('WALL event: ')[1])['pose'] for l in lines if '"event": "tag16_anchor"' in l)
cap16=1794272526.339480
s=list(csv.DictReader(open('roomberry/logs/sensors/roomberry-sensors-20261109-170134.csv')))
t=np.array([float(r['epoch_s']) for r in s]);d=np.array([float(r['distance_mm']) for r in s]);a=np.radians([float(r['angle_deg']) for r in s]);h=a-np.interp(cap16,t,a)+anchor['heading_rad']
p=np.zeros((len(t),2))
for i in range(1,len(t)):
 mid=(h[i]+h[i-1])/2;p[i]=p[i-1]+(d[i]-d[i-1])*np.array([math.cos(mid),math.sin(mid)])
p-=np.array([np.interp(cap16,t,p[:,j]) for j in (0,1)]);p+=np.array([anchor['x_mm'],anchor['y_mm']])
fixes=[];capture=None
for l in lines:
 if 'id=15 distance_mm=' in l:capture=float(re.search(r'captured_at=([\d.]+)',l)[1].rstrip('.'))
 if 'Return to tag 15 scan: ' in l:
  rec=ast.literal_eval(l.split('Return to tag 15 scan: ')[1]);pose=rec['pose'];w=np.array([np.interp(capture,t,p[:,j]) for j in (0,1)]);tag=np.array([pose['x_mm'],pose['y_mm']]);dh=math.degrees(math.atan2(math.sin(pose['heading_rad']-np.interp(capture,t,h)),math.cos(pose['heading_rad']-np.interp(capture,t,h))))
  fixes.append(dict(capture_epoch=capture,time=datetime.fromtimestamp(capture).isoformat(),purpose=rec['purpose'],confirmed=rec['accepted'],tag_x_mm=tag[0],tag_y_mm=tag[1],tag_range_mm=float(np.linalg.norm(np.array([7730,790])-tag)),wheel_x_mm=w[0],wheel_y_mm=w[1],tag_minus_wheel_x_mm=tag[0]-w[0],tag_minus_wheel_y_mm=tag[1]-w[1],wheel_error_mm=float(np.linalg.norm(tag-w)),tag_minus_wheel_heading_deg=dh,local_innovation=rec['innovation']))
phone=[]
with open('roomberry/logs/navlink/roomberry-navlink-20261109-170134-0000.bin','rb') as f:
 f.read(16)
 while r:=f.read(144):
  v=decode_packet(r[16:]);row=dict(zip(packet_fields(v),v));row['epoch']=RECEIPT.unpack(r[:16])[0]/1e9;phone.append(row)
last=[r for r in phone if r['session']==phone[-1]['session']];normal=[r for r in last if r['tracking']==2]
summary=dict(anchor=anchor,anchor_capture_epoch=cap16,fixes=fixes,phone=dict(packets=len(phone),sessions=len(set(r['session'] for r in phone)),first_received=datetime.fromtimestamp(phone[0]['epoch']).isoformat(),last_session_packets=len(last),last_session_tracking=dict(Counter(r['tracking'] for r in last)),last_session_reasons=dict(Counter(r['reason'] for r in last)),normal_features_min=min(r['features'] for r in normal),normal_features_median=float(np.median([r['features'] for r in normal])),normal_features_max=max(r['features'] for r in normal)))
(out/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
with (out/'tag15-wheel-check.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=list(fixes[0]));writer.writeheader();writer.writerows(fixes)
fig,axs=plt.subplots(1,3,figsize=(16,5),constrained_layout=True)
use=(t>=cap16)&(t<=fixes[-1]['capture_epoch'])
axs[0].plot(p[use,0]/1000,p[use,1]/1000,label='Pure wheel integration incl. manual driving')
axs[0].scatter([anchor['x_mm']/1000],[anchor['y_mm']/1000],marker='*',s=100,label='Tag16 anchor')
axs[0].scatter([r['tag_x_mm']/1000 for r in fixes],[r['tag_y_mm']/1000 for r in fixes],label='Tag15 measured robot poses')
axs[0].scatter([7.73],[.79],marker='s',label='Surveyed tag15')
for r in fixes:axs[0].plot([r['wheel_x_mm']/1000,r['tag_x_mm']/1000],[r['wheel_y_mm']/1000,r['tag_y_mm']/1000],c='gray',ls=':')
axs[0].set(xlabel='Room X (m)',ylabel='Room Y (m)',title='Tag16 wheel trace and tag15 checks');axs[0].axis('equal');axs[0].legend(fontsize=7)
x=[r['capture_epoch']-cap16 for r in fixes];axs[1].plot(x,[r['wheel_error_mm'] for r in fixes],'o-',label='Independent wheel position error (mm)');axs[1].set(xlabel='Seconds from tag16',ylabel='Position error (mm)',title='No tag corrections to wheel trace');axs[1].legend(fontsize=7)
pt=np.array([r['epoch'] for r in last]);axs[2].plot(pt-pt[0],[r['features'] for r in last],label='Live features');axs[2].set(xlabel='Seconds in final iPhone session',ylabel='Feature count',title='No tag16/iPhone anchor available');axs[2].legend(fontsize=8)
for ax in axs:ax.grid(alpha=.3)
fig.suptitle('17:01 run: wheel/tag checks; wheel–iPhone disagreement unavailable')
fig.savefig(out/'run-analysis.png',dpi=160);fig.savefig(out/'run-analysis.pdf')
print(json.dumps(summary,indent=2))
