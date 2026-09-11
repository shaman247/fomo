from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-045/art')
# Flat camera pictogram beside a broken route with two waypoint dots.
# No depicted moving person, geographical claim or specific camera requirement.
s='''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>Photography walk</title><path d="M22 91H79Q105 91 105 69V59" fill="none" stroke="#BA9BC0" stroke-width="7" stroke-linecap="round" stroke-dasharray="9 13"/><circle cx="21" cy="91" r="9" fill="#85AFA9"/><circle cx="105" cy="37" r="9" fill="#DAB580"/><path d="M16 26H30L37 17H60L66 26H78Q84 26 84 32V69Q84 75 78 75H16Q10 75 10 69V32Q10 26 16 26Z" fill="#81A3B0"/><path d="M10 60H84V69Q84 75 78 75H16Q10 75 10 69Z" fill="#648896"/><circle cx="47" cy="49" r="20" fill="#D3E0DC"/><circle cx="47" cy="49" r="14" fill="#506D82"/><circle cx="47" cy="49" r="9" fill="#7197B0"/><path d="M41 46Q43 41 49 42" fill="none" stroke="#C1DBDD" stroke-width="4" stroke-linecap="round"/><rect x="68" y="32" width="10" height="7" rx="2" fill="#EEE4C9"/></svg>'''
(b/'photography-walk.svg').write_text(s+'\n')
