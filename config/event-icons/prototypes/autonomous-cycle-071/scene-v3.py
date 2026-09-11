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


scene('paper-flowers',(3,8,7))
# Three original ruffled paper sheets pinch into one tied centre. The low knot
# and stem rest on a common table plane. This is not an instructional pattern.
for layer,(R,h,col) in enumerate([(.050,.014,'#D9928F'),(.038,.025,'#ECAA9A'),(.023,.034,'#E9BB80')]):
 n=48;v=[]
 for j,rr in enumerate([.003,R*.48,R]):
  for k in range(n):
   t=2*math.pi*k/n;pleat=(1-math.cos(12*t))/2
   r=rr*(1+.06*math.cos(6*t)) if j==2 else rr
   y=.005+layer*.001 if j==0 else (.008+(h-.008)*(j/2)+.0025*pleat*j)
   v.append([r*math.cos(t)-.024,y,r*math.sin(t)-.026])
 f=[]
 for j in range(2):
  for k in range(n):
   a=j*n+k;bb=j*n+(k+1)%n;c=(j+1)*n+(k+1)%n;d=(j+1)*n+k
   f.extend([[a,c,bb],[a,d,c]])
 mesh('ruffled tissue layer'+str(layer),v,[list(reversed(face)) for face in f],col);S['parts'][-1]['double_sided']=True
# Tied centre and trailing craft-wire stem; joins rather than floating petals.
tube('centre tie',[(-.027,.004,-.026),(-.024,.009,-.029),(-.021,.010,-.026),(-.024,.004,-.023),(-.027,.004,-.026)],.0014,'#709785',n=8)
tube('stem',[(-.024,.003,-.026),(-.015,.0025,.001),(.004,.0025,.030),(.015,.0025,.072)],.0025,'#709785',n=10)
# Separate accordion folded strip shows the material/process; edges contact table.
n=9;v=[]
for z in [-.033,.032]:
 for j in range(n):v.append([.044+j*.0038,.001+(j%2)*.006,z])
f=[[j,j+1,n+j+1,n+j] for j in range(n-1)]
mesh('folded tissue strip',v,[list(reversed(face)) for face in f],'#E6B58B');S['parts'][-1]['double_sided']=True
S['notes']=['Original three-layer ruffled paper bloom with centre tie,joined stem and a separate accordion-folded tissue strip. Sheets meet at the tied centre. Stem and knot support the bloom on the table; no levitating flower.','Layer shaping is a simplified mesh abstraction,not an exact cutting/folding recipe or promised class design. The maker tutorial text informed a centre tie,stacked layers and accordion material; no external pictures traced.']

scene('lantern-making',(3,4,8))
# Eight-sided hollow lantern with tapered,closed end panels. The construction
# is a generic craft-frame study rather than an exact kit or traditional motif.
n=8;angles=[math.pi/8+2*math.pi*i/n for i in range(n)]
profile=[(.025,.0025),(.040,.020),(.040,.075),(.025,.095)]
for level,((ra,ya),(rb,yb)) in enumerate(zip(profile,profile[1:])):
 for i,t in enumerate(angles):
  u=angles[(i+1)%n];v=[[ra*math.cos(t),ya,ra*math.sin(t)],[ra*math.cos(u),ya,ra*math.sin(u)],[rb*math.cos(u),yb,rb*math.sin(u)],[rb*math.cos(t),yb,rb*math.sin(t)]]
  panel('colored film facet',v,'#D9AA7C' if i%2==0 else '#CDB592')
for ra,y in profile:
 points=[[ra*math.cos(t),y,ra*math.sin(t)] for t in angles];tube('octagonal joined ring',points+[points[0]],.0025,'#9F7A64',n=8)
for t in angles:
 tube('connected craft rib',[[ra*math.cos(t),y,ra*math.sin(t)] for ra,y in profile],.002,'#9F7A64',n=8)
# Flat closure sheets seal the upper and lower openings; lantern cannot read
# as an open shopping bag. All geometry is fully attached to its perimeter.
for ra,y in [profile[0],profile[-1]]:panel('closure panel',[[ra*math.cos(t),y,ra*math.sin(t)] for t in angles],'#C29E79')
pts=[[.020*math.cos(t),.095+.023*math.sin(t),0] for t in [i*math.pi/20 for i in range(21)]]
tube('attached carry loop',pts,.002,'#9F7A64',n=8)
rod('battery light base',(0,.003,0),(0,.008,0),.008,'#DDD1B3',n=12)
ball('small light dome',(0,.011,0),.005,'#F2D9A1')
star=[]
for i in range(10):
 t=math.pi/2+i*math.pi/5;rr=.020 if i%2==0 else .009
 star.append([rr*math.cos(t),.047+rr*math.sin(t),.040*math.cos(math.pi/8)+.0001])
panel('paper star on front film',star,'#F8DFA3')
flat_extrude('spare film sheet',[(.050,-.015),(.075,-.015),(.075,.022),(.050,.022)],0,.0005,'#E5BD8B')
S['notes']=['Metres; original hollow octagonal craft lantern with tapered closed ends,eight continuous ribs,four joined perimeter rings and a two-ended carry loop. Film panels share the frame edges; bottom sits on a common ground plane with the spare sheet.','Colored film uses flat opaque shading for pictogram clarity; battery mini light is enclosed. Generic star decoration is attached to the front panel. No candle,flame,flying release,cultural design copy or exact workshop kit claimed.','Initial open cuboid read too much like a bag. Replaced it with a fully closed tapered octagonal lantern body in the authoritative3D source; review all six views and native sizes again.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
