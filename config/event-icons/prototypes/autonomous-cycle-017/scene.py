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
# Original drum, suspended paper sculpture, glider and actual-play studies.
def shift(parts,offset):
 for p in parts:p['vertices']=(np.array(p['vertices'])+offset).tolist()
def ring_x(name,x,cy,cz,r,width,thick,col,n=40):
 v=[]
 for xx,rr in [(x-width/2,r),(x+width/2,r),(x-width/2,r-thick),(x+width/2,r-thick)]:
  for a in np.linspace(0,2*math.pi,n,endpoint=False):v.append([xx,cy+rr*math.cos(a),cz+rr*math.sin(a)])
 faces=[]
 for i in range(n):
  j=(i+1)%n;faces.extend([[i,j,n+j,n+i],[2*n+i,3*n+i,3*n+j,2*n+j],[i,2*n+i,2*n+j,j],[n+i,n+j,3*n+j,3*n+i]])
 mesh(name,v,faces,col)
scene('dhol',(7,4,10))
# An isolated instrument study, no player or gravity/playing pose is implied.
# Length550mm, heads330mm across, widest shell380mm across.
profile=[(.165,-.275),(.171,-.23),(.183,-.14),(.190,0),(.183,.14),(.171,.23),(.165,.275)]
lathe('wood shell',profile,'#BC784E',48);p=S['parts'][-1];p['vertices']=[[y,.20+x,-z] for x,y,z in p['vertices']]
for sign in [-1,1]:
 rod('drumhead',(sign*.274,.20,0),(sign*.278,.20,0),.165,'#E8D9B7',48)
 ring_x('head hoop',sign*.271,.20,0,.177,.020,.010,'#DAA776')
# Rope segments follow the outer shell rather than cutting through its bulge.
for i in range(12):
 a=i*2*math.pi/12
 for da in [-math.pi/12,math.pi/12]:
  pts=[]
  for t in np.linspace(0,1,7):
   x=-.271+t*.542;rr=np.interp(x,[q[1] for q in profile],[q[0] for q in profile])+.009;ang=a+da*t
   pts.append((x,.20+rr*math.cos(ang),rr*math.sin(ang)))
  for p,q in zip(pts,pts[1:]):rod('tension rope',p,q,.0027,'#E5C99B',8)
# Three visible decorative tassels tied to rope junctions, not detached ornaments.
for x,ang,col in [(-.12,1.22,'#4AA8A5'),(.08,1.32,'#CC6C72'),(.22,1.35,'#4AA8A5')]:
 r=np.interp(x,[q[1] for q in profile],[q[0] for q in profile])+.011;y=.20+r*math.cos(ang);z=r*math.sin(ang)
 rod('tassel tie',(x,y,z),(x,y-.033,z),.0027,'#E5C99B',8);rod('tassel',(x,y-.03,z),(x,y-.075,z),.008,col,12,r2=.017)
# Separate accessory studies share the ground plane, clear of drum envelope.
rod('thin straight beater',(-.22,.009,.275),(.22,.009,.315),.0045,'#DBB775',10)
pts=[(-.19,.010,.36),(.10,.010,.40),(.15,.010,.395),(.18,.010,.37)]
for p,q in zip(pts,pts[1:]):rod('curved bass beater',p,q,.008,'#9D6746',12)
S['notes']=['Original Punjabi-style dhol study uses a550mm wooden shell,330mm heads and380mm maximum barrel diameter. Both membranes close the shell ends; annular hoops encircle the head edges.24 alternating rope segments follow the barrel exterior, with decorative tassels tied to ropes. Contrasting curved heavy and straight thin beaters are shown separately. This is an isolated instrument illustration, not a claimed supported playing pose or an exact performer instrument. Regional dhol construction varies; it does not depict tabla, dholak or a universal dhol model.']
scene('paper-gliders',(7,6,10))
# Two parallel paper hoops are taped above a straight straw, both bottom tangents align.
rod('straw',(-.12,.004,0),(.12,.004,0),.004,'#D6B171',16)
ring_x('large paper hoop',-.095,.050,0,.042,.025,.0012,'#5BAFBB',48)
ring_x('small paper hoop',.095,.029,0,.021,.025,.0012,'#E7B768',48)
for x in [-.095,.095]:box('attachment tape',(x,.0078,0),(.012,.0016,.013),'#C7DCD7')
# A folded dart shares one continuous center keel and symmetric connected wings.
# It is displayed separately from the hoop glider as a second workshop example.
o=np.array([-.03,-.002,.135]);verts=np.array([[.10,.022,0],[-.10,.022,0],[-.10,.002,0],[-.10,.032,-.060],[-.10,.032,.060]])+o
mesh('paper dart left',verts,[[0,1,3],[3,1,0]],'#E8D8B3');mesh('paper dart right',verts,[[0,4,1],[1,4,0]],'#B8D0CC');mesh('paper dart keel',verts,[[0,2,1],[1,2,0]],'#A9BEB9')
# All fold facets meet the shared ridge; doubled faces are thin paper, not solids.
S['notes']=['Hoop glider uses a240mm straight straw and25mm-wide paper bands with42mm and21mm radii. Both lower tangent surfaces are at8mm; tape overlaps the straw top at8mm and the paper edge. Hoop planes are parallel and normal to the straw. The large and small hoops are deliberately different sizes. A separate folded paper dart has symmetric wings joined to one central fold/keel. This is a static object study without flight or lift simulation; not a construction instruction promising performance.']
scene('mobiles',(2,1,12))
# Three equal-area cut-paper leaves; a symmetric lower pair and a measured top pivot.
leaf=[(0,0),(-.015,-.017),(-.038,-.035),(-.021,-.043),(-.042,-.065),(-.014,-.060),(0,-.084),(.014,-.060),(.042,-.065),(.021,-.043),(.038,-.035),(.015,-.017)]
leaf=[(x*1.7,y*1.7) for x,y in leaf]
# Uniform card density and equal shapes give matching paper loads. Rod masses included.
from shapely.geometry import Polygon
area=Polygon(leaf).area;leaf_mass=area*.24;rho_rod=500;rad=.0045;mass_per_m=math.pi*rad*rad*rho_rod
lower_length=.20;upper_length=.40;lower_mass=2*leaf_mass+lower_length*mass_per_m
upper_mass=upper_length*mass_per_m
pivot=(-.20*leaf_mass+.20*lower_mass)/(leaf_mass+lower_mass+upper_mass)
rod('top rail',(-.20,.37,0),(.20,.37,0),rad,'#B08A65',12)
rod('lower rail',(.10,.23,0),(.30,.23,0),rad,'#B08A65',12)
rod('ceiling suspension',(pivot,.37,0),(pivot,.46,0),.002,'#637F86',10)
rod('left string',(-.20,.37,0),(-.20,.25,0),.002,'#637F86',10)
rod('lower suspension',(.20,.37,0),(.20,.23,0),.002,'#637F86',10)
for x,y in [(.10,.23),(.30,.23)]:rod('leaf string',(x,y,0),(x,.16,0),.002,'#637F86',10)
for x,y,col in [(-.20,.25,'#D6A855'),(.10,.16,'#C97864'),(.30,.16,'#8DAF91')]:
 points=[(x+xx,y+yy) for xx,yy in leaf];extrude('paper leaf',points,-.0003,.0003,col)
 rod('leaf vein',(x,y-.020,.0005),(x,y-.120,.0005),.0012,'#F0D7AE',8)
# Endpoint loop is a visible suspension point at the upper edge, ceiling omitted.
S['notes']=['All three paper leaves share one outline, area and paper stock. Lower rail is centered between equal leaves. Upper support pivot is computed from two lower leaves plus their rail, one left leaf and uniform top-rail mass; string/paint mass is neglected. Top rail400mm, lower rail200mm. Every vertical string meets its rail and leaf attachment; the top suspension continues toward an implied ceiling outside the icon. Paper shapes are original, not a replica of a particular artist mobile. Static first-moment balance does not model swinging or air forces.']
S['measurements']=dict(leaf_area_m2=area,leaf_mass_kg=leaf_mass,rod_mass_per_m=mass_per_m,top_pivot_x_m=pivot,first_moment_residual=(-.20*leaf_mass+.20*lower_mass)-pivot*(leaf_mass+lower_mass+upper_mass))
scene('actual-play-show',(4,5,11))
# Folding game-master screen: three attached vertical panels resting on lower edges.
box('screen center',(0,.115,-.12),(.18,.23,.003),'#7E8FAC')
for side in [-1,1]:
 a=np.array([side*.09,0,-.12]);q=np.array([side*.17,0,-.055]);normal=np.cross(q-a,[0,1,0]);normal/=np.linalg.norm(normal);v=[a,q,q+[0,.23,0],a+[0,.23,0]]
 mesh('screen wing',v,[[0,1,2,3]],'#8798B8')
# Broad geometric emblem on the screen, not licensed fantasy or RPG branding.
panel('screen diamond',[(-.023,.12,-.118), (0,.091,-.118),(.023,.12,-.118),(0,.15,-.118)],'#D8BD7C')
# Equal-edge regular icosahedron; rotate one triangular face onto the work plane.
phi=(1+math.sqrt(5))/2;vs=np.array([(0,a,b) for a in [-1,1] for b in [-phi,phi]]+[(a,b,0) for a in [-1,1] for b in [-phi,phi]]+[(b,0,a) for a in [-1,1] for b in [-phi,phi]])
import itertools
faces=[]
for ids in itertools.combinations(range(12),3):
 a,bb,c=vs[list(ids)]
 if all(abs(np.linalg.norm(vs[i]-vs[j])-2)<1e-6 for i,j in itertools.combinations(ids,2)):
  ids=list(ids)
  if np.dot(np.cross(bb-a,c-a),(a+bb+c)/3)<0:ids.reverse()
  faces.append(ids)
normal=np.mean(vs[faces[0]],axis=0);normal/=np.linalg.norm(normal);target=np.array([0,-1,0]);axis=np.cross(normal,target);ss=np.linalg.norm(axis);cc=np.dot(normal,target);K=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]]);R=np.eye(3)+K+K@K*((1-cc)/(ss*ss))
vs=(vs@R.T)*.035;vs[:,1]-=vs[:,1].min();vs+=np.array([-.075,0,.10]);mesh('twenty sided die',vs,faces,'#BD807F')
# Joined die-face edges retain triangular recognition at native icon size.
for i,j in sorted({tuple(sorted((f[k],f[(k+1)%3]))) for f in faces for k in range(3)}):rod('die edge',vs[i],vs[j],.0009,'#E3B5AC',8)
# Tabletop microphone base, stem and capsule attach continuously.
rod('microphone base',(.105,0,.085),(.105,.014,.085),.043,'#637E87',32)
rod('microphone stem',(.105,.010,.085),(.105,.12,.085),.007,'#7696A0',16)
rod('microphone capsule',(.105,.10,.085),(.105,.175,.085),.025,'#9CB1B5',24)
ball('microphone top',(.105,.175,.085),.025,'#9CB1B5')
for y in [.132,.147,.162]:box('grille mark',(.105,y,.1102),(.031,.004,.001),'#526D75')
S['notes']=['Game-master screen has a center panel and two hinged wings, all with ground-contact lower edges. Regular20-faced die has equal original edges and is rotated onto one triangular face. A distinct tabletop microphone has connected base, stem, capsule and grille; it is separate from the die and screen. Original diamond emblem avoids licensed RPG logos. This symbolic still life depicts performed tabletop storytelling without claiming the exact live show furniture, player count or microphones.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-017')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
