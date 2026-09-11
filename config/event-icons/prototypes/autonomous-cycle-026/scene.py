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


scene('kimekomi',(2,5,9))
# Original palm-sized owl-like decorative blank, seated on its flat base.
# Grid material boundaries represent cloth edges sunk into shallow carved grooves.
n=48;ts=sorted(set(np.linspace(-math.pi/2+.12,math.pi/2,19).tolist()+[-.035,0,.035]));v=[]
for t in ts:
 for i in range(n):
  a=2*math.pi*i/n
  groove=min(abs(t),min(abs(a-math.pi/4),abs(a-3*math.pi/4)))
  cut=.0012*math.exp(-(groove/.025)**2)
  r=math.cos(t)
  v.append([-.021+(.035*r-cut)*math.cos(a),.049+.045*math.sin(t),(.028*r-cut)*math.sin(a)])
parts={}
for j in range(len(ts)-1):
 for i in range(n):
  a=2*math.pi*(i+.5)/n;t=(ts[j]+ts[j+1])/2
  color='#D7B67C' if abs(t)<.025 or min(abs(a-math.pi/4),abs(a-3*math.pi/4))<.04 else ('#EADFC8' if t>.02 and math.pi/5<a<4*math.pi/5 else '#65A6A0' if math.pi/4<a<3*math.pi/4 else '#AC799B')
  parts.setdefault(color,[]).append([j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n])
for col,faces in parts.items():
 mesh('groove' if col=='#D7B67C' else 'fabric',v,faces,col);S['parts'][-1]['paint_underlay']=True
mesh('flat base',v,[list(range(n))],'#AE9373')
# Rounded cream eye pads and dark eyes attach into the solid front surface.
def ellipsoid(name,c,r,col,n=24,m=12):
 verts=[[c[0]+r[0]*math.cos(t)*math.cos(a),c[1]+r[1]*math.sin(t),c[2]+r[2]*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,m+1) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 fs=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(m) for i in range(n)];mesh(name,verts,fs,col)
for x in [-.032,-.010]:
 ellipsoid('fabric',(x,.068,.021),(.013,.014,.007),'#F6E8CF')
 ellipsoid('eye',(x,.070,.027),(.003,.0035,.002),'#46565B',16,8)
# Solid stylized beak attached at its base, a decorative doll part rather than bird anatomy.
mesh('beak',[[-.026,.064,.025],[-.016,.064,.025],[-.021,.051,.027],[-.021,.060,.038]],[[1,2,0],[3,1,0],[3,2,1],[3,0,2]],'#E5AD5D')
# Attached broad fabric motifs on the lower chest; original pattern, no copied cloth print.
for x,y,z in [(-.032,.035,.025),(-.010,.035,.025),(-.021,.019,.021)]:ellipsoid('fabric',(x,y,z),(.003,.004,.0015),'#F0DBA7',12,6)
# Separate fabric swatch on the same ground plane, plus a blunt tucking spatula.
flat_extrude('fabric swatch',[(.008,.026),(.055,.021),(.060,.051),(.013,.056)],.004,.0045,'#E1BC70')
rod('spatula handle',(.050,.004,-.025),(.051,.060,-.020),.0038,'#B98D63',12)
box('spatula tang',(.051,.066,-.0194),(.0025,.014,.0018),'#91A9B2')
mesh('blunt spatula blade',[[.047,.068,-.0203],[.055,.068,-.0203],[.055,.086,-.0185],[.047,.086,-.0185],[.047,.068,-.0185],[.055,.068,-.0185],[.055,.086,-.0167],[.047,.086,-.0167]],[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],'#B1C4C7')
# Lay the isolated tool beside the doll on the cloth-level support plane.
toolparts=[p for p in S['parts'] if p['name'].startswith('spatula') or p['name']=='blunt spatula blade']
for p in toolparts:p['vertices']=[[x,.008+z+.025-(y-.004)*(.005/.056),.040-(y-.004)] for x,y,z in p['vertices']]
miny=min(v[1] for p in toolparts for v in p['vertices'])
for p in toolparts:
 for v in p['vertices']:v[1]+=.0045-miny
S['measurements']=dict(tool_lowest_y_m=.0045,body_height_m=.0897,maximum_body_width_m=.070,maximum_depth_m=.056,groove_depth_m=.0012,cloth_thickness_illustrative_m=.0005,spatula_handle_diameter_m=.0076)
S['notes']=['Original owl-like kimekomi blank has a flat bottom, fabric panels with shallow groove depressions and attached eye/beak details. Decorative cloth motifs are original. Side swatch and blunt tucking tool identify making rather than live bird observation. No stitching, actual class kit dimensions, exact doll model or anatomical bird is claimed. Flat colors intentionally keep fabric faces coherent.']
b=Path('.scratch/icon-cycles-20260909/cycle-026');(b/'scenes.json').write_text(json.dumps(SCENES,indent=2));(b/'geometry-measurements.json').write_text(json.dumps({k:s['measurements'] for k,s in SCENES.items()},indent=2))
