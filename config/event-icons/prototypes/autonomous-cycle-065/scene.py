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

scene('natural-bundle-dyeing',(4,8,11))
# Cloth laid out with generic dye plants; a separate rolled textile bundle bound with twine.
box('prepared cloth',(-.13,.008,0),(.50,.016,.70),'#E6D6B7')
# Curved generic botanical leaves rest flat on the cloth. No exact species or imprint promised.
for x,z,ang,col in [(-.22,-.21,.6,'#B69A65'),(-.07,.03,-.8,'#9EA47A'),(-.23,.19,.1,'#C19479')]:
 pts=[]
 for t in np.linspace(0,2*math.pi,32,endpoint=False):
  xx=.041*math.sin(t);zz=.10*math.cos(t);pts.append([x+xx*math.cos(ang)+zz*math.sin(ang),.017,z+zz*math.cos(ang)-xx*math.sin(ang)])
 panel('natural dyestuff leaf',pts,col)
 rod('leaf center vein',(x-.08*math.sin(ang),.019,z-.08*math.cos(ang)),(x+.08*math.sin(ang),.019,z+.08*math.cos(ang)),.0035,'#867E5D',8)
for x,z in [(-.31,-.05),(-.10,-.24),(-.10,.25)]:rod('dye petal',(x,.017,z),(x,.020,z),.018,'#AE785B',12)
rod('rolled textile bundle',(.29,.114,-.31),(.29,.114,.31),.103,'#D4BE9D',40)
# Spiral end indicates rolled cloth, rather than a food item.
for z in [-.313,.313]:
 pts=[[.29+r*math.cos(t),.114+r*math.sin(t),z] for t,r in zip(np.linspace(0,math.pi*4,70),np.linspace(.014,.094,70))];tube('cloth roll end spiral',pts,.005,'#A18E70',6)
for z in [-.20,0,.20]:torus_z('binding twine',(.29,.114,z),.105,.009,'#7C8574')
S['notes']=['Original generic dyestuffs rest on cloth; separate bound cloth roll rests on ground. Rolled fabric end and three continuous twine loops communicate bundling. No recipe, guaranteed species, dye result, chemical dose or steaming instructions.']

scene('macrame',(1,2,15))
# Hanging knot sample: physical dowel suspension and continuous cord groups, no pot included.
rod('wooden dowel',(-.40,.86,0),(.40,.86,0),.025,'#B69A75',24)
# Two suspension lines converge at a fixed upper ring; symbolic cropped wall attachment.
for x in [-.32,.32]:tube('support cord',[[x,.86,0],[x*.85,.95,0],[0,1.12,0]],.010,'#9C8B71')
torus_z('hanging ring',(0,1.135,0),.035,.009,'#9A8263',32)
cord='#C5B58E';shade='#A89774'
centers=[-.27,-.09,.09,.27]
# Eight continuous strands in four folded cords form alternating pairs of knots.
# A loose connected net reads as knotting instead of three isolated bamboo-like bands.
paths=[]
for i in range(8):
 group=i//2;side=-1 if i%2==0 else 1;x=centers[group]
 pts=[[x+side*.015,.85,side*.030]]
 nodes=[(x,.69,side)]
 if i not in [0,7]:
  pair=(i-1)//2;nodes.append((-.18+.18*pair,.49,-1 if i%2 else 1))
 else:nodes.append((x+side*.045,.49,side))
 nodes.append((x,.29,side))
 for cx,y,hand in nodes:
  # Compact opposing wraps with open approaches; cord paths remain continuous through each knot.
  phase=0 if hand==1 else math.pi
  pts += [[cx+.025*math.cos(phase+hand*t),y-.032*t/(2*math.pi),.023*math.sin(phase+hand*t)] for t in np.linspace(0,2*math.pi,15)]
 pts += [[x+side*.025,.12,0]]
 paths.append(pts)
for group,x in enumerate(centers):
 # One continuous folded cord: up one strand, over dowel, down the other.
 left=paths[group*2];right=paths[group*2+1]
 arch=[[x-.015+.030*t/math.pi,.86+.040*math.sin(t),-.030*math.cos(t)] for t in np.linspace(0,math.pi,13)]
 tube('continuous knotted net cord',left[::-1]+arch+right,.012,cord if group%2==0 else shade,6)
S['notes']=['Original macrame sample uses four continuous folded cords suspended on a dowel and joined in alternating pairs to form open diamond netting with fringe. Compact knots are deliberately simplified volumes, not a named knot tutorial or exact commercial pattern. No disconnected rings or separate floating wraps. Suspension cords attach to dowel and hanging ring; no plant or pot promised.']

scene('glass-etching',(4,4,11))
# One hollow glass with a broad original frosted diamond and a closed supplies jar.
lathe('glass wall',[(.15,.0),(.17,.02),(.19,.54),(.18,.55),(.169,.53),(.149,.03),(.15,.0)],'#BDD1D0',40)
S['parts'][-1]['transparent']=True
# Grounded thick base and lip; glass has open hollow interior.
lathe('glass base',[(0,0),(.15,0),(.17,.02),(.15,.04),(0,.04)],'#A9C1C4',40)
lathe('glass rim',[(.180,.53),(.193,.54),(.187,.557),(.173,.548),(.180,.53)],'#9EBABC',40)
# Motif conforms to the cylindrical front wall. Opaque frost, not painted-on translucent sticker.
verts=[]
for y,w in [(.16,0),(.25,.36),(.35,0)]:
 for a in [-w,w]:verts.append([(.16+y*.055)*math.sin(a),y,(.16+y*.055)*math.cos(a)])
mesh('frosted diamond',verts,[[0,2,4],[1,5,3],[2,3,5,4]],'#EEF0DD');S['parts'][-1]['double_sided']=True;S['parts'][-1]['flat_paint']=True
# Small sealed etching-supply jar without chemical instructions or product branding.
start=len(S['parts']);lathe('closed etching jar',[(0,0),(.09,0),(.105,.025),(.105,.20),(.09,.23),(0,.23)],'#C5BFA4',32)
lathe('jar lid',[(0,.23),(.115,.23),(.115,.265),(0,.265)],'#798F90',32)
for p in S['parts'][start:]:p['vertices']=(np.array(p['vertices'])+[.35,0,.06]).tolist()
box('neutral jar label',(.35,.125,.165),(.13,.075,.006),'#E8DFBF')
S['notes']=['Original hollow glass has grounded base, open rim and frosted geometric motif attached to its front wall. Closed plain supplies jar suggests the etching process without a chemical label, pouring, recipe or brand. Exact etchant, glass shape and class kit are not promised.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
