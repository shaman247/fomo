"""Tests for the exported click-through URL order (`exporter.order_event_urls`).

Ground truth is the 2026-08-17 measurement of live, exported events: 16 published a
past-dated occurrence permalink as their primary while holding a future-dated sibling,
and 116 held more than one `sort_order = 0` row, so `sort_order` alone cannot identify
the link the frontend renders.
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exporter import order_event_urls, url_embedded_date

TODAY = date(2026, 8, 17)


class TestUrlEmbeddedDate(unittest.TestCase):
    def test_iso_and_us_day_precision_dates_parse(self):
        cases = {
            "https://stpaulandstandrew.org/event/wscah-86th-street-market-2-2/2026-08-11/":
                date(2026, 8, 11),
            "https://www.nypl.org/events/programs/2026/08/03/chair-yoga": date(2026, 8, 3),
            "https://www.brooklynmuseum.org/programs/member-mornings-2026/09-19-2026":
                date(2026, 9, 19),
            "https://calendar.aiany.org/2026/08/06/petals-and-pushcarts/": date(2026, 8, 6),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(url_embedded_date(url), expected)

    def test_bare_year_slugs_are_not_dates(self):
        """`/long-play-2026` read as Jan 1 would rank a live URL as expired."""
        for url in ("https://bangonacan.org/long-play-2026/",
                    "https://example.org/summer-2026",
                    "https://www.brooklynmuseum.org/programs/member-mornings-iris-van-herpen-2026",
                    "https://example.org/shows/a-true-york-comedy-experience-f06f6b5b"):
            with self.subTest(url=url):
                self.assertIsNone(url_embedded_date(url))

    def test_impossible_dates_are_not_dates(self):
        self.assertIsNone(url_embedded_date("https://example.org/e/2026-13-45/"))

    def test_slug_year_next_to_a_us_date_does_not_bleed_into_it(self):
        """Brooklyn Museum's shape: a `-2026/` slug year immediately before an
        `MM-DD-YYYY` occurrence date. Mixing the two ("2026/08-15") silently
        picks up the slug's year, which is wrong the moment they disagree."""
        self.assertEqual(
            url_embedded_date(
                "https://www.brooklynmuseum.org/programs/member-mornings-2025/09-19-2026"),
            date(2026, 9, 19))
        self.assertEqual(
            url_embedded_date(
                "https://www.brooklynmuseum.org/programs/member-mornings-2026/08-15-2026"),
            date(2026, 8, 15))


class TestOrderEventUrls(unittest.TestCase):
    def test_expired_primary_yields_to_the_next_upcoming_url(self):
        urls = [
            "https://www.stmarkscomedy.com/shows/friday-night-laughs-2026-08-14-4c805c45",
            "https://www.stmarkscomedy.com/shows/friday-night-laughs-2026-10-02-aaaa",
            "https://www.stmarkscomedy.com/shows/friday-night-laughs-2026-09-04-c3fea67f",
        ]
        self.assertEqual(order_event_urls(urls, TODAY), [urls[2], urls[0], urls[1]])

    def test_todays_url_still_counts_as_upcoming(self):
        urls = ["https://x.org/e/2026-08-10/", "https://x.org/e/2026-08-17/"]
        self.assertEqual(order_event_urls(urls, TODAY), [urls[1], urls[0]])

    def test_no_url_is_ever_dropped_or_duplicated(self):
        urls = ["https://x.org/e/2026-08-10/", "https://x.org/about",
                "https://x.org/e/2026-09-01/"]
        self.assertCountEqual(order_event_urls(urls, TODAY), urls)

    def test_live_primary_is_left_alone(self):
        """Only a demonstrably expired head moves — this is not a re-sort."""
        urls = ["https://x.org/e/2026-09-01/", "https://x.org/e/2026-08-20/"]
        self.assertEqual(order_event_urls(urls, TODAY), urls)

    def test_undated_primary_is_left_alone(self):
        """An undated slug is usually the evergreen program page — never demote it."""
        urls = ["https://x.org/programs/chair-yoga", "https://x.org/e/2026-09-01/"]
        self.assertEqual(order_event_urls(urls, TODAY), urls)

    def test_all_dates_past_keeps_the_incoming_order(self):
        urls = ["https://x.org/e/2026-08-10/", "https://x.org/e/2026-08-01/"]
        self.assertEqual(order_event_urls(urls, TODAY), urls)

    def test_a_different_host_never_wins_the_primary(self):
        """e139847's shape: an expired NYPL Chair Yoga link beside an upcoming
        NYC Parks one. That is a cross-site over-merge, not a stale link, and
        promoting it would point the event at another organization's page."""
        urls = ["https://www.nypl.org/events/programs/2026/08/03/chair-yoga-hosted-shapeup-nyc",
                "https://www.nycgovparks.org/events/2026/08/19/chair-yoga"]
        self.assertEqual(order_event_urls(urls, TODAY), urls)

    def test_www_prefix_is_not_a_different_host(self):
        urls = ["https://www.x.org/e/2026-08-10/", "https://x.org/e/2026-09-01/"]
        self.assertEqual(order_event_urls(urls, TODAY), [urls[1], urls[0]])

    def test_single_and_empty_lists(self):
        self.assertEqual(order_event_urls(["https://x.org/e/2026-08-10/"], TODAY),
                         ["https://x.org/e/2026-08-10/"])
        self.assertEqual(order_event_urls([], TODAY), [])


if __name__ == "__main__":
    unittest.main()
