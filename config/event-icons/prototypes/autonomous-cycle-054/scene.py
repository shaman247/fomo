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


from shapely.geometry import box as shape_box, Point
from shapely.geometry.polygon import orient
scene('fused-glass',(2,2,12))
def rounded(name,x,y,w,h,z0,z1,r,col):
 g=shape_box(x-w/2+r,y-h/2+r,x+w/2-r,y+h/2-r).buffer(r,quad_segs=8)
 extrude(name,list(orient(g,sign=1).exterior.coords)[:-1],z0,z1,col)
# Illustrative shallow fused glass cabochon and two separate pieces of raw colored glass.
rounded('fused glass base',-.10,.43,.66,.76,-.035,.035,.12,'#547F96')
# Color regions attach to the front; they are material patches, not raised beads.
from shapely.affinity import scale, translate
for shape,col in [(translate(scale(Point(0,0).buffer(.23,quad_segs=12),yfact=.65),xoff=-.09,yoff=.58),'#77ADA6'),(translate(scale(Point(0,0).buffer(.23,quad_segs=12),yfact=.55),xoff=-.08,yoff=.28),'#D59A78')]:
 panel('embedded glass patch',[(x,y,.036) for x,y in list(orient(shape,sign=1).exterior.coords)[:-1]],col);S['parts'][-1]['flat_paint']=True
rounded('small amber glass',.38,.79,.25,.25,-.03,.015,.015,'#E6B568')
rounded('small teal glass',.43,.40,.23,.24,-.03,.015,.015,'#67A49B')
# Soft short highlight strokes belong to the front of the large glass face.
# Broad attached highlight arc follows the upper-left rounded surface.
points=[(-.34,.53,.039),(-.34,.66,.039),(-.32,.70,.039),(-.27,.73,.039),(-.18,.73,.039)]
for a,bb in zip(points,points[1:]):
 rod('surface glint',a,bb,.016,'#D0E4DF',12);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(main_width=.66,main_height=.76,thickness=.07,front=.035,patches=.036,highlight_front=.039)
S['notes']=['Original illustrative fused-glass material sample and loose colored pieces. Source photo shows rounded multicolor fused jewelry and loose glass. No copied design, bracelet clasp, kiln operation or on-site firing claim. Patches meet the surface; separated squares are diagrammed supplies rather than floating physical supports.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
