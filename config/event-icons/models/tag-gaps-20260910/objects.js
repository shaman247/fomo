// Stylized construction: X right, Y up, Z front. All details sit on object surfaces.
export async function extend(api){
const {THREE,C}=api,{model,group,box,ball,cyl,rod,tube,plate,disk,ring,mesh,mat,lathe,topDisk,surfaceRect,note}=api.helpers;
{
 const g=model('equipment-tap-shoe',[.24,-.40,1]);
 const shape='M-48 6V31Q-39 37-26 29L-13 15Q3 9 29 10Q46 10 49 2L48-4H-48Z';
 plate(g,shape,-15,'#3D4854',30);plate(g,shape,15.1,'#596572',0,true);
 plate(g,'M-48 0H-22Q-10 0-2-3H48V-8H-48Z',-16,'#292F37',32);
 box(g,-35,-12,0,27,12,30,'#313941');box(g,-35,-18.5,0,26,2.5,31,C.pale);
 box(g,26,-9,0,39,2,31,C.pale);
 plate(g,'M-48 27Q-37 35-28 29L-22 23Q-33 20-45 22Z',15.3,'#293541',0,true);
 for(let i=0;i<4;i++){const x=-19+i*6,y=20-i*2.1;tube(g,[[x,y,13],[x+4,y+1,1],[x+1,y,-12]],.9,'#CBD4D6');}
 for(const x of [-41,-29,17,35]){const s=disk(g,x,x<0?-20:-10.5,0,1.3,'#657787');s.rotation.x=Math.PI/2;}
 g.userData.checks=['Toe and heel taps are separate metal plates on sole undersides.','Low heel; laces follow upper across width; no implied ballet pointe toe.'];
}
{
 const g=model('instrument-singing-bowl',[.12,.55,1]);
 lathe(g,[0,0,0],[[0,0],[20,0],[29,7],[36,22],[39,34],[39,38],[36,38],[35,33],[31,20],[24,10],[0,9]],'#DDB15C');
 const lip=mesh(g,new THREE.TorusGeometry(37.5,1.7,12,64),'#F4D189',[0,37,0]);lip.rotation.x=Math.PI/2;
 // A separate padded striker sits diagonally beside the open bowl, with air gap.
 rod(g,[40,4,24],[57,65,15],3.6,'#A46D40');rod(g,[53,50,17],[58,68,14],5.6,'#514B56');
 tube(g,[[-41,39,0],[-47,47,0],[-47,56,0]],1.6,'#66ABB0',true,true);
 tube(g,[[-49,35,0],[-56,45,0],[-56,56,0]],1.4,'#9BD0CE',true,true);
 g.userData.checks=['Bowl wall returns inward with visible cavity; striker remains separate.'];
}
{
 const g=model('format-animation',[.16,.12,1]);
 function frame(x,y,z,color,ballX,ballY){const n=group(g,[x,y,z]);box(n,0,0,0,72,67,3,color);box(n,0,0,1.8,60,47,.5,C.cream);
 for(const side of [-1,1])for(let i=0;i<5;i++)box(n,-26+i*13,side*28,2.2,6,4,.4,'#DBEBE9');disk(n,ballX,ballY,2.5,10,'#E9876B');box(n,0,-20,2.5,52,2,.5,'#B7CCC8');}
 frame(-13,14,-6,'#6C909E',-15,7);frame(13,-14,1,'#3D677C',13,-9);
 tube(g,[[-7,0,5],[1,10,5],[12,12,5],[21,7,5]],1.6,'#A1B8B9',true,true);
 g.userData.checks=['Two animation frames depict one ball at different positions; no franchise artwork or implied nationality.'];
}
{
 const g=model('art-hand-puppet',[.12,.10,1]);
 plate(g,'M-21 0L-24 27L-43 38Q-52 47-45 53Q-41 58-34 51L-22 45L-15 65H15L22 45L34 51Q42 58 47 52Q53 45 44 38L24 27L21 0Z',-9,'#75AFA6',18);
 plate(g,'M-21 0H21V15H-21Z',9.2,'#446B93',1);
 ball(g,[0,71,0],23,'#EDBE87',[1,1.06,.77]);
 disk(g,-8,76,17.5,2.3,'#3D464A');disk(g,8,76,17.5,2.3,'#3D464A');
 plate(g,'M-9 63Q0 51 9 63Z',18,'#A65760',0,true);ball(g,[0,67,18],3.6,'#F2C596');
 plate(g,'M-22 84Q-29 103-12 97Q-13 110 2 99Q18 111 22 91Q10 94 5 89Q-4 95-9 88Z',-2,'#B78350',9);
 g.userData.checks=['Glove body has no legs, a broad wrist cuff, and two raised puppet arms.','Not a marionette, static display doll or all puppet mechanisms.'];
}
{
 const g=model('equipment-risograph',[.5,.35,1]);
 box(g,0,30,0,74,48,43,'#BBCBC9');box(g,0,57,0,78,8,47,'#E2E7DD');
 box(g,0,53,3,64,3,35,'#3E5966');box(g,0,56,0,66,3,31,'#E9ECE3');
 box(g,-7,34,22,51,23,1,'#547687');box(g,-7,33,23,42,15,1,'#233E50');
 box(g,27,40,22,10,9,1,'#76BAC2');for(let i=0;i<3;i++)disk(g,23+i*4,28,23,1,'#5A747E');
 box(g,-6,17,40,53,3,43,'#B7CDCE');box(g,-6,19,44,44,1,44,C.cream);
 surfaceRect(g,-14,19.6,43,15,24,'#5ABAC7');surfaceRect(g,-3,19.8,49,15,24,'#D47B9B');surfaceRect(g,-8.5,20,46,4,18,'#8F83B2');
 for(const x of [-26,26])box(g,x,3,0,13,8,32,'#486171');
 g.userData.checks=['Lidded scanner, front cylinder bay and supported output tray; cyan/magenta overprint sheet.','Stylized duplicator, not exact RISO model or manufacturer logo.'];
}
{
 const g=model('instrument-vibraphone',[.26,.58,1]);
 for(const x of [-43,43]){rod(g,[x,0,-17],[x,54,-17],2.4,'#708F9D');rod(g,[x,0,17],[x,54,17],2.4,'#708F9D');rod(g,[x,2,-21],[x,2,21],2.7,'#4A6471');}
 box(g,0,49,-16,99,5,4,'#688894');box(g,0,49,18,99,5,4,'#688894');
 for(let i=0;i<10;i++){let x=-42+i*9.2,len=35-i*1.45;box(g,x,54,5,7.5,2.7,len,'#D3DDE0');cyl(g,[x,49-(34-i*1.5)/2,6],3,34-i*1.5,'#C0A665');
 if([0,1,3,4,5].includes(i%7)&&i<9)box(g,x+4.6,57,-15,7.4,2.7,len*.62,'#A9BEC6');}
 rod(g,[0,4,8],[0,47,8],1.5,'#79949D');box(g,0,4,13,13,2,12,'#405768');
 rod(g,[-28,72,8],[19,60,-13],1,'#BD9567');ball(g,[-29,72,9],4,'#5EA5B0');
 rod(g,[-6,63,-15],[31,76,9],1,'#BD9567');ball(g,[32,76,10],4,'#8F71AC');
 g.userData.checks=['Staggered aluminum tone bars; resonators shorten toward the high notes; damper pedal supported below.','Bar count reduced for icon scale; not a literal keyboard range.'];
}
function stand(g,x,y,z,scale=1){const n=group(g,[x,y,z]);n.scale.setScalar(scale);box(n,0,45,0,30,23,2,'#516D7C');box(n,0,45,1.2,25,19,.5,C.cream);rod(n,[0,0,0],[0,38,0],2.1,'#647F8D');for(const xx of [-13,13])rod(n,[0,8,0],[xx,0,4],1.9,'#647F8D');rod(n,[0,8,0],[0,0,-12],1.9,'#647F8D');note(n,-4,42,2.1,1.7,'#71878D');}
{
 const g=model('ensemble-chamber',[.13,.15,1]);stand(g,0,0,-13,.94);stand(g,-33,0,6,.94);stand(g,33,0,6,.94);
 g.userData.checks=['Three separate music stands establish shared chamber performance without specifying instrument lineup.'];
}
{
 const g=model('ensemble-music-duo',[.13,.15,1]);stand(g,-24,0,0,1.1);stand(g,24,0,0,1.1);
 tube(g,[[-9,67,2],[0,72,2],[9,67,2]],1.5,'#A68AC5',true,true);
 g.userData.checks=['Exactly two music stands with independent support; visual shorthand for a musical duo, not guaranteed equipment.'];
}
{
 const g=model('instrument-oud',[.40,.16,1]);const n=group(g,[0,0,0],[0,0,-.46]);
 // Short-necked, fretless lute with a rounded bowl back and bent pegbox.
 const front=plate(n,'M0 0C-25 0-32 20-25 42C-21 55-8 64-5 73H5C8 64 21 55 25 42C32 20 25 0 0 0Z',7,'#E6B975',1);
 // Bowl rings share the soundboard perimeter, closing behind it without gaps.
 const outline=front.geometry.parameters.shapes.getPoints(28),positions=[],indices=[],N=outline.length;
 for(let j=0;j<=16;j++){const a=j/16*Math.PI/2,k=Math.cos(a);for(const p of outline)positions.push(p.x*k,32+(p.y-32)*k,7-25*Math.sin(a));}
 for(let j=0;j<16;j++)for(let i=0;i<N-1;i++){const a=j*N+i,b=a+N;indices.push(a,b,a+1,a+1,b,b+1);}
 const bowl=new THREE.BufferGeometry();bowl.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));bowl.setIndex(indices);bowl.computeVertexNormals();mesh(n,bowl,'#AD7448');
 box(n,0,79,5,10,27,7,'#925E3E');box(n,0,79,9,8,28,1,'#664638');
 const peg=group(n,[0,93,4],[-1.18,0,0]);box(peg,0,9,0,8,21,6,'#A97346');for(let i=0;i<5;i++){const side=i%2?1:-1;rod(peg,[0,3+i*3.5,0],[side*8,3+i*3.5,0],.7,'#9B7147');ball(peg,[side*8,3+i*3.5,0],1.6,'#634C3D');}
 for(const [x,y,r] of [[0,42,7.5],[-11,28,3.6],[11,28,3.6]]){disk(n,x,y,8.3,r,'#795A3D');ring(n,x,y,8.4,r+.9,.8,'#F2D293');for(const s of [-1,0,1])rod(n,[x-r*.6,y+s*r*.42,8.5],[x+r*.6,y+s*r*.42,8.5],.3,'#C29A60',true);}
 box(n,0,15,9,17,3,2,'#795033');for(let i=0;i<6;i++)rod(n,[(i-2.5)*1.1,15,10.3],[(i-2.5)*1.1,93,9.7],.17,'#F4E6C3',true);
 g.userData.checks=['Short fretless neck; pear-shaped soundboard on bowl back; three rosettes; pegbox bends behind neck.','Stylized string courses and pegs, not exact instrument replication.'];
}
{
 const g=model('craft-printmaking',[.12,.65,1]);box(g,6,0,7,77,2,75,C.cream);
 surfaceRect(g,6,1.3,5,59,57,'#74AEB7');const emblem=plate(g,'M-12-10Q-25 4-11 19Q1 16 8 5Q5-7-12-10Z',0,'#ECDBAC',0,true);emblem.rotation.x=-Math.PI/2;emblem.position.set(9,1.5,10);
 const roller=group(g,[-18,13,-12],[0,0,.2]);const roll=cyl(roller,[0,0,0],8,48,'#3E596B');roll.rotation.z=Math.PI/2;
 for(const x of [-26,26])rod(roller,[x,0,0],[x,0,16],1.4,'#AABEC6');rod(roller,[-26,0,16],[26,0,16],1.4,'#AABEC6');rod(roller,[0,0,16],[0,0,36],4,'#CB8C57');
 g.userData.checks=['Brayer has an axle, two supporting arms, crossbar and handle; paper sits below.','Illustrative printmaking topic; individual event rules require a compatible hand-print process.'];
}
{
 const g=model('place-performance-stage',[.05,.10,1]);box(g,0,0,0,106,8,35,'#8876AD');box(g,0,45,-14,99,80,3,'#324759');
 box(g,0,86,-2,112,13,25,'#C66F8C');
 plate(g,'M-52 83H-26Q-27 45-41 14H-52Z',-1,'#C26687',8);plate(g,'M52 83H26Q27 45 41 14H52Z',-1,'#A85779',8);
 const light=plate(g,'M-8 78L-30 7H30L8 78Z',-9,'#718592',0,true);disk(g,0,79,-8,5,'#F4DCA8');
 box(g,0,7,5,91,3,24,'#C49EB8');
 g.userData.checks=['Open empty stage with curtains and light; no circus tent or specific performer.'];
}
{
 const g=model('place-heritage-site',[.08,.14,1]);
 plate(g,'M-40 0H40V56Q40 67 27 72L0 85L-27 72Q-40 67-40 56Z',-3,'#AC7D4B',6);
 plate(g,'M-34 6H34V55Q34 62 23 67L0 78L-23 67Q-34 62-34 55Z',3.1,'#E4CA91',0,true);
 // Heritage plaque with column emblem, not a ruin or a particular landmark.
 box(g,0,20,4,40,5,1,'#7D6546');box(g,0,54,4,40,4,1,'#7D6546');for(const x of [-13,0,13])box(g,x,37,4,6,28,1,'#8F744E');
 plate(g,'M-22 58L0 71L22 58Z',4.2,'#8F744E',0,true);
 for(const x of [-29,29])disk(g,x,11,4,1.6,'#AF9159');
 g.userData.checks=['Flat heritage plaque rather than a crumbling building; column is symbolic and does not identify a named site.'];
}
}
