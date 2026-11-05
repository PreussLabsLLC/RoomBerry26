#!/usr/bin/env python3
# @(#)plot_grout_bumps.py 3.1.grout.11 2026/11/04
"""Offline speed/phone-impact timing plots; no robot control or serial access."""
import argparse
import ast
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
from roomberry_navlink import HEALTH_FIELDS, decode_health_packet


def plot(log, sensors, navlink, prefix):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'roomberry-pit-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with sensors.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    # Derive the log's local-clock offset from the paired ISO/Unix CSV fields.
    def naive_epoch(stamp):
        return datetime.fromisoformat(stamp.replace(',', '.')).replace(tzinfo=timezone.utc).timestamp()
    offset = float(rows[0]['epoch_s'])-naive_epoch(rows[0]['timestamp'])
    commands, starts, threshold_times = [], [], []
    armed = False
    for line in log.read_text().splitlines():
        try:
            t = naive_epoch(line[:23])+offset
        except ValueError:
            continue
        if 'Mission mode changed to gridrunner' in line:
            armed = True
        if 'GridRunner sample: ' in line:
            r = json.loads(line.split('GridRunner sample: ')[1])
            if r['stage']=='driving' and armed:
                starts.append(t)
                armed = False
        match = re.search(r'Actuator command (\w+) (\{.*?\}) accepted', line)
        if match:
            op, args = match[1], ast.literal_eval(match[2])
            if op=='drive_direct':
                commands.append((t, (args['left_velocity']+args['right_velocity'])/2))
            elif op=='drive_straight':
                commands.append((t, args['velocity']))
            elif op in ('spin_left', 'spin_right'):
                commands.append((t, 0.))
        if re.search(r'Roomba operation (stop|soft_stop|emergency_stop) completed', line):
            commands.append((t, 0.))
        if 'GridRunner threshold bump:' in line:
            threshold_times.append(t)
    commands.sort()
    if not starts:
        raise ValueError('no grout movement starts found')
    origin = math.floor(starts[0])-1
    ending = max(threshold_times)+17
    acceleration, events = [], {}
    data = navlink.read_bytes()
    if data[:16] != struct.pack('<8sHHI', b'NVLLOG1\0', 1, 144, 128):
        raise ValueError('unsupported NavLink recording header')
    for i in range(16, len(data)-143, 144):
        rec = data[i:i+144]
        if rec[21] != 3:
            continue
        h = dict(zip(HEALTH_FIELDS, decode_health_packet(rec[16:])))
        wall = struct.unpack('<Q', rec[:8])[0]/1e9
        acceleration.append((wall, h['interval_accel_peak_mm_s2']/9806.65,
                             math.sqrt(sum(h[k]**2 for k in ('device_ax_mm_s2','device_ay_mm_s2','device_az_mm_s2')))/9806.65))
        if not h['bump_count']:
            continue
        key = (h['session'], h['calibration'], h['bump_count'])
        if key not in events:
            events[key] = dict(count=h['bump_count'], receipt_epoch=wall,
                              event_epoch=wall-(h['send_us']-h['bump_us'])/1e6,
                              first_peak_g=h['last_bump_peak_mm_s2']/9806.65,
                              peak_g=h['last_bump_peak_mm_s2']/9806.65)
        events[key]['peak_g'] = max(events[key]['peak_g'],h['last_bump_peak_mm_s2']/9806.65)
    bumps = sorted((e for e in events.values() if origin<=e['event_epoch']<=ending),key=lambda e:e['event_epoch'])
    for event in bumps:
        threshold = min(threshold_times,key=lambda t:abs(t-event['event_epoch']))
        event['ended_outbound'] = abs(threshold-event['event_epoch'])<.5
        prior = [(t,v) for t,v in commands if t<=event['event_epoch']]
        event['command_before_bump_mm_s'] = prior[-1][1] if prior else 0
    prefix.parent.mkdir(parents=True,exist_ok=True)
    with prefix.with_suffix('.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(bumps[0]))
        writer.writeheader();writer.writerows(bumps)
    odometry=[]
    for previous,row in zip(rows,rows[1:]):
        t=float(row['epoch_s']);dt=t-float(previous['epoch_s'])
        if origin<=t<=ending and 0<dt<=.5 and row['distance_delta_mm']:
            odometry.append((t,float(row['distance_delta_mm'])/dt))
    def command_window(lo,hi):
        before=[c for c in commands if c[0]<=lo]
        pts=[(lo,before[-1][1] if before else 0)]+[c for c in commands if lo<c[0]<hi]
        return pts+[(hi,pts[-1][1])]
    def draw(ax,lo,hi,zero):
        pts=command_window(lo,hi)
        ax.step([t-zero for t,v in pts],[v for t,v in pts],where='post',color='black',lw=1.3,label='Requested mean wheel speed')
        ax.axhline(0,color='grey',lw=.4);ax.set_ylabel('Speed (mm/s)');ax.grid(alpha=.2)
    def save(fig,suffix):
        for ext in ('png','svg'):
            out=prefix.parent/(prefix.name+suffix+'.'+ext)
            fig.savefig(out,dpi=160);print(out)
        plt.close(fig)
    fig,axes=plt.subplots(2,1,sharex=True,figsize=(16,8))
    draw(axes[0],origin,ending,origin)
    axes[0].plot([t-origin for t,v in odometry],[v for t,v in odometry],color='tab:blue',alpha=.65,lw=.8,label='Wheel-odometry speed')
    axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    acc=[a for a in acceleration if origin<=a[0]<=ending]
    axes[1].plot([a[0]-origin for a in acc],[a[1] for a in acc],color='tab:purple',lw=.8,label='Phone interval peak user acceleration')
    for e in bumps:
        color='tab:red' if e['ended_outbound'] else 'tab:orange'
        x=e['event_epoch']-origin
        axes[1].scatter(x,e['peak_g'],color=color,zorder=4)
        axes[1].annotate(f"#{e['count']}",(x,e['peak_g']),xytext=(3,7),textcoords='offset points',fontsize=8)
        for ax in axes:ax.axvline(x,color=color,lw=.7,alpha=.5)
    axes[1].set_ylabel('Acceleration (g)');axes[1].grid(alpha=.2)
    axes[1].legend(loc='upper right',fontsize=9)
    local_zero=datetime.fromtimestamp(origin-offset,tz=timezone.utc).strftime('%H:%M:%S')
    axes[1].set_xlabel('Seconds from '+local_zero+' (Pi local clock)')
    axes[1].set_ylim(bottom=0)
    fig.suptitle('Grout starts, speed and phone bumps — Nov 4, 22:18 run',fontsize=15)
    fig.text(.5,.012,'Red markers ended outbound; orange markers were other bump events. User acceleration excludes gravity. Event dots use the updated 150 ms peak.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.95));save(fig,'')

    fig,axes=plt.subplots(2,3,figsize=(17,9))
    timings=[]
    for number,(ax,start) in enumerate(zip(axes.flat,starts),1):
        outbound_end=next(t for t in threshold_times if t>=start)
        first=next(t for t,v in commands if t>=start and v<-100)
        lo,hi=first-.35,max(first+1.1,outbound_end+.25)
        draw(ax,lo,hi,first)
        ax.set_ylim(-210,110);ax.axvline(0,color='black',lw=.8,ls=':')
        secondary=ax.twinx()
        acc=[a for a in acceleration if lo<=a[0]<=hi]
        secondary.plot([a[0]-first for a in acc],[a[1] for a in acc],color='tab:purple',lw=1,label='Phone interval peak')
        secondary.set_ylabel('Acceleration (g)',color='tab:purple');secondary.tick_params(axis='y',colors='tab:purple')
        secondary.set_ylim(0,max(.7,max((a[1] for a in acc),default=0)*1.2))
        for e in bumps:
            if lo<=e['event_epoch']<=hi:
                secondary.scatter(e['event_epoch']-first,e['peak_g'],color='tab:red' if e['ended_outbound'] else 'tab:orange',zorder=4)
        event=min(bumps,key=lambda e:abs(e['event_epoch']-outbound_end))
        delta=event['event_epoch']-first
        timings.append(dict(attempt=number,command_epoch=first,event_epoch=event['event_epoch'],delay_ms=delta*1000,bump_count=event['count']))
        ax.set_title(f"Attempt {number}: threshold bump at +{delta*1000:.0f} ms",fontsize=11)
        ax.set_xlabel('Seconds from first accepted -150 command')
        ax.set_xlim(lo-first,hi-first)
    fig.suptitle('Start-up detail: black = speed request; purple = phone acceleration; red = threshold bump',fontsize=14)
    fig.text(.5,.015,'Packet peaks summarize intervals; raw 100 Hz IMU/jerk is not recorded. Bump time estimated from phone timestamps; network latency remains. Attempt 2 uses a longer window.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.95));save(fig,'-starts')
    prefix.with_suffix('.json').write_text(json.dumps(dict(timing=timings,event_peak_note='First and final 150ms episode peaks retained separately',events=bumps),indent=2)+'\n')
    for item in timings:print(item)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--sensors',type=Path,required=True)
    p.add_argument('--navlink',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,required=True)
    a=p.parse_args();plot(a.log,a.sensors,a.navlink,a.output_prefix)


if __name__=='__main__':main()
