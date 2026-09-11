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
# An original open zine study: folded sheet topology with explicit surface coordinates.
scene('zine-making',(1,12,6))
# Open spread measures .20m across and .14m deep; spine and page edges are shared.
# Each side is a shallow planar leaf rising from the central fold.
def sheetpoint(u,v,offset=0):return [u,.018+abs(u)*.33+offset,v]
def leaf(name,ua,ub,va,vb,offset,color):
 points=[sheetpoint(ua,va,offset),sheetpoint(ua,vb,offset),sheetpoint(ub,vb,offset),sheetpoint(ub,va,offset)]
 if name in ['colored cover','paper edge','open page']:
  points += [[x,y-.0015,z] for x,y,z in points]
  mesh(name,points,[[0,1,2,3],[7,6,5,4],[0,4,5,1],[1,5,6,2],[2,6,7,3],[3,7,4,0]],color)
 else:panel(name,points,color)
for sign in [-1,1]:
 ua,ub=sorted([0,sign*.102])
 leaf('colored cover',ua,ub,-.074,.074,-.005,'#83A49B')
 leaf('paper edge',ua,ub,-.071,.071,-.002,'#C5CEC6')
 ua,ub=sorted([0,sign*.098])
 leaf('open page',ua,ub,-.069,.069,0,'#F0E4C8')
# A bright cut-paper collage motif, with deliberately different non-text panels.
leaf('left collage',-.086,-.013,-.055,.010,.0002,'#B495AA')
panel('collage mountain',[sheetpoint(-.086,.010,.0003),sheetpoint(-.030,.010,.0003),sheetpoint(-.060,-.035,.0003)],'#708D9B')
# Circle printed on the left page, all coordinates on its own paper plane.
poly=[sheetpoint(-.033+.013*math.cos(t),-.034+.013*math.sin(t),.0004) for t in np.linspace(0,2*math.pi,32,endpoint=False)];panel('collage sun',poly,'#E5B47E')
for v,length in [(.026,.067),(.038,.058),(.050,.071)]:leaf('left text',-.084,-.084+length,v,v+.003,.0002,'#89968F')
for va,vb,col in [(-.055,-.010,'#78A3A3'),(.003,.040,'#C99E78')]:leaf('right panel',.014,.085,va,vb,.0002,col)
for v in [.050,.058]:leaf('right text',.017,.073,v,v+.003,.0002,'#89968F')
# Two saddle staples span the central fold along its depth axis.
for v in [-.037,.037]:
 a=sheetpoint(0,v-.004,.0007);bb=sheetpoint(0,v+.004,.0007)
 rod('staple crown',a,bb,.00065,'#778C92',8)
 for point in [a,bb]:rod('staple leg',point,[point[0],point[1]-.006,point[2]],.00065,'#778C92',8)
# Hexagonal pencil beside the spread: wooden taper meets lead tip and painted barrel.
a=np.array([.025,.012,.100]);bb=np.array([.114,.012,-.016]);axis=(bb-a);axis/=np.linalg.norm(axis)
rod('pencil wood',a,a+axis*.016,.0008,'#D8B486',6,r2=.0055)
rod('pencil lead',a-axis*.004,a,.0001,'#566974',6,r2=.0008)
rod('pencil barrel',a+axis*.016,bb,.0055,'#D5A367',6)
rod('pencil ferrule',bb,bb+axis*.008,.0056,'#ACBAB6',12)
rod('pencil eraser',bb+axis*.008,bb+axis*.018,.0056,'#C7949B',12)
for part in S['parts']:
 if part['name'].startswith('pencil'):
  part['vertices']=(np.array(part['vertices'])+np.array([.035,0,.025])).tolist()
S['notes']=['Open booklet uses two page planes joined at a shared central crease; upper paper, page edge and colored cover are nested layers. Printed collage and text are parameterized on the corresponding page, not independent screen-space overlays. Two short staples penetrate the crease. Pencil has a continuous collinear lead, wood taper, hexagonal barrel, ferrule and eraser; it is separate from the booklet. Dimensions are illustrative, and the saddle-stapled booklet is one representative zine construction, not a promise that every workshop teaches binding.']
if __name__=='__main__':(ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
