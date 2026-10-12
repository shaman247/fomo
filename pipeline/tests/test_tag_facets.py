"""BL15: topic ancestry, keyword inference and authoritative Format membership."""
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import db
import processor
import tag_facets as tf
from tag_canonicalization import TagResolutionError

EDGES = [
    ('Format', 'Performance'), ('Format', 'Participatory'), ('Format', 'Gathering'),
    ('Performance', 'Sports'), ('Sports', 'Running'), ('Performance', 'Concert'),
    ('Music', 'Concert'), ('Participatory', 'Workshop'), ('Education', 'Workshop'),
    ('Participatory', 'Tasting'), ('Tasting', 'Wine Tasting'), ('Food', 'Wine Tasting'),
    ('Gathering', 'Talk'), ('Family', 'Kids'),
]
ROOTS = {'Music', 'Education', 'Food', 'Sports', 'Family'}


def topic_parents():
    return tf.parent_map(tf.topic_edges(EDGES))


class FacetDefinitionTests(unittest.TestCase):
    def test_shared_topics_are_not_format_exclusive(self):
        self.assertIn('Talk', tf.FORMAT_EXCLUSIVE)
        self.assertIn('Performance', tf.FORMAT_EXCLUSIVE)
        self.assertIn('Format', tf.FORMAT_EXCLUSIVE)
        for shared in ('Sports', 'Workshop', 'Concert', 'Party'):
            self.assertNotIn(shared, tf.FORMAT_EXCLUSIVE)
            self.assertIn(shared, tf.FORMAT_FAMILY)
        self.assertEqual(tf.format_membership('Talk'), {'Talk', 'Gathering', 'Format'})
        self.assertEqual(tf.format_membership('Tour'), {'Tour', 'Outings', 'Format'})
        # BL23: Concert/Sports keep the union; the other shared chips are content-only.
        self.assertEqual(tf.format_membership('Concert'), {'Concert', 'Performance', 'Format'})
        self.assertEqual(tf.format_membership('Workshop'), {'Participatory', 'Format'})
        self.assertEqual(tf.UNION_LEAVES | tf.CONTENT_ONLY_LEAVES, tf.SHARED_LEAVES)
        self.assertEqual(tf.format_membership('Other'), set())
        self.assertEqual(tf.format_membership(None), set())

    def test_topic_closure_never_reaches_format_nodes(self):
        parents = topic_parents()
        self.assertEqual(tf.ancestors('Running', parents), {'Sports'})
        self.assertEqual(tf.ancestors('Wine Tasting', parents), {'Food'})
        self.assertEqual(tf.ancestors('Concert', parents), {'Music'})

    def test_format_implied_union_leaf_adds_no_topic_parents(self):
        parents = topic_parents()
        self.assertEqual(tf.topic_closure({'Concert', 'Kids'}, parents, 'Concert'),
                         {'Concert', 'Kids', 'Family'})
        # Content evidence for the same leaf on another format still derives Music.
        self.assertIn('Music', tf.topic_closure({'Concert'}, parents, 'Talk'))
        # A content-only leaf is never format-implied, so it always derives parents.
        self.assertIn('Education', tf.topic_closure({'Workshop'}, parents, 'Workshop'))

    def test_derivation_is_idempotent_and_honours_blocks(self):
        parents = topic_parents()
        cases = [
            ({'Running', 'Performance', 'Format'}, 'Fitness', ()),
            ({'Workshop', 'Kids'}, 'Workshop', ()),
            ({'Wine Tasting', 'Participatory'}, 'Tasting', ('Participatory',)),
            ({'Talk'}, 'Concert', ()),
            ({'Some Keyword'}, None, ()),
        ]
        for direct, event_type, blocked in cases:
            once = tf.derive_event_tags(direct, event_type, parents, ROOTS, blocked)
            twice = tf.derive_event_tags(once, event_type, parents, ROOTS, blocked)
            self.assertEqual(once, twice, (direct, event_type))
            self.assertFalse(set(blocked) & once)
            self.assertEqual(once & tf.FORMAT_EXCLUSIVE,
                             (tf.format_membership(event_type) - set(blocked)) & tf.FORMAT_EXCLUSIVE)
        running = tf.derive_event_tags({'Running', 'Performance', 'Format'}, 'Fitness', parents, ROOTS)
        self.assertEqual(running, {'Running', 'Sports', 'Participatory', 'Format'})
        self.assertIn('Other', tf.derive_event_tags({'Talk'}, 'Talk', parents, ROOTS))

    def test_health_helpers(self):
        parents = topic_parents()
        self.assertEqual(tf.missing_topic_ancestors({'Concert', 'Format'}, 'Concert', parents), set())
        self.assertEqual(tf.missing_topic_ancestors({'Workshop', 'Format'}, 'Workshop', parents), {'Education'})
        self.assertEqual(tf.missing_topic_ancestors({'Running'}, 'Fitness', parents), {'Sports'})
        extra, missing = tf.format_drift({'Performance', 'Format', 'Running'}, 'Fitness')
        self.assertEqual(extra, {'Performance'})
        self.assertEqual(missing, {'Participatory'})
        self.assertEqual(tf.format_drift({'Sports', 'Running'}, 'Sports')[1], {'Performance', 'Format'})
        found = tf.shadowing_aliases([('musical theater', 'Theater Show'), ('Game', 'Games'),
                                      ('gig', 'Concert')], {'Musical Theater', 'Game', 'Games'})
        self.assertEqual(found, [('Game', 'Games', 'Game', False),
                                 ('musical theater', 'Theater Show', 'Musical Theater', True)])


class AncestorMapTests(unittest.TestCase):
    def test_db_ancestor_map_is_topic_only_and_sports_is_a_root(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = EDGES
        ancestors, roots = db.build_tag_ancestor_map(cursor)
        self.assertEqual(ancestors['running'], {'Sports'})
        self.assertEqual(ancestors['winetasting'], {'Food'})
        self.assertNotIn('talk', ancestors)
        self.assertIn('sports', roots)
        self.assertNotIn('format', roots)

    def test_process_tags_derives_topics_not_formats(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = EDGES
        ancestors, roots = db.build_tag_ancestor_map(cursor)
        rules = {'rewrite': {}, 'canonical': {}, 'exclude': []}
        tags = processor.process_tags({'hashtags': ['Running']}, rules, ancestor_map=ancestors,
                                      root_tags=roots)['tags']
        self.assertEqual(tags, ['Running', 'Sports'])
        # A format-only hashtag reaches no topic root, so the Other keyword applies.
        tags = processor.process_tags({'hashtags': ['Talk']}, rules, ancestor_map=ancestors,
                                      root_tags=roots)['tags']
        self.assertEqual(tags, ['Talk', 'Other'])


class FakeTagCursor:
    """Just enough SQL for upsert_event_tags / sync_event_format_tags."""

    def __init__(self, event_type, rows=(), blocks=()):
        names = sorted(tf.FORMAT_FAMILY | {'Running', 'Sports', 'Music'})
        self.ids = {n: i for i, n in enumerate(names, 1)}
        self.names = {i: n for n, i in self.ids.items()}
        self.event_type, self.rows, self.blocks = event_type, {self.ids[n] for n in rows}, {self.ids[n] for n in blocks}
        self.result = None

    def execute(self, sql, params=()):
        sql = ' '.join(sql.split())
        if sql.startswith('SELECT tag_id FROM event_tag_blocks'):
            self.result = [(b,) for b in self.blocks]
        elif sql.startswith('SELECT name, id FROM tags'):
            self.result = [(n, self.ids[n]) for n in params if n in self.ids]
        elif sql.startswith('SELECT id FROM tags'):
            self.result = (self.ids[params[0]],)
        elif sql.startswith('SELECT event_type FROM events'):
            self.result = (self.event_type,)
        elif sql.startswith('DELETE FROM event_tags WHERE event_id = %s AND tag_id IN'):
            self.rows -= set(params[1:])
        elif sql.startswith('DELETE FROM event_tags'):
            self.rows.clear()
        elif sql.startswith('INSERT IGNORE INTO event_tags'):
            self.rows.add(params[1])
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result

    def tags(self):
        return {self.names[i] for i in self.rows}


class WriterTests(unittest.TestCase):
    def setUp(self):
        db._format_tag_id_cache = None
        self.addCleanup(setattr, db, '_format_tag_id_cache', None)

    def test_merge_replace_keeps_event_type_format_and_strips_derived_formats(self):
        cur = FakeTagCursor('Fitness', rows={'Fitness', 'Participatory', 'Format'})
        # Historical crawl tags still carry topic-derived Performance/Format.
        db.upsert_event_tags(cur, 1, ['Running', 'Sports', 'Performance', 'Format'], replace=True)
        # Fitness is a content-only chip: the event_type alone no longer re-adds it.
        self.assertEqual(cur.tags(), {'Running', 'Sports', 'Participatory', 'Format'})
        db.upsert_event_tags(cur, 1, ['Running', 'Sports', 'Fitness'], replace=True)
        self.assertEqual(cur.tags(), {'Running', 'Sports', 'Fitness', 'Participatory', 'Format'})
        cur = FakeTagCursor('Concert')
        db.upsert_event_tags(cur, 1, ['Music'], replace=True)
        self.assertEqual(cur.tags(), {'Music', 'Concert', 'Performance', 'Format'})

    def test_unclassified_event_has_no_format_and_blocks_bind(self):
        cur = FakeTagCursor(None)
        db.upsert_event_tags(cur, 1, ['Concert', 'Performance', 'Music'])
        self.assertEqual(cur.tags(), {'Concert', 'Music'})  # shared leaf from content stays
        cur = FakeTagCursor('Talk', blocks={'Gathering'})
        db.upsert_event_tags(cur, 1, ['Music'])
        self.assertEqual(cur.tags(), {'Music', 'Talk', 'Format'})

    def test_shared_leaf_from_content_survives_other_event_type(self):
        cur = FakeTagCursor('Talk')
        db.upsert_event_tags(cur, 1, ['Sports', 'Running'])
        self.assertEqual(cur.tags(), {'Sports', 'Running', 'Talk', 'Gathering', 'Format'})


class AliasGuardTests(unittest.TestCase):
    def cursor(self, curated):
        cursor = MagicMock()
        cursor.fetchone.return_value = ('Theater Show', 'event')
        cursor.fetchall.side_effect = [[(n,) for n in curated], []]
        return cursor

    def test_alias_cannot_shadow_curated_topic(self):
        cursor = self.cursor(['Musical Theater'])
        with self.assertRaises(TagResolutionError):
            db.upsert_tag_alias(cursor, 'musical theater', 7)
        self.assertFalse(any('INSERT' in c.args[0] for c in cursor.execute.call_args_list))

    def test_format_only_name_may_redirect_to_its_topic(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ('Games', 'event')
        cursor.fetchall.side_effect = [[('Game',)], []]
        db.upsert_tag_alias(cursor, 'Game', 9)
        self.assertTrue(any('INSERT INTO tag_aliases' in c.args[0] for c in cursor.execute.call_args_list))


class BackfillTests(unittest.TestCase):
    def test_backfill_skips_format_implied_union_leaf_parents(self):
        import backfill_category_tags as backfill
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[
            {'id': 1, 'name': 'Kids show', 'event_type': 'Concert', 'tags': 'Concert|||Kids|||Family'},
            {'id': 2, 'name': 'Pottery talk', 'event_type': 'Talk', 'tags': 'Workshop|||Talk'},
            {'id': 3, 'name': 'Horror film', 'event_type': 'Screening', 'tags': 'Horror|||Film'},
        ], [{'event_id': 3, 'name': 'Literature'}]]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        ancestors = {'concert': {'Music'}, 'workshop': {'Education'}, 'kids': {'Family'},
                     'horror': {'Literature', 'Film'}}
        with patch.object(backfill, 'validate_hierarchy'), \
                patch.object(backfill, 'get_tag_hierarchy_for_export'), \
                patch.object(backfill, 'build_tag_ancestor_map',
                             return_value=(ancestors, {'education', 'family', 'film', 'music'})):
            backfill._backfill(conn, apply=True, verbose=False, event_ids=None)
        inserts = [c.args[1] for c in cursor.execute.call_args_list if 'INSERT IGNORE' in c.args[0]]
        # Only the content-only Workshop gains Education (the union Concert implied by
        # event_type adds no Music); the judged Literature block binds.
        self.assertEqual([args[0] for args in inserts], [2])


if __name__ == '__main__':
    unittest.main()
