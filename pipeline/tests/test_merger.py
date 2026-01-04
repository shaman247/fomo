"""Tests for merger.py deduplication utilities."""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merger import normalize_name_for_dedup, stem_word, get_significant_words, are_names_similar, is_false_positive, extract_core_title

# Test cases for normalize_name_for_dedup: (input, expected_output)
NORMALIZE_TEST_CASES = [
    # Basic lowercasing and whitespace normalization
    ("Hello World", "hello world"),
    ("  Multiple   Spaces  ", "multiple spaces"),

    # Punctuation removal
    ("Event - With Dashes", "event with dashes"),
    ("What's Happening?", "whats happening"),

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

    # Should NOT match - different events
    ("Weekly Thursday Karaoke", "Friday Night Karaoke", False),
    ("Tim Berne Concert", "John Smith Concert", False),
    ("Jazz Festival", "Rock Festival", False),
    ("Art Show", "Food Festival", False),
    ("Morning Yoga", "Evening Dance", False),

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
]


class TestNormalizeNameForDedup(unittest.TestCase):
    """Tests for the normalize_name_for_dedup function."""

    def test_normalize_cases(self):
        """Test all normalization cases."""
        for input_str, expected in NORMALIZE_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(normalize_name_for_dedup(input_str), expected)


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
        """Words shorter than 3 characters should be filtered out."""
        result = get_significant_words("A is the an")
        self.assertEqual(result, {"the"})

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


if __name__ == "__main__":
    unittest.main()
