# @(#)analyze.py 3.1 2026/10/31 14:20:00
import sys, csv, json, math, struct, statistics, collections, ast
from pathlib import Path
sys.path.insert(0,str(Path('roomberry').resolve()))
from roomberry_navlink import decode_packet,packet_fields
out=Path(__file__).parent
start=1793480437.374; stop=1793480449.331
s=list(csv.DictReader(open('roomberry/logs/sensors/roomberry-sensors-20261031-135830.csv',newline='')))
s=[r for r in s if r.get('epoch_s')]
near=lambda t:min(s,key=lambda r:abs(float(r['epoch_s'])-t))
a,b=near(start),near(stop)
origin=(7436.793214149913,1197.0396075593337,-.2077582489272598)
x,y,h=origin; pd=float(a['distance_mm']); pa=float(a['angle_deg'])
trajectory=[]
for r in s:
 t=float(r['epoch_s'])
 if not start<=t<=stop:continue
 d=float(r['distance_mm']); angle=float(r['angle_deg']); da=math.radians(angle-pa)
 x+=(d-pd)*math.cos(h+da/2); y+=(d-pd)*math.sin(h+da/2);h+=da;pd=d;pa=angle
 trajectory.append([t-start,d-float(a['distance_mm']),angle-float(a['angle_deg']),x,y])
pack=[]; raw=Path('roomberry/logs/navlink/roomberry-navlink-20261031-135830-0000.bin').read_bytes()
for i in range(16,len(raw)-143,144):
 v=decode_packet(raw[i+16:i+144]);r=dict(zip(packet_fields(v),v));r['t']=struct.unpack_from('<Q',raw,i)[0]/1e9;pack.append(r)
offsets={ss:min(r['t']-r['send_us']/1e6 for r in pack if r['session']==ss) for ss in {r['session'] for r in pack}}
for r in pack:r['source_t']=offsets[r['session']]+r.get('end_us',r.get('imu_us',r['send_us']))/1e6
p=[r for r in pack if start<=r['t']<=stop]
g=[r for r in p if r['type']==2];health=[r for r in pack if r['type']==3 and start<=r['source_t']<=stop];comp=[r for r in p if r['type']==4]
yaw=0;coverage=0
for aa,bb in zip(health,health[1:]):
 dt=(bb['imu_us']-aa['imu_us'])/1e6
 if 0<dt<.5 and aa['flags']&1 and bb['flags']&1:
  def rate(r):return -sum(r['device_w'+axis+'_rad_s']*r['gravity_'+axis+'_g'] for axis in 'xyz')
  yaw+=(rate(aa)+rate(bb))/2*dt;coverage+=dt
poses=[]
for line in Path('roomberry/logs/roomberry.log').read_text().splitlines():
 if 'Idle AprilTag localization: pose=' in line and line[:19]>='2026-10-31 14:00:49':
  pose=ast.literal_eval(line.split('pose=',1)[1].split(' detections=',1)[0]);poses.append(pose)
summary={'interval_epoch':[start,stop],'wheel_distance_mm':float(b['distance_mm'])-float(a['distance_mm']),'wheel_yaw_deg':float(b['angle_deg'])-float(a['angle_deg']),'wheel_endpoint':[x,y,h],'wheel_last_progress':next(r['timestamp'] for r in s if float(r['epoch_s'])>=start and float(r['distance_mm'])==float(b['distance_mm'])),'tag_first_after_stop':poses[0],'tag_static_median':{k:statistics.median(r[k] for r in poses) for k in ('x_mm','y_mm','heading_rad')},'tag_static_ranges':{k:[min(r[k] for r in poses),max(r[k] for r in poses)] for k in ('x_mm','y_mm','heading_rad')},'tag_count':len(poses),'ground_packets':len(g),'ground_valid':sum(r['flags']==7 and r['tracking']==2 for r in g),'ground_reasons':dict(collections.Counter(r['reason'] for r in g)),'ground_continuities':dict(collections.Counter(r['continuity'] for r in g)),'ground_first':{k:g[0][k] for k in ('continuity','segment_x_mm','segment_y_mm','segment_yaw_rad','reason')},'ground_last':{k:g[-1][k] for k in ('continuity','segment_x_mm','segment_y_mm','segment_yaw_rad','reason')},'gyro_yaw_deg':math.degrees(yaw),'gyro_coverage_s':coverage,'compass_packets':len(comp),'compass_valid':sum(bool(r['flags']&1) for r in comp),'compass_accuracy_deg_range':[math.degrees(min(r['heading_accuracy_rad'] for r in comp)),math.degrees(max(r['heading_accuracy_rad'] for r in comp))],'health':{k:[min(r[k] for r in health),max(r[k] for r in health)] for k in ('battery_pct','app_cpu_pct','app_footprint_bytes','image_width','image_height','bump_count','thermal_state')}}
for name,pose in [('first',poses[0]),('median',summary['tag_static_median'])]:
 dx=pose['x_mm']-origin[0];dy=pose['y_mm']-origin[1];summary['tag_'+name+'_displacement']={'distance_mm':math.hypot(dx,dy),'dx_mm':dx,'dy_mm':dy,'yaw_deg':math.degrees(pose['heading_rad']-origin[2]),'wheel_endpoint_error_mm':math.hypot(pose['x_mm']-x,pose['y_mm']-y)}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
with (out/'wheel_trajectory.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['seconds','signed_distance_mm','yaw_deg','x_mm','y_mm']);w.writerows(trajectory)
print(json.dumps(summary,indent=2))
