"""Tests for the FareHarbor plugin's PRIMARY-company resolution.

The primary company decides whose WHOLE catalogue gets emitted, while a partner
contributes only the item pks the listing page links. So picking the wrong primary
does not cause a small error — it swaps one business's catalogue for another's.

That is exactly what happened on 2026-07-29: the old `pick_company()` heuristic
handed the primary slot to the most-linked company, a cross-promoted partner
(`sail-nyc`) out-linked the venue's own company 11 to 6, and w4998 ingested Classic
Harbor Line's booze-cruise catalogue while 29 genuine Untapped tours archived out.

These tests pin that behaviour down. They are pure-function tests over
`_resolve_companies` — no network, no DB — driven by fake page text.
"""

import os
import sys
import unittest
from unittest import mock

# Add parent directory to path for imports (db.py etc. use bare imports).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sources'))

import fareharbor


def _page(*links):
    """Minimal page text carrying FareHarbor embed links."""
    return " ".join(
        f'<a href="https://fareharbor.com/embeds/book/{company}/items/{pk}/">book</a>'
        for company, pk in links
    )


class ResolveCompaniesTests(unittest.TestCase):
    """`_resolve_companies` must not let link volume choose the primary."""

    def _resolve(self, page_text, urls=("https://untappednewyorktours.com/home-calendar/",),
                 extras=None):
        """Resolve against fake page text.

        `extras` defaults to EMPTY so the production `EXTRA_PARTNER_ITEMS` pins
        don't leak into tests that aren't about them (and so retiring a pinned
        tour never breaks an unrelated test).
        """
        with mock.patch.object(fareharbor, "_http_get", return_value=page_text), \
             mock.patch.object(fareharbor, "EXTRA_PARTNER_ITEMS",
                               {} if extras is None else extras):
            return fareharbor._resolve_companies(list(urls))

    def test_partner_outlinking_the_venue_does_not_steal_primary(self):
        """The 2026-07-29 regression, verbatim: partner 11 links vs venue 6."""
        links = [("sail-nyc", 25950 + i) for i in range(11)]
        links += [("untappednewyork", 284615 + i) for i in range(6)]
        primary, primary_pks, partners = self._resolve(_page(*links))

        self.assertEqual(primary, "untappednewyork")
        self.assertIn("sail-nyc", partners)
        # The partner contributes only its LINKED pks, never a whole catalogue.
        self.assertEqual(len(partners["sail-nyc"]), 11)
        self.assertEqual(len(primary_pks), 6)

    def test_primary_wins_even_when_not_linked_at_all(self):
        """A page that stops linking the venue must not promote a partner."""
        primary, primary_pks, partners = self._resolve(
            _page(("sail-nyc", 25950), ("sail-nyc", 25953)))

        self.assertEqual(primary, "untappednewyork")
        self.assertEqual(primary_pks, set())
        self.assertEqual(partners["sail-nyc"], {25950, 25953})

    def test_extra_partner_items_are_emitted_without_a_page_link(self):
        """Venue-branded products hosted on a partner's account survive."""
        primary, _, partners = self._resolve(
            _page(("untappednewyork", 284615)), extras={"sail-nyc": {749785}})

        self.assertEqual(primary, "untappednewyork")
        self.assertIn(749785, partners.get("sail-nyc", set()))

    def test_extras_never_override_the_primary_company(self):
        """An extras entry for the primary itself must not create a self-partner."""
        primary, _, partners = self._resolve(
            _page(("untappednewyork", 284615)),
            extras={"untappednewyork": {999999}})

        self.assertEqual(primary, "untappednewyork")
        self.assertNotIn("untappednewyork", partners)

    def test_falls_back_to_most_linked_when_pin_is_cleared(self):
        """Unsetting the pin restores the old heuristic (the documented escape hatch)."""
        links = [("sail-nyc", 25950 + i) for i in range(11)]
        links += [("untappednewyork", 284615 + i) for i in range(6)]
        with mock.patch.object(fareharbor, "PRIMARY_COMPANY", None):
            primary, _, _ = self._resolve(_page(*links))

        self.assertEqual(primary, "sail-nyc")

    # ---- Resilience: a broken listing page must not retire the catalogue ----
    #
    # These two cases changed behaviour when the pin landed, deliberately. The
    # primary's catalogue comes from the FareHarbor API, not the page; the page
    # only decides PARTNER items. So a page that fails to fetch, or renders
    # without embeds, previously resolved to "no company" and emitted ZERO tours
    # — mass-archiving ~27 live tours over a transient outage. With the pin, the
    # primary still resolves and its catalogue still publishes; only partners are
    # lost, and a warning is logged.

    def test_page_without_embeds_still_resolves_the_pinned_primary(self):
        primary, primary_pks, partners = self._resolve("<html>no bookings here</html>")

        self.assertEqual(primary, "untappednewyork")
        self.assertEqual(primary_pks, set())
        self.assertEqual(partners, {})

    def test_fetch_failure_still_resolves_the_pinned_primary(self):
        with mock.patch.object(fareharbor, "_http_get", side_effect=OSError("boom")), \
             mock.patch.object(fareharbor, "EXTRA_PARTNER_ITEMS", {}):
            primary, primary_pks, partners = fareharbor._resolve_companies(
                ["https://untappednewyorktours.com/home-calendar/"])

        self.assertEqual(primary, "untappednewyork")
        self.assertEqual(partners, {})

    def test_unpinned_page_without_embeds_yields_nothing(self):
        """Without the pin, 'no embed' still means 'nothing to crawl'."""
        with mock.patch.object(fareharbor, "PRIMARY_COMPANY", None):
            primary, primary_pks, partners = self._resolve("<html>nothing</html>")

        self.assertIsNone(primary)
        self.assertEqual(primary_pks, set())
        self.assertEqual(partners, {})


class PickCompanyTests(unittest.TestCase):
    """`pick_company` itself is unchanged — it is just no longer load-bearing."""

    def test_most_linked_wins(self):
        self.assertEqual(fareharbor.pick_company({"a": 3, "b": 9}), "b")

    def test_ties_break_alphabetically_for_determinism(self):
        self.assertEqual(fareharbor.pick_company({"zebra": 5, "alpha": 5}), "alpha")

    def test_empty_tally(self):
        self.assertIsNone(fareharbor.pick_company({}))


if __name__ == "__main__":
    unittest.main()
