"""Current source categories survive formatting and keyword history voting."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
from merger import compute_voted_tags
from processor import process_tags


class CurrentSourceTagTests(unittest.TestCase):
    def process(self, tags):
        return process_tags(
            {'hashtags': tags},
            {'rewrite': {'online': 'Virtual'}, 'exclude': ['spam']},
            ancestor_map={'webinar': {'Education'}},
            root_tags={'education'},
        )['tags']

    def vote(self, history, current, curated=('Education', 'Virtual'), count=9):
        cursor = MagicMock()
        cursor.fetchall.return_value = history
        cursor.fetchone.return_value = (count,)
        return compute_voted_tags(cursor, 1, current, set(curated), {}, {'education'})

    def test_prefixed_array_matches_markdown_tags(self):
        array = [' #Education ', '#Online', '#Webinar,', 'Education', '#Spam']
        expected = self.process('#Education #Online #Webinar, #Education #Spam')
        self.assertEqual(self.process(array), expected)
        self.assertEqual(set(expected), {'Education', 'Virtual', 'Webinar'})

    def test_empty_prefixes_drop_without_damaging_literal_sharps(self):
        tags = self.process(['#', ' ## ', ' ', '#C#', 'F#', '#Webinar'])
        self.assertEqual(set(tags), {'C#', 'F#', 'Webinar', 'Education'})

    def test_current_curated_tag_survives_sparse_history(self):
        tags = self.vote([('Education', 9)], ['Education', 'Virtual', 'One Off'])
        self.assertEqual(set(tags), {'Education', 'Virtual'})

    def test_old_curated_outlier_does_not_gain_an_exemption(self):
        tags = self.vote([('Education', 9), ('Virtual', 1)], ['Education'])
        self.assertEqual(tags, ['Education'])

    def test_historical_consensus_still_survives_current_omission(self):
        tags = self.vote([('Education', 9), ('Virtual', 4)], ['Education'])
        self.assertEqual(set(tags), {'Education', 'Virtual'})

    def test_duplicate_current_keywords_still_get_one_vote(self):
        tags = self.vote([('Education', 9)], ['Education', 'Keyword', 'Keyword', 'Keyword'])
        self.assertNotIn('Keyword', tags)

    def test_keyword_cap_and_ancestor_derivation_still_apply(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(f'Keyword {n}', 5) for n in range(8)]
        cursor.fetchone.return_value = (9,)
        tags = compute_voted_tags(cursor, 1, ['Webinar'], {'Education', 'Webinar'},
                                  {'webinar': {'Education'}}, {'education'})
        self.assertIn('Webinar', tags)
        self.assertIn('Education', tags)
        self.assertNotIn('Other', tags)
        self.assertEqual(len([t for t in tags if t.startswith('Keyword')]), 6)

    def test_current_virtual_cannot_override_reviewed_block(self):
        tags = self.vote([('Education', 9)], ['Education', 'Virtual'])
        self.assertIn('Virtual', tags)
        writer = MagicMock()
        writer.fetchall.return_value = [(20,)]
        ids = {'Education': 10, 'Virtual': 20}
        writer.execute.side_effect = lambda sql, args: setattr(
            writer.fetchone, 'return_value', (ids[args[0]],)
        ) if 'SELECT id FROM tags' in sql else None
        db.upsert_event_tags(writer, 1, tags, replace=True)
        inserted = [c.args[1] for c in writer.execute.call_args_list
                    if 'INSERT IGNORE INTO event_tags' in c.args[0]]
        self.assertEqual(inserted, [(1, 10)])


if __name__ == '__main__':
    unittest.main()
