# @(#)turns.py 2.3.analysis.1 2026/10/30 14:15:00
"""Compare encoder yaw with phone heading over separated in-place turns."""
import csv
from datetime import datetime
from pathlib import Path
import numpy as np

out=Path(__file__).resolve().parent
nav=list(csv.DictReader(open(out/'navlink.csv')))
sensor=list(csv.DictReader(open(out.parents[1]/'roomberry/logs/sensors/roomberry-sensors-20261030-131355.csv')))
def n(k): return np.array([float(r[k]) for r in nav])
def s(k): return np.array([float(r[k] or 0) for r in sensor])
rt=n('receive_epoch_ns')/1e9
offset=min(rt-n('send_us')/1e6)
nt=n('frame_us')/1e6+offset
it=n('imu_us')/1e6+offset
st=s('epoch_s'); a=s('angle_deg'); dist=s('distance_mm')
nh=np.degrees(np.unwrap(n('heading_rad')))
dt=np.diff(st); da=np.diff(a); dd=np.diff(dist)
turn=(abs(da)>np.maximum(dt*5,.5)) & (abs(dd)<np.maximum(dt*25,3)) & (dt<.6)
indices=np.where(turn)[0]+1
groups=[]
for i in indices:
    if groups and st[i]-st[groups[-1][-1]]<.8 and np.sign(da[i-1])==np.sign(da[groups[-1][-1]-1]):
        groups[-1].append(i)
    else: groups.append([i])
results=[]
for g in groups:
    start=st[g[0]-1]-.3; end=st[g[-1]]+.3
    if start<nt[0] or end>nt[-1]: continue
    wheel=np.interp(end,st,a)-np.interp(start,st,a)
    if abs(wheel)<25: continue
    phone=np.interp(end,nt,nh)-np.interp(start,nt,nh)
    mask=(it>=start)&(it<=end)
    gyro=np.degrees(np.sum(np.diff(it[mask])*(n('yaw_rad_s')[mask][1:]+n('yaw_rad_s')[mask][:-1])/2))
    results.append(dict(start=datetime.fromtimestamp(start).strftime('%H:%M:%S.%f')[:-3],
        end=datetime.fromtimestamp(end).strftime('%H:%M:%S.%f')[:-3],wheel_deg=round(wheel,2),
        phone_deg=round(phone,2),gyro_deg=round(gyro,2),phone_over_wheel=round(phone/wheel,3)))
with open(out/'turn-comparison.csv','w') as f:
    w=csv.DictWriter(f,fieldnames=results[0].keys());w.writeheader();w.writerows(results)
for r in results: print(r)
for sign in [-1,1]:
    subset=[r for r in results if np.sign(r['wheel_deg'])==sign]
    print('CW' if sign<0 else 'CCW','turns',len(subset),'median phone/wheel',np.median([r['phone_over_wheel'] for r in subset]))

# Verify the cumulative logged yaw against independently unwrapped encoders.
left=s('left_encoder_counts');right=s('right_encoder_counts')
ld=(np.diff(left)+32768)%65536-32768
rd=(np.diff(right)+32768)%65536-32768
encoder_da=(rd-ld)*.444564998149499/235*180/np.pi
print('encoder yaw delta versus logged yaw max residual deg',max(abs(encoder_da-da)))
print('sensor sample max gap seconds',max(dt),'phone coverage max gap',max(dt[(st[1:]<nt[-1])]))
