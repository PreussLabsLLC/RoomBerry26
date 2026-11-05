# @(#)build_mount_diagram.py 3.1.diagram.2 2026/11/04
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from html import escape
import math
OUT = Path(__file__).resolve().parent
W,H=2200,1580
im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<title>RoomBerry: GroundHog and GridRunner mount measurements</title>', '<desc>Scaled robot and nominal iPhone X outline. Camera on rear-left faces down; current screenshot has a negative left setting. Carton and body side profile are approximate.</desc>', '<!-- 3.1.diagram.2 2026/11/04 -->',f'<rect width="{W}" height="{H}" fill="#f3f6fa"/>']
ink='#172b46'; blue='#176cbd'; red='#b73535'; green='#16735d'; muted='#53657a'; gray='#9baabd'
def font(size,bold=False):return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial'+(' Bold' if bold else '')+'.ttf',size)
def text(x,y,s,size=24,color=ink,bold=False,anchor='start'):
 f=font(size,bold);width=d.textlength(s,font=f);xx=x-(width/2 if anchor=='middle' else width if anchor=='end' else 0)
 d.text((xx,y),s,font=f,fill=color)
 svg.append(f'<text x="{x}" y="{y+size*.86}" font-family="Arial, sans-serif" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{escape(s)}</text>')
def line(points,color=ink,width=3,dash=False):
 if dash:
  for (a,b),(c,e) in zip(points,points[1:]):
   dist=math.hypot(c-a,e-b)
   if not dist:continue
   for t in range(0,int(dist),15):
    p=t/dist;q=min(t+8,dist)/dist;d.line([(a+(c-a)*p,b+(e-b)*p),(a+(c-a)*q,b+(e-b)*q)],fill=color,width=width)
 else:d.line(points,fill=color,width=width)
 svg.append('<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="8 7"' if dash else '')+'/>')
def rect(box,fill,outline=None,radius=0,width=2):
 d.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=width);x,y,xx,yy=box
 svg.append(f'<rect x="{x}" y="{y}" width="{xx-x}" height="{yy-y}" rx="{radius}" fill="{fill}" stroke="{outline or fill}" stroke-width="{width}"/>')
def ellipse(box,fill,outline=None,width=2):
 d.ellipse(box,fill=fill,outline=outline,width=width);x,y,xx,yy=box
 svg.append(f'<ellipse cx="{(x+xx)/2}" cy="{(y+yy)/2}" rx="{(xx-x)/2}" ry="{(yy-y)/2}" fill="{fill}" stroke="{outline or fill}" stroke-width="{width}"/>')
def polygon(p,fill):
 d.polygon(p,fill=fill);svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in p)+f'" fill="{fill}"/>')
def arrow(a,b,color=ink,width=3,both=False):
 line([a,b],color,width)
 def head(p,q):
  ang=math.atan2(q[1]-p[1],q[0]-p[0]);length=12;half=5
  polygon([q,(q[0]-length*math.cos(ang)+half*math.sin(ang),q[1]-length*math.sin(ang)-half*math.cos(ang)),(q[0]-length*math.cos(ang)-half*math.sin(ang),q[1]-length*math.sin(ang)+half*math.cos(ang))],color)
 head(a,b)
 if both:head(b,a)
def dot(x,y,color=red,r=8):ellipse((x-r,y-r,x+r,y+r),'white',color,3)
text(42,30,'RoomBerry: phone mount & settings check',44,bold=True)
text(44,92,'Camera is rear-left, looking down. Measure from the wheel-axle midpoint to the active lens center.',26,muted)
rect((35,155,1150,1225),'white','#d6dfea',18)
rect((1180,155,2165,625),'white','#d6dfea',18)
rect((1180,650,2165,1030),'white','#d6dfea',18)
rect((1180,1055,2165,1225),'white','#d6dfea',18)
text(65,180,'TOP VIEW · 2 drawing units = 1 mm',28,bold=True)
text(65,222,'Body Ø348 mm · wheel centers 235 mm apart',22,muted)
# Robot coordinates (forward X, left Y) map to screen (-Y, -X).
S=2.;cx,cy=530.,650.
def xy(forward,left):return cx-S*left,cy-S*forward
radius=174*S
ellipse((cx-radius,cy-radius,cx+radius,cy+radius),'#e7edf4','#698099',4)
ellipse((cx-255,cy-255,cx+255,cy+255),'#eef2f6','#c2ccd6',2)
line([(cx,285),(cx,1120)],gray,2,True)
# Nominal wheel centers; wheel shapes are diagram symbols.
for left in (117.5,-117.5):
 wx,wy=xy(0,left);rect((wx-18,wy-60,wx+18,wy+60),'#52657b',radius=6)
line([(cx-radius-20,cy),(cx+radius+20,cy)],'#c49235',3,True)
text(75,683,'Wheel axle',22,'#946b21',True)
dot(cx,cy,ink,7);text(cx+17,cy+12,'C',25,bold=True)
text(620,738,'C = wheel-axle midpoint',20,muted)
arrow((cx,350),(cx,278),blue,4)
text(cx,253,'ROBOT FRONT (+X)',22,blue,True,'middle')
arrow((cx-40,cy),(cx-130,cy),blue,3)
text(242,610,'LEFT (+Y)',21,blue,True)
# AYI carton: reference-photo layout only, no asserted measurements.
bx0,by0=xy(145,60);bx1,by1=xy(45,-60)
rect((bx0,by0,bx1,by1),'#e2c79c','#aa8250',8)
line([(bx0,by0),(bx1,by0),(bx1,by1),(bx0,by1),(bx0,by0)],'#aa8250',2,True)
ellipse((cx-36,by0+75,cx+36,by0+147),'#f6f4ef','#b4b4b4',3)
text(cx,by0+155,'AYI',23,'#795b34',True,'middle')
# Front-face camera points horizontally forward, unlike the phone camera.
rect((cx-23,by0-9,cx+23,by0+17),'#394650',radius=5)
arrow((cx,by0-15),(cx,by0-65),blue,3)
line([(cx+24,by0+10),(730,365),(780,365)],gray,2)
text(790,345,'AYI carton / front camera',22,bold=True)
text(790,379,'Rough placement from photo',18,muted)
text(790,406,'Carton dimensions unmeasured',18,muted)
# iPhone X nominal dimensions. Lens-to-body edge spacings are illustrative.
# Physical lateral magnitude is unknown: show L=13 mm only for sign comparison.
L=13.;lens=xy(-200,L)
phone_left=lens[0]-20;phone_top=cy+S*64.4
phone_right=phone_left+S*70.9;phone_bottom=phone_top+S*143.6
rect((phone_left,phone_top,phone_right,phone_bottom),'#d9ebfa',blue,24)
rect((phone_left+10,phone_top+13,phone_right-10,phone_bottom-13),'#f0f7fc',radius=18)
rect((phone_left+46,phone_bottom-13,phone_right-46,phone_bottom-5),'#34495d',radius=4)
text((phone_left+phone_right)/2,phone_top+42,'iPhone X',20,blue,True,'middle')
arrow(((phone_left+phone_right)/2,phone_top+95),((phone_left+phone_right)/2,phone_top+175),blue,3)
text(710,875,'Screen up',23,blue,True)
text(710,909,'Top / notch end faces rear',20,muted)
line([(700,933),(phone_right-15,phone_bottom-16)],blue,2)
dot(*lens,red,9)
line([lens,(360,1065),(235,1065)],red,2)
text(80,1034,'ACTIVE LENS',24,red,True)
text(80,1070,'Rear-left, underside',21,muted)
text(80,1100,'Projection shown through phone',18,muted)
# Forward distance is scaled exactly at 200 mm.
line([(cx,cy),(944,cy)],gray,2,True)
line([lens,(944,lens[1])],gray,2,True)
arrow((930,cy),(930,lens[1]),red,3,True)
text(955,795,'3. Forward',23,red,True)
text(955,829,'−200 mm',27,red,True)
text(955,870,'Behind C',20,muted)
# Lateral sign and small, explicitly provisional magnitude.
line([(lens[0],lens[1]),(lens[0],1140)],gray,2,True)
line([(cx,lens[1]),(cx,1140)],gray,2,True)
arrow((lens[0],1135),(cx,1135),green,2,True)
line([((lens[0]+cx)/2,1135),(650,1135)],green,2)
text(665,1116,'4. Lens left = +L',25,green,True)
text(665,1150,'L = 13 mm drawn only as a sign example.',20,muted)
text(665,1180,'Remeasure L; do not assume its magnitude.',20,muted)
# Local ruler gives scale independent of print size.
for i in range(4):
 x=80+i*50;rect((x,1160,x+50,1174),ink if i%2==0 else 'white',ink,0,1)
text(80,1182,'0',17,muted);text(280,1182,'100 mm',17,muted,'', 'end')
# Settings transcription and sign comparison.
text(1215,183,'GRIDRUNNER SCREENSHOT → MOUNT',28,bold=True)
text(1215,232,'Setting',21,muted,True);text(1630,232,'Screenshot',21,muted,True);text(1875,232,'Rear-left mount',21,muted,True)
for y,name,current,actual,color in [(280,'1. Lens height','85 mm','85 mm*',ink),(331,'2. Top-edge angle','180°','180°',ink),(382,'3. Lens forward','−200 mm','−200 mm*',ink),(433,'4. Lens left','−13 mm','+L mm',red)]:
 line([(1215,y+39),(2125,y+39)],'#e6ebf1',1)
 text(1215,y,name,25,color);text(1630,y,current,25,color,True);text(1875,y,actual,25,color,True)
text(1215,500,'−13 means RIGHT. A lens on the LEFT needs a positive value.',23,red,True)
text(1215,542,'*Height and forward distance are existing settings, not a new survey.',20,muted)
text(1215,573,'If L measures 13 mm, enter +13; changing the sign shifts the model 26 mm.',20,muted)
# Scaled side view: front points left; body profile schematic only.
text(1215,678,'SIDE VIEW · same scale · front ←',27,bold=True)
sc=1640.;floor=955.
line([(1230,floor),(2125,floor)],ink,3)
# Only show a shallow schematic body profile, without implying a height dimension.
rect((sc-348,floor-130,sc+348,floor-14),'#e7edf4','#b3c1d0',22)
text(1308,871,'Body side profile schematic',18,muted)
ellipse((sc-36,floor-72,sc+36,floor),'#52657b')
line([(sc,759),(sc,floor+15)],gray,2,True)
# Draw phone thickness and lens height at source-setting values.
px0=sc+64.4*S;px1=px0+143.6*S;ly=floor-85*S
rect((px0,ly-7.7*S,px1,ly),'#d9ebfa',blue,6)
slx=sc+200*S;dot(slx,ly,red,6)
arrow((slx,ly+15),(slx,floor-20),blue,3)
line([(slx,ly),(2120,ly)],gray,2,True)
arrow((2105,ly),(2105,floor),red,2,True)
text(1910,833,'1. H = 85 mm*',22,red,True)
text(1745,734,'Rear camera faces down',22,blue,True)
text(1215,985,'Height is lens center → floor; phone thickness 7.7 mm (nominal).',20,muted)
# Sign conventions clarify reverse-travel observation.
text(1215,1080,'LEFT / RIGHT ALWAYS REFER TO THE ROBOT',25,bold=True)
text(1215,1124,'Outbound motion is backward: travel-left is robot-right.',23,blue,True)
text(1215,1163,'Your ~10 mm travel-left offset alone does not determine the lens correction.',21,muted)
# Bottom editorial notes with measured versus illustrative distinctions.
rect((35,1250,2165,1542),'white','#d6dfea',18)
text(65,1277,'WHAT IS SCALED — AND WHAT STILL NEEDS MEASURING',27,bold=True)
text(65,1323,'Scaled geometry',23,blue,True)
text(65,1360,'Body Ø348 mm and wheel base 235 mm use current robot assumptions.',22,muted)
text(65,1396,'Phone outline 143.6 × 70.9 × 7.7 mm uses Apple’s nominal iPhone X size.',22,muted)
text(65,1432,'Lens −200 mm forward and 85 mm high reproduce the screenshot settings.',22,muted)
text(65,1468,'No app, mount calibration or robot-control settings were changed.',22,muted)
text(1215,1323,'Illustrative geometry / next measurement',23,green,True)
text(1215,1360,'Lens lateral distance L, lens-to-phone edges and carton placement',22,muted)
text(1215,1396,'are provisional. Measure L from the centerline to the active lens.',22,muted)
text(1215,1432,'Phone top means the physical notch/camera end, not landscape UI.',22,muted)
text(1215,1468,'References: RoomBerry26b.png · RoomBerry.svg · GridRunner.png',20,muted)
text(2160,1553,'GroundHog / GridRunner mount review · 2026-11-04',17,muted,anchor='end')
svg.append('</svg>')
im.save(OUT/'groundhog-mount-measurements.png')
(OUT/'groundhog-mount-measurements.svg').write_text('\n'.join(svg)+'\n')
