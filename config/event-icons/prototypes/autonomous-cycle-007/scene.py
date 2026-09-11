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
scene('meal-packing',(3,8,10))
box('container bottom',(0,.012,0),(.42,.024,.30),'#D6C9AE')
frame('tray wall',(0,.040,0),.42,.30,.023,.060,'#DCCFB6')
box('meal divider',(.025,.045,0),(.014,.042,.26),'#DCCFB6')
box('rice',(-.09,.04,0),(.15,.035,.23),'#E2C38B')
for x,z in [(.095,-.075),(.155,-.04),(.10,.035),(.15,.075)]:ball('vegetables',(x,.050,z),.027,'#85A276')
# Lid is hinged at back rim and held open; the lid is empty, food stays in tray.
panel('lid outer',[(-.21,.07,-.15),(.21,.07,-.15),(.21,.28,-.23),(-.21,.28,-.23)],'#D4C6AA')
panel('lid inset',[(-.185,.091,-.156),(.185,.091,-.156),(.185,.258,-.22),(-.185,.258,-.22)],'#EDE1C7')
S['notes']=['Container walls and divider join base; food lies below rim. Lid hinges at back rim and rises outward; no hand or exact meal recipe is promised.']
scene('community-meal-prep',(3,5,12))
# Large open stockpot; dimensions approximately36cm diameter and30cm high.
lathe('pot',[(0,0),(.17,0),(.18,.015),(.18,.285),(.19,.30),(.176,.30),(.164,.28),(.164,.025),(0,.025)],'#98ADB8',48)
for side in [-1,1]:
 x=side*.18
 for y in [.20,.25]:rod('pot handle',(x,y,0),(x+side*.07,y,0),.012,'#738D9D',12)
 rod('pot handle',(x+side*.07,.20,0),(x+side*.07,.25,0),.012,'#738D9D',12)
rod('pot contents',(0,.235,0),(0,.238,0),.157,'#C5B887',40)
# Separate preparation board and knife; all their supporting surfaces meet.
box('board',(.39,.013,.14),(.31,.026,.24),'#C69367')
box('knife blade',(.32,.029,.185),(.16,.006,.043),'#C3D0D3')
box('knife handle',(.46,.035,.185),(.12,.018,.038),'#657A80')
for x in [.32,.41]:rod('carrot',(x,.044,.085),(x+.07,.030,.015),.018,'#DEA064',20,r2=.004)
S['notes']=['Pot has continuous outer and inner wall with a closed floor; contents lie below rim. Handle loops join the pot. Board shares y=0; knife and carrots rest on board top. Illustrative preparation tools, not a specific recipe.']
scene('meal-service',(2,8,10))
lathe('bowl',[(0,0),(.085,0),(.11,.014),(.14,.04),(.163,.08),(.185,.145),(.17,.145),(.149,.084),(.129,.045),(.085,.018),(0,.018)],'#89AEBB',48)
rod('soup',(0,.088,0),(0,.091,0),.143,'#D8B67F',40)
# Ladle scoop rests inside the bowl. Its handle crosses and rests on the right rim.
before=len(S['parts']);lathe('ladle cup',[(0,.058),(.04,.064),(.059,.10),(.053,.107),(.033,.075),(0,.072)],'#98B4C0',32)
for part in S['parts'][before:]:part['vertices']=[[x-.045,y,z] for x,y,z in part['vertices']]
rod('ladle shaft',(.005,.09,0),(.275,.188,0),.010,'#7895A3',16)
rod('ladle grip',(.235,.173,0),(.285,.192,0),.018,'#728D98',20)
S['notes']=['Bowl has a closed base, hollow wall and rim. Soup lies below rim. Ladle cup lies in the bowl and joins its shaft; shaft intersects right rim support region near x=.17,y=.16, with grip extending outward. No person or guaranteed recipe.']
scene('goalball',(2,4,12))
# A24cm goalball shell with eight evenly distributed sound apertures.
center=np.array([-.075,.12,0]);R=.12;n=144;rings=72
v=np.array([[R*math.cos(t)*math.cos(a),R*math.sin(t),R*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)])
dirs=[np.array([math.sqrt(2/3)*math.cos(i*math.pi/2+(math.pi/4 if y>0 else 0)),y/math.sqrt(3),math.sqrt(2/3)*math.sin(i*math.pi/2+(math.pi/4 if y>0 else 0))]) for y in [-1,1] for i in range(4)];faces=[]
for j in range(rings-1):
 for i in range(n):
  f=[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n];normal=v[f].mean(0);normal/=np.linalg.norm(normal)
  if any(np.dot(normal,d)>math.cos(.068) for d in dirs):continue
  faces.append(f)
mesh('ball shell',v+center,faces,'#719DB9')
# Dark inner surface makes the actual openings legible; internal bells are hidden.
ball('ball interior',center,.11,'#35586B')
# Curved opaque eyeshades, with a nose notch and a joined rear elastic band.
xs=np.linspace(-.095,.095,21);verts=[]
for x in xs:
 q=x/.095;z=.17-.07*q*q;top=.055+.026*math.sqrt(max(0,1-q*q));bottom=.018+.022*math.exp(-(q/.25)**2)
 verts += [[x+.14,bottom,z],[x+.14,top,z]]
mesh('eyeshade face',verts,[[2*i+2,2*i+3,2*i+1,2*i] for i in range(len(xs)-1)],'#40525D')
pts=[]
for t in np.linspace(0,math.pi,32):
 x=.14+.095*math.cos(t);z=.10-.115*math.sin(t);pts.extend([[x,.035,z],[x,.057,z]])
mesh('elastic band',pts,[[2*i,2*i+1,2*i+3,2*i+2] for i in range(31)],'#566A75')
S['notes']=['Ball exterior is24cm diameter with eight mesh openings in two staggered hemispheric rings; hole width is mildly enlarged for icon readability, not manufacturing geometry. Dark inner surface stands for the hollow interior, hiding the bells. Opaque eyeshades curve with a nose notch and joined elastic band; no face anatomy. Ball rests on y=0; eyeshades are a separate equipment diagram.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created four equipment scenes')
