"""Operational model gates, including cold-start and interrupted publication."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from test_similarity import fixture
from similarity import fit, write_model
from similarity_health import audit, inspect_artifacts
from upload_public_html import upload_directory


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'public'
        self.workspace = Path(self.temp.name) / 'private'
        self.data = fixture()
        self.data['capturedAt'] = datetime.now(timezone.utc).isoformat()
        self.fitted = fit(self.data, dimensions=6, min_df=1)
        self.report = write_model(self.data, self.fitted, self.output, self.workspace)
        self.manifest = json.loads((self.output / 'manifest.json').read_text())
        self.domain = self.manifest['domain']

    def test_fresh_model_covers_all_current_events(self):
        result = audit(self.data, self.output, self.domain)
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['activeVectorCoverage'], 1)

    def test_normalized_tag_collisions_combine_without_losing_support(self):
        self.data['tags'][0]['name'] = 'ＪＡＺＺ!'
        write_model(self.data, self.fitted, self.output, self.workspace)
        manifest, _, _, tags = inspect_artifacts(self.output, self.domain)
        self.assertTrue(tags['jazz'])
        core = json.loads((self.output / manifest['generation'] / 'core.json').read_text())
        block = core['blocks']['tag']
        self.assertEqual(block['support'][block['ids'].index('jazz')], 4)

    def test_new_events_history_rollover_and_unknown_tags_are_distinguished(self):
        self.data['active_ids'] += [1, 9000, 9001]
        self.data['event_tags'] += [{'event_id': 9000, 'tag_id': 2}, {'event_id': 9001, 'tag_id': 5}]
        result = audit(self.data, self.output, self.domain)
        self.assertEqual(result['status'], 'review')
        self.assertEqual(result['activeVectorEvents'], 3)
        self.assertEqual(result['tagFallbackEvents'], 2)
        self.assertEqual(result['exactOnlyEvents'], 1)
        self.assertEqual(result['currentEventsInHistory'], 1)
        self.assertEqual(result['eventsAbsentFromModel'], 2)

    def test_rebuilding_an_old_snapshot_does_not_reset_freshness(self):
        self.data['capturedAt'] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        write_model(self.data, self.fitted, self.output, self.workspace)
        self.assertIn('Model is at least 7 days old', audit(self.data, self.output, self.domain)['reasons'])

    def test_corrupt_or_missing_shards_and_wrong_city_fail_closed(self):
        with self.assertRaises(ValueError):
            inspect_artifacts(self.output, 'wrong-city')
        shard = self.output / self.report['generation'] / 'active-0.json'
        shard.write_text('{"ids":["2"],"vectors":"AA=="}')
        with self.assertRaises(ValueError):
            inspect_artifacts(self.output, self.domain)
        shard.unlink()
        with self.assertRaises(FileNotFoundError):
            inspect_artifacts(self.output, self.domain)

    def test_repeat_build_preserves_generation_files_and_invalid_fit_preserves_pointer(self):
        core = self.output / self.report['generation'] / 'core.json'
        before = core.stat().st_mtime_ns
        write_model(self.data, self.fitted, self.output, self.workspace)
        self.assertEqual(core.stat().st_mtime_ns, before)
        pointer = (self.output / 'manifest.json').read_bytes()
        self.fitted[1][0, 0] = np.nan
        with self.assertRaises(ValueError):
            write_model(self.data, self.fitted, self.output, self.workspace)
        self.assertEqual((self.output / 'manifest.json').read_bytes(), pointer)

    def test_failed_relevance_gate_preserves_public_manifest(self):
        pointer = (self.output / 'manifest.json').read_bytes()
        self.data['active_ids'] = [1, 2, 3, 4]
        def reject(_):
            raise ValueError('relevance regression')
        with self.assertRaisesRegex(ValueError, 'relevance regression'):
            write_model(self.data, self.fitted, self.output, self.workspace, validate=reject)
        self.assertEqual((self.output / 'manifest.json').read_bytes(), pointer)

    def test_missing_aggregate_shard_fails_integrity_audit(self):
        generation = self.output / self.report['generation']
        (generation / 'tags-0.json').unlink()
        with self.assertRaises(FileNotFoundError):
            inspect_artifacts(self.output, self.domain)

    def test_upload_publishes_manifest_after_all_shards(self):
        ftp = Mock()
        upload_directory(ftp, self.output, 'public_html/data/similarity')
        targets = [call.args[1] for call in ftp.rename.call_args_list]
        self.assertEqual(targets[-1], 'manifest.json')
        self.assertIn('core.json', targets[:-1])
        self.assertIn('active-0.json', targets[:-1])
        self.assertIn('events-0.json', targets[:-1])

    def test_upload_failure_never_publishes_manifest(self):
        ftp = Mock()
        ftp.rename.side_effect = OSError('interrupted generation upload')
        with self.assertRaises(OSError):
            upload_directory(ftp, self.output, 'public_html/data/similarity')
        self.assertNotIn('manifest.json', [call.args[1] for call in ftp.rename.call_args_list])

    def test_failed_return_to_parent_never_uploads_manifest_into_generation(self):
        ftp = Mock()
        parent_visits = 0

        def cwd(path):
            nonlocal parent_visits
            if path == '/public_html/data/similarity':
                parent_visits += 1
                if parent_visits > 1:
                    raise OSError('cannot restore parent directory')

        ftp.cwd.side_effect = cwd
        with self.assertRaises(OSError):
            upload_directory(ftp, self.output, 'public_html/data/similarity')
        self.assertNotIn('manifest.json', [call.args[1] for call in ftp.rename.call_args_list])


if __name__ == '__main__':
    unittest.main()
