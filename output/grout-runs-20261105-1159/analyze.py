# @(#)analyze.py 3.1.grout.19 2026/11/05
"""Compare uploaded runs using wheel sensors independently of corrected map poses."""
import csv,json,ast,bisect,statistics,math
from pathlib import Path
from datetime import datetime
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
lines=[l for l in (root/'roomberry/logs/roomberry.log').read_text().splitlines() if l.startswith('2026-11-05 ')]
rows=list(csv.DictReader((root/'roomberry/logs/sensors/roomberry-sensors-20261105-115925.csv').open()))
times=[float(r['epoch_s']) for r in rows]
def ts(s):return datetime.strptime(s,'%Y-%m-%d %H:%M:%S,%f').timestamp()
def nearest(t):
 i=bisect.bisect_left(times,t);return rows[min((max(0,i-1),min(i,len(rows)-1)),key=lambda k:abs(times[k]-t))]
thresholds=[];samples=[];checkpoints=[]
for l in lines:
 t=ts(l[:23])
 if 'GridRunner threshold settled: ' in l:thresholds.append((t,json.loads(l.split('settled: ')[1])))
 if 'GridRunner sample: ' in l:samples.append((t,json.loads(l.split('sample: ')[1])))
 if 'GridRunner tag checkpoint: ' in l:checkpoints.append((t,json.loads(l.split('checkpoint: ')[1])))
starts=['2026-11-05 11:59:50,336','2026-11-05 12:06:27,156','2026-11-05 12:10:00,585']
ends=['2026-11-05 12:06:12,520','2026-11-05 12:09:47,433','2026-11-05 12:12:27,167']
result=[]
for n,((t,threshold),start,end) in enumerate(zip(thresholds,starts,ends),1):
 a,b=ts(start),ts(end);tr=nearest(t);er=nearest(b+.3)
 distance=float(tr['distance_mm']);ret=float(er['distance_mm'])-distance
 r=dict(run=n,start=start[11:19],outbound_mm=threshold['settled_distance_mm'],
  return_net_mm=ret,closure_mm=ret-threshold['settled_distance_mm'],
  return_path_mm=float(er['travelled_distance_mm'])-float(tr['travelled_distance_mm']),
  threshold_sensor_mm=distance,end_sensor_mm=float(er['distance_mm']))
 for l in lines:
  lt=ts(l[:23])
  if a<=lt<=b and 'threshold clearance: measured_mm=' in l:r['clearance_mm']=float(l.split('measured_mm=')[1].split()[0])
 leg=[v for st,v in samples if a<=st<=b and v['stage']=='driving']
 r['outbound_locked_samples']=sum(v.get('tracking')=='locked' for v in leg);r['outbound_samples']=len(leg)
 cp=[v for ct,v in checkpoints if a<=ct<=b];r['checkpoints']=len(cp);r['accepted_checkpoints']=sum(v['accepted'] for v in cp)
 scans=[]
 for l in lines:
  lt=ts(l[:23])
  if a<=lt<=b and 'Vision scan:' in l:scans.append(ast.literal_eval(l.split('timings_ms=')[1])['total']/1000)
 r['scans']=len(scans);r['scan_seconds']=sum(scans)
 result.append(r);print(json.dumps(r,indent=2))
print('full run difference',result[2]['outbound_mm']-result[1]['outbound_mm'])
print('mean full runs',statistics.mean(r['outbound_mm'] for r in result[1:]))
with (out/'distances.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=result[0].keys());w.writeheader();w.writerows(result)
(out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
