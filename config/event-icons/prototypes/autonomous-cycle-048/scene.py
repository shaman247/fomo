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

scene('marimba',(5,4,9))
# One illustrative chromatic octave: eight naturals, five accidentals in2+3 groups.
xs=np.linspace(-.68,.68,8)
for i,x in enumerate(xs):
 length=.52-.027*i
 box('wood natural bar',(x,1.03,.17),(.174,.038,length),'#A76E4D')
 # Hollow tube open under the bar, closed at its lower end.
 bottom=.29+.048*i;top=.967;r=.046
 lathe('natural resonator',[(0,bottom),(r,bottom),(r,top),(r-.006,top),(r-.006,bottom+.008),(0,bottom+.008)],'#C6A770',20);shift_last(dx=x,dz=.17)
 # Supporting suspension cords pass through both nodal regions (simplified straight).
for z in [.08,.26]:rod('suspension cord',(-.81,1.014,z),(.81,1.014,z),.004,'#65564A',8)
for i in [0,1,3,4,5]:
 x=(xs[i]+xs[i+1])/2;length=.41-.024*i
 box('wood accidental bar',(x,1.089,-.13),(.15,.038,length),'#865B45')
 bottom=.36+.048*i;top=1.026;r=.041
 lathe('accidental resonator',[(0,bottom),(r,bottom),(r,top),(r-.006,top),(r-.006,bottom+.008),(0,bottom+.008)],'#C6A770',20);shift_last(dx=x,dz=-.13)
for z in [-.20,-.045]:rod('raised suspension cord',(-.81,1.071,z),(.81,1.071,z),.004,'#65564A',8)
for z in [-.39,.48]:box('long wooden rail',(0,.985,z),(1.68,.10,.055),'#8C5E45')
for x in [-.82,.82]:
 box('frame end',(x,1.015,.04),(.066,.13,.96),'#A77654')
 for z in [-.27,.36]:
  rod('vertical stand',(x,.08,z),(x,.95,z),.032,'#596C70',12)
  box('foot',(x,.04,z),(.19,.08,.18),'#596C70')
 rod('end brace',(x,.19,-.27),(x,.89,.36),.020,'#718287',12)
box('lower crossbar',(0,.29,.36),(1.67,.035,.035),'#596C70')
# Two illustrative resting mallets lie across the upper keyboard. Heads meet the bars.
for x,z in [(-.30,.29),(.12,.19)]:
 rod('mallet shaft',(x,1.099,z),(x+.43,1.058,z-.02),.009,'#D2AF7E',12)
 ellipsoid('yarn mallet head',(x,1.099,z),(.047,.05,.047),'#A1BBC1')
for p in S['parts']:
 if any(w in p['name'] for w in ['resonator','cord','stand','brace','crossbar']):p['flat_paint']=True
S['measurements']=dict(natural_count=8,accidental_count=5,pattern='2+3, C-major chromatic octave',bar_y=1.03,accidental_y=1.089,lower_bar_bottom=1.011,upper_bar_bottom=1.070,resonators_open_top=True,resonators_closed_bottom=True,support_feet_y=0)
S['notes']=['Original generic wooden-bar marimba, one octave rather than a product range. Two levels with2+3 accidental grouping, suspended hollow closed-bottom resonators and a common braced stand. No motor, vibraphone damper pedal or playing hands. Simplified rail/cord support is illustrative; tuning, exact node placement and acoustic performance are not simulated. Two resting mallets are illustrative accessories, not event-supplied equipment.']

scene('contra-dance',(6,4,10));alljoints={}
# A small hands-four formation, original four-person scene. All dancers grounded.
for index,(x,z,angle,col,skincol) in enumerate([(-.47,-.44,math.pi/2,'#579B98','#C38D66'),(.47,-.44,-math.pi/2,'#DCAA65','#976B50'),(-.47,.44,math.pi/2,'#B9818F','#AC7857'),(.47,.44,-math.pi/2,'#748CAE','#D5A882')]):
 first=len(S['parts']);skin=skincol;pants='#526275';shirt=col;hair=['#45434A','#54453D','#3D3E45','#66574D'][index];js={}
 for side in [-1,1]:
  hip=np.array([side*.10,.865,0]);ankle=np.array([side*.17,.09,.035]);knee=joint(hip,ankle,.42,.40,[0,0,1])
  capsule('trouser thigh',hip,knee,.065,.059,pants);capsule('trouser shin',knee,ankle,.059,.043,pants);foot(side*.17,.083,'#D3D3C7');js[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
 torso('waist',[(.79,.13,.085),(.92,.142,.089)],pants)
 torso('shirt',[(.875,.146,.10),(1.11,.165,.096),(1.26,.164,.085),(1.29,.069,.06)],shirt)
 capsule('short neck',(0,1.27,0),(0,1.335,0),.048,.046,skin);human_head((0,1.445,0))
 # Hands extend toward the center, with a deliberate clear space between people.
 for side in [-1,1]:js[str(side)].update(arm((side*.16,1.24,0),(side*.255,1.00,.31),(side*.4,-.2,1),(side*.27,.987,.37),shirt))
 co,si=math.cos(angle),math.sin(angle);rot=np.array([[co,0,si],[0,1,0],[-si,0,co]])
 for p in S['parts'][first:]:
  p['vertices']=(np.array(p['vertices'])@rot.T+[x,0,z]).tolist();p['person']=index
  p['flat_paint']=True
 alljoints[str(index)]=dict(joints=js,center=[x,0,z],yaw=angle)
S['measurements']=dict(formation='two opposing pairs; illustrative approach, no named figure or grip',people=4,joints=alljoints,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,arm_radius=.039,thigh_radius=.065,foot_plane=0)
S['notes']=['Original four-person opposing formation indicates interacting contra lines rather than isolated solo steps. Each dancer has matched paired limbs, short neck, flat skin color and two feet on the common floor. Hands approach but do not claim a connected grip or exact choreography. No assigned gender roles, costumes, physical requirements or partner requirement.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
if __name__=='__main__':print('Built2 original3D scenes; flat concepts are in planar_art.py')
