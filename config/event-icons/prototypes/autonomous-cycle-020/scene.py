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
scene('rubber-stamping',(3,7,10))
# A mounted hand stamp stands beside an already printed paper, not levitating.
box('rubber die',(-.033,.002,-.012),(.050,.004,.038),'#54636A')
box('wood stamp mount',(-.033,.009,-.012),(.054,.010,.042),'#CF9F6B')
lathe('wood handle',[(0,.014),(.009,.014),(.009,.032),(.015,.044),(.015,.055),(.012,.058),(0,.058)],'#AA7553',40)
p=S['parts'][-1];p['vertices']=[[x-.033,y,z-.012] for x,y,z in p['vertices']]
box('printed paper',(.039,.0005,.020),(.069,.001,.064),'#EEE2C8')
def star(cx,cy,outer,inner):return [(cx+(outer if i%2==0 else inner)*math.sin(i*math.pi/5),cy+(outer if i%2==0 else inner)*math.cos(i*math.pi/5)) for i in range(10)]
flat_extrude('star impression',star(.039,.020,.020,.009),.001,.0012,'#729EA0')
# A corresponding small relief lies in the die footprint and shares the table plane.
flat_extrude('star die relief',star(-.033,-.012,.018,.008),0,.001,'#54636A')
S['notes']=['Original54x42mm wooden stamp mount supports a turned handle rising58mm overall. Rubber die and corresponding star relief contact the support plane. The paper beside it carries a separate completed ink impression; no floating tool or active pressing pose is shown. Wood/rubber/handle relationships follow manufacturer photographs, while dimensions and star motif are original. No exact stamp or tote design is promised.']
S['measurements']=dict(mount_m=[.054,.010,.042],height_m=.058,paper_m=[.069,.001,.064])
scene('cardboard-construction',(4,3,9))
# Original miniature cardboard architecture study; the actual workshop scale is unconfirmed.
card='#C5A174';roof='#B78C5D'
box('interior shaded back',(0,.045,-.0419),(.094,.09,.0002),'#856C50')
box('left wall',(-.0485,.045,0),(.003,.09,.09),card);box('right wall',(.0485,.045,0),(.003,.09,.09),card);box('rear wall',(0,.045,-.0435),(.094,.09,.003),card)
for name,x0,x1,y0,y1 in [('left post',-.05,-.034,0,.09),('door lintel',-.034,-.008,.055,.09),('center post',-.008,.012,0,.09),('window sill',.012,.037,0,.04),('window lintel',.012,.037,.066,.09),('right post',.037,.05,0,.09)]:box(name,((x0+x1)/2,(y0+y1)/2,.0435),(x1-x0,y1-y0,.003),card)
for z0 in [-.045,.042]:extrude('gable',[(-.05,.09),(.05,.09),(0,.132)],z0,z0+.003,card)
extrude('left roof',[(-.055,.088),(.001,.135),(.001,.131),(-.055,.084)],-.049,.049,roof)
extrude('right roof',[(-.001,.135),(.055,.088),(.055,.084),(-.001,.131)],-.049,.049,roof)
# Folded ridge tape follows both actual roof slopes.
extrude('ridge tape left',[(-.008,.128),(.001,.1355),(.001,.135),(-.008,.1275)],-.041,.041,'#E1C99E')
extrude('ridge tape right',[(-.001,.1355),(.008,.128),(.008,.1275),(-.001,.135)],-.041,.041,'#E1C99E')
box('front join tape',(-.042,.036,.0452),(.011,.035,.0004),'#E1C99E')
# Door is open55degrees, still joined to its vertical left hinge and ground plane.
box('folded door',(-.021,.0265,.0445),(.026,.053,.001),card)
p=S['parts'][-1];t=math.radians(55);p['vertices']=[[-.034+(x+.034)*math.cos(t)-(z-.0445)*math.sin(t),y,.0445+(x+.034)*math.sin(t)+(z-.0445)*math.cos(t)] for x,y,z in p['vertices']]
S['notes']=['Original100x90mm cardboard model has90mm walls and135mm ridge. Thin joined wall panels rest on the same plane. Front door and window are true openings; an open door is joined at its left hinge and reaches the floor. Both roof panels overlap the gables and meet at the ridge. Folded tape follows roof slopes and a front join. Dimensions are a small illustrative model, not the actual museum project, a structural building plan or a copied Makedo design.']
S['measurements']=dict(footprint_m=[.100,.090],wall_height_m=.09,ridge_height_m=.135,panel_thickness_m=.003,door_angle_deg=55,window_m=[.025,.026])
scene('ravioli',(1,10,7))
# Two sealed square pasta pillows; outline scallops do not substitute for raised filling.
def raviolo(name,origin,angle):
 ox,oz=origin;n=48;v=[]
 # Successive closed rings from underside to crimped rim and soft square mound.
 for size,y,ruffle in [(.049,0,.0007),(.050,.002,.0007),(.037,.0025,0),(.030,.0075,0),(.017,.012,0),(.004,.0127,0)]:
  for i in range(n):
   a=2*math.pi*i/n;x=math.copysign(abs(math.cos(a))**.45,math.cos(a))*size/2;z=math.copysign(abs(math.sin(a))**.45,math.sin(a))*size/2
   bump=ruffle*math.cos(i*math.pi);x+=bump*math.cos(a);z+=bump*math.sin(a)
   v.append([ox+x*math.cos(angle)-z*math.sin(angle),y,oz+x*math.sin(angle)+z*math.cos(angle)])
 faces=[list(range(n)),list(range(6*n-1,5*n-1,-1))]
 # outward normals: increasing angles point clockwise viewed from above.
 for j in range(5):
  for i in range(n):faces.append([j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n])
 mesh(name+' sealed rim',v,faces[:1]+faces[2:2+n*2],'#DAB064')
 mesh(name+' filled center',v,faces[1:2]+faces[2+n*2:],'#F1CE86')
raviolo('rear pasta pillow',(-.015,-.032),-.22)
raviolo('front pasta pillow',(.014,.025),.30)
S['notes']=['Two original approximately50mm square ravioli have a thin sealed outer rim, scalloped cut edges and a12.7mm raised filling mound. Both undersides rest on one plane; separate centers avoid interpenetration. Primary class photographs show square ravioli formed over ricotta filling; Eataly describes an approximately2inch square mold. These are generic filled pasta pieces without a promised exact cutter, serving sauce, recipe or process simulation.']
S['measurements']=dict(width_m=.050,maximum_height_m=.0127,centers=[[-.015,-.032],[.014,.025]],rim_height_m=.002)
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-020')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
