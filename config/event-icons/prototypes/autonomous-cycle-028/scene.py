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


scene('miniature-houses',(3,4,8))
# Original hollow cardstock house with painted windows; no lamp or wiring.
box('display base',(-.02,.0015,0),(.145,.003,.105),'#DDD7C2')
outline=[(-.07,.003),(.03,.003),(.03,.075),(-.02,.115),(-.07,.075)]
extrude('front card wall',outline,.033,.035,'#D78D83');extrude('rear card wall',outline,-.035,-.033,'#D78D83')
for x in [-.069,.029]:box('side card wall',(x,.039,0),(.002,.072,.066),'#D78D83')
roof=[(-.078,.074),(-.02,.120),(.038,.074),(.038,.069),(-.02,.115),(-.078,.069)]
roof.reverse();extrude('folded card roof',roof,-.041,.041,'#87A7A7')
for x in [-.046,.006]:
 box('painted window',(x,.049,.0353),(.020,.022,.0006),'#EAD49C')
 box('window mullion',(x,.049,.0357),(.0025,.022,.0002),'#AC776B')
 box('window crossbar',(x,.049,.0357),(.020,.0025,.0002),'#AC776B')
box('painted door',(-.02,.020,.0353),(.022,.034,.0006),'#A56F68')
# Extra unassembled house-shaped paper piece on work surface, beside model.
flat_extrude('flat card blank',[(.060,-.035),(.114,-.035),(.114,.012),(.087,.035),(.060,.012)],0,.001,'#E8C58B')
rod('craft brush handle',(.077,.0044,.055),(.13,.0044,-.028),.0028,'#6C949A',10)
rod('craft brush ferrule',(.071,.0044,.064),(.077,.0044,.055),.0034,'#A8B5B0',10)
rod('craft brush bristles',(.062,.0044,.078),(.071,.0044,.064),.0004,'#8C7056',10,r2=.0034)
S['measurements']=dict(house_width_m=.1,house_depth_m=.07,house_height_m=.117,card_wall_thickness_m=.002,roof_projected_thickness_m=.005,display_base_thickness_m=.003)
S['notes']=['Original hollow miniature cardstock house rests on a small display base. Painted door and windows are surface decoration rather than holes or lit glass. Roof fold contacts the gabled walls with a small overhang. Separate flat house-shaped blank and brush indicate decorative making and miniature scale, not full-size construction. No exact class kit, copied vintage design, lighting or hand pose is implied.']
scene('foam-block-play',(4,5,8))
# Freestanding arch, through-hole block and loose cylindrical foam piece.
outer=[(-.34+.34*math.cos(a),.34*math.sin(a)) for a in np.linspace(0,math.pi,25)]
inner=[(-.34+.18*math.cos(a),.18*math.sin(a)) for a in np.linspace(math.pi,0,25)]
extrude('foam arch',outer+inner,-.14,.14,'#649BB8')
# Square block with circular through-hole. Rings are connected at the front,
# rear, outside and inside; the aperture is real and visible from both faces.
cx=.26;cy=.22;n=32;v=[]
for z in [-.25,-.01]:
 for ring in ['outside','inside']:
  for a in np.linspace(0,2*math.pi,n,endpoint=False):
   rr=.22/max(abs(math.cos(a)),abs(math.sin(a))) if ring=='outside' else .11
   v.append([cx+rr*math.cos(a),cy+rr*math.sin(a),z])
f=[]
for i in range(n):
 j=(i+1)%n
 f.extend([[i,n+i,n+j,j],[2*n+i,2*n+j,3*n+j,3*n+i],[i,j,2*n+j,2*n+i],[n+i,3*n+i,3*n+j,n+j]])
mesh('foam hole block',v,f,'#649BB8')
rod('loose foam cylinder',(-.02,.09,.29),(.53,.09,.29),.09,'#6AA3BE',24)
S['measurements']=dict(arch_outer_radius_m=.34,arch_inner_radius_m=.18,arch_depth_m=.28,square_block_m=[.44,.44,.24],hole_radius_m=.11,cylinder_length_m=.55,cylinder_radius_m=.09,ground_y_m=0)
S['notes']=['Original arrangement of oversized loose blue foam shapes, grounded at y=0: open-bottom arch, square block with real through-hole, and horizontal cylinder. No balancing stack, promised set, child pose or manufacturer logo. Illustrative dimensions are not product specifications.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-028')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
