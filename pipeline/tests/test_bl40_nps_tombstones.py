"""Deleted nps.gov event pages answer HTTP 200 (BL40, 2026-10-12).

e139621 (Home of FDR Top Cottage Tour, w4795) stayed live after NPS deleted its
October series: the deleted event-details.htm?id= page is the bare template
under the generic title "Event Details (U.S. National Park Service)", and the
event's other URL is the finished summer series' page, which NPS keeps "for
reference only". Fixture: those two pages and a live one, fetched 2026-10-12.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import liveness_probe as lp

PAGES = json.loads((Path(__file__).parent / 'fixtures' / 'bl40_nps_event_details.json')
                   .read_text(encoding='utf-8'))


def _classify(page, **overrides):
    page = dict(page, **overrides)
    return lp.classify(page['url'], page['status'], page['title'], page['content'], page['url'])


class NpsTombstoneTests(unittest.TestCase):

    def test_deleted_event_page_is_dead(self):
        verdict, reason = _classify(PAGES['deleted'])
        self.assertEqual(verdict, 'dead')
        self.assertIn('nps.gov empty event template', reason)

    def test_finished_series_page_is_dead(self):
        verdict, reason = _classify(PAGES['occurred'])
        self.assertEqual(verdict, 'dead')
        self.assertIn('already occurred', reason)

    def test_live_event_page_stays_alive(self):
        self.assertEqual(_classify(PAGES['live'])[0], 'alive')

    def test_generic_title_alone_is_not_enough(self):
        # A real event page must never die on the title: the template body is required.
        page = dict(PAGES['live'], title=PAGES['deleted']['title'])
        self.assertEqual(_classify(page)[0], 'alive')

    def test_signature_is_scoped_to_nps(self):
        page = dict(PAGES['deleted'], url='https://example.org/planyourvisit/event-details.htm?id=1')
        self.assertNotEqual(_classify(page)[0], 'dead')
        page = dict(PAGES['occurred'], url='https://example.org/event/1')
        self.assertEqual(_classify(page)[0], 'alive')


if __name__ == '__main__':
    unittest.main()
