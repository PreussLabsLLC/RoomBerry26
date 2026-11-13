# @(#)analyze.py 3.2.analysis.4 2026/11/10 14:10:00
"""One-time initial tag16 alignment; free phone/wheel tracks checked against later tags."""
import ast,collections,csv,json,math,os,re,sys
from pathlib import Path
from datetime import datetime
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
from roomberry_trek_anchor import TrekTagAnchor
config=json.loads((ROOT/'roomberry/autonomy.json').read_text());mount=config['roomtrek_alignment']
raw=[]
with (ROOT/'roomberry/logs/navlink/roomberry-navlink-20261110-135820-0000.bin').open('rb') as f:
 f.read(16)
 while block:=f.read(144):
  assert len(block)==144
  v=decode_packet(block[16:]);assert v[2]==6
  r=dict(zip(packet_fields(v),v));r['epoch'],r['mono']=[x/1e9 for x in RECEIPT.unpack(block[:16])];raw.append(r)
assert len({r['session'] for r in raw})==1
clock=min(r['mono']-r['send_us']/1e6 for r in raw);offsets=np.array([r['epoch']-r['mono'] for r in raw]);assert np.ptp(offsets)<.1
for r in raw:r['t']=r['frame_us']/1e6+clock+float(np.median(offsets))
rows=list({r['frame_us']:r for r in reversed(raw)}.values())[::-1]
pt=np.array([r['t'] for r in rows]);assert np.all(np.diff(pt)>0)
pp=np.array([[r['x_m']*1000,r['y_m']*1000] for r in rows]);ph=np.unwrap([TrekTagAnchor.axis_heading(r,'optical_forward') for r in rows])+math.radians(mount['mount_yaw_deg'])
good=np.array([TrekTagAnchor.usable(r,'optical_forward') for r in rows])
with (ROOT/'roomberry/logs/sensors/roomberry-sensors-20261110-135820.csv').open() as f:sensors=list(csv.DictReader(f))
assert len({r['odometry_epoch'] for r in sensors})==1
st=np.array([float(r['epoch_s']) for r in sensors]);sd=np.array([float(r['distance_mm']) for r in sensors]);sh=np.radians([float(r['angle_deg']) for r in sensors]);assert np.all(np.diff(st)>0)
wp=np.zeros((len(st),2))
for i in range(1,len(st)):
 h=(sh[i]+sh[i-1])/2;wp[i]=wp[i-1]+(sd[i]-sd[i-1])*np.array([np.cos(h),np.sin(h)])
wrap=lambda x:np.arctan2(np.sin(x),np.cos(x))
rot=lambda a:np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
def interp(t,x,times=pt):
 return np.array([np.interp(t,times,x[:,k]) for k in range(x.shape[1])]) if x.ndim==2 else np.interp(t,times,x)
# Log contains NUL spans; preserve the source and only parse timestamped text lines.
text=(ROOT/'roomberry/logs/roomberry.log').read_text();fixes=[];captures={};steps=[];modes=[]
for line in text.splitlines():
 try:lt=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()
 except ValueError:continue
 if 'AprilTag detected:' in line:
  m=re.search(r'id=(\d+).*captured_at=([0-9.]+)',line)
  if m:captures[int(m[1])]=float(m[2].rstrip('.'))
 if 'Return to tag 15 scan: ' in line:
  d=ast.literal_eval(line.split('Return to tag 15 scan: ',1)[1])
  if d.get('pose'):fixes.append(dict(tag=15,t=captures[15],log_t=lt,accepted=d['accepted'],purpose=d['purpose'],pose=d['pose'],innovation=d['innovation']))
 if 'Idle AprilTag localization: pose={' in line:
  p=ast.literal_eval(line.split('Idle AprilTag localization: pose=',1)[1].split(' detections=',1)[0]);tag=p['accepted_tag_ids'][0][1]
  fixes.append(dict(tag=tag,t=captures[tag],log_t=lt,accepted=True,purpose='idle',pose=p,innovation=None))
 if 'Steering pad result: ' in line:steps.append(dict(t=lt,**ast.literal_eval(line.split('Steering pad result: ',1)[1])))
 if 'Mission mode changed to ' in line:modes.append((lt,line.split('Mission mode changed to ',1)[1]))
anchor=next(f for f in fixes if f['tag']==16);t0=anchor['t'];a=anchor['pose'];axy=np.array([a['x_mm'],a['y_mm']]);lens=np.array([mount['lens_x_mm'],mount['lens_y_mm']]);rotation=a['heading_rad']-interp(t0,ph)
pheading=ph+rotation
phone=(pp-interp(t0,pp))@rot(rotation).T+axy+rot(a['heading_rad'])@lens-np.array([rot(h)@lens for h in pheading])
wrot=a['heading_rad']-interp(t0,sh,st);wheading=sh+wrot;wheel=(wp-interp(t0,wp,st))@rot(wrot).T+axy
for f in fixes:
 t=f['t'];pose=f['pose'];tagxy=np.array([pose['x_mm'],pose['y_mm']]);p=interp(t,phone);w=interp(t,wheel,st)
 f.update(local_time=datetime.fromtimestamp(t).isoformat(),phone_xy_mm=p.tolist(),wheel_xy_mm=w.tolist(),phone_tag_mm=float(np.linalg.norm(p-tagxy)),wheel_tag_mm=float(np.linalg.norm(w-tagxy)),phone_tag_heading_deg=float(np.degrees(wrap(interp(t,pheading)-pose['heading_rad']))),wheel_tag_heading_deg=float(np.degrees(wrap(interp(t,wheading,st)-pose['heading_rad']))),phone_wheel_mm=float(np.linalg.norm(p-w)),phone_wheel_heading_deg=float(np.degrees(wrap(interp(t,pheading)-interp(t,wheading,st)))),phone_usable=bool(good[np.argmin(abs(pt-t))]),phone_pair_delta_s=float(pt[np.argmin(abs(pt-t))]-t))
final16=next(f for f in fixes if f['tag']==16 and f['t']>t0+30)
repeat16=fixes[-1];last15=next(f for f in reversed(fixes) if f['tag']==15 and f['accepted']);first15=next(f for f in fixes if f['tag']==15 and f['accepted'])
wx=np.column_stack([np.interp(pt,st,wheel[:,k]) for k in (0,1)]);sep=np.linalg.norm(phone-wx,axis=1);hdiff=np.degrees(wrap(pheading-np.interp(pt,st,wheading)))
mask=(pt>=t0)&(pt<=final16['t'])&good
quality=[]
for i,r in enumerate(raw):
 if r['tracking']!=2:
  if i==0 or raw[i-1]['tracking']==2:quality.append(dict(start=r['t'],end=r['t'],reason=r['reason'],packets=1))
  else:quality[-1]['end']=r['t'];quality[-1]['packets']+=1
checks={}
for f in (anchor,final16,repeat16):
 t=f['t'];i=int(np.argmin(abs(pt-t)));win=abs(pt-t)<.25;wheel_window=1.5 if f is anchor else .3;sw=abs(st-t)<wheel_window
 c=dict(wheel_check_half_window_s=wheel_window,nearest_wheel_sample_delta_s=float(st[np.argmin(abs(st-t))]-t),pair_delta_s=float(pt[i]-t),phone_usable=bool(good[i]),phone_frames=int(win.sum()),phone_span_mm=float(np.max(np.linalg.norm(pp[win]-pp[i],axis=1))),phone_heading_span_deg=float(np.degrees(np.ptp(ph[win]))),wheel_span_mm=float(np.ptp(sd[sw])),wheel_heading_span_deg=float(np.degrees(np.ptp(sh[sw]))))
 assert c['phone_usable'] and abs(c['pair_delta_s'])<.25 and c['phone_frames']>=3 and c['phone_span_mm']<20 and c['phone_heading_span_deg']<2
 assert c['wheel_span_mm']<5 and c['wheel_heading_span_deg']<2
 checks[f['local_time']]=c
phases={}
for name,start,end in [('outbound',t0,last15['t']),('return',last15['t'],final16['t']),('all',t0,final16['t'])]:
 k=(pt>=start)&(pt<=end)&good
 phases[name]=dict(samples=int(k.sum()),heading_abs_percentiles_deg=np.percentile(abs(hdiff[k]),[50,95,100]).tolist(),separation_percentiles_mm=np.percentile(sep[k],[50,95,100]).tolist())
tag15=next(x['world_from_tag'] for x in config['landmarks'] if x['id']==15)
path=lambda t:float(np.interp(t,st,[float(s['travelled_distance_mm']) for s in sensors])-np.interp(t0,st,[float(s['travelled_distance_mm']) for s in sensors]))
summary=dict(session=str(raw[0]['session']),packets=len(raw),unique_frames=len(rows),tracking=dict(collections.Counter(r['tracking'] for r in raw)),reasons=dict(collections.Counter(r['reason'] for r in raw)),sequence_gaps=sum(max(0,b['seq']-a['seq']-1) for a,b in zip(raw,raw[1:])),recorded_live_tag16_anchor='RoomTrek tag16 alignment:' in text,offline_anchor=anchor,clock_epoch_span_s=float(np.ptp(offsets)),phone_feature_percentiles=np.percentile([r['features'] for r in raw],[0,50,95,100]).tolist(),limited_intervals=quality,stationary_checks=checks,phases=phases,tag_fixes=fixes,wheel_travel_mm=path(final16['t']),tag15_travel_mm=path(last15['t']),tag15_stop_range_mm=math.hypot(tag15[0][3]*1000-last15['pose']['x_mm'],tag15[1][3]*1000-last15['pose']['y_mm']),end_tag16=final16,repeat_tag16=repeat16,sensor_errors=text.count('Roomba sensor poll failed.'),nul_bytes=text.count('\0'),battery_start_percent=float(sensors[0]['battery_percent']),battery_end_percent=float(sensors[-1]['battery_percent']))
# Relative endpoint motions, with the start tag16 as the shared room baseline.
for f in (final16,repeat16):
 f['tag_displacement_from_start_mm']=float(np.linalg.norm(np.array([f['pose']['x_mm'],f['pose']['y_mm']])-axy))
 f['phone_displacement_from_start_mm']=float(np.linalg.norm(np.array(f['phone_xy_mm'])-axy))
 f['wheel_displacement_from_start_mm']=float(np.linalg.norm(np.array(f['wheel_xy_mm'])-axy))
 f['tag_heading_change_deg']=float(np.degrees(wrap(f['pose']['heading_rad']-a['heading_rad'])))
 f['phone_heading_change_deg']=float(np.degrees(wrap(interp(f['t'],pheading)-a['heading_rad'])))
 f['wheel_heading_change_deg']=float(np.degrees(wrap(interp(f['t'],wheading,st)-a['heading_rad'])))
(OUT/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
with (OUT/'comparison.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['epoch_s','usable','wheel_x_mm','wheel_y_mm','phone_x_mm','phone_y_mm','phone_minus_wheel_heading_deg','separation_mm']);w.writerows(zip(pt,good,*wx.T,*phone.T,hdiff,sep))
with (OUT/'tag-checks.csv').open('w') as f:
 fields=['tag','purpose','accepted','local_time','phone_tag_mm','wheel_tag_mm','phone_tag_heading_deg','wheel_tag_heading_deg','phone_wheel_mm','phone_wheel_heading_deg','phone_usable'];w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(fixes)
fig,axs=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
axs[0,0].plot(wheel[:,0]/1000,wheel[:,1]/1000,label='Wheel integration; no later tag corrections')
axs[0,0].plot(np.where(good,phone[:,0]/1000,np.nan),np.where(good,phone[:,1]/1000,np.nan),label='iPhone robot centre')
for i,f in enumerate(fixes):
 if f['accepted']:
  p=f['pose'];axs[0,0].scatter(p['x_mm']/1000,p['y_mm']/1000,marker='x',c='black');axs[0,0].annotate('tag '+str(f['tag']),(p['x_mm']/1000,p['y_mm']/1000),fontsize=8)
axs[0,0].set(title='One initial tag16 alignment, scale 1; no path fitting',xlabel='Room X (m)',ylabel='Room Y (m)');axs[0,0].axis('equal');axs[0,0].legend(fontsize=8);axs[0,0].grid(alpha=.3)
x=[datetime.fromtimestamp(t) for t in pt]
axs[0,1].plot(x,np.where(good,sep,np.nan),c='black');axs[0,1].set(title='Phone–wheel separation',ylabel='mm')
axs[1,0].plot(x,np.where(good,hdiff,np.nan));axs[1,0].set(title='Heading disagreement',ylabel='Phone minus wheel (degrees)')
axs[1,1].plot(x,[r['features'] for r in rows],lw=.8);axs[1,1].set(title='Features: normal tracking throughout this recording',ylabel='Visible features')
for ax in (axs[0,1],axs[1,0],axs[1,1]):
 for f in (last15,final16):ax.axvline(datetime.fromtimestamp(f['t']),c='gray',ls=':',lw=1)
 for gap in quality:ax.axvspan(datetime.fromtimestamp(gap['start']),datetime.fromtimestamp(gap['end']+.1),color='orange',alpha=.2)
 ax.set_xlim(datetime.fromtimestamp(t0),datetime.fromtimestamp(pt[-1]));ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M:%S'));ax.grid(alpha=.3)
fig.suptitle('Scan cool-off round trip — starting tag16, tag15, returning tag16\nStationary tag capture pairing; fixed mount/lens correction; free wheel odometry')
fig.savefig(OUT/'comparison.png',dpi=160);fig.savefig(OUT/'comparison.pdf');plt.close(fig)
print(json.dumps({k:v for k,v in summary.items() if k not in ('tag_fixes','offline_anchor','stationary_checks')},indent=2))

# Preview the live-map renderer with this recording's independently aligned trails.
from roomberry_map_image import render_map
def map_tag_markers(landmarks):
    return [(float(t["world_from_tag"][0][3])*1000, float(t["world_from_tag"][1][3])*1000, t["id"], math.atan2(-float(t["world_from_tag"][1][2]), -float(t["world_from_tag"][0][2]))) for t in landmarks]
map_state = json.loads((ROOT/'roomberry/logs/map-state-reset-20261031-01.json').read_text())
map_state['pose'] = None
map_state['run_trails'] = dict(wheel=wheel.tolist(), iphone=phone[good].tolist())
(OUT/'map.png').write_bytes(render_map(map_state, map_tag_markers(config['landmarks']),
    caption='Recorded run135820; initial tag16 alignment; independent trails'))
