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
scene('blacksmithing',(3,3,10))
# Original single-horn anvil; approximate473mm-long,200mm-high workshop scale.
outline=[(-.095,0),(.095,0),(.095,.025),(.048,.072),(.042,.135),(.102,.180),(.108,.188),(-.108,.188),(-.102,.180),(-.042,.135),(-.048,.072),(-.095,.025)]
extrude('anvil waist and foot',outline,-.070,.070,'#657D87')
box('horn shoulder',(-.115,.165,0),(.050,.050,.080),'#657D87')
# Face slab, with a genuine square hardy opening in the heel overhang.
x0,x1=-.132,.170;hx=.137;h=.022;z0,z1=-.05,.05
box('face left',((x0+hx-h/2)/2,.194,0),(hx-h/2-x0,.012,.10),steel)
box('face heel',((hx+h/2+x1)/2,.194,0),(x1-hx-h/2,.012,.10),steel)
for z in [-(.05+h/2)/2,(.05+h/2)/2]:box('face beside hardy',(hx,.194,z),(h,.012,.05-h/2),steel)
# Circular horn is smoothly tapered, bonded inside the shoulder, tip raised.
rod('round horn',(-.127,.165,0),(-.303,.187,0),.035,steel,40,r2=.0018)
S['notes']=['Original single-horn anvil is473mm overall length,200mm high,100mm face width and190mm foot width. Grounded foot and continuous waist support the flat face.22mm square hardy opening passes through the overhanging heel beyond the body. Round horn narrows continuously toward its raised tip, with base embedded in shoulder. Dimensions use a manufacturer range as scale guidance, not a replica or the exact workshop anvil. No striking pose or forging process is depicted.']
S['measurements']=dict(total_length_m=.473,height_m=.20,face_width_m=.10,hardy_hole_m=.022,heel_hole_clear_of_body_m=.137-.011-.108)
scene('instant-camera',(2,2.5,12))
# Generic instant camera, using mini-format dimensions without copying casing/logo.
outline=[(x,y+.061) for x,y in rounded_outline(.104,.122,.015)]
extrude('camera body',outline,-.028,.025,'#719CAA')
rod('lens collar',(0,.053,.024),(0,.053,.039),.029,'#ADC7C8',48)
rod('lens rim',(0,.053,.039),(0,.053,.044),.020,'#486975',48)
rod('optical glass',(0,.053,.044),(0,.053,.0445),.013,'#263D50',40)
rod('glass reflection',(-.004,.058,.0446),(-.004,.058,.0448),.004,'#75B5C8',24)
box('flash window',(-.027,.101,.0255),(.025,.011,.002),cream)
box('finder frame',(.032,.098,.0255),(.014,.013,.002),'#365363')
box('finder glass',(.032,.098,.0266),(.009,.008,.0003),'#92BDC4')
rod('shutter',(-.032,.070,.025),(-.032,.070,.028),.0055,'#D6AF79',24)
# Output slot at top: a modeled opening in a separate dark mouth surround.
box('output mouth',(0,.1221,-.006),(.062,.001,.009),'#365363')
# Thin54x86mm print partly inside slot; only upper58mm emerges, model full stock.
box('instant print',(0,.137,-.006),(.054,.086,.0005),cream)
box('picture field',(0,.148,-.00570),(.046,.058,.00008),'#98BDC1')
# Original simple landscape on physical paper surface, no depicted person.
panel('landscape',[(-.023,.119,-.00564),(.023,.119,-.00564),(.023,.135,-.00564),(.008,.148,-.00564),(-.004,.138,-.00564),(-.013,.145,-.00564),(-.023,.132,-.00564)],'#6C9580')
rod('picture sun',(-.012,.161,-.00563),(-.012,.161,-.00561),.0045,'#E7C278',24)
S['notes']=['Original compact camera uses104mm width,122mm body height and approximately67mm overall body/lens depth. Lens cylinders attach to the front; flash, optical finder and shutter share that surface.54x86mm instant stock intersects the top output slot with lower28mm inside the body. Original landscape lies on the visible print surface; partly developed print is a category emblem, not a simulated ejection mechanism. No brand logo or exact casing is copied; actual event camera model is unverified.']
S['measurements']=dict(body_width_m=.104,body_height_m=.122,film_width_m=.054,film_height_m=.086,slot_width_m=.062,lateral_film_clearance_m=.004,film_below_slot_m=.122-(.137-.043))
scene('woodcarving',(2,12,9))
# Faceted wooden blank with chamfered upper corners, resting on its lower face.
section=[(-.022,0),(.022,0),(.022,.022),(.014,.034),(-.014,.034),(-.022,.022)]
v=[[x,y,z-.040] for x in [-.085,.065] for z,y in section];n=len(section)
# Orient faces outward by testing against centroid for this convex solid.
faces=[list(range(n)),list(range(n,2*n))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
vs=np.array(v);center=vs.mean(0)
for f in faces:
 if np.dot(np.cross(vs[f[1]]-vs[f[0]],vs[f[2]]-vs[f[0]]),vs[f].mean(0)-center)<0:f.reverse()
mesh('faceted wood blank',v,faces,lightwood)
# Three broad grain lines follow the top face, not surface cut instructions.
for z in [-.047,-.039,-.031]:rod('wood grain',(-.065,.0341,z),(.043,.0341,z),.0007,'#C89761',8)
# Short straight carving blade joins an ergonomic handle on the common plane.
handle=[(-.071,.036),(-.065,.028),(-.047,.025),(-.019,.029),(.014,.030),(.019,.035),(.019,.046),(.007,.050),(-.035,.056),(-.061,.054),(-.072,.047)]
flat_extrude('carving knife handle',handle,0,.014,'#B5734C')
blade=[(.012,.033),(.046,.033),(.049,.040),(.045,.047),(.015,.047)]
flat_extrude('short carving blade',blade,.005,.007,'#B1C6C8')
# Detached shaved chips stay on the support plane and clear both tools and blank.
flat_extrude('wood chip',[(.045,.067),(.069,.066),(.062,.081)],0,.0025,'#DEAD73')
flat_extrude('wood chip',[(-.015,.077),(.003,.067),(.012,.080)],0,.003,'#EAC28A')
S['notes']=['Original150mm wooden blank has continuous chamfered surfaces and grounded lower face. Carving knife has about90mm handle and32mm visible short blade, overlapping the handle by7mm; blade lies inside handle thickness. Knife and blank are separate resting studies, not a cutting pose; detached chips lie on the same support plane. Generic blank/knife symbolize whittling, without claiming a precise cheese-spreader shape or actual class tool. Manufacturer carving-knife proportions inform scale only.']
S['measurements']=dict(blank_length_m=.15,blank_height_m=.034,visible_blade_length_m=.032,blade_handle_overlap_m=.007,blank_knife_gap_m=.025-(-.018))
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-018')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
