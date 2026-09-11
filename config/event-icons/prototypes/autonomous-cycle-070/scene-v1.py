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

scene('jewelry-wax-carving',(3,8,6))
# Original hollowed oval pendant with a smaller chain hole; no silver model.
outer=translate(scale(Point(0,0).buffer(1,resolution=32),.029,.040),xoff=-.027)
window=translate(scale(Point(0,0).buffer(1,resolution=24),.013,.018),xoff=-.03,yoff=-.006)
bail=Point(-.027,.029).buffer(.0035,resolution=12)
pierced_prism('carved wax pendant',outer.difference(window.union(bail)),0,.006,'#709D89')
# Sharp steel tool seated in beechwood handle; handle underside touches table.
rod('wood handle',(.032,.00475,-.070),(.032,.00475,.008),.00475,wood,n=20)
rod('steel shaft',(.032,.00475,.005),(.032,.00475,.048),.0017,steel,n=12)
flat_extrude('carving blade',[(.0285,.045),(.0355,.045),(.034,.064),(.032,.072),(.029,.062)],.0035,.0055,steel)
for i,(x,z,a) in enumerate([(-.003,-.053,.7),(-.021,-.051,-.8),(.004,-.033,.3)]):
 poly=[(x+math.cos(t+a)*.006,z+math.sin(t+a)*.0024) for t in np.linspace(0,2*math.pi,8,endpoint=False)]
 flat_extrude('wax shaving'+str(i),poly,0,.0015,'#88B39A')
S['notes']=['Metres; original wax pendant55–58mmwide80mmlong,6mmthick,one large negative-spacewindow and a separate small chain hole. All openings continue through the model.','Beechwoodhandle9.5mmdiameter,steelshaftandbladephysicallyjoined; handle rests ontable andsupports light cantileveredblade. Waxshavingsrestontable. Noonsitecastingoractualworkshopdesignpromised.']

scene('coffee-cupping',(3,7,8))
profile=[(0,0),(.027,0),(.03,.003),(.041,.056),(.04,.06),(.037,.06),(.036,.055),(.026,.009),(0,.009)]
for j,(x,z) in enumerate([(-.049,-.022),(.047,-.042)]):
 lathe('cupping bowl'+str(j),profile,cream,n=40);p=S['parts'][-1];p['vertices']=[[a+x,y,c+z] for a,y,c in p['vertices']]
 rod('coffee sample'+str(j),(x,.047,z),(x,.048,z),.03426,'#876754' if j==0 else '#97715A',n=40,r2=.0344783)
# Deep-bowled spoon, joined to one curved handle, rests on its bowl bottom
# and handle tip. It is not inserted at an impossible angle through a cup.
lathe('spoon bowl',[(0,0),(.007,.001),(.014,.005),(.017,.010),(.017,.012),(.0155,.012),(.012,.007),(.005,.003),(0,.003)],steel,n=32)
p=S['parts'][-1];p['vertices']=[[x-.055,y,z*1.2+.079] for x,y,z in p['vertices']]
tube('spoon handle',[(-.039,.011,.079),(-.029,.012,.079),(-.010,.010,.079),(.04,.006,.079),(.07,.0025,.079)],.0025,steel,n=10)
S['notes']=['Metres; two identical hollow vessels rest ontable,3mmrims,supportedbases,coffee surfaces below rims and insidewalls. Bowls are an original generic cupping reference,notanexactbrand or certifiedcapacity.','Concave spoon has solid outer/inner bowl surfaces, joins one curved handle and rests onbowlbottom/handleend. No humans,shared-spoonpractice or proceduralrecipe depicted.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
