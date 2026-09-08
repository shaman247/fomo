import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'scripts/consolidate_tag_aliases.py'
spec = importlib.util.spec_from_file_location('consolidate_tag_aliases', path)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

class ConsolidationTests(unittest.TestCase):
    def test_retirement_preserves_parents_children_and_removes_self_edges(self):
        # Science -> Artificial Intelligence -> AI; AI -> specialist topic.
        result = repair.remap_edges([(1,2),(2,3),(3,4),(2,4)], {3:2})
        self.assertEqual(result,{(1,2),(2,4)})
        self.assertEqual(repair.remap_edges(result,{3:2}),result)

    def test_alias_across_branches_cannot_create_cycle(self):
        with self.assertRaises(ValueError):
            repair.remap_edges([(1,2),(2,3),(3,4)],{4:1})
