() => {
const {THREE,scene,bones,entities,bassBody}=window.__jazz3d;
const results=[];
const kb=new THREE.Box3(new THREE.Vector3(-.649,.665,.418),new THREE.Vector3(.649,.806,.782));
for(const bone of bones.filter(b=>b.entity.name==='Keyboard')){
 let minimum=Infinity;
 for(const [a,b,r] of [[bone.start,bone.middle,bone.radius],[bone.middle,bone.end,bone.radius*.82]]){
  for(let i=0;i<=150;i++){let t=i/150;const pt=a.clone().lerp(b,t);minimum=Math.min(minimum,kb.distanceToPoint(pt)-r);}
 }
 results.push({part:bone.name,against:'keyboard case',clearance_m:minimum});
}
// Test limb capsule samples against the actual extruded bass surface triangles.
const geom=bassBody.geometry,attr=geom.attributes.position,idx=geom.index;
const matrix=bassBody.matrixWorld,triangles=[];
const count=idx?idx.count:attr.count;
for(let i=0;i<count;i+=3){const points=[0,1,2].map(k=>new THREE.Vector3().fromBufferAttribute(attr,idx?idx.getX(i+k):i+k).applyMatrix4(matrix));triangles.push(new THREE.Triangle(...points));}
const temp=new THREE.Vector3();
for(const bone of bones.filter(b=>b.entity.name==='Bass')){
 let minimum=Infinity;
 for(const [a,b,r] of [[bone.start,bone.middle,bone.radius],[bone.middle,bone.end,bone.radius*.82]]){
  for(let i=0;i<=100;i++){
   const pt=bone.entity.localToWorld(a.clone().lerp(b,i/100));let d=Infinity;
   for(const tri of triangles){tri.closestPointToPoint(pt,temp);d=Math.min(d,pt.distanceTo(temp));}
   minimum=Math.min(minimum,d-r);
  }
 }
 results.push({part:bone.name,against:'bass body',clearance_m:minimum});
}
return results;
}
