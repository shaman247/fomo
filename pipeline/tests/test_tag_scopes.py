import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_scopes import migration_plan, public_tag_key
import db


class TagScopeTests(unittest.TestCase):
    def test_topics_become_location_keywords_and_dual_names_keep_independent_graphs(self):
        names = ['Jazz', 'Music', 'Ballroom', 'Event Space', 'Dance', 'Neighborhood', 'Village']
        tags = [dict(id=i, name=n, type='tag') for i,n in enumerate(names)]
        plan = migration_plan(tags, {(1,0),(3,2),(5,6)}, ['Event Space','Ballroom'], {'Ballroom':['Dance']})
        self.assertNotIn('Jazz',plan['venue_names'])
        self.assertIn('Village',plan['venue_names'])
        self.assertIn((4,2),plan['event_edges'])
        self.assertNotIn((3,2),plan['event_edges'])
        self.assertIn((3,2),plan['venue_edges'])
        self.assertNotEqual(public_tag_key('Ballroom','event'),public_tag_key('Ballroom','venue'))
        self.assertNotIn(2,plan['demote'])
        self.assertIn(3,plan['demote'])

    def test_event_ingestion_resolves_only_event_identity(self):
        cur=MagicMock()
        cur.fetchall.return_value=[]
        cur.fetchone.return_value=(42,)
        db.upsert_event_tags(cur,1,['Ballroom'])
        selects=[c.args[0] for c in cur.execute.call_args_list if 'FROM tags' in c.args[0]]
        self.assertTrue(all("scope='event'" in sql for sql in selects))
        self.assertIn(('INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)', (1,42)),
                      [c.args for c in cur.execute.call_args_list])

    def test_same_alias_resolves_independently_for_both_scopes(self):
        cur=MagicMock()
        cur.fetchall.return_value=[('Ballroom','ballroom dancing','event'),('Event Space','ballroom dancing','venue')]
        self.assertEqual(db.get_tag_aliases_for_export(cur),
                         {'Ballroom':['ballroom dancing'], 'venue:Event Space':['ballroom dancing']})

    def test_hierarchy_export_never_collapses_same_name_parents(self):
        cur=MagicMock()
        cur.fetchall.side_effect=[
            [(1,'Ballroom','💃',0,None,None,'event'), (2,'Ballroom','🏛️',0,None,None,'venue')],
            [('Dance','Ballroom'),('venue:Event Space','venue:Ballroom')]]
        entries=db.get_tag_hierarchy_for_export(cur)
        self.assertEqual([(t['name'],t['parents']) for t in entries],
                         [('Ballroom',['Dance']),('venue:Ballroom',['venue:Event Space'])])
        self.assertEqual([t['display_name'] for t in entries],['Ballroom','Ballroom'])
