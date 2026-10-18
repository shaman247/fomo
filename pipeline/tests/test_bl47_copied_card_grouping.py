"""In-crawl grouping keeps a "Copy of <title>" card apart from <title> (BL47, 2026-10-18).

Gladys (w994) duplicated a calendar card without renaming it. The extractor
returned the copy as its own record, but group_event_occurrences folded it into
the original by name containment (same venue, same listing URL), so the
merger's copied-card guard never saw it and the copy's Oct 31 date landed on
the original event.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_name_guards import copied_card_mismatch
from processor import group_event_occurrences

URL = 'https://gladysbooksandwine.com/pages/events'


def _row(name, start_date, start_time, **extra):
    return dict(name=name, location='Gladys Books & Wine', location_id=2571, url=URL,
                start_date=start_date, start_time=start_time,
                description=extra.pop('description', 'No description available.'), **extra)


class CopiedCardGroupingTests(unittest.TestCase):

    def test_copy_is_not_grouped_into_its_original_in_either_order(self):
        rows = [_row('I DO the Bending Live Podcast Recording!', '2026-10-30', '6:30pm',
                     end_time='9pm', description='A live podcast recording of I DO the Bending.'),
                _row('Copy of I DO the Bending Live Podcast Recording!', '2026-10-31', '7pm',
                     end_date='2026-11-01', end_time='1am')]
        for order in (rows, rows[::-1]):
            groups = group_event_occurrences([dict(r) for r in order], URL)
            self.assertEqual(sorted((g['name'], len(g['occurrences'])) for g in groups), [
                ('Copy of I DO the Bending Live Podcast Recording!', 1),
                ('I DO the Bending Live Podcast Recording!', 1)])

    def test_two_copies_still_group(self):
        rows = [_row('Copy of Trivia Night', '2026-10-20', '7pm'),
                _row('Copy of Trivia Night', '2026-10-27', '7pm')]
        groups = group_event_occurrences(rows, URL)
        self.assertEqual([(g['name'], len(g['occurrences'])) for g in groups],
                         [('Copy of Trivia Night', 2)])

    def test_guard(self):
        self.assertTrue(copied_card_mismatch('Copy of Jazz Brunch', 'Jazz Brunch'))
        self.assertTrue(copied_card_mismatch('Jazz Brunch', '  copy of Jazz Brunch'))
        self.assertFalse(copied_card_mismatch('Copy of A', 'Copy of B'))
        self.assertFalse(copied_card_mismatch('Copycat Comedy', 'Copycat Comedy Live'))
        self.assertFalse(copied_card_mismatch('A', 'B'))


if __name__ == '__main__':
    unittest.main()
