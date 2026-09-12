import numpy as np, math
import scene as m
from scene import *
scene('cotton-spinning',(1.5,1.8,9))
m.S['camera_roll']=-32
# An isolated equipment display, not an unsupported in-use pose.
rod('pointed metal tip',(0,0,0),(0,.019,0),.00015,'#647D88',16,r2=.0018)
rod('metal shaft',(0,.019,0),(0,.208,0),.0018,'#8DA4AD',16)
rod('brass whorl',(0,.035,0),(0,.038,0),.013,'#DDB45F',40)
rod('whorl centre collar',(0,.032,0),(0,.041,0),.003,'#B5904E',20)
# Yarn cop sits around the shaft immediately above the whorl.
lathe('wound cotton yarn',[(0,.042),(.005,.042),(.009,.051),(.010,.068),(.009,.087),(.006,.103),(.002,.110),(0,.110)],'#EEE8D7',32)
tube('top hook',[(0,.208,0),(.001,.214,0),(.005,.218,0),(.009,.216,0),(.009,.210,0)],.0018,'#647D88',12)
# Visible windings stay on the cop surface; no loose line falsely suspends it.
for y,r in [(.054,.0094),(.067,.0101),(.080,.0095),(.094,.0078)]:
 pts=[(r*math.cos(t),y+.003*t/(2*math.pi),r*math.sin(t)) for t in np.linspace(0,2*math.pi,33)]
 tube('cotton winding',pts,.0008,'#C9BFA9',6)
# Separate prepared cotton sliver, illustrated as a soft folded bundle.
ellipsoid('cotton sliver centre',(-.045,.134,-.005),(.019,.040,.010),'#EEE8D7',24,9)
ellipsoid('cotton sliver fold',(-.060,.145,-.004),(.014,.029,.009),'#F7F1E2',24,9)
ellipsoid('cotton sliver taper',(-.032,.109,-.004),(.009,.022,.008),'#EEE8D7',20,9)
# Triangulate curved quads to avoid non-planar face projection artifacts.
for p in m.S['parts']:
 if p['name'].startswith('cotton sliver'):
  p['faces']=[tri for f in p['faces'] for tri in ([f[:3],[f[0],f[2],f[3]]] if len(f)==4 else [f])]
m.S['notes']=['Isolated tahkli equipment display with prepared cotton sliver; not an in-use posture, dropped spindle or suspended yarn.','Approximately 21.8 cm shaft length and 2.6 cm brass whorl diameter, based on instructor dimensions and photographed construction. Shaft thickness slightly amplified for icon readability.','Point, low whorl, centred yarn cop and connected top hook. No bowl or operator; orientation is an illustrative product display.']
if __name__=='__main__':
 import json
 from pathlib import Path
 Path(__file__).with_name('scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
