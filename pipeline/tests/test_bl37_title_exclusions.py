"""Per-site title exclusions applied before chunking (BL37, 2026-10-12).

The Dram Shop's Eventbrite organizer feed (w5053, cr-131206) is ~99% recurring
food/drink specials. Measured on that capture: 259 excluded records, 169,770 ->
18,841 chars, 8 chunked packets -> 1 single call, all 3 real events kept. The
card excerpts below are trimmed from it.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor as ex

PATTERNS = ex.parse_title_exclusions(
    '^The Best Happy Hour in Park Slope!?$\n'
    '^Weekday Lunch & Happy Hour!?$\n'
    '\n'
    '^Tex-Mex Brunch( in Crown Heights)?$\n'
    '^Taco Thursday$\n')


def card(title, slug, when):
    return (f'[![{title} primary image](https://img.evbuc.com/x/{slug}.jpg)]'
            f'(https://www.eventbrite.com/e/{slug}?aff=ebdsoporgprofile)\n'
            f'### [{title}](https://www.eventbrite.com/e/{slug}?aff=ebdsoporgprofile)\n'
            f'{when}\nThe Dram Shop Bar\nFree\n'
            f'_Save this event: {title}_ _Share this event: {title}_\n')


PAGE = ('# The Dram Shop Bar\n'
        + card('Taco Thursday', 'taco-thursday-tickets-1', 'Thursday • 3:00 PM and 9+ more')
        + card('NBA Season Opener: 76ers @ KNICKS', 'nba-season-opener-2', 'Tue, Oct 20 • 7:00 PM')
        + 'October 24Saturday\n'
        + card('Weekday Lunch & Happy Hour!', 'weekday-lunch-3', 'Tomorrow • 11:00 AM and 9+ more')
        + card('The Dram Shop Bar Annual Pumpkin Carving', 'pumpkin-4', 'Sat, Oct 24 • 11:00 AM')
        + card('Tex-Mex Brunch in Crown Heights', 'tex-mex-5', 'Saturday • 11:00 AM and 9+ more')
        + '## Eventbrite organizer API — upcoming events\n'
        + '### [Taco Thursday](https://www.eventbrite.com/e/taco-6)\n**Date** : October 15, 2026\n'
        + 'EVENT DETAIL URL: https://www.eventbrite.com/e/taco-6\n* * *\n'
        + '### [Camp Friendship Brooklyn 1st annual Pancake Breakfast](https://www.eventbrite.com/e/pb-7)\n'
        + '**Date** : November 1, 2026\nEVENT DETAIL URL: https://www.eventbrite.com/e/pb-7\n* * *\n')


class TitleExclusionTests(unittest.TestCase):

    def test_parse_skips_blanks_and_compiles_case_insensitive(self):
        self.assertEqual(len(PATTERNS), 4)
        self.assertTrue(PATTERNS[3].search('TACO THURSDAY'))

    def test_invalid_regex_is_matched_literally(self):
        (pattern,) = ex.parse_title_exclusions('Kids Eat Free (Saturdays')
        self.assertTrue(pattern.search('Kids Eat Free (Saturdays'))

    def test_excluded_records_are_dropped_and_real_events_survive(self):
        text, dropped, chars = ex.drop_excluded_records(PAGE, PATTERNS)
        self.assertEqual(dropped, 4)
        self.assertEqual(chars, len(PAGE) - len(text))
        for gone in ('Taco Thursday', 'Weekday Lunch', 'Tex-Mex Brunch', 'taco-6'):
            self.assertNotIn(gone, text)
        for kept in ('NBA Season Opener', 'Tue, Oct 20', 'Annual Pumpkin Carving',
                     'Sat, Oct 24', 'Pancake Breakfast', 'November 1, 2026',
                     'October 24Saturday', '# The Dram Shop Bar',
                     '## Eventbrite organizer API'):
            self.assertIn(kept, text)

    def test_card_image_goes_with_its_excluded_heading(self):
        text, _, _ = ex.drop_excluded_records(PAGE, PATTERNS)
        self.assertNotIn('Taco Thursday primary image', text)
        # The next card's image line stays with the next card.
        self.assertIn('NBA Season Opener: 76ers @ KNICKS primary image', text)
        self.assertIn('Annual Pumpkin Carving primary image', text)

    def test_anchored_pattern_spares_a_real_event_sharing_words(self):
        page = card('Halloween Taco Thursday Costume Party', 'h-1', 'Thu, Oct 29 • 8:00 PM')
        self.assertEqual(ex.drop_excluded_records(page, PATTERNS), (page, 0, 0))

    def test_no_patterns_or_no_headings_is_a_no_op(self):
        self.assertEqual(ex.drop_excluded_records(PAGE, []), (PAGE, 0, 0))
        flat = 'Taco Thursday every week\nNBA Season Opener Oct 20'
        self.assertEqual(ex.drop_excluded_records(flat, PATTERNS), (flat, 0, 0))


if __name__ == '__main__':
    unittest.main()
