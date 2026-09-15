"""Reviewed icon continuity must not turn enrichment into semantic approval."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from event_icons import input_hash
from event_icon_policy import (IMPLIED_TAGS, context_hash, context_matches,
                               input_matches, metadata, seed_review_baseline)
from event_icon_assignments import (desired_assignment, export_contexts, export_icon,
                                    manual_assignment, merge_manual_decisions,
                                    retained_assignment, sync_assignments)
from event_icon_review import (catalog_revision, collect_opportunities, make_packets,
                               refresh_review_state, review_reason, validate_decisions,
                               validate_tag_additions)


EVENT = dict(id=1, name='Beginner Go', description='Learn to play Go with boards and stones.',
             tags=['Go'], short_name='Beginner Go', emoji='⚫', event_type='Class',
             location_name='Library', sublocation='Meeting Room', venue='Library',
             address='1 Main Street', source='Library Programs', urls=['https://example.com/go'],
             **{IMPLIED_TAGS: ['Board Games', 'Games']})
APPROVED = [dict(tag='Beginners', reason='The reviewed class is explicitly introductory.',
                 evidence=['The title says Beginner Go.'])]


class IconPolicyTests(unittest.TestCase):
    def packet_and_decisions(self, event=None, icon='game-go', action='assign', additions=()):
        event = copy.deepcopy(EVENT if event is None else event)
        packet = make_packets([event], {})[0][0]
        decisions = dict(catalog_revision=packet['catalog_revision'], decisions=[dict(
            event_id=event['id'], input_hash=packet['events'][0]['input_hash'],
            icon_id=icon, decision=action, reason='Go is the activity being taught.',
            evidence=['The description identifies playing Go with boards and stones.'],
            opportunities=[], harmless_tag_additions=list(additions))])
        return event, packet, decisions

    def reviewed(self, **kwargs):
        event, packet, decisions = self.packet_and_decisions(**kwargs)
        return validate_decisions(packet, decisions, {event['id']: event}, {})[0]

    def enriched(self, *tags, **changes):
        return dict(copy.deepcopy(EVENT), tags=EVENT['tags'] + list(tags), **changes)

    def assert_accepted(self, event, row):
        self.assertTrue(input_matches(event, row))
        self.assertTrue(context_matches(event, row))
        self.assertIsNone(review_reason(event, row, catalog_revision()))
        self.assertEqual(retained_assignment(event, row), row)
        self.assertEqual(desired_assignment(event, row), row)
        self.assertEqual(export_icon(event, row), row['icon_id'])

    def test_frozen_ancestors_preserve_review_without_advancing_hashes(self):
        row = self.reviewed()
        before = copy.deepcopy(row)
        self.assert_accepted(self.enriched('Board Games', 'Games'), row)
        self.assertNotEqual(row['input_hash'], input_hash(self.enriched('Games')))
        self.assertEqual(row, before)
        self.assertEqual(metadata(row)['tag_enrichment']['context']['tags'], ['Go'])

    def test_current_auxiliary_permissions_cannot_expand_frozen_approval(self):
        row = self.reviewed()
        event = self.enriched('Documentary', **{IMPLIED_TAGS: ['Documentary', 'Games']})
        self.assertFalse(input_matches(event, row))
        self.assertIsNone(export_icon(event, row))
        self.assertEqual(review_reason(event, row, catalog_revision()), 'changed-or-deferred')

    def test_explicit_reviewed_addition_is_narrow_and_preserves_evidence(self):
        row = self.reviewed(additions=APPROVED)
        self.assert_accepted(self.enriched('Beginners', 'Games'), row)
        self.assertFalse(input_matches(self.enriched('Advanced'), row))
        self.assertFalse(input_matches(self.enriched('Education'), row))
        self.assertEqual(metadata(row)['tag_enrichment']['approved_additions'], APPROVED)

    def test_addition_requires_reason_evidence_and_exact_unique_tag(self):
        for value in [None, ['Beginners'], [dict(tag='')], [dict(tag=' Beginners ', reason='x', evidence=['x'])],
                      [dict(tag='Beginners', evidence=['x'])], [dict(tag='Beginners', reason='x', evidence=[])],
                      APPROVED + APPROVED]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tag_additions(value)

    def test_meaningful_additions_and_any_removal_require_review(self):
        row = self.reviewed(additions=APPROVED)
        for tag in ['Chess', 'Documentary', 'Watch Party', 'Kids', 'Advanced', 'Stencils', 'Cello']:
            with self.subTest(tag=tag):
                event = self.enriched(tag)
                self.assertFalse(input_matches(event, row))
                self.assertIsNone(export_icon(event, row))
                self.assertTrue(retained_assignment(event, row)['review_required'])
        for tags in [[], ['Games'], ['Beginners', 'Games']]:
            with self.subTest(tags=tags):
                self.assertFalse(input_matches(dict(EVENT, tags=tags), row))

    def test_safe_tags_do_not_hide_activity_or_full_context_changes(self):
        row = self.reviewed()
        for field, value in [('name', 'Watch Go'), ('description', 'A film about Go.'),
                             ('event_type', 'Screening'), ('venue', 'Other Library'),
                             ('sublocation', 'Auditorium'), ('source', 'Other organizer'),
                             ('urls', ['https://example.com/film'])]:
            with self.subTest(field=field):
                event = self.enriched('Games', **{field: value})
                self.assertFalse(context_matches(event, row))
                self.assertIsNotNone(review_reason(event, row, catalog_revision()))
                self.assertIsNone(export_icon(event, row))

    def test_deferred_and_merge_review_flags_are_sticky(self):
        row = self.reviewed()
        merged = merge_manual_decisions(EVENT, [row])
        for pending in [dict(row, review_required=1), merged,
                        self.reviewed(icon=None, action='defer')]:
            with self.subTest(origin=pending['origin']):
                event = self.enriched('Games')
                self.assertTrue(retained_assignment(event, pending)['review_required'])
                self.assertIsNone(export_icon(event, pending))
                self.assertEqual(review_reason(event, pending, catalog_revision()), 'changed-or-deferred')
                self.assertEqual(seed_review_baseline(EVENT, pending), pending)

    def test_reviewed_fallback_stays_reviewed_without_heuristic_assignment(self):
        row = self.reviewed(icon=None, action='fallback')
        with patch('event_icon_assignments.propose', side_effect=AssertionError('No classifier')):
            self.assert_accepted(self.enriched('Games'), row)
        self.assertIsNone(row['icon_id'])

    def test_unknown_icons_and_legacy_rules_gain_no_enrichment_exception(self):
        row = self.reviewed()
        self.assertIsNone(export_icon(self.enriched('Games'), dict(row, icon_id='missing-icon')))
        rule = desired_assignment(dict(EVENT, name='Go Club'))
        self.assertFalse(input_matches(dict(EVENT, name='Go Club', tags=['Go', 'Games']), rule))

    def test_exact_legacy_baseline_seed_is_idempotent_and_non_blessing(self):
        row = self.reviewed()
        info = metadata(row)
        del info['tag_enrichment']
        legacy = dict(row, evidence_json=json.dumps(info))
        seeded = seed_review_baseline(EVENT, legacy)
        self.assertIn('tag_enrichment', metadata(seeded))
        self.assertEqual(seeded['input_hash'], legacy['input_hash'])
        self.assertEqual(seed_review_baseline(EVENT, seeded), seeded)
        self.assertEqual(seed_review_baseline(self.enriched('Games'), legacy), legacy)
        self.assertEqual(seed_review_baseline(dict(EVENT, venue='Elsewhere'), legacy), legacy)
        self.assertEqual(seed_review_baseline(EVENT, dict(legacy, review_required=1)),
                         dict(legacy, review_required=1))
        self.assertEqual(seed_review_baseline(EVENT, dict(legacy, evidence_json='[]')),
                         dict(legacy, evidence_json='[]'))
        mapping_legacy = dict(row, evidence_json=copy.deepcopy(info))
        before = copy.deepcopy(mapping_legacy)
        seed_review_baseline(EVENT, mapping_legacy)
        self.assertEqual(mapping_legacy, before)

    def test_refresh_seeds_only_current_catalog_and_discovery_reviews(self):
        row = self.reviewed()
        for change, seeds in [({}, True), ({'catalog_revision': 'old'}, False),
                              ({'opportunity_review_version': 0}, False)]:
            info = metadata(row)
            del info['tag_enrichment']
            info.update(change)
            legacy = dict(row, evidence_json=json.dumps(info))
            with patch('event_icon_review.fetch_review_events', return_value=[copy.deepcopy(EVENT)]), \
                 patch('event_icon_review.load_assignments', return_value={1: legacy}), \
                 patch('event_icon_review.require_lock'), patch('event_icon_review.save') as save:
                stats = refresh_review_state(None, apply=True)
            self.assertEqual(bool(stats.get('baselines_added')), seeds)
            self.assertEqual(save.called, seeds)

    def test_refresh_keeps_safe_enrichment_but_flags_full_context_change(self):
        for origin in ['agent', 'manual']:
            row = dict(self.reviewed(), origin=origin)
            for event, invalidated in [(self.enriched('Games'), False),
                                       (self.enriched('Games', event_type='Screening'), True)]:
                with self.subTest(origin=origin, event_type=event['event_type']), \
                     patch('event_icon_review.fetch_review_events', return_value=[event]), \
                     patch('event_icon_review.load_assignments', return_value={1: row}), \
                     patch('event_icon_review.require_lock'), patch('event_icon_review.save') as save:
                    stats = refresh_review_state(None, apply=True)
                self.assertEqual(bool(stats.get('invalidated')), invalidated)
                self.assertEqual(save.called, invalidated)
                if invalidated:
                    self.assertTrue(save.call_args.args[1]['review_required'])

    def test_full_context_manual_choice_is_protected_but_not_immortal(self):
        row = manual_assignment(EVENT, 'game-go', 'Human review')
        changed = dict(EVENT, event_type='Screening')
        self.assertIsNone(export_icon(changed, row))
        self.assertEqual(review_reason(changed, row, catalog_revision()), 'changed-context')
        self.assertEqual(row['icon_id'], 'game-go')

    def test_stale_packet_rejects_even_approved_enrichment(self):
        event, packet, choices = self.packet_and_decisions(additions=APPROVED)
        for current in [self.enriched('Games'), self.enriched('Beginners')]:
            with self.subTest(tags=current['tags']), self.assertRaises(ValueError):
                validate_decisions(packet, choices, {1: current}, {})
        row = validate_decisions(packet, choices, {1: event}, {})[0]
        self.assertEqual(validate_decisions(packet, choices, {1: event}, {1: row}), [row])

    def test_unhashed_packet_auxiliary_cannot_grant_new_permissions(self):
        event, packet, choices = self.packet_and_decisions()
        packet['events'][0]['event'][IMPLIED_TAGS].append('Documentary')
        row = validate_decisions(packet, choices, {1: copy.deepcopy(EVENT)}, {})[0]
        self.assertNotIn('Documentary', metadata(row)['tag_enrichment']['implied_tags'])
        self.assertFalse(input_matches(self.enriched('Documentary'), row))

    def test_catalog_and_discovery_reviews_still_reopen(self):
        row = self.reviewed()
        self.assertEqual(review_reason(self.enriched('Games'), row, 'changed'), 'changed-catalog')
        info = metadata(row)
        info['opportunity_review_version'] = 0
        self.assertEqual(review_reason(self.enriched('Games'), dict(row, evidence_json=json.dumps(info)),
                                       catalog_revision()), 'icon-opportunities')

    def test_opportunity_report_preserves_safe_reviews_and_excludes_material_changes(self):
        event, packet, choices = self.packet_and_decisions()
        opportunity = dict(concept='game-teaching-board', category='equipment', label='Teaching board',
                           visual='An upright board with black and white stones.',
                           rationale='Communicates instruction.', existing_alternative='Go stones omit teaching.',
                           evidence=['The class teaches the game.'])
        choices['decisions'][0]['opportunities'] = [opportunity]
        row = validate_decisions(packet, choices, {1: event}, {})[0]
        good = collect_opportunities([self.enriched('Games')], {1: row})
        self.assertEqual(good['reviewed_events'], 1)
        self.assertEqual(good['concept_count'], 1)
        self.assertEqual(metadata(row)['opportunities'], [opportunity])
        bad = collect_opportunities([self.enriched('Watch Party')], {1: row})
        self.assertEqual(bad['stale_reviews_excluded'], 1)
        self.assertEqual(bad['concept_count'], 0)

    def test_export_requires_full_context_for_baseline_and_hydrates_historical_ids(self):
        row = self.reviewed()
        thin = {k: EVENT[k] for k in ('id', 'name', 'description', 'tags')}
        self.assertIsNone(export_icon(thin, row))
        self.assertEqual(export_icon(EVENT, row), 'game-go')
        rows = {1: row, 2: dict(row, event_id=2, review_required=1),
                3: dict(row, event_id=3, icon_id=None)}
        with patch('event_icon_assignments.fetch_events', return_value=[thin]) as fetch, \
             patch('event_icon_assignments.hydrate_contexts', return_value=[copy.deepcopy(EVENT)]) as hydrate:
            contexts = export_contexts('cursor', rows)
        fetch.assert_called_once_with('cursor', [1])
        hydrate.assert_called_once_with('cursor', [thin])
        self.assertEqual(contexts[1], EVENT)

    def test_default_maintenance_counts_current_policy_icons_with_full_context(self):
        row = self.reviewed()
        thin = {k: EVENT[k] for k in ('id', 'name', 'description', 'tags')}
        with patch('event_icon_assignments.fetch_events', return_value=[thin]), \
             patch('event_icon_assignments.hydrate_contexts', return_value=[copy.deepcopy(EVENT)]), \
             patch('event_icon_assignments.load_assignments', return_value={1: row}):
            self.assertEqual(sync_assignments('cursor'),
                             {'events': 1, 'unchanged': 1, 'assigned': 1})

    def test_actual_export_hydration_has_no_active_window_gate_and_detects_format_change(self):
        class Cursor:
            def __init__(self, event_type):
                self.queries = []
                self.event_type = event_type

            def execute(self, query, params):
                self.queries.append((query, params))

            def fetchall(self):
                if len(self.queries) == 1:
                    return [(99, EVENT['name'], EVENT['description'])]
                if len(self.queries) == 2:
                    return [(99, 'Go'), (99, 'Games')]
                if len(self.queries) == 3:
                    return [(99, EVENT['short_name'], EVENT['emoji'], self.event_type,
                             EVENT['location_name'], EVENT['sublocation'], EVENT['venue'],
                             EVENT['address'], EVENT['source'])]
                return [(99, EVENT['urls'][0])]

        row = dict(self.reviewed(), event_id=99)
        for event_type, expected_icon in [('Class', 'game-go'), ('Screening', None)]:
            with self.subTest(event_type=event_type):
                cursor = Cursor(event_type)
                contexts = export_contexts(cursor, {99: row})
                self.assertEqual(export_icon(contexts[99], row), expected_icon)
                self.assertEqual(cursor.queries[0][1], (99,))
                self.assertNotIn('archived', cursor.queries[0][0])
                self.assertNotIn('event_occurrences', cursor.queries[0][0])

    def test_malformed_baselines_cannot_authorize_enrichment_or_crash(self):
        row = self.reviewed(additions=APPROVED)
        for mutate in [lambda p: p.update(version=999), lambda p: p.update(context=None),
                       lambda p: p['context'].update(name=42), lambda p: p['context'].update(tags=[{}]),
                       lambda p: p.update(implied_tags='Games'), lambda p: p.update(implied_tags=[{}]),
                       lambda p: p.update(approved_additions=[{'tag': 'Beginners'}])]:
            info = metadata(row)
            mutate(info['tag_enrichment'])
            broken = dict(row, evidence_json=json.dumps(info))
            with self.subTest(policy=info['tag_enrichment']):
                self.assertFalse(input_matches(self.enriched('Beginners', 'Games'), broken))
                self.assertFalse(context_matches(self.enriched('Beginners', 'Games'), broken))


if __name__ == '__main__':
    unittest.main()
