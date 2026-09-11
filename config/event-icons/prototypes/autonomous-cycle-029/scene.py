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

scene('shadowcast',(1.1,2.4,10))
box('screen frame',(0,1.23,-.38),(2.12,1.40,.09),'#536783')
box('screen surface',(0,1.23,-.326),(1.97,1.25,.018),'#D9D6CB')
for x in [-.88,.88]:
 box('screen support',(x,.26,-.38),(.06,.52,.06),'#536783')
 box('screen foot',(x,.025,-.38),(.30,.05,.38),'#536783')
# A single original standing performer; equal fixed limb lengths and common floor.
start=len(S['parts']);x=-.64;z=.22;skin='#C98F6C';shirt='#529DA2';pants='#655B89'
box('performer pelvis',(x,.855,z),(.28,.20,.19),pants)
extrude('performer shirt',[(x-.15,.88),(x+.15,.88),(x+.21,1.29),(x-.21,1.29)],z-.11,z+.11,shirt)
rod('neck',(x,1.28,z),(x,1.38,z),.055,skin)
oval('head hair',(x,1.49,z),.135,[.90,1.12,.87],'#514F65',True)
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
performer=S['parts'][start:]
# Matching pose printed on the screen: same mesh flattened onto its front plane.
import copy
for original in performer:
 p=copy.deepcopy(original);p['name']='projected '+p['name'];v=np.array(p['vertices']);v[:,0]=(v[:,0]-x)*.60+.48;v[:,1]=v[:,1]*.60+.66;v[:,2]=-.311
 p.update(vertices=v.tolist(),color='#9B86AA',double_sided=True,flat_paint=True);S['parts'].append(p)
# Small face features belong to the live actor; not enlarged into the screen symbol.
for xx in [-.035,.035]:
 rod('eye',(x+xx,1.497,z+.145),(x+xx,1.497,z+.151),.010,'#514F65',12);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(height_m=1.641,exposed_neck_m=.045,upper_arm_radius_m=.041,thigh_radius_m=.071,left_right_leg_lengths_equal=True,shoe_bottom_y_m=0,screen_foot_bottom_y_m=0,projection_scale=.60)
S['notes']=['Anonymous original neutral pose with continuous sleeves and trousers; hands hang beside the thighs. Both equal-length legs terminate in shoes on y=0, as do the screen feet. Neck overlaps shirt and head, leaving a short exposed segment. Matching figure is a flat image on the screen, not a second levitating performer. No specific Rocky Horror character or production blocking is copied.']

scene('tree-care',(5,6,8))
box('paving slab',(0,-.06,0),(1.6,.12,1.48),'#A5B3B2')
box('soil bed',(0,.008,0),(1.32,.016,1.20),'#917259')
ring_y('mulch away from trunk',(0,.016,0),.52,.16,.045,'#AD815E',40)
rod('rooted trunk',(0,-.06,0),(.015,1.40,0),.074,'#927356',20,r2=.040)
for end in [(-.30,1.47,.03),(.34,1.59,-.02),(-.06,1.81,0)]:rod('attached branch',(.008,1.10,0),end,.037,'#927356',16,r2=.017)
for c,r,sc,col in [((-.28,1.62,.01),.36,[1,1.1,.75],'#76A76D'),((.29,1.75,-.04),.37,[1,1.08,.80],'#689B6D'),((-.06,2.00,0),.38,[1,1,.8],'#80AF73')]:oval('leaf canopy',c,r,sc,col,True)
# Hand cultivator lies completely on the exposed bed, clear of the trunk.
rod('care tool handle',(.40,.072,.33),(.61,.072,.33),.036,'#DBAD69',20)
rod('care tool shaft',(.22,.070,.33),(.40,.070,.33),.012,'#657F89',12)
rod('care tool head',(.22,.070,.24),(.22,.070,.42),.014,'#657F89',12)
for zz in [.25,.33,.41]:rod('care tool tine',(.22,.07,zz),(.13,.030,zz),.014,'#657F89',12)
for p in S['parts']:
 if p['name'] in ['mulch away from trunk','rooted trunk','attached branch','care tool shaft','care tool head','care tool tine','care tool handle']:p['flat_paint']=True
S['measurements']=dict(paving_m=[1.60,.12,1.48],tree_bed_m=[1.32,1.20],trunk_base_below_soil_m=.06,mulch_inner_radius_m=.16,mulch_outer_radius_m=.52,mulch_depth_m=.045,tree_height_illustrative_m=2.38)
S['notes']=['Small tree grows from a soil bed surrounded by paving. Branches join the rooted trunk and enter overlapping canopy volumes. A low mulch ring leaves a visible gap around the trunk, avoiding a mound against bark. Care tool rests in the bed; no floating hand or unsupported grip. Dimensions are illustrative, not a municipal planting standard or species-specific care prescription.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-029')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')

