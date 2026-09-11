"""Original flat genre emblems using the accepted film-frame visual language.
No actor, character, logo, film still, real anatomical figure or 3D apparatus.
"""
from pathlib import Path
import json,gzip
b=Path('.scratch/icon-cycles-20260909/cycle-080')
def frame(bg):
 s='<rect x="8" y="20" width="112" height="88" rx="9" fill="#628795"/><path d="M8 96h112v3a9 9 0 0 1-9 9H17a9 9 0 0 1-9-9Z" fill="#4E6F7B"/><rect x="24" y="30" width="80" height="68" rx="3" fill="'+bg+'"/>'
 for x in [12,108]:
  for y in [32,49,66,83]:s+=f'<rect x="{x}" y="{y}" width="8" height="9" rx="1" fill="#DCE7E5"/>'
 return s
art={}
# Castle-and-spark glyph is a magical-world emblem, not architecture from any film.
art['fantasy-film']=frame('#C6C3D5')+'<path d="M33 91V59h19V44h24v15h19v32Z" fill="#F0DCB5"/><path d="m29 59 13-19 14 19Zm21-15 14-20 14 20Zm22 15 13-19 14 19Z" fill="#9D737C"/><path d="M57 91V76a7 7 0 0 1 14 0v15Z" fill="#9F8F9C"/><path d="M39 66h7v9h-7Zm43 0h7v9h-7Z" fill="#9F8F9C"/><path d="m91 30 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z" fill="#FFF0CA"/>'
# Medal is a flat competition symbol, without a sporting event or outcome claim.
art['sports-film']=frame('#CCD7CF')+'<path d="m39 34 17 0 11 24-17 9Zm33 0h17L77 67 60 58Z" fill="#9C6E70"/><circle cx="64" cy="73" r="24" fill="#D8AB65"/><circle cx="64" cy="72" r="18" fill="#F2CE88"/><path d="m64 56 4 10 11 1-8 7 2 11-9-6-9 6 2-11-8-7 11-1Z" fill="#AD7D50"/>'
# Abstract domino mask, no trademark insignia or anatomical head.
art['superhero-film']=frame('#D7CEC0')+'<path d="M35 43Q47 38 64 48Q81 38 93 43l-4 29-17 3-8-8-8 8-17-3Z" fill="#756A8D"/><path d="m43 52 14 6-4 7-11-3Zm42 0-14 6 4 7 11-3Z" fill="#EEE0BE"/><path d="m61 79 12-5-4 10 9-1-15 13 2-11-9 2Z" fill="#D3A662"/>'
# Small and large stars joined by a rising path symbolize a growth narrative.
art['coming-of-age-film']=frame('#CED8CE')+'<path d="M39 87Q67 90 75 59" fill="none" stroke="#A77F69" stroke-width="8" stroke-linecap="round"/><path d="m40 69 4 8 9 1-7 6 2 9-8-5-8 5 2-9-7-6 9-1Z" fill="#E6BB74"/><path d="m78 35 6 12 14 2-10 10 2 14-12-7-12 7 2-14-10-10 14-2Z" fill="#ECCB8F"/><path d="m51 39 3 6 7 1-5 5 1 6-6-3-6 3 1-6-5-5 7-1Z" fill="#89A79B"/>'
# Route and smiling destination mark comedy on a journey; no real road geometry.
art['road-comedy-film']=frame('#D6D9C7')+'<path d="M38 87h28q17 0 17-12T64 63H49q-14 0-14-10t13-10h15" fill="none" stroke="#7C9695" stroke-width="13" stroke-linecap="round"/><path d="M39 87h8m9 0h8m14-7 3-6M73 64h-8m-9-1h-8M37 55v-5m9-7h8" fill="none" stroke="#F6E5BF" stroke-width="3" stroke-linecap="round"/><circle cx="79" cy="46" r="19" fill="#E7BE7C"/><path d="m69 42 4-2 4 2m5-2h7M69 49q10 12 19 0" fill="none" stroke="#8C6E5C" stroke-width="4" stroke-linecap="round"/>'
for n,s in art.items():(b/'art'/f'{n}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+s+'</svg>\n')
(b/'sizes-v1.json').write_text(json.dumps({p.name:dict(raw=len(p.read_bytes()),gzip_level_6=len(gzip.compress(p.read_bytes(),compresslevel=6,mtime=0))) for p in (b/'art').glob('*.svg')},indent=2)+'\n')
