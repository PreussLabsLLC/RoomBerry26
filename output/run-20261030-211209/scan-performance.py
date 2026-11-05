"""Extract scan durations and sensor-failure overlaps from this run's mission log."""
import ast
import csv
from datetime import datetime
from pathlib import Path
import statistics

OUT = Path(__file__).resolve().parent
lines = (OUT/'mission.log').read_text().splitlines()
def timestamp(line):
    return datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f').timestamp()
errors = [timestamp(line) for line in lines if 'Roomba sensor poll failed.' in line]
rows=[]
for line in lines:
    if 'Vision scan:' not in line:
        continue
    d=ast.literal_eval(line.split('timings_ms=')[1]);end=timestamp(line)
    start=end-d['total']/1000
    rows.append(dict(start=datetime.fromtimestamp(start).strftime('%H:%M:%S'),end=line[11:19],
        skipped='skipped=True' in line,total_s=d['total']/1000,detect_s=d.get('detect',0)/1000,
        save_s=d['image_save']/1000,pause_s=d['pause']/1000,
        poll_failures=sum(start<=t<=end for t in errors)))
with (OUT/'scan-timings.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
for name,selected in [('full',[r for r in rows if not r['skipped']]),
                      ('full/no poll failures',[r for r in rows if not r['skipped'] and not r['poll_failures']]),
                      ('full/with poll failures',[r for r in rows if not r['skipped'] and r['poll_failures']]),
                      ('detection skipped',[r for r in rows if r['skipped']])]:
    print(name,len(selected),'mean',round(statistics.mean(r['total_s'] for r in selected),3),
          'range',round(min(r['total_s'] for r in selected),3),round(max(r['total_s'] for r in selected),3))
