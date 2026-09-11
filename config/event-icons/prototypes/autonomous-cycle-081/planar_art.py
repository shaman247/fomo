from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-081')
def frame(bg):
 s='<rect x="8" y="20" width="112" height="88" rx="9" fill="#628795"/><path d="M8 96h112v3a9 9 0 0 1-9 9H17a9 9 0 0 1-9-9Z" fill="#4E6F7B"/><rect x="24" y="30" width="80" height="68" rx="3" fill="'+bg+'"/>'
 for x in [12,108]:
  for y in [32,49,66,83]:s+=f'<rect x="{x}" y="{y}" width="8" height="9" rx="1" fill="#DCE7E5"/>'
 return s
art={}
# Evening prayer book and sung-note symbols, not a replica liturgical page.
art['evensong']='<path d="M17 56q24-10 47 1 23-11 47-1v54q-25-8-47 0-23-8-47 0Z" fill="#79869B"/><path d="M22 51q20-8 42 3v49q-20-9-42-3Zm84 0q-20-8-42 3v49q20-9 42-3Z" fill="#EEDFC6"/><path d="M64 54v49" stroke="#B4A895" stroke-width="3"/><path d="M38 64v22m-8-14h16" fill="none" stroke="#AD8A69" stroke-width="5" stroke-linecap="round"/><path d="M82 84V61l14-4v23" fill="none" stroke="#7C8D9F" stroke-width="5" stroke-linejoin="round"/><ellipse cx="77" cy="85" rx="7" ry="5" fill="#7C8D9F"/><ellipse cx="91" cy="81" rx="7" ry="5" fill="#7C8D9F"/><path d="M73 13a23 23 0 1 0 25 27A24 24 0 0 1 73 13Z" fill="#DEC18B"/>'
# Cast identity card with music note distinguishes dramatized musician biography.
art['music-biopic']=frame('#D6CCBF')+'<rect x="33" y="37" width="61" height="54" rx="5" fill="#F1E0BE"/><circle cx="48" cy="50" r="7" fill="#AB8A79"/><path d="M38 68v-3a10 10 0 0 1 20 0v3Z" fill="#AB8A79"/><path d="M73 72V45l16 5v6l-10-3v20" fill="#7A9197"/><ellipse cx="70" cy="75" rx="9" ry="6" fill="#7A9197"/><path d="M41 81h17" stroke="#C8B797" stroke-width="4" stroke-linecap="round"/>'
# Broken ledge and suspended rescue ring are flat danger/survival symbols.
art['survival-film']=frame('#CBD1CD')+'<path d="M28 91V42h26l-9 17 10 12-7 20Zm50 0 4-22 18-15v37Z" fill="#8D9A94"/><path d="m53 35 8 9-6 11 11 11-6 12" fill="none" stroke="#B2876E" stroke-width="4" stroke-linejoin="round"/><circle cx="82" cy="48" r="13" fill="none" stroke="#EED7AE" stroke-width="8"/><path d="M82 35v6m0 14v6m-13-13h6m14 0h6" stroke="#B67E6E" stroke-width="7"/>'
for n,s in art.items():(b/'art'/f'{n}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+s+'</svg>\n')
