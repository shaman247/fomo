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
# Vat, screen and upper deckle; wet sheet supported on the mould, no floating hand.
scene('papermaking',(3,6,9))
box('vat floor',(0,.035,0),(.82,.07,.57),'#337B8C');frame('vat walls',(0,.12,0),.82,.57,.045,.18,'#4CA2AF');box('pulp water',(0,.17,0),(.72,.02,.47),'#B3DAD5')
frame('mould',(0,.42,0),.66,.43,.055,.045,darkwood);frame('deckle',(0,.465,0),.66,.43,.055,.045,lightwood)
box('wet paper',(0,.449,0),(.545,.006,.315),cream)
for x,z in [(-.19,-.09),(.09,.08),(.18,-.08),(-.09,.045)]:box('paper fibre',(x,.454,z),(.035,.002,.008),'#C7C4AF')
for x in [-.23,.23]:
 rod('drop lower',(x,.25,.16),(x,.285,.16),.016,'#3DABD0',12,r2=.024)
 rod('drop tip',(x,.285,.16),(x,.335,.16),.024,'#3DABD0',12,r2=.001)
S['notes']=['Vat .82×.57 m stylized oversized; deckle .66×.43, paper supported by lower mould at y=.449; intentional separated tool diagram.']
# Single neck, four attached splayed legs, pedal rail/rods, no piano keys.
scene('pedal-steel',(3,4,9))
for x in [-.48,.48]:
 for z in [-.14,.14]:rod('leg',(x*1.1,.025,z*1.6),(x,.69,z),.022,steel)
box('front pedal rail',(0,.075,.225),(1.10,.06,.045),steel)
for x in [-.32,-.20,-.08]:
 box('pedal',(x,.035,.27),(.065,.025,.17),dark);rod('pedal rod',(x,.075,.225),(x,.7,.15),.0065,steel,8)
box('body',(0,.735,0),(1.07,.125,.36),'#377E92');box('top',(0,.803,0),(1.07,.015,.36),'#B8CFD0');box('fretboard',(.025,.818,-.015),(.72,.017,.22),dark)
for i in range(9):box('fret',(-.30+i*.068,.831,-.015),(.008,.004,.22),'#AFC2C2')
for z in np.linspace(-.1,.07,10):rod('string',(-.47,.842,z),(.43,.842,z),.0028,cream,6)
box('bridge',(.43,.829,-.015),(.045,.04,.235),steel);box('keyhead',(-.45,.833,-.015),(.13,.045,.24),steel)
for x in [-.49,-.465,-.44,-.415,-.39]:
 for z in [-.153,.13]:rod('tuner',(x,.843,z),(x,.866,z),.01,cream,8)
for x in [.18,.30]:box('knee lever',(x,.62,-.11),(.023,.15,.028),dark)
S['notes']=['Approximate single-neck .1.07 m console, ten strings, three pedals, four legs; ten tuning keys abbreviated. Pedal rods attach rail to front underside; strings lie above fretboard.']
# Gel plate on table plane, curling paper model and independent brayer resting to side.
scene('gel-plate-printing',(2,7,10))
box('gel thickness',(-.07,.025,0),(.70,.05,.57),'#83C6C2');box('inked gel',(-.07,.052,0),(.60,.008,.47),'#6D8BBF')
panel('negative leaf',[[-.31,.058,-.13],[-.20,.058,-.06],[-.19,.058,.09],[-.28,.058,.16],[-.36,.058,.04]],'#C4DDD0')
# paper lifts from near edge in a continuous curved surface on the right half
for i in range(6):
 z0=-.20+i*.074;z1=z0+.074
 def h(z):return .064+.32*((z+.20)/.444)**2
 panel('peeled paper',[[-.08,h(z0),z0],[.25,h(z0),z0],[.25,h(z1),z1],[-.08,h(z1),z1]],cream)
rod('brayer roller',(-.35,.132,-.26),(.12,.132,-.26),.075,'#344F69',24)
for x in [-.37,.14]:rod('brayer fork',(x,.132,-.26),(x,.132,-.44),.013,steel,8)
rod('brayer fork crossbar',(-.37,.132,-.44),(.14,.132,-.44),.013,steel,8)
rod('brayer handle',(-.115,.132,-.44),(-.115,.132,-.63),.030,dark,16)
rod('leaf stem',(-.28,.061,.12),(-.25,.061,-.09),.0035,'#6D8BBF',8)
S['notes']=['Plate .70×.57 m stylized; paper shares plate plane at back edge then curls upward continuously. Brayer rests on rear plate edge; fork/handle extend behind. It does not pass through lifted paper.']
# Rocker blade is a wide curved steel edge contacting the copper plate at its low point.
scene('mezzotint',(2,4.5,10))
box('copper plate',(0,.018,0),(.77,.035,.51),'#C98562');box('rocked tone',(-.13,.038,.045),(.32,.002,.27),'#665A57')
outline=[(-.23,.30),(-.07,.40),(.07,.40),(.23,.30),(.23,.105),(.17,.067),(.09,.045),(0,.037),(-.09,.045),(-.17,.067),(-.23,.105)]
# outline clockwise: reverse for proper front normal
extrude('rocker blade',list(reversed(outline)),-.045,-.015,steel)
rod('ferrule',(0,.38,-.03),(0,.45,-.03),.048,dark,16)
rod('wooden handle',(0,.45,-.03),(0,.76,-.03),.072,wood,20,r2=.092)
for x in np.linspace(-.20,.20,11):
 yy=.038+.065*(abs(x)/.23)**2
 rod('rocker tooth',(x,yy,-.012),(x,yy+.055,-.012),.0028,dark,6)
S['notes']=['Illustrative .46 m rocker enlarged for recognition; convex blade edge has one low contact on copper. Teeth abbreviated; no cylindrical roller.']
# Single planted shoe and short lower-leg crop avoids implying unequal full limbs.
scene('step-aerobics',(3,3.8,9))
box('step riser',(0,.065,0),(.78,.13,.42),'#78559A');box('step platform',(0,.15,0),(.91,.07,.49),'#39A8A7');box('step tread',(0,.189,0),(.79,.009,.37),'#315D69')
# Side-profile shoe extruded through foot width, sole bottom exactly on platform.
sole=[(-.24,.195),(.27,.195),(.30,.22),(.28,.245),(-.22,.25),(-.28,.225)]
extrude('shoe sole',sole,-.095,.095,cream)
upper=[(-.24,.25),(.28,.25),(.28,.30),(.20,.35),(.025,.37),(-.055,.46),(-.20,.45),(-.24,.36)]
extrude('shoe upper',upper,-.085,.085,'#EC7770')
rod('ankle and cropped calf',(-.135,.40,0),(-.105,.77,0),.070,'#466B8C',24,r2=.080)
rod('sock',(-.135,.405,0),(-.125,.505,0),.074,cream,24)
for x in [-.015,.045,.105]:rod('shoelace',(x,.365,.086),(x+.037,.318,.086),.009,cream,8)
S['notes']=['One lower-leg crop, shoe .58 m stylized vs .91 m step. Sole bottom y=.195 equals tread top .1935 within rounding; ankle enters heel collar. No paired limbs or full-body pose implied.']
# Compact single-sided inkle loom with transverse cantilevered pegs and narrow band.
scene('inkle-loom',(4,3,9))
box('base',(0,.055,0),(.88,.11,.40),darkwood)
box('rear upright',(-.29,.34,-.08),(.095,.56,.10),wood);box('front upright',(.30,.28,-.08),(.10,.44,.10),wood)
rod('angled brace',(-.32,.12,-.08),(.31,.47,-.08),.037,wood,10)
pegs=[(-.29,.59),(-.29,.36),(-.29,.18),(.30,.47),(.30,.19)]
for i,(x,y) in enumerate(pegs):rod('warp peg '+str(i),(x,y,-.10),(x,y,.18),.028,lightwood,16)
# Continuous outer warp loop; cross-section spanning the peg width, controlled route.
route=[(-.29,.62),(.30,.50),(.33,.19),(-.29,.15),(-.32,.59),(-.29,.62)]
for z in [.055,.135]:
 for a,bb in zip(route,route[1:]):rod('warp',(a[0],a[1],z),(bb[0],bb[1],z),.006,'#F1D6AB',8)
for z in [.055,.135]:rod('heddle',(-.29,.36,z),(-.10,.58,z),.004,cream,6)
# woven section rests directly on the upper sloping warp run
panel('woven band',[[.02,.56,.035],[.30,.503,.035],[.30,.503,.16],[.02,.56,.16]],teal)
for x in [.04,.09,.14,.19,.24]:
 y=.56-(x-.02)*(.057/.28)+.004
 rod('weft',(x,y,.035),(x,y,.16),.007,'#B5DBBD',8)
S['notes']=['Compact single-sided tabletop band loom, not a tapestry frame. All pegs attach uprights/brace. Warp route schematic with continuous return loop; narrow fabric aligned on upper run. No claim of exact proprietary peg pattern.']
# Small road roller with broad drum explicitly pressing a printed sheet.
scene('steamroller-printing',(4,4,9))
box('relief block',(0,.025,.17),(1.20,.05,.82),darkwood);box('paper',(0,.053,.17),(1.10,.008,.74),cream)
# rear tyre and front steel drum bottoms coincide with paper top
for z in [-.20,.20]:rod('rear tyre',(-.33,.235,z-.055),(-.33,.235,z+.055),.18,'#37474D',24)
rod('front drum',(.35,.245,-.16),(.35,.245,.43),.19,steel,32)
box('chassis',(-.13,.36,.08),(.77,.12,.37),'#F6BE54');box('engine',(-.28,.51,.08),(.36,.22,.33),'#F5A94B')
for z in [-.18,.45]:rod('drum support',(.05,.36,z),(.35,.245,z),.033,dark,10)
box('seat pedestal',(-.015,.49,.075),(.10,.145,.14),dark)
box('seat',(.0,.59,.075),(.19,.07,.25),dark);box('seat back',(-.08,.70,.075),(.05,.20,.25),dark)
rod('steering column',(.14,.40,.075),(.23,.71,.075),.018,dark,10);rod('steering crossbar',(.20,.72,-.035),(.20,.72,.185),.018,dark,10)
# leaf-shaped artwork on the exposed foreground sheet, safely ahead of roller
panel('printed leaf',[[-.28,.059,.43],[-.14,.059,.27],[.05,.059,.38],[-.05,.059,.52],[-.20,.059,.53]],'#4D9C91')
S['notes']=['Generic compact roller; no driver. Front drum bottom y=.055 contacts paper y=.057 within tolerance. Rear tyres .055 base likewise. Paper on relief block, exposed teal print cue. Chassis and fork support drum.']
# Export scene only until geometry has been inspected.
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 print('Created',len(SCENES),'inspectable 3D scenes; use project.py for SVG output')
