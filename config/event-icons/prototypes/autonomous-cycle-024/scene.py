"""Original 3D equipment studies and orthographic vector exporter. Units: metres.
Run from the repository root. The same mesh vertices drive inspection and SVG.
No third-party geometry, textures or artwork are embedded.
"""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
SCENES={};S=None
wood='#CE8963';lightwood='#FFCC80';darkwood='#AD7156';steel='#91A9B2';dark='#405A63';cream='#F1EDEC';teal='#409C9C';ink='#596896'
def scene(name,camera=(3,5,8)):
 global S
 S=dict(name=name,parts=[],camera=camera,notes=[]);SCENES[name]=S

def mesh(name,vertices,faces,color):S['parts'].append(dict(name=name,vertices=np.asarray(vertices).tolist(),faces=faces,color=color))
def box(name,c,d,color):
 x,y,z=c;a,b,e=np.array(d)/2
 v=[[x+sx*a,y+sy*b,z+sz*e] for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 mesh(name,v,[[0,3,2,1],[4,5,6,7],[0,4,7,3],[1,2,6,5],[0,1,5,4],[3,7,6,2]],color)
def rod(name,a,b,r,color,n=16,r2=None):
 a,b=np.array(a,float),np.array(b,float);axis=b-a;axis/=np.linalg.norm(axis);u=np.cross(axis,[0,0,1] if abs(axis[2])<.9 else [0,1,0]);u/=np.linalg.norm(u);v=np.cross(axis,u);r2=r if r2 is None else r2
 pts=[p+rr*(u*math.cos(t*2*math.pi/n)+v*math.sin(t*2*math.pi/n)) for p,rr in [(a,r),(b,r2)] for t in range(n)]
 faces=[list(range(n-1,-1,-1)),list(range(n,n*2))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)];mesh(name,pts,faces,color)
def extrude(name,outline,z0,z1,color):
 n=len(outline);v=[[x,y,z] for z in [z0,z1] for x,y in outline];faces=[list(range(n-1,-1,-1)),list(range(n,n*2))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)];mesh(name,v,faces,color)
def panel(name,points,color):mesh(name,points,[list(range(len(points)))],color)
def frame(name,c,w,d,t,h,color):
 x,y,z=c
 box(name+' left',(x-w/2+t/2,y,z),(t,h,d),color);box(name+' right',(x+w/2-t/2,y,z),(t,h,d),color)
 box(name+' back',(x,y,z-d/2+t/2),(w-2*t,h,t),color);box(name+' front',(x,y,z+d/2-t/2),(w-2*t,h,t),color)
def lathe(name,profile,color,n=40):
 verts=[[r*math.cos(2*math.pi*i/n),y,r*math.sin(2*math.pi*i/n)] for r,y in profile for i in range(n)]
 faces=[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(len(profile)-1) for i in range(n)]
 mesh(name,verts,faces,color)
def ball(name,c,r,color):
 # Smooth six-ring sphere; illustrative geometry, not a proxy joint.
 x,y,z=c;n=24;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
def rounded_outline(w,h,r,n=8):
 return [(cx+r*math.cos(a),cy+r*math.sin(a)) for cx,cy,start in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)] for a in np.linspace(math.radians(start),math.radians(start+90),n)]
def ring_y(name,c,outer,inner,height,col,n=48):
 x,y,z=c;v=[]
 for yy,rr in [(y,outer),(y+height,outer),(y,inner),(y+height,inner)]:
  for t in np.linspace(0,2*math.pi,n,endpoint=False):v.append([x+rr*math.cos(t),yy,z+rr*math.sin(t)])
 faces=[]
 for i in range(n):
  j=(i+1)%n;faces.extend([[i,n+i,n+j,j],[2*n+i,2*n+j,3*n+j,3*n+i],[i,j,2*n+j,2*n+i],[n+i,3*n+i,3*n+j,n+j]])
 mesh(name,v,faces,col)



scene('garden-stewardship',(5,7,10))
# A representative timber bed,1100x650mm, with connected corner stakes and soil.
frame('bed frame',(0,.14,0),1.1,.65,.04,.28,'#C49167')
for x in [-.50,.50]:
 for z in [-.275,.275]:box('corner stake',(x,.16,z),(.035,.32,.035),'#A77558')
box('soil',(0,.12,0),(1.02,.24,.57),'#806955')
def leaf(name,base,tip,width,col):
 a,c=np.array(base),np.array(tip);axis=c-a;side=np.cross(axis,[0,.6,.8]);side/=np.linalg.norm(side);v=[a,a+axis*.48+side*width,c,a+axis*.48-side*width,a+axis*.5+np.array([0,width*.35,0])]
 mesh(name,v,[[0,1,4],[1,2,4],[2,3,4],[3,0,4]],col);S['parts'][-1]['double_sided']=True
for x,z,height in [(-.29,-.04,.28),(.02,.10,.35),(.28,-.14,.25)]:
 rod('plant stem',(x,.23,z),(x,.24+height,z),.011,'#588D69',10)
 leaf('left leaf',(x,.28+height*.25,z),(x-.16,.30+height*.60,z-.025),.08,'#78A878')
 leaf('right leaf',(x,.30+height*.40,z),(x+.14,.31+height*.75,z+.025),.07,'#94B87F')
# Representative trowel inserted in soil; metal blade joins a wooden grip, no human pose.
a=np.array([.39,.20,.17]);c=np.array([.45,.55,.17]);u=(c-a)/np.linalg.norm(c-a);w=np.array([0,0,1]);pts=[a,a+u*.15+w*.058,a+u*.22+w*.045,a+u*.24,a+u*.22-w*.045,a+u*.15-w*.058]
mesh('trowel blade',pts,[[0,1,2,3,4,5]],'#AABCC4');rod('trowel shank',a+u*.21,c,.011,'#7F959F',10);rod('trowel handle',c,c+u*.18,.026,'#698CAC',16)
S['measurements']=dict(bed_m=[1.10,.65,.28],board_thickness_m=.04,soil_height_m=.24,trowel_length_approx_m=.54)
S['notes']=['Timber boards meet at the corners and contain soil below their rim. Three representative plants root in the soil. Trowel blade is inserted into soil and connects through a shank to its handle. This garden-maintenance emblem does not promise specific tools, plants or a raised bed at every event.']

scene('piano-trio',(1.4,12,7))
# Isolated common-scale instrument study: violin, cello and a piano keyboard fragment.
# Instruments lie on their backs; keybed is a cutaway semantic fragment, not a full electronic keyboard.
box('piano keybed',(0,.028,.48),(1.27,.056,.27),'#43515E');S['parts'][-1]['paint_underlay']=1
n=52;kw=1.20/n
for i in range(n):
 x=-.60+(i+.5)*kw;box('white piano key',(x,.064,.48),(kw-.0008,.020,.21),'#EDE9DA');S['parts'][-1]['paint_underlay']=2
 if i<n-1 and i%7 not in [1,4]:box('black piano key',(-.60+(i+1)*kw,.081,.431),(kw*.56,.016,.112),'#34404C')
# Body contour: cubic curves on each side establish bouts, C-waist and neck junction.
def curve(a,b,c,d,n=7):
 a,b,c,d=map(lambda p:np.array(p,float),(a,b,c,d));return [(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d for t in np.linspace(0,1,n,endpoint=False)]
side=[]
for pts in [((0,-.378),(.18,-.39),(.22,-.25),(.14,-.12)),((.14,-.12),(.07,-.10),(.07,.025),(.15,.055)),((.15,.055),(.255,.08),(.255,.29),(.14,.345)),((.14,.345),(.085,.39),(.035,.38),(0,.378))]:side+=curve(*pts)
side.append(np.array([0,.378]));outline=side+[np.array([-x,z]) for x,z in side[-2:0:-1]]
# This outline runs clockwise in XZ; reverse for upward-facing flat extrusion.
outline=list(reversed(outline))
def bowed(name,cx,cz,scale,rib,col):
 start=len(S['parts']);pts=[(cx+x*scale,cz+z*scale) for x,z in outline];flat_extrude(name+' body',pts,0,rib,col)
 # A slightly inset top plate gives a broad edge without tiny purfling.
 flat_extrude(name+' top',[(cx+x*scale*.97,cz+z*scale*.99) for x,z in outline],rib,rib+.006*scale,col)
 box(name+' neck',(cx,rib*.7,cz-.48*scale),(.055*scale,.065*scale,.25*scale),'#B17B51')
 box(name+' fingerboard',(cx,rib+.019*scale,cz-.305*scale),(.066*scale,.028*scale,.57*scale),'#3C4247')
 box(name+' pegbox',(cx,rib*.78,cz-.66*scale),(.055*scale,.075*scale,.12*scale),'#B57A4C')
 rod(name+' scroll',(cx-.018*scale,rib*.85,cz-.735*scale),(cx+.018*scale,rib*.85,cz-.735*scale),.027*scale,col,18)
 for j in range(4):
  z=cz-(.618+j*.022)*scale;side=-1 if j%2 else 1
  rod(name+' peg',(cx,rib*.8,z),(cx+side*.065*scale,rib*.8,z),.009*scale,'#424B50',8)
 bridge_y=rib+.060*scale;box(name+' bridge',(cx,rib+.026*scale,cz+.07*scale),(.13*scale,.052*scale,.012*scale),'#E5C995')
 tail=[(cx-.026*scale,cz+.33*scale),(cx+.026*scale,cz+.33*scale),(cx+.045*scale,cz+.16*scale),(cx-.045*scale,cz+.16*scale)]
 flat_extrude(name+' tailpiece',list(reversed(tail)),rib+.006*scale,rib+.027*scale,'#455057')
 for dx in [-.021,-.007,.007,.021]:
  rod(name+' string',(cx+dx*scale,rib+.035*scale,cz-.59*scale),(cx+dx*scale,bridge_y,cz+.07*scale),.0018*scale,'#F0D9AE',5)
  rod(name+' string',(cx+dx*scale,bridge_y,cz+.07*scale),(cx+dx*scale,rib+.028*scale,cz+.24*scale),.0018*scale,'#F0D9AE',5)
 # Two original f-hole symbols follow the top plate, represented by flat dark apertures.
 for side in [-1,1]:
  p0=(cx+side*.105*scale,rib+.0062*scale,cz-.055*scale);p1=(cx+side*.092*scale,rib+.0062*scale,cz+.02*scale);p2=(cx+side*.115*scale,rib+.0062*scale,cz+.105*scale)
  rod(name+' sound hole',p0,p1,.007*scale,'#765235',6);rod(name+' sound hole',p1,p2,.007*scale,'#765235',6)
 if name=='cello':rod('retracted endpin',(cx,rib*.5,cz+.37*scale),(cx,rib*.5,cz+.46*scale),.009,'#869DA8',10)
 else:
  flat_extrude('chinrest',[(cx-.06*scale,cz+.33*scale),(cx-.16*scale,cz+.29*scale),(cx-.15*scale,cz+.19*scale),(cx-.055*scale,cz+.24*scale)],rib+.01,rib+.035,'#41484F')
 if name=='violin':
  # Violin neck/head are proportionally longer than a cello scaled by body length.
  hinge=cz-.378*scale
  for part in S['parts'][start:]:part['vertices']=[[x,y,hinge+(z-hinge)*1.30 if z<hinge else z] for x,y,z in part['vertices']]
 return start
bowed('cello',-.27,-.19,1,.115,'#D99A62')
bowed('violin',.33,-.21,.357/.756,.032,'#BE824F')
S['measurements']=dict(cello_body_length_m=.756,violin_body_length_m=.357,cello_ribs_m=.115,violin_ribs_m=.032,violin_total_length_approx_m=.589,piano_white_keys=52,piano_keyboard_width_m=1.20)
S['notes']=['Common-scale original violin and cello bodies are paired with a piano keybed fragment. Body lengths follow museum/reference measurements approximately. Both bowed instruments lie on their backs; necks, pegboxes, bridges, tailpieces and four strings connect. No player pose, stand or actual concert layout is implied. The piano is a symbolic cutaway keybed rather than a complete instrument. Its52white keys include the A0toC8black-key grouping; keys and strings intentionally simplify at small sizes.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-024')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
