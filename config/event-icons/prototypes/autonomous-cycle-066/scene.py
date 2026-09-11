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

def bezier_path(start,segments,n=14):
 out=[np.array(start,float)];p=out[0]
 for a,b,c in segments:
  a,b,c=map(lambda x:np.array(x,float),(a,b,c))
  out.extend((1-t)**3*p+3*(1-t)**2*t*a+3*(1-t)*t*t*b+t**3*c for t in np.linspace(0,1,n+1)[1:]);p=c
 return np.array(out).tolist()

def guitar(strings=7):
 # Original single-cutaway archtop: 0.406 m wide, 0.064 m deep, 0.635 m scale.
 # Smooth outline based on construction, not traced product coordinates.
 outline=bezier_path([0,0],[([-.18,0],[-.225,.07],[-.197,.19]),([-.18,.26],[-.112,.265],[-.113,.31]),([-.114,.35],[-.165,.40],[-.145,.46]),([-.12,.52],[-.04,.52],[0,.51]),([.025,.51],[.030,.433],[.075,.438]),([.11,.441],[.113,.505],[.155,.463]),([.20,.405],[.11,.35],[.113,.30]),([.115,.26],[.20,.22],[.204,.14]),([.211,.045],[.15,0],[0,0])])
 extrude('guitar body',outline,-.032,.032,'#B47C5C')
 inset=[[x*.95,.25+(y-.25)*.96] for x,y in outline];extrude('bound guitar top',inset,.032,.036,'#D9A778')
 extrude('continuous guitar neck',[[-.034,.43],[.034,.43],[.027,.91],[-.027,.91]],-.01,.037,'#90694F')
 extrude('fingerboard',[[-.033,.43],[.033,.43],[.027,.91],[-.027,.91]],.037,.045,'#4C5D60')
 extrude('headstock',[[-.027,.908],[.027,.908],[.045,1.02],[.027,1.075],[-.027,1.075],[-.045,1.02]],-.02,.038,'#90694F')
 box('nut',(0,.91,.048),(.057,.006,.007),'#E4D8B5')
 box('pickup',(0,.425,.043),(.083,.045,.014),'#55666A')
 box('bridge',(0,.275,.045),(.103,.016,.019),'#715947')
 extrude('tailpiece',[[-.037,.18],[.037,.18],[.009,.018],[-.009,.018]],.039,.048,'#5D625B')
 # Two stylized connected f-hole curves lie in top surface, not disconnected tubing.
 for side in [-1,1]:
  pts=bezier_path([side*.090,.37],[([side*.145,.415],[side*.09,.29],[side*.104,.23]),([side*.115,.19],[side*.135,.23],[side*.117,.22])],10)
  tube('f-hole',[[x,y,.0385] for x,y in pts],.005,'#715947',6)
 # Frets stop at the fingerboard edges and follow physical scale ratio.
 for i in range(1,13):
  y=.91-.635*(1-2**(-i/12));w=.027+(.91-y)/.48*.006
  rod('fret',(-w,y,.046),(w,y,.046),.0008,'#BDB897',6)
 for i in range(strings):
  x=(i-(strings-1)/2)*(.045/(strings-1));side=-1 if i<math.ceil(strings/2) else 1;j=i if side==-1 else i-math.ceil(strings/2);yy=.935+j*.036
  rod('tuner shaft',(side*.032,yy,.005),(side*.056,yy,.005),.003,'#919D99',8)
  ellipsoid('tuning button',(side*.060,yy,.005),(.008,.012,.005),'#55666A',12,5)
  rod('string tail',(x,.045,.050),(x,.275,.056),.0009,'#E9D9B4',6)
  rod('string speaking length',(x,.275,.056),(x,.91,.051),.0009,'#E9D9B4',6)
  rod('string to tuner',(x,.91,.051),(side*.027,yy,.044),.0009,'#E9D9B4',6)
 # Raise the instrument to rest on the cradle top; foot bottoms meet ground.
 for part in S['parts']:
  part['vertices']=(np.array(part['vertices'])+[0,.016,0]).tolist()
  if any(k in part['name'] for k in ['string','fret','tuner','tuning','f-hole']):part['flat_paint']=True
 # Compact physical display stand; cradle below lower bout and supported backrest.
 for x in [-.08,.08]:
  rod('stand foot',(x,.008,-.13),(x,.008,.10),.008,dark,8)
  rod('stand support',(x,.008,-.08),(x,.32,-.08),.008,dark,8)
  rod('stand cradle',(x,.008,-.08),(x,.008,.055),.008,dark,8)
 box('stand backrest',(0,.30,-.06),(.18,.018,.050),dark)

scene('seven-string-guitar',(1.7,1.1,12));guitar(7);S['camera_roll']=30
S['notes']=['Original smooth single-cutaway archtop, approximately .406 m wide and .064 m deep, .635 m nut-to-bridge scale. Seven strings connect tailpiece, bridge, nut and seven tuning posts in a four/three configuration. Exact strings merge at16px; label carries specificity. Connected pickup, bridge, tailpiece and f-hole marks sit on the top. Stand supports lower bout/back; no artist-owned model claim.']

scene('loop-pedal',(4,7,10))
# Approximate compact pedal envelope from manufacturer 73 x129 x59 mm.
box('rubber base',(0,.004,0),(.073,.008,.129),'#526469')
box('metal case',(0,.022,0),(.071,.036,.127),'#B76D68')
box('lower hinged footplate',(0,.044,.025),(.065,.008,.073),'#9A605D')
box('rubber foot pad',(0,.049,.027),(.056,.003,.055),'#516166')
rod('hinge pin',(-.035,.043,-.010),(.035,.043,-.010),.003,'#8D9898',12)
rod('level knob',(-.019,.04,-.049),(-.019,.059,-.049),.008,'#50646B',20)
rod('loop display',(0,.040,-.029),(0,.041,-.029),.014,'#53676D',32)
# Thin circular loop indicator mounted on top, not a disconnected arrow in space.
for start,end,col in [(0,math.pi*1.6,'#BCD09B'),(math.pi*1.66,math.pi*1.96,'#E8BE9B')]:
 tube('loop indicator',[[.010*math.cos(t),.042,-.029+.010*math.sin(t)] for t in np.linspace(start,end,30)],.0015,col,6)
for side in [-1,1]:
 for z in [-.030,-.050]:rod('audio jack',(side*.035,.021,z),(side*.038,.021,z),.0045,'#6E8186',12)
S['notes']=['Original simplified foot-operated loop recorder uses approximate73x129x59mm compact envelope, rubber base, hinged pad, level knob, loop indicator and side sockets. Manufacturer schematic/text inform construction. No branding, exact model, live cabling or artist ownership promise.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
