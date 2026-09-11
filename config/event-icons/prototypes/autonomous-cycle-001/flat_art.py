import math
from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-001/art');b.mkdir(exist_ok=True)
def save(name,title,body):(b/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+title+'</title>'+body+'</svg>\n')
# Flat illustrative diagram: microphone plus flowing narrative speech bubble.
save('personal-storytelling','Personal oral storytelling','''<path d="M49 13h52q15 0 15 15v23q0 15-15 15H81L65 80V66H49q-15 0-15-15V28q0-15 15-15z" fill="#4D9FA8"/><path d="M49 13h52q15 0 15 15v5q0-13-15-13H49q-15 0-15 13v-5q0-15 15-15z" fill="#87C9CA"/><path d="M51 34h45M51 45h33M51 56h17" stroke="#E7F2E8" stroke-width="5" stroke-linecap="round"/><g transform="rotate(28 37 83)"><path d="M27 77h20l-3 35q-7 8-14 0z" fill="#49616B"/><path d="M29 81h6l-1 30-4 1z" fill="#7E99A1"/><rect x="21" y="48" width="32" height="40" rx="16" fill="#D7E3E2"/><path d="M40 49q13 2 13 15v8q0 16-16 16v-6q10-2 10-13v-5q0-9-7-15z" fill="#9EB7BC"/><path d="M27 64h20m-21 8h22m-17-15h12" stroke="#6B8791" stroke-width="2.5" stroke-linecap="round"/><path d="M26 84h22v6H26z" fill="#476470"/></g>''')
# Flat overhead bead-stringing diagram: thread, punctured colored beads and loose bead.
body='<path d="M33 17C8 30 10 90 44 106s65-5 65-43q0-24-18-37" fill="none" stroke="#B3A493" stroke-width="2.4" stroke-linecap="round"/>'
colors=['#62ABA8','#EFAC64','#B896C9','#EC8B84','#76AAB9']
for i in range(12):
 t=math.radians(205+i*25);x=62+42*math.cos(t);y=65+42*math.sin(t);c=colors[i%len(colors)]
 body+=f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.2" fill="{c}"/><circle cx="{x-2:.1f}" cy="{y-2.2:.1f}" r="2.4" fill="#FFFFFF" opacity=".38"/><circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="#5B6968"/>'
body+='<path d="M31 24Q52 8 76 24Q82 28 83 14" fill="none" stroke="#B3A493" stroke-width="2.4" stroke-linecap="round"/><ellipse cx="64" cy="19" rx="8" ry="7" fill="#62ABA8"/><ellipse cx="64" cy="19" rx="2" ry="2" fill="#4B737A"/><path d="m83 14 24 16" stroke="#8198A0" stroke-width="3" stroke-linecap="round"/>'
save('beading','Bead stringing',body)
