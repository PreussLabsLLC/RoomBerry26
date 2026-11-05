import runpy,re,csv,json,ast,statistics
from datetime import datetime
from pathlib import Path
import numpy as np
v=runpy.run_path(str(Path(__file__).with_name('analyze.py')));out=v['OUT'];rows=[];anchors=[]
for line in v['lines']:
 t=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').timestamp() if re.match(r'\d{4}-',line)else None
 if t is None:continue
 m=re.search(r'Phone position correction: error_mm=([\d.]+) step_mm=([\d.]+) total_correction_mm=([\d.]+)',line)
 if m:
  travel=(np.interp(t,v['st'],v['sf']('travelled_distance_mm'))-v['sf']('travelled_distance_mm')[0])/10
  rows.append(dict(time=v['stamp'](t),roomba_travelled_cm=travel,live_residual_cm=float(m[1])/10,disagreement_pct=float(m[1])/travel*10 if travel>0 else None,total_correction_cm=float(m[3])/10))
 m=re.search(r'Phone position anchored:.*room_mm=\(([-\d.]+), ([-\d.]+)\)',line)
 if m:
  i=np.argmin(abs(v['nt']-t));p=np.array([float(m[1]),float(m[2])]);phone=v['aligned'][i]
  anchors.append(dict(time=v['stamp'](t),roomba_travelled_cm=float((np.interp(t,v['st'],v['sf']('travelled_distance_mm'))-v['sf']('travelled_distance_mm')[0])/10),room_xy_mm=p.tolist(),fixed_phone_xy_mm=phone.tolist(),fixed_separation_cm=float(np.linalg.norm(p-phone))/10))
for name,r in [('live-correction.csv',rows),('tag-anchors.csv',anchors)]:
 with (out/name).open('w')as f:
  w=csv.DictWriter(f,fieldnames=r[0]);w.writeheader();w.writerows(r)
print('ANCHORS',json.dumps(anchors,indent=2));print('MAX LIVE',max(rows,key=lambda r:r['live_residual_cm']));print('LAST LIVE',rows[-1])
