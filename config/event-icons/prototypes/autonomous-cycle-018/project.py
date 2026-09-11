"""Depth-aware orthographic vector projection of original mesh geometry.
Every visible face is clipped by the portions of other faces actually nearer
at that screen position. Adjacent opaque regions are then united by paint.
"""
import json,gzip
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely import set_precision
from shapely.ops import unary_union
from shapely.strtree import STRtree
from scene import SCENES,basis
b=Path('.scratch/icon-cycles-20260909/cycle-018');out=b/'art'
def halfplane(a,bb,c):
 pts=[(-1000,-1000),(1000,-1000),(1000,1000),(-1000,1000)];result=[]
 for p,q in zip(pts,pts[1:]+pts[:1]):
  dp=a*p[0]+bb*p[1]+c;dq=a*q[0]+bb*q[1]+c
  if dp>=0:result.append(p)
  if (dp>=0)!=(dq>=0):
   t=dp/(dp-dq);result.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
 return Polygon(result) if len(result)>=3 else Polygon()
def project(s):
 right,up,n=basis(s['camera']);allv=np.concatenate([p['vertices'] for p in s['parts']]);xy=np.column_stack([allv@right,-allv@up]);lo=xy.min(0);hi=xy.max(0);scale=108/max(hi-lo);center=(lo+hi)/2;faces=[]
 for p in s['parts']:
  if s['name']=='pedal-steel' and p['name'] in ['string','fret']:continue
  vs=np.array(p['vertices']);base=np.array([int(p['color'][i:i+2],16) for i in (1,3,5)])
  for fidx in p['faces']:
   f=vs[fidx];norm=sum((np.cross(a,bb) for a,bb in zip(f,np.roll(f,-1,axis=0))),np.zeros(3));length=np.linalg.norm(norm)
   if length<1e-8:continue
   norm/=length
   if len(p['faces'])>1 and np.dot(norm,n)<=0:continue
   pts=(np.column_stack([f@right,-f@up])-center)*scale+64;poly=Polygon(pts).buffer(0)
   if poly.area<.025:continue
   den=np.dot(norm,n)
   if abs(den)<1e-9:continue
   nr,nu=np.dot(norm,right),np.dot(norm,up)
   plane=np.array([-nr/(scale*den),nu/(scale*den),(np.dot(norm,f[0])-nr*center[0]+nu*center[1]+(64/scale)*(nr-nu))/den])
   light=np.dot(norm,np.array([-.4,.8,.5])/np.linalg.norm([-.4,.8,.5]));factor=1.08 if light>.55 else 1 if light>0 else .84
   if p['name'] in ['leaf vein','screen diamond','grille mark','tension rope','die edge']:factor=1
   col='#'+''.join(f'{int(v):02X}' for v in np.clip(base*factor,0,255));faces.append((poly,plane,col))
 tree=STRtree([f[0] for f in faces]);paints={}
 for i,(poly,plane,color) in enumerate(faces):
  visible=poly
  for j in tree.query(poly):
   if j==i:continue
   other,op,_=faces[j];delta=op-plane
   if max(abs(delta))<1e-8:
    if j<i:continue
    cutter=other
   else:
    hp=halfplane(*delta)
    if hp.is_empty:continue
    cutter=other.intersection(hp)
   if not cutter.is_empty:visible=visible.difference(cutter)
   if visible.is_empty:break
  if not visible.is_empty:paints.setdefault(color,[]).append(visible)
 def polygon_parts(g):
  if g.geom_type=='Polygon':return [g]
  return [p for child in getattr(g,'geoms',[]) for p in polygon_parts(child)]
 def fmt(v):return f'{v:.1f}'.rstrip('0').rstrip('.')
 def ring(coords):
  pts=list(coords)[:-1];return 'M'+' '.join(fmt(v) for v in pts[0])+''.join('L'+' '.join(fmt(v) for v in p) for p in pts[1:])+'Z'
 body=[]
 for color,polys in paints.items():
  geom=unary_union([set_precision(p,.001) for g in polys for p in polygon_parts(g)]).simplify(.22,preserve_topology=True);parts=[geom] if geom.geom_type=='Polygon' else list(getattr(geom,'geoms',[]));d=''
  for poly in parts:
   if poly.geom_type=='Polygon' and poly.area>.045:d+=ring(poly.exterior.coords)+''.join(ring(r.coords) for r in poly.interiors)
  if d:body.append(f'<path fill="{color}" d="{d}"/>')
 return '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+s['name'].replace('-',' ').title()+'</title>'+''.join(body)+'</svg>\n'
if __name__=='__main__':
 for name,s in SCENES.items():
  raw=project(s).encode();(out/(name+'.svg')).write_bytes(raw);print(name,len(raw),len(gzip.compress(raw,compresslevel=6,mtime=0)),flush=True)
