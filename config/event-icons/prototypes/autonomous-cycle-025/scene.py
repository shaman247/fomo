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


scene('sculpt-object',(3,2,8))
# A closed original virtual clay form. Dimensionless units: software-space sculpting study.
n=24;rings=14;v=[]
for j in range(rings+1):
 t=-math.pi/2+math.pi*j/rings
 for i in range(n):
  a=2*math.pi*i/n
  # A pinched lower body and gently offset upper lobe; one continuous closed surface.
  width=.70+.16*math.sin(t*3)
  v.append([width*math.cos(t)*math.cos(a)+.12*math.sin(t),math.sin(t),.68*math.cos(t)*math.sin(a)])
faces=[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(rings) for i in range(n)]
faces=[list(reversed(f)) for f in faces]
# Smooth vertex normals derived from this same surface, then split its triangles at
# two light thresholds. Geometry is unchanged; only broad paint boundaries improve.
v=np.array(v);normals=np.zeros_like(v)
for f in faces:
 face=v[f];normal=sum((np.cross(a,b) for a,b in zip(face,np.roll(face,-1,axis=0))),np.zeros(3))
 for idx in f:normals[idx]+=normal
normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
light=np.array([-.4,.8,.5]);light/=np.linalg.norm(light);levels=normals@light
# Pole duplicate normals share the smooth vertical normal.
levels[:n]=np.dot([0,-1,0],light);levels[-n:]=np.dot([0,1,0],light)
def clip(poly,threshold,above):
 result=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  da=(a[1]-threshold)*(1 if above else -1);db=(b[1]-threshold)*(1 if above else -1)
  if da>=0:result.append(a)
  if (da>=0)!=(db>=0):
   t=da/(da-db);result.append((a[0]+t*(b[0]-a[0]),threshold))
 return result
for low,high,color in [(-2,0,'#A7785F'),(0,.55,'#C79172'),(.55,2,'#D69C7B')]:
 vv=[];ff=[]
 for f in faces:
  for tri in [(f[0],f[1],f[2]),(f[0],f[2],f[3])]:
   poly=[(v[i],levels[i]) for i in tri];poly=clip(clip(poly,low,True),high,False)
   if len(poly)<3:continue
   ids=list(range(len(vv),len(vv)+len(poly)));vv.extend(x[0] for x in poly);ff.append(ids)
 mesh('virtual clay paint',vv,ff,color)
S['measurements']=dict(height_virtual_units=2,angular_samples=n,latitude_intervals=rings,physical_scale=None)
S['notes']=['One connected virtual sculpt with a pinched lower body and offset upper lobe. A software-space specimen, not a real clay object or printable model. No anatomy or real-world supports are implied. Original software window and brush cursor are planar symbolic UI surrounding its projected silhouette.']
b=Path('.scratch/icon-cycles-20260909/cycle-025')
(b/'scenes.json').write_text(json.dumps(SCENES,indent=2))
(b/'geometry-measurements.json').write_text(json.dumps({k:s['measurements'] for k,s in SCENES.items()},indent=2))
