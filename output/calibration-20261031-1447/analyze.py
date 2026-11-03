# @(#)analyze.py 3.1 2026/10/31 15:10:00
import sys,json,csv,math,struct,statistics,collections
from pathlib import Path
sys.path.insert(0,str(Path('roomberry').resolve()))
from roomberry_navlink import decode_packet,packet_fields
out=Path(__file__).parent
log=Path('roomberry/logs/roomberry.log').read_text().splitlines()
check=[json.loads(l.split('Calibration checkpoint: ')[1]) for l in log if 'Calibration checkpoint:' in l]
raw=Path('roomberry/logs/navlink/roomberry-navlink-20261031-144728-0000.bin').read_bytes();p=[]
for i in range(16,len(raw)-143,144):
 v=decode_packet(raw[i+16:i+144]);r=dict(zip(packet_fields(v),v));r['t']=struct.unpack_from('<Q',raw,i)[0]/1e9;p.append(r)
s=list(csv.DictReader(open('roomberry/logs/sensors/roomberry-sensors-20261031-144728.csv',newline='')))
near=lambda t:min(s,key=lambda r:abs(float(r['epoch_s'])-t))
summ=[];origin=None
for c in check:
 if c['checkpoint']=='start':origin=c
 w=c['wheels_pose'];o=origin['wheels_pose'];dx=w['x_mm']-o['x_mm'];dy=w['y_mm']-o['y_mm']
 summ.append({'checkpoint':c['checkpoint'],'epoch':c['wall_time'],'wheel_mm':c['wheel_distance_from_start_mm'],'start_heading_deg':math.degrees(o['heading_rad']),'wheel_yaw_change_deg':math.degrees(w['heading_rad']-o['heading_rad']),'cross_track_initial_axis_mm':-math.sin(o['heading_rad'])*dx+math.cos(o['heading_rad'])*dy,'world_delta_mm':[dx,dy],'phone_available':c['iphone_pose'] is not None,'tag_available':c['tag_pose'] is not None,'tag_wheel_error_mm':None if not c['wheels_minus_tag'] else c['wheels_minus_tag']['distance_mm']})
intervals=[]
for label,a,b in [('attempt1',check[0]['wall_time'],1793483313.126),('attempt2_outbound',check[3]['wall_time'],check[-1]['wall_time']),('attempt2_return',check[-1]['wall_time'],1793483388.432)]:
 pp=[r for r in p if a<=r['t']<=b];g=[r for r in pp if r['type']==2];h=[r for r in pp if r['type']==3];comp=[r for r in pp if r['type']==4];aa,bb=near(a),near(b)
 intervals.append({'run':label,'seconds':b-a,'wheel_delta_mm':float(bb['distance_mm'])-float(aa['distance_mm']),'motion_packets':len(g),'motion_max_gap_s':max(b['t']-a['t'] for a,b in zip(g,g[1:])),'motion_max_send_gap_s':max((b['send_us']-a['send_us'])/1e6 for a,b in zip(g,g[1:])),'valid_fraction':sum(r['flags']==7 for r in g)/len(g),'continuity_range':[g[0]['continuity'],g[-1]['continuity']],'accepted_frame_delta':g[-1]['accepted_frames']-g[0]['accepted_frames'],'rejected_frame_delta':g[-1]['rejected_frames']-g[0]['rejected_frames'],'reasons':dict(collections.Counter(r['reason'] for r in g)),'health_packets':len(h),'cpu_range':[min(r['app_cpu_pct'] for r in h),max(r['app_cpu_pct'] for r in h)],'compass_valid':sum(bool(r['flags']&1) for r in comp),'compass_accuracy_deg_range':[math.degrees(min(r['heading_accuracy_rad'] for r in comp)),math.degrees(max(r['heading_accuracy_rad'] for r in comp))]})
events=[];last=None
for r in p:
 if r['type']==3 and last is not None and r['bump_count']>last:
  events.append({k:r[k] for k in ('t','bump_count','bump_us','last_bump_peak_mm_s2','device_ax_mm_s2','device_ay_mm_s2','device_az_mm_s2')})
 if r['type']==3:last=r['bump_count']
requests=collections.Counter(l.split('"GET ')[1].split(' HTTP')[0] for l in log if '"GET ' in l)
result={'checkpoints':summ,'intervals':intervals,'new_bump_events':events,'http_requests':dict(requests)}
(out/'summary.json').write_text(json.dumps(result,indent=2));(out/'checkpoints.json').write_text(json.dumps(check,indent=2));print(json.dumps(result,indent=2))
