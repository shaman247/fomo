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

def oval(name,c,r,sc,col,flat=False):
 ball(name,c,r,col);p=S['parts'][-1];p['vertices']=(np.array(c)+(np.array(p['vertices'])-c)*sc).tolist();p['flat_paint']=flat

# Generic harp structure: column, curved neck, angled soundbox and attached strings.
# Salvi Daphne47SE informs connectivity, not a claim of exact event instrument.
scene('harp',(2.3,1.4,10))
# Soundbox widens towards its foot and has a tapered depth.
outline=[(-.31,.10),(-.10,.10),(.64,1.29),(.59,1.39)]
extrude('tapered soundbox',outline,-.13,.07,wood)
# Cream sounding board is the forward face; strings attach along its left edge.
panel('soundboard',[[-.31,.10,.074],[-.10,.10,.074],[.64,1.29,.074],[.59,1.39,.074]],'#EBC98E')
rod('column',(-.39,.11,0),(-.43,1.75,0),.052,darkwood,n=20,r2=.064)
# Neck follows a gently concave falling curve then rising shoulder.
neck=[(-.45,1.73),(-.32,1.74),(-.21,1.70),(-.11,1.63),(-.01,1.49),(.09,1.29),(.18,1.16),(.27,1.12),(.36,1.14),(.47,1.24),(.57,1.32),(.64,1.33),(.69,1.30),(.67,1.43),(.61,1.48),(.52,1.46),(.42,1.37),(.32,1.28),(.26,1.27),(.20,1.34),(.10,1.55),(.01,1.70),(-.12,1.80),(-.28,1.86),(-.44,1.85)]
extrude('curved neck',neck,-.065,.065,wood)
# Original plank-shaped base; broad feet ensure a supported instrument.
flat_extrude('base',[(x-.24,z) for x,z in rounded_outline(.58,.34,.08)],.035,.125,darkwood)
for x in [-.43,-.07]:
 for z in [-.12,.12]:box('foot',(x,.018,z),(.085,.036,.08),dark)
# 17 representative strings, fewer than a playable full-size harp.
xs=[-.29+i*.05 for i in range(17)]
curve=neck[:13]
for i,x in enumerate(xs):
 top=float(np.interp(x,[v[0] for v in curve],[v[1] for v in curve]))+.035
 bottom=.10+(x+.31)/.9*1.29-.02
 # Longest strings terminate in low sounding-board edge; column is separate.
 bottom=max(.105,bottom)
 rod('string '+str(i),(x,top,.079),(x,bottom,.079),.0033,['#B39169','#C57664','#698995'][i%3],n=6);S['parts'][-1]['flat_paint']=True
S['measurements']=dict(height=1.86,base_width=.58,base_depth=.34,column_height=1.64,representative_strings=17,string_radius=.0033)
S['notes']=['Connected column, broad base, curved neck and tapered angled sounding box.17representative strings are intentionally fewer than a playable concert harp. No pedal mechanism, string count, tuning or exact model is promised. String endpoints follow the neck and sounding-board line; no player is present.']

# Open caviar tin: continuous shallow metal wall and inner floor, roe surface,
# mother-of-pearl-like spoon with actual concave bowl resting separately on plane.
scene('caviar',(2.4,5.7,8))
ring_y('tin wall',(0,.005,0),.055,.051,.029,'#B9985A',n=48)
rod('tin floor',(0,.005,0),(0,.009,0),.051,dark,n=48)
ring_y('upper rim',(0,.032,0),.056,.0505,.003,'#E3C587',n=48)
rod('roe aggregate',(0,.009,0),(0,.030,0),.050,'#343D3C',n=40)
# Selected broad beads are a texture abbreviation, not to-scale egg count.
for j,z in enumerate([-.035,-.0175,0,.0175,.035]):
 for i,x in enumerate([-.035,-.0175,0,.0175,.035]):
  xx=x+(.006 if j%2 else 0)
  if xx*xx+z*z<.043**2:
   n=12;rings=5;r=.0038;c=np.array([xx,.030,z]);v=[c+np.array([r*math.cos(t)*math.cos(a),r*math.sin(t),r*math.cos(t)*math.sin(a)]) for t in np.linspace(-math.pi/2,math.pi/2,rings) for a in np.linspace(0,2*math.pi,n,endpoint=False)]
   mesh('roe bead',v,[[k*n+h,(k+1)*n+h,(k+1)*n+(h+1)%n,k*n+(h+1)%n] for k in range(rings-1) for h in range(n)],'#60665B');S['parts'][-1]['flat_paint']=True
# Spoon lies beside tin on the same support plane, diagonal within world XZ.
# Elliptical bowl with joined concave inner/outer surfaces, 1mm thickness.
cx,cz=.087,-.011;n=28;verts=[]
for rx,rz,yy in [(0,0,.001),(.009,.014,.004),(.013,.019,.009),(.012,.018,.010),(.008,.013,.005),(0,0,.002)]:
 verts.extend([[cx+rx*math.cos(t),yy,cz+rz*math.sin(t)] for t in np.linspace(0,2*math.pi,n,endpoint=False)])
faces=[[k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i] for k in range(5) for i in range(n)]
mesh('concave spoon bowl',verts,faces,'#E5E4D4')
flat_extrude('spoon handle',[(cx+x,cz+z+.042) for x,z in rounded_outline(.009,.057,.004,n=6)],.004,.007,'#D3DACD')
S['measurements']=dict(tin_diameter=.11,tin_height=.035,wall_thickness=.004,spoon_bowl_length=.038,spoon_bowl_width=.026,spoon_handle_length=.057,spoon_bowl_shell=.001,representative_bead_radius=.0038)
S['notes']=['Generic shallow open tin uses primary product silhouette without copying brand or label. Roe shown with enlarged sparse texture for icon clarity; not actual egg size/species. Concave spoon bowl and handle form a connected utensil beside the tin on the same implied surface. No meal ingredients, exact utensil or serving quantity promised.']
if __name__=='__main__':
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,separators=(',',':'))+'\n')
 (Path('.scratch/icon-cycles-20260909/cycle-033')/'geometry-measurements.json').write_text(json.dumps({k:v.get('measurements',{}) for k,v in SCENES.items()},indent=2)+'\n')
