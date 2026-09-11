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

def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]

# Connected modular circuit: blue USB power, pink input button, green LED output.
scene('modular-circuits',(1,7,10))
for x,col,kind in [(-.31,'#6C9DAF','power'),(0,'#BB90A6','input'),(.31,'#8DAD83','output')]:
 box(kind+' board',(x,.07,0),(.26,.025,.21),col)
 for xx in [x-.105,x+.105]:
  for z in [-.076,.076]:box('board support foot',(xx,.03,z),(.025,.055,.025),'#C6CABE')
 if x<.31:box('right magnetic connector',(x+.142,.075,0),(.05,.065,.13),'#E1DEC9')
 if x>-.31:box('left magnetic connector',(x-.142,.075,0),(.05,.065,.13),'#D1D3C4')
box('USB power inlet',(-.37,.11,-.018),(.11,.06,.10),'#7A8B91')
box('USB socket dark opening',(-.427,.11,-.018),(.006,.028,.055),'#4E6470')
box('USB connected plug',(-.475,.11,-.018),(.105,.045,.066),'#C5C8BC')
# Cable continuously enters connector; source kept outside silhouette as a symbolic power pack.
pts=[(-.525,.11,-.018),(-.57,.10,-.15),(-.48,.09,-.31),(-.30,.09,-.34)]
for a,z in zip(pts,pts[1:]):rod('USB power lead',a,z,.012,'#677F88',10)
box('external USB power pack',(-.16,.09,-.34),(.28,.13,.13),'#9BA8AF')
box('power pack indicator',(-.12,.159,-.34),(.05,.003,.027),'#C9D7B6')
box('input switch base',(0,.108,0),(.115,.05,.12),'#77868E')
rod('raised push button',(0,.13,0),(0,.165,0),.048,'#D8C0AA',16)
box('LED package',(.31,.108,0),(.10,.05,.09),'#E0DAC0')
ball('LED luminous dome',(.31,.147,0),.032,'#D7B96E')
# Rotate the entire connected circuit plane for stronger canvas coverage.
angle=math.radians(-28);R=np.array([[math.cos(angle),0,math.sin(angle)],[0,1,0],[-math.sin(angle),0,math.cos(angle)]])
for part in S['parts']:part['vertices']=(np.array(part['vertices'])@R.T).tolist()
S['notes']=['Original simplified littleBits-style magnetic module chain. Manufacturer documentation confirms blue power first, pink input then green output, board feet and keyed magnetic snaps. The blue USB power module connects to an external power pack through a continuous cable. Generic push button and LED are illustrative, not exact kit inventory. Tiny contacts, traces and electrical specifications are omitted.']

scene('hygiene-kit-distribution',(2,3,12))
# Open gusseted kit pouch: supported bottle, soap and toothbrush. Generic contents only.
outline=[(-.34,.05),(.32,.05),(.36,.12),(.31,.49),(-.30,.49),(-.36,.12)]
extrude('pouch rear',outline,-.10,-.075,'#9AB5AF')
extrude('pouch front',[(-.34,.05),(.32,.05),(.36,.12),(.29,.37),(-.29,.37),(-.36,.12)],.075,.10,'#ADC5B6')
box('pouch bottom',(0,.06,0),(.66,.05,.18),'#799B95')
for side in [-1,1]:
 panel('pouch side gusset',[(side*.34,.07,-.09),(side*.31,.49,-.09),(side*.29,.37,.09),(side*.34,.07,.09)],'#8BA9A1')
# Objects rest at pouch floor; front panel occludes their lower portions.
extrude('toiletry bottle',[(-.23,.09),(-.04,.09),(-.04,.54),(-.085,.60),(-.185,.60),(-.23,.54)],-.058,.065,'#D7C5AB')
box('bottle cap',(-.135,.626,0),(.11,.052,.13),'#A3A0BA')
box('bottle label',(-.135,.47,.067),(.13,.13,.004),'#F0E7D1')
rod('toothbrush handle',(.09,.11,0),(.14,.74,0),.018,'#869FB5',12)
box('toothbrush head',(.144,.77,0),(.057,.14,.038),'#90ABC0')
box('white brush bristles',(.144,.77,.035),(.056,.115,.055),'#E5DFC8')
box('wrapped soap',(.235,.26,-.005),(.125,.29,.10),'#B49DB5')
box('soap wrapper stripe',(.235,.28,.049),(.126,.052,.006),'#E0D7C8')
# Hygiene cue on pouch front: a clean water droplet, no medical cross.
extrude('water drop badge',[(0,.31),(-.052,.225),(-.054,.20),(-.033,.171),(0,.163),(.033,.171),(.054,.20),(.052,.225)],.102,.105,'#6F969F')
S['notes']=['Original open soft pouch with rear/front panels, side gussets and supported generic toiletry bottle, toothbrush and wrapped soap. Contents stand on pouch floor; pouch front occludes lower portions. The primary ParkSlope program guarantees essential hygiene items but not these exact contents or bag type. Badge is a water droplet rather than a medical cross; no first-aid or medication claim.']

scene('science-stage-show',(1,2,12))
# A physical single pendulum in a stand, not an atom or disconnected decoration.
box('demonstration base',(0,.025,0),(.70,.05,.36),'#A1AAA7')
for x in [-.27,.27]:
 rod('upright stand',(x,.05,0),(x,.71,0),.020,'#819AA5',12)
rod('crossbar',(-.29,.71,0),(.29,.71,0),.023,'#819AA5',12)
pivot=np.array([0,.688,0]);L=.40;theta=math.radians(26);bob=pivot+np.array([L*math.sin(theta),-L*math.cos(theta),0])
rod('pendulum suspension',pivot,bob,.008,'#667D88',10);ball('pendulum bob',bob,.069,'#D0AD70')
# Stage architecture is part of scene; curtains stand behind apparatus, no floating table.
box('stage platform',(0,-.028,0),(.92,.056,.42),'#A28D9D')
for x in [-.43,.43]:
 side=-1 if x<0 else 1
 extrude('stage side curtain',[(side*.49,.005),(side*.35,.015),(side*.415,.27),(side*.38,.51),(side*.30,.75),(side*.49,.75)],-.17,-.14,'#AA859D')
 box('curtain tie',(side*.408,.29,-.128),(.065,.027,.025),'#D0B483')
box('stage top valance',(0,.77,-.155),(.98,.08,.06),'#BE9AAF')
S['notes']=['Single pendulum attached by one continuous cord to crossbar, with upright rods attached to a broad base on a stage. Authoritative rest-length relation is 0.40sceneunits at26degrees; bob positioned from pivot by trigonometry, not independently placed. Motion is a static displaced pendulum pose. Primary Mr.C program specifically includes pendulum swings and Newton laws, but exact apparatus and stage design are illustrative. No chemical experiment, actual kit design or animation claimed.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
