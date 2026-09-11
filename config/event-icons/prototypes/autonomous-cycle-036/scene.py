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

# Original generic mobile kitchen, positive Z is the service side, cab at +X.
scene('food-truck',(3.6,2.5,8))
box('chassis',(0,.42,0),(4.55,.28,1.60),dark)
# Body solid has an actual open wheel well above the rear tire.
arch=[(-1.50+.47*math.cos(a),.42+.47*math.sin(a)) for a in np.linspace(math.pi-math.asin(.12/.47),math.asin(.12/.47),17)]
extrude('kitchen body',[(-2.295,.54)]+arch+[(1.155,.54),(1.155,2.46),(-2.295,2.46)],-.94,.94,'#CFA36B')
# Cab silhouette is a real extruded prism with a sloped windscreen at the nose.
arch=[(1.57+.47*math.cos(a),.42+.47*math.sin(a)) for a in np.linspace(math.pi-math.asin(.15/.47),math.asin(.15/.47),17)]
extrude('cab',[(1.10,.57)]+arch+[(2.28,.57),(2.28,1.08),(1.98,1.16),(1.70,2.12),(1.10,2.12)],-.92,.92,'#75A9A3')
# Both side windows attach to the cab surfaces. No impossible interior occlusion.
for z in [-.925,.925]:
 panel('cab side window',[(1.27,1.3,z),(1.89,1.3,z),(1.64,1.97,z),(1.27,1.97,z)],'#526E7D')
 panel('cab door seam',[(1.24,.64,z),(1.27,.64,z),(1.27,1.22,z),(1.24,1.22,z)],'#508B8B')
 box('cab handle',(1.42,1.18,z),(.19,.045,.025),'#D0D7CC')
# Front sloped windshield follows the cab’s sloping face, not a floating rectangle.
panel('windshield',[(1.75,1.96,-.75),(1.75,1.96,.75),(1.925,1.36,.75),(1.925,1.36,-.75)],'#526E7D')
# Service aperture is a dark flat recess symbol on the body; actual glass not implied.
box('service window frame',(-.55,1.54,.947),(1.9,.84,.06),'#EEE1C7')
box('service opening',(-.55,1.54,.985),(1.73,.66,.03),'#526E7D')
box('service sill',(-.55,1.1,1.09),(2.04,.09,.36),'#D6D9CA')
# Hinged canopy connects its rear edge to the body top; two support rods connect to body.
mesh('raised canopy',[[-1.6,2.02,.96],[.5,2.02,.96],[.5,2.21,1.67],[-1.6,2.21,1.67]],[[0,1,2,3]],'#D58E86')
for x in [-1.6,.5]:rod('canopy support',(x,1.57,.97),(x,2.19,1.64),.018,dark,n=8)
# Simple plate/utensil emblem on a small attached side panel.
box('food sign',(-.55,.77,.966),(.72,.44,.025),'#8EAB9A')
rod('plate',(-.55,.77,.985),(-.55,.77,1.001),.15,'#EFE3C7',n=24)
rod('fork handle',(-.80,.63,1.003),(-.80,.88,1.003),.014,'#EFE3C7',n=6)
for x in [-.84,-.80,-.76]:rod('fork tine',(x,.87,1.003),(x,.94,1.003),.012,'#EFE3C7',n=6)
rod('fork crossbar',(-.84,.87,1.003),(-.76,.87,1.003),.012,'#EFE3C7',n=6)
rod('knife',(-.30,.63,1.003),(-.30,.94,1.003),.021,'#EFE3C7',n=6)
# Four matched wheels share one ground plane; front/rear axles parallel Z.
for x in [-1.50,1.57]:
 rod('axle',(x,.42,-1.0),(x,.42,1.0),.07,dark,n=10)
 for sign in [-1,1]:
  z=sign*1.0;rod('tire',(x,.42,z-.13),(x,.42,z+.13),.42,'#45555F',n=24)
  zz=sign*1.14;rod('hub',(x,.42,zz-sign*.006),(x,.42,zz+sign*.022),.20,'#BAC8C9',n=20)
box('front bumper',(2.31,.58,0),(.12,.16,1.84),'#AABCC0')
for z in [-.65,.65]:box('headlamp',(2.29,.94,z),(.03,.18,.27),'#F3DCAA')
S['measurements']=dict(wheels=4,wheel_radius=.42,ground_y=0,wheelbase=3.07,wheel_well_radius=.47,tire_clearance=.05,body_width=1.88,body_roof_y=2.46,canopy_attached=True)
S['notes']=['Original representative compact food truck, informed by a mobile-kitchen operator photograph. Four same-sized wheels meet y=0; open wheel wells give 0.05 m radial tire clearance and the narrower chassis clears the inner tire faces; front bumper, cab, kitchen body and attached service opening form one solid assembly. The raised service hatch connects at its rear edge and has two attached supporting rods. No vendor branding, exact fleet specification or promised food menu.']
# Bench-top fly-tying vise: hook bend clamped at left, level shank extends right.
scene('fly-tying',(1.2,2.3,9))
flat_extrude('weighted base',rounded_outline(.33,.22,.025,6),0,.027,'#5D8790')
rod('stem',(-.065,.027,0),(-.065,.295,0),.014,'#AABBC0',n=12)
rod('stem collar',(-.065,.235,0),(-.065,.265,0),.027,'#5B737C',n=12)
rod('locking screw',(-.065,.246,0),(-.025,.246,.047),.009,'#9BAFB4',n=10)
rod('locking knob',(-.025,.246,.047),(-.013,.246,.061),.020,'#5B737C',n=12)
# Angled jaw carrier and matched two jaws, actual gap holds the hook bend.
rod('jaw carrier',(-.065,.285,0),(-.006,.355,0),.029,'#708994',n=12,r2=.020)
for sign in [-1,1]:
 extrude('jaw', [(-.026,.33),(.010,.352),(.020,.393),(.006,.405),(-.014,.367)],sign*.001 if sign>0 else -.017, .017 if sign>0 else -0.001,'#647D88')
# Hook lies in XY plane: shank y=.435, bend meets jaws at(.013,.392).
pts=[(.159,.435,0),(.042,.435,0),(.022,.431,0),(.008,.417,0),(.004,.399,0),(.012,.383,0),(.029,.378,0),(.045,.387,0),(.054,.405,0)]
for a,bb in zip(pts,pts[1:]):rod('hook wire',a,bb,.0036,'#B5C4C7',n=8)
# Eye is an actual small annulus perpendicular to Z, with a visible center hole.
for a in np.linspace(0,2*math.pi,17)[:-1]:
 aa=(.165+.009*math.cos(a),.435+.009*math.sin(a),0);bb=(.165+.009*math.cos(a+2*math.pi/16),.435+.009*math.sin(a+2*math.pi/16),0);rod('hook eye',aa,bb,.0025,'#B5C4C7',n=6)
# Thread body and representative feather wing attach to the shank, not the clamp.
rod('wrapped fly body',(.065,.435,0),(.146,.435,0),.009,'#B59A71',n=12)
for x in [.08,.097,.114,.131]:
 rod('body thread ridge',(x,.426,.002),(x,.444,.002),.0022,'#775D51',n=6)
for i,(y,z) in enumerate([(.454,.004),(.468,-.002),(.480,.004)]):
 extrude('feather vane',[(.127,.437),(.116,.453),(.062,y+.018),(.022,y+.006),(.064,y-.010)],z-.001,z+.001,'#C89772' if i!=1 else '#DBBE8C')
rod('feather shaft',(.031,.467,.009),(.127,.437,.009),.002,'#896C57',n=6)
# Working thread hangs from the tie-in point through a bobbin tube to a held spool.
rod('working thread',(.142,.43,.012),(.142,.334,.012),.0018,'#BDA47E',n=6)
rod('bobbin tube',(.142,.333,.012),(.142,.289,.012),.0045,'#B8C8C9',n=10)
for sign in [-1,1]:
 rod('bobbin arm',(.142,.289,.012),(.142+sign*.026,.258,.012),.0035,'#95AFB6',n=8)
rod('thread spool',(.116,.255,.012),(.168,.255,.012),.017,'#C5909E',n=12)
for x in [.116,.168]:rod('spool flange',(x-.002,.255,.012),(x+.002,.255,.012),.023,'#DCE0CF',n=12)
# A compact bench vise keeps the fly prominent. Shorten the exposed stem while
# translating the complete connected working assembly by the same amount.
for p in S['parts']:
 if p['name']=='weighted base':continue
 for v in p['vertices']:
  if p['name']=='stem' and v[1]<.04:continue
  v[1]-=.14
S['measurements']=dict(base_y=0,base_width=.33,stem_radius=.014,hook_shank_y=.295,clamp_contact=[.012,.253,0],hook_eye_radius=.009,paired_jaw_gap=.002)
S['notes']=['Original simplified bench vise and representative feather fly. Heavy base rests on y=0; compact stem, angled carrier and paired jaws connect. The hook bend passes through the jaw gap; the level shank and eye remain clear. Feather and thread attach to the hook shank; working thread connects to a hanging bobbin. This is an illustrative tying setup, not a precise fly recipe, manufacturing drawing or claim of supplied tools.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-036')/'geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
