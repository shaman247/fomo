"""Original craft-object studies. Dimensions are representative, not event kit specifications."""
from scene import *
import scene as sc

scene('mizuhiki',(0,10,2.0))
# Open awaji-form route, constructed from continuous cubic arcs. These control
# points are original, not sampled from the maker's illustration. The three
# loops and alternating crossings follow the functional knot structure.
segments=[((-45,-35),(-15,-15),(0,10),(26,14)),((26,14),(57,12),(45,-30),(20,-20)),((20,-20),(-8,-24),(-16,-6),(-20,18)),((-20,18),(-25,47),(34,45),(16,18)),((16,18),(28,-5),(6,-27),(-19,-21)),((-19,-21),(-55,-28),(-57,20),(-31,14)),((-31,14),(-11,26),(16,-8),(49,-34))]
route=[]
for seg in segments:
 p=np.array(seg,float)*.0007
 for t in np.linspace(0,1,19,endpoint=False):route.append((1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3])
route.append(np.array(segments[-1][-1])*.0007);route=np.array(route)
from shapely.geometry import LineString
crossings=[]
for i in range(len(route)-1):
 for j in range(i+3,len(route)-1):
  hit=LineString(route[i:i+2]).intersection(LineString(route[j:j+2]))
  if hit.geom_type=='Point':crossings.append((i,j))
# Assign alternating over/under encounters along the continuous strand.
encounters=sorted([(i,k,0) for k,(i,j) in enumerate(crossings)]+[(j,k,1) for k,(i,j) in enumerate(crossings)])
raised={};seen={}
for n,(i,k,which) in enumerate(encounters):
 if k not in seen:seen[k]=n%2
 raised[i]=seen[k] if which==0 else 1-seen[k]
height=np.full(len(route),.00115)
for i,up in raised.items():
 if up:
  for k in range(max(0,i-9),min(len(route),i+11)):
   height[k]=max(height[k],.00115+.0056*math.exp(-((k-i-.5)/4.8)**2))
for c,col in [(-1,'#C69B61'),(0,'#EFE0BD'),(1,'#B9848C')]:
 pts=[]
 for i,(x,z) in enumerate(route):
  d=route[min(i+1,len(route)-1)]-route[max(i-1,0)];d/=np.linalg.norm(d);normal=np.array([-d[1],d[0]]);x,z=np.array([x,z])+normal*c*.00235
  pts.append((x,height[i],z))
 tube('continuous paper cord '+str(c),pts,.0011,col,n=8)
sc.S['notes']=['Original three-cord awaji-form decorative knot; twisted paper cords, not macrame rope. Maker Tsuda five-step awaji diagram establishes loop/crossing topology, not copied coordinates.','Cord diameter2.2mm is an illustrative enlargement. Adjacent centerlines2.35mm apart. Ground contacts at low arcs; raised crossing spans rest on the lower bundle. No suspended hands or tools.','Alternating crossing order follows one continuous open strand; three parallel strands have six free ends. Inspect all six views for crossing separation and clear openings.','The gourd and leaf workshops use different finished motifs. This generic technique emblem does not promise the exact ornament, color or number of cords supplied.']
sc.S['crossings']=crossings

scene('nerikiri',(2,7,6))
# Low serving board and two original floral sweets. No source composition copied.
box('small serving board',(0,.0015,0),(.096,.003,.057),'#B68D73')
def flower(name,c,R,h,col,lobes=5):
 x,y,z=c;n=60;rings=[(0,0),(.84,.05),(1,.28),(.95,.62),(.65,.90),(0,1)]
 vv=[]
 for radius,yy in rings:
  for a in np.linspace(0,2*math.pi,n,endpoint=False):
   rr=R*radius*(.86+.14*math.cos(lobes*a));vv.append((x+rr*math.cos(a),y+h*yy,z+rr*math.sin(a)))
 ff=[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(len(rings)-1) for i in range(n)]
 mesh(name,vv,ff,col)
flower('five-petal nerikiri',(-.022,.003,.002),.022,.017,'#AA83AD')
ellipsoid('flower center',(-.022,.020,.002),(.004,.0018,.004),'#F2DB9C',n=16,rings=7)
# Chrysanthemum: one solid rounded mass, with radial surface scoring represented
# by gentle shape grooves rather than a disconnected pile of petals.
x=.025;n=72;rings=13;vv=[]
for t in np.linspace(-math.pi/2,math.pi/2,rings):
 for a in np.linspace(0,2*math.pi,n,endpoint=False):
  rad=.019*math.cos(t)*(1-.045*(1-math.cos(18*a))*.5)
  vv.append((x+rad*math.cos(a),.018+.015*math.sin(t),rad*math.sin(a)))
mesh('scored chrysanthemum sweet',vv,[[j*n+i,(j+1)*n+i,(j+1)*n+(i+1)%n,j*n+(i+1)%n] for j in range(rings-1) for i in range(n)],'#EBC568')
ellipsoid('small paste leaf',(.026,.005,.019),(.010,.002,.004),'#86A780',n=16,rings=7)
sc.S['notes']=['Original representative edible-paste flowers44mm and38mm wide,17/30mm tall, on96x57mm board. All sweets contact the board atY3mm. Leaf is joined at board and sweet base.','Nerikiri primary event photo establishes hand-shaped floral paste, five petals and radial chrysanthemum scoring. No exact flower, tray layout or photograph coordinates reproduced.','One continuous petal mass and one scored rounded mass; no disconnected petals or floating garnish. Colors are illustrative, not ingredient/allergen claims.']

scene('miniature-clay-food',(3,7,6))
# An original opaque model-bento base, not a replica of the source hinged box.
box('model tray base',(-.004,.0015,0),(.064,.003,.048),'#9BB8AC')
frame('model tray rim',(-.004,.005,0),.064,.048,.0025,.007,'#799C90')
box('model divider',(.003,.005,0),(.0015,.008,.042),'#78996E')
# Rounded triangular rice models, made from polymer clay; solid extrusions with
# original seaweed-colored surface bands. No edible cooking or curing shown.
outline=[(-.010,0),(.010,0),(.011,.003),(.007,.009),(.002,.018),(-.002,.018),(-.009,.007),(-.011,.003)]
for j,z in enumerate([-.011,.010]):
 outline2=[(xx-.019,yy+.003) for xx,yy in outline];extrude('clay rice triangle '+str(j),outline2,z-.006,z+.006,'#EFE4CF')
 box('dark clay nori front '+str(j),(-.019,.007,z+.0061),(.008,.008,.0003),'#425F57')
 box('dark clay nori top fold '+str(j),(-.019,.0032,z),(.008,.0004,.012),'#425F57')
for j,z in enumerate([-.013,-.005]):
 box('clay egg roll '+str(j),(.014,.007,z),(.016,.008,.006),'#E7BA65')
 box('egg roll spiral cue '+str(j),(.015,.008,z+.0031),(.008,.0014,.00025),'#C98E51')
for j,(x,z) in enumerate([(.011,.010),(.024,.010),(.020,.019)]):
 ellipsoid('clay fried chicken '+str(j),(x,.008,z),(.0058,.005,.0055),'#A87552',n=12,rings=7)
 for dx,dz in [(-.002,0),(.002,.002)]:ellipsoid('clay crust '+str(j),(x+dx,.0115,z+dz),(.002,.0018,.002),'#C69765',n=8,rings=5)
ellipsoid('clay tomato',(.025,.007,-.016),(.0045,.004,.0045),'#BF7564',n=16,rings=7)
# Modeling tool rests outside the tray, on the same ground, clarifying craft.
rod('modeling tool handle',(-.028,.0028,.032),(.017,.0028,.032),.0028,'#B0839B',n=12)
rod('modeling tool tip',(.017,.0028,.032),(.029,.0028,.032),.0028,'#A5ADB0',n=12,r2=.0005)
sc.S['notes']=['Representative64x48mm model bento, no human hand. Primary photo and event text confirm miniature polymer-clay rice triangles, egg rolls, fried chicken and tomato.','All food forms are nonedible clay. Original opaque tray, arrangement and modeling tool differ from photographed clear hinged box; not promised event kit.','Rice/egg/chicken/tomato bases contact tray atY3mm. Rim and divider join base. Modeling-tool handle contacts ground atY0; pointed end has normal clearance.','Seaweed-colored bands are surface clay details. Simplified fried-food texture and egg marks soften at16px; label must specify clay craft, not food service.']

scene('wooden-buoy-decoration',(3,5,8))
# Representative carved buoy lies on its side, supported by the widest body
# section. A spindle passes axially through the body. No functional use claimed.
profile=[(0,-.046),(.007,-.046),(.018,-.035),(.022,-.012),(.022,.017),(.018,.030),(0,.034)]
lathe('carved wooden body',profile,'#D3AA80',n=12)
p=sc.S['parts'][-1];p['vertices']=[[y,.022+z,-x] for x,y,z in p['vertices']]
# Continuous spindle, extending farther from one end, as in the supplier object.
rod('wood spindle',(-.060,.022,0),(.066,.022,0),.0045,'#C39A75',n=12)
# Paint is a thin surface band on the body, preserving the same axial profile.
for name,lo,hi,col in [('rose painted band',-.026,-.010,'#B77D82'),('cream painted band',-.010,.006,'#EEE1C7')]:
 def rad(y):
  for (ra,ya),(rb,yb) in zip(profile[1:-1],profile[2:-1]):
   if ya<=y<=yb:return ra+(rb-ra)*(y-ya)/(yb-ya)
  return .022
 levels=[lo]+[y for r,y in profile if lo<y<hi]+[hi]
 lathe(name,[(rad(y)+.00005,y) for y in levels],col,n=12)
 p=sc.S['parts'][-1];p['vertices']=[[y,.022+z,-x] for x,y,z in p['vertices']]
# Brush lies independently on the ground beside the buoy, not hovering at paint.
rod('brush handle',(-.038,.0035,.041),(.022,.0035,.041),.0035,'#7D9F9C',n=12,r2=.0025)
box('brush ferrule',(.028,.0035,.041),(.014,.007,.008),'#A8B5B5')
box('brush bristles',(.042,.0035,.041),(.014,.007,.008),'#B77D82')
sc.S['notes']=['Original side-lying buoy body80mm long44mm wide with126mm axial spindle; illustrative proportions informed by supplier hand-carved pine buoy, not exact event material.','Carved12-sided body, continuous spindle and painted bands share geometry. Broad lower side supports body atY0; spindle has normal clearance. Brush ferrule/bristles shareY0 with lower handle contact.','Supplier photo shows tapered wooden body with long and short spindle ends. String hole is omitted rather than falsely painting a hole onto solid wood; no cord depicted or event specification promised.','Paint and brush distinguish decoration from lobster fishing or general buoy equipment. No claim of flotation, navigation safety or seaworthiness.']
ROOT.joinpath('scenes.json').write_text(json.dumps(SCENES,indent=2)+'\n')
