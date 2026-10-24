"""Reworded or truncated copies of one listing must not become per-date sections."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_details import preserve_session_details


def row(description, start_date, url='https://example.org/e/1', sublocation=''):
    return dict(name='Class', description=description, start_date=start_date,
                start_time='10:30am', end_date='', end_time='11:15am', url=url,
                sublocation=sublocation, location='Library', location_id=1)


def preserve(rows):
    event = dict(description=rows[0]['description'])
    preserve_session_details(event, rows)
    return event


class FoldingTests(unittest.TestCase):
    def test_paraphrases_fold_to_longest_text(self):
        # e221022: two BPL permalinks for one Shape Up NYC series.
        short = ('A Shape Up NYC bodyweight circuit class combining cardio, strength '
                 'and core movements, instructed by Jasmine Alexander; all fitness levels welcome.')
        long = ('A bodyweight circuit class combining cardio, strength, and core-focused '
                'movements for a full-body workout, open to all fitness levels. Provided by '
                'Shape Up NYC and instructed by Jasmine Alexander.')
        event = preserve([row(short, '2026-10-24'), row(short, '2026-10-31'),
                          row(long, '2027-01-09', url='https://example.org/e/2')])
        self.assertEqual(event['description'], long)
        self.assertEqual(len(event['session_details']), 2)

    def test_truncated_teaser_folds_into_full_text(self):
        # e185355: a listing teaser cut mid-word at 200 characters.
        full = ('Join the Macon Library and Shape Up NYC for Bodyweight Circuit Training, '
                'an energetic yet low impact exercise class! This mix of cardio and body '
                'weight strength exercises gives a full body workout.')
        for teaser in (full[:150], full[:120] + '…', full[:120] + '...'):
            with self.subTest(teaser=teaser[-12:]):
                event = preserve([row(full, '2026-10-03'), row(teaser, '2026-10-10')])
                self.assertEqual(event['description'], full)

    def test_complete_text_beats_longer_cut_off_teaser(self):
        complete = 'Join the Macon Library for Bodyweight Circuit Training, an energetic class!'
        cut = complete + ' This mix of cardio and body weight strength exerc'
        for ordered in ([complete, cut], [cut, complete]):
            event = preserve([row(ordered[0], '2026-10-03'), row(ordered[1], '2026-10-10')])
            self.assertEqual(event['description'], complete)

    def test_per_date_lineups_stay_sections(self):
        base = 'Start your Saturday night off swinging. No cover.'
        rows = [row(base + ' Featuring Kaushik Viswanath, voice.', '2026-10-10'),
                row(base + ' Featuring William Humphrey, sax.', '2026-10-17'),
                row(base, '2026-10-31')]
        event = preserve(rows)
        self.assertIn('2026-10-10 10:30am–11:15am\n', event['description'])
        self.assertIn('Kaushik Viswanath', event['description'])
        self.assertIn('William Humphrey', event['description'])
        self.assertEqual(event['description'].count('\n\n'), 2)

    def test_different_numbers_or_polarity_stay_sections(self):
        pairs = [('There is a $42 fee for this 8-session class.',
                  'There is a $32 fee for this 6-session class.'),
                 ('Adults only.', 'All ages welcome.'),
                 ('Registration required.', 'No registration required.'),
                 ('Tonight’s show is sold out.', 'Tickets on sale tonight.')]
        for a, b in pairs:
            with self.subTest(a=a):
                event = preserve([row(a, '2026-10-01'), row(b, '2026-10-08')])
                self.assertIn(a, event['description'])
                self.assertIn(b, event['description'])

    def test_same_text_in_different_rooms_keeps_room_headings(self):
        text = 'Learn to play the trading card game Magic: The Gathering.'
        event = preserve([row(text, '2026-10-01', sublocation='Room A'),
                          row(text + ' ', '2026-10-08', sublocation='Room B')])
        self.assertIn('— Room A', event['description'])
        self.assertIn('— Room B', event['description'])
        self.assertEqual(event['sublocation'], 'Varies by session; see description')

    def test_all_stubs_keep_rooms_only_when_rooms_differ(self):
        stub = 'No description available.'
        # e74106: two stubs, one per stage, stay as heading-only room sections.
        event = preserve([row(stub, '2026-11-07', sublocation='Mainstage'),
                          row(stub, '2026-12-19', sublocation='LAB')])
        self.assertEqual(event['description'],
                         '2026-11-07 10:30am–11:15am — Mainstage\n\n'
                         '2026-12-19 10:30am–11:15am — LAB')
        self.assertEqual(event['sublocation'], 'Varies by session; see description')
        for rooms in (('Mainstage', ''), ('', '')):
            with self.subTest(rooms=rooms):
                event = preserve([row('', '2026-11-07', sublocation=rooms[0]),
                                  row(stub, '2026-12-19', sublocation=rooms[1])])
                self.assertEqual(event['description'], stub)
                self.assertNotIn('sublocation', event)

    def test_folded_sessions_share_one_heading_when_others_differ(self):
        a = 'Prime Time Comedy featuring special guest comedians.'
        a2 = 'Prime Time Comedy, featuring special guest comedians!'
        b = a + " This session's lineup: Corinne Fisher, Tom Zappia."
        event = preserve([row(b, '2026-10-03'), row(a, '2026-10-24'), row(a2, '2026-10-31')])
        sections = event['description'].split('\n\n')
        self.assertEqual(len(sections), 2)
        self.assertTrue(sections[1].startswith(
            '2026-10-24 10:30am–11:15am; 2026-10-31 10:30am–11:15am\n'))


if __name__ == '__main__':
    unittest.main()
