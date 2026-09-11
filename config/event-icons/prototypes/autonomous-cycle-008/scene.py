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
# All volumes are illustrative, in metres; no human anatomy is implied.
scene('cake-decorating',(3,6,12))
lathe('cake plate',[(0,0),(.18,0),(.185,.012),(.18,.022),(0,.022)],'#86B3BD',48)
lathe('cake',[(0,.022),(.142,.022),(.15,.030),(.15,.115),(.143,.125),(0,.125)],'#E7BABB',48)
lathe('cake icing',[(0,.12),(.14,.12),(.143,.107),(.15,.105),(.15,.12),(.145,.128),(0,.128)],'#F8E3C7',48)
# A ring of piped frosting beads sits on the cake surface.
for t in np.linspace(.3,5.6,15):
 ball('frosting bead',(.123*math.cos(t),.132,.123*math.sin(t)),.013,'#D8879A')
# Illustrative piping bag poised over the near right border; joined conical tip.
x,z=.115,.045
rod('piping tip',(x,.145,z),(x,.175,z),.007,'#98B1BC',16,r2=.014)
rod('piping bag',(x,.175,z),(x,.31,z),.014,'#86B5BD',32,r2=.055)
rod('gathered bag',(x,.31,z),(x,.337,z),.055,'#86B5BD',24,r2=.016)
rod('twisted tail',(x,.337,z),(x,.357,z),.016,'#648F9F',16,r2=.023)
S['notes']=['Illustrative30cm round cake sits on plate; frosting and border beads meet its upper surface. Bag, gathered neck and metal nozzle are joined. Nozzle sits just above border at x=.115,z=.045 as a decorating-tool diagram; no invisible hand or gravity claim.']
scene('journaling',(1,18,8))
# Two shallow open book halves with visible page block, binding and ribbon.
box('journal cover',(0,.009,0),(.42,.018,.29),'#769EA0')
box('page block',(-.103,.029,0),(.192,.022,.27),'#F3E8D1')
box('page block',(.103,.029,0),(.192,.022,.27),'#F3E8D1')
box('binding',(0,.026,0),(.014,.028,.27),'#CFB99C')
for x in [-.104,.104]:
 for z in [-.072,-.015,.042,.099]:box('journal line',(x,.0408,z),(.137,.0016,.0035),'#B9C7CA')
# Page-top pen rests on the right leaf, both endpoints clear of the binding.
rod('pen body',(.055,.052,-.098),(.142,.052,.073),.012,'#647BB1',16)
rod('pen point',(.142,.052,.073),(.150,.052,.089),.012,'#B0BDC8',16,r2=.001)
rod('pen end',(.047,.052,-.114),(.055,.052,-.098),.012,'#DBB975',16)
box('ribbon',(-.069,.024,.157),(.023,.003,.044),'#D68C91')
# A small personal-entry heart lies on the left page, above the ruled lines.
outline=[(-.122,-.115),(-.134,-.104),(-.134,-.093),(-.123,-.086),(-.108,-.097),(-.093,-.086),(-.082,-.093),(-.082,-.104),(-.108,-.123)]
panel('heart entry',[(x,.042,-z-.216) for x,z in outline],'#D88B96')
S['notes']=['Open journal has two page blocks joined by binding over one cover. Pen radius equals its support offset over page top, with both endpoints within right page. Ribbon crosses lower cover edge. Heart and ruled strokes are planar personal-entry symbols, not text.']
scene('vintage-clothing-market',(1,2,12))
for x in [-.40,.40]:
 rod('rack upright',(x,.03,0),(x,.72,0),.016,'#8CA4A8',16)
 rod('rack foot',(x,.025,-.12),(x,.025,.12),.018,'#7C949A',16)
rod('clothes rail',(-.40,.72,0),(.40,.72,0),.016,'#8CA4A8',16)
def hanger(x):
 # Closed triangular shoulder support and curved hook meeting the rail.
 for a,bb in [((x-.135,.61,0),(x,.665,0)),((x,.665,0),(x+.135,.61,0)),((x+.135,.61,0),(x-.135,.61,0))]:rod('hanger',a,bb,.005,'#C79C66',12)
 points=[(x,.665,0),(x,.686,0),(x+.014,.703,0),(x+.024,.724,0),(x+.009,.737,0),(x-.010,.732,0),(x-.014,.716,0)]
 for a,bb in zip(points,points[1:]):rod('hanger hook',a,bb,.004,'#7E979A',12)
hanger(-.19);hanger(.18)
# Front/back dress surfaces share silhouette; sleeves and skirt are connected.
outline=[(-.27,.62),(-.32,.59),(-.36,.50),(-.30,.48),(-.27,.53),(-.26,.40),(-.35,.17),(-.03,.17),(-.12,.40),(-.11,.53),(-.08,.48),(-.02,.50),(-.06,.59),(-.11,.62),(-.15,.60),(-.19,.57),(-.23,.60)]
extrude('dress',outline,-.013,.019,'#76A9A3')
box('dress belt',(-.19,.40,.022),(.143,.022,.008),'#D9AB71')
panel('left collar',[(-.27,.62,.025),(-.23,.60,.025),(-.19,.57,.025),(-.23,.55,.025)],'#F0DEC0')
panel('right collar',[(-.11,.62,.025),(-.15,.60,.025),(-.19,.57,.025),(-.15,.55,.025)],'#F0DEC0')
for y in [.53,.475]:rod('dress button',(-.19,y,.023),(-.19,y,.028),.005,'#DBB783',12)
# Folded trousers over the second hanger's lower bar; both legs same length.
extrude('trousers',[(.055,.613),(.305,.613),(.292,.18),(.193,.18),(.18,.37),(.167,.18),(.068,.18)],-.012,.014,'#B28776')
box('waistband',(.18,.603,.019),(.25,.026,.01),'#956F64')
# Resale tag is tied to the front of the rail, physically separate from clothing.
rod('tag cord',(.32,.72,.005),(.32,.60,.052),.003,'#A07955',12)
extrude('price tag',[(.28,.60),(.36,.60),(.367,.58),(.367,.49),(.273,.49),(.273,.58)],.045,.052,'#E7BD74')
rod('tag eye',(.32,.578,.052),(.32,.578,.054),.006,'#987751',16)
S['notes']=['Both rack feet support equal-height uprights and one connected rail. Each hanger hook crosses the rail; shoulder bars pass inside joined dress shoulders and the second hanger supports folded trousers. Two trouser legs have identical height. Garment silhouette is a generic vintage-inspired shirtwaist, not an exact era artifact. Tag is tied to rail; blank tag conveys resale without invented price.']
scene('library-shelving',(3,4,12))
# Two equal-depth shelves joined to the uprights and a backing panel.
box('shelf back',(0,.285,-.105),(.60,.56,.018),'#BA946F')
for x in [-.295,.295]:box('shelf side',(x,.285,0),(.025,.57,.23),'#C9996B')
for y in [.025,.28,.555]:box('shelf board',(0,y,0),(.60,.025,.23),'#C9996B')
def book(name,x,y,w,h,col,z=0):
 box(name,(x,y+h/2,z),(w,h,.175),col)
 for yy in [y+.025]:panel('spine band',[(x-w*.325,yy-.004,z+.088),(x+w*.325,yy-.004,z+.088),(x+w*.325,yy+.004,z+.088),(x-w*.325,yy+.004,z+.088)],'#E7D5AF')
for x,w,h,col in [(-.239,.060,.18,'#7E9DB2'),(-.163,.065,.20,'#C88489'),(-.090,.055,.17,'#89A89A'),(.00,.085,.21,'#D5B26E'),(.105,.065,.18,'#8D91B6'),(.19,.07,.205,'#86A6A8')]:book('upper book',x,.293,w,h,col)
for x,w,h,col in [(-.235,.07,.20,'#A9B8B5'),(-.15,.065,.21,'#B6A0B4'),(.17,.073,.19,'#DAB882'),(.24,.048,.20,'#7C9EB5')]:book('lower book',x,.038,w,h,col)
# A sorting book pulled forward from the lower shelf, supported by its base.
book('sorting book',-.02,.038,.10,.207,'#648CA4',z=.092)
S['notes']=['Books rest on board tops y=.038 and y=.293. Joined side panels, back and boards make a two-shelf unit. Sorting book is pulled forward but still overlaps the supporting shelf depth by .11m; no unsupported floating volume. Room, call numbers and exact shelving system are not represented.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four equipment scenes')
