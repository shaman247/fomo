import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_icon_audit import prepare


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.events = [dict(id=i, name='Go club' if i % 2 else 'Music',
                            emoji='🎲' if i % 2 else '🎵', tags=['Games', 'Games'])
                       for i in range(40)]

    def test_reproducible_independent_of_input_order_and_no_overlap(self):
        result = prepare(self.events, 10, 20260908, r'\bGo\b', 12)
        self.assertEqual(result, prepare(list(reversed(self.events)), 10, 20260908, r'\bGo\b', 12))
        summary, rows = result
        self.assertEqual(summary['focus_matches_population'], 20)
        self.assertEqual(summary['random_size'], 10)
        self.assertEqual(len({r['event']['id'] for r in rows}), len(rows))
        self.assertTrue(all(r['event']['name'] == 'Go club' for r in rows if r['cohort'] == 'targeted'))
        self.assertTrue(all(r['review']['fit'] is None for r in rows))

    def test_counts_are_population_counts_and_unicode_exact(self):
        self.events[0]['emoji'] = '🀄'
        self.events[1]['emoji'] = '🀄️'
        summary, _ = prepare(self.events, 1)
        self.assertEqual(summary['emoji']['🀄'], 1)
        self.assertEqual(summary['emoji']['🀄️'], 1)
        self.assertEqual(summary['tags']['Games'], 40)
        self.assertEqual(sum(summary['emoji'].values()), 40)

    def test_small_empty_and_invalid_populations(self):
        self.assertEqual(prepare([], 300)[1], [])
        self.assertEqual(len(prepare(self.events[:2], 300)[1]), 2)
        with self.assertRaises(ValueError):
            prepare(self.events * 2)
        with self.assertRaises(ValueError):
            prepare(self.events, -1)


if __name__ == '__main__':
    unittest.main()
