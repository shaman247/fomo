"""Inline identical projected poses at their authoritative scene offsets.
Flat paint and disjoint bodies allow compact self-contained paths per paint; no href references.
Every placement derives from the scene; compare to complete dense projection.
"""
import copy,json,re,gzip
import numpy as np
from pathlib import Path
from scene import SCENES,basis
from project import project
b=Path('.scratch/icon-cycles-20260909/cycle-043');s=SCENES['line-dance'];dense=project(s);(b/'line-dense-v2.svg').write_text(dense)
first=copy.deepcopy(s);first['parts']=[p for p in s['parts'] if p['name'].startswith('dancer 1 ')];template=project(first,bounds=s)
paths=re.findall(r'<path fill="(#[A-Fa-f0-9]+)" stroke="#[A-Fa-f0-9]+"(.*?)/>',template)
right,up,n=basis(s['camera']);allv=np.concatenate([p['vertices'] for p in s['parts']]);xy=np.column_stack([allv@right,-allv@up]);scale=108/max(xy.max(0)-xy.min(0))
def short_d(d):
 # Polygon projection uses M/L/Z only. Preserve every vertex at one decimal.
 out=[]
 def fmt(v):
  t=f'{v:.1f}'.rstrip('0').rstrip('.')
  if t.startswith('0.'):t=t[1:]
  if t.startswith('-0.'):t='-'+t[2:]
  return t
 def nums(v):
  result=''
  for n in v:
   t=fmt(n);result+=('' if not result or t.startswith('-') else ' ')+t
  return result
 for ring in d.split('Z'):
  if not ring:continue
  points=[list(map(float,re.findall(r'-?\d*\.?\d+',v))) for v in re.split('[ML]',ring) if v]
  assert all(len(v)==2 for v in points)
  ab='M'+nums(points[0])+(' '+ ' '.join(nums(v) for v in points[1:]) if len(points)>1 else '')+'Z'
  rel='M'+nums(points[0])
  if len(points)>1:rel+='l'+' '.join(nums(np.array(q)-p) for p,q in zip(points,points[1:]))
  rel+='Z';out.append(min([ab,rel],key=len))
 return ''.join(out)
base=['#A87555','#63A5A0','#556C8D','#45434A'];variants=[base,['#E5B38A','#DCA267','#697899','#776056'],['#C48C68','#B58AA6','#4E777D','#4C4747']];body=''
for j,palette in enumerate(variants):
 colors=dict(zip(base,palette));dx=j*.83*scale
 body+=f'<g transform="translate({dx:.5f})">'
 for i,(col,rest) in enumerate(paths):
  c=colors.get(col.upper(),col);d=re.search(r'd="([^"]+)"',rest)[1];body+=f'<path fill="{c}" stroke="{c}" d="{short_d(d)}"/>'
 body+='</g>'
raw=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><title>Line dance</title><g stroke-width=".15" stroke-linejoin="round">'+body+'</g></svg>\n').encode();(b/'art/line-dance.svg').write_bytes(raw)
(b/'line-projection-composition.json').write_text(json.dumps(dict(source='Authoritative scene; three identical posed body geometries with distinct paints.',dense_bytes=len(dense.encode()),compact_bytes=len(raw),gzip_level_6=len(gzip.compress(raw,compresslevel=6,mtime=0)),scale=scale,translation=.83*scale,paths=len(paths),limitation='Requires disjoint projected bodies and flat paint; no painter-layer assumption for overlapping performers.'),indent=2)+'\n');print(len(raw),len(gzip.compress(raw,compresslevel=6,mtime=0)))
