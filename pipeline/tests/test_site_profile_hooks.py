"""The platform-wide SiteProfile hooks, exercised with a fake plugin.

`canonicalize_url`, `absolutize_relative`, `is_listing_url` and
`check_crawl_payload` let a gitignored platform plugin own its URL/payload
quirks (alias hosts, site-global slugs, listing endpoints, capped feeds)
while the engine stays platform-free. These tests pin the plumbing — what the
engine does with a hook that answers, and with no hook at all — using a fake
profile, so they hold on a fresh clone with an empty plugin directory.
"""

import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import merger
import site_profiles
from processor import absolutize_url
from site_profiles import SiteProfile


def _canon(url):
    return url.replace('://alias.test/', '://canon.test/') if url else url


def _abs_rel(rel, source_url):
    if 'canon.test' in (source_url or '') and rel.startswith('slug-'):
        return f'https://canon.test/{rel}'
    return None


def _is_listing(url, source_url):
    return url == source_url == 'https://canon.test/feed'


FAKE = SiteProfile(
    name='fake',
    host_re=re.compile(r'^(alias|canon)\.test$'),
    canonicalize_url=_canon,
    absolutize_relative=_abs_rel,
    is_listing_url=_is_listing,
    check_crawl_payload=lambda content, name: 'CAPPED' in (content or ''),
)


class TestHooksWithAPlugin(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(site_profiles, 'PROFILES', [FAKE])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_absolute_urls_are_canonicalized_at_ingest(self):
        self.assertEqual(absolutize_url('https://alias.test/e/1', 'https://src.example/'),
                         'https://canon.test/e/1')
        self.assertEqual(absolutize_url('//alias.test/e/1', 'https://src.example/'),
                         'https://canon.test/e/1')
        self.assertEqual(absolutize_url('http://https://alias.test/e/1', 'https://src.example/'),
                         'https://canon.test/e/1')

    def test_resolved_relative_urls_are_canonicalized(self):
        self.assertEqual(absolutize_url('/e/1', 'https://alias.test/list'),
                         'https://canon.test/e/1')

    def test_plugin_resolves_its_own_relative_refs_first(self):
        self.assertEqual(absolutize_url('slug-abc', 'https://canon.test/cal/x'),
                         'https://canon.test/slug-abc')
        # Not the plugin's shape: ordinary urljoin.
        self.assertEqual(absolutize_url('other', 'https://canon.test/cal/x'),
                         'https://canon.test/cal/other')

    def test_merger_identity_folds_the_alias_host(self):
        self.assertEqual(merger.normalize_url_for_identity('https://alias.test/e/1/'),
                         merger.normalize_url_for_identity('https://canon.test/e/1'))

    def test_listing_url_and_payload_hooks_aggregate(self):
        self.assertTrue(site_profiles.is_listing_url('https://canon.test/feed',
                                                     'https://canon.test/feed'))
        self.assertFalse(site_profiles.is_listing_url('https://canon.test/e/1',
                                                      'https://canon.test/feed'))
        self.assertTrue(site_profiles.check_crawl_payload('{"CAPPED": 1}', 'site'))
        self.assertFalse(site_profiles.check_crawl_payload('{"ok": 1}', 'site'))


class TestHooksWithNoPlugins(unittest.TestCase):
    """A fresh clone has an empty registry: every hook is a no-op."""

    def setUp(self):
        patcher = mock.patch.object(site_profiles, 'PROFILES', [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_urls_pass_through_untouched(self):
        self.assertEqual(site_profiles.canonicalize_url('https://alias.test/e/1'),
                         'https://alias.test/e/1')
        self.assertEqual(absolutize_url('slug-abc', 'https://canon.test/cal/x'),
                         'https://canon.test/cal/slug-abc')
        self.assertIsNone(site_profiles.absolutize_relative('x', 'https://a.test/'))
        self.assertFalse(site_profiles.is_listing_url('https://a.test/f', 'https://a.test/f'))
        self.assertFalse(site_profiles.check_crawl_payload('CAPPED', 'site'))


if __name__ == '__main__':
    unittest.main()
