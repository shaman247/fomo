"""BL35/BL36: source plugins that see a legitimately smaller source.

BL35 — a Weeknights club the API answers for, with nothing upcoming in the
coverage area, is a processed 0-event crawl (an explicitly empty JSON body),
not a failed one. A missing club or a malformed answer still fails.

BL36 — the Bhakti Center Shastri course card is optional: when the publisher
drops it from the listing, the remaining offerings are still captured. The
listing's own inventory checks still fail closed.
"""
import json
import sys
import unittest
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor  # noqa: E402

try:
    from sources import weeknights
except ImportError:
    weeknights = None
try:
    from sources import bhakti_offerings
except ImportError:
    bhakti_offerings = None

NOW = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
PAST = {"public_id": "evt_past", "title": "Book Swap NYC", "start_at": "2026-09-29T22:00:00+00:00",
        "end_at": "2026-09-29T23:30:00+00:00", "timezone": "America/New_York"}
CLUB = {"id": "club-1", "title": "Amigas Means Friends"}


@unittest.skipIf(weeknights is None, 'deployment-specific source plugin not installed')
class WeeknightsEmptyClubTests(unittest.TestCase):
    def run_fetch(self, listing=None, error=None, detail=None):
        def post(fn, payload):
            if fn == "manage-calendars":
                if error:
                    raise error
                return listing
            if detail is None:
                raise RuntimeError("events.get down")
            return detail
        real_fetch_club = weeknights.fetch_club
        with mock.patch.object(weeknights, "_post", side_effect=post), \
                mock.patch.object(weeknights, "fetch_club",
                                  side_effect=lambda slug: real_fetch_club(slug, now=NOW)):
            return weeknights.fetch_and_build_markdown(["https://weeknights.co/amigas-means-friends"])

    def test_found_club_with_only_past_events_is_explicitly_empty(self):
        body, count = self.run_fetch({"club": CLUB, "events": [PAST], "total_event_count": 1})
        self.assertEqual(count, 0)
        self.assertTrue(body)  # a non-empty body, so the crawler stores it
        self.assertTrue(extractor.is_empty_api_payload(body))
        self.assertIn("https://weeknights.co/amigas-means-friends", body)

    def test_found_club_with_no_events_at_all_is_explicitly_empty(self):
        body, count = self.run_fetch({"club": CLUB, "events": [], "total_event_count": 0})
        self.assertEqual(count, 0)
        self.assertTrue(extractor.is_empty_api_payload(body))

    def test_upcoming_events_all_out_of_area_is_explicitly_empty(self):
        denver = dict(PAST, public_id="evt_den", start_at="2026-10-20T15:00:00+00:00",
                      end_at="2026-10-20T16:00:00+00:00", timezone="America/Denver")
        detail = {"event": {}, "location": {"address": "1260 22nd St, Denver, CO 80205, US",
                                            "latitude": 39.75, "longitude": -104.99}}
        body, count = self.run_fetch({"club": CLUB, "events": [denver]}, detail=detail)
        self.assertEqual(count, 0)
        self.assertTrue(extractor.is_empty_api_payload(body))

    def test_missing_club_fails(self):
        import urllib.error
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with self.assertRaises(RuntimeError):
            self.run_fetch(error=missing)

    def test_malformed_listing_fails(self):
        for bad in ({}, {"club": CLUB}, {"events": []}, {"club": {"title": "x"}, "events": []},
                    {"club": CLUB, "events": "none"}):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                self.run_fetch(bad)

    def test_detail_outage_that_drops_every_upcoming_event_fails(self):
        upcoming = dict(PAST, public_id="evt_up", start_at="2026-10-20T22:00:00+00:00",
                        end_at="2026-10-20T23:00:00+00:00")
        with self.assertRaises(RuntimeError):
            self.run_fetch({"club": CLUB, "events": [upcoming]}, detail=None)

    def test_no_club_url_fails(self):
        with self.assertRaises(RuntimeError):
            weeknights.fetch_and_build_markdown(["https://weeknights.co/events/evt_x"])


def bhakti_listing(urls, combined=False):
    """A formatter-shaped capture: one section + one markdown chunk per card."""
    if combined:
        urls = urls + [bhakti_offerings.COMBINED]
    n = len(urls)
    html = (f'<main><p>DETAIL-BODIES {n}/{n}</p>'
            f'<p>OFFERING-COLUMNS total={n} cards={n} merged=0 unrecognized=0</p>')
    md = '# All Offerings\n\n'
    for i, url in enumerate(urls):
        title = f'Offering {i}'
        body = [url, f'Detail paragraph {i} one.', f'Detail paragraph {i} two.']
        if url == bhakti_offerings.COMBINED:
            body += ['https://momence.com/Bhakti-Center/Bhakti-Shastri-Course-Online/111',
                     'https://momence.com/Bhakti-Center/Bhakti-Shastri-Course-In-person/222']
        html += (f'<section data-source-url="{escape(url)}"><h2>{escape(title)}</h2>'
                 + ''.join(f'<p>{escape(line)}</p>' for line in body) + '</section>')
        md += f'## {title}\n' + '\n'.join(body) + '\n\n'
    return html + '</main>', md


@unittest.skipIf(bhakti_offerings is None, 'deployment-specific source plugin not installed')
class BhaktiOptionalCombinedBlockTests(unittest.TestCase):
    URLS = ['https://bhakticenter.org/marma/', 'https://bhakticenter.org/intro-to-sanskrit/',
            'https://bhakticenter.org/tuesdaynightkirtan/']

    def test_listing_without_combined_block_keeps_every_offering(self):
        html, md = bhakti_listing(self.URLS)
        prefix, rows, links = bhakti_offerings.source_sections(html, md)
        self.assertEqual([r['url'] for r in rows], self.URLS)
        self.assertEqual(links, [])
        result = bhakti_offerings.build_result(prefix, rows, [], {}, {})
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['markdown'], md)
        self.assertIsNone(result['audit']['original_combined_block'])
        self.assertEqual(result['audit']['markdown_sha256'], bhakti_offerings.sha(result['markdown']))

    def test_combined_block_still_requires_its_two_registrations(self):
        html, md = bhakti_listing(self.URLS, combined=True)
        _, rows, links = bhakti_offerings.source_sections(html, md)
        self.assertEqual(len(links), 2)
        one_link = md.replace('https://momence.com/Bhakti-Center/Bhakti-Shastri-Course-In-person/222\n', '')
        one_link_html = html.replace('<p>https://momence.com/Bhakti-Center/Bhakti-Shastri-Course-In-person/222</p>', '')
        with self.assertRaises(ValueError):
            bhakti_offerings.source_sections(one_link_html, one_link)
        # A present block with no normalized courses must not pass silently.
        with self.assertRaises(ValueError):
            bhakti_offerings.build_result('', rows, [], {}, {})

    def test_broken_listing_still_fails_closed(self):
        html, md = bhakti_listing(self.URLS)
        cases = {
            'detail inventory short': (html.replace('DETAIL-BODIES 3/3', 'DETAIL-BODIES 2/3'), md),
            'tally missing': (html.replace('OFFERING-COLUMNS total=3 cards=3 merged=0 unrecognized=0', ''), md),
            'unaccounted column': (html.replace('total=3 cards=3', 'total=4 cards=3'), md),
            'section boundaries changed': (html, md.replace('## Offering 1', '### Offering 1')),
            'error page': ('<main><h1>Page not found</h1></main>', '# Page not found\n'),
        }
        for name, (bad_html, bad_md) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                bhakti_offerings.source_sections(bad_html, bad_md)

    def test_skip_diagnostic_reaches_the_run_log(self):
        html, md = bhakti_listing(self.URLS)
        prefix, rows, _ = bhakti_offerings.source_sections(html, md)
        result = bhakti_offerings.build_result(prefix, rows, [], {}, {})
        stderr = ('  ! Bhakti: combined course block https://bhakticenter.org/bg1-6/ not on the listing; '
                  'skipping registration sessions (3 other offerings kept)\nnoise line\n')
        with mock.patch.object(bhakti_offerings.subprocess, 'Popen') as popen, \
                mock.patch('agent_extraction.work_dir', return_value=Path(self.tmp)), \
                mock.patch('builtins.print') as printed:
            popen.return_value.communicate.return_value = (json.dumps(result), stderr)
            popen.return_value.returncode = 0
            markdown, count = bhakti_offerings.fetch_offerings([bhakti_offerings.LISTING])
        self.assertEqual((markdown, count), (md, 3))
        lines = [c.args[0] for c in printed.call_args_list]
        self.assertTrue(any('not on the listing' in line for line in lines))
        self.assertFalse(any('noise line' in line for line in lines))

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


if __name__ == '__main__':
    unittest.main()
