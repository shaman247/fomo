"""Depth-aware orthographic vector projection of original mesh geometry.
Every visible face is clipped by the portions of other faces actually nearer
at that screen position. Adjacent opaque regions are then united by paint.
"""
import json,gzip
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from scene import SCENES,basis
b=Path('.scratch/icon-cycles-20260909/cycle-002');out=b/'art'
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
   plane=np.linalg.lstsq(np.column_stack([pts,np.ones(len(pts))]),f@n,rcond=None)[0]
   light=np.dot(norm,np.array([-.4,.8,.5])/np.linalg.norm([-.4,.8,.5]));factor=1 if any(k in p['name'] for k in ['petal','heart','bud','interior','wool']) else 1 if p['name'] in ['warp','heddle','weft','tuner','pedal rod'] else 1.10 if light>.55 else 1 if light>0 else .82
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
 def fmt(v):return f'{v:.1f}'.rstrip('0').rstrip('.')
 def ring(coords):
  pts=list(coords)[:-1];return 'M'+' '.join(fmt(v) for v in pts[0])+''.join('L'+' '.join(fmt(v) for v in p) for p in pts[1:])+'Z'
 body=[]
 for color,polys in paints.items():
  geom=unary_union(polys).simplify(.30 if s['name']=='inkle-loom' else .16,preserve_topology=True);parts=[geom] if geom.geom_type=='Polygon' else list(geom.geoms);d=''
  for poly in parts:
   if poly.geom_type=='Polygon' and poly.area>.045:d+=ring(poly.exterior.coords)+''.join(ring(r.coords) for r in poly.interiors)
  if d:body.append(f'<path fill="{color}" d="{d}"/>')
 if s['name']=='pedal-steel':
  def screen(v):return (np.array([np.dot(v,right),-np.dot(v,up)])-center)*scale+64
  for name in ['fret','string']:
   paths=[]
   for p in s['parts']:
    if p['name']!=name:continue
    vs=np.array(p['vertices'])
    if name=='string':
     nn=len(vs)//2;a=vs[:nn].mean(0);bb=vs[nn:].mean(0);a[0]=-.38
    else:
     c=vs.mean(0);a=c.copy();bb=c.copy();a[1]=bb[1]=vs[:,1].max();a[2]=vs[:,2].min();bb[2]=vs[:,2].max()
    paths.append('M'+' '.join(fmt(v) for v in screen(a))+'L'+' '.join(fmt(v) for v in screen(bb)))
   color='#F1EDEC' if name=='string' else '#AFC2C2';width='.48' if name=='string' else '.7'
   body.append('<path d="'+''.join(paths)+'" fill="none" stroke="'+color+'" stroke-width="'+width+'"/>')
 if s['name']=='backlit-tracing':body.append('<path d="M26 25l-4-6M60 18v-8M94 23l5-6" fill="none" stroke="#F3C267" stroke-width="3" stroke-linecap="round"/>')
 return '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+s['name'].replace('-',' ').title()+'</title>'+''.join(body)+'</svg>\n'
if __name__=='__main__':
 for name,s in SCENES.items():
  raw=project(s).encode();(out/(name+'.svg')).write_bytes(raw);print(name,len(raw),len(gzip.compress(raw,compresslevel=6,mtime=0)),flush=True)
