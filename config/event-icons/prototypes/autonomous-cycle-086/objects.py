import math,json
from pathlib import Path
import scene as m
from scene import *
scene('paper-squishy',(2,2,9))
# Two gently inflated paper faces join at a flat perimeter, 10 cm wide, 2.4 cm thick.
n=40;v=[]
for r,z in [(0,-.012),(.5,-.010),(1,0),(.5,.010),(0,.012)]:
 for i in range(n):
  a=i*2*math.pi/n;v.append([.05*r*math.cos(a),.055+.05*r*math.sin(a),z])
f=[[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(4) for i in range(n)]
mesh('stuffed paper envelope',v,f,'#E1B568');m.S['parts'][-1]['flat_paint']=True
# Eyes and smile lie on the actual curved front face, no disconnected face components.
for x in [-.014,.014]:rod('drawn eye',(x,.062,.011),(x,.062,.012),.0032,'#5E7681',16)
pts=[(.016*math.cos(t),.047+.008*math.sin(t),.012) for t in np.linspace(math.pi,2*math.pi,13)]
tube('drawn smile',pts,.0018,'#5E7681',8)
# Clear tape perimeter is a narrow paint cue, not a second solid toy.
torus_z('taped perimeter',(0,.055,0),.05,.0011,'#EED6A2',40,6)
m.S['notes']=['Original round smile motif on two paper faces joined at the perimeter and stuffed. Ten centimetres across and 2.4 cm deep are illustrative, not a required class pattern.','Face marks follow the front surface approximately; tape seam joins front and rear. No copyrighted character is reproduced. A paper-sheet corner in the final icon identifies the material.']
scene('lip-balm-making',(3,3,9));m.S['camera_roll']=40
# Nominal 12.7 mm tube diameter and 66 mm closed height from supplier.
rod('twist base',(0,0,0),(0,.007,0),.00635,'#577E86',32)
rod('tube body',(0,.007,0),(0,.048,0),.00635,'#86B2A0',32)
rod('collar',(0,.047,0),(0,.051,0),.0065,'#659A8D',32)
rod('balm stick',(0,.049,0),(0,.059,0),.00515,'#E9C98C',32)
rod('flat balm tip',(0,.059,0),(0,.0596,0),.00515,'#F5DBA6',32)
# Hollow cap stands beside the tube with its closed end on the ground.
lathe('detached hollow cap',[(0,0),(.0069,0),(.0069,.022),(.0059,.022),(.0059,.002),(0,.002)],'#7DA399',32)
p=m.S['parts'][-1];p['vertices']=[[x+.020,y,z] for x,y,z in p['vertices']]
m.S['notes']=['Illustrative round twist-up lip balm tube, 12.7 mm nominal diameter, separated hollow cap. Supplier closed height is 66 mm; open pictured height is approximately 60 mm with modest exposed balm.','Tube base and detached cap share ground plane; collar surrounds the stick. No recipe, health claim or promise of the workshop container.']
scene('3d-modeling',(4,3,7))
box('modeled cube',(0,.5,0),(1,1,1),'#85ABA4')
m.S['notes']=['A unit cube projected orthographically into an original modeling-window pictogram. Faces share exact vertices and edges. The projected cube represents a virtual object, not a physical monitor model.','Selection handles and cursor are flat interface symbols; no software branding or screenshot is copied.']
if __name__=='__main__':Path(__file__).with_name('scene.json').write_text(json.dumps(SCENES,indent=2)+'\n')
