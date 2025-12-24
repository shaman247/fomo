"""Tests for process_responses.py"""

import unittest
from process_responses import _create_short_name

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
    """Tests for the _create_short_name function."""

    def test_short_name_cases(self):
        """Test all short name transformation cases."""
        for input_str, expected in SHORT_NAME_TEST_CASES:
            with self.subTest(input=input_str):
                self.assertEqual(_create_short_name(input_str), expected)

    def test_none_input(self):
        """None input should return None."""
        self.assertIsNone(_create_short_name(None))


if __name__ == "__main__":
    unittest.main()
