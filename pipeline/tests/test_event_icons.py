"""Semantic regressions: similar words must not assign unrelated activities."""
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_icons import propose, CATALOG, ICON_IDS, PATTERNS, ROOT

class IconRulesTest(unittest.TestCase):
    def test_each_legacy_heuristic_has_a_positive(self):
        examples = {'game-go':'Baduk Game Class', 'game-dominoes':'Dominoes Night',
            'game-scrabble':'Scrabble Club', 'game-mtg':'MTG Commander',
            'tabletop-rpg':'Dungeons & Dragons', 'trivia':'Harry Potter Trivia',
            'bingo':'Drag Bingo', 'music-bingo':'Music Bingo',
            'machine-sewing':'Sewing Machine 101', '3d-printing':'3D Printing',
            'game-backgammon':'Backgammon Club', 'game-rummikub':'Rummikub',
            'pole-dance':'Intro to Pole Dance', 'chair-yoga':'Chair Yoga',
            'glassblowing':'Intro to Glassblowing'}
        self.assertEqual(set(examples), set(PATTERNS))
        self.assertTrue(set(examples) <= ICON_IDS)
        for icon, name in examples.items():
            with self.subTest(name=name):
                self.assertEqual(propose({'name':name})['icon_id'],icon)

    def test_false_friends_abstain(self):
        for name in ['Go to the Movies', 'Bridge Over the Creek', 'MTG Board Meeting',
                     'Stage Magic', 'Hand Sewing', 'Knitting Circle', '3D Movie',
                     'Fused Glass Workshop', 'Senior Exercise', 'Pokemon Cards',
                     'Sewing Machine Documentary', 'Scrabble and Mahjong',
                     'Magic the Gathering & Other Trading Card Games Club']:
            with self.subTest(name=name):
                self.assertIsNone(propose({'name':name})['icon_id'])

    def test_description_mentions_are_review_only(self):
        result=propose({'name':'Family Fun', 'description':'Try Scrabble and trivia or watch a movie.'})
        self.assertEqual(result['decision'],'review')
        self.assertIsNone(result['icon_id'])
        self.assertEqual({e['field'] for e in result['evidence']},{'description'})

    def test_specific_bingo_and_conflicting_families(self):
        self.assertEqual(propose({'name':'Music Bingo'})['icon_id'],'music-bingo')
        self.assertEqual(propose({'name':'Bingo and Trivia'})['decision'],'review')

    def test_mixtape_bingo_refines_bingo_without_matching_other_mixtape_events(self):
        for name in ["Mixtape Bingo at Dolly's", 'FREE MIXTAPE BINGO',
                     'Mix Tape Bingo Night', 'Mix-tape Bingo']:
            with self.subTest(name=name):
                result = propose({'name': name})
                self.assertEqual(result['icon_id'], 'music-bingo')
                self.assertEqual(result['decision'], 'proposed')
                self.assertEqual({e['icon_id'] for e in result['evidence']}, {'music-bingo'})
        for name in ['Mixtape Comedy Show', 'Mixtape Craft Club']:
            self.assertIsNone(propose({'name': name})['icon_id'])
        for name in ['Bingo Night', 'Drag Bingo']:
            self.assertEqual(propose({'name': name})['icon_id'], 'bingo')
        self.assertEqual(propose({'name': 'Mixtape Bingo and Trivia'})['decision'], 'review')
        self.assertEqual(propose({'name': 'History of Mixtape Bingo'})['decision'], 'review')
        result = propose({'name': 'Games Night', 'description': 'Try Mixtape Bingo.'})
        self.assertEqual(result['decision'], 'review')
        self.assertIsNone(result['icon_id'])

    def test_input_hash_is_stable_and_tracks_relevant_content(self):
        a={'name':'Go Club','description':'Play together','tags':['Adult','Games']}
        self.assertEqual(propose(a)['input_hash'],propose(dict(a,tags=['Games','Adult']))['input_hash'])
        self.assertNotEqual(propose(a)['input_hash'],propose(dict(a,description='Changed'))['input_hash'])
        self.assertEqual(propose(a)['input_hash'],propose(dict(a,emoji='🌳'))['input_hash'])

    def test_go_titles_require_specific_context_and_preserve_evidence(self):
        for name in ['Jersey City Go', 'Go Jersey City Go', 'Gotham Go Group', 'New Town Go']:
            with self.subTest(name=name):
                result = propose({'name': name, 'tags': ['Games', 'Go']})
                self.assertEqual(result['icon_id'], 'game-go')
                self.assertEqual({e['field'] for e in result['evidence']}, {'name', 'tags'})
                self.assertEqual(propose({'name': name, 'tags': ['Games', 'Board Games']})['icon_id'], None)
        for description in ['Weekly gathering to play the board game Go.',
                            'Learn the game of Go.', 'Go (baduk / weiqi) meetup.']:
            result = propose({'name': 'New Town Go', 'description': description})
            self.assertEqual(result['icon_id'], 'game-go')
            self.assertIn('description', {e['field'] for e in result['evidence']})
        for name in ['Go to the Movies', 'Go Figure', 'Grab & Go Craft Kit', 'Go Programming Meetup']:
            self.assertIsNone(propose({'name': name, 'tags': ['Games', 'Board Games']})['icon_id'])
        self.assertIsNone(propose({'name': 'Community Gathering', 'tags': ['Go']})['icon_id'])
        for name in ['Go and Chess', 'Go and Scrabble', 'History of Go', 'Go Documentary']:
            result = propose({'name': name, 'tags': ['Go']})
            self.assertEqual(result['decision'], 'review')
            self.assertIsNone(result['icon_id'])

    def test_dungeons_and_drafts_is_an_rpg_alias_not_any_dungeon_or_draft(self):
        for name in ['Dungeons & Drafts', 'Dungeons and Drafts at Wild East Brewing',
                     'DUNGEONS & DRAFTS at Brooklyn Brewery']:
            self.assertEqual(propose({'name': name})['icon_id'], 'tabletop-rpg')
        for name in ['Dungeon Tour', 'Draft Beer Night', 'MTG Draft', 'Dungeons & Draftsmanship']:
            self.assertNotEqual(propose({'name': name})['icon_id'], 'tabletop-rpg')
        for name in ['Dungeons & Drafts and Trivia', 'Dungeons & Drafts Documentary']:
            self.assertEqual(propose({'name': name})['decision'], 'review')
        result = propose({'name': 'Community Night', 'description': 'Dungeons & Drafts also meets here.'})
        self.assertEqual(result['decision'], 'review')
        self.assertIsNone(result['icon_id'])

    def test_safe_vector_assets_and_catalog_identity(self):
        self.assertEqual(len(CATALOG['icons']),len(ICON_IDS))
        for item in CATALOG['icons']:
            root=ET.parse(ROOT/'config/event-icons'/item['source']).getroot()
            self.assertEqual(root.attrib['viewBox'],'0 0 128 128')
            for element in root.iter():
                self.assertNotIn(element.tag.split('}')[-1], ['text','image','script','foreignObject','filter'])
                self.assertFalse(any(k.lower().startswith('on') or k.split('}')[-1]=='href' for k in element.attrib))

if __name__=='__main__': unittest.main()
