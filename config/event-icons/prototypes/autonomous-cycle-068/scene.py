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


scene('construction-brick-robotics',(4,5,8))
box('chassis',(0,.135,0),(.19,.06,.25),teal)
# Driven wheels share axle level; rear caster supplies the third ground contact.
for side in [-1,1]:
 x=side*.108
 box('motor case',(side*.075,.08,.055),(.055,.07,.085),cream)
 rod('axle',(side*.075,.08,.055),(side*.13,.08,.055),.009,steel)
 rod('tire',(side*.105,.08,.055),(side*.142,.08,.055),.08,dark,n=32)
 rod('wheel hub',(side*.142,.08,.055),(side*.144,.08,.055),.047,lightwood,n=24)
 rod('axle cap',(side*.144,.08,.055),(side*.146,.08,.055),.011,steel,n=12)
ball('rear caster',(0,.025,-.1),.025,dark)
rod('caster support',(0,.025,-.1),(0,.11,-.1),.009,steel)
box('controller',(0,.192,-.03),(.15,.054,.15),lightwood)
for x in [-.05,0,.05]:
 for z in [-.075,-.025,.025]:rod('interlocking stud',(x,.219,z),(x,.228,z),.012,lightwood,n=12)
box('sensor bracket',(0,.18,.087),(.095,.03,.035),teal)
box('distance sensor',(0,.215,.106),(.12,.045,.04),cream)
for x in [-.032,.032]:
 rod('sensor port',(x,.217,.126),(x,.217,.129),.016,dark,n=20)
 rod('sensor lens',(x,.217,.13),(x,.217,.131),.009,ink,n=16)
tube('sensor cable',[(-.064,.2,-.05),(-.093,.205,-.052),(-.102,.232,-.01),(-.085,.248,.074),(-.061,.227,.098)],.0045,dark)
S['notes']=['Metres; two driven tires radius.08 and rear caster radius.025 touch y0. Axles meet motor cases, which overlap supported chassis; studded controller and sensor bracket seat on it.','Original generic construction-brick robot; not a LEGO kit replica. Sensor is connected by continuous cable. No extra arm or exact class build promised.']

scene('wire-wrapped-jewelry',(2,9,6))
box('work mat',(0,.005,0),(.39,.01,.35),'#C4B399')
# One pierced oval bead, lying with its bore along Z. Wire passes through it,
# forms a bail and wraps its own stem. A second connected overwrap returns
# over the bead to the lower stem, rather than floating independent rings.
cx=-.08;cy=.065
profile=[]
for z in np.linspace(-.095,.095,17):profile.append((.007+.048*math.sqrt(max(0,1-(z/.095)**2)),z))
profile += [(.005,.095),(.005,-.095),profile[0]]
lathe('pierced oval bead',profile,teal,n=32)
p=S['parts'][-1];p['vertices']=[[x+cx,z+cy,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
# Bare headpin stem exits bead, loop above it, and three close tail turns.
pts=[(cx,cy,-.112),(cx,cy,-.095),(cx,cy,.095),(cx,cy,.117)]
for t in np.linspace(-math.pi/2,3*math.pi/2,25)[1:]:pts.append((cx+.02*math.cos(t),cy,.137+.02*math.sin(t)))
pts += [(cx+.007,cy,.115)]
for t in np.linspace(0,6*math.pi,49):pts.append((cx+.007*math.cos(t),cy+.007*math.sin(t),.115-.018*t/(6*math.pi)))
# Downward helix hugs the bead surface (illustrative bead overwrap).
for t in np.linspace(0,4*math.pi,65):
 z=.095-.19*t/(4*math.pi);r=.011+.048*math.sqrt(max(0,1-(z/.095)**2));pts.append((cx+r*math.cos(t),cy+r*math.sin(t),z))
pts += [(cx+.006,cy,-.11),(cx,cy,-.112)]
tube('continuous copper wire',pts,.0035,'#D69B60',n=8)
# Seat bead and its connected wire together on the mat.
parts=[p for p in S['parts'] if p['name'] in ['pierced oval bead','continuous copper wire']]
shift=.01-min(v[1] for p in parts for v in p['vertices'])
for p in parts:p['vertices']=[[x,y+shift,z] for x,y,z in p['vertices']]
# Small round-nose pliers: crossed metal arms share a central rivet.
for side in [-1,1]:
 pts=[(.105+side*.007,.024,.02),(.105+side*.033,.024,-.055),(.105+side*.05,.024,-.12)]
 tube('pliers handle metal',pts,.007,steel,n=10)
 tube('handle grip',pts[1:],.014,ink,n=12)
 rod('round jaw',(.105+side*.007,.025,.02),(.105+side*.014,.025,.10),.009,steel,n=12,r2=.003)
rod('pivot rivet',(.105,.021,.015),(.105,.037,.015),.017,dark,n=16)
S['notes']=['Metres; pierced bead rests with lowest body/wire near mat surface. Headpin passes through bore, forms bail, coils at stem and continues into bead overwrap; no separate floating rings.','Original illustrative bead-and-wire piece with round-nose pliers. Not a claimed class project, material recipe or step-by-step executable wire pattern.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
