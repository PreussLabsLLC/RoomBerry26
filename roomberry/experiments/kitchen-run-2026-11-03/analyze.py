#!/usr/bin/env python3
# @(#)analyze.py 3.1.groundtruth.1 2026/11/03 17:15:00
"""Measure reviewed video outlines against the nominal tile grid, offline.

Only experiment artifacts are written. Coordinates are explicitly elevated-rim
floor projections; no telemetry is used to place or fit the video observations.
"""
from pathlib import Path
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'roomberry'))
from roomberry_overhead import homography_from_points, apply_homography
CACHE=Path('/tmp/roomberry-kitchen-0917-frames')
CACHE.mkdir(exist_ok=True)
VIDEO=HERE/'IMG_0917.MOV'
WIDTH=960


def frame(t):
    path=CACHE/f'{t:07.3f}.png'
    if not path.exists():
        subprocess.run(['ffmpeg','-v','error','-threads','2','-ss',str(t),'-i',str(VIDEO),
                        '-frames:v','1','-vf',f'scale={WIDTH}:-2','-y',str(path)],check=True)
    return Image.open(path).convert('RGB')


def camera_shift(base,current,grid):
    """Median integer translation of static floor patches; no robot tracking."""
    window=np.outer(np.hanning(64),np.hanning(64))
    a=np.array(base.convert('L'),float);b=np.array(current.convert('L'),float)
    shifts=[]
    for x,y in grid[2:,:2].astype(int):
        p=a[y-32:y+32,x-32:x+32];q=b[y-32:y+32,x-32:x+32]
        p=(p-p.mean())*window;q=(q-q.mean())*window
        cross=np.fft.fft2(q)*np.conj(np.fft.fft2(p))
        corr=np.fft.fftshift(np.fft.ifft2(cross/np.maximum(abs(cross),1e-8)).real)
        local=corr[22:43,22:43];iy,ix=np.unravel_index(np.argmax(local),local.shape)
        if local[iy,ix]>.15:shifts.append([ix-10,iy-10])
    if len(shifts)<5:raise ValueError('Too few static reference patches')
    shift=np.median(shifts,axis=0)
    residual=np.linalg.norm(np.array(shifts)-shift,axis=1)
    return shift,len(shifts),float(np.median(residual))


def conic_center(points):
    """Center/radii of a transformed reviewed ellipse, not a floor robot pose."""
    origin=points.mean(axis=0);p=(points-origin)/200.;x,y=p.T
    A,B,C,D,E=np.linalg.lstsq(np.column_stack((x*x,x*y,y*y,x,y)),np.ones(len(p)),rcond=None)[0]
    Q=np.array([[A,B/2],[B/2,C]]);c=-np.linalg.solve(2*Q,[D,E])
    f=float(c@Q@c+D*c[0]+E*c[1]-1);values,vectors=np.linalg.eigh(Q)
    if np.any(-f/values<=0):raise ValueError('Invalid transformed ellipse')
    return origin+c*200.,np.sqrt(-f/values)*200.


def phone_axis(im,H,pixel):
    """Uncalibrated heading proxy from the phone screen's principal axis."""
    px,py=pixel;rgb=np.array(im)
    x0=max(0,int(px-90));x1=min(im.width,int(px+90))
    y0=max(0,int(py+10));y1=min(im.height,int(py+145))
    roi=rgb[y0:y1,x0:x1].astype(float)
    mask=(roi[:,:,2]-roi[:,:,0]>25)&(roi[:,:,2]>120)
    yy,xx=np.where(mask)
    if len(xx)<100:return None
    fp=apply_homography(H,np.column_stack((xx+x0,yy+y0)))
    val,vec=np.linalg.eigh(np.cov(fp.T));axis=vec[:,-1]
    if val[-1]<1.8*val[0]:return None
    if axis[1]>0:axis=-axis
    return math.degrees(math.atan2(-axis[0],-axis[1]))


def main():
    ann=json.loads((HERE/'annotations.json').read_text())
    grid=np.array(ann['grid_points_xy_column_row'],float)
    pitch=ann['nominal_tile_pitch_mm']
    H=homography_from_points(grid[:,:2],grid[:,2:]*pitch)
    residual=np.linalg.norm(apply_homography(H,grid[:,:2])-grid[:,2:]*pitch,axis=1)
    train=(grid[:,3]%2)==0
    holdout=homography_from_points(grid[train,:2],grid[train,2:]*pitch)
    validation=np.linalg.norm(apply_homography(holdout,grid[~train,:2])-grid[~train,2:]*pitch,axis=1)
    bounds=ann['body_bounds'];times=[r[0] for r in bounds]
    with ThreadPoolExecutor(max_workers=3) as pool:images=dict(zip(times,pool.map(frame,times)))
    initial=images[0]
    calibration=dict(width=WIDTH,pitch_mm=pitch,pitch_status='nominal; not tape-verified',
                     points=grid.tolist(),H=H.tolist(),fit_rms_mm=float(np.sqrt(np.mean(residual**2))),
                     max_residual_mm=float(max(residual)),heldout_rms_mm=float(np.sqrt(np.mean(validation**2))),
                     door_floor_line_projection=apply_homography(H,ann['door_floor_line_xy']).tolist(),
                     limitations=['rim above floor','nominal pitch','lens distortion not calibrated','manual bounds +/-5 px'])
    (HERE/'calibration.json').write_text(json.dumps(calibration,indent=2)+'\n')
    debug=initial.copy();draw=ImageDraw.Draw(debug);inv=np.linalg.inv(H)
    for x,y,u,v in grid:
        draw.ellipse((x-5,y-5,x+5,y+5),outline='#00ffff',width=2)
        draw.text((x+7,y+4),f'{int(u)},{int(v)}',fill='#00ffff')
    for u in range(-1,4):
        pts=apply_homography(inv,[[u*pitch,-pitch],[u*pitch,8*pitch]])
        draw.line([tuple(x) for x in pts],fill='#ff00ff',width=1)
    for v in range(-1,9):
        pts=apply_homography(inv,[[-pitch,v*pitch],[3*pitch,v*pitch]])
        draw.line([tuple(x) for x in pts],fill='#ff00ff',width=1)
    debug.save(HERE/'grid-check.png')
    found=[]
    for t,x0,y0,x1,y1 in bounds:
        im=images[t];shift,npatch,scatter=camera_shift(initial,im,grid)
        Hframe=H@np.array([[1,0,-shift[0]],[0,1,-shift[1]],[0,0,1]])
        center=np.array([(x0+x1)/2,(y0+y1)/2]);radii=np.array([(x1-x0)/2,(y1-y0)/2])
        aa=np.linspace(0,2*np.pi,120,endpoint=False)
        ring=center+np.column_stack((np.cos(aa),np.sin(aa)))*radii
        floor=apply_homography(Hframe,ring);c,r=conic_center(floor)
        found.append(dict(video_s=t,visible=True,center=c.tolist(),radius_mm=float(np.sqrt(np.prod(r))),
                          axes_mm=(2*r).tolist(),pixel=center.tolist(),bounds=[x0,y0,x1,y1],
                          heading_proxy_deg=phone_axis(im,Hframe,center),camera_shift_px=shift.tolist(),
                          camera_reference_patches=npatch,camera_patch_scatter_px=scatter,
                          method='visually reviewed body ellipse projected onto floor; NOT height-corrected'))
    (HERE/'video-measurements.json').write_text(json.dumps(found,indent=2)+'\n')
    # Contact sheets preserve the exact image-space annotation for review.
    for group in range(math.ceil(len(found)/6)):
        subset=found[group*6:(group+1)*6]
        sheet=Image.new('RGB',(3*480,2*879),'white');d=ImageDraw.Draw(sheet)
        for i,r in enumerate(subset):
            im=images[r['video_s']].copy();dr=ImageDraw.Draw(im)
            dr.ellipse(tuple(r['bounds']),outline='#00ffff',width=3)
            x,y=r['pixel'];dr.ellipse((x-4,y-4,x+4,y+4),fill='#ff00ff')
            im.thumbnail((480,854));x=(i%3)*480;y=(i//3)*879
            sheet.paste(im,(x,y+25));d.text((x+7,y+5),f"{r['video_s']} s / reviewed body outline",fill='black')
        sheet.save(HERE/f'video-review-{group+1}.jpg',quality=85)
    print('Grid fit/held-out RMS mm:',calibration['fit_rms_mm'],calibration['heldout_rms_mm'])
    for r in found:print(r['video_s'],np.round(r['center'],1),round(r['radius_mm'],1),r['heading_proxy_deg'])

if __name__=='__main__':main()
