# @(#)analyze.py 3.1 2026/10/31 14:35:00
import sys,json,csv,math,struct,statistics,collections
from pathlib import Path
sys.path.insert(0,str(Path('roomberry').resolve()))
from roomberry_navlink import decode_packet,packet_fields
out=Path(__file__).parent
log=Path('roomberry/logs/roomberry.log').read_text().splitlines()
check=[json.loads(l.split('Calibration checkpoint: ')[1]) for l in log if 'Calibration checkpoint:' in l]
raw=Path('roomberry/logs/navlink/roomberry-navlink-20261031-142101-0000.bin').read_bytes();p=[]
for i in range(16,len(raw)-143,144):
 v=decode_packet(raw[i+16:i+144]);r=dict(zip(packet_fields(v),v));r['t']=struct.unpack_from('<Q',raw,i)[0]/1e9;p.append(r)
s=list(csv.DictReader(open('roomberry/logs/sensors/roomberry-sensors-20261031-142102.csv',newline='')))
near=lambda t:min(s,key=lambda r:abs(float(r['epoch_s'])-t))
summ=[]
for n,c in enumerate(check):
 origin=check[0 if n<2 else 2]
 d={'checkpoint':c['checkpoint'],'time':c['wall_time'],'wheel_mm':c['wheel_distance_from_start_mm'],'wheel_heading_change_deg':math.degrees(c['wheels_pose']['heading_rad']-origin['wheels_pose']['heading_rad']),'wheel_xy':[c['wheels_pose']['x_mm']-origin['wheels_pose']['x_mm'],c['wheels_pose']['y_mm']-origin['wheels_pose']['y_mm']]}
 for label,key in [('phone','iphone_pose'),('tag','tag_pose')]:
  a=c[key];b=origin[key]
  if a and b:d[label]={'xy':[a['x_mm']-b['x_mm'],a['y_mm']-b['y_mm']],'chord_mm':math.hypot(a['x_mm']-b['x_mm'],a['y_mm']-b['y_mm']),'yaw_change_deg':math.degrees(a['heading_rad']-b['heading_rad'])}
 if c['iphone_minus_wheels']:d['phone_wheel_error_mm']=c['iphone_minus_wheels']['distance_mm'];d['phone_wheel_yaw_error_deg']=math.degrees(c['iphone_minus_wheels']['heading_rad'])
 summ.append(d)
intervals=[]
for label,a,b in [('attempt1',check[0]['wall_time'],1793481706.101),('attempt2',check[2]['wall_time'],1793481800.715)]:
 pp=[r for r in p if a<=r['t']<=b];g=[r for r in pp if r['type']==2];h=[r for r in pp if r['type']==3];comp=[r for r in pp if r['type']==4]
 intervals.append({'run':label,'seconds':b-a,'motion_packets':len(g),'motion_max_gap_s':max(bb['t']-aa['t'] for aa,bb in zip(g,g[1:])),'motion_valid_fraction':sum(r['flags']==7 for r in g)/len(g),'continuities':[min(r['continuity'] for r in g),max(r['continuity'] for r in g)],'reasons':dict(collections.Counter(r['reason'] for r in g)),'health_packets':len(h),'cpu_range':[min(r['app_cpu_pct'] for r in h),max(r['app_cpu_pct'] for r in h)],'memory_MB_range':[min(r['app_footprint_bytes'] for r in h)/1e6,max(r['app_footprint_bytes'] for r in h)/1e6],'battery_range':[min(r['battery_pct'] for r in h),max(r['battery_pct'] for r in h)],'compass_valid':sum(bool(r['flags']&1) for r in comp),'compass_accuracy_deg_range':[math.degrees(min(r['heading_accuracy_rad'] for r in comp)),math.degrees(max(r['heading_accuracy_rad'] for r in comp))]})
bumps=[];last=0
for r in p:
 if r['type']==3 and r['bump_count']>last:
  bumps.append({k:r[k] for k in ('t','bump_count','bump_us','last_bump_peak_mm_s2','interval_accel_peak_mm_s2')});last=r['bump_count']
result={'checkpoints':summ,'intervals':intervals,'bump_events':bumps,'abort_sensor':{k:near(1793481800.715)[k] for k in ('timestamp','distance_mm','angle_deg','bump_left','bump_right','left_motor_current_a','right_motor_current_a','applied_left_velocity_mm_s','applied_right_velocity_mm_s')}}
(out/'summary.json').write_text(json.dumps(result,indent=2));(out/'checkpoints.json').write_text(json.dumps(check,indent=2));print(json.dumps(result,indent=2))
