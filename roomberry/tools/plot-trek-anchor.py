"""Plot next-run wheel/iPhone disagreement using only its recorded tag16 anchor."""
# @(#)plot-trek-anchor.py 3.2 2026/11/09 13:35:55
import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from roomberry_navlink import decode_packet, packet_fields, RECEIPT
from roomberry_trek_anchor import TrekTagAnchor


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',required=True,type=Path)
    parser.add_argument('--navlink',required=True,type=Path)
    parser.add_argument('--sensors',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    anchors=[json.loads(line.split('RoomTrek tag16 alignment: ',1)[1])
             for line in args.log.read_text().splitlines() if 'RoomTrek tag16 alignment: ' in line]
    if not anchors: parser.error('No tag16 alignment record. Run the updated Pi code and collect its logs first.')
    rows=[]
    with args.navlink.open('rb') as source:
        source.read(16)
        while True:
            record=source.read(144)
            if not record: break
            if len(record)!=144: parser.error('Incomplete NavLink record; collect the complete flushed file')
            values=decode_packet(record[16:])
            if values[2]!=6: continue
            row=dict(zip(packet_fields(values),values))
            row['epoch'],row['mono']=[n/1e9 for n in RECEIPT.unpack(record[:16])]
            rows.append(row)
    matching=[a for a in anchors if any(r['session']==a['session'] and r['map_uuid'].hex()==a['map_uuid_hex'] for r in rows)]
    if not matching: parser.error('Log anchor and NavLink file have no matching phone session/map')
    anchor=matching[-1]
    rows=[r for r in rows if r['session']==anchor['session'] and r['map_uuid'].hex()==anchor['map_uuid_hex']]
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    clock=min(r['mono']-r['send_us']/1e6 for r in rows)
    offsets=[r['epoch']-r['mono'] for r in rows]
    if max(offsets)-min(offsets)>.1: parser.error('Pi epoch clock changed by more than100ms; segment the recording before comparing')
    epoch_offset=float(np.median(offsets))
    rows=[r for r in rows if r['frame_us']>=anchor['phone_frame_us'] and TrekTagAnchor.usable(r,anchor.get('heading_basis','camera_y'))]
    if not rows: parser.error('No normal frames after the recorded anchor')
    with args.sensors.open() as source: sensors=list(csv.DictReader(source))
    sensors=[r for r in sensors if int(r['odometry_epoch'])==anchor['odometry_epoch']]
    if len(sensors)<2: parser.error('Insufficient wheel samples in the anchor odometry epoch')
    t=np.array([float(r['epoch_s']) for r in sensors]);d=np.array([float(r['distance_mm']) for r in sensors])
    if np.any(np.diff(t)<=0): parser.error('Wheel timestamps must increase strictly')
    base=anchor['wheel_odometry_at_anchor']
    if base is None or base['sensor_monotonic'] is None: parser.error('Anchor lacks timestamped wheel baseline')
    heading=np.radians([float(r['angle_deg'])-base['angle_deg'] for r in sensors])+anchor['tag_robot_pose']['heading_rad']
    position=np.zeros((len(t),2))
    for i in range(1,len(t)):
        mid=(heading[i]+heading[i-1])/2
        position[i]=position[i-1]+(d[i]-d[i-1])*np.array([np.cos(mid),np.sin(mid)])
    at=base['sensor_monotonic']+epoch_offset
    origin=np.array([np.interp(at,t,position[:,i]) for i in (0,1)])
    position=position-origin+np.array([anchor['tag_robot_pose']['x_mm'],anchor['tag_robot_pose']['y_mm']])
    rows=[r for r in rows if t[0]<=r['frame_us']/1e6+clock+epoch_offset<=t[-1]]
    if not rows: parser.error('No overlapping phone and wheel time interval')
    pt=np.array([r['frame_us']/1e6+clock+epoch_offset for r in rows])
    transform=TrekTagAnchor(None,None);transform.anchor=anchor
    phone=[transform.transform(r) for r in rows]
    p=np.array([[r['x_mm'],r['y_mm']] for r in phone])
    wheel=np.column_stack([np.interp(pt,t,position[:,i]) for i in (0,1)])
    wh=np.interp(pt,t,heading)
    dh=np.degrees(np.arctan2(np.sin(np.array([r['heading_rad'] for r in phone])-wh),np.cos(np.array([r['heading_rad'] for r in phone])-wh)))
    delta=p-wheel; separation=np.linalg.norm(delta,axis=1);elapsed=pt-anchor['tag_captured_epoch']
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'disagreement.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['seconds_from_tag16','wheel_x_mm','wheel_y_mm','phone_x_mm','phone_y_mm','dx_mm','dy_mm','heading_delta_deg'])
        writer.writerows(zip(elapsed,*wheel.T,*p.T,*delta.T,dh))
    metrics=dict(anchor=anchor,frames=len(rows),final_separation_mm=float(separation[-1]),
                 max_separation_mm=float(separation.max()),final_heading_delta_deg=float(dh[-1]),
                 alignment='Recorded tag16 capture and mount, fixed scale=1; no path fitting')
    (args.out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    fig,axs=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    axs[0].plot(*(wheel/1000).T,label='Wheel');axs[0].plot(*(p/1000).T,label='iPhone robot centre')
    axs[0].scatter([anchor['tag_robot_pose']['x_mm']/1000],[anchor['tag_robot_pose']['y_mm']/1000],marker='*',label='Tag16 robot anchor')
    axs[0].set(xlabel='Room X (m)',ylabel='Room Y (m)',title='Fixed tag16 room frame');axs[0].axis('equal');axs[0].legend(fontsize=8)
    axs[1].plot(elapsed,delta[:,0],label='ΔX');axs[1].plot(elapsed,delta[:,1],label='ΔY');axs[1].plot(elapsed,separation,label='Separation',c='black')
    axs[1].set(xlabel='Seconds from tag16 capture',ylabel='iPhone minus wheel (mm)',title='Position disagreement');axs[1].legend()
    axs[2].plot(elapsed,dh);axs[2].set(xlabel='Seconds from tag16 capture',ylabel='iPhone minus wheel (degrees)',title='Heading disagreement')
    for ax in axs: ax.grid(alpha=.3)
    fig.suptitle('Tag16-anchored comparison — configured mount, no trajectory/scale fitting')
    fig.savefig(args.out/'disagreement.png',dpi=160);fig.savefig(args.out/'disagreement.pdf');plt.close(fig)
    print(json.dumps({k:v for k,v in metrics.items() if k!='anchor'},indent=2))


if __name__=='__main__': main()
