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

    # Apostrophes are DELETED, not spaced, so a possessive matches the
    # apostrophe-less spelling of the same title. This case previously expected
    # "what s happening" — changed deliberately when the possessive-mismatch bug
    # was fixed (sources disagree about apostrophes on the same event name).
    ("What's Happening?", "whats happening"),
    ("Hell's Kitchen", "hells kitchen"),
    ("Hells Kitchen", "hells kitchen"),
    ("Women's Day", "womens day"),
    ("Womens Day", "womens day"),
    # Curly apostrophe (U+2019) — what most CMSes emit — normalizes identically
    ("Kid’s Crafternoon", "kids crafternoon"),
    ("Kids Crafternoon", "kids crafternoon"),
    # Plural possessive
    ("Writers' Circle", "writers circle"),
    ("Writer's Circle", "writers circle"),
    # Contractions were already fine and must stay that way
    ("Rock 'n' Roll", "rock n roll"),
    ("Rock n Roll", "rock n roll"),
    # An apostrophe must not glue two real words together
    ("Alice/Bob", "alice bob"),

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

    # "In-Person:" / "In Person:" is NYPL's and BPL's house prefix — a delivery
    # mode, never a title. Collapsing it handed the containment tiers the core
    # "In-Person", which matched every other library program sharing the prefix
    # and fused unrelated classes into one event (regression 2026-08-17).
    ("In-Person: Searching Bloomberg: One-on-One", "In-Person: Searching Bloomberg: One-on-One"),
    ("In Person: Friday Open Lab - Databases", "In Person: Friday Open Lab - Databases"),
    ("IN PERSON: Open Lab", "IN PERSON: Open Lab"),
    ("Hybrid: Book Club", "Hybrid: Book Club"),
    # A real head that merely CONTAINS a delivery word still collapses.
    ("Class Act: The Musical", "Class Act"),

    # The presenter patterns must not match INSIDE a word. Without a word
    # boundary "Tax Preparation Presentation" reduced to the core "ation",
    # which the containment tier found inside "English CONVERSATION Group" and
    # merged two unrelated BPL programs (event 26789). Likewise "Production"
    # only introduces a presenter when a colon follows it, or "FOSSS Guided
    # Music Production Session: Beginner" reduces to "Session" and fuses with
    # every other session listing. Regression 2026-08-17.
    ("Tax Preparation Presentation", "Tax Preparation Presentation"),
    ("Special Monday Movie Presentation: Origin", "Special Monday Movie Presentation"),
    ("FOSSS Guided Music Production Session: Beginner", "FOSSS Guided Music Production Session"),
    ("Digital Music Production Workshop", "Digital Music Production Workshop"),
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

    # Two unrelated NYPL programs sharing the house prefix "In-Person" / "In
    # Person" must NOT merge. `extract_core_title` used to reduce the subtitled
    # one to the core "In-Person", which the containment tier then found inside
    # ANY other title starting with the prefix; the 2026-06-24 umbrella-head gate
    # missed it because it only bit when BOTH names carried a colon, and NYPL
    # routinely writes the prefix without one. Regression 2026-08-17 — this
    # fused ~18 live library events across w3/w4.
    ("In-Person An Introduction to the Business Center and Its Resources",
     "In-Person: Searching Bloomberg: One-on-One", False),
    ("In Person: Friday Open Lab - Databases",
     "In Person - We Speak NYC English Conversation Classes", False),
    ("Money Matters [In-Person Financial Coaching with NYLAG at the Business Center]",
     "In-Person: Excel Open Lab", False),
    # ...but the SAME program across two crawls still merges, prefix noise and all.
    ("In-Person: Microsoft Excel for Beginners",
     "*In-Person: Microsoft Excel for Beginners", True),
    ("In-Person: Open Lab", "In Person - Open Lab", True),

    # Sibling class listings that differ only by skill level are different
    # classes. Six of seven stemmed tokens are shared, so the 75% asymmetric
    # containment tier fused them (regression 2026-08-17: this is what
    # over-merged the "We Speak NYC" English conversation classes).
    ("High Beginner Level English Conversation Classes: We Speak NYC",
     "Intermediate Level English Conversation Classes: We Speak NYC", False),
    ("Online: Beginner Level English Conversation Classes",
     "Online: Advanced Level English Conversation Classes", False),
    ("Mah Jongg Beginner (6-week workshop)", "Mah Jongg Intermediate (6-week workshop)", False),
    # ...but spelling variants of ONE level are the same class ("Computer
    # Basics" vs BPL's "Computer Basic"), and a level word on only one side is
    # the ordinary fuller-title shape.
    ("Computer Basics", "Computer Basic", True),
    ("West Coast Swing Beginner Boot Camp", "West Coast Swing for Beginners", True),
    ("Excel Class", "Excel Class: Advanced", True),

    # Garbage core titles from a word-internal presenter match must not fuse
    # unrelated programs (event 26789 / 124725, regression 2026-08-17).
    ("English Conversation Group", "Tax Preparation Presentation", False),
    ("Immigrant Job Support (one-on-one) Sessions",
     "FOSSS Guided Music Production Session: Beginner", False),
    # ...and a real presenter credit still collapses to the core title.
    ("Manhattan Theatre Club Presents The Monsters", "The Monsters", True),
    ("BAM Productions: Dance Performance", "Dance Performance", True),

    # A private booking must never merge into the public class it names. w1190
    # Painting Lounge publishes both in one feed, and the public title is a
    # literal substring of the private one, so every containment tier fused
    # them — crawl_event 1227898 landed on the public class 67670 and put a
    # stranger's party date on it. Regression 2026-08-17.
    ("Starry Night Over Empire State Building",
     "Private Party - Ryan W. / NYU - Starry Night Over Empire State Building", False),
    ("Indivisible Western Queens Meeting", "Private event (Indivisible Western Queens Meeting)", False),
    # ...but two private bookings are left to the ordinary rules.
    ("Private Event", "Private Events", True),

    # Spelled-out installment numbers are installment numbers (event 187715).
    ("First Five Years: Story and Play - Session One",
     "First Five Years: Story and Play - Session Two", False),
    ("Junk Journal Meetup at YTB! (Session One)", "Junk Journal Meetup at YTB! (Session 1)", True),

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

    # Different skill levels of one class series - should NOT merge
    # (regression 2026-08-17, NYPL/BPL "We Speak NYC" conversation classes).
    ("High Beginner Level English Conversation Classes: We Speak NYC",
     "Intermediate Level English Conversation Classes: We Speak NYC", True),
    ("Beginner Latin (Samba) with Tatiana Keegan", "Intermediate Latin (Samba) with Tatiana Keegan", True),
    ("Intro to Oil Painting - Summer '26", "Oil Painting - Intermediate/Advanced - Summer '26", True),
    ("Intro to Hip Hop (Absolute Beginner)", "Hip Hop (Advanced Beginner)", True),
    # Spelling variants of the same level - NOT a false positive
    ("Computer Basics", "Computer Basic", False),
    ("West Coast Swing Beginner Boot Camp", "West Coast Swing for Beginners", False),
    ("Advanced Beginner Ballet", "Beginner Ballet", False),
    # A level word on only ONE side is a fuller title, not a disagreement
    ("Excel Class", "Excel Class: Advanced", False),

    # Private booking vs the public class it names (w1190, 2026-08-17)
    ("Starry Night Over Empire State Building",
     "Private Party - Ryan W. / NYU - Starry Night Over Empire State Building", True),
    ("Private Party - Jennifer L. / Group Outting - Starry Night Over Manhattan",
     "Starry Night over Manhattan", True),
    ("Private Event", "Private Events", False),

    # Spelled-out installment numbers, canonicalized against digits
    ("First Five Years: Story and Play - Session One",
     "First Five Years: Story and Play - Session Two", True),
    ("Tots For Sculpture | Shifting Shapes: Session One",
     "Tots For Sculpture | Shifting Shapes: Session Two", True),
    ("NYU Golf at Stith Invitational - Round 3",
     "NYU Golf at Stith Invitational - Rounds One and Two", True),
    ("Junk Journal Meetup at YTB! (Session One)", "Junk Journal Meetup at YTB! (Session 1)", False),
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

    def test_gendered_guard_survives_apostrophe_deletion(self):
        """Men's vs Women's must stay distinct in every apostrophe spelling.

        Normalization deletes apostrophes, so "Men's" reaches this guard as the
        single token "mens". A guard matching only \\bmen\\b stops firing on the
        possessive form — which is the form these listings almost always use —
        and lets men's and women's fixtures merge into one event.
        """
        for men, women in [
            ("Men's Tennis Tournament", "Women's Tennis Tournament"),
            ("Mens Tennis Tournament", "Womens Tennis Tournament"),
            ("Men’s Tennis Tournament", "Women’s Tennis Tournament"),
            ("Men Tennis Tournament", "Women Tennis Tournament"),
        ]:
            with self.subTest(men=men, women=women):
                self.assertTrue(is_false_positive(men, women))
                self.assertFalse(are_names_similar(men, women))

    def test_gendered_guard_does_not_overreach(self):
        """The optional trailing s must not fire on unrelated words."""
        # "documentary"/"commencement" contain "men" but are not gendered events;
        # identical names must never be called a false positive.
        for name in ["Documentary Night", "Commencement Ceremony", "Menswear Pop-Up"]:
            with self.subTest(name=name):
                self.assertFalse(is_false_positive(name, name))

    def test_symmetry(self):
        """False positive detection should be symmetric."""
        test_pairs = [
            ("NYU Men's Basketball", "NYU Women's Basketball"),
            ("NYU Mens Basketball", "NYU Women's Basketball"),
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

    def test_single_word_name_must_lead_the_longer_name(self):
        """A lone significant word only matches when it LEADS the other name.

        Regression 2026-08-04: "Block by Block" normalizes to the word set
        {block} ("by" is a stop word, the set collapses the repeat), which is a
        subset of {brooklyn, botanic, garden, block, party}. The BBG exhibition
        (May 23 - Oct 25) merged into the one-evening Block Party and kept a
        finished event on the map for three extra months.

        The single-word subset itself is load-bearing (see _subset_match), so the
        guard is positional: a shared word buried mid-name is coincidence, a
        shared word at the front is a title.
        """
        buried = [  # shared word is NOT the longer name's first significant word
            ("Brooklyn Botanic Garden Block Party 2026", "Block by Block"),
            ("A Midsummer Night's Dream", "The Dream"),
            ("Queer Book Club Meetup", "Meetup #29"),
            ("Graduating Student Exhibition", "An Exhibit"),
            ("Boy Band Brunch with The Boy Band Project", "The the Band Band"),
            ("Ari Kiki", "The Kiki"),
            ("Board Game Cafe'", "Game On!"),
            ("Live Jazz at Nook", "Nook"),
        ]
        for name1, name2 in buried:
            with self.subTest(name1=name1, name2=name2):
                self.assertFalse(
                    are_names_similar(name1, name2),
                    f"Expected {name1!r} vs {name2!r} to NOT match "
                    f"(lone shared word is buried in the longer name)"
                )

    def test_leading_single_word_still_matches(self):
        """A bare headliner/title still picks up its fuller listing.

        These are the merges the guard above must not cost us — refusing every
        single-word subset would break all of them.
        """
        leading = [
            ("Yoga", "Yoga with Nicole and ShapeUp NYC"),
            ("SYTË, Von Stearns", "SYTË"),
            ("OGUZ", "OGUZ with Stan Christ & Guests"),
            ("QED: A conversation about math education", "QED"),
            ("Alok", "Alok presents Rave The World"),
            ("Tournaments", "Tournament Play"),          # stemmed side
            ("Baby & Me Storytime", "Baby and Me"),
            # Equal word sets: differ only in stop words, and too short for the
            # 5-char substring branch upstream to catch.
            ("The Moth", "Moth"),
        ]
        for name1, name2 in leading:
            with self.subTest(name1=name1, name2=name2):
                self.assertTrue(
                    are_names_similar(name1, name2),
                    f"Expected {name1!r} vs {name2!r} to match"
                )

    def test_single_word_rule_is_symmetric(self):
        """Argument order must not change the verdict.

        find_best_match calls are_names_similar(crawl_name, event_name), but the
        same pair is reached in both orders across the merge tiers.
        """
        pairs = [
            ("Brooklyn Botanic Garden Block Party 2026", "Block by Block"),
            ("Yoga", "Yoga with Nicole and ShapeUp NYC"),
            ("Graduating Student Exhibition", "An Exhibit"),
        ]
        for name1, name2 in pairs:
            with self.subTest(name1=name1, name2=name2):
                self.assertEqual(
                    are_names_similar(name1, name2),
                    are_names_similar(name2, name1),
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


class TestTrailingDateToken(unittest.TestCase):
    """A trailing MM/DD is the per-night discriminator on RA / posh.vip feeds.

    `get_significant_words` drops tokens shorter than 3 chars, so "08/02"
    normalized to "08 02" and both halves vanished — two listings differing ONLY
    by their date suffix looked identical (event 167515 swallowed 5 RA listings
    that already had rows of their own).
    """

    def test_slash_forms(self):
        self.assertEqual(merger._trailing_date_token("Joonbug Dusk 08/02"), "0802")
        self.assertEqual(merger._trailing_date_token("Joonbug Dusk 8/2"), "0802")
        self.assertEqual(merger._trailing_date_token("$5 Friday Family Fun 8/14"), "0814")
        self.assertEqual(merger._trailing_date_token("Ailey in London - 9/15/26"), "0915")
        self.assertEqual(merger._trailing_date_token("Ambient Music (2/3)"), "0203")
        self.assertEqual(merger._trailing_date_token("voguing 101 w/ zenith • (9/15)"), "0915")

    def test_padded_dot_form(self):
        self.assertEqual(merger._trailing_date_token("Lyra Rooftop Party 06.12.26"), "0612")
        self.assertEqual(merger._trailing_date_token("NYC Summer Boat Series - 05.09"), "0509")

    def test_hyphen_ranges_are_not_dates(self):
        """"Ages 12-16" is an age band, not December 16th — the hyphen form is
        deliberately not recognised."""
        self.assertIsNone(merger._trailing_date_token("Free Filmmaking Lab: Ages 12-16"))
        self.assertIsNone(merger._trailing_date_token("Junior Youth Modern (ages 11-12)"))

    def test_unpadded_dot_is_not_a_date(self):
        """Requiring MM.DD zero-padding keeps "Vol. 2.5" from reading as Feb 5."""
        self.assertIsNone(merger._trailing_date_token("Mixtape Vol. 2.5"))

    def test_embedded_date_is_part_of_the_title(self):
        self.assertIsNone(merger._trailing_date_token("9/11 Memorial Tour"))
        self.assertIsNone(merger._trailing_date_token("The 9/11 Museum After Hours"))

    def test_impossible_dates_rejected(self):
        self.assertIsNone(merger._trailing_date_token("Studio 13/40"))
        self.assertIsNone(merger._trailing_date_token("Room 24/99"))

    def test_bare_date_has_no_series_name(self):
        self.assertIsNone(merger._trailing_date_token("08/02"))


class TestTrailingDateSuffixMatching(unittest.TestCase):

    def test_different_date_suffixes_never_match(self):
        """The reproduced 167515 bug."""
        self.assertFalse(are_names_similar(
            "Joonbug Presents: Dusk Rooftop Party at The Crown 08/02",
            "Joonbug Presents: Dusk Rooftop Party at The Crown 08/16"))
        self.assertTrue(is_false_positive("Joonbug Dusk 08/02", "Joonbug Dusk 08/16"))

    def test_long_names_differing_only_by_date(self):
        """Word-overlap rules alone would still fuse these — 5 shared tokens push
        Jaccard over 0.7 — so the suffix has to be a hard false-positive."""
        self.assertFalse(are_names_similar(
            "DSA Running Club - Chinatown Office Loop (05/26/26)",
            "DSA Running Club - Chinatown Office Loop (06/02/26)"))

    def test_session_enumeration_is_a_discriminator(self):
        """"(1/3)" vs "(2/3)" are separate sessions of one class series."""
        self.assertFalse(are_names_similar("Ambient Music (2/3)", "Ambient Music (3/3)"))
        self.assertFalse(are_names_similar("Learn To Play Mahjong (1/3)",
                                           "Learn To Play Mahjong (3/3)"))

    def test_bare_series_name_still_matches_a_dated_listing(self):
        """Deliberate: only ONE side carries a suffix, which is the ordinary
        fuller-title shape. The merger still requires an overlapping date, so a
        bare name can only absorb the night it actually shares dates with."""
        self.assertTrue(are_names_similar("Joonbug Presents: Dusk Rooftop Party",
                                          "Joonbug Presents: Dusk Rooftop Party 08/02"))

    def test_identical_suffixes_still_match(self):
        self.assertTrue(are_names_similar("Joonbug Presents: Dusk Rooftop Party 08/02",
                                          "Joonbug Presents: Dusk Rooftop Party at The Crown 08/02"))

    def test_undated_names_are_unaffected(self):
        self.assertTrue(are_names_similar("The Monsters", "The Monsters: a Sibling Love Story"))
        self.assertFalse(are_names_similar("Jazz Night", "Comedy Brunch"))


class TestShortNumbersAreSignificant(unittest.TestCase):
    """A short number is the whole discriminator between two identical names.

    The 3-char floor dropped every token under 3 chars, so "Rugby Clinic (Ages
    3-6)" and "Rugby Clinic (Ages 7-12)" both reduced to {ages, clinic, rugby}
    and BPCA events 212806/215628 genuinely cross-merged (both rows ended up
    holding both cohorts' event_sources) and had to be repaired by hand.
    """

    def test_age_cohorts_are_distinct(self):
        """The reproduced 212806/215628 bug."""
        self.assertNotEqual(get_significant_words("Rugby Clinic (Ages 3-6)"),
                            get_significant_words("Rugby Clinic (Ages 7-12)"))
        self.assertFalse(are_names_similar("Rugby Clinic (Ages 3-6)",
                                           "Rugby Clinic (Ages 7-12)"))
        self.assertFalse(are_names_similar("Basketball Clinic (Ages 3-5)",
                                           "Basketball Clinic (Ages 6-10)"))
        self.assertFalse(are_names_similar("Children's Soccer (Ages 3-5)",
                                           "Children's Soccer (Ages 6-10)"))

    def test_numbered_weeks_levels_and_programs_are_distinct(self):
        self.assertFalse(are_names_similar("Swingiversity 201 [Week 1 of 8]",
                                           "Swingiversity 201 [Week 3 of 8]"))
        self.assertFalse(are_names_similar("Program 12 - Shorts", "Program 14 - Shorts"))
        self.assertFalse(are_names_similar(
            "CQ – Saturday – Level 1 – (4 – 8 years) – 12:00PM-12:45PM",
            "CQ – Saturday – Level 3 – (5 – 9 years) – 12:00PM-12:45PM"))

    def test_trailing_mm_dd_suffixes_stay_distinct(self):
        """Already guarded by `_trailing_date_token`; pinned here because the
        numeric tokens are now the second line of defence for the same shape."""
        self.assertFalse(are_names_similar("Joonbug Dusk 08/14", "Joonbug Dusk 08/02"))
        self.assertFalse(are_names_similar("Ambient Music (2/3)", "Ambient Music (1/3)"))

    def test_years_are_still_dropped(self):
        self.assertNotIn("2026", get_significant_words("Fall Festival 2026"))

    def test_stop_words_and_short_non_numbers_still_dropped(self):
        self.assertEqual(get_significant_words("A is the an"), set())


class TestShortNumbersDoNotBreakLegitimateMerges(unittest.TestCase):
    """The regressions the measurement hunted for — a name-rule change cuts both
    ways, and a legitimate pair differing only by a stray number must still merge.
    """

    def test_leading_bare_number_is_an_artifact_not_a_discriminator(self):
        """Partiful's discover page prefixes an RSVP count and NYC DSA's canvass
        feed a per-day count. "39 ⁂ release party ⁂" and "47 ⁂ release party ⁂"
        are the same Partiful URL on the same date."""
        self.assertTrue(are_names_similar("39 ⁂ release party ⁂", "47 ⁂ release party ⁂"))
        self.assertTrue(are_names_similar("4 Candidate Canvasses", "119 Candidate Canvasses"))
        self.assertTrue(are_names_similar(
            "56 Lotería Pride", "Lotería Pride Hosted by Iranipapi Sponsored by ASSET*"))
        self.assertTrue(are_names_similar("2 Day Balboa Crash Course/Fundamentals",
                                          "Balboa CRASH Course / Fundamentals w/ Sara-Sofia Rentas"))

    def test_fuller_title_with_an_extra_number_still_merges(self):
        """One-sided numbers break set containment, not the subset tier."""
        self.assertTrue(are_names_similar("Yoga", "Yoga 2"))
        self.assertTrue(are_names_similar("Level 2 Improv Class", "Level 2 Improv Class with Brook"))

    def test_zero_padding_is_not_a_different_number(self):
        self.assertTrue(are_names_similar(
            "Sunset Latin & Reggaeton Yacht Party - August 8",
            "Sunset Latin & Reggaeton Yacht Party at Skyport Marina | Aug 08"))

    def test_a_date_only_subtitle_is_not_distinguishing_content(self):
        """A bare series name must still absorb its own dated listing — the same
        call the `_trailing_date_token` comment makes."""
        self.assertTrue(are_names_similar("NEW VENUE! Reading Rhythms Lower Manhattan: July 27",
                                          "Reading Rhythms Lower Manhattan"))

    def test_a_shared_number_cannot_manufacture_a_match(self):
        """Numbers block a match but never create one: two acts on one night at
        one venue share the date tokens and nothing else."""
        self.assertFalse(are_names_similar("Sunday June 21 | the Alex Owen Quartet",
                                           "Sunday June 21 | DJ Dance"))
        self.assertFalse(are_names_similar(
            "FRI 8 & 9:30 - Igor Lumpert w/Drew Gress, Jeff Miles, Tom Rainey",
            "FRI 8 & 9:30 - Igor Lumpert w/Drew Gress, Damion Reid"))


class TestCohortLabelsAreSignificant(unittest.TestCase):
    """A short LETTER after a cohort keyword is a cohort label, not noise.

    Same shape as the short-number carve-out: NYC Parks publishes one row per
    class letter, so "... Learn to Swim Level 1 (Class C)", "(Class D)" and
    "(Class E)" reduced to byte-identical token lists and e203371 ended up
    holding the Class D and Class E permalinks. Measured 2026-08-19 over all
    32,856 distinct (event, source crawl_event) name pairs: 39 stop matching,
    0 newly match, and all 39 stops are distinct events.
    """

    def test_class_letter_reaches_the_comparison(self):
        self.assertIn("c", get_significant_words(
            "Session 3: Astoria Pool - Learn to Swim Level 1 (Class C)"))
        self.assertNotEqual(
            get_significant_words("Session 3: Astoria Pool - Learn to Swim Level 1 (Class C)"),
            get_significant_words("Session 3: Astoria Pool - Learn to Swim Level 1 (Class D)"))

    def test_distinct_cohorts_stop_merging(self):
        self.assertFalse(are_names_similar(
            "Session 1: Astoria Pool - Children's Learn to Swim Level 1 (Class A)",
            "Session 1: Astoria Pool - Parent and Tots Learn to Swim (Class B)"))
        self.assertFalse(are_names_similar("Kerboom Kidz- Grades K-2",
                                           "Kerboom Kidz- Grades 3-5"))
        self.assertFalse(are_names_similar("Layer the Walls Part II: Mid-Century",
                                           "Layer the Walls Part I"))

    def test_only_a_letter_or_roman_numeral_after_a_cohort_keyword_counts(self):
        """The keyword is the trigger, not the letter — a bare short letter is
        noise almost everywhere else."""
        self.assertNotIn("b", get_significant_words("Plan B Karaoke"))
        self.assertNotIn("of", get_significant_words("Day of the Dead Celebration"))
        # Connectors directly after a keyword are still connectors.
        self.assertNotIn("w", get_significant_words(
            "Solo Jazz & SWING Classes w/Margaret Batiuchok NYC"))
        self.assertNotIn("x", get_significant_words(
            "Marvin's First Day x Brooklyn Book Bodega"))

    def test_a_run_of_short_letters_is_mangled_text_not_a_label(self):
        """Measured regressions of the looser rule: a censored word split at its
        asterisk, and an ampersand joining two installments."""
        self.assertTrue(are_names_similar("HMU Academy: Navigating Group S*x",
                                          "HMU Acamdey: Navigating Group Sex"))
        self.assertTrue(are_names_similar("Intro to Microsoft Excel Part I & II",
                                          "Learn Microsoft Excel (2 Parts)"))

    def test_a_shared_cohort_label_cannot_manufacture_a_match(self):
        """Two different lectures in the same Part II must not fuse on the "ii"
        (`_drop_shared_weak_tokens`)."""
        self.assertFalse(are_names_similar(
            "Lecture Series - Glass in Context Part II: The Rise of the Artist",
            "Lecture Series - Glass in Context: Part II - From Venice to "
            "Industrialization and Beyond (February)"))

    def test_fuller_title_with_an_extra_cohort_label_still_merges(self):
        self.assertTrue(are_names_similar("Improv Level 2 Class",
                                          "Improv Level 2 Class (Section A)"))


class TestNormalizeUrlForIdentity(unittest.TestCase):

    def test_scheme_www_slash_and_fragment_are_dropped(self):
        self.assertEqual(
            merger.normalize_url_for_identity("https://www.Example.com/Events/Foo/#tickets"),
            "example.com/events/foo")
        self.assertEqual(merger.normalize_url_for_identity("http://example.com/events/foo"),
                         "example.com/events/foo")

    def test_tracking_params_dropped_but_real_query_kept(self):
        """The query is the identity on several platforms — Alamo Drafthouse's
        `?cinemaId=` is the ONLY thing separating its Brooklyn and Staten Island
        listings of the same film — so only tracking params may be stripped."""
        self.assertEqual(
            merger.normalize_url_for_identity("https://drafthouse.com/show/blow-out?cinemaId=2101&utm_source=x"),
            "drafthouse.com/show/blow-out?cinemaid=2101")
        self.assertNotEqual(
            merger.normalize_url_for_identity("https://drafthouse.com/show/blow-out?cinemaId=2101"),
            merger.normalize_url_for_identity("https://drafthouse.com/show/blow-out?cinemaId=2102"))

    def test_param_order_does_not_split_one_event(self):
        self.assertEqual(
            merger.normalize_url_for_identity("https://x.com/e?b=2&a=1"),
            merger.normalize_url_for_identity("https://x.com/e?a=1&b=2"))

    def test_empty(self):
        self.assertEqual(merger.normalize_url_for_identity(None), "")
        self.assertEqual(merger.normalize_url_for_identity(""), "")

    def test_trailing_occurrence_date_is_dropped(self):
        """Tribe mints one permalink per DATE of the same event.

        Industry City's "Guided Brewery Tour and Sake Tasting" ran as two live
        rows — one holding the August dates, one the September/November ones —
        purely because these variants never met on a key.
        """
        base = "industrycity.com/event/guided-brewery-tour-and-sake-tasting"
        for url in (
            "https://industrycity.com/event/guided-brewery-tour-and-sake-tasting/2026-08-23/",
            "https://industrycity.com/event/guided-brewery-tour-and-sake-tasting/2026-11-01/",
            "https://industrycity.com/event/guided-brewery-tour-and-sake-tasting/",
        ):
            self.assertEqual(merger.normalize_url_for_identity(url), base, url)

    def test_trailing_datetime_variant_is_dropped(self):
        self.assertEqual(
            merger.normalize_url_for_identity("https://x.com/e/summer-fest/2026-08-23T19:00/"),
            "x.com/e/summer-fest")

    def test_per_day_listing_index_is_left_intact(self):
        """`/events/2026-08-23/` is a per-day INDEX, not one event's permalink.

        Collapsing it would hand every event on the site a single shared key.
        The listing-segment guard is what separates it from an event slug.
        """
        for url, expected in (
            ("https://x.com/events/2026-08-23/", "x.com/events/2026-08-23"),
            ("https://x.com/calendar/2026-08-23/", "x.com/calendar/2026-08-23"),
            ("https://x.com/e/2026-08-23", "x.com/e/2026-08-23"),
        ):
            self.assertEqual(merger.normalize_url_for_identity(url), expected, url)

    def test_date_in_a_query_string_is_not_stripped(self):
        """A query-string date may be doing real routing work."""
        self.assertEqual(
            merger.normalize_url_for_identity("https://x.com/e/show?date=2026-08-23"),
            "x.com/e/show?date=2026-08-23")

    def test_mid_path_date_is_not_stripped(self):
        """Only a TRAILING date segment is per-occurrence; a WordPress-style
        mid-path date is part of the permalink itself."""
        self.assertEqual(
            merger.normalize_url_for_identity("https://x.com/blog/2026/08/23/post"),
            "x.com/blog/2026/08/23/post")

    def test_distinct_slugs_still_differ(self):
        self.assertNotEqual(
            merger.normalize_url_for_identity("https://x.com/event/jazz-night/2026-08-23/"),
            merger.normalize_url_for_identity("https://x.com/event/blues-night/2026-08-23/"))

    def test_luma_short_host_folds_into_the_canonical_one(self):
        """`lu.ma/<slug>` 301s to `luma.com/<slug>` — one page, two strings.

        The Luma calendar injector emits `lu.ma` while embeds and cross-listing
        sites emit `luma.com`, so 3 of the 10 Luma slug collisions measured on
        2026-08-17 were invisible to this tier (e.g. Fabrik DUMBO's
        `luma.com/84fec4e2` vs Unmuted's `lu.ma/84fec4e2`)."""
        canonical = merger.normalize_url_for_identity("https://luma.com/84fec4e2")
        self.assertEqual(canonical, "luma.com/84fec4e2")
        for variant in ("https://lu.ma/84fec4e2",
                        "http://lu.ma/84fec4e2/",
                        "https://www.lu.ma/84fec4e2",
                        "https://LU.MA/84fec4e2#tickets"):
            with self.subTest(variant=variant):
                self.assertEqual(merger.normalize_url_for_identity(variant), canonical)

    def test_luma_api_host_is_not_folded(self):
        """api.lu.ma is the JSON endpoint, a different resource from the page."""
        self.assertEqual(
            merger.normalize_url_for_identity("https://api.lu.ma/url?url=pubkey-jj3u"),
            "api.lu.ma/url?url=pubkey-jj3u")
        self.assertNotEqual(
            merger.normalize_url_for_identity("https://api.lu.ma/url?url=pubkey-jj3u"),
            merger.normalize_url_for_identity("https://luma.com/url?url=pubkey-jj3u"))

    def test_lookalike_hosts_are_not_folded(self):
        for url in ("https://notlu.ma/84fec4e2", "https://lu.market/84fec4e2"):
            with self.subTest(url=url):
                self.assertNotIn("luma.com", merger.normalize_url_for_identity(url))


class TestLocationsWithin(unittest.TestCase):
    COORDS = {
        1: ('40.730000', '-73.997000'),   # Father Demo Square
        2: ('40.733000', '-74.002000'),   # Greenwich Village, ~0.5 km away
        3: ('40.660000', '-73.969000'),   # Prospect Park, ~8 km away
        4: (None, None),
    }

    def test_same_or_unknown_is_compatible(self):
        self.assertTrue(merger._locations_within(1, 1, self.COORDS))
        self.assertTrue(merger._locations_within(None, 3, self.COORDS))
        self.assertTrue(merger._locations_within(3, None, self.COORDS))
        self.assertTrue(merger._locations_within(1, 4, self.COORDS))

    def test_near_and_far(self):
        self.assertTrue(merger._locations_within(1, 2, self.COORDS))
        self.assertFalse(merger._locations_within(1, 3, self.COORDS))


class TestUrlIdentityTier(unittest.TestCase):
    """The tier is exempt from the merger's cross-location guard, so every other
    signal is held at maximum strictness. Each test removes exactly one."""

    COORDS = TestLocationsWithin.COORDS
    URL = "https://www.boweryboyswalks.com/walking-tours/greenwich-village-history-walking-tour"
    KEY = ("boweryboyswalks.com/walking-tours/greenwich-village-history-walking-tour")
    SLOTS = {("2026-08-12", "2pm")}

    def _index(self, name="The Hidden History of Greenwich Village", location_id=1,
               slots=None, event_id=100):
        return {(495, self.KEY): [{
            'id': event_id, 'name': name, 'location_id': location_id,
            'slots': slots if slots is not None else set(self.SLOTS),
        }]}

    def _match(self, index=None, counts=None, listing=None, name="The Hidden History of Greenwich Village",
               url=None, website_id=495, location_id=2, slots=None):
        return merger._match_by_url_identity(
            name, url if url is not None else self.URL, website_id, location_id,
            slots if slots is not None else set(self.SLOTS),
            index if index is not None else self._index(),
            counts if counts is not None else {(495, self.KEY): 1},
            listing if listing is not None else set(),
            self.COORDS,
        )

    def test_matches_across_a_location_disagreement(self):
        """The whole point: the listing page said "Greenwich Village" and the
        detail page said "Father Demo Square", so no other tier survives the
        cross-location guard and a duplicate row is created and then archived."""
        self.assertEqual(self._match(), 100)

    def test_listing_url_is_refused(self):
        self.assertIsNone(self._match(listing={(495, self.KEY)}))

    def test_url_carrying_many_names_is_refused(self):
        """Painting Lounge's rezclick root carries 190 distinct event names
        across two real studios; without the cap the tier fuses the branches."""
        self.assertIsNone(self._match(counts={(495, self.KEY): 3}))

    def test_fuzzy_name_is_refused(self):
        self.assertIsNone(self._match(name="The Hidden History of Greenwich Village Food Tour"))

    def test_exact_name_ignores_punctuation_and_case(self):
        self.assertEqual(self._match(name="the hidden history of GREENWICH village!"), 100)

    def test_shared_date_without_a_shared_slot_is_refused(self):
        """Two showtimes of one film on one day share a date but not a slot."""
        self.assertIsNone(self._match(slots={("2026-08-12", "7pm")}))

    def test_distant_venue_is_refused(self):
        """A run club that meets in two parks (w4860) publishes one club page,
        one name and one weekly slot for both meeting points."""
        self.assertIsNone(self._match(index=self._index(location_id=3)))

    def test_unlocated_crawl_event_is_allowed(self):
        self.assertEqual(self._match(location_id=None), 100)

    def test_other_website_does_not_match(self):
        self.assertIsNone(self._match(website_id=496))

    def test_no_slots_means_no_match(self):
        """Dateless crawl_events are out of scope — they carry no schedule to
        corroborate a cross-location merge."""
        self.assertIsNone(self._match(slots=set()))

    def test_same_location_candidate_beats_a_nearer_lower_id(self):
        """Two branch rows can both end up holding one branch's URL; the branch
        the crawl_event actually names must win over the lowest id."""
        index = {(495, self.KEY): [
            {'id': 100, 'name': 'X', 'location_id': 2, 'slots': set(self.SLOTS)},
            {'id': 200, 'name': 'X', 'location_id': 1, 'slots': set(self.SLOTS)},
        ]}
        self.assertEqual(self._match(index=index, name='X', location_id=1), 200)
        self.assertEqual(self._match(index=index, name='X', location_id=2), 100)

    def test_missing_url_or_website(self):
        self.assertIsNone(self._match(url=""))
        self.assertIsNone(self._match(website_id=None))


class TestDatelessNeverCreatesAnEvent(unittest.TestCase):
    """A dateless crawl_event carries no occurrences, so any event it creates has
    ZERO `event_occurrences` rows — invisible on the map (the exporter needs a
    date) yet still absorbing `event_sources`, participating in dedup, and
    counting against archival. `merge_crawl_events` must therefore reach its
    create-new branch only with `dateless` false.

    Two paths inside the function can leave a dateless crawl_event unmatched: the
    dateless matcher returning None (guarded since the matcher was added), and the
    global cross-location guard nulling a match the matcher DID make (unguarded
    until 2026-08-13 — that hole created 834 zero-occurrence rows). The check is
    structural because the create-new branch sits ~600 lines into a DB-driven loop
    with no unit-test seam; what matters is that BOTH `continue` guards survive a
    refactor of the matching tiers.
    """

    def _merge_source(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(merger))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'merge_crawl_events':
                return node
        self.fail("merge_crawl_events not found in merger.py")

    @staticmethod
    def _is_bare_continue(if_node):
        import ast
        return len(if_node.body) == 1 and isinstance(if_node.body[0], ast.Continue)

    def test_guard_rejected_dateless_match_does_not_fall_through(self):
        """The cross-location guard nulls `matched_event_id` AFTER the dateless
        matcher succeeded. Without a top-level `if dateless and matched_event_id
        is None: continue`, that crawl_event lands in the create-new branch."""
        import ast
        found = any(
            isinstance(node, ast.If)
            and self._is_bare_continue(node)
            and {'dateless', 'matched_event_id'} <= {
                n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            for node in ast.walk(self._merge_source())
        )
        self.assertTrue(found,
            "merge_crawl_events lost the `if dateless and matched_event_id is None: "
            "continue` guard — a dateless crawl_event whose match is rejected by the "
            "cross-location guard will create a zero-occurrence event again."
        )

    def test_the_dateless_no_match_guard_also_survives(self):
        """The other hole: the dateless matcher itself returning None. That guard
        lives INSIDE `if dateless:` so it does not name `dateless` in its own test
        — match on the nesting, or this silently passes on the unrelated
        `not valid_occurrences and not dateless` skip a few lines earlier."""
        import ast
        dateless_blocks = [
            node for node in ast.walk(self._merge_source())
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name) and node.test.id == 'dateless'
        ]
        self.assertTrue(dateless_blocks, "the `if dateless:` matching block is gone")
        self.assertTrue(
            any(self._is_bare_continue(inner)
                for block in dateless_blocks
                for inner in ast.walk(block) if isinstance(inner, ast.If)),
            "the `if dateless:` block no longer short-circuits when "
            "_match_dateless_crawl_event returns None."
        )


class TestResolveStaleLocationName(unittest.TestCase):
    """`events.location_name` is written from `locations.name` on event CREATION
    but never refreshed on merge, so a later `location_id` correction leaves the
    label frozen at the PREVIOUS location's canonical name.

    Every case below is drawn from the live scan run before the fix shipped:
    the REWRITE cases are real stale rows, the SKIP cases are the coincidence
    class that killed the naive "always refresh from locations.name" version —
    a source that genuinely wrote a neighborhood generic's name."""

    LOCATIONS = {
        2425: 'Flatbush',
        2505: 'Park Slope',
        2385: 'Chelsea',
        4727: 'Kadampa Meditation Center NYC',
        7390: 'Trinity Lutheran Church of Manhattan',
        100: 'Flatbush Library',
        101: 'BPL Park Slope',
        102: 'Kadampa Meditation Center NYC',
        103: 'The Sheen Center for Thought & Culture',
        104: 'Trinity Lutheran Church of Staten Island',
    }

    def resolve(self, stored, current_loc_id, source_loc_ids, source_raw_names):
        return merger.resolve_stale_location_name(
            stored, current_loc_id, self.LOCATIONS, source_loc_ids, source_raw_names
        )

    # ── rewrite: the label is our own copy of a previous location's name ──

    def test_rewrites_label_frozen_at_previous_location(self):
        """ev 144834: pinned to Flatbush Library, still labelled 'Flatbush'
        because the first crawl_event resolved to the neighborhood row 2425.
        No source ever wrote the bare word."""
        self.assertEqual(
            self.resolve('Flatbush', 100, [2425, 100], ['Flatbush Library']),
            'Flatbush Library',
        )

    def test_rewrites_park_slope_label(self):
        """ev 192836 / 198467 — same shape via BPL's branch pages."""
        self.assertEqual(
            self.resolve('Park Slope', 101, [2505], ['Park Slope Library']),
            'BPL Park Slope',
        )

    def test_rewrites_when_previous_location_was_a_sibling_venue(self):
        """ev 193577: an alt-name hijack was repaired by moving location_id from
        the Manhattan church to the Staten Island one; the label never moved."""
        self.assertEqual(
            self.resolve('Trinity Lutheran Church of Manhattan', 104, [7390],
                         ['Trinity Evangelical Lutheran Church, Staten Island']),
            'Trinity Lutheran Church of Staten Island',
        )

    def test_rewrites_umbrella_label_after_branch_split(self):
        """ev 139214: branch classes split off the KMC umbrella row 4727."""
        self.assertEqual(
            self.resolve('Kadampa Meditation Center NYC', 103, [4727],
                         ['KMC NYC Main Center Chelsea']),
            'The Sheen Center for Thought & Culture',
        )

    def test_comparison_ignores_case_and_surrounding_whitespace(self):
        self.assertEqual(
            self.resolve('  flatbush  ', 100, [2425], ['Flatbush Library']),
            'Flatbush Library',
        )

    # ── skip: the coincidence class the naive fix would have destroyed ──

    def test_skips_when_a_source_wrote_the_label_itself(self):
        """The 3464-row majority: the extractor genuinely emitted 'Chelsea'.
        That is the source's label, not our copy — it must stand even though it
        also happens to be the name of location row 2385."""
        self.assertIsNone(
            self.resolve('Chelsea', 102, [2385, 102], ['Chelsea', 'Kadampa Meditation Center NYC'])
        )

    def test_skips_when_only_the_incoming_crawl_event_wrote_the_label(self):
        """The corroborating source can be THIS merge's crawl_event."""
        self.assertIsNone(self.resolve('Park Slope', 101, [2505], ['Park Slope']))

    def test_skips_when_label_matches_no_location_the_event_resolved_to(self):
        """A label equal to some unrelated location row's name is not evidence
        that WE wrote it — the task's proposed global 'equals some other row'
        test alone would have rewritten 3874 rows on this signal."""
        self.assertIsNone(self.resolve('Chelsea', 100, [2425], ['Flatbush Library']))

    def test_skips_when_label_already_matches_the_current_location(self):
        self.assertIsNone(self.resolve('Flatbush Library', 100, [2425], ['Flatbush Library']))

    def test_skips_free_text_labels(self):
        """Anything that is not verbatim some location row's name is a source
        string by construction and is never touched."""
        self.assertIsNone(
            self.resolve('Flatbush Library, Large Meeting Room', 100, [2425], ['Flatbush Library'])
        )

    def test_skips_unmapped_events_and_placeholders(self):
        self.assertIsNone(self.resolve('Flatbush', None, [2425], []))
        self.assertIsNone(self.resolve('Not specified', 100, [2425], []))
        self.assertIsNone(self.resolve('', 100, [2425], []))
        self.assertIsNone(self.resolve(None, 100, [2425], []))

    def test_skips_when_current_location_id_is_unknown(self):
        self.assertIsNone(self.resolve('Flatbush', 999999, [2425], []))

    def test_tolerates_null_source_location_ids(self):
        """crawl_events that never resolved a venue carry location_id NULL."""
        self.assertIsNone(self.resolve('Flatbush', 100, [None, None], ['Flatbush Library']))


class TestMergeRefreshesStaleLocationName(unittest.TestCase):
    """Structural pin: the merge path must actually call the discriminator, and
    must not regress to refreshing `location_name` unconditionally."""

    def _merge_source(self):
        import ast
        import inspect
        return ast.parse(inspect.getsource(merger.merge_crawl_events))

    def test_merge_path_calls_resolve_stale_location_name(self):
        import ast
        calls = [
            node for node in ast.walk(self._merge_source())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'resolve_stale_location_name'
        ]
        self.assertTrue(
            calls,
            "merge_crawl_events no longer consults resolve_stale_location_name — "
            "a corrected location_id will freeze location_name again."
        )


class TestSiblingSubtitleVeto(unittest.TestCase):
    """Equal series head + word-disjoint subtitles = sibling sub-events; the
    containment tiers must not let the shared head outvote the subtitle.
    Dominant shape of the 2026-08-19 URL contamination (21 of 37 wrong rows).
    Measured 2026-08-27 (.scratch/nametier_measure.py): 498 pairs stop, 0 new."""

    def test_distinct_program_categories_do_not_match(self):
        self.assertFalse(merger.are_names_similar(
            '2026 Oscar Nominated Shorts: Animation',
            '2026 Oscar Nominated Shorts: Documentary'))

    def test_distinct_playgrounds_do_not_match(self):
        self.assertFalse(merger.are_names_similar(
            'Kids in Motion: Flynn Playground',
            'Kids in Motion: Willis Playground'))

    def test_distinct_author_talks_do_not_match(self):
        self.assertFalse(merger.are_names_similar(
            '67th Street Library Comic Book Festival: Author Talk with Kevin Alvir',
            '67th Street Library Comic Book Festival: Author Talk with Adam Szym'))

    def test_muhlenberg_cinema_screenings_do_not_match(self):
        self.assertFalse(merger.are_names_similar(
            "Muhlenberg Cinema Club: 'Rocky'",
            "Muhlenberg Cinema Club: 'Cat on a Hot Tin Roof'"))

    def test_abbreviated_lineup_still_matches_full_spelling(self):
        # Word-level corroboration: subtitle subset (abbreviated vs full names)
        self.assertTrue(merger.are_names_similar(
            '30th Showcase Reading: Khraibani, Matuk, Peñaloza, & Salas Rivera',
            '30th Showcase Reading: Sahar Khraibani, Farid Matuk, Michelle '
            'Peñaloza, and Roque Raquel Salas Rivera'))

    def test_expanded_lineup_still_matches(self):
        self.assertTrue(merger.are_names_similar(
            '4 Years of Paragon: Joey Beltram, WTCHCRFT, LISAS+',
            '4 Years of Paragon: Joey Beltram, WTCHCRFT, Guillotine, '
            'Dream + Andi b2b Arvin T, LISAS'))

    def test_formatting_twin_still_matches_via_jaccard(self):
        # "&" vs "and" twins judge on whole names in the symmetric tiers,
        # which the veto leaves on.
        self.assertTrue(merger.are_names_similar(
            '30th Showcase Reading: Almallah, Shunnarah, Tbakhi, & Tuffaha',
            '30th Showcase Reading: Almallah, Shunnarah, Tbakhi, and Tuffaha'))


class BareClockTwinTests(unittest.TestCase):
    """A meridiem-less showtime must collapse into its own am/pm twin.

    `processor._standardize_time` leaves a bare 1-11 o'clock alone on purpose
    (inferring PM from '7:00' is the documented trap), so one site can emit the
    same screening as both '6:50' and '6:50pm' and the two spellings hash to
    different dedupe keys. Film Forum's "Late Fame" carried three such twin rows.
    `_merge_occurrences_into_event` now treats the bare form as strictly less
    specific — in BOTH arrival orders — without ever guessing a meridiem.
    """

    class FakeCursor:
        """Minimal event_occurrences store for _merge_occurrences_into_event."""

        def __init__(self, rows):
            # rows: (start_date, start_time, end_date, end_time)
            self.rows = list(rows)
            self._result = []

        def execute(self, sql, params=None):
            s = ' '.join(sql.split())
            if s.startswith('SELECT start_date, start_time, end_date, end_time'):
                self._result = [(sd, st, ed, et, i)
                                for i, (sd, st, ed, et) in enumerate(self.rows)]
            elif s.startswith('INSERT INTO event_occurrences'):
                _eid, sd, st, ed, et, _so = params
                self.rows.append((sd, st, ed, et))
                self._result = []
            elif s.startswith('DELETE FROM event_occurrences'):
                if 'end_date IS NULL' in s:
                    _eid, sd, st = params
                    ed = None
                else:
                    _eid, sd, st, ed = params
                if 'start_time IS NULL OR start_time' in s:
                    self.rows = [r for r in self.rows
                                 if not (r[0] == sd and not r[1] and r[2] == ed)]
                else:
                    self.rows = [r for r in self.rows
                                 if not (r[0] == sd and r[1] == st and r[2] == ed)]
                self._result = []
            elif s.startswith('UPDATE event_occurrences SET end_time'):
                self._result = []
            else:  # pragma: no cover
                raise AssertionError('unexpected SQL: ' + s)

        def fetchall(self):
            return self._result

        def fetchone(self):
            return self._result[0] if self._result else None

    def _merge(self, existing, incoming):
        cursor = self.FakeCursor(existing)
        merger._merge_occurrences_into_event(cursor, 1, incoming)
        return sorted(cursor.rows, key=lambda r: (r[0], r[1]))

    D = date(2026, 8, 7)

    def test_bare_time_loses_to_its_existing_qualified_twin(self):
        rows = self._merge([(self.D, '6:50pm', None, '')],
                           [(self.D, '6:50', None, '')])
        self.assertEqual(rows, [(self.D, '6:50pm', None, '')])

    def test_qualified_time_evicts_an_existing_bare_twin(self):
        rows = self._merge([(self.D, '6:50', None, '')],
                           [(self.D, '6:50pm', None, '')])
        self.assertEqual(rows, [(self.D, '6:50pm', None, '')])

    def test_am_twin_collapses_too(self):
        """No meridiem is inferred — either qualified spelling absorbs the bare one."""
        rows = self._merge([(self.D, '2:25am', None, '')],
                           [(self.D, '2:25', None, '')])
        self.assertEqual(rows, [(self.D, '2:25am', None, '')])

    def test_whole_hour_forms_collapse(self):
        # '7' and '7:00' both normalize through _standardize_time to bare forms
        # of the same clock face as '7pm'.
        self.assertEqual(self._merge([(self.D, '7pm', None, '')],
                                     [(self.D, '7', None, '')]),
                         [(self.D, '7pm', None, '')])
        self.assertEqual(self._merge([(self.D, '7:00', None, '')],
                                     [(self.D, '7pm', None, '')]),
                         [(self.D, '7pm', None, '')])

    def test_a_different_clock_face_is_not_collapsed(self):
        rows = self._merge([(self.D, '6:50pm', None, '')],
                           [(self.D, '7:50', None, '')])
        self.assertEqual(rows, [(self.D, '6:50pm', None, ''),
                                (self.D, '7:50', None, '')])

    def test_bare_time_with_no_twin_is_stored_unchanged(self):
        """The fix must never invent a meridiem."""
        rows = self._merge([], [(self.D, '6:50', None, '')])
        self.assertEqual(rows, [(self.D, '6:50', None, '')])

    def test_twelve_and_24_hour_values_are_untouched(self):
        # '12pm'/'12am' are unambiguous and already canonical; a bare '12'
        # normalizes to '12pm' upstream, so no bare twin can exist for them.
        self.assertEqual(merger._bare_clock_twins('12'), ())
        self.assertEqual(merger._bare_clock_twins('19:30'), ())
        self.assertEqual(merger._qualified_clock_bare_forms('12pm'), ())

    def test_helper_forms(self):
        self.assertEqual(merger._bare_clock_twins('6:50'), ('6:50am', '6:50pm'))
        self.assertEqual(merger._bare_clock_twins('7'), ('7am', '7pm'))
        self.assertEqual(merger._bare_clock_twins('7:00'), ('7am', '7pm'))
        self.assertEqual(merger._qualified_clock_bare_forms('6:50pm'), ('6:50',))
        self.assertEqual(merger._qualified_clock_bare_forms('7am'), ('7', '7:00'))


EXHIBITION = 'Machel Montano: Journey of a Soca King'
TALK = ('Journey of a Soca King: Elizabeth \u201cLady\u201d Montano on Machel '
        'Montano\u2019s Lyrics with Dr. Ottley & Melissa Noel')
TALK_RECRAWL = ('Journey of a Soca King: Elizabeth \u201cLady\u201d Montano on Machel '
                'Montano\u2019s Lyrics with Dr. Rudolph Ottley & Melissa Noel')


class TestContainmentMatchShape(unittest.TestCase):
    """`_is_containment_match` — the name half of the sibling-listing veto."""

    def test_umbrella_inside_subevent_title_is_containment_match(self):
        # BPL e220817: the exhibition's five significant words are a strict
        # subset of the talk's, and the talk's extra words are not a suffix of
        # a shared leading run.
        self.assertTrue(merger._is_containment_match(EXHIBITION, TALK))

    def test_leading_prefix_is_a_fuller_title_not_containment(self):
        # "<name>" vs "<name> + more" is the same event spelled out — the same
        # exemption `_bare_name_vs_distinct_subtitle` makes.
        self.assertFalse(merger._is_containment_match(
            'Matinee with Ry Daddy',
            'Matinee w/ Ry Daddy ft: Daniel Simonsen, Henry Sir, Alingon Mitra'))

    def test_too_few_extra_words_is_not_a_containment_match(self):
        # A one- or two-word difference is ordinary title drift, not an umbrella.
        self.assertFalse(merger._is_containment_match('Craft Circle',
                                                      'Virtual Crafting Circle'))
        self.assertFalse(merger._is_containment_match(TALK, TALK_RECRAWL))

    def test_near_subset_still_counts(self):
        # The threshold mirrors the 0.75 asymmetric-containment tier: a sibling
        # talk that drops one of the umbrella's words is still reachable by it.
        # (BPL e220820, the second sub-event the strict-subset form missed.)
        self.assertTrue(merger._is_containment_match(
            EXHIBITION,
            'Journey of a Soca King Exhibition Conversation with Elizabeth '
            '\u201cLady\u201d Montano on King of Soca (Book)'))

    def test_names_that_barely_overlap_are_not_a_containment_match(self):
        # Below 0.75 no containment tier could have fused them anyway.
        self.assertFalse(merger._is_containment_match(
            'C-41 Developing Workshop', 'Advanced Darkroom Printing Intensive'))


class TestSiblingListingVeto(unittest.TestCase):
    """An umbrella listing must not fuse onto a sub-event inside it.

    Reference case (2026-08-30): BPL w74 published the exhibition "Machel
    Montano: Journey of a Soca King" (8/22\u20139/12) and, in the same crawl, the
    talk "Journey of a Soca King: Elizabeth 'Lady' Montano ..." (8/27 7pm). The
    exhibition's words are a strict subset of the talk's, so both `_subset_match`
    and the 0.75 asymmetric-containment tier fuse them and the three-week span
    lands on the one-evening talk (e220817).
    """

    WEBSITE = 74
    EXHIBITION_URL = 'bklynlibrary.org/exhibitions/machel-montano-journey'
    TALK_URL = ('bklynlibrary.org/calendar/journey-soca-king-central-library-'
                'dweck-20260827-0700pm')

    def setUp(self):
        self.candidate = {'id': 220817, 'name': TALK, 'website_id': self.WEBSITE}
        self.candidate_slots = {('2026-08-27', '7pm')}
        self.crawl_slots = {('2026-08-22', '')}
        # The same extraction pass also emitted the talk itself.
        self.roster = [(1292759, TALK_RECRAWL), (1292787, EXHIBITION)]
        self.event_url_keys = {220817: {self.TALK_URL}}
        self.listing_url_keys = {(self.WEBSITE, 'bklynlibrary.org/calendar')}
        self.url_key_name_counts = {
            (self.WEBSITE, self.EXHIBITION_URL): 1,
            (self.WEBSITE, self.TALK_URL): 1,
        }

    def _veto(self, name=EXHIBITION, url_key=None, website_id=None,
              crawl_slots=None, roster=None, event_url_keys=None,
              candidate=None, candidate_slots=None):
        return merger._sibling_listing_veto(
            name,
            self.EXHIBITION_URL if url_key is None else url_key,
            self.WEBSITE if website_id is None else website_id,
            self.crawl_slots if crawl_slots is None else crawl_slots,
            1292787,
            self.candidate if candidate is None else candidate,
            self.candidate_slots if candidate_slots is None else candidate_slots,
            self.roster if roster is None else roster,
            self.listing_url_keys,
            self.url_key_name_counts,
            self.event_url_keys if event_url_keys is None else event_url_keys,
        )

    def test_names_still_look_similar_to_the_name_tiers(self):
        """The veto is needed precisely because no name tier rejects this pair."""
        self.assertTrue(are_names_similar(EXHIBITION, TALK))

    def test_exhibition_does_not_fuse_onto_the_talk(self):
        self.assertTrue(self._veto())

    def test_shared_occurrence_slot_wins(self):
        """A shared date+time is same-eventness whatever the names say."""
        self.assertFalse(self._veto(crawl_slots={('2026-08-27', '7pm')}))

    def test_no_clean_sibling_in_the_same_extraction_means_no_veto(self):
        """Without a row that already speaks for the event, this row may BE it."""
        self.assertFalse(self._veto(roster=[(1292787, EXHIBITION)]))

    def test_shared_permalink_means_no_veto(self):
        self.assertFalse(self._veto(url_key=self.TALK_URL))

    def test_event_without_its_own_permalink_is_not_vetoed(self):
        self.assertFalse(self._veto(event_url_keys={}))

    def test_listing_page_url_is_not_evidence(self):
        self.assertFalse(self._veto(url_key='bklynlibrary.org/calendar'))

    def test_relative_legacy_url_is_not_evidence(self):
        """A host-less key can never equal the absolute spelling of one page."""
        self.assertFalse(self._veto(url_key='/exhibitions/machel-montano-journey'))

    def test_url_carrying_many_names_is_not_evidence(self):
        counts = dict(self.url_key_name_counts)
        counts[(self.WEBSITE, self.EXHIBITION_URL)] = 40
        self.url_key_name_counts = counts
        self.assertFalse(self._veto())

    def test_cross_website_difference_is_free_and_never_vetoes(self):
        """Two sites always spell a URL differently; that is not evidence."""
        other = dict(self.candidate, website_id=999)
        self.assertFalse(self._veto(candidate=other))

    def test_fuller_title_of_the_same_event_still_merges(self):
        """The re-crawled talk (one extra word, leading run shared) is unaffected."""
        self.assertFalse(self._veto(name=TALK_RECRAWL, url_key=self.TALK_URL))



if __name__ == "__main__":
    unittest.main()
