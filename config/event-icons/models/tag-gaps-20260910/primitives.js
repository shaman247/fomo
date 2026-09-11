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

  return {THREE,C,models,helpers:{model,group,box,ball,cyl,rod,tube,plate,disk,ring,mesh,mat,lathe,topDisk,surfaceRect,keys,text,note}};
}
