# @(#)plot-battery.py 2.3.analysis.1 2026/10/30 14:00:00
"""Plot logged battery telemetry using phone-relative time and estimated wall time."""
import csv
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(out / 'navlink.csv')))
offset = min(int(r['receive_epoch_ns']) / 1e9 - int(r['send_us']) / 1e6 for r in rows)
times = [int(r['send_us']) / 1e6 + offset for r in rows]
levels = [int(r['battery_pct']) for r in rows]
fontpath = '/System/Library/Fonts/Supplemental/Arial.ttf'
def font(size): return ImageFont.truetype(fontpath, size)
im = Image.new('RGB', (1500, 850), 'white')
d = ImageDraw.Draw(im)
left, top, right, bottom = 125, 160, 1380, 650
duration = times[-1] - times[0]
def x(t): return left + (t - times[0]) / duration * (right - left)
def y(b): return bottom - b / 100 * (bottom - top)
d.text((70, 30), 'iPhone battery during the Roomba ride', font=font(38), fill='#182536')
d.text((70, 85), 'October 30, 2026  |  Pacific time  |  NavLink battery telemetry', font=font(24), fill='#526175')
d.rectangle((left, y(20), right, bottom), fill='#fff1e9')
for b in range(0, 101, 20):
    d.line((left, y(b), right, y(b)), fill='#dce2e9', width=2)
    d.text((left-18, y(b)), f'{b}%', anchor='rm', font=font(22), fill='#526175')
for minute in range(7):
    t = datetime.fromtimestamp(times[0]).replace(second=0, microsecond=0).timestamp() + (minute+1)*60
    if times[0] <= t <= times[-1]:
        d.line((x(t), top, x(t), bottom), fill='#e8ecf1', width=2)
        d.text((x(t), bottom+24), datetime.fromtimestamp(t).strftime('%H:%M'), anchor='mt', font=font(22), fill='#526175')
points = [(x(times[0]), y(levels[0]))]
for t, b in zip(times[1:], levels[1:]):
    points.append((x(t), points[-1][1]))
    points.append((x(t), y(b)))
d.line(points, fill='#1769aa', width=5)
for t,b in [(times[0],levels[0]),(times[-1],levels[-1])]:
    px,py=x(t),y(b)
    d.ellipse((px-7,py-7,px+7,py+7),fill='#1769aa')
    d.text((px,py-20), f'{b}%', anchor='mb',font=font(28),fill='#1769aa')
d.text((70, 740), f'77% to 20% in {duration/60:.2f} minutes  |  Unplugged throughout',font=font(27),fill='#182536')
d.text((70, 790), 'Clock offset estimated from least-delayed receipt. Low Power Mode / warning state is not recorded.',font=font(20),fill='#526175')
im.save(out/'iphone-battery.png')
with open(out/'battery-changes.csv','w') as f:
    w=csv.writer(f); w.writerow(['estimated_local_time','elapsed_s','battery_pct','battery_state'])
    last=None
    for r,t,b in zip(rows,times,levels):
        if b != last:
            w.writerow([datetime.fromtimestamp(t).isoformat(timespec='milliseconds'),round(t-times[0],3),b,'unplugged' if r['battery_state']=='1' else r['battery_state']])
            last=b
print('Battery plot:', out/'iphone-battery.png')
print('Estimated final 20% observation:',datetime.fromtimestamp(times[next(i for i,b in enumerate(levels) if b==20)]))
