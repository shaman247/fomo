"""Tests for `site_profiles.resolve_notes` URL scoping (added 2026-08-26).

A source plugin is selected at CRAWL time from `website_urls.url`. Its
`extraction_notes` — the prompt guidance that plugin wants attached to every
extraction of its content — were resolved from `websites.base_url` instead.

For any profile carrying a `path_substr` those two disagree, because base_url is
normally the bare site root. The result was silent and total: on 2026-08-26 all
117 meetup sites (`path_substr="/events/"`) and all 76 eventbrite `/o/` sites had
a base_url without that segment, so notes such as "use the EVENT DETAIL URL as
the event URL" never reached the model. 227 websites across 9 profiles were
affected, and nothing anywhere reported a problem — the extraction simply ran
without the guidance its plugin author wrote for it.

That is what these tests defend: notes must follow the URL the plugin actually
matched, not the site root.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sources'))

import site_profiles


# The real shape of the rows involved: a bare-root base_url next to the crawl URL
# that actually carries the path segment the profile is scoped to.
MEETUP_BASE = "https://www.meetup.com/amcnynj/"
MEETUP_CRAWL = "https://www.meetup.com/amcnynj/events/"


class TestResolveNotesUrlScoping(unittest.TestCase):

    def test_base_url_alone_misses_a_path_scoped_profile(self):
        """The precondition for the bug — kept so the fix can't be misread.

        base_url does not match the meetup profile at all. If this ever starts
        matching, the scoping problem has moved rather than been fixed.
        """
        self.assertIsNone(site_profiles.resolve_profile(MEETUP_BASE))
        self.assertIsNotNone(site_profiles.resolve_profile(MEETUP_CRAWL))

    def test_crawl_url_in_candidates_restores_the_notes(self):
        notes = site_profiles.resolve_notes([MEETUP_BASE, MEETUP_CRAWL], "")
        self.assertIn("EVENT DETAIL URL", notes)

    def test_site_notes_are_preserved_and_come_after(self):
        notes = site_profiles.resolve_notes([MEETUP_BASE, MEETUP_CRAWL],
                                            "site-specific note")
        self.assertIn("EVENT DETAIL URL", notes)
        self.assertIn("site-specific note", notes)
        self.assertLess(notes.index("EVENT DETAIL URL"),
                        notes.index("site-specific note"))

    def test_accepts_a_bare_string(self):
        """Backward compatibility — the old single-URL call must still work."""
        self.assertIn("EVENT DETAIL URL",
                      site_profiles.resolve_notes(MEETUP_CRAWL, ""))

    def test_none_and_unmatched_urls_pass_notes_through_untouched(self):
        self.assertEqual("abc", site_profiles.resolve_notes(None, "abc"))
        self.assertEqual("abc", site_profiles.resolve_notes(
            ["https://example.org/whatever"], "abc"))
        self.assertEqual("", site_profiles.resolve_notes([], None))

    def test_first_matching_url_wins(self):
        """Order is significant: crawl URLs are passed before base_url."""
        notes = site_profiles.resolve_notes(
            ["https://example.org/nothing", MEETUP_CRAWL], "")
        self.assertIn("EVENT DETAIL URL", notes)


class TestMeetupMarkerIsUnambiguous(unittest.TestCase):
    """The marker must OPEN its card block, not float between two of them.

    Meetup renders each event as one <a> card whose body runs to thousands of
    characters. A marker emitted with no delimiter sits directly below the
    previous card's text, and on 2026-08-26 the extractor read 2 of 16 markers
    on w4959 as the *preceding* card's trailing link — shipping event URLs that
    pointed at a different event than the one shown.
    """

    def _js(self):
        import meetup
        return meetup._MEETUP_JS

    def test_a_rule_is_inserted_before_the_marker(self):
        js = self._js()
        self.assertIn("createElement('hr')", js)
        self.assertLess(js.index("createElement('hr')"),
                        js.index("EVENT DETAIL URL"),
                        "the rule must be inserted before the marker text")

    def test_href_is_removed_not_pointed_at_a_fragment(self):
        """'#' resolves against the page URL, re-emitting the listing link."""
        js = self._js()
        self.assertIn("removeAttribute('href')", js)
        self.assertNotIn("setAttribute('href', '#')", js)

    def test_profile_tells_the_model_which_card_the_url_belongs_to(self):
        import meetup
        notes = meetup.PROFILE.extraction_notes
        self.assertIsNotNone(notes)
        self.assertIn("BELOW", notes)


if __name__ == '__main__':
    unittest.main()
