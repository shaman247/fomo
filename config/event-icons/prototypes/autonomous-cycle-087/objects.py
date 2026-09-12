import math,json
from pathlib import Path
import scene as m
from scene import *
scene('typewriter',(3,4,8))
# Generic portable scale informed by Smithsonian collection dimensions.
# A tapered chassis supports keys, ribbon cover and transverse carriage.
v=[[-.145,.012,-.11],[.145,.012,-.11],[.145,.012,.145],[-.145,.012,.145],[-.13,.085,-.11],[.13,.085,-.11],[.13,.042,.145],[-.13,.042,.145]]
mesh('tapered body',v,[[1,2,3,0],[7,6,5,4],[4,5,1,0],[2,6,7,3],[3,7,4,0],[5,6,2,1]],'#83A9A1')
for x in [-.11,.11]:
 for z in [-.08,.11]:rod('rubber foot',(x,0,z),(x,.018,z),.014,'#526E7A',16)
box('ribbon cover',(0,.091,-.025),(.255,.038,.080),'#69978E')
# Three key banks follow the inclined deck; simplified count is deliberate.
for row,z in enumerate([.035,.067,.099]):
 y=.085-(z+.11)*(.043/.255)
 for col in range(8):
  x=(col-3.5)*.028+(row%2)*.007
  rod('key stem',(x,y,z),(x,y+.015,z),.004,'#78929A',10)
  rod('round key',(x,y+.014,z),(x,y+.020,z),.011,'#E7D3AE',12);m.S['parts'][-1]['flat_paint']=True
box('spacebar',(0,.058,.128),(.168,.012,.016),'#E0C49A')
for x in [-.118,.118]:box('carriage support',(x,.102,-.081),(.025,.047,.034),'#6D858E')
rod('platen',(-.131,.129,-.082),(.131,.129,-.082),.015,'#506B78',24)
rod('platen axle',(-.156,.129,-.082),(.156,.129,-.082),.005,'#91A7AA',16)
for x in [-.157,.157]:rod('platen knob',(x-.008,.129,-.082),(x+.008,.129,-.082),.019,'#587880',20)
# Paper contacts the back of the roller then exits vertically; top edge unobstructed.
box('paper support',(0,.145,-.101),(.225,.067,.008),'#71938E')
box('paper',(0,.189,-.097),(.204,.198,.001),'#F0DDB8')
rod('paper bail',(-.105,.136,-.063),(.105,.136,-.063),.003,'#AAC0B7',12)
for x in [-.07,.07]:rod('paper bail roller',(x-.010,.136,-.063),(x+.010,.136,-.063),.006,'#5C7682',12)
# Return lever connected to carriage at the left.
tube('return lever',[(-.145,.128,-.087),(-.170,.145,-.087),(-.170,.145,-.025),(-.120,.145,-.025)],.004,'#B0C0B5',10)
for y,w in [(.26,.126),(.242,.147),(.224,.09)]:box('typed line',(-.015,y,-.0962),(w,.004,.0005),'#AF9D7B')
m.S['notes']=['Original generic portable typewriter, approximately 33 cm across knobs, 27 cm deep, 15 cm high without paper. Smithsonian Corona example measures 30.48 by 26.67 by 12.7 cm and has three keyboard rows; this is not a model replica.','Sloped case supports three key banks and spacebar. Carriage supports a transverse platen with axle, two knobs, connected return lever and paper bail. Paper meets the roller and rises behind it. Hidden typebars and internal linkages are intentionally omitted.','Four feet share ground plane. Key count is simplified, no letter layout or brand is claimed. Geometry inspection is not a working mechanical simulation.']
if __name__=='__main__':Path(__file__).with_name('scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
