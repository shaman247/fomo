import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js';

const root = document.getElementById('jazz-trio-geometry');
const host = root.querySelector('[data-stage]');
const readColor = (name, fallback) => { const probe=document.createElement('span');probe.style.color=`var(${name}, ${fallback})`;root.appendChild(probe);const color=getComputedStyle(probe).color;probe.remove();return color; };
const bg = new THREE.Color(readColor('--background', '#f5f5f5'));
const fg = new THREE.Color(readColor('--foreground', '#272727'));
const tone = n => bg.clone().lerp(fg, n);
const material = (n, extra={}) => new THREE.MeshStandardMaterial({color:tone(n), roughness:.83, metalness:0, ...extra});
const mats = {body:material(.35), skin:material(.25), leg:material(.49), joint:material(.58), metal:material(.62,{metalness:.35}), shell:material(.46), head:material(.10), black:material(.88), white:material(.015), bass:material(.39), string:material(.10,{metalness:.5})};
const scene = new THREE.Scene();
const renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.0;
renderer.setClearColor(0,0);host.appendChild(renderer.domElement);
renderer.domElement.setAttribute('role','img');
renderer.domElement.setAttribute('aria-label','Rotatable three-dimensional jazz trio: seated keyboardist, seated drummer, and standing double bassist. Camera presets and joint overlay provide alternative inspection views.');
renderer.domElement.style.touchAction='none';
const camera = new THREE.OrthographicCamera(-2.5,2.5,2.2,-2.2,.01,40);
const target = new THREE.Vector3(0,.93,0);
scene.add(new THREE.HemisphereLight(0xffffff,0x67717b,1.4));
const key = new THREE.DirectionalLight(0xffffff,2.1);key.position.set(-3,7,5);key.castShadow=true;
key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-4,right:4,top:4,bottom:-4,near:.5,far:15});key.shadow.bias=-.0002;scene.add(key);
const fill = new THREE.DirectionalLight(0xffffff,.7);fill.position.set(4,3,-2);scene.add(fill);
const ground=new THREE.Mesh(new THREE.CircleGeometry(2.55,96),material(.045));ground.rotation.x=-Math.PI/2;ground.position.y=-.008;ground.receiveShadow=true;scene.add(ground);
const grid = new THREE.GridHelper(5,10,tone(.16),tone(.095));grid.position.y=-.003;scene.add(grid);
const layoutRadius=1.55, bassInset=.40, keyboardInset=0.471277977493, bassLeftTurn=Math.PI/2, playerRightTurn=20*Math.PI/180, initialHeadScale=1.35, heads=[];
const layoutAngles={Keyboard:-Math.PI/3,Drums:Math.PI,Bass:Math.PI/3};
const entities={}, solids=[], bones=[], contactData=[], clearanceTests=[], skeleton=new THREE.Group();scene.add(skeleton);skeleton.visible=false;
const skelMat = new THREE.LineBasicMaterial({color:new THREE.Color(readColor('--blue','#367ac0')),depthTest:false});
const dotMat = new THREE.MeshBasicMaterial({color:skelMat.color,depthTest:false});
const v = (x,y,z)=>new THREE.Vector3(x,y,z);
function part(parent,geo,mat,name,pos){const m=new THREE.Mesh(geo,mat);m.name=name;if(pos)m.position.copy(pos);m.castShadow=true;m.receiveShadow=true;parent.add(m);solids.push(m);return m;}
function box(p,w,h,d,pos,mat,name){return part(p,new THREE.BoxGeometry(w,h,d),mat,name,pos);}
function ellipsoid(p,pos,r,mat,name){const m=part(p,new THREE.SphereGeometry(1,24,16),mat,name,pos);m.scale.set(...r);return m;}
function rod(p,a,b,r,mat,name,r2=r){const delta=b.clone().sub(a);const m=part(p,new THREE.CylinderGeometry(r2,r,delta.length(),12),mat,name,a.clone().add(b).multiplyScalar(.5));m.quaternion.setFromUnitVectors(v(0,1,0),delta.normalize());return m;}
function cylinder(p,r,h,pos,mat,name){return part(p,new THREE.CylinderGeometry(r,r,h,40),mat,name,pos);}
function frame(name,pos,yaw){const g=new THREE.Group();g.name=name;g.position.copy(pos);g.rotation.y=yaw;scene.add(g);entities[name]=g;return g;}
function arrangedFrame(name){const angle=layoutAngles[name],radius=layoutRadius-(name==='Bass'?bassInset:name==='Keyboard'?keyboardInset:0),turn=(name==='Bass'?bassLeftTurn:0)-(['Keyboard','Bass'].includes(name)?playerRightTurn:0);return frame(name,v(radius*Math.sin(angle),0,radius*Math.cos(angle)),angle+Math.PI+turn);}
function inverseJoint(start,end,a,b,pole){
 const delta=end.clone().sub(start),distance=delta.length();
 if(distance>a+b+1e-7 || distance<Math.abs(a-b)-1e-7)throw Error(`Unreachable limb: ${distance.toFixed(3)} m for ${a+b} m`);
 const axis=delta.divideScalar(distance),along=(a*a-b*b+distance*distance)/(2*distance);
 const normal=pole.clone().sub(start);normal.addScaledVector(axis,-normal.dot(axis)).normalize();
 return start.clone().addScaledVector(axis,along).addScaledVector(normal,Math.sqrt(Math.max(0,a*a-along*along)));
}
function limb(p,name,start,end,a,b,pole,mat,r){
 const middle=inverseJoint(start,end,a,b,pole);
 rod(p,start,middle,r,mat,name+' upper',r*.91);rod(p,middle,end,r*.82,mat,name+' lower',r*.64);
 ellipsoid(p,middle,[r*.99,r*.99,r*.99],mat,name+' joint');
 bones.push({entity:p,name,start:start.clone(),middle:middle.clone(),end:end.clone(),lengths:[a,b],radius:r});
 return middle;
}
function hand(p,wrist,contact,name){
 const mid=wrist.clone().lerp(contact,.52),dir=contact.clone().sub(wrist).normalize();
 const mesh=ellipsoid(p,mid,[.035,.022,.07],mats.skin,name);mesh.quaternion.setFromUnitVectors(v(0,0,1),dir);
 return mesh;
}
function stool(p,height,name){
 box(p,.45,.055,.32,v(0,height-.0275,-.045),mats.leg,name+' seat');
 for(const x of [-.17,.17])for(const z of [-.16,.065])rod(p,v(x,.018,z),v(x,height-.055,z),.014,mats.metal,name+' leg');
}
function person(p,{standing=false,seat=.50,lean=.06,headTurn=0,hands,name}){
 const hipY=standing?.94:seat+.09,shoulderY=hipY+.52;
 const hip=v(0,hipY,0),shoulderCenter=v(0,shoulderY,lean);
 ellipsoid(p,hip,[.17,.09,.105],mats.leg,name+' pelvis');
 const profile=[[.13,0],[.15,.045],[.155,.13],[.18,.30],[.20,.46],[.195,.52],[.14,.56],[.055,.59]].map(([r,y])=>new THREE.Vector2(r,y));
 const torsoGeo=new THREE.LatheGeometry(profile,32);const pos=torsoGeo.attributes.position;
 for(let i=0;i<pos.count;i++)pos.setZ(i,pos.getZ(i)*.65+lean*pos.getY(i)/.52);
 torsoGeo.computeVertexNormals();part(p,torsoGeo,mats.body,name+' torso',hip);
 rod(p,v(0,shoulderY+.015,lean),v(0,shoulderY+.105,lean+.004),.043,mats.skin,name+' neck');
 const headGroup=new THREE.Group();p.add(headGroup);headGroup.position.set(0,shoulderY+.077+.118*initialHeadScale,lean+.008);headGroup.rotation.y=headTurn;headGroup.scale.setScalar(initialHeadScale);heads.push({group:headGroup,shoulderY});
 ellipsoid(headGroup,v(0,0,0),[.087,.118,.096],mats.skin,name+' head');
 ellipsoid(headGroup,v(0,-.003,.093),[.018,.025,.026],mats.skin,name+' nose');
 for(const s of [-1,1])ellipsoid(headGroup,v(s*.087,-.003,0),[.014,.027,.018],mats.skin,name+' ear');
 const legRecord=[];
 for(const sign of [-1,1]){
   const h=v(sign*.10,hipY,0), ankle=standing?v(sign*.15,.09,.035):v(sign*.12,.09,.514);
   const a=standing?.435:.43,b=standing?.435:.43;
   const pole=standing?v(sign*.25,.49,.20):v(sign*.13,.5,.8);
   const k=limb(p,`${name} ${sign<0?'left':'right'} leg`,h,ankle,a,b,pole,mats.leg,.071);
   box(p,.115,.10,.265,v(ankle.x,.05,ankle.z+.083),mats.leg,name+' shoe');
   legRecord.push({hip:h,knee:k,ankle});
 }
 hands.forEach((spec,index)=>{
   const side=index===0?-1:1, shoulder=v(side*.185,shoulderY,lean);
   ellipsoid(p,shoulder,[.059,.065,.059],mats.body,name+' shoulder');
   const elbow=limb(p,`${name} ${side<0?'left':'right'} arm`,shoulder,spec.wrist,.31,.28,spec.pole,mats.body,.047);
   hand(p,spec.wrist,spec.contact,name+' hand');
   contactData.push({entity:p,name:`${name} ${side<0?'left':'right'} hand`,kind:spec.kind,point:spec.contact.clone(),surface:spec.surface?.clone(),wrist:spec.wrist.clone()});
 });
 contactData.push({entity:p,name:name+' seat / soles',kind:standing?'soles at floor':`pelvis bottom at ${seat.toFixed(2)} m seat`,gap:0});
 return {hip,shoulderCenter,legs:legRecord};
}

// All dimensions below are metres. Forward is local +Z for each musician.
// Keyboard envelope uses Yamaha CP88 published W/D/H, without branded details.
const keys=arrangedFrame('Keyboard');
stool(keys,.50,'keyboard stool');
const keyboardCenter=v(0,.7355,.60);
box(keys,1.298,.141,.364,keyboardCenter,mats.shell,'keyboard case');
const whiteCount=52,keyWidth=1.20/whiteCount;
for(let i=0;i<whiteCount;i++){
 box(keys,keyWidth-.0008,.015,.210,v(-.60+(i+.5)*keyWidth,.8095,.535),mats.white,'white key');
 // A0 to C8: A B C D E F G repeats; no black key after B or E.
 if(i<whiteCount-1 && ![1,4].includes(i%7))box(keys,keyWidth*.56,.014,.115,v(-.60+(i+1)*keyWidth,.824,.584),mats.black,'black key');
}
box(keys,.16,.003,.053,v(-.39,.808,.729),mats.black,'control panel');
for(let i=0;i<4;i++)cylinder(keys,.012,.008,v(.35+i*.045,.812,.73),mats.black,'control knob');
for(const x of [-.43,.43]){
 rod(keys,v(x,.025,.36),v(x,.665,.76),.014,mats.metal,'X stand brace');
 rod(keys,v(x,.025,.83),v(x,.665,.43),.014,mats.metal,'X stand brace');
 rod(keys,v(x,.024,.28),v(x,.024,.9),.018,mats.metal,'stand foot');
 rod(keys,v(x,.653,.42),v(x,.653,.78),.016,mats.metal,'keyboard support');
}
box(keys,.08,.02,.14,v(.12,.01,.64),mats.black,'sustain pedal');
const keyboardPose=person(keys,{name:'keyboardist',hands:[
 {wrist:v(-.16,.855,.389),contact:v(-.16,.839,.50),pole:v(-.48,.91,.16),kind:'white keys',surface:v(-.16,.817,.50)},
 {wrist:v(.16,.855,.389),contact:v(.16,.839,.50),pole:v(.48,.91,.16),kind:'white keys',surface:v(.16,.817,.50)}
]});
clearanceTests.push({entity:keys,type:'keyboard',center:keyboardCenter,size:v(1.298,.141,.364),pose:keyboardPose});

const drums=arrangedFrame('Drums');
stool(drums,.52,'drum throne');
function drum(p,r,depth,center,axis,name){
 const g=new THREE.Group();g.position.copy(center);g.quaternion.setFromUnitVectors(v(0,1,0),axis.clone().normalize());p.add(g);
 cylinder(g,r,depth,v(0,0,0),mats.shell,name+' shell');
 for(const s of [-1,1]){
 cylinder(g,r+.009,.018,v(0,s*depth/2,0),mats.metal,name+' hoop');
 cylinder(g,r-.008,.002,v(0,s*(depth/2+.010),0),mats.head,name+' skin');
 }
 for(let i=0;i<8;i++){let a=i*Math.PI/4;rod(g,v((r+.003)*Math.cos(a),-depth*.38,(r+.003)*Math.sin(a)),v((r+.003)*Math.cos(a),depth*.38,(r+.003)*Math.sin(a)),.006,mats.metal,name+' tension rod');}
 return g;
}
const kick=drum(drums,.2794,.4064,v(.035,.2894,1.0),v(0,0,1),'22-inch kick');
for(const s of [-1,1])rod(drums,v(s*.21,.2,1.12),v(s*.34,.014,1.20),.009,mats.metal,'kick spur');
box(drums,.09,.018,.16,v(.12,.009,.69),mats.black,'kick pedal');
rod(drums,v(.12,.03,.77),v(.11,.25,.80),.006,mats.metal,'beater');
ellipsoid(drums,v(.11,.26,.803),[.026,.032,.018],mats.head,'beater felt');
drum(drums,.1778,.1397,v(-.33,.66,.53),v(0,1,0),'14-inch snare');
rod(drums,v(-.33,.03,.53),v(-.33,.58,.53),.012,mats.metal,'snare stand');
for(let i=0;i<3;i++){let a=i*2*Math.PI/3;rod(drums,v(-.33,.18,.53),v(-.33+.18*Math.cos(a),.012,.53+.18*Math.sin(a)),.009,mats.metal,'snare tripod');}
drum(drums,.127,.20,v(.07,.79,.92),v(0,1,-.16),'10-inch rack tom');
rod(drums,v(.035,.52,1.0),v(.07,.71,.92),.011,mats.metal,'tom mount');
function cymbal(x,z,y,r,name){
 rod(drums,v(x,.02,z),v(x,y+.035,z),.007,mats.metal,name+' stand');
 for(let i=0;i<3;i++){const a=i*2*Math.PI/3;rod(drums,v(x,.21,z),v(x+.23*Math.cos(a),.01,z+.23*Math.sin(a)),.008,mats.metal,name+' tripod');}
 const m=ellipsoid(drums,v(x,y,z),[r,.014,r],mats.metal,name+' disc');
 ellipsoid(drums,v(x,y+.018,z),[.058,.025,.058],mats.metal,name+' bell');
}
cymbal(-.57,.79,1.02,.254,'left cymbal');cymbal(.52,.79,1.08,.254,'ride cymbal');
const sticks=[{grip:v(-.21,.96,.32),tip:v(-.32,.74985,.52)}, {grip:v(.27,1.05,.39),tip:v(.48,1.095,.73)}];
for(const [i,s] of sticks.entries()){const direction=s.tip.clone().sub(s.grip).normalize();rod(drums,s.grip.clone().addScaledVector(direction,-.095),s.tip,.0045,mats.head,'drumstick '+i);}
person(drums,{name:'drummer',seat:.52,headTurn:.22,hands:[
 {wrist:v(-.19,.972,.263),contact:sticks[0].grip,pole:v(-.45,.92,.15),kind:'stick grip'},
 {wrist:v(.24,1.04,.33),contact:sticks[1].grip,pole:v(.5,.92,.13),kind:'stick grip'}
]});

const bass=arrangedFrame('Bass');
const instrument=new THREE.Group();instrument.name='upright bass';instrument.position.set(-.15,0,.36);instrument.rotation.x=-.045;bass.add(instrument);
const outline=new THREE.Shape();
outline.moveTo(0,.27);outline.bezierCurveTo(-.22,.27,-.32,.40,-.30,.60);outline.bezierCurveTo(-.29,.72,-.17,.76,-.17,.84);outline.bezierCurveTo(-.17,.90,-.25,.93,-.23,1.03);outline.bezierCurveTo(-.21,1.15,-.09,1.25,0,1.25);outline.bezierCurveTo(.09,1.25,.21,1.15,.23,1.03);outline.bezierCurveTo(.25,.93,.17,.90,.17,.84);outline.bezierCurveTo(.17,.76,.29,.72,.30,.60);outline.bezierCurveTo(.32,.40,.22,.27,0,.27);
const bassBody=part(instrument,new THREE.ExtrudeGeometry(outline,{depth:.17,bevelEnabled:true,bevelSegments:2,steps:1,bevelSize:.012,bevelThickness:.008,curveSegments:32}),mats.bass,'bass body',v(0,0,-.085));
rod(instrument,v(0,.008,0),v(0,.30,0),.006,mats.metal,'endpin');
ellipsoid(instrument,v(0,.008,0),[.008,.008,.008],mats.black,'endpin foot');
const bassNeck=box(instrument,.051,.60,.048,v(0,1.53,.01),mats.bass,'bass neck');
const neckVertices=bassNeck.geometry.attributes.position;
for(let i=0;i<neckVertices.count;i++)neckVertices.setZ(i,neckVertices.getZ(i)+.031+(1.83-(neckVertices.getY(i)+1.53))*.035/.89);bassNeck.geometry.computeVertexNormals();
const fb=new THREE.Shape();fb.moveTo(-.052,.94);fb.lineTo(.052,.94);fb.lineTo(.025,1.83);fb.lineTo(-.025,1.83);fb.closePath();
const fingerboard=part(instrument,new THREE.ExtrudeGeometry(fb,{depth:.018,bevelEnabled:false}),mats.black,'fingerboard',v(0,0,.065));
const fbVertices=fingerboard.geometry.attributes.position;
for(let i=0;i<fbVertices.count;i++)fbVertices.setZ(i,fbVertices.getZ(i)+(1.83-fbVertices.getY(i))*.035/.89);fingerboard.geometry.computeVertexNormals();
ellipsoid(instrument,v(0,1.91,.02),[.048,.072,.04],mats.bass,'scroll');
for(const y of [1.86,1.90])for(const x of [-.055,.055])rod(instrument,v(x*.5,y,.014),v(x,y,.014),.009,mats.metal,'tuning peg');
box(instrument,.11,.064,.017,v(0,.69,.117),mats.head,'bridge');
const tail=new THREE.Shape();tail.moveTo(-.045,.52);tail.lineTo(.045,.52);tail.lineTo(.016,.34);tail.lineTo(-.016,.34);tail.closePath();
part(instrument,new THREE.ExtrudeGeometry(tail,{depth:.018,bevelEnabled:false}),mats.black,'tailpiece',v(0,0,.096));
for(let i=0;i<4;i++){
 const x=(i-1.5)*.012;
 rod(instrument,v(x,.37,.118),v(x,.72,.136),.0008,mats.string,'string tail');
 rod(instrument,v(x,.72,.136),v(x,1.85,.087),.0008,mats.string,'string');
}
// Targets are derived from instrument-local string positions, not screen coordinates.
instrument.updateMatrix();
const stringPoint=(y,z)=>v(0,y,z).applyMatrix4(instrument.matrix);
const leftTouch=stringPoint(1.55,.104),rightTouch=stringPoint(1.09,.128);
const leftWrist=leftTouch.clone().add(v(-.065,0,-.015));
const rightWrist=rightTouch.clone().add(v(.074,.012,.065));
const bassPose=person(bass,{name:'bassist',standing:true,lean:.16,headTurn:-.12,hands:[
 {wrist:leftWrist,contact:leftTouch,pole:v(-.60,1.21,.42),kind:'fingerboard strings',surface:leftTouch.clone()},
 {wrist:rightWrist,contact:rightTouch,pole:v(.64,1.05,.80),kind:'plucking strings',surface:rightTouch.clone()}
]});

const guide=new THREE.Group();scene.add(guide);
const guideColor=new THREE.Color(readColor('--blue','#367ac0'));
const guideMat=new THREE.LineDashedMaterial({color:guideColor,transparent:true,opacity:.48,dashSize:.065,gapSize:.04,depthWrite:false});
const circlePoints=Array.from({length:121},(_,i)=>v(layoutRadius*Math.sin(i*Math.PI/60),.004,layoutRadius*Math.cos(i*Math.PI/60)));
const circleLine=new THREE.Line(new THREE.BufferGeometry().setFromPoints(circlePoints),guideMat);circleLine.computeLineDistances();guide.add(circleLine);
for(const entity of Object.values(entities)){
 const point=v(entity.position.x,.006,entity.position.z);
 const spoke=new THREE.Line(new THREE.BufferGeometry().setFromPoints([v(0,.006,0),point]),guideMat);spoke.computeLineDistances();guide.add(spoke);
}
scene.updateMatrixWorld(true);
for(const b of bones){
 const points=[b.start,b.middle,b.end].map(p=>b.entity.localToWorld(p.clone()));
 const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),skelMat);line.renderOrder=30;line.userData.entity=b.entity.name;skeleton.add(line);
 for(const p of points){const d=new THREE.Mesh(new THREE.SphereGeometry(.019,12,8),dotMat);d.position.copy(p);d.renderOrder=31;d.userData.entity=b.entity.name;skeleton.add(d);}
}

let azimuth=0,elevation=.30,span=3.30;
const presets={icon:[0,.30,3.30],quarter:[-.72,.39,3.30],top:[0,Math.PI/2-.001,4.10],keyboard:[Math.PI/6,.13,3.20],left:[-Math.PI/2,.13,3.20],bass:[Math.PI/2,.13,3.20],rear:[Math.PI,.23,3.50]};
function draw(){const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h,false);const ratio=w/h,visibleSpan=span*Math.max(1,1.10/ratio);camera.left=-visibleSpan*ratio/2;camera.right=visibleSpan*ratio/2;camera.top=visibleSpan/2;camera.bottom=-visibleSpan/2;camera.updateProjectionMatrix();camera.position.set(target.x+8*Math.sin(azimuth)*Math.cos(elevation),target.y+8*Math.sin(elevation),target.z+8*Math.cos(azimuth)*Math.cos(elevation));camera.up.set(0,1,0);camera.lookAt(target);renderer.render(scene,camera);}
function updateSelection(){
 const selected=root.querySelector('[data-entity]').value;
 for(const [name,g] of Object.entries(entities))g.visible=selected==='all'||name===selected;
 if(selected==='all')target.set(0,.93,0);else new THREE.Box3().setFromObject(entities[selected]).getCenter(target);
 skeleton.visible=root.querySelector('[data-joints]').checked;
 guide.visible=root.querySelector('[data-guide]').checked&&selected==='all';
 for(const child of skeleton.children)child.visible=selected==='all'||child.userData.entity===selected;
 for(const mat of Object.values(mats)){mat.transparent=skeleton.visible;mat.opacity=skeleton.visible?.22:1;mat.depthWrite=!skeleton.visible;mat.needsUpdate=true;}
}
function view(name){[azimuth,elevation,span]=presets[name];if(root.querySelector('[data-entity]').value!=='all')span*=.75;root.querySelector('[data-view]').value=name;updateSelection();draw();}
root.querySelector('[data-view]').addEventListener('change',e=>view(e.target.value));
root.querySelector('[data-joints]').addEventListener('change',()=>{updateSelection();draw();});
root.querySelector('[data-entity]').addEventListener('change',()=>view(root.querySelector('[data-view]').value));
root.querySelector('[data-guide]').addEventListener('change',()=>{updateSelection();draw();});
root.querySelector('[data-head]').addEventListener('input',e=>{
 const scale=Number(e.target.value);for(const head of heads){head.group.scale.setScalar(scale);head.group.position.y=head.shoulderY+.077+.118*scale;}
 root.querySelector('[data-head-value]').textContent=scale.toFixed(2)+'×';
 if(window.__jazz3d)window.__jazz3d.report.head_scale=scale;
 scene.updateMatrixWorld(true);updateSelection();draw();
});
let drag=null;
renderer.domElement.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY};renderer.domElement.setPointerCapture(e.pointerId);});
renderer.domElement.addEventListener('pointermove',e=>{if(!drag)return;azimuth-=(e.clientX-drag.x)*.007;elevation=Math.max(.035,Math.min(Math.PI/2-.001,elevation+(e.clientY-drag.y)*.006));drag={x:e.clientX,y:e.clientY};draw();});
renderer.domElement.addEventListener('pointerup',()=>drag=null);renderer.domElement.addEventListener('pointercancel',()=>drag=null);
renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();span=Math.max(2.3,Math.min(6.5,span*Math.exp(e.deltaY*.001)));draw();},{passive:false});
new ResizeObserver(draw).observe(host);
function refreshTheme(){
 bg.set(readColor('--background','#f5f5f5'));fg.set(readColor('--foreground','#272727'));
 const levels={body:.35,skin:.25,leg:.49,joint:.58,metal:.62,shell:.46,head:.10,black:.88,white:.015,bass:.39,string:.10};
 for(const [name,level] of Object.entries(levels))mats[name].color.copy(tone(level));
 ground.material.color.copy(tone(.045));
 const positions=grid.geometry.attributes.position,colors=grid.geometry.attributes.color;
 for(let i=0;i<positions.count;i++){const x=positions.getX(i),z=positions.getZ(i);const c=tone(x===0||z===0?.16:.095);colors.setXYZ(i,c.r,c.g,c.b);}colors.needsUpdate=true;
 skelMat.color.set(readColor('--blue','#367ac0'));dotMat.color.copy(skelMat.color);guideMat.color.copy(skelMat.color);draw();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',refreshTheme);
new MutationObserver(refreshTheme).observe(document.documentElement,{attributes:true,attributeFilter:['class','style','data-theme']});
const report={units:'metres',head_scale:initialHeadScale,arrangement:{reference_radius:layoutRadius,bearing_spacing_degrees:120,bass_inward_offset:bassInset,keyboard_inward_offset:keyboardInset,bass_left_turn_degrees:90,subsequent_right_turn_degrees:{Keyboard:20,Bass:20},positions:Object.fromEntries(Object.entries(entities).map(([name,g])=>[name,{position:g.position.toArray(),radius:Math.hypot(g.position.x,g.position.z),yaw:g.rotation.y}]))},keyboard:{width:1.298,depth:.364,height:.141,keySurface:.817},limbs:bones.map(b=>({name:b.name,entity:b.entity.name,nominal:b.lengths,actual:[b.start.distanceTo(b.middle),b.middle.distanceTo(b.end)],joints:[b.start,b.middle,b.end].map(p=>p.toArray())})),contacts:contactData.map(c=>({name:c.name,kind:c.kind,gap:c.gap,point:c.point?.toArray(),surface:c.surface?.toArray()}))};
window.__jazz3d={scene,camera,renderer,entities,bones,mats,report,view,draw,clearanceTests,bassBody,instrument,THREE,skeleton,heads,guide};
root.dataset.ready='true';draw();
