"""Tests for processor.py text utilities."""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import (
    create_short_name,
    normalize_event_name_caps,
    strip_leading_emoji,
    is_obvious_non_event,
    _normalize_location_name,
    _extract_street_address,
    _parse_city_state,
    _region_conflict,
)

# Test cases: (input, expected_output, description)
SHORT_NAME_TEST_CASES = [
    # Preserve times without am/pm that are part of the event name
    ("In Bed by 1:00 - New Years Eve 2026 at Caveat", "In Bed by 1:00"),

    # Remove trailing times with am/pm
    ("Event Name 7pm", "Event Name"),
    ("Show Name 10:30 PM", "Show Name"),

    # Remove trailing dates
    ("Museum Tour January 15th", "Museum Tour"),
    ("Gallery Opening Oct 5th 6:00pm", "Gallery Opening"),
    ("Park closes 1:00pm December 24", "Park closes"),

    # Preserve meaningful content like session numbers
    ("Everybody Can Sing - Session 2 - Wed 7:30 PM", "Everybody Can Sing - Session 2"),

    # Remove day + time suffixes
    ("Crochet for Beginners - Wed - 6:30PM - Jan", "Crochet for Beginners"),

    # Remove inline dates but preserve middle content
    ("New York Sign Museum December 28th Tour 3:00pm", "New York Sign Museum Tour"),

    # Short titles without metadata stay unchanged
    ("Film Night: The Great Movie", "Film Night: The Great Movie"),

    # Remove venue suffixes
    ("Concert at Madison Square Garden", "Concert"),

    # Short names that fit on the map label aren't over-shortened
    ("Java with Jo Anne", "Java with Jo Anne"),
    ("Coffee w/ Sarah", "Coffee w/ Sarah"),
    ("Talk at MoMA", "Talk at MoMA"),

    # Long titles with colons extract subtitle
    ("A Very Long Exhibition Title That Exceeds Forty Characters: The Actual Show Name", "The Actual Show Name"),

    # Time colons don't trigger subtitle extraction (original bug)
    ("New York Sign Museum December 28th Tour 3:00pm", "New York Sign Museum Tour"),

    # Common prefixes removed
    ("Exhibition: Art of the Century", "Art of the Century"),
    ("Screening: Classic Film", "Classic Film"),

    # Empty input
    ("", ""),
]


class TestCreateShortName(unittest.TestCase):
    """Tests for the create_short_name function."""

    def test_short_name_cases(self):
        """Test all short name transformation cases."""
        for input_str, expected in SHORT_NAME_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(create_short_name(input_str), expected)

    def test_none_input(self):
        """None input should return None."""
        self.assertIsNone(create_short_name(None))


# Test cases: (input, expected_output)
NORMALIZE_CAPS_TEST_CASES = [
    # Apostrophe possessives lowercased
    ("EDGAR A. POE'S SMASHED VALENTINE", "Edgar A. Poe's Smashed Valentine"),

    # Middle initials preserved (A. not lowercased to a.)
    ("MARY J. BLIGE TRIBUTE NIGHT", "Mary J. Blige Tribute Night"),

    # Connecting words lowercased (except at start)
    ("NIGHT OF THE LIVING DEAD", "Night of the Living Dead"),
    ("A TALE OF TWO CITIES", "A Tale of Two Cities"),

    # Roman numerals uppercased
    ("STAR WARS EPISODE III SCREENING", "Star Wars Episode III Screening"),

    # Ordinals lowercased
    ("THE 5TH ANNUAL COMEDY SHOW", "The 5th Annual Comedy Show"),

    # w/ prefix lowercased
    ("JAZZ NIGHT W/ THE QUARTET", "Jazz Night w/ the Quartet"),

    # Film sizes
    ("CLASSIC 35MM FILM FESTIVAL", "Classic 35mm Film Festival"),

    # Two-letter acronyms preserved
    ("DJ NIGHT AT THE CLUB", "DJ Night at the Club"),

    # Already mixed case (<=50% upper) — unchanged
    ("Edgar A. Poe's Smashed Valentine", "Edgar A. Poe's Smashed Valentine"),

    # Short names (<=5 chars) — unchanged
    ("HELLO", "HELLO"),

    # Empty string — unchanged
    ("", ""),
]


# Test cases: (input, expected_output)
STRIP_EMOJI_TEST_CASES = [
    # Leading emoji stripped, trailing preserved
    ("\U0001f5a4\U0001f56f\ufe0f Edgar A. Poe's Smashed Valentine \U0001f494\U0001f377",
     "Edgar A. Poe's Smashed Valentine \U0001f494\U0001f377"),

    # Multiple leading emoji with spaces
    ("\U0001f389 \U0001f38a Party Time", "Party Time"),

    # No leading emoji — unchanged
    ("Event Name", "Event Name"),

    # Leading digits not stripped (digits are \p{Emoji} but not \p{Emoji_Presentation})
    ("3 Blind Mice", "3 Blind Mice"),

    # Text-default emoji without variation selector (e.g. dove 🕊 U+1F54A) — should still be stripped
    ("\U0001f54a Upper West Side Girl Club Coffee Walk", "Upper West Side Girl Club Coffee Walk"),

    # Empty string
    ("", ""),
]


class TestNormalizeEventNameCaps(unittest.TestCase):
    """Tests for the normalize_event_name_caps function."""

    def test_normalize_caps_cases(self):
        for input_str, expected in NORMALIZE_CAPS_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(normalize_event_name_caps(input_str), expected)


class TestStripLeadingEmoji(unittest.TestCase):
    """Tests for the strip_leading_emoji function."""

    def test_strip_emoji_cases(self):
        for input_str, expected in STRIP_EMOJI_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(strip_leading_emoji(input_str), expected)

    def test_none_input(self):
        self.assertIsNone(strip_leading_emoji(None))


class TestNormalizeLocationName(unittest.TestCase):
    """Tests for _normalize_location_name borough/state stripping."""

    def test_generic_token_keeps_borough(self):
        # A venue whose name collapses to a bare generic token must NOT be
        # stripped, or it exact-matches any unrelated event located in a
        # "Gallery" / "Loft" / etc. (regression: Ace Hotel "Gallery" sublocation
        # was mapping to the "Gallery Brooklyn" venue in Red Hook).
        cases = [
            ("Gallery Brooklyn", "gallery brooklyn"),
            ("Dance Manhattan", "dance manhattan"),
            ("GYM NYC", "gym nyc"),
            ("The Loft New York", "loft new york"),
            ("The Table New York", "table new york"),
            ("Basement NY", "basement ny"),
        ]
        for input_str, expected in cases:
            with self.subTest(input=input_str):
                self.assertEqual(_normalize_location_name(input_str), expected)

    def test_distinctive_token_still_strips(self):
        # Distinctive proper-noun names should still strip the borough/state so
        # an aggregator's bare "Fotografiska" resolves to "Fotografiska New York".
        # Directional/area words also still strip — "Midtown Manhattan" -> "midtown"
        # is intended neighborhood resolution, not a venue collision.
        cases = [
            ("Aurora Brooklyn", "aurora"),
            ("Fotografiska New York", "fotografiska"),
            ("Isola Brooklyn", "isola"),
            ("The Bell House Brooklyn", "bell house"),
            ("Williamsburg, Brooklyn", "williamsburg"),
            ("Midtown Manhattan", "midtown"),
            ("Downtown Brooklyn", "downtown"),
        ]
        for input_str, expected in cases:
            with self.subTest(input=input_str):
                self.assertEqual(_normalize_location_name(input_str), expected)


class TestExtractStreetAddress(unittest.TestCase):
    """Tests for _extract_street_address house-number requirement."""

    def test_real_addresses(self):
        cases = [
            ("347 Davis Ave, Staten Island, NY 10310, USA", "347 davis ave"),
            ("100 Hinsdale St, NY", "100 hinsdale st"),
            ("5-25 46th Ave, Queens, NY", "5-25 46th ave"),
        ]
        for input_str, expected in cases:
            with self.subTest(input=input_str):
                self.assertEqual(_extract_street_address(input_str), expected)

    def test_non_addresses_rejected(self):
        # A value with no leading house number is not a street address. Without
        # this guard, "Harbor" (a venue whose address is literally
        # "Harbor, Frankfort, NY") or a bare park name pollutes the address tier
        # and collides with unrelated queries.
        for input_str in [
            "Harbor, Frankfort, NY 13340, USA",
            "Bryant Park, New York, NY 10018, USA",
            "Central Park, New York, NY, USA",
            "New York, NY 10004",
        ]:
            with self.subTest(input=input_str):
                self.assertIsNone(_extract_street_address(input_str))


class TestParseCityState(unittest.TestCase):
    def test_parses_city_state_tail(self):
        cases = [
            ("9003 Bergenline Ave, North Bergen, NJ 07047, USA", ("north bergen", "NJ")),
            ("Central Park, New York, NY, USA", ("new york", "NY")),
            ("Columbus Park, Mulberry St & Baxter St, New York, NY 10013, USA", ("new york", "NY")),
            ("47 Strickland Rd, Cos Cob, CT 06804", ("cos cob", "CT")),
        ]
        for addr, expected in cases:
            with self.subTest(addr=addr):
                self.assertEqual(_parse_city_state(addr), expected)

    def test_no_recognizable_tail(self):
        for addr in ["", None, "Some Venue", "Prospect Park", "123 Main St"]:
            with self.subTest(addr=addr):
                self.assertEqual(_parse_city_state(addr), (None, None))


class TestRegionConflict(unittest.TestCase):
    # city -> single state, as learned from DB addresses
    CITY_STATES = {
        "hoboken": {"NJ"}, "hackensack": {"NJ"}, "union city": {"NJ"},
        "jersey city": {"NJ"}, "new york": {"NY"}, "brooklyn": {"NY"},
        "greenwich": {"CT"},
    }
    NY = {"address": "X, New York, NY 10013, USA"}
    NJ = {"address": "X, Hoboken, NJ 07030, USA"}

    def _conf(self, raw, cand):
        return _region_conflict(raw, cand, self.CITY_STATES)

    def test_flags_cross_state_address_tail(self):
        # A "Columbus Park ... Hoboken" event must not match a Manhattan candidate.
        self.assertTrue(self._conf("Columbus Park, 10th St and Clinton St, Hoboken", self.NY))
        self.assertTrue(self._conf("Columbus Park, 199 W Franklin St, Hackensack, NJ", self.NY))
        self.assertTrue(self._conf("Washington Park, Union City/Jersey City", self.NY))

    def test_allows_same_state(self):
        # Same-state (incl. cross-borough) is fine — the guard only blocks states.
        self.assertFalse(self._conf("Columbus Park, ..., Hoboken", self.NJ))
        self.assertFalse(self._conf("Foo, Brooklyn, NY", self.NY))

    def test_ignores_city_word_in_venue_name_or_street(self):
        # City words embedded in a venue name or street must NOT trigger.
        self.assertFalse(self._conf("Elizabeth Catlett Art Space", self.NY))  # no comma
        self.assertFalse(self._conf("Fairfield Inn, 330 W 40th St, New York, NY", self.NY))
        self.assertFalse(self._conf("Greenwich House Theater", self.NY))  # no comma
        self.assertFalse(self._conf("Foo, 50 Madison Ave, New York, NY", self.NY))

    def test_no_candidate_state_is_safe(self):
        self.assertFalse(self._conf("Foo, Hoboken", {"address": "Online"}))


class TestIsObviousNonEvent(unittest.TestCase):
    """Junk filter: fundraising campaigns, submission-call contests, info booths.

    Positive fixtures are the real name+description of events 157587, 157914,
    and 158129 (extracted 2026-06-10, hand-suppressed as UNKNOWN)."""

    # --- positive fixtures: must be dropped ---

    def test_festival_info_booth_listing(self):
        # e157587 — marketing booth inside a festival program (note the curly
        # apostrophe from the source page).
        self.assertTrue(is_obvious_non_event(
            "L’Alliance Booths",
            "L’Alliance New York is the center for French language and "
            "francophone cultures. Visit one of our info booths to learn more "
            "about our French classes for kids and adults, membership, "
            "upcoming film screenings, performances, library, and more, with "
            "a special Bastille Day deal!"))

    def test_donation_match_campaign(self):
        # e157914 — 89-day donation-match fundraising campaign.
        self.assertTrue(is_obvious_non_event(
            "Give Where Your Heart Lives Match Campaign",
            "A match campaign to support and empower the local community."))

    def test_submission_call_art_contest(self):
        # e158129 — call-for-submissions design contest.
        self.assertTrue(is_obvious_non_event(
            "Children's Library Card Art Contest (PreK-Grade 5)",
            "Community members are invited to participate in a library card "
            "design contest. Winning submissions will be printed for National "
            "Library Week."))

    def test_giving_day_and_anchored_campaigns(self):
        # Name-only fundraising patterns work without a description.
        self.assertTrue(is_obvious_non_event("North Fork Giving Day", ""))
        self.assertTrue(is_obvious_non_event(
            "Annual Fundraising Campaign 2026", None))

    # --- negative fixtures: real events that must NOT be dropped ---

    def test_attendable_trivia_contest_kept(self):
        self.assertFalse(is_obvious_non_event(
            "Trivia Contest Tuesdays",
            "Compete in our weekly pub trivia contest. Winners take home a "
            "bar tab!"))

    def test_attendable_pie_eating_contest_kept(self):
        self.assertFalse(is_obvious_non_event(
            "Pie-Eating Contest",
            "Watch contestants race to finish a whole pie. Sign up at the "
            "fairgrounds tent."))

    def test_live_art_contest_without_submission_framing_kept(self):
        # "Art Contest" name alone is not enough — call-for-entries language
        # in the description is required.
        self.assertFalse(is_obvious_non_event(
            "Live Art Contest",
            "Watch ten artists paint head-to-head while the audience votes "
            "for the winner."))

    def test_contest_awards_ceremony_kept(self):
        # Attendable-occasion words in the name veto the contest rule even
        # when the description mentions submissions.
        self.assertFalse(is_obvious_non_event(
            "Library Card Art Contest Awards Ceremony",
            "Celebrate the winning submissions with the young artists and "
            "their families."))

    def test_rental_prefix_kept(self):
        # A bare "RENTAL:" prefix is NOT junk — venues use it as an internal
        # booking label on public events.
        self.assertFalse(is_obvious_non_event(
            "RENTAL: Bachata Social Dance Party",
            "An open-to-all social dance with beginner lesson at 8pm."))

    def test_charity_benefit_kept(self):
        # An attendable benefit is not a donation campaign.
        self.assertFalse(is_obvious_non_event(
            "Benefit Concert for CAST North Fork",
            "An evening of live music raising funds for local families. All "
            "donations matched by a generous sponsor."))

    def test_campaign_kickoff_event_kept(self):
        # Campaign patterns are anchored to the end of the name, so the
        # attendable kickoff for a fundraising campaign survives.
        self.assertFalse(is_obvious_non_event(
            "Capital Campaign Kickoff Celebration",
            "Join us to celebrate the launch of our capital campaign."))

    def test_festival_with_booths_mid_name_kept(self):
        # "booths" mid-name (not name-final) never triggers the booth rule.
        self.assertFalse(is_obvious_non_event(
            "Harvest Festival: Food Booths, Games & Live Music",
            "Stop by the food booths and enjoy live music all afternoon."))

    def test_two_signal_rules_require_description(self):
        # Without a corroborating description the ambiguous categories are
        # kept (conservative: a false drop silently loses a real event).
        self.assertFalse(is_obvious_non_event(
            "Children's Library Card Art Contest (PreK-Grade 5)", None))
        self.assertFalse(is_obvious_non_event("L’Alliance Booths", ""))

    def test_name_only_signature_still_works(self):
        # Pre-existing single-argument call style remains valid.
        self.assertTrue(is_obvious_non_event("Open Call for Artists"))
        self.assertFalse(is_obvious_non_event("Jazz Night at the Park"))


if __name__ == "__main__":
    unittest.main()
