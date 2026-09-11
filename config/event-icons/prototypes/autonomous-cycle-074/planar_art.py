"""Original flat diagrams for art cinema and performed literary fiction."""
from pathlib import Path
ROOT=Path('.scratch/icon-cycles-20260909/cycle-074/art')
a='<rect x="9" y="20" width="110" height="87" rx="8" fill="#718C92"/><rect x="23" y="29" width="82" height="68" rx="2" fill="#DBD9C3"/>'
for x in [13,108]:
 for y in [32,51,70,89]:a+=f'<rect x="{x}" y="{y}" width="7" height="8" rx="1" fill="#EAE7D8"/>'
a+='<rect x="31" y="36" width="55" height="50" rx="2" fill="#B89C77"/><rect x="37" y="42" width="43" height="38" fill="#BFD3CC"/><circle cx="67" cy="51" r="5" fill="#EAC691"/><path d="m37 76 14-17 11 13 8-8 10 12v4H37Z" fill="#789C90"/><circle cx="92" cy="84" r="17" fill="#A9816C"/><circle cx="92" cy="75" r="2.5" fill="#F6E6C7"/><path d="M92 83v10m-3 0h6" stroke="#F6E6C7" fill="none" stroke-width="4" stroke-linecap="round"/>'
b='<path d="M13 18h102v83H13Z" fill="#CCD6CC"/><path d="M13 18h24v14q0 25-24 36ZM115 18H91v14q0 25 24 36Z" fill="#AC7F84"/><rect x="8" y="99" width="112" height="9" rx="3" fill="#9B8475"/><path d="M28 57q20-7 36 2 16-9 36-2v32q-20-5-36 3-16-8-36-3Z" fill="#EEDCBA"/><path d="M64 59v33" stroke="#B5A082" stroke-width="3"/><path d="M35 66q12-3 21 1M35 74q12-3 21 1M73 67q10-4 20-1M73 75q10-4 20-1" fill="none" stroke="#A8AA8E" stroke-width="3" stroke-linecap="round"/><path d="M47 26h31q7 0 7 7v10q0 7-7 7H64l-9 7v-7h-8q-7 0-7-7V33q0-7 7-7Z" fill="#779B99"/><path d="M50 35h24M50 42h16" stroke="#EDE3C8" stroke-width="3" stroke-linecap="round"/>'
for n,s in [('art-documentary',a),('performed-fiction',b)]:
 (ROOT/f'{n}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+s+'</svg>\n')
