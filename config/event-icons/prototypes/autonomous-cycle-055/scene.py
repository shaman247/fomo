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


# Original equipment and botanical cutaway scenes; geometry precedes projection.
scene('pinhole-camera',(2,3,12))
box('light tight matchbox',(0,.027,0),(.053,.036,.017),'#526776')
for x in [-.039,.039]:
 rod('film canister',(x,.003,0),(x,.053,0),.014,'#536C70',24)
 rod('canister top',(x,.052,0),(x,.055,0),.0145,'#A4B9B2',24)
 rod('spindle',(x,.055,0),(x,.06,0),.005,'#45545D',16)
 box('sealed film connection',(x/1.4,.027,0),(.012,.034,.012),'#354751')
# A flat silver aperture patch has no protruding photographic lens.
box('metal aperture patch',(0,.029,.009),(.016,.016,.001),'#C4D3D0')
rod('pinhole visibility mark',(0,.029,.0095),(0,.029,.010),.0012,'#263A46',16)
# Three attached rails form the shutter sleeve. Card slides upward to expose aperture.
for x in [-.012,.012]:box('shutter rail',(x,.03,.011),(.005,.033,.004),'#798893')
box('bottom shutter rail',(0,.014,.011),(.027,.004,.004),'#798893')
box('raised sliding shutter',(0,.052,.0105),(.020,.025,.001),'#BC946A')
box('takeup winder',(.039,.061,0),(.025,.003,.010),'#A4B9B2')
S['notes']=['Original matchbox camera construction informed by matchboxpinhole.com. Canisters meet and seal to the box; the card is retained in its sleeve. Aperture is enlarged to 2.4mm as an icon visibility mark instead of the roughly 0.2mm working hole; not a fabrication plan. No glass lens.']
scene('bulb-planting',(1,2,12))
# Half soil block is intentionally cut away at z=0. The whole bulb is diagrammatically exposed in front.
box('rear soil volume',(0,.35,-.17),(.85,.70,.34),'#A87959')
box('topsoil layer',(0,.68,-.17),(.85,.055,.34),'#806448')
lathe('papery bulb',[(0,.11),(.075,.11),(.125,.15),(.15,.23),(.12,.31),(.055,.38),(.008,.45),(0,.455)],'#DDB276',32)
rod('basal plate',(0,.105,0),(0,.12,0),.065,'#A87951',24)
for x,z in [(-.04,.03),(0,.05),(.04,.02)]:
 rod('root',(x,.11,z),(x*1.4,.055,z*1.6),.007,'#E2C899',12)
 rod('root tip',(x*1.4,.055,z*1.6),(x*1.7,.015,z*1.7),.005,'#E2C899',12)
# The center seam is a attached papery skin marking rather than another bulb.
rod('skin fold',(.002,.16,.141),(.004,.27,.140),.006,'#C79860',12)
S['notes']=['Illustrative cutaway removes foreground soil to expose an upright bulb with roots at the basal plate. Point stays below the soil surface. Simplified depth is not a planting measurement; RHS specifies pointed end uppermost and appropriate depth. No mature bloom or immediate germination promised.']
scene('soda-mixing',(1,3,12))
lathe('glass outline',[(0,0),(.14,0),(.17,.62),(.155,.62),(.128,.02),(0,.02)],'#A7C9CB',32)
S['parts'][-1]['transparent']=True
lathe('soda liquid',[(0,.025),(.13,.025),(.152,.49),(0,.49)],'#C09069',32)
# Attached spoon extends from submerged bowl to above rim; no straw/alcohol cue.
rod('stirring spoon',(.04,.12,.015),(.17,.83,.015),.012,'#8BA4AE',16)
ball('spoon bowl',(.04,.13,.015),.028,'#8BA4AE')
for x,y,z,r in [(-.07,.18,.13,.013),(.055,.29,.142,.014),(-.04,.4,.149,.012),(.055,.44,.14,.01)]:
 ball('bubble diagram',(x,y,z),r,'#EDD6AA')
S['notes']=['Original transparent-glass diagram with brown syrup soda, submerged stirring spoon and enlarged bubble marks. Illustrative liquid can be coffee or fruit syrup; exact flavor, dairy and recipe require event text. No cocktail, alcoholic bottle, drinking straw or sorbet is depicted. Glass uses an outline pass to expose liquid and spoon.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
