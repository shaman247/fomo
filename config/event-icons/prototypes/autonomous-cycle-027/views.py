import copy,json
from pathlib import Path
from scene import SCENES
from project import project
b=Path('.scratch/icon-cycles-20260909/cycle-027');body='<style>body{font:15px sans-serif;background:#ddd}.row{display:flex}.cell{width:175px;background:white;margin:4px;text-align:center}.cell svg{width:160px;height:160px}</style>'
for name,scene in SCENES.items():
 body+='<h2>'+name+'</h2><div class="row">'
 for label,cam in [('front',(0,0,10)),('rear',(0,0,-10)),('left',(-10,0,0)),('right',(10,0,0)),('top',(.01,10,.01)),('icon',scene['camera'])]:
  s=copy.deepcopy(scene);s['camera']=cam;svg=project(s);body+='<div class="cell">'+label+svg+'</div>'
 body+='</div>'
(b/'geometry.html').write_text(body)
