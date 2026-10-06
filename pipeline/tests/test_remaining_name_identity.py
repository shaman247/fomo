import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remaining_name_identity import remaining_name_identity_mismatch as mismatch


class RemainingNameIdentityTests(unittest.TestCase):
    def assertPair(self, left, right, expected):
        self.assertEqual(bool(mismatch(left, right)), expected)
        self.assertEqual(bool(mismatch(right, left)), expected)

    def test_explicit_disjoint_age_bands_keep_program_sessions_separate(self):
        import merger
        import processor
        parent = 'Arte en Familia/Art Among Family'
        younger, older = parent + ' (Ages 4–6)', parent + ' (Ages 7+)'
        self.assertPair(younger, older, True)
        self.assertFalse(merger.are_names_similar(younger, older))
        self.assertFalse(merger.are_names_similar(older, younger))
        self.assertPair(younger, parent + ' (Ages 4-6)', False)
        self.assertPair(older, parent + ' (Ages 7+)', False)
        self.assertPair(younger, parent + ' (Ages 6–9)', False)
        self.assertPair(older, parent + ' (Ages 9–12)', False)
        self.assertPair(younger, parent, False)
        self.assertPair(younger, 'Other Family Program (Ages 7+)', False)
        self.assertPair(parent + ' (Ages 9-4)', older, False)
        rows = [dict(name=n, location='Same museum', location_id=1,
                     url=url, start_date='2026-11-01', start_time='1pm',
                     end_date='', end_time='2pm') for n, url in
                ((younger, 'https://example.org/session/11740'),
                 (older, 'https://example.org/session/11750'))]
        for ordered in (rows, rows[::-1]):
            self.assertEqual(len(processor.group_event_occurrences(ordered)), 2)

    def test_bilingual_repeated_age_band_is_not_part_of_parent_identity(self):
        import merger
        import processor
        a = '親子藝術探索 (4–6歲)/Family Art Adventures in Mandarin (Ages 4–6)'
        b = '親子藝術探索 (7+歲)/Family Art Adventures in Mandarin (Ages 7+)'
        self.assertPair(a, b, True)
        for left, right in ((a, b), (b, a)):
            self.assertFalse(merger.are_names_similar(left, right))
            rows = [dict(name=n, location='Museum', location_id=1,
                         url='https://example.org/' + str(i), start_date='2026-11-21',
                         start_time='10:15am', end_date='', end_time='11:15am')
                    for i, n in enumerate((left, right))]
            self.assertEqual(len(processor.group_event_occurrences(rows)), 2)
        self.assertPair(a, a.replace('歲', '岁').replace('–', '-'), False)
        self.assertPair(a, b.replace('(7+歲)', '(4–6歲)'), False)
        self.assertPair(a, b.replace('Family Art Adventures', 'Other Family Adventures'), False)
        self.assertPair(a, b.replace('(7+歲)', '(6–9歲)').replace('(Ages 7+)', '(Ages 6–9)'), False)

    def test_explicit_exhibition_and_performance_parts(self):
        import merger
        a, b = 'Sarah Michelson: nowhere — Performance', 'Sarah Michelson: nowhere — Exhibition'
        self.assertPair(a, b, True)
        self.assertFalse(merger.are_names_similar(a, b))
        self.assertFalse(merger.are_names_similar(b, a))
        self.assertPair(a, 'Sarah Michelson: nowhere', False)
        self.assertPair(a, a.replace('Performance', 'Performances'), False)
        self.assertPair(a, 'Other Artist: nowhere — Exhibition', False)

    def test_named_tree_lighting_is_not_the_seasonal_display(self):
        import merger
        import processor
        a = 'Rockefeller Center Christmas Tree Lighting'
        b = 'Rockefeller Center Christmas Tree Display'
        for lighting in (a, 'Rockefeller Center Tree Lighting',
                         'Rockefeller Center Christmas Tree Lighting Ceremony'):
            self.assertPair(lighting, b, True)
            self.assertFalse(merger.are_names_similar(lighting, b))
        self.assertPair(a, 'Rockefeller Center Tree Lighting', False)
        self.assertPair(b, 'Rockefeller Center Christmas Tree', False)
        self.assertPair('Main Square Tree Lighting', 'Other Square Tree Display', False)
        self.assertPair('Tree Lighting', 'Tree Display', False)
        self.assertPair('Main Square Holiday Light Show', 'Main Square Tree Display', False)
        rows = [dict(name=n, location='Same place', location_id=1,
                     url='https://example.org/holiday-tree', start_date='2026-12-02',
                     start_time='', end_date=end, end_time='')
                for n, end in ((a, ''), (b, '2027-01-09'))]
        for ordered in (rows, rows[::-1]):
            grouped = processor.group_event_occurrences(ordered)
            self.assertEqual(len(grouped), 2)
            self.assertEqual(sorted(len(e['occurrences']) for e in grouped), [1, 1])

    def test_explicit_production_and_delivery_parts_remain_distinct(self):
        import merger
        import processor
        pairs = [
            ('Legally Blonde Jr Fall2026 — Tech and Dress Rehearsals',
             'Legally Blonde Jr Fall2026 — Performances'),
            ('Legally Blonde Jr Fall2026 — Enrollment and Rehearsal Course',
             'Legally Blonde Jr Fall2026 — Performances'),
            ('MODArts Dance Collective presents Move to Change — Live Concerts',
             'MODArts Dance Collective presents Move to Change — Online Dance Films'),
        ]
        for a, b in pairs:
            self.assertPair(a, b, True)
            self.assertFalse(merger.are_names_similar(a, b))
            rows = [dict(name=n, location='Same venue', location_id=1,
                         url='https://example.org/one-production', start_date='2026-10-10',
                         start_time='1pm', end_date='', end_time='3pm') for n in (a, b)]
            for ordered in (rows, rows[::-1]):
                self.assertEqual(len(processor.group_event_occurrences(ordered)), 2)
        self.assertPair('Musical — Performances', 'Musical', False)
        self.assertPair('Performance Workshop', 'Performance', False)
        self.assertPair('Alpha — Live Concerts', 'Beta — Online Dance Films', False)
        self.assertPair('Musical — Performance', 'Musical — Performances', False)

    def test_explicit_registration_sections_survive_parent_and_same_clock(self):
        import itertools
        import merger
        import processor
        names = ('Center & Throw — Sawyer section 1974642',
                 'Center & Throw — Sawyer section 1974647',
                 'Center & Throw')
        for left, right in itertools.combinations(names, 2):
            self.assertPair(left, right, True)
            self.assertFalse(merger.are_names_similar(left, right))
        self.assertPair(names[0], 'Center and Throw — Sawyer section 1974642', False)
        self.assertPair('Pottery — Registration section ID 123456',
                        'Pottery — Registration section ID 654321', True)
        self.assertPair('Pottery Section 2', 'Pottery', False)
        self.assertPair('Pottery 1974642', 'Pottery', False)
        rows = [dict(name=n, location='Same studio', location_id=1,
                     url='https://example.org/classes', start_date='2026-10-10',
                     start_time='1pm', end_date='', end_time='3pm') for n in names]
        for ordered in itertools.permutations(rows):
            self.assertEqual(len(processor.group_event_occurrences(list(ordered))), 3)

    def test_distinct_named_tour_subjects(self):
        import itertools
        import merger
        import processor
        names = ('Spooky Snug Harbor Tour', 'Sailor’s Snug Harbor Historical Tour',
                 'Sailors’ Snug Harbor Art & Architecture Tour')
        for left, right in itertools.combinations(names, 2):
            self.assertPair(left, right, True)
            self.assertFalse(merger.are_names_similar(left, right))
        self.assertPair(names[0], '2026 Spooky Snug Harbor Tour', False)
        self.assertPair(names[1], "Sailors' Snug Harbor Historical Tour", False)
        self.assertPair(names[0], 'Snug Harbor Tour', False)
        self.assertPair('Haunted Historical Old Town Tour', 'Historical Old Town Tour', False)
        self.assertPair('Spooky Museum Tour', 'Historical Museum Tour', False)
        self.assertPair(names[0], 'OHNY Weekend: Snug Harbor Tours', True)
        self.assertPair(names[0], 'Spooky Weekend: Snug Harbor Tours', False)
        self.assertPair(names[0], 'Weekend Snug Harbor Tour', False)
        self.assertFalse(merger.are_names_similar(names[0], 'OHNY Weekend: Snug Harbor Tours'))
        rows = [dict(name=n, location='Same place', location_id=1,
                     url='https://example.org/calendar', start_date='2026-10-10',
                     start_time='1pm', end_date='', end_time='2pm') for n in names]
        for ordered in itertools.permutations(rows):
            self.assertEqual(len(processor.group_event_occurrences(list(ordered))), 3)

    def test_different_numbered_courses(self):
        self.assertPair('Master Composter Certification | Course 1: Compost in Context | Virtual Session',
                        'Master Composter Certification | Course 2: Introduction to Composting | Virtual Session', True)
        self.assertPair('Master Composter Certification | Course 1: Compost in Context',
                        'Master Composter Certification | Course 1: Compost in Context | Virtual Session', False)
        self.assertPair('Alpha Course 1: Painting', 'Beta Course 2: Painting', False)
        self.assertPair('Master Composter Certification | Course 3: Soil Health | Virtual Session',
                        'Master Composter Certification | Course 3: Soil Health | In-person', True)

    def test_named_parent_afterparty(self):
        self.assertPair('Halloween Rock Show & DJ Masquerade - KAMIJO',
                        'Halloween Rock Show & DJ Masquerade: AFTER PARTY - KAMIJO', True)
        self.assertPair('30th Anniversary Benefit Afterparty', 'Rhizome’s 30th Anniversary Benefit', True)
        self.assertPair('Speed Friending', 'Speed Friending (+ After Party)', False)
        self.assertPair('The Faggot Fête', 'The Faggots Fête: Nightboat Gala Afterparty', False)
        self.assertPair('Benefit Afterparty', 'Benefit After Party', False)

    def test_sports_watch_party_and_dance_series(self):
        self.assertPair('Ritmos: Salsa Sundays Colombian Latin Dance Party NYC',
                        'Mexico vs USA Soccer Game Watch Party at Ritmos 60 Salsa Bar', True)
        self.assertPair('Mexico vs USA Soccer Game Watch Party',
                        'Mexico vs USA Soccer Game Watch Party at Ritmos 60 Salsa Bar', False)
        self.assertPair('Mexico vs USA Soccer Game Watch Party at Ritmos 60 Salsa Bar',
                        'Ritmos: Sabado de Parranda - Colombian Salsa, Vallenato Reggaeton Party NYC', True)
        self.assertPair('Anime Watch Party', 'Anime Dance Party', False)

    def test_branded_boats(self):
        self.assertPair('Woodshop Boat powered by Elsewhere', 'MAታA Boat Party - Powered by Elsewhere', True)
        self.assertPair('Elsewhere Presents: MAትA Boat Party w/ Father, DJ Nico, Lilla, EDEN + more',
                        'Elsewhere Presents: Woodshop Boat', True)
        self.assertPair('Woodshop Boat powered by Elsewhere', 'Elsewhere Presents: Woodshop Boat', False)
        self.assertPair('NYC Boat Party: Reggaeton / Hip-Hop / House Music on Multi-Level Yacht',
                        'NYC Boat Party: Reggaeton / Hip-Hop / House - Multi-Level Yacht', False)
        self.assertPair('Presenter Presents: House Music Boat', 'Presenter Presents: Reggaeton Boat', False)

    def test_unquoted_art_class_subject(self):
        self.assertPair('Keith Haring (2hr:Williamsburg:Loft)', '"With The Waves" (2hr:Williamsburg:Loft)', True)
        self.assertPair('Sunset Over Manhattan (2hr:Midtown:Main)', '"Starry Night Over Manhattan" (2hr:Midtown:Main)', True)
        self.assertPair('Keith Haring (2hr:Williamsburg:Loft) $40.00', '"With The Waves" (2hr:Williamsburg:Loft) $35.00', True)
        self.assertPair('"Blue Wave" (2hr:Midtown:Main)', 'Blue Waves (2hr:Midtown:Main)', False)
        self.assertPair('Café Sunset (2hr:Midtown:Main)', 'Cafe Sunset Painting (2hr:Midtown:Main)', False)
        self.assertPair('Miles Davis (18+)', 'John Coltrane (18+)', False)

    def test_explicit_webinar_audiences(self):
        self.assertPair('ONLINE | Parsons Summer Intensive Studies 2027 | College & Adult Webinars',
                        'ONLINE | Parsons Summer Intensive Studies 2027 | Pre-College Webinars', True)
        self.assertPair('Summer Studies | Pre-College Webinars', 'Summer Studies Webinars', False)

    def test_weekday_holiday_editions(self):
        self.assertPair('Friday Night Halloween Party NYC @ American Whiskey | Top Halloween Event',
                        'Saturday Night Halloween Party NYC @ American Whiskey | Top Singles Event', True)
        self.assertPair('The Cafe Wha? House Band | Friday Set 1 | 9:00 pm',
                        'The Cafe Wha? House Band | Wednesday Set 1 | 9:00 pm', False)
        self.assertPair('Halloween Party Friday and Saturday', 'Saturday Halloween Party', False)

    def test_ambiguous_pipes_and_presenters_remain_eligible(self):
        self.assertPair('Schneider Concerts Presents | Erinys Quartet', 'Schneider Concerts Presents | Tesla Quartet', False)
        self.assertPair('Jubilee, nextdimensional, BELLA, Jawar | Dead Letter No.9',
                        'Jubilee, nextdimensional, Bella De León, Jawar | Dead Letter No.9', False)
        self.assertPair('NEW DATE - Ensemble Concert', 'SOLD OUT - Ensemble Concert', False)

    def test_named_halloween_mixology_is_not_regular_class(self):
        regular='Ice Cream Cocktail Mixology Class - Queens'
        themed='Ice Cream Cocktail Mixology: Boo-zy Halloween Cocktails in Queens'
        self.assertPair(regular,themed,True)
        self.assertPair(themed,'Ice Cream Cocktail Mixology: Halloween Cocktails',False)
        self.assertPair('Halloween Art Class','Art Class',False)
        import merger
        self.assertTrue(merger.is_false_positive(regular,themed))
        import processor
        rows=[dict(name=n,location='Barlour',location_id=1,url='https://example.org/class',
                   start_date='2026-10-02',start_time='3pm',end_date='',end_time='4:30pm')
              for n in (regular,themed)]
        for ordered in (rows,rows[::-1]):
            self.assertEqual(len(processor.group_event_occurrences(ordered)),2)
            self.assertFalse(merger.are_names_similar(ordered[0]['name'],ordered[1]['name']))

    def test_named_class_variants(self):
        self.assertPair('30 – Minute Lunchtime Meditation (Chelsea Center)',
                        '30-Minute After-Work Meditation (Chelsea Center)', True)
        self.assertPair('Sunday General Program Class (Chelsea Center)',
                        'Tweens Class (Chelsea Center)', True)
        self.assertPair('Sunday General Program (Chelsea Center)',
                        'Tweens Class – note special time (Chelsea Center)', True)
        self.assertPair('Cat Toy "Take & Make" - The Great Give Back (Grades 3-5)',
                        'Dog Toy "Take & Make" - The Great Give Back (Grades 3-5)', True)
        self.assertPair('Tweens Meditation Class (Chelsea Center)',
                        'Tweens Class (Chelsea Center)', False)
        self.assertPair('30-Minute Lunchtime Meditation (Chelsea Center)',
                        'Lunchtime Meditation', False)


if __name__ == '__main__':
    unittest.main()
