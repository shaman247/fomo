import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_hierarchy_policy import graph_findings, hierarchy_findings, validate_hierarchy, promote_tag


def tag(name, parents=(), scope='event'):
    return dict(name=name, parents=list(parents), scope=scope)


CFG = {'frontend': {'filter_roots': {'tag': ['Art', 'Sports'], 'venue': ['Hotel']}},
       'tag_hierarchy': {'structural_roots': {'event': ['Format']}}}


class HierarchyPolicyTests(unittest.TestCase):
    def test_reviewed_parents_reject_semantic_edge_regression(self):
        cfg = {**CFG, 'tag_hierarchy': {'parents': {'event': {'Competition': ['Art']}}}}
        tags = [tag('Art'), tag('Sports'), tag('venue:Hotel', scope='venue'),
                tag('Competition', ['Art', 'Sports'])]
        self.assertEqual(hierarchy_findings(tags, cfg)['reviewed_parent_mismatches'], ['Competition'])
        with self.assertRaises(ValueError):
            validate_hierarchy(tags, cfg)
        tags[-1]['parents'] = ['Art']
        validate_hierarchy(tags, cfg)

    def test_orphan_component_is_reported_even_with_children(self):
        report = graph_findings([tag('Art'), tag('Orphan'), tag('Child', ['Orphan'])], {'Art'})
        self.assertEqual(report['unapproved_roots'], ['Orphan'])
        self.assertEqual(report['unreachable'], ['Child', 'Orphan'])

    def test_reviewed_standalone_root_and_dag_are_valid(self):
        tags = [tag('Art'), tag('Sports'), tag('venue:Hotel', scope='venue'),
                tag('Shared', ['Art', 'Sports'])]
        validate_hierarchy(tags, CFG)

    def test_projection_cannot_turn_format_only_child_into_topic_root(self):
        tags = [tag('Art'), tag('Sports', ['Performance']), tag('venue:Hotel', scope='venue'),
                tag('Format'), tag('Performance', ['Format']), tag('Accidental Topic', ['Performance'])]
        findings = hierarchy_findings(tags, CFG)
        self.assertEqual(findings['stored']['unapproved_roots'], [])
        self.assertEqual(findings['public']['unapproved_roots'], ['Accidental Topic'])

    def test_cycles_missing_parents_and_cross_scope_links_are_rejected(self):
        for extra in ([tag('A', ['B']), tag('B', ['A'])],
                      [tag('A', ['Missing'])], [tag('A', ['venue:Hotel'])]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_hierarchy([tag('Art'), tag('Sports'), tag('venue:Hotel', scope='venue'), *extra], CFG)

    def test_missing_root_policy_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Configure frontend.filter_roots'):
            validate_hierarchy([], {})

    def test_no_parent_promotion_rejected_before_any_write(self):
        cur = MagicMock()
        with self.assertRaisesRegex(ValueError, 'requires at least one'):
            promote_tag(cur, 'New', 'event', [], '🎨', CFG)
        cur.execute.assert_not_called()

    def test_missing_parent_aborts_instead_of_silently_skipping(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [(10,), None]
        with self.assertRaisesRegex(ValueError, 'Invalid event parent'):
            promote_tag(cur, 'New', 'event', ['Missing'], '🎨', CFG)
        statements = [c.args[0] for c in cur.execute.call_args_list]
        self.assertIn('ROLLBACK TO SAVEPOINT tag_promotion', statements)
        self.assertFalse(any(s.startswith('UPDATE') for s in statements))

    def test_invalid_final_graph_rolls_back_type_change_and_links(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [(10,), (11,)]
        with patch('db.get_tag_hierarchy_for_export', return_value=[tag('New', ['New'])]), \
                self.assertRaises(ValueError):
            promote_tag(cur, 'New', 'event', ['Art'], '🎨', CFG)
        statements = [c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any(s.startswith('UPDATE') for s in statements))
        self.assertIn('ROLLBACK TO SAVEPOINT tag_promotion', statements)

    def test_both_exports_refuse_orphans_before_writing_files(self):
        import exporter
        for export in (exporter.export_events, exporter.export_tag_hierarchy):
            with self.subTest(export=export.__name__), \
                    patch('db.get_tag_hierarchy_for_export', return_value=[tag('Orphan')]), \
                    patch('tag_hierarchy_policy.get_config', return_value=CFG), \
                    patch('builtins.open') as opened, self.assertRaises(ValueError):
                export(MagicMock())
            opened.assert_not_called()

    def test_backfill_creates_missing_other_as_keyword(self):
        import io
        from contextlib import redirect_stdout
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        import backfill_category_tags as backfill
        conn, cur = MagicMock(), MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = [{'id': 1, 'name': 'Uncategorized', 'tags': ''}]
        cur.fetchone.return_value = None
        with patch.object(backfill, 'validate_hierarchy'), \
                patch.object(backfill, 'get_tag_hierarchy_for_export', return_value=[]), \
                patch.object(backfill, 'build_tag_ancestor_map', return_value=({}, set())), \
                redirect_stdout(io.StringIO()):
            backfill._backfill(conn, True, False, None)
        inserts = [c.args for c in cur.execute.call_args_list if 'INSERT INTO tags' in c.args[0]]
        self.assertEqual(inserts, [("INSERT INTO tags (name, type, scope) VALUES (%s, 'keyword', 'event')", ('Other',))])


if __name__ == '__main__':
    unittest.main()
