export function extend(api) {
 const {THREE,C}=api;const {model,group,box,ball,cyl,rod,tube,plate,disk,ring,lathe,topDisk,surfaceRect,keys,text,note,mesh}=api.helpers;
 // North Indian lutes: restrained pear/gourd resonators, long necks, and a
 // short-necked skin-faced sarangi. Shape proxies, not manufacturer replicas.
 for(const kind of ['sitar','tanpura','sarangi']){
  const root=model('instrument-'+kind,[.26,.1,1]);const g=group(root,[0,0,0],[0,0,-.22]);
  if(kind==='sarangi'){
   plate(g,'M-14 0Q-20 1-20 13L-16 41Q-14 45-10 45L-10 62H10V45Q14 45 16 41L20 13Q20 1 14 0Z',-6,'#B37948',13);
   plate(g,'M-15 3Q-18 4-17 13L-13 33Q0 38 13 33L17 13Q18 4 15 3Z',7.2,'#F0D7AD',0,true);
   box(g,0,68,1,22,18,14,'#B37948');box(g,0,68,8.2,13,9,.5,'#634231');
   for(let i=0;i<4;i++)rod(g,[-11,59+i*6,2],[-18,59+i*6,2],1.6,C.ink);
   for(let i=0;i<6;i++)rod(g,[9,38+i*4,4],[15,38+i*4,4],.8,'#76553A');
   box(g,0,20,9,11,3,3,C.cream);for(let i=0;i<3;i++)rod(g,[-2+i*2,73,8.8],[-2+i*2,8,10],.25,C.cream,true);
   tube(g,[[29,1,0],[31,40,0],[30,77,0]],1.2,'#785239');rod(g,[29,2,1],[30,75,1],.6,C.cream,true);
  }else{
   const sitar=kind==='sitar';
   // Oval shell with a tapered upper shoulder, rather than a flattened bulb.
   plate(g,'M0 0C-16 0-23 9-22 23C-21 38-13 43-7 50H7C13 43 21 38 22 23C23 9 16 0 0 0Z',-8,'#985E39',13);
   plate(g,'M0 3C-13 3-19 11-18 23C-17 36-9 42-5 47H5C9 42 17 36 18 23C19 11 13 3 0 3Z',5.1,'#CD9154',0,true);
   box(g,0,78,0,10,78,10,'#AA7043');box(g,0,78,5.3,8,76,.5,'#B9814D');
   if(sitar){ball(g,[0,102,-12],12,'#A96C40',[1,.9,.8]);for(let i=0;i<12;i++){const yy=51+i*4.5;tube(g,[[-6,yy,6],[0,yy+.4,8],[6,yy,6]],.65,C.pale,true,true);}for(let i=0;i<7;i++)rod(g,[5,65+i*6,3],[10,65+i*6,3],.75,C.cream);}
   for(let i=0;i<4;i++){const side=i%2?-1:1;const yy=109+Math.floor(i/2)*6;rod(g,[side*3,yy,1],[side*11,yy,1],1.3,'#71472E');ball(g,[side*11,yy,1],2,'#825232',[1,1.1,.7]);}
   box(g,0,17,7,13,3,3,C.cream);for(let i=0;i<(sitar?5:4);i++)rod(g,[(i-(sitar?2:1.5))*.9,113,7],[(i-(sitar?2:1.5))*1.2,8,8.7],.19,'#F7DEAD',true);
  }
 }
 {const g=model('instrument-tabla',[.35,.58,1]);
  // Bayan is a broad metal bowl; dayan is a taller tapered wooden barrel.
  for(const [x,r,h,color] of [[-22,22,31,'#A6B8C0'],[23,16,39,'#B07A4B']]){
   const profile=x<0?[[0,0],[11,0],[18,4],[22,14],[22,25],[20,31]]:[[0,0],[11,0],[14,8],[15,25],[16,h]];
   lathe(g,[x,3,0],profile,color);cyl(g,[x,3+h,0],r,3,C.cream);topDisk(g,x,5+h,0,r*.84,'#D4B48A');topDisk(g,x,5.1+h,0,r*.68,C.cream);topDisk(g,x+(x<0?4:0),5.2+h,0,r*.30,'#383738');
   for(let i=0;i<12;i++){const a=i*Math.PI/6;const points=profile.slice(1).map(([rr,yy])=>[x+Math.cos(a)*(rr+1),3+yy,Math.sin(a)*(rr+1)]);tube(g,points,.6,'#E6CDA0',false,true);if(x>0){const rr=16;rod(g,[x+Math.cos(a)*rr,14,Math.sin(a)*rr],[x+Math.cos(a)*rr,23,Math.sin(a)*rr],1.25,'#D1AC73');}}
   cyl(g,[x,2,0],r*.8,4,'#92729C');
  }
 }
 {const g=model('instrument-steelpan',[.33,.58,1]);for(const x of [-27,27]){rod(g,[x,0,8],[x,55,0],2,C.metal);rod(g,[x-12,0,16],[x+12,0,-9],2,C.ink);}lathe(g,[0,48,0],[[0,0],[26,0],[31,4],[32,15],[32,17]],'#7C9EB0');cyl(g,[0,65,0],32,2,C.pale);topDisk(g,0,66.2,0,29,'#98BEC9');
  for(let i=0;i<7;i++){const a=i*2*Math.PI/7;const m=topDisk(g,Math.cos(a)*20,66.4,Math.sin(a)*20,6,'#CEE0DC');m.scale.set(1,.7,1);}topDisk(g,0,66.5,0,9,'#D9E8DE');rod(g,[-35,72,12],[-9,67,1],1.1,'#BC8B5D');ball(g,[-9,67,1],2.5,C.ink);rod(g,[35,74,6],[12,67,0],1.1,'#BC8B5D');ball(g,[12,67,0],2.5,C.ink);
 }
 {const root=model('instrument-shakuhachi',[.28,.12,1]);const g=group(root,[0,0,0],[0,0,-.27]);const pts=[[0,5,0],[-1,14,0],[-2,28,0],[-2,52,0],[-1,83,0],[0,106,0]];tube(g,pts,4.6,'#D3A264');
  for(const [x,y] of [[-1,18],[-2,36],[-2,62],[-1,88]]){const n=cyl(g,[x,y,0],5.15,1.8,'#A47B46');}
  for(const y of [35,48,63,78])disk(g,-2+(y-35)/43, y,4.62,1.9,'#5B4430');
  const mouth=cyl(g,[0,106.3,0],4.7,1.2,'#684D36');topDisk(g,0,107,0,3.2,'#342B24');plate(g,'M-3 107L3 107L2 102H-2Z',4.2,'#F0DCB0',0,true);
 }
 {const root=model('instrument-trombone',[.5,.30,1]);const g=group(root,[0,0,0],[0,0,.55]);
  // Slide lies in XY. Bell return bows out in Z: orthogonal tubing planes.
  tube(g,[[0,5,0],[76,5,0],[83,7,0],[84,12,0],[81,18,0],[76,19,0],[0,19,0]],2,C.gold);
  tube(g,[[0,19,0],[-16,19,0],[-23,19,-5],[-23,19,-13],[-16,19,-18],[30,19,-18]],2.4,C.gold);
  rod(g,[8,5,0],[8,19,0],1.3,'#D29B30');rod(g,[21,5,0],[21,19,0],1.3,'#D29B30');rod(g,[0,19,0],[0,19,-18],1.3,'#D29B30');
  const bell=lathe(g,[29,19,-18],[[2.4,0],[2.8,10],[4,17],[7,23],[12,29],[14,31]],C.gold);bell.rotation.z=-Math.PI/2;
  const opening=disk(g,60,19,-18,13,'#9A5A24');opening.rotation.y=Math.PI/2;
  const lip=mesh(g,new THREE.TorusGeometry(13.5,.9,8,48), '#FFD875',[60.3,19,-18]);lip.rotation.y=Math.PI/2;
  rod(g,[-8,5,0],[0,5,0],1.2,C.pale);const mouth=cyl(g,[-9,5,0],3,3,C.pale,1.3);mouth.rotation.z=Math.PI/2;
 }
 {const g=model('craft-pottery-wheel',[.32,.50,1]);cyl(g,[0,6,0],32,12,'#688A98');cyl(g,[0,16,0],8,10,C.ink);cyl(g,[0,23,0],37,4,C.pale);lathe(g,[0,25,0],[[0,0],...new THREE.CatmullRomCurve3([[13,0],[14,4],[20,12],[23,26],[21,34],[17,39],[17,44]].map(p=>new THREE.Vector3(...p,0))).getPoints(70).map(p=>[p.x,p.y])],'#CB8059');cyl(g,[0,69,0],17,2,'#E6A27A');topDisk(g,0,70.2,0,13,'#824D39');}
 for(const kind of ['composting','natural-dyeing']){
  if(kind==='natural-dyeing')continue;const g=model('activity-'+kind,[.25,.46,1]);
  lathe(g,[0,0,0],[[0,0],[23,0],[27,8],[31,48],[32,51]],'#4E9A7D');cyl(g,[0,51,0],32,3,'#94C7A5');topDisk(g,0,52.7,0,28,'#315849');
  // The scraps penetrate the opening; the near rim masks their submerged ends.
  const carrot=group(g,[-6,52,-5],[0,0,-.35]);mesh(carrot,new THREE.ConeGeometry(7,26,32),'#F2A245',[0,10,0]);for(const dx of [-5,0,5])tube(carrot,[[0,23,0],[dx,31,-1],[dx*1.6,33,-1]],1.7,'#73B568');
  plate(g,'M8 51Q-2 70 14 83Q32 69 8 51Z',-3,'#91BE65',1);tube(g,[[8,51,0],[11,65,0],[15,77,0]],.9,'#487D4D');
  const rim=new THREE.Mesh(new THREE.TorusGeometry(30,2,10,60,Math.PI),api.helpers.mat('#96CCA8'));rim.rotation.x=Math.PI/2;rim.rotation.z=Math.PI;rim.position.y=53;g.add(rim);
 }
 {const g=model('craft-watercolor',[.25,.85,1]);box(g,6,1,17,81,1,67,C.cream);surfaceRect(g,9,1.8,28,45,21,'#8DCCDD');box(g,-6,5,-24,88,8,29,C.pale);for(let i=0;i<5;i++)box(g,-40+i*17,9.4,-24,12,2,20,['#DE6A78','#F2C150','#7EB86F','#529DBC','#8B74B5'][i]);rod(g,[45,7,-27],[24,4,40],2,'#B7814E');rod(g,[26,4,31],[24,4,40],2.2,C.metal);const tip=mesh(g,new THREE.ConeGeometry(2.8,13,24),'#38768D',[22,4,46]);tip.rotation.x=Math.PI/2;tip.rotation.z=.16;}
 {const g=model('craft-origami',[.25,.55,1]);
  // Classic paper boat: a central raised fold inside a symmetric folded hull.
  const pts=[[-50,23,0],[50,23,0],[-29,0,0],[29,0,0],[-24,17,18],[24,17,18],[-24,17,-18],[24,17,-18],[0,43,0],[-29,17,0],[29,17,0]];
  const faces=[[0,2,4],[2,3,5],[2,5,4],[3,1,5],[0,6,2],[2,6,7],[2,7,3],[3,7,1],[9,10,8],[0,4,9],[1,10,5],[0,9,6],[1,7,10]];
  faces.forEach((f,i)=>{const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(f.flatMap(j=>pts[j]),3));geo.computeVertexNormals();mesh(g,geo,['#EF8FA9','#E87298','#F8ACC0'][i%3],[0,0,0],true);});
 }
 {const g=model('format-planetarium',[0,.06,1]);
  // Readable cutaway dome, horizon and projector in a front view.
  const dome=new THREE.Shape();dome.moveTo(-53,9);dome.absarc(0,9,53,Math.PI,0,true);dome.lineTo(-53,9);plate(g,dome,-8,'#364969',6);const inner=new THREE.Shape();inner.moveTo(-48,12);inner.absarc(0,12,48,Math.PI,0,true);inner.lineTo(-48,12);plate(g,inner,-1,'#273352',0,true);
  for(const [x,y,r] of [[-29,30,1.8],[-17,46,1.4],[7,50,1.8],[28,34,1.6],[19,20,1.2],[-5,32,1.2]])disk(g,x,y,0,r,'#FFE6A0');
  tube(g,[[-29,30,0],[-17,46,0],[7,50,0],[28,34,0]],.45,'#7D9DBC',false,true);box(g,0,3,0,112,8,17,'#7A8FB0');box(g,0,13,10,6,15,6,C.metal);ball(g,[0,27,10],10,C.ink);for(const x of [-5,0,5])disk(g,x,29+(x===0?3:0),19,1.5,C.gold);box(g,0,6,11,28,5,12,C.metal);
 }
 {const g=model('craft-letterpress',[.38,.4,1]);box(g,0,10,0,73,12,49,C.ink);box(g,0,18,8,54,2,29,C.cream);for(const x of [-29,29])box(g,x,45,-14,8,57,9,'#5F8797');box(g,0,70,-14,69,9,12,'#81AAB9');rod(g,[0,68,-14],[0,37,-14],3,C.metal);box(g,0,34,0,49,6,30,'#668C9C');rod(g,[0,72,-14],[25,88,-14],2.5,C.ink);ball(g,[25,88,-14],5,'#D88C58');text(g,'A',-5,19.3,17,12,'#81599B','top');}
 // Dice and tile rack use true supporting planes for their markings.
 {const g=model('tabletop-rpg',[.12,.18,1]);const geo=new THREE.IcosahedronGeometry(42,0);const pos=geo.attributes.position;geo.rotateY(.31);geo.rotateX(.21);const colors=['#BCA2DF','#9B7BC8','#8063AA','#D2BCEB'];
  for(let i=0;i<pos.count;i+=3){const a=new THREE.Vector3().fromBufferAttribute(pos,i),b=new THREE.Vector3().fromBufferAttribute(pos,i+1),c=new THREE.Vector3().fromBufferAttribute(pos,i+2);const tri=new THREE.BufferGeometry().setFromPoints([a,b,c]);tri.computeVertexNormals();mesh(g,tri,colors[(i/3)%4],[0,0,0],true);
   const center=a.clone().add(b).add(c).multiplyScalar(1/3),normal=center.clone().normalize();if(normal.z>.1){const label=group(g,center.clone().addScaledVector(normal,.25).toArray());label.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),normal);text(label,String(i/3+1),-5,-4,0,9,C.cream);}}
 }
 {const g=model('game-rummikub',[.28,.35,1]);box(g,0,3,0,102,6,27,'#3A7D8E');const rack=group(g,[0,5,-5],[-.18,0,0]);box(rack,0,13,-1,100,29,5,'#286479');for(let i=0;i<5;i++){box(rack,-39+i*19,16,3,16,27,5,C.cream);text(rack,String(i+3),-44+i*19,14,6,10,i<3?'#3C7198':'#C65353');disk(rack,-39+i*19,9,6.1,1.2,'#B6A492');}box(g,0,8,8,105,7,6,'#519EAD');}
 {const g=model('game-backgammon',[.12,.85,1]);box(g,0,1,0,93,3,75,'#94694A');box(g,0,3,0,86,1,68,'#EAC595');for(let side of [-1,1])for(let i=0;i<6;i++){const x=side*(8+i*6.4);for(const zside of [-1,1]){const shape=new THREE.Shape();shape.moveTo(x-2.8,zside*31);shape.lineTo(x+2.8,zside*31);shape.lineTo(x,zside*4);shape.closePath();const m=plate(g,shape,0,(i+(zside===1?1:0))%2?'#986044':'#F6DFB8',0,true);m.rotation.x=-Math.PI/2;m.position.y=3.7;}}
  box(g,0,4,0,5,2,70,'#AA7651');for(const [x,z,n,color] of [[-40,-28,3,C.cream],[40,28,3,C.ink],[-8,28,2,C.cream],[8,-28,2,C.ink]])for(let j=0;j<n;j++)cyl(g,[x,5,z-Math.sign(z)*j*6.2],2.75,2,color);
 }
 {const g=model('trivia',[.15,.28,1]);cyl(g,[0,5,0],36,10,C.ink);cyl(g,[0,11,0],31,4,C.pale);lathe(g,[0,12,0],[[0,0],[26,0],[26,5],[23,10],[15,13],[0,14]],'#EE6762');plate(g,'M-21 41H-31Q-39 41-39 49V77Q-39 85-31 85H31Q39 85 39 77V49Q39 41 31 41H-8L-24 31Z',0,'#64BBC7',4);text(g,'?',-8,51,4.2,19,C.cream);}
 {const g=model('format-string-quartet',[.14,.1,1]);for(const [x,scale] of [[-39,.45],[-16,.45],[10,.52],[40,.72]]){const n=group(g,[x,0,0]);n.scale.setScalar(scale);api.helpers.bowed(n,false,0,scale<.7);rod(n,[29,10,0],[29,103,0],.8,'#915C3B');rod(n,[27,10,0],[27,103,0],.3,C.cream,true);}}
}
