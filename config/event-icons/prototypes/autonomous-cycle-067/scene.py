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

# Connected tubular curves, with continuous parallel-transport-like local frames.
def tube(name,points,r,col,n=8,flat=True):
 pts=np.asarray(points,float);vv=[]
 for i,p in enumerate(pts):
  axis=pts[min(i+1,len(pts)-1)]-pts[max(i-1,0)];axis/=np.linalg.norm(axis);u=np.cross(axis,[0,0,1] if abs(axis[2])<.9 else [0,1,0]);u/=np.linalg.norm(u);v=np.cross(axis,u)
  vv.extend(p+r*(u*math.cos(t)+v*math.sin(t)) for t in np.linspace(0,2*math.pi,n,endpoint=False))
 ff=[[i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j] for i in range(len(pts)-1) for j in range(n)]
 ff += [list(range(n-1,-1,-1)),list(range((len(pts)-1)*n,len(pts)*n))];mesh(name,vv,ff,col);S['parts'][-1]['flat_paint']=flat

def torus_z(name,c,R,r,col,n=32,m=8):
 x,y,z=c;v=[[x+(R+r*math.cos(q))*math.cos(t),y+(R+r*math.cos(q))*math.sin(t),z+r*math.sin(q)] for t in np.linspace(0,2*math.pi,n,endpoint=False) for q in np.linspace(0,2*math.pi,m,endpoint=False)]
 f=[[i*m+j,((i+1)%n)*m+j,((i+1)%n)*m+(j+1)%m,i*m+(j+1)%m] for i in range(n) for j in range(m)];mesh(name,v,f,col)

scene('pantry-restocking',(3,3,11))
# Approximate small pantry shelving, 1.0 x.36 x1.20m; front is +Z.
for x in [-.48,.48]:
 for z in [-.15,.15]:box('shelf upright',(x,.60,z),(.040,1.20,.040),'#87978A')
for y in [.10,.59,1.08]:box('shelf board',(0,y,0),(.98,.045,.36),'#9AAB96')
# Two broad cartons and two canned goods already on shelving.
for x,y,w,h,col in [(-.24,.8075,.34,.39,'#C8A77C'),(.23,.785,.33,.345,'#CAB899'),(-.28,.27,.30,.295,'#BB9D79')]:
 box('pantry food carton',(x,y,0),(w,h,.27),col)
 box('food category label',(x,y,.139),(w*.55,h*.37,.008),'#E3D5B3')
for x in [.14,.34]:
 start=len(S['parts']);lathe('sealed food tin',[(0,.1225),(.075,.1225),(.079,.14),(.079,.40),(.075,.4175),(0,.4175)],'#8CA4A0',24)
 for p in S['parts'][start:]:p['vertices']=(np.array(p['vertices'])+[x,0,0]).tolist()
# Delivery carton on floor in foreground; two open top flaps and bagged food inside.
box('delivery box bottom',(-.56,.025,.49),(.43,.05,.39),'#B78B61')
for x in [-.755,-.365]:box('delivery box side',(x,.19,.49),(.04,.33,.39),'#C49A70')
for z in [.315,.665]:box('delivery box face',(-.56,.19,z),(.35,.33,.04),'#CBA77B')
# Flaps hinge directly to front/back rims, tilted outward but no unsupported panels.
mesh('open rear flap',[[-.755,.355,.295],[-.365,.355,.295],[-.365,.43,.16],[-.755,.43,.16]],[[0,1,2,3]],'#D9B78B')
mesh('open front flap',[[-.755,.355,.685],[-.365,.355,.685],[-.365,.39,.80],[-.755,.39,.80]],[[3,2,1,0]],'#D9B78B')
for x,col in [(-.65,'#A2B19A'),(-.47,'#D6C39D')]:
 box('sealed pantry bag',(x,.21,.49),(.13,.32,.19),col)
 rod('folded bag top',(x-.065,.378,.49),(x+.065,.378,.49),.008,'#84987E',8)
# Original fruit emblem on the delivery carton clarifies food rather than generic storage.
rod('fruit label',(-.56,.20,.686),(-.56,.20,.691),.067,'#B9826B',24)
rod('fruit stem',(-.56,.258,.692),(-.55,.284,.692),.004,'#758870',8)
panel('fruit leaf',[[-.55,.279,.693],[-.53,.311,.693],[-.50,.31,.693],[-.514,.287,.693]],'#839777')
S['notes']=['Original approximate shelf and delivery box rest on ground. Shelf boards support closed cartons and tins; bags rest on delivery-box bottom. Open box flaps hinge to upper edges. No promised food brands, exact diet contents, pallet equipment or location layout.']

scene('gem-mineral-show',(4,5,11))
# Display plinths ground both specimens; exact commercial fixtures not promised.
box('mineral display base',(-.22,.035,0),(.39,.07,.35),'#A8947D')
box('gem display base',(.25,.06,.02),(.30,.12,.30),'#829B97')
# Generic clustered prismatic crystals. Hexagonal prism and termination are simplified illustrative forms.
for x,z,R,h,col in [(-.25,-.04,.090,.51,'#A494B7'),(-.12,.05,.065,.31,'#C1B1CE'),(-.33,.05,.065,.29,'#B2A3C1')]:
 n=6;v=[[x+R*math.cos(t),y,z+R*math.sin(t)] for y in [.07,h] for t in np.linspace(0,2*math.pi,n,endpoint=False)];v.append([x,h+.13,z]);f=[list(range(n-1,-1,-1))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]+[[i+n,(i+1)%n+n,2*n] for i in range(n)];mesh('prismatic crystal',v,[list(reversed(ff)) for ff in f],col)
# Original simplified octagonal faceted gem: table, crown, girdle and pavilion.
# Pavilion sits in a shallow display support; no optical/cut-grade claim.
n=8;cx=.25;cz=.02;v=[]
for radius,y in [(.009,.14),(.137,.29),(.137,.31),(.075,.385)]:
 v += [[cx+radius*math.cos(t),y,cz+radius*math.sin(t)] for t in np.linspace(0,2*math.pi,n,endpoint=False)]
f=[list(range(n-1,-1,-1)),list(range(3*n,4*n))]
for j in range(3):
 for i in range(n):f.append([j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i])
mesh('faceted gem',v,[list(reversed(ff)) for ff in f],'#7BA8AD')
# Low ring seat has bottom on plinth and upper rim matching pavilion at y.19.
start=len(S['parts']);lathe('gem display seat',[(.064,.12),(.064,.19),(.0517,.19),(.0517,.12),(.064,.12)],'#6E8986',24)
for p in S['parts'][start:]:p['vertices']=(np.array(p['vertices'])+[cx,0,cz]).tolist()
S['notes']=['Original generic crystal cluster on a plinth beside a faceted gem in a supported ring seat. GIA terminology informs table/crown/girdle/pavilion, not a specific58-facet brilliant or cut grade. Crystals are illustrative prismatic mineral forms, not mineral identification or a guaranteed dealer inventory.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
