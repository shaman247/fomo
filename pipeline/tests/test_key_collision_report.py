"""build_locations_map: alias/short-name keys claimed by two locations are reported, not silent.

Background: the alternate_names/short_names tiers are plain dicts written with
`tier[key] = info`, so a curated alias present on two locations silently resolves to whichever
row was loaded last (memory: alias_key_collision_last_write_wins; 31 such keys cleaned by hand
2026-09-04). `_note_key_collision` records the collision and `_report_key_collisions` prints
alternate_names collisions one per line and short_names collisions as a single count (block-party
rows legitimately share normalized shorthands like '72nd st' — 460 of them on 2026-09-07).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import processor  # noqa: E402


class TestKeyCollisionReport(unittest.TestCase):
    def _map(self):
        return {'alternate_names': {}, 'short_names': {}}

    def test_same_location_repeat_is_not_a_collision(self):
        m = self._map()
        info = {'id': 1, 'name': 'A'}
        m['alternate_names']['the a'] = info
        processor._note_key_collision(m, 'alternate_names', 'the a', {'id': 1, 'name': 'A'})
        self.assertNotIn('key_collisions', m)

    def test_alias_claimed_by_two_locations_is_recorded_and_printed(self):
        m = self._map()
        m['alternate_names']['conference house'] = {'id': 1479, 'name': 'Conference House Park'}
        processor._note_key_collision(m, 'alternate_names', 'conference house',
                                      {'id': 9000, 'name': 'Conference House'})
        self.assertEqual(m['key_collisions'],
                         [('alternate_names', 'conference house', 1479, 'Conference House Park',
                           9000, 'Conference House')])
        out = io.StringIO()
        with redirect_stdout(out):
            processor._report_key_collisions(m)
        self.assertIn("'conference house'", out.getvalue())
        self.assertIn('1479', out.getvalue())
        self.assertIn('9000 wins', out.getvalue())

    def test_short_name_collisions_are_summarised_as_one_line(self):
        m = self._map()
        for i in range(5):
            m['short_names'][f'{i}th st'] = {'id': 100 + i, 'name': f'{i}th St (A-B)'}
            processor._note_key_collision(m, 'short_names', f'{i}th st',
                                          {'id': 200 + i, 'name': f'{i}th St (C-D)'})
        out = io.StringIO()
        with redirect_stdout(out):
            processor._report_key_collisions(m)
        lines = [l for l in out.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertIn('5 short_names keys', lines[0])

    def test_no_collisions_prints_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            processor._report_key_collisions(self._map())
        self.assertEqual(out.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
