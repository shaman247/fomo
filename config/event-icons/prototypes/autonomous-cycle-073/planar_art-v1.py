"""Original flat genre diagrams. Film perforations are symbolic,not gauge claims.
No physical scene,human pose,photographic tracing or copied film character.
"""
from pathlib import Path
import json,gzip
ROOT=Path('.scratch/icon-cycles-20260909/cycle-073')
def frame(bg):
 s='<rect x="8" y="20" width="112" height="88" rx="9" fill="#628795"/><path d="M8 96h112v3a9 9 0 0 1-9 9H17a9 9 0 0 1-9-9Z" fill="#4E6F7B"/><rect x="24" y="30" width="80" height="68" rx="3" fill="'+bg+'"/>'
 for x in [12,108]:
  for y in [32,49,66,83]:s+=f'<rect x="{x}" y="{y}" width="8" height="9" rx="1" fill="#DCE7E5"/>'
 return s
art={}
# Eye/play is a diagram of seeing ahead,not a real eyeball or video-player control.
art['preview-screening']=frame('#E4D3B4')+'<path d="M29 61Q62 23 99 61Q62 98 29 61Z" fill="#FEF5DC"/><circle cx="64" cy="61" r="16" fill="#7C9F96"/><path d="m60 50 16 11-16 11Z" fill="#45616B"/><path d="m100 84-8-7v5h-9v5h9v5Z" fill="#B67D6A"/>'
# Ringed planet is a conventional genre symbol,not a particular astrophysical scene.
art['science-fiction-film']=frame('#536D83')+'<ellipse cx="65" cy="62" rx="34" ry="9" transform="rotate(-25 65 62)" fill="none" stroke="#ACCCD0" stroke-width="6"/><circle cx="65" cy="62" r="22" fill="#E6C18B"/><path d="M80 46a22 22 0 0 1-29 31 22 22 0 0 0 29-31Z" fill="#CD9E76"/><path d="M31 62a34 9 0 0 0 68 0" transform="rotate(-25 65 62)" fill="none" stroke="#ACCCD0" stroke-width="6"/><path d="m36 36 2 5 5 2-5 2-2 5-2-5-5-2 5-2Z" fill="#EFE2BE"/><circle cx="91" cy="88" r="3" fill="#E9D9B6"/>'
# Abstract monster-face glyph,no claim of a real animal or a film character.
art['creature-feature']=frame('#D8DECA')+'<path d="m35 53-3-18 18 9q14-6 28 0l18-9-3 18v25q-4 17-29 17T35 78Z" fill="#8D9B80"/><path d="m44 58 13 4-12 6Zm40 0-13 4 12 6Z" fill="#3E5A5C"/><path d="M46 76h36q-3 14-18 14T46 76Z" fill="#405B58"/><path d="m49 76 5 7 5-7Zm20 0 5 7 5-7Z" fill="#F3E2C3"/>'
# Lens and clue card are flat outline symbols,not a physically lit magnifier study.
art['crime-mystery-film']=frame('#DCCBBB')+'<rect x="33" y="39" width="39" height="49" rx="3" fill="#F2E3C9"/><path d="M41 48h23M41 57h15M41 66h19M41 75h11" fill="none" stroke="#A3917D" stroke-width="5" stroke-linecap="round"/><path d="m76 74 17 17" stroke="#876B62" stroke-width="10" stroke-linecap="round"/><circle cx="65" cy="62" r="20" fill="#C1D5D0" stroke="#496B73" stroke-width="7"/><path d="M57 61q8-11 16 0-8 11-16 0Z" fill="#F4E9CD"/><circle cx="65" cy="61" r="4" fill="#55747C"/>'
# Lectern and exaggerated smiling speech bubble are flat satire symbols.
art['political-satire-film']=frame('#C4D1C5')+'<path d="M46 70h36l-5 24H51Z" fill="#AD826B"/><rect x="42" y="66" width="44" height="8" rx="2" fill="#CFA580"/><path d="M64 65V54l9-4" fill="none" stroke="#506C72" stroke-width="4" stroke-linecap="round"/><path d="M38 33h48q8 0 8 8v10q0 8-8 8H57l-9 7v-7H38q-8 0-8-8V41q0-8 8-8Z" fill="#EAD19F"/><path d="m42 43 6-3 6 3M72 41h10" fill="none" stroke="#856B5B" stroke-width="4" stroke-linecap="round"/><path d="M51 48h26q-4 8-13 8t-13-8Z" fill="#8C6A5B"/>'
for n,s in art.items():(ROOT/'art'/f'{n}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+s+'</svg>\n')
(ROOT/'sizes-v1.json').write_text(json.dumps({p.name:dict(raw=len(p.read_bytes()),gzip_level_6=len(gzip.compress(p.read_bytes(),compresslevel=6,mtime=0))) for p in (ROOT/'art').glob('*.svg')},indent=2)+'\n')
