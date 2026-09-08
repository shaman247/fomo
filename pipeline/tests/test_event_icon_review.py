"""Agent decisions outrank heuristics, remain incremental, and apply atomically."""
import copy
import json
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_icons import input_hash
from event_icon_assignments import (desired_assignment, export_icon, manual_assignment,
                                    merge_manual_decisions, sync_assignments)
from event_icon_review import (catalog_revision, make_packets, review_reason,
                               validate_decisions, refresh_review_state,
                               collect_opportunities, metadata, validate_opportunities)
from event_icon_review import fetch_review_events

EVENT = dict(id=1, name='Community Games', description='A night of Go with boards and stones.',
             tags=['Games'], venue='Community Center', urls=['https://example.com/go'])


class ReviewTests(unittest.TestCase):
    def packet(self, events=None, rows=None):
        return make_packets(events or [EVENT], rows or {}, 100)[0][0]

    def decisions(self, packet, icon='game-go', action='assign'):
        return dict(catalog_revision=packet['catalog_revision'], decisions=[dict(
            event_id=e['event']['id'], input_hash=e['input_hash'], icon_id=icon,
            decision=action, reason='Go is the defining activity in the full description.',
            evidence=['The description identifies Go with boards and stones.'],
            opportunities=[]) for e in packet['events']])

    def reviewed(self, icon='game-go', action='assign'):
        p = self.packet()
        return validate_decisions(p, self.decisions(p, icon, action), {1: EVENT}, {})[0]

    def test_queue_includes_events_without_a_heuristic_match_and_full_catalog(self):
        unrelated = dict(EVENT, id=2, name='Poetry Reading', description='Poems', tags=['Literature'])
        packets, counts = make_packets([EVENT, unrelated], {}, 1)
        self.assertEqual(len(packets), 2)
        self.assertEqual(counts, {'unreviewed': 2})
        self.assertEqual(len(packets[0]['icons']), len(packets[1]['icons']))
        self.assertEqual(packets[1]['events'][0]['event']['description'], 'Poems')
        self.assertIsNone(packets[1]['events'][0]['heuristic_proposal']['icon_id'])

    def test_date_scope_filters_by_occurrence_before_loading_context(self):
        class Cursor:
            def __init__(self): self.calls = []
            def execute(self, query, params): self.calls.append((query,params))
            def fetchall(self):
                if len(self.calls) == 1: return [(2,)]
                if len(self.calls) == 2: return [(2,None,'🎵','Concert','Hall',None,'Hall','Address','Source')]
                return [(2,'https://example.com/event')]
        cursor=Cursor(); day=date(2026,9,8)
        with patch('event_icon_review.fetch_events',return_value=[dict(EVENT),dict(EVENT,id=2)]):
            rows=fetch_review_events(cursor,day)
        self.assertEqual([e['id'] for e in rows],[2])
        self.assertEqual(cursor.calls[0][1],(day,day))
        self.assertEqual(cursor.calls[1][1],(2,))
        self.assertEqual(rows[0]['urls'],['https://example.com/event'])

    def test_agent_can_override_a_heuristic_and_exports_as_final_choice(self):
        event = dict(EVENT, name='Bingo Night', description='Identify song clips on your bingo card.')
        p = self.packet([event])
        self.assertEqual(p['events'][0]['heuristic_proposal']['icon_id'], 'bingo')
        row = validate_decisions(p, self.decisions(p, 'music-bingo'), {1:event}, {})[0]
        self.assertEqual(row['origin'], 'agent')
        self.assertEqual(export_icon(event, row), 'music-bingo')
        self.assertEqual(desired_assignment(event, row), row)

    def test_fallback_is_a_reviewed_decision_not_a_permanent_new_candidate(self):
        row = self.reviewed(None, 'fallback')
        self.assertIsNone(review_reason(EVENT, row, catalog_revision()))
        self.assertEqual(make_packets([EVENT], {1:row})[0], [])
        self.assertIsNone(export_icon(EVENT, row))
        self.assertEqual(review_reason(EVENT, row, 'new-catalog'), 'changed-catalog')

    def test_context_and_content_changes_return_to_queue(self):
        row = self.reviewed()
        self.assertEqual(review_reason(dict(EVENT, venue='Other venue'), row, catalog_revision()), 'changed-context')
        self.assertEqual(review_reason(dict(EVENT, description='Different activity'), row, catalog_revision()), 'changed-or-deferred')
        self.assertEqual(review_reason(EVENT, self.reviewed(None, 'defer'), catalog_revision()), 'changed-or-deferred')

    def test_legacy_rules_need_review_but_current_manual_decisions_are_protected(self):
        event = dict(EVENT, name='Go Club')
        self.assertEqual(review_reason(event, desired_assignment(event), catalog_revision()), 'legacy-rule')
        self.assertEqual(review_reason(event, manual_assignment(event, None, 'Keep emoji'), catalog_revision()), 'icon-opportunities')

    def test_complete_batch_coverage_unknown_ids_and_empty_reasons_rejected(self):
        p = self.packet()
        for edit in [lambda d: d['decisions'].clear(),
                     lambda d: d['decisions'].append(copy.deepcopy(d['decisions'][0])),
                     lambda d: d['decisions'][0].update(event_id=99),
                     lambda d: d['decisions'][0].update(icon_id='unknown'),
                     lambda d: d['decisions'][0].update(reason=''),
                     lambda d: d['decisions'][0].update(evidence=[]),
                     lambda d: d['decisions'][0].update(decision='fallback'),
                     lambda d: d['decisions'][0].update(input_hash='old')]:
            d = self.decisions(p); edit(d)
            with self.assertRaises(ValueError): validate_decisions(p,d,{1:EVENT},{})

    def test_stale_packet_catalog_context_and_concurrent_choices_rejected(self):
        p = self.packet(); d = self.decisions(p)
        for current in [{}, {1:dict(EVENT, venue='Changed')}, {1:dict(EVENT, tags=['New'])}]:
            with self.assertRaises(ValueError): validate_decisions(p,d,current,{})
        changed = dict(p, catalog_revision='old')
        with self.assertRaises(ValueError): validate_decisions(changed,d,{1:EVENT},{})
        with self.assertRaises(ValueError): validate_decisions(p,d,{1:EVENT},{1:manual_assignment(EVENT,None,'Keep emoji')})

    def test_manual_choice_can_be_revalidated_but_not_replaced(self):
        old = manual_assignment(dict(EVENT,description='Old content'),None,'Keep emoji')
        p = self.packet(rows={1:old})
        with self.assertRaises(ValueError): validate_decisions(p,self.decisions(p),{1:EVENT},{1:old})
        row = validate_decisions(p,self.decisions(p,None,'fallback'),{1:EVENT},{1:old})[0]
        self.assertEqual(row['origin'], 'manual')
        self.assertEqual(row['input_hash'], input_hash(EVENT))
        self.assertIsNone(review_reason(EVENT,row,catalog_revision()))

    def test_reapplying_identical_decisions_is_idempotent(self):
        p = self.packet(); d = self.decisions(p)
        row = validate_decisions(p,d,{1:EVENT},{})[0]
        self.assertEqual(validate_decisions(p,d,{1:EVENT},{1:row}), [row])

    def test_maintenance_never_accepts_heuristics_for_new_events(self):
        with patch('event_icon_assignments.load_assignments',return_value={}), \
             patch('event_icon_assignments.propose',side_effect=AssertionError('No classifier in maintenance')):
            self.assertEqual(sync_assignments(None, [EVENT]), {'events':1,'unchanged':1})

    def test_full_context_change_invalidates_saved_agent_choice_before_export(self):
        row = self.reviewed()
        with patch('event_icon_review.fetch_review_events',return_value=[dict(EVENT,venue='Changed')]), \
             patch('event_icon_review.load_assignments',return_value={1:row}), \
             patch('event_icon_review.require_lock'), patch('event_icon_review.save') as save:
            stats = refresh_review_state(None,apply=True)
            self.assertEqual(stats, {'pending':1,'invalidated':1})
            self.assertTrue(save.call_args.args[1]['review_required'])

    def test_merge_queues_agent_choice_and_preserves_human_priority(self):
        agent = self.reviewed()
        self.assertTrue(merge_manual_decisions(EVENT,[agent])['review_required'])
        manual = manual_assignment(EVENT,None,'Human fallback')
        row = merge_manual_decisions(EVENT,[agent,manual])
        self.assertEqual(row['origin'],'manual')
        self.assertIsNone(row['icon_id'])

    def opportunity(self, concept='instrument-cello'):
        return dict(concept=concept, label='Cello', category='instrument',
                    visual='A tall cello body with endpin and a single diagonal bow.',
                    rationale='Distinguishes a cello recital from generic music and smaller string instruments.',
                    existing_alternative='Generic music notes lose instrument identity; violin artwork has different proportions.',
                    evidence=['The program explicitly names a solo cello recital.'])

    def test_opportunity_survives_fallback_without_becoming_an_assignment(self):
        event = dict(EVENT,name='Solo Cello Recital',description='An evening of solo cello music.',tags=['Music'])
        p = self.packet([event]); d = self.decisions(p, None, 'fallback')
        d['decisions'][0]['opportunities'] = [self.opportunity()]
        row = validate_decisions(p,d,{1:event},{})[0]
        self.assertIsNone(export_icon(event,row))
        self.assertEqual(metadata(row)['opportunities'][0]['concept'],'instrument-cello')
        self.assertIsNone(review_reason(event,row,catalog_revision()))

    def test_missing_opportunity_review_and_malformed_suggestions_rejected(self):
        p = self.packet(); d = self.decisions(p)
        del d['decisions'][0]['opportunities']
        with self.assertRaises(ValueError): validate_decisions(p,d,{1:EVENT},{})
        for value in [None, [dict(self.opportunity(),concept='bad key')],
                      [dict(self.opportunity(),category='invalid')],
                      [dict(self.opportunity(),visual='')], [dict(self.opportunity(),evidence=[])],
                      [self.opportunity(),self.opportunity()]]:
            with self.assertRaises(ValueError): validate_opportunities(value)

    def test_agent_reviews_before_discovery_step_are_queued_once(self):
        row = self.reviewed()
        info = metadata(row); del info['opportunity_review_version']
        row['evidence_json'] = json.dumps(info)
        self.assertEqual(review_reason(EVENT,row,catalog_revision()),'icon-opportunities')

    def test_backlog_merges_concepts_and_counts_unique_events_not_occurrences(self):
        recital = dict(EVENT,name='Baroque Cello Recital',description='A solo cello recital of Baroque repertoire.',tags=['Music','Baroque'])
        events = [dict(recital,id=1,venue='Hall A'), dict(recital,id=2,venue='Hall B')]
        p = self.packet(events); d = self.decisions(p,None,'fallback')
        for choice in d['decisions']:
            choice['opportunities']=[self.opportunity(),dict(self.opportunity('genre-baroque'),
                category='genre',label='Baroque',visual='A harpsichord silhouette, subject to genre-recognition review.')]
        rows = validate_decisions(p,d,{e['id']:e for e in events},{})
        report = collect_opportunities(events,{r['event_id']:r for r in rows})
        self.assertEqual(report['concept_count'],2)
        self.assertEqual(report['reviewed_events'],2)
        for concept in report['concepts']:
            self.assertEqual(concept['event_ids'],[1,2])
            self.assertEqual(concept['event_count'],2)
            self.assertEqual(concept['venue_count'],2)
        changed = [events[0],dict(events[1],description='Now another program')]
        report = collect_opportunities(changed,{r['event_id']:r for r in rows})
        self.assertEqual(report['stale_reviews_excluded'],1)
        self.assertTrue(all(c['event_count']==1 for c in report['concepts']))


if __name__ == '__main__':
    unittest.main()
