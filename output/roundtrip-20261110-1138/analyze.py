# @(#)analyze.py 3.2.analysis.1 2026/11/10 11:53:34
"""Offline single-session comparison; no trajectory fitting or live controls."""
import ast, collections, csv, json, math, os, re, sys
from datetime import datetime
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'roomberry'))
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
from roomberry_trek_anchor import TrekTagAnchor
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
config=json.loads((ROOT/'roomberry/autonomy.json').read_text());mount=config['roomtrek_alignment']
rows=[]
with (ROOT/'roomberry/logs/navlink/roomberry-navlink-20261110-113843-0000.bin').open('rb') as f:
 f.read(16)
 while rec:=f.read(144):
  if len(rec)!=144:break
  v=decode_packet(rec[16:]);assert v[2]==6
  r=dict(zip(packet_fields(v),v));r['epoch'],r['mono']=[x/1e9 for x in RECEIPT.unpack(rec[:16])];rows.append(r)
assert len({r['session'] for r in rows})==1
clock=min(r['mono']-r['send_us']/1e6 for r in rows)
offsets=np.array([r['epoch']-r['mono'] for r in rows]);assert np.ptp(offsets)<.1
for r in rows:r['t']=r['frame_us']/1e6+clock+float(np.median(offsets))
all_rows=rows
# Repeated telemetry may contain the same camera frame; keep its first receipt.
rows=list({r['frame_us']:r for r in reversed(rows)}.values())[::-1]
with (ROOT/'roomberry/logs/sensors/roomberry-sensors-20261110-113843.csv').open() as f:ss=list(csv.DictReader(f))
assert len({r['odometry_epoch'] for r in ss})==1
st=np.array([float(r['epoch_s']) for r in ss]);sd=np.array([float(r['distance_mm']) for r in ss]);sh=np.radians([float(r['angle_deg']) for r in ss]);assert np.all(np.diff(st)>0)
wp=np.zeros((len(st),2))
for i in range(1,len(st)):
 middle=(sh[i]+sh[i-1])/2
 wp[i]=wp[i-1]+(sd[i]-sd[i-1])*np.array([np.cos(middle),np.sin(middle)])
wrap=lambda x:np.arctan2(np.sin(x),np.cos(x))
rot=lambda a:np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
lens=np.array([mount['lens_x_mm'],mount['lens_y_mm']])
pt=np.array([r['t'] for r in rows]);pp=np.array([[r['x_m']*1000,r['y_m']*1000] for r in rows]);ph=np.unwrap([TrekTagAnchor.axis_heading(r,'optical_forward') for r in rows])+math.radians(mount['mount_yaw_deg'])
good=np.array([TrekTagAnchor.usable(r,'optical_forward') for r in rows]);assert np.all(np.diff(pt)>0)
interp=lambda t,arr:np.array([np.interp(t,pt,arr[:,k]) for k in range(arr.shape[1])]) if arr.ndim==2 else np.interp(t,pt,arr)
wi=lambda t:np.array([np.interp(t,st,wp[:,k]) for k in (0,1)])
# Stable pre-motion reference. This fixes origin/yaw only, with physical scale=1.
t0=datetime(2026,11,10,11,39,10).timestamp();h0=np.interp(t0,st,sh);pr0=interp(t0,pp);pa0=interp(t0,ph)
rotation=h0-pa0
rh=ph+rotation
rp=(pp-pr0)@rot(rotation).T+(rot(h0)@lens)-np.array([rot(h)@lens for h in rh])
rw=wp-wi(t0)
wh=np.interp(pt,st,sh);wheel_at=np.column_stack([np.interp(pt,st,rw[:,k]) for k in (0,1)])
sep=np.linalg.norm(rp-wheel_at,axis=1);heading_diff=np.degrees(wrap(rh-wh))
# Read tag solutions and associate with the detector's actual capture timestamp.
fixes=[];captures={};steps=[];modes=[]
for line in (ROOT/'roomberry/logs/roomberry.log').read_text().splitlines():
 try:lt=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()
 except ValueError:continue
 if 'AprilTag detected:' in line:
  m=re.search(r'id=(\d+).*captured_at=([0-9.]+)',line)
  if m:captures[int(m[1])]=float(m[2].rstrip('.'))
 if 'Return to tag 15 scan: ' in line:
  d=ast.literal_eval(line.split('Return to tag 15 scan: ',1)[1]);p=d.get('pose')
  if p:fixes.append(dict(t=captures[15],log_t=lt,tag=15,accepted=d['accepted'],purpose=d['purpose'],pose=p,innovation=d.get('innovation')))
 if 'Idle AprilTag localization: pose={' in line:
  p=ast.literal_eval(line.split('Idle AprilTag localization: pose=',1)[1].split(' detections=',1)[0]);tag=p['accepted_tag_ids'][0][1]
  fixes.append(dict(t=captures[tag],log_t=lt,tag=tag,accepted=True,purpose='idle',pose=p,innovation=None))
 if 'Steering pad result: ' in line:
  d=ast.literal_eval(line.split('Steering pad result: ',1)[1]);steps.append(dict(t=lt,**d))
 if 'Mission mode changed to ' in line:modes.append((lt,line.split('Mission mode changed to ',1)[1]))
# One independent, offline room transform fixed at the first confirmed tag15.
anchor=next(f for f in fixes if f['accepted']);at=anchor['t'];a=anchor['pose'];angle=a['heading_rad']-interp(at,ph)
axy=np.array([a['x_mm'],a['y_mm']]);acamera=axy+rot(a['heading_rad'])@lens
roomh=ph+angle
roomp=(pp-interp(at,pp))@rot(angle).T+acamera-np.array([rot(h)@lens for h in roomh])
wa=np.interp(at,st,sh);wheelroom=(wp-wi(at))@rot(a['heading_rad']-wa).T+axy
for fix in fixes:
 t=fix['t'];p=fix['pose'];tagxy=np.array([p['x_mm'],p['y_mm']]);phone=interp(t,roomp);wheel=np.array([np.interp(t,st,wheelroom[:,k]) for k in (0,1)])
 fix.update(phone_x_mm=float(phone[0]),phone_y_mm=float(phone[1]),wheel_x_mm=float(wheel[0]),wheel_y_mm=float(wheel[1]),phone_tag_mm=float(np.linalg.norm(phone-tagxy)),wheel_tag_mm=float(np.linalg.norm(wheel-tagxy)),phone_heading_delta_deg=float(np.degrees(wrap(interp(t,roomh)-p['heading_rad']))),wheel_heading_delta_deg=float(np.degrees(wrap(np.interp(t,st,sh)+a['heading_rad']-wa-p['heading_rad']))),phone_frame_pair_delta_s=float(pt[np.argmin(abs(pt-t))]-t),usable_phone=bool(good[np.argmin(abs(pt-t))]))
# Settled per-command comparison uses medians around stopped endpoints.
# The previous mode transition to remote supplies each step's start time.
for step in steps:
 start=max(t for t,mode in modes if mode=='remote_control' and t<step['t'])
 end=step['t'];pre=(pt>=start-.6)&(pt<=start-.1)&good;post=(pt>=end-.1)&(pt<=end+.3)&good
 if pre.sum()<2 or post.sum()<2:step['phone_usable']=False;continue
 hbefore=np.median(ph[pre]);hafter=np.median(ph[post]);delta_h=float(np.degrees(wrap(hafter-hbefore)))
 raw_distance=float(np.linalg.norm(np.median(pp[post],axis=0)-np.median(pp[pre],axis=0)))
 body_before=np.median(rp[pre],axis=0);body_after=np.median(rp[post],axis=0)
 step.update(start_t=start,phone_usable=True,phone_heading_deg=delta_h,phone_distance_mm=float(np.linalg.norm(body_after-body_before)),raw_camera_distance_mm=raw_distance)
# Quality gaps, including insufficient-features intervals.
gaps=[]
for i,r in enumerate(rows):
 if r['tracking']!=2:
  if not gaps or i==0 or rows[i-1]['tracking']==2:gaps.append(dict(start=r['t'],end=r['t'],reason=r['reason'],packets=1))
  else:gaps[-1]['end']=r['t'];gaps[-1]['packets']+=1
summary=dict(session=str(rows[0]['session']),packets=len(all_rows),unique_camera_frames=len(rows),duplicate_camera_frames=len(all_rows)-len(rows),tracking=dict(collections.Counter(r['tracking'] for r in all_rows)),reasons=dict(collections.Counter(r['reason'] for r in all_rows)),sequence_gaps=sum(max(0,b['seq']-a['seq']-1) for a,b in zip(all_rows,all_rows[1:])),clock_epoch_span_s=float(np.ptp(offsets)),relative_reference_epoch=t0,room_anchor=dict(t=at,tag=15,pose=a,offline=True),phone_feature_percentiles=np.percentile([r['features'] for r in rows],[0,50,95,100]).tolist(),phone_quality_gaps=gaps,recorded_tag16_anchor=False)
checkpoints={}
for label,t in [('before_move',t0),('tag15_first_fix',at),('tag15_stop',next(f['t'] for f in fixes if f['purpose']=='validate' and f['accepted'])),('tag16_return',fixes[-1]['t']),('end',pt[-1])]:
 p=interp(t,rp);w=np.array([np.interp(t,st,rw[:,k]) for k in (0,1)]);checkpoints[label]=dict(t=t,local_time=datetime.fromtimestamp(t).isoformat(),phone_x_mm=float(p[0]),phone_y_mm=float(p[1]),wheel_x_mm=float(w[0]),wheel_y_mm=float(w[1]),separation_mm=float(np.linalg.norm(p-w)),heading_delta_deg=float(np.degrees(wrap(interp(t,rh)-np.interp(t,st,sh)))),wheel_path_mm=float(np.interp(t,st,[float(r['travelled_distance_mm']) for r in ss])-np.interp(t0,st,[float(r['travelled_distance_mm']) for r in ss])),phone_usable=bool(good[np.argmin(abs(pt-t))]))
phase_stats={}
for name,start,end in [('outbound',t0,gaps[0]['start']),('return',gaps[0]['end'],checkpoints['tag16_return']['t'])]:
 mask=(pt>=start)&(pt<=end)&good
 phase_stats[name]=dict(samples=int(mask.sum()),absolute_heading_percentiles_deg=np.percentile(abs(heading_diff[mask]),[50,95,100]).tolist(),max_separation_mm=float(sep[mask].max()))
reference_checks={}
for name,t in [('pre_motion',t0),('offline_tag15',at)]:
 ix=int(np.argmin(abs(pt-t)));window=abs(pt-t)<.25;sw=abs(st-t)<.3
 reference_checks[name]=dict(pair_delta_s=float(pt[ix]-t),phone_usable=bool(good[ix]),phone_frames=int(window.sum()),phone_position_variation_mm=float(np.max(np.linalg.norm(pp[window]-pp[ix],axis=1))),phone_heading_variation_deg=float(np.degrees(np.ptp(ph[window]))),wheel_distance_variation_mm=float(np.ptp(sd[sw])),wheel_angle_variation_deg=float(np.degrees(np.ptp(sh[sw]))))
 assert good[ix] and abs(pt[ix]-t)<.25 and reference_checks[name]['phone_position_variation_mm']<20 and reference_checks[name]['phone_heading_variation_deg']<2
 assert reference_checks[name]['wheel_distance_variation_mm']<5 and reference_checks[name]['wheel_angle_variation_deg']<2
last15=next(f for f in fixes if f['tag']==15 and f['accepted'] and f['purpose']=='validate')
landmark15=next(x for x in config['landmarks'] if x['id']==15)['world_from_tag']
tag15_range=math.hypot(landmark15[0][3]*1000-last15['pose']['x_mm'],landmark15[1][3]*1000-last15['pose']['y_mm'])
summary.update(phase_stats=phase_stats,reference_checks=reference_checks,tag15_validated_robot_range_mm=tag15_range,checkpoints=checkpoints,max_separation_mm=float(sep[(pt>=t0)&good].max()),max_heading_delta_deg=float(abs(heading_diff[(pt>=t0)&good]).max()),tag_fixes=fixes,steps=steps)
(OUT/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
with (OUT/'comparison.csv').open('w') as f:
 writer=csv.writer(f);writer.writerow(['epoch_s','usable','wheel_x_mm','wheel_y_mm','phone_x_mm','phone_y_mm','heading_delta_deg','separation_mm']);writer.writerows(zip(pt,good,*wheel_at.T,*rp.T,heading_diff,sep))
with (OUT/'tag-checks.csv').open('w') as f:
 fields=['tag','purpose','accepted','t','phone_tag_mm','wheel_tag_mm','phone_heading_delta_deg','wheel_heading_delta_deg','phone_frame_pair_delta_s','usable_phone'];w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(fixes)
# Publication/export plot: relative curves and independent room check, no path fit.
fig,axs=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
mask=(pt>=t0)&good
axs[0,0].plot(rw[:,0]/1000,rw[:,1]/1000,label='Wheel integration (no tag corrections)',lw=1.5)
axs[0,0].plot(np.where(mask,rp[:,0]/1000,np.nan),np.where(mask,rp[:,1]/1000,np.nan),label='iPhone robot centre; usable frames',lw=1.2)
for label,title in [('before_move','start'),('tag15_stop','tag15 stop (wheel)'),('tag16_return','back at tag16 (wheel)')]:
 c=checkpoints[label];xw,yw=c['wheel_x_mm']/1000,c['wheel_y_mm']/1000
 axs[0,0].scatter([xw],[yw],c='black',s=20);axs[0,0].annotate(title,(xw,yw),fontsize=8)
axs[0,0].axis('equal');axs[0,0].set(title='Same pre-motion origin and heading; relative paths',xlabel='Initial robot forward (m)',ylabel='Initial robot left (m)');axs[0,0].legend(fontsize=8)
x=[datetime.fromtimestamp(t) for t in pt]
axs[0,1].plot(x,np.where(good,sep,np.nan),c='black');axs[0,1].set(title='Phone–wheel separation; fixed pre-motion baseline',ylabel='Separation (mm)')
axs[1,0].plot(x,np.where(good,heading_diff,np.nan));axs[1,0].set(title='Heading disagreement; fixed pre-motion baseline',ylabel='Phone minus wheel (degrees)')
axs[1,1].plot(x,[r['features'] for r in rows],lw=.8);axs[1,1].set(title='Visible features and limited-tracking intervals',ylabel='Features')
for ax in (axs[0,1],axs[1,0],axs[1,1]):
 for gap in gaps:ax.axvspan(datetime.fromtimestamp(gap['start']),datetime.fromtimestamp(gap['end']+.1),color='orange',alpha=.18)
 for label in ('tag15_stop','tag16_return'):
  t=datetime.fromtimestamp(checkpoints[label]['t']);ax.axvline(t,c='gray',ls=':',lw=.8)
 ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M:%S'));ax.set_xlim(datetime.fromtimestamp(t0),datetime.fromtimestamp(pt[-1]));ax.grid(alpha=.25)
axs[0,0].grid(alpha=.25)
fig.suptitle('Tag15 and back to tag16 — one continuous fresh phone session\nScale 1; configured lens/mount; no trajectory fitting; orange = limited tracking')
fig.savefig(OUT/'comparison.png',dpi=160);fig.savefig(OUT/'comparison.pdf');plt.close(fig)
print(json.dumps({k:v for k,v in summary.items() if k not in ('steps','tag_fixes','phone_quality_gaps')},indent=2))
print('TAGCHECKS',json.dumps([{k:f[k] for k in ('tag','purpose','accepted','t','phone_tag_mm','wheel_tag_mm','phone_heading_delta_deg','wheel_heading_delta_deg','usable_phone')} for f in fixes],indent=2))
print('GAPS',json.dumps(gaps))
