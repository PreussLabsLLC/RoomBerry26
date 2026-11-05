#!/usr/bin/env python3
# @(#)report.py 3.1.groundtruth.1 2026/11/03 17:15:00
"""Align archived run telemetry and sparse video observations, offline only."""
from pathlib import Path
import csv
import io
import hashlib
import subprocess
import json
import math
import os
import sys
from datetime import datetime
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_navlink import export_csv


def interpolate(rows,time,key,max_gap=.5):
    times=np.array([r['time'] for r in rows])
    i=np.searchsorted(times,time)
    if i<len(rows) and abs(times[i]-time)<1e-5:return rows[i].get(key)
    if i==0 or i==len(rows) or times[i]-times[i-1]>max_gap:return None
    a,b=rows[i-1],rows[i]
    if key not in a or key not in b:return None
    return a[key]+(b[key]-a[key])*(time-times[i-1])/(times[i]-times[i-1])


def dump(name,obj):
    (HERE/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def main():
    archive=HERE/'application-extract.json'
    if archive.exists():app=json.loads(archive.read_text())
    else:
        cp=[];samples=[];events=[]
        for line in (ROOT/'roomberry/logs/roomberry.log').read_text().splitlines():
            for marker,dest in [('Calibration checkpoint: ',cp),('Calibration sample: ',samples)]:
                if marker in line:dest.append(json.loads(line.split(marker)[1]))
            if any(x in line for x in ['Calibration phone bump:','Calibration complete:',
                                       'Calibration aborted:','Stop command completed',
                                       'Calibration idle:', 'safety sensor triggered']):events.append(line)
        assert len(cp)==3 and cp[0]['iphone_pose']['session']==13338831590178131288
        app=dict(checkpoints=cp,samples=samples,events=events)
        dump('application-extract.json',app)
    cp=app['checkpoints'];a,turn,b=[r['wall_time'] for r in cp]
    return_command=next(r['wall_time'] for r in app['samples'] if r['stage']=='return')
    sensor_path=ROOT/'roomberry/logs/sensors/roomberry-sensors-20261103-134454.csv'
    nav_path=ROOT/'roomberry/logs/navlink/roomberry-navlink-20261103-134454-0000.bin'
    raw=list(csv.DictReader(sensor_path.open()))
    origin=min(raw,key=lambda r:abs(float(r['epoch_s'])-a))
    od=float(origin['distance_mm']);oa=float(origin['angle_deg'])
    x=y=path=0.;prev=raw[0];sensor=[]
    for r in raw:
        t=float(r['epoch_s']);heading=math.radians(float(r['angle_deg'])-oa)
        if t>=a:
            dd=float(r['distance_mm'])-float(prev['distance_mm'])
            mid=math.radians((float(r['angle_deg'])+float(prev['angle_deg']))/2-oa)
            x+=dd*math.cos(mid);y+=dd*math.sin(mid);path+=abs(dd)
        if t<a:x=y=path=0.
        sensor.append(dict(time=t,L=-x,Y=y,heading=math.degrees(heading),path=path,
                           signed_distance=float(r['distance_mm'])-od,
                           left=float(r['applied_left_velocity_mm_s']),right=float(r['applied_right_velocity_mm_s']),
                           bump_left=int(r['bump_left']),bump_right=int(r['bump_right']),
                           cliff_left=float(r['cliff_left_signal']),cliff_front_left=float(r['cliff_front_left_signal']),
                           cliff_front_right=float(r['cliff_front_right_signal']),cliff_right=float(r['cliff_right_signal'])))
        prev=r
    out=io.StringIO();export_csv(nav_path,out);packets=list(csv.DictReader(io.StringIO(out.getvalue())))
    g=[r for r in packets if r['type']=='2' and int(r['session'])==cp[0]['iphone_pose']['session']]
    anchor=next(r for r in g if int(r['seq'])==cp[0]['iphone_pose']['seq'])
    ax,ay,ah=[float(anchor[k]) for k in ('segment_x_mm','segment_y_mm','segment_yaw_rad')]
    phone=[]
    for r in g:
        if int(r['flags'])!=7 or r['continuity']!=anchor['continuity'] or r['calibration']!=anchor['calibration']:continue
        receipt=int(r['receive_epoch_ns'])/1e9
        capture=receipt-(int(r['send_us'])-int(r['end_us']))/1e6
        dx=float(r['segment_x_mm'])-ax;dy=float(r['segment_y_mm'])-ay
        xx=math.cos(ah)*dx+math.sin(ah)*dy;yy=-math.sin(ah)*dx+math.cos(ah)*dy
        phone.append(dict(time=capture,receive_time=receipt,L=-xx,Y=yy,
                          heading=math.degrees(float(r['segment_yaw_rad'])-ah),
                          path=float(r['path_mm'])-float(anchor['path_mm']),
                          frame_us=int(r['end_us']),seq=int(r['seq'])))
    phone.sort(key=lambda r:r['time'])
    video=json.loads((HERE/'video-measurements.json').read_text())
    v0=np.array(video[0]['center'])
    for r in video:
        r['L']=r['center'][1]-v0[1];r['Y']=-(r['center'][0]-v0[0])
    # Estimate only temporal origin and a diagnostic longitudinal scale.
    # Video positions are NEVER rescaled to match odometry. Both travel legs
    # constrain time; metadata clocks differ by one second in this movie.
    metadata_epoch=datetime.fromisoformat('2026-11-03T13:46:20-08:00').timestamp()
    usable=[r for r in video if 20<=r['video_s']<=170]
    fit=[]
    for offset in np.arange(-2.,2.001,.01):
        origin_time=metadata_epoch+offset
        w=np.array([interpolate(sensor,origin_time+r['video_s'],'L') for r in usable])
        vv=np.array([r['L'] for r in usable])
        scale=float(w@vv/(w@w))
        residual=vv-scale*w
        fit.append((float(np.sqrt(np.mean(residual**2))),float(offset),scale))
    rms,offset,sync_scale=min(fit)
    video_origin=metadata_epoch+offset
    # Curves around the optimum convey timing sensitivity, not formal CI.
    near=[r[1] for r in fit if r[0]<=rms+10]
    fits=[]
    for label,selected in [('outbound',[r for r in video if 20<=r['video_s']<=54]),
                           ('return',[r for r in video if 136<=r['video_s']<=170])]:
        result=dict(interval=label,video_start_s=selected[0]['video_s'],video_end_s=selected[-1]['video_s'])
        vp=np.array([[r['L'],r['Y']] for r in selected])
        result['projected_video_polyline_mm']=float(np.sum(np.linalg.norm(np.diff(vp,axis=0),axis=1)))
        result['video_longitudinal_delta_mm']=float(vp[-1,0]-vp[0,0])
        for source,rows in [('wheel',sensor),('phone',phone)]:
            t0=video_origin+selected[0]['video_s'];t1=video_origin+selected[-1]['video_s']
            delta=interpolate(rows,t1,'L')-interpolate(rows,t0,'L')
            result[source+'_longitudinal_delta_mm']=delta
            result[source+'_over_projected_video']=delta/result['video_longitudinal_delta_mm']
        fits.append(result)
    # Combined CSV: sampled telemetry plus exact sparse observation/event rows.
    end_video=178.808333
    times=set(np.round(np.arange(0,end_video,.1),6))
    times.update(r['video_s'] for r in video)
    event_map={round(return_command-video_origin,6):'first_forward_command'}
    times.add(round(return_command-video_origin,6))
    for r in cp:
        ts=round(r['wall_time']-video_origin,6);times.add(ts);event_map[ts]=r['checkpoint']
    physical=next(r for r in sensor if r['time']>b and r['bump_left'] and r['bump_right'])
    event_map[round(physical['time']-video_origin,6)]='physical_bump_first_observed_after_finish'
    times.add(round(physical['time']-video_origin,6))
    vm={r['video_s']:r for r in video}
    columns=['video_s','pi_epoch_s','elapsed_from_run_start_s','phase','event',
             'wheel_longitudinal_mm','wheel_lateral_mm','wheel_heading_deg','wheel_cumulative_path_mm',
             'wheel_signed_distance_mm','command_left_mm_s','command_right_mm_s','physical_bump_left','physical_bump_right',
             'cliff_left_signal','cliff_front_left_signal','cliff_front_right_signal','cliff_right_signal',
             'groundhog_longitudinal_mm','groundhog_lateral_mm','groundhog_heading_deg','groundhog_cumulative_path_mm',
             'groundhog_receive_epoch_s','groundhog_frame_end_us',
             'video_measurement_available','video_rim_projection_longitudinal_mm','video_rim_projection_lateral_mm',
             'video_screen_axis_proxy_deg','video_body_pixel_x','video_body_pixel_y','camera_shift_x_px','camera_shift_y_px']
    with (HERE/'measurements.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,lineterminator='\n');writer.writeheader()
        for ts in sorted(times):
            if not 0<=ts<=end_video:continue
            epoch=video_origin+ts
            phase='before_start' if epoch<a else 'reverse' if epoch<turn else 'turnaround_hold' if epoch<return_command else 'return' if epoch<=b else 'after_finish'
            row=dict(video_s=round(ts,6),pi_epoch_s=round(epoch,6),elapsed_from_run_start_s=round(epoch-a,6),phase=phase,event=event_map.get(ts,''),video_measurement_available=int(ts in vm))
            for target,key in [('wheel_longitudinal_mm','L'),('wheel_lateral_mm','Y'),('wheel_heading_deg','heading'),('wheel_cumulative_path_mm','path'),('wheel_signed_distance_mm','signed_distance'),('command_left_mm_s','left'),('command_right_mm_s','right'),('cliff_left_signal','cliff_left'),('cliff_front_left_signal','cliff_front_left'),('cliff_front_right_signal','cliff_front_right'),('cliff_right_signal','cliff_right')]:
                value=interpolate(sensor,epoch,key);row[target]='' if value is None else round(value,6)
            # Flags/commands are previous observations, not fractional flags.
            prior=[r for r in sensor if r['time']<=epoch]
            if prior:
                r=prior[-1];row.update(physical_bump_left=r['bump_left'],physical_bump_right=r['bump_right'],command_left_mm_s=r['left'],command_right_mm_s=r['right'])
            for target,key in [('groundhog_longitudinal_mm','L'),('groundhog_lateral_mm','Y'),('groundhog_heading_deg','heading'),('groundhog_cumulative_path_mm','path'),('groundhog_receive_epoch_s','receive_time')]:
                value=interpolate(phone,epoch,key);row[target]='' if value is None else round(value,6)
            # Capture timestamp is retained as the nearest actual frame ID.
            nearest=min(phone,key=lambda r:abs(r['time']-epoch))
            if abs(nearest['time']-epoch)<.15:row['groundhog_frame_end_us']=nearest['frame_us']
            if ts in vm:
                r=vm[ts];row.update(video_rim_projection_longitudinal_mm=r['L'],video_rim_projection_lateral_mm=r['Y'],video_screen_axis_proxy_deg=r['heading_proxy_deg'],video_body_pixel_x=r['pixel'][0],video_body_pixel_y=r['pixel'][1],camera_shift_x_px=r['camera_shift_px'][0],camera_shift_y_px=r['camera_shift_px'][1])
            writer.writerow(row)
    summary=dict(sync=dict(video_origin_pi_epoch_s=video_origin,offset_from_stream_creation_s=offset,
                           longitudinal_fit_rms_mm=rms,diagnostic_projected_video_over_wheel_scale=sync_scale,
                           offsets_within_10mm_rms=near,method='joint time/diagnostic-scale fit; video coordinates unchanged; not a formal confidence interval'),
                 checkpoints=cp,visible_comparisons=fits,video_endpoint=dict(projected_longitudinal_mm=video[-1]['L'],projected_lateral_mm=video[-1]['Y']),legs=[])
    for name,c0,c1 in [('outbound',cp[0],cp[1]),('return',cp[1],cp[2])]:
        result=dict(name=name,duration_s=c1['wall_time']-c0['wall_time'])
        for source,posekey,rows in [('wheel','wheels_pose',sensor),('phone','iphone_pose',phone)]:
            p0,p1=c0[posekey],c1[posekey]
            h=[r['heading'] for r in rows if c0['wall_time']<=r['time']<=c1['wall_time']]
            result[source]=dict(longitudinal_delta_mm=-(p1['x_mm']-p0['x_mm']),lateral_delta_mm=p1['y_mm']-p0['y_mm'],
                                endpoint_displacement_mm=math.hypot(p1['x_mm']-p0['x_mm'],p1['y_mm']-p0['y_mm']),
                                path_mm=interpolate(rows,c1['wall_time'],'path',max_gap=1.25)-interpolate(rows,c0['wall_time'],'path',max_gap=1.25),
                                net_heading_deg=math.degrees(p1['heading_rad']-p0['heading_rad']),
                                cumulative_absolute_heading_deg=float(sum(abs(np.diff(h)))))
        summary['legs'].append(result)
    summary['physical_bump_first_observed_after_finish']=physical['time']
    summary['video_measurements']=len(video)
    summary['video_measured_ranges']=[[0,0],[20,54],[136,178]]
    summary['return_command_pi_epoch_s']=return_command
    summary['visible_polylines_mm']={}
    for label,lo,hi in [('outbound',20,54),('return',136,178)]:
        p=np.array([[r['L'],r['Y']] for r in video if lo<=r['video_s']<=hi])
        summary['visible_polylines_mm'][label]=float(np.sum(np.linalg.norm(np.diff(p,axis=0),axis=1)))
    active=[r for r in g if a<=int(r['receive_epoch_ns'])/1e9<=b]
    summary['tracking']=dict(motion_reports=len(active),valid_reports=sum(r['flags']=='7' for r in active),
        rejected_frame_increment=int(active[-1]['rejected_frames'])-int(active[0]['rejected_frames']),
        missing_sequences=sum(int(y['seq'])-int(x['seq'])-1 for x,y in zip(active,active[1:])),
        processing_median_ms=float(np.median([float(r['processing_us']) for r in active]))/1000)
    # Separate event timestamps from the combined sampled/interpolated CSV.
    with (HERE/'events.csv').open('w',newline='') as f:
        wr=csv.writer(f,lineterminator='\n');wr.writerow(['event','pi_epoch_s','video_s','notes'])
        for r in cp:
            wr.writerow([r['checkpoint'],r['wall_time'],r['wall_time']-video_origin,
                         'phone impact, physical bumpers clear' if r['checkpoint']=='turnaround' else 'application checkpoint'])
        wr.writerow(['first_forward_command',return_command,return_command-video_origin,'command time, not physical motion onset'])
        wr.writerow(['first_observed_both_physical_bumpers',physical['time'],physical['time']-video_origin,'contact time bracketed by sensor polls; first observation after completion'])
    metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height,avg_frame_rate,duration,nb_frames:stream_tags=creation_time:stream_side_data=rotation',
        '-of','json',str(HERE/'IMG_0917.MOV')]))
    dump('video-metadata.json',metadata)
    provenance={}
    for name,path in [('video',HERE/'IMG_0917.MOV'),('sensors',sensor_path),('navlink',nav_path)]:
        hasher=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):hasher.update(block)
        provenance[name]=dict(filename=path.name,size_bytes=path.stat().st_size,sha256=hasher.hexdigest())
    dump('provenance.json',provenance)
    dump('summary.json',summary)
    print(json.dumps(summary,indent=2))
    # Comparison figures use unscaled floor-projected video coordinates.
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    fig.suptitle('Kitchen ground-truth investigation · 3 November 2026',fontsize=17,weight='bold')
    curves=[('Wheels',sensor,'#2466a5'),('GroundHog',phone,'#d87823')]
    for name,rows,color in curves:
        use=[r for r in rows if a<=r['time']<=b]
        tt=np.array([r['time']-video_origin for r in use]);ll=np.array([r['L'] for r in use])/1000;yy=np.array([r['Y'] for r in use])
        for condition,ls in [(np.array([r['time']<=turn for r in use]),'-'),(np.array([r['time']>=turn for r in use]),'--')]:
            axes[0,0].plot(ll[condition],yy[condition],color=color,ls=ls,lw=1.6,label=name if ls=='-' else None)
        axes[0,1].plot(tt,ll,color=color,label=name)
        axes[1,0].plot(tt,yy,color=color,label=name)
        axes[1,1].plot(tt,[r['heading'] for r in use],color=color,lw=.9,label=name)
    vt=np.array([r['video_s'] for r in video]);vl=np.array([r['L'] for r in video]);vy=np.array([r['Y'] for r in video])
    axes[0,0].scatter(vl/1000,vy,color='#36846b',marker='D',s=35,label='Video rim projection (uncorrected height)',zorder=5)
    axes[0,1].scatter(vt,vl/1000,color='#36846b',marker='D',s=30,zorder=5,label='Video rim projection')
    axes[1,0].scatter(vt,vy,color='#36846b',marker='D',s=30,zorder=5,label='Video rim projection')
    axes[0,0].set(xlabel='Longitudinal displacement from start (m, toward carpet)',ylabel='Lateral displacement (mm, +left)',title='Estimated paths and independent sparse video projections\nLateral magnified; initial grid/body alignment is uncalibrated')
    axes[0,1].set(xlabel='Video time (s)',ylabel='Longitudinal displacement (m)',title='No video positions filled through the unobserved interval')
    axes[1,0].set(xlabel='Video time (s)',ylabel='Lateral displacement (mm, +left)',title='End-to-end lateral drift confirmed in the image')
    axes[1,1].set(xlabel='Video time (s)',ylabel='Heading relative to initial robot direction (degrees)',title='Telemetry heading; no reliable calibrated video heading')
    for ax in axes.flat:ax.grid(alpha=.2);ax.legend(fontsize=8)
    for ax in [axes[0,1],axes[1,0],axes[1,1]]:
        ax.axvspan(54,136,color='gray',alpha=.12)
        ax.axvline(turn-video_origin,color='#bf303d',ls=':',lw=1)
        ax.axvline(b-video_origin,color='#777',ls=':',lw=1)
    axes[0,1].annotate('Phone-impact turnaround\nnot visible in camera',((turn-video_origin),4.58),xytext=(95,3.2),arrowprops=dict(arrowstyle='-',color='#bf303d'),color='#bf303d',fontsize=9)
    fig.supxlabel('Green points are elevated-body floor projections, not height-corrected center truth. Gray: no video measurements. No scale factor applied to video.',fontsize=9)
    fig.savefig(HERE/'trajectory.png',dpi=180);fig.savefig(HERE/'trajectory.pdf');plt.close(fig)

if __name__=='__main__':main()
