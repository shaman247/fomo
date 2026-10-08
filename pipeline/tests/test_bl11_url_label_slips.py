"""Neighbour-link slips are restored from the source's own link labels (BL11).

Fixtures (`fixtures/bl11_url_label_slips.json`) pair a trimmed real crawl
excerpt with the records the extraction returned for it.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import repair_url_label_slips

FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'bl11_url_label_slips.json')
                      .read_text(encoding='utf-8'))


def repair(case):
    response = json.dumps({'events': case['events']})
    with contextlib.redirect_stdout(io.StringIO()):
        out = repair_url_label_slips(case['content'], response)
    return response, json.loads(out)['events']


class UrlLabelSlipTests(unittest.TestCase):
    def test_shifted_card_gets_the_link_its_title_labels(self):
        # Brooklyn Public Library cr123180: Maternal Health Workshop came back
        # with the next card's node/843367 (University Open Air's).
        case = FIXTURES['bpl_shift']
        _, events = repair(case)
        by_name = {e['name']: e['url'] for e in events}
        for name, url in case['expect'].items():
            self.assertEqual(by_name[name], url)
        self.assertEqual(
            by_name['University Open Air: Technical Drawing Exercises for Beginners'],
            'https://www.bklynlibrary.org/node/843367')
        self.assertEqual(len({e['url'] for e in events}), len(events))

    def test_records_that_share_or_own_their_links_are_untouched(self):
        for key in ('ucb_byot_misnamed', 'nyctourism_comic_con', 'basie_image_link',
                    'timely_exhibition_reception'):
            with self.subTest(key):
                response, events = repair(FIXTURES[key])
                self.assertEqual(events, json.loads(response)['events'])

    def test_unparseable_or_empty_responses_pass_through(self):
        self.assertEqual(repair_url_label_slips('[A](https://a.example/1)', 'not json'), 'not json')
        self.assertEqual(repair_url_label_slips('', '{"events": []}'), '{"events": []}')


if __name__ == '__main__':
    unittest.main()
