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

scene('plant-swap',(1,4,12))
for side,col in [(-1,'#CE8963'),(1,'#79A8AB')]:
 first=len(S['parts']);x=side*.29
 lathe('nursery pot',[(0,0),(.14,0),(.19,.24),(.20,.24),(.20,.285),(.172,.285),(.172,.25),(.12,.035),(0,.035)],col,32)
 for p in S['parts'][first:]:p['vertices']=(np.array(p['vertices'])+[x,0,0]).tolist()
 rod('soil',(x,.235,0),(x,.25,0),.165,'#796553',28)
 rod('stem',(x,.25,0),(x,.58,0),.011,'#65914E',12)
 for dx,yy,zz in [(-.13,.46,.025),(.14,.55,-.01)]:
  panel('leaf',[(x,yy-.08,0),(x+dx*.25,yy+.01,zz),(x+dx,yy+.075,zz),(x+dx*.90,yy-.025,zz),(x+dx*.35,yy-.07,zz)],'#71A75E' if dx<0 else '#90B56B');S['parts'][-1]['double_sided']=True
# Exchange arrows are editorial floating diagram marks, not physical equipment.
for points in [[(-.21,.78),( .16,.78),(.16,.84),(.30,.75),(.16,.66),(.16,.72),(-.21,.72)],[(.21,-.10),(-.16,-.10),(-.16,-.04),(-.30,-.13),(-.16,-.22),(-.16,-.16),(.21,-.16)]]:
 extrude('exchange arrow',points,.04,.05,'#7292B5');S['parts'][-1]['flat_paint']=True
S['measurements']=dict(pots=2,pot_bottom=0,soil_surface=.25,stem_base=.25,pot_centers=[-.29,.29],pot_outer_radius=.20)
S['notes']=['Original two generic seedling pots, rooted stems and attached leaves. Two opposite arrow annotations convey exchange. No botanical species or exact container supply claim. Common surface y=0 supports both pots; arrows are diagram marks.']
scene('calaveras',(0,1,16))
outline=[(-.21,.08),(.21,.08),(.25,.14),(.25,.29),(.34,.37),(.38,.54),(.35,.70),(.25,.82),(0,.87),(-.25,.82),(-.35,.70),(-.38,.54),(-.34,.37),(-.25,.29),(-.25,.14)]
from shapely.geometry import Point, box as shape_box
from shapely.affinity import scale as shape_scale, translate as shape_translate
from shapely.geometry.polygon import orient
crown=shape_translate(shape_scale(Point(0,0).buffer(.36,quad_segs=16),yfact=.34/.36),yoff=.53)
shape=crown.union(shape_box(-.24,.08,.24,.39)).buffer(-.025).buffer(.025)
outline=list(orient(shape,sign=1).exterior.coords)[:-1]
extrude('decorative clay skull',outline,-.04,.04,'#F1EDEC')
# Original decorative face, not anatomically accurate skull or copied source pattern.
for x in [-.17,.17]:
 for a in np.linspace(0,2*math.pi,8,endpoint=False):
  rod('flower petal',(x+.086*math.cos(a),.55+.086*math.sin(a),.040),(x+.086*math.cos(a),.55+.086*math.sin(a),.048),.043,'#69A3A8',16)
 rod('flower eye',(x,.55,.040),(x,.55,.052),.064,'#645D84',24)
 for y in [.325]:rod('cheek dot',(x,y,.040),(x,y,.047),.025,'#CD7095',16)
extrude('nose',[(-.04,.36),(.04,.36),(0,.43)],.040,.049,'#665B75')
extrude('forehead diamond',[(0,.70),(.055,.755),(0,.81),(-.055,.755)],.040,.05,'#CD7095')
# Teeth are decoration engraved as connected broad marks, not detailed anatomy.
box('mouth',(0,.23,.045),(.31,.02,.010),'#9C8582')
for x in [-.10,0,.10]:box('tooth divider',(x,.235,.046),(.012,.08,.012),'#9C8582')
for p in S['parts']:
 if p['name']!='decorative clay skull':p['flat_paint']=True
S['measurements']=dict(base_front=.04,decoration_front=.052,base_thickness=.08,eyes=2,eye_center_spacing=.34)
S['notes']=['Original frontal decorated calavera plaque with flower eye motifs and colored forehead detail, informed by explicit clay calavera program and its craft photograph. No photo tracing, edible sugar claim, exact supplied materials or anatomical accuracy. Decorative pieces attach to the front surface.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
if __name__=='__main__':print('Built plant exchange and decorated calavera scenes')
