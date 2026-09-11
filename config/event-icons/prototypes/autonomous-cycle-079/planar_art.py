"""Five original flat symbolic activity diagrams; no apparatus or anatomy model."""
from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-079/art')
# Television screen and two spectator conversation bubbles. Abstract screen
# content is not a still, branded program logo, cast portrait or actual venue.
a='<rect x="10" y="16" width="108" height="72" rx="8" fill="#849CA9"/><rect x="19" y="25" width="90" height="52" rx="3" fill="#E9DDBF"/><path d="m40 53 15-17 13 16 12-10 17 24H29Z" fill="#A2B3A0"/><path d="M52 89v7h24v-7" fill="#849CA9"/><path d="M12 86h26q12 0 12 11v7q0 11-12 11H27l-12 7v-8q-11-2-11-12v-5q0-11 8-11Z" fill="#BC8D99"/><path d="M90 86h26q8 0 8 11v5q0 10-11 12v8l-12-7H90q-12 0-12-11v-7q0-11 12-11Z" fill="#8CA89C"/><path d="M16 99h22m52 0h22" stroke="#F3E6CC" stroke-width="3" stroke-linecap="round"/>'
# Computing represented by original braces and syntax marks, with a discussion
# tail. This is an explanatory talk, not a computer or code editor tutorial.
c='<path d="M24 11h80q15 0 15 15v49q0 15-15 15H74L58 106V90H24Q9 90 9 75V26q0-15 15-15Z" fill="#8DA79F"/><path d="M43 30q-9 0-9 10v3q0 8-8 8 8 0 8 8v3q0 10 9 10m42-42q9 0 9 10v3q0 8 8 8-8 0-8 8v3q0 10-9 10" stroke="#F0E1BC" stroke-width="5" stroke-linecap="round" fill="none"/><path d="m59 64 10-26" stroke="#F0E1BC" stroke-width="5" stroke-linecap="round"/><circle cx="26" cy="108" r="8" fill="#BD949D"/><circle cx="100" cy="108" r="8" fill="#BD949D"/>'
# A voice waveform contained by a calm, open listening circle. No mouth/neck,
# breathing instruction, microphone, brain scan or clinical measurement implied.
d='<path d="M34 24a47 47 0 1 1-12 56" stroke="#8BA79F" stroke-width="8" stroke-linecap="round" fill="none"/><path d="M25 55v10m13-23v36m13-45v54m13-49v44m13-39v34m13-28v22m13-15v8" stroke="#B58C9D" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M8 36q8-8 18-10m-9 13q5-4 11-5" stroke="#C9AC7F" stroke-width="4" stroke-linecap="round" fill="none"/>'
# An observation inventory with two invented biodiversity symbols and tally
# checks. This is not an app screenshot or identification key.
e='<rect x="20" y="12" width="88" height="106" rx="7" fill="#EDE1C5"/><rect x="45" y="7" width="38" height="13" rx="5" fill="#9BAFA3"/><path d="M37 57Q30 33 56 30q7 26-19 27Z" fill="#8DA98E"/><path d="m36 62 15-24" stroke="#668A79" stroke-width="3" stroke-linecap="round"/><path d="M31 91q1-18 20-18t20 18Z" fill="#BE8F82"/><path d="M47 91h9v16h-9Z" fill="#C8AE89"/><path d="m78 44 6 6 11-13m-17 48 6 6 11-13" stroke="#86A1A5" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
# Flat camera glyph plus volunteer-support heart; the heart is not a consent
# badge, beneficiary portrait or promise that pictures can be shared publicly.
f='<path d="M13 37h20l8-14h36l9 14h20q12 0 12 12v46q0 12-12 12H22q-12 0-12-12V49q0-12 3-12Z" fill="#809DA7"/><circle cx="61" cy="69" r="25" fill="#E6D8B8"/><circle cx="61" cy="69" r="18" fill="#547886"/><circle cx="55" cy="63" r="6" fill="#91B0B4"/><rect x="95" y="46" width="12" height="7" rx="2" fill="#E6D8B8"/><path d="M97 120C90 114 76 104 76 93c0-12 13-17 21-6 8-11 21-6 21 6 0 11-14 21-21 27Z" fill="#BD8797"/>'
for name,body in [('television-watch-party',a),('computing-talk',c),('contemplative-voice',d),('bioblitz',e),('volunteer-photography',f)]:
 (b/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+body+'</svg>\n')
