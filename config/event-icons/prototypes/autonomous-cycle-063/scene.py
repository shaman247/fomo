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

# Original sign collection mounted to a neutral exhibition panel.
scene('signmaking-heritage-tour',(3,2,12))
box('display backing',(0,.54,-.10),(.86,1.08,.055),'#CFCEC1')
box('display foot',(0,.025,-.06),(.90,.05,.28),'#8FA3A4')
box('upper sign case',(0,.81,-.025),(.78,.30,.10),'#A96661')
box('upper sign face',(0,.81,.031),(.71,.24,.015),'#B47969')
# Plain outlined OPEN lettering; generic original storefront type, no business logo.
def lineletter(points,x,y,k=.11):
 for a,bb in zip(points,points[1:]):rod('raised sign lettering',(x+a[0]*k,y+a[1]*k,.047),(x+bb[0]*k,y+bb[1]*k,.047),.011,'#F0DFB8',8)
lineletter([(0,0),(0,1),(.7,1),(.7,0),(0,0)],-.27,.755)
lineletter([(0,0),(0,1),(.7,1),(.7,.5),(0,.5)],-.12,.755)
lineletter([(.7,0),(0,0),(0,1),(.7,1)],.03,.755);lineletter([(0,.5),(.55,.5)],.03,.755)
lineletter([(0,0),(0,1),(.7,0),(.7,1)],.18,.755)
# Second recovered-style arrow sign mounted via two short brackets.
for x in [-.22,.22]:box('lower sign bracket',(x,.40,-.015),(.025,.05,.15),'#8D9290')
extrude('oval sign',[(.33*math.cos(t),.40+.18*math.sin(t)) for t in np.linspace(0,2*math.pi,40,endpoint=False)],-.01,.065,'#639699')
extrude('raised star',[(r*math.cos(t),.40+r*math.sin(t)) for t,r in [(math.pi/2+i*math.pi/5,.105 if i%2==0 else .045) for i in range(10)]],.066,.075,'#E9D9AA')
box('museum caption',(0,.13,-.065),(.25,.07,.015),'#EFE7CF')
S['notes']=['Two original generic storefront signs attach to a freestanding display backing; backing contacts a broad foot. Raised OPEN lettering and oval star sign are original motifs, not copied collection objects. A small caption card indicates exhibition interpretation; no navigation arrow.']

scene('foraging',(4,5,11))
# Open produce bag with folded rim; bag and field guide rest on ground.
box('bag bottom',(-.17,.025,0),(.43,.05,.32),'#B6976C')
frame('open paper bag',(-.17,.255,0),.46,.35,.025,.46,'#C6A276')
frame('folded bag rim',(-.17,.49,0),.48,.37,.035,.05,'#D1B48B')
for a,bb in zip(np.linspace(0,math.pi,17),np.linspace(0,math.pi,17)[1:]):rod('paper bag handle',(-.17+.16*math.cos(a),.49+.18*math.sin(a),.16),(-.17+.16*math.cos(bb),.49+.18*math.sin(bb),.16),.009,'#A18664',8)
# Stems start inside the bag; leaves are generic, not edible-species identification.
for x,z,top in [(-.28,0,.83),(-.08,.04,.76),(-.20,-.06,.92)]:
 rod('plant stem',(x,.06,z),(x+.025,top,z),.009,'#6C8E63',10)
 for side,y in [(-1,top-.10),(1,top-.22)]:
  bx=x+.025*(y-.06)/(top-.06);tip=np.array([bx+side*.14,y+.12,z]);base=np.array([bx,y,z]);axis=tip-base;perp=np.array([-axis[1],axis[0],0]);perp/=np.linalg.norm(perp);outline=[base+axis*t+perp*.037*math.sin(math.pi*t) for t in np.linspace(0,1,9)]+[base+axis*t-perp*.037*math.sin(math.pi*t) for t in np.linspace(1,0,9)];panel('generic gathered leaf',outline,'#90A376')
# Closed illustrated field guide alongside the bag, angled in plan.
box('field guide cover',(.24,.024,.17),(.29,.048,.40),'#70989A')
box('guide pages',(.24,.053,.17),(.265,.014,.37),'#EEE6CB')
box('guide top cover',(.24,.065,.17),(.29,.012,.40),'#70989A')
flat_extrude('leaf on guide',[(.24,.035),(.155,.145),(.17,.24),(.24,.29),(.30,.20),(.31,.11)],.072,.075,'#D4DEB6')
rod('guide leaf vein',(.24,.077,.05),(.24,.077,.27),.004,'#8DAE91',8)
S['notes']=['Open paper bag rests on bottom and has four continuous walls/folded rim. Stems extend into bag rather than float above it. Generic leaves and a closed field guide indicate guided foraging without asserting a species, edibility, medicinal effect or actual kit. Primary asks participants to bring collecting bags.']

scene('candle-making',(4,5,11))
# A grounded pouring vessel, unlit finished candle and raw wax illustrate making.
lathe('pouring pitcher',[(0,0),(.17,0),(.18,.04),(.18,.47),(.16,.48),(.15,.06),(0,.06)],'#9FAEB0',32)
# translate the vessel left/back
for part in S['parts']:part['vertices']=[[x-.22,y,z-.05] for x,y,z in part['vertices']]
# Open attached handle, no hand or unsupported pour.
for a,bb in [((-.39,.38,-.05),(-.51,.38,-.05)),((-.51,.38,-.05),(-.51,.14,-.05)),((-.51,.14,-.05),(-.39,.14,-.05))]:rod('pitcher handle',a,bb,.018,'#8C9EA2',12)
panel('pitcher spout',[(-.13,.46,.105),(-.04,.47,.18),(-.06,.48,.065)],'#C2CBCA')
rod('unlit pillar',(.23,0,.02),(.23,.34,.02),.145,'#E6D4A4',32)
rod('candle wick',(.23,.34,.02),(.23,.39,.02),.012,'#746C60',12)
box('wax slab',(.18,.03,.32),(.29,.06,.17),'#E8DDBD')
# Small spool of wick rests flat beside candle.
rod('wick spool core',(-.18,.022,.31),(-.18,.115,.31),.044,'#D7C5A4',20)
for y in [.014,.121]:rod('wick spool flange',(-.18,y-.014,.31),(-.18,y+.014,.31),.075,'#B79777',24)
rod('wick spool winding',(-.18,.031,.31),(-.18,.10,.31),.063,'#ECE2CA',24)
S['notes']=['Original grounded hollow pouring pitcher with connected handle/spout, unlit pillar with centered wick, raw wax slab and wick spool. No floating pouring action, flame, recipe, exact kit, wax type or event method promised. Container/mold/wick relationships use manufacturer structural text.']

scene('monotype',(4,8,10))
# Smooth Plexiglas plate and a pulled impression, no relief carved image.
box('smooth printing plate',(-.21,.025,-.11),(.47,.05,.61),'#A9BDBD')
box('paper impression',(.25,.005,.17),(.42,.01,.56),'#F0E8D2')
# Same asymmetric abstract motif reversed between plate and paper in world x.
def motif(cx,cz,y,flip):
 flat_extrude('painted broad mark',[(cx+flip*x,cz+z) for x,z in [(-.13,-.16),(.04,-.12),(.13,.04),(.07,.16),(-.06,.13),(-.12,.02)]],y,y+.002,'#87A6A0')
 flat_extrude('second painted mark',[(cx+flip*x,cz+z) for x,z in [(-.11,-.14),(-.03,-.15),(.10,.08),(.05,.13)]],y+.003,y+.005,'#C59C82')
motif(-.21,-.11,.051,1);motif(.25,.17,.011,-1)
# Brush rests next to smooth plate on its handle and flat bristles.
rod('brush handle',(-.54,.023,-.30),(-.54,.023,.07),.021,'#C4A37D',16)
rod('brush ferrule',(-.54,.023,.055),(-.54,.023,.14),.024,'#91A2A7',16)
box('flat paint bristles',(-.54,.017,.18),(.058,.034,.08),'#5F8580')
S['notes']=['Original smooth rigid plate painted directly, with a separate mirrored paper impression. Brush rests alongside plate; no carved relief or gel plate assumed. Primary confirms Plexiglas and press-assisted transfer; this depicts the painted plate and result, not an invented press model or complete transfer sequence.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
