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

scene('wine-chocolate-pairing',(5,4,10))
# Illustrative stemware, hollow bowl with contained liquid, beside segmented chocolate.
lathe('glass foot',[(0,0),(.062,0),(.066,.008),(.051,.013),(0,.013)],'#ADC6CA',40);shift_last(dx=-.095)
rod('glass stem',(-.095,.012,0),(-.095,.111,0),.0075,'#ADC6CA',20)
lathe('hollow wine bowl',[(0,.104),(.025,.115),(.059,.146),(.075,.190),(.072,.236),(.060,.28),(.055,.28),(.067,.234),(.070,.19),(.054,.15),(.02,.121),(0,.116)],'#B6CCD0',40);shift_last(dx=-.095);S['parts'][-1]['transparent']=True
lathe('rose wine',[(0,.116),(.019,.121),(.054,.151),(.069,.19),(.068,.211),(0,.211)],'#C77F8B',40);shift_last(dx=-.095);S['parts'][-1]['flat_paint']=True
rod('wine surface',(-.095,.211,0),(-.095,.2111,0),.068,'#DFA4AE',40);S['parts'][-1]['flat_paint']=True
box('chocolate tablet base',(.102,.009,.035),(.126,.018,.15),'#70503E')
for x in [.069,.135]:
 for z in [-.002,.073]:
  # Raised pieces join the continuous chocolate tablet below.
  y0=.018;y1=.040;w=.057;d=.064;v=[[x+sx*w/2,y0,z+sz*d/2] for sx,sz in [(-1,-1),(1,-1),(1,1),(-1,1)]]+[[x+sx*(w-.012)/2,y1,z+sz*(d-.012)/2] for sx,sz in [(-1,-1),(1,-1),(1,1),(-1,1)]]
  mesh('chocolate segment',v,[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],'#8C6048');S['parts'][-1]['faces']=[list(reversed(f)) for f in S['parts'][-1]['faces']]
S['measurements']=dict(glass_height=.28,bowl_max_radius=.075,wine_surface=.211,glass_base=0,chocolate_base=0,chocolate_top=.04)
S['notes']=['Generic original wine glass and chocolate tablet. Glass foot and chocolate base meet y0; stem joins bowl and base, hollow walls contain a horizontal wine surface. Transparent projection uses an outline and pale tint, not optical simulation. Pink wine matches the source rosé pairing but quantities, brands, chocolate form and serving details are illustrative.']

scene('rooftop-water-tower',(5,3,10))
# Original rooftop wooden cylinder, external steel hoops and conical roof.
box('roof slab',(0,.07,0),(4.3,.14,3.8),'#71858A')
for x in [-1.08,1.08]:
 for z in [-1.08,1.08]:box('steel leg',(x,.74,z),(.17,1.20,.17),'#50676E')
for z in [-1.08,1.08]:
 rod('cross brace',(-1.08,.20,z),(1.08,1.28,z),.065,'#637B80');rod('cross brace',(1.08,.20,z),(-1.08,1.28,z),.065,'#637B80')
for x in [-1.08,1.08]:
 rod('side brace',(x,.20,-1.08),(x,1.28,1.08),.065,'#637B80');rod('side brace',(x,.20,1.08),(x,1.28,-1.08),.065,'#637B80')
box('support beam',(0,1.29,-1.08),(2.9,.18,.2),'#50676E');box('support beam',(0,1.29,1.08),(2.9,.18,.2),'#50676E')
lathe('wood staves',[(0,1.38),(1.52,1.38),(1.52,4.05),(0,4.05)],'#B48A60',48)
for y in [1.60,2.25,2.92,3.73]:lathe('steel hoop',[(1.522,y-.043),(1.56,y-.043),(1.56,y+.043),(1.522,y+.043),(1.522,y-.043)],'#677F84',48)
# Broad wood paint and steel hoops carry recognition without tiny stave rods.
for p in S['parts']:
 if any(k in p['name'] for k in ['steel','brace','beam']):p['flat_paint']=True
lathe('conical cover',[(0,4.05),(1.66,4.05),(1.66,4.14),(.07,4.98),(0,4.98)],'#7D9197',48)
S['measurements']=dict(tank_radius=1.52,tank_bottom=1.38,tank_top=4.05,cover_top=4.98,leg_bottom=.14,leg_top=1.34,roof_top=.14,beam_top=1.38)
S['notes']=['Four steel legs bear on a small rooftop slab, with crossing braces and two beams meeting the wood tank bottom. External hoops surround a closed stave cylinder under a conical cover. Illustration omits plumbing, access ladder and hidden internal construction; not an engineering plan or a specific observed tower.']

scene('diabolo',(12,5,6))
# Two hollow cups share the same z axle; string sits under the central roller.
for side in [-1,1]:
 lathe('hollow cup',[(.010,.010),(.018,.019),(.039,.040),(.064,.066),(.062,.071),(.057,.070),(.034,.043),(.014,.023),(.008,.022),(.010,.010)],'#8E85B9',40)
 p=S['parts'][-1];p['vertices']=[[x,.14+z,side*y] for x,y,z in p['vertices']]
 # Y/Z swap has negative determinant; side mirror compensates when negative.
 if side==1:p['faces']=[list(reversed(f)) for f in p['faces']]
rod('central steel axle',(0,.14,-.024),(0,.14,.024),.008,'#8AA1A7',24)
for side in [-1,1]:rod('handstick',(side*.16,.27,0),(side*.20,.048,.018),.0075,'#B78864',16)
# Tangent string segments approach the underside of the roller in its XY plane.
radius=.01066;theta=math.atan2(.13,-.16)+math.acos(radius/math.hypot(.16,.13))
pts=[[-.16,.27,0]]+[[radius*math.cos(t),.14+radius*math.sin(t),0] for t in np.linspace(theta,3*math.pi-theta,17)]+[[.16,.27,0]]
for a,c in zip(pts,pts[1:]):rod('string',a,c,.0026,'#D7B867',10);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(cup_outer_radius=.064,cup_width=.142,axle_radius=.008,axle_y=.14,string_center_min=.12934,string_lowest=.12674,roller_string_clearance=.00006,stick_length=.225,hand_positions='omitted at lower stick ends')
S['notes']=['Hollow opposed cups form an hourglass spool around a common steel roller. String passes through the central gap and under the roller, leading to two stick tips; sticks are an equipment diagram with grips/hands omitted. Approximate shortened display lengths improve recognition, not a specification or prescribed operating posture. No single-string conventional yo-yo mechanism.']

scene('hip-hop-dance',(2,1,20));skin='#B77E59';pants='#596E88';shirt='#DCA35D';hair='#413E43';joints={}
for side in [-1,1]:
 hip=np.array([side*.11,.70,0]);ankle=np.array([side*.36,.09,.06]);knee=joint(hip,ankle,.42,.40,[side*.25,0,1])
 capsule('loose trouser thigh',hip,knee,.081,.073,pants);capsule('loose trouser shin',knee,ankle,.073,.056,pants)
 foot(side*.36,.115,'#DDD9C9');joints[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
torso('waist',[(.63,.15,.095),(.76,.153,.10)],pants)
torso('loose shirt',[(.71,.168,.109),(.84,.158,.10),(1.06,.187,.103),(1.14,.17,.087),(1.17,.072,.06)],shirt)
capsule('neck',(0,1.15,0),(0,1.225,0),.049,.047,skin);human_head((0,1.335,0))
for side,wrist,hint,end in [(-1,[-.40,.91,.13],[-1,-.2,0],[-.44,.877,.15]),(1,[.025,1.105,.23],[1,0,0],[-.032,1.105,.235])]:joints[str(side)].update(arm(np.array([side*.175,1.11,0]),np.array(wrist),hint,np.array(end),shirt))
for p in S['parts']:p['flat_paint']=True
S['measurements']=dict(joints=joints,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.081,foot_plane=0,hip_height=.70,pose='grounded bent-knee rhythmic groove, original')
S['notes']=['Original grounded hip-hop-inspired groove with bent knees, angular offset arms, loose clothing and street shoes. Both feet contact y0 and paired bone lengths are fixed. Ailey primary describes rhythmic combinations/popping/locking/breaking and shows bent-arm movement; this original pose is not copied choreography or a universal hip-hop stance. One skin paint, short neck attachments and arms narrower than legs. Adult-shaped emblem can label youth classes without asserting participant ages.']

scene('tugboat',(6,4,10))
# Generic compact harbor tug; below-water geometry omitted from visible emblem.
outline=[(-.61,-.16),(-.52,-.225),(.37,-.225),(.57,-.15),(.65,0),(.57,.15),(.37,.225),(-.52,.225),(-.61,.16)]
v=[[x*.83,-.12,z*.80] for x,z in outline]+[[x,.18,z] for x,z in outline];n=len(outline)
mesh('rounded working hull',v,[list(range(n-1,-1,-1)),list(range(n,n*2))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)],'#465E69');S['parts'][-1]['faces']=[list(reversed(f)) for f in S['parts'][-1]['faces']]
flat_extrude('deck',outline,.18,.205,'#A8ADA1')
box('aft engine house',(-.25,.302,0),(.47,.195,.28),'#DAC9A2');box('aft roof',(-.25,.405,0),(.50,.025,.31),'#85979A')
box('wheelhouse',(.14,.409,0),(.37,.408,.31),'#E5D7B8');box('wheelhouse roof',(.14,.631,0),(.43,.035,.36),'#809397')
# Window panels attach to both cabin sides and forward wall.
for z in [-.157,.157]:
 for x in [.045,.20]:box('cabin window',(x,.512,z),(.115,.133,.008),'#668C9B')
box('forward window',(.329,.515,0),(.009,.135,.24),'#668C9B')
lathe('open exhaust stack',[(.052,.4175),(.052,.746),(.038,.746),(.038,.4175),(.052,.4175)],'#AD7656',32);shift_last(dx=-.25)
lathe('stack rim',[(.052,.717),(.060,.717),(.060,.746),(.038,.746),(.038,.735),(.052,.735),(.052,.717)],'#495B62',32);shift_last(dx=-.25)
for z in [-.231,.231]:
 for x in [-.40,-.10,.30]:torus('tire fender',(x,.137,z),.055,.018,'#374B53',24,8)
# Bow rope bumper and stern towing bollard distinguish tug from passenger launch.
ellipsoid('bow rope fender',(.619,.159,0),(.052,.078,.11),'#B19674')
rod('stern tow post',(-.49,.205,0),(-.49,.30,0),.027,'#596F74');rod('tow post crossbar',(-.49,.282,-.06),(-.49,.282,.06),.021,'#596F74')
flat_extrude('water patch',[(-.74,-.28),(-.51,-.32),(.36,-.30),(.73,-.15),(.76,.15),(.39,.31),(-.5,.32),(-.76,.20)],-.008,.006,'#8BBAC0')
S['measurements']=dict(hull_length=1.26,beam=.45,water_y=.006,deck_top=.205,wheelhouse_bottom=.205,wheelhouse_roof=.6485,stack_top=.746)
S['notes']=['Original generic harbor tug with compact rounded hull, forward wheelhouse, aft deckhouse, stack, protective tire/rope fenders and stern tow post. Water plane intersects lower hull, depicting afloat support rather than a land contact. No crew, propeller, engine internals, towing load or navigation simulation; no smoke implying steam. Does not reproduce W.O. Decker exactly or guarantee excursion route.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-047/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
