export function extend(api){
 const {THREE,C}=api;const {model,group,box,ball,cyl,rod,tube,plate,disk,lathe,mesh}=api.helpers;
 const v=a=>new THREE.Vector3(...a);
 function limb(g,a,b,c,r,color){const A=v(a),B=v(b),D=v(c);tube(g,[a,A.clone().lerp(B,.45).toArray(),A.clone().lerp(B,.85).toArray(),b,B.clone().lerp(D,.15).toArray(),B.clone().lerp(D,.55).toArray(),c],r,color);ball(g,a,r,color);ball(g,c,r,color);}
 function solve(a,c,l1,l2,bend){const A=v(a),C=v(c),d=A.distanceTo(C);if(d>l1+l2||d<Math.abs(l1-l2))throw Error('Unreachable joint target');const axis=C.clone().sub(A).normalize(),u=(l1*l1-l2*l2+d*d)/(2*d);const dir=v(bend).addScaledVector(axis,-v(bend).dot(axis)).normalize();return A.addScaledVector(axis,u).addScaledVector(dir,Math.sqrt(Math.max(0,l1*l1-u*u))).toArray();}
 function face(g,center,skin,hair,turn=0){const h=group(g,center,[0,turn,0]);ball(h,[0,0,0],9,skin,[.88,1.12,.86],true);ball(h,[-7.5,-.3,0],2,skin,[.6,1,.6],true);ball(h,[7.5,-.3,0],2,skin,[.6,1,.6],true);
  mesh(h,new THREE.SphereGeometry(9.3,32,20,0,Math.PI*2,0,1.23),hair,[0,.7,-.2],true).scale.set(.9,1.12,.86);
  plate(h,'M-7 4Q-3 4 0 8Q2 5 7 4L6 8Q0 12-7 8Z',7.2,hair,0,true);
  for(const x of [-3.1,3.1]){const eye=disk(h,x,.1,7.5,.74,'#513c31');eye.userData.eye=true;}
  ball(h,[.2,-2,7.5],1,skin,[.8,.8,.5],true);tube(h,[[-1.8,-4.2,7],[-.1,-4.7,7],[1.7,-4.1,7]],.42,'#865540',true,true);
 }
 function person(g,{hip,shoulder,arms,legs,shirt=C.teal,pants=C.purple,skin=C.skin,hair='#60493C',headTurn=0}){
  const axis=v(shoulder).sub(v(hip)).normalize();const len=v(shoulder).distanceTo(v(hip));const torso=lathe(g,hip,[[0,0],[6,0],[8,3],[8.5,len*.35],[10,len-3],[8.5,len],[3.5,len+1]],shirt);torso.scale.z=.56;torso.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),axis);
  const neck=v(shoulder).addScaledVector(axis,4);rod(g,shoulder,neck.toArray(),3.2,skin,true);face(g,neck.addScaledVector(axis,8).toArray(),skin,hair,headTurn);
  const checks=[];
  for(const arm of arms){const elbow=solve(arm.a,arm.hand,17,16,arm.bend);limb(g,arm.a,elbow,arm.hand,2.7,skin);const end=v(arm.a).lerp(v(elbow),.3).toArray();rod(g,arm.a,end,3.4,shirt);ball(g,arm.a,3.4,shirt);ball(g,arm.hand,2.8,skin,[1,1,.7],true);checks.push({part:'arm',upper:v(arm.a).distanceTo(v(elbow)),lower:v(elbow).distanceTo(v(arm.hand)),shoulder:arm.a,elbow,wrist:arm.hand});}
  for(const leg of legs){const knee=solve(leg.a,leg.foot,22,23,leg.bend);limb(g,leg.a,knee,leg.foot,4.3,pants);ball(g,v(leg.foot).add(new THREE.Vector3(2,-1,2)).toArray(),3.5,skin,[1.7,.6,1],true);checks.push({part:'leg',upper:v(leg.a).distanceTo(v(knee)),lower:v(knee).distanceTo(v(leg.foot)),hip:leg.a,knee,ankle:leg.foot});}
  g.userData.checks=checks;
 }
 {const g=model('chair-yoga',[.4,.13,1]);for(const x of [-12,12])for(const z of [-10,10])box(g,x,12,z,3,24,3,'#A9784F');box(g,0,25,0,30,3,27,'#D9A66E');box(g,0,40,-12,30,26,3,'#D9A66E');
  person(g,{hip:[0,30,0],shoulder:[0,57,0],arms:[{a:[-8,56,0],hand:[-7,85,0],bend:[-1,0,0]},{a:[8,56,0],hand:[7,85,0],bend:[1,0,0]}],legs:[{a:[-5,29,2],foot:[-8,3,25],bend:[0,1,1]},{a:[5,29,2],foot:[9,3,25],bend:[0,1,1]}],skin:'#D9A478'});
 }
 {const g=model('activity-pilates',[.15,.08,1]);box(g,0,-3,0,100,2,34,'#83B7CC');
  person(g,{hip:[-5,5,0],shoulder:[-24,27,0],arms:[{a:[-24,25,-5],hand:[5,13,-5],bend:[0,-1,0]},{a:[-24,25,5],hand:[5,13,5],bend:[0,-1,0]}],legs:[{a:[-3,5,-4],foot:[28,35,-4],bend:[1,-1,0]},{a:[-3,5,4],foot:[28,35,4],bend:[1,-1,0]}],headTurn:.35});
 }
 {const g=model('activity-tai-chi',[.1,.1,1]);person(g,{hip:[0,35,0],shoulder:[-4,63,0],arms:[{a:[-12,61,0],hand:[-32,73,4],bend:[0,-1,0]},{a:[4,61,0],hand:[31,65,5],bend:[0,1,0]}],legs:[{a:[-5,35,0],foot:[-32,2,2],bend:[-1,1,0]},{a:[5,35,0],foot:[36,3,1],bend:[1,1,0]}],skin:'#D6A57D',hair:'#4A4545'});}
 {const g=model('pole-dance',[.14,.08,1]);rod(g,[23,0,0],[23,111,0],1.6,C.metal);cyl(g,[23,0,0],10,2,C.ink);
  person(g,{hip:[-5,38,4],shoulder:[-1,65,4],arms:[{a:[-9,64,4],hand:[23,66,3],bend:[0,-1,0]},{a:[7,64,4],hand:[23,88,2],bend:[1,0,0]}],legs:[{a:[-10,38,4],foot:[-39,7,4],bend:[-1,0,0]},{a:[0,38,4],foot:[23,21,2],bend:[1,1,0]}],shirt:'#B867AE',pants:'#7956A7',skin:'#D6A077',hair:'#473C38'});
 }
 {const g=model('craft-figure-drawing',[.1,.1,1]);box(g,0,47,-7,61,91,3,'#C59C6F');box(g,0,48,-5,56,86,1,C.cream);for(const x of [-22,-7,8,23])tube(g,[[x,86,-3],[x,94,-3],[x,94,-9]],1.2,C.metal);
  const figure=group(g,[-2,10,0]);figure.scale.setScalar(.65);person(figure,{hip:[0,39,0],shoulder:[0,66,0],arms:[{a:[-8,65,0],hand:[-20,37,0],bend:[-1,0,0]},{a:[8,65,0],hand:[19,40,0],bend:[1,0,0]}],legs:[{a:[-5,39,0],foot:[-12,0,0],bend:[0,0,1]},{a:[5,39,0],foot:[12,0,0],bend:[0,0,1]}],shirt:'#BA9A80',pants:'#BA9A80',skin:'#E2BB95',hair:'#746459'});
  // Flatten the modeled mannequin into a graphite study on the paper plane.
  figure.scale.z=.08;figure.traverse(o=>{if(o.isMesh)o.material=api.helpers.mat('#98795F',true);});
  const pencil=group(g,[39,41,0],[0,0,-.20]);cyl(pencil,[0,0,0],3.6,68,'#EDB64E');mesh(pencil,new THREE.ConeGeometry(3.6,12,24),'#E0BC91',[0,-40,0]).rotation.z=Math.PI;mesh(pencil,new THREE.ConeGeometry(1.6,5,24),C.ink,[0,-45,0]).rotation.z=Math.PI;cyl(pencil,[0,35,0],3.6,5,C.pale);
 }
}
