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
# Original book structures, marbling tray, and cardboard-enrichment studies.
scene('long-stitch-binding',(-8,4,9))
cover='#8EA9A6';paper='#E8DDC6';thread='#B78484'
# Standing closed book. Three folded sections occupy distinct depth layers.
for side in [-1,1]:box('soft cover',(0,.12,side*.026),(.16,.24,.003),cover)
from shapely.geometry import Polygon,Point
from shapely.ops import triangulate
from shapely.geometry.polygon import orient
stations=[.024,.082,.158,.216];sections=[-.016,0,.016]
spine=Polygon([(0,-.0275),(.24,-.0275),(.24,.0275),(0,.0275)])
for z in sections:
 for y in stations:spine=spine.difference(Point(y,z).buffer(.0026,resolution=10))
for tri in triangulate(spine):
 if spine.covers(tri.representative_point()):
  extrude('pierced cover spine',list(orient(tri,sign=1).exterior.coords)[:-1],-.080,-.077,cover);p=S['parts'][-1];p['vertices']=[[z,x,y] for x,y,z in p['vertices']]
# Sections are nested folded leaves rather than glued hardback blocks.
for z in sections:
 for j in range(3):
  rr=.006-j*.0015;outline=[(-.071,.006),(.077,.006),(.077,.234),(-.071,.234)]
  for side in [-1,1]:box('signature leaves',(.003,.12,z+side*rr),(.148,.228,.0012),paper)
  # Half-cylinder fold joins the two leaves around the spine edge.
  verts=[];n=14
  for y in [.006,.234]:
   for a in np.linspace(math.pi/2,3*math.pi/2,n):verts.append([-.071+rr*math.cos(a),y,z+rr*math.sin(a)])
  mesh('signature fold',verts,[[i,n+i,n+i+1,i+1] for i in range(n-1)],paper)
 # A continuous illustrated thread path passes through the spine/section stations.
 xout=-.082;xin=-.067
 points=[(xin,stations[0],z),(xout,stations[0],z),(xout,stations[1],z),(xin,stations[1],z),(xin,stations[2],z),(xout,stations[2],z),(xout,stations[3],z),(xin,stations[3],z),(xin,stations[0],z)]
 for a,bb in zip(points,points[1:]):rod('long stitch',a,bb,.0012,thread,10)
# Cover label is blank and decorative, attached to the cover surface.
panel('cover label',[(-.033,.15,.0277),(.050,.15,.0277),(.050,.192,.0277),(-.033,.192,.0277)],'#D8C39B')
S['notes']=['Three folded paper sections lie between a continuous three-panel soft cover. A pierced spine has four sewing stations per section. Long external thread runs alternate with internal runs, passing through the prepared stations and tying the section to its cover. Original illustrative geometry depicts the defining through-cover spine sewing, not a complete instructional stitch sequence. Cover lower edges meet the ground; the paper sections begin .006m above it and attach to the cover through stitching; the fine internal fold detail is retained for inspection, not expected to resolve at16px.']
scene('book-slipcase',(7,4,10));case='#9A95AE'
# Four lined boards form a protective sleeve, open at both ends along x.
for z in [-.030,.030]:box('case side',(0,.128,z),(.18,.256,.006),case)
for y in [.003,.253]:box('case cap',(0,y,0),(.18,.006,.054),case)
# Partly withdrawn book keeps its lower cover edge on the sleeve floor y=.006.
for z in [-.023,.023]:box('book cover',(.065,.126,z),(.17,.24,.002),'#D1AC7D')
box('book pages',(.066,.126,0),(.164,.23,.044),'#E7DEC7')
box('book spine',(.149,.126,0),(.002,.24,.048),'#C49C6D')
# Spine label is a surface emblem; all pieces share the insertion axis.
panel('spine label',[(.1503,.13,-.015),(.1503,.13,.015),(.1503,.19,.015),(.1503,.19,-.015)],'#EEE2C3')
# Lining planes stay on the case cavity surface, leaving3mm side clearance.
for side in [-1,1]:panel('case lining',[(-.089,.006,side*.0269),(.089,.006,side*.0269),(.089,.250,side*.0269),(-.089,.250,side*.0269)],'#B7ACC0')
S['notes']=['Four joined cloth-covered boards enclose a rectangular book sleeve, with open insertion ends along x. Interior depth .054m clears book outside depth .048m by3mm on each side. Inner height .244m clears the .240m book, whose bottom meets the sleeve floor at y=.006m. A partly withdrawn book remains aligned with the cavity and supported by its overlapping section. Book cover, pages and spine join; the label is surface-attached. This is a generic four-board slipcase/sleeve, not the exact class project or a clamshell box.']
scene('paper-marbling',(4,7,10))
# Shared work plane y=0. Tray and separate sample sheet both rest on it.
cx=.08
box('tray floor',(cx,.003,0),(.32,.006,.40),'#A1AEB4')
for x in [cx-.157,cx+.157]:box('tray side',(x,.023,0),(.006,.04,.40),'#A1AEB4')
for z in [-.197,.197]:box('tray end',(cx,.023,z),(.308,.04,.006),'#A1AEB4')
box('sizing bath',(cx,.016,0),(.308,.020,.388),'#D8E2D8')
# Broad original pigment ribbons lie on the bath surface; no fluid simulation claimed.
for x0,col in [(-.105,'#9AAAC0'),(-.035,'#C296A7'),(.037,'#D2B681')]:
 pts=[]
 for z in np.linspace(-.188,.188,42):pts.append([cx+x0+.015*math.sin(z*24),.0262,z])
 for z in np.linspace(.188,-.188,42):pts.append([cx+x0+.036+.015*math.sin(z*24),.0262,z])
 panel('floating pigment',pts,col)
# Rake handle bridges side rims at y=.043; nine tines enter the bath.
box('rake bar',(cx,.050,-.090),(.35,.014,.015),'#BEA07A')
for x in np.linspace(cx-.125,cx+.125,9):rod('rake tine',(x,.043,-.09),(x,.022,-.09),.0018,'#89999D',10)
# Finished paper laid flat beside the tray, not an unsupported floating sheet.
box('sample paper',(-.180,.001,.045),(.15,.002,.245),'#EFE2C2')
for x0,col in [(-.223,'#9AAAC0'),(-.189,'#C296A7'),(-.155,'#D2B681')]:
 pts=[]
 for z in np.linspace(-.067,.157,26):pts.append([x0+.007*math.sin(z*31),.0022,z])
 for z in np.linspace(.157,-.067,26):pts.append([x0+.015+.007*math.sin(z*31),.0022,z])
 panel('sample marbling',pts,col)
S['notes']=['Tray has a joined floor and four walls. Bath top y=.026m is below rim y=.043m; pigment ribbons are attached to that surface. Rake bar bottom y=.043m rests across both side rims, and all9 equal tines descend into the bath to y=.022m. Finished sample paper rests separately at ground level and carries matching illustrative patterns. No hand, pouring pose or physical fluid dynamics are implied.']
scene('animal-enrichment-making',(5,5,10))
# Cardboard play tunnel: .17m outer diameter, .156m clear bore, .28m long.
verts=[];n=44
for x,r in [(-.14,.085),(.14,.085),(-.14,.078),(.14,.078)]:
 for a in np.linspace(0,2*math.pi,n,endpoint=False):verts.append([x,.085+r*math.cos(a),r*math.sin(a)])
faces=[]
for i in range(n):
 j=(i+1)%n;faces += [[i,j,n+j,n+i],[2*n+i,3*n+i,3*n+j,2*n+j],[i,2*n+i,2*n+j,j],[n+i,n+j,3*n+j,3*n+i]]
mesh('cardboard tunnel',verts,faces,'#CAA77D')
# Short cardboard strips represent materials on the same working plane.
for x,z,w,d in [(.17,-.045,.09,.19),(.18,.07,.10,.07)]:box('cardboard stock',(x,.0015,z),(w,.003,d),'#DCC09A')
# Supported card carries a generic paw pictogram: a sign, not part of the toy.
box('sign foot',(-.035,.006,-.16),(.14,.012,.070),'#9FAE9B');box('paw card',(-.035,.183,-.171),(.17,.22,.006),'#DCE2CD')
box('sign stem',(-.035,.049,-.171),(.015,.074,.009),'#9FAE9B')
def markball(name,c,r,col):
 ball(name,(0,0,0),1,col);S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])*r+c).tolist()
markball('paw pad',(-.035,.164,-.166),(.031,.026,.002),'#8AA09B')
for x,y in [(-.079,.203),(-.052,.222),(-.018,.222),(.009,.203)]:markball('paw toe',(x,y,-.166),(.013,.018,.002),'#8AA09B')
S['notes']=['Open cardboard tunnel has continuous inner and outer walls and both annular ends; outer radius .085m equals center height, so the tube meets y=0. Separate cardboard materials rest on the ground. Paw-sign stem reaches its foot and card; the paw is a planar animal-category symbol. Tunnel is a representative enrichment object, not a promise that this specific project is used for every animal or any animal-care instruction. No food, animal interaction or species-specific scale is claimed.']
if __name__=='__main__':(ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
