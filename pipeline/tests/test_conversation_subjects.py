"""Named festival conversations must retain their own guests and schedules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_name_guards import conversation_subject_mismatch
from merger import are_names_similar
from processor import group_event_occurrences


class ConversationSubjects(unittest.TestCase):
    def test_different_speakers_do_not_match_either_order(self):
        a = 'In Conversation: Tony Goldwyn & Griffin Dunne'
        b = 'In Conversation with Britt Lower'
        for left, right in [(a, b), (b, a), (a, 'In Conversation')]:
            self.assertFalse(are_names_similar(left, right))
            self.assertFalse(are_names_similar(right, left))

    def test_shared_calendar_url_does_not_join_talks(self):
        rows = [dict(name=name, location='Studio', location_id=1,
                     url='https://example.org/schedule', start_date='2026-10-17',
                     start_time=time)
                for name, time in [('In Conversation: Tony Goldwyn & Griffin Dunne', '3pm'),
                                   ('In Conversation with Britt Lower', '5pm')]]
        for entries in [rows, rows[::-1]]:
            groups = group_event_occurrences(entries)
            self.assertEqual(len(groups), 2)
            self.assertTrue(all(len(g['occurrences']) == 1 for g in groups))

    def test_spelling_guest_expansion_and_unrelated_formats_remain_compatible(self):
        for a, b in [('In Conversation: Britt Lower', 'In Conversation with BRITT LOWER'),
                     ('In Conversation: Tony Goldwyn', 'In Conversation: Tony Goldwyn & Griffin Dunne'),
                     ('In Conversation: Cynthia López', 'In Conversation with Cynthia Lopez'),
                     ('In Conversation: Film', 'In Conversation: Television'),
                     ('A Conversation About Trees', 'A Conversation About Plants')]:
            self.assertFalse(conversation_subject_mismatch(a, b))
        self.assertTrue(are_names_similar('In Conversation: Britt Lower', 'In Conversation with BRITT LOWER'))


if __name__ == '__main__':
    unittest.main()
