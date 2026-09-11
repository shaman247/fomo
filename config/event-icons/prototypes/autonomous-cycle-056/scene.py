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

# Original commercial-jazz-inspired grounded open pose. Fixed skeleton before styling.
scene('jazz-dance',(1,1,22));skin='#BD835C';pants='#656E96';shirt='#6EA59A';hair='#463C42';joints={}
for side in [-1,1]:
 hip=np.array([side*.105,.79,0]);ankle=np.array([side*.33,.085,.025]);knee=joint(hip,ankle,.42,.40,[side*.7,0,1])
 capsule('trouser thigh',hip,knee,.069,.057,pants);capsule('trouser shin',knee,ankle,.057,.041,pants)
 foot(side*.33,.085,'#B5A88F');joints[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
torso('waist',[(.72,.15,.092),(.83,.143,.094)],pants)
torso('fitted shirt',[(.79,.145,.098),(.96,.132,.091),(1.14,.166,.094),(1.20,.158,.077),(1.23,.065,.055)],shirt)
capsule('neck',(0,1.205,0),(0,1.255,0),.044,.042,skin);human_head((0,1.367,0))
# Diagonal open arms, both attached; no ungrounded jump or required choreography implied.
for side,wrist,hint,end in [(-1,[-.64,1.02,.025],[-1,.2,0],[-.69,1.01,.026]),(1,[.45,1.61,.025],[1,0,.3],[.478,1.658,.026])]:
 joints[str(side)].update(arm(np.array([side*.16,1.175,0]),np.array(wrist),hint,np.array(end),shirt))
for part in S['parts']:part['flat_paint']=True
# Exact segment-length validation supplements, but does not replace, multi-view visual checks.
for q in joints.values():
 for a,b,l in [('hip','knee',.42),('knee','ankle',.40),('shoulder','elbow',.285),('elbow','wrist',.255)]:assert abs(np.linalg.norm(np.array(q[a])-q[b])-l)<1e-8
S['measurements']=dict(joints=joints,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.069,shoe_sole_y=0,neck_axis_length=.05,head_bottom=1.234,shirt_collar=1.23)
S['notes']=['Original grounded open jazz-inspired pose based on the described commercial-jazz dance activity, not traced choreography. Equal fixed limb lengths, two floor-contact shoes and one skin paint. No jazz music instrument or specific substyle promised. Ailey uses a shared hip-hop-named promotional photo on its commercial-jazz page; reference informs general dance anatomy, not a unique jazz pose.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
