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
scene('prize-wheel',(1,1.2,12))
# Original610mm wheel on a supported tabletop stand; no TV-game replica.
box('stand base',(0,.016,-.060),(.38,.032,.25),'#637780')
box('rear upright',(0,.415,-.055),(.052,.80,.035),'#637780')
rod('wheel axle',(0,.50,-.070),(0,.50,.034),.026,'#7D939B',24)
rod('wheel back',(0,.50,-.016),(0,.50,.016),.305,'#435F6B',72)
cols=['#C5787D','#6DA6AD','#DAB36E','#9390B0']
for i in range(12):
 arc=[(.286*math.cos(t),.50+.286*math.sin(t)) for t in np.linspace(i*math.pi/6,(i+1)*math.pi/6,9)]
 extrude('colored sector',[(0,.50)]+arc,.016,.019,cols[i%4])
 a=i*math.pi/6
 rod('rim peg',(.294*math.cos(a),.50+.294*math.sin(a),.014),(.294*math.cos(a),.50+.294*math.sin(a),.032),.006,'#D8C99F',12)
rod('hub',(0,.50,.019),(0,.50,.033),.037,'#E7DCC5',32)
# A fixed pointer hangs from the rear upright, independent of spinning disk.
box('pointer support',(0,.819,-.013),(.022,.028,.105),'#637780')
extrude('fixed pointer',[(0,.778),(.026,.832),(-.026,.832)],.041,.048,'#E4BF73')
S['notes']=['Generic610mm-diameter prize wheel has12 equal colored wedges,12 rim pegs and an attached central axle. Rear upright and broad base connect to the axle and touch the ground. A fixed top pointer attaches to a bracket on the upright and projects in front of the rim; it is not a second freely moving needle. All parts are original; no TV-game words, money labels, logos or exact stage equipment are reproduced. Static bearing alignment is modeled, not spin dynamics.']
S['measurements']=dict(diameter_m=.610,sector_count=12,sector_angle_deg=30,base_width_m=.38,base_depth_m=.25,pointer_front_clearance_m=.041-.032)
scene('duct-tape',(3,8,11))
# One48mm-wide roll with genuine through core, standing on one circular side.
ring_y('rolled blue tape',(-.04,0,0),.052,.034,.048,'#6B9BAA',56)
ring_y('cardboard core',(-.04,0,0),.034,.030,.048,'#C7AA7E',56)
# Wide free tape strip leaves the front tangent, then curves outward without cutting roll.
pts=[(-.04,.052),(-.005,.052),(.025,.057),(.048,.070),(.065,.081)]
v=[[x,y,z] for y in [0,.048] for x,z in pts];n=len(pts)
faces=[]
for i in range(n-1):faces.extend([[i,i+1,n+i+1,n+i],[n+i,n+i+1,i+1,i]])
mesh('loose wide tape',v,faces,'#79ADBB')
# Restrained crosshatch on the last broad face indicates cloth backing, not exact weave.
for t in [.3,.55,.8]:
 x=.048+t*.017;z=.070+t*.011
 rod('backing line',(x,.005,z+.0002),(x,.042,z+.0002),.00055,'#A0C7CD',8)
S['notes']=['Original colored duct tape roll is48mm wide,104mm outer diameter with a60mm clear core. A cardboard annulus lines the core. Both annuli rest on the same circular side at y0, and a wide strip starts at the front tangent then bends outward; its lower edge also meets the support plane. Only broad cloth-backing cues are retained. No exact roll brand, length, adhesive properties or finished class carrier is promised.']
S['measurements']=dict(tape_width_m=.048,outer_diameter_m=.104,core_clear_diameter_m=.060,core_wall_m=.004,tangent_start=[-.04,.052])
scene('fascinators',(3,4,12))
# A small domed percher base with original sculptural felt loops; no wearer.
profile=[(0,.022),(.035,.020),(.058,.012),(.067,.004),(.067,0),(0,0)]
lathe('felt percher base',profile,'#835C81',56);p=S['parts'][-1];p['vertices']=[[x,y,z*.74] for x,y,z in p['vertices']]
def felt_loop(name,origin,rx,high,angle,width,col):
 ox,oy,oz=origin;v=[];steps=36;angles=np.linspace(0,2*math.pi,steps,endpoint=False)
 for side in [-1,1]:
  for t in angles:
   along=rx*math.sin(t);cross=side*width/2
   v.append([ox+along*math.cos(angle)-cross*math.sin(angle),oy+high*(1-math.cos(t))/2,oz+along*math.sin(angle)+cross*math.cos(angle)])
 faces=[]
 for i in range(steps):
  j=(i+1)%steps;faces.extend([[i,j,steps+j,steps+i],[steps+i,steps+j,j,i]])
 mesh(name,v,faces,col)
felt_loop('tall sculpted felt loop',(-.015,.018,-.010),.035,.087,1.15,.052,'#BD7F94')
felt_loop('side sculpted felt loop',(.022,.017,.004),.036,.057,-.9,.043,'#D6A3B0')
# Small joined fastening bar sits directly under the base; no head or wearing pose implied.
box('fastening clip',(0,-.003,0),(.049,.006,.012),'#697A84')
S['notes']=['Original percher base is134x99mm with a22mm dome. Two thin double-sided felt strips form sculptural loops; both return to their attached points within the base. Loops rise87mm and57mm above their attachments and have52/43mm widths. A small fastening bar touches the underside. This is an isolated headpiece study without a wearer, head-contact fit or load simulation; finished felt is reshaped rather than made by wet felting. Forms are original and do not reproduce the class photograph.']
S['measurements']=dict(base_width_m=.134,base_depth_m=.09916,base_dome_m=.022,loop_heights_m=[.087,.057],loop_widths_m=[.052,.043])
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-019')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
