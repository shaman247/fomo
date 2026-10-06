"""scripts/ai_tag_events.py: agent-review tagging packets, validation and apply path."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_tag_events as ate  # noqa: E402

ROOTS = ['Education', 'Science', 'Sports', 'Games']
GEO = {'manhattan', 'brooklyn', 'nyc'}


def fixture_events():
    base = dict(location_id=7, sublocation='', website_id=731, archived=0, suppressed=0,
                venue='The Woods', website='Lectures on Tap NYC', event_type='Talk')
    return {
        1: dict(base, id=1, name='Lectures on Tap - "Myths in Psychology"', description='Bar talks.',
                location_name='The Woods', emoji=None),
        2: dict(base, id=2, name='Lectures on Tap - "Math of Billiards"', description='Bar talks.',
                location_name='Online via Zoom', emoji='🎓'),
    }


def fixture_state(events):
    return {eid: dict(curated=['Format', 'Gathering', 'Talk'], keywords=[], blocked=set(),
                      urls=[f'https://example.org/e/{eid}'], website_tags=['Lectures'],
                      occurrences=[dict(start_date='2026-10-05', start_time='6:30pm',
                                        end_date='', end_time='8:30pm')])
            for eid in events}


def fixture_tag_context():
    tag_rules = {'rewrite': {'lecture': 'Talk', 'lectures': 'Talk'}, 'exclude': ['event'],
                 'remove': ['privateevent'], 'canonical': {}}
    ancestor_map = {
        'psychology': {'Science'}, 'mathematics': {'STEM', 'Science'}, 'stem': {'Science'},
        'talk': {'Gathering', 'Format'}, 'gathering': {'Format'},
        'pool/billiards': {'Games'}, 'onlinetalk': {'Virtual'},
    }
    root_tags = {'science', 'education', 'games', 'sports', 'format'}
    disambiguation = {'pool': [
        {'ctx_name': 'games', 'target_name': 'Pool / Billiards', 'priority': 10},
        {'ctx_name': None, 'target_name': 'Pool / Swimming', 'priority': 0}]}
    return tag_rules, ancestor_map, root_tags, disambiguation


def good_decisions(packet):
    picks = {1: (['Science', 'Psychology', 'Lecture', 'MythBusting'], '🧠'),
             2: (['#Mathematics', 'Pool', 'Games', 'Physics', 'Lecture'], '🎱')}
    return dict(packet_hash=packet['packet_hash'], decisions=[
        dict(event_id=e['id'], content_hash=e['content_hash'], hashtags=picks[e['id']][0],
             emoji=picks[e['id']][1], reason='title') for e in packet['events']])


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.events = fixture_events()
        self.state = fixture_state(self.events)
        self.packet = ate.build_packets(self.events, self.state, ROOTS, [{'name': 'Science'}])[0]

    def validate(self, decisions, events=None):
        return ate.validate_decisions(self.packet, decisions, events or self.events, geo_keys=GEO)

    def test_packet_carries_context_and_template_covers_every_event(self):
        entry = self.packet['events'][0]
        self.assertEqual(entry['current_tags']['curated'], ['Format', 'Gathering', 'Talk'])
        self.assertEqual(entry['website_default_tags'], ['Lectures'])
        self.assertEqual(entry['content_hash'], ate.content_hash(self.events[1]))
        self.assertIn('Science', self.packet['guidance']['hashtags'])
        template = ate.decisions_template(self.packet)
        self.assertEqual([d['event_id'] for d in template['decisions']], [1, 2])
        ate.check_packet(self.packet)

    def test_valid_decisions_strip_hash_marker(self):
        result = self.validate(good_decisions(self.packet))
        self.assertEqual(result[1]['hashtags'][0], 'Mathematics')
        self.assertEqual(result[0]['emoji'], '🧠')

    def test_rejects_incomplete_coverage_and_extra_ids(self):
        d = good_decisions(self.packet)
        d['decisions'][1]['event_id'] = 99
        with self.assertRaisesRegex(ValueError, r'missing decisions for \[2\][\s\S]*not in packet: \[99\]'):
            self.validate(d)

    def test_rejects_stale_event_and_mismatched_decision_hash(self):
        changed = copy.deepcopy(self.events)
        changed[1]['name'] = 'Renamed'
        with self.assertRaisesRegex(ValueError, '1: event changed since prepare'):
            self.validate(good_decisions(self.packet), changed)
        d = good_decisions(self.packet)
        d['decisions'][0]['content_hash'] = 'x'
        with self.assertRaisesRegex(ValueError, '1: decision content_hash does not match'):
            self.validate(d)

    def test_rejects_edited_packet_and_foreign_decisions(self):
        edited = copy.deepcopy(self.packet)
        edited['events'][0]['name'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'edited after prepare'):
            ate.validate_decisions(edited, good_decisions(self.packet), self.events, geo_keys=GEO)
        d = good_decisions(self.packet)
        d['packet_hash'] = 'other'
        with self.assertRaisesRegex(ValueError, 'packet_hash does not match'):
            self.validate(d)

    def test_emoji_must_be_one_neutral_emoji(self):
        for bad in ['🧠🧪', 'brain', '', '👍🏽', '🧠 ']:
            d = good_decisions(self.packet)
            d['decisions'][0]['emoji'] = bad
            if bad == '🧠 ':
                self.validate(d)  # surrounding whitespace is trimmed
                continue
            with self.assertRaises(ValueError, msg=bad):
                self.validate(d)

    def test_hashtag_count_case_and_geography(self):
        cases = [(['Science', 'Psychology', 'Lecture'], 'need 4-7'),
                 (['Science', 'A', 'B', 'C', 'D', 'E', 'F', 'G'], 'need 4-7'),
                 (['Science', 'mental health', 'Lecture', 'Talk'], 'not CamelCase'),
                 (['Science', 'Psychology', 'Lecture', 'Manhattan'], 'is geography'),
                 (['Science', 'Psychology', 'Lecture', 'science'], 'duplicate hashtag')]
        for tags, message in cases:
            d = good_decisions(self.packet)
            d['decisions'][0]['hashtags'] = tags
            with self.assertRaisesRegex(ValueError, message):
                self.validate(d)

    def test_skip_requires_reason_and_no_payload(self):
        d = good_decisions(self.packet)
        d['decisions'][0].update(skip=True, hashtags=[], emoji='', reason='not an event')
        self.assertTrue(self.validate(d)[0]['skip'])
        d['decisions'][0]['hashtags'] = ['Science']
        with self.assertRaisesRegex(ValueError, 'skip decisions must not carry'):
            self.validate(d)


class DryRunApplyTests(unittest.TestCase):
    """Decisions flow through the real processor.process_tags + db.upsert_event_tags."""

    def setUp(self):
        self.events = fixture_events()
        self.state = fixture_state(self.events)
        self.packet = ate.build_packets(self.events, self.state, ROOTS, [])[0]
        self.validated = ate.validate_decisions(self.packet, good_decisions(self.packet),
                                                self.events, geo_keys=GEO)
        self.known = {'science', 'psychology', 'talk', 'gathering', 'format', 'mathematics',
                      'stem', 'games', 'pool/billiards', 'physics', 'virtual'}

    def plan(self, validated=None, **kw):
        return ate.plan_changes(validated or self.validated, self.events, self.state,
                                fixture_tag_context(), self.known, ROOTS, **kw)

    def test_normalization_matches_pipeline_path(self):
        plan = {p['event_id']: p for p in self.plan()}
        one, two = plan[1], plan[2]
        # alias lecture->Talk, website default tag 'Lectures' -> Talk, ancestors backfilled.
        self.assertEqual(one['tags'], ['Talk', 'Science', 'Psychology', 'Myth Busting',
                                       'Format', 'Gathering'])
        self.assertEqual(one['added'], ['Science', 'Psychology', 'Myth Busting'])
        self.assertEqual(one['new_keywords'], ['Myth Busting'])
        self.assertEqual(one['format_only'], [])
        self.assertEqual(one['emoji_action'], 'set')
        # homonym resolved by co-tag, ancestors added, Virtual from the raw location string.
        self.assertIn('Pool / Billiards', two['tags'])
        self.assertNotIn('Pool', two['tags'])
        self.assertIn('STEM', two['tags'])
        self.assertIn('Virtual', two['tags'])
        self.assertEqual(two['emoji_action'], 'keep')
        self.assertEqual(self.plan(overwrite_emoji=True)[1]['emoji_action'], 'replace')

    def test_result_without_a_category_or_with_remove_rule_is_rejected(self):
        bad = copy.deepcopy(self.validated)
        bad[0]['hashtags'] = ['Mythology', 'Trivia', 'Bar', 'Night']
        with self.assertRaisesRegex(ValueError, '1: normalized tags .* reach no category'):
            self.plan(bad)
        bad[0]['hashtags'] = ['Science', 'Psychology', 'Lecture', 'PrivateEvent']
        with self.assertRaisesRegex(ValueError, 'remove pattern'):
            self.plan(bad)

    def test_write_uses_upsert_helper_honoring_blocks(self):
        plan = self.plan()

        class Cursor:
            def __init__(self):
                self.calls, self.lastrowid, self.result = [], 500, None

            def execute(self, sql, params=()):
                self.calls.append((' '.join(sql.split()), params))
                if 'FROM event_tag_blocks' in sql:
                    self.result = [(12,)] if params[0] == 1 else []
                elif sql.startswith('SELECT id FROM tags'):
                    self.result = {'Psychology': (12,), 'Science': (11,)}.get(params[0])

            def fetchall(self):
                return self.result

            def fetchone(self):
                return self.result

        cursor = Cursor()
        with patch('icon_catalog.record_unknown') as record:
            ate.write_changes(cursor, plan)
        links = [p for sql, p in cursor.calls if sql.startswith('INSERT IGNORE INTO event_tags')]
        self.assertIn((1, 11), links)
        self.assertNotIn((1, 12), links)  # blocked pair is never re-inserted
        self.assertTrue(any(sql.startswith("INSERT INTO tags (name, type) VALUES (%s, 'keyword')")
                            and p == ('Myth Busting',) for sql, p in cursor.calls))
        emoji_updates = [p for sql, p in cursor.calls if sql.startswith('UPDATE events SET emoji')]
        self.assertEqual(emoji_updates, [('🧠', 1)])  # event 2 keeps its existing emoji
        record.assert_called_once()
        self.assertFalse(any('DELETE' in sql for sql, _ in cursor.calls))


class SelectionAndCliTests(unittest.TestCase):
    def test_missing_tags_ignores_format_family_and_counts_descendants(self):
        class Cursor:
            def execute(self, sql, params=()):
                self.sql = sql

            def fetchall(self):
                return [(1, 'Talk'), (1, 'Format'), (2, 'Psychology'), (3, None), (4, 'Science')]

        ids = ate.select_ids(Cursor(), missing_tags=True, ancestor_map={'psychology': {'Science'}},
                             roots=ROOTS)
        self.assertEqual(ids, [1, 3])

    def test_legacy_invocation_without_scope_points_to_new_flow(self):
        with self.assertRaises(SystemExit), patch('sys.stderr'):
            ate.main(['--dry-run'])


if __name__ == '__main__':
    unittest.main()
