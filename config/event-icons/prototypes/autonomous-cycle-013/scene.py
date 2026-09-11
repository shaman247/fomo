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
# Two original object studies; no articulated human figures.
scene('furniture-making',(5,6,10))
# Four joined legs, apron frame, lower stretchers, and a wood seat. Metres.
for x in [-.14,.14]:
 for z in [-.12,.12]:box('stool leg',(x,.205,z),(.045,.41,.045),'#B38A63')
for z in [-.12,.12]:
 box('seat apron',(0,.376,z),(.28,.058,.025),'#B38A63')
 box('low rail',(0,.120,z),(.28,.025,.022),'#B38A63')
for x in [-.14,.14]:
 box('seat apron',(x,.376,0),(.025,.058,.24),'#B38A63')
 box('low rail',(x,.150,0),(.022,.025,.24),'#B38A63')
box('stool seat',(0,.4275,0),(.36,.035,.32),'#CAA172')
# Broad wood grain marks lie just above top, confined to the seat.
for x,z,w,d in [(-.055,-.06,.17,.003),(.035,.095,.19,.003),(-.030,.071,.23,.0025)]:box('seat grain',(x,.4453,z),(w,.0006,d),'#B78E64')
# A wooden mallet rests on the seat, its handle passes into its own head.
box('mallet head',(-.015,.4835,-.050),(.17,.077,.065),'#8BA6A0')
rod('mallet handle',(-.015,.4835,-.064),(-.015,.4835,.130),.012,'#D5B181',16)
# Chisel beside the stool, not in contact with hands. One complete connected tool.
# It lies diagonally in the scene and is not an assembly instruction.
a=np.array([.195,.012,.195]);v=np.array([.52,0,-.85]);v/=np.linalg.norm(v)
rod('chisel handle',a,a+v*.115,.014,'#9CAAAA',16)
rod('chisel ferrule',a+v*.108,a+v*.130,.0145,'#657D88',16)
# Flat metal blade has a bevel at its far tip. Tool local x spans blade width.
u=np.array([-v[2],0,v[0]])
pts=[]
for dist,half,height in [(.128,.007,.008),(.230,.013,.008),(.246,.013,.001)]:
 c=a+v*dist
 for xx,yy in [(-half,-height),(half,-height),(half,height),(-half,height)]:pts.append(c+u*xx+np.array([0,yy,0]))
mesh('chisel blade',pts,[[0,3,2,1],[8,9,10,11]]+[[j*4+i,j*4+(i+1)%4,(j+1)*4+(i+1)%4,(j+1)*4+i] for j in range(2) for i in range(4)],'#91A8B1')
S['notes']=['Four equal stool legs terminate at a common ground plane; all apron rails and lower stretchers overlap the supporting legs. Seat bottom .410 equals leg top .410. Mallet head bottom .445 equals seat top .445; handle is embedded in the mallet head. Separate chisel ferrule overlaps handle and blade, and the metal tip has a flat bevel. Stool and tools are representative furniture work, not a specific historical replica or event project.']
scene('museum-object-handling',(4,6,12))
# Simple museum teaching tray and a generic camera-shaped handling object.
box('tray base',(0,.010,0),(.46,.020,.27),'#B4B9A6')
frame('tray rim',(0,.031,0),.46,.27,.012,.028,'#9DAA99')
box('soft mat',(0,.021,0),(.425,.004,.235),'#CAD0BD')
# Camera and separate small material sample rest on the mat.
box('camera body',(-.075,.081,-.008),(.195,.116,.070),'#899EA6')
box('camera top',(-.075,.141,-.015),(.19,.013,.060),'#B6C0BD')
rod('camera lens',(-.075,.084,.027),(-.075,.084,.070),.039,'#607E8C',32)
rod('lens rim',(-.075,.084,.068),(-.075,.084,.078),.041,'#91ACB1',32)
rod('lens glass',(-.075,.084,.078),(-.075,.084,.080),.031,'#577A8C',32)
box('viewfinder',(-.126,.118,.028),(.026,.018,.002),'#546F7A')
rod('shutter button',(-.135,.1475,-.015),(-.135,.156,-.015),.010,'#778F98',16)
box('material sample',(.101,.033,-.035),(.088,.020,.10),'#CBA779')
# Three broad shallow material grooves, planar and attached.
for z in [-.066,-.041,-.016]:box('sample groove',(.101,.0435,z),(.065,.001,.005),'#B38E67')
# Upright handling sign supported by tray rear. Printed five-digit hand symbol.
box('sign foot',(.130,.024,-.09),(.13,.015,.030),'#72978E')
box('sign panel',(.130,.149,-.102),(.130,.25,.008),'#72978E')
# Palm silhouette drawn in local sign coordinates; it is a flat handprint pictogram.
# Thumb is separated from four upper fingers, with distinct heights and gaps.
outline=[(-.021,-.045),(-.032,-.025),(-.048,-.006),(-.046,.004),(-.038,.005),(-.024,-.008),(-.024,.048),(-.020,.055),(-.013,.055),(-.009,.048),(-.009,.006),(-.004,.006),(-.004,.069),(0,.075),(.007,.075),(.011,.069),(.011,.006),(.016,.006),(.016,.061),(.021,.067),(.027,.066),(.031,.060),(.031,.001),(.036,.001),(.036,.038),(.041,.044),(.047,.043),(.051,.037),(.051,-.023),(.040,-.047),(.023,-.061),(-.008,-.061)]
panel('handprint',[[.124+x,.160+y,-.0975] for x,y in outline],'#F1E5C8')
S['notes']=['Tray base, joined rim and thin mat support a generic camera and a separate textured material sample. Camera body bottom .023 meets mat top .023; lens cylinders share one axis and are attached to body front. Viewfinder and shutter remain on camera surfaces. Sign foot joins the rear tray; five-digit handprint is a planar sign glyph, not an articulated hand touching the collection. Selected objects are representative, and the icon does not grant permission to handle other museum objects.']
if __name__=='__main__':(ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
