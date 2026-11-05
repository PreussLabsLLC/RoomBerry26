# @(#)analyze.py 2.3.analysis.1 2026/10/30 13:45:00
"""Offline reconciliation; receipt-time alignment is approximate, not clock sync."""
import ast
import csv
from datetime import datetime
from pathlib import Path
import re
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
nav = list(csv.DictReader(open(OUT / 'navlink.csv')))
sensor = list(csv.DictReader(open(ROOT / 'roomberry/logs/sensors/roomberry-sensors-20261030-131355.csv')))
nt = np.array([int(r['receive_epoch_ns']) / 1e9 for r in nav])
receipt_t = nt.copy()
st = np.array([float(r['epoch_s']) for r in sensor])
def nf(k): return np.array([float(r[k]) for r in nav])
def sf(k): return np.array([float(r[k] or 0) for r in sensor])
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
def stamp(t): return datetime.fromtimestamp(t).strftime('%H:%M:%S.%f')[:-3]

# Estimate a constant clock offset from the least-delayed receipt; use capture
# uptime for motion comparisons so receive-thread stalls cannot shift the pose.
# Unknown minimum one-way latency remains; this is offline estimation only.
send_t = nf('send_us') / 1e6
offset = np.min(receipt_t - send_t)
nt = nf('frame_us') / 1e6 + offset

# Use Pi wall-clock receipt for comparison; never subtract phone and Pi uptime.
xy = np.array([nf('x_mm'), nf('y_mm')]).T
nh = np.unwrap(nf('heading_rad'))
sa = np.radians(sf('angle_deg'))
sd = sf('distance_mm')
poses = []
for line in open(ROOT / 'roomberry/logs/roomberry.log'):
    m = re.search(r"pose=(\{'x_mm':.*?\})", line)
    if m:
        p = ast.literal_eval(m[1])
        t = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f').timestamp()
        poses.append((t, p, line.strip()))

# Establish a fixed room rotation and translation at the stationary initial scan.
anchor_t, anchor, _ = next(p for p in poses if 'Discovery initial_scan:' in p[2])
ni = np.argmin(abs(nt - anchor_t))
# Translation versus signed wheel motion shows camera +Y faces backward.
# Infer the mount yaw from straight half-second intervals, before room alignment.
k = 5
wheel_d = np.interp(nt, st, sd)
wheel_a = np.interp(nt, st, np.degrees(sa))
dd = wheel_d[k:] - wheel_d[:-k]
da = wheel_a[k:] - wheel_a[:-k]
dxy = xy[k:] - xy[:-k]
ok = (abs(dd) > 25) & (abs(da) < 3) & (nt[k:] - nt[:-k] < .7)
offsets = wrap(np.arctan2(dxy[:,1], dxy[:,0]) - nh[:-k] - np.where(dd < 0, np.pi, 0))
mount = np.angle(np.mean(np.exp(1j * offsets[ok])))
print('inferred camera-to-forward yaw degrees', np.degrees(mount), 'intervals',sum(ok))
rot = wrap(anchor['heading_rad'] - nh[ni] - mount)
R = np.array([[np.cos(rot), -np.sin(rot)], [np.sin(rot), np.cos(rot)]])
aligned = (xy - xy[ni]) @ R.T + [anchor['x_mm'], anchor['y_mm']]
print('nav receipt coverage', stamp(receipt_t[0]), stamp(receipt_t[-1]), 'records', len(nav))
print('estimated capture coverage',stamp(nt[0]),stamp(nt[-1]))
print('excess receipt delay percentiles seconds',np.percentile(receipt_t-send_t-offset,[0,50,95,99,100]))
print('alignment rotation degrees', np.degrees(rot), 'anchor', stamp(anchor_t))
print('tracking', sorted(set((r['tracking'],r['reason'],r['flags']) for r in nav)))
print('feature percentiles', np.percentile(nf('feature_count'), [0,50,95,100]))
print('z change mm', nf('z_mm')[-1]-nf('z_mm')[ni])
print('battery endpoints',nf('battery_pct')[0],nf('battery_pct')[-1])
print('phone send duration', (nf('send_us')[-1]-nf('send_us')[0])/1e6)
print('receipt duration',receipt_t[-1]-receipt_t[0])
for i in np.where(np.diff(receipt_t) > .3)[0]:
    print('receipt gap',stamp(receipt_t[i]),stamp(receipt_t[i+1]),'seconds',receipt_t[i+1]-receipt_t[i],
          'send gap',(nf('send_us')[i+1]-nf('send_us')[i])/1e6,
          'next intervals',np.diff(receipt_t)[i+1:i+6])

rows=[]
for t,p,line in poses:
    if t < nt[0] or t > nt[-1]: continue
    i=np.argmin(abs(nt-t))
    rows.append(dict(time=stamp(t),epoch_s=t,room_x_mm=p['x_mm'],room_y_mm=p['y_mm'],
        room_heading_deg=np.degrees(p['heading_rad']),phone_aligned_x_mm=aligned[i,0],
        phone_aligned_y_mm=aligned[i,1],separation_mm=np.linalg.norm(aligned[i]-[p['x_mm'],p['y_mm']]),
        heading_difference_deg=np.degrees(wrap(p['heading_rad']-nh[i]-rot-mount)),
        localization_age_s=p['localization_age'],event=line.split(' - ')[-1].split('pose=')[0]))
with open(OUT/'pose-comparison.csv','w') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print('POSE COMPARISONS')
for r in rows:
    print(r['time'],'separation',round(r['separation_mm']),'heading diff',round(r['heading_difference_deg'],1),
          'age',round(r['localization_age_s'],1),r['event'][:70])

# Interval wheel vs phone yaw avoids room-frame and tag-correction dependence.
print('INTERVALS: wheel distance, phone path, wheel yaw, phone yaw')
for a,b in [('13:14:39','13:14:49'),('13:14:58','13:15:15'),('13:15:22','13:15:44'),
            ('13:15:54','13:16:13'),('13:16:14','13:16:46'),('13:18:39','13:18:58'),
            ('13:18:59','13:19:20')]:
    ts=[datetime.strptime('2026-10-30 '+s,'%Y-%m-%d %H:%M:%S').timestamp() for s in [a,b]]
    ix=[np.argmin(abs(nt-t)) for t in ts]; sx=[np.argmin(abs(st-t)) for t in ts]
    path=np.linalg.norm(np.diff(xy[ix[0]:ix[1]+1],axis=0),axis=1).sum()
    print(a,b,'wheel signed',round(sd[sx[1]]-sd[sx[0]]),'wheel absolute',round(abs(np.diff(sd[sx[0]:sx[1]+1])).sum()),
          'phone path',round(path),'phone displacement',round(np.linalg.norm(xy[ix[1]]-xy[ix[0]])),
          'wheel yaw',round(np.degrees(sa[sx[1]]-sa[sx[0]]),1),'phone yaw',round(np.degrees(nh[ix[1]]-nh[ix[0]]),1),
          'gyro yaw',round(np.degrees(np.sum((nf('yaw_rad_s')[ix[0]+1:ix[1]+1]+nf('yaw_rad_s')[ix[0]:ix[1]])*.5*np.diff(nf('imu_us')[ix[0]:ix[1]+1])/1e6)),1))

# Lightweight standalone vector plot, no plotting dependencies.
allxy=np.vstack([aligned,[[r['room_x_mm'],r['room_y_mm']] for r in rows]])/1000
lo=allxy.min(axis=0)-.2;hi=allxy.max(axis=0)+.2
scale=min(840/(hi[0]-lo[0]),540/(hi[1]-lo[1]))
def point(p):
    p=np.asarray(p)/1000
    return f'{70+(p[0]-lo[0])*scale:.1f},{640-(p[1]-lo[1])*scale:.1f}'
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="740" viewBox="0 0 1000 740">',
     '<rect width="1000" height="740" fill="white"/>',
     '<g font-family="sans-serif" font-size="16" fill="#222">',
     '<text x="40" y="30">October 30 run: fixed initial alignment, no scale fitting</text>',
     '<text x="40" y="57" fill="#1769aa">Blue: phone camera trajectory, 13:13:56–13:20:09</text>',
     '<text x="40" y="82" fill="#c43c26">Red: Roomberry logged poses (sparse samples, includes tag corrections)</text>']
for x in np.arange(np.ceil(lo[0]),hi[0],1):
    a=point([x*1000,lo[1]*1000]);b=point([x*1000,hi[1]*1000])
    svg += [f'<line x1="{a.split(",")[0]}" y1="{a.split(",")[1]}" x2="{b.split(",")[0]}" y2="{b.split(",")[1]}" stroke="#ddd"/>',f'<text x="{a.split(",")[0]}" y="665">{x:g}</text>']
for y in np.arange(np.ceil(lo[1]),hi[1],1):
    a=point([lo[0]*1000,y*1000]);b=point([hi[0]*1000,y*1000])
    svg += [f'<line x1="{a.split(",")[0]}" y1="{a.split(",")[1]}" x2="{b.split(",")[0]}" y2="{b.split(",")[1]}" stroke="#ddd"/>',f'<text x="30" y="{a.split(",")[1]}">{y:g}</text>']
svg += ['<polyline points="'+' '.join(point(p) for p in aligned[::3])+'" fill="none" stroke="#1769aa" stroke-width="2"/>',
        '<polyline points="'+' '.join(point([r['room_x_mm'],r['room_y_mm']]) for r in rows)+'" fill="none" stroke="#c43c26" stroke-width="2" stroke-dasharray="6 4"/>']
for r in rows:
    if 'Stationary AprilTag' not in r['event'] and 'obstacle contact' not in r['event']:
        p=point([r['room_x_mm'],r['room_y_mm']]).split(',')
        svg += [f'<circle cx="{p[0]}" cy="{p[1]}" r="4" fill="#c43c26"/>',f'<text x="{float(p[0])+6}" y="{float(p[1])-6}" font-size="12">{r["time"][:8]}</text>']
svg += ['<text x="40" y="705">Axes: room metres. Phone mount offset and drift are uncorrected; this is not surveyed ground truth.</text></g></svg>']
(OUT/'trajectory.svg').write_text('\n'.join(svg))
