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

scene('robot-combat',(5,5,9))
# Original opposing toy-scale arena robots. Visual shells only, no mechanisms.
for index,(x,z,yaw,col) in enumerate([(-.38,-.13,math.pi/2,'#679FAC'),(.38,.13,-math.pi/2,'#CD9565')]):
 first=len(S['parts'])
 box('low chassis',(0,.11,0),(.31,.14,.38),col)
 for xx in [-.18,.18]:
  for zz in [-.12,.12]:
   rod('wheel',(xx-.028,.07,zz),(xx+.028,.07,zz),.07,'#4F6270',16)
   rod('hub',(xx-.030,.07,zz),(xx+.030,.07,zz),.024,'#98ADB0',12)
 # Hinged lifting plate represented as a solid closed prism, inactive at rest.
 vertices=[[-.12,.155,.045],[.12,.155,.045],[.12,.035,.30],[-.12,.035,.30],[-.12,.166,.045],[.12,.166,.045],[.12,.046,.30],[-.12,.046,.30]]
 mesh('hinged lifting plate',vertices,[[0,3,2,1],[4,5,6,7],[0,1,5,4],[3,7,6,2],[0,4,7,3],[1,2,6,5]],'#C2CCCA')
 if index==0:
  p=S['parts'][-1];angle=-.65;c0,s0=math.cos(angle),math.sin(angle);r0=np.array([[1,0,0],[0,c0,-s0],[0,s0,c0]]);origin=np.array([0,.162,.045]);p['vertices']=((np.array(p['vertices'])-origin)@r0.T+origin).tolist()
 rod('attached hinge',(-.14,.162,.045),(.14,.162,.045),.018,'#7B8E96',12)
 box('top panel',(0,.186,-.065),(.23,.012,.15),col)
 c,s=math.cos(yaw),math.sin(yaw);rot=np.array([[c,0,s],[0,1,0],[-s,0,c]])
 for p in S['parts'][first:]:p['vertices']=(np.array(p['vertices'])@rot.T+[x,0,z]).tolist();p['robot']=index
# No actual cage: broad common arena pad grounds the original pair.
box('arena pad',(0,-.016,0),(1.30,.032,.94),'#E2D5BC')
for p in S['parts']:
 if 'wheel' in p['name'] or 'hub' in p['name'] or 'hinge' in p['name']:p['flat_paint']=True
S['measurements']=dict(robots=2,wheels_per_robot=4,wheel_radius=.07,wheel_center_y=.07,arena_top=0,minimum_chassis_gap=.38,blue_plate_rotation=-.65)
S['notes']=['Two original generic low wheeled combat robots face each other with one raised and one resting hinged lifting plate. No specific competitor,brand,weight class,internal mechanism,power source or operating design. Common pad stands for arena floor,not a replica or full safety enclosure. No impact,sparks,fire or human depicted.']

scene('tunnel-book',(5,3,12))
# Four original cutout planes attached to zigzag side gussets; back is closed.
zs=[.30,.10,-.10,-.30];colors=['#D5AF76','#93B1A7','#77A2AF','#86B5C7']
for i,(z,col) in enumerate(zip(zs,colors)):
 if i==3:box('closed back sheet',(0,.37,z),(.72,.70,.009),col)
 else:
  # Rectangular portal cut out of one page; connected strips form its perimeter.
  box('page left',(-.335,.37,z),(.05,.70,.009),col);box('page right',(.335,.37,z),(.05,.70,.009),col)
  box('page top',(0,.695,z),(.62,.05,.009),col);box('page bottom',(0,.045,z),(.62,.05,.009),col)
  # Lower silhouettes joined to bottom border give true receding scene depth.
  outlines=[ [(-.31,.045),(.31,.045),(.31,.14),(.15,.18),(-.03,.12),(-.20,.24),(-.31,.18)], [(-.31,.045),(.31,.045),(.31,.27),(.16,.40),(-.04,.22),(-.21,.35),(-.31,.29)], [(-.31,.045),(.31,.045),(.31,.40),(.12,.54),(-.03,.41),(-.18,.57),(-.31,.39)] ]
  extrude('integral scenic paper',outlines[i],z-.0045,z+.0045,['#779876','#568B80','#597F9F'][i])
# Sun as a paper disc pasted directly to rear sheet, original landscape.
rod('paper sun',(.14,.575,-.293),(.14,.575,-.290),.072,'#EDC676',24)
for side in [-1,1]:
 pts=[]
 for i,z in enumerate([.30,.20,.10,0,-.10,-.20,-.30]):pts.append([side*(.36 if i%2==0 else .40),z])
 for j,((x,z),(xx,zz)) in enumerate(zip(pts,pts[1:])):
  panel('accordion gusset',[(x,.02,z),(xx,.02,zz),(xx,.72,zz),(x,.72,z)],'#D1C29F' if j%2==0 else '#E7D9B8');S['parts'][-1]['double_sided']=True
S['measurements']=dict(layers=4,layer_z=zs,gussets=2,page_bottom=.02,page_height=.70,outer_width=.72,depth=.60)
S['notes']=['Original four-layer landscape tunnel book with open front,three window/scenery planes,closed back and two connected accordion sides. Illustrated mountains/sun are original geometric paper shapes,not copied Prado or museum artwork. Dimensions are schematic,not a cutting template; no adhesive tabs or actual folding simulation.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
if __name__=='__main__':print('Built two original3D scenes')
