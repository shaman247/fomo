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



scene('scribbling-robot',(4,5,8))
# Three equal marker legs support a triangle of wooden craft sticks.
legs=[(-.045,.025),(.045,.025),(0,-.047)]
box('drawing paper',(0,-.0006,0),(.15,.0012,.15),'#E9DDC8')
for i,(x,z) in enumerate(legs):
 col=['#C88076','#769E94','#7C95AC'][i]
 rod('marker body'+str(i),(x,.009,z),(x,.082,z),.0045,col,n=12)
 rod('felt tip'+str(i),(x,0,z),(x,.009,z),.001,'#445C68',n=10,r2=.003)
 rod('marker cap'+str(i),(x,.076,z),(x,.087,z),.005,col,n=12)
# Each craft stick is a shallow rectangular prism,flat in Y,rotated in XZ.
for i,((xa,za),(xb,zb)) in enumerate(zip(legs,legs[1:]+legs[:1])):
 a=np.array([xa,za]);bb=np.array([xb,zb]);d=bb-a;u=d/np.linalg.norm(d);v=np.array([-u[1],u[0]])*.006
 poly=Polygon([a-u*.006-v,bb+u*.006-v,bb+u*.006+v,a-u*.006+v]);pierced_prism('craft stick'+str(i),poly,.055+i*.002,.057+i*.002,'#C7A17C')
 # Tape binding crosses each leg and its adjacent stick.
 box('marker binding'+str(i),(xa,.059,za),(.011,.006,.016),'#DED2AB')
box('battery support',(0,.062,0),(.062,.008,.013),'#C7A17C')
box('battery pack',(0,.073,0),(.044,.014,.022),'#6B8586')
box('battery lid',(0,.0805,0),(.038,.001,.018),'#A8B5A7')
# Upright motor on a supported bracket. Shaft and offset mass rotate above all parts.
box('motor mounting rail',(0,.064,-.032),(.039,.010,.012),'#C7A17C')
box('motor bracket',(0,.0785,-.032),(.022,.019,.024),'#AD8A70')
rod('motor body',(0,.088,-.032),(0,.11,-.032),.01,'#A2B2B2',n=16)
rod('motor shaft',(0,.11,-.032),(0,.118,-.032),.0018,'#5F747A',n=10)
rod('offset arm',(0,.118,-.032),(.011,.118,-.032),.0022,'#8C7967',n=8)
ball('offset mass',(.011,.118,-.032),.004,'#C88B75')
# Both wires attach separate battery contacts to motor terminals.
for j,(x,col) in enumerate([(-.017,'#596E80'),(.017,'#B77869')]):
 box('battery contact'+str(j),(x,.0815,0),(.004,.002,.006),'#BAA88A')
 tube('motor wire'+str(j),[(x,.083,0),(x*1.25,.090,.008),(x*.8,.096,-.040),(x*.42,.093,-.040)],.001,col,n=6)
 ball('motor terminal'+str(j),(x*.42,.093,-.040),.0016,'#BAA88A')
# Painted traces lie on the paper. They do not act as physical supports.
for i,(cx,cz,col) in enumerate([(-.042,.026,'#C88076'),(.039,.025,'#769E94')]):
 pts=[(cx+.009*math.sin(t),.00012,cz+.018+.015*math.cos(t)) for t in np.linspace(0,math.pi*2.5,22)]
 pts.append((legs[i][0],.00012,legs[i][1]))
 tube('ink trace'+str(i),pts,.00035,col,n=4)
S['notes']=['Original triangular craft-stick chassis is supported by three equal marker legs with tips touching paper. Battery and upright motor have joined wooden supports; tape binds markers.','Two wires meet separate battery contacts and motor terminals. The offset arm/mass is above the motor and has clear rotational space,not intersecting the battery or frame. No human anatomy.','Exploratorium text informs generic offset-motor scribbling mechanics. The event lists craft sticks,motors and tape but does not promise this exact mechanism or kit.']

scene('mirrorwork-embroidery',(2,7,8))
box('cloth swatch',(0,.001,0),(.09,.002,.083),'#D6B38F')
lathe('mirror',[(0,.002),(.025,.002),(.025,.0045),(0,.0045)],'#B4D5D5',n=32)
# Twelve border loops pass over the disc perimeter and anchor outside it.
for i in range(12):
 t=i*2*math.pi/12;points=[]
 for rr,y,dt in [(.030,.0015,-.035),(.027,.005,-.025),(.0235,.0051,0),(.027,.005,.025),(.030,.0015,.035)]:points.append((rr*math.cos(t+dt),y,rr*math.sin(t+dt)))
 tube('anchored border stitch'+str(i),points,.00085,'#A7685E',n=6)
# Narrow reflective paint bands sit on the mirror,not floating above it.
for i,(x,z,w,d) in enumerate([(-.004,-.006,.027,.004),(.005,.006,.014,.003)]):
 box('mirror reflection'+str(i),(x,.0046,z),(w,.00012,d),'#EAF0D9')
tube('thread tail',[(.03,.002,0),(.038,.002,.009),(.042,.002,.022),(.034,.002,.029)],.0007,'#A7685E',n=6)
S['notes']=['Cloth swatch supports a thin closed reflective disc. Twelve embroidered loops cross its edge and anchor in the fabric outside it; a thread tail rests on the cloth.','Mirror highlight bands are graphic reflection cues on the disc surface,not a simulated reflected room. No needle or hand is depicted. Generic securing border is original,not a copied regional motif or exact stitch tutorial.']

scene('no-sew-quilted-ornament',(3,4,9))
R=.0381;c=np.array([0,R,0.])
# A soft core with cloth cover. Folded triangular layers conform to the sphere.
ellipsoid('fabric-covered core',c,(R,R,R),'#8DAAA1',n=32,rings=13)
def pos(theta,phi,rr,side):return c+np.array([rr*math.sin(theta)*math.cos(phi),rr*math.sin(theta)*math.sin(phi),side*rr*math.cos(theta)])
def patch(name,theta0,theta1,phi,spread,rr,col,side):
 # Barycentric samples normalized onto the spherical core. This keeps the cloth
 # outside the ball,unlike a planar triangular chord that cuts through it.
 abc=[pos(theta0,phi,1,side)-c,pos(theta1,phi-spread,1,side)-c,pos(theta1,phi+spread,1,side)-c]
 v=[];idx={};N=3
 for i in range(N+1):
  for j in range(N+1-i):
   q=(abc[0]*(N-i-j)+abc[1]*i+abc[2]*j)/N;q=q/np.linalg.norm(q);idx[i,j]=len(v);v.append(c+q*rr)
 f=[]
 for i in range(N):
  for j in range(N-i):
   f.append([idx[i,j],idx[i+1,j],idx[i,j+1]])
   if j<N-i-1:f.append([idx[i+1,j],idx[i+1,j+1],idx[i,j+1]])
 # Correct outward winding for each face and close the thin cloth perimeter.
 for face in f:
  a,bb,d=np.array(v)[face]
  if np.dot(np.cross(bb-a,d-a),(a+bb+d)/3-c)<0:face.reverse()
 count=len(v);v += [c+(np.array(q)-c)*(rr-.00016)/rr for q in v.copy()];ff=f+[[x+count for x in reversed(face)] for face in f]
 edges={}
 for face in f:
  for a,bb in zip(face,face[1:]+face[:1]):
   k=tuple(sorted([a,bb]));edges[k]=None if k in edges else (a,bb)
 for pair in edges.values():
  if pair is not None:a,bb=pair;ff.append([bb,a,a+count,bb+count])
 mesh(name,v,ff,col)
for side in [1,-1]:
 for layer,(t0,t1,col) in enumerate([(.08,.58,'#DCB17D'),(.36,.95,'#BE8174'),(.72,1.40,'#D6C59E')]):
  for i in range(8):patch('folded fabric'+str((side,layer,i)),t0,t1,i*math.pi/4,.36,R+.0004+layer*.0005,col,side)
 # Four visible pin heads secure the outer fabric near its broad edge.
 for i in range(4):
  q=pos(1.33,i*math.pi/2+.2,R+.0017,side);ball('sequin pin'+str((side,i)),q,.0009,'#D6D2B9')
# A narrow equatorial band covers the raw outer fabric edges.
verts=[];n=48
for z in [-.004,.004]:
 rr=math.sqrt((R+.0021)**2-z*z)
 for t in np.linspace(0,2*math.pi,n,endpoint=False):verts.append([rr*math.cos(t),R+rr*math.sin(t),z])
mesh('equator ribbon',verts,[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)],'#A87B6B');S['parts'][-1]['double_sided']=True
# The sphere rests at the lowest ribbon point,with all scene parts shifted up
# so that the bottom ribbon reaches the ground rather than passing through it.
loopbase=R+math.sqrt((R+.0021)**2-.008**2)
tube('attached ribbon loop',[(-.008,loopbase,0),(-.01,loopbase+.012,0),(0,loopbase+.020,0),(.01,loopbase+.012,0),(.008,loopbase,0)],.0017,'#A87B6B',n=6)
ymin=min(v[1] for p in S['parts'] for v in p['vertices'])
for p in S['parts']:p['vertices']=[[x,y-ymin,z] for x,y,z in p['vertices']]
S['notes']=['Original generic pinned fabric ornament. Triangular cloth layers conform to both sides of a covered soft sphere; each patch is a thin closed shell outside the core. Successive layers cover preceding bases.','Small pin heads secure outer fabric. A continuous equatorial ribbon covers raw perimeter edges and an attached ribbon loop closes at its upper edge. The lowest ribbon point touches ground.','Event describes a no-sew ball using folded fabric and pins. This generic radial arrangement is not a replica of the teacher’s heirloom pattern; no sewn seams or sewing needle are depicted.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
