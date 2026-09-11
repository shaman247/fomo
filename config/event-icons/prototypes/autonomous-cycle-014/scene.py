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
# Original household-sale scene and closed-wing butterfly study.
def shift_last(v):S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])+v).tolist()
scene('yard-sale',(4,6,12))
box('lawn',(0,.009,0),(1.06,.018,.64),'#A0B08F')
for x in [-.38,.38]:
 for z in [-.20,.20]:box('table leg',(x,.356,z),(.04,.676,.04),'#879E9C')
box('table top',(0,.712,0),(.90,.036,.49),'#C7A477')
for z in [-.20,.20]:box('table apron',(0,.670,z),(.80,.050,.024),'#A48869')
for x in [-.38,.38]:box('table apron',(x,.670,0),(.024,.050,.42),'#A48869')
# Two closed household books, with page blocks inside covers.
for y,w,d,col in [(.753,.28,.18,'#919BAA'),(.799,.23,.17,'#B8A18A')]:
 for yy in [y-.020,y+.020]:box('book cover',(.15,yy,.005),(w,.006,d),col)
 box('book page block',(.152,y,.006),(w-.009,.034,d-.008),'#E6DEC9')
 box('book spine',(.15-w/2+.003,y,.005),(.006,.046,d),col)
# Potted household plant: pot walls include an inner lip and closed floor.
lathe('plant pot',[(0,0),(.065,0),(.078,.016),(.083,.155),(.091,.155),(.091,.17),(.075,.17),(.069,.026),(0,.026)],'#C79472',32);shift_last((-.258,.730,-.010))
lathe('soil',[(0,0),(.074,0),(.074,.004),(0,.004)],'#89775F',24);shift_last((-.258,.880,-.010))
rod('plant stem',(-.258,.883,-.010),(-.258,1.090,-.010),.010,'#799977',12)
for x,y,z,rx,ry,rz in [(-.30,1.02,-.01,.060,.032,.022),(-.215,1.06,-.01,.060,.032,.022),(-.258,1.12,-.01,.031,.06,.021)]:
 ball('plant leaf',(0,0,0),1,'#8FA87B');part=S['parts'][-1];part['vertices']=(np.array(part['vertices'])*[rx,ry,rz]+[x,y,z]).tolist()
# Small mug on the table, with a connected C-shaped handle and hollow mouth.
lathe('mug',[(0,0),(.049,0),(.056,.014),(.057,.135),(.049,.135),(.047,.018),(0,.018)],'#99ADB5',32);shift_last((.315,.730,-.068))
verts=[];m,n=20,10
for i in range(m+1):
 t=-math.pi/2+i*math.pi/m;center=np.array([.365+.043*math.cos(t),.797+.044*math.sin(t),-.068]);normal=np.array([math.cos(t),math.sin(t),0])
 for j in range(n):verts.append(center+.010*(normal*math.cos(j*2*math.pi/n)+np.array([0,0,1])*math.sin(j*2*math.pi/n)))
mesh('mug handle',verts,[[i*n+j,(i+1)*n+j,(i+1)*n+(j+1)%n,i*n+(j+1)%n] for i in range(m) for j in range(n)],'#99ADB5')
# Hanging price-tag polygon has an actual round aperture, triangulated from its outline.
from shapely.geometry import Polygon,Point
from shapely.ops import triangulate
from shapely.geometry.polygon import orient
poly=Polygon([(.08,.48),(.27,.48),(.27,.60),(.18,.69),(.08,.60)]).difference(Point(.18,.637).buffer(.013,resolution=12))
for t in triangulate(poly):
 if poly.covers(t.representative_point()):extrude('price tag',list(orient(t,sign=1).exterior.coords)[:-1],.252,.256,'#E4C485')
rod('tag peg',(.18,.712,.236),(.18,.712,.265),.008,'#8D9F9D',12)
rod('tag string',(.18,.711,.265),(.18,.637,.259),.0025,'#7A8E91',8)
rod('tag string return',(.18,.637,.259),(.18,.711,.248),.0025,'#7A8E91',8)
for y,w in [(.563,.080),(.536,.058)]:panel('price mark',[(.132,y,.2565),(.132+w,y,.2565),(.132+w,y+.008,.2565),(.132,y+.008,.2565)],'#A18F6E')
S['notes']=['Four table legs meet the lawn and underside of the top; apron rails join the legs. Nested book covers/page blocks rest on the top. Potted plant and hollow mug bases meet tabletop y=.730. Mug C-handle ends enter its vessel wall and the pot has a closed floor, inner lip and soil. Price tag has a real circular aperture and a two-segment string loop returning to a table peg. Household items represent mixed resale, not a guaranteed sale inventory.']
scene('monarch-tagging',(0,0,10))
# Butterfly coordinates below are original illustrative lateral profiles, scaled later.
def curve(start,*segments):
 out=[start];p=np.array(start)
 for c1,c2,end in segments:
  c1,c2,end=map(np.array,[c1,c2,end])
  for t in np.linspace(0,1,13)[1:]:out.append(((1-t)**3*p+3*(1-t)**2*t*c1+3*(1-t)*t*t*c2+t**3*end).tolist())
  p=end
 return out
fore=curve((.041,.058),((.013,.123),(-.010,.207),(-.056,.214)),((-.094,.223),(-.105,.178),(-.080,.127)),((-.107,.095),(-.035,.038),(.041,.058)))
hind=curve((.038,.063),((-.013,.122),(-.070,.153),(-.107,.114)),((-.142,.069),(-.108,.019),(-.074,.022)),((-.025,.017),(.007,.033),(.038,.063)))
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
black='#4C5557';orange='#D89E61';pale='#F0E6CC'
def plate(name,outline,z,color):extrude(name,list(orient(Polygon(outline),sign=1).exterior.coords)[:-1],z-.0005,z+.0005,color)
def decal(name,outline,z,color):panel(name,[[x,y,z] for x,y in outline],color)
# Paired fore/hind wings are folded on opposite sides of the thorax.
for side in [-1,1]:
 for name,path,z,col,cx,cy in [('forewing',fore,side*.003,orange,-.030,.119),('hindwing',hind,side*.006,'#E3AD68',-.044,.076)]:
  plate(name,path,z,black)
  inset=[(cx+(x-cx)*.89,cy+(y-cy)*.89) for x,y in path];decal(name+' orange',inset,z+side*.0006,col)
  root=(.028,.063)
  ends=[(-.059,.195),(-.075,.162),(-.077,.122),(-.022,.155)] if name=='forewing' else [(-.090,.117),(-.108,.094),(-.110,.061),(-.091,.036),(-.059,.030),(-.025,.038)]
  if name=='forewing':
   lines=[(root,end) for end in ends]
  else:
   # Closed elongated hindwing cell around the tag, with veins branching to the margin.
   cell=[(.028,.063),(-.025,.101),(-.057,.102),(-.072,.086),(-.070,.067),(-.048,.059),(.028,.063)]
   lines=list(zip(cell,cell[1:]))+[(cell[i],end) for i,end in zip([2,3,4,5,5,0],ends)]
  for (ax,ay),(ex,ey) in lines:
   rod('wing vein',(ax,ay,z+side*.0008),(ex,ey,z+side*.0008),.0019,black,8)
  spots=[(-.054,.207),(-.074,.203),(-.085,.186),(-.086,.169),(-.081,.150),(-.066,.121),(-.037,.113)] if name=='forewing' else [(-.100,.117),(-.113,.102),(-.122,.083),(-.119,.064),(-.110,.046),(-.096,.033),(-.077,.028)]
  for x,y in spots:rod('border spot',(x,y,z+side*.0007),(x,y,z+side*.001),.0032,pale,14)
# Continuous body segments: abdomen, thorax, head; white body spots remain sparse.
for name,c,radii in [('abdomen',(-.006,.043,0),(.042,.010,.008)),('thorax',(.034,.053,0),(.018,.014,.011)),('head',(.058,.054,0),(.012,.011,.009))]:
 ball(name,(0,0,0),1,black);S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])*radii+c).tolist()
for side in [-1,1]:
 # Reduced front legs fold against thorax; middle/rear pairs extend below body.
 for a,j,t in [((.039,.047,side*.007),(.044,.039,side*.011),(.035,.041,side*.012)),((.026,.045,side*.009),(.028,.022,side*.012),(.014,.017,side*.013)),((.012,.044,side*.008),(.009,.024,side*.011),(-.007,.018,side*.012))]:
  rod('leg upper',a,j,.0017,black,8);rod('leg lower',j,t,.0014,black,8)
 # Two separate clubbed antennae join the head, with curved two-segment stalks.
 a=(.062,.060,side*.005);j=(.069,.093,side*.008);t=(.083,.109 if side==1 else .118,side*.009)
 rod('antenna lower',a,j,.0015,black,8);rod('antenna upper',j,t,.0013,black,8);ball('antenna club',t,.003,black)
# Mark sits on the visible underside hindwing, in the large central discal region.
rod('tag disc',(-.047,.079,.0072),(-.047,.079,.0080),.014,pale,40)
# Abstract short code lines, not Monarch Watch branding or a usable tag number.
for y,w in [(.083,.014),(.077,.019),(.071,.011)]:panel('tag mark',[(-.047-w/2,y,.0081),(-.047+w/2,y,.0081),(-.047+w/2,y+.002,.0081),(-.047-w/2,y+.002,.0081)],'#7A8584')
for part in S['parts']:part['vertices']=(np.array(part['vertices'])*.3).tolist()
S['notes']=['Closed wing pairs attach beside the thorax; the lateral icon shows the underside of one fore/hind pair, with the opposite pair behind. The hindwing bears one circular mark in its central discal-cell region, following Monarch Watch’s primary placement reference. Six legs include reduced folded front legs, and two separate clubbed antennae attach to the head. Wing contours, vein network and white spot count are deliberately simplified; this is category artwork, not a handling guide, taxonomic plate or official tag. Overall shape is about6cm tall at illustrative scale; tag diameter about8.4mm.']
if __name__=='__main__':(ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
