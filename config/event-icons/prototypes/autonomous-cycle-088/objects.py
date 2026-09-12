"""Original soft market-bag volume with symbolic surface weave. Metres.
Envelope geometry is authoritative; paint patches abbreviate yarn crossings,
not a simulation of individual yarn topology. No source pattern is traced.
"""
from scene import *
scene('woven-bag',(3,3.5,8))
S=SCENES['woven-bag']
# Rounded rectangular cross-section: 28 cm wide, 8 cm deep, 22 cm tall.
outline=[]
for cx,cz,a in [(.11,.01,0),(-.11,.01,90),(-.11,-.01,180),(.11,-.01,270)]:
 for theta in np.linspace(a,a+90,7,endpoint=False):
  t=math.radians(theta);outline.append((cx+.03*math.cos(t),cz+.03*math.sin(t)))
# Reorder via polar angle to preserve outward winding.
outline=sorted(outline,key=lambda p:math.atan2(p[1],p[0]))
outer=Polygon(outline);inner=outer.buffer(-.006,join_style=1)
pierced_prism('continuous soft woven walls',outer.difference(inner),.014,.224,'#CC8868')
pierced_prism('closed cloth base',outer,.006,.014,'#AD765D')
# Flat paint surface diagram of a tight weave, anchored on front/back fabric.
# No loose rods or floating stitches; at small sizes the checks become texture.
for side in [-1,1]:
 z=side*.0401
 for row in range(7):
  y=.027+row*.026
  for col in range(8):
   x=-.103+col*.029
   if (row+col)%2==0:
    panel('cream overpass paint',[(x-.014,y-.012,z),(x+.014,y-.012,z),(x+.014,y+.012,z),(x-.014,y+.012,z)],'#F1D9AD')
    S['parts'][-1]['double_sided']=True;S['parts'][-1]['flat_paint']=True
# A broad cloth rim joins the shell. Hollow opening remains visible from above.
pierced_prism('bound open rim',outer.buffer(.001).difference(inner.buffer(-.001)),.220,.233,'#E5B97C')
# Long flat shoulder strap, attached at opposing side corners. Continuous band
# arches in XY; thickness in Z. Ends extend into reinforced top attachment tabs.
pts=[]
for t in np.linspace(math.pi,0,25):pts.append((.112*math.cos(t),.222+.125*math.sin(t)))
verts=[]
for i,(x,y) in enumerate(pts):
 tangent=np.array(pts[min(i+1,len(pts)-1)])-np.array(pts[max(i-1,0)]);tangent/=np.linalg.norm(tangent);normal=np.array([-tangent[1],tangent[0]])*.009
 for sign,z in [(-1,-.003),(1,-.003),(1,.003),(-1,.003)]:verts.append([x+sign*normal[0],y+sign*normal[1],z])
faces=[]
for i in range(len(pts)-1):
 for j in range(4):faces.append([i*4+j,i*4+(j+1)%4,(i+1)*4+(j+1)%4,(i+1)*4+j])
faces += [[3,2,1,0],list(range((len(pts)-1)*4,len(pts)*4))]
mesh('continuous shoulder strap',verts,faces,'#71999B');S['parts'][-1]['double_sided']=True
for x in [-.112,.112]:box('strap attachment tab',(x,.216,0),(.017,.033,.012),'#71999B')
S['notes']=['28 × 8 × 22 cm illustrative soft bag body, 12.5 cm strap rise. Exact workshop dimensions not promised.','Original rounded envelope with hollow top, cloth base and bound rim. Tight weave abbreviated by anchored color patches; individual yarn paths and load-bearing behavior not simulated.','Two instructor/organizer photographs inspected: chunky checks, open top and shoulder straps inform construction, without tracing their pattern or motif.']
(ROOT/'scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
