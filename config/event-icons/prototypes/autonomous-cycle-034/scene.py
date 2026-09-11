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

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat

def puff(name,c,w,d,h,col,sugar=False):
 # Rounded-square inflated pastry, ring mesh; flattened underside rests at y=0.
 n=24;rings=9;v=[]
 for t in np.linspace(-math.pi/2,math.pi/2,rings):
  rr=abs(math.cos(t))**.7
  for a in np.linspace(0,2*math.pi,n,endpoint=False):
   co,si=math.cos(a),math.sin(a)
   x=w/2*rr*np.sign(co)*abs(co)**.5
   z=d/2*rr*np.sign(si)*abs(si)**.5
   y=h/2+h/2*math.sin(t)
   v.append([c[0]+x,c[1]+y,c[2]+z])
 fs=[[k*n+i,(k+1)*n+i,(k+1)*n+(i+1)%n,k*n+(i+1)%n] for k in range(rings-1) for i in range(n)]
 if sugar:
  lower=[];upper=[]
  for f in fs:
   # Coarse irregular powder edge, all paint is attached to real dough surface.
   cy=sum(v[i][1] for i in f)/4-c[1];a=math.atan2(v[f[0]][2]-c[2],v[f[0]][0]-c[0])
   (upper if cy>h*(.86+.025*math.sin(a*5)) else lower).append(f)
  mesh(name+' crust',v,lower,col);S['parts'][-1]['double_sided']=True
  mesh(name+' powdered top',v,upper,'#F4EBDA');S['parts'][-1]['double_sided']=True
 else:mesh(name,v,fs,col)
scene('beignets',(2.5,6,9))
# Three separate puffs share one serving plane, no intersections or stacking.
for i,(x,z,w,d) in enumerate([(-.032,-.027,.056,.052),(.033,-.025,.054,.055),(0,.040,.057,.053)]):
 puff('beignet '+str(i),(x,0,z),w,d,.035,'#D59A51',True)
S['measurements']=dict(pieces=3,width_range=[.054,.057],height=.035,minimum_center_separation=.065,base_y=0)
S['notes']=['Three original inflated, rounded-square fried-pastry forms rest on the same plane. Powder sugar is a broad attached paint region, not a thick icing slab. Shape is a representative NewOrleans-style example informed by KingArthur primary photograph; Atelier current class confirms yeast dough, frying and optional fillings but does not establish exact shape or regional recipe. No filling or sugar quantity promised.']
scene('french-pastry',(3,5,9))
# Three puff-pastry sheets with two continuous custard layers, topped with icing.
xc,zc=-.025,-.01;w=.080;d=.054
for j,y in enumerate([0,.017,.034]):
 outline=[(x+xc,z+zc) for x,z in rounded_outline(w,d,.003,n=5)]
 flat_extrude('puff pastry sheet '+str(j),outline,y,y+.006,'#CD9858')
 # A thin lighter laminated edge, bounded by actual pastry dimensions.
 if j<2:
  flat_extrude('custard layer '+str(j),[(x+xc,z+zc) for x,z in rounded_outline(w-.004,d-.004,.004,n=5)],y+.006,y+.017,'#F4DEAA')
flat_extrude('icing',[(x+xc,z+zc) for x,z in rounded_outline(w-.003,d-.003,.003,n=5)],.040,.0415,'#F1EADF')
# Three sparse original feathered icing lines attached to top surface.
for q,z in enumerate([-.027,-.011,.005]):
 pts=[]
 for x in np.linspace(xc-.033,xc+.033,19):pts.append((x,.0417,z+.004*math.sin((x-xc)*130)))
 for a,bb in zip(pts,pts[1:]):rod('chocolate feather',a,bb,.0008,'#9B755B',n=6);S['parts'][-1]['flat_paint']=True
# Madeleine shell back facing up: four shallow illustrative flutes and tapered oval outline.
# The opposite humped face is simplified to a low supporting underside.
cx,cz=.052,.033;n=40;rings=8;verts=[]
for rr in np.linspace(0,1,rings):
 for a in np.linspace(0,2*math.pi,n,endpoint=False):
  xx=.023*rr*math.cos(a)*(1+.18*math.sin(a));zz=.033*rr*math.sin(a)
  broad=.012*(1-rr*rr)
  # Four flutes converge gently near the narrower end.
  yy=.002+broad+.0025*(1-rr)*math.cos(4*math.pi*xx/(.023*max(.15,math.sqrt(max(0,1-(zz/.034)**2)))))
  verts.append([cx+xx,yy,cz+zz])
faces=[[k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i] for k in range(rings-1) for i in range(n)]
# The XZ grid is clockwise viewed from above, reverse for upward surface.
# XZ radial ring order already gives upward surface normals.
mesh('madeleine fluted back',verts,faces,'#DFA963');S['parts'][-1]['double_sided']=False;S['parts'][-1]['flat_paint']=True
outline=[(verts[(rings-1)*n+i][0],verts[(rings-1)*n+i][2]) for i in range(n)]
flat_extrude('madeleine edge and supporting base',outline,0,.002,'#C88E50')
# Darker shallow crease lines follow four valley tracks on the same surface.
for off in [-.01725,-.00575,.00575,.01725]:
 points=[]
 for zz in np.linspace(-.025,.025,16):
  taper=math.sqrt(1-(zz/.034)**2);xx=off*taper
  # Recover radial mesh radius from the slightly tapered elliptical outline.
  rr=min(.98,math.sqrt((xx/(.023*(1+.18*zz/.033)))**2+(zz/.033)**2))
  yy=.002+.012*(1-rr*rr)-.0025*(1-rr)
  points.append((cx+xx,yy+.0006,cz+zz))
 for a,bb in zip(points,points[1:]):
  rod('madeleine flute crease',a,bb,.00065,'#C58C4D',n=6);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(pastry_sheets=3,custard_layers=2,pastry_width=w,pastry_depth=d,pastry_total_height=.0415,madeleine_width=.046,madeleine_length=.066,madeleine_max_height=.0165,base_y=0)
S['notes']=['Original mille-feuille and madeleine form a representative French-pastry assortment, matching two explicitly billed class foods. Three pastry sheets and two custard layers are connected solids; icing and chocolate lines attach to the upper sheet. Madeleine has a tapered shell back with shallow flutes and rests separately on the same support plane. No exact recipe, filling flavor, pattern or assortment beyond the event text promised.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-034')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
