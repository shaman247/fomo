"""Tests for the FareHarbor plugin's MULTI-SITE scoping (added 2026-08-12).

Companion to `test_fareharbor_primary.py`, which pins down *which company* one site
resolves. These pin down *which site* a URL belongs to.

The hazard is structural. `SiteProfile.fetcher` is argless, so a fetcher cannot
ask which website is being crawled — it rediscovers its scope from `website_urls`.
One profile whose `host_re` matched several FareHarbor venues would therefore
publish whichever company it resolved first into ALL of them. The plugin answers
that with one profile per site, each carrying its own `host_re`, its own LIKE
patterns, and its own pinned company bound into the fetcher.

So the invariants worth defending are:
  * a site's profile matches its own URLs and NOTHING else;
  * each profile's fetcher is a DISTINCT object, because that identity is exactly
    what `site_profiles.custom_fetch_profile` compares before short-circuiting the
    browser crawl;
  * the LIKE patterns partition the URL space the same way the host regexes do —
    a mismatch between the two is how one company's catalogue reaches another's
    page without any host regex ever being wrong;
  * every company we checked and REJECTED as mixed-source stays UNMATCHED, so none
    of them can be switched on by a widened host regex without a test failing.

`sail-nyc.com` used to be in that forbidden set. It was enabled deliberately on
2026-08-13 (w5161 Classic Harbor Line), so it now lives in `SITE_URLS` instead —
if a future change makes it foreign again, move the URL back rather than deleting
the coverage.
"""

import fnmatch
import os
import sys
import unittest
from unittest import mock

# Add parent directory to path for imports (db.py etc. use bare imports).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sources'))

import fareharbor
import site_profiles


# The live `website_urls` rows each site owns, as of 2026-08-12. Kept literal so a
# change to a host regex or a LIKE pattern has to face the real URLs it must serve.
SITE_URLS = {
    "fareharbor": [
        "https://untappednewyorktours.com/home-calendar/",
    ],
    "fareharbor_boweryboyswalks": [
        "https://www.boweryboyswalks.com/upcoming-tours/",
    ],
    "fareharbor_turnstiletours": [
        "https://fareharbor.com/embeds/book/turnstiletours/items/?flow=42986",
        "https://fareharbor.com/embeds/book/turnstiletours/items/?flow=42958",
    ],
    "fareharbor_bkwinery": [
        "https://fareharbor.com/embeds/book/bkwinery/",
    ],
    "fareharbor_sail_nyc": [
        "https://sail-nyc.com/public-cruises/",
    ],
}

# URLs that must NEVER resolve to a FareHarbor profile: other FareHarbor companies
# we deliberately did not enable, and ordinary sites that merely embed FareHarbor.
FOREIGN_URLS = [
    # Companies checked on 2026-08-12 and rejected as mixed-source pages.
    "https://thealdrich.org/events",
    "https://barrowsintense.com/events/",
    "https://tastebudskitchen.com/nyc/",
    "https://thomascole.org/events/",
    "https://bannermancastle.org/tours-events/",
    "https://calendar.aiany.org/",
    # A FareHarbor embed for a company with no profile at all.
    "https://fareharbor.com/embeds/book/historicrichmondtown/",
]


def _profiles_by_name():
    return {p.name: p for p in fareharbor.PROFILES}


def _like_matches(pattern, value):
    """Approximate MySQL `LIKE` for the `%`-only patterns this plugin uses."""
    assert "_" not in pattern.replace("_", "_"), pattern  # no single-char wildcards
    return fnmatch.fnmatchcase(value, pattern.replace("%", "*"))


class ProfileExportTests(unittest.TestCase):
    """The registry surface: one CUSTOM profile per configured site."""

    def test_one_profile_per_site(self):
        self.assertEqual(len(fareharbor.PROFILES), len(fareharbor.SITES))
        self.assertEqual([p.name for p in fareharbor.PROFILES],
                         [s.name for s in fareharbor.SITES])

    def test_every_profile_is_a_custom_fetch(self):
        for p in fareharbor.PROFILES:
            with self.subTest(p.name):
                self.assertIs(p.crawl_mode, site_profiles.CrawlMode.CUSTOM)
                self.assertTrue(callable(p.fetcher))
                self.assertTrue(p.extraction_notes)

    def test_fetchers_are_distinct_objects(self):
        """`custom_fetch_profile` compares fetcher IDENTITY, not profile equality.

        If two profiles shared one fetcher object, a website whose URLs straddled
        both sites would still short-circuit to a browser-crawl bypass and publish
        one company's catalogue under the other's name.
        """
        fetchers = [p.fetcher for p in fareharbor.PROFILES]
        self.assertEqual(len({id(f) for f in fetchers}), len(fetchers))

    def test_back_compat_single_profile_export(self):
        self.assertIs(fareharbor.PROFILE, fareharbor.PROFILES[0])
        self.assertEqual(fareharbor.PROFILE.name, "fareharbor")

    def test_site_names_and_companies_are_unique(self):
        self.assertEqual(len({s.name for s in fareharbor.SITES}), len(fareharbor.SITES))
        self.assertEqual(len({s.company for s in fareharbor.SITES}), len(fareharbor.SITES))


class HostMatchingTests(unittest.TestCase):
    """Each profile owns its own URLs and nothing else."""

    def test_each_site_matches_its_own_urls(self):
        profiles = _profiles_by_name()
        for name, urls in SITE_URLS.items():
            for url in urls:
                with self.subTest(url=url):
                    self.assertTrue(profiles[name].matches(url))

    def test_no_site_matches_another_sites_urls(self):
        for p in fareharbor.PROFILES:
            for name, urls in SITE_URLS.items():
                if name == p.name:
                    continue
                for url in urls:
                    with self.subTest(profile=p.name, url=url):
                        self.assertFalse(p.matches(url))

    def test_foreign_urls_match_nothing(self):
        for url in FOREIGN_URLS:
            with self.subTest(url=url):
                self.assertIsNone(
                    next((p for p in fareharbor.PROFILES if p.matches(url)), None))

    def test_lightframe_sites_are_scoped_by_path_not_host(self):
        """A bare `fareharbor.com` host_re would swallow every other company."""
        for site in fareharbor.SITES:
            if site.host_re is fareharbor.FAREHARBOR_HOST_RE:
                with self.subTest(site.name):
                    self.assertTrue(site.path_substr)
                    self.assertIn(site.company, site.path_substr)


class CustomFetchResolutionTests(unittest.TestCase):
    """What `crawler.py` actually asks: does this whole website bypass the browser?"""

    def test_each_websites_full_url_set_resolves_to_one_fetcher(self):
        for name, urls in SITE_URLS.items():
            with self.subTest(name):
                profile = site_profiles.custom_fetch_profile(urls)
                self.assertIsNotNone(profile)
                self.assertEqual(profile.name, name)

    def test_a_stray_non_fareharbor_url_falls_back_to_a_browser_crawl(self):
        """Fail-safe, deliberately.

        Adding an ordinary page to one of these websites turns the plugin OFF for
        it rather than publishing a catalogue for a page nobody is reading.
        """
        urls = SITE_URLS["fareharbor_turnstiletours"] + ["https://turnstiletours.com/tours/"]
        self.assertIsNone(site_profiles.custom_fetch_profile(urls))

    def test_urls_from_two_fareharbor_sites_do_not_short_circuit(self):
        urls = (SITE_URLS["fareharbor_bkwinery"]
                + SITE_URLS["fareharbor_turnstiletours"])
        self.assertIsNone(site_profiles.custom_fetch_profile(urls))


class UrlLikePatternTests(unittest.TestCase):
    """The LIKE patterns must partition URLs exactly as the host regexes do.

    These are the plugin's OTHER matcher: `host_re` decides which website bypasses
    the browser, `url_like` decides which URLs that website's fetcher then reads.
    If they disagree, a site crawls a listing page that belongs to someone else.
    """

    def test_patterns_select_the_sites_own_urls(self):
        for site in fareharbor.SITES:
            for url in SITE_URLS[site.name]:
                with self.subTest(site=site.name, url=url):
                    self.assertTrue(
                        any(_like_matches(p, url) for p in site.url_like))

    def test_patterns_reject_every_other_sites_urls(self):
        for site in fareharbor.SITES:
            for other, urls in SITE_URLS.items():
                if other == site.name:
                    continue
                for url in urls:
                    with self.subTest(site=site.name, url=url):
                        self.assertFalse(
                            any(_like_matches(p, url) for p in site.url_like))

    def test_patterns_reject_foreign_urls(self):
        for site in fareharbor.SITES:
            for url in FOREIGN_URLS:
                with self.subTest(site=site.name, url=url):
                    self.assertFalse(
                        any(_like_matches(p, url) for p in site.url_like))

    def test_listing_urls_query_binds_one_placeholder_per_pattern(self):
        """String-built WHERE clause — the count must track the bound params."""
        captured = {}

        class _Cur:
            def execute(self, sql, params=None):
                captured["sql"], captured["params"] = sql, params

            def fetchall(self):
                return [{"url": "https://example.com/"}]

        class _Conn:
            def cursor(self, dictionary=False):
                return _Cur()

            def close(self):
                pass

        site = fareharbor.TURNSTILE
        with mock.patch.dict(sys.modules, {"db": mock.Mock(create_connection=lambda: _Conn())}):
            out = fareharbor._listing_urls_from_db(site.url_like)

        self.assertEqual(out, ["https://example.com/"])
        self.assertEqual(list(captured["params"]), list(site.url_like))
        self.assertEqual(captured["sql"].count("%s"), len(site.url_like))

    def test_listing_urls_defaults_to_the_untapped_site(self):
        """The historical argless call must keep its old scope."""
        captured = {}

        class _Cur:
            def execute(self, sql, params=None):
                captured["params"] = params

            def fetchall(self):
                return []

        class _Conn:
            def cursor(self, dictionary=False):
                return _Cur()

            def close(self):
                pass

        with mock.patch.dict(sys.modules, {"db": mock.Mock(create_connection=lambda: _Conn())}):
            fareharbor._listing_urls_from_db()

        self.assertEqual(list(captured["params"]), list(fareharbor.UNTAPPED.url_like))


class PerSitePrimaryPinTests(unittest.TestCase):
    """The pin travels with the site, not with the module."""

    def _page(self, *links):
        return " ".join(
            f'<a href="https://fareharbor.com/embeds/book/{c}/items/{pk}/">book</a>'
            for c, pk in links)

    def _resolve(self, site, page_text, urls=("https://example.com/tours",)):
        with mock.patch.object(fareharbor, "_http_get", return_value=page_text):
            return fareharbor._resolve_companies(
                list(urls), site.company, site.extra_partner_items)

    def test_each_site_pins_its_own_company(self):
        for site in fareharbor.SITES:
            with self.subTest(site.name):
                primary, _, _ = self._resolve(site, "<html>no embeds</html>")
                self.assertEqual(primary, site.company)

    def test_a_partner_outlinking_the_venue_cannot_steal_primary(self):
        """The 2026-07-29 failure, replayed against a newly added site."""
        links = [("sail-nyc", 25950 + i) for i in range(11)]
        links += [("boweryboyswalks", 310611 + i) for i in range(2)]
        primary, primary_pks, partners = self._resolve(
            fareharbor.BOWERY_BOYS, self._page(*links))

        self.assertEqual(primary, "boweryboyswalks")
        self.assertEqual(len(primary_pks), 2)
        self.assertEqual(len(partners["sail-nyc"]), 11)

    def test_untapped_extra_partner_pins_do_not_leak_to_other_sites(self):
        """`EXTRA_PARTNER_ITEMS` is Untapped's editorial decision, not a global one."""
        page = self._page(("boweryboyswalks", 310611))
        _, _, partners = self._resolve(fareharbor.BOWERY_BOYS, page)
        self.assertEqual(partners, {})

        _, _, untapped_partners = self._resolve(
            fareharbor.UNTAPPED, self._page(("untappednewyork", 284615)))
        self.assertIn("sail-nyc", untapped_partners)

    def test_lightframe_url_answers_directly_without_a_fetch(self):
        """An /embeds/book/ URL in the DB is the operator stating the answer."""
        with mock.patch.object(fareharbor, "_http_get",
                               side_effect=AssertionError("must not fetch")):
            primary, _, partners = fareharbor._resolve_companies(
                list(SITE_URLS["fareharbor_bkwinery"]),
                fareharbor.BROOKLYN_WINERY.company,
                fareharbor.BROOKLYN_WINERY.extra_partner_items)

        self.assertEqual(primary, "bkwinery")
        self.assertEqual(partners, {})


class HeadlineIsNotAlwaysAPriceTests(unittest.TestCase):
    """`headline` means different things per operator — emit it only when priced.

    Untapped puts the price there ("$42"); Bowery Boys puts a duration blurb and
    Turnstile a recurring schedule ("Walking • Saturdays, 2pm"). Labelling those
    "**Price**" is wrong, and dropping a "Saturdays, 2pm" sentence next to an
    enumerated departure list is what stops the extractor inventing a weekly span.
    """

    def _card(self, headline):
        item = {"pk": 1, "name": "Some Tour", "headline": headline,
                "description": "", "start_location": {}}
        return "\n".join(fareharbor.build_card(
            "someco", item, {"2026-08-20": {("14:00", "16:00")}}))

    def test_currency_headline_is_emitted_as_a_price(self):
        self.assertIn("**Price**: $42", self._card("$42"))
        self.assertIn("**Price**: $96. Includes ferry tickets",
                      self._card("$96. Includes ferry tickets"))

    def test_tagline_headline_is_dropped_entirely(self):
        for headline in ("2 hours • Ages 16+",
                         "Walking • Saturdays, 2pm",
                         "Every Thursday at Brooklyn Winery!",
                         "Learn About Winemaking in the Heart of Brooklyn"):
            with self.subTest(headline):
                card = self._card(headline)
                self.assertNotIn("**Price**", card)
                self.assertNotIn(headline, card)

    def test_the_departure_line_survives_either_way(self):
        for headline in ("$42", "Walking • Saturdays, 2pm"):
            with self.subTest(headline):
                self.assertIn("2026-08-20 at 2:00 PM–4:00 PM", self._card(headline))


class StorefrontProductFilterTests(unittest.TestCase):
    """Catalogue rows every operator keeps alongside real events."""

    def test_non_event_products_are_skipped(self):
        for name in ("Gift Card", "Gift Certificates", "Staff Memberships & Donations",
                     "Memberships", "Gratuity", "Secrets of Grand Central - Private Tour",
                     "Public Tour Template", "Jordan's Library Test"):
            with self.subTest(name):
                self.assertFalse(fareharbor.is_public_item({"name": name}))

    def test_real_tours_survive_the_filter(self):
        for name in ("Brooklyn Army Terminal Tour",
                     "Gilded Age Mansions of Fifth Avenue",
                     "Wine & Grazing",
                     "Smarter Than a Somm Blind Tasting Game",
                     "Food Cart Tour: Midtown",
                     # The filter matches WORDS, not substrings — these are events.
                     "Privateers of the Hudson",
                     "Testament: A Staged Reading"):
            with self.subTest(name):
                self.assertTrue(fareharbor.is_public_item({"name": name}))


class StorefrontProductTests(unittest.TestCase):
    """Classic Harbor Line's 90-item catalogue mixes two storefront products in with
    the sails. Added 2026-08-13 with w5161."""

    def test_storefront_products_are_not_events(self):
        for name in ("Seasoned Sailor Pass", "Passes", "Available Onboard at the Bar"):
            with self.subTest(name):
                self.assertFalse(fareharbor.is_public_item({"name": name}))

    def test_pass_alternation_matches_the_bare_word(self):
        """Regression on a live slip: the pattern was first written `passes?`, which
        is `passe` + optional `s` and therefore does NOT match "Pass". The catalogue
        item is "Seasoned Sailor Pass", so the filter silently did nothing."""
        self.assertTrue(fareharbor.SKIP_NAME_RE.search("Seasoned Sailor Pass"))

    def test_the_filter_still_matches_whole_words_only(self):
        for name in ("Palisades Fall Foliage Cruise",   # 'Pal...', not 'pass'
                     "Passport to Brooklyn",            # 'Passport' is not 'pass'
                     "Compass Rose Navigation Talk"):   # 'Compass' contains 'pass'
            with self.subTest(name):
                self.assertTrue(fareharbor.is_public_item({"name": name}))


class PartnerBrandedItemTests(unittest.TestCase):
    """An operator that FULFILS other organizers' tours carries them in its own
    catalogue. Whoever owns the brand publishes them; the boat is the venue, not the
    organizer. Without this, each tour is listed once per brand — and the borrower
    usually RENAMES it, so the merger's same-name dedup never collapses the pair."""

    def _dropped(self, site, items):
        borrowed = {pk for other in fareharbor.SITES if other is not site
                    for pk in (other.extra_partner_items or {}).get(site.company, ())}
        return {pk for pk, it in items.items()
                if pk in borrowed
                or (site.skip_name_re and site.skip_name_re.search(it.get("name") or ""))}

    def test_classic_harbor_leaves_aiany_and_untapped_tours_alone(self):
        items = {1: {"name": "AIANY Around Manhattan Architecture Tour"},
                 2: {"name": "Untapped NY Harbor Tour: Secrets of the Harbor"},
                 3: {"name": "Sunset Sail aboard the Schooner Adirondack"}}
        self.assertEqual(self._dropped(fareharbor.CLASSIC_HARBOR, items), {1, 2})

    def test_an_item_another_site_pins_is_dropped_even_when_renamed(self):
        """The load-bearing case: Untapped pins sail-nyc item 749785 but sells it as
        "Untapped NY Harbor Tour: The Unframed City", while sail-nyc's own catalogue
        name is "The Unframed City: NYC Waterfront Art Tour" — which matches neither
        `skip_name_re` nor Untapped's title. Only the pk link catches it."""
        pinned = fareharbor.UNTAPPED.extra_partner_items.get("sail-nyc") or set()
        self.assertTrue(pinned, "Untapped no longer pins a sail-nyc item")
        pk = next(iter(pinned))
        items = {pk: {"name": "The Unframed City: NYC Waterfront Art Tour"}}
        self.assertIsNone(fareharbor.CLASSIC_HARBOR.skip_name_re.search(
            "The Unframed City: NYC Waterfront Art Tour"),
            "name filter would mask the pk-link this test is for")
        self.assertEqual(self._dropped(fareharbor.CLASSIC_HARBOR, items), {pk})

    def test_the_exclusion_is_scoped_to_the_lending_company(self):
        """Untapped's pin is on `sail-nyc` items, so it must not suppress a
        same-numbered item in some other company's catalogue."""
        pk = next(iter(fareharbor.UNTAPPED.extra_partner_items["sail-nyc"]))
        items = {pk: {"name": "Brooklyn Army Terminal Tour"}}
        self.assertEqual(self._dropped(fareharbor.TURNSTILE, items), set())

    def test_other_sites_carry_no_name_exclusion(self):
        for site in fareharbor.SITES:
            if site is not fareharbor.CLASSIC_HARBOR:
                with self.subTest(site.name):
                    self.assertIsNone(site.skip_name_re)


if __name__ == "__main__":
    unittest.main()
