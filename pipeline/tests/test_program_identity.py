"""Exhibition runs must not become the schedules of talks about them."""
import io
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger
from program_identity import program_profile, conflicting_program_profiles, volunteer_program_mismatch


EXHIBITION = 'Taking a Broad View: Portrait Photography from the Collection'
TALK = ('Taking a Broad View — An Illustrated Talk by Chief Curator and '
        'Museum Director Susan Chevlowe')


class VolunteerProgramTests(unittest.TestCase):
    def test_explicit_registration_and_child_program_stay_distinct(self):
        program = 'Creative Wednesdays'
        volunteer = 'Volunteer Registration for Creative Wednesdays'
        for left, right in ((program, volunteer), (volunteer, program)):
            self.assertTrue(volunteer_program_mismatch(left, right))
            self.assertTrue(merger.is_false_positive(left, right))
            self.assertFalse(merger.are_names_similar(left, right))

    def test_presentation_changes_do_not_erase_the_distinction(self):
        self.assertTrue(volunteer_program_mismatch(
            'VOLUNTEER REGISTRATION FOR: Creative Wednesdays', 'Creative Wednesdays!'))

    def test_registration_aliases_and_volunteer_programs_are_not_split(self):
        for left, right in (
            ('Volunteer Registration for Creative Wednesdays',
             'Volunteer Registration for Creative Wednesdays!'),
            ('Creative Wednesdays', 'Registration for Creative Wednesdays'),
            ('Volunteer Appreciation', 'Volunteer Appreciation'),
            ('Volunteer Registration for Creative Wednesdays', 'Creative Fridays'),
            ('Volunteer Registration for Creative Wednesdays', 'Creative Wednesdays: Painting'),
            ('', 'Volunteer Registration for'),
        ):
            with self.subTest(left=left, right=right):
                self.assertFalse(volunteer_program_mismatch(left, right))


class ProgramProfileTests(unittest.TestCase):
    SPAN = [('2026-10-05', '', '2027-01-24', '')]
    SESSION = [('2026-10-06', '2pm', None, '3pm')]

    def test_explicit_opposite_formats_and_schedules(self):
        exhibition = program_profile(['Art', 'Exhibition', 'Format'], self.SPAN)
        talk = program_profile(['Talk', 'Photography'], self.SESSION)
        self.assertTrue(conflicting_program_profiles(exhibition, talk))
        self.assertTrue(conflicting_program_profiles(talk, exhibition))
        self.assertFalse(conflicting_program_profiles(exhibition, exhibition))
        self.assertFalse(conflicting_program_profiles(talk, talk))

    def test_uncertain_or_companion_representations_remain_undecided(self):
        cases = [([], self.SPAN), (['Tour'], self.SPAN),
                 (['Exhibition', 'Tour'], self.SESSION),
                 (['Tour', 'Talk'], self.SESSION),
                 (['Tour'], [('2026-10-06', '', None, '')]),
                 (['Exhibition', 'Talk'], self.SPAN),
                 (['Exhibition', 'Festival'], self.SPAN),
                 (['Exhibition'], self.SPAN + self.SESSION),
                 (['Talk'], self.SPAN + self.SESSION),
                 (['Exhibition'], [('2026-10-05', '', '2027-01-24', '5pm')]),
                 (['Talk'], [('2026-10-06', '', None, '')]),
                 (['Talk'], [('2026-10-06', 'tba', None, '')]),
                 (['Talk'], [('2026-10-06', '2', None, '')]),
                 (['Exhibition'], [('2026-10-06', '', None, '')]),
                 (['Talk'], [('2026-10-06', '2pm', '2026-10-08', '')]),
                 (['Talk'], []), (['Exhibition'], [(None, '', None, '')])]
        for formats, occurrences in cases:
            with self.subTest(formats=formats, occurrences=occurrences):
                self.assertIsNone(program_profile(formats, occurrences))

    def test_strict_slot_fallback_cannot_reunite_opposite_profiles(self):
        # URL identity and post-merge exact-name dedup both require shared slots.
        span_slots = {(str(o[0]), o[1] or '') for o in self.SPAN}
        session_slots = {(str(o[0]), o[1] or '') for o in self.SESSION}
        self.assertFalse(span_slots & session_slots)
        # Even a talk on the exhibition opening day cannot share its untimed slot.
        session_slots = {('2026-10-05', '2pm')}
        self.assertIsNone(merger._match_by_url_identity(
            'Same title', 'https://example.org/program', 1, 1, session_slots,
            {(1, 'https://example.org/program'): [dict(id=1, name='Same title',
                slots=span_slots, location_id=1)]}, {}, set(), {}))


class ProgramMergeTests(unittest.TestCase):
    def run_merge(self, incoming='Exhibition', *, companion='Talk', tier='venue', exact=False,
                  old=False, batch=False, reviewed=False, unknown=False,
                  no_overlap=False, mixed=False, correct_candidate=True,
                  named_companion=None, exhibition_shape=None, shared_slot=False):
        today = date.today()
        schedules = {
            'Exhibition': [(today, '', today + timedelta(days=60), '')],
            companion: [(today + timedelta(days=1), '2pm', None, '3pm')],
        }
        names = {'Exhibition': EXHIBITION, companion: TALK if companion == 'Talk'
                 else EXHIBITION + ' Gallery Tour'}
        if named_companion:
            names[companion] = EXHIBITION + ': ' + named_companion
        if exhibition_shape == 'timed':
            schedules['Exhibition'] = [(today, '12pm', today + timedelta(days=60), '5pm')]
        elif exhibition_shape == 'discrete':
            schedules['Exhibition'] = [(today + timedelta(days=d), '2pm', None, '5pm')
                                      for d in (0, 1, 8)]
        elif exhibition_shape == 'mixed':
            schedules['Exhibition'].append(schedules[companion][0])
        if shared_slot:
            schedules['Exhibition'].append(schedules[companion][0])
        if exact:
            names = dict.fromkeys(names, 'Taking a Broad View')
        opposite = companion if incoming == 'Exhibition' else 'Exhibition'
        # Wrong target first; rejection must keep searching for the right one.
        events = {} if batch else {
            10: dict(name=names[opposite], typ=opposite, occ=list(schedules[opposite])),
            20: dict(name=names[incoming], typ=incoming, occ=list(schedules[incoming])),
        }
        if not batch and not correct_candidate:
            del events[20]
        if no_overlap:
            for event in events.values():
                event['occ'] = [(o[0] + timedelta(days=70), o[1],
                                 o[2] + timedelta(days=70) if o[2] else None, o[3])
                                for o in event['occ']]
        if unknown:
            events[10]['typ'] = None
        if mixed:
            events[10]['occ'].extend(schedules[incoming])
        source_types = [incoming, opposite, incoming] if batch else [incoming]
        sources = [(100 + i, names[typ], None, 'Program description.', '📅',
                    'Museum', None, 1 if tier == 'venue' else None,
                    f'https://example.org/source-{i}', 2, None, None, 3)
                   for i, typ in enumerate(source_types)]
        cursor = MagicMock(lastrowid=30)
        def execute(query, params=None):
            rows, one = [], None
            if 'SELECT ce.id, ce.name' in query:
                rows = sources
            elif 'SELECT DISTINCT e.id, e.name, e.location_id' in query:
                rows = [(eid, e['name'], 1 if tier == 'venue' else None,
                         None, None, 'Museum' if tier == 'venue' else '',
                         2 if tier == 'website' else 9, 0) for eid, e in events.items()]
            elif 'SELECT event_id, start_date, start_time, end_date' in query:
                rows = [(eid, *o[:3]) for eid, e in events.items() for o in e['occ']]
            elif 'SELECT e.event_type, eo.start_date' in query:
                event = events[params[0]]
                rows = [(event['typ'], *o) for o in event['occ']]
            elif 'FROM crawl_event_occurrences' in query:
                rows = [(100+i, *o, 0) for i, typ in enumerate(source_types)
                        for o in schedules[typ]]
            elif 'SELECT crawl_event_id, tag FROM crawl_event_tags' in query:
                rows = [(100+i, typ) for i, typ in enumerate(source_types)]
            elif 'SELECT location_id FROM events WHERE id' in query:
                one = (1 if tier == 'venue' else None,)
            elif 'SELECT location_name, location_id FROM events WHERE id' in query:
                one = ('Museum', 1 if tier == 'venue' else None)
            elif 'SELECT description, emoji, name, short_name, event_type' in query:
                e = events[params[0]]
                one = ('Program description.', '📅', e['name'], None, e['typ'])
            elif 'INSERT INTO events (' in query:
                cursor.lastrowid = 30 + len(events)
                events[cursor.lastrowid] = dict(name=params[0], typ=None, occ=[])
            cursor.fetchall.return_value = rows
            cursor.fetchone.return_value = one
        cursor.execute.side_effect = execute
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(merger, 'EditLogger', None))
            stack.enter_context(patch.object(merger.reviewed_event_identity, 'load_index', return_value={}))
            stack.enter_context(patch.object(merger.venue_overrides, 'load_rules', return_value=[]))
            stack.enter_context(patch.object(merger, 'get_active_date_window',
                                            return_value=(today, today + timedelta(days=90))))
            if old:
                stack.enter_context(patch.object(merger, 'conflicting_program_profiles', return_value=False))
                stack.enter_context(patch.object(merger, 'exhibition_companion_mismatch', return_value=False))
            if reviewed:
                stack.enter_context(patch.object(merger.reviewed_event_identity, 'match', return_value=10))
            database = stack.enter_context(patch.object(merger, 'db'))
            database.build_tag_ancestor_map.return_value = ({}, set())
            database.archive_dead_source_events.return_value = (0, [])
            database.insert_event_occurrences.side_effect = lambda cur, eid, occ, **kw: events[eid]['occ'].extend(o[:4] for o in occ)
            stack.enter_context(patch.object(merger, '_deduplicate_same_name_events', return_value=0))
            stack.enter_context(patch.object(merger, 'compute_voted_tags', return_value=[]))
            for helper in ('_merge_occurrences_into_event', '_merge_grouped_event_urls',
                           'refresh_source_metadata', 'refresh_source_session_details'):
                stack.enter_context(patch.object(merger, helper))
            result = merger.merge_crawl_events(cursor, MagicMock(), website_ids=[2])
        links = [call.args[1] for call in cursor.execute.call_args_list
                 if 'INSERT IGNORE INTO event_sources' in call.args[0]]
        return result, links

    def test_real_names_reproduce_old_cross_publisher_merge(self):
        self.assertTrue(merger.are_names_similar(EXHIBITION, TALK))
        self.assertEqual(self.run_merge(old=True, correct_candidate=False),
                         ((0, 1), [(10, 100)]))
        result, links = self.run_merge(correct_candidate=False)
        self.assertEqual(result, (1, 0))
        self.assertNotEqual(links[0][0], 10)

    def test_both_directions_choose_correct_canonical_across_matching_tiers(self):
        for incoming in ('Exhibition', 'Talk'):
            for tier in ('venue', 'website'):
                for exact in (False, True):
                    with self.subTest(incoming=incoming, tier=tier, exact=exact):
                        self.assertEqual(self.run_merge(incoming, tier=tier, exact=exact),
                                         ((0, 1), [(20, 100)]))

    def test_exact_name_recurring_fallback_cannot_bypass_guard(self):
        self.assertEqual(self.run_merge(exact=True, no_overlap=True)[1], [(20, 100)])

    def test_same_batch_unclassified_rows_remain_separate_in_both_orders(self):
        for incoming in ('Exhibition', 'Talk'):
            with self.subTest(incoming=incoming):
                result, links = self.run_merge(incoming, batch=True)
                self.assertEqual(result, (2, 1))
                self.assertNotEqual(links[0][0], links[1][0])
                self.assertEqual(links[0][0], links[2][0])

    def test_unknown_and_mixed_profiles_do_not_block_existing_matches(self):
        for kwargs in (dict(unknown=True), dict(mixed=True)):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.run_merge(exact=True, **kwargs)[1], [(10, 100)])

    def test_explicit_reviewed_identity_remains_authoritative(self):
        self.assertEqual(self.run_merge(reviewed=True)[1], [(10, 100)])

    def test_tours_choose_their_own_owner_in_both_directions_and_tiers(self):
        for incoming in ('Exhibition', 'Tour'):
            for tier in ('venue', 'website'):
                for exact in (False, True):
                    with self.subTest(incoming=incoming, tier=tier, exact=exact):
                        self.assertEqual(self.run_merge(incoming, companion='Tour',
                            tier=tier, exact=exact)[1], [(20, 100)])

    def test_tour_guard_reproduces_old_failure_and_covers_batch_and_fallback(self):
        self.assertEqual(self.run_merge(companion='Tour', old=True,
                                       correct_candidate=False)[1], [(10, 100)])
        result, links = self.run_merge(companion='Tour', correct_candidate=False)
        self.assertEqual(result, (1, 0))
        self.assertNotEqual(links[0][0], 10)
        self.assertEqual(self.run_merge(companion='Tour', exact=True,
                                       no_overlap=True)[1], [(20, 100)])
        for incoming in ('Exhibition', 'Tour'):
            result, links = self.run_merge(incoming, companion='Tour', batch=True)
            self.assertEqual(result, (2, 1))
            self.assertNotEqual(links[0][0], links[1][0])
            self.assertEqual(links[0][0], links[2][0])

    def test_named_companions_keep_owners_with_mixed_timed_and_discrete_parents(self):
        for label, kind in (('Opening Reception', 'Mixer'), ('Closing Weekend', 'Mixer'),
                            ('Gallery Tour', 'Tour')):
            for shape in ('mixed', 'timed', 'discrete'):
                for incoming in ('Exhibition', kind):
                    with self.subTest(label=label, shape=shape, incoming=incoming):
                        self.assertEqual(self.run_merge(incoming, companion=kind,
                            named_companion=label, exhibition_shape=shape,
                            shared_slot=True)[1], [(20, 100)])

    def test_named_reception_same_batch_keeps_parent_span(self):
        for incoming in ('Exhibition', 'Mixer'):
            result, links = self.run_merge(incoming, companion='Mixer',
                named_companion='Opening Reception', exhibition_shape='mixed', batch=True)
            self.assertEqual(result, (2, 1))
            self.assertNotEqual(links[0][0], links[1][0])
            self.assertEqual(links[0][0], links[2][0])

    def test_tours_do_not_conflict_with_talks_or_ambiguous_formats(self):
        tour = program_profile(['Tour'], ProgramProfileTests.SESSION)
        self.assertEqual(tour, 'Tour')
        self.assertFalse(conflicting_program_profiles(tour, 'Talk'))
        self.assertFalse(conflicting_program_profiles(tour, tour))
        self.assertEqual(self.run_merge(companion='Tour', mixed=True, exact=True)[1], [(10, 100)])
        self.assertEqual(self.run_merge(companion='Tour', reviewed=True)[1], [(10, 100)])


if __name__ == '__main__':
    unittest.main()
