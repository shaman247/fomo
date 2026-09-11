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
 x,y,z=c;n=24;rings=12;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
scene('book-giveaway',(3,5,10))
box('box base',(0,.035,0),(.92,.07,.62),'#CDA277')
frame('box wall',(0,.22,0),.92,.62,.04,.40,'#CCA074')
# Three upright books rest inside on the bottom; separate covers enclose pages.
for i,(x,h,col) in enumerate([(-.28,.74,'#719CA7'),(0,.83,'#CB7F7B'),(.27,.66,'#9DA579')]):
 box('book pages'+str(i),(x,.07+h/2,0),(.15,h,.39),'#F0E8D9')
 for dx in [-.09,.09]:box('book cover'+str(i),(x+dx,.07+h/2,0),(.03,h+.015,.44),col)
 box('book spine'+str(i),(x,.07+h/2,.22),(.21,h+.015,.035),col)
 for y in [.17,.22]:box('spine band'+str(i),(x,.07+h-y,.240),(.15,.015,.004),'#EAD6AD')
# Cardboard flaps remain connected along the upper edges and slope outward.
panel('left flap',[(-.46,.42,-.31),(-.46,.42,.31),(-.66,.25,.31),(-.66,.25,-.31)],'#D9B38A')
panel('right flap',[(.46,.42,.31),(.46,.42,-.31),(.66,.25,-.31),(.66,.25,.31)],'#BF9169')
panel('front flap',[(-.42,.42,.31),(.42,.42,.31),(.42,.22,.47),(-.42,.22,.47)],'#D9AD7D')
S['notes']=['Books rest on the box base; covers enclose pages and spines join covers. Flaps connect to wall tops. Illustrative distribution container, not a promise of boxed or identical books.']
scene('staged-reading',(2,3,12))
rod('base',(0,.015,0),(0,.055,0),.27,'#66828E',32)
rod('stand',(0,.04,0),(0,.78,0),.028,'#66828E',12)
box('script tray',(0,.91,0),(.65,.45,.05),'#6D8992')
box('script page',(0,.8975,.03),(.56,.38,.012),'#EFE6D3')
box('tray lip',(0,.69,.055),(.69,.035,.10),'#91A9AD')
for i,y in enumerate([1.02,.95,.88,.81]):box('script ink',(-.12,y,.039),(.23,.015,.004),'#ADA38E')
# Symbolic mask is a flat theatrical badge on the front face of the script.
# Its outline and facial marks are plane geometry tied to the page, not a human.
mask=[(.035,.965),(.285,.965),(.285,.87),(.25,.79),(.16,.735),(.07,.79),(.035,.87)]
extrude('theater mask',mask,.048,.053,'#DDA586')
for x in [.095,.225]:rod('mask eye',(x-.018,.902,.055),(x+.018,.902,.055),.006,'#825F53',8)
# Raised mouth circle on planar emblem, not anatomy.
rod('mask mouth',(.16,.825,.055),(.16,.825,.057),.03,'#825F53',16)
S['notes']=['Base, pole and script tray are joined; script rests on the tray lip. Mask is an emblem on the script plane, not a performer or a claim about exact staging.']
scene('live-podcast',(1,2,12))
for i,(x,col) in enumerate([(-.27,'#728B9C'),(.27,'#B9858D')]):
 rod('mic base'+str(i),(x,.01,0),(x,.045,0),.20,'#536F7B',32)
 rod('mic stem'+str(i),(x,.04,0),(x,.33,0),.025,'#7C979E',12)
 # Upright microphone capsule joins stand with a broad lower socket.
 rod('mic body'+str(i),(x,.31,0),(x,.65,0),.102,col,32)
 ball('mic cap'+str(i),(x,.65,0),.103,col)
 rod('socket'+str(i),(x,.28,0),(x,.35,0),.043,'#536F7B',12)
 for y in [.48,.54,.60]:rod('grille'+str(i),(x-.064,y,.102),(x+.064,y,.102),.011,'#405E6B',8)
extrude('conversation emblem',[(-.20,.84),(-.18,.88),(.18,.88),(.20,.84),(.20,.72),(.16,.69),(.07,.69),(.0,.64),(.0,.69),(-.18,.69),(-.20,.72)],-.15,-.14,'#D7B275')
for x in [-.09,0,.09]:rod('dialogue dot',(x,.785,-.135),(x,.785,-.13),.017,'#796449',16)
S['notes']=['Each microphone, socket, stem and disk base is connected; bases share y=.01 and remain separated. Paired microphone motif is symbolic, not a fixed host count or an exact venue equipment promise.']
scene('sake-cheese-pairing',(3,4,12))
# Small illustrative tokkuri and choko: continuous exterior and interior profiles.
before=len(S['parts']);lathe('tokkuri',[(0,0),(.14,0),(.17,.08),(.17,.30),(.13,.43),(.065,.50),(.055,.68),(.067,.71),(.041,.71),(.037,.67),(.040,.51),(.10,.42),(.13,.29),(.13,.08),(0,.05)],'#E8E8DF',32)
for part in S['parts'][before:]:part['vertices']=[[x-.24,y,z-.08] for x,y,z in part['vertices']]
# blue painted band lies on the lower body, interpreted as a broad glaze accent.
for y in [.15,.21]:
 before=len(S['parts']);rod('glaze band',(-.24,y,-.08),(-.24,y+.026,-.08),.171,'#7B9FBB',32)
before=len(S['parts']);lathe('choko',[(0,0),(.085,0),(.115,.17),(.10,.18),(.07,.04),(0,.04)],'#9FB9C8',28)
for part in S['parts'][before:]:part['vertices']=[[x-.36,y,z+.30] for x,y,z in part['vertices']]
rod('sake surface',(-.36,.11,.30),(-.36,.113,.30),.083,'#D4DEC9',24)
# Cheese wedge with rind; its six vertices define the complete connected solid.
verts=[(.08,0,.26),(.53,0,.26),(.48,0,-.13),(.08,.22,.26),(.53,.22,.26),(.48,.22,-.13)]
mesh('cheese',verts,[[0,2,1],[3,4,5],[0,1,4,3],[1,2,5,4],[2,0,3,5]],'#EAC579')
box('front rind',(.305,.03,.27),(.45,.06,.02),'#E6D9B5')
S['notes']=['Tokkuri and cup have continuous hollow vessel profiles and share a support plane with cheese. Cup liquid lies below the rim. Blue bands are glaze accents; pictured vessels and cheese shape are representative, not exact serviceware or variety promises.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four object scenes')
