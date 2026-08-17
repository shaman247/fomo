"""Tests for processor.absolutize_url.

Ground truth is the 2026-07-25 repair pass: 2,688 `event_urls` rows across 601 live events held
a value the frontend cannot render (Utils.isValidUrl accepts http/https only), and 175 events had
nothing else to link to. Every shape below was taken from that data.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from processor import absolutize_url, canonicalize_luma_host


class TestAbsolutizeUrl(unittest.TestCase):
    def test_absolute_url_is_unchanged(self):
        for url in ("https://example.org/events/1", "http://example.org/e?a=b#c"):
            self.assertEqual(absolutize_url(url, "https://src.example/list"), url)

    def test_site_root_path_resolves_against_source(self):
        self.assertEqual(
            absolutize_url("/events/2026/05/27/ranger-tot-time",
                           "https://www.nycgovparks.org/events/kids-in-motion"),
            "https://www.nycgovparks.org/events/2026/05/27/ranger-tot-time")

    def test_relative_path_resolves_against_source(self):
        self.assertEqual(
            absolutize_url("detail/42", "https://example.org/events/list"),
            "https://example.org/events/detail/42")

    def test_protocol_relative_takes_source_scheme(self):
        self.assertEqual(absolutize_url("//cdn.example/e/1", "http://src.example/x"),
                         "http://cdn.example/e/1")

    def test_double_scheme_is_unwrapped(self):
        self.assertEqual(absolutize_url("http://https://linktr.ee/artist", "https://src.example/"),
                         "https://linktr.ee/artist")

    def test_luma_bare_slug_is_site_global_not_calendar_relative(self):
        # The slug lives at luma.com/<slug>, NOT under the calendar path it was listed on.
        for source in ("https://luma.com/calendar/cal-NTMiDyT9ElAgpn",
                       "https://luma.com/bkrun",
                       "https://lu.ma/nyc-tech"):
            self.assertEqual(absolutize_url("a7oxbpwy", source), "https://luma.com/a7oxbpwy")

    def test_luma_slug_rule_does_not_apply_to_other_hosts(self):
        self.assertEqual(absolutize_url("a7oxbpwy", "https://example.org/events/list"),
                         "https://example.org/events/a7oxbpwy")

    def test_non_page_schemes_are_dropped(self):
        for url in ("mailto:hi@example.org", "tel:+12125551212", "javascript:void(0)"):
            self.assertEqual(absolutize_url(url, "https://src.example/"), "")

    def test_empty_and_unresolvable_return_empty(self):
        self.assertEqual(absolutize_url("", "https://src.example/"), "")
        self.assertEqual(absolutize_url(None, "https://src.example/"), "")
        self.assertEqual(absolutize_url("/events/1", ""), "")
        self.assertEqual(absolutize_url("/events/1", None), "")

    def test_signed_cdn_media_urls_are_dropped(self):
        """Instagram/Facebook image CDN links expire, so they are never an event URL.

        Shapes taken from the 29 `event_urls` rows found on 2026-08-02; the signature
        (`oh`/`oe`/`_nc_sig`) makes them 404 within weeks of extraction.
        """
        for url in (
            "https://scontent-iad3-2.cdninstagram.com/v/t39.30808-6/525335330_n.jpg?stp=dst-jpg&oh=00_AfQ&oe=689",
            "https://scontent-sea1-1.cdninstagram.com/v/t51.82787-15/628516610_n.jpg",
            "https://scontent.xx.fbcdn.net/v/t1.6435-9/photo.jpg",
            "https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=123",
            "//scontent-iad3-1.cdninstagram.com/v/t39.30808-6/509288042_n.jpg",
        ):
            with self.subTest(url=url):
                self.assertEqual(absolutize_url(url, "https://src.example/list"), "")

    def test_lookalike_hosts_are_not_dropped(self):
        for url in ("https://cdninstagram.com.example.org/events/1",
                    "https://www.instagram.com/p/Cabc123/",
                    "https://scontenders.example.org/events/1"):
            with self.subTest(url=url):
                self.assertEqual(absolutize_url(url, "https://src.example/list"), url)

    def test_whitespace_is_trimmed(self):
        self.assertEqual(absolutize_url("  /events/1  ", "https://src.example/list"),
                         "https://src.example/events/1")


class TestLumaHostCanonicalization(unittest.TestCase):
    """`lu.ma/<slug>` 301s to `luma.com/<slug>` — one page, two strings.

    The Luma calendar injector emits `lu.ma` while embeds and cross-listing
    sites emit `luma.com`, so the same event arrives under both hosts and every
    URL-keyed comparison downstream sees two unrelated links (3 of the 10 Luma
    slug collisions measured 2026-08-17 were invisible for exactly this reason).
    """

    def test_short_host_is_canonicalized(self):
        for url, expected in (
            ("https://lu.ma/09nr86jb", "https://luma.com/09nr86jb"),
            ("http://lu.ma/09nr86jb", "https://luma.com/09nr86jb"),
            ("https://www.lu.ma/09nr86jb", "https://luma.com/09nr86jb"),
            ("https://www.luma.com/09nr86jb", "https://luma.com/09nr86jb"),
            ("https://LU.MA/09nr86jb", "https://luma.com/09nr86jb"),
        ):
            with self.subTest(url=url):
                self.assertEqual(canonicalize_luma_host(url), expected)
                self.assertEqual(absolutize_url(url, "https://src.example/list"), expected)

    def test_path_query_and_fragment_survive(self):
        self.assertEqual(
            canonicalize_luma_host("https://lu.ma/41q3uicl?lm_source=embed#tickets"),
            "https://luma.com/41q3uicl?lm_source=embed#tickets")
        self.assertEqual(
            canonicalize_luma_host("https://lu.ma/calendar/cal-NTMiDyT9ElAgpn"),
            "https://luma.com/calendar/cal-NTMiDyT9ElAgpn")

    def test_canonical_host_and_non_luma_are_untouched(self):
        for url in ("https://luma.com/09nr86jb",
                    "https://example.org/lu.ma/09nr86jb",
                    "https://notlu.ma/09nr86jb",
                    "https://lu.macro.example/9nr86jb"):
            with self.subTest(url=url):
                self.assertEqual(canonicalize_luma_host(url), url)

    def test_api_host_is_a_different_service_and_is_left_alone(self):
        # api.lu.ma is the JSON endpoint, not an alias of the web page —
        # `_luma_calendar_key` keys the calendar-junk filter off it.
        for url in ("https://api.lu.ma/url?url=pubkey-jj3u",
                    "https://api.lu.ma/calendar/get-items?calendar_api_id=cal-XXX"):
            with self.subTest(url=url):
                self.assertEqual(canonicalize_luma_host(url), url)
                self.assertEqual(absolutize_url(url, "https://src.example/list"), url)

    def test_relative_and_protocol_relative_luma_links_are_canonicalized(self):
        self.assertEqual(
            absolutize_url("/09nr86jb", "https://lu.ma/calendar/cal-NTMiDyT9ElAgpn"),
            "https://luma.com/09nr86jb")
        self.assertEqual(absolutize_url("//lu.ma/09nr86jb", "https://src.example/x"),
                         "https://luma.com/09nr86jb")

    def test_bare_slug_still_resolves_to_the_canonical_host(self):
        self.assertEqual(absolutize_url("a7oxbpwy", "https://lu.ma/calendar/cal-X"),
                         "https://luma.com/a7oxbpwy")

    def test_empty_input_is_passed_through(self):
        for url in ("", None):
            self.assertEqual(canonicalize_luma_host(url), url)


if __name__ == "__main__":
    unittest.main()
