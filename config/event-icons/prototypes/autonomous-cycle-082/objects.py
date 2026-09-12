import numpy as np,math
import scene as m
from scene import *
scene('hot-foil-stamping',(4,3.5,8))
box('weighted base',(0,.015,0),(.31,.03,.29),'#708B96')
box('rear upright',(0,.27,-.10),(.055,.48,.055),'#708B96')
box('head support bridge',(0,.46,-.02),(.105,.065,.21),'#708B96')
# Four supports keep the platen level and physically connected to the base.
for x in [-.105,.105]:
 for z in [-.035,.125]:rod('platform support',(x,.03,z),(x,.1125,z),.009,'#637781',12)
box('level work platform',(0,.125,.045),(.30,.025,.24),'#BBC5C4')
box('paper substrate',(0,.140,.04),(.245,.005,.17),'#F1E2C4')
box('gold foil above substrate',(0,.143,.06),(.27,.001,.065),'#D9B45E')
rod('vertical sliding ram',(0,.295,.055),(0,.59,.055),.018,'#B4C4C8',20)
box('ram carriage',(0,.46,.055),(.08,.08,.075),'#526E7A')
rod('crosswise lever shaft',(-.058,.47,.055),(.095,.47,.055),.013,'#94A9AF',16)
rod('power lever',(.095,.47,.055),(.095,.67,.14),.012,'#849EA7',16)
rod('insulated lever grip',(.095,.595,.108),(.095,.675,.142),.018,'#496878',16)
box('insulating connector',(0,.297,.055),(.05,.035,.055),'#A8A292')
box('heated type holder',(0,.268,.055),(.265,.045,.095),'#BC9269')
box('downward die face',(0,.241,.055),(.215,.008,.065),'#DFBF80')
# Return spring around the ram is continuous, with contacts at carriage and cap.
points=[(.024*math.cos(t),.501+.073*t/(math.pi*8),.055+.024*math.sin(t)) for t in np.linspace(0,math.pi*8,65)]
tube('return spring',points,.003,'#536D77',6)
rod('spring top cap',(0,.578,.055),(0,.589,.055),.035,'#647E89',20)
box('heat control',(0,.046,.127),(.055,.026,.025),'#526E7A')
box('heat indicator',(0,.047,.140),(.016,.009,.001),'#DEAE64')
m.S['notes']=['Generic manually fed bench hot-foil press,not an exact CBA machine.','Typeholder and platform are parallel;foil sits over paper on supported platform. Lever,shaft,ram andreturn spring connected;head is in raised loading position.','Approximate envelope31cmwide29cmdeep68cmhigh;view/layout derived frommodel. No operator,power cable or tinytype characters.']
