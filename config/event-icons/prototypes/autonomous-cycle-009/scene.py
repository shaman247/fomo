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
 x,y,z=c;n=16;rings=6;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
# Four original equipment diagrams. No brand-specific vehicle or venue replica.
def screen(width=1.05,bottom=.43,height=.58):
 box('screen border',(0,bottom+height/2,-.04),(width,.0+height,.045),'#597481')
 box('screen picture',(0,bottom+height/2,-.014),(width-.065,height-.065,.008),'#AEC9CC')
 # Simple projected film landscape, all marks coplanar with the screen face.
 w=width/2-.035;y=bottom+.035;top=bottom+height-.035
 panel('film landscape',[(-w,y,-.008),(w,y,-.008),(w,y+.14,-.008),(.17,y+.28,-.008),(-.04,y+.10,-.008),(-.23,y+.22,-.008),(-w,y+.10,-.008)],'#749991')
 for x in [-width/2+.017,width/2-.017]:
  for j in range(4):box('film perforation',(x,bottom+.085+j*.13,-.013),(.012,.040,.007),'#D4E3DB')
 for x in [-width*.38,width*.38]:
  rod('screen post',(x,.025,-.04),(x,bottom,-.04),.012,'#758C92',12)
  rod('screen foot',(x,.025,-.17),(x,.025,.11),.017,'#758C92',12)
def musicstand(x,z):
 # A tilted desk with connected mast, three feet and open score.
 rod('stand mast',(x,.03,z),(x,.47,z),.014,'#657681',16)
 rod('desk mount',(x,.47,z),(x,.47,z+.056),.015,'#657681',16)
 for t in [0,2*math.pi/3,4*math.pi/3]:rod('stand foot',(x,.12,z),(x+.13*math.cos(t),.016,z+.13*math.sin(t)),.011,'#657681',12)
 points=[(x-.275,.32,z+.12),(x+.275,.32,z+.12),(x+.275,.73,z-.055),(x-.275,.73,z-.055)]
 panel('music desk',points,'#566B79')
 def point(u,v):return (x+u,.34+v*.37,z+.1135-v*.158)
 panel('score page',[point(-.251,0),point(.251,0),point(.251,1),point(-.251,1)],'#F4E5C6')
 # A bold beamed musical pair survives small size; no tiny score typography.
 for u in [-.15,.07]:
  outline=[point(u+.045*math.cos(t),.28+.060*math.sin(t)) for t in np.linspace(0,2*math.pi,20,endpoint=False)]
  panel('score note',outline,'#4C6574')
  panel('score note',[point(u+.022,.30),point(u+.045,.30),point(u+.045,.78),point(u+.022,.78)],'#4C6574')
 panel('score note',[point(-.128,.71),point(.115,.76),point(.115,.85),point(-.128,.80)],'#4C6574')
 rod('score ledge',(x-.285,.321,z+.134),(x+.285,.321,z+.134),.012,'#566B79',16)
scene('live-film-score',(2,3,12))
screen();musicstand(.19,.32)
# Baton supported across the desk ledge, rather than a floating conductor hand.
rod('baton grip',(-.08,.344,.46),(.00,.344,.46),.012,'#B18E65',16)
rod('baton',(.00,.344,.46),(.14,.344,.46),.004,'#EBDAB3',12)
S['notes']=['Film screen has two joined posts and stabilizing feet. Foreground score desk connects to mast and tripod feet; score and notation lie on the tilted desk. Baton rests along desk ledge. One symbolic stand does not promise solo or exact instrumental lineup.']
scene('outdoor-cinema',(2,4,12))
screen()
# Lawn is an illustrative thin ground plane supporting chairs and screen.
box('lawn',(0,.001,.10),(1.28,.014,1.02),'#93A987')
def chair(x):
 # Crossed folding legs on each side; seat and back join these frame rails.
 for side in [-1,1]:
  xx=x+side*.108
  rod('chair frame',(xx,.014,.39),(xx,.425,.655),.008,'#AD947A',12)
  rod('chair frame',(xx,.014,.66),(xx,.235,.408),.008,'#AD947A',12)
 box('chair seat',(x,.237,.505),(.234,.016,.20),'#D2AA78')
 panel('chair back',[(x-.108,.31,.577),(x+.108,.31,.577),(x+.108,.416,.650),(x-.108,.416,.650)],'#D2AA78')
 for yy,zz in [(.31,.577),(.416,.650)]:rod('chair back rail',(x-.108,yy,zz),(x+.108,yy,zz),.008,'#AD947A',12)
chair(-.25);chair(.25)
# Crescent and star are explicitly graphic sky emblems, not unsupported objects.
# Crescent formed as a planar concave outline, open towards upper-right.
outline=[]
for t in np.linspace(.6,5.7,30):outline.append((-.61+.105*math.cos(t),1.14+.105*math.sin(t)))
for t in np.linspace(5.55,.76,23):outline.append((-.565+.080*math.cos(t),1.17+.080*math.sin(t)))
extrude('moon emblem',outline,-.06,-.05,'#E0BE79')
S['notes']=['Screen posts and chairs meet the common lawn plane. Folding frames cross at each side, with seat and slanted back joined to rails. Chairs face the screen, their backs towards the viewer. Crescent is a symbolic sky mark; it does not assert a particular date, weather or screening time beyond explicit outdoor night context.']
scene('mobile-clinic',(9,4,7))
# Generic six-metre clinic coach: body above four equal wheels, no emergency lights.
box('coach floor',(0,.75,0),(1.70,.22,5.8),'#6C8894')
box('clinic body',(0,1.725,-.305),(2.12,1.75,5.05),'#DFE3D7')
# Sloping cab nose closes with windshield and front panels.
outline=[(2.22,.86),(2.85,.86),(2.98,1.35),(2.22,2.60)]
extrude('cab',outline,-1.06,1.06,'#D8DFD6')
part=S['parts'][-1];part['vertices']=[[z,y,x] for x,y,z in part['vertices']];part['faces']=[list(reversed(f)) for f in part['faces']]
panel('windshield',[(-.93,1.55,2.864),(.93,1.55,2.864),(.93,2.42,2.335),(-.93,2.42,2.335)],'#7495A6')
# Longitudinal teal side stripe and a clinic door; opposite sides share structure.
for side in [-1,1]:
 x=side*1.066
 panel('clinic stripe',[(x,.89,-2.72),(x,.89,2.36),(x,1.13,2.36),(x,1.13,-2.72)],'#70A7A3')
 panel('clinic door',[(x,1.14,.42),(x,1.14,1.25),(x,2.39,1.25),(x,2.39,.42)],'#BDCCC7')
 panel('door window',[(x+side*.006,1.89,.53),(x+side*.006,1.89,1.13),(x+side*.006,2.26,1.13),(x+side*.006,2.26,.53)],'#7798A6')
 # Generic teal medical plus: brand-neutral and no emergency transport promise.
 panel('medical plus',[(x+side*.008,1.66,-1.73),(x+side*.008,1.66,-1.03),(x+side*.008,1.89,-1.03),(x+side*.008,1.89,-1.73)],'#589A95')
 panel('medical plus',[(x+side*.010,1.43,-1.50),(x+side*.010,1.43,-1.26),(x+side*.010,2.12,-1.26),(x+side*.010,2.12,-1.50)],'#589A95')
 for z in [-1.95,1.95]:
  rod('tire',(side*.93,.42,z),(side*1.14,.42,z),.42,'#566771',40)
  rod('wheel hub',(side*1.142,.42,z),(side*1.151,.42,z),.21,'#AAB9B8',32)
for z in [-1.95,1.95]:
 rod('axle',(-.98,.42,z),(.98,.42,z),.065,'#657681',16)
 box('suspension',(0,.56,z),(1.45,.23,.24),'#657681')
# Four wheels use the same radius and axle heights; bumper and twin headlamps.
box('front bumper',(0,.70,2.83),(2.15,.15,.20),'#8DA4AE')
for x in [-.72,.72]:panel('headlight',[(x-.16,.98,2.888),(x+.16,.98,2.888),(x+.16,1.13,2.928),(x-.16,1.13,2.928)],'#E8D09C')
S['notes']=['Generic clinic coach has a floor, continuous body, closed sloping cab, narrowed chassis, axles and four equal-radius wheels with clearance at y=.42. Treads meet y=0, axles share heights. Cab windshield lies on the sloped face; clinic doors and teal plus are attached to side panels. No siren or emergency light bar. Exterior is a symbolic mobile clinic, not a replica of NYP equipment or a clinical-service specification.']
scene('mural-painting',(3,3,12))
# A wall with exposed masonry along the foot and one side; no canvas frame.
box('masonry wall',(0,.36,-.036),(.90,.72,.072),'#C1A38A')
for y in [.06,.18,.30,.42,.54,.66]:
 panel('mortar course',[(-.45,y-.006,.001),(.45,y-.006,.001),(.45,y+.006,.001),(-.45,y+.006,.001)],'#E0CBB0')
for j in range(6):
 for x in ([-.30,0,.30] if j%2 else [-.44,-.15,.15,.44]):
  panel('mortar joint',[(x-.005,j*.12,.002),(x+.005,j*.12,.002),(x+.005,j*.12+.12,.002),(x-.005,j*.12+.12,.002)],'#E0CBB0')
panel('mural ground',[(-.395,.15,.004),(.36,.15,.004),(.36,.66,.004),(-.395,.66,.004)],'#AAC6C3')
panel('mural landscape',[(-.395,.15,.006),(.36,.15,.006),(.36,.37,.006),(.15,.53,.006),(-.045,.30,.006),(-.23,.44,.006),(-.395,.32,.006)],'#739C92')
panel('mural river',[(-.24,.15,.008),(-.07,.15,.008),(.22,.37,.008),(.09,.37,.008)],'#DEBD82')

# Roller is poised just off the mural face. Its bent frame joins the handle.
rod('paint roller',(.20,.51,.053),(.50,.51,.053),.044,'#C98896',32)
for a,bb in [((.50,.51,.053),(.54,.51,.053)),((.54,.51,.053),(.54,.38,.070)),((.54,.38,.070),(.34,.38,.070)),((.34,.38,.070),(.34,.23,.083))]:rod('roller frame',a,bb,.010,'#6F8996',12)
rod('roller handle',(.34,.25,.083),(.34,.08,.096),.027,'#A27059',20)
S['notes']=['Masonry wall has a closed solid base. Painted regions and mortar lines attach to the front plane; broad exposed courses distinguish wall painting from a framed canvas. Roller radius=.044 at z=.053 sits5mm in front of the mural ground atz=.004 after removing the trial paint swatch, with a short roller overhang beyond the wall edge; one connected bent shaft joins roller to handle. Tool is an illustrative equipment diagram, with no invisible human anatomy.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four equipment scenes')
