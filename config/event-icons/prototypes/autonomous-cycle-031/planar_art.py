from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-031/art')
def save(name,title,body):(b/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+title+'</title>'+body+'</svg>\n')
# Companion to accepted70mm: same generic film-strip language, outlined gauge digits.
base=Path('config/event-icons/art/70mm-screening.svg').read_text();start=base.index('<path d="M29');end=base.index('</svg>')
digits='<path d="M27 49h17q13 0 13 9 0 6-6 8 8 2 8 8 0 10-16 10H26v-8h16q6 0 6-3t-6-3h-9v-8h9q5 0 5-3t-5-3H27ZM66 49h29v8H74v6h9q14 0 14 10 0 11-16 11H65v-8h17q5 0 5-3t-6-3H66Z" fill="#596A83"/>'
(b/'35mm-screening.svg').write_text(base[:start].replace('70Mm Screening','35mm screening')+digits+'</svg>\n')
# A planar exploded frame: three joined rails plus a detached top rail, with a short measuring rule.
save('picture-framing','Picture framing','<path d="M15 43l14 14v46l-14 14Zm0 74 14-14h60l14 14Zm88 0L89 103V57l14-14Z" fill="#B98259"/><path d="M15 27h88L89 41H29Z" fill="#DEAF77"/><path d="M29 57v46h60V57" fill="none" stroke="#E9C593" stroke-width="4"/><path d="M35 113h45M22 67v22M96 68v25M39 34h29" fill="none" stroke="#9B7152" stroke-width="2" stroke-linecap="round"/><rect x="48" y="58" width="70" height="17" rx="2" transform="rotate(-28 48 58)" fill="#E6C869"/><path d="M53 59v6m10-6v9m10-9v6m10-6v9m10-9v6m10-6v9" transform="rotate(-28 48 58)" fill="none" stroke="#886E44" stroke-width="2"/>')
