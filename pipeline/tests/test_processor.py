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
    is_cancelled_by_url,
    _normalize_location_name,
    _extract_street_address,
    _extract_street_address_loose,
    sublocation_redundant_with_address,
    _parse_city_state,
    _region_conflict,
    _extract_parenthetical_parent,
    apply_crawled_details,
    get_location_id,
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

    def test_campus_closure_notice_dropped(self):
        # e139324 — Duke Farms' recurring weekly closure notice, captured as an
        # event 13 times before this rule existed.
        self.assertTrue(is_obvious_non_event(
            "Campus Closed",
            "The Duke Farms campus is closed every Sunday & Monday."))

    def test_estate_venue_closure_nouns_dropped(self):
        for name in ("Grounds Closed", "Trails Closed for Maintenance",
                     "Farm Closes Early", "Cafe Closed", "Preserve Closure"):
            with self.subTest(name=name):
                self.assertTrue(is_obvious_non_event(name, "Notice."))

    def test_closure_noun_words_in_real_events_kept(self):
        # The noun must sit immediately before the closure word — real events
        # that merely mention these places must survive.
        for name in ("Campus Tour", "Farm to Table Dinner",
                     "Trails & Ales Group Hike", "Closing Reception: New Work",
                     "Trail Closure Workshop", "Campus Closure Community Meeting",
                     "Cafe Concert Series", "Behind the Scenes at the Preserve"):
            with self.subTest(name=name):
                self.assertFalse(is_obvious_non_event(name, "A real event."))

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


class TestJunkFilterGaps20260719(unittest.TestCase):
    """Three non-event shapes that reached the event-type classifier on
    2026-07-19 because the junk filter had no rule for them.

    Fixtures are the real name+description of events 193783 (NYC Resistor
    "Busy"), 193866 (Kadampa "No Walk-In Class Today") and 193797 (The Gem
    Saloon "Lunch Specials")."""

    # --- (a) opaque calendar placeholders ---

    def test_busy_placeholder_dropped(self):
        # e193783 — NYC Resistor publishes bare "Busy" blocks routinely. The
        # merged row's description is the placeholder string, which must count
        # as blank for the bare-generic-name rule.
        self.assertTrue(is_obvious_non_event("Busy", "No description available."))
        self.assertTrue(is_obvious_non_event("Busy", ""))
        self.assertTrue(is_obvious_non_event("Busy", None))

    def test_other_opaque_availability_markers_dropped(self):
        for name in ("Reserved", "Blocked", "Booked", "On Hold", "Occupied",
                     "Unavailable", "Private", "Maintenance"):
            self.assertTrue(is_obvious_non_event(name, ""), name)

    def test_opaque_marker_with_real_description_kept(self):
        # The rule is gated on a blank description, so a genuine event that
        # happens to be titled "Busy" survives.
        self.assertFalse(is_obvious_non_event(
            "Busy",
            "An evening of improv from the Busy troupe, with a bar and a "
            "late-night set."))

    # --- (b) negation / cancellation titles ---

    def test_no_walk_in_class_today_dropped(self):
        # e193866 — the pre-existing "No <X> Today" rule used `[\w\s]*`, which
        # could not span the hyphen in "Walk-In", so this slipped through.
        self.assertTrue(is_obvious_non_event(
            "No Walk-In Class Today (Chelsea Center)", "No description available."))
        self.assertTrue(is_obvious_non_event("No Drop-In Open Gym This Week", ""))
        self.assertTrue(is_obvious_non_event("No Children's Story Time Today", ""))

    def test_cancellation_notices_dropped(self):
        self.assertTrue(is_obvious_non_event("CANCELLED: Yoga in the Park", "desc"))
        self.assertTrue(is_obvious_non_event("Canceled - Bird Walk", "desc"))
        self.assertTrue(is_obvious_non_event("Movie Night (CANCELLED)", "desc"))
        self.assertTrue(is_obvious_non_event("Book Club - Cancelled", "desc"))
        self.assertTrue(is_obvious_non_event("Class Cancelled", "desc"))
        self.assertTrue(is_obvious_non_event(
            "Tonight's Show Has Been Cancelled", "desc"))
        self.assertTrue(is_obvious_non_event("Closed Today", "desc"))
        self.assertTrue(is_obvious_non_event("Closed This Weekend", "desc"))

    def test_legitimate_no_prefixed_events_kept(self):
        # A leading "No" is common in real event names; the rule requires both
        # a program noun and a temporal marker precisely so these survive.
        self.assertFalse(is_obvious_non_event(
            "No Pants Subway Ride", "Ride the subway without pants."))
        self.assertFalse(is_obvious_non_event(
            "No Lights No Lycra", "A dance party in the dark, every Tuesday."))
        self.assertFalse(is_obvious_non_event(
            "No Sleep Till Brooklyn: A Beastie Boys Tribute", "Live tribute set."))

    def test_legitimate_cancel_words_kept(self):
        # "cancel" as subject matter, not as a status marker.
        self.assertFalse(is_obvious_non_event(
            "Cancel Culture in Context", "A panel discussion at NYU."))
        self.assertFalse(is_obvious_non_event(
            "Cancelled Plans: A Comedy Show", "Standup from local comics."))

    # --- (c) venue marketing / menu items ---

    def test_lunch_specials_dropped(self):
        # e193797 — The Gem Saloon's standing menu, not an occasion.
        self.assertTrue(is_obvious_non_event(
            "Lunch Specials",
            "Daily lunch specials are available Monday through Friday."))
        self.assertTrue(is_obvious_non_event(
            "Happy Hour Specials", "Happy hour specials daily from 4-7pm."))
        self.assertTrue(is_obvious_non_event(
            "Dinner Menu", "Our dinner menu is served Tuesday through Sunday."))

    def test_menu_special_needs_recurring_offer_description(self):
        # A one-night occasion described with the same words is not a menu.
        self.assertFalse(is_obvious_non_event(
            "Lunch Specials",
            "A one-off chef's lunch on July 22 with a live DJ and tasting."))

    def test_menu_special_name_must_be_the_whole_title(self):
        # Any real event built on the same words carries more in the name.
        self.assertFalse(is_obvious_non_event(
            "Lunch Specials Tasting Party",
            "Daily lunch specials, plus a party Monday through Friday."))
        self.assertFalse(is_obvious_non_event(
            "Prix Fixe Dinner with the Chef",
            "A four-course dinner served daily from our specials menu."))
        self.assertFalse(is_obvious_non_event(
            "Happy Hour Trivia",
            "Trivia every Monday with drink specials all week."))

    # --- regression guard ---

    def test_rental_prefix_still_not_junk(self):
        # Venues use "RENTAL:" as an internal booking label on public events.
        # None of the new rules may start dropping these.
        self.assertFalse(is_obvious_non_event(
            "RENTAL: Warehouse Dance Party", "A late-night party, doors at 10."))
        self.assertFalse(is_obvious_non_event("RENTAL: Comedy Showcase", ""))


class TestJunkFilterGaps20260720(unittest.TestCase):
    """Three non-event shapes that reached final classification on 2026-07-20
    and had to be suppressed by hand.

    Fixtures are the real name+description of events 194190 (Innisfree's
    venue-OPEN holiday notice), 194432 (a Saturday-swing series' summer-hiatus
    announcement) and 194509 (an Angelika placeholder screening row)."""

    # --- (a) venue-OPEN holiday notices (inverse of the closure rule) ---

    def test_open_for_holiday_notice_dropped(self):
        self.assertTrue(is_obvious_non_event(
            "Columbus Day/Indigenous Peoples’ Day | Innisfree Open for Holiday",
            "Innisfree is open in observance of Columbus Day/Indigenous "
            "Peoples’ Day. We invite you to spend the day in reflection on the "
            "layered histories of this land."))

    def test_other_open_holiday_phrasings_dropped(self):
        self.assertTrue(is_obvious_non_event(
            "Memorial Day - Garden Open on the Holiday",
            "The garden is open in observance of Memorial Day."))
        self.assertTrue(is_obvious_non_event(
            "Museum Open for Thanksgiving",
            "We are open in observance of Thanksgiving Day; no programs are "
            "scheduled."))

    def test_real_holiday_programming_kept(self):
        # The whole risk of an "Open"/"Holiday" rule is eating real holiday
        # events. Each of these must survive.
        self.assertFalse(is_obvious_non_event(
            "July 4th Concert on the Green",
            "Join us for a free concert and fireworks in observance of "
            "Independence Day."))
        self.assertFalse(is_obvious_non_event(
            "Open Studios",
            "Twenty artists open their studios to the public."))
        self.assertFalse(is_obvious_non_event(
            "Preschool Open House",
            "Tour the classrooms and meet the teachers."))
        self.assertFalse(is_obvious_non_event(
            "Memorial Day BBQ - We're Open for the Holiday!",
            "Come celebrate with us: live music, a cookout and drink specials "
            "all afternoon."))
        self.assertFalse(is_obvious_non_event(
            "Open House on Labor Day",
            "An open house with tours running all day."))

    def test_open_holiday_rule_needs_a_description(self):
        self.assertFalse(is_obvious_non_event(
            "Columbus Day | Innisfree Open for Holiday", None))

    # --- (b) hiatus / series-paused announcements ---

    def test_summer_hiatus_announcement_dropped(self):
        self.assertTrue(is_obvious_non_event(
            "Summer Hiatus ... Monthly Saturday Night Swings @ You Should Be "
            "Dancing...! Nyc (Returning in Sep)",
            "Monthly Saturday Night Swings features a pre-party intro swing "
            "lesson followed by a dance party with live band sets and DJ "
            "music."))

    def test_other_hiatus_phrasings_dropped(self):
        for name in ("Hiatus - Trivia Night Returns in October",
                     "Winter Hiatus: Sunday Sessions",
                     "Open Mic on Hiatus Until Fall"):
            self.assertTrue(is_obvious_non_event(name, "A description."), name)

    def test_events_that_merely_mention_a_break_kept(self):
        for name in ("Hiatus Kaiyote", "The Return of Sunday Sessions",
                     "Summer Series Kickoff", "Coffee Break Social"):
            self.assertFalse(is_obvious_non_event(name, "A description."), name)

    # --- (c) placeholder "Untitled <format>" screening rows ---

    def test_untitled_movie_placeholder_dropped(self):
        self.assertTrue(is_obvious_non_event(
            "Untitled Movie (Angelika SoHo)", "No description available."))
        self.assertTrue(is_obvious_non_event("Untitled Film", ""))
        self.assertTrue(is_obvious_non_event("Untitled Event (Village East)", None))

    def test_untitled_placeholder_with_description_kept(self):
        self.assertFalse(is_obvious_non_event(
            "Untitled Movie (Angelika SoHo)",
            "A secret preview screening of an unannounced feature, with a Q&A "
            "with the director to follow."))

    def test_real_films_containing_untitled_kept(self):
        for name in ('"Untitled" Movie', "An Untitled Horror Movie",
                     "Untitled Horror Movie", "Untitled: A Dance Work"):
            self.assertFalse(is_obvious_non_event(name, ""), name)


class TestSeoAffiliateListicleSpam(unittest.TestCase):
    """Insurance-affiliate SEO listicles injected into website 388's feed
    (RA / Resident Advisor GraphQL) on 2026-07-22.

    Nine rows cleared all three junk layers and got pinned to real NYC venues;
    five reached the map (196425-196433) and had to be suppressed by hand. The
    shape is title-only + year suffix + commercial how-to/bill-pay phrasing.
    Fixtures are the verbatim names and descriptions.
    """

    # --- the real spam, description == title ---

    def test_allstate_listicles_dropped(self):
        for name in (
            "Allstate Insurance Pay Without Login — No Credentials Needed 2026",
            "Allstate Insurance One-Time Payment — No Account Needed Guide 2026",
            "Allstate Insurance Near Me — Locations, Coverage, and Bill Pay 2026",
            "Allstate Insurance Quick Pay — Fastest Bill Pay Method Available 2026",
        ):
            self.assertTrue(is_obvious_non_event(name, name), name)

    def test_progressive_listicles_dropped(self):
        for name in (
            "Progressive Insurance Policy Number — Where to Find It and How to Pay 2026",
            "Progressive Insurance Grace Period — Days Before Cancellation by Policy Type 2026",
            "Progressive Insurance — The Definitive Consumer Guide 2026",
        ):
            self.assertTrue(is_obvious_non_event(name, name), name)

    # --- the same spam with the placeholder description (196429, 196430) ---

    def test_listicles_with_no_description_dropped(self):
        self.assertTrue(is_obvious_non_event(
            "Progressive Insurance AutoPay — Setup, Troubleshoot, and Cancel Guide 2026",
            "No description available."))
        self.assertTrue(is_obvious_non_event(
            "Progressive Insurance One-Time Payment — No Account Needed Guide 2026",
            None))

    # --- negative fixtures: real events that must NOT be dropped ---

    def test_real_how_to_apply_clinic_kept(self):
        # e13529 / e61055 / e90179 — the ONLY real events in the whole events
        # table that clear the year-suffix + commercial-marker gates. The
        # attendable-word veto ("clinic") is what saves them.
        for month in ("February", "April", "May"):
            name = ("Brooklyn Org Application Clinic: How to Apply For Funding "
                    f"From BKO ({month} 2026)")
            self.assertFalse(is_obvious_non_event(name, name), name)

    def test_year_suffix_alone_does_not_drop(self):
        for name in ("Winter Jazzfest 2026", "NYC Pride March 2026",
                     "Open Studios 2026"):
            self.assertFalse(is_obvious_non_event(name, None), name)

    def test_commercial_marker_alone_does_not_drop(self):
        # No trailing year -> not the listicle shape.
        self.assertFalse(is_obvious_non_event(
            "Insurance Literacy Night — Everything You Need to Know", None))

    def test_marker_plus_year_but_real_description_kept(self):
        # A genuine description that is not a copy of the title means the row
        # carries real content; the title-only gate must block the drop.
        self.assertFalse(is_obvious_non_event(
            "Progressive Insurance — The Definitive Consumer Guide 2026",
            "A two-hour evening session in our Bushwick space where a licensed "
            "broker walks through auto policies line by line. Doors at 7pm."))

    def test_attendable_words_veto_the_drop(self):
        for name in ("How to Pay Off Debt Workshop 2026",
                     "Credit Score Clinic 2026",
                     "Everything You Need to Know About Mortgage Rates: A Talk 2026"):
            self.assertFalse(is_obvious_non_event(name, name), name)


class TestSublocationRedundantWithAddress(unittest.TestCase):
    """Normalization gaps found on 2026-07-19 — both would have silently
    dropped a location from future address scans.

    Fixtures are locations 2078 (Empire Stores) and 507 (Mabou Mines)."""

    def test_house_number_inside_building_range(self):
        # loc 2078 — DB "53-83 Water St" is one building; a listing citing
        # "55 Water Street" is the same address, not a sub-venue.
        self.assertTrue(sublocation_redundant_with_address(
            "55 Water Street", "53-83 Water St"))
        self.assertTrue(sublocation_redundant_with_address(
            "81 Water St", "53-83 Water St"))

    def test_range_endpoints_still_match(self):
        self.assertTrue(sublocation_redundant_with_address(
            "12 Vestry St", "12-16 Vestry St"))
        self.assertTrue(sublocation_redundant_with_address(
            "16 Vestry St", "12-16 Vestry St"))
        self.assertTrue(sublocation_redundant_with_address(
            "14 Vestry St", "12-16 Vestry St"))

    def test_range_check_is_symmetric(self):
        self.assertTrue(sublocation_redundant_with_address(
            "53-83 Water St", "55 Water St"))

    def test_number_outside_range_not_redundant(self):
        self.assertFalse(sublocation_redundant_with_address(
            "91 Water St", "53-83 Water St"))
        self.assertFalse(sublocation_redundant_with_address(
            "45 Water St", "53-83 Water St"))

    def test_parity_mismatch_not_redundant(self):
        # A building range runs down one side of the street, so an even number
        # is not inside an odd range even though it is numerically between.
        self.assertFalse(sublocation_redundant_with_address(
            "54 Water St", "53-83 Water St"))

    def test_queens_hyphenated_address_not_treated_as_range(self):
        # "5-52 47th Ave" is a Queens house number, not a 5-through-52 range.
        # Unequal digit lengths and mismatched parity both veto it.
        self.assertFalse(sublocation_redundant_with_address(
            "30 47th Ave", "5-52 47th Ave"))

    def test_different_street_never_redundant(self):
        self.assertFalse(sublocation_redundant_with_address(
            "55 Main St", "53-83 Water St"))

    def test_leading_room_code_and_ordinal_word(self):
        # loc 507 — DB "150 1st Ave Second Floor" vs sublocation
        # "122 CC 150 First Avenue" (room 122CC). Needs both the leading
        # room-code strip and the First -> 1st ordinal-word normalization.
        self.assertTrue(sublocation_redundant_with_address(
            "122 CC 150 First Avenue", "150 1st Ave Second Floor"))
        self.assertTrue(sublocation_redundant_with_address(
            "150 First Avenue", "150 1st Ave"))

    def test_room_code_strip_does_not_eat_directional(self):
        # "150 W 42nd St" must keep its house number — W is a compass
        # directional, not a room code.
        self.assertEqual(
            _extract_street_address_loose("150 W 42nd St"), "150 w 42 st")
        self.assertFalse(sublocation_redundant_with_address(
            "150 W 42nd St", "42 W 150th St"))

    def test_real_sub_venue_values_preserved(self):
        for sub in ("Studio B", "5th Floor", "The Great Hall", "Suite 630"):
            self.assertFalse(
                sublocation_redundant_with_address(sub, "150 1st Ave"), sub)

    def test_room_code_strip_does_not_eat_real_house_numbers(self):
        # A long word after the number is a venue name, not a room code.
        self.assertEqual(
            _extract_street_address_loose("122 Community Center Dr"),
            "122 community center dr")
        self.assertEqual(
            _extract_street_address_loose("45 East 20th St"), "45 e 20 st")
        self.assertFalse(sublocation_redundant_with_address(
            "45 East 20th St", "150 1st Ave"))


class TestCrossStreetSuffixAddresses(unittest.TestCase):
    """Galleries and theaters address themselves by cross street ("980 Madison
    at 76th Street" — loc 333 Gagosian, event 97417). The cross street's own
    type token closed the address regex, so the key came out "980 madison at 76
    st" and never matched the DB form "980 madison ave"; the sublocation then
    exported redundantly beside the venue address.

    Verified against all 31,465 (sublocation, address) pairs in the DB: 5 newly
    redundant, 0 previously-redundant pairs lost."""

    def test_gagosian_cross_street_sublocation_is_redundant(self):
        self.assertTrue(sublocation_redundant_with_address(
            "980 Madison at 76th Street",
            "980 Madison Ave, New York, NY 10075, USA"))

    def test_cross_street_clause_is_stripped(self):
        self.assertIsNone(_extract_street_address_loose("980 Madison at 76th Street"))

    def test_typeless_house_address_matches_typed_db_form(self):
        # e93485 / e174275 / e187065 — sublocation drops the street type.
        self.assertTrue(sublocation_redundant_with_address(
            "55 Chrystie", "55 Chrystie St, New York, NY 10002, USA"))

    def test_queens_hyphenated_db_form_still_matches(self):
        # e129834 — DB "5-85 Woodward Ave" glues to "585 woodward ave".
        self.assertTrue(sublocation_redundant_with_address(
            "585 Woodward", "5-85 Woodward Ave, Ridgewood, NY 11385, USA"))

    # --- the strip must not eat addresses that legitimately contain " at " ---

    def test_address_after_the_preposition_is_preserved(self):
        # The house address comes AFTER " at ", so nothing may be stripped.
        self.assertEqual(
            _extract_street_address_loose("Studio B at 150 W 42nd St"),
            "150 w 42 st")
        self.assertTrue(sublocation_redundant_with_address(
            "Studio B at 150 W 42nd St", "150 W 42nd St, New York, NY"))

    def test_sub_venue_named_with_at_is_not_an_address(self):
        for sub, addr in (
            ("The Loft at Prince Street", "177 Prince St, New York, NY 10012, USA"),
            ("Audubon Center at the Boathouse", "101 East Dr, Brooklyn, NY 11225, USA"),
            ("Pier 55 at Hudson River Park",
             "Little Island, Pier 55 at Hudson River Park, New York, NY 10014, USA"),
            ("East Drive at Center Drive", "171 East Dr, Brooklyn, NY 11215"),
        ):
            self.assertFalse(sublocation_redundant_with_address(sub, addr), sub)

    def test_typed_address_before_the_cross_street_is_unchanged(self):
        # e76977 — already matched before the fix; must still match.
        self.assertTrue(sublocation_redundant_with_address(
            "509 Atlantic Avenue at 3rd Avenue, Downtown Brooklyn",
            "509 Atlantic Ave, Brooklyn, NY 11217, USA"))

    def test_typeless_match_requires_the_same_number_and_street(self):
        self.assertFalse(sublocation_redundant_with_address(
            "982 Madison at 76th Street",
            "980 Madison Ave, New York, NY 10075, USA"))
        self.assertFalse(sublocation_redundant_with_address(
            "980 Lexington at 76th Street",
            "980 Madison Ave, New York, NY 10075, USA"))

    def test_room_and_floor_sublocations_still_preserved(self):
        for sub in ("Studio B", "5th Floor", "Suite 630", "Room 4 at the rear"):
            self.assertFalse(
                sublocation_redundant_with_address(sub, "150 1st Ave"), sub)


class TestIntersectionAddresses(unittest.TestCase):
    """Greenmarkets and park entrances are addressed by cross street, not house
    number, so `_extract_street_address_loose` returned None for BOTH sides and
    the redundant sublocation printed anyway.

    Fixtures are locations 798 (Stuyvesant Town Greenmarket) and 82 (Bay Ridge
    Greenmarket, whose DB address carries the intersection AND a parking-lot
    house number)."""

    def test_stuyvesant_town_intersection(self):
        self.assertTrue(sublocation_redundant_with_address(
            "14th Street Loop & Avenue A",
            "14th St Loop & Avenue A, New York, NY 10009, USA"))

    def test_bay_ridge_intersection_behind_a_house_number(self):
        self.assertTrue(sublocation_redundant_with_address(
            "3rd Avenue & 95th Street",
            "3rd Avenue & 95th Street, Walgreen's Parking, "
            "lot 9408 3rd Ave, Brooklyn, NY 11209, USA"))

    def test_order_insensitive(self):
        self.assertTrue(sublocation_redundant_with_address(
            "Avenue A & 14th St Loop", "14th St Loop & Avenue A, New York, NY"))

    def test_and_and_at_separators(self):
        self.assertTrue(sublocation_redundant_with_address(
            "3rd Avenue and 95th Street", "3rd Ave & 95th St, Brooklyn, NY"))
        self.assertTrue(sublocation_redundant_with_address(
            "3rd Avenue at 95th Street", "3rd Ave & 95th St, Brooklyn, NY"))

    def test_standalone_street_names(self):
        self.assertTrue(sublocation_redundant_with_address(
            "Broadway & 176th Street", "Broadway and W 176th St, New York, NY"))

    def test_different_intersection_not_redundant(self):
        self.assertFalse(sublocation_redundant_with_address(
            "3rd Avenue & 96th Street", "3rd Ave & 95th St, Brooklyn, NY"))
        self.assertFalse(sublocation_redundant_with_address(
            "5th Avenue & 95th Street", "3rd Ave & 95th St, Brooklyn, NY"))

    def test_non_street_ampersand_is_not_an_intersection(self):
        # Both sides must actually name a street; "Arts & Crafts Room" doesn't.
        for sub in ("Arts & Crafts Room", "Bar & Lounge", "Ping Pong & Pool"):
            self.assertFalse(
                sublocation_redundant_with_address(
                    sub, "3rd Ave & 95th St, Brooklyn, NY"), sub)

    def test_intersection_does_not_match_a_house_address(self):
        self.assertFalse(sublocation_redundant_with_address(
            "3rd Avenue & 95th Street", "150 1st Ave, New York, NY"))
        self.assertFalse(sublocation_redundant_with_address(
            "Studio B", "3rd Ave & 95th St, Brooklyn, NY"))


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


def _make_locations_map(entries, website_scoped=None):
    """Build a minimal locations_map for get_location_id from (name, id) pairs."""
    names = {}
    for name, lid in entries:
        names[_normalize_location_name(name)] = {'id': lid, 'emoji': 'X', 'name': name}
    scoped = {}
    for wid, alts in (website_scoped or {}).items():
        scoped[wid] = {
            _normalize_location_name(n): {'id': lid, 'emoji': 'X', 'name': n}
            for n, lid in alts
        }
    return {
        'names': names, 'alternate_names': {}, 'short_names': {}, 'addresses': {},
        'website_scoped': scoped, 'website_linked': {}, 'city_states': {},
    }


class TestLocationTripwireGuard(unittest.TestCase):
    """The fuzzy token-overlap tripwire must not fuse two unrelated venues that
    share only a generic phrase ("X Training Center", "Pier N at Hudson River
    Park") but differ in a distinctive token. Regression for "Babes!" mapping to
    DEP Training Center via "BCC training center"."""

    def _id(self, loc, locmap, website_id=None, sub=None, event_name='Some Event'):
        res = get_location_id(loc, sub, 'site', event_name, locmap, website_id=website_id)
        return (res or {}).get('id')

    def test_acronym_swap_rejected(self):
        m = _make_locations_map([('DEP Training Center', 1927)])
        self.assertIsNone(self._id('BCC training center', m))

    def test_distinct_streetname_rejected(self):
        m = _make_locations_map([('Maple Street Community Garden', 525)])
        self.assertIsNone(self._id('Java Street Community Garden', m))

    def test_distinct_number_rejected(self):
        m = _make_locations_map([('55 Washington Street', 5757)])
        self.assertIsNone(self._id('100 Washington Street', m))

    def test_distinct_pier_number_rejected(self):
        m = _make_locations_map([('Pier 66 at Hudson River Park', 4867)])
        self.assertIsNone(self._id('Pier 25 at Hudson River Park', m))

    def test_typo_still_matches(self):
        # The tripwire's original purpose — single-char typo recovery.
        m = _make_locations_map([('Le Petit Versailles', 500)])
        self.assertEqual(self._id('La Petit Versailles', m), 500)

    def test_saint_abbreviation_still_matches(self):
        m = _make_locations_map([('St. Nicholas Park', 782)])
        self.assertEqual(self._id('Saint Nicholas Park', m), 782)

    def test_corporate_suffix_still_matches(self):
        m = _make_locations_map([('Urbani Truffles USA Corp', 5788)])
        self.assertEqual(self._id('Urbani Truffles USA Inc', m), 5788)

    def test_hyphen_join_still_matches(self):
        # "Mid Hudson" vs "Mid-Hudson": normalization joins the hyphen, so the
        # leftover tokens differ on token count — the guard must reconcile them
        # via containment ("hudson" ⊂ "midhudson") rather than reject.
        m = _make_locations_map([('Mid-Hudson Discovery Museum', 4951)])
        self.assertEqual(self._id('Mid Hudson Discovery Museum', m), 4951)

    def test_website_scoped_alt_resolves_bcc(self):
        # With the curated per-website alt, the same input now resolves to BCC.
        m = _make_locations_map(
            [('DEP Training Center', 1927), ('Brooklyn Comedy Collective', 143)],
            website_scoped={60: [('BCC training center', 143)]})
        self.assertEqual(self._id('BCC training center', m, website_id=60), 143)


class TestCrossWebsiteScopedAltFallback(unittest.TestCase):
    """An EXACT match on a curated website-scoped alternate name is real venue
    knowledge. When nothing else in the cascade matched, honoring it for a
    different website beats returning NULL (which spawns a duplicate event).

    Regression: "Prospect Park Picnic House" (location 6434) had that exact
    alternate-name row scoped to website 2704, so the same string arriving from
    website 464 resolved to nothing at all.
    """

    def _id(self, loc, locmap, website_id=None, sub=None, event_name='Some Event'):
        res = get_location_id(loc, sub, 'site', event_name, locmap, website_id=website_id)
        return (res or {}).get('id')

    def test_scoped_alt_resolves_for_other_website(self):
        m = _make_locations_map(
            [('Picnic House', 6434), ('Prospect Park', 682)],
            website_scoped={2704: [('Prospect Park Picnic House', 6434)]})
        self.assertEqual(
            self._id('Prospect Park Picnic House', m, website_id=464), 6434)

    def test_scoped_alt_resolves_with_no_website_id(self):
        m = _make_locations_map(
            [('Picnic House', 6434)],
            website_scoped={2704: [('Prospect Park Picnic House', 6434)]})
        self.assertEqual(self._id('Prospect Park Picnic House', m), 6434)

    def test_owning_website_still_wins(self):
        m = _make_locations_map(
            [('Picnic House', 6434)],
            website_scoped={2704: [('Prospect Park Picnic House', 6434)]})
        self.assertEqual(
            self._id('Prospect Park Picnic House', m, website_id=2704), 6434)

    def test_conflicting_scoped_alts_stay_unmatched(self):
        # The whole point of scoping is disambiguation: if two websites map the
        # same string to DIFFERENT venues, a cross-website guess is a coin flip.
        m = _make_locations_map(
            [('Aardvark Hall', 100), ('Bumblebee Lodge', 200)],
            website_scoped={10: [('The Annex', 100)],
                            20: [('The Annex', 200)]})
        self.assertIsNone(self._id('The Annex', m, website_id=30))

    def test_scoped_alt_does_not_override_exact_global_name(self):
        # Ordering guard: the new tier runs last, so an exact primary-name match
        # for a different venue must still win.
        m = _make_locations_map(
            [('Picnic House', 6434)],
            website_scoped={2704: [('Picnic House', 9999)]})
        self.assertEqual(self._id('Picnic House', m, website_id=464), 6434)

    def test_scoped_alt_requires_exact_match(self):
        # No partial/prefix credit — an unrelated longer string must not latch on.
        m = _make_locations_map(
            [('Somewhere Else', 1)],
            website_scoped={2704: [('Prospect Park Picnic House', 6434)]})
        self.assertIsNone(self._id('Prospect Park Bandshell Lawn', m, website_id=464))


class TestParentheticalParentVenue(unittest.TestCase):
    """NYC Parks names a sub-feature first and puts the park we actually have a
    row for in an "(in …)" parenthetical ("Main Pool (in Crotona Park)"). The
    full string clears neither the prefix-coverage nor the fuzzy threshold, so
    ~57 Parks sub-features re-orphaned to NULL on every crawl. The last-resort
    tier extracts the parenthetical parent — exact + unambiguous only.
    """

    def _id(self, loc, locmap, website_id=None, sub=None, event_name='Some Event'):
        res = get_location_id(loc, sub, 'site', event_name, locmap, website_id=website_id)
        return (res or {}).get('id')

    def test_extract_parent_helper(self):
        cases = [
            ('Main Pool (in Crotona Park)', 'crotona park'),
            ('Play Area (in Spuyten Duyvil Playground), Bronx', 'spuyten duyvil playground'),
            ("Dance Room (in St. John's Recreation Center), Brooklyn",
             'st johns recreation center'),
            # Not an "(in …)" container — a name qualifier. Must not fire.
            ('Devocion (Williamsburg)', ''),
            ('Somewhere Else', ''),
            ('', ''),
            (None, ''),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_extract_parenthetical_parent(raw), expected)

    def test_pool_resolves_to_park(self):
        m = _make_locations_map([('Crotona Park', 238)])
        self.assertEqual(self._id('Main Pool (in Crotona Park), Bronx', m), 238)

    def test_pier_resolves_to_park(self):
        # "brooklyn bridge park" covers only 0.69 of the full string — just under
        # PREFIX_MATCH_COVERAGE, which is exactly why this used to go NULL.
        m = _make_locations_map([('Brooklyn Bridge Park', 140)])
        self.assertEqual(self._id('Pier 2 (in Brooklyn Bridge Park)', m), 140)

    def test_parent_from_sublocation(self):
        m = _make_locations_map([('Bryant Park', 163)])
        self.assertEqual(
            self._id('Le Carrousel', m, sub='Le Carrousel (in Bryant Park)'), 163)

    def test_curated_scoped_alt_still_wins(self):
        # Ordering guard: the tier runs last, so a curated website-scoped alt on
        # the full string (the way a sub-feature gets pinned to its own row when
        # the parent is the wrong answer) must still take precedence.
        m = _make_locations_map(
            [('Highland Park', 385)],
            website_scoped={2: [('Lower Highland Playground (in Highland Park)', 7777)]})
        self.assertEqual(
            self._id('Lower Highland Playground (in Highland Park), Queens', m,
                     website_id=2), 7777)

    def test_named_subfeature_falls_back_to_parent(self):
        # The convention the ~57 hand-remappings follow: an unresolvable
        # sub-feature maps to its containing park, not to NULL.
        m = _make_locations_map([('Highland Park', 385)])
        self.assertEqual(
            self._id('Lower Highland Playground (in Highland Park), Queens', m), 385)

    def test_ambiguous_parent_declines(self):
        # Two distinct venues share the name — a guess would be a coin flip.
        m = {
            'names': {'columbus park': [{'id': 11, 'emoji': 'X', 'name': 'Columbus Park'},
                                        {'id': 22, 'emoji': 'X', 'name': 'Columbus Park'}]},
            'alternate_names': {}, 'short_names': {}, 'addresses': {},
            'website_scoped': {}, 'website_linked': {}, 'city_states': {},
        }
        self.assertIsNone(self._id('Play Area (in Columbus Park)', m))

    def test_unknown_parent_stays_unmatched(self):
        # Exact only — no fuzzy/prefix credit, so a park we don't have must not
        # latch onto a similarly-named one.
        m = _make_locations_map([('Marine Park', 530)])
        self.assertIsNone(self._id('Playground 278 (in Maritime Park)', m))

    def test_generic_parenthetical_ignored(self):
        m = _make_locations_map([('The Gallery at Somewhere', 900)])
        self.assertIsNone(self._id('Front Room (in gallery)', m))


class _DetailCursor:
    """Cursor stub for apply_crawled_details that answers its lookup queries."""

    def __init__(self, website_id=464):
        self.statements = []
        self._website_id = website_id
        self._next = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        s = ' '.join(sql.split()).lower()
        if 'cr.website_id' in s:
            self._next = (1, self._website_id)
        elif s.startswith('select count(*)'):
            self._next = (0,)
        else:
            self._next = None

    def fetchone(self):
        return self._next


class TestApplyCrawledDetailsRelocation(unittest.TestCase):
    """The detail crawl rewrites location_name/sublocation but historically left
    location_id alone, so an event whose listing-page location was unmatchable
    stayed NULL even after the detail page supplied a name that resolves fine.

    Regression: crawl_event 1057326 got location_name "Pelham Fritz Recreation
    Center" + sublocation "Marcus Garvey Park" from the detail crawl and still
    exported with no location_id.
    """

    _TAG_CONTEXT = ({}, {}, set(), [])

    def _update(self, cursor):
        return next(s for s in cursor.statements
                    if s[0].startswith("UPDATE crawl_events SET"))

    def test_new_location_name_resolves_location_id(self):
        cursor = _DetailCursor()
        locmap = _make_locations_map([('Pelham Fritz Recreation Center', 1970)])
        apply_crawled_details(
            cursor, _NoopConnection(), 1057326,
            {'description': 'd', 'hashtags': [], 'emoji': '',
             'location': 'Pelham Fritz Recreation Center',
             'sublocation': 'Marcus Garvey Park'},
            self._TAG_CONTEXT, locations_map=locmap,
        )
        sql, params = self._update(cursor)
        self.assertIn("location_id = %s", sql)
        self.assertIn(1970, params)

    def test_unmatched_new_location_does_not_clobber_existing_id(self):
        cursor = _DetailCursor()
        locmap = _make_locations_map([('Somewhere Else', 1)])
        apply_crawled_details(
            cursor, _NoopConnection(), 1,
            {'description': 'd', 'hashtags': [], 'emoji': '',
             'location': 'A Venue We Do Not Know'},
            self._TAG_CONTEXT, locations_map=locmap,
        )
        sql, _ = self._update(cursor)
        self.assertNotIn("location_id = %s", sql)

    def test_no_location_change_leaves_location_id_alone(self):
        cursor = _DetailCursor()
        locmap = _make_locations_map([('Pelham Fritz Recreation Center', 1970)])
        apply_crawled_details(
            cursor, _NoopConnection(), 1,
            {'description': 'd', 'hashtags': [], 'emoji': ''},
            self._TAG_CONTEXT, locations_map=locmap,
        )
        sql, _ = self._update(cursor)
        self.assertNotIn("location_id = %s", sql)

    def test_missing_locations_map_is_a_noop(self):
        cursor = _DetailCursor()
        apply_crawled_details(
            cursor, _NoopConnection(), 1,
            {'description': 'd', 'hashtags': [], 'emoji': '',
             'location': 'Pelham Fritz Recreation Center'},
            self._TAG_CONTEXT,
        )
        sql, _ = self._update(cursor)
        self.assertNotIn("location_id = %s", sql)


class TestIsCancelledByUrl(unittest.TestCase):
    """Venues signal a cancellation by re-slugging the URL while leaving the
    visible title clean, so the event otherwise lands looking perfectly live."""

    CANCELLED = [
        # Leading marker (NYC Parks, Carnegie Hall, Asia Society, Eventbrite…)
        'https://www.nycgovparks.org/events/2026/07/18/canceled-kids-in-motion-flynn-playground',
        'https://www.carnegiehall.org/calendar/2026/03/27/cancelled-northeastern-native-arts-festival',
        'https://asiasociety.org/new-york/events/postponed-aapi-poets-power-and-presence',
        'https://www.eventbrite.com/e/cancelled-failure-a-work-in-progress-show-tickets-198797',
        # Relative URL (NYC Parks emits these on some listing pages)
        '/events/2026/07/03/canceled-low-impact-dance-fitness',
        # Trailing marker
        'https://sfxavier.org/event/june-28-5pm-mass-canceled/',
        'https://industrycity.com/event/a-taste-of-grand-bazaar-postponed/',
        'https://madmuseum.org/events/between-us-dana-barnes-event-cancelled',
        # Marker mid-slug
        'https://salmagundi.org/2026-monotype-party-postponed-summer/',
    ]

    NOT_CANCELLED = [
        # A real panel ABOUT cancel culture — bare "cancel" must never match
        'https://events.nyu.edu/event/382314-cancel-culture-context-gender-and-sexuality',
        # No delimiter after the word
        'https://www.caveat.nyc/events/cancelledpitched-through-friends',
        'https://example.com/events/cancellation-policy-workshop',
        # Rescheduled events still happen, just on a new date
        'https://www.ypl.org/event/rescheduled-sing-along-storytime-tati-sabrina-112171',
        'https://www.eventbrite.com/e/rescheduled-field-meridians-kimjang-party-tickets-197843',
        # Marker only in the query string / fragment
        'https://example.com/e/my-show?aff=canceled-promo',
        'https://example.com/e/my-show#postponed',
        # Host containing the word must not count — only the path does
        'https://postponed.example.com/events/my-show',
        '',
    ]

    def test_cancelled_urls_detected(self):
        for url in self.CANCELLED:
            with self.subTest(url=url):
                self.assertTrue(is_cancelled_by_url(url))

    def test_live_urls_untouched(self):
        for url in self.NOT_CANCELLED:
            with self.subTest(url=url):
                self.assertFalse(is_cancelled_by_url(url))

    def test_none_is_safe(self):
        self.assertFalse(is_cancelled_by_url(None))


if __name__ == "__main__":
    unittest.main()
