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


from shapely.geometry import Polygon,Point
from shapely.geometry.polygon import orient
from shapely.ops import triangulate
from shapely.affinity import scale,translate

def pierced_prism(name,poly,y0,y1,col):
 poly=orient(poly,1);v=[];faces=[]
 for tri in triangulate(poly):
  if not poly.buffer(1e-10).covers(tri):continue
  pts=list(orient(tri,1).exterior.coords)[:-1];i=len(v);v += [[x,y0,z] for x,z in pts]+[[x,y1,z] for x,z in pts]
  # XZ projection reverses the usual XY face handedness.
  faces += [[i,i+1,i+2],[i+5,i+4,i+3]]
 for ring in [poly.exterior,*poly.interiors]:
  pts=list(ring.coords)
  for a,bb in zip(pts,pts[1:]):
   i=len(v);v += [[a[0],y0,a[1]],[bb[0],y0,bb[1]],[bb[0],y1,bb[1]],[a[0],y1,a[1]]];faces.append([i+3,i+2,i+1,i])
 mesh(name,v,faces,col)



scene('book-signing',(2,7,6))
# An original,representative lay-flat book. No real signature or cover reproduced.
box('open covers',(0,.0015,0),(.252,.003,.19),'#719A9F')
box('center binding',(0,.004,0),(.006,.005,.184),'#BBA886')
def page_y(x):return .015-.008*math.exp(-abs(x)/.019)
for side in [-1,1]:
 xs=np.linspace(.004,.120,13)*side;xs=sorted(xs)
 profile=[(xs[0],.003),(xs[-1],.003)]+[(x,page_y(x)) for x in reversed(xs)]
 extrude('closed page block',profile,-.091,.091,'#EEE2CA')
 # Same shape uses a broad warm top,with edge occlusion dictated by the mesh.
 for y in [.005,.008,.011]:
  xa=.012 if y<=.008 else .025
  box('front page edge',(side*(.120+xa)/2,y,.09105),(.120-xa,.00045,.0001),'#C8BCA2')
# Curved ink line symbols lie on the top sheet,not raised floating text.
def inkline(name,xz,col,r=.00065):
 tube(name,[(x,page_y(x)+.00012,z) for x,z in xz],r,col,n=4)
for z in [-.050,-.031,-.012]:inkline('left printed line',[(-.102,z),(-.046,z),(-.032,z+.002)],'#B6AA92',.00045)
# Original abstract flourish,not a person's signature or legible name.
sig=[(.025,.025),(.046,-.026),(.043,.023),(.061,-.003),(.053,.031),(.072,.012),(.082,.021),(.104,.011)]
inkline('abstract signed flourish',sig,'#718795',.0010)
inkline('signature underline',[(.028,.043),(.061,.040),(.103,.040)],'#718795',.0008)
# Uncapped writing pen rests on the shared ground beyond the book's near edge.
rod('pen barrel',(-.055,.004,.116),(.066,.004,.116),.004,'#AC7D88',n=12)
rod('metal pen nose',(-.075,.004,.116),(-.055,.004,.116),.00065,'#9AAAB0',n=12,r2=.004)
rod('ink point',(-.079,.004,.116),(-.075,.004,.116),.00035,'#4F6976',n=8,r2=.00065)
rod('end plug',(.066,.004,.116),(.071,.004,.116),.004,'#839DA3',n=12)
# Metal band is joined over barrel,not a detached cap.
rod('grip band',(-.056,.004,.116),(-.051,.004,.116),.0042,'#BDAD8D',n=12)
S['notes']=['Original representative lay-flat book252x190mm including covers. Broad pages curve toward the gutter; closed page blocks,cover and binding connect. Cover rests on ground.','Printed lines and original abstract signing flourish follow page height. No real signature,author name,cover image or readable text copied.','Uncapped pen lies beyond the near edge on the same ground plane. Barrel touches ground; narrow conical tip naturally has clearance. Grip band/end plug join the barrel. No hovering hand or writing-action claim.','Dimensions approximate generic stationery,not event-provided materials. LOC book structure excerpt inherited from75; original geometric approximation is not a conservation tutorial.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
