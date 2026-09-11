from pathlib import Path
from project import project
from scene import SCENES
b=Path('.scratch/icon-cycles-20260909/cycle-039');s=project(SCENES['musical-chairs']);(b/'chairs-projection.svg').write_text(s)
body=s[s.index('</title>')+8:s.rindex('</svg>')]
notes='<path d="M86 30V11l22-4v19" fill="none" stroke="#C6AA74" stroke-width="4" stroke-linejoin="round"/><ellipse cx="80" cy="31" rx="8" ry="5" fill="#C6AA74"/><ellipse cx="102" cy="27" rx="8" ry="5" fill="#C6AA74"/>'
(b/'art/musical-chairs.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>Musical chairs</title><g transform="translate(5 21) scale(.87)">'+body+'</g>'+notes+'</svg>\n')
