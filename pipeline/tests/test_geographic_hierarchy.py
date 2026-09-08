import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geographic_hierarchy import plan_repairs, event_counts

class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.edges = {('Neighborhood','Metro'),('Metro','Town'),('Metro','County'),('Topic','Town')}
        self.tags = {n:{'type':'tag'} for e in self.edges for n in e}

    def test_reparent_preserves_non_geographic_edges_and_is_idempotent(self):
        config={'groups':{'County':['Town']}}
        p=plan_repairs(self.tags,self.edges,config)
        self.assertEqual(p['remove'],[('Metro','Town')])
        final=(self.edges-set(p['remove']))|set(p['add'])
        self.assertIn(('Topic','Town'),final)
        self.assertFalse(any(plan_repairs(self.tags,final,config).values()))

    def test_existing_search_only_geography_is_promoted(self):
        self.tags['Town']['type']='keyword'
        self.assertEqual(plan_repairs(self.tags,self.edges,{})['promote'],['Town'])

    def test_rejects_cycles_and_unknown_names_before_writes(self):
        for cfg in [{'groups':{'Town':['Metro']}}, {'groups':{'County':['Typo']}}]:
            with self.assertRaises(ValueError):
                plan_repairs(self.tags,self.edges,cfg)

    def test_explicit_new_heading_must_be_reachable(self):
        cfg={'promote':['New County'],'groups':{'Metro':['New County'],'New County':['Town']}}
        self.assertEqual(plan_repairs(self.tags,self.edges,cfg)['create'],['New County'])
        with self.assertRaises(ValueError):
            plan_repairs(self.tags,self.edges,{'promote':['Stranded']})

    def test_counts_dedupe_event_and_venue_ancestors(self):
        edges=self.edges|{('County','Town')}
        counts=event_counts(edges,{1:['Town','County','Metro','Town'],2:['Town'],3:['Topic']})
        self.assertEqual(counts['Neighborhood'],2)
        self.assertEqual(counts['County'],2)
        self.assertEqual(counts['Town'],2)
        self.assertNotIn('Topic',counts)

    def test_empty_branches_get_explicit_zero(self):
        self.assertEqual(event_counts(self.edges,{})['Town'],0)

if __name__=='__main__':
    unittest.main()
