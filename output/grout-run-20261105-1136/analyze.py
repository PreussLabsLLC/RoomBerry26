# @(#)analyze.py 3.1.grout.19 2026/11/05
"""Offline bump comparison; receipt minus phone event age is approximate alignment."""
import sys, csv, bisect, json, math, statistics
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'roomberry'))
from roomberry_navlink import LOG_HEADER, RECEIPT, decode_packet, packet_fields
root=Path(__file__).resolve().parents[2]
logs=(root/'roomberry/logs/roomberry.log').read_text().splitlines()
all_events=[]
for stamp in ('084144','091626','101653','110632','113607'):
 path=root/f'roomberry/logs/navlink/roomberry-navlink-20261105-{stamp}-0000.bin'
 events={}
 with path.open('rb') as f:
  f.read(LOG_HEADER.size)
  while record:=f.read(144):
   if len(record)!=144:break
   v=decode_packet(record[16:]);r=dict(zip(packet_fields(v),v))
   if r['type']!=3 or not r['bump_count']:continue
   key=(r['session'],r['calibration'],r['bump_count'])
   t=RECEIPT.unpack(record[:16])[0]/1e9-(r['send_us']-r['bump_us'])/1e6
   if key not in events:events[key]=dict(time=t,g=0,count=r['bump_count'])
   events[key]['g']=max(events[key]['g'],r['last_bump_peak_mm_s2']/9806.65)
 samples=[]
 for line in logs:
  if 'GridRunner sample: ' not in line:continue
  t=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp()
  r=json.loads(line.split('GridRunner sample: ')[1]);samples.append((t,r))
 times=[r[0] for r in samples]
 rows=list(csv.DictReader((root/f'roomberry/logs/sensors/roomberry-sensors-20261105-{('101654' if stamp=='101653' else stamp)}.csv').open()))
 st=[float(r['epoch_s']) for r in rows]
 print('\nSESSION',stamp)
 for e in events.values():
  if e['time']<st[0]-.1:continue
  i=bisect.bisect_left(st,e['time']);i=min(i,len(st)-1)
  j=bisect.bisect_right(times,e['time'])-1
  r=samples[j][1] if j>=0 and e['time']-times[j]<.6 else {}
  if not r:
   speed=(float(rows[i]['requested_left_velocity_mm_s'])+float(rows[i]['requested_right_velocity_mm_s']))/2
   r=dict(stage='reverse' if speed<0 else 'forward' if speed>0 else 'stationary')
  e.update(session=stamp,time_text=datetime.fromtimestamp(e['time']).strftime('%H:%M:%S.%f')[:-3],
   stage=r.get('stage','inactive/scan/manual'),leg_distance_mm=r.get('wheel_distance_mm',''),
   sensor_distance_mm=rows[i]['distance_mm'],sensor_time_error_s=round(abs(st[i]-e['time']),3))
  all_events.append(e)
  print(e['time_text'],e['count'],round(e['g'],3),e['stage'],round(e['leg_distance_mm']) if e['leg_distance_mm']!='' else '', 'sensor',round(float(e['sensor_distance_mm'])))
 latest=[(t,r) for t,r in samples if datetime.fromtimestamp(t).strftime('%H%M%S')>=stamp and datetime.fromtimestamp(t).strftime('%H%M%S')<('114300' if stamp=='113607' else {'084144':'084800','091626':'093000','101653':'102200','110632':'112000'}[stamp])]
 for stage in ('driving','return','approach'):
  a=[r for t,r in latest if r.get('stage')==stage]
  if a:print(stage,len(a),'locked',sum(r.get('tracking')=='locked' for r in a),'median_conf',round(statistics.median(r.get('confidence',0) for r in a),3))
with (Path(__file__).parent/'bumps.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(all_events[0]));w.writeheader();w.writerows(all_events)

# Encoder coordinates make repeat impact locations comparable without trusting
# corrected map anchors. Manual moves/restarts and slip still limit the comparison.
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained')
colors={'101653':'#4477aa','110632':'#ee7733','113607':'#228833'}
for stamp,color in colors.items():
 for ax,phases in zip(axes,({'reverse','driving'},{'forward','return','approach'})):
  pts=[e for e in all_events if e['session']==stamp and e['stage'] in phases]
  ax.scatter([-float(e['sensor_distance_mm'])/1000 for e in pts],[e['g'] for e in pts],s=60,label=stamp[:2]+':'+stamp[2:4],color=color)
  ax.axhline(.6,color='#777777',ls='--',lw=.5)
for ax,title in zip(axes,('Reverse / outbound impacts','Forward / return impacts (includes manual positioning)')):
 ax.set_title(title,loc='left');ax.set_ylabel('Phone event peak (g)');ax.grid(alpha=.2);ax.legend();ax.set_ylim(bottom=0)
axes[-1].set_xlabel('Reverse encoder displacement from session zero (m) — not a surveyed room coordinate')
fig.suptitle('Recent phone bump events: final refined peaks, approximate event-time alignment')
fig.savefig(Path(__file__).parent/'bump-comparison.png',dpi=160)
