import math,json
from pathlib import Path
import scene as m
from scene import *

scene('cyberdeck',(4,5,8))
box('portable case',(0,.014,.010),(.150,.028,.095),'#728D99')
box('top plate',(0,.029,.010),(.144,.003,.091),'#ADC2B6')
# Supported display assembly: two stanchions rise from the base to the screen.
for x in [-.050,.050]:box('screen support',(x,.036,-.031),(.011,.017,.012),'#536C7A')
box('display housing',(0,.080,-.031),(.130,.080,.012),'#526B7B')
box('color display',(0,.080,-.0245),(.111,.062,.001),'#263F4E')
for x,y,w in [(-.030,.097,.037),(-.011,.082,.075),(-.020,.067,.057)]:box('symbolic terminal bar',(x,y,-.0237),(w,.006,.001),'#80C6B1')
for row,z in enumerate([.011,.027,.043]):
 for col,x in enumerate([-.058,-.042,-.026,-.010]):box('key',(x,.033,z),(.012,.005,.011),'#F0DEB8')
box('exposed maker board',(.041,.033,.026),(.040,.004,.038),'#4E967E')
box('processor',(.039,.037,.025),(.015,.004,.015),'#4D6170')
for z in [.014,.025,.036]:box('connector',(.059,.037,z),(.006,.004,.005),'#E0B46C')
box('side port',(-.0754,.016,.020),(.001,.009,.018),'#3F5662')
m.S['notes']=['Original generic portable DIY computer, approximately 15 cm wide. Connected base, two display supports, screen housing, keyboard and exposed maker board.','Reference shows computer keyboard with physically plugged display; this layout is illustrative, not a copy of the workshop kit, a wiring diagram or a specified Raspberry Pi model.','Abstract screen bars are not executable code. Internal wiring is intentionally omitted; no electronics certification is claimed.']

scene('studio-lighting',(6,3,7))
zcenter=-.10
# Three grounded feet, spaced equally about the central column and braced.
for angle in [90,210,330]:
 a=math.radians(angle);foot=(.43*math.cos(a),.030,zcenter+.43*math.sin(a));joint=(foot[0]*.62,.19,zcenter+(foot[2]-zcenter)*.62)
 rod('stand leg',(0,.34,zcenter),foot,.023,'#627A89',12)
 rod('leg brace',(0,.11,zcenter),joint,.012,'#7F939B',10)
 rod('rubber foot',(foot[0],0,foot[2]),(foot[0],.050,foot[2]),.028,'#526A79',12)
rod('lower stand',(0,.16,zcenter),(0,.60,zcenter),.027,'#607986',16)
rod('upper stand',(0,.57,zcenter),(0,.87,zcenter),.021,'#8AA0A8',16)
rod('height collar',(0,.54,zcenter),(0,.61,zcenter),.036,'#496574',16)
box('tilt yoke bottom',(0,.87,zcenter),(.20,.03,.035),'#657E8B')
for x in [-.09,.09]:box('tilt yoke side',(x,.96,zcenter),(.025,.19,.035),'#657E8B')
rod('lamp housing',(0,1.05,-.22),(0,1.05,0),.075,'#607784',20)
for x in [-.098,.098]:rod('tilt pivot',(x-.030,1.05,zcenter),(x+.030,1.05,zcenter),.035,'#DCB36B',16)
# Sixteen-sided fabric shell, continuous from rear mounting ring to front diffuser.
n=16;v=[]
for z,r in [(0,.078),(.10,.19),(.327,.29)]:
 for i in range(n):a=2*math.pi*i/n;v.append([r*math.cos(a),1.05+r*math.sin(a),z])
faces=[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(2) for i in range(n)]
mesh('softbox shell',v,[list(reversed(f)) for f in faces],'#5E7785')
rod('front edge',(0,1.05,.323),(0,1.05,.334),.29,'#8499A3',16)
rod('diffusion surface',(0,1.05,.335),(0,1.05,.337),.264,'#F0E4C9',16)
m.S['notes']=['Generic studio light with modifier approximately 58 cm diameter and 32.7 cm depth, informed by manufacturer dimensions. It is not a promise of equipment supplied at the event.','Light connects to a tilt yoke and telescoping stand. Three braced feet contact the same ground plane; column and light remain within the footprint.','Approximate total height 1.34 m, three foot radii 43 cm. No operator, dangling cords, collision-free setup guarantee or load certification.']
if __name__=='__main__':Path(__file__).with_name('scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
