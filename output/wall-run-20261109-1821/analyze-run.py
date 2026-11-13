# @(#)analyze-run.py 3.2 2026/11/09 18:38:31
import os,sys,csv,json,collections
from pathlib import Path
from datetime import datetime
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/roomberry-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
from matplotlib.patches import Patch
sys.path.insert(0,'roomberry')
from roomberry_navlink import decode_packet,packet_fields,RECEIPT
out=Path('output/wall-run-20261109-1821');rows=[]
with open('roomberry/logs/navlink/roomberry-navlink-20261109-182116-0000.bin','rb') as f:
 f.read(16)
 while r:=f.read(144):
  v=decode_packet(r[16:]);d=dict(zip(packet_fields(v),v));d['epoch']=RECEIPT.unpack(r[:16])[0]/1e9;rows.append(d)
source=next(Path('/tmp/RoomTrek-1821-events').rglob('*.jsonl'));events=[json.loads(x) for x in source.read_text().splitlines()];events=[x for x in events if '2026-11-10T02:21:17Z'<=x['ts']<='2026-11-10T02:30:43Z'];(out/'iphone-events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
sessions=[]
for session in dict.fromkeys(r['session'] for r in rows):
 a=[r for r in rows if r['session']==session]
 sessions.append(dict(session=session,packets=len(a),start=datetime.fromtimestamp(a[0]['epoch']).isoformat(),end=datetime.fromtimestamp(a[-1]['epoch']).isoformat(),tracking=dict(collections.Counter(x['tracking'] for x in a)),reasons=dict(collections.Counter(x['reason'] for x in a)),relocalization=dict(collections.Counter(x['relocalization'] for x in a)),valid=sum(bool(x['flags']&1) for x in a),features_percentiles=np.percentile([x['features'] for x in a],[0,50,100]).tolist(),frame_age_ms=np.percentile([x['frame_age_us']/1000 for x in a],[50,95,100]).tolist(),missing_sequences=sum(max(0,y['seq']-x['seq']-1) for x,y in zip(a,a[1:]))))
metrics=dict(sessions=sessions,heartbeat=dict(collections.Counter(x['detail'] for x in events if x['event']=='heartbeat')))
(out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
fig,axs=plt.subplots(2,1,figsize=(13,6),sharex=True,constrained_layout=True)
colors={0:'#b7b7b7',1:'#ef9b20',2:'#e6ce37',3:'#278e54'}
start=datetime(2026,11,9,18,21,17).timestamp();end=datetime(2026,11,9,18,30,43).timestamp()
axs[0].axhspan(0,1,color=colors[0])
for i,r in enumerate(rows):
 state=3 if r['flags']&1 else 2 if r['tracking']==2 else 1
 nxt=rows[i+1]['epoch'] if i+1<len(rows) else r['epoch']+.1
 a=md.date2num(datetime.fromtimestamp(r['epoch']));b=md.date2num(datetime.fromtimestamp(min(nxt,r['epoch']+.25)))
 axs[0].broken_barh([(a,b-a)],(0,1),facecolors=colors[state],linewidth=0)
axs[0].set(ylim=(0,1),yticks=[],title='Phone state: valid map pose requires successful relocalization')
axs[0].legend(handles=[Patch(color=colors[i],label=l) for i,l in enumerate(['No received frames','Limited / relocalizing','Normal, not map-qualified','Relocalized valid pose'])],loc='lower left',fontsize=8)
for session in dict.fromkeys(r['session'] for r in rows):
 a=[r for r in rows if r['session']==session];axs[1].plot([datetime.fromtimestamp(r['epoch']) for r in a],[r['features'] for r in a],lw=1)
axs[1].set(ylabel='Visible feature count',xlabel='Local time',title='Feature counts are not a map-quality grade')
for ax in axs:
 ax.set_xlim(datetime.fromtimestamp(start),datetime.fromtimestamp(end));ax.grid(alpha=.2)
 for t,label in [(datetime(2026,11,9,18,21,57),'Resume timeout'),(datetime(2026,11,9,18,28,14),'Second WALL')]:
  ax.axvline(t,color='black',ls=':',lw=1)
axs[1].xaxis.set_major_formatter(md.DateFormatter('%H:%M:%S'))
fig.suptitle('18:21 and 18:28 attempts — no qualified tag16/iPhone alignment')
fig.savefig(out/'tracking-timeline.png',dpi=160);fig.savefig(out/'tracking-timeline.pdf')
print(json.dumps(metrics,indent=2))
