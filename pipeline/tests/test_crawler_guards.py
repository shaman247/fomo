"""Tests for crawler.py interstitial guards.

Covers the detection that keeps bot-challenge pages and Cloudflare 5xx
error/landing pages from being stored as *successful* zero-event crawls
(which would feed the merger's archival logic and retire live events).
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crawler
from crawler import (
    BOT_CHALLENGE_MAX_CHARS,
    CLOUDFLARE_ERROR_CODES,
    MIN_CRAWL_CONTENT_SIZE,
    MIN_EVENT_PAGE_SIZE,
    SOFT_404_MAX_CHARS,
    _is_bot_challenge,
    _is_cloudflare_error_page,
    _is_json_api_payload,
    _is_soft_404,
)


# Verbatim shape of a JSON feed that legitimately has nothing to serve. The
# payload is 65 bytes; combined_markdown adds the ~84-byte URL line, landing at
# ~163 bytes — well under MIN_CRAWL_CONTENT_SIZE.
EMPTY_JSON_FEED_BODY = (
    "https://api.example.com/v2/partner/events?city=nyc&window=30&token=abc123\n"
    '{"data":{"events":[],"has_next_page":false},"success":true}\n'
)


# Verbatim body stored for website 88 (ShapeShifter Lab) on 2026-07-20 as a
# "successful" 953-byte, 0-event crawl. 953 bytes > MIN_CRAWL_CONTENT_SIZE.
CF_502_BODY = (
    "https://www.shapeshifterplus.org/index.html\n"
    "#  Bad gateway Error code 502\n"
    "Visit [cloudflare.com](https://www.cloudflare.com/5xx-error-landing?"
    "utm_source=errorcode_502&utm_campaign=www.shapeshifterplus.org) for more information. \n"
    "2026-07-20 12:04:27 UTC\nYou\n###  Browser \nWorking\n"
    "Newark\n###  [ Cloudflare ](https://www.cloudflare.com/5xx-error-landing"
    "?utm_source=errorcode_502) \nWorking\nwww.shapeshifterplus.org\n"
    "###  Host \nError\n## What happened?\n"
    "The web server reported a bad gateway error.\n"
    "## What can I do?\nPlease try again in a few minutes.\n"
    "Cloudflare Ray ID: **a1e1d4145c5426f1** - Your IP: Click to reveal - "
    "Performance & security by Cloudflare\n"
)

CF_JUST_A_MOMENT_BODY = (
    "https://example.org/events\n"
    "# Just a moment...\n"
    "Enable JavaScript and cookies to continue.\n"
    "Please enable cookies.\n"
    "Cloudflare Ray ID: 8f2c11aa9b3d0001\n"
    "Performance & security by Cloudflare\n"
)

# A genuine, small event listing. Above MIN_CRAWL_CONTENT_SIZE but well below
# BOT_CHALLENGE_MAX_CHARS, so only the marker logic can save it.
LEGIT_SMALL_PAGE = (
    "https://smallvenue.example/events\n"
    "# Upcoming Events\n"
    "## August 2026\n"
    "  * ### Tuesday Night Jazz Quartet\n"
    "    Tuesday, August 4, 2026 at 8:00 PM - $20 at the door\n"
    "  * ### Open Mic Night\n"
    "    Wednesday, August 5, 2026 at 7:30 PM - Free\n"
    "  * ### Brooklyn Songwriters in the Round\n"
    "    Friday, August 7, 2026 at 9:00 PM - $15 advance / $20 door\n"
    "  * ### Sunday Afternoon Chamber Series\n"
    "    Sunday, August 9, 2026 at 3:00 PM - $25 general admission\n"
    "Doors open one hour before showtime. All ages welcome.\n"
    "Our venue is protected by Cloudflare and accessible by subway.\n"
    "Tickets available at the box office or online. No refunds or exchanges.\n"
)


# --- Meetup soft 404 --------------------------------------------------------
#
# Verbatim shape of crawl_result 113103 (website 3713, 2026-08-13): the body a
# deleted/private Meetup group serves at HTTP 200. Stored as a *successful*
# 4,121-byte, 0-event crawl five times running. Trimmed here (the real body
# carries the full Meetup footer), but every line is copied from it, curly
# apostrophes included.
MEETUP_SOFT_404_BODY = (
    "https://www.meetup.com/FunCrowd/events/\n"
    "[Skip to content](https://www.meetup.com/funcrowd/events/#main)\n"
    "[](https://www.meetup.com/)\n"
    "Homepage\nEnglish\nLog inSign up\n"
    "![calendarOrange illustration](https://secure.meetupstatic.com/next/images/"
    "illustrations/calendar-orange.webp?w=384)\n"
    "### Group not found\n"
    "Sorry, the group you\u2019re looking for doesn\u2019t exist\n"
    ".\nThe people platform\nCreate your own Meetup group.\n"
    "[Get Started](https://www.meetup.com/start?origin=groups&eventOrigin=page-footer)\n"
    "Your account\n"
    "  * [Sign up](https://www.meetup.com/register/?returnUri=https%3A%2F%2Fwww.meetup.com%2Ffuncrowd%2Fevents%2F)\n"
    "  * [Log in](https://www.meetup.com/login/?returnUri=https%3A%2F%2Fwww.meetup.com%2Ffuncrowd%2Fevents%2F)\n"
    "  * [Help](https://help.meetup.com/hc)\n"
    "Discover\n"
    "  * [Groups](https://www.meetup.com/find/?source=GROUPS)\n"
    "  * [Events](https://www.meetup.com/find/?source=EVENTS)\n"
    "  * [Topics](https://www.meetup.com/topics/)\n"
    "\u00a9 2026 Bending Spoons US Inc.\n"
    "Made with by\n[Bending Spoons](https://www.bendingspoons.com)\n"
)

# The page that must NEVER be flagged: crawl_result 100749 (website 4884,
# 2026-07-12) — a live Meetup group that simply has nothing scheduled. Same
# chrome, same footer, same illustration; only the message differs. 199 stored
# Meetup bodies look like this.
MEETUP_EMPTY_GROUP_BODY = (
    "https://www.meetup.com/coney-island-volleyball/events/\n"
    "[Skip to content](https://www.meetup.com/coney-island-volleyball/events/#main)\n"
    "Homepage\nEnglish\nLog inSign up\n"
    "# [Coney Island Volleyball](https://www.meetup.com/coney-island-volleyball/)\n"
    "5.0\u2022[3 ratings](https://www.meetup.com/coney-island-volleyball/feedback-overview/)\n"
    "[Brooklyn, NY, USA](https://www.meetup.com/find/us--ny--brooklyn/)\n"
    "[48 members](https://www.meetup.com/coney-island-volleyball/members/)\n"
    "# Events\n0\n"
    "[List](https://www.meetup.com/coney-island-volleyball/events/)"
    "[Calendar](https://www.meetup.com/coney-island-volleyball/events/calendar/)\n"
    "Upcoming\n"
    "![calendarOrange illustration](https://secure.meetupstatic.com/next/images/"
    "illustrations/calendar-orange.webp?w=384)\n"
    "### Nothing planned yet\n"
    "No events at the moment. Keep an eye out for when new ones are announced!\n"
    "Remove ads\n## Similar events nearby\n"
    "[See all](https://www.meetup.com/find/?source=EVENTS&keywords=Sports+%26+Fitness)\n"
    "\u00a9 2026 Bending Spoons US Inc.\n"
    "Made with by\n[Bending Spoons](https://www.bendingspoons.com)\n"
)

# A live group with events, reduced to the parts that matter here.
MEETUP_LIVE_GROUP_BODY = (
    "https://www.meetup.com/astoriarunners/events/\n"
    "# [Astoria Runners](https://www.meetup.com/astoriarunners/)\n"
    "# Events\n3\nUpcoming\n"
    "[Wed, Sep 2, 2026, 7:00 PM EDT\nTrack Tuesday at Astoria Park\n"
    "Astoria Park \u00b7 Queens, NY\n12 attendees]"
    "(https://www.meetup.com/astoriarunners/events/315701055/)\n"
    "\u00a9 2026 Bending Spoons US Inc.\n"
)


class TestCloudflareErrorPageDetection(unittest.TestCase):
    """CF 5xx error pages must be treated like bot challenges."""

    def test_real_cf_502_body_is_detected(self):
        self.assertTrue(_is_bot_challenge(CF_502_BODY))

    def test_cf_502_body_slips_past_the_size_floor(self):
        # Regression anchor: the size floor alone cannot catch this.
        self.assertGreater(len(CF_502_BODY), MIN_CRAWL_CONTENT_SIZE)

    def test_all_cf_origin_error_codes_detected(self):
        for code in CLOUDFLARE_ERROR_CODES:
            body = (
                f"# Web server error Error code {code}\n"
                "Visit cloudflare.com for more information.\n"
                "Cloudflare Ray ID: 8f2c11aa9b3d0001\n"
            )
            with self.subTest(code=code):
                self.assertTrue(_is_bot_challenge(body))

    def test_error_code_with_colon_and_spacing_variants(self):
        for rendered in ("Error code: 522", "error code  521", "ERROR CODE 524"):
            body = f"# Origin unreachable {rendered}\nPerformance & security by Cloudflare\n"
            with self.subTest(rendered=rendered):
                self.assertTrue(_is_bot_challenge(body))

    def test_5xx_error_landing_link_alone_is_enough_fingerprint(self):
        body = (
            "# Gateway time-out Error code 524\n"
            "Visit https://host.example/5xx-error-landing?utm_source=errorcode_524\n"
        )
        self.assertTrue(_is_bot_challenge(body))

    def test_error_code_without_cloudflare_fingerprint_is_not_flagged(self):
        body = "# Our ticketing partner returned Error code 502. Try again later.\n"
        self.assertFalse(_is_bot_challenge(body))

    def test_cloudflare_mention_without_error_code_is_not_flagged(self):
        self.assertFalse(_is_cloudflare_error_page(LEGIT_SMALL_PAGE.lower()))

    def test_4xx_codes_are_not_in_the_cf_origin_family(self):
        body = "# Not found Error code 404\nPerformance & security by Cloudflare\n"
        self.assertFalse(_is_bot_challenge(body))


class TestBotChallengeDetection(unittest.TestCase):
    """The pre-existing challenge path must keep working."""

    def test_just_a_moment_challenge_is_detected(self):
        self.assertTrue(_is_bot_challenge(CF_JUST_A_MOMENT_BODY))

    def test_blocked_page_is_detected(self):
        self.assertTrue(_is_bot_challenge("Sorry, you have been blocked\nRay ID: abc\n"))


class TestLegitimateContentNotFlagged(unittest.TestCase):
    """Real pages — especially small ones — must never be flagged."""

    def test_small_real_event_page_is_not_flagged(self):
        self.assertFalse(_is_bot_challenge(LEGIT_SMALL_PAGE))

    def test_small_real_page_is_above_the_size_floor(self):
        self.assertGreater(len(LEGIT_SMALL_PAGE), MIN_CRAWL_CONTENT_SIZE)

    def test_empty_content_is_not_flagged(self):
        # Empty content is handled by the "No content retrieved" path, not here.
        self.assertFalse(_is_bot_challenge(""))
        self.assertFalse(_is_bot_challenge(None))

    def test_large_page_quoting_a_marker_is_not_flagged(self):
        body = CF_502_BODY + "x" * BOT_CHALLENGE_MAX_CHARS
        self.assertFalse(_is_bot_challenge(body))


class TestEmptyJsonApiResponse(unittest.TestCase):
    """A successful JSON feed with zero events must not be stored as failed.

    The size floor exists to catch pages that failed to render. A JSON API that
    correctly answers "no events right now" is short but not broken, so it gets
    a narrow carve-out from MIN_CRAWL_CONTENT_SIZE.
    """

    def test_empty_json_feed_is_recognised(self):
        self.assertTrue(_is_json_api_payload(EMPTY_JSON_FEED_BODY))

    def test_empty_json_feed_is_below_the_size_floor(self):
        # Regression anchor: without the carve-out this crawl fails on size.
        self.assertLess(len(EMPTY_JSON_FEED_BODY), MIN_CRAWL_CONTENT_SIZE)

    def test_populated_json_feed_is_recognised(self):
        body = (
            "https://api.example.com/events\n"
            '{"data":{"events":[{"id":1,"name":"Show"}]},"success":true}\n'
        )
        self.assertTrue(_is_json_api_payload(body))

    def test_bare_empty_array_feed_is_recognised(self):
        self.assertTrue(_is_json_api_payload("https://api.example.com/events\n[]\n"))

    def test_fenced_json_body_is_recognised(self):
        body = (
            "https://api.example.com/events\n"
            "```json\n"
            '{"events":[],"ok":true}\n'
            "```\n"
        )
        self.assertTrue(_is_json_api_payload(body))

    # --- the carve-out must not widen any existing hole ---

    def test_cloudflare_error_page_is_not_json(self):
        self.assertFalse(_is_json_api_payload(CF_502_BODY))

    def test_bot_challenge_page_is_not_json(self):
        self.assertFalse(_is_json_api_payload(CF_JUST_A_MOMENT_BODY))

    def test_challenge_wrapped_in_json_is_still_rejected(self):
        # Defence in depth: even if a challenge were served as JSON, the
        # challenge detector runs first and vetoes the carve-out.
        body = (
            "https://example.org/events\n"
            '{"message":"Just a moment... please enable cookies","ok":false}\n'
        )
        self.assertFalse(_is_json_api_payload(body))

    def test_url_only_body_is_not_json(self):
        # The classic failed JS-rendered crawl: nothing but the URL echoed back.
        self.assertFalse(_is_json_api_payload("https://example.org/events\n"))

    def test_truncated_json_is_not_accepted(self):
        body = 'https://api.example.com/events\n{"data":{"events":[{"id":1,'
        self.assertFalse(_is_json_api_payload(body))

    def test_bare_scalars_are_not_accepted(self):
        for payload in ("null", "0", '"error"', "true"):
            with self.subTest(payload=payload):
                self.assertFalse(
                    _is_json_api_payload(f"https://api.example.com/events\n{payload}\n"))

    def test_empty_object_is_not_accepted(self):
        self.assertFalse(_is_json_api_payload("https://api.example.com/events\n{}\n"))

    def test_html_error_stub_is_not_accepted(self):
        self.assertFalse(_is_json_api_payload(
            "https://example.org/events\n# 404 Not Found\nPage unavailable.\n"))

    def test_empty_and_none_are_not_accepted(self):
        self.assertFalse(_is_json_api_payload(""))
        self.assertFalse(_is_json_api_payload(None))


class _FakeMarkdown:
    def __init__(self, fit_markdown=None, raw_markdown=None):
        self.fit_markdown = fit_markdown
        self.raw_markdown = raw_markdown


class _FakeResult:
    def __init__(self, content, success=True, use_raw=False):
        self.success = success
        if content is None:
            self.markdown = None
        elif use_raw:
            self.markdown = _FakeMarkdown(fit_markdown=None, raw_markdown=content)
        else:
            self.markdown = _FakeMarkdown(fit_markdown=content)


class _FakeCrawler:
    """Stands in for an AsyncWebCrawler; serves queued bodies in order."""

    def __init__(self, *bodies, success=True, use_raw=False):
        self._bodies = list(bodies)
        self._success = success
        self._use_raw = use_raw
        self.calls = 0

    async def arun(self, url=None, config=None):
        self.calls += 1
        body = self._bodies.pop(0) if self._bodies else self._bodies_default()
        return _FakeResult(body, success=self._success, use_raw=self._use_raw)

    def _bodies_default(self):
        return None


# A challenge body served by a *detail* page. Well over MIN_EVENT_PAGE_SIZE (the
# detail path's only content gate before this guard existed), which is precisely
# how website 1087's five events burned both detail_crawl_attempts.
DETAIL_CHALLENGE_BODY = CF_JUST_A_MOMENT_BODY

# A real event detail page. Short — detail pages usually are — but real.
REAL_EVENT_PAGE = (
    "# Queer Climb Night\n"
    "Thursday, August 6, 2026 · 7:00 PM\n"
    "Central Rock Gym, 40 W 23rd St\n"
    "An inclusive climbing session for LGBTQ+ climbers of all levels. "
    "Rentals included with admission.\n"
)


class TestDetailCrawlChallengeGuard(unittest.TestCase):
    """crawl_event_url() must not store an interstitial as the event page.

    Step 5 increments detail_crawl_attempts once per candidate no matter what,
    and get_detail_crawl_candidates caps at < 2, so an unrecovered challenge
    permanently costs an event one of only two chances.
    """

    def _run(self, fake, **kwargs):
        return asyncio.run(
            crawler.crawl_event_url(fake, "https://example.org/e/1", object(), **kwargs)
        )

    def test_real_page_is_returned(self):
        fake = _FakeCrawler(REAL_EVENT_PAGE)
        self.assertEqual(self._run(fake), REAL_EVENT_PAGE)

    def test_real_page_falls_back_to_raw_markdown(self):
        fake = _FakeCrawler(REAL_EVENT_PAGE, use_raw=True)
        self.assertEqual(self._run(fake), REAL_EVENT_PAGE)

    def test_challenge_body_is_long_enough_to_have_slipped_through(self):
        # Regression anchor: the old `len(content) > 50` gate accepted this.
        self.assertGreater(len(DETAIL_CHALLENGE_BODY), MIN_EVENT_PAGE_SIZE)
        self.assertTrue(_is_bot_challenge(DETAIL_CHALLENGE_BODY))

    def test_challenge_triggers_refetch_and_returns_recovered_content(self):
        fake = _FakeCrawler(DETAIL_CHALLENGE_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=REAL_EVENT_PAGE),
        ) as refetch:
            self.assertEqual(self._run(fake), REAL_EVENT_PAGE)
        refetch.assert_awaited_once()

    def test_refetch_uses_the_bounded_detail_budget(self):
        fake = _FakeCrawler(DETAIL_CHALLENGE_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=None),
        ) as refetch:
            self._run(fake)
        kwargs = refetch.await_args.kwargs
        self.assertEqual(kwargs['attempts'], crawler.DETAIL_CHALLENGE_RETRIES)
        self.assertEqual(kwargs['backoff'], crawler.DETAIL_CHALLENGE_BACKOFF)
        self.assertEqual(kwargs['timeout'], crawler.DETAIL_CHALLENGE_TIMEOUT)

    def test_retry_budget_is_bounded(self):
        # No infinite retry loop: a finite number of re-fetches per attempt...
        self.assertGreaterEqual(crawler.DETAIL_CHALLENGE_RETRIES, 1)
        self.assertLessEqual(crawler.DETAIL_CHALLENGE_RETRIES, 3)
        # ...and the worst case must stay inside Step 5's 300s stall watchdog:
        # initial fetch + sum(backoff * n) + retries * per-retry timeout.
        n = crawler.DETAIL_CHALLENGE_RETRIES
        worst = (
            120
            + crawler.DETAIL_CHALLENGE_BACKOFF * (n * (n + 1) // 2)
            + n * crawler.DETAIL_CHALLENGE_TIMEOUT
        )
        self.assertLess(worst, 300)

    def test_unrecovered_challenge_returns_none(self):
        fake = _FakeCrawler(DETAIL_CHALLENGE_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=None),
        ):
            self.assertIsNone(self._run(fake))

    def test_cf_5xx_interstitial_is_also_guarded(self):
        fake = _FakeCrawler(CF_502_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=None),
        ) as refetch:
            self.assertIsNone(self._run(fake))
        refetch.assert_awaited_once()

    def test_recovered_but_still_tiny_content_is_rejected(self):
        fake = _FakeCrawler(DETAIL_CHALLENGE_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value="ok"),
        ):
            self.assertIsNone(self._run(fake))

    # --- genuine failures and real-but-small pages must behave as before ---

    def test_no_refetch_for_a_real_page(self):
        fake = _FakeCrawler(REAL_EVENT_PAGE)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=None),
        ) as refetch:
            self._run(fake)
        refetch.assert_not_awaited()

    def test_tiny_body_still_fails_without_a_refetch(self):
        fake = _FakeCrawler("https://example.org/e/1")
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=REAL_EVENT_PAGE),
        ) as refetch:
            self.assertIsNone(self._run(fake))
        refetch.assert_not_awaited()

    def test_unsuccessful_result_still_fails(self):
        fake = _FakeCrawler(REAL_EVENT_PAGE, success=False)
        self.assertIsNone(self._run(fake))

    def test_missing_markdown_still_fails(self):
        fake = _FakeCrawler(None)
        self.assertIsNone(self._run(fake))

    def test_crawl_exception_still_fails(self):
        class Boom:
            async def arun(self, url=None, config=None):
                raise RuntimeError("browser wedged")

        self.assertIsNone(self._run(Boom()))

    def test_crawl_timeout_still_fails(self):
        class Hang:
            async def arun(self, url=None, config=None):
                await asyncio.sleep(5)

        self.assertIsNone(self._run(Hang(), timeout=0.05))

    def test_long_page_is_truncated_to_12k(self):
        fake = _FakeCrawler("x" * 20000)
        self.assertEqual(len(self._run(fake)), 12000)

    def test_json_detail_payload_is_not_treated_as_a_challenge(self):
        # The tiny-JSON carve-out added for API feeds must keep working here:
        # a JSON detail response is real content, not an interstitial.
        body = '{"event":{"id":42,"name":"Prom!","start":"2026-08-14T20:00:00"}}'
        self.assertGreater(len(body), MIN_EVENT_PAGE_SIZE)
        self.assertTrue(_is_json_api_payload(body))
        fake = _FakeCrawler(body)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=None),
        ) as refetch:
            self.assertEqual(self._run(fake), body)
        refetch.assert_not_awaited()


class TestMeetupSoft404Detection(unittest.TestCase):
    """A deleted/private Meetup group answers 200 with a "Group not found" body.

    It clears MIN_CRAWL_CONTENT_SIZE and matches no BOT_CHALLENGE_MARKERS, so
    before this guard it was stored as a healthy 0-event crawl — forever, on six
    websites. Storing it as `failed` is what keeps the merger from archiving on
    a page that was never really read.
    """

    def test_real_soft_404_body_is_detected(self):
        self.assertTrue(_is_soft_404(MEETUP_SOFT_404_BODY))

    def test_soft_404_slips_past_every_preexisting_gate(self):
        # Regression anchors: this is exactly why it was invisible.
        self.assertGreater(len(MEETUP_SOFT_404_BODY), MIN_CRAWL_CONTENT_SIZE)
        self.assertFalse(_is_bot_challenge(MEETUP_SOFT_404_BODY))
        self.assertFalse(_is_json_api_payload(MEETUP_SOFT_404_BODY))

    def test_ascii_apostrophes_match_too(self):
        # Meetup serves U+2019; a platform using ' must hit the same marker.
        ascii_body = MEETUP_SOFT_404_BODY.replace("\u2019", "'")
        self.assertNotIn("\u2019", ascii_body)
        self.assertTrue(_is_soft_404(ascii_body))

    def test_case_is_ignored(self):
        self.assertTrue(_is_soft_404(MEETUP_SOFT_404_BODY.upper()))

    # --- the markers must not fire on anything real ---

    def test_live_group_with_events_is_not_flagged(self):
        self.assertFalse(_is_soft_404(MEETUP_LIVE_GROUP_BODY))

    def test_empty_but_live_group_is_not_flagged(self):
        """The whole point: "Nothing planned yet" is a *correct* 0-event crawl."""
        self.assertFalse(_is_soft_404(MEETUP_EMPTY_GROUP_BODY))
        self.assertGreater(len(MEETUP_EMPTY_GROUP_BODY), MIN_CRAWL_CONTENT_SIZE)

    def test_bare_group_not_found_substring_is_not_a_marker(self):
        """"Group not found" ships in Meetup's i18n bundle on every group page.

        Only the full sentence counts, so the guard cannot start firing on
        healthy listings if <script> stripping ever changes.
        """
        body = MEETUP_EMPTY_GROUP_BODY + "\ngroupEvents.groupNotFoundTitle: Group not found\n"
        self.assertFalse(_is_soft_404(body))

    def test_page_quoting_the_sentence_is_not_flagged_when_large(self):
        body = MEETUP_SOFT_404_BODY + "x" * SOFT_404_MAX_CHARS
        self.assertFalse(_is_soft_404(body))

    def test_size_ceiling_clears_the_real_body(self):
        # The observed bodies are 4.1-4.4 KB; the ceiling must sit above them.
        self.assertLess(len(MEETUP_SOFT_404_BODY), SOFT_404_MAX_CHARS)

    def test_empty_content_is_not_flagged(self):
        self.assertFalse(_is_soft_404(""))
        self.assertFalse(_is_soft_404(None))

    def test_interstitials_are_not_misfiled_as_soft_404s(self):
        # A challenge is transient and must keep routing to the retry path.
        self.assertFalse(_is_soft_404(CF_JUST_A_MOMENT_BODY))
        self.assertFalse(_is_soft_404(CF_502_BODY))


class TestDetailCrawlSoft404Guard(unittest.TestCase):
    """crawl_event_url() must discard a dead permalink without spending retries."""

    def _run(self, fake, **kwargs):
        return asyncio.run(
            crawler.crawl_event_url(fake, "https://www.meetup.com/g/events/1/", object(), **kwargs)
        )

    def test_soft_404_detail_page_is_discarded(self):
        fake = _FakeCrawler(MEETUP_SOFT_404_BODY)
        self.assertIsNone(self._run(fake))

    def test_soft_404_is_not_retried(self):
        """Permanent, unlike a challenge — a refetch would only waste an attempt."""
        fake = _FakeCrawler(MEETUP_SOFT_404_BODY)
        with mock.patch.object(
            crawler, '_refetch_past_challenge',
            new=mock.AsyncMock(return_value=REAL_EVENT_PAGE),
        ) as refetch:
            self.assertIsNone(self._run(fake))
        refetch.assert_not_awaited()

    def test_live_detail_page_still_returned(self):
        fake = _FakeCrawler(REAL_EVENT_PAGE)
        self.assertEqual(self._run(fake), REAL_EVENT_PAGE)

if __name__ == '__main__':
    unittest.main()


class TestLumaCapWarning(unittest.TestCase):
    """`api.lu.ma/url?url=` caps featured_items at 20 with no has_more flag.

    A capped calendar is indistinguishable from a small one downstream, so the
    warning at crawl time is the only place the truncation can announce itself.
    """

    def _payload(self, n, wrapped=True, cal='cal-ABC'):
        import json as _json
        body = {'calendar': {'api_id': cal}, 'featured_items': [{'i': i} for i in range(n)]}
        doc = {'kind': 'calendar', 'data': body} if wrapped else body
        return 'https://api.lu.ma/url?url=slug\n' + _json.dumps(doc)

    def test_fires_at_exactly_twenty(self):
        self.assertTrue(crawler.warn_if_luma_capped(self._payload(20), 'Some Calendar'))

    def test_fires_on_unwrapped_shape(self):
        self.assertTrue(
            crawler.warn_if_luma_capped(self._payload(20, wrapped=False), 'Some Calendar')
        )

    def test_silent_below_the_cap(self):
        self.assertFalse(crawler.warn_if_luma_capped(self._payload(19), 'Some Calendar'))

    def test_silent_above_the_cap(self):
        """A paginated get-items feed can exceed 20 legitimately - never warn."""
        self.assertFalse(crawler.warn_if_luma_capped(self._payload(44), 'Some Calendar'))

    def test_silent_on_empty_feed(self):
        self.assertFalse(crawler.warn_if_luma_capped(self._payload(0), 'Some Calendar'))

    def test_silent_on_non_luma_content(self):
        for content in ('', None, 'just some markdown', '<h1>featured_items</h1>',
                        '{"events": []}', 'featured_items but not json'):
            self.assertFalse(crawler.warn_if_luma_capped(content, 'Some Site'))

    def test_names_the_calendar_id_in_the_fix(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            crawler.warn_if_luma_capped(self._payload(20, cal='cal-XYZ'), 'Some Calendar')
        out = buf.getvalue()
        self.assertIn('cal-XYZ', out)
        self.assertIn('pagination_limit=100', out)
        self.assertIn('Some Calendar', out)
