from pathlib import Path
import re
b=Path('.scratch/icon-cycles-20260909/cycle-086')
def wrap(name,bg,transform,fg=''):
 p=b/'art'/f'{name}.svg';s=p.read_text();body=re.sub(r'^.*?</title>','',s).split('</svg>')[0];p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+name+'</title>'+bg+'<g transform="'+transform+'">'+body+'</g>'+fg+'</svg>\n')
wrap('paper-squishy','<path fill="#A2B6B5" d="M13 13h65l17 17v74H13z"/><path fill="#F1DFC0" d="M18 9h59l16 18v73H18z"/><path fill="#CDB18C" d="M77 9v18h16z"/>','translate(14 22) scale(.80)')
wrap('3d-modeling','<rect x="9" y="17" width="110" height="94" rx="7" fill="#7794A1"/><path fill="#D9DCC7" d="M16 35h96v66H16z"/><path d="M20 26h3m8 0h3m8 0h3" stroke="#ECD9B2" stroke-width="4" stroke-linecap="round"/>','translate(29 34) scale(.51)','<path d="M34 39h8m-8 0v8m58-8h-8m8 0v8M34 95h8m-8 0v-8" stroke="#C69859" stroke-width="3" fill="none"/><path fill="#B17C63" d="m84 71 28 17-13 2-6 13z"/><path fill="#E6C28A" d="m84 71 11 22 4-3 13-2z"/>')
