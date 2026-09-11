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
 x,y,z=c;n=16;rings=8;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
scene('backlit-tracing',(2,6,10))
box('lightboard body',(0,.025,0),(1.0,.05,.78),'#607F93')
box('luminous border',(0,.054,0),(.94,.012,.72),'#A9E0D6')
box('canvas surface',(0,.062,0),(.80,.006,.60),'#F4F0DF')
# Simple non-branded contour projected onto the actual lit canvas surface.
outline=[(-.30,-.05),(-.20,-.15),(-.06,-.11),(.03,.01),(.19,-.17),(.29,-.08)]
for a,bb in zip(outline,outline[1:]):rod('guide', (a[0],.068,a[1]),(bb[0],.068,bb[1]),.008,'#87BEBB',8)
rod('outlined sun',(0,.069,.14),(0,.071,.14),.057,'#F3C766',20)
# Resting paintbrush lies beside lower edge, physically separate from canvas.
rod('brush handle',(-.30,.034,.44),(.22,.034,.44),.028,'#DD9470',16)
rod('brush ferrule',(.22,.034,.44),(.34,.034,.44),.033,'#A9BFC3',16)
rod('brush bristles',(.34,.034,.44),(.47,.034,.44),.034,'#526A82',16,r2=.005)
S['notes']=['Illustrative low lightboard with canvas; luminous border and surface guides indicate backlighting. Brush rests at floor y=0 beside the board, not a hovering held pose or exact proprietary model.']
scene('needle-felting',(3,4,10))
box('foam pad',(0,.07,0),(.85,.14,.65),'#729EA5');box('foam top',(0,.143,0),(.82,.006,.62),'#B1D1CA')
# Flattened overlapping wool lobes represent loose fiber laid onto the pad.
for i,(x,z,r) in enumerate([(-.14,-.06,.17),(.10,-.10,.18),(.20,.07,.14),(-.05,.13,.17),(-.22,.09,.12),(0,0,.22)]):
 before=len(S['parts']);ball('wool'+str(i),(x,.20,z),r,'#DFA6C3')
 for p in S['parts'][before:]:p['vertices']=[[a,.17+(yy-.20)*.23,zz] for a,yy,zz in p['vertices']]
# Needle has no eye; barbed shaft enters wool and foam. Wooden grip is connected.
a=np.array([.02,.18,.04]);bb=np.array([.25,.87,.04]);direction=(bb-a)/np.linalg.norm(bb-a)
rod('needle',a,bb,.011,'#ADBFC5',8)
rod('handle',bb,bb+direction*.24,.046,'#E7BC83',16)
for t in [.10,.17,.24]:
 c=a+direction*t;rod('barb',c,c+np.array([-.020,.009,0]),.004,'#81969E',6)
S['notes']=['Loose wool lies on foam; a single eye-free needle enters the fiber pad. Needle grip and shaft join; small barbs are illustrative and soften at icon size. No sewing thread or embroidery stitch is implied.']
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');print('Created two spatial craft scenes')
