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

scene('smocking',(2,10,7))
# Original gathered textile swatch with real corrugation and joining stitches.
nx,nz=32,8
def cloth(x,z):return .003+.012*(1+math.cos(2*math.pi*x/.06))*(.78+.22*math.cos(z*math.pi/.11))
v=[]
for layer in [0,-.001]:
 for iz in range(nz+1):
  z=-.11+iz*.22/nz
  for ix in range(nx+1):
   x=-.12+ix*.24/nx;v.append([x,cloth(x,z)+layer,z])
nf=(nx+1)*(nz+1);faces=[]
for j in range(nz):
 for i in range(nx):
  a=j*(nx+1)+i;faces.extend([[a,a+nx+1,a+nx+2,a+1],[a+nf,a+1+nf,a+nx+2+nf,a+nx+1+nf]])
edges=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,nz+1)]+[nz*(nx+1)+i for i in range(nx-1,-1,-1)]+[j*(nx+1) for j in range(nz-1,0,-1)]
for a,c in zip(edges,edges[1:]+edges[:1]):faces.append([a,c,c+nf,a+nf])
mesh('gathered cotton',v,faces,'#89A8AC')
for j,z in enumerate([-.066,-.022,.022,.066]):
 for i,x in enumerate([-.09,-.03,.03,.09]):
  xa,xb=x-.018,x+.018;za=z-.005 if (i+j)%2 else z+.005;zb=z+.005 if (i+j)%2 else z-.005
  a=np.array([xa,cloth(xa,za),za]);c=np.array([xb,cloth(xb,zb),zb]);mid=(a+c)/2;mid[1]=max(cloth(t,za+(zb-za)*(t-xa)/(xb-xa)) for t in np.linspace(xa,xb,15))+.002
  # A surface-following arch joins points through the gathered fabric, not a loose floating line.
  prev=a
  for t in np.linspace(0,1,5)[1:]:
   q=(1-t)**2*a+2*t*(1-t)*mid+t*t*c;q[1]=max(q[1],cloth(q[0],q[2])+.0014*math.sin(math.pi*t));rod('joining stitch',prev,q,.0022,'#ECD69B',6);prev=q
S['measurements']=dict(swatch_m=[.24,.22],cloth_thickness_m=.001,fold_pitch_m=.06,maximum_fold_height_m=.027,thread_diameter_m=.0044)
S['notes']=['Original corrugated cotton swatch illustrates dimensional smocking rather than flat embroidery. Four rows of pale stitches connect visible folded fabric at endpoints and arch over the surface. Regularized stitches are a representative smocking motif, not the exact irregular punk-smocking workshop pattern. No needle or hand is shown and no cloth/tension simulation is claimed.']

scene('terrarium',(2,4,12))
# Open glass vessel: connected outer/inner lathe surfaces and an actual open rim.
profile=[(.102,.230),(.115,.211),(.130,.183),(.142,.155),(.149,.128),(.150,.105),(.149,.078),(.145,.050),(.136,.028),(.125,.014),(.115,.006),(0,.006),(0,0),(.117,0),(.130,.009),(.141,.024),(.151,.047),(.155,.076),(.156,.105),(.155,.13),(.148,.158),(.136,.186),(.121,.214),(.108,.234),(.102,.230)]
lathe('clear glass vessel',profile,'#A7C9CB',48);S['parts'][-1]['transparent']=True
ring_y('open rim',(0,.229,0),.108,.102,.005,'#A7C9CB',48)
lathe('grit layer',[(0,.025),(.127,.025),(.115,.007),(0,.007)],'#BAAE91',40)
lathe('potting mix',[(0,.073),(.145,.073),(.140,.049),(.127,.025),(0,.025)],'#91775A',40)
def succulent(name,c,scale,col):
 x,y,z=c;rod(name+' crown',(x,y-.006,z),(x,y+.022*scale,z),.007*scale,col,16)
 for j in range(7):
  a=2*math.pi*j/7;u=np.array([math.cos(a),0,math.sin(a)]);w=np.array([-math.sin(a),0,math.cos(a)]);base=np.array([x,y+.008*scale,z]);pts=[]
  for t in np.linspace(0,1,9):
   center=base+u*(.072*scale*t)+np.array([0,.125*scale*t-.025*scale*t*t,0]);width=.022*scale*math.sin(math.pi*t)
   for side in [-1,0,1]:pts.append(center+w*width*side+np.array([0,.007*scale*math.sin(math.pi*t)*(1-abs(side)),0]))
  fs=[]
  for k in range(8):
   for m in range(2):fs.append([k*3+m,(k+1)*3+m,(k+1)*3+m+1,k*3+m+1])
  mesh(name+' leaf',pts,fs,col);S['parts'][-1]['double_sided']=True
succulent('large rosette',(-.046,.073,-.017),1,'#72A78E')
succulent('small rosette',(.063,.073,.030),.66,'#A8B77D')
S['measurements']=dict(vessel_max_diameter_m=.312,height_m=.234,opening_diameter_m=.204,soil_surface_m=.073,glass_thickness_approx_m=.006)
S['notes']=['Original312mm wide open glass vessel has an uninterrupted curved wall,6mm base,204mm open neck and visible soil layers. Two stylized succulent rosettes root at the soil surface and stay within the bowl. RHS guidance supports open vessels and succulents; exact Snug Harbor plants/container are unspecified. Transparent glass is drawn from projected mesh silhouette plus its real open rim; optics/refraction and a botanical species diagnosis are not simulated.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-022')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
