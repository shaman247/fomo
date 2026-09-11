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


scene('forest-bathing',(.8,2.4,10))
flat_extrude('forest ground',rounded_outline(1.95,1.35,.35),-.05,0,'#A0AE83')
# A single original standing performer; equal fixed limb lengths and common floor.
start=len(S['parts']);x=0;z=.35;skin='#BE8968';shirt='#D59479';pants='#607F9F'
box('performer pelvis',(x,.855,z),(.28,.20,.19),pants)
extrude('performer shirt',[(x-.15,.88),(x+.15,.88),(x+.21,1.29),(x-.21,1.29)],z-.11,z+.11,shirt)
rod('neck',(x,1.28,z),(x,1.38,z),.055,skin)
oval('head hair',(x,1.49,z),.135,[.90,1.12,.87],'#514A45',True)
oval('face',(x,1.475,z+.047),.113,[.88,1.06,.85],skin,True)
for sx in [-1,1]:
 shoulder=np.array([x+sx*.18,1.25,z]);elbow=np.array([x+sx*.29,.98,z+.025]);wrist=np.array([x+sx*.35,.75,z+.06])
 rod('continuous short sleeve',shoulder,shoulder+(elbow-shoulder)*.65,.053,shirt,20,r2=.047)
 rod('upper arm',shoulder+(elbow-shoulder)*.57,elbow,.041,skin,20,r2=.038)
 rod('forearm',elbow,wrist,.038,skin,20,r2=.029)
 oval('hand',wrist+[0,-.035,0],.038,[.78,1.3,.65],skin,True)
 hip=np.array([x+sx*.084,.84,z]);knee=np.array([x+sx*.112,.46,z]);ankle=np.array([x+sx*.14,.09,z])
 rod('trouser thigh',hip,knee,.071,pants,20,r2=.060)
 rod('trouser shin',knee,ankle,.060,pants,20,r2=.045)
 box('shoe',(ankle[0],.043,z+.045),(.105,.086,.235),'#48586A')

for xx in [-.035,.035]:
 rod('eye',(x+xx,1.497,z+.145),(x+xx,1.497,z+.151),.010,'#514A45',12);S['parts'][-1]['flat_paint']=True
for tx,tz,h,c in [(-.67,-.30,2.16,'#78A571'),(.70,-.42,2.48,'#619A7A')]:
 rod('rooted trunk',(tx,-.04,tz),(tx,h-.25,tz),.058,'#947759',20,r2=.026)
 for dx in [-.22,.22]:rod('branch',(tx,h-.76,tz),(tx+dx,h-.27,tz),.025,'#947759',16,r2=.012)
 oval('canopy',(tx-.16,h-.31,tz),.34,[1,1.13,.75],c,True)
 oval('canopy',(tx+.18,h-.30,tz-.015),.33,[1,1.07,.8],c,True)
 oval('canopy',(tx,h-.03,tz),.32,[1,1.1,.8],c,True)
for p in S['parts']:
 if p['name'] in ['rooted trunk','branch']:p['flat_paint']=True
S['measurements']=dict(person_height_m=1.641,shoe_bottom_m=0,exposed_neck_m=.045,upper_arm_radius_m=.041,thigh_radius_m=.071,bilateral_leg_lengths_equal=True,tree_bases_m=-.04,ground_top_m=0,tree_top_m=[2.482,2.802])
S['notes']=['Original fully clothed person pauses in a small wooded setting. Equal fixed leg lengths and shoes meet the ground plane; a short neck joins the head and shirt, with thinner arms than thighs. Side and top views establish separation from two rooted trees. This is a sensory-pause emblem, not a bathing or yoga pose, a specific forest route, or a medical treatment claim.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-030')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
