import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_types import separate_format_topics

class FormatTaxonomyTests(unittest.TestCase):
    def test_root_sports_topic_survives_separation_while_game_format_does_not(self):
        rows=[{'name':'Format'}, {'name':'Performance','parents':['Format']},
              {'name':'Sports','parents':['Performance']},
              {'name':'Soccer','parents':['Sports']},
              {'name':'Game','parents':['Participatory']}, {'name':'Games','parents':[]},
              {'name':'Reading','parents':['Performance','Literature']}]
        topics, hidden=separate_format_topics(rows)
        graph={t['name']:t.get('parents',[]) for t in topics}
        self.assertEqual(graph,{'Sports':[],'Soccer':['Sports'],'Games':[],'Reading':['Literature']})
        self.assertIn('Game',hidden)
        self.assertNotIn('Sports',hidden)
        self.assertEqual(rows[2]['parents'],['Performance'])
