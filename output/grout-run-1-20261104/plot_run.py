# @(#)plot_run.py 3.1.grid.1 2026/11/04 10:10:00
"""Plot recorded single-stripe detections; never interpolate invalid frames."""
from pathlib import Path
import csv
import datetime as dt
import struct
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'roomberry'))
from roomberry_gridrunner import GRID_PACKET, GRID_FIELDS

OUT = Path(__file__).resolve().parent
source = ROOT / 'roomberry/logs/navlink/roomberry-navlink-20261104-094541-0000.bin'
start = dt.datetime(2026, 11, 4, 9, 45, 51, 389000)
stop = (dt.datetime(2026, 11, 4, 9, 45, 59, 652000)-start).total_seconds()
rows = []
data = source.read_bytes()
for i in range(16, len(data)-143, 144):
    record = data[i:i+144]
    wall_ns, _ = struct.unpack('<QQ', record[:16])
    time = dt.datetime.fromtimestamp(wall_ns/1e9)
    elapsed = (time-start).total_seconds()
    if record[21] != 5 or not 0 <= elapsed <= stop+1:
        continue
    row = dict(zip(GRID_FIELDS, GRID_PACKET.unpack(record[16:])))
    rows.append(dict(elapsed_s=elapsed, timestamp=time.isoformat(timespec='milliseconds'),
                     **{k: row[k] for k in ('seq','flags','reason','scan1_x','scan1_y',
                         'scan2_x','scan2_y','offset_mm','line_angle_rad','confidence')}))
with (OUT/'detections.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
t = np.array([r['elapsed_s'] for r in rows])
valid = np.array([r['flags'] == 3 for r in rows])
lost = t[~valid][0]
def values(key, scale=1):
    return np.array([r[key]*scale if good else np.nan for r,good in zip(rows,valid)])

plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True,
                         gridspec_kw={'height_ratios':[1.6,1,1]}, constrained_layout=True)
fig.suptitle('Grout run #1 — tracking one grout stripe\nNovember 4, 2026 · 09:45:51–09:46:00', fontsize=15, y=.995)
ax = axes[0]
ax.plot(t, values('scan1_x',100), '.-', ms=3, label='Upper scanline: stripe center')
ax.plot(t, values('scan2_x',100), '.-', ms=3, label='Lower scanline: same stripe')
ax.axhline(12.5, color='#bb4422', ls='--', label='Left search boundary (12.5%)')
ax.set_ylabel('Horizontal image position (%)\n0 = left edge')
ax.set_ylim(10,34)
ax.legend(loc='upper left', fontsize=9)
axes[1].plot(t,values('offset_mm'),'.-',ms=3,color='#417b42')
axes[1].set_ylabel('Estimated line offset (mm)\npositive = robot left')
axes[2].plot(t,values('line_angle_rad',180/np.pi),'.-',ms=3,color='#7855a5')
axes[2].set_ylabel('Estimated line angle (°)')
axes[2].set_xlabel('Seconds since first Pi driving sample (receipt time)')
for ax in axes:
    ax.axvspan(lost,t[-1],color='#e7e7e7',zorder=0)
    ax.axvline(lost,color='#bb4422',lw=1.2)
    ax.axvline(stop,color='#444444',ls=':',lw=1.4)
    ax.grid(alpha=.2)
    ax.set_xlim(0,t[-1])
axes[0].text(lost-.12,33,'First invalid detection\n8.144 s',ha='right',va='top',color='#a53619')
axes[1].text(stop+.08,-28,'Pi stop\n8.263 s',va='top',fontsize=9)
fig.get_layout_engine().set(rect=(0,.045,1,.92))
fig.text(.05,.012,'Invalid packets are blank: their zero/default coordinates are not measurements.\n'
         'Search-boundary clipping is plausible; camera images were not recorded to confirm it.',fontsize=9,color='#555555')
for ext in ('png','pdf'):
    fig.savefig(OUT/f'grout-line-over-time.{ext}',dpi=180)
print(f'{len(rows)} packets; first invalid {lost:.3f} s; stop {stop:.3f} s')
