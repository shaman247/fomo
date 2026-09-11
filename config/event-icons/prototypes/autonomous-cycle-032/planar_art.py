"""Original planar emblems: front-facing documents, stitch diagram, nib and map.
These are symbolic arrangements, not perspective equipment or construction diagrams.
No fonts, embedded raster images or borrowed artwork.
"""
from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-032/art')
def svg(name,body):
 (b/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><title>'+name.replace('-',' ').title()+'</title>'+body+'</svg>\n')
svg('personal-archiving','''<path fill="#459598" d="M13 29q0-8 8-8h29l10 10h46q8 0 8 8v65q0 9-9 9H22q-9 0-9-9Z"/><path fill="#EFE8D8" d="M29 14h51q5 0 5 5v66H24V19q0-5 5-5Z"/><path fill="#8BAAB4" d="M32 23h45v35H32Z"/><circle cx="62" cy="33" r="6" fill="#F1CB77"/><path fill="#60877E" d="m32 51 14-15 13 15 8-7 10 8v6H32Z"/><path fill="#D5CCC0" d="M33 66h36v4H33Zm0 9h26v4H33Z"/><path fill="#FFF4E4" d="M75 42h34q5 0 5 5v42H70V47q0-5 5-5Z"/><path fill="#82969A" d="M79 53h25v4H79Zm0 10h19v4H79Zm0 10h25v4H79Z"/><path fill="#60B5AD" d="M15 80q0-7 7-7h34l8 9h48q6 0 5 7l-4 19q-1 6-8 6H23q-7 0-8-7Z"/><rect x="44" y="91" width="39" height="14" rx="3" fill="#E7ECE0"/><path d="M51 98h25" fill="none" stroke="#7A9B97" stroke-width="3" stroke-linecap="round"/>''')
# The broad pointed nib is a flat cutaway-style symbol, with slit and breather.
svg('pointed-pen-calligraphy','''<rect x="14" y="34" width="83" height="80" rx="7" fill="#E3DAC8"/><rect x="14" y="30" width="79" height="79" rx="6" fill="#FFF1DB"/><path d="M25 56h53M25 77h53M25 98h53" fill="none" stroke="#DCCEB5" stroke-width="2"/><path d="M26 82C44 70 30 53 26 69c-4 17 9 31 19 12 11-21 0-34-5-24-9 19 14 39 24 18 7-14 11-14 13-10" fill="none" stroke="#596689" stroke-width="4" stroke-linecap="round"/><path fill="#687B9C" d="m84 52 24-39q4-6 9-3t1 10L94 61Z"/><path fill="#8EA4BF" d="m88 51 23-37q2-3 4-2L93 56Z"/><path fill="#B6C6CE" d="m83 49 15 10-13 15-19 9 4-21Z"/><path fill="#8DA3B0" d="m91 57 7 2-13 15-19 9 12-15Z"/><circle cx="80" cy="65" r="3.2" fill="#4D6073"/><path d="m78 68-12 15" stroke="#4D6073" stroke-width="2.3"/>''')
svg('film-location-tour','''<rect x="14" y="25" width="95" height="85" rx="9" fill="#D5E4C5"/><path d="M16 56h38v51M16 85h75V29" fill="none" stroke="#F8F4E4" stroke-width="8"/><path d="M30 95h44q12 0 12-12V64" fill="none" stroke="#679E96" stroke-width="4" stroke-dasharray="4 7" stroke-linecap="round"/><path fill="#D8866E" d="M87 10a23 23 0 0 0-23 23c0 17 23 35 23 35s23-18 23-35a23 23 0 0 0-23-23Z"/><circle cx="87" cy="33" r="9" fill="#FFF0D4"/><path fill="#4B6271" d="M11 62h57v36q0 6-6 6H17q-6 0-6-6Z"/><path fill="#7793A0" d="M11 62h57v8H11Z"/><path fill="#EDF0E5" d="m10 51 54-13 3 13-54 13Z"/><path fill="#4B6271" d="m14 50 10-2 10 11-10 2Zm23-6 10-2 10 11-10 2ZM60 39l4-1 3 13-2 1Z"/><path d="M23 81h30M23 92h20" stroke="#C6D7D6" stroke-width="4" stroke-linecap="round"/>''')
body='<rect x="13" y="19" width="92" height="93" rx="9" fill="#D5CAB4"/><rect x="13" y="15" width="88" height="92" rx="8" fill="#F1E4CB"/>'
# Grid holes coincide with the four corners of every complete stitch.
for y in range(25,86,20):
 for x in range(25,86,20):body+=f'<circle cx="{x}" cy="{y}" r="1.4" fill="#BBAE94"/>'
centers=[(55,35),(35,55),(55,55),(75,55),(55,75)]
for col,sign in [('#AD6368',1),('#D38B84',-1)]:
 d=''.join(f'M{x-10} {y-10*sign}l20 {20*sign}' for x,y in centers)
 body+=f'<path d="{d}" fill="none" stroke="{col}" stroke-width="4.8" stroke-linecap="round"/>'
body+='<path d="M105 24q16 8 6 22T98 72" fill="none" stroke="#D58C87" stroke-width="3" stroke-linecap="round"/><path d="m91 76 14-54q1-5 4-4t2 6L94 77l-4 8Z" fill="#8199A5"/><path d="m107 23-2 7" stroke="#E8EEE8" stroke-width="2.4" stroke-linecap="round"/>'
svg('cross-stitch',body)
