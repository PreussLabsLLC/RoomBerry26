# @(#)reconstruct-map.py 2.3.analysis.1 2026/10/30 14:00:00
"""Rebuild the active saved map and compare its trail with the phone path."""
import contextlib
from io import BytesIO, StringIO
import json
from pathlib import Path
import runpy
import sys
from PIL import Image, ImageDraw, ImageFont

out=Path(__file__).resolve().parent
root=out.parents[1]
sys.path.insert(0,str(root/'roomberry'))
from roomberry_map_image import render_map

state=json.loads((root/'roomberry/logs/map-state-reset-20261028-02.json').read_text())
config=json.loads((root/'roomberry/autonomy.json').read_text())
tags=[(v['world_from_tag'][0][3]*1000,v['world_from_tag'][1][3]*1000,v['id']) for v in config['landmarks']]
image_bytes=render_map(state,tags)
(out/'map-reconstructed.png').write_bytes(image_bytes)
im=Image.open(BytesIO(image_bytes)).convert('RGB')
with contextlib.redirect_stdout(StringIO()):
    analysis=runpy.run_path(str(out/'analyze.py'))
scale=max(2,min(12,720//max(state['cols'],state['rows'])))
bottom=42+state['rows']*scale
def point(x,y):
    return (56+(x-state['origin_x'])/state['cell_size_mm']*scale,
            bottom-(y-state['origin_y'])/state['cell_size_mm']*scale)
draw=ImageDraw.Draw(im)
draw.line([point(*p) for p in analysis['aligned']],fill='#b5179e',width=3)
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',18)
canvas=Image.new('RGB',(im.width,im.height+135),'white')
canvas.paste(im,(0,65));draw=ImageDraw.Draw(canvas)
draw.text((15,8),'Active map saved Oct 30, 13:22:36',fill='#182536',font=font)
draw.text((15,34),'Blue: saved robot trail   Magenta: aligned phone camera path',fill='#182536',font=font)
draw.text((15,im.height+78),'Phone ends ~13:20:08; robot trail continues. No mount lever-arm correction.',fill='#526175',font=font)
draw.text((15,im.height+104),'Reconstructed from JSON; this is not the missing original map.png.',fill='#526175',font=font)
canvas.save(out/'map-phone-overlay.png')
print('Saved reconstructed map and phone overlay.')
