#!/usr/bin/env python3
# @(#)plot_pitstop.py 3.1.pit.3 2026/11/04
"""Plot a recorded pit session without opening serial or importing robot controls."""
import argparse
import csv
import json
import os
from pathlib import Path
import tempfile


def plot_session(session, prefix):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'roomberry-pit-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    manifest = json.loads((session/'manifest.json').read_text())
    with (session/'samples.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('session contains no samples')
    origin = float(rows[0]['monotonic_s'])
    prefix.parent.mkdir(parents=True, exist_ok=True)
    synthetic = 'SIMULATED — ' if manifest.get('simulated') else ''

    def figure(samples, suffix, title, annotate=False):
        x = [float(r['monotonic_s'])-origin for r in samples]
        def values(key, scale=1):
            return [float(r[key])*scale if r.get(key) not in ('', None) else float('nan') for r in samples]
        fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True)
        for ax, wheel, color in zip(axes[:2], ('left', 'right'), ('tab:blue', 'tab:orange')):
            ax.step(x, values('command_'+wheel), where='post', color='black', ls='--', lw=1.3,
                    label='Requested command')
            ax.plot(x, values('requested_'+wheel+'_velocity'), color='tab:purple', lw=.9,
                    alpha=.7, label='Firmware-reported request')
            ax.plot(x, values(wheel+'_mm_s'), color=color, lw=.9, alpha=.9,
                    label='Measured from encoders')
            ax.set_ylabel(wheel.capitalize()+' speed (mm/s)')
            ax.legend(loc='lower left', bbox_to_anchor=(0, 1.01), ncol=3, fontsize=9)
            axes[2].plot(x, values(wheel+'_motor_current', .001), color=color, lw=.9,
                         label=wheel.capitalize()+' motor')
        axes[2].set_ylabel('Motor current (A)')
        axes[2].set_xlabel('Seconds since first recorded sample')
        axes[2].legend(loc='upper left', ncol=2)
        for ax in axes:
            ax.axhline(0, color='grey', lw=.5)
            ax.grid(alpha=.2)
            ax.margins(x=.005)
        if annotate:
            previous = None
            for r, t in zip(samples, x):
                if r['label'] != previous:
                    for ax in axes:
                        ax.axvline(t, color='grey', lw=.5, alpha=.5)
                    axes[0].text(t+.15, .97, r['label'].split('/')[-1],
                                 transform=axes[0].get_xaxis_transform(), va='top', fontsize=8,
                                 bbox=dict(facecolor='white', edgecolor='none', alpha=.7))
                    previous = r['label']
        fig.suptitle(synthetic+title+'\n'+session.name, fontsize=14)
        fig.text(.5, .015, 'Suspended wheels • nominal encoder conversion • current converted from mA to A',
                 ha='center', fontsize=9, color='dimgray')
        fig.tight_layout(rect=(0, .025, 1, .94))
        for extension in ('png', 'svg'):
            target = prefix.parent/(prefix.name+suffix+'.'+extension)
            fig.savefig(target, dpi=160)
            print(target)
        plt.close(fig)

    figure(rows, '', 'Requested and measured wheel speed / drive-motor current')
    detail = [r for r in rows if r['label'].startswith('sweep30/')]
    if detail:
        figure(detail, '-30mm-detail', '30 mm/s sweep — individual, paired and opposing wheels', True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--output-prefix', type=Path)
    args = parser.parse_args()
    plot_session(args.session, args.output_prefix or args.session/'drive-speeds-current')


if __name__ == '__main__':
    main()
