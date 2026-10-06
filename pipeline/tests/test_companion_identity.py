"""Exhibition companions remain distinct even when slots are shared."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from companion_identity import (broad_exhibition_schedule, companion_parent_side,
                                exhibition_companion_mismatch)


class NamedLearningProgramTests(unittest.TestCase):
    def test_named_play_set_is_separate_from_broad_exhibition(self):
        parent = ('Lee Ufan', ['Exhibition'], [('2026-05-08', '', '2026-12-31', ''),
                                             ('2026-12-05', '10:30am', None, '11:15am')])
        learning = ('Play Sets: Lee Ufan', ['Workshop', 'Family'],
                    [('2026-12-05', '10:30am', None, '11:15am')])
        self.assertTrue(exhibition_companion_mismatch(*parent, *learning))
        self.assertTrue(exhibition_companion_mismatch(*learning, *parent))

    def test_ambiguous_artist_and_same_learning_program_remain_eligible(self):
        point = [('2026-12-05', '10:30am', None, '11:15am')]
        self.assertFalse(exhibition_companion_mismatch(
            'Lee Ufan', ['Talk'], point, 'Play Sets: Lee Ufan', ['Workshop'], point))
        self.assertFalse(exhibition_companion_mismatch(
            'Play Sets: Lee Ufan', ['Workshop'], point,
            'Play Sets: Lee Ufan', ['Workshop'], point))


class CompanionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.span = [('2026-09-01', '', '2026-10-31', '')]
        self.point = [('2026-09-01', '6pm', None, '8pm')]

    def test_reception_both_directions(self):
        a = ('The Painted World', ['Exhibition'], self.span)
        b = ('The Painted World: Opening Reception', ['Party'], self.point)
        self.assertTrue(exhibition_companion_mismatch(*a, *b))
        self.assertTrue(exhibition_companion_mismatch(*b, *a))

    def test_opening_for_exact_exhibition_keeps_untimed_point_separate(self):
        import processor
        title='Carol Struve & Stephen Niccols Exhibition'
        parent=(title,['Art','Exhibition'],[('2026-11-07','','2026-11-28','')])
        opening=('Opening for '+title,['Art','Reception'],[('2026-11-07','',None,'')])
        self.assertTrue(exhibition_companion_mismatch(*parent,*opening))
        self.assertTrue(exhibition_companion_mismatch(*opening,*parent))
        rows=[dict(name=n,location='Same gallery',location_id=1,url='https://example.org/events/',
                   tags=tags,start_date=o[0],start_time=o[1],end_date=o[2],end_time=o[3])
              for n,tags,occ in (parent,opening) for o in occ]
        for ordered in (rows,rows[::-1]):
            grouped=processor.group_event_occurrences(ordered)
            self.assertEqual(len(grouped),2)
            self.assertEqual(sorted(len(e['occurrences']) for e in grouped),[1,1])
        self.assertFalse(exhibition_companion_mismatch(title,['Theater Show'],self.span,*opening))
        self.assertFalse(exhibition_companion_mismatch(title,['Exhibition'],opening[2],*opening))
        self.assertIsNone(companion_parent_side(title,'Opening for Another Exhibition'))
        self.assertIsNone(companion_parent_side(title,title+' Opening'))
        self.assertIsNone(companion_parent_side(title,title+' Opening for'))

    def test_closing_weekend_discrete_parent_dates(self):
        regular = [('2026-09-05', '12pm', None, '6pm'),
                   ('2026-09-06', '12pm', None, '6pm'),
                   ('2026-09-12', '12pm', None, '6pm')]
        self.assertTrue(exhibition_companion_mismatch(
            'The Unintended Blues', ['Exhibition'], regular,
            'The Unintended Blues: Closing Weekend', ['Exhibition'],
            [('2026-09-26', '12pm', None, '6pm')]))

    def test_shared_date_and_clock_do_not_erase_mixed_parent_identity(self):
        self.assertTrue(exhibition_companion_mismatch(
            'Lost & Found: Mapping it Out', ['Exhibition'], self.span + self.point,
            'Reception for Lost & Found: Mapping it Out', ['Exhibition'], self.point))

    def test_parent_hours_are_still_an_exhibition(self):
        self.assertTrue(exhibition_companion_mismatch(
            'Lost & Found', ['Exhibition'], [('2026-08-24', '11am', '2026-10-03', '5pm')],
            'Reception for Lost & Found', [], self.point))

    def test_dateless_companion_still_has_distinct_explicit_identity(self):
        self.assertTrue(exhibition_companion_mismatch(
            'Anywhere–Everywhere', ['Exhibition'], self.span,
            'Anywhere–Everywhere Reception', [], []))

    def test_one_day_exhibition_opening_alias_is_not_split(self):
        self.assertFalse(exhibition_companion_mismatch(
            'The Painted World', ['Exhibition'], self.point,
            'The Painted World Opening Night', ['Party'], self.point))

    def test_weekend_exhibition_opening_alias_is_not_split(self):
        self.assertFalse(exhibition_companion_mismatch(
            'The Painted World', ['Exhibition'], [('2026-09-01', '', '2026-09-03', '')],
            'The Painted World Opening Reception', ['Party'], self.point))

    def test_recurring_show_is_not_an_exhibition(self):
        for formats in ([], ['Theater Show'], ['Festival'], ['Exhibition', 'Party']):
            with self.subTest(formats=formats):
                self.assertFalse(exhibition_companion_mismatch(
                    'Our Town', formats, self.span, 'Our Town Opening Night', [], self.point))

    def test_unrelated_and_ambiguous_titles(self):
        for names in [('The Painted World', 'The Painted World: New Paintings'),
                      ('The Painted World', 'The Painted World Tour'),
                      ('The Painted World', 'The Painted World Opening'),
                      ('The Painted World', 'The Painted World Closing'),
                      ('The Painted World', 'The Painted World Talk'),
                      ('The Painted World Opening Reception',
                       'Opening Reception The Painted World Opening Reception'),
                      ('The Painted World', 'Opening Reception: Another World')]:
            with self.subTest(names=names):
                self.assertIsNone(companion_parent_side(*names))

    def test_strong_kind_prefixes_suffixes_and_possessives(self):
        pairs = [('Betye Saar\'s Black Dolls', 'Gallery Tour: Betye Saar’s Black Dolls'),
                 ('Whitney Biennial 2026', 'Curator-Led Tour of Whitney Biennial 2026'),
                 ('Group Show | Vertex', 'Artist’s Reception – Group Show | VERTEX')]
        for a, b in pairs:
            with self.subTest(a=a):
                self.assertEqual(companion_parent_side(a, b), 0)
                self.assertEqual(companion_parent_side(b, a), 1)

    def test_explicit_exhibition_and_duration_tours(self):
        for companion in ('Exhibition Tour: Whitney Biennial 2026',
                          'Installation Tour of Whitney Biennial 2026',
                          '15-Minute Tour: Highlights of the Whitney Biennial 2026'):
            with self.subTest(companion=companion):
                self.assertTrue(exhibition_companion_mismatch(
                    'Whitney Biennial 2026', ['Exhibition'], self.span + self.point,
                    companion, ['Tour'], self.point))
        self.assertFalse(exhibition_companion_mismatch(
            'Whitney Biennial 2026', ['Exhibition'], self.span,
            '15-Minute Film: Highlights of the Whitney Biennial 2026', [], self.point))

    def test_member_and_accessibility_programs(self):
        for name, tags in [('Behind the Scenes: Whitney Biennial 2026', []),
                           ('Member Evening Viewing: Whitney Biennial 2026', []),
                           ('Member Mornings: Last Look at Whitney Biennial 2026', []),
                           ('Whitney Signs: Whitney Biennial 2026', ['ASL']),
                           ('Whitney Descriptions Online: Whitney Biennial 2026', ['Tour', 'Virtual'])]:
            with self.subTest(name=name):
                self.assertTrue(exhibition_companion_mismatch(
                    'Whitney Biennial 2026', ['Exhibition'], self.span,
                    name, tags, self.point))
        for name in ('Whitney Signs: Whitney Biennial 2026',
                     'Whitney Descriptions Online: Whitney Biennial 2026'):
            self.assertFalse(exhibition_companion_mismatch(
                'Whitney Biennial 2026', ['Exhibition'], self.span, name, [], self.point))
        self.assertTrue(exhibition_companion_mismatch(
            'Whitney Biennial 2026', ['Exhibition'], self.span,
            '15-Minute Tour: Highlights of the Whitney Biennial 2026 — Floor 6, Free Second Sundays',
            ['Tour'], self.point))

    def test_online_description_tour_canonical_needs_no_virtual_topic_tag(self):
        # The name already establishes online delivery; canonical profiles have
        # event_type, whereas source profiles additionally include topic tags.
        parent = ('Whitney Biennial 2026', ['Exhibition'], self.span)
        companion = ('Whitney Descriptions Online: Whitney Biennial 2026',
                     ['Tour'], self.point)
        self.assertTrue(exhibition_companion_mismatch(*parent, *companion))
        self.assertTrue(exhibition_companion_mismatch(*companion, *parent))
        self.assertFalse(exhibition_companion_mismatch(
            *parent, companion[0], ['Exhibition'], self.point))

    def test_gallery_presentation_prefix_is_not_exhibition_identity(self):
        self.assertTrue(exhibition_companion_mismatch(
            'The Richards Gallery — SELDOM SEEN II | Historic Works by Woodstock Artists',
            ['Exhibition'], self.span,
            'Opening Reception – SELDOM SEEN II | Historic Works by Woodstock Artists',
            ['Exhibition'], self.point))
        self.assertIsNone(companion_parent_side(
            'Another Program — SELDOM SEEN II | Historic Works by Woodstock Artists',
            'Opening Reception – SELDOM SEEN II | Historic Works by Woodstock Artists'))

    def test_malformed_reversed_and_insufficient_dates(self):
        for occurrences in ([('bad-date', '', None, '')],
                            [('2026-10-01', '', '2026-09-01', '')],
                            [('2026-09-01', '', None, ''), ('2026-10-01', '', None, '')],
                            [], self.span + [('bad-date', '', None, '')]):
            with self.subTest(occurrences=occurrences):
                self.assertFalse(broad_exhibition_schedule(['Exhibition'], occurrences))

    def test_database_date_objects_and_topic_tags(self):
        self.assertTrue(broad_exhibition_schedule(['Exhibition', 'Painting'],
            [(date(2026, 9, 1), '', date(2026, 10, 31), '')]))


if __name__ == '__main__':
    unittest.main()
