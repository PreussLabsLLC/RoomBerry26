#!/usr/bin/env python3
# @(#)analyze-motor-currents.py 2.3.9 2026/10/28 16:30:00
"""Align recorded actuator commands with current samples; save plots and event CSVs."""
import argparse
import ast
import csv
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import numpy as np
os.environ.setdefault('MPLCONFIGDIR', '/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--sensors', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.sensors.open()))
    # Match naive local timestamps directly: log and CSV share the robot's clock.
    origin = datetime.fromisoformat(rows[0]['timestamp'])
    def seconds(stamp):
        return (datetime.fromisoformat(stamp.replace(',', '.')) - origin).total_seconds()
    valid = [r for r in rows if r['oi_mode'] in ('0', '1', '2', '3')]
    rejected = [r for r in rows if r['oi_mode'] not in ('0', '1', '2', '3')]
    t = np.array([seconds(r['timestamp']) for r in valid])
    left = np.array([float(r['left_motor_current_a']) for r in valid])
    right = np.array([float(r['right_motor_current_a']) for r in valid])
    battery = -np.array([float(r['battery_current_a']) for r in valid])
    voltage = np.array([float(r['battery_voltage_v']) for r in valid])
    contact = np.array([r['bump_left']=='1' or r['bump_right']=='1' for r in valid])
    load = np.maximum(np.abs(left), np.abs(right))
    raw = []
    lines = args.log.read_text().splitlines()
    applied_steps = any('Wheel ramp applied:' in line for line in lines)
    for line in lines:
        if not re.match(r'\d{4}-\d\d-\d\d ', line):
            continue
        ts = seconds(line[:23])
        step = re.search(r'Wheel ramp applied: left=(-?\d+) right=(-?\d+) mm/s', line)
        if step:
            raw.append((ts, (int(step[1]), int(step[2])), 'ramp_step'))
            continue
        if applied_steps:
            if 'Wheel drop: OI STOP' in line:
                raw.append((ts, (0,0), 'safety_stop'))
            continue
        m = re.search(r'Actuator command (\w+) (\{.*?\}) accepted in ([\d.]+) ms', line)
        if m:
            op, kw = m[1], ast.literal_eval(m[2])
            if op == 'drive_straight': wheels = (kw['velocity'], kw['velocity'])
            elif op == 'drive_direct': wheels = (kw['left_velocity'], kw['right_velocity'])
            elif op == 'spin_left': wheels = (-kw['velocity'], kw['velocity'])
            elif op == 'spin_right': wheels = (kw['velocity'], -kw['velocity'])
            else: continue
            # Report timestamp is just after the serial operation. Preserve this
            # uncertainty rather than infer exact transmission from unrelated work.
            raw.append((ts, tuple(wheels), op))
        elif (re.search(r'Roomba operation (?:stop|emergency_stop) completed in .* ms$', line)
              or 'safety sensor triggered; braking' in line or 'Wheel drop: OI STOP' in line):
            raw.append((ts, (0,0), 'safety_stop' if 'safety sensor' in line or 'Wheel drop' in line else 'stop'))
    raw.sort()
    events = []
    previous = (0,0)
    for ts, wheels, op in raw:
        if wheels == previous: continue  # Heartbeats are not speed transitions.
        if previous == (0,0): kind = 'start'
        elif wheels == (0,0): kind = 'stop'
        elif np.allclose(np.array(previous)/np.linalg.norm(previous), np.array(wheels)/np.linalg.norm(wheels)):
            kind = 'speed_change'
        else: kind = 'direction_change'
        events.append(dict(t=ts, kind=kind, operation=op, before=previous, after=wheels))
        previous = wheels
    # Retain only events actually covered by the sensor recording.
    events = [e for e in events if t[0] <= e['t'] <= t[-1]]
    command_events = list(events)
    # A 5–150 ms zero pulse is not evidence of starting from physical rest.
    # Group it as a speed/direction transition, keeping the full command trace.
    events = []
    i = 0
    while i < len(command_events):
        e = dict(command_events[i])
        if (e['kind'] == 'stop' and i + 1 < len(command_events) and
                command_events[i+1]['kind'] == 'start' and
                command_events[i+1]['t'] - e['t'] < .15):
            nxt = command_events[i+1]
            e['after'] = nxt['after']
            e['brief_zero_s'] = nxt['t'] - e['t']
            e['operation'] = 'brief_zero_then_' + nxt['operation']
            if e['before'] == e['after']:
                e['kind'] = 'restart_pulse'
            elif np.allclose(np.array(e['before'])/np.linalg.norm(e['before']),
                             np.array(e['after'])/np.linalg.norm(e['after'])):
                e['kind'] = 'speed_change'
            else:
                e['kind'] = 'direction_change'
            i += 1
        else:
            e['brief_zero_s'] = 0.0
        events.append(e)
        i += 1
    et = np.array([e['t'] for e in command_events])
    for i,e in enumerate(events):
        at = e['t']
        next_t = events[i+1]['t'] if i+1<len(events) else t[-1]+1
        before = (t >= at-.5) & (t < at-.05)
        after = (t >= at) & (t < min(at+.6, next_t))
        e.update(timestamp=(origin + timedelta(seconds=at)).isoformat(timespec='milliseconds'),
                 first_sample_delay_s=float(t[np.searchsorted(t, at)]-at),
                 next_transition_s=float(next_t-at),
                 contact_near=bool(np.any(contact[(t>=at-.25)&(t<=at+.6)])),
                 baseline_a=float(np.median(load[before])) if before.any() else None,
                 peak_a=float(np.max(load[after])) if after.any() else None,
                 samples_after=int(after.sum()))
    with (args.output/'aligned-events.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(events[0]));w.writeheader();w.writerows(events)
    with (args.output/'rejected-samples.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rejected)
    colors=dict(start='#14825a',stop='#c54848',speed_change='#a16bc2',direction_change='#d99326',restart_pulse='#777777')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':140})
    def commands(ax,lo,hi,minutes=False):
        factor=60 if minutes else 1
        xs=[t[0]]+list(et); ls=[0]+[e['after'][0] for e in command_events];rs=[0]+[e['after'][1] for e in command_events]
        ax.step(np.array(xs)/factor,ls,where='post',label='Left command',lw=1,color='#2565a8')
        ax.step(np.array(xs)/factor,rs,where='post',label='Right command',lw=1,color='#e47731')
        ax.set_ylim(-65,65);ax.set_ylabel('Command\nmm/s');ax.set_xlim(lo/factor,hi/factor)
    end=t[-1]
    fig,axs=plt.subplots(4,1,figsize=(15,10),sharex=True,layout='constrained')
    commands(axs[0],0,end,True);axs[0].legend(loc='upper right',ncols=2)
    axs[1].plot(t/60,left,lw=.65,label='Left');axs[1].plot(t/60,right,lw=.65,label='Right');axs[1].set_ylabel('Wheel current A');axs[1].legend(ncols=2)
    axs[2].plot(t/60,battery,lw=.6,color='#65528d');axs[2].set_ylabel('Battery discharge A')
    axs[3].plot(t/60,voltage,lw=.7,color='#555');axs[3].set_ylabel('Battery V');axs[3].set_xlabel('Minutes since recording start')
    for ax in axs:
        ax.grid(alpha=.18)
        for ct in t[np.flatnonzero(contact & np.r_[True,~contact[:-1]])]:ax.axvline(ct/60,color='red',alpha=.10,lw=.6)
    fig.suptitle('Motor commands and measured currents — 2026-10-28 14:20 run\nFaint red lines: physical bumper onset; repeated identical commands omitted')
    fig.savefig(args.output/'01-run-overview.png');plt.close(fig)
    # Event responses: no interpolation through gaps, no data after a different
    # transition. Median per 125 ms bin avoids overweighting densely sampled runs.
    kinds=['start','stop','speed_change','direction_change']
    fig,axs=plt.subplots(2,2,figsize=(13,8),sharex=True,sharey=True,layout='constrained')
    bins=np.arange(-.5,.751,.125); curves={};summary={}
    for ax,kind in zip(axs.flat,kinds):
        subset=[e for e in events if e['kind']==kind]
        curves[kind]=[]
        for e in subset:
            dt=t-e['t'];i=events.index(e)
            prev=events[i-1]['t'] if i else -np.inf
            nxt=events[i+1]['t'] if i+1<len(events) else np.inf
            curve=[]
            for b in bins:
                mask=(dt>=b-.0625)&(dt<b+.0625)&(t>=prev)&(t<nxt)
                curve.append(float(np.median(load[mask])) if mask.any() else np.nan)
            curves[kind].append(curve)
        a=np.array(curves[kind])
        if len(a):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',RuntimeWarning)
                q=np.nanpercentile(a,[10,50,90],axis=0)
            ax.fill_between(bins,q[0],q[2],alpha=.2,color=colors[kind],label='10–90% between events')
            ax.plot(bins,q[1],color=colors[kind],lw=2,label='Median (all)')
            clean_curves=np.array([c for c,e in zip(curves[kind],subset) if not e['contact_near']])
            if len(clean_curves):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',RuntimeWarning)
                    clean_med=np.nanmedian(clean_curves,axis=0)
                ax.plot(bins,clean_med,color=colors[kind],lw=1.5,ls='--',label='Median (no nearby bumper)')
        ax.axvline(0,color='black',ls='--',lw=.8);ax.grid(alpha=.2)
        ax.set_title(f'{kind.replace("_"," ").title()} — {len(subset)} transitions')
        peaks=[e['peak_a'] for e in subset if e['peak_a'] is not None]
        rises=[e['peak_a']-e['baseline_a'] for e in subset if e['peak_a'] is not None and e['baseline_a'] is not None]
        clean=[e['peak_a'] for e in subset if e['peak_a'] is not None and not e['contact_near']]
        summary[kind]=dict(count=len(subset),measurable_peak_count=len(peaks),contact_near=sum(e['contact_near'] for e in subset),
            median_peak_a=float(np.median(peaks)) if peaks else None,
            p95_peak_a=float(np.percentile(peaks,95)) if peaks else None,
            median_peak_minus_baseline_a=float(np.median(rises)) if rises else None,
            no_contact_median_peak_a=float(np.median(clean)) if clean else None,
            no_contact_count=len(clean))
    for ax in axs[-1]:ax.set_xlabel('Seconds from command transition')
    for ax in axs[:,0]:ax.set_ylabel('Larger absolute wheel current (A)')
    axs[0,0].legend(fontsize=8)
    fig.suptitle('Current around command changes (zero pulses <150 ms grouped with the next motion)\nEach response stops at the next transition; no interpolation across missing samples')
    fig.savefig(args.output/'02-transition-responses.png');plt.close(fig)
    # Largest excursions at least 5 seconds apart.
    selected=[]
    for idx in np.argsort(load)[::-1]:
        if all(abs(t[idx]-t[j])>5 for j in selected):selected.append(idx)
        if len(selected)==4:break
    fig,axs=plt.subplots(4,2,figsize=(15,11),layout='constrained',gridspec_kw={'width_ratios':[1,2]})
    spike_summary=[]
    for row,idx in enumerate(selected):
        lo,hi=t[idx]-3,t[idx]+3; mask=(t>=lo)&(t<=hi)
        commands(axs[row,0],lo,hi)
        axs[row,1].plot(t[mask],left[mask],'.-',ms=3,lw=1,label='Left')
        axs[row,1].plot(t[mask],right[mask],'.-',ms=3,lw=1,label='Right')
        for e in events:
            if lo<=e['t']<=hi:
                for ax in axs[row]:ax.axvline(e['t'],color=colors[e['kind']],ls='--',alpha=.65,lw=.8)
                axs[row,1].text(e['t'],.97,e['kind'],rotation=90,va='top',fontsize=7,transform=axs[row,1].get_xaxis_transform())
        for ax in axs[row]:
            ax.axvline(t[idx],color='black',lw=.6,alpha=.5);ax.grid(alpha=.2);ax.set_xlim(lo,hi)
            for ct in t[mask&contact]:ax.axvline(ct,color='red',alpha=.08)
        nearest=min(events,key=lambda e:abs(e['t']-t[idx]))
        prev=[e for e in command_events if e['t']<=t[idx]][-1]
        spike_summary.append(dict(timestamp=valid[idx]['timestamp'],left_a=float(left[idx]),right_a=float(right[idx]),
            physical_bumper=bool(contact[idx]),last_transition=prev['kind'],
            seconds_after_transition=float(t[idx]-prev['t']),command=prev['after'],
            nearest_transition=nearest['kind'],offset_from_nearest_s=float(t[idx]-nearest['t'])))
        axs[row,1].set_title(f'{valid[idx]["timestamp"][11:]} — L={left[idx]:.3f} A, R={right[idx]:.3f} A')
        axs[row,1].set_ylabel('Wheel current A')
    axs[0,1].legend(loc='lower right');axs[-1,0].set_xlabel('Seconds since recording start');axs[-1,1].set_xlabel('Seconds since recording start')
    fig.suptitle('Four largest measured wheel-current excursions (separated by ≥5 s)\nDashed: transitions; red: bumper samples; dots: samples. Contact-triggering samples are recorded after brake I/O.')
    fig.savefig(args.output/'03-largest-spikes.png');plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,kind in zip(axs.flat,kinds):
        subset=[e for e in events if e['kind']==kind and not e['contact_near'] and e['peak_a'] is not None]
        if kind == 'start':
            subset=[e for e in subset if np.any((t>=e['t']-.2)&(t<e['t']-.02)) and
                    np.max(load[(t>=e['t']-.2)&(t<e['t']-.02)]) < .02]
        if not subset:
            ax.set_title(kind+' — no examples');continue
        target=np.median([e['peak_a'] for e in subset])
        e=min(subset,key=lambda item:abs(item['peak_a']-target))
        at=e['t'];lo,hi=at-1.5,at+1.5;mask=(t>=lo)&(t<=hi)
        ax.plot(t[mask]-at,left[mask],'.-',ms=3,label='Left current',lw=1)
        ax.plot(t[mask]-at,right[mask],'.-',ms=3,label='Right current',lw=1)
        ax.axvline(0,color='black',ls='--',lw=1)
        twin=ax.twinx()
        cx=np.array([t[0]]+[c['t'] for c in command_events])-at
        twin.step(cx,[0]+[c['after'][0] for c in command_events],where='post',alpha=.3,color='#2565a8',ls='--')
        twin.step(cx,[0]+[c['after'][1] for c in command_events],where='post',alpha=.3,color='#e47731',ls='--')
        twin.set_ylim(-65,65);twin.set_ylabel('Dashed commands mm/s',fontsize=8)
        ax.set_xlim(-1.5,1.5);ax.set_ylim(-.01,.55);ax.grid(alpha=.2)
        ax.set_title(kind.replace('_',' ').title()+' — '+e['timestamp'][11:])
        ax.set_xlabel('Seconds from transition');ax.set_ylabel('Wheel current A')
    axs[0,0].legend(fontsize=8)
    fig.suptitle('Representative transitions without nearby physical bumper contact\nExamples near the median peak; start also requires near-zero prior current. Dots are actual samples.')
    fig.savefig(args.output/'04-typical-transitions.png');plt.close(fig)
    rest_peaks=[]
    moving_samples=[]
    for i,e in enumerate(events):
        if e['kind']!='start' or e['contact_near'] or e['peak_a'] is None:
            continue
        at=e['t'];pre=(t>=at-.2)&(t<at-.02)
        if pre.any() and np.max(load[pre])<.02:
            rest_peaks.append(e['peak_a'])
        nxt=events[i+1]['t'] if i+1<len(events) else t[-1]
        moving_samples.extend(load[(t>=at+.6)&(t<min(at+1.5,nxt))&~contact])
    stats=dict(recording=str(args.sensors),log=str(args.log),valid_samples=len(valid),rejected_samples=len(rejected),
        rejection_reason='OI mode outside valid 0–3 range; entire malformed row excluded',
        sample_interval_percentiles_s=np.percentile(np.diff(t),[50,90,99,100]).tolist(),
        sample_delay_percentiles_s=np.percentile([e['first_sample_delay_s'] for e in events],[50,90,99]).tolist(),
        max_left_a=float(max(np.abs(left))),max_right_a=float(max(np.abs(right))),
        valid_wheel_overcurrent_samples=sum(r['wheel_overcurrent_left']=='1' or r['wheel_overcurrent_right']=='1' for r in valid),
        near_rest_start_count=len(rest_peaks),near_rest_median_peak_a=float(np.median(rest_peaks)),
        later_moving_sample_count=len(moving_samples),later_moving_median_a=float(np.median(moving_samples)),
        raw_command_transition_count=len(command_events),brief_zero_pulse_count=sum(e['brief_zero_s']>0 for e in events),
        restart_pulse_count=sum(e['kind']=='restart_pulse' for e in events),
        transitions=summary,spikes=spike_summary)
    (args.output/'summary.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps(stats,indent=2))

if __name__ == '__main__':
    main()
