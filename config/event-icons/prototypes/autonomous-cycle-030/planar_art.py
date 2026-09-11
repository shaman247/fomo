from pathlib import Path
import math
b=Path('.scratch/icon-cycles-20260909/cycle-030/art')
def save(n,s): (b/(n+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+n.replace('-',' ').title()+'</title>'+s+'</svg>\n')
save('language-learning','<path d="M8 58q27-8 55 5 28-13 57-5v56q-29-8-57 5-28-13-55-5Z" fill="#698792"/><path d="M14 52q24-5 49 7v53q-25-12-49-5Zm49 7q25-12 50-7v55q-25-5-50 5Z" fill="#F1E6CC"/><path d="M63 61v47" stroke="#CCBD9C" stroke-width="3"/><path d="M76 77q13-5 26-5M76 88q13-5 26-5" stroke="#A9977D" stroke-width="4" stroke-linecap="round"/><path d="M25 96l8-29h8l9 32-7-2-2-8-9-2-2 10Zm9-15 6 1-3-11Z" fill="#8E7A66" fill-rule="evenodd"/><path d="M44 10h56q10 0 10 10v20q0 10-10 10H73L57 62V50H44q-10 0-10-10V20q0-10 10-10" fill="#5B9F9D"/><path d="M50 29h3M68 29h3M86 29h3" stroke="#F1E6CC" stroke-width="7" stroke-linecap="round"/>')
save('ghost-tour','<path d="M8 68l36-10 40 11 36-10v54l-36 10-40-11-36 10Z" fill="#BBC6B5"/><path d="M44 58l40 11v54l-40-11Z" fill="#DFD9B9"/><path d="M25 99q12-18 30-10t39-1" fill="none" stroke="#91819D" stroke-width="4" stroke-linecap="round" stroke-dasharray="4 8"/><path d="M34 37q0-28 29-28t29 28v29l-11-8-10 9-10-8-12 9-15-6Z" fill="#F3ECE3"/><path d="M34 40v22l15 6 12-9 10 8 10-9 11 8V46q-4 17-15 9-11 12-22 1-13 7-21-16" fill="#D5CFDD"/><ellipse cx="53" cy="34" rx="4" ry="6" fill="#756781"/><ellipse cx="74" cy="34" rx="4" ry="6" fill="#756781"/><path d="M58 49q6 6 12 0" fill="none" stroke="#756781" stroke-width="3" stroke-linecap="round"/>')
save('fundraising-gala','<rect x="18" y="59" width="88" height="61" rx="6" fill="#B79A6B"/><path d="M18 65q0-6 6-6h76q6 0 6 6v8H18Z" fill="#D9B783"/><path d="M39 65h45" stroke="#786859" stroke-width="5" stroke-linecap="round"/><path d="M62 54C32 37 38 15 51 17q8 0 12 8 5-8 13-8 19 1 9 20-5 8-23 17" fill="#CD8886"/><path d="M41 85l20 9 21-9v24l-21-9-20 9Z" fill="#607A91"/><rect x="57" y="92" width="9" height="11" rx="2" fill="#8199AA"/><path d="M108 14l3 10 10 3-10 3-3 10-3-10-10-3 10-3Z" fill="#DFB365"/>')
s='<rect x="10" y="7" width="108" height="114" rx="7" fill="#806653"/><rect x="17" y="14" width="94" height="100" rx="3" fill="#B99B72"/><rect x="23" y="20" width="82" height="88" rx="2" fill="#E6D7B7"/><path d="M41 38q-24 54 23 58 47-4 23-58" fill="none" stroke="#9A785A" stroke-width="4"/>'
# Original broad looped floral ornament, not a copied museum object or weaving chart.
for cx,cy,r,angle in [(39,49,9,-20),(36,73,10,10),(49,89,9,-10),(72,91,9,15),(89,74,10,-15),(87,47,9,20)]:
 s+='<g fill="none" stroke="#806650" stroke-width="2.4">'
 for i in range(5):
  a=angle+i*72;s+=f'<ellipse cx="{cx}" cy="{cy-r*.60:.1f}" rx="{r*.32:.1f}" ry="{r*.64:.1f}" transform="rotate({a} {cx} {cy})"/>'
 s+='</g>'+f'<circle cx="{cx}" cy="{cy}" r="2.7" fill="#AA8861"/>'
s+='<path d="M47 46q17-16 29 0M47 49q17-16 29 0M48 52q16-15 27 0" fill="none" stroke="#AB8865" stroke-width="2" stroke-linecap="round"/>'
save('victorian-hairwork',s)
