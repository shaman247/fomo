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
 x,y,z=c;n=24;rings=11;v=[[x+r*math.cos(t)*math.cos(a),y+r*math.sin(t),z+r*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)
def basis(cam):
 n=np.array(cam,float);n/=np.linalg.norm(n);right=np.cross([0,1,0],n);right/=np.linalg.norm(right);up=np.cross(n,right);return right,up,n

def flat_extrude(name,outline,y0,y1,col):
 extrude(name,outline,y0,y1,col);p=S['parts'][-1];p['vertices']=[[x,z,y] for x,y,z in p['vertices']];p['faces']=[list(reversed(f)) for f in p['faces']]

def ellipsoid(name,c,scale,color,n=24,rings=9):
 x,y,z=c;rx,ry,rz=scale
 v=[[x+rx*math.cos(t)*math.cos(a),y+ry*math.sin(t),z+rz*math.cos(t)*math.sin(a)] for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
 mesh(name,v,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],color)

scene('banana-leaf-weaving',(4,9,11))
# Four-by-four original over-under ribbons, with continuous thickness and grounded low points.
def ribbon(name,c,phase,rotate,col):
 samples=np.linspace(-.39,.39,49);v=[]
 for t in samples:
  y=.014+.011*math.cos(math.pi*(t+.225)/.15+phase)
  for side,dy in [(-1,-.003),(1,-.003),(1,.003),(-1,.003)]:
   x=c+side*.058;z=t;v.append([z,y+dy,x] if rotate else [x,y+dy,z])
 faces=[]
 for i in range(len(samples)-1):
  for j in range(4):faces.append([4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j])
 faces += [[3,2,1,0],[4*(len(samples)-1)+j for j in range(4)]]
 mesh(name,v,[list(reversed(f)) for f in faces] if rotate else faces,col)
for j,c in enumerate([-.225,-.075,.075,.225]):
 ribbon('banana leaf length strip',c,j*math.pi,False,'#829B6E')
 ribbon('banana leaf cross strip',c,(j+1)*math.pi,True,'#B0B787')
# Broad ribbed material sample beside patch; generic banana-leaf silhouette, no copied weaving pattern.
center=.51;zs=np.linspace(-.39,.39,21)
outline=[[center-.12*math.sin(math.pi*(z+.39)/.78),.005,z] for z in zs]+[[center+.12*math.sin(math.pi*(z+.39)/.78),.005,z] for z in zs[::-1]]
panel('banana leaf material',outline,'#7C9870')
rod('leaf midrib',(center,.009,-.39),(center,.009,.39),.006,'#B7C196',8)
for z in np.linspace(-.27,.27,7):
 w=.105*math.sin(math.pi*(z+.39)/.78)
 for side in [-1,1]:rod('parallel leaf vein',(center,.009,z),(center+side*w,.009,z+.055),.0025,'#A4B38A',6)
S['notes']=['Original continuous ribbon meshes alternate above and below at16crossings; ribbon thickness separates surfaces and lowest points meet ground. Broad leaf sample supplies material cue. No frame loom, thread yarn or exact artist design; this is a generic basic weave, not a claimed traditional pattern or finished class project.']

scene('pepper-drying',(3,3,11))
# A small free-standing drying rack supports a continuous string and four peppers.
for x in [-.40,.40]:
 box('rack upright',(x,.44,0),(.035,.88,.035),'#B59878')
 box('rack foot',(x,.017,0),(.14,.034,.26),'#A58769')
rod('rack top',(-.45,.88,0),(.45,.88,0),.022,'#C0A584',16)
# Each pod is a single curved tapering volume, no floating disconnected tips.
def pepper(x,top,length,curve,col):
 n=20;ts=np.linspace(0,1,17);verts=[]
 for t in ts:
  center=np.array([x+curve*t*t,top-length*t,0])
  radius=.066*(math.sin(math.pi*(.12+.88*t))**.75)
  if t==1:radius=.001
  verts.extend([center+[radius*math.cos(a),0,radius*.65*math.sin(a)] for a in np.linspace(0,2*math.pi,n,endpoint=False)])
 faces=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(ts)-1) for i in range(n)];faces+=[list(range(n-1,-1,-1)),list(range((len(ts)-1)*n,len(ts)*n))]
 faces=[tri for f in faces for tri in ([[f[0],f[1],f[2]],[f[0],f[2],f[3]]] if len(f)==4 else [f])]
 mesh('drying pepper pod',verts,faces,col);S['parts'][-1]['flat_paint']=True
 rod('pepper stem',(x,top-.015,0),(x+.012,top+.08,0),.011,'#87916B',12)
 # Thread contacts stem/upper pod, then the supporting rail. Symbolic, not an instructional knot.
 rod('hanging thread',(x+.009,top+.055,0),(x+.009,.88,0),.004,'#D5C5A5',8)
for args in [(-.27,.71,.39,-.035,'#B76C53'),(-.09,.63,.43,.04,'#A96050'),(.09,.73,.41,-.035,'#C18755'),(.27,.66,.39,.035,'#B86F54')]:pepper(*args)
S['notes']=['Original four curved pepper volumes hang via stems/threads attached to a grounded rack. This preserves physical support while symbolizing drying. Extension describes rack or threaded peppers; event does not specify air drying, cultivar, time or preparation. No preservation instructions or efficacy claim.']

scene('kalamkari',(4,7,11))
# A gently folded cloth sheet on a work surface, with original floral mark and cotton-wrapped kalam.
box('cloth underfold',(0,.008,0),(.64,.016,.67),'#C8B58F')
box('cloth surface',(0,.019,0),(.67,.007,.70),'#E4D2AB')
# Original simple floral strokes painted flat on cloth, not copied from an artwork/tradition.
for t in np.linspace(0,2*math.pi,6,endpoint=False):
 cx=-.075+.092*math.cos(t);cz=-.04+.092*math.sin(t)
 pts=[[cx+.050*math.cos(a),.023,cz+.065*math.sin(a)] for a in np.linspace(0,2*math.pi,24,endpoint=False)]
 panel('original flower petal',pts,'#A26455')
rod('painted flower center',(-.075,.023,-.04),(-.075,.025,-.04),.041,'#B49A67',24)
for a,bb in [((-.075,.025,.06),(-.05,.025,.27)),((-.05,.025,.20),(.065,.025,.12))]:rod('painted stem',a,bb,.008,'#696B54',10)
flat_extrude('painted leaf',[(-.047,.18),(.03,.22),(.085,.16),(.065,.12),(.00,.12)],.024,.026,'#808466')
# Kalam lies diagonally with a cotton dye reservoir near the sharpened end.
a=np.array([.13,.072,.25]);bb=np.array([.40,.072,-.32]);axis=bb-a;unit=axis/np.linalg.norm(axis)
rod('bamboo kalam',a,bb,.018,'#B99A69',20)
rod('sharpened bamboo tip',a-unit*.07,a,.003,'#655945',16,.018)
rod('cotton reservoir',a+axis*.12,a+axis*.34,.049,'#D5C7A6',24,.039)
# Wrapped thread as ring bands around cotton, each contacts its surface.
for frac in [.15,.23,.31]:rod('cotton binding thread',a+axis*frac,a+axis*(frac+.014),.050-(frac-.12)*.045,'#93795A',20)
# The wrapped reservoir supports the pen at cloth height; a small rest supports rear shaft.
box('pen rest',tuple(bb-[0,.045,0]),(.09,.054,.065),'#BFA889')
S['notes']=['Original cloth with generic six-petal floral study, never a copied sacred/historical design. Original pointed bamboo pen has a cotton reservoir secured by thread near tip. Cotton bottom.023 meets cloth surface; rear shaft rests on a small block. NID/government tool text informs structure. No complete dye process, actual class kit or block-print-only tradition claimed.']

# Two related but distinct fair scenes use information tables without human figures.
def fair(name,volunteer):
 scene(name,(4,4,11))
 for x,z,col in [(-.22,-.12,'#A77E62'),(.24,.18,'#819A9D')]:
  for dx in [-.20,.20]:
   for dz in [-.105,.105]:box('table leg',(x+dx,.18,z+dz),(.026,.36,.026),'#A6A094')
  box('tabletop',(x,.378,z),(.47,.036,.29),col)
  # Rear sign on two posts contacts table.
  for dx in [-.13,.13]:box('sign post',(x+dx,.51,z-.11),(.02,.24,.025),'#ADB3A7')
  box('recruitment sign',(x,.66,z-.09),(.39,.21,.045),'#D9D3B9')
  if volunteer:
   outline=[]
   for t in np.linspace(0,2*math.pi,48,endpoint=False):outline.append((x+.006*(16*math.sin(t)**3),.66+.006*(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))))
   extrude('volunteer heart',outline,z-.065,z-.058,'#B87C75')
  else:
   box('briefcase emblem',(x,.655,z-.060),(.20,.09,.012),'#8B8D7B')
   # Open handle made from connected segments on sign face.
   for aa,bbb in [((x-.040,.70,z-.05),(x-.040,.733,z-.05)),((x-.040,.733,z-.05),(x+.040,.733,z-.05)),((x+.040,.733,z-.05),(x+.040,.70,z-.05))]:rod('briefcase handle',aa,bbb,.008,'#8B8D7B',8)
   box('briefcase clasp',(x,.655,z-.052),(.025,.035,.005),'#D6CBA9')
  box('information sheets',(x+.06,.405,z+.02),(.14,.018,.16),'#EEE7CF')
 S['notes']=['Two original recruitment tables have four equal legs, supported tops, connected sign posts and small information sheets. '+('Heart signs indicate volunteer organizations.' if volunteer else 'Briefcase signs indicate employment recruitment.')+' No exact booth layout, institution, participant count or guaranteed placement implied.']
fair('career-fair',False)
fair('volunteer-fair',True)
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
