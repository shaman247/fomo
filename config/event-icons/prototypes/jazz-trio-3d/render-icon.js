() => {
const {THREE,entities,bones,camera:sourceCamera}=window.__jazz3d;
const scene=new THREE.Scene(),camera=sourceCamera.clone();camera.updateMatrixWorld(true);
const palettes={Keyboard:{cloth:'#F9B548',pants:'#8055AE',skin:'#B77D53',hair:'#3C2B26'},Drums:{cloth:'#EF6355',pants:'#425A79',skin:'#F9DDBD',hair:'#6D4034'},Bass:{cloth:'#009E89',pants:'#394B65',skin:'#E6B78B',hair:'#8D4932'}};
const v=(x,y,z)=>new THREE.Vector3(x,y,z);
function added(parent,geometry,name,point){const m=new THREE.Mesh(geometry);m.name=name;if(point)m.position.copy(point);parent.add(m);return m;}
function ball(parent,name,point,scale){const m=added(parent,new THREE.SphereGeometry(1,40,28),name,point);m.scale.set(...scale);return m;}
function curve(parent,name,points,radius){return added(parent,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),32,radius,7,false),name);}
function facePoint(x,y,offset=.003){return v(x,y,.096*Math.sqrt(Math.max(.03,1-(x/.100)**2-(y/.118)**2))+offset);}
function patch(parent,name,points){const shape=new THREE.Shape(points.map(p=>new THREE.Vector2(p[0],p[1])));return added(parent,new THREE.ShapeGeometry(shape),name);}
function drape(mesh,surface){
 const g=mesh.geometry.toNonIndexed(),p=g.attributes.position,vertices=[];
 function tri(a,b,c,level){if(level){const ab=a.clone().lerp(b,.5),bc=b.clone().lerp(c,.5),ca=c.clone().lerp(a,.5);tri(a,ab,ca,level-1);tri(ab,b,bc,level-1);tri(ca,bc,c,level-1);tri(ab,bc,ca,level-1);}else for(const q of [a,b,c])vertices.push(...surface(q.x,q.y).toArray());}
 for(let i=0;i<p.count;i+=3)tri(v(p.getX(i),p.getY(i),0),v(p.getX(i+1),p.getY(i+1),0),v(p.getX(i+2),p.getY(i+2),0),3);
 mesh.geometry=new THREE.BufferGeometry();mesh.geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));mesh.geometry.computeVertexNormals();
}
function segment(parent,name,a,b,r1,r2=r1){const m=added(parent,new THREE.CylinderGeometry(r2,r1,a.distanceTo(b),32),name,a.clone().lerp(b,.5));m.quaternion.setFromUnitVectors(v(0,1,0),b.clone().sub(a).normalize());return m;}
function softLimb(group,bone,name){
 const {start:a,middle:b,end:c}=bone;
 const cornerA=b.clone().lerp(a,.09),cornerB=b.clone().lerp(c,.09),path=new THREE.CurvePath();
 path.add(new THREE.LineCurve3(a,cornerA));path.add(new THREE.QuadraticBezierCurve3(cornerA,b,cornerB));path.add(new THREE.LineCurve3(cornerB,c));
 const arm=bone.name.includes('arm'),r=arm?(name==='icon sleeve'?.052:.044):.076;
 added(group,new THREE.TubeGeometry(path,48,r,20,false),name);
 for(const pt of [a,c])ball(group,name,pt,[r,r,r]);
}
for(const [name,original] of Object.entries(entities)){
 const group=original.clone(true);group.visible=true;scene.add(group);
 // Reduce raised-key relief in the pictogram so this shallow camera still
 // separates the modeled black-key groups. Footprints and playing plane stay fixed.
 if(name==='Keyboard'){
  const remove=[];
  group.traverse(m=>{
   if(['white key','black key','X stand brace','stand foot','keyboard support'].includes(m.name))remove.push(m);
  });remove.forEach(m=>m.removeFromParent());
  // Three clearly grouped octaves are sufficient for the small pictogram;
  // retain the measured keyboard envelope and original playing surface.
  const kw=1.20/14;
  for(let i=0;i<14;i++){
   added(group,new THREE.BoxGeometry(kw-.002,.015,.210),'white key',v(-.60+(i+.5)*kw,.8095,.535));
   if(i<13&&![2,6].includes(i%7))added(group,new THREE.BoxGeometry(kw*.55,.0015,.110),'black key',v(-.60+(i+1)*kw,.81775,.582));
  }
  for(const [a,b] of [[v(0,.03,.31),v(0,.66,.81)],[v(0,.03,.88),v(0,.66,.38)],[v(-.45,.03,.31),v(.45,.03,.31)],[v(-.45,.03,.88),v(.45,.03,.88)],[v(-.46,.66,.38),v(.46,.66,.38)],[v(-.46,.66,.81),v(.46,.66,.81)]])segment(group,'icon keyboard stand',a,b,.020);
 }
 const seats=[];group.traverse(m=>{if(m.name.endsWith('stool seat')||m.name.endsWith('throne seat'))seats.push(m);if(/stool leg|throne leg|cymbal stand|endpin$/.test(m.name)){m.scale.x*=1.30;m.scale.z*=1.30;}});
 for(const seat of seats){ball(group,seat.name,seat.position,[.235,.036,.17]);seat.removeFromParent();}
 const who=name==='Keyboard'?'keyboardist':name==='Drums'?'drummer':'bassist';
 // Garments wrap the existing articulated skeleton. A continuous silhouette
 // replaces the separate rods and joint spheres of the geometry study.
 const hidden=[];group.traverse(m=>{if(m.isMesh&&m.name.startsWith(who+' ')&&(/(arm|leg) (upper|lower|joint)$/.test(m.name)||m.name.endsWith(' shoulder')))hidden.push(m);});hidden.forEach(m=>m.removeFromParent());
 for(const bone of bones.filter(b=>b.entity.name===name)){
  const arm=bone.name.includes('arm');softLimb(group,bone,arm?'icon bare arm':'icon trousers');
  if(arm&&name!=='Bass'){
   const sleeveEnd=bone.middle.clone().lerp(bone.end,.27);
   const dressed={...bone,end:sleeveEnd};softLimb(group,dressed,'icon sleeve');
   segment(group,'icon cuff',sleeveEnd.clone().lerp(bone.middle,.10),sleeveEnd,.053);
  }
 }
 const torso=group.getObjectByName(who+' torso');
 const hipY=torso.position.y,lean=name==='Bass'?.16:.06;
 const profile=new THREE.SplineCurve([[.13,0],[.156,.06],[.16,.18],[.18,.32],[.198,.45],[.19,.51],[.13,.56],[.055,.59]].map(([x,y])=>new THREE.Vector2(x,y))).getPoints(64);
 torso.geometry=new THREE.LatheGeometry(profile,64);const tp=torso.geometry.attributes.position;
 for(let i=0;i<tp.count;i++)tp.setZ(i,tp.getZ(i)*.65+lean*tp.getY(i)/.52);torso.geometry.computeVertexNormals();
 function chestPoint(x,y){const dy=y-hipY;let rr=profile.reduce((a,b)=>Math.abs(a.y-dy)<Math.abs(b.y-dy)?a:b).x;return v(x,y,Math.sqrt(Math.max(0,rr*rr-x*x))*.65+lean*dy/.52+.005);}
 const shoes=[];group.traverse(m=>{if(m.name===who+' shoe')shoes.push(m);});
 for(const shoe of shoes){ball(group,'icon shoe',shoe.position.clone().add(v(0,.009,0)),[.070,.059,.143]);shoe.removeFromParent();}
 // Broad garment details stay visible when reduced; each lies on its torso.
 if(name==='Keyboard')torso.name='icon waistcoat';
 if(name==='Drums'){
  for(const s of [-1,1]){const collar=patch(group,'icon collar',[[s*.008,hipY+.584],[s*.092,hipY+.55],[s*.071,hipY+.485],[s*.006,hipY+.538]]);drape(collar,chestPoint);}
  for(const dy of [.40,.32,.24])ball(group,'icon button',v(0,hipY+dy,.65*(.16+dy*.09)+lean*dy/.52+.003),[.008,.008,.004]);
 }
 if(name==='Bass'){
  // A small gold necklace follows the upper chest, above the instrument.
  curve(group,'icon gold',[chestPoint(-.063,hipY+.565),chestPoint(-.040,hipY+.52),chestPoint(0,hipY+.505),chestPoint(.040,hipY+.52),chestPoint(.063,hipY+.565)],.008);
  const belt=segment(group,'icon belt',v(0,hipY+.028,0),v(0,hipY+.068,0),.16);belt.scale.z=.66;
 }
 const head=group.getObjectByName(who+' head'),hg=head.parent;
 hg.position.y+=.118*(1.60-hg.scale.y);hg.scale.setScalar(1.60);head.scale.x=.100;
 for(const side of [-1,1]){const ears=hg.children.filter(m=>m.name===who+' ear'&&Math.sign(m.position.x)===side);ears.forEach(m=>m.position.x=side*.099);}
 // Detail follows the same head transform and ellipsoid as the approved scene.
 const nose=group.getObjectByName(who+' nose');nose.scale.set(.011,.010,.016);nose.position.set(0,-.014,.095);
 for(const side of [-1,1]){
  const x=side*.035;
  ball(hg,'icon eye',facePoint(x,.001,.004),[.009,.011,.004]);
  const brow=[];for(let i=0;i<=10;i++){let t=i/10,dx=(t-.5)*.032;brow.push(facePoint(x+dx,.033+.006*(1-(2*t-1)**2),.004));}
  curve(hg,'icon eyebrow',brow,.0034);
 }
 const mouth=[];for(let i=0;i<=14;i++){let t=i/14;mouth.push(facePoint((t-.5)*.043,-.034-.009*(1-(2*t-1)**2),.004));}
 curve(hg,'icon mouth',mouth,.0037);
 // Rounded hair cap: short forehead, lower back/sides, no independent 2D head placement.
 const verts=[],indices=[],rows=20,cols=64;
 for(let r=0;r<=rows;r++)for(let c=0;c<=cols;c++){
  const phi=c/cols*Math.PI*2;
  const edge=1.52-.39*Math.cos(phi)+.12*Math.sin(phi)+(name==='Bass'?.35*(1-Math.cos(phi)):0);
  const theta=r/rows*edge;
  verts.push(.104*Math.sin(theta)*Math.sin(phi),.124*Math.cos(theta),.100*Math.sin(theta)*Math.cos(phi));
 }
 for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const a=r*(cols+1)+c,b=a+cols+1;indices.push(a,b,a+1,b,b+1,a+1);}
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(verts,3));geo.setIndex(indices);geo.computeVertexNormals();
 added(hg,geo,'icon hair');
 if(name==='Keyboard'){
  for(let i=0;i<9;i++){const a=i/9*Math.PI*2;ball(hg,'icon hair',v(.077*Math.sin(a),.081+.009*Math.cos(3*a),.071*Math.cos(a)),[.036,.044,.033]);}
  ball(hg,'icon hair',v(0,.115,0),[.080,.034,.075]);
 }
 if(name==='Drums'){
  const sweep=ball(hg,'icon hair',v(-.028,.093,.060),[.080,.042,.055]);sweep.rotation.z=-.23;
  const lock=ball(hg,'icon hair',v(-.069,.061,.061),[.034,.034,.032]);lock.rotation.z=.35;
 }
 if(name==='Bass'){
  for(const side of [-1,1]){
   ball(hg,'icon hair',v(side*.083,-.042,-.059),[.040,.077,.040]);
   ball(hg,'icon hair',v(side*.080,-.078,-.036),[.036,.039,.038]);
   const hoop=added(hg,new THREE.TorusGeometry(.014,.0036,12,32),'icon gold',v(side*.107,-.041,.014));hoop.rotation.y=side*Math.PI/3;
  }
  const fringe=ball(hg,'icon hair',v(-.023,.081,.066),[.083,.035,.042]);fringe.rotation.z=-.26;
 }
 if(name==='Bass'){
  const body=group.getObjectByName('bass body'),ig=body.parent;
  for(const side of [-1,1]){
   curve(ig,'icon f hole',[v(side*.13,.83,.105),v(side*.15,.80,.105),v(side*.125,.75,.105),v(side*.15,.70,.105)],.006);
   ball(ig,'icon f hole',v(side*.13,.83,.105),[.009,.010,.002]);
  }
 }
 group.userData.palette=palettes[name];
}
scene.updateMatrixWorld(true);
function colorFor(mesh,p){
 const n=mesh.name;
 if(n==='icon waistcoat')return '#37474F';
 if(n==='icon sleeve')return p.cloth;
 if(n==='icon cuff')return '#FFD58A';
 if(n==='icon bare arm')return p.skin;
 if(n==='icon trousers'||n==='icon belt')return p.pants;
 if(n==='icon collar'||n==='icon button')return '#FFF3D6';
 if(n==='icon gold')return '#FFCA28';
 if(n==='icon hair'||n==='icon eyebrow')return p.hair;
 if(n==='icon eye'||n==='icon mouth')return '#49352E';
 if(n==='icon f hole')return '#74412E';
 if(/(head|nose|ear|neck|hand)$/.test(n)&&!n.startsWith('bass neck'))return p.skin;
 if(n.startsWith('bassist ')&&/arm (upper|lower|joint)$/.test(n))return p.skin;
 if(/(torso|shoulder)$/.test(n)||/arm (upper|lower|joint)$/.test(n))return p.cloth;
 if(/(pelvis|leg (upper|lower|joint))$/.test(n))return p.pants;
 if(n.includes('shoe'))return '#263238';
 if(n.includes('stool')||n.includes('throne'))return '#455A64';
 if(n.includes('white key')||n.endsWith(' skin')||n==='bridge'||n==='beater felt')return '#F1EDEC';
 if(n.includes('black key')||['fingerboard','tailpiece','control panel','control knob','sustain pedal'].includes(n))return '#293840';
 if(n==='bass body'||n==='bass neck'||n==='scroll')return '#D68A50';
 if(n.startsWith('string'))return '#F9DDB1';
 if(n.includes('cymbal')||n.includes('ride'))return /disc|bell/.test(n)?'#E7B34D':'#738A96';
 if(n.includes('shell'))return '#BE6353';
 if(n.startsWith('drumstick'))return '#D9AE79';
 if(n==='keyboard case')return '#455A64';
 return '#78909C';
}
// Three warm stage spots, aimed at the actual performer positions. Lighting is
// quantized into broad painted regions rather than photorealistic gradients.
const spots=Object.values(entities).map((g,i)=>{const target=g.position.clone().add(v(0,1.05,0)),position=target.clone().add(v(-.8+i*.20,2.6,1.25));return {position:position.applyMatrix4(camera.matrixWorldInverse),direction:target.applyMatrix4(camera.matrixWorldInverse).sub(position).normalize()};});
const colors=new Set(),materials=new Map();
function rgba(hex){return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);}
function blend(hex,tint,f){return '#'+rgba(hex).map((x,i)=>Math.round((x*(1-f)+rgba(tint)[i]*f)*255).toString(16).padStart(2,'0')).join('');}
function mat(hex,flat=false,wood=false,cloth=false){
 const key=hex+flat+wood+cloth;if(materials.has(key))return materials.get(key);
 const mid=blend(hex,'#FFC97B',.045),dark=blend(hex,'#273457',.25),high=mid;for(const c of [mid,dark])colors.add(c);
 const material=new THREE.ShaderMaterial({side:THREE.DoubleSide,uniforms:{spotPos:{value:spots.map(s=>s.position)},spotDir:{value:spots.map(s=>s.direction)},base:{value:new THREE.Vector3(...rgba(mid))},shade:{value:new THREE.Vector3(...rgba(dark))},highlight:{value:new THREE.Vector3(...rgba(high))},flatColor:{value:flat?1:0},wood:{value:wood?1:0},cloth:{value:cloth?1:0}},vertexShader:`
 varying vec3 n,localN,p;
 void main(){localN=normal;n=normalMatrix*normal;p=(modelViewMatrix*vec4(position,1.)).xyz;gl_Position=projectionMatrix*vec4(p,1.);}`,
 fragmentShader:`precision highp float;
 varying vec3 n,localN,p;uniform vec3 spotPos[3],spotDir[3],base,shade,highlight;uniform float flatColor,wood,cloth;
 void main(){vec3 N=normalize(n);float lit=0.;for(int i=0;i<3;i++){vec3 L=normalize(spotPos[i]-p);float cone=smoothstep(.78,.94,dot(-L,spotDir[i]));lit=max(lit,cone*max(0.,dot(N,L)));}
 vec3 c=lit>.67?highlight:(lit>.16?base:shade);
 if(cloth>.5){vec3 sideNormal=normalize(vec3(N.x,0.,N.z)+vec3(0.,0.,.0001));c=dot(sideNormal,normalize(vec3(-.5,0.,.86)))>-.1?base:shade;}
 if(flatColor>.5)c=base;
 if(wood>.5)c=abs(normalize(localN).z)>.85?(lit>.67?highlight:base):shade;
 gl_FragColor=vec4(c,1.);}`});
 materials.set(key,material);return material;
}
for(const group of scene.children){const p=group.userData.palette;group.traverse(mesh=>{
 if(!mesh.isMesh)return;
 // Omit subpixel mechanical clutter; preserve the modeled playing surfaces and structure.
 if(/tension rod|control knob|snare tripod|tuning peg|icon button/.test(mesh.name)){mesh.visible=false;return;}
 if(mesh.name.startsWith('string')){mesh.scale.x*=2.4;mesh.scale.z*=2.4;}
 const face=/^(keyboardist|drummer|bassist) (head|nose|ear|neck)$/.test(mesh.name);
 // Skin on faces and necks stays a single warm color; shaded jaws can read as beards.
 const cloth=/torso$|icon sleeve|icon waistcoat|icon trousers|pelvis$/.test(mesh.name);
 const flat=face||(!cloth&&!/icon hair|bass body/.test(mesh.name));
 mesh.material=mat(colorFor(mesh,p),flat,mesh.name==='bass body',cloth);
});}
// A low midnight-blue stage and three restrained pools establish the indoor
// nighttime setting while the outer canvas remains transparent.
const stageMaterial=new THREE.ShaderMaterial({side:THREE.DoubleSide,uniforms:{centers:{value:Object.values(entities).map(g=>new THREE.Vector2(g.position.x,g.position.z+.15))}},vertexShader:'varying vec3 w;void main(){w=(modelMatrix*vec4(position,1.)).xyz;gl_Position=projectionMatrix*viewMatrix*vec4(w,1.);}',fragmentShader:'precision highp float;varying vec3 w;uniform vec2 centers[3];void main(){float d=10.;for(int i=0;i<3;i++)d=min(d,length((w.xz-centers[i])/vec2(.55,.60)));vec3 c=d<.65?vec3(.29,.27,.31):(d<1.?vec3(.23,.24,.30):vec3(.14,.17,.25));gl_FragColor=vec4(c,1.);}'});
const stage=new THREE.Mesh(new THREE.CircleGeometry(1,96),stageMaterial);stage.rotation.x=-Math.PI/2;stage.scale.set(1.38,1.82,1);stage.position.set(0,-.025,-.22);scene.add(stage);
scene.updateMatrixWorld(true);
let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
scene.traverse(mesh=>{if(!mesh.isMesh||!mesh.visible)return;const a=mesh.geometry.attributes.position,m=new THREE.Matrix4().multiplyMatrices(camera.matrixWorldInverse,mesh.matrixWorld);for(let i=0;i<a.count;i++){const p=new THREE.Vector3().fromBufferAttribute(a,i).applyMatrix4(m);xmin=Math.min(xmin,p.x);xmax=Math.max(xmax,p.x);ymin=Math.min(ymin,p.y);ymax=Math.max(ymax,p.y);}});
const span=Math.max(2*Math.max(-xmin,xmax),ymax-ymin)*128/120,cy=(ymin+ymax)/2;
camera.left=-span/2;camera.right=span/2;camera.top=cy+span/2;camera.bottom=cy-span/2;camera.updateProjectionMatrix();
const renderer=new THREE.WebGLRenderer({antialias:false,alpha:true,preserveDrawingBuffer:true});renderer.setSize(1536,1536);renderer.setPixelRatio(1);renderer.setClearColor(0,0);renderer.toneMapping=THREE.NoToneMapping;renderer.outputColorSpace=THREE.LinearSRGBColorSpace;renderer.render(scene,camera);
const data=renderer.domElement.toDataURL('image/png');
// Complete depth-ordered layers avoid tracing all the cutouts behind another
// performer. Each performer still uses the depth buffer for its own geometry.
const layers={};const visibleGroups=scene.children.filter(o=>o.visible);
for(const layer of ['stage','Drums','Keyboard','Bass']){
 for(const o of visibleGroups)o.visible=layer==='stage'?o===stage:o.name===layer;
 renderer.render(scene,camera);layers[layer]=renderer.domElement.toDataURL('image/png');
}
for(const o of visibleGroups)o.visible=true;
const headCenters=scene.children.filter(g=>g.userData.palette).map(g=>{let head;g.traverse(m=>{if(m.name.endsWith(' head'))head=m;});return {performer:g.name,ndc:head.getWorldPosition(new THREE.Vector3()).project(camera).toArray()};});
const eyeCenters=[];for(const g of scene.children.filter(g=>g.userData.palette))g.traverse(m=>{if(m.name==='icon eye')eyeCenters.push({performer:g.name,ndc:m.getWorldPosition(new THREE.Vector3()).project(camera).toArray()});});
const projection={camera_world:camera.matrixWorld.toArray(),projection:camera.projectionMatrix.toArray(),frustum:{left:camera.left,right:camera.right,top:camera.top,bottom:camera.bottom},drummer_centered:true,head_centers:headCenters,eye_centers:eyeCenters,head_scale:1.60,lighting:'Three warm overhead spotlights, cool fill, two-tone fabrics, midnight stage with clipped light pools',render_size:1536,svg_size:128,colors:[...colors]};
renderer.dispose();return {data,projection,layers};
}
