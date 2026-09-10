// Original, inspectable geometry for the September 9 feedback batch.
// X right, Y up, Z toward the front of the object. No screen-space pose edits.
import {glyphs} from './glyphs.js';
export function createModels(THREE) {
  const V = (a) => new THREE.Vector3(...a);
  const C = {ink:'#354451', metal:'#849BA6', pale:'#D8E3E5', cream:'#F5EADB', wood:'#C58A52', gold:'#F3BD48', teal:'#38A99B', purple:'#8B65BA', skin:'#E8B58C'};
  const materials = new Map();
  function mat(color, flat=false) {
    const key=color+flat;
    if (!materials.has(key)) {
      if(flat) materials.set(key,new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide}));
      else materials.set(key,new THREE.ShaderMaterial({side:THREE.DoubleSide, uniforms:{paint:{value:new THREE.Color(color)}},
        vertexShader:'varying vec3 n; void main(){n=normalize(mat3(modelMatrix)*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
        fragmentShader:'uniform vec3 paint; varying vec3 n; void main(){float l=dot(normalize(n),normalize(vec3(-.7,1.,1.5))); float s=l>.6?1.:l>-.1?.82:.63;gl_FragColor=vec4(pow(paint*s,vec3(1./2.2)),1.);}' }));
    }
    return materials.get(key);
  }
  function mesh(g,geo,color,pos=[0,0,0],flat=false) {const m=new THREE.Mesh(geo,mat(color,flat));m.position.set(...pos);g.add(m);return m;}
  function box(g,x,y,z,w,h,d,color=C.wood) {return mesh(g,new THREE.BoxGeometry(w,h,d),color,[x,y,z]);}
  function ball(g,p,r,color,scale=[1,1,1],flat=false) {const m=mesh(g,new THREE.SphereGeometry(r,40,28),color,p,flat);m.scale.set(...scale);return m;}
  function cyl(g,p,r,h,color,r2=r) {return mesh(g,new THREE.CylinderGeometry(r,r2,h,48),color,p);}
  function rod(g,a,b,r,color,flat=false) {const va=V(a),vb=V(b);const m=mesh(g,new THREE.CylinderGeometry(r,r,va.distanceTo(vb),20),color,va.clone().add(vb).multiplyScalar(.5).toArray(),flat);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),vb.sub(va).normalize());return m;}
  function tube(g,points,r,color,smooth=true,flat=false) {const p=points.map(V);const curve=smooth?new THREE.CatmullRomCurve3(p):new THREE.CurvePath();if(!smooth)for(let i=1;i<p.length;i++)curve.add(new THREE.LineCurve3(p[i-1],p[i]));return mesh(g,new THREE.TubeGeometry(curve,Math.max(24,points.length*10),r,10,false),color,[0,0,0],flat);}
  function path(d) {
    const s=new THREE.Shape(),t=d.match(/[a-zA-Z]|[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?/g);let i=0,c,x=0,y=0,sx=0,sy=0;
    while(i<t.length){if(/[a-z]/i.test(t[i]))c=t[i++];const rel=c===c.toLowerCase(),cmd=c.toUpperCase(),ox=x,oy=y;
      const n=()=>Number(t[i++]),pt=()=>[n()+(rel?ox:0),n()+(rel?oy:0)];
      if(cmd==='Z'){s.closePath();x=sx;y=sy;c='';continue;}
      if(cmd==='M'||cmd==='L'){[x,y]=pt();s[cmd==='M'?'moveTo':'lineTo'](x,y);if(cmd==='M'){sx=x;sy=y;c=rel?'l':'L';}}
      else if(cmd==='H'){x=n()+(rel?x:0);s.lineTo(x,y);}
      else if(cmd==='V'){y=n()+(rel?y:0);s.lineTo(x,y);}
      else if(cmd==='C'){const a=pt(),b=pt();[x,y]=pt();s.bezierCurveTo(...a,...b,x,y);}
      else if(cmd==='Q'){const a=pt();[x,y]=pt();s.quadraticCurveTo(...a,x,y);}
      else throw Error('Unsupported shape command '+c);
    }return s;
  }
  function plate(g,d,z,color,depth=0,flat=false) {const s=typeof d==='string'?path(d):d;return mesh(g,depth?new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:20}):new THREE.ShapeGeometry(s,24),color,[0,0,z],flat);}
  function disk(g,x,y,z,r,color,rx=1,ry=1) {const m=mesh(g,new THREE.CircleGeometry(r,48),color,[x,y,z],true);m.scale.set(rx,ry,1);return m;}
  function ring(g,x,y,z,r,thick,color){return mesh(g,new THREE.RingGeometry(r-thick,r,48),color,[x,y,z],true);}
  function lathe(g,p,profile,color){return mesh(g,new THREE.LatheGeometry(profile.map(a=>new THREE.Vector2(...a)),48),color,p);}
  function group(g,p=[0,0,0],rot=[0,0,0]) {const n=new THREE.Group();n.position.set(...p);n.rotation.set(...rot);g.add(n);return n;}
  function topDisk(g,x,y,z,r,color){const m=disk(g,x,y,z,r,color);m.rotation.x=-Math.PI/2;return m;}
  function surfaceRect(g,x,y,z,w,h,color){return box(g,x,y,z,w,.12,h,color);}
  function keys(g,x,y,z,w,depth,n=14){box(g,x,y-1,z,w,2,depth,C.cream);const step=w/n;for(let i=1;i<n;i++)rod(g,[x-w/2+i*step,y+.1,z-depth/2],[x-w/2+i*step,y+.1,z+depth/2],.23,'#A99586',true);for(let i=0;i<n;i++)if([0,1,3,4,5].includes(i%7)&&i<n-1)box(g,x-w/2+(i+1)*step,y+1,z-depth*.22,step*.56,2,depth*.55,C.ink);}
  function text(g,word,x,y,z,size,color,face='front') {
    let advance=0;
    for(const c of word){const glyph=glyphs[c];if(!glyph)continue;
      const contours=glyph.path.match(/M[^M]+/g).map(path);
      const area=s=>THREE.ShapeUtils.area(s.getPoints(16));
      const outerSign=Math.sign(area(contours.reduce((a,b)=>Math.abs(area(a))>Math.abs(area(b))?a:b)));
      const outlines=contours.filter(s=>Math.sign(area(s))===outerSign);
      for(const hole of contours.filter(s=>Math.sign(area(s))!==outerSign))outlines[0].holes.push(hole);
      const m=mesh(g,new THREE.ShapeGeometry(outlines,12),color,[x+advance*size,y,z],true);m.scale.setScalar(size);if(face==='top')m.rotation.x=-Math.PI/2;
      advance+=glyph.advance+.15;
    }
  }

  function note(g,x,y,z,s,color=C.ink){disk(g,x,y,z,s,color,1.25,.75);rod(g,[x+s,y,z],[x+s,y+s*5,z],s*.35,color,true);plate(g,`M${x+s} ${y+s*5}q${s*4} ${-s} ${s*2} ${-s*3}l${-s*.2} ${s*1.7}q${-s} ${s*.2} ${-s*1.8} ${s*.3}Z`,z,color,0,true);}
  const models={};
  function model(id,camera=[.36,.3,1]){const root=new THREE.Group();root.userData={id,camera};models[id]=root;return root;}

  // Six-string guitar and four-string soprano: body length ~half total length,
  // restrained waists and instrument-specific neck/upper-bout proportions.
  function guitar(g,ukulele=false){
    const b=group(g,[0,0,0],[0,0,-.65]);
    const d=ukulele?'M0 0C-14 0-19 7-18 17C-18 24-12 28-12 34C-12 39-17 41-16 48C-15 56-7 58 0 58C7 58 15 56 16 48C17 41 12 39 12 34C12 28 18 24 18 17C19 7 14 0 0 0Z':'M0 0C-18 0-24 8-23 21C-22 31-14 35-14 41C-14 47-20 48-19 56C-18 65-9 68 0 68C9 68 18 65 19 56C20 48 14 47 14 41C14 35 22 31 23 21C24 8 18 0 0 0Z';
    const join=ukulele?58:68,nut=ukulele?96:113,head=nut+17;
    plate(b,d,-5,ukulele?'#BD8155':'#DEA661',9);
    const front=plate(b,d,4.1,ukulele?'#D59962':'#F1C582',0,true);
    box(b,0,(join+nut)/2,3,7,nut-join+10,6,'#6B4834');
    box(b,0,(join+nut)/2-2,6.2,7,nut-join+14,1,'#523B32');
    plate(b,`M-4 ${nut}L-6 ${head-3}Q0 ${head+1} 6 ${head-3}L4 ${nut}Z`,1,'#AF734B',5);
    const soundY=ukulele?39:46;disk(b,0,soundY,4.3,ukulele?6.8:8,'#744D31');ring(b,0,soundY,4.4,ukulele?7.8:9.2,1,'#F9DEAA');
    box(b,0,ukulele?19:22,5,14,4,2,'#70442E');box(b,0,ukulele?20:23,6.1,10,.9,.5,C.cream);
    const strings=ukulele?4:6;for(let i=0;i<strings;i++){const x=(i-(strings-1)/2)*.85;rod(b,[x,nut,7],[x,ukulele?19:22,6.6],.17,'#F4E2BE',true);}
    for(let i=0;i<9;i++){const yy=nut-(nut-(ukulele?21:24))*(1-Math.pow(2,-(i+1)/12));rod(b,[-3.4,yy,6.9],[3.4,yy,6.9],.24,'#C6B0A0',true);}
    for(const side of [-1,1])for(let i=0;i<(ukulele?2:3);i++){const yy=nut+5+i*4.5;rod(b,[side*3,yy,3],[side*8,yy,3],.7,C.metal);ball(b,[side*8,yy,3],1.6,C.pale,[1,1.2,.5]);}
    box(b,0,nut,6.7,7,1,.6,C.cream);
  }
  guitar(model('instrument-acoustic-guitar',[.22,.13,1]));guitar(model('instrument-ukulele',[.22,.13,1]),true);
  function bowed(g,bass=false,tilt=-.20,violin=false){const b=group(g,[0,0,0],[0,0,tilt]);
    const d=bass?'M0 5C-15 5-23 12-23 26C-23 36-15 41-13 47C-11 53-18 58-17 66C-16 77-8 81-5 88H5C8 81 16 77 17 66C18 58 11 53 13 47C15 41 23 36 23 26C23 12 15 5 0 5Z':'M0 6C-15 6-23 13-22 25C-22 33-17 39-13 44L-16 47C-8 48-8 57-16 59L-13 62C-19 70-19 78-11 82C-6 85 6 85 11 82C19 78 19 70 13 62L16 59C8 57 8 48 16 47L13 44C17 39 22 33 22 25C23 13 15 6 0 6Z';
    plate(b,d,-4,bass?'#A75F3D':'#B8733E',9);plate(b,d,5.1,bass?'#CE8851':'#DB9859',0,true);
    box(b,0,97,3,6,36,5,'#8B5639');plate(b,'M-4 53H4L3 117H-3Z',6,'#393833',1);
    plate(b,'M-5 19H5L2 39H-2Z',6,'#38352F',2);box(b,0,40,8,12,2,2,C.cream);
    const scroll=cyl(b,[0,121,3],3,6,'#A96B3F');scroll.rotation.x=Math.PI/2;disk(b,0,121,6.2,2,'#6C4531');
    for(const side of [-1,1])for(let i=0;i<2;i++)rod(b,[side*2,111+i*5,3],[side*7,111+i*5,3],1.2,C.ink);
    for(let i=0;i<4;i++)rod(b,[(i-1.5)*.9,116,7.2],[(i-1.5)*1.2,22,8.2],.19,'#F5DEB8',true);
    for(const side of [-1,1])tube(b,[[side*7,58,5.4],[side*8,55,5.4],[side*6.5,48,5.4],[side*8,44,5.4]],.65,'#683C29',true,true);
    if(!violin)rod(b,[0,5,0],[0,-9,0],.9,C.metal);
  }
  bowed(model('instrument-cello',[.18,.13,1]));bowed(model('instrument-double-bass',[.23,.12,1]),true);

  // Machines: all controls, keys and beds share their supporting surface planes.
  {const g=model('equipment-audio-mixing-console',[.35,.8,1]);box(g,0,6,0,96,12,60,C.ink);for(let i=0;i<6;i++){const x=-38+i*15;for(let j=0;j<2;j++)cyl(g,[x,13,-19+j*10],2.7,2,j?C.gold:C.teal);surfaceRect(g,x,12.2,12,2,23,'#171F29');box(g,x,14,4+(i%3)*5,9,3,5,C.pale);}surfaceRect(g,0,12.2,-26,79,3,'#74CFC2');}
  {const g=model('instrument-synthesizer',[.30,.72,1]);box(g,0,5,0,105,10,43,'#4E6272');keys(g,5,11,9,86,22);for(let i=0;i<5;i++)cyl(g,[-24+i*11,11.5,-12],2,2,i%2?C.teal:C.gold);surfaceRect(g,30,10.2,-12,20,8,'#83D3D5');box(g,-47,11,8,4,2,12,'#27333F');}
  {const g=model('instrument-hammond-organ',[.4,.60,1]);box(g,0,34,0,100,27,45,'#98603E');box(g,0,59,-18,100,23,12,'#98603E');box(g,0,71,-18,103,6,16,'#BA8253');keys(g,0,65,-2,87,18);keys(g,0,51,15,87,18);for(const x of [-47,47])box(g,x,57,0,6,21,43,'#AF754B');box(g,0,22,0,100,6,45,'#714A36');for(const x of [-43,43])for(const z of [-14,16])box(g,x,9,z,7,22,7,'#714A36');for(let i=0;i<8;i++)box(g,-25+i*7,75,-18,2,3,8,i%2?C.cream:C.ink);}
  {const g=model('instrument-harmonium',[.55,.46,1]);box(g,0,14,0,83,28,42,'#AC6C40');keys(g,0,29,9,72,17);box(g,0,31,-7,83,6,14,'#D6995D');for(let i=0;i<6;i++)ball(g,[-29+i*11,23,22],2,C.cream,[1,1,.6]);
    // Side-opening bellows: one hinge line, increasing opening toward the right.
    for(let i=0;i<6;i++){const y=35+i*2.4;plate(g,`M-40 34L40 ${y+4}L40 ${y+6}L-40 35Z`,-19,i%2?'#875242':'#E5B576',23);}
    plate(g,'M-42 36L42 54L42 58L-42 40Z',-21,'#AD7548',27);
  }
  {const g=model('3d-printing',[.42,.22,1]);box(g,0,4,0,77,8,61,C.ink);box(g,0,74,0,77,9,61,C.metal);box(g,0,39,-28,77,63,5,'#4C6068');for(const x of [-35,35])box(g,x,39,0,7,65,58,'#526772');box(g,0,23,2,61,4,49,'#4AA4C8');box(g,0,57,5,61,5,5,C.metal);box(g,4,49,5,12,15,12,C.ink);cyl(g,[4,39,5],2,5,C.gold,.8);for(let i=0;i<4;i++)box(g,4,26+i*2,5,23-i*4,2,20-i*4,'#F8C052');surfaceRect(g,23,8.2,20,13,7,'#6BBAC9');}
  {const g=model('equipment-digital-cutting-machine',[.3,.45,1]);box(g,0,12,0,95,24,34,'#67AFAF');box(g,0,24,-9,95,7,18,'#B7E3DA');box(g,0,14,18,85,13,2,C.ink);rod(g,[-40,17,19],[40,17,19],1.5,C.pale);box(g,12,16,21,9,12,6,C.pale);box(g,0,6,32,70,1,33,'#9ED09E');box(g,0,6.8,35,42,.5,24,C.cream);surfaceRect(g,0,7.2,35,22,14,'#EBA3AA');}
  {const g=model('equipment-laser-cutter',[.35,.5,1]);box(g,0,10,0,95,20,64,'#5D8697');box(g,0,21,0,76,2,49,C.ink);box(g,0,23,0,64,1,38,'#D4AC77');rod(g,[-34,29,0],[34,29,0],2,C.pale);box(g,8,27,0,10,9,10,'#D76C59');rod(g,[8,22,0],[8,24,0],.8,'#F88F51');const lid=group(g,[0,22,-29],[-.8,0,0]);box(lid,0,26,0,96,52,4,'#7FB5C4');box(lid,0,26,2.2,79,36,.5,'#294B63');surfaceRect(g,40,20.2,17,8,12,C.teal);}

  return {models,helpers:{model,group,box,ball,cyl,rod,tube,path,plate,disk,ring,lathe,topDisk,surfaceRect,keys,text,note,mesh,mat,bowed},C,THREE};
}
