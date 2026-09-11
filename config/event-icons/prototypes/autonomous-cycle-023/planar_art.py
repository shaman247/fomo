from pathlib import Path
import math
b=Path('.scratch/icon-cycles-20260909/cycle-023');pr=Path('config/event-icons/prototypes/autonomous-cycle-023')
def save(name,body):
 s='<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+name.replace('-',' ').title()+'</title>'+body+'</svg>\n';(pr/(name+'.svg')).write_text(s);(b/'art'/(name+'.svg')).write_text(s)
s='<path fill="#9BBEBB" d="M12 16H90V90H12Z"/><path fill="#668E9C" d="M12 16L51 53L12 90ZM51 53L90 16V90Z"/><path fill="#E8AD7A" d="M12 90L51 53L90 90Z"/><path d="M16 20L86 86M86 20L16 86" fill="none" stroke="#F3E9D4" stroke-width="2.8" stroke-dasharray="3 5"/>'
s+='<path fill="#B96B73" d="M67 117L93 61L119 117Z"/><path fill="#F1E5CF" d="M76 111L93 76L110 111Z"/><path fill="#DE9290" d="M67 117L76 111H110L119 117ZM93 61L93 76L76 111L67 117Z"/><path d="M82 103L93 81L104 103" fill="none" stroke="#A99586" stroke-width="2" stroke-dasharray="3 4"/>'
s+='<path d="M23 108C29 98 36 113 42 105S48 99 52 105" fill="none" stroke="#8D687C" stroke-width="2.5" stroke-linecap="round"/><path d="M51 106L73 90" stroke="#9EADB3" stroke-width="4" stroke-linecap="round"/><path d="M53 104L56 102" stroke="#4D626F" stroke-width="1.5" stroke-linecap="round"/>'
save('english-paper-piecing',s)
s='<rect x="13" y="17" width="102" height="94" rx="6" fill="#E9D9BD"/>'
# Vertical counted-stitch segments form original repeating steps, not painted diagonal stripes.
colors=['#617D9E','#8A9EB5','#DA8D88','#EFC194'];offset=[0,5,10,15,10,5,0,5,10,15,10,5]
for j,col in enumerate(colors):
 d=''
 for i,dy in enumerate(offset):
  x=19+i*7.5;y=24+dy+j*16;d+=f'M{x:g} {y:g}v13'
 s+=f'<path d="{d}" stroke="{col}" stroke-width="6" stroke-linecap="round"/>'
s+='<path d="M93 31C112 25 109 9 99 13C91 16 107 23 113 19" fill="none" stroke="#B76576" stroke-width="2.8" stroke-linecap="round"/><path d="M71 53L98 22" stroke="#ABBAC0" stroke-width="4.5" stroke-linecap="round"/><path d="M93 28L96 24" stroke="#526873" stroke-width="1.7" stroke-linecap="round"/>'
save('bargello-embroidery',s)
s='<rect x="9" y="18" width="110" height="93" rx="9" fill="#51616D"/><path d="M18 18H110Q119 18 119 27V36H9V27Q9 18 18 18Z" fill="#8AA3B0"/><circle cx="20" cy="27" r="3" fill="#F5D99B"/><circle cx="30" cy="27" r="3" fill="#E7A19D"/><path fill="#BBDACB" d="M102 23L110 27L102 31Z"/><path fill="#E8ECE8" d="M17 43H88V101H17Z"/><path d="M17 57H88M17 71H88M17 85H88M35 43V101M53 43V101M71 43V101" stroke="#CBD6D4" stroke-width="1.5"/>'
s+='<g fill="#58A89B"><rect x="21" y="48" width="23" height="6" rx="2"/><rect x="48" y="62" width="17" height="6" rx="2"/><rect x="68" y="76" width="16" height="6" rx="2"/></g><g fill="#D69879"><rect x="22" y="90" width="25" height="6" rx="2"/><rect x="57" y="90" width="27" height="6" rx="2"/></g><path d="M62 43V101" stroke="#A36178" stroke-width="2.5"/><path d="M99 48V96M110 48V96" stroke="#B8C8CD" stroke-width="3" stroke-linecap="round"/><path d="M95 62H103M106 82H114" stroke="#EDD69A" stroke-width="6" stroke-linecap="round"/>'
save('digital-music-production',s)
