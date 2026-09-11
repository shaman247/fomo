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
# Original dance-fitness figure, fixed anatomical lengths and explicit floor contacts.
def ellipsoid(name,c,r,col):
 ball(name,(0,0,0),1,col);S['parts'][-1]['vertices']=(np.array(S['parts'][-1]['vertices'])*r+c).tolist()
def capsule(name,a,b,r1,r2,col):
 rod(name,a,b,r1,col,12,r2);ball(name+' start',a,r1,col);ball(name+' end',b,r2,col)
def joint(a,b,l1,l2,hint):
 a,b=np.array(a,float),np.array(b,float);v=b-a;d=np.linalg.norm(v);u=v/d;h=np.array(hint,float);h-=u*np.dot(h,u);h/=np.linalg.norm(h)
 along=(l1*l1-l2*l2+d*d)/(2*d);return a+u*along+h*math.sqrt(l1*l1-along*along)
def torso(name,levels,col):
 verts=[];n=20
 for y,rx,rz in levels:
  for i in range(n):verts.append([rx*math.cos(2*math.pi*i/n),y,rz*math.sin(2*math.pi*i/n)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]+[list(range(n-1,-1,-1)),list(range((len(levels)-1)*n,len(levels)*n))]
 mesh(name,verts,faces,col)

# Original figures use fixed bone lengths; no traced photograph geometry.
skin='#BE8664';pants='#5D688B';shirt='#52A49B';hair='#45434A'
def human_head(center,tilt=0):
 first=len(S['parts']);cx,cy,cz=center
 ellipsoid('head',(0,0,0),(.103,.133,.090),skin)
 for side in [-1,1]:ellipsoid('ear',(side*.10,-.005,-.005),(.018,.030,.017),skin)
 v=[];n=20
 for theta in np.linspace(0,1.28,6):
  for phi in np.linspace(0,2*math.pi,n,endpoint=False):v.append([.11*math.sin(theta)*math.cos(phi),.145*math.cos(theta),.097*math.sin(theta)*math.sin(phi)-.008])
 mesh('hair',v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(5) for i in range(n)],hair)
 for side in [-1,1]:ellipsoid('eye',(side*.033,.013,.086),(.0075,.01,.005),'#45434A')
 ellipsoid('nose',(0,-.011,.092),(.012,.015,.015),skin)
 rod('mouth',(-.020,-.036,.086),(.020,-.036,.086),.004,'#855E50',8)
 c,s=math.cos(tilt),math.sin(tilt);rot=np.array([[1,0,0],[0,c,-s],[0,s,c]])
 for part in S['parts'][first:]:part['vertices']=(np.array(part['vertices'])@rot.T+center).tolist()
def curved_body(levels,col):
 n=20;v=[]
 for y,z,rx,rz in levels:
  v.extend([[rx*math.cos(a),y,z+rz*math.sin(a)] for a in np.linspace(0,2*math.pi,n,endpoint=False)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(levels)-1) for i in range(n)]
 faces += [list(range(n-1,-1,-1)),list(range((len(levels)-1)*n,len(levels)*n))]
 mesh('continuous curved shirt',v,faces,col)
def palm(name,wrist,end,col):
 # Simple continuous mitten silhouette; no extra fingers or detached hand.
 capsule(name,wrist,end,.029,.030,col)
def foot(x,z,col):
 ellipsoid('soft shoe',(x,.043,z),(.076,.043,.128),col)
 box('grounded sole',(x,.008,z),(.14,.016,.224),col)

def arm(shoulder,wrist,hint,handend,col):
 elbow=joint(shoulder,wrist,.285,.255,hint)
 capsule('upper arm',shoulder,elbow,.039,.035,skin);capsule('forearm',elbow,wrist,.035,.028,skin)
 sleeve=np.array(shoulder)+(elbow-shoulder)*.23;capsule('short sleeve',shoulder,sleeve,.051,.046,col)
 palm('hand',wrist,handend,skin)
 return dict(shoulder=list(shoulder),elbow=elbow.tolist(),wrist=list(wrist),hand_end=list(handend))

scene('graham',(7,3,10));joints={}
# Seated rounded-torso study: buttocks and heels on the same plane, knees opened.
ellipsoid('seated pelvis',(0,.103,0),(.147,.103,.133),pants)
for side in [-1,1]:
 hip=np.array([side*.098,.135,.025]);ankle=np.array([side*.053,.074,.60]);knee=joint(hip,ankle,.42,.40,[side,0,0])
 capsule('trouser thigh',hip,knee,.071,.061,pants);capsule('trouser shin',knee,ankle,.061,.043,pants)
 ellipsoid('bare foot',(side*.052,.035,.66),(.051,.035,.104),skin)
 joints[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
curved_body([(.16,.0,.135,.095),(.29,-.065,.136,.083),(.42,-.064,.143,.09),(.55,.015,.170,.087),(.605,.055,.147,.069),(.62,.063,.066,.053)],shirt)
capsule('neck',(0,.60,.065),(0,.674,.081),.049,.046,skin)
human_head((0,.778,.135),.22)
for side in [-1,1]:
 shoulder=np.array([side*.163,.564,.025]);wrist=np.array([side*.29,.345,.36]);end=wrist+np.array([side*.008,.010,.063])
 joints[str(side)].update(arm(shoulder,wrist,[side,-.2,-.1],end,shirt))
for p in S['parts']:p['flat_paint']=True
S['measurements']=dict(joints=joints,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.071,seat_bottom=0,feet_bottom=0,head_tilt=.22)
S['notes']=['Original seated Graham-inspired rounded-torso floorwork study, not an exact exercise frame or a claim that a static pose captures contraction/release. Buttocks and both feet contact y=0. Fixed paired leg/arm lengths; hands extend openly in front, away from torso. Ailey photograph establishes seated bent-knee floorwork with open arms; museum-curated primary describes breath-led contraction. No choreography or teacher likeness copied.']

scene('vogue',(0,1,20));joints={}
for side in [-1,1]:
 hip=np.array([side*.105,.84,0]);ankle=np.array([side*.27,.085,.018]);knee=joint(hip,ankle,.42,.40,[side*.15,0,1])
 capsule('trouser thigh',hip,knee,.071,.061,pants);capsule('trouser shin',knee,ankle,.061,.047,pants);foot(side*.27,.075,'#E4D9BD')
 joints[str(side)]=dict(hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist())
torso('waist',[(.78,.133,.089),(.88,.137,.086)],pants)
torso('shirt',[(.865,.142,.089),(1.03,.137,.087),(1.21,.171,.097),(1.29,.155,.081),(1.32,.075,.058)],'#B889A9')
capsule('neck',(0,1.30,0),(0,1.385,0),.049,.047,skin);human_head((0,1.495,0))
for side,wrist,hint,end in [(-1,[-.035,1.695,.025],[-1,0,0],[.04,1.70,.025]),(1,[.12,1.39,.17],[1,-.15,0],[.045,1.385,.20])]:
 joints[str(side)].update(arm(np.array([side*.165,1.265,0]),np.array(wrist),hint,np.array(end),'#B889A9'))
for p in S['parts']:p['flat_paint']=True
S['measurements']=dict(joints=joints,femur=.42,tibia=.40,upper_arm=.285,forearm=.255,upper_arm_radius=.039,thigh_radius=.071,foot_plane=0,visible_neck=.042)
S['notes']=['Original standing face-framing arm study: upper arm line and lower hand frame a clear face, with both feet grounded. Does not prescribe choreography, identify a teacher, represent every ballroom substyle or promise a particular move. Ailey primary image and New Way text inform angular arms; no tracing. One flat skin paint and thin arms avoid contradictory shading or inflated limbs.']

scene('ballet-barre',(5,4,10))
for x in [-.46,.46]:
 rod('barre stanchion',(x,.045,0),(x,.88,0),.039,steel)
 box('stable floor foot',(x,.026,0),(.105,.052,.46),dark)
rod('wooden barre',(-.64,.90,0),(.64,.90,0),.040,wood)
# Soft ballet slippers: hollow heel opening, flexible flat sole, crossed elastic.
for side in [-1,1]:
 x=side*.19;z=.39;shoe_first=len(S['parts'])
 ellipsoid('flat slipper sole',(x,.012,z),(.074,.012,.17),'#B88C88')
 ellipsoid('soft slipper toe',(x,.042,z+.076),(.077,.042,.105),'#E6B1AB')
 first=len(S['parts']);lathe('open heel quarter',[(.064,.012),(.073,.025),(.071,.061),(.057,.061),(.052,.025),(.0,.022)],'#E6B1AB',24)
 part=S['parts'][-1];part['vertices']=[[a+x,y,c*1.28+z-.055] for a,y,c in part['vertices']]
 rod('elastic strap',(x-.052,.052,z-.10),(x+.052,.059,z+.015),.009,'#F6D3C6',10)
 rod('elastic strap',(x+.052,.052,z-.10),(x-.052,.059,z+.015),.009,'#F6D3C6',10)
 for part in S['parts'][shoe_first:]:
  vs=np.array(part['vertices']);vs[:,0]=x+(vs[:,0]-x)*1.35;vs[:,2]=z+(vs[:,2]-z)*1.35;part['vertices']=vs.tolist()
S['measurements']=dict(barre_height=.90,barre_length=1.28,post_x=[-.46,.46],foot_plane=0,slipper_sole_bottom=0,shoe_type='soft flat ballet slippers, no pointe box',slipper_plan_scale=1.35,post_radius=.039)
S['notes']=['Two freestanding posts and transverse feet support a single continuous wooden rail. Both illustrative soft slippers rest on y=0 with open heel quarters and crossed elastic. No dancer, pointe block or claimed Ailey equipment inventory. Simplified equipment proportions, not a product specification.']

def flat_extrude(name,outline,y0,y1,color):
 extrude(name,outline,y0,y1,color);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]
scene('knife-skills',(2,9,9))
flat_extrude('cutting board',[(-.27,-.18),(.24,-.18),(.27,-.15),(.27,.17),(-.24,.17),(-.27,.14)],0,.024,'#D3A775')
# Chef blade lies on board; stylized tool at rest, no hand/use instruction.
knife_first=len(S['parts'])
flat_extrude('chef blade',[(-.04,-.052),(.205,-.052),(.235,-.009),(.164,.033),(-.04,.042)],.024,.032,'#B3C5C9')
flat_extrude('blade edge',[(-.04,.025),(.164,.019),(.235,-.009),(.164,.033),(-.04,.042)],.032,.033,'#E4EBEA')
box('knife handle',(-.14,.045,-.005),(.215,.042,.065),'#495E65')
box('bolster',(-.035,.040,-.005),(.027,.032,.068),'#91A9B2')
for x in [-.20,-.12]:rod('handle rivet',(x,.066,-.005),(x,.068,-.005),.006,'#C9D5D4',12)
# Set the blade to 8 inches and handle to about 4.5 inches before layout.
for part in S['parts'][knife_first:]:
 vs=np.array(part['vertices']);rel=vs[:,0]+.04;vs[:,0]=-.04+np.where(rel<0,rel*(.1143/.2075),rel*(.2032/.275));part['vertices']=vs.tolist()
# Narrow the board to retain visual emphasis on the tool.
S['parts'][0]['vertices']=[[x*.8,y,z] for x,y,z in S['parts'][0]['vertices']]
for i in range(3):
 x=.015+i*.052;rod('carrot slice',(x,.052,.092),(x+.024,.052,.092),.028,'#E8A45B',16)
rod('remaining carrot',(-.175,.052,.092),(-.048,.052,.092),.028,'#DD9550',16,r2=.025)
S['measurements']=dict(board_bottom=0,board_top=.024,blade_bottom=.024,blade_top=.032,handle_bottom=.024,carrot_bottom=.024,knife_length=.3175,blade_length=.2032,handle_length=.1143)
S['notes']=['Chef knife, bolster and handle share one axis on a board. Handle, blade and carrot pieces rest on board top .024. Three carrot slices are illustrative, not promised class ingredients. No hand placement, cutting action or safety instruction depicted.']
scene('swiss-roll',(5,4,10))
# Original chocolate sponge roll and one cut slice. Flat cut faces carry a projected spiral.
# The cake rests on its cylindrical lower tangent at y=0; slice shares the plane.
R=.12
for name,center,z0,z1 in [('roll',(.055,R),-.22,.13),('slice',(-.16,R),.17,.245)]:
 x,y=center
 rod(name+' sponge',(x,y,z0),(x,y,z1),R,'#A87853',48)
 # Dark cut face and cream spiral are integral surface layers, not floating marks.
 rod(name+' cut crumb',(x,y,z1),(x,y,z1+.001),R*.98,'#795642',48)
 pts=[]
 for t in np.linspace(0,math.pi*5.1,108):
  r=.008+.0061*t
  for rr in [r-.0048,r+.0048]:pts.append([x+rr*math.cos(t),y+rr*math.sin(t),z1+.0011])
 mesh(name+' cream spiral',pts,[[2*i,2*i+1,2*i+3,2*i+2] for i in range(107)],'#F0D8AA');S['parts'][-1]['double_sided']=True;S['parts'][-1]['flat_paint']=True
 if name=='slice':
  rod('slice rear cut crumb',(x,y,z0),(x,y,z0-.001),R*.98,'#795642',48)
  rear=[[a,b,z0-.0011] for a,b,c in pts];mesh('slice rear cream spiral',rear,[[2*i,2*i+1,2*i+3,2*i+2] for i in range(107)],'#F0D8AA');S['parts'][-1]['double_sided']=True;S['parts'][-1]['flat_paint']=True
S['measurements']=dict(radius=R,axis_y=R,ground_plane=0,roll_length=.35,slice_thickness=.075,cream_radius=.0048,cream_turns=2.55)
S['notes']=['Original rolled chocolate sponge cake with cream spiral and one separate slice, as explicitly named in the primary classic-bakes menu. Cylindrical cake and slice rest on y0; cream pattern is attached to front cut faces. No recipe ratios, serving quantity, brand decoration or exact supplied cake is promised. Surface spiral communicates rolled layers, not a full volumetric baking simulation.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n');Path('.scratch/icon-cycles-20260909/cycle-046/geometry-measurements.json').write_text(json.dumps({k:v['measurements'] for k,v in SCENES.items()},indent=2)+'\n')
