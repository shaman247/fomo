"""Film Forum's TNEW showtime js_code keeps full titles and per-showing titles (BL11).

Tessitura cuts production titles at 30 characters (`A CHRONICLE OF AMOROUS
INCIDEN` is A Chronicle of Amorous Accidents) and puts chapter / caption
distinctions only in each performance's title. The fixture
(`fixtures/bl11_filmforum_tnew.json`) holds the deployed js_code for
website_urls 5017, a trimmed real API response and the matching JSON-LD from
filmforum.org/now_playing. The js_code is run under Node with a synchronous
XHR stub, as Chromium runs it in the crawl.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'bl11_filmforum_tnew.json')
                     .read_text(encoding='utf-8'))

HARNESS = r'''
const fs = require('fs'), input = JSON.parse(fs.readFileSync(0, 'utf8'));
let html = '';
global.document = {body: {set innerHTML(x) { html = x; }}};
global.XMLHttpRequest = class {
  open(method, url) { this.url = url; }
  setRequestHeader() {}
  send() {
    this.status = 200;
    this.responseText = this.url === '/api/products/productionseasons' ? JSON.stringify(input.api)
      : this.url.endsWith('/now_playing') ? input.now_playing
      : this.url.endsWith('/coming_soon') ? input.coming_soon : '';
  }
};
global.DOMParser = class {
  parseFromString(text) {
    const scripts = [...text.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)]
      .map(m => ({textContent: m[1]}));
    return {querySelectorAll: () => scripts};
  }
};
global.Date = class extends Date { constructor(...a) { super(...(a.length ? a : ['2026-10-07T12:00:00'])); } };
eval(input.js);
process.stdout.write(html);
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required to run the in-page js_code')
class FilmForumTnewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = subprocess.run(['node', '-e', HARNESS], input=json.dumps(FIXTURE),
                                  capture_output=True, text=True, check=True).stdout

    def test_cut_title_takes_the_public_title_for_its_slug(self):
        self.assertIn('>A CHRONICLE OF AMOROUS ACCIDENTS</a></h3>', self.html)
        self.assertNotIn('INCIDEN<', self.html)

    def test_unmapped_cut_title_is_flagged(self):
        card = self.html.split('MY UNDESIRABLE FRIENDS: PART 2</a></h3>')[1].split('</div></div>')[0]
        self.assertIn('Title cut at 30 characters by the ticketing system', card)

    def test_performance_titles_survive(self):
        self.assertIn('(MY UNDESIRABLE FRIENDS: CH 1-3)', self.html)
        self.assertIn('(MY UNDESIRABLE FRIENDS: CH 4-5)', self.html)
        self.assertIn('(THE SCOUT - OPEN CAPTIONS)', self.html)

    def test_uncut_titles_and_showtime_lines_are_unchanged(self):
        self.assertIn('>DANTON</a></h3><div>View Event Details</div><div>Showtimes:</div>'
                      '<div>2026-10-07: 6:10PM</div>', self.html)


if __name__ == '__main__':
    unittest.main()
