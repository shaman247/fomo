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
 x,y,z=c;n=16;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
# Repair seams lie on the surface of a continuous ceramic bowl; no floating shards.
scene('kintsugi',(0.6,3,9))
profile=[(.0,.04),(.25,.04),(.26,.09),(.40,.16),(.53,.29),(.60,.46),(.61,.51),(.57,.51),(.56,.46),(.49,.29),(.37,.18),(.20,.12),(0,.12)]
lathe('ceramic bowl',profile[:7],'#3F93A6',56)
lathe('bowl interior',profile[6:],'#78BAC6',56)
# camera-facing meridians follow the exact bowl profile slightly above its surface.
def seam(name,path):
 for j,(a,bb) in enumerate(zip(path,path[1:])):rod(name+str(j),a,bb,.018,'#F9C455',8)
def surf(angle,r,y):return ((r+.009)*math.cos(angle),y,(r+.009)*math.sin(angle))
seam('gold central seam',[surf(a,r,y) for a,r,y in [(1.55,.61,.51),(1.64,.60,.46),(1.50,.53,.29),(1.71,.40,.16),(1.65,.26,.09)]])
seam('gold branch',[surf(a,r,y) for a,r,y in [(1.50,.53,.29),(1.09,.55,.35),(.91,.58,.42),(.89,.61,.51)]])
seam('gold left seam',[surf(a,r,y) for a,r,y in [(2.55,.61,.51),(2.40,.60,.46),(2.60,.53,.29),(2.42,.40,.16)]])
S['notes']=['Continuous hollow bowl with connected rim, inner wall and base; decorative gold repair lines track outer ceramic surface. Stylized approximate bowl, not an exact historical object.']
scene('ikebana',(1.5,3.5,10))
lathe('shallow vessel',[(0,.025),(.38,.025),(.47,.08),(.49,.17),(.45,.17),(.43,.085),(0,.07)],'#57799F',40)
rod('kenzan',(0,.071,0),(0,.10,0),.095,'#75865E',20)
branches=[[(0,.1,0),(-.055,.52,0),(-.21,1.02,-.025),(-.16,1.55,-.04)],[(.018,.1,0),(.21,.43,.015),(.60,.78,.02)],[(.01,.1,.035),(.14,.28,.19),(.35,.48,.30)]]
for i,path in enumerate(branches):
 for j,(a,bb) in enumerate(zip(path,path[1:])):rod('stem'+str(i)+'-'+str(j),a,bb,.024 if i==0 else .021,'#58865D',10)
def leaf(name,base,tip,w):
 a=np.array(base);bb=np.array(tip);mid=(a+bb)/2;delta=bb-a;side=np.array([-delta[1],delta[0],0]);side=side/np.linalg.norm(side)*w
 panel(name,[a.tolist(),(mid+side).tolist(),bb.tolist(),(mid-side).tolist()],'#6DA66B')
leaf('tall leaf',(-.19,1.08,-.025),(-.46,1.29,-.025),.07);leaf('upper leaf',(-.18,1.28,-.035),(.05,1.43,-.035),.065)
leaf('lower leaf',(.17,.37,.015),(.40,.43,.015),.085)
for name,c,r,col in [('tall bud',(-.16,1.55,-.04),.075,'#EDAB78'),('flower',(.60,.78,.02),.14,'#EEAC87'),('low flower',(.35,.48,.30),.12,'#F4CB83')]:
 if name=='tall bud':ball(name,c,r,col)
 else:
  for j in range(5):
   a=j*2*math.pi/5;ball(name+' petal'+str(j),(c[0]+r*.65*math.cos(a),c[1]+r*.65*math.sin(a),c[2]),r*.56,col)
  ball(name+' heart',(c[0],c[1],c[2]+r*.50),r*.38,'#D6A447')
S['notes']=['Asymmetric illustrative arrangement in shallow moribana-style bowl. Three stems originate inside fixed kenzan; leaves attach stems; flowers join stem endpoints. Not a claim that every ikebana school uses this arrangement.']
scene('arcade-cabinet',(3,2,10))
# Common scale 0.65m wide / 1.75m high; screen recessed above supported controls.
profile=[(-.32,0),(.32,0),(.32,.92),(.40,.98),(.40,1.07),(.25,1.09),(.20,1.49),(.34,1.56),(.34,1.75),(-.32,1.75)]
# profile uses (depth,height), extrusion width; explicit transform of vertices.
n=len(profile);v=[[x,y,z] for x in [-.35,.35] for z,y in profile];faces=[list(range(n-1,-1,-1)),list(range(n,2*n))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)];mesh('cabinet',v,[list(reversed(f)) for f in faces],'#665992')
box('marquee',(0,1.64,.345),(.61,.145,.018),'#F1C05F')
panel('bezel',[[-.29,1.14,.247],[.29,1.14,.247],[.29,1.48,.205],[-.29,1.48,.205]],'#263C49')
panel('screen',[[-.24,1.19,.244],[.24,1.19,.244],[.24,1.43,.215],[-.24,1.43,.215]],'#68B8B4')
# Generic game shapes, no brand/logo.
panel('screen platform',[[-.20,1.23,.241],[.20,1.23,.241],[.20,1.25,.239],[-.20,1.25,.239]],'#D6EBD4')
box('control panel',(0,1.075,.28),(.62,.025,.25),'#414E67')
rod('joystick',(-.17,1.09,.30),(-.17,1.23,.30),.018,'#CEDADD',10);ball('joystick ball',(-.17,1.24,.30),.065,'#E77F77')
for x,z in [(.04,.28),(.16,.28),(.10,.38),(.22,.38)]:rod('button',(x,1.088,z),(x,1.112,z),.035,'#F3C55D',12)
box('coin panel',(0,.67,.326),(.20,.20,.015),'#384755');box('coin slot',(0,.715,.337),(.08,.017,.015),'#F1EDEC')
S['notes']=['Solid upright cabinet with connected foot, screen bezel, control deck, joystick, buttons and coin door. Generic one-player motif does not promise cabinet model, manufacturer or exact control count.']
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created 3 scenes')
