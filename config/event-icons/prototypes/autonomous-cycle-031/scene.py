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
 mesh(name,verts,faces,color)
def ball(name,c,r,color):
 # Smooth six-ring sphere; illustrative geometry, not a proxy joint.
 x,y,z=c;n=24;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
def rounded_outline(w,h,r,n=8):
 return [(cx+r*math.cos(a),cy+r*math.sin(a)) for cx,cy,start in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)] for a in np.linspace(math.radians(start),math.radians(start+90),n)]
def ring_y(name,c,outer,inner,height,col,n=48):
 x,y,z=c;v=[]
 for yy,rr in [(y,outer),(y+height,outer),(y,inner),(y+height,inner)]:
  for t in np.linspace(0,2*math.pi,n,endpoint=False):v.append([x+rr*math.cos(t),yy,z+rr*math.sin(t)])
 faces=[]
 for i in range(n):
  j=(i+1)%n;faces.extend([[i,n+i,n+j,j],[2*n+i,2*n+j,3*n+j,3*n+i],[i,j,2*n+j,2*n+i],[n+i,3*n+i,3*n+j,n+j]])
 mesh(name,v,faces,col)

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat


def transform(start,angle=0,offset=(0,0,0)):
 a=math.radians(angle);m=np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
 for p in S['parts'][start:]:p['vertices']=(np.array(p['vertices'])@m.T+offset).tolist()

def actor(x,angle,skin,shirt,pants,hair,reach=False):
 start=len(S['parts']);z=0
 box('performer pelvis',(0,.855,0),(.28,.20,.19),pants)
 extrude('performer shirt',[(-.15,.88),(.15,.88),(.21,1.29),(-.21,1.29)],-.11,.11,shirt)
 rod('neck',(0,1.28,0),(0,1.38,0),.055,skin)
 oval('head hair',(0,1.49,0),.135,[.90,1.12,.87],hair,True)
 oval('face',(0,1.475,.047),.113,[.88,1.06,.85],skin,True)
 for sx in [-1,1]:
  shoulder=np.array([sx*.18,1.25,0]);elbow=shoulder+np.array([sx*.075,-.21,.19]);wrist=elbow+np.array([-sx*.04,.17,.162])
  if reach and sx==1:
   u=np.array([0,.07,.284]);u*=np.linalg.norm([.075,.21,.19])/np.linalg.norm(u);v=np.array([0,.05,.233]);v*=np.linalg.norm([.04,.17,.162])/np.linalg.norm(v);elbow=shoulder+u;wrist=elbow+v
  rod('continuous short sleeve',shoulder,shoulder+(elbow-shoulder)*.60,.053,shirt,16,r2=.046)
  rod('upper arm',shoulder+(elbow-shoulder)*.56,elbow,.041,skin,16,r2=.037)
  rod('forearm',elbow,wrist,.037,skin,16,r2=.029)
  oval('open hand',wrist+[0,.047,.013],.044,[.68,1.35,.50],skin,True)
  hip=np.array([sx*.084,.84,0]);knee=np.array([sx*.135,.46,0]);ankle=np.array([sx*.186,.09,0])
  rod('trouser thigh',hip,knee,.071,pants,16,r2=.060);rod('trouser shin',knee,ankle,.060,pants,16,r2=.045)
  box('shoe',(ankle[0],.043,.045),(.105,.086,.235),'#455B68')
 for xx in [-.035,.035]:rod('eye',(xx,1.497,.145),(xx,1.497,.151),.010,'#514A45',12);S['parts'][-1]['flat_paint']=True
 transform(start,angle,(x,0,0))
scene('stage-combat',(.25,1.5,10))
flat_extrude('stage',rounded_outline(2.0,1.15,.16),-.13,0,'#A27965')
actor(-.55,48,'#BD8767','#649AAB','#66769B','#494540',True)
actor(.55,-48,'#E6B28B','#CE967D','#687E72','#5E4B42')
S['measurements']=dict(shoe_bottom=0,platform_top=0,person_height=1.641,neck_exposure=.045,upper_arm_radius=.041,thigh_radius=.071,upper_arm_length=float(np.linalg.norm([.075,.21,.19])),forearm_length=float(np.linalg.norm([.04,.17,.162])),bilateral_leg_lengths_equal=True,actor_centers=1.1)
S['notes']=['Two original actors rehearse a separated open-handed defensive reaction on a stage. Neither actor strikes the other. Both shoes contact a common platform, fixed paired limb vectors preserve equal lengths. No copied pose, contact maneuver, exact fight technique or equipment guarantee.']

# An original A-style mandolin, with an actual hollow box and paired sound holes.
from shapely.geometry import Polygon,LineString
from shapely.ops import triangulate
scene('mandolin',(1.6,.4,10))
# Bezier-sampled teardrop contour; bottom to shoulders to narrow neck.
def bez(a,b,c,d,n=12):
 return [tuple((1-t)**3*np.array(a)+3*(1-t)**2*t*np.array(b)+3*(1-t)*t*t*np.array(c)+t**3*np.array(d)) for t in np.linspace(0,1,n,endpoint=False)]
outline=bez((0,.02),(.16,.02),(.16,.16),(.075,.245))+bez((.075,.245),(.037,.28),(.023,.31),(.020,.33))+[(-.020,.33)]+bez((-.020,.33),(-.023,.31),(-.037,.28),(-.075,.245))+bez((-.075,.245),(-.16,.16),(-.16,.02),(0,.02))
poly=Polygon(outline);assert poly.exterior.is_ccw
holes=[]
for sx in [-1,1]:
 pts=[(sx*(.077+.012*math.sin(t*2*math.pi)),.115+t*.110) for t in np.linspace(0,1,15)]
 holes.append(LineString(pts).buffer(.005,resolution=5))
front=poly
for h in holes:front=front.difference(h)
verts=[];faces=[]
for tr in triangulate(front):
 if not front.covers(tr.representative_point()):continue
 pts=list(tr.exterior.coords)[:-1];pts=pts if tr.exterior.is_ccw else pts[::-1];i=len(verts);verts +=[[x,y,.023] for x,y in pts];faces.append([i,i+1,i+2])
mesh('soundboard',verts,faces,'#D79A57');S['parts'][-1]['flat_paint']=True
# Back and outer ribs enclose a shallow body; front apertures remain genuine holes.
extrude('body back',outline,-.026,-.021,'#9D6847')
v=[[x,y,z] for z in [-.021,.023] for x,y in outline];n=len(outline);mesh('body ribs',v,[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)],'#AF784D')
extrude('neck',[(-.022,.282),(.022,.282),(.014,.492),(-.014,.492)],-.008,.022,'#835A45')
extrude('fingerboard',[(-.019,.274),(.019,.274),(.013,.49),(-.013,.49)],.022,.027,'#465662')
extrude('headstock',[(-.014,.49),(.014,.49),(.035,.58),(.025,.668),(-.025,.668),(-.035,.58)],-.019,.011,'#765A49')
box('nut',(0,.49,.031),(.034,.006,.010),'#E7DBC1')
box('bridge feet',(0,.135,.028),(.086,.013,.010),'#574F45')
box('bridge saddle',(0,.137,.040),(.080,.008,.017),'#655849')
extrude('tailpiece',[(-.018,.025),(.018,.025),(.020,.080),(-.020,.080)],.025,.032,'#B7C5CA')
for sy in [.552,.580,.608,.636]:
 for sx in [-1,1]:
  rod('tuner shaft',(sx*.020,sy,-.004),(sx*.044,sy,-.004),.003,'#A5B5BA',8)
  oval('tuner button',(sx*.047,sy,-.004),.009,[.80,1,.55],'#DFDED1',True)
for y in [.31,.34,.37,.40,.43,.455,.475]:box('fret',(0,y,.029),(.032,.002,.002),'#AFB6B1')
for course in [-1.5,-.5,.5,1.5]:
 for pair in [-1,1]:
  x=course*.010+pair*.00135
  rod('paired string',(x,.045,.034),(x,.137,.050),.00085,'#E6D6AE',6)
  rod('paired string',(x,.137,.050),(x*.74,.49,.037),.00085,'#E6D6AE',6)
  rod('paired string',(x*.74,.49,.037),(np.sign(x)*.016,.552+(.028*([(-1.5,-1),(-1.5,1),(-.5,-1),(-.5,1),(.5,-1),(.5,1),(1.5,-1),(1.5,1)].index((course,pair))%4)),.015),.00065,'#E6D6AE',6)
for p in S['parts']:
 if p['name'] in ['paired string','fret','headstock','neck','fingerboard','bridge saddle','bridge feet']:p['flat_paint']=True
S['measurements']=dict(overall_length=.648,body_width_approx=.254,body_depth=.049,scale_length=.353,courses=4,strings=8,tuning_buttons=8,sound_holes=2)
S['notes']=['Original unbranded A-style silhouette, dimensions approximated from Eastman MD305: 13 7/8in scale,10in width and1 7/8in depth. Soundboard is simplified flat but has two actual apertures opening into a shallow body. Four paired courses cross the raised bridge to the tailpiece; eight tuning buttons. Tiny winding hardware and full23frets omitted.']

# Tilt the whole instrument as one rigid object to give its body more pixels.
a=math.radians(-28);rot=np.array([[math.cos(a),-math.sin(a),0],[math.sin(a),math.cos(a),0],[0,0,1]])
for part in S['parts']:part['vertices']=((np.array(part['vertices'])-[0,.345,0])@rot.T+[0,.345,0]).tolist()
S['measurements']['whole_instrument_z_rotation_degrees']=-28

scene('blood-pressure-cuff',(2,4,9))
# Rolled cuff resting on its cylindrical side, with open bore toward the viewer.
start=len(S['parts']);ring_y('cuff fabric',(0,0,0),.054,.045,.12,'#526978',n=32)
p=S['parts'][-1];p['vertices']=[[x-.090,z+.054,y-.060] for x,y,z in p['vertices']]
# Rotation (x,y,z)->(x,z,y) reverses handedness.
p['faces']=[list(reversed(f)) for f in p['faces']]
box('cuff overlap',(-.090,.108,-.014),(.060,.010,.090),'#697F8D')
# Wedge monitor, a broad display on its sloped upper face.
vs=[[x,y,z] for x in [.012,.158] for y,z in [(0,-.065),(0,.075),(.035,.075),(.085,-.065)]]
mesh('monitor housing',vs,[list(reversed(f)) for f in [[0,3,2,1],[4,5,6,7],[0,4,7,3],[1,2,6,5],[0,1,5,4],[3,7,6,2]]],'#D7DFDC')
def topy(z):return .035+(.075-z)*(.05/.14)
points=[(.030,-.043),(.139,-.043),(.139,.021),(.030,.021)]
# Ordering normal toward upper face.
verts=[[x,topy(z)+.0015,z] for x,z in points]
mesh('display bezel',verts,[[3,2,1,0]],'#5A6F76');S['parts'][-1]['flat_paint']=True
points=[(.039,-.034),(.130,-.034),(.130,.013),(.039,.013)]
mesh('LCD',[[x,topy(z)+.002,z] for x,z in points],[[3,2,1,0]],'#B4CCB4');S['parts'][-1]['flat_paint']=True
for z in [-.022,-.002]:
 for x in [.067,.100]:
  points=[(x-.009,z-.002),(x+.009,z-.002),(x+.009,z+.002),(x-.009,z+.002)]
  mesh('idle display dashes',[[xx,topy(zz)+.0025,zz] for xx,zz in points],[[3,2,1,0]],'#536B62');S['parts'][-1]['flat_paint']=True
rod('start button',(.085,topy(.049),.049),(.085,topy(.049)+.004,.049),.013,'#55A4AC',24)
# A single continuous air tube meets the cuff and left monitor port.
path=[[-.042,.052,.015],[-.015,.020,.040],[-.023,.009,.094],[.004,.009,.112],[.037,.012,.095],[.021,.025,.030],[.012,.025,.020]]
for a,bb in zip(path,path[1:]):rod('air tube',a,bb,.004,'#526978',12)
for pnt in path[1:-1]:oval('tube bend',pnt,.004,[1,1,1],'#526978',True)
S['measurements']=dict(cuff_outer_diameter=.108,cuff_inner_diameter=.090,cuff_width=.12,monitor_width=.146,monitor_depth=.140,monitor_height=.085,cuff_and_monitor_bottom=0,tube_radius=.004)
S['notes']=['Original generic tabletop device with a rolled fabric cuff, actual open bore, single connected air hose, sloped LCD monitor and neutral idle dashes. OMRON construction reference establishes cuff/tube/monitor relationship; no brand, actual reading, ECG trace, diagnosis or exact offered device is claimed.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-031')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
