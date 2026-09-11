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

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat

scene('oyster-research-tank',(5,6,9))
# Generic classroom tank: approximate dimensions, not a specific supplied brand or volume.
box('tank base',(0,.006,0),(.42,.012,.25),'#8CAEB1')
frame('upper rim',(0,.254,0),.42,.25,.01,.012,'#AC889E')
box('clear tank envelope',(0,.133,0),(.414,.242,.244),'#A7C9CB');S['parts'][-1]['transparent']=True
for x in [-.204,.204]:
 for z in [-.119,.119]:rod('clear corner',(x,.012,z),(x,.254,z),.002,'#97BBBD',n=8)
frame('waterline',(0,.208,0),.399,.229,.0025,.003,'#8DBBC0')
def oyster(name,c,rotation):
 n=14;rs=[0,.35,.65,1.];x0,z0=c;ang=math.radians(rotation)
 for upper in [True,False]:
  v=[]
  for r in rs:
   for i in range(n):
    t=2*math.pi*i/n;rough=1+.07*math.sin(5*t)+.035*math.cos(7*t);x=.078*r*rough*math.cos(t);z=.048*r*rough*math.sin(t)
    y=.031+(.029 if upper else -.019)*max(0,1-r*r)**.65
    if upper:y+=.002*math.sin(r*math.pi*5)*r*(1-r)
    v.append([x0+x*math.cos(ang)+z*math.sin(ang),y,z0-x*math.sin(ang)+z*math.cos(ang)])
  f=[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(len(rs)-1) for i in range(n)]
  if not upper:f=[list(reversed(q)) for q in f]
  mesh(name+(' upper valve' if upper else ' lower valve'),v,f,'#C7B9A1' if upper else '#A19486')
  # Broad growth bands use the same sampled shell surface, with no detached paint geometry.
  if upper:
   for j in [2]:
    for i in range(n):
     a=np.array(v[j*n+i]);bb=np.array(v[j*n+(i+1)%n]);rod(name+' growth ridge',a,bb,.0012,'#A59B8B',n=6)
oyster('left oyster',(-.092,.035),-18)
oyster('right oyster',(.092,.035),20)
# Illustrative gravel-filled biological-filter bottle; no mechanical cartridge filter is implied.
lathe('gravel bottle',[(0,.012),(.023,.012),(.023,.07),(.012,.088),(.008,.088),(.008,.1),(0,.1)],'#AAA38D',n=12)
p=S['parts'][-1];p['vertices']=[[x+.15,y,z-.06] for x,y,z in p['vertices']]
rod('air stone',(.15,.017,-.06),(.15,.03,-.06),.008,'#789BA3',n=8)
# Air line crosses above the rim then enters the bottle at a low side opening.
# External pump and complete plumbing are intentionally outside this equipment study.
points=[(.25,.29,-.06),(.21,.29,-.06),(.19,.285,-.06),(.177,.272,-.06),(.175,.25,-.06),(.175,.05,-.06),(.17,.032,-.06),(.15,.025,-.06)]
for i,(a,bb) in enumerate(zip(points,points[1:])):rod('air line '+str(i),a,bb,.0028,'#7E9AAB',n=8)
for i,y in enumerate([.119,.15,.182]):ball('aeration bubble '+str(i),(.15+(i%2)*.006,y,-.06),.0045,'#9BC0C5')
S['measurements']=dict(tank_outer_width=.42,tank_outer_depth=.25,rim_top=.26,base_top=.012,waterline_y=.208,oyster_bottom_y=.012,oyster_top_y=.06,oyster_centers_xz=[[-.092,.035],[.092,.035]],oyster_nominal_half_width=.078,oyster_nominal_half_depth=.048,filter_center_xz=[.15,-.06],airline_points=points)
S['notes']=['Original generic transparent rectangular classroom tank, two closed oyster shells on its base, waterline and a biological-filter bottle. Dimensions are approximate and not an exact six-gallon kit or stocking prescription.','Air line passes above the rim and enters the bottle near its base. External pump and full kit are outside the scene; this is not a working installation guide.','Shells use closed upper and lower sampled surfaces with shared perimeter seams, irregular outlines and growth ridges following the same upper surface. No exposed oyster meat or food presentation.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-042/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
