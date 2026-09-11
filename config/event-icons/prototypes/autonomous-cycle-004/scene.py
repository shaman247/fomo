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
 x,y,z=c;n=24;rings=12;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
# A pair of hand-sized earth balls on a common support plane, with shallow
# embedded seed shapes. A small sprout represents one germinated ball.
scene('seed-balls',(3,4,10))
for i,(x,z,r) in enumerate([(-.19,.02,.23),(.25,-.02,.18)]):
 ball('earth ball '+str(i),(x,r,z),r,'#B5865D' if i==0 else '#A97952')
 # Ellipsoidal seeds lie on the near-upper hemisphere, with their inner half embedded.
 for j,(dx,dz) in enumerate([(-.085,.135),(.04,.175)]):
  dx*=r/.23;dz*=r/.23;y=r+math.sqrt(max(0,r*r-dx*dx-dz*dz))
  before=len(S['parts']);ball('seed '+str(i)+' '+str(j),(x+dx,y,z+dz),.048,'#EED3A0')
  for part in S['parts'][before:]:part['vertices']=[[a,y+(yy-y)*.38,zz] for a,yy,zz in part['vertices']]
rod('sprout stem',(-.19,.44,.02),(-.19,.76,.02),.014,'#548A68',10)
# Flat leaves are authoritative planar surfaces connected at their bases to stem.
for sign in [-1,1]:
 panel('leaf '+str(sign),[(-.19,.66,.02),(-.19+sign*.13,.82,.025),(-.19+sign*.23,.80,.025),(-.19+sign*.20,.69,.025),(-.19+sign*.09,.63,.02)],'#77AD77' if sign<0 else '#639B6C')
S['notes']=['Both balls touch y=0; stylized visible seeds are partly embedded, and the sprout joins the larger ball. Sprout is an outcome cue, not a promise of pre-germinated materials.']
scene('vermicomposting',(3,8,10))
# Opaque open demonstration bin; lid is removed for inspection.
box('base',(0,.055,0),(.90,.11,.64),'#577E80')
frame('bin walls',(0,.265,0),.90,.64,.055,.42,'#5F9690')
box('soil bedding',(0,.265,0),(.79,.32,.53),'#826750')
frame('top rim',(0,.49,0),.96,.70,.07,.07,'#7CB0A2')
# One exaggerated earthworm rests on bedding y=.425; joined tube segments and
# rounded joints share a centerline. No eyes, legs or disconnected rings.
pts=[(-.25,.47,.07),(-.17,.47,.14),(-.06,.47,.14),(.01,.47,.07),(-.025,.47,-.015),(.02,.47,-.10),(.14,.47,-.13),(.24,.47,-.07)]
for i,(a,bb) in enumerate(zip(pts,pts[1:])):rod('worm tube'+str(i),a,bb,.045,'#DFA09A',12)
for i,c in enumerate(pts):ball('worm joint'+str(i),c,.045,'#DFA09A')
# Flat food/bedding pieces share the bedding support plane; no enormous fruit.
panel('leaf scrap',[(-.32,.43,-.13),(-.24,.43,-.22),(-.10,.43,-.22),(-.18,.43,-.11)],'#88AE75')
for x in [-.27,-.09,.09,.27]:
 # Ventilation marks on the visible front wall are surface emblems, not holes.
 panel('vent mark',[(x-.018,.38,.323),(x+.018,.38,.323),(x+.018,.35,.323),(x-.018,.35,.323)],'#3D6466')
S['notes']=['Bin bottom rests at y=0. Lid is omitted for the open demonstration view; this does not depict long-term storage. Worm underside touches bedding y=.425; rounded joints overlap adjacent tube ends. Rim surrounds the open top. Food and bedding are illustrative, not a complete bin-building diagram; vent marks do not claim exact working airflow.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created two garden/compost scenes')
