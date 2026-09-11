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
 x,y,z=c;n=24;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
# Original dance-fitness figure, fixed anatomical lengths and explicit floor contacts.
def ellipsoid(name,c,r,col):
 ball(name,(0,0,0),1,col);S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])*r+c).tolist()
def capsule(name,a,b,r1,r2,col):
 rod(name,a,b,r1,col,20,r2);ball(name+' start',a,r1,col);ball(name+' end',b,r2,col)
def joint(a,b,l1,l2,hint):
 a,b=np.array(a,float),np.array(b,float);v=b-a;d=np.linalg.norm(v);u=v/d;h=np.array(hint,float);h-=u*np.dot(h,u);h/=np.linalg.norm(h)
 along=(l1*l1-l2*l2+d*d)/(2*d);return a+u*along+h*math.sqrt(l1*l1-along*along)
def torso(name,levels,col):
 verts=[];n=28
 for y,rx,rz in levels:
  for i in range(n):verts.append([rx*math.cos(2*math.pi*i/n),y,rz*math.sin(2*math.pi*i/n)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]+[list(range(n-1,-1,-1)),list(range((len(levels)-1)*n,len(levels)*n))]
 mesh(name,verts,faces,col)
scene('zumba',(1.2,1,12));skin='#D5A176';shirt='#78A5A0';pants='#737F9E';hair='#665E57'
# Two shoes rest on the same floor. Fixed femur .420m and tibia .400m.
for side in [-1,1]:
 hip=np.array([side*.105,.840,0]);footx=-.20 if side==-1 else .34;ankle=np.array([footx,.085,.018]);knee=joint(hip,ankle,.420,.400,[0,0,1])
 capsule('trouser thigh',hip,knee,.071,.061,pants);capsule('trouser shin',knee,ankle,.061,.047,pants)
 ellipsoid('shoe',(footx,.043,.075),(.079,.043,.136),'#E3D9BD')
 # Narrow outsole lies on the floor, enclosing the shoe sole plane.
 box('shoe sole',(footx,.008,.075),(.145,.016,.235),'#C9BC9E')
torso('trouser waist',[(.780,.133,.089),(.880,.137,.086)],pants)
torso('athletic shirt',[(.865,.142,.089),(1.03,.137,.087),(1.21,.171,.097),(1.29,.155,.081),(1.32,.075,.058)],shirt)
# Neck lower end is hidden within the shirt; only .04m is visible below head.
capsule('neck',(0,1.30,0),(0,1.385,0),.049,.047,skin)
for side in [-1,1]:
 shoulder=np.array([side*.165,1.265,0]);wrist=np.array([side*.47,1.53 if side==-1 else 1.14,.10]);elbow=joint(shoulder,wrist,.285,.255,[side,-1,.2])
 capsule('upper arm',shoulder,elbow,.039,.035,skin);capsule('forearm',elbow,wrist,.035,.028,skin)
 sleeve=shoulder+(elbow-shoulder)*.34;capsule('shirt sleeve',shoulder,sleeve,.054,.046,shirt)
 direction=(wrist-elbow)/np.linalg.norm(wrist-elbow);hand=wrist+direction*.046
 capsule('hand',wrist,hand,.029,.030,skin)
 thumb=wrist+np.array([-side*.033,.020,.032]);capsule('thumb',wrist,thumb,.016,.014,skin)
ellipsoid('head',(0,1.495,0),(.103,.133,.090),skin)
for side in [-1,1]:ellipsoid('ear',(side*.10,1.49,-.005),(.018,.030,.017),skin)
# Hair cap ends above the face; broad flat paint avoids inconsistent skin shading.
verts=[];n=32
for theta in np.linspace(0,1.28,10):
 for phi in np.linspace(0,2*math.pi,n,endpoint=False):verts.append([.110*math.sin(theta)*math.cos(phi),1.495+.145*math.cos(theta),.097*math.sin(theta)*math.sin(phi)-.008])
mesh('short hair',verts,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(9) for i in range(n)],hair)
S['parts'][-1]['faces']=[list(reversed(f)) for f in S['parts'][-1]['faces']]
for side in [-1,1]:ellipsoid('eye',(side*.033,1.508,.086),(.0075,.010,.005),'#5A5753')
ellipsoid('nose',(0,1.484,.09),(.010,.013,.010),skin)
for aa,bb in zip([(-.024,1.466),(-.012,1.457),(0,1.455),(.012,1.457)],[(-.012,1.457),(0,1.455),(.012,1.457),(.024,1.466)]):rod('smile',(aa[0],aa[1],.087),(bb[0],bb[1],.087),.004,'#875F50',10)
# Musical beat symbols are separate flat emblems, not floating physical equipment.
for side in [-1,1]:
 x=side*.61;y=1.07 if side==-1 else 1.60
 ellipsoid('beat note',(x,y,0),(.039,.025,.009),'#D5B17C');rod('beat stem',(x+.027,y,0),(x+.027,y+.14,0),.007,'#D5B17C',8)
S['notes']=['Paired femur lengths .420m and tibia lengths .400m are fixed by inverse kinematics. Both shoes and outsoles contact y=0. Knees bend forward, separated from one another; the lateral stance is a grounded illustrative step, not a jump.', 'Both upper arms measure .285m and forearms .255m. Upper arm radii .039m are smaller than thigh radii .071m. Hands and thumbs connect to wrists; sleeves overlap shoulder/upper arm and continuous trouser volumes cover the skeleton.', 'Short neck enters shirt and head; head bottom1.362m leaves about.04m above shirt. Both arms/legs use identical colors, and skin paint is flat. Musical notes are symbolic. No specific choreography, impact level, age, instructor likeness or brand affiliation is promised.']
scene('bookmobile',(9,4,7))
# Generic six-metre library coach: body above four equal wheels, no emergency lights.
box('coach floor',(0,.75,0),(1.70,.22,5.8),'#6C8894')
box('library body',(0,1.725,-.305),(2.12,1.75,5.05),'#DCE1D1')
# Sloping cab nose closes with windshield and front panels.
outline=[(2.22,.86),(2.85,.86),(2.98,1.35),(2.22,2.60)]
extrude('cab',outline,-1.06,1.06,'#D8DFD6')
part=S['parts'][-1];part['vertices']=[[z,y,x] for x,y,z in part['vertices']];part['faces']=[list(reversed(f)) for f in part['faces']]
panel('windshield',[(-.93,1.55,2.864),(.93,1.55,2.864),(.93,2.42,2.335),(-.93,2.42,2.335)],'#7495A6')
# Longitudinal teal side stripe and a library door; opposite sides share structure.
for side in [-1,1]:
 x=side*1.066
 panel('library stripe',[(x,.89,-2.72),(x,.89,2.36),(x,1.13,2.36),(x,1.13,-2.72)],'#9A91AD')
 panel('library door',[(x,1.14,.42),(x,1.14,1.25),(x,2.39,1.25),(x,2.39,.42)],'#BDCCC7')
 panel('door window',[(x+side*.006,1.89,.53),(x+side*.006,1.89,1.13),(x+side*.006,2.26,1.13),(x+side*.006,2.26,.53)],'#7798A6')
 # Open-book side emblem is original planar geometry attached to the body.
 panel('book left',[(x+side*.012,1.46,-1.40),(x+side*.012,1.60,-2.16),(x+side*.012,2.16,-2.16),(x+side*.012,2.02,-1.40)],'#F1D9AB')
 panel('book right',[(x+side*.012,1.46,-1.40),(x+side*.012,1.60,-.64),(x+side*.012,2.16,-.64),(x+side*.012,2.02,-1.40)],'#E6C98F')
 for y in [1.72,1.91]:
  rod('book page line',(x+side*.015,y,-2.01),(x+side*.015,y-.085,-1.55),.014,'#BCA884',8)
  rod('book page line',(x+side*.015,y-.085,-1.25),(x+side*.015,y,-.79),.014,'#BCA884',8)
 for z in [-1.95,1.95]:
  rod('tire',(side*.93,.42,z),(side*1.14,.42,z),.42,'#566771',40)
  rod('wheel hub',(side*1.142,.42,z),(side*1.151,.42,z),.21,'#AAB9B8',32)
for z in [-1.95,1.95]:
 rod('axle',(-.98,.42,z),(.98,.42,z),.065,'#657681',16)
 box('suspension',(0,.56,z),(1.45,.23,.24),'#657681')
# Four wheels use the same radius and axle heights; bumper and twin headlamps.
box('front bumper',(0,.70,2.83),(2.15,.15,.20),'#8DA4AE')
for x in [-.72,.72]:panel('headlight',[(x-.16,.98,2.888),(x+.16,.98,2.888),(x+.16,1.13,2.928),(x-.16,1.13,2.928)],'#E8D09C')
S['notes']=['Generic bookmobile exterior derives from the accepted original coach study: continuous floor/body, closed sloping cab, four equal .42m-radius wheels at equal axle heights, suspension and front bumper. Wheels contact y=0. The book side emblem replaces all clinic markings. Doors, windshield and book graphics stay attached to vehicle surfaces; no emergency lighting, specific fleet replica or service inventory is promised.']
if __name__=='__main__':(ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
