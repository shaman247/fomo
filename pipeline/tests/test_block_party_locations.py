"""Street-segment identity must survive spelling changes without crossing boroughs."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
try:
    import add_block_party_locations as blocks
except ModuleNotFoundError as exc:
    if exc.name != 'add_block_party_locations':
        raise
    blocks = None  # This NYC deployment helper is intentionally gitignored.


@unittest.skipIf(blocks is None, 'SAPO deployment helper is not installed')
class BlockIdentityTests(unittest.TestCase):
    def test_reviewed_spelling_pairs(self):
        pairs = [
            ('DECATUR AVENUE between EAST 194 STREET and EAST 195 STREET',
             'Decatur Ave (E 195th St–E 194th St), Bronx'),
            ('SOUTH SECOND STREET between MARCY AVENUE and HAVEMEYER STREET',
             'SOUTH 2 STREET between HAVEMEYER STREET and MARCY AVENUE'),
            ('EAST 115 STREET between 3 AVENUE and 2 AVENUE',
             'East 115th St (Second Ave–Third Ave), Manhattan'),
            ('DEGRAW STREET between COURT STREET and SMITH STREET',
             'Degraw St (Ct St–Smith St), Brooklyn'),
            ('QUINCY STREET between MALCOM X BOULEVARD and PATCHEN AVENUE',
             'Quincy St (Patchen Ave–Malcolm X Blvd), Brooklyn'),
        ]
        for left, right in pairs:
            with self.subTest(left=left):
                self.assertEqual(blocks.canon(left), blocks.canon(right))
                self.assertEqual(blocks.canon(left), blocks.canon(blocks.canon(left)))

    def test_distinct_streets_and_directions_stay_distinct(self):
        base = 'East 115 St between Second Ave and Third Ave'
        for other in ('West 115 St between Second Ave and Third Ave',
                      'East 116 St between Second Ave and Third Ave',
                      'East 115 St between First Ave and Third Ave'):
            self.assertNotEqual(blocks.canon(base), blocks.canon(other))
        self.assertEqual(blocks.street_key('St Johns Place'), 'ST JOHNS PL')

    def test_boroughs_do_not_collide_and_ambiguous_matches_remain_visible(self):
        index = blocks.BlockIndex()
        name = 'Main Street between First Avenue and Second Avenue'
        index.add(name, 'Brooklyn', 1)
        index.add(name, 'Queens', 2)
        self.assertEqual(index.candidates(name, 'Brooklyn'), {1})
        index.add(name, 'Brooklyn', 3)
        self.assertEqual(index.candidates(name, 'Brooklyn'), {1, 3})
        self.assertEqual(index.candidates(name, 'Manhattan'), set())

    def test_bare_names_and_unknown_boroughs_are_not_block_evidence(self):
        index = blocks.BlockIndex()
        index.add('Main Street', 'Brooklyn', 1)
        index.add('Main St (1st Ave–2nd Ave)', '', 2)
        self.assertFalse(index.by_key)

    def test_other_publishers_names_and_aliases_are_loaded(self):
        class Cursor:
            def __init__(self):
                self.results = iter([
                    [{'id': 7, 'name': 'A block', 'borough': 'Brooklyn'}],
                    [{'id': 7, 'name': 'A block'},
                     {'id': 8, 'name': 'Quincy St (Patchen Ave–Malcolm X Blvd), Brooklyn'}],
                    [{'location_id': 7, 'alternate_name':
                      'Degraw Street between Court Street and Smith Street', 'website_id': 555}],
                ])
            def execute(self, *args):
                pass
            def fetchall(self):
                return next(self.results)
        index, _ = blocks.load_block_index(Cursor())
        self.assertEqual(index.candidates('Degraw St (Ct St–Smith St)', 'Brooklyn'), {7})
        self.assertEqual(index.candidates('Quincy St (Malcom X Blvd–Patchen Ave)', 'Brooklyn'), {8})


if __name__ == '__main__':
    unittest.main()
