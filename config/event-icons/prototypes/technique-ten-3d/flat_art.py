"""Original flat Noto-style designs. No external assets or runtime fonts."""
import math,json
from pathlib import Path
b=Path('.scratch/icon-technique-ten-20260909/art');b.mkdir(exist_ok=True)
def save(name,title,desc,body):
 (b/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+title+'</title><desc>'+desc+'</desc>'+body+'</svg>\n')
# Bassoon: folded wooden bore, common boot, tall bass/bell joint and shorter wing.
save('bassoon','Bassoon','A reddish wooden bassoon with a joined boot, tall bell, shorter wing, curved bocal and double reed.', '''<g transform="rotate(18 64 64)"><path d="M48 16h16l3 73H47z" fill="#A65842"/><path d="M49 18h5l-1 69h-5z" fill="#CF8E64"/><path d="M48 16q-3-5-2-10h20q1 5-2 10z" fill="#AC654D"/><ellipse cx="56" cy="7" rx="10" ry="3.5" fill="#E8D7B4"/><ellipse cx="56" cy="7" rx="6.3" ry="1.8" fill="#563F38"/><path d="M70 43h11l3 45H68z" fill="#B56D4E"/><path d="M72 45h4v41h-5z" fill="#DAA275"/><path d="M47 82h37v24q0 13-18 13t-19-13z" fill="#AC6448"/><path d="M49 85h6v22q0 6 7 7-13 0-13-11z" fill="#D4976C"/><path d="M48 108q18 8 35 0v6q-17 9-35 0z" fill="#92A7AB"/><path d="M75 44c4-8 19-8 17-15-2-6 2-10 10-13" fill="none" stroke="#546E79" stroke-width="5" stroke-linecap="round"/><path d="M75 43c4-8 19-8 17-14-2-6 2-10 10-13" fill="none" stroke="#CDDADB" stroke-width="2.6" stroke-linecap="round"/><path d="m100 13 11-5 2 5-11 5z" fill="#D9B978"/><path d="M58 21v60m18-29v44" stroke="#D9E1DA" stroke-width="2.7" stroke-linecap="round"/><path d="M61 25h7m-7 12h7m-7 12h7m-7 13h7m-7 13h7M74 58h9m-9 12h9m-9 12h9m-15 18h14" stroke="#77949C" stroke-width="3" stroke-linecap="round"/><g fill="#E8ECE6"><circle cx="61" cy="25" r="3.2"/><circle cx="61" cy="37" r="3.2"/><circle cx="61" cy="49" r="3.2"/><circle cx="61" cy="62" r="3.2"/><circle cx="61" cy="75" r="3.2"/><circle cx="76" cy="58" r="3"/><circle cx="77" cy="70" r="3"/><circle cx="78" cy="82" r="3"/><circle cx="69" cy="100" r="3.5"/></g></g>''')
# A framed, symmetric six-point asanoha lattice. Joins share endpoints, no arbitrary overlaps.
center=(61,60);radius=42
pts=[(center[0]+radius*math.cos(math.radians(-90+i*60)),center[1]+radius*math.sin(math.radians(-90+i*60))) for i in range(6)]
lines=[]
for i,p in enumerate(pts):
 q=pts[(i+1)%6];m=((p[0]+q[0])/2,(p[1]+q[1])/2);j=((center[0]+m[0])/2,(center[1]+m[1])/2)
 lines += [(center,p),(p,j),(q,j),(j,m)]
linepath=''.join(f'M{a[0]:.1f} {a[1]:.1f}L{bb[0]:.1f} {bb[1]:.1f}' for a,bb in lines)
framepath='M'+'L'.join(f'{x:.1f} {y:.1f}' for x,y in pts)+'Z'
save('kumiko','Kumiko joinery','A wooden hexagonal frame containing a fitted sixfold hemp-leaf lattice, with a loose notched strip.',f'''<path d="{framepath}" fill="#FCF2DF" stroke="#AD7156" stroke-width="10" stroke-linejoin="round"/><path d="{linepath}" fill="none" stroke="#B37A52" stroke-width="4.8" stroke-linejoin="round"/><path d="{linepath}" fill="none" stroke="#F1C18A" stroke-width="2.7" stroke-linejoin="round"/><path d="{framepath}" fill="none" stroke="#E9B77D" stroke-width="5" stroke-linejoin="round"/><path d="m78 105 34-24 5 7-13 9-3-3-5 4 2 3-15 11z" fill="#AD7156"/><path d="m77 101 34-24 5 7-13 9-3-3-5 4 2 3-15 11z" fill="#FFCC80"/>''')
# Five-by-five rotationally symmetric grid with non-trivial white across/down runs.
body='<rect x="11" y="10" width="91" height="105" rx="7" fill="#B8C9CC"/><rect x="11" y="7" width="91" height="105" rx="7" fill="#F1EDEC"/>'
blocked={(0,0),(0,1),(1,0),(1,4),(3,0),(3,4),(4,3),(4,4)}
for y in range(5):
 for x in range(5):body+=f'<rect x="{19+x*15}" y="{22+y*15}" width="15" height="15" fill="'+('#40535E' if (y,x) in blocked else '#FFFCF4')+'" stroke="#738990" stroke-width="1.3"/>'
body+='''<g transform="rotate(32 99 76)"><path d="M92 35h14v65l-7 17-7-17z" fill="#EEB754"/><path d="M92 40h5v60h-5z" fill="#FFDC82"/><path d="M101 40h5v60h-5z" fill="#DA933D"/><path d="m92 100 7 17 7-17z" fill="#E7C394"/><path d="m96 110 3 7 3-7z" fill="#40535E"/><path d="M92 35v-6q7-5 14 0v6z" fill="#EC8B8B"/><path d="M92 35h14v7H92z" fill="#AAC0C3"/></g>'''
save('crossword','Crossword puzzle','A black-and-white crossword grid on a sheet with a yellow pencil.',body)
print('Three flat vector designs created.')
