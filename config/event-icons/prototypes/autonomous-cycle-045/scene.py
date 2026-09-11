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
 mesh(name,verts,[list(reversed(f)) for f in faces],color)
def ball(name,c,r,color):
 # Smooth six-ring sphere; illustrative geometry, not a proxy joint.
 x,y,z=c;n=16;rings=7;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
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

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat


def torus(name,c,major,minor,col,n=64,m=8,plane='xy'):
 v=[]
 for a in np.linspace(0,2*math.pi,n,endpoint=False):
  for t in np.linspace(0,2*math.pi,m,endpoint=False):
   x=(major+minor*math.cos(t))*math.cos(a);y=(major+minor*math.cos(t))*math.sin(a);z=minor*math.sin(t)
   if plane=='xz':y,z=z,y
   v.append(np.array(c)+[x,y,z])
 f=[[i*m+j,((i+1)%n)*m+j,((i+1)%n)*m+(j+1)%m,i*m+(j+1)%m] for i in range(n) for j in range(m)]
 # Parameter winding in XY is outward; swapping to XZ reverses it.
 if plane=='xz':f=[list(reversed(a)) for a in f]
 mesh(name,v,f,col)

scene('aerial-hoop',(1.2,1.2,12))
# Apparatus study: one continuous circular hoop and a single tab with a connector.
# The short strap leaves the upper frame; it is not a complete rigging diagram.
R=.46;r=.030
# Slightly exaggerated tube thickness at icon scale, not a specification.
torus('continuous steel hoop',(0,.58,0),R,r,'#74A7B5',64,8)
# A metal tab with a real through-opening, joined to upper hoop.
ring_y('attachment tab',(0,0,0),.043,.025,.016,'#718791',24)
p=S['parts'][-1];p['vertices']=[[x,y+1.072,z-.008] for x,z,y in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
# Narrow oval connector in a perpendicular plane intersects tab hole geometrically.
torus('connector',(0,1.118,0),.040,.008,'#B9ADA0',32,8)
p=S['parts'][-1];p['vertices']=[[z,y,x*.52] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
box('suspension strap',(0,1.24,0),(.035,.19,.009),'#B7A2BB')
S['measurements']=dict(hoop_center_y=.58,centerline_radius=R,tube_radius=r,hoop_bottom=.090,tab_center_y=1.072,connector_center_y=1.118,strap_bottom=1.145)
S['notes']=['Original circular apparatus study, no performer. Tab and connector are visible geometric approximations; strap exits the crop toward an omitted overhead support. Not a complete rigging assembly, load specification or installation instruction.']

scene('historic-cookstove',(4,3.5,10))
# Generic late-nineteenth-century range: elevated iron body, closed oven/firebox,
# circular cooktop plates and a rear flue. No claim to reproduce a museum object.
col='#657A82';darkcol='#43565F';edge='#8DA1A6'
for x in [-.35,.35]:
 for z in [-.22,.22]:
  rod('iron leg',(x,.01,z),(x*.94,.19,z*.94),.026,darkcol,8)
  box('foot',(x,.01,z),(.09,.02,.07),darkcol)
box('range body',(0,.365,0),(.78,.39,.51),col)
box('base apron',(0,.18,0),(.83,.04,.55),darkcol)
box('cast cooktop',(0,.58,0),(.87,.045,.60),edge)
for x,z in [(-.235,-.13),(-.235,.13),(.19,-.13),(.19,.13)]:
 rod('circular stove lid',(x,.603,z),(x,.606,z),.087,darkcol,24)
 # lifting slot is a dark inset motif on the plate
 box('lid slot',(x,.608,z),(.04,.003,.009),'#2F444D')
box('closed oven door',(.145,.37,.263),(.40,.265,.018),darkcol)
box('oven panel',(.145,.37,.275),(.325,.188,.008),col)
rod('oven handle',(.04,.45,.307),(.25,.45,.307),.013,edge,8)
for x in [.04,.25]:rod('handle mount',(x,.45,.278),(x,.45,.307),.011,edge,8)
box('firebox door',(-.26,.415,.263),(.22,.18,.018),darkcol)
box('ash door',(-.26,.26,.263),(.22,.08,.018),darkcol)
rod('firebox latch',(-.205,.42,.282),(-.17,.42,.282),.012,edge,8)
lathe('open rear flue',[(.068,0),(.068,.419),(.055,.419),(.055,0),(.068,0)],darkcol,24)
S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])+[0,.601,-.22]).tolist()
ring_y('flue collar',(0,.60,-.22),.079,.060,.035,edge,24)
# Shallow pot on front-left cook plate gives cooking specificity.
first=len(S['parts']);lathe('covered pot',[(0,0),(.065,0),(.080,.025),(.082,.11),(0,.11)],'#BC8E66',24)
rod('pot lid',(0,.11,0),(0,.116,0),.088,'#D0A579',24);ball('lid knob',(0,.124,0),.014,darkcol)
for side in [-1,1]:rod('pot side handle',(side*.073,.073,0),(side*.115,.073,0),.013,darkcol,8)
for p in S['parts'][first:]:p['vertices']=(np.array(p['vertices'])+[-.235,.606,.13]).tolist()
S['measurements']=dict(body_bottom=.17,apron_bottom=.16,leg_top=.19,feet_bottom=0,cooktop_top=.6025,plate_top=.606,pot_bottom=.606,flue_top=1.02)
S['notes']=['Four supported legs, closed oven and firebox, flush circular plates and rear flue. Pot rests on the front-left plate. External silhouette only; no internal fire path, combustion model, operating advice or exact Longstreet equipment reproduction.']

scene('pizza-making',(2,8,10))
# A whole uncut pizza on a wooden peel, with a separate raw dough ball.
outline=rounded_outline(.36,.37,.07,6)
flat_extrude('peel blade',outline,0,.014,'#CAA472')
box('peel handle',(0,.007,.26),(.047,.014,.20),'#CAA472')
rod('pizza base',(0,.014,0),(0,.028,0),.151,'#DEB76F',48)
torus('raised crust',(0,.028,0),.139,.014,'#EAC887',48,8,plane='xz')
rod('tomato surface',(0,.028,0),(0,.029,0),.125,'#C9755E',40)
for x,z,r0 in [(-.048,-.052,.025),(.062,-.04,.025),(.025,.063,.026),(-.057,.046,.023),(.009,.007,.020)]:
 rod('cheese patch',(x,.029,z),(x,.031,z),r0,'#EEE0B8',12)
for x,z in [(-.043,-.047),(.050,-.034),(.013,.065)]:
 oval('basil leaf',(x,.033,z),.018,[.6,.13,1.25],'#77A17B',True)
# A low rounded dough portion, deliberately separated from blade and handle.
oval('unshaped dough',(-.230,.02376,.125),.036,[1.08,.66,1],'#E6CD99')
S['measurements']=dict(peel_top=.014,pizza_bottom=.014,crust_min_y=.014,dough_bottom=0,blade_width=.36,blade_depth=.37,handle_end_z=.36)
S['notes']=['Whole pizza on a supported peel plus separate dough portion communicates making, not a sliced restaurant meal. No topping recipe, supplied peel, wood-fired oven or specific process timing is promised.']

scene('play-dough',(3.5,6,10))
# Soft colorful compound slab and ball with a small toy roller.
# Saturated nonfood colors and a star shape distinguish from cookie preparation.
outline=[(.09*math.cos(t)*(1+.10*math.sin(3*t)),.07*math.sin(t)*(1+.08*math.cos(5*t))) for t in np.linspace(0,2*math.pi,40,endpoint=False)]
flat_extrude('flattened dough',outline,0,.014,'#A990BD')
# Raised embossed star is molded compound, not a separate sharp cutter.
star=[(math.cos(math.pi/2+i*math.pi/5)*(.045 if i%2==0 else .020),math.sin(math.pi/2+i*math.pi/5)*(.045 if i%2==0 else .020)) for i in range(10)]
flat_extrude('molded star',star,.014,.025,'#D5BAD9')
oval('compound ball',(.135,.0301,-.012),.035,[1,.86,1],'#79B4AD')
# Roller body and handles share one axis and rest on floor, separate from slab.
rod('toy roller body',(-.07,.022,-.125),(.08,.022,-.125),.022,'#C99B72',20)
rod('left toy handle',(-.115,.022,-.125),(-.07,.022,-.125),.010,'#B880A0',12)
rod('right toy handle',(.08,.022,-.125),(.125,.022,-.125),.010,'#B880A0',12)
S['measurements']=dict(slab_bottom=0,slab_top=.014,star_bottom=.014,star_top=.025,roller_axis_y=.022,roller_radius=.022,ball_bottom=0)
S['notes']=['Original soft modeling-compound forms and toy roller, not branded product replicas. Roller and compound forms rest on one common plane. Pastel purple/teal/pink and an embossed star indicate nonfood creative play; no age rating or supplied inventory promised.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-045/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
