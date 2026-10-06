"""Resident Advisor reviewed day corrections (2026-10-06, backlog BL13).

RA's GraphQL times are naive local wall times and the plugin renders them as-is;
the only date errors found were promoter-entered wrong days (RA 2542449 listed
Oct 31 while Elsewhere + Eventbrite say Fri Oct 30). A reviewed correction must
fix exactly that reported value, keep RA's clock, and retire itself when RA
changes the listing.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from sources import resident_advisor as plugin
except ImportError:
    plugin = None


def hellp(start='2026-10-31T22:00:00.000', end='2026-11-01T04:00:00.000'):
    return {'id': '2542449', 'title': 'Elsewhere presents: The Hellp (DJ Set) at 99 Scott',
            'date': start[:10] + 'T00:00:00.000', 'startTime': start, 'endTime': end,
            'contentUrl': '/events/2542449', 'venue': {'name': '99 Scott Ave'}}


@unittest.skipIf(plugin is None, 'resident_advisor plugin not installed')
class ReviewedDayCorrectionTests(unittest.TestCase):
    def test_reported_wrong_day_is_shifted_keeping_clock(self):
        [ev] = plugin.apply_reviewed_day_corrections([hellp()])
        self.assertEqual(ev['date'], '2026-10-30T00:00:00.000')
        self.assertEqual(ev['startTime'], '2026-10-30T22:00:00.000')
        self.assertEqual(ev['endTime'], '2026-10-31T04:00:00.000')

    def test_markdown_renders_corrected_day(self):
        [ev] = plugin.apply_reviewed_day_corrections([hellp()])
        md = plugin.build_markdown([ev], '2026-10-06', '2027-01-04')
        self.assertIn('**Date**: October 30, 2026', md)
        self.assertIn('**Start**: 10pm — **End**: 4am', md)
        self.assertNotIn('October 31', md)

    def test_stale_correction_is_not_applied(self):
        # Promoter fixed RA (or moved the event): leave RA's new value alone.
        fixed = hellp('2026-10-30T22:00:00.000', '2026-10-31T04:00:00.000')
        moved = hellp('2026-11-07T22:00:00.000', '2026-11-08T04:00:00.000')
        self.assertEqual(plugin.apply_reviewed_day_corrections([fixed]), [fixed])
        self.assertEqual(plugin.apply_reviewed_day_corrections([moved]), [moved])

    def test_other_events_and_input_untouched(self):
        other = dict(hellp(), id='1')
        original = hellp()
        out = plugin.apply_reviewed_day_corrections([other, original])
        self.assertIs(out[0], other)
        self.assertEqual(original['startTime'], '2026-10-31T22:00:00.000')

    def test_fetcher_applies_corrections(self):
        with patch.object(plugin, 'fetch_nyc_events', return_value=[hellp()]), \
                patch.object(plugin, 'date') as fake_date:
            from datetime import date
            fake_date.today.return_value = date(2026, 10, 6)
            fake_date.fromisoformat = date.fromisoformat
            md, n = plugin.fetch_and_build_markdown()
        self.assertEqual(n, 1)
        self.assertIn('**Date**: October 30, 2026', md)

    def test_every_entry_is_well_formed(self):
        for eid, fix in plugin.REVIEWED_DAY_CORRECTIONS.items():
            self.assertTrue(eid.isdigit())
            self.assertRegex(fix['reported_start'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}')
            self.assertIn(fix['shift_days'], (-1, 1))
            self.assertTrue(fix['evidence'] and fix['reviewed'])


if __name__ == '__main__':
    unittest.main()
