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
    apply_crawled_details,
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
    """Junk filter: fundraising campaigns, submission-call contests, info
    booths, childcare amenities.

    Positive fixtures are the real name+description of events 157587, 157914,
    and 158129 (extracted 2026-06-10, hand-suppressed as UNKNOWN), plus
    childcare-amenity events 159310, 363, 20105, and 108296 (church nursery
    care during worship, hand-suppressed 2026-06-10/11)."""

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

    def test_nursery_care_during_worship(self):
        # e159310 (Wiggin House) — childcare amenity during worship services,
        # not an attendable event.
        self.assertTrue(is_obvious_non_event(
            "Nursery-Preschool Care",
            "Our nursery provides a safe, nurturing environment for children "
            "ages 6 months to 5 years during worship services."))

    def test_nursery_childcare_during_the_service(self):
        # e363 (All Souls) — "during the worship service" framing.
        self.assertTrue(is_obvious_non_event(
            "Nursery and Childcare",
            "Nursery care provided by professional sitters is available for "
            "children ages 1-3 during the worship service. Check in at the "
            "front desk when you arrive for the service."))

    def test_nursery_care_while_parents_attend(self):
        # e20105 — "Parents can attend worship while their children are
        # supervised" framing.
        self.assertTrue(is_obvious_non_event(
            "Nursery Care",
            "Safe and professional nursery care provided for infants and "
            "toddlers during Sunday morning services. Parents can attend "
            "worship while their children are supervised in a welcoming "
            "environment."))

    def test_child_care_supporting_families_attending(self):
        # e108296 — "to support families attending" framing.
        self.assertTrue(is_obvious_non_event(
            "Child Care",
            "Child care services are provided weekly on Sunday mornings to "
            "support families attending church activities."))

    def test_school_early_dismissal_dropped(self):
        # e170643 — school-calendar early-dismissal marker (name-only).
        self.assertTrue(is_obvious_non_event(
            "Fair Lawn Schools Early Dismissal", None))

    def test_holiday_closure_observance_dropped(self):
        # e84293 — a community-board office's holiday-closure notice.
        self.assertTrue(is_obvious_non_event(
            "Memorial Day",
            "The office is closed in observance of the holiday."))

    def test_drink_month_promotion_dropped(self):
        # e170885 — a bar's month-long drink-special marketing period.
        self.assertTrue(is_obvious_non_event(
            "Martini Month",
            "Celebrate Martini Month throughout June with special Tanqueray "
            "martinis at Medusa Bar."))

    def test_retail_spend_and_get_promotion_dropped(self):
        # e170900 — a vendor's spend-and-get purchase incentive.
        self.assertTrue(is_obvious_non_event(
            "Blackbird Special World Cup Promotion",
            "Spend $40 with Blackbird at the brewery to receive a free KCBC "
            "beer 4-pack to go, while supplies last."))

    def test_venue_reopening_announcement_dropped(self):
        # e170899 — a museum's reopening status notice.
        self.assertTrue(is_obvious_non_event(
            "Museum Reopening",
            "The Neue Galerie, including galleries, shops, and cafés, reopens "
            "in Autumn 2026 following summer restoration enhancements. Visitors "
            "are welcomed back to see iconic works of Gustav Klimt."))

    def test_registration_open_suffix_dropped(self):
        # e171536 — registration-window announcement where the notice is a
        # suffix, not the start of the name. The start-anchored rule misses it.
        self.assertTrue(is_obvious_non_event(
            "Read a Palooza Registration Open",
            "Registration is now open for our summer reading program."))
        self.assertTrue(is_obvious_non_event(
            "Summer Camp Registration Now Open", ""))

    def test_non_library_program_placeholder_dropped(self):
        # e171539 — library room-booking placeholder ("Non Library Program").
        self.assertTrue(is_obvious_non_event("Non Library Program", ""))
        self.assertTrue(is_obvious_non_event("Non-Library Program", None))

    def test_bare_generic_name_no_description_dropped(self):
        # e171547 — a bare generic one-word name with no description is a
        # placeholder row the extractor should never have emitted.
        self.assertTrue(is_obvious_non_event("Music", ""))
        self.assertTrue(is_obvious_non_event("Program", None))
        self.assertTrue(is_obvious_non_event("TBD", ""))
        self.assertTrue(is_obvious_non_event("Untitled", "   "))

    def test_cinema_format_badge_chips_dropped(self):
        # e173472-e173476 — AMC premium-format / accessibility badge chips that
        # leak from theater calendars as standalone "events". The whole name is
        # just the format descriptor. Name-only match (description irrelevant).
        self.assertTrue(is_obvious_non_event("Dolby Cinema at AMC", None))
        self.assertTrue(is_obvious_non_event("RealD 3D", ""))
        self.assertTrue(is_obvious_non_event("Laser at AMC", None))
        self.assertTrue(is_obvious_non_event("70mm", ""))
        self.assertTrue(is_obvious_non_event(
            "Open Caption (On-screen Subtitles)", None))
        self.assertTrue(is_obvious_non_event("IMAX at AMC", ""))
        self.assertTrue(is_obvious_non_event("Audio Description", None))

    # --- negative fixtures: real events that must NOT be dropped ---

    def test_holiday_celebration_kept(self):
        # e41561 — a bar's Memorial Day celebration shares the bare holiday
        # name but reads as an attendable event.
        self.assertFalse(is_obvious_non_event(
            "Memorial Day",
            "Come celebrate the long weekend with us at Rosa's At Park! A "
            "great way to kick off the summer season with friends."))

    def test_registration_mid_name_kept(self):
        # "Registration" mid-name (not the start, not a window-open suffix) is a
        # real attendable event — only bare announcements are dropped.
        self.assertFalse(is_obvious_non_event(
            "Open Registration Soccer Tournament",
            "Sign up your team and compete in our all-day tournament."))
        self.assertFalse(is_obvious_non_event(
            "Voter Registration Drive",
            "Help neighbors register to vote at our community table."))

    def test_bare_generic_name_with_description_kept(self):
        # A generic one-word title is fine when there is a real description —
        # the bare-name rule only fires on an empty description.
        self.assertFalse(is_obvious_non_event(
            "Music",
            "An evening of live jazz with the Julia Danielle Quartet."))
        self.assertFalse(is_obvious_non_event(
            "Performance",
            "Object Collection presents a live-film performance piece."))

    def test_generic_word_in_longer_name_kept(self):
        # The bare-name rule requires a full-string match, so multi-word names
        # containing a generic word survive even without a description.
        self.assertFalse(is_obvious_non_event("Music in the Park", ""))
        self.assertFalse(is_obvious_non_event("Family Program", None))

    def test_real_screening_with_format_suffix_kept(self):
        # The cinema-badge rule anchors to the whole name, so a real film that
        # merely carries a format/accessibility tag survives.
        self.assertFalse(is_obvious_non_event(
            "Wicked (Open Caption)",
            "An open-caption screening of the film."))
        self.assertFalse(is_obvious_non_event("Oppenheimer in 70mm", ""))
        self.assertFalse(is_obvious_non_event("Avatar: RealD 3D", None))
        # "Prime" / "Big D" only fire with the AMC qualifier, never bare.
        self.assertFalse(is_obvious_non_event(
            "Prime", "A late-night party at the rooftop bar."))

    def test_juneteenth_workshop_kept(self):
        # e87101 — bare "Juneteenth" name, but the body is an art workshop.
        self.assertFalse(is_obvious_non_event(
            "Juneteenth",
            "Celebrate Juneteenth by creating collaborative art projects that "
            "honor the holiday."))

    def test_drink_week_tasting_kept(self):
        # A "<drink> Week" tasting event is attendable — the veto fires.
        self.assertFalse(is_obvious_non_event(
            "Negroni Week Tasting",
            "Join us for a guided tasting of featured Negroni variations all "
            "week long."))

    def test_band_named_promotion_kept(self):
        # e82823 — "...Pawn Promotion" is a band in a live-music lineup, not a
        # retail promo; the description gate keeps it.
        self.assertFalse(is_obvious_non_event(
            "Roseblud / Cestari / Cfra / Pawn Promotion",
            "A live music event featuring performances by Roseblud, Cestari, "
            "Cfra, and Pawn Promotion. Strictly for attendees 21 and older."))

    def test_grand_reopening_party_kept(self):
        # An attendable reopening celebration survives via the name veto.
        self.assertFalse(is_obvious_non_event(
            "Grand Reopening Party",
            "Celebrate our reopening after renovation with live music and "
            "drinks all night."))

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

    def test_parent_child_classes_kept(self):
        # Parent-child programs are attendable events — any non-amenity word
        # in the name vetoes the childcare rule.
        self.assertFalse(is_obvious_non_event(
            "Toddler Storytime",
            "Songs, rhymes, and stories for toddlers and their caregivers."))
        self.assertFalse(is_obvious_non_event(
            "Caregiver & Me",
            "Music and movement for babies while caregivers participate."))

    def test_childcare_workshops_kept(self):
        # Childcare-themed trainings/classes are real events.
        self.assertFalse(is_obvious_non_event(
            "Childcare CPR Training",
            "Learn infant and child CPR. Certification provided during the "
            "session for parents, babysitters, and childcare providers."))
        # e21737 — real fixture.
        self.assertFalse(is_obvious_non_event(
            "Babysitting 101 Training Course",
            "A comprehensive course designed to help teens develop the "
            "essential skills and responsibility needed to be a successful "
            "babysitter."))
        self.assertFalse(is_obvious_non_event(
            "Infant Care Class for New Parents",
            "Hands-on infant care basics for expecting and new parents."))

    def test_preschool_open_house_kept(self):
        self.assertFalse(is_obvious_non_event(
            "Preschool Open House",
            "Tour our nursery school classrooms and meet teachers who care "
            "for children ages 2-5 during the school year."))

    def test_dropoff_program_kept(self):
        # A drop-off program that is itself the event — "while parents enjoy"
        # is not during-another-activity-here framing, and the name has
        # non-amenity words anyway.
        self.assertFalse(is_obvious_non_event(
            "Kids' Night Out Drop-Off Party",
            "Drop the kids off for pizza, games, and a movie while parents "
            "enjoy a night out."))

    def test_public_records_nursery_club_series_kept(self):
        # e90185 etc. — "The Nursery" is a club stage at Public Records; the
        # leading "The" and artist names veto the name gate.
        self.assertFalse(is_obvious_non_event(
            "The Nursery: HAAi All Day Long",
            "Nursery Sundays returns for the season with an all-day set from "
            "London-based producer and DJ HAAi."))

    def test_nursery_care_without_during_framing_kept(self):
        # e53674 — amenity-shaped name but no during-another-activity signal
        # in the description: fail open, leave for human review.
        self.assertFalse(is_obvious_non_event(
            "Nursery Care",
            "Childcare services provided for families during the morning."))

    def test_two_signal_rules_require_description(self):
        # Without a corroborating description the ambiguous categories are
        # kept (conservative: a false drop silently loses a real event).
        self.assertFalse(is_obvious_non_event(
            "Children's Library Card Art Contest (PreK-Grade 5)", None))
        self.assertFalse(is_obvious_non_event("L’Alliance Booths", ""))
        self.assertFalse(is_obvious_non_event("Nursery-Preschool Care", None))
        self.assertFalse(is_obvious_non_event("Nursery Care", ""))

    def test_casting_call_dropped(self):
        # e165536 — a casting/recruitment call, not an attendable public event.
        self.assertTrue(is_obvious_non_event("Fashion Week Queens Casting Call"))
        self.assertTrue(is_obvious_non_event("Open Casting Call for Short Film"))
        self.assertTrue(is_obvious_non_event("Models Wanted"))
        self.assertTrue(is_obvious_non_event("Dancers Needed for Music Video"))
        self.assertTrue(is_obvious_non_event("Vocalists Sought for New Choir"))

    def test_casting_adjacent_real_events_kept(self):
        # "Wanted" / "casting" in other contexts must not over-match.
        self.assertFalse(is_obvious_non_event(
            "Wanted: Dead or Alive Screening",
            "A 35mm screening of the 1987 action film."))
        self.assertFalse(is_obvious_non_event(
            "The Casting Couch: A Comedy Show",
            "Stand-up comedy about Hollywood auditions."))

    def test_election_day_marker_dropped(self):
        # e165769 — bare civic date markers leak from gov/library calendars.
        self.assertTrue(is_obvious_non_event("Primary Election Day"))
        self.assertTrue(is_obvious_non_event("Election Day"))
        self.assertTrue(is_obvious_non_event("General Election Day 2026"))
        self.assertTrue(is_obvious_non_event("Presidential Primary Day"))
        self.assertTrue(is_obvious_non_event("Primary Day"))

    def test_election_night_events_kept(self):
        # Attendable election-night occasions must survive (end-anchored marker).
        self.assertFalse(is_obvious_non_event(
            "Election Day Watch Party",
            "Join us to watch the returns come in with drinks and snacks."))
        self.assertFalse(is_obvious_non_event(
            "Election Night Returns Social",
            "Gather to follow the results together."))
        self.assertFalse(is_obvious_non_event(
            "Voter Registration Drive",
            "Get registered to vote before the deadline."))

    def test_attraction_admission_dropped(self):
        # e166200 — a zoo's dated general-admission ticket, not a scheduled
        # event. Name-only (works without a description).
        self.assertTrue(is_obvious_non_event(
            "Bergen County Zoo Admission 2026",
            "Purchase tickets for admission to the Bergen County Zoo, located "
            "in Van Saun County Park in Paramus."))
        self.assertTrue(is_obvious_non_event("Bronx Zoo Admission"))
        self.assertTrue(is_obvious_non_event("Botanical Garden Admission 2026"))

    def test_general_admission_ticket_tier_kept(self):
        # A show's "General Admission" ticket tier is not attraction admission.
        self.assertFalse(is_obvious_non_event(
            "Summer Jazz Series - General Admission",
            "General admission tickets to the rooftop concert."))
        self.assertFalse(is_obvious_non_event(
            "Museum Late: After Hours Party (Admission Included)",
            "An evening party with DJ, drinks, and gallery access."))

    def test_rewards_membership_marketing_dropped(self):
        # e166229 — retail loyalty marketing leaked from a store calendar.
        self.assertTrue(is_obvious_non_event(
            "Premium & Rewards Members Online Exclusive Bonus $10 Reward on "
            "Our Biggest Books", None))

    def test_member_occasion_kept(self):
        # A real member occasion carries an occasion word and no marketing combo.
        self.assertFalse(is_obvious_non_event(
            "Rewards Members Holiday Party",
            "Celebrate the season with fellow members."))
        self.assertFalse(is_obvious_non_event(
            "Member Appreciation Night",
            "An evening of thanks for our members with light bites."))

    def test_test_placeholder_rows_dropped(self):
        # e166445 — an obvious test/placeholder row.
        self.assertTrue(is_obvious_non_event("Do not buy tickets test test"))
        self.assertTrue(is_obvious_non_event("test test"))

    def test_test_word_in_real_event_kept(self):
        # A lone "test" in a real name must not over-match.
        self.assertFalse(is_obvious_non_event(
            "Test Kitchen Cooking Class",
            "A hands-on cooking class in our test kitchen."))
        self.assertFalse(is_obvious_non_event(
            "SAT Test Prep Workshop", "Free practice test and strategy session."))

    def test_standing_attraction_dropped(self):
        # e166689 / e166201 — a carousel and a water-park splash attraction:
        # things you ride/visit whenever the venue is open, not scheduled events.
        self.assertTrue(is_obvious_non_event(
            "Le Carrousel",
            "Take a whirl at Le Carrousel in Bryant Park with 14 delightful "
            "creatures to ride. This carousel is an homage to both European and "
            "American carousel traditions, revolving to French cabaret music."))
        self.assertTrue(is_obvious_non_event(
            "The Splash Zone at The Lakes at Darlington County Park",
            "Bergen County's newest water attraction. Hop around and climb on "
            "this obstacle course on the water."))

    def test_attraction_requires_both_signals(self):
        # Visit-it framing without an attraction noun (and vice versa) is kept.
        self.assertFalse(is_obvious_non_event(
            "Swing Dance Social",
            "Take a whirl on the dance floor with a live band all night."))
        self.assertFalse(is_obvious_non_event(
            "Le Carrousel", None))

    def test_attraction_event_at_attraction_kept(self):
        # A real scheduled event AT a carousel/splash venue keeps (name veto).
        self.assertFalse(is_obvious_non_event(
            "Carousel Sing-Along Concert",
            "Ride the carousel then enjoy live show tunes. Creatures to ride "
            "for all ages."))
        self.assertFalse(is_obvious_non_event(
            "Splash Zone Family Story Hour",
            "Stories by the water attraction; kids can hop around after."))

    def test_name_only_signature_still_works(self):
        # Pre-existing single-argument call style remains valid.
        self.assertTrue(is_obvious_non_event("Open Call for Artists"))
        self.assertFalse(is_obvious_non_event("Jazz Night at the Park"))


class _RecordingCursor:
    """Minimal cursor stub that records executed SQL for assertions."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        return (0,)


class _NoopConnection:
    def commit(self):
        pass


class TestApplyCrawledDetailsEmoji(unittest.TestCase):
    """The detail crawl must not wipe an existing emoji with an empty result.

    Single-event extraction frequently returns no emoji; writing that NULL over
    the crawl_event left the merged event blank on the map (e.g. "Poetry Night
    at Barzakh Café"). The UPDATE should only touch emoji when one was found.
    """

    _TAG_CONTEXT = ({}, {}, set(), [])  # tag_rules, ancestor_map, root_tags, disambig

    def _run(self, emoji):
        cursor = _RecordingCursor()
        apply_crawled_details(
            cursor, _NoopConnection(), 123,
            {'description': 'A real description.', 'hashtags': [], 'emoji': emoji},
            self._TAG_CONTEXT,
        )
        # The crawl_events UPDATE is the statement that sets description.
        update = next(s for s in cursor.statements
                      if s[0].startswith("UPDATE crawl_events SET"))
        return update

    def test_empty_emoji_does_not_overwrite(self):
        sql, params = self._run('')
        self.assertNotIn("emoji = %s", sql)
        self.assertEqual(params, ['A real description.', 123])

    def test_blocked_emoji_does_not_overwrite(self):
        sql, _ = self._run('⬛')
        self.assertNotIn("emoji = %s", sql)

    def test_real_emoji_is_written(self):
        sql, params = self._run('🎤')
        self.assertIn("emoji = %s", sql)
        self.assertEqual(params, ['A real description.', '🎤', 123])


if __name__ == "__main__":
    unittest.main()
