from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-024');pr=Path('config/event-icons/prototypes/autonomous-cycle-024')
def save(name,body):
 s='<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+name.replace('-',' ').title()+'</title>'+body+'</svg>\n';(pr/(name+'.svg')).write_text(s);(b/'art'/(name+'.svg')).write_text(s)
# Planar listening emblem: no head, posture, equipment or health claim.
s='<path fill="#CFA7B2" d="M57 22C38 22 30 36 31 54C32 67 43 71 45 84C46 96 53 106 65 103C76 101 75 90 81 84C91 74 99 61 96 45C93 29 77 20 57 22Z"/><path d="M45 52C43 35 61 30 74 39C86 47 79 60 70 65C62 69 68 76 62 82" fill="none" stroke="#A66D86" stroke-width="6" stroke-linecap="round"/><path d="M21 32Q7 62 22 88M108 32Q122 62 107 88" fill="none" stroke="#72AAA9" stroke-width="6" stroke-linecap="round"/><path d="M34 114Q65 122 96 114" fill="none" stroke="#A2C8C2" stroke-width="4.5" stroke-linecap="round"/>'
save('sound-bath',s)
s='<path fill="#B58B67" d="M51 49H90C101 49 108 57 108 68V108Q108 116 100 116H44Q36 116 36 108V68Q36 49 51 49Z"/><path fill="#D3AF81" d="M44 66Q44 57 54 57H90V108H44Z"/><rect x="42" y="39" width="59" height="13" rx="4" fill="#6E8E87"/><rect x="49" y="72" width="45" height="29" rx="4" fill="#F0E3C9"/><path d="M67 94L77 78" fill="none" stroke="#699173" stroke-width="3" stroke-linecap="round"/><path fill="#79A37B" d="M73 86Q61 88 61 78Q72 77 73 86ZM73 86Q86 88 87 76Q76 75 73 86Z"/><path d="M23 89L33 22" stroke="#6E9370" stroke-width="4" stroke-linecap="round"/><path fill="#7EAE7B" d="M28 58Q5 58 12 38Q30 41 28 58ZM31 41Q34 19 51 20Q55 38 31 41ZM24 76Q10 81 7 65Q21 59 24 76ZM26 64Q29 45 44 47Q44 66 26 64Z"/><path d="M83 40L98 15" stroke="#A6B7BC" stroke-width="6" stroke-linecap="round"/><ellipse cx="101" cy="12" rx="8" ry="5" transform="rotate(-54 101 12)" fill="#B9C8CC"/>'
save('herbal-preparation',s)
def bubble(x,y,c):return f'<path fill="{c}" d="M{x+8} {y}h28q8 0 8 8v21q0 8-8 8h-13l-11 8v-8h-4q-8 0-8-8v-21q0-8 8-8Z"/>'
s=bubble(10,12,'#92B9B7')+bubble(72,12,'#7D9FB9')+bubble(10,70,'#8FA7BE')+bubble(72,70,'#D8A36F')
for x,y in [(22,29),(84,29),(22,87)]:s+=f'<path d="M{x} {y}l6 6l12-13" fill="none" stroke="#F2EBDD" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
s+='<path d="M85 84C85 76 102 76 102 84C102 89 93 89 93 95" fill="none" stroke="#795E57" stroke-width="4.5" stroke-linecap="round"/><circle cx="93" cy="103" r="2.6" fill="#795E57"/>'
save('truth-or-lie-storytelling',s)
