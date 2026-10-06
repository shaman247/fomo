"""Review packets must not lose delivery evidence or confuse map pins with labels."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_event_tags as audit


class Cursor:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        self.current = next(self.replies)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class AuditSnapshotTests(unittest.TestCase):
    def test_online_label_full_description_and_source_links_survive(self):
        description = 'Program details. ' * 50 + 'Attend online via Zoom.'
        cur = Cursor([
            ('Book discussion', 'Talk', description, 'Zoom', 'Physical Library', None, '1 Main St'),
            [('Literature', 'tag'), ('Virtual', 'tag'), ('Books', 'keyword')],
            [('https://example.org/events/book-discussion',), ('https://zoom.us/j/123',)],
        ])
        row = audit.review_snapshots(cur, [42])[0]
        self.assertEqual(row['desc'], description)
        self.assertEqual(row['location_name'], 'Zoom')
        self.assertEqual(row['venue'], 'Physical Library')
        self.assertEqual(row['urls'][1], 'https://zoom.us/j/123')
        self.assertEqual(row['curated_tags'], ['Literature', 'Virtual'])
        self.assertEqual(row['keywords'], ['Books'])
        self.assertEqual(row['virtual_review']['default_without_delivery_evidence'], 'review')
        self.assertTrue(row['virtual_review']['source_verification_required_before_removal'])
        self.assertIn("t.scope='event'", cur.queries[1][0])
        self.assertTrue(all(sql.lstrip().startswith('SELECT') for sql, _ in cur.queries))

    def test_missing_online_evidence_does_not_authorize_removal(self):
        cur = Cursor([('Program', 'Class', None, None, 'Library', None, None),
                      [('Virtual', 'tag')], []])
        row = audit.review_snapshots(cur, [1])[0]
        self.assertEqual(row['urls'], [])
        self.assertEqual(row['location_name'], '')
        self.assertFalse(row['virtual_review']['physical_map_pin_proves_in_person'])
        self.assertEqual(row['virtual_review']['default_without_delivery_evidence'], 'review')

    def test_no_physical_pin_does_not_relabel_online_location_as_venue(self):
        cur = Cursor([('Program', 'Class', 'Live online', 'Online', None, None, None),
                      [('Virtual', 'tag')], []])
        row = audit.review_snapshots(cur, [1])[0]
        self.assertEqual(row['venue'], '')
        self.assertEqual(row['location_name'], 'Online')

    def test_pattern_uses_sorted_snapshot_and_task_output_directory(self):
        cur = Cursor([[(9,), (2,)]])
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(audit, 'patterns', return_value=[('virtual_on_physical', '', 'SELECT candidates', None)]), \
             patch.object(audit, 'review_snapshots', return_value=[{'id': 2}, {'id': 9}]) as snapshots:
            audit.run_pattern(cur, 'virtual_on_physical', tmp)
            snapshots.assert_called_once_with(cur, [2, 9])
            self.assertEqual(json.loads((Path(tmp) / 'audit_virtual_on_physical_review.json').read_text()),
                             [{'id': 2}, {'id': 9}])

    def test_unknown_pattern_fails_without_running_candidate_query(self):
        cur = Cursor([])
        with patch.object(audit, 'patterns', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'Unknown audit pattern'):
                audit.run_pattern(cur, 'typo')
        self.assertEqual(cur.queries, [])


if __name__ == '__main__':
    unittest.main()
