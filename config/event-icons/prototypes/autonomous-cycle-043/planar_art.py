"""Original planar diagrams; no spatial solids or borrowed artwork."""
from pathlib import Path
out=Path('.scratch/icon-cycles-20260909/cycle-043/art')
def svg(name,body):
 (out/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><title>'+name.replace('-',' ').title()+'</title>'+body+'</svg>\n')
# Four front-view speaker symbols form a schematic surrounding layout, not perspective equipment.
a='<path d="M44 36Q64 28 84 36M44 92Q64 100 84 92M33 52Q25 64 33 76M95 52Q103 64 95 76" fill="none" stroke="#A8C5C5" stroke-width="5" stroke-linecap="round"/>'
for x,y in [(13,14),(85,14),(13,74),(85,74)]:
 a+=f'<rect x="{x}" y="{y}" width="30" height="40" rx="6" fill="#52677A"/><path d="M{x+5} {y+5}h20" stroke="#79909F" stroke-width="3" stroke-linecap="round"/><circle cx="{x+15}" cy="{y+13}" r="4" fill="#D5C39D"/><circle cx="{x+15}" cy="{y+28}" r="9" fill="#AABFC4"/><circle cx="{x+15}" cy="{y+28}" r="4" fill="#405B6C"/>'
a+='<circle cx="64" cy="64" r="17" fill="#DCB57E"/><path d="M54 64h3l3-7 6 14 4-7h4" fill="none" stroke="#FFF0CF" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
svg('quadraphonic-sound',a)
# Two literary pages with distinct abstract line groupings, joined by a transfer arrow.
# No invented script, copied prose or implied particular language pair.
svg('literary-translation','''<rect x="10" y="18" width="43" height="83" rx="6" fill="#729B9C"/><rect x="15" y="14" width="38" height="82" rx="4" fill="#F1E5CF"/><path d="M25 28h17M24 43h19M24 51h15M24 59h19M24 76h18M24 84h13" stroke="#8A8274" stroke-width="3" stroke-linecap="round"/><rect x="75" y="33" width="43" height="81" rx="6" fill="#A58AAA"/><rect x="75" y="29" width="38" height="80" rx="4" fill="#F1E5CF"/><path d="M86 43h17M86 58h9m6 0h3M86 66h18M86 74h8m6 0h4M86 91h18M86 99h12" stroke="#8A8274" stroke-width="3" stroke-linecap="round"/><path d="M42 113h15q7 0 7-7V22q0-8 8-8h17" fill="none" stroke="#DCA766" stroke-width="6" stroke-linecap="round"/><path d="m84 5 13 9-13 9" fill="none" stroke="#DCA766" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>''')
# Front-view monitor, separate top-view mouse and keyboard as a teaching diagram.
svg('computer-basics','''<path d="M54 66h14v18H54z" fill="#7E929C"/><rect x="38" y="80" width="47" height="7" rx="3.5" fill="#A9B9BE"/><rect x="9" y="16" width="102" height="57" rx="7" fill="#5A7180"/><rect x="16" y="23" width="88" height="41" rx="3" fill="#BDD5D5"/><path d="M29 32v22l7-6 6 10 5-3-6-10h9z" fill="#FFF1D5" stroke="#617B86" stroke-width="2" stroke-linejoin="round"/><path d="M63 35h27M63 45h18" stroke="#7B9B9E" stroke-width="4" stroke-linecap="round"/><rect x="10" y="93" width="76" height="20" rx="5" fill="#9AAEB6"/><path d="M20 100h5m7 0h5m7 0h5m7 0h5m7 0h7M29 107h39" stroke="#E2E4D9" stroke-width="3" stroke-linecap="round"/><rect x="95" y="83" width="22" height="32" rx="11" fill="#D4AE7C"/><path d="M106 84v11M96 96h20" stroke="#A38057" stroke-width="2"/><path d="M106 87v4" stroke="#F3DFB8" stroke-width="3" stroke-linecap="round"/>''')
