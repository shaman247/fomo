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

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat

from shapely.geometry import Polygon,Point
from shapely.ops import triangulate
scene('focaccia',(3,7,9))
# A low rectangular bread, with real depressions in its upper surface.
outline=rounded_outline(.32,.23,.030,10);top=.038
flat_extrude('bread side and underside',outline,0,top,'#D4A15F');S['parts'][-1]['faces'].pop(1)
centers=[(-.115,-.070),(-.035,-.073),(.045,-.073),(.118,-.060),(-.105,.005),(-.010,.010),(.103,.020),(-.100,.073),(.050,.079)]
shape=Polygon(outline);holes=[Point(x,z).buffer(.008,resolution=8) for x,z in centers]
for hole in holes:shape=shape.difference(hole)
verts=[];faces=[]
for t in triangulate(shape):
 if not shape.covers(t.representative_point()):continue
 coords=list(t.exterior.coords)[:3];start=len(verts);verts += [[x,top,z] for x,z in coords];faces.append([start+2,start+1,start])
mesh('bread top',verts,faces,'#E2BB79');S['parts'][-1]['flat_paint']=True
for x,z in centers:
 n=32;v=[[x,top-.006,z]]+[[x+.008*math.cos(a),top,z+.008*math.sin(a)] for a in np.linspace(0,2*math.pi,n,endpoint=False)];fs=[[0,(i+1)%n+1,i+1] for i in range(n)];mesh('dimple',v,fs,'#C8985D')
# Original sparse arrangement of tomato halves and a herb sprig, not the source’s floral composition.
for x,z in [(-.068,-.015),(.055,-.030),(.104,.060)]:
 rod('tomato cut half',(x,top,z),(x,top+.009,z),.021,'#C96C5B',n=24)
 rod('tomato flesh',(x,top+.0091,z),(x,top+.0095,z),.015,'#E08C65',n=20)
 for off in [-.006,.006]:oval('tomato seed',(x+off,top+.010,z),.002,[.65,.4,1],'#E6BB7E',True)
# Thin herb stem is in contact with the bread surface.
pts=[(-.070,top+.002,.073),(-.035,top+.002,.048),(.005,top+.002,.033),(.040,top+.002,.010)]
for a,bb in zip(pts,pts[1:]):rod('herb stem',a,bb,.002,'#70916A',n=8)
for x,z,sgn in [(-.050,.059,1),(-.020,.042,-1),(.010,.030,1),(.026,.018,-1)]:
 dx,dz=.024*sgn,.025;poly=[(x,z),(x+dx*.1,z+dz*.7),(x+dx,z+dz),(x+dx*.85,z+dz*.25)];flat_extrude('herb leaf',poly,top,top+.003,'#6E946E')
# Give the baked loaf a gently raised center. Apply the same height field to
# surface details so every topping remains attached to the bread.
for p in S['parts']:
 for v in p['vertices']:
  if v[1]>.026:
   v[1]+=.010*max(0,1-(v[0]/.16)**4)*max(0,1-(v[2]/.115)**4)
S['measurements']=dict(width=.32,depth=.23,rim_height=top,max_center_height=top+.010,base_y=0,dimple_count=len(centers),dimple_depth=.006,tomato_halves=3)
S['notes']=['Original representative baked focaccia, informed by the provider’s edible-decorated dough photograph and explicit recipe subject. Bread is a low rounded rectangle with a closed underside, connected sides and upper surface with actual shallow dimple bowls. Tomato halves and herb leaves sit on the top surface. Arrangement is original and does not promise exact toppings, recipe or dietary suitability.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');(Path('.scratch/icon-cycles-20260909/cycle-037')/'geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
