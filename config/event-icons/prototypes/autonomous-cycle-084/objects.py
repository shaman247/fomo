import numpy as np,math,json
from pathlib import Path
import scene as m
from scene import *
scene('farfalle',(1,8,5))
def bow(name,c,angle):
 nu,nv=17,25;v=[]
 for offset in [0,-.0012]:
  for i,u in enumerate(np.linspace(-1,1,nu)):
   for j,w in enumerate(np.linspace(-1,1,nv)):
    # Serrated short ends and an unbroken pinched, pleated centre.
    serr=.0009*math.cos(6*math.pi*w)*abs(u)**8
    x=.025*u+np.sign(u)*serr
    z=.018*w*(.10+.90*abs(u)**.72)
    y=.005+.0055*(1-abs(u)**.8)*(1+math.cos(2*math.pi*w))+.0015*w*w+offset
    a=math.radians(angle);v.append([c[0]+x*math.cos(a)-z*math.sin(a),c[1]+y,c[2]+x*math.sin(a)+z*math.cos(a)])
 count=nu*nv;faces=[]
 for i in range(nu-1):
  for j in range(nv-1):
   a=i*nv+j;bb=a+nv
   faces += [[a,a+1,bb+1],[a,bb+1,bb],[a+count,bb+count+1,a+count+1],[a+count,bb+count,bb+count+1]]
 perimeter=list(range(nv))+[i*nv+nv-1 for i in range(1,nu)]+[nu*nv-1-j for j in range(1,nv)]+[i*nv for i in range(nu-2,0,-1)]
 for a,bb in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append([a,a+count,bb+count,bb])
 mesh(name,v,faces,'#E6B563')
bow('first folded pasta',(-.010,0,-.023),-18);bow('second folded pasta',(.010,0,.022),20)
m.S['notes']=['Two separate approximately 5 cm long farfalle formed from continuous thickened rectangular sheets, with fluted ends and a pinched pleated centre.','Both lobes remain joined across the pinch. No artificial tie band, filling or separate glued bow wings. Surface is an illustrative approximation of hand shaping.','Organizer photograph and Sur La Table chef instructions inspected for construction; no image traced.']
scene('pizza-al-padellino',(3,5,7))
lathe('round baking pan',[(0,0),(.106,0),(.111,.003),(.113,.041),(.109,.041),(.106,.006),(0,.006),(0,0)],'#51616B',48)
lathe('pizza dough',[(0,.006),(.102,.006),(.104,.012),(.103,.024),(.097,.029),(.090,.027),(.085,.021),(0,.021),(0,.006)],'#DFB06A',48)
rod('tomato surface',(0,.021,0),(0,.0225,0),.088,'#DA6950',48)
for x,z,rx,rz in [(-.036,-.047,.018,.013),(.036,-.026,.018,.015),(-.048,.019,.019,.014),(.005,.038,.022,.014),(.057,.037,.015,.012),(.001,-.009,.017,.011)]:
 ellipsoid('mozzarella piece',(x,.024,z),(rx,.003,rz),'#F4E6C5',20,7)
for x,z,a in [(-.010,-.051,-25),(.048,.003,20),(-.031,.052,40)]:
 pts=[]
 for u,w in [(-1,0),(-.55,-.55),(0,-.8),(.7,-.45),(1,0),(.7,.45),(0,.8),(-.55,.55)]:
  aa=math.radians(a);xx=u*.018;zz=w*.010;pts.append((x+xx*math.cos(aa)-zz*math.sin(aa),.028,z+xx*math.sin(aa)+zz*math.cos(aa)))
 mesh('basil leaf',pts,[list(reversed(range(8)))],'#60966C');m.S['parts'][-1]['double_sided']=True
# Curved cheese surfaces triangulated for reliable depth projection.
for p in m.S['parts']:
 if p['name']=='mozzarella piece':p['faces']=[t for f in p['faces'] for t in ([f[:3],[f[0],f[2],f[3]]] if len(f)==4 else [f])]
m.S['notes']=['Small round pan approximately 22.6 cm diameter and 4.1 cm high; scale is illustrative, not specified Eataly hardware.','Pizza rests on pan base within continuous side wall. Dough rim, tomato layer, cheese and herb leaves are supported and contained.','Tomato, mozzarella and basil follow organizer reference photograph; icon does not guarantee a particular menu topping or recipe. No handle added to the handleless baking tin.']
if __name__=='__main__':Path(__file__).with_name('scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
