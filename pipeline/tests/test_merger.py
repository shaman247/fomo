"""Tests for merger.py deduplication utilities."""

import unittest
import sys
import os
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import merger
from merger import normalize_name_for_dedup, normalize_time_for_dedup, stem_word, get_significant_words, are_names_similar, is_false_positive, extract_core_title

# Test cases for normalize_name_for_dedup: (input, expected_output)
NORMALIZE_TEST_CASES = [
    # Basic lowercasing and whitespace normalization
    ("Hello World", "hello world"),
    ("  Multiple   Spaces  ", "multiple spaces"),

    # Punctuation removal
    ("Event - With Dashes", "event with dashes"),
    ("What's Happening?", "what s happening"),

    # Underscore removal
    ("Event_Name", "eventname"),

    # Accent/diacritic removal
    ("Stéphane Wrembel", "stephane wrembel"),
    ("Café Concert", "cafe concert"),
    ("Zürich Festival", "zurich festival"),
    ("Naïve Art Show", "naive art show"),

    # Combined cases
    ("Café_Night - Live Músic!", "cafenight live music"),
]

# Test cases for stem_word: (input, expected_output)
STEM_TEST_CASES = [
    # -ency/-ence variations
    ("residency", "residenc"),
    ("residence", "residenc"),
    ("emergency", "emergenc"),  # ency -> enc

    # -ing removal
    ("running", "runn"),
    ("singing", "sing"),

    # -tion/-sion
    ("creation", "creat"),
    ("decision", "decis"),

    # -ies -> -y
    ("stories", "story"),
    ("parties", "party"),

    # -es removal
    ("boxes", "box"),
    ("classes", "class"),

    # -s removal
    ("cats", "cat"),
    ("events", "event"),

    # Words too short for suffix removal
    ("is", "is"),
    ("as", "as"),
    ("yes", "yes"),

    # No suffix match
    ("hello", "hello"),
    ("world", "world"),
]

# Test cases for extract_core_title: (input, expected_output)
CORE_TITLE_TEST_CASES = [
    # Presenter prefixes
    ("Manhattan Theatre Club Presents The Monsters", "The Monsters"),
    ("Lincoln Center Presents: Jazz at Midnight", "Jazz at Midnight"),
    ("BAM Productions: Dance Performance", "Dance Performance"),
    ("Hosted by John Smith: Comedy Night", "Comedy Night"),

    # Subtitles after colon
    ("The Monsters: a Sibling Love Story", "The Monsters"),
    ("Hamilton: An American Musical", "Hamilton"),
    ("Star Wars: A New Hope", "Star Wars"),

    # No changes needed
    ("The Monsters", "The Monsters"),
    ("Jazz Concert", "Jazz Concert"),

    # Short title before colon - keep full name
    ("Q&A: Discussion Panel", "Q&A: Discussion Panel"),

    # Generic delivery/category prefixes — keep full name so the subtitle isn't
    # collapsed to a high-collision substring (e.g. "online" matching every
    # event whose name contains the word "online").
    ("Online: Nothing Stands Alone", "Online: Nothing Stands Alone"),
    ("Virtual: Yoga Class", "Virtual: Yoga Class"),
    ("Workshop: Photography 101", "Workshop: Photography 101"),
]

# Test cases for are_names_similar: (name1, name2, should_match)
# These are real duplicate cases that were missed before
SIMILARITY_TEST_CASES = [
    # Exact match after normalization
    ("Hello World", "hello world", True),
    ("Event  Name", "Event Name", True),

    # Accent variations (real case: Stéphane vs Stephane)
    ("Stéphane Wrembel", "Stephane Wrembel", True),
    ("Café Concert", "Cafe Concert", True),

    # Suffix variations (real case: Residency vs Residence)
    ("Tim Berne Residency", "TIM BERNE - In residence", True),
    ("Art Exhibition", "Art Exhibitions", True),

    # Word subset (real case: Weekly Karaoke subset of Weekly Thursday Karaoke)
    ("Weekly Thursday Karaoke", "Weekly Karaoke", True),
    ("Jazz Night at the Club", "Jazz Night", True),
    ("Annual Summer Festival", "Summer Festival", True),

    # Substring matching
    ("Brooklyn Museum Tour", "Brooklyn Museum", True),
    ("Concert Series", "Concert Series 2026", True),

    # Core title extraction (real case: The Monsters variants)
    ("Manhattan Theatre Club Presents The Monsters", "The Monsters", True),
    ("Manhattan Theatre Club Presents The Monsters", "The Monsters: a Sibling Love Story", True),
    ("The Monsters", "The Monsters: a Sibling Love Story", True),
    ("Lincoln Center Presents: Jazz Night", "Jazz Night at Lincoln Center", True),

    # Screening-format/accessibility parentheticals must not make DIFFERENT films
    # match. Regression 2026-06-01: "(Open Cap/Eng Sub)" contributed 4 generic
    # tokens (open/cap/eng/sub) that tripped asymmetric word-containment, merging
    # different films screened at the same cinema (e106069 Star Wars + Pressure).
    ("Star Wars: Mandalorian & Grogu (Open Cap/Eng Sub)", "Pressure (Open Cap/Eng Sub)", False),
    ("Wicked (Open Cap/Eng Sub)", "Pressure (Open Cap/Eng Sub)", False),
    # ...but the same film across screening labels must still merge
    ("Star Wars: Mandalorian & Grogu (Open Cap/Eng Sub)", "Star Wars: The Mandalorian & Grogu", True),
    ("Pressure (Open Cap/Eng Sub)", "Pressure", True),

    # Should NOT match - different events
    ("Weekly Thursday Karaoke", "Friday Night Karaoke", False),
    ("Tim Berne Concert", "John Smith Concert", False),
    ("Jazz Festival", "Rock Festival", False),
    ("Art Show", "Food Festival", False),
    ("Morning Yoga", "Evening Dance", False),

    # Generic "Online:" prefix must not act as a core-title hook (regression
    # 2026-05-14 — a brooklynpride.org admin notice "Parade Registration is
    # online NOW!" was merging into "Online: Nothing Stands Alone …" because
    # extract_core_title collapsed the latter to "Online" and the 6-char
    # substring matched any title containing the word "online").
    ("Parade Registration is online NOW!", "Online: Nothing Stands Alone – A Four Part Course Exploring the Heart Sutra", False),

    # Umbrella name vs enumerated "N of M" series member must NOT merge
    # (regression 2026-06-24: the bare Broadway run "Schmigadoon" absorbed the
    # Entertainment Community Fund benefit "Schmigadoon! Producer's Picks
    # [3 of 4]" via substring matching, polluting the run with foreign URLs).
    ("Schmigadoon", "Schmigadoon! Producer's Picks [3 of 4]", False),
    ("Summer Camp", "Summer Camp Session 2 of 8", False),
    # ...but the same enumerated member across crawls must still merge.
    ("Schmigadoon! Producer's Picks [3 of 4]", "Schmigadoon! Producer's Picks [3 of 4]", True),

    # Distinct sub-events under a shared generic prefix must NOT merge: core-title
    # extraction reduces "Early Literacy: ..." to the umbrella head "Early
    # Literacy", which is contained in the other's core. The DISTINCT subtitles
    # ("Fine Motor Skills" vs "...Summer Stories") are the tell. Regression
    # 2026-06-24 (two different NYPL "Early Literacy ..." programs at one branch).
    ("Early Literacy Process Art: Fine Motor Skills",
     "Early Literacy: Lapsit and Little Movers Storytime: Summer Stories", False),
    ("Teen Tech Lab: 3D Printing Basics", "Teen Tech: Robotics Build Workshop", False),
    # ...but when the SUBTITLES match, it's the same event with a fuller prefix —
    # must still merge (the umbrella-head gate only blocks divergent subtitles).
    ("Brooklyn Museum First Saturdays: Live Jazz Set", "First Saturdays: Live Jazz Set", True),
    ("Williamsburg Lapsit Storytime: Babies and Books", "Lapsit Storytime: Babies and Books", True),
    # ...and a subtitled "Artist: Tour" vs an unsubtitled "Artist at Venue"
    # listing is the SAME concert — the gate must not split it (no subtitle on
    # one side => not an umbrella-head conflation).
    ("Chet Faker: A Love For Strangers Tour", "Chet Faker at The Rooftop at Pier 17", True),
    # ...a pure leading prefix is a fuller title of the SAME event — merge.
    ("Summer Reading Kickoff", "Summer Reading Kickoff Party at the Library", True),

    # Edge cases
    ("A", "B", False),  # Single letters
    ("Concert Tonight", "Gallery Opening", False),  # Completely different events
]

# Test cases for is_false_positive: (name1, name2, is_false_positive)
# These are cases where names look similar but are actually different events
FALSE_POSITIVE_TEST_CASES = [
    # Men's vs Women's sports - should NOT match
    ("NYU Men's Basketball vs Columbia", "NYU Women's Basketball vs Columbia", True),
    ("Men's Tennis Tournament", "Women's Tennis Tournament", True),

    # Different showtimes - should NOT match
    ("New Year's Eve at The Stand! (6:00 PM)", "New Year's Eve at The Stand! (8:00 PM)", True),
    ("Comedy Show 7:30 PM", "Comedy Show 9:30 PM", True),

    # Different bare-hour showtimes - should NOT match (comedy-club multi-showtime listings)
    ("Friday: Primetime Comedy 8pm", "Friday: Primetime Comedy 10pm", True),
    ("Friday: Primetime Comedy 10pm", "Friday: Primetime Comedy 12am", True),
    ("Late Show 11pm", "Late Show 9pm", True),
    # Same time in different formats - SHOULD match (not a false positive)
    ("Comedy Show 8pm", "Comedy Show 8:00pm", False),

    # Early vs Late sets - should NOT match
    ("New Years Eve Early Set", "New Years Eve Late Set", True),
    ("Jazz Night Early Show", "Jazz Night Late Show", True),

    # Different night numbers - should NOT match
    ("Festival Night 1", "Festival Night 2", True),
    ("Concert Series Night 3", "Concert Series Night 4", True),

    # Different episodes - should NOT match
    ("Twin Peaks: Season 2, Ep. 1", "Twin Peaks: Season 2, Ep. 2", True),
    ("Breaking Bad Episode 5", "Breaking Bad Episode 6", True),

    # Different sports opponents - should NOT match
    ("NYU Basketball vs Columbia", "NYU Basketball vs Princeton", True),
    ("Yankees vs Red Sox", "Yankees vs Mets", True),

    # Same opponent variations - should match (NOT false positive)
    ("NYU vs Columbia University", "NYU vs Columbia", False),
    ("Team A vs Team B - Finals", "Team A vs Team B", False),

    # Regular duplicates - should match (NOT false positive)
    ("Jazz Concert", "Jazz Concert at the Club", False),
    ("Art Exhibition", "Art Exhibition Opening", False),

    # Bare/umbrella name vs distinct "Head: Subtitle" sibling - should NOT merge.
    # Regression 2026-06-01: a single-token festival name ("DanceAfrica") was
    # absorbing a long-running art installation ("BAM DanceAfrica 2026: Visual
    # Art | Sanaa Gateja", on view May–Sep) via loose substring/subset matching,
    # dragging the festival's displayed end date to September 30.
    ("DanceAfrica", "BAM DanceAfrica 2026: Visual Art | Sanaa Gateja", True),
    ("Jazz", "Jazz at Lincoln Center: Duke Ellington Tribute", True),
    # Bare name EQUALS the head => same event, must still merge (NOT a false positive)
    ("The Monsters", "The Monsters: a Sibling Love Story", False),
    ("Brooklyn Museum", "Brooklyn Museum: First Saturdays", False),

    # Umbrella vs enumerated "N of M" member - should NOT merge (regression
    # 2026-06-24: "Schmigadoon" absorbing "...Producer's Picks [3 of 4]").
    ("Schmigadoon", "Schmigadoon! Producer's Picks [3 of 4]", True),
    ("Summer Camp", "Summer Camp Session 2 of 8", True),
    # Same enumerated member - NOT a false positive (must still merge)
    ("Schmigadoon! Producer's Picks [3 of 4]", "Schmigadoon! Producer's Picks [3 of 4]", False),
]


class TestNormalizeNameForDedup(unittest.TestCase):
    """Tests for the normalize_name_for_dedup function."""

    def test_normalize_cases(self):
        """Test all normalization cases."""
        for input_str, expected in NORMALIZE_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(normalize_name_for_dedup(input_str), expected)


class TestNormalizeTimeForDedup(unittest.TestCase):
    """Tests for normalize_time_for_dedup — collapses format drift from nyc.gov etc."""

    def test_format_variants_collapse(self):
        cases = [
            ('11:30 AM', '11:30am'),
            ('11:30am',  '11:30am'),
            ('1:00 PM',  '1pm'),
            ('1pm',      '1pm'),
            ('9:00 AM',  '9am'),
            ('9am',      '9am'),
            ('12pm',     '12pm'),
            (None,       ''),
            ('',         ''),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_time_for_dedup(raw), expected)


class TestStemWord(unittest.TestCase):
    """Tests for the stem_word function."""

    def test_stem_cases(self):
        """Test all stemming cases."""
        for input_str, expected in STEM_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(stem_word(input_str), expected)


class TestGetSignificantWords(unittest.TestCase):
    """Tests for the get_significant_words function."""

    def test_filters_short_words(self):
        """Words shorter than 3 characters and stop words should be filtered out."""
        result = get_significant_words("A is the an")
        self.assertEqual(result, set())  # "the" is a stop word, rest are < 3 chars

    def test_returns_set(self):
        """Should return a set of words."""
        result = get_significant_words("Hello World Hello")
        self.assertEqual(result, {"hello", "world"})

    def test_stemmed_words(self):
        """With stem=True, words should be stemmed."""
        result = get_significant_words("running events", stem=True)
        self.assertEqual(result, {"runn", "event"})


class TestExtractCoreTitle(unittest.TestCase):
    """Tests for the extract_core_title function."""

    def test_core_title_cases(self):
        """Test all core title extraction cases."""
        for input_str, expected in CORE_TITLE_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(extract_core_title(input_str), expected)


class TestIsFalsePositive(unittest.TestCase):
    """Tests for the is_false_positive function."""

    def test_false_positive_cases(self):
        """Test all false positive detection cases."""
        for name1, name2, expected_fp in FALSE_POSITIVE_TEST_CASES:
            with self.subTest(name1=name1, name2=name2):
                result = is_false_positive(name1, name2)
                self.assertEqual(
                    result,
                    expected_fp,
                    f"Expected is_false_positive({name1!r}, {name2!r}) = {expected_fp}"
                )

    def test_symmetry(self):
        """False positive detection should be symmetric."""
        test_pairs = [
            ("NYU Men's Basketball", "NYU Women's Basketball"),
            ("Show 6:00 PM", "Show 8:00 PM"),
            ("Twin Peaks Ep. 1", "Twin Peaks Ep. 2"),
        ]
        for name1, name2 in test_pairs:
            with self.subTest(name1=name1, name2=name2):
                self.assertEqual(
                    is_false_positive(name1, name2),
                    is_false_positive(name2, name1)
                )


class TestFanShowingIsFalsePositive(unittest.TestCase):
    """A cinema "Fan Event" is a separately ticketed showing on its own date, listed
    alongside the film's regular run under a nearly identical name. Merging the two
    unions their occurrences and leaves the survivor holding two sort_order=0 URLs,
    so the primary ticket link becomes non-deterministic and often wrong.

    The guard is deliberately narrow — screening-FORMAT variants of the same showing
    must keep merging, and the bare word "fan" appears in plenty of ordinary titles.
    """

    FAN_SHOWING_SPLITS = [
        ("Legend of the White Dragon", "Legend of the White Dragon Fan Event"),
        ("Super Troopers 3", "Super Troopers 3: Special Broken Lizard Fan Event"),
        ("Scary Movie", "Scary Movie Opening Night Fan Event"),
        ("Supergirl", "Supergirl Fan First Screenings"),
        ("Dune: Part Three", "Dune: Part Three Fan Screening"),
        ("Wicked: For Good", "Wicked: For Good Fan Premiere"),
    ]

    MUST_STILL_MERGE = [
        # Screening-format variants of the same showing (memory:
        # merger_cinema_format_parens_false_match) — no fan marker on either side.
        ("Spider-Man: Brand New Day", "Spider-Man: Brand New Day (Open Cap/Eng Sub)"),
        ("The Odyssey", "The Odyssey (IMAX)"),
        ("PAW Patrol: The Dino Movie", "PAW Patrol: The Dino Movie (3D)"),
        # Both sides carry the fan marker — same showing, differently punctuated.
        ("Legend of the White Dragon Fan Event", "Legend of the White Dragon - Fan Event"),
        # "fan" as an ordinary word, not a showing marker.
        ("Met Opera Live in HD: Cosi Fan Tutte", "Met Opera: Live in HD Cosi Fan Tutte"),
        ("When Sh*t Hits the Fan - Broken Heart Dharma",
         "Online: When Sh*t Hits the Fan – Broken Heart Dharma"),
        ("World Cup 26 Fan Village", "World Cup 26 Fan Village at Rockefeller Center"),
    ]

    def test_fan_showing_splits_from_regular_run(self):
        for regular, fan in self.FAN_SHOWING_SPLITS:
            with self.subTest(regular=regular, fan=fan):
                self.assertTrue(
                    is_false_positive(regular, fan),
                    f"{fan!r} is a distinct showing and must not merge into {regular!r}"
                )
                self.assertFalse(
                    are_names_similar(regular, fan),
                    f"{fan!r} must not be treated as similar to {regular!r}"
                )

    def test_guard_is_symmetric(self):
        for regular, fan in self.FAN_SHOWING_SPLITS:
            with self.subTest(regular=regular, fan=fan):
                self.assertEqual(
                    is_false_positive(regular, fan),
                    is_false_positive(fan, regular),
                )

    def test_guard_does_not_split_legitimate_pairs(self):
        for name1, name2 in self.MUST_STILL_MERGE:
            with self.subTest(name1=name1, name2=name2):
                self.assertFalse(
                    is_false_positive(name1, name2),
                    f"{name1!r} vs {name2!r} must NOT be flagged as a false positive"
                )


class TestAreNamesSimilar(unittest.TestCase):
    """Tests for the are_names_similar function."""

    def test_similarity_cases(self):
        """Test all similarity cases."""
        for name1, name2, should_match in SIMILARITY_TEST_CASES:
            with self.subTest(name1=name1, name2=name2):
                result = are_names_similar(name1, name2)
                self.assertEqual(
                    result,
                    should_match,
                    f"Expected {name1!r} vs {name2!r} to {'match' if should_match else 'NOT match'}"
                )

    def test_false_positives_dont_match(self):
        """Events that are false positives should not be considered similar."""
        false_positive_pairs = [
            ("NYU Men's Basketball vs Columbia", "NYU Women's Basketball vs Columbia"),
            ("New Year's Eve at The Stand! (6:00 PM)", "New Year's Eve at The Stand! (8:00 PM)"),
            ("Twin Peaks: Season 2, Ep. 1", "Twin Peaks: Season 2, Ep. 2"),
            ("Festival Night 1", "Festival Night 2"),
            ("New Years Eve Early Set", "New Years Eve Late Set"),
        ]
        for name1, name2 in false_positive_pairs:
            with self.subTest(name1=name1, name2=name2):
                self.assertFalse(
                    are_names_similar(name1, name2),
                    f"Expected {name1!r} vs {name2!r} to NOT match (false positive)"
                )

    def test_symmetry(self):
        """Similarity should be symmetric: similar(a,b) == similar(b,a)."""
        test_pairs = [
            ("Tim Berne Residency", "TIM BERNE - In residence"),
            ("Weekly Karaoke", "Weekly Thursday Karaoke"),
            ("Jazz Festival", "Rock Festival"),
        ]
        for name1, name2 in test_pairs:
            with self.subTest(name1=name1, name2=name2):
                self.assertEqual(
                    are_names_similar(name1, name2),
                    are_names_similar(name2, name1)
                )


class TestDatelessCrawlEventMatching(unittest.TestCase):
    """A crawl_event carrying NO dates at all (an "Ongoing" exhibition whose
    detail page is dateless too) must still be able to say "this show is still
    listed" by linking to its existing event.

    MoMA's `Marcel Duchamp` (e66269) went archived because its crawl_events had
    zero crawl_event_occurrences: the merger's loader required a future
    occurrence, so the crawl_event was never even considered, never linked, and
    archival read the show as absent from the crawl.
    """

    def setUp(self):
        # MoMA (location 582) and Gagosian (location 331) both run a show called
        # "Marcel Duchamp" — the classic wrong-link this matcher must not make.
        self.by_location_id = {
            582: [{'id': 66269, 'name': 'Marcel Duchamp'},
                  {'id': 70001, 'name': 'Frida and Diego: The Last Dream'}],
            331: [{'id': 194543, 'name': 'Marcel Duchamp'}],
        }
        self.by_coords = {}
        self.by_location = {
            'museum of modern art moma': [
                {'id': 66269, 'name': 'Marcel Duchamp', 'location_id': 582}],
            'moma design store soho': [
                {'id': 80002, 'name': 'Modern Mural: Nina Chanel Abney', 'location_id': None}],
        }

        self.by_website = {
            62: [{'id': 66269, 'name': 'Marcel Duchamp', 'location_name': 'MoMA'},
                 {'id': 66275, 'name': 'Modern Mural: Nina Chanel Abney',
                  'location_name': 'MoMA'}],
            77: [{'id': 90001, 'name': 'Studio Visit', 'location_name': 'North Gallery'},
                 {'id': 90002, 'name': 'Studio Visit', 'location_name': 'South Gallery'}],
        }

    def _match(self, name, location_id=None, lat=None, lng=None, location_name=None,
               website_id=None):
        return merger._match_dateless_crawl_event(
            name, location_id, lat, lng, location_name,
            self.by_location_id, self.by_coords, self.by_location,
            website_id, self.by_website)

    def test_exact_name_at_the_same_venue_matches(self):
        self.assertEqual(self._match('Marcel Duchamp', location_id=582), 66269)

    def test_same_name_at_a_different_venue_is_not_matched(self):
        """The Gagosian show is a different exhibition that happens to share a name."""
        self.assertEqual(self._match('Marcel Duchamp', location_id=999), None)
        self.assertNotEqual(self._match('Marcel Duchamp', location_id=331), 66269)

    def test_partial_name_match_is_refused(self):
        """With no dates there is no second signal, so only exact names count."""
        self.assertIsNone(self._match('Marcel Duchamp: A Retrospective', location_id=582))
        self.assertIsNone(self._match('Duchamp', location_id=582))

    def test_case_and_punctuation_are_normalized(self):
        self.assertEqual(self._match('MARCEL  DUCHAMP!', location_id=582), 66269)

    def test_location_name_tier_matches_when_no_location_id(self):
        self.assertEqual(
            self._match('Modern Mural: Nina Chanel Abney',
                        location_name='MoMA Design Store Soho'),
            80002)

    def test_location_name_tier_rejects_a_conflicting_location_id(self):
        """A resolved location_id outranks the raw location_name text: the
        crawl_event is pinned to venue 999, so MoMA's event is not its show."""
        self.assertIsNone(
            self._match('Marcel Duchamp', location_id=999,
                        location_name='Museum of Modern Art (MoMA)'))

    def test_unknown_venue_without_a_website_matches_nothing(self):
        self.assertIsNone(self._match('Marcel Duchamp', location_name='Somewhere Else'))
        self.assertIsNone(self._match('Marcel Duchamp'))

    def test_venueless_row_falls_back_to_a_unique_same_website_name(self):
        """MoMA's satellite "MoMA Design Store Soho" isn't in `locations`, so the
        crawl_event has no venue signal at all — but the website has exactly one
        show by that name."""
        self.assertEqual(
            self._match('Modern Mural: Nina Chanel Abney',
                        location_name='MoMA Design Store Annex', website_id=62),
            66275)

    def test_website_fallback_refuses_an_ambiguous_name(self):
        """Two same-named shows at different venues: a dateless row can't choose."""
        self.assertIsNone(
            self._match('Studio Visit', location_name='Unknown Annex', website_id=77))

    def test_website_fallback_is_not_used_when_the_venue_is_known(self):
        """A crawl_event pinned to a venue that has no such show links to nothing —
        it must not wander to another venue of the same website."""
        self.assertIsNone(self._match('Marcel Duchamp', location_id=999, website_id=62))
        # Venue known (MoMA has events under that location_name) but no show by
        # this name there — must not jump to the same website's other venue.
        self.assertIsNone(
            self._match('Modern Mural: Nina Chanel Abney',
                        location_name='Museum of Modern Art (MoMA)', website_id=62))

    def test_blank_name_matches_nothing(self):
        self.assertIsNone(self._match('', location_id=582))


class TestDatelessUnarchiveGate(unittest.TestCase):
    """A dateless link may only un-archive an event that is still showable."""

    class FakeCursor:
        def __init__(self, row):
            self.row = row
            self.params = None

        def execute(self, sql, params=None):
            self.params = params

        def fetchone(self):
            return self.row

    def test_event_with_a_live_occurrence_may_unarchive(self):
        cursor = self.FakeCursor((1,))
        self.assertTrue(merger._event_has_live_occurrence(cursor, 66269, date(2026, 7, 26)))

    def test_event_with_only_past_occurrences_stays_archived(self):
        cursor = self.FakeCursor(None)
        self.assertFalse(merger._event_has_live_occurrence(cursor, 66269, date(2026, 7, 26)))


class TestSinglePrimaryUrl(unittest.TestCase):
    """`exporter` orders an event's URLs by `sort_order` alone, so two rows at
    sort_order = 0 make the published link query-plan-dependent — the user gets
    whichever the optimizer happens to return first.

    Regal exposed this: 139 live events carried two sort_order = 0 rows because
    the merger inserts every new event-specific detail URL at 0 without looking
    at the incumbent primary. `_demote_other_primary_urls` makes the incoming
    URL the sole primary and pushes the incumbents to the end of the ordering.
    """

    class FakeCursor:
        """Just enough of event_urls to exercise the guard's three statements."""

        def __init__(self, rows):
            # rows: list of dicts with id / event_id / sort_order
            self.rows = rows
            self._result = []

        def execute(self, sql, params=None):
            s = ' '.join(sql.split())
            if s.startswith('SELECT id FROM event_urls WHERE event_id = %s AND sort_order = 0'):
                self._result = [(r['id'],) for r in
                                sorted(self.rows, key=lambda r: r['id'])
                                if r['event_id'] == params[0] and r['sort_order'] == 0]
            elif s.startswith('SELECT COALESCE(MAX(sort_order), 0)'):
                orders = [r['sort_order'] for r in self.rows if r['event_id'] == params[0]]
                self._result = [(max(orders) if orders else 0,)]
            elif s.startswith('UPDATE event_urls SET sort_order = %s WHERE id = %s'):
                for r in self.rows:
                    if r['id'] == params[1]:
                        r['sort_order'] = params[0]
                self._result = []
            else:  # pragma: no cover - guard should issue nothing else
                raise AssertionError('unexpected SQL: ' + s)

        def fetchall(self):
            return self._result

        def fetchone(self):
            return self._result[0] if self._result else None

    def _rows(self, spec, event_id=1):
        return [{'id': i, 'event_id': event_id, 'sort_order': so}
                for i, so in spec]

    def test_incumbent_primary_is_demoted_before_a_new_one_is_inserted(self):
        rows = self._rows([(10, 0), (11, 1)])
        cursor = self.FakeCursor(rows)
        self.assertEqual(merger._demote_other_primary_urls(cursor, 1), 1)
        self.assertEqual({r['id']: r['sort_order'] for r in rows}, {10: 2, 11: 1})

    def test_several_incumbents_get_distinct_ranks(self):
        """All-at-0 rows must not merely be moved to a single shared value —
        that would leave the same ambiguity one rank down."""
        rows = self._rows([(10, 0), (11, 0), (12, 0)])
        cursor = self.FakeCursor(rows)
        self.assertEqual(merger._demote_other_primary_urls(cursor, 1), 3)
        self.assertEqual(sorted(r['sort_order'] for r in rows), [1, 2, 3])

    def test_keep_id_stays_primary(self):
        """The promote branch keeps the row it is about to promote at 0."""
        rows = self._rows([(10, 0), (11, 0)])
        cursor = self.FakeCursor(rows)
        self.assertEqual(merger._demote_other_primary_urls(cursor, 1, keep_id=11), 1)
        self.assertEqual({r['id']: r['sort_order'] for r in rows}, {10: 1, 11: 0})

    def test_no_primary_row_is_a_no_op(self):
        rows = self._rows([(10, 1), (11, 2)])
        cursor = self.FakeCursor(rows)
        self.assertEqual(merger._demote_other_primary_urls(cursor, 1), 0)
        self.assertEqual({r['id']: r['sort_order'] for r in rows}, {10: 1, 11: 2})

    def test_other_events_are_untouched(self):
        rows = self._rows([(10, 0)]) + self._rows([(20, 0)], event_id=2)
        cursor = self.FakeCursor(rows)
        merger._demote_other_primary_urls(cursor, 1)
        self.assertEqual({r['id']: r['sort_order'] for r in rows}, {10: 1, 20: 0})

    def test_demoted_row_lands_after_the_listing_url_rank(self):
        """A listing URL sits at 99; the demoted primary must sort after it so it
        cannot become the fallback link ahead of a real detail page."""
        rows = self._rows([(10, 0), (11, 99)])
        cursor = self.FakeCursor(rows)
        merger._demote_other_primary_urls(cursor, 1)
        self.assertEqual({r['id']: r['sort_order'] for r in rows}, {10: 100, 11: 99})


if __name__ == "__main__":
    unittest.main()
