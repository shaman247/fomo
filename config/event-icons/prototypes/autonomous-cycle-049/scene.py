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
# Original dance-fitness figure, fixed anatomical lengths and explicit floor contacts.
def ellipsoid(name,c,r,col):
 ball(name,(0,0,0),1,col);S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])*r+c).tolist()
def capsule(name,a,b,r1,r2,col):
 rod(name,a,b,r1,col,12,r2);ball(name+' start',a,r1,col);ball(name+' end',b,r2,col)
def joint(a,b,l1,l2,hint):
 a,b=np.array(a,float),np.array(b,float);v=b-a;d=np.linalg.norm(v);u=v/d;h=np.array(hint,float);h-=u*np.dot(h,u);h/=np.linalg.norm(h)
 along=(l1*l1-l2*l2+d*d)/(2*d);return a+u*along+h*math.sqrt(l1*l1-along*along)
def torso(name,levels,col):
 verts=[];n=20
 for y,rx,rz in levels:
  for i in range(n):verts.append([rx*math.cos(2*math.pi*i/n),y,rz*math.sin(2*math.pi*i/n)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]+[list(range(n)),list(range(len(levels)*n-1,(len(levels)-1)*n-1,-1))]
 mesh(name,verts,faces,col)

# Original figures use fixed bone lengths; no traced photograph geometry.
skin='#BE8664';pants='#5D688B';shirt='#52A49B';hair='#45434A'
def human_head(center,tilt=0):
 first=len(S['parts']);cx,cy,cz=center
 ellipsoid('head',(0,0,0),(.103,.133,.090),skin)
 for side in [-1,1]:ellipsoid('ear',(side*.10,-.005,-.005),(.018,.030,.017),skin)
 v=[];n=20
 for theta in np.linspace(0,1.28,6):
  for phi in np.linspace(0,2*math.pi,n,endpoint=False):v.append([.11*math.sin(theta)*math.cos(phi),.145*math.cos(theta),.097*math.sin(theta)*math.sin(phi)-.008])
 mesh('hair',v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(5) for i in range(n)],hair)
 for side in [-1,1]:ellipsoid('eye',(side*.033,.013,.086),(.0075,.01,.005),'#45434A')
 ellipsoid('nose',(0,-.011,.092),(.012,.015,.015),skin)
 rod('mouth',(-.020,-.036,.086),(.020,-.036,.086),.004,'#855E50',8)
 c,s=math.cos(tilt),math.sin(tilt);rot=np.array([[1,0,0],[0,c,-s],[0,s,c]])
 for part in S['parts'][first:]:part['vertices']=(np.array(part['vertices'])@rot.T+center).tolist()
def curved_body(levels,col):
 n=20;v=[]
 for y,z,rx,rz in levels:
  v.extend([[rx*math.cos(a),y,z+rz*math.sin(a)] for a in np.linspace(0,2*math.pi,n,endpoint=False)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]
 faces += [list(range(n)),list(range(len(levels)*n-1,(len(levels)-1)*n-1,-1))]
 mesh('continuous curved shirt',v,faces,col)
def palm(name,wrist,end,col):
 # Simple continuous mitten silhouette; no extra fingers or detached hand.
 capsule(name,wrist,end,.029,.030,col)
def foot(x,z,col):
 ellipsoid('soft shoe',(x,.043,z),(.076,.043,.128),col)
 box('grounded sole',(x,.008,z),(.14,.016,.224),col)

def arm(shoulder,wrist,hint,handend,col):
 elbow=joint(shoulder,wrist,.285,.255,hint)
 capsule('upper arm',shoulder,elbow,.039,.035,skin);capsule('forearm',elbow,wrist,.035,.028,skin)
 sleeve=np.array(shoulder)+(elbow-shoulder)*.23;capsule('short sleeve',shoulder,sleeve,.051,.046,col)
 palm('hand',wrist,handend,skin)
 return dict(shoulder=list(shoulder),elbow=elbow.tolist(),wrist=list(wrist),hand_end=list(handend))

def flat_extrude(name,outline,y0,y1,color):
 extrude(name,outline,y0,y1,color);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
def torus(name,c,R,r,col,n=32,m=8):
 cx,cy,cz=c;v=[]
 for a in np.linspace(0,2*math.pi,n,endpoint=False):
  for bb in np.linspace(0,2*math.pi,m,endpoint=False):v.append([cx+(R+r*math.cos(bb))*math.cos(a),cy+(R+r*math.cos(bb))*math.sin(a),cz+r*math.sin(bb)])
 faces=[[i*m+j,((i+1)%n)*m+j,((i+1)%n)*m+(j+1)%m,i*m+(j+1)%m] for i in range(n) for j in range(m)];mesh(name,v,faces,col)
def shift_last(dx=0,dy=0,dz=0):
 p=S['parts'][-1];p['vertices']=(np.array(p['vertices'])+[dx,dy,dz]).tolist()

# Serving board: a single solid slab with a real through-hole, laid flat.
from shapely.geometry import box as polygon_box,Point
from shapely.ops import triangulate
scene('serving-board',(4,8,7))
outline=polygon_box(-.29,-.39,.29,.39).buffer(.055,resolution=8)
hole=Point(-.21,-.30).buffer(.043,resolution=12);shape=outline.difference(hole)
for tri in triangulate(shape):
 if shape.covers(tri.representative_point()):
  coords=list(tri.exterior.coords)[:-1];flat_extrude('solid wood board',coords,0,.035,'#CE9865')
for ring in [shape.exterior,*shape.interiors]:
 cs=list(ring.coords)
 for (x,z),(xx,zz) in zip(cs,cs[1:]):panel('continuous board edge',[(x,0,z),(xx,0,zz),(xx,.035,zz),(x,.035,z)],'#B67B51')
# Pencil resting on board surface, not a promise of supplied materials.
rod('pencil body',(-.12,.047,.22),(.23,.047,.32),.012,'#DBB65D',6)
rod('pencil wood tip',(-.15,.047,.211),(-.12,.047,.22),.001,'#EDD1A1',6,.012)
rod('graphite',(-.159,.047,.208),(-.15,.047,.211),.0005,'#536575',6,.003)
# Sparse embedded grain, also in the authoritative board plane.
for x,z,end in [(-.15,-.13,.12),(-.03,-.29,.23),(.11,-.29,.18)]:rod('wood grain',(x,.0355,z),(x+.01,.0355,end),.003,'#B67B51',6)
S['measurements']=dict(board_thickness=.035,hole_radius=.043,pencil_radius=.012,pencil_center_y=.047,board_top_y=.035)
S['notes']=['Original rounded solid-wood serving board with through-hole; generic design, not a replica or promised class output. Pencil rests on top. No food, powered cutting operation, blade or exact finish represented.']

scene('bodyweight-circuit',(7,2,11));skin='#BE8664';pants='#596C8C';shirt='#56A29B';hair='#45434A';js={}
for side in [-1,1]:
 hip=np.array([side*.105,.62,-.22]);ankle=np.array([side*.205,.09,.025]);knee=joint(hip,ankle,.42,.40,[0,0,1])
 capsule('trouser thigh',hip,knee,.068,.062,pants);capsule('trouser shin',knee,ankle,.062,.044,pants);foot(side*.205,.065,'#D3D3C7');js[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
curved_body([(.55,-.21,.13,.10),(.67,-.21,.15,.10),(.83,-.12,.165,.09),(1.00,-.03,.16,.084),(1.035,-.012,.062,.052)],shirt)
capsule('short neck',(0,1.015,-.012),(0,1.08,.005),.047,.046,skin);human_head((0,1.185,.011),.03)
for side in [-1,1]:js[str(side)].update(arm((side*.16,.985,-.025),(side*.225,.885,.45),(side*.35,-1,0),(side*.23,.885,.51),shirt))
for part in S['parts']:part['flat_paint']=True
S['measurements']=dict(joints=js,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.068,floor=0)
S['notes']=['Original grounded partial squat illustrating bodyweight exercise; paired fixed-length limbs and two feet on floor. One flat skin paint, short neck and arms narrower than thighs. Timer added as a flat editorial diagram, not a physical floating object. Does not prescribe a routine, duration or exact movement taught by either program.']

scene('art-cart',(5,4,9))
# Original two-tier trolley; not a reproduction of an organizer or retail model.
for x in [-.29,.29]:
 for z in [-.19,.19]:
  rod('caster wheel',(x-.022,.07,z),(x+.022,.07,z),.07,'#526776',16)
  rod('caster stem',(x,.105,z),(x,.18,z),.018,'#75969C',10)
  rod('upright',(x,.17,z),(x,.78,z),.019,'#72A5A5',12)
for y in [.22,.73]:
 box('tray base',(0,y,0),(.65,.035,.47),'#66A0A0')
 frame('tray rim',(0,y+.045,0),.65,.47,.025,.09,'#72A5A5')
# Handle connects to both rear uprights.
for x in [-.29,.29]:rod('handle side',(x,.77,-.19),(x,.91,-.19),.018,'#72A5A5',12)
rod('handle top',(-.29,.91,-.19),(.29,.91,-.19),.018,'#72A5A5',12)
# Paper stack rests inside upper tray; sketch line is illustrative.
box('paper stack',(-.09,.761,.02),(.32,.027,.32),'#F1E7D2')
rod('paper drawing',(-.18,.778,.08),(-.03,.778,-.08),.008,'#799777',8)
# Open pencil cup rests on tray; wall and bottom are continuous.
lathe('pencil cup',[(0,.747),(.066,.747),(.066,.935),(.054,.935),(.054,.760),(0,.760)],'#CB9769',20);shift_last(dx=.205,dz=.055)
for x,z,y,col in [(.18,.04,1.08,'#DAAD5D'),(.22,.03,1.105,'#927AB4'),(.21,.083,1.035,'#B97166')]:
 rod('colored pencil',(x,.76,z),(x,y,z),.009,col,6)
 rod('pencil point',(x,y,z),(x,y+.027,z),.009,'#DFC393',6,0)
box('lower colored paper',(0,.2555,.01),(.46,.036,.32),'#AD8EB4')
for p in S['parts']:
 if any(x in p['name'] for x in ['upright','handle','pencil','caster']):p['flat_paint']=True
S['measurements']=dict(wheels=4,wheel_radius=.07,wheel_centers_y=.07,tiers=2,paper_bottom=.7475,tray_top=.7475,cup_bottom=.747)
S['notes']=['Original generic two-tier art-supply trolley, four caster wheels on floor and connected uprights/handle. Paper and pencil cup rest in trays. Symbolic supplies are examples, not guaranteed inventory. Event photo showed a shared worktable, not cart construction; a manufacturer reference only informed basic trolley relationships. No product replica.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
if __name__=='__main__':print('Built three original3D scenes')
