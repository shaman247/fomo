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

scene('wooden-block-play',(4,4,10))
# Original stable toy-block bridge; each stacked face meets its support.
for x,col in [(-.27,'#8DADB0'),(.27,'#BE9D83')]:box('upright wooden block',(x,.22,0),(.20,.44,.24),col)
box('bridge beam',(0,.51,0),(.77,.14,.26),'#C4B28B')
extrude('triangular prism roof',[(-.24,.58),(.24,.58),(0,.84)],-.13,.13,'#B09BB7')
box('loose cube',(-.48,.105,.30),(.21,.21,.21),'#87A786')
rod('loose cylinder',(.42,0,.32),(.42,.25,.32),.12,'#C7A284',24)
S['notes']=['Loose wooden blocks follow primary library context and generic manufacturer shapes. Original two uprights support a bridge beam atheight.44; prism base meets beam top.58. Loose cube and upright cylinder rest on ground. No branded set or age suitability inferred from manufacturer comparison.']

scene('scarecrow-making',(2,2,12))
# Inanimate straw-stuffed clothes supported by an explicit wooden cross, not a posed human.
box('vertical support stake',(0,.71,-.10),(.045,1.42,.045),wood)
box('shoulder crossbar',(0,1.04,-.10),(1.0,.045,.045),wood)
box('trouser crossbar',(0,.67,-.10),(.36,.04,.045),wood)
shirt=[(-.18,.72),(.18,.72),(.18,.96),(.45,.92),(.48,1.08),(.18,1.13),(.10,1.13),(.07,1.08),(-.07,1.08),(-.10,1.13),(-.18,1.13),(-.48,1.08),(-.45,.92),(-.18,.96)]
extrude('stuffed shirt',shirt,-.095,.06,'#87A7A6')
# Paired cloth legs have equal length, width and attachment height.
for x in [-.105,.105]:
 box('stuffed trouser leg',(x,.53,-.02),(.16,.38,.15),'#9BA0BA')
 for off in [-.045,0,.045]:rod('straw below trouser',(x+off,.36,.02),(x+off*1.25,.29,.02),.008,'#D2BD88',8)
box('waist band',(0,.72,.025),(.35,.055,.11),'#C5A285')
for sign in [-1,1]:
 for off in [-.045,0,.045]:rod('straw sleeve filling',(sign*.43,1.0+off,.005),(sign*.55,1.0+off*1.5,.005),.009,'#D2BD88',8)
ellipsoid('stuffed cloth head',(0,1.25,-.015),(.13,.14,.115),'#D8C49A',28,11);S['parts'][-1]['flat_paint']=True
# A low hat rests directly on head; cross stake runs through the stuffed head to support it.
rod('hat brim', (0,1.365,-.015),(0,1.39,-.015),.205,'#C3A478',32)
rod('hat crown',(0,1.39,-.015),(0,1.52,-.015),.115,'#C3A478',28,.085)
for x in [-.047,.047]:rod('cloth eye',(x,1.265,.093),(x,1.265,.102),.012,'#8B7866',12)
# Friendly stitched smile on cloth, three connected short segments.
for a,bb in [((-.045,1.215,.094),(-.018,1.195,.100)),((-.018,1.195,.100),(.018,1.195,.100)),((.018,1.195,.100),(.045,1.215,.094))]:rod('cloth smile',a,bb,.006,'#967E68',8)
for y in [.82,.91,1.0]:rod('shirt button',(0,y,.061),(0,y,.067),.012,'#D9C5A4',12)
box('shirt patch',(-.105,.83,.063),(.08,.085,.008),'#C6AA93')
S['notes']=['Original inanimate scarecrow constructed from RHS reference: head tied to pole, shirt supported on upper crossbar, trousers on lower crossbar, straw stuffing. Symmetric sleeves and equal trouser legs; no human anatomical or live-person depiction. Head base overlaps collar; brim rests on stuffed head. Exposed support pole continues below trousers into assumed ground; no balancing performer. Design is illustrative, not the exact collaborative EMPL scarecrow.']

scene('pasta-chitarra',(4,7,11))
# Wooden wire-strung frame with removable catching tray; broad few strings preserve icon recognition.
box('catching tray',(0,.045,0),(.62,.035,.88),'#C2A285')
for x in [-.31,.31]:box('long frame rail',(x,.14,0),(.07,.25,.94),wood)
for z in [-.44,.44]:box('wire anchor crossrail',(0,.18,z),(.62,.17,.06),'#CFAC83')
for x in [-.24,-.16,-.08,0,.08,.16,.24]:rod('tensioned cutting wire',(x,.27,-.44),(x,.27,.44),.0045,'#909C9A',8)
# Sheet spans wires; rolling pin rests on its top, without disembodied hands.
box('pasta dough sheet',(0,.279,-.07),(.46,.015,.36),'#E4CB91')
rod('rolling pin barrel',(-.26,.325,-.07),(.26,.325,-.07),.040,'#C5A886',24)
rod('rolling pin handles',(-.39,.325,-.07),(.39,.325,-.07),.020,'#AA8E70',16)
for x in [-.16,-.08,0,.08,.16]:rod('cut pasta on tray',(x,.072,.15),(x,.072,.37),.014,'#DBC18B',10)
S['notes']=['Original simplified wire-strung wood-frame pasta cutter. Eataly text describes dough pressed through strings into square-section spaghetti; class copy explicitly names this tool. Seven illustrative parallel wires anchor at crossrails; dough lies on wires, rolling pin contacts dough, catcher is below wire bed. No musical guitar, exact wire spacing/count or equipment model implied.']

scene('oyster-shucking',(3,10,10))
box('folded cloth',(0,.018,0),(.70,.036,.85),'#91AAAD')
# Irregular cupped half shell has a continuous shell wall and edible interior.
n=40;angles=np.linspace(0,2*math.pi,n,endpoint=False);cx=-.09;cz=.015
outer=np.array([[cx+.225*math.cos(t)*(1+.10*math.sin(7*t)),.14,cz+.33*math.sin(t)*(1+.07*math.sin(5*t))] for t in angles])
bottom=np.array([[cx+.13*math.cos(t),.036,cz+.23*math.sin(t)] for t in angles]);panel('shell underside',bottom,'#8C9794')
inner=outer.copy();inner[:,0]=cx+(inner[:,0]-cx)*.88;inner[:,2]=cz+(inner[:,2]-cz)*.85;inner[:,1]=.12
mesh('outer oyster cup',np.vstack([bottom,outer]),[[i,n+i,n+(i+1)%n,(i+1)%n] for i in range(n)],'#8C9794');S['parts'][-1]['double_sided']=True
mesh('shell rim',np.vstack([outer,inner]),[[i,n+i,n+(i+1)%n,(i+1)%n] for i in range(n)],'#D0CDBE');S['parts'][-1]['double_sided']=True
lower=inner.copy();lower[:,0]=cx+(lower[:,0]-cx)*.65;lower[:,2]=cz+(lower[:,2]-cz)*.7;lower[:,1]=.055
mesh('inner cupped shell',np.vstack([inner,lower]),[[i,n+i,n+(i+1)%n,(i+1)%n] for i in range(n)],'#D7D4C1');S['parts'][-1]['double_sided']=True
panel('shell inner floor',lower,'#D7D4C1')
ellipsoid('oyster meat',(cx-.025,.09,cz),(.125,.035,.205),'#C9BD99',24,9);S['parts'][-1]['flat_paint']=True
# Short-bladed shucking knife placed beside shell on cloth, not a demonstrated grip.
rod('knife handle',(.275,.079,-.29),(.275,.079,-.075),.043,'#B59D83',24)
flat_extrude('knife blade',[(.247,-.075),(.303,-.075),(.303,.13),(.275,.18),(.247,.13)],.046,.057,'#BEC6C4')
box('knife guard',(.275,.075,-.073),(.115,.024,.022),'#A1AFB2')
S['notes']=['Original open oyster half-shell and short shucking knife resting separately on folded cloth. Provider confirms hands-on shucking and six participant-opened oysters; OXO reference supports short stainless tool, not an exact product. Shell rim joins walls and interior, flesh is supported; knife handle/blade/guard connect. No risky grip, blade-in-hand scene or instructional technique; food content and supplied tool are illustrative.']

# Folded cloth edge reinforces fabric, not a cutting board.
box('cloth folded edge',(0,.039,.375),(.68,.005,.055),'#AEC1BC')
scene('mozzarella',(3,5,12))
# Fresh mozzarella has smooth pale balls, distinct from hole-filled aged cheese wedges.
lathe('serving plate',[(0,0),(.29,0),(.38,.025),(.40,.055),(.37,.065),(.27,.045),(0,.045)],'#89A4AD',40)
ellipsoid('whole mozzarella',(-.145,.175,-.015),(.16,.125,.155),'#E5E2CF',40,17)
ellipsoid('second mozzarella',(.17,.15,.05),(.135,.10,.135),'#D5D8C7',40,17)
# A single broad illustrative basil leaf rests on plate alongside cheese, not an ingredient requirement.
leaf=[[-.20,.074,.18],[-.30,.083,.21],[-.30,.080,.31],[-.24,.072,.35],[-.16,.073,.31],[-.145,.079,.25]]
panel('basil leaf',leaf,'#7DA078');rod('leaf vein',(-.24,.084,.34),(-.20,.088,.20),.004,'#AAC19A',8)
S['notes']=['Original fresh mozzarella balls on shallow plate with optional illustrative basil leaf. Eataly primary descriptions distinguish fresh mozzarella and making workshops; no Swiss holes, burrata filling or exact milk source. Both balls rest at plateheight.045 and do not overlap in worldspace: x separation.26 with z offset.065 gives small contact; their ellipsoidal extents may touch as piled food. No fixed portion, garnish or recipe promised.']
# Broad smooth cheese paint; one contiguous highlight follows exact sphere faces.
for part in list(S['parts']):
 if 'mozzarella' in part['name']:
  part['flat_paint']=True
  v=part['vertices'];center=np.asarray(v).mean(0)
  faces=[f for f in part['faces'] if all(v[i][1]>center[1]+.045 and v[i][0]<center[0]+.09 for i in f)]
  mesh('smooth cheese highlight',v,faces,'#F2EFDD');S['parts'][-1]['flat_paint']=True
S['notes']=['Original fresh mozzarella balls on shallow plate with optional basil. Broader smooth paint eliminates faceted scoop-like shading. Centers separated0.315 inx and0.065 inz exceed combinedxradius0.295; lower surfaces meet plate nearheight0.05. No cheese holes or burrata filling. Exactmilk,portion,garnish andrecipe remain unspecified.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
