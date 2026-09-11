from pathlib import Path
out=Path('.scratch/icon-cycles-20260909/cycle-007/art')
# Ancestral record cards and branching connections: planar genealogy diagram.
body='<path d="M28 34v47h72V34M64 81v18" fill="none" stroke="#A78D6C" stroke-width="7" stroke-linejoin="round"/><path d="M63 58q-22 1-21-15 18-2 21 15M65 69q21 0 20-15-16-2-20 15" fill="#83A184"/>'
for x,y,col in [(11,8,'#A7BDC2'),(83,8,'#C3A5B5'),(11,48,'#9DB499'),(83,48,'#CEB98C'),(47,89,'#B6B2CC')]:
 body+=f'<rect x="{x}" y="{y}" width="34" height="31" rx="4" fill="{col}"/><path d="M{x+7} {y+10}h20m-20 7h16m-16 7h11" fill="none" stroke="#F8EEDA" stroke-width="3" stroke-linecap="round"/>' if y!=89 else f'<rect x="{x}" y="{y}" width="34" height="31" rx="4" fill="{col}"/>'
body+='<path d="M64 113c-4-3-11-7-11-12 0-6 8-7 11-2 4-5 11-4 11 2 0 5-7 9-11 12" fill="#F8EEDA"/>'
(out/'genealogy.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+body+'</svg>\n')
