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

# Original sundial: horizontal circular base, polar triangular gnomon and computed shadow.
scene('sundial',(4,6,10))
lathe('stone dial',[(0,0),(.48,0),(.49,.06),(.48,.08),(0,.08)],'#D9C397',48)
latitude=math.radians(41);height=.40*math.tan(latitude)
# Fin rises toward north (negative z); its sloping edge is parallel to polar axis.
v=[[-.015,.08,.20],[-.015,.08,-.20],[-.015,.08+height,-.20],[.015,.08,.20],[.015,.08,-.20],[.015,.08+height,-.20]]
mesh('triangular gnomon',v,[[0,2,1],[3,4,5],[0,1,4,3],[1,2,5,4],[2,0,3,5]],'#7E9A94')
sun=np.array([-.8,1.3,-.6]);pts=[np.array([0,.08,.20]),np.array([0,.08,-.20]),np.array([0,.08+height,-.20])]
shadow=[q-(q[1]-.081)/sun[1]*sun for q in pts]
panel('geometrically projected shadow',shadow,'#A78E66')
# Nonuniform hour directions from tan(theta)=sin(latitude)*tan(hour angle); no numeric labels.
for hour in [-5,-4,-3,-2,-1,0,1,2,3,4,5]:
 theta=math.atan(math.sin(latitude)*math.tan(math.radians(15*hour)))
 x,z=math.sin(theta),-math.cos(theta)
 rod('hour mark',(x*.39,.083,z*.39),(x*.445,.083,z*.445),.006,'#9A845F',8)
S['notes']=['Horizontal plate with an attached triangular fin; polar edge41degrees is illustrative local latitude, not a calibrated instrument. Shadow vertices are projected to plate from sun vector(-.8,1.3,-.6). Hour tick angles are nonuniform; omitted clock numerals avoid false exact time. No freestanding clock hands.']

# Folded cloth bundle and a completed resist-pattern sample; illustrative binding method.
scene('shibori',(2,4,12))
for j in range(5):
 box('accordion folded cloth',(-.22,.08+j*.032,.03),(.38,.03,.36),'#86ADA7' if j%2 else '#D6E0CB')
# Two continuous bindings around stacked fabric, with broad visible top and side segments.
for x in [-.31,-.13]:
 box('binding top',(x,.226,.03),(.022,.012,.376),'#536E81')
 box('binding bottom',(x,.066,.03),(.022,.012,.376),'#536E81')
 for z in [-.158,.218]:box('binding side',(x,.146,z),(.022,.16,.012),'#536E81')
# Sample is separate and deliberately upright to reveal an original resist motif.
def cloth(u,v):return [.25+u+.018*math.sin(v*17),.34+v,-.07]
def patch(name,u0,u1,v0,v1,color,offset=0):
 us=np.linspace(u0,u1,7);vs=np.linspace(v0,v1,9);verts=[]
 for vv in vs:
  for uu in us:
   q=cloth(uu,vv);q[2]+=offset;verts.append(q)
 faces=[]
 for j in range(8):
  for i in range(6):
   k=j*7+i;faces.extend([[k,k+1,k+8],[k,k+8,k+7]])
 mesh(name,verts,faces,color)
patch('flat schematic cloth sample',-.24,.24,-.275,.275,'#6F95A2')
for u in [-.15,0,.15]:patch('irregular vertical resist',u-.016,u+.016,-.275,.275,'#E2E3CA',.001)
for v in [-.18,0,.18]:patch('irregular horizontal resist',-.24,.24,v-.016,v+.016,'#E2E3CA',.002)
S['notes']=['Five-layer accordion fold and two closed compression bindings are original generic examples. The separate bandana sample shows pale resist bands; the actual event does not promise this precise pattern or indigo dye. Model uses teal-blue illustratively, not as a dye identification.']

# Two original views of a textile brooch: embroidered felt face and separate back inset.
scene('textile-brooch',(0,1,14))
def flower(cx,cy,z,r,base,color):
 outline=[]
 for i in range(80):
  t=2*math.pi*i/80;rr=r*(.83+.17*math.cos(5*t));outline.append((cx+rr*math.cos(t),cy+rr*math.sin(t)))
 extrude('felt backing',outline,z,z+.022,base)
 if color:
  for i in range(5):
   t=i*2*math.pi/5;circle=[(cx+.21*math.cos(t)+.14*math.cos(a),cy+.21*math.sin(t)+.14*math.sin(a)) for a in np.linspace(0,2*math.pi,24,endpoint=False)]
   extrude('embroidered petal',circle,z+.022,z+.030,color)
   rod('long embroidery stitch',(cx+.14*math.cos(t),cy+.14*math.sin(t),z+.033),(cx+.29*math.cos(t),cy+.29*math.sin(t),z+.033),.009,'#E4B7AD',10)
  rod('flower center',(cx,cy,z+.03),(cx,cy,z+.04),.085,'#D3B36F',24)
flower(-.16,.44,0,.40,'#718B87','#BD8C9D')
# Rear inset uses the same shape at a smaller illustrative scale. Needle is shown open above its C catch.
start=len(S['parts']);flower(0,0,0,.40,'#98AAA1',None)
box('sewn pin base',(0,0,.032),(.54,.08,.025),'#B2C4C0')
rod('hinge axle',(-.23,-.04,.061),(-.23,.04,.061),.018,'#617D89',12)
rod('pin stem',(-.23,0,.07),(.20,.16,.085),.018,'#526E7B',12)
box('catch base',(.23,0,.042),(.05,.065,.023),'#617D89')
box('catch outer side',(.247,0,.072),(.018,.065,.046),'#617D89')
box('catch hook',(.222,0,.095),(.05,.065,.012),'#617D89')
for part in S['parts'][start:]:part['vertices']=(np.array(part['vertices'])*.65+np.array([.35,.14,.10])).tolist()
S['notes']=['Separate front and back views, not two overlapping parts of one physical pin. Felt carries original five-petal stitched decoration. Back inset hinge, stem and C catch are attached to a bar, with needle intentionally opened upward from its hinge to reveal the fastening. C-catch geometry informed by jewelry maker structural account; workshop clasp type may vary. Hardware is enlarged relative to real brooch to remain visible.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')

