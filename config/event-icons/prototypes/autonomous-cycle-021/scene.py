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

scene('monopoly',(3,7,10))
# Original property-game components. No copied board, property names or logo.
box('property card',(-.013,.0006,-.010),(.064,.0012,.088),'#E9DFC8')
box('color band',(-.013,.00125,-.042),(.053,.0001,.017),'#7F98AD')
for z,w in [(-.025,.032),(-.019,.040),(-.013,.027)]:box('deed line',(-.013,.0013,z),(w,.0001,.0015),'#A39782')
def building(name,x,z,w,d,h,col):
 extrude(name,[(-w/2,0),(w/2,0),(w/2,h*.66),(0,h),(-w/2,h*.66)],-d/2,d/2,col)
 p=S['parts'][-1];p['vertices']=[[xx+x,yy+.0014,zz+z] for xx,yy,zz in p['vertices']]
building('green house',-.031,.012,.022,.020,.024,'#56A47C')
building('red hotel',.002,.012,.030,.022,.028,'#CC6966')
box('die',(.037,.011,.037),(.022,.022,.022),'#EFEAE0')
# Six physical pip faces, opposite totals seven; coordinate-local face markers.
pipsets={1:[(0,0)],2:[(-1,-1),(1,1)],3:[(-1,-1),(0,0),(1,1)],4:[(-1,-1),(-1,1),(1,-1),(1,1)],5:[(-1,-1),(-1,1),(0,0),(1,-1),(1,1)],6:[(-1,-1),(-1,0),(-1,1),(1,-1),(1,0),(1,1)]}
for axis,sign,count in [('z',1,3),('z',-1,4),('x',1,1),('x',-1,6),('y',1,5),('y',-1,2)]:
 for u,v in pipsets[count]:
  center=np.array([.037,.011,.037]);k={'x':0,'y':1,'z':2}[axis];others=[i for i in range(3) if i!=k];center[k]+=sign*.01105;center[others[0]]+=u*.0055;center[others[1]]+=v*.0055;end=center.copy();end[k]+=sign*.00012
  rod('die pip',center,end,.00165,'#586571',16)
S['measurements']=dict(card_m=[.064,.088],house_m=[.022,.020,.024],hotel_m=[.030,.022,.028],die_edge_m=.022)
S['notes']=['Original generic green house, red hotel, property card and six-sided die represent Monopoly play. Building bases touch the card; die rests on the same external support plane. Opposite die faces sum to seven. No complete board, trademark lettering, exact edition proportions or supplied component promise.']

scene('studio-recording',(3,3,12))
# 295mm original desktop microphone, side-pivot yoke and stable round foot.
lathe('weighted foot',[(0,.013),(.057,.013),(.062,.009),(.062,0),(0,0)],'#637D89')
rod('stand stem',(0,.009,0),(0,.050,0),.012,'#697F8A',24)
box('yoke bottom',(0,.051,0),(.103,.012,.014),'#4D6675')
for x in [-.049,.049]:
 box('yoke upright',(x,.104,0),(.012,.107,.014),'#4D6675')
 rod('side pivot',(x-.010,.146,0),(x+.010,.146,0),.010,'#A3B1B3',24)
lathe('microphone body',[(0,.212),(.036,.212),(.036,.090),(.029,.082),(0,.082)],'#81A4AC')
lathe('rounded grille',[(0,.295),(.018,.292),(.031,.279),(.036,.258),(.036,.209),(0,.209)],'#B5C6CB')
for yy,rr in [(.223,.0362),(.239,.0362),(.255,.0362),(.270,.0338)]:ring_y('grille stripe',(0,yy,0),rr,rr-.0012,.003,'#819AA4',40)
rod('gain control',(0,.148,.034),(0,.148,.044),.009,'#446674',24)
S['measurements']=dict(overall_height_m=.295,foot_diameter_m=.124,body_diameter_m=.072,pivot_height_m=.146)
S['notes']=['Original microphone assembly follows the broad capsule, side-pivot yoke and circular supported foot visible in the Logitech Yeti product photograph. It is not an exact Yeti model or an assertion about the library equipment. The lower body clears the yoke bottom by25mm. Recording dot and waveform in the icon are flat semantic overlays, not floating physical parts.']

scene('party-cruise',(7,5,13))
# Generic 30m passenger vessel; waterline cross-section only, no engineering claim.
outline=[(-15,-3.6),(-15,3.6),(9,3.6),(13,2.2),(15,0),(13,-2.2),(9,-3.6)]
# Reverse clockwise XZ outline so flat_extrude receives CCW input.
outline=list(reversed(outline))
flat_extrude('blue hull',outline,-.7,1.5,'#557D98')
flat_extrude('main deck',[(x*1.015,z*1.015) for x,z in outline],1.5,1.8,'#DADBCF')
box('passenger cabin',(-1,3.0,0),(24,2.4,5.9),'#E6E7DB')
box('upper deck roof',(-1,4.32,0),(24.8,.24,6.45),'#C9D5D3')
for z in [-2.96,2.96]:
 for x in [-11,-7,-3,1,5,9]:box('cabin window',(x,3.15,z),(2.6,1.15,.035),'#537789')
box('pilothouse',(8,5.6,0),(4.8,2.3,4.6),'#E6E7DB')
box('pilothouse roof',(8,6.87,0),(5.25,.24,4.95),'#C57864')
for z in [-2.32,2.32]:box('bridge side window',(8,5.94,z),(3.6,1.05,.035),'#537789')
for z in [-1.2,1.2]:box('bridge forward window',(10.42,5.94,z),(.035,1.05,1.6),'#537789')
for z in [-3.12,3.12]:
 rod('upper side rail',(-13.1,5.48,z),(5.2,5.48,z),.095,'#7D979C',10)
 for x in [-13,-9.4,-5.8,-2.2,1.4,5]:rod('rail post',(x,4.44,z),(x,5.48,z),.085,'#7D979C',10)
rod('aft rail',(-13.1,5.48,-3.12),(-13.1,5.48,3.12),.095,'#7D979C',10)
for z in [-1.55,0,1.55]:rod('aft rail post',(-13.1,4.44,z),(-13.1,5.48,z),.085,'#7D979C',10)
S['measurements']=dict(length_m=30,beam_m=7.2,main_deck_m=1.8,upper_deck_m=4.44,roof_m=6.99,rail_height_m=1.04)
S['notes']=['Original generic two-level passenger vessel uses joined hull/deck/cabin geometry and a forward pilothouse with open upper passenger area. Circle Line Manhattan-class photograph is a construction reference only, not the event vessel. Window panels lie on cabin surfaces; rail posts terminate at the upper deck. Underwater hull is deliberately schematic and no stability, capacity, access or exact deck-count promise is made. Musical notes and waves are flat semantic overlays.']

if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-021')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
