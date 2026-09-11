"""Original flat symbolic museum membership-orientation diagram."""
from pathlib import Path
b=Path('.scratch/icon-cycles-20260909/cycle-078/art')
body='<rect x="10" y="25" width="105" height="82" rx="9" fill="#D8C7A6"/><path d="m25 55 24-17 24 17v6H25Zm5 10h8v22h-8Zm15 0h8v22h-8Zm15 0h8v22h-8ZM24 88h50v6H24Z" fill="#9C8582"/><rect x="80" y="50" width="24" height="5" rx="2" fill="#B69A83"/><rect x="80" y="61" width="18" height="5" rx="2" fill="#B69A83"/><path d="M77 9h24q16 0 16 15v11q0 15-16 15H88L76 61V47q-14-3-14-14v-9q0-15 15-15Z" fill="#7F9EAB"/><circle cx="89" cy="21" r="3.5" fill="#F3E5C8"/><path d="M89 30v11" stroke="#F3E5C8" stroke-width="6" stroke-linecap="round"/>'
(b/'museum-member-orientation.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+body+'</svg>\n')
