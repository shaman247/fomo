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

scene('takoyaki',(3,7,11))
# Shallow paper food boat with four supported balls, not skewered dango.
box('food boat bottom',(0,.018,0),(.46,.035,.36),'#C6B58D')
for side in [-1,1]:
 panel('long folded boat side',[(-.24,.035,side*.18),(.24,.035,side*.18),(.27,.085,side*.22),(-.27,.085,side*.22)],'#E6D6B3')
 panel('boat end',[(side*.24,.035,-.18),(side*.24,.035,.18),(side*.27,.085,.22),(side*.27,.085,-.22)],'#B9A481')
r=.108
for x in [-.12,.12]:
 for z in [-.12,.12]:
  c=np.array([x,.145,z]);ball('round takoyaki batter',c,r,'#D3A168');S['parts'][-1]['flat_paint']=True
  # Sauced upper cap follows spherical surface; no detached discs.
  n=12;verts=[c+np.array([r*math.cos(t)*math.cos(a),r*math.sin(t)+.002,r*math.cos(t)*math.sin(a)]) for t in np.linspace(.45,math.pi/2,3) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
  mesh('brown sauce',verts,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(2) for i in range(n)],'#9D7258')
  # Two broad pale drizzle ribbons, geometric surface points keep toppings attached.
  for dz in [-.028,.031]:
   xs=np.linspace(-.075,.075,5);vs=[]
   for off in [-.008,.008]:
    for dx in xs:
     zz=dz+off+.009*math.sin(dx*32);yy=math.sqrt(max(0,r*r-dx*dx-zz*zz));vs.append(c+np.array([dx,yy+.004,zz]))
   mesh('pale drizzle',vs,[[i,i+1,5+i+1,5+i] for i in range(4)],'#EAD9B2');S['parts'][-1]['double_sided']=True;S['parts'][-1]['flat_paint']=True
  for dx,dz in [(-.036,-.002),(.033,.004)]:
   yy=math.sqrt(r*r-dx*dx-dz*dz)
   panel('green garnish',[c+[dx-.009,yy+.006,dz-.011],c+[dx+.009,yy+.006,dz-.005],c+[dx+.003,yy+.006,dz+.010]],'#819470')
S['notes']=['Original generic boat serving of four takoyaki. Golden spherical batter and sauce follow Otafuku primary culinary descriptions. Each ball radius0.108 rests at bottomheight0.037; centerheight0.145. Balls spaced0.24apart with radius0.108avoid mutual penetration. Sauce and drizzle follow sphere surfaces. Four pieces, pale drizzle and garnish are illustrative, not guaranteed YokoNipsportion or recipe; no visible ingredient cross-section or food-safety claim.']

scene('radio-theater',(3,3,12))
# Generic tabletop radio receiver, with theatre speech emblem added as a flat semantic diagram.
box('radio cabinet',(0,.28,0),(.75,.50,.23),'#AE9C88')
for x in [-.27,.27]:box('cabinet foot',(x,.02,0),(.10,.05,.15),'#7D877F')
box('front face',(0,.28,.121),(.70,.43,.016),'#CCBA98')
box('speaker cloth',(-.15,.28,.132),(.32,.32,.011),'#809694')
for y in [.17,.225,.28,.335,.39]:box('speaker grille slat',(-.15,y,.143),(.30,.016,.013),'#B5C0AE')
box('tuning window',(.205,.37,.14),(.24,.065,.015),'#728994')
box('tuning indicator',(.22,.37,.151),(.012,.055,.008),'#CFA991')
for x in [.14,.265]:rod('radio control knob',(x,.205,.135),(x,.205,.163),.035,'#8B9D99',16)
S['notes']=['Original simplified tabletop receiver with cabinet, two supported feet, front speaker grille, tuning window and two knobs. This is a conventional receiver symbol, not a depiction of venue production equipment or a claimed historical radio model. Flat theatre-mask speech emblem supplies fictional performance meaning; no actual radio broadcast is promised.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
