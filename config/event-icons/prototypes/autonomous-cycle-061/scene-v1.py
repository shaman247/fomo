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
 x,y,z=c;n=24;rings=11;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n

def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]

def ellipsoid(name,c,scale,color,n=24,rings=9):
 x,y,z=c;rx,ry,rz=scale
 v=[[x+rx*math.cos(t)*math.cos(a),y+ry*math.sin(t),z+rz*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)

scene('kayaking',(-5,10,10))
# Generic sit-inside kayak: continuous bottom hull and annular deck with a real open cockpit.
n=40;angles=np.linspace(0,2*math.pi,n,endpoint=False)
outer=np.array([[1.6*math.cos(t),.19,.34*math.sin(t)*(abs(math.sin(t))**.18)] for t in angles])
inner=np.array([[.46*math.cos(t)-.06,.22,.215*math.sin(t)] for t in angles])
low=outer.copy();low[:,0]*=.94;low[:,2]*=.55;low[:,1]=-.05
verts=np.vstack([outer,low]);mesh('tapered hull',verts,[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]+[list(range(n,2*n))],'#D48B67');S['parts'][-1]['double_sided']=True
verts=np.vstack([outer,inner]);mesh('deck with cockpit opening',verts,[[i,n+i,n+(i+1)%n,(i+1)%n] for i in range(n)],'#E6AE78');S['parts'][-1]['double_sided']=True
floor=inner.copy();floor[:,1]=-.025
mesh('cockpit inner wall',np.vstack([inner,floor]),[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)],'#766F6B');S['parts'][-1]['double_sided']=True
panel('cockpit floor',list(floor),'#59666B')
for i in range(n):rod('cockpit rim',inner[i],inner[(i+1)%n],.025,'#8B9088',8)
box('seat cushion',(-.19,.012,0),(.22,.05,.30),'#82959A');box('seat back',(-.35,.105,0),(.045,.23,.30),'#6E878D')
# Double-bladed paddle resting across deck behind the cockpit; blades are attached to one shaft.
a=np.array([-.65,.235,-.98]);bb=np.array([-.65,.235,.98]);rod('paddle shaft',a,bb,.023,'#789297',12)
for sign in [-1,1]:
 outline=[(-.69,sign*.65),(-.79,sign*.82),(-.80,sign*1.12),(-.74,sign*1.22),(-.58,sign*1.22),(-.54,sign*1.09),(-.55,sign*.83),(-.61,sign*.65)]
 flat_extrude('paddle blade',outline,.22,.255,'#6EA5A3')
S['notes']=['Original generic single-cockpit kayak, not the actual Quogue fleet model. Manufacturer text establishes bow, stern, hull and cockpit. Deck has an actual oval opening, attached rim and inner wall reaching floor; seat reaches the cockpit floor. One shaft connects two equal opposing blades and rests on rear deck. No paddler or implied unsafe pose. Shape, paddle and seat count are illustrative; event offers single and double kayaks.']

scene('potato-harvest',(3,5,10))
# Low soil patch and freshly lifted tubers, with a supported four-tine digging fork.
box('soil patch',(0,.055,0),(.9,.11,.46),'#9E806A')
for c,scale in [((-.23,.21,.07),(.19,.105,.115)),((.17,.195,.09),(.15,.085,.105)),((-.07,.19,-.16),(.14,.08,.10))]:
 ellipsoid('harvested potato',c,scale,'#D2AB7F');S['parts'][-1]['flat_paint']=True
 x,y,z=c
 for dx,dz in [(-.055,.035),(.055,.015)]:
  dy=scale[1]*math.sqrt(max(0,1-(dx/scale[0])**2-(dz/scale[2])**2))
  ellipsoid('potato eye',(x+dx,y+dy,z+dz),(.012,.006,.009),'#AB865F',10,5);S['parts'][-1]['flat_paint']=True
# Fork tine tips penetrate soil to y=.065; back and shaft stay visibly connected.
for x in [.14,.22,.30,.38]:rod('fork tine',(x,.065,-.12),(x,.36,-.12),.013,steel,10)
rod('fork shoulder',(.12,.36,-.12),(.40,.36,-.12),.024,steel,12)
rod('fork neck',(.26,.36,-.12),(.26,.44,-.12),.026,steel,12)
rod('wood shaft',(.26,.43,-.12),(.26,.86,-.12),.026,wood,12)
for a,bb in [((.26,.84,-.12),(.17,.99,-.12)),((.17,.99,-.12),(.17,1.08,-.12)),((.17,1.08,-.12),(.35,1.08,-.12)),((.35,1.08,-.12),(.35,.99,-.12)),((.35,.99,-.12),(.26,.84,-.12))]:rod('open D handle',a,bb,.025,wood,12)
S['notes']=['Three original ellipsoid harvested potatoes sit on soil: center heights equal soilheight plus each vertical radius. Eyes are attached small skin markings, not sprouts. Four-tine fork joins shoulder, neck, wood shaft and open D handle; tips penetrate soil so the upright tool is supported. This depicts the harvest activity, not underground botany, supplied equipment, guaranteed yield or actual nineteenth-century tool specification.']

scene('bonsai',(2,3,12))
# Shallow planted tray, two feet, a connected informal-upright trunk and branch-supported leaf pads.
for x in [-.26,.26]:box('tray foot',(x,.025,0),(.12,.05,.25),'#748F97')
box('tray base',(0,.065,0),(.70,.07,.40),'#71959D')
frame('tray rim',(0,.12,0),.77,.46,.045,.08,'#88A6A9')
box('soil surface',(0,.133,0),(.68,.035,.37),'#978171')
trunk=[((-.12,.15,0),.082),((-.03,.31,0),.06),((-.10,.48,0),.049),((.04,.65,-.015),.038),((.02,.84,0),.016)]
for (a,r),(bb,r2) in zip(trunk,trunk[1:]):rod('connected tapered trunk',a,bb,r,wood,16,r2)
for a,bb,r in [((-.06,.39,0),(-.31,.49,0),.028),((-.08,.50,0),(.27,.61,0),.03),((.03,.69,0),(-.17,.78,0),.022)]:rod('leaf-pad branch',a,bb,r,wood,12,.013)
for c,scale,col in [((-.31,.55,0),(.25,.085,.16),'#729D6E'),((.27,.67,0),(.24,.085,.16),'#76A775'),((-.17,.83,0),(.21,.08,.14),'#83AE78'),((.02,.93,0),(.18,.105,.14),'#86B17D')]:ellipsoid('trimmed foliage pad',c,scale,col,24,9)
# Roots flare into soil, instead of a trunk balancing at a single tangent point.
for bb in [(-.25,.149,.08),(.04,.15,.065),(-.09,.15,-.12)]:rod('surface root',(-.11,.19,0),bb,.028,wood,10,.013)
S['notes']=['Original informal-upright miniature tree in shallow tray informed by NC Cooperative Extension construction text. Trunk starts in soil; tapering segments join and branches reach leaf pads; surface roots meet soil. Feet support tray base, rim encloses soil. Simplified leaf pads do not identify a species or prescribe bonsai care; no exact displayed tree or hands-on class promised.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
