// Human anatomy and skin weights: Quaternius Universal Base Characters, CC0.
// See assets/License_Standard.txt. Poses and illustration treatments are local.
import {GLTFLoader} from '/loaders/GLTFLoader.js';
export async function extend(api){
 const {THREE,C}=api,{model,group,box,ball,cyl,rod,tube,plate,disk,mesh,mat}=api.helpers;
 const loader=new GLTFLoader();
 const V=a=>new THREE.Vector3(...a);
 async function person(g,{female=true,shirt=C.teal,pants=C.purple,skin=C.skin,pose='chair'}={}){
  const asset=await loader.loadAsync('/assets/Superhero_'+(female?'Female':'Male')+'_FullBody.gltf');
  const rig=asset.scene,bones={};rig.updateMatrixWorld(true);
  rig.traverse(o=>{if(o.isBone)bones[o.name]=o;});
  const wp=n=>bones[n].getWorldPosition(new THREE.Vector3());
  const rest=Object.fromEntries(Object.keys(bones).map(n=>[n,wp(n).toArray()]));
  // Attach hair and restrained face marks to the actual head bone in rest space.
  const hair=await loader.loadAsync('/assets/'+(female?'Hair_Buns':'Hair_SimpleParted')+'.gltf');
  rig.add(hair.scene);rig.updateMatrixWorld(true);bones.Head.attach(hair.scene);
  hair.scene.traverse(o=>{if(o.isMesh)o.userData.paint='#564437';});
  const face=new THREE.Group();rig.add(face);
  const body=rig.getObjectByName(female?'Superhero_Female':'SuperHero_Male');body.skeleton.update();
  const surface=(x,y)=>new THREE.Raycaster(V([x,y,2]),V([0,0,-1])).intersectObject(body)[0]?.point.z ?? .09;
  const fy=female?1.65:1.724,fz=female?.070:.082;
  for(const x of [-.039,.039]){const e=disk(face,x,fy,surface(x,fy)+.003,.0075,'#513c31');e.userData.eye=true;}
  tube(face,[-1,-.5,0,.5,1].map(t=>{const x=t*.022,y=fy-.051+t*t*.005;return [x,y,surface(x,y)+.004];}),.004,'#895443',true,true);
  rig.updateMatrixWorld(true);bones.Head.attach(face);bones.Head.scale.setScalar(1.45);
  function orient(name,child,dir){
   rig.updateMatrixWorld(true);const b=bones[name],q=b.getWorldQuaternion(new THREE.Quaternion());
   const delta=new THREE.Quaternion().setFromUnitVectors(wp(child).sub(wp(name)).normalize(),V(dir).normalize());
   b.quaternion.copy(b.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(delta.multiply(q)));rig.updateMatrixWorld(true);
  }
  function movePelvis(to){bones.pelvis.position.copy(bones.pelvis.parent.worldToLocal(V(to)));rig.updateMatrixWorld(true);}
  function chain(a,b,c,target,bend){
   const A=wp(a),B=wp(b),D=wp(c),T=V(target),l1=A.distanceTo(B),l2=B.distanceTo(D),axis=T.clone().sub(A),distance=axis.length();
   if(distance>l1+l2+1e-4||distance<Math.abs(l1-l2))throw Error('Unreachable '+pose+' '+a+' target '+distance+' / '+(l1+l2));
   axis.normalize();const u=(l1*l1-l2*l2+distance*distance)/(2*distance),v=V(bend);v.addScaledVector(axis,-v.dot(axis)).normalize();
   const joint=A.clone().addScaledVector(axis,u).addScaledVector(v,Math.sqrt(Math.max(0,l1*l1-u*u)));
   orient(a,b,joint.clone().sub(A).toArray());orient(b,c,T.clone().sub(wp(b)).toArray());
  }
  const checks=[];
  if(pose==='partner'){
   movePelvis([0,.84,0]);
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('thigh_'+side,'calf_'+side,'foot_'+side,[sign*.19,.09,side==='l'?.08:-.07],[0,0,1]);orient('foot_'+side,'ball_'+side,[sign*.05,-.056,.13]);
    chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[sign*.20,1.22,.40],[sign,-1,0]);orient('hand_'+side,'middle_01_'+side,[0,0,1]);
   }
  }
  if(pose==='contemporary'){
   movePelvis([0,.86,0]);
   chain('thigh_l','calf_l','foot_l',[.12,.08,.04],[1,0,1]);orient('foot_l','ball_l',[.13,-.04,.06]);
   chain('thigh_r','calf_r','foot_r',[-.55,.34,-.03],[-1,0,1]);orient('foot_r','ball_r',[-.13,-.05,.03]);
   chain('upperarm_l','lowerarm_l','hand_l',[.34,1.67,.03],[1,0,1]);orient('hand_l','middle_01_l',[.2,1,0]);
   chain('upperarm_r','lowerarm_r','hand_r',[-.54,1.18,.06],[-1,-1,0]);orient('hand_r','middle_01_r',[-1,.2,0]);
  }
  if(pose==='chair'){
   movePelvis([0,.63,-.0457]);
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('thigh_'+side,'calf_'+side,'foot_'+side,[sign*.14,.071,.38],[0,0,1]);
    orient('foot_'+side,'ball_'+side,[0,-.056,.138]);
    const shoulder=wp('upperarm_'+side);
    chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[sign*.15,shoulder.y+.43,.01],[sign,0,0]);
    orient('hand_'+side,'middle_01_'+side,[-sign*.3,1,0]);
   }
  }
  if(pose==='pilates'){
   movePelvis([0,.16,0]);
   const b=bones.pelvis,q=b.getWorldQuaternion(new THREE.Quaternion()),delta=new THREE.Quaternion().setFromAxisAngle(V([1,0,0]),-.55);
   b.quaternion.copy(b.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(delta.multiply(q)));rig.updateMatrixWorld(true);
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('thigh_'+side,'calf_'+side,'foot_'+side,[sign*.11,.58,.69],[0,-1,1]);orient('foot_'+side,'ball_'+side,[0,.15,.10]);
    const shoulder=wp('upperarm_'+side);chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[sign*.18,.48,.17],[0,-1,1]);orient('hand_'+side,'middle_01_'+side,[0,0,1]);
   }
  }
  if(pose==='tai-chi'){
   movePelvis([0,.72,0]);
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('thigh_'+side,'calf_'+side,'foot_'+side,[sign*.54,.071,.05],[sign,.1,1]);orient('foot_'+side,'ball_'+side,[sign*.05,-.056,.13]);
    const shoulder=wp('upperarm_'+side);chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[sign*.40,side==='l'?1.25:1.05,.28],[sign,-1,0]);orient('hand_'+side,'middle_01_'+side,[0,.3,1]);
   }
  }
  if(pose==='pole'){
   movePelvis([.02,.76,.05]);
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('thigh_'+side,'calf_'+side,'foot_'+side,side==='l'?[.30,.09,.04]:[-.53,.071,.03],[sign,.2,1]);orient('foot_'+side,'ball_'+side,[sign*.06,-.06,.13]);
    chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[.34,side==='l'?1.54:1.22,.07],[sign,0,1]);orient('hand_'+side,'middle_01_'+side,[0,.8,-.25]);
    for(const finger of ['index','middle','ring','pinky'])for(const n of ['01','02','03'])bones[finger+'_'+n+'_'+side].rotateX(.7);
   }
  }
  if(pose==='drawing'){
   for(const side of ['l','r']){const sign=side==='l'?1:-1;
    chain('upperarm_'+side,'lowerarm_'+side,'hand_'+side,[sign*.27,1.10,.03],[sign,0,1]);orient('hand_'+side,'middle_01_'+side,[0,-1,0]);
    chain('thigh_'+side,'calf_'+side,'foot_'+side,[sign*.18,.105,.02],[0,0,1]);orient('foot_'+side,'ball_'+side,[sign*.03,-.056,.138]);
   }
  }
  for(const side of ['l','r'])for(const chainNames of [['upperarm_','lowerarm_','hand_'],['thigh_','calf_','foot_']]){
   const names=chainNames.map(n=>n+side);checks.push({bones:names,positions:names.map(n=>wp(n).toArray()),lengths:[wp(names[0]).distanceTo(wp(names[1])),wp(names[1]).distanceTo(wp(names[2]))]});
  }
  g.userData.checks={asset:'Quaternius CC0 Universal Base Characters',pose,rest,posed:checks};
  // The source remains skinned while posing. Bake only after all bone edits.
  rig.updateMatrixWorld(true);rig.traverse(o=>{if(o.isSkinnedMesh)o.skeleton.update();});
  const view=group(g);view.scale.setScalar(50);
  rig.traverse(o=>{if(!o.isSkinnedMesh||!o.name.toLowerCase().startsWith('superhero'))return;
   const geo=o.geometry.clone(),pos=geo.attributes.position,p=new THREE.Vector3(),old=new THREE.Vector3();
   const restPositions=[];
   for(let i=0;i<pos.count;i++){
    old.fromBufferAttribute(o.geometry.attributes.position,i).applyMatrix4(o.matrixWorld);
    restPositions.push(old.x,old.y,old.z);
    o.getVertexPosition(i,p).applyMatrix4(o.matrixWorld);pos.setXYZ(i,p.x,p.y,p.z);
   }
   geo.clearGroups();geo.setAttribute('restPosition',new THREE.Float32BufferAttribute(restPositions,3));geo.computeVertexNormals();geo.computeBoundingBox();geo.computeBoundingSphere();
   const paint=new THREE.ShaderMaterial({side:THREE.DoubleSide,uniforms:{skin:{value:new THREE.Color(skin)},shirt:{value:new THREE.Color(shirt)},pants:{value:new THREE.Color(pants)},neckCut:{value:rest.neck_01[1]-.01},sleeveCut:{value:Math.abs(rest.upperarm_l[0])+.12},waist:{value:rest.pelvis[1]+.12}},
    vertexShader:'attribute vec3 restPosition; varying vec3 rp; varying vec3 n;void main(){rp=restPosition;n=normalize(mat3(modelMatrix)*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader:'uniform vec3 skin,shirt,pants;uniform float neckCut,sleeveCut,waist;varying vec3 rp;varying vec3 n;void main(){vec3 c=skin;if(rp.y>.095&&rp.y<waist){float shade=dot(normalize(n),normalize(vec3(-.7,1.,1.5)))>.0?1.:.8;c=pants*shade;}else if(rp.y>=waist&&rp.y<neckCut&&abs(rp.x)<sleeveCut)c=shirt;gl_FragColor=vec4(pow(c,vec3(1./2.2)),1.);}'
   });view.add(new THREE.Mesh(geo,paint));
  });
  if(pose==='pilates')view.rotation.y=Math.PI/2;
  // Static hair and face geometry inherits the posed head transform.
  rig.traverse(o=>{if(!o.isMesh||o.isSkinnedMesh)return;const geo=o.geometry.clone();geo.applyMatrix4(o.matrixWorld);const m=new THREE.Mesh(geo,o.userData.paint?mat(o.userData.paint,true):o.material);m.userData={...o.userData};if(o.userData.eye){geo.computeBoundingSphere();m.position.copy(geo.boundingSphere.center);geo.translate(-m.position.x,-m.position.y,-m.position.z);}view.add(m);});
  if(pose==='pilates'){view.updateMatrixWorld(true);const bounds=new THREE.Box3().setFromObject(view);view.position.y-=bounds.min.y;}
  return view;
 }
 {const g=model('dance-partner',[.18,.08,1]);const left=group(g,[-20,0,0],[0,Math.PI/2,0]);const a=await person(left,{pose:'partner',female:false,shirt:'#54ACB3',pants:'#4C6688',skin:'#BE855F'});const right=group(g,[20,0,0],[0,-Math.PI/2,0]);const b=await person(right,{pose:'partner',female:true,shirt:'#E17A93',pants:'#915C9F',skin:'#EDBC98'});}
 {const g=model('dance-contemporary',[.18,.06,1]);await person(g,{pose:'contemporary',female:true,shirt:'#57AFB3',pants:'#7862AA'});}
}
