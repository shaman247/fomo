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

from processor import absolutize_url


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

    def test_whitespace_is_trimmed(self):
        self.assertEqual(absolutize_url("  /events/1  ", "https://src.example/list"),
                         "https://src.example/events/1")


if __name__ == "__main__":
    unittest.main()
