import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import sync_format_tags as sync


class TargetedFormatSyncTests(unittest.TestCase):
    def test_targeted_sync_stays_inside_callers_transaction(self):
        cur, conn = MagicMock(), MagicMock()
        cur.fetchall.return_value = [(17, 'Talk')]
        with patch.object(sync, '_tag_id', return_value=1):
            sync.sync_event_tags(cur, conn, event_ids=[17], commit=False)
        calls = cur.execute.call_args_list
        self.assertIn('AND event_id IN (%s)', calls[0].args[0])
        self.assertEqual(calls[0].args[1][-1], 17)
        self.assertIn('AND id IN (%s)', calls[1].args[0])
        self.assertEqual(calls[1].args[1][-1], 17)
        self.assertEqual({row[0] for row in cur.executemany.call_args.args[1]}, {17})
        conn.commit.assert_not_called()

    def test_empty_scope_is_noop(self):
        cur, conn = MagicMock(), MagicMock()
        sync.sync_event_tags(cur, conn, event_ids=[])
        cur.execute.assert_not_called()
        conn.commit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
