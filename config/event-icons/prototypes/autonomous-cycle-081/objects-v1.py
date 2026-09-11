"""Original construction studies. Metres,Y-up. No person or actual animal model.
Balloon is ten inflated sections joined by narrow twists; paired bubbles loop
between shared endpoints. Stair is a generic five-riser race symbol, not ESB.
"""
import scene as sc
from scene import *
def bubble(name,a,b,r,col,bend=(0,0,0),n=16,rings=15):
 a=np.asarray(a,float);b=np.asarray(b,float);bend=np.asarray(bend,float);pts=[a+(b-a)*t+bend*math.sin(math.pi*t) for t in np.linspace(0,1,rings)];verts=[]
 for j,(t,p) in enumerate(zip(np.linspace(0,1,rings),pts)):
  axis=np.asarray(pts[min(j+1,rings-1)])-pts[max(j-1,0)];axis/=np.linalg.norm(axis);u=np.cross(axis,[0,0,1] if abs(axis[2])<.9 else [0,1,0]);u/=np.linalg.norm(u);v=np.cross(axis,u);rad=.0025+(r-.0025)*math.sin(math.pi*t)**.55
  verts.extend(p+rad*(u*math.cos(q)+v*math.sin(q)) for q in np.linspace(0,2*math.pi,n,endpoint=False))
 faces=[[i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j] for i in range(rings-1) for j in range(n)]
 faces += [list(range(n-1,-1,-1)),list(range((rings-1)*n,rings*n))];mesh(name,verts,faces,col)
scene('balloon-twisting',camera=(-3,1.8,7));col='#56B5AB'
front=(-.055,.108,0);back=(.055,.108,0);head=(-.064,.165,0);nose=(-.114,.168,0);ear=(-.066,.213,0)
bubble('body',front,back,.019,col)
bubble('neck',front,head,.018,col)
bubble('muzzle',head,nose,.018,col)
for side in [-1,1]:
 bubble('ear '+str(side),head,ear,.015,col,bend=(0,0,side*.017))
 bubble('front leg '+str(side),front,(-.065,.01,0),.017,col,bend=(0,0,side*.02))
 bubble('rear leg '+str(side),back,(.067,.01,0),.017,col,bend=(0,0,side*.02))
bubble('tail',back,(.099,.175,0),.016,col)
rod('tied nozzle',nose,(-.124,.167,0),.0025,col,n=8)
sc.S['notes']=['Original long-balloon dog topology from instructor photo and manufacturer text; dimensions stylized, not a step-by-step lesson.','Four inflated leg sections have equal endpoint lengths by mirrored front/rear arrangement, with paired ends joined. Ears paired, muzzle/neck distinct; no eyes or animal anatomy added.','Same teal latex throughout, coherent broad shading. Transparent support, pump and human hands not depicted.']
scene('tower-race',camera=(4,3.5,7));step=.26;rise=.18;depth=.62
for i in range(5):box('stair '+str(i),(i*step,(i+1)*rise/2,0),(step,(i+1)*rise,depth),'#93B2BB')
# Flat checkered flag is attached to a pole standing on the top tread.
rod('finish pole',(1.1,.9,-.19),(1.1,1.53,-.19),.024,'#667E89',n=12)
box('flag',(1.255,1.365,-.19),(.31,.25,.008),'#EEE3C8')
for i in range(3):
 for j in range(2):
  if (i+j)%2==0:box('check '+str(i)+str(j),(1.1+(i+.5)*.103333,1.24+(j+.5)*.125,-.183),(.103333,.125,.003),'#708C93')
sc.S['notes']=['Five equal180mmrisers and260mmtreads,620mmwide; illustrative cropped stair segment, not the actual ESB stairwell.','Solid risers rest on common ground; finish pole rests on upper tread and flag is physically attached. No runner or implied safety/access guarantee.']
if __name__=='__main__':
 (ROOT/'scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
