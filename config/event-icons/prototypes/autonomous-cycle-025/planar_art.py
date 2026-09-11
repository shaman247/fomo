from pathlib import Path
import math,re
b=Path('.scratch/icon-cycles-20260909/cycle-025/art')
def save(n,s): (b/(n+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+n.replace('-',' ').title()+'</title>'+s+'</svg>\n')
# Original symbolic astrology chart:12equal zodiac sectors, not a calculated natal chart.
s='<circle cx="64" cy="64" r="54" fill="#6F65A6"/><circle cx="64" cy="64" r="47" fill="#D8C6E8"/>'
for i in range(12):
 t=i*math.pi/6;x,y=64+47*math.cos(t),64+47*math.sin(t)
 s+=f'<path d="M64 64L{x:.1f} {y:.1f}" stroke="#8B79B5" stroke-width="2"/>'
s+='<circle cx="64" cy="64" r="31" fill="#6F65A6"/><path d="M44 72L76 44 83 78Z" fill="none" stroke="#B9ABD5" stroke-width="2.5"/><circle cx="49" cy="57" r="12" fill="#FFD56D"/><path d="M83 70a15 15 0 1 1-17-18 13 13 0 0 0 17 18" fill="#FFF0BD"/>'
for i in range(12):
 t=(i+.5)*math.pi/6;x,y=64+40*math.cos(t),64+40*math.sin(t)
 s+=f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.7" fill="#FFF0BD"/>'
save('astrology',s)
save('songwriting','<rect x="15" y="9" width="83" height="109" rx="8" fill="#BFCDD0"/><rect x="15" y="9" width="78" height="104" rx="7" fill="#F6ECD9"/><path d="M28 77h33M28 87h28M28 97h22" stroke="#B39B89" stroke-width="4" stroke-linecap="round"/><path d="M45 55V29l31-6v27" fill="none" stroke="#7965A9" stroke-width="6" stroke-linejoin="round"/><path d="M44 31l32-6v9l-32 6" fill="#7965A9"/><ellipse cx="38" cy="56" rx="10" ry="7" transform="rotate(-15 38 56)" fill="#7965A9"/><ellipse cx="69" cy="50" rx="10" ry="7" transform="rotate(-15 69 50)" fill="#7965A9"/><g transform="rotate(35 94 81)"><path d="M88 50h12v54l-6 13-6-13Z" fill="#FFCD63"/><path d="M95 50h5v54l-6 13 1-13Z" fill="#E8A947"/><path d="M88 49q0-5 5-5h2q5 0 5 5v8H88Z" fill="#D78190"/><path d="M88 102h12l-6 15Z" fill="#EED2A3"/><path d="M91 111l3 6 3-6" fill="#4D5964"/></g>')
save('junk-journaling','<path d="M22 10h73q9 0 9 9v94H24q-11 0-11-10V21q0-11 9-11" fill="#98705D"/><path d="M27 14h70v88H27Z" fill="#CFAB82"/><path d="M27 103h78v10H27q-8 0-8-5t8-5" fill="#EEE5D1"/><path d="M30 99h69" stroke="#866954" stroke-width="3"/><path d="M17 20v78" stroke="#BC8E71" stroke-width="4" stroke-linecap="round"/><g transform="rotate(-10 55 43)"><path d="M32 24h46v34l-5-2-5 3-5-3-5 3-5-3-5 3-5-3-5 3-6-2Z" fill="#F3EAD4"/><path d="M40 34h29M40 42h24M40 50h15" stroke="#A3947D" stroke-width="3" stroke-linecap="round"/></g><g transform="rotate(9 73 77)"><path d="M44 63h54v5a6 6 0 0 0 0 12v6H44v-6a6 6 0 0 0 0-12Z" fill="#7AAEAE"/><path d="M84 66v17" stroke="#D2E4D7" stroke-width="2" stroke-dasharray="3 3"/><path d="M55 74h18" stroke="#E1EDD9" stroke-width="4" stroke-linecap="round"/></g><path d="M34 19l26-4 2 9-26 4Z" fill="#D89BB2"/><path d="M71 85l27-7 2 10-27 7Z" fill="#D89BB2"/>')
# Simple flat top-view product silhouettes; no anatomical diagram, use instructions or inventory promise.
save('menstrual-products','<path d="M34 14c-13 0-18 10-16 24l3 14-12 7v18l12 7-3 15c-2 14 3 22 16 22h12c13 0 18-8 16-22l-3-15 12-7V59l-12-7 3-14c2-14-3-24-16-24Z" fill="#7CA2B2"/><path d="M35 18c-11 0-15 9-13 21l5 23-5 35c-2 12 2 20 13 20h10c11 0 15-8 13-20l-5-35 5-23c2-12-2-21-13-21Z" fill="#F0EEEC"/><path d="M36 29h8q7 0 6 9l-4 26 4 34q1 8-6 8h-8q-7 0-6-8l4-34-4-26q-1-9 6-9" fill="none" stroke="#C9DDE1" stroke-width="3"/><path d="M99 82v12c0 16-17 9-17 18 0 5 8 6 15 4" fill="none" stroke="#799C92" stroke-width="3" stroke-linecap="round"/><path d="M86 36q0-15 13-15t13 15v40q0 8-8 8H94q-8 0-8-8Z" fill="#91B0A6"/><path d="M86 36q0-15 13-15 4 0 6 2v53q0 5-5 5H92q-6 0-6-5Z" fill="#F2EFE7"/><path d="M94 34v35M103 34v35" fill="none" stroke="#CFDBD8" stroke-width="2.5" stroke-linecap="round"/>')
# Put the authoritative virtual mesh projection inside an original flat software window.
p=Path('.scratch/icon-cycles-20260909/cycle-025/sculpt-object.svg')
if p.exists():
 raw=p.read_text();body=re.sub(r'^.*?</title>','',raw).rsplit('</svg>',1)[0]
 save('digital-sculpting','<rect x="7" y="14" width="114" height="94" rx="9" fill="#527780"/><rect x="12" y="20" width="104" height="80" rx="5" fill="#DFE9E3"/><path d="M12 35h104V20H12Z" fill="#A4C4C6"/><circle cx="21" cy="27" r="3" fill="#527780"/><circle cx="31" cy="27" r="3" fill="#527780"/><path d="M24 93V45M24 93h77" fill="none" stroke="#AECAC4" stroke-width="2"/><g transform="translate(27 31) scale(.53)">'+body+'</g><circle cx="83" cy="66" r="12" fill="none" stroke="#FFFFFF" stroke-width="3"/><path d="M87 66l13 36 6-12 13-5Z" fill="#527780" stroke="#DFE9E3" stroke-width="2.5" stroke-linejoin="round"/>')
