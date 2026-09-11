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



scene('press-on-nails',(3,7,8))
# Curved artificial nail shells in five sizes. They are objects rather than
# fingers. Closed upper/lower surfaces join at every perimeter edge.
from shapely.ops import triangulate,unary_union
from shapely.geometry import MultiPoint

def nail(name,c,w,L,col,accent=False):
 x0,z0=c;cap=w*.46
 # Rounded capsule-like outline with a long central nail plate.
 poly=scale(Point(0,0).buffer(1,resolution=20),w/2,L/2)
 # A broad middle with softly rounded ends,not an anatomical hand.
 poly=Polygon([(-w/2,-L*.24),(-w*.46,-L*.40),(-w*.28,-L*.49),(0,-L/2),(w*.28,-L*.49),(w*.46,-L*.40),(w/2,-L*.24),(w/2,L*.35),(w*.42,L*.47),(-w*.42,L*.47),(-w/2,L*.35)])
 pts=list(poly.exterior.coords)[:-1]+[(x,z) for x in np.linspace(-w/2,w/2,13) for z in np.linspace(-L/2,L/2,13) if poly.covers(Point(x,z))]
 v=[];f=[];h=w*.25;th=.00065
 def pos(x,z,lower=False):return [x+x0,th+h*math.sqrt(max(0,1-(x/(w/2))**2))-(th if lower else 0),z+z0]
 for tri in triangulate(MultiPoint(pts)):
  if not poly.buffer(1e-10).covers(tri):continue
  pp=list(orient(tri,1).exterior.coords)[:-1];i=len(v);v += [pos(x,z) for x,z in pp]+[pos(x,z,True) for x,z in pp];f += [[i+2,i+1,i],[i+3,i+4,i+5]]
 for a,bb in zip(list(poly.exterior.coords),list(poly.exterior.coords)[1:]):
  i=len(v);v += [pos(*a),pos(*bb),pos(*bb,True),pos(*a,True)];f.append([i,i+1,i+2,i+3])
 mesh(name,v,f,col)
 if accent:
  # A short painted stripe follows the same curved upper surface.
  v=[];f=[]
  for z in [L*.15,L*.25]:
   for x in np.linspace(-w*.40,w*.40,13):q=pos(x,z);q[1]+=.00004;v.append(q)
  for j in range(12):f.append([j+1,j,j+13,j+14])
  mesh(name+' painted band',v,f,'#F4DBB7');S['parts'][-1]['double_sided']=True
for i,(x,z,w,L,col) in enumerate([(-.027,.031,.016,.030,'#D9918C'),(-.006,.033,.013,.028,'#D59C91'),(.012,.034,.012,.029,'#87AEA0'),(.030,.033,.011,.027,'#DFA8A0'),(.046,.031,.009,.023,'#B0BCAF')]):
 nail('nail tip'+str(i),(x,z),w,L,col,accent=i in [0,2])
# Small closed nail-color bottle: body rests onground,neck/cap are joined.
lathe('color bottle',[(0,0),(.012,0),(.014,.003),(.014,.028),(.010,.032),(0,.032)],'#B98582',n=32)
p=S['parts'][-1];p['vertices']=[[x-.025,y,z-.025] for x,y,z in p['vertices']]
rod('bottle cap',(-.025,.031,-.025),(-.025,.051,-.025),.009,'#927D6D',n=24)
# Plain bottle label,attached to front tangent as a small physical plaque.
box('bottle label',(-.025,.017,-.0108),(.013,.012,.0004),'#EAD4B2')
S['notes']=['Original artificial nail shells have a transverse C curve,joined inner/outer surfaces and a closed perimeter. Five different widths/lengths depict removable nail tips,not fingers or an anatomical hand. Lower side edges touch the table.','Two painted bands follow their shell surfaces rather than floating. Closed color bottle rests on the same table,with connected neck/cap and attached label. No wet brush or impossible hand interaction.','Aprés technical text supports curvature differences; KISS cached product text supports rounded-square press-on shapes,not a copied pattern. CurrentKISSURLredirected; no product photographs viewed. No adhesive chemistry,UV lamp,exacttip count or class kit promised.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
