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

def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]

scene('hydroponics',(1,2,12))
# Original cutaway of an opaque covered reservoir; foreground wall intentionally omitted.
box('rear reservoir wall',(0,.18,-.14),(.60,.34,.025),'#809DA0')
box('tank floor',(0,.022,0),(.60,.035,.30),'#809DA0')
for x in [-.287,.287]:box('tank side',(x,.18,0),(.026,.34,.30),'#A2B6AB')
box('nutrient solution rear volume',(0,.14,-.065),(.55,.21,.105),'#95C3CA')
# Two opaque lid pieces leave the central net-pot hole rather than piercing solid material.
for x in [-.18,.18]:box('opaque lid',(x,.35,0),(.24,.035,.30),'#D2DAC2')
for z in [-.109,.109]:box('lid around plant',(0,.35,z),(.12,.035,.082),'#D2DAC2')
lathe('net pot rim',[(.050,.324),(.070,.351),(.070,.368),(.054,.368),(.038,.324),(.050,.324)],'#7D918B',24)
for x in [-.027,0,.027]:
 a=(x,.33,.025);mid=(x*1.6,.21,.044);end=(x*2.0,.075,.05)
 rod('root upper',a,mid,.006,'#E7DFC0',10);rod('root lower',mid,end,.0045,'#E7DFC0',10)
 rod('root branch',mid,(x*2.3+.016,.14,.075),.0035,'#E7DFC0',8)
rod('plant stem',(0,.338,0),(0,.70,0),.013,'#6E986C',12)
for side,y in [(-1,.43),(1,.48),(-1,.57),(1,.62)]:
 base=np.array([0,y,.002]);tip=np.array([side*.18,y+.10,.015]);mid=(base+tip)/2
 panel('broad leaf',[base,mid+np.array([0,.05,.014]),tip,mid-np.array([0,.025,.007])],'#87AD77' if side<0 else '#709970')
# Small external air pump, continuous tube and submerged stone establish DWC aeration.
box('air pump',(.405,.065,0),(.16,.10,.13),'#A8A0B8')
points=[(.33,.09,0),(.32,.39,.04),(.24,.40,.06),(.22,.075,.07)]
for a,z in zip(points,points[1:]):rod('air tube',a,z,.008,'#607C88',10)
box('air stone',(.22,.067,.07),(.065,.027,.032),'#728B93')
for x,y in [(.20,.13),(.225,.18),(.21,.23)]:ball('aeration bubble',(x,y,.09),.009,'#E0E5D0')
S['notes']=['Original DWC cutaway informed by OSU Extension: opaque reservoir and lid, net-pot support, roots reaching aerated nutrient solution, external air pump and submerged stone. Foreground wall and foreground water deliberately omitted to expose roots. Not a literal transparent tank or a guaranteed Farm.One system. Simplified leaves and fluid level are illustrative; no yield or growing instructions promised.']

scene('beaded-barrette',(1,5,10))
# Generic French barrette: shallow arched decorative spine plus hinged lower clasp arm.
def spine_y(x):return .025+.065*(1-(x/.42)**2)
xs=np.linspace(-.42,.42,17)
verts=[[x,spine_y(x)+dy,z] for dy,z in [(0,-.055),(0,.055),(.012,-.055),(.012,.055)] for x in xs]
faces=[]
for j in range(16):
 faces += [[j,j+1,17+j+1,17+j],[34+j,51+j,51+j+1,34+j+1],[j,34+j,34+j+1,j+1],[17+j,17+j+1,51+j+1,51+j]]
faces += [[0,17,51,34],[16,50,67,33]]
mesh('arched decorative spine',verts,faces,'#B6C3BF')
for x,col in [(-.31,'#B893AE'),(-.155,'#D5B676'),(0,'#7FAEA7'),(.155,'#D5B676'),(.31,'#B893AE')]:
 ball('attached bead',(x,spine_y(x)+.050,0),.058,col)
rod('hinge axle',(-.385,.01,-.048),(-.385,.01,.048),.014,'#6F8993',12)
# Lower arm intentionally opened below upper spine to show the hair-holding gap.
box('hinge bracket',(-.385,.019,0),(.033,.06,.10),'#869FA5')
armstart=np.array([-.385,.01,0]);armend=np.array([.345,-.16,0]);axis=armend-armstart;normal=np.array([-axis[1],axis[0],0]);normal=normal/np.linalg.norm(normal)*.008
mesh('opened clasp arm',[armstart+normal+[0,0,z] for z in [-.034,.034]]+[armend+normal+[0,0,z] for z in [-.034,.034]]+[armstart-normal+[0,0,z] for z in [-.034,.034]]+[armend-normal+[0,0,z] for z in [-.034,.034]],[[0,2,3,1],[4,5,7,6],[0,4,6,2],[1,3,7,5],[0,1,5,4],[2,6,7,3]],'#8DA5AC')
for z in [-.065,.065]:box('press clasp tab',(.36,.002,z),(.07,.045,.045),'#7F98A2')
box('latch bridge',(.385,.027,0),(.028,.016,.10),'#7F98A2')
S['notes']=['Original generic beaded French barrette, not a copied workshop pattern. Top spine arches gently, five beads touch it, hinge supports deliberately opened lower arm and opposite clasp has two press tabs. Supplier tutorial confirms press-side opening; exact workshop barrette types vary. Wire attachment and internal spring simplified, no assembly instructions or actual dimensions promised.']

# Reuse our original cycle021 passenger-vessel construction, with a route-map emblem instead of party notes.
boat_source=Path('config/event-icons/prototypes/autonomous-cycle-021/scene.py').read_text()
boat_code=boat_source[boat_source.index("scene('party-cruise'"):boat_source.index("if __name__=='__main__':")]
exec(boat_code.replace("scene('party-cruise'", "scene('boat-tour'"))
S['notes']=['Reuses the original cycle021 generic passenger-vessel scene, whose construction reference was the Circle Line Manhattan-class vessel photograph. This event specifies an on-water narrated tour but no vessel; no exact boat, propulsion, capacity, deck access or route is asserted. The final map/route card is a flat semantic overlay, not a physical object on the boat.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')

