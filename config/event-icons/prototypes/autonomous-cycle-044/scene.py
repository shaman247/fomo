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
 x,y,z=c;n=16;rings=7;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
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


scene('sensory-bin',(5,7,10))
# A shallow rimmed tray. Every object rests on the filler surface or tray rim.
box('tray base',(0,.008,0),(.48,.016,.33),'#619E9F')
frame('tray walls',(0,.045,0),.48,.33,.014,.072,'#80B2B0')
frame('thick rim',(0,.08,0),.49,.34,.021,.012,'#9DC5C0')
box('tactile filler',(0,.03,0),(.449,.028,.299),'#D2B88B')
# Broad textured patches are actual flat pieces on the filler, not stippled noise.
for x,z,r in [(-.15,-.07,.025),(.12,.07,.020),(.02,-.10,.019)]:
 rod('texture disc',(x,.044,z),(x,.045,z),r,'#BDA177',10)
# Big ring and block represent sortable objects, not an age-safety recommendation.
ring_y('sorting ring',(-.105,.044,.045),.050,.030,.019,'#C38DA5',24)
box('wood block',(.13,.069,-.06),(.065,.050,.065),'#6A96B4')
rod('block circular motif',(.13,.094,-.06),(.13,.0945,-.06),.020,'#D9E6DC',20)
# A shallow scoop with connected handle, resting in the bin.
first=len(S['parts'])
lathe('scoop cup',[(0,0),(.034,0),(.049,.041),(.043,.044),(.029,.007),(0,.007)],'#B77F9A',24)
rod('scoop handle',(0,.024,.033),(0,.032,.109),.011,'#B77F9A',12)
for p in S['parts'][first:]:p['vertices']=(np.asarray(p['vertices'])+[.055,.044,.025]).tolist()
S['measurements']=dict(width=.48,depth=.33,base_top=.016,filler_top=.044,rim_top=.086,ring_bottom=.044,block_bottom=.044,scoop_bottom=.044)
S['notes']=['Shallow tray has continuous base, four walls and an overlapping rim. Ring, block and scoop rest on the filler plane y=.044 m. Interior colors and sortable forms are symbolic, not a promised activity inventory, filler composition, child-age suitability or therapeutic claim.']

scene('foil-sculpture',(5,6,10))
# One thin crinkled rectangular sheet, with a lifted corner, next to a crumpled form.
# No historic artifact, melting, casting, gold leaf or chemical process is represented.
v=[[-.14,.001,-.085],[.012,.003,-.085],[.005,0,.065],[-.14,.002,.068],[-.064,.008,-.008],[-.14,.037,-.047]]
mesh('thin foil sheet',v,[[0,1,4],[1,2,4],[2,3,4],[3,5,4],[5,0,4]],'#D9B160');S['parts'][-1]['double_sided']=True
# Alternating triangular creases make a foil-like surface. Lower point rests on y=0.
n=10;rings=6;v=[]
for j,t in enumerate(np.linspace(-math.pi/2,math.pi/2,rings)):
 for i,a in enumerate(np.linspace(0,2*math.pi,n,endpoint=False)):
  rad=.047*(1+.14*math.sin(i*2.6+j*1.7))
  v.append([rad*math.cos(t)*math.cos(a),rad*math.sin(t),rad*math.cos(t)*math.sin(a)])
f=[]
for j in range(rings-1):
 for i in range(n):
  a=j*n+i;bb=(j+1)*n+i;c=(j+1)*n+(i+1)%n;d=j*n+(i+1)%n;f += [[a,bb,c],[a,c,d]]
arr=np.array(v);arr[:,1]-=arr[:,1].min();arr += [.075,0,.01];mesh('crumpled foil form',arr,f,'#DAB76B')
S['measurements']=dict(sheet_span_x=.152,sheet_span_z=.153,sheet_min_y=0,folded_corner_y=.037,crumpled_form_lowest_y=0,form_center_x=.075)
S['notes']=['The thin sheet is an original triangulated folded surface, drawn double-sided, with a raised edge. Crumpled form is a compact faceted foil study resting on y=0, separate from the sheet. Gold-colored paint indicates craft foil, not precious-metal content or a Colombian artifact. Reflective appearance is stylized using a few coherent lighting bands; no physical metal simulation.']

scene('finger-puppets',(1,2,14))
# Hollow closed-top covers for individual fingers, with textile animal emblems.
for idx,(offset,col,accent) in enumerate([(-.027,'#AB93BD','#D9C8E0'),(.027,'#DCA477','#F0D2AB')]):
 first=len(S['parts']);r=.016
 # Outer wall rises from open hem into domed cap; inner wall returns to open hem.
 profile=[(r,0),(r,.053),(.014,.064),(.009,.071),(0,.073),(0,.069),(.008,.068),(.012,.062),(.013,.052),(.013,0),(r,0)]
 lathe('felt finger sleeve',profile,col,24)
 # Hem remains hollow; short stitches decorate front and do not cap the opening.
 for x in [-.010,0,.010]:rod('hem stitch',(x,.005,math.sqrt(max(0,r*r-x*x))+.0003),(x,.008,math.sqrt(max(0,r*r-x*x))+.0003),.0006,accent,6)
 if idx==0:
  for side in [-1,1]:
   outline=[(side*.014,.060),(side*.017,.085),(side*.004,.071)]
   if side<0:outline.reverse()
   extrude('cat ear',outline,-.004,.001,col)
 else:
  for side in [-1,1]:oval('round bear ear',(side*.013,.067,-.002),.008,[1,1,.45],col,True)
 # Eyes and muzzle are small felt appliques attached to the forward curved wall.
 for side in [-1,1]:oval('eye',(side*.006,.058,.0145),.0015,[1,1,.35],'#4F525D',True)
 oval('muzzle',(0,.049,.0162),.006,[1,.7,.15],accent,True)
 oval('nose',(0,.053,.0172),.002,[1,.65,.4],'#665A61',True)
 for a,bb in [((0,.051),(-.004,.047)),((0,.051),(.004,.047))]:rod('stitched smile',(a[0],a[1],.0175),(bb[0],bb[1],.0175),.00055,'#756676',6)
 for p in S['parts'][first:]:p['vertices']=(np.asarray(p['vertices'])+[offset,0,0]).tolist()
S['measurements']=dict(covers=2,outer_radius=.016,inner_radius=.013,body_height=.073,centers_x=[-.027,.027],bottom_open=True,material_thickness_approx=.003,lowest_y=0)
S['notes']=['Two short closed-top fabric covers have open bottom hems and inner walls. Cat triangular ears and bear round ears attach to their caps; facial patches stay on the front surface. This is an original standalone equipment study with no actual human finger or hand anatomy, no operating pose and no promised character or sewing pattern.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-044/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
