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
scene('cocktail-shaker',(3,4,12))
# Three-piece closed cobbler shaker, approximately 24cm tall.
lathe('shaker body',[(0,0),(.058,0),(.064,.014),(.080,.158),(.077,.178),(0,.178)],'#A8BBC4',48)
lathe('strainer shoulder',[(0,.176),(.078,.176),(.081,.185),(.072,.198),(.045,.218),(0,.218)],'#D1DDE0',48)
lathe('cap',[(0,.212),(.038,.212),(.040,.218),(.040,.247),(.035,.253),(0,.253)],'#91AAB7',40)
# Reduce cup width to a plausible 25cm-tall,10.7cm-wide shaker envelope.
for part in S['parts']:part['vertices']=[[x*.66,y,z*.66] for x,y,z in part['vertices']]
rod('glass base',(.17,0,0),(.17,.008,0),.052,'#9ABAC4',32)
rod('glass stem',(.17,.008,0),(.17,.088,0),.008,'#9ABAC4',16)
before=len(S['parts']);lathe('glass bowl',[(0,.08),(.076,.17),(.069,.17),(0,.091)],'#B5D3D8',40)
for part in S['parts'][before:]:part['vertices']=[[x+.17,y,z] for x,y,z in part['vertices']]
rod('cocktail surface',(.17,.145,0),(.17,.147,0),.048,'#DACA8B',32)
S['notes']=['Closed three-piece cobbler: cup, fitted shoulder/strainer and cap overlap at joins. Illustrative approximate24cm height; no brand geometry copied.']
scene('weeding',(1,3,12))
# Uprooted specimen diagram. The soil line is intentionally absent: roots are exposed.
rod('plant stem',(-.19,.35,0),(-.18,.88,0),.012,'#6F9471',12)
# Broad leaves attach directly to main stem and branch outward.
for name,base,tip,w in [('left low',(-.19,.48,0),(-.43,.65,0),.085),('right low',(-.185,.57,0),(.02,.73,0),.09),('left high',(-.18,.69,0),(-.36,.87,0),.08),('right high',(-.18,.80,0),(-.02,.99,0),.075)]:
 a=np.array(base);z=np.array(tip);d=z-a;perp=np.array([-d[1],d[0],0]);perp=perp/np.linalg.norm(perp)*w;mid=(a+z)/2
 points=[a+d*t+perp*math.sin(math.pi*t) for t in np.linspace(0,1,12)]+[a+d*t-perp*math.sin(math.pi*t) for t in np.linspace(1,0,12)]
 panel('leaf '+name,points,'#719C75')
rod('taproot',(-.19,.35,0),(-.22,.06,0),.02,'#BF936A',12,r2=.004)
for i,(a,bb,cc) in enumerate([((-.195,.28,0),(-.32,.20,0),(-.37,.09,0)),((-.20,.22,0),(-.10,.15,.01),(-.06,.05,.01)),((-.21,.14,0),(-.29,.11,-.02),(-.32,.02,-.02))]):
 rod('root branch'+str(i),a,bb,.012,'#BF936A',10,r2=.009);rod('root tip'+str(i),bb,cc,.009,'#BF936A',10,r2=.004)
# A separate hand fork has a wooden grip, continuous shaft, crossbar and four tines.
rod('fork handle',(.29,.63,0),(.29,1.00,0),.064,'#C28E63',24)
ball('handle top',(.29,1.00,0),.064,'#C28E63')
rod('fork ferrule',(.29,.59,0),(.29,.65,0),.047,'#869DA7',24)
rod('fork shaft',(.29,.33,0),(.29,.61,0),.023,'#9FB7BF',12)
box('fork crossbar',(.29,.34,0),(.27,.065,.055),'#9FB7BF')
for x in [.175,.252,.328,.405]:rod('fork tine',(x,.34,0),(x,.12,.055),.014,'#9FB7BF',12,r2=.007)
S['notes']=['Diagram pairs an uprooted plant specimen with hand fork; no unsupported human pose or claimed extraction action. Stem and four leaves meet; branching roots connect continuously. Fork handle, ferrule, shaft, crossbar and four tines connect.']
scene('literary-open-mic',(2,3,12))
rod('lectern base',(-.08,.015,0),(-.08,.055,0),.27,'#698B93',32)
rod('lectern stem',(-.08,.04,0),(-.08,.68,0),.03,'#698B93',16)
box('book tray',(-.08,.76,0),(.62,.35,.045),'#A77E60')
# An open book with its two flat page blocks rising outward from the gutter.
# Pages are held on the tray; outer edges and gutter are closed geometry.
for side in [-1,1]:
 x0=-.08;x1=x0+side*.32
 panel('book cover',[(x0,.585,.032),(x1,.61,.032),(x1,.94,.032),(x0,.91,.032)],'#B28F68')
 panel('page block',[(x0+side*.012,.607,.045),(x1-side*.025,.63,.045),(x1-side*.025,.918,.045),(x0+side*.012,.892,.045)],'#F0E6D1')
 for y in [.69,.76,.83]:rod('verse ink',(x0+side*.055,y,.048),(x1-side*.06,y+.02,.048),.005,'#AD9C82',8)
# Gooseneck microphone mounted to the lectern, separate from the open pages.
rod('microphone mount',(.21,.70,0),(.36,.84,-.025),.018,'#617782',12)
rod('gooseneck',(.36,.84,-.025),(.31,1.06,-.025),.018,'#617782',12)
rod('microphone body',(.31,1.06,-.025),(.17,1.13,-.025),.04,'#607E8E',24)
ball('microphone grille',(.15,1.14,-.025),.052,'#99B2BE')
S['notes']=['Base, pole and tray join. Open book lies on the tray, split at its gutter with raised outer edges in the page plane. A side-mounted gooseneck rises clear of the right page; microphone and grille join the stem. Diagram is illustrative, not an exact venue lectern promise.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created three equipment scenes')
