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
 x,y,z=c;n=16;rings=6;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
# Four equipment studies, all dimensions illustrative, no exact product replicas.
def move_last(c):
 S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])+c).tolist()
def flat_solid(name,outline,y0,y1,color):
 extrude(name,outline,y0,y1,color);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
scene('wet-felting',(3,8,10))
# Ribbed working mat, wet wool fibers, soap and small foam clusters.
box('mat',(0,.005,0),(.30,.010,.24),'#A9B9AC')
for x in np.linspace(-.14,.14,15):rod('rib',(x,.012,-.115),(x,.012,.115),.003,'#CAD3BD',8)
outline=[(-.110,-.065),(-.080,-.085),(-.024,-.077),(.024,-.087),(.095,-.065),(.107,-.025),(.098,.035),(.063,.070),(.015,.080),(-.040,.068),(-.093,.075),(-.115,.033)]
flat_solid('wool pad',outline,.015,.027,'#B386B1')
# Broad tapered wool wisps, rather than a crossed ribbon or stitched motif.
for dx,dz,ang in [(-.045,-.035,.2),(.025,-.025,-.3),(-.025,.015,.3),(.020,.040,-.3)]:
 pts=[]
 for t,w in [(-1,0),(-.6,.009),(0,.012),(.6,.008),(1,0),(.6,-.005),(0,-.008),(-.6,-.006)]:
  u=t*.055;v=w+.006*math.sin(t*math.pi);pts.append((dx+u*math.cos(ang)-v*math.sin(ang),.0275,dz+u*math.sin(ang)+v*math.cos(ang)))
 panel('wool fibers',pts,'#D4AFCD')
box('soap bar',(.088,.028,.091),(.063,.026,.036),'#E9D7A4')
for c,r in [((.065,.031,.060),.014),((.091,.039,.061),.010),((.031,.032,.054),.009)]:ball('soap foam',c,r,'#E6F3E9')
# A graphic water droplet is explicitly an emblem above the work, no pouring vessel.
pts=[(-.115,.116),(-.139,.081),(-.141,.065),(-.132,.052),(-.113,.049),(-.096,.058),(-.092,.074)]
extrude('water emblem',pts,-.102,-.098,'#70B9CD')
S['notes']=['Mat is30x24cm, with a1cm base and parallel ribs. Wool pad bottom y=.015 meets rib tops; fiber strokes are on its top. Soap and foam are illustrative wet-process cues. Droplet is a symbolic graphic, not a floating physical vessel. No needle, sewn seam or finished-hat claim.']
scene('sushi-making',(12,12,6))
#24cm makisu: parallel bamboo slats along x, thread bindings perpendicular.
for z in np.linspace(-.12,.12,15):rod('bamboo slat',(-.14,.007,z),(.14,.007,z),.007,'#CEA673',8)
for x in [-.10,.10]:rod('mat binding',(x,.014,-.122),(x,.014,.122),.0018,'#F3D9A7',8)
# A maki roll and its unfinished rice-covered sheet occupy the mat.
box('nori sheet',(0,.016,.016),(.18,.003,.090),'#43564E')
box('rice sheet',(-.003,.019,.012),(.166,.004,.077),'#F5EAD1')
rod('nori roll',(-.09,.053,-.027),(.09,.053,-.027),.032,'#43564E',40)
for side in [-1,1]:
 rod('rice end',(side*.0903,.053,-.027),(side*.091,.053,-.027),.027,'#F7EDD8',32)
 rod('cucumber end',(side*.0912,.058,-.033),(side*.092,.058,-.033),.010,'#7AAA75',16)
 rod('carrot end',(side*.0913,.044,-.020),(side*.0922,.044,-.020),.009,'#E59A72',16)
# Cut piece stands on mat at front-right, separate from the uncut roll.
rod('nori cut',(.077,.014,.088),(.077,.058,.088),.030,'#43564E',36)
rod('rice cut',(.077,.0582,.088),(.077,.0588,.088),.025,'#F7EDD8',36)
rod('cucumber cut',(.071,.059,.083),(.071,.0596,.083),.009,'#7AAA75',20)
rod('carrot cut',(.085,.059,.093),(.085,.0596,.093),.008,'#E59A72',20)
S['notes']=['Makisu measures28x24cm: bamboo runs parallel to roll axis, bindings run perpendicular, following Kikkoman construction. Filled roll rests above a partly prepared nori/rice sheet. Separate cut piece bottom meets slat top at y=.014. Rice/filling cross sections attach to cut ends. Food dimensions and colors are generic, not an exact recipe claim.']
scene('pond-dipping',(4,6,12))
# Shallow observation tray with water, paired with a poised dip-net diagram.
box('tray floor',(.035,.008,.13),(.30,.016,.19),'#CFD9CF')
frame('tray rim',(.035,.039,.13),.30,.19,.013,.046,'#CFD9CF')
box('water',(.035,.028,.13),(.272,.002,.162),'#8DBBC6')
# Net has a circular rim in the xy plane, a bag sagging behind it, and connected pole.
cx,cy,cz=-.070,.280,-.005;r=.103
for i in range(32):
 t=i*2*math.pi/32;u=(i+1)*2*math.pi/32
 rod('net rim',(cx+r*math.cos(t),cy+r*math.sin(t),cz),(cx+r*math.cos(u),cy+r*math.sin(u),cz),.0075,'#769C98',8)
# Mesh curves meet the hoop and sag to z=-.055 at center.
for d in [-.65,-.30,.05,.40,.72]:
 span=math.sqrt(1-d*d)
 for orient in [0,1]:
  pts=[]
  for t in np.linspace(-span,span,12):
   xx,yy=(d,t) if orient==0 else (t,d)
   pts.append((cx+xx*r,cy+yy*r,cz-.050*max(0,1-xx*xx-yy*yy)))
  for aa,bb in zip(pts,pts[1:]):rod('net mesh',aa,bb,.0024,'#9CB5AF',6)
a=(cx+r*.60,cy-r*.80,cz)
rod('net socket',a,(.005,.161,.010),.009,'#849B9D',12)
rod('net pole',(.005,.161,.010),(.11,.067,.045),.007,'#C19670',16)
rod('net grip',(.075,.098,.034),(.135,.044,.054),.013,'#A77557',16)
# One broad tadpole-style observation mark; illustrative, no species claim.
rod('observed organism',(.016,.030,.13),(.016,.031,.13),.012,'#5B797C',20)
panel('organism tail',[(.019,.0315,.133),(.043,.0315,.151),(.032,.0315,.126)],'#5B797C')
for part in S['parts']:
 if part['name'].startswith('tray') or part['name'] in ['water','observed organism','organism tail']:
  part['vertices']=[[x,y,z+.04] for x,y,z in part['vertices']]
S['notes']=['Tray30x19cm has a closed floor, joined rim and inset shallow water plane. Dip net hoop is20.6cm across with mesh curves meeting its circumference and sagging5cm behind the hoop. Socket connects hoop to pole and grip. Tray is shifted4cm forward to clear the poised grip by at least8mm at its back wall. Net is posed as an equipment diagram beside the tray, not claimed to balance unsupported in a real setting. Organism mark is generic, not a species identification or fishing hook.']
scene('cider-tasting',(3,6,12))
# Three small tasting tumblers on a wooden flight paddle, plus apple cue.
flat_solid('flight board',[(-.15,-.068),(.15,-.068),(.15,.065),(.036,.065),(.025,.105),(-.025,.105),(-.036,.065),(-.15,.065)],0,.012,'#BA895D')
for x,col in [(-.096,'#DDA25B'),(0,'#D0B66D'),(.096,'#C78B51')]:
 # Opaque tinted glass pictogram: outer profile surrounds stylized visible cider.
 lathe('tumbler',[(0,.012),(.022,.012),(.027,.019),(.033,.121),(.029,.121),(.024,.026),(0,.026)],'#B8CFCA',32);move_last((x,0,-.018))
 lathe('cider',[(0,.026),(.0238,.026),(.0270,.087),(0,.087)],col,32);move_last((x,0,-.018))
 # Deliberate front cutaway surface makes contents visible in opaque vector art.
 # Liquid colored side sits just outside the glass skin; symbolic transparency.
 for i in range(32):
  t=i*2*math.pi/32;tt=(i+1)*2*math.pi/32
  panel('visible cider',[(x+.02775*math.cos(t),.026,-.018+.02775*math.sin(t)),(x+.02775*math.cos(tt),.026,-.018+.02775*math.sin(tt)),(x+.0313*math.cos(tt),.087,-.018+.0313*math.sin(tt)),(x+.0313*math.cos(t),.087,-.018+.0313*math.sin(t))],col)
# Apple lies on board front-left; two lobes, connected stem and leaf.
for x in [-.069,-.045]:ball('apple',(x,.041,.057),.029,'#C87975')
rod('apple stem',(-.057,.065,.057),(-.050,.085,.054),.004,'#866A4D',10)
panel('apple leaf',[(-.052,.077,.055),(-.025,.089,.054),(-.019,.075,.057),(-.042,.073,.062)],'#779C70')
S['notes']=['Flight board supports three identical small tumblers; each bottom is y=.012, equal to board top. Closed outer/inner glass profile encloses the symbolic drink. Colored front overlay indicates transparency stylistically; this is not a refractive material simulation. Apple is a symbolic cider cue on the board; three glasses do not promise a particular number of samples, alcohol level or exact glassware.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four equipment scenes')
