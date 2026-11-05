# @(#)plot_run.py 3.1.analysis.1 2026/11/03 14:00:00
"""Plot the complete kitchen run from archived samples and metrics."""
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
m = json.loads((OUT/'metrics.json').read_text())
samples = json.loads((OUT/'motion-samples.json').read_text())
poses = sorted([*m['checkpoints'], *samples], key=lambda r: r['wall_time'])
t = np.array([r['wall_time']-m['start'] for r in poses])
turn = m['turnaround']-m['start']
st = np.array([r['wall_time']-m['start'] for r in samples])
steer = np.array([r['steering'] for r in samples])
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': '#fafbfc',
                     'savefig.facecolor': '#fafbfc'})
fig, axes = plt.subplots(3, 1, figsize=(13, 11), layout='constrained',
                         gridspec_kw={'height_ratios': [1.35, 1, .85]})
fig.suptitle('Complete kitchen run · iPhone X · 3 November 2026, 13:46–13:49',
             fontsize=17, weight='bold')
colors = ['#2466a5', '#d87823']
for key, name, color in zip(('wheels_pose', 'iphone_pose'), ('Wheels', 'GroundHog'), colors):
    x = -np.array([r[key]['x_mm'] for r in poses])/1000
    y = np.array([r[key]['y_mm'] for r in poses])
    h = np.degrees([r[key]['heading_rad'] for r in poses])
    for mask, ls, leg in ((t <= turn, '-', 'reverse'), (t >= turn, '--', 'return')):
        axes[0].plot(x[mask], y[mask], ls=ls, color=color, lw=1.8,
                     label=name+' · '+leg)
    axes[0].scatter(x[-1], y[-1], color=color, edgecolor='white', s=85, zorder=5)
    axes[0].annotate(f'{name} finish: {y[-1]:.0f} mm', (x[-1], y[-1]),
                     xytext=(.35, y[-1]+6), color=color,
                     arrowprops=dict(arrowstyle='-', color=color))
    for et in (25, 60, 105, 140):
        j = np.searchsorted(t, et)
        axes[0].annotate('', xy=(x[j+3], y[j+3]), xytext=(x[j], y[j]),
                         arrowprops=dict(arrowstyle='->', color=color, lw=1.8))
    axes[1].plot(t, h, color=color, lw=1, label=name+' heading')
axes[0].scatter(0, 0, marker='o', s=70, color='#333', zorder=5)
axes[0].annotate('Start, aligned at tag 15', (0, 0), xytext=(.2, 15), fontsize=10)
axes[0].annotate('Threshold bump: 0.47 g\n78.75 s → hold → forward return',
                 (4.58, -52.46), xytext=(2.95, 20), color='#bf303d',
                 arrowprops=dict(arrowstyle='-', color='#bf303d'))
axes[0].scatter(4.58, -52.46, marker='*', color='#bf303d', s=180, zorder=5)
axes[0].set(xlabel='Distance opposite initial forward heading (m)',
            ylabel='Lateral position (mm, +left)', ylim=(-260, 65), xlim=(-.1, 4.95),
            title='Both legs accumulate rightward displacement — lateral scale magnified')
axes[0].axhline(0, color='#888', lw=.8)
axes[0].legend(loc='lower right', ncol=2, fontsize=9)
axes[1].axhline(0, color='#777', lw=.8)
axes[1].set(ylabel='Heading relative to start (degrees)',
            title='Heading approaches zero at the finish, while the lateral offset remains')
axes[1].legend(loc='lower left', fontsize=9)
for key, a, b in [('reverse', 0, turn), ('return', turn, m['elapsed_s'])]:
    avg = m[key]['iphone_pose']['distance_weighted_heading_deg']
    axes[1].plot([a, b], [avg, avg], color=colors[1], lw=2.2, ls=':')
    axes[1].text((a+b)/2, avg+.3, f'{key}: distance-weighted mean {avg:+.2f}°',
                 ha='center', fontsize=9, color=colors[1])
axes[2].plot(st, steer, color='#36846b', lw=1.1)
axes[2].axhline(.35, color='#888', ls='--', lw=.8)
axes[2].axhline(-.35, color='#888', ls='--', lw=.8)
axes[2].axhline(0, color='#888', lw=.8)
axes[2].set(xlabel='Seconds since 13:46:35.279 (Pi clock)', ylabel='Steering command',
            ylim=(-.39, .39), title='Proportional heading control: return mean +0.157; peak +0.338 (cap 0.35)')
for ax in axes[1:]:
    ax.axvspan(0, turn, color=colors[0], alpha=.05)
    ax.axvspan(turn, m['elapsed_s'], color=colors[1], alpha=.05)
    ax.axvline(turn, color='#bf303d', ls=':', lw=1)
    ax.set_xlim(0, m['elapsed_s'])
for ax in axes:
    ax.grid(alpha=.18)
fig.supxlabel('Local pose estimates, not overhead truth · 1590/1590 valid motion reports · no tracking break · finish poses at stop-command checkpoint', fontsize=9)
for ext in ('png', 'pdf'):
    fig.savefig(OUT/('drift-analysis.'+ext), dpi=180)
plt.close(fig)
