"""Tests for processor.py text utilities."""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import create_short_name, normalize_event_name_caps, strip_leading_emoji

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


if __name__ == "__main__":
    unittest.main()
