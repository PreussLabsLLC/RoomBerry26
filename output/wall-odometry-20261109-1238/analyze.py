"""Compare wheel/body odometry with survey camera pose; no ground-truth claim."""
# @(#)analyze.py 3.2 2026/11/09 13:07:03
from pathlib import Path
import sys, json, csv, math, os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/roomberry-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
from roomberry_control import WHEEL_SIZE_ADJUSTMENT
from irobot.openinterface.constants import ROBOT
OUT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'roomberry/autonomy.json').read_text())
with (ROOT/'roomberry/logs/sensors/roomberry-sensors-20261109-123844.csv').open() as f: sensors=list(csv.DictReader(f))
t=np.array([float(r['epoch_s']) for r in sensors]); d=np.array([float(r['distance_mm']) for r in sensors])/1000
h=np.radians([float(r['angle_deg']) for r in sensors]); pos=np.zeros((len(t),2))
for i in range(1,len(t)):
 pos[i]=pos[i-1]+(d[i]-d[i-1])*np.array([np.cos((h[i]+h[i-1])/2),np.sin((h[i]+h[i-1])/2)])
phone=[]
with (ROOT/'roomberry/logs/navlink/roomberry-navlink-20261109-123843-0000.bin').open('rb') as f:
 f.read(16)
 while True:
  b=f.read(144)
  if len(b)!=144: break
  v=decode_packet(b[16:]);r=dict(zip(packet_fields(v),v));r['rx']=RECEIPT.unpack(b[:16])[0]/1e9;phone.append(r)
offset=min(r['rx']-r['send_us']/1e6 for r in phone)
p=[r for r in phone if r['tracking']==2 and r['frame_age_us']<=250000]
pt=np.array([r['frame_us']/1e6+offset for r in p]);px=np.array([[r['x_m'],r['y_m']] for r in p]); ph=np.unwrap([r['yaw_rad'] for r in p])
wp=np.column_stack([np.interp(pt,t,pos[:,i]) for i in (0,1)]); wh=np.interp(pt,t,h)
# Fit only the first 0.2m straight departure, never the full route. This removes
# the arbitrary survey yaw without fitting away later disagreement or scale.
travel=np.r_[0,np.cumsum(np.abs(np.diff(d)))]; tr=np.interp(pt,t,travel)
cal=(tr>=.015)&(tr<=.185)
if cal.sum()<3: raise RuntimeError('Insufficient early departure samples')
a=px[cal][-1]-px[cal][0]; b=wp[cal][-1]-wp[cal][0]
yaw=math.atan2(b[1],b[0])-math.atan2(a[1],a[0]); R=np.array([[math.cos(yaw),-math.sin(yaw)],[math.sin(yaw),math.cos(yaw)]])
phone_heading=ph-ph[0]+wh[0]
raw=(px-px[0])@R.T+wp[0]
# Configured lens lever arm is an assumption; retain an uncorrected curve too.
r=np.array([cfg['phone_position']['lens_x_mm'],cfg['phone_position']['lens_y_mm']])/1000
lever=np.column_stack([np.cos(phone_heading)*r[0]-np.sin(phone_heading)*r[1],np.sin(phone_heading)*r[0]+np.cos(phone_heading)*r[1]])
body=raw-(lever-lever[0]); residual=body-wp
heading_error=np.degrees(np.arctan2(np.sin(phone_heading-wh),np.cos(phone_heading-wh)))
base=pt[0]; x=pt-base
stop=1794256902.192; window=(pt<=stop)
# Per-wheel encoder speeds use true sample intervals and signed 16-bit wrapping.
dt=np.diff(t); velocities={}; speed_stats={}
for side in ('left','right'):
 counts=np.array([int(r[side+'_encoder_counts']) for r in sensors]);delta=(np.diff(counts)+32768)%65536-32768
 speed=delta*ROBOT.TICK_TO_DISTANCE*WHEEL_SIZE_ADJUSTMENT/dt
 command=np.array([float(r['applied_'+side+'_velocity_mm_s']) for r in sensors])
 velocities[side]=(speed,command)
 age=np.zeros(len(t))
 for j in range(1,len(t)):
  age[j]=age[j-1]+t[j]-t[j-1] if command[j]==command[j-1] else 0.
 stable=age>=.5
 for value in (30,35,50):
  mask=(command[1:]==value)&stable[1:]&(np.abs(dt)<.5)
  if mask.sum():speed_stats[side+'_'+str(value)]=dict(n=int(mask.sum()),median_mm_s=float(np.median(speed[mask])),p10=float(np.percentile(speed[mask],10)),p90=float(np.percentile(speed[mask],90)))
metrics=dict(packets=len(p),alignment_deg=math.degrees(yaw),alignment='first 0.2m straight forward departure, rotation only, no scale fit',lens_offset_m=r.tolist(),clock='minimum receipt epoch minus phone send uptime, applied to frame timestamp',uncorrected_camera_separation_end_m=float(np.linalg.norm((raw-wp)[window][-1])),position_separation_end_m=float(np.linalg.norm(residual[window][-1])),position_separation_max_m=float(np.linalg.norm(residual[window],axis=1).max()),heading_disagreement_end_deg=float(heading_error[window][-1]),heading_disagreement_abs_max_deg=float(np.abs(heading_error[window]).max()),speed=speed_stats)
(OUT/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
with (OUT/'disagreement.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['time_s','wheel_x_m','wheel_y_m','phone_body_x_m','phone_body_y_m','dx_m','dy_m','heading_difference_deg'])
 for row in zip(x,*wp.T,*body.T,*residual.T,heading_error): w.writerow(row)
fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
a=axes[0,0];a.plot(*wp[window].T,label='Wheel centre');a.plot(*body[window].T,label='Phone, configured lens offset');a.plot(*raw[window].T,ls=':',alpha=.6,label='Phone camera, no offset');a.set_aspect('equal');a.set(xlabel='Initial robot forward X (m)',ylabel='Initial robot left Y (m)',title='Trajectories: early-departure alignment only');a.legend(fontsize=7,loc='upper left',bbox_to_anchor=(1.01,1.0));a.grid(alpha=.3)
a=axes[0,1];a.plot(x[window],residual[window,0]*1000,label='ΔX');a.plot(x[window],residual[window,1]*1000,label='ΔY');a.plot(x[window],np.linalg.norm(residual[window],axis=1)*1000,label='Planar separation',color='black');a.set(xlabel='Time after first normal phone frame (s)',ylabel='iPhone minus wheel (mm)',title='Position disagreement (not absolute error)');a.legend();a.grid(alpha=.3)
a=axes[1,0];a.plot(x[window],heading_error[window]);a.axhline(0,c='gray',lw=.7);a.set(xlabel='Time (s)',ylabel='iPhone minus wheel heading (degrees)',title='Heading change disagreement, initial offset removed');a.grid(alpha=.3)
a=axes[1,1]
for side,color in [('left','tab:blue'),('right','tab:orange')]:
 speed,command=velocities[side];a.plot(t[1:]-base,speed,c=color,alpha=.25,lw=.6);a.plot(t-base,command,c=color,lw=1.2,label=side+' command (faint = encoder speed)')
a.set(xlim=(0,stop-base),ylim=(-130,140),xlabel='Time (s)',ylabel='Wheel speed (mm/s)',title='Commanded speed versus encoders');a.legend(fontsize=8);a.grid(alpha=.3)
fig.suptitle('12:38 WALL run — survey camera versus wheel odometry\nRelative comparison; clock, mounting and alignment uncertainty remain',fontsize=14)
fig.savefig(OUT/'disagreement.png',dpi=160);fig.savefig(OUT/'disagreement.pdf');plt.close(fig)
print(json.dumps(metrics,indent=2))
