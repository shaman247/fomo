"""Tests for the Luma calendar-endpoint guard in the extract-stage filter.

**Why this is NOT in `is_obvious_non_event`.** That function sees a name and a
description; this defect has neither tell. e208609 "Technologists" (w5111
Fractal Tech) was the calendar's own `tags[].name` — an audience label with
`upcoming_event_count: 0` — read out of the calendar-level half of the
`api.lu.ma/url?url=nyc-tech` JSON, with `url: null`, no description, and **36
merged occurrences** pooled from every real Fractal Tech event's times. It
false-matched every real Fractal meetup in the dedupe pass. "Technologists" is
an unremarkable event name; only the URL gives it away.

**Why it is NOT in a source plugin.** There is no Luma plugin — Luma organizers
are ordinary `website_urls` rows crawled by the standard crawler (92 such URLs),
so `pipeline/sources/` has nowhere to host it. And a fetcher could not see the
offending URL anyway: the record arrives with `url: null`, and the calendar
endpoint only becomes its URL later, when `group_event_occurrences` falls back
to `source_url`. The extract loop in `process_crawl_result` is the one place
that holds both the row and `source_url`, which is where the sibling
`is_cancelled_by_url` arm already lives.

**The rule.** Reject a record whose *effective* URL (own URL if any, else
`source_url`) addresses the very Luma calendar the page was crawled from, and
whose description is blank.

Both halves are load-bearing:

* Self-referential, not shape-only. `api.lu.ma/url?url=<slug>` also accepts an
  EVENT slug — e199135 carries a live `api.lu.ma/url?url=pubkey-jj3u`, a real
  PubKey event whose link is merely the unusable JSON form. Only the comparison
  against `source_url` separates the calendar from an event.
* Blank description. e161574 (w3328 Accent Sisters, "We Are Here 《我们在这里》
  Screening & Discussion with Shi Tou") is a REAL screening whose only URL is
  its own calendar page `lu.ma/calendar/cal-Sc85BAZzQ7GZiZE`. Its description
  spares it. Without this gate the rule runs 1 false positive out of 2 hits.

`luma.com/user/<handle>` host pages are deliberately excluded: both corpus
instances (w1108 knitting workshops) are real, described events.

Measured 2026-08-16 (`.scratch/luma_measure.py`, `.scratch/luma_replay_all.py`):

    event_urls rows scanned                        279,635
      URL-shape hits (Luma calendar endpoint)            3
      + self-referential                                 2
      + blank description  (THE RULE)                    1   -> e208609, true junk
    crawl_events rows scanned                    1,077,757
      THE RULE                                           1   -> same row
    replay over every Luma extraction    2,182 crawl_results / 10,363 rows
      self-referential records                           3
      THE RULE                                           2   -> e208609 "Technologists"
                                                              + cr114300 "The Canvas NYC"

    precision: 2 hits / 2 true junk / 0 false positives

"The Canvas NYC" (w2653, `api.lu.ma/calendar/get-items?calendar_api_id=…`) was
the calendar's own `name`, extracted the morning this guard was written — a
second site, a second endpoint form, the same defect. It never reached the map.

Do not loosen either gate without re-running those two scripts.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import _luma_calendar_key, is_luma_calendar_listing_url


NYC_TECH = 'https://api.lu.ma/url?url=nyc-tech'
CANVAS = ('https://api.lu.ma/calendar/get-items?calendar_api_id='
          'cal-8pBzUbxu1rqFgsw&period=future&pagination_limit=50')
ACCENT = 'https://lu.ma/calendar/cal-Sc85BAZzQ7GZiZE'


class TestLumaCalendarKey(unittest.TestCase):
    """The three endpoint forms Luma organizer sources actually use."""

    def test_slug_endpoint(self):
        self.assertEqual(_luma_calendar_key(NYC_TECH), 'slug:nyc-tech')

    def test_get_items_endpoint(self):
        self.assertEqual(_luma_calendar_key(CANVAS), 'cal:cal-8pbzubxu1rqfgsw')

    def test_calendar_page(self):
        self.assertEqual(_luma_calendar_key(ACCENT), 'cal:cal-sc85bazzq7gzize')
        self.assertEqual(
            _luma_calendar_key('https://luma.com/calendar/cal-Sc85BAZzQ7GZiZE'),
            'cal:cal-sc85bazzq7gzize')

    def test_key_ignores_query_noise_and_trailing_slash(self):
        """The same calendar reached two ways must compare equal."""
        self.assertEqual(
            _luma_calendar_key('https://api.lu.ma/calendar/get-items/'
                               '?calendar_api_id=cal-8pBzUbxu1rqFgsw'),
            _luma_calendar_key(CANVAS))

    def test_not_a_calendar(self):
        for url in (
            '',
            None,
            'https://lu.ma/2diqa4rd',                    # a real event page
            'https://luma.com/thecanvas-a9m4',           # a real event page
            'https://luma.com/user/usr-fMdmHgwkfKFqXoQ',  # host page, not a calendar
            'https://luma.com/nyc',                      # discover feed
            'https://partiful.com/e/i4op0BIzi5SNaqoxsohm',
            'https://api.lu.ma/discover/get-paginated-events?slug=nyc',
            'https://api.lu.ma/calendar/get-items?period=future',  # no calendar id
        ):
            with self.subTest(url=url):
                self.assertEqual(_luma_calendar_key(url), '')

    def test_event_slug_on_the_api_endpoint_still_keys(self):
        """`url?url=` takes event slugs too — the key differs, which is the point."""
        self.assertEqual(
            _luma_calendar_key('https://api.lu.ma/url?url=pubkey-jj3u'),
            'slug:pubkey-jj3u')


class TestLumaCalendarListingUrl(unittest.TestCase):
    """Self-referential means "this record has no event page of its own"."""

    def test_the_technologists_shape_fires(self):
        """e208609: url:null, so the effective URL is the source itself."""
        self.assertTrue(is_luma_calendar_listing_url(NYC_TECH, NYC_TECH))

    def test_the_canvas_get_items_shape_fires(self):
        self.assertTrue(is_luma_calendar_listing_url(CANVAS, CANVAS))

    def test_calendar_page_shape_fires(self):
        self.assertTrue(is_luma_calendar_listing_url(ACCENT, ACCENT))

    def test_real_event_url_never_fires(self):
        for url in ('https://lu.ma/2diqa4rd', 'https://luma.com/thecanvas-a9m4',
                    'https://partiful.com/e/i4op0BIzi5SNaqoxsohm'):
            with self.subTest(url=url):
                self.assertFalse(is_luma_calendar_listing_url(url, NYC_TECH))

    def test_pubkey_event_on_the_api_endpoint_is_spared(self):
        """e199135 — an EVENT slug on the calendar's endpoint shape. Real event."""
        self.assertFalse(is_luma_calendar_listing_url(
            'https://api.lu.ma/url?url=pubkey-jj3u',
            'https://api.lu.ma/url?url=pubkey'))

    def test_a_different_calendar_is_not_self_referential(self):
        self.assertFalse(is_luma_calendar_listing_url(CANVAS, NYC_TECH))

    def test_missing_source_url_never_fires(self):
        self.assertFalse(is_luma_calendar_listing_url(NYC_TECH, ''))
        self.assertFalse(is_luma_calendar_listing_url(NYC_TECH, None))
        self.assertFalse(is_luma_calendar_listing_url('', ''))

    def test_non_luma_self_reference_never_fires(self):
        """A listing-page URL on any other site is normal and must survive."""
        for url in ('https://www.barbesbrooklyn.com/calendar',
                    'https://viewcyembed.com/barbes',
                    'https://www.eventbrite.com/o/someone-12345'):
            with self.subTest(url=url):
                self.assertFalse(is_luma_calendar_listing_url(url, url))


class TestExtractLoopIntegration(unittest.TestCase):
    """The guard as the extract loop composes it: effective URL + blank body."""

    @staticmethod
    def _would_drop(row, source_url):
        from processor import absolutize_url, _description_is_blank
        if not source_url or not _description_is_blank(row.get('description')):
            return False
        effective = absolutize_url((row.get('url') or '').strip(), source_url) or source_url
        return is_luma_calendar_listing_url(effective, source_url)

    def test_technologists_row_is_dropped(self):
        self.assertTrue(self._would_drop(
            {'name': 'Technologists', 'url': None,
             'description': 'No description available.'}, NYC_TECH))

    def test_the_canvas_row_is_dropped(self):
        self.assertTrue(self._would_drop(
            {'name': 'The Canvas NYC', 'url': '',
             'description': 'No description available.'}, CANVAS))

    def test_real_luma_event_without_a_description_survives(self):
        """Blank bodies are ordinary on Luma listings — the URL is the tell."""
        self.assertFalse(self._would_drop(
            {'name': 'Fractal Circles', 'url': 'https://lu.ma/2diqa4rd',
             'description': 'No description available.'}, NYC_TECH))

    def test_accent_sisters_screening_survives(self):
        """e161574 — urlless on its own calendar page, but really an event."""
        self.assertFalse(self._would_drop(
            {'name': 'We Are Here 《我们在这里》Screening & Discussion with Shi Tou',
             'url': None,
             'description': 'A film screening and discussion event featuring Shi Tou.'},
            ACCENT))

    def test_urlless_row_on_a_non_luma_site_survives(self):
        """Every site with no per-event links would otherwise be wiped out."""
        self.assertFalse(self._would_drop(
            {'name': 'Open Mic', 'url': None, 'description': ''},
            'https://www.barbesbrooklyn.com/calendar'))


if __name__ == '__main__':
    unittest.main()
