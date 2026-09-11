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

# Original small craft scenes. Geometries are illustrative models, not promised workshop dimensions.
scene('decorative-ceramic-tiles',(2,2,15))
box('square clay tile',(0,.45,0),(.85,.85,.055),'#F1DDC5')
# Drawn surface decoration is attached at the front plane, not a raised glaze claim.
for points,col in [([(-.34,.11),(.34,.11),(.34,.79),(-.34,.79)],'#548EAA'),([(-.28,.17),(.28,.17),(.28,.73),(-.28,.73)],'#F4E9D6')]:
 panel('painted border',[(x,y,.028) for x,y in points],col);S['parts'][-1]['flat_paint']=True
# An original four-petal geometry, deliberately not a specific regional ceramic pattern.
for angle in [0,math.pi/2,math.pi,3*math.pi/2]:
 outline=[]
 for t in np.linspace(0,2*math.pi,24,endpoint=False):
  x=.09*math.cos(t);y=.145+.12*math.sin(t)
  outline.append((x*math.cos(angle)-y*math.sin(angle),.45+x*math.sin(angle)+y*math.cos(angle)))
 panel('painted petal',[(x,y,.029) for x,y in outline],'#DB9570');S['parts'][-1]['flat_paint']=True
rod('painted flower center',(0,.45,.029),(0,.45,.030),.065,'#64A4A0',24);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(tile_width=.85,tile_height=.85,thickness=.055,paint_front=.030)
S['notes']=['Flat decorative square tile; marks attached to front, four broad petals original rather than a specific traditional motif. No firing, glazing, supplied color or exact project-size claim.']
scene('diorama',(3.0,2.3,8.5))
# Open-front tabletop box: continuous floor, back and side walls with shared boundaries.
box('base',(0,.035,0),(1.1,.07,.58),'#CE986E')
box('back',(0,.45,-.265),(1.1,.9,.05),'#88BFC5')
box('left wall',(-.525,.45,0),(.05,.9,.58),'#DAAD80')
box('right wall',(.525,.45,0),(.05,.9,.58),'#DAAD80')
box('green scene floor',(0,.076,0),(1.0,.012,.48),'#95B26F')
# Two planted paper trees with roots meeting the floor, separated in depth and height.
for x,y,z,r,col in [(-.24,.66,-.14,.21,'#5E9470'),(.22,.45,.12,.18,'#79AD6B')]:
 box('paper tree trunk',(x,(y+.082)/2,z),(.045,y-.082,.018),'#A47655')
 outline=[(x+r*math.cos(t),y+r*math.sin(t)) for t in np.linspace(0,2*math.pi,32,endpoint=False)]
 extrude('flat tree canopy',outline,z-.015,z+.015,col)
# Sun fixed to the painted rear panel; illustrative miniature habitat, no species claim.
rod('painted sun',(.28,.72,-.239),(.28,.72,-.238),.085,'#F4CB71',24);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(box_width=1.1,box_depth=.58,box_height=.9,ground=.082,tree_depths=[-.14,.12],tree_roots=.082)
S['notes']=['Open-front three-sided miniature box scene; side walls, back and base share boundaries. Trees rooted on floor with separated depth planes. Stylized vegetation is not a promised species or exact supplied craft material.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
