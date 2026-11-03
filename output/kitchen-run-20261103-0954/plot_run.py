# @(#)plot_run.py 3.1.plot.1 2026/11/03 10:15:00
"""Reproduce kitchen trajectory, impact and floor-IR plots from recorded logs."""
import csv
import io
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MPLCONFIGDIR', '/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'roomberry'))
import roomberry_navlink as nav

metrics = json.loads((ROOT / 'output/calibration-20261103-0954-metrics.json').read_text())
start, end = metrics['start'], metrics['abort']
turn = metrics['turnaround'] - start
samples = []
cached_samples = OUT / 'motion-samples.json'
if cached_samples.exists():
    samples = json.loads(cached_samples.read_text())
else:
    for line in (ROOT / 'roomberry/logs/roomberry.log').read_text().splitlines():
        if 'Calibration sample: ' in line:
            row = json.loads(line.split('Calibration sample: ')[1])
            if start <= row['wall_time'] <= end:
                samples.append(row)
    cached_samples.write_text(json.dumps(samples, indent=2)+'\n')
poses = [metrics['checkpoints'][0], *samples, metrics['checkpoints'][1]]
poses.sort(key=lambda r: r['wall_time'])
pt = np.array([r['wall_time']-start for r in poses])
wx = -np.array([r['wheels_pose']['x_mm'] for r in poses])/1000
wy = np.array([r['wheels_pose']['y_mm'] for r in poses])
px = -np.array([r['iphone_pose']['x_mm'] for r in poses])/1000
py = np.array([r['iphone_pose']['y_mm'] for r in poses])
rows = list(csv.DictReader((ROOT / 'roomberry/logs/sensors/roomberry-sensors-20261103-095424.csv').open()))
rows = [r for r in rows if start <= float(r['epoch_s']) <= end+1.5]
t = np.array([float(r['epoch_s'])-start for r in rows])
d = -np.array([float(r['distance_mm']) for r in rows])/1000
keys = ['cliff_left_signal', 'cliff_front_left_signal', 'cliff_front_right_signal', 'cliff_right_signal']
names = ['Left floor IR', 'Front-left floor IR', 'Front-right floor IR', 'Right floor IR']
signals = np.array([[float(r[k]) for r in rows] for k in keys])
# Local median removes slow floor/height drift. These are heuristic dips,
# not confirmed grout, and no surveyed sensor offsets or grid phase are known.
baselines = np.array([[np.median(v[np.abs(t-ti) <= 1.25]) for ti in t] for v in signals])
dip = baselines-signals
noise = np.maximum(1, 1.4826*np.median(np.abs(dip-np.median(dip, axis=1)[:, None]), axis=1))
z = dip/noise[:, None]
score = np.sort(z, axis=0)[-2]  # At least two channels must dip simultaneously.
indices = [i for i in range(1, len(t)-1) if t[i] <= end-start and
           score[i] >= 2.5 and score[i] >= score[i-1] and score[i] > score[i+1]]
chosen = []
for i in sorted(indices, key=lambda i: -score[i]):
    if all(abs(t[i]-t[j]) >= .8 for j in chosen):
        chosen.append(i)
chosen.sort()
events = []
for i in chosen:
    events.append(dict(kind='IR dip candidate', elapsed_s=float(t[i]),
                       wheel_distance_from_start_m=float(d[i]), score=float(score[i]),
                       channels='; '.join(names[j] for j in range(4) if z[j, i] >= 2.5)))
for count in ('8', '9'):
    event = metrics['bumps'][count]
    et = event['first_receipt_s']-start
    events.append(dict(kind='phone bump '+count, elapsed_s=et,
                       wheel_distance_from_start_m=float(np.interp(et, t, d)),
                       peak_mm_s2=event['peak_mm_s2'], peak_g=event['peak_mm_s2']/9806.65))
events.sort(key=lambda r: r['elapsed_s'])
fields = ['kind', 'elapsed_s', 'wheel_distance_from_start_m', 'score', 'channels', 'peak_mm_s2', 'peak_g']
with (OUT / 'events.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(events)
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'figure.facecolor': '#fafbfc', 'axes.facecolor': 'white', 'savefig.facecolor': '#fafbfc'})
blue, orange, red, green = '#2466a5', '#d87823', '#bf303d', '#36846b'

def save(fig, name):
    fig.savefig(OUT / (name+'.png'), dpi=180)
    fig.savefig(OUT / (name+'.pdf'))
    plt.close(fig)

fig, axes = plt.subplots(2, 1, figsize=(13, 8.4), gridspec_kw={'height_ratios': [1.1, 1]}, layout='constrained')
fig.suptitle('Kitchen run · iPhone X · 3 November 2026, 09:54–09:56', fontsize=17, weight='bold')
ax = axes[0]
for a, b, color, name in [(wx, wy, blue, 'Wheel estimate'), (px, py, orange, 'GroundHog estimate')]:
    outbound, returning = pt <= turn, pt >= turn
    ax.plot(a[outbound], b[outbound], color=color, lw=1.8, label=name+' · reverse')
    ax.plot(a[returning], b[returning], color=color, lw=1.8, ls='--', label=name+' · return')
    for et in (25, 55, 95):
        j = np.searchsorted(pt, et)
        if j+2 < len(pt):
            ax.annotate('', xy=(a[j+2], b[j+2]), xytext=(a[j], b[j]),
                        arrowprops=dict(arrowstyle='->', color=color, lw=1.8))
for e in events:
    et = e['elapsed_s']
    if e['kind'].startswith('phone'):
        ex, ey = np.interp(et, pt, wx), np.interp(et, pt, wy)
        ax.scatter(ex, ey, marker='*', s=220, color=red, edgecolors='white', zorder=5)
    else:
        ax.scatter(np.interp(et, pt, wx), np.interp(et, pt, wy), marker='D', s=50,
                   facecolors='white', edgecolors=green, linewidths=1.8, zorder=5)
ax.annotate('Start at tag 15\nmanual alignment', (0, 0), xytext=(.15, 36), arrowprops=dict(arrowstyle='-', color='#666'))
ax.annotate('Threshold bump\n0.49 g → turnaround', (wx[np.argmin(abs(pt-turn))], wy[np.argmin(abs(pt-turn))]),
            xytext=(3.4, 98), arrowprops=dict(arrowstyle='-', color=red), color=red)
ax.annotate('Return bump\n0.63 g → abort', (wx[-1], wy[-1]), xytext=(2.65, -105),
            arrowprops=dict(arrowstyle='-', color=red), color=red)
ax.set(xlabel='Distance opposite initial forward heading (m)', ylabel='Lateral position (mm, +left)',
       title='Local trajectories — lateral scale magnified; paths are estimates, not overhead truth', ylim=(-125, 135), xlim=(-.08, 4.9))
ax.axhline(0, color='#ddd', lw=.8)
ax.grid(alpha=.18)
ax.legend(loc='upper left', ncol=2, fontsize=8)
ax = axes[1]
ax.axvspan(0, turn, color=blue, alpha=.06)
ax.axvspan(turn, end-start, color=orange, alpha=.06)
ax.plot(pt, wx, color=blue, label='Wheel X projection')
ax.plot(pt, px, color=orange, label='GroundHog X projection')
ax.plot(t, d, color=blue, alpha=.35, lw=.8, label='Signed wheel distance (includes stop settling)')
for e in events:
    et, dist = e['elapsed_s'], e['wheel_distance_from_start_m']
    bump = e['kind'].startswith('phone')
    ax.axvline(et, color=red if bump else green, ls=':' if bump else '--', alpha=.7)
    ax.scatter(et, dist, marker='*' if bump else 'D', s=150 if bump else 45,
               color=red if bump else green, zorder=5)
    if not bump:
        ax.annotate('IR dip?\n'+f'{et:.1f} s', (et, dist), xytext=(et+2, dist-.7),
                    color=green, fontsize=9, arrowprops=dict(arrowstyle='-', color=green))
ax.text(25, 4.8, 'REVERSE', color=blue, ha='center', fontsize=9)
ax.text(96, 4.8, 'RETURN', color=orange, ha='center', fontsize=9)
ax.set(xlabel='Seconds since 09:54:34.514 (Pi clock)', ylabel='Distance from start (m)', ylim=(-.15, 5.05), xlim=(-1, end-start+2),
       title='Bumps (red stars) and coincident floor-IR dips (green diamonds; unconfirmed grout)')
ax.grid(alpha=.18)
ax.legend(loc='lower right', fontsize=8)
fig.supxlabel('The run stopped at ~2.46 m wheel distance from its origin. IR detections do not establish tile positions.', fontsize=9)
save(fig, 'kitchen-run')

fig, axes = plt.subplots(5, 1, figsize=(13, 11), sharex=True, layout='constrained', gridspec_kw={'height_ratios': [1, 1, 1, 1, 1.2]})
fig.suptitle('Kitchen floor IR · raw reflectance and candidate grout indications', fontsize=16, weight='bold')
colors = [blue, orange, '#7754a0', green]
for j, ax in enumerate(axes[:4]):
    ax.plot(t, signals[j], color=colors[j], lw=.9, label=names[j])
    ax.plot(t, baselines[j], color='#333', ls='--', alpha=.5, lw=.8, label='2.5 s local median')
    ax.set_ylabel('Raw signal')
    ax.legend(loc='upper right', fontsize=8, ncol=2)
ax = axes[4]
ax.plot(t, score, color=green, lw=1, label='Second-largest normalized dip across four sensors')
ax.axhline(2.5, color='#888', ls='--', label='Candidate threshold: 2.5 robust noise units')
for i in chosen:
    ax.scatter(t[i], score[i], color=green, marker='D', s=45)
    ax.annotate(f'{t[i]:.1f} s / {d[i]:.3f} m', (t[i], score[i]), xytext=(t[i]+1, score[i]+.35), fontsize=8, color=green)
ax.set(ylabel='Coincident dip score', xlabel='Seconds since 09:54:34.514 (Pi clock)', ylim=(-2.5, max(5, max(score)+.6)))
ax.legend(loc='lower left', fontsize=8)
for ax in axes:
    ax.axvline(turn, color='#777', lw=1, ls=':')
    for e in events:
        ax.axvline(e['elapsed_s'], color=red if e['kind'].startswith('phone') else green, ls=':', alpha=.65)
    ax.grid(alpha=.18)
    ax.set_xlim(0, end-start+1.5)
axes[0].set_title('Red: phone impacts · green: coincident IR dips · gray: turnaround', fontsize=10)
fig.supxlabel('Only two candidate dips; no clean 304.8 mm repeating pattern. Sensor offsets and grout-grid phase are uncalibrated.', fontsize=9)
save(fig, 'floor-ir')
print(json.dumps(events, indent=2))
