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
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]+[list(range(n-1,-1,-1)),list(range((len(levels)-1)*n,len(levels)*n))]
 mesh(name,verts,faces,col)

scene('line-dance',(0,1,20))
measure=[]
for dancer,(offset,skin,shirt,pants,hair) in enumerate([(-.83,'#A87555','#63A5A0','#556C8D','#45434A'),(0,'#E5B38A','#DCA267','#697899','#776056'),(.83,'#C48C68','#B58AA6','#4E777D','#4C4747')]):
 first=len(S['parts']);joints={}
 for side in [-1,1]:
  hip=np.array([side*.105+.06,.84,0]);footx=-.26 if side==-1 else .29;ankle=np.array([footx,.085,.018]);knee=joint(hip,ankle,.42,.40,[0,0,1])
  capsule('trouser thigh',hip,knee,.071,.061,pants);capsule('trouser shin',knee,ankle,.061,.047,pants)
  ellipsoid('shoe',(footx,.043,.075),(.079,.043,.136),'#E4D9BD');box('sole',(footx,.008,.075),(.145,.016,.235),'#C6BBA1')
  joints[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
 upper_first=len(S['parts'])
 torso('waist',[(.78,.133,.089),(.88,.137,.086)],pants)
 torso('shirt',[(.865,.142,.089),(1.03,.137,.087),(1.21,.171,.097),(1.29,.155,.081),(1.32,.075,.058)],shirt)
 capsule('neck',(0,1.30,0),(0,1.385,0),.049,.047,skin)
 for side in [-1,1]:
  shoulder=np.array([side*.165,1.265,0]);wrist=np.array([-.31 if side==-1 else .34,1.24 if side==-1 else 1.14,.15]);elbow=joint(shoulder,wrist,.285,.255,[side*.3,-1,.1])
  capsule('upper arm',shoulder,elbow,.039,.035,skin);capsule('forearm',elbow,wrist,.035,.028,skin)
  sleeve=shoulder+(elbow-shoulder)*.34;capsule('sleeve',shoulder,sleeve,.054,.046,shirt)
  hand=wrist+(wrist-elbow)/np.linalg.norm(wrist-elbow)*.046;capsule('hand',wrist,hand,.029,.030,skin)
  joints[str(side)].update(shoulder=shoulder.tolist(),elbow=elbow.tolist(),wrist=wrist.tolist())
 ellipsoid('head',(0,1.495,0),(.103,.133,.090),skin)
 for side in [-1,1]:ellipsoid('ear',(side*.10,1.49,-.005),(.018,.030,.017),skin)
 v=[];n=20
 for theta in np.linspace(0,1.28,6):
  for phi in np.linspace(0,2*math.pi,n,endpoint=False):v.append([.11*math.sin(theta)*math.cos(phi),1.495+.145*math.cos(theta),.097*math.sin(theta)*math.sin(phi)-.008])
 mesh('hair',v,[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(5) for i in range(n)],hair)
 for side in [-1,1]:ellipsoid('eye',(side*.033,1.508,.086),(.0075,.01,.005),'#4B4947')
 ellipsoid('nose',(0,1.484,.090),(.01,.013,.01),skin)
 for aa,bb in zip([(-.024,1.466),(-.012,1.457),(0,1.455),(.012,1.457)],[(-.012,1.457),(0,1.455),(.012,1.457),(.024,1.466)]):rod('smile',(aa[0],aa[1],.087),(bb[0],bb[1],.087),.004,'#825C4D',8)
 for p in S['parts'][upper_first:]:p['vertices']=(np.asarray(p['vertices'])+[.06,0,0]).tolist()
 for p in S['parts'][first:]:
  p['vertices']=(np.asarray(p['vertices'])+[offset,0,0]).tolist();p['flat_paint']=True;p['name']=f'dancer {dancer+1} '+p['name']
 measure.append(dict(dancer=dancer+1,offset_x=offset,upper_body_shift_x=.06,joints=joints,femur=.420,tibia=.400,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.071,foot_plane=0,visible_neck=.042))
S['measurements']=dict(dancers=measure,notes='Identical fixed skeleton lengths, pose and floor plane. Distinct skin, clothing and hair paint; no handhold. Posed generic synchronized side step, not a named choreography. No dynamic balance simulation or exhaustive mesh-collision proof.')
S['notes']=['Three unlinked dancers form a straight row and repeat the same grounded step. All six soles touch y=0. Paired segment lengths are fixed by inverse kinematics. Arms are thinner than thighs and skin uses one paint per dancer; neck endpoints overlap shirt and head. Group transforms preserve pose and contacts.']

scene('trail-stone-steps',(6,6,9))
# Single broad rocks overlap the preceding rock and are embedded into a cut earth bank.
# Units metres: rise .17, exposed run .36; slabs .54 deep, .17 tall.
for i in range(3):
 top=.17*(i+1);front=.60-.36*i;back=front-.54;bottom=top-.17
 outline=[(-.45,back+.03),(-.40,back),(.40,back+.018),(.45,back+.08),(.44,front-.04),(.37,front),(-.40,front-.008),(-.46,front-.07)]
 # Extrude an X/Z plan around vertical Y, keeping outward normals.
 extrude('stone '+str(i+1),outline,bottom,top,['#A8AEAE','#9EA8A8','#AAB2B0'][i]);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
 # Earth fills below and beside rock but leaves the tread and riser exposed.
 banktop=max(.018,top-.17);box('earth core '+str(i+1),(0,(-.12+banktop)/2,(front+back)/2),(1.10,banktop+.12,.54),'#B89A75')
 for side in [-1,1]:box('earth shoulder',(side*.535,(-.12+top-.08)/2,(front+back)/2),(.18,top+.04,.54),'#B89A75')
# One short upright trail marker is embedded beside the top tread, not a tool demonstration.
box('wooden trail marker',(-.55,.49,-.46),(.09,.42,.09),'#AD7957');box('plain blaze',(-.55,.59,-.413),(.055,.095,.004),'#DCE1C8')
S['measurements']=dict(rise=.17,run=.36,stone_depth=.54,stone_height=.17,width=.90,overlap=.18,side_bank_cover=.09,earth_base=-.12,stones=3)
S['notes']=['Three broad single-rock treads rise at .17 m increments with .36 m exposed runs and .18 m overlapping depth. Each .17 m thick rock bears on the preceding tread over the overlap and on earth behind it; there is no solid interpenetration. Side banks cover approximately .09 m of the rock edges. Earth banks and side shoulders support the stairway; all risers and treads are horizontal-plane simplifications with irregular plan outlines.','Generic original trail structure, not an actual Bear Mountain site or usable engineering design. Dimensions are illustrative within published trail-stair proportions. Marker is generic, without an official route color or arrow. No person or tool-use technique is depicted.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-043/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
