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


scene('shuttle-tatting',(2,8,7))
# A60mm closed-point post shuttle. Curved shell plates meet at both tips.
nx,nz=16,6
for layer in ['upper','lower']:
 verts=[]
 for face in [0,1]:
  for i in range(nx+1):
   t=i/nx;x=-.030+.060*t;w=.012*math.sin(math.pi*t)
   for j in range(nz+1):
    q=-1+2*j/nz;z=w*q-.018
    y=(.002+.007*math.sin(math.pi*t)*(1-.20*q*q) if layer=='upper' else .001)+face*.0012
    verts.append([x,y,z])
 n=(nx+1)*(nz+1);fs=[]
 for i in range(nx):
  for j in range(nz):
   a=i*(nz+1)+j;fs.extend([[a,a+1,a+nz+2,a+nz+1],[a+n,a+n+nz+1,a+n+nz+2,a+n+1]])
 edge=list(range(nz+1))+[i*(nz+1)+nz for i in range(1,nx+1)]+[nx*(nz+1)+j for j in range(nz-1,-1,-1)]+[i*(nz+1) for i in range(nx-1,0,-1)]
 for a,c in zip(edge,edge[1:]+edge[:1]):fs.append([a,c,c+n,a+n])
 mesh(layer+' shuttle plate',verts,fs,'#DCAD56')
rod('central post',(0,.002,-.018),(0,.0088,-.018),.0035,'#BC8845',20)
rod('wound thread',(0,.003,-.018),(0,.007,-.018),.007,'#D57586',28)
# Original three-ring lace sample. Rings, joins and picots are enlarged for pictogram readability.
def threadline(points,col='#C96D84',r=.0009):
 for a,c in zip(points,points[1:]):rod('lace thread',a,c,r,col,6)
for cx,cz,rx,rz in [(-.014,.019,.009,.012),(.005,.019,.009,.012),(.024,.019,.009,.012)]:
 points=[[cx+rx*math.cos(t),.0012,cz+rz*math.sin(t)] for t in np.linspace(0,2*math.pi,25)];threadline(points)
 for a in [math.pi/4,math.pi/2,3*math.pi/4]:
  center=np.array([cx+(rx+.0018)*math.cos(a),.0012,cz+(rz+.0018)*math.sin(a)])
  threadline([center+np.array([.0022*math.cos(t),0,.0022*math.sin(t)]) for t in np.linspace(0,2*math.pi,9)])
threadline([[-.005,.0012,.019],[-.004,.0012,.019]]);threadline([[.014,.0012,.019],[.015,.0012,.019]])
threadline([[.006,.005,-.018],[.024,.003,-.010],[.036,.0012,.001],[.024,.0012,.007]])
S['measurements']=dict(shuttle_length_m=.060,maximum_width_m=.024,maximum_height_m=.0102,plate_thickness_m=.0012,thread_diameter_illustrative_m=.0018)
S['notes']=['Two closed-point shuttle plates are connected by an internal post with wound thread. Side gap is real geometry. Original enlarged three-ring lace and picots are semantic technique evidence, not a working tatting pattern or knot-level model. No hand pose is implied.']

scene('stuffed-applique',(2,9,7))
flat_extrude('foundation cloth',rounded_outline(.18,.17,.012),0,.002,'#A0BAB7')
# Original padded oval attached to the intact foundation; no copied workshop motif.
nr,nt=6,32;verts=[]
for j in range(nr+1):
 r=j/nr
 for i in range(nt):
  a=2*math.pi*i/nt;verts.append([.062*r*math.cos(a),.002+.025*(1-r*r)**.7,.046*r*math.sin(a)])
fs=[]
for j in range(nr):
 for i in range(nt):
  k=(i+1)%nt;fs.append([j*nt+i,(j+1)*nt+i,(j+1)*nt+k,j*nt+k])
# XZ ring sequence has downward normal; reverse to face upward.
mesh('padded fabric',verts,[list(reversed(f)) for f in fs],'#DF8B87')
for i in range(20):
 a=2*math.pi*i/20
 p=[.060*math.cos(a),.0055,.0445*math.sin(a)];q=[.066*math.cos(a),.0025,.050*math.sin(a)]
 rod('joining stitch',p,q,.0017,'#805E72',6)
S['measurements']=dict(foundation_m=[.18,.17],foundation_thickness_m=.002,pad_width_m=.124,pad_depth_m=.092,pad_height_above_base_m=.025)
S['notes']=['Raised stuffed fabric oval is attached at its perimeter to an intact foundation swatch. Twenty representative attachment stitches enter near the edge of the cushion and the foundation. Layered padding and broad coherent shading distinguish it from flat applique. This is not the exact class pattern or a stitch-by-stitch construction guide.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-023')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
