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
 x,y,z=c;n=24;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
# Four original equipment/environment diagrams; dimensions illustrative.
def move_last(c):S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])+c).tolist()
def flat_solid(name,outline,y0,y1,color):
 extrude(name,outline,y0,y1,color);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
scene('artist-studio-visit',(3,3,12))
# Door jambs and lintel share a floor with the easel beyond the opening.
box('studio floor',(0,.008,-.13),(1.22,.016,.72),'#D5C5AD')
for x in [-.50,.50]:box('door jamb',(x,.68,-.11),(.065,1.36,.085),'#87A8A8')
box('door lintel',(0,1.36,-.11),(1.065,.065,.085),'#87A8A8')
# Open door rotates about its left hinge. All fittings use same transform.
start=len(S['parts']);box('open door',(.467,.675,0),(.934,1.29,.035),'#C7D2BD')
box('door inset',(.467,.71,.019),(.69,.94,.009),'#ADC0AF')
rod('door knob',(.815,.61,.023),(.815,.61,.057),.018,'#A98658',20)
angle=math.radians(67)
for part in S['parts'][start:]:part['vertices']=[[-.467+x*math.cos(angle)-z*math.sin(angle),y,-.11+x*math.sin(angle)+z*math.cos(angle)] for x,y,z in part['vertices']]
# A connected tripod studio easel carrying a small painting.
for x in [-.23,.23]:rod('easel front leg',(x,.022,-.12),(x*.30,1.11,-.31),.020,'#BD9169',12)
rod('easel rear leg',(0,.022,-.48),(0,1.07,-.30),.018,'#A57E60',12)
rod('easel cross rail',(-.18,.35,-.18),(.18,.35,-.18),.015,'#BD9169',12)
box('canvas shelf',(0,.44,-.15),(.56,.045,.115),'#BD9169')
# Vertical canvas sits on shelf; brace behind connects to easel top.
box('canvas',(0,.76,-.19),(.52,.595,.042),'#EFE2C5')
rod('canvas back brace',(0,.62,-.214),(0,1.08,-.305),.018,'#A57E60',12)
panel('paint sky',[(-.23,.49,-.167),(.23,.49,-.167),(.23,1.026,-.167),(-.23,1.026,-.167)],'#A7C5C7')
panel('paint hills',[(-.23,.49,-.165),(.23,.49,-.165),(.23,.70,-.165),(.08,.83,-.165),(-.09,.66,-.165),(-.23,.80,-.165)],'#84A793')
S['notes']=['Door is hinged at left jamb, rotated67degrees, with attached inset and knob. Easel has three connected legs, shelf and canvas brace beyond the doorway. All lower leg ends overlap the common floor surface. Canvas bottom y=.4625 matches shelf top=.4625. Doorway signifies studio access; the generic painting does not promise a particular medium or artist.']
scene('sculpture-walk',(3,4,12))
box('lawn',(0,.015,0),(1.65,.030,1.04),'#A3B691')
# Short path is painted on the common ground surface, passing the plinth.
flat_solid('path',[(.12,.53),(.54,.53),(.35,.24),(.17,.10),(.23,-.09),(.47,-.32),(.23,-.32),(.04,-.11),(-.03,.12)],.031,.034,'#DEC8A5')
box('plinth',(-.29,.145,-.03),(.60,.23,.43),'#B9B5A9')
# Smooth abstract elliptical bronze loop; radius plus tube sets base contact.
verts=[];m,n=40,12
for i in range(m):
 t=i*2*math.pi/m;outward=np.array([math.cos(t)/.32,math.sin(t)/.44,0]);outward/=np.linalg.norm(outward);center=np.array([-.29+.32*math.cos(t),.79+.44*math.sin(t),-.03])
 for j in range(n):
  phi=j*2*math.pi/n;verts.append(center+.09*(math.cos(phi)*outward+math.sin(phi)*np.array([0,0,1])))
faces=[[i*n+j,((i+1)%m)*n+j,((i+1)%m)*n+(j+1)%n,i*n+(j+1)%n] for i in range(m) for j in range(n)]
mesh('sculpture loop',verts,faces,'#72A3A0')
# Ellipse bottom=.35, tube bottom=.26, exactly the plinth top.
rod('tree trunk',(.54,.03,-.25),(.54,.93,-.25),.045,'#A98262',12)
for x,y,z,r in [(.54,1.11,-.25,.255),(.38,.95,-.25,.215),(.68,.94,-.25,.22)]:ball('tree canopy',(x,y,z),r,'#87AA77')
S['notes']=['Ground/lawn supports the plinth and tree. Elliptical loop minimum y=.79-.44-.09=.26 equals plinth top; loop is an invented abstract sculpture, not copied public art. Path lies immediately above ground. Tree trunk penetrates canopy. Ground/plant and plinth distinguish outdoor sculpture viewing from sculpture making; no exact route or site shape is asserted.']
scene('trad-climbing',(12,3,10))
# Four cam plates across two parallel axles, following the visible C4 component layout.
# Plate silhouettes approximate curved lobes; no engineering cam profile is claimed.
for i,x in enumerate([-.036,-.014,.014,.036]):
 sign=-1 if i%2==0 else 1
 outline=[(-.013,.179),(.014,.179),(.022,.190)]
 for t in np.linspace(-.10,math.pi*.89,20):outline.append((.041*math.cos(t),.195+.035*math.sin(t)))
 outline+=[(-.025,.183)]
 if sign<0:outline=[(-u,v) for u,v in reversed(outline)]
 extrude('cam lobe',outline,x-.005,x+.005,'#70A2BA' if i%2==0 else '#91B4C1')
 part=S['parts'][-1];part['vertices']=[[z,y,u] for u,y,z in part['vertices']];part['faces']=[list(reversed(f)) for f in part['faces']]
for z in [-.009,.009]:
 rod('cam axle',(-.043,.190,z),(.043,.190,z),.0037,'#70858E',16)
 for x in [-.044,.044]:rod('axle cap',(x,.190,z),(x+(.001 if x>0 else -.001),.190,z),.006,'#B1C1C5',20)
 rod('stem fork',(0,.163,0),(0,.190,z),.0045,'#8C9A9F',12)
rod('stem',(0,.052,0),(0,.170,0),.0055,'#627883',16)
# Wide pull-trigger, with individual wires joining all four plates.
box('trigger',(0,.112,.002),(.080,.009,.022),'#627883')
for i,x in enumerate([-.036,-.014,.014,.036]):
 z=-.026 if i%2==0 else .026
 rod('trigger wire',(x*.82,.112,.003),(x,.182,z),.0012,'#AAB9BB',8)
# Continuous cable thumb loop below the stem, attached through shoulder branches.
for i in range(24):
 t=i*2*math.pi/24;u=(i+1)*2*math.pi/24
 rod('thumb loop',(.014*math.cos(t),.029+.022*math.sin(t),0),(.014*math.cos(u),.029+.022*math.sin(u),0),.0028,'#8E9FA6',8)
for x in [-.007,.007]:rod('stem shoulder',(x,.049,0),(0,.059,0),.004,'#627883',12)
# Sewn webbing loop links through the thumb loop and hangs free, unattached to a rope.
# Closed flat ribbon uses outer/inner profiles, creating an open center.
outer=[(-.012,.013),(.012,.013),(.019,-.006),(.017,-.057),(.011,-.069),(-.011,-.069),(-.017,-.057),(-.019,-.006)]
inner=[(-.005,.002),(.005,.002),(.010,-.010),(.009,-.052),(.005,-.060),(-.005,-.060),(-.009,-.052),(-.010,-.010)]
# Ribbon mesh has a genuine aperture, not a dark painted fake hole.
for z0,z1 in [(-.003,.003)]:
 v=[[x,y,z] for z in [z0,z1] for path in [outer,inner] for x,y in path];n=8;faces=[]
 for i in range(n):
  j=(i+1)%n;faces.extend([[i,j,8+j,8+i],[16+i,24+i,24+j,16+j],[i,16+i,16+j,j],[8+i,8+j,24+j,24+i]])
 mesh('sling webbing',v,faces,'#719DB4')
box('sling sewn overlap',(0,-.017,.004),(.033,.033,.004),'#719DB4')
# Rotate the unplaced assembly in its camera plane to use the square icon canvas.
axis=basis(S['camera'])[2];theta=-math.pi/4
K=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
R=np.eye(3)*math.cos(theta)+(1-math.cos(theta))*np.outer(axis,axis)+math.sin(theta)*K
for part in S['parts']:part['vertices']=(np.array(part['vertices'])@R.T).tolist()
S['notes']=['Cam shown unplaced and rotated45degrees as a whole in the icon camera plane, with four separate lobe plates, two parallel axles, end caps, fork/stem, trigger and four wires, thumb loop and sewn sling. Manufacturer product photo and component description ground topology; lobe profile and dimensions are illustrative, not a load-rated design. No rock placement, rope system, climbing instruction or safety validation is depicted. Sling has a real opening with a short overlapping sewn section.']
scene('special-waste-dropoff',(3,5,12))
box('collection base',(0,.008,0),(.34,.016,.23),'#80A69D')
frame('collection sides',(0,.057,0),.34,.23,.015,.082,'#80A69D')
# Closed household-product can, all surfaces capped; a battery stands beside it.
lathe('closed can',[(0,.016),(.060,.016),(.062,.020),(.062,.167),(.059,.173),(0,.173)],'#A6BAC0',36);move_last((-.071,0,-.018))
lathe('can lid',[(0,.173),(.060,.173),(.063,.179),(.060,.183),(0,.183)],'#CBD8D6',36);move_last((-.071,0,-.018))
# Broad painted band identifies a household-product tin; no open fluid or spill.
lathe('can band',[(.0625,.049),(.0625,.137)],'#D1A169',36);move_last((-.071,0,-.018))
box('battery',(.078,.104,-.010),(.085,.176,.072),'#667E89')
box('battery cap',(.078,.184,-.010),(.087,.018,.074),'#AEBBB9')
for x in [.057,.098]:rod('battery terminal',(x,.193,-.010),(x,.207,-.010),.010,'#D0D8D2',16)
# Caution mark attaches to front crate wall; it denotes special collection generally.
panel('caution triangle',[(-.060,.029,.116),(.060,.029,.116),(0,.089,.116)],'#E6C279')
panel('caution mark',[(-.005,.049,.117),(.005,.049,.117),(.006,.069,.117),(-.006,.069,.117)],'#66716B')
rod('caution dot',(0,.037,.117),(0,.037,.118),.005,'#66716B',16)
S['notes']=['Collection crate has a closed base and joined sides. Sealed can and battery bases y=.016 meet base top. Can lid caps the vessel; no mixing, spills, flames or exposed chemical contents are depicted. Battery has two separated terminals. Caution triangle is a generic graphic on the front, not a statutory hazard label or a packing instruction. Specific accepted products depend on the event program.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four studies')
