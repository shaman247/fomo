"""Tests for crawler.resolve_url_templates.

These placeholders let a `website_urls.url` express a ROLLING window instead of a
hardcoded date, which is what keeps a widened crawl window from silently going
stale. They had no coverage at all until 2026-08-11, when `{{month_num}}` /
`{{next_month_num}}` were added for month-view calendar URLs and Queens Public
Library was resharded onto `{{mdy+N}}` date ranges (271 -> 1,096 crawl_events).

A silent failure here is expensive and invisible: an unresolved `{{...}}` goes to
the site verbatim, which usually 404s or returns an unfiltered page, and the crawl
still reports "processed".

Dates are computed relative to today rather than pinned, so these stay valid.
"""

import datetime as dt
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler import resolve_url_templates


def _next_month(today):
    return (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)


class TestMonthAndYearPlaceholders(unittest.TestCase):

    def setUp(self):
        self.today = dt.datetime.now()
        self.nxt = _next_month(self.today)

    def test_month_name_and_year(self):
        out = resolve_url_templates('https://x/{{month}}/{{year}}')
        self.assertEqual(out, f"https://x/{self.today.strftime('%B').lower()}/{self.today.year}")

    def test_month_num_is_zero_padded(self):
        out = resolve_url_templates('https://x/{{year}}/{{month_num}}')
        self.assertEqual(out, f"https://x/{self.today.year}/{self.today.strftime('%m')}")
        self.assertRegex(out, r'/\d{4}/\d{2}$')

    def test_next_month_num_and_year_roll_over_together(self):
        """A December crawl must ask for January of the NEXT year, not this one."""
        out = resolve_url_templates('https://x/{{next_month_year}}/{{next_month_num}}')
        self.assertEqual(out, f"https://x/{self.nxt.year}/{self.nxt.strftime('%m')}")

    def test_next_month_name(self):
        out = resolve_url_templates('https://x/{{next_month}}')
        self.assertEqual(out, f"https://x/{self.nxt.strftime('%B').lower()}")


class TestDatePlaceholders(unittest.TestCase):

    def test_iso_date_and_offset(self):
        today = dt.date.today()
        self.assertEqual(resolve_url_templates('https://x/{{date}}'),
                         f'https://x/{today.isoformat()}')
        self.assertEqual(resolve_url_templates('https://x/{{date+7}}'),
                         f'https://x/{(today + dt.timedelta(days=7)).isoformat()}')

    def test_mdy_offsets_used_by_the_qpl_date_shards(self):
        """QPL shards its calendar into `sm_pSsnDate:[ {{mdy+5}} TO {{mdy+90}} ]`."""
        today = dt.date.today()
        out = resolve_url_templates(
            'https://x/?f=sm_pSsnDate%3A%5B%20{{mdy+5}}%2A%20TO%20{{mdy+90}}%2A%20%5D')
        self.assertIn((today + dt.timedelta(days=5)).strftime('%m/%d/%y'), out)
        self.assertIn((today + dt.timedelta(days=90)).strftime('%m/%d/%y'), out)


class TestNoPlaceholderIsLeftBehind(unittest.TestCase):
    """The failure that matters: an unresolved token is sent to the site verbatim."""

    def test_every_documented_placeholder_resolves(self):
        url = ('https://x/{{month}}/{{month_num}}/{{year}}/{{next_month}}/'
               '{{next_month_num}}/{{next_month_year}}/{{date}}/{{date+3}}/'
               '{{mdy}}/{{mdy+10}}')
        out = resolve_url_templates(url)
        self.assertNotIn('{{', out, f'unresolved placeholder left in {out!r}')
        self.assertNotIn('}}', out)

    def test_urls_without_placeholders_are_untouched(self):
        for url in ('https://x/calendar',
                    'https://x/calendar?page=2&q=a%20b'):
            with self.subTest(url=url):
                self.assertEqual(resolve_url_templates(url), url)

    def test_an_unknown_placeholder_is_left_alone_rather_than_mangled(self):
        """Better to fail visibly on the site than to substitute something wrong."""
        out = resolve_url_templates('https://x/{{not_a_real_placeholder}}')
        self.assertEqual(out, 'https://x/{{not_a_real_placeholder}}')


if __name__ == '__main__':
    unittest.main()
