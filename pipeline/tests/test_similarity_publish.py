"""Gated similarity publication: gate checks, shard→manifest order, verification and rollback."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from test_similarity import fixture
from similarity import fit, write_model
from similarity_publish import (COMPARISON_GATES, PublicationError, generation_files, publish, rollback,
                                check_gates)
from upload_public_html import upload_directory


class FakeServer:
    """Served files keyed by path under data/similarity/, shared by the site and the target."""

    def __init__(self):
        self.files, self.puts, self.corrupt, self.fail_on = {}, [], set(), None

    def get(self, relative):
        data = self.files.get(relative)
        return data + b' ' if data is not None and relative in self.corrupt else data

    def put(self, relative, data):
        if relative == self.fail_on:
            raise OSError('connection dropped')
        self.puts.append(relative)
        self.files[relative] = data


def summary(ndcg=1.0, pairwise=1.0, wrong=0.0):
    return {'queries': 3, 'judgments': 9, 'ndcgAt5': ndcg, 'pairwiseAccuracy': pairwise, 'wrongTop1': wrong}


def write_evidence(directory, generation, baseline, **overrides):
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('health-src.json', 'health-dist.json'):
        (directory / name).write_text(json.dumps({'status': 'healthy', 'reasons': [], 'generation': generation,
                                                  'activeVectorCoverage': 1.0, 'tagFallbackEvents': 0,
                                                  'exactOnlyEvents': 0}))
    for name, checks in COMPARISON_GATES.items():
        document = {}
        for candidate_key, baseline_key, precision in checks:
            candidate = {'generation': generation, 'precision': precision, 'summary': summary(), 'queries': []}
            reference = {'generation': baseline, 'precision': precision, 'summary': summary(), 'queries': []}
            if candidate_key:
                document[candidate_key] = candidate
            else:
                document.update(candidate)
            document[baseline_key] = reference
        (directory / name).write_text(json.dumps(document))
    (directory / 'python-tests.log').write_text('....\nRan 4 tests in 0.1s\n\nOK\n')
    (directory / 'js-tests.log').write_text('ℹ pass 9\nℹ fail 0\n')
    for name, text in overrides.items():
        (directory / name).write_text(text)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.model, self.state, self.evidence = root / 'public', root / 'publications.json', root / 'evidence'
        data = fixture()
        data['capturedAt'] = datetime.now(timezone.utc).isoformat()
        # Two real generations: A is served, B is the local candidate.
        self.old = write_model(data, fit(data, dimensions=5, min_df=1), self.model, root / 'a')['generation']
        self.old_manifest = (self.model / 'manifest.json').read_bytes()
        self.new = write_model(data, fit(data, dimensions=6, min_df=1), self.model, root / 'b')['generation']
        self.new_manifest = (self.model / 'manifest.json').read_bytes()
        self.domain = json.loads(self.new_manifest)['domain']
        self.server = FakeServer()
        self.serve(self.old, self.old_manifest)
        write_evidence(self.evidence, self.new, self.old)
        self.log = []

    def serve(self, generation, manifest):
        for name in generation_files(json.loads(manifest)):
            self.server.files[f'{generation}/{name}'] = (self.model / generation / name).read_bytes()
        self.server.files['manifest.json'] = manifest

    def publish(self, **kwargs):
        return publish(self.server, self.server, self.model, self.evidence, self.domain, self.state,
                       log=self.log.append, **kwargs)

    def test_publish_uploads_every_shard_before_the_manifest_and_records_rollback(self):
        self.assertTrue(self.publish())
        names = generation_files(json.loads(self.new_manifest))
        self.assertEqual(self.server.puts, [f'{self.new}/{n}' for n in names] + ['manifest.json'])
        self.assertEqual(self.server.puts[-2], f'{self.new}/core.json')
        self.assertEqual(self.server.files['manifest.json'], self.new_manifest)
        self.assertIn(f'{self.old}/core.json', self.server.files)  # previous generation retained
        entry = json.loads(self.state.read_text())['publications'][-1]
        self.assertEqual((entry['generation'], entry['previous']), (self.new, self.old))
        self.assertEqual(entry['previousManifest'].encode(), self.old_manifest)

    def test_dry_run_prints_the_ordered_plan_without_uploading(self):
        self.assertFalse(self.publish(dry_run=True))
        self.assertEqual(self.server.puts, [])
        self.assertFalse(self.state.exists())
        steps = [line for line in self.log if re.match(r'\s+\d+\. ', line)]
        self.assertIn(f'{self.new}/core.json', steps[-5])
        self.assertIn('upload data/similarity/manifest.json', steps[-3])
        self.assertIn(f'previous generation {self.old} still served', steps[-1])

    def test_failed_or_stale_gates_upload_nothing(self):
        cases = {
            'health-dist.json': json.dumps({'status': 'review', 'reasons': ['old'], 'generation': self.new}),
            'source-browser.json': json.dumps({
                'candidate': {'generation': self.new, 'precision': 'browser', 'summary': summary(wrong=.1)},
                'baseline': {'generation': self.old, 'precision': 'browser', 'summary': summary()}}),
            'probes.json': json.dumps({'generation': 'ffffffffffffffff', 'precision': 'full', 'summary': summary(),
                                       'baseline': {'generation': self.old, 'summary': summary()}}),
            'hard-negatives.json': json.dumps({
                'candidate': {'generation': self.new, 'precision': 'browser', 'summary': summary()},
                'baseline': {'generation': self.old, 'precision': 'full', 'summary': summary()}}),
            'js-tests.log': 'ℹ fail 2\n',
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                write_evidence(self.evidence, self.new, self.old, **{name: text})
                with self.assertRaisesRegex(PublicationError, name):
                    self.publish()
                self.assertEqual(self.server.puts, [])
        (self.evidence / 'aspect-probes-browser.json').unlink()
        with self.assertRaisesRegex(PublicationError, 'aspect-probes-browser.json: missing'):
            self.publish()

    def test_gates_measured_against_an_older_baseline_do_not_cover_a_newer_served_model(self):
        with self.assertRaisesRegex(PublicationError, 'not the served generation'):
            check_gates(self.evidence, self.new, 'eeeeeeeeeeeeeeee')
        self.assertTrue(check_gates(self.evidence, self.new, self.old))

    def test_interrupted_shard_upload_never_publishes_the_manifest(self):
        self.server.fail_on = f'{self.new}/core.json'
        with self.assertRaises(OSError):
            self.publish()
        self.assertEqual(self.server.files['manifest.json'], self.old_manifest)
        self.assertNotIn('manifest.json', self.server.puts)

    def test_served_bytes_that_do_not_verify_never_publish_the_manifest(self):
        self.server.corrupt.add(f'{self.new}/places-0.json')
        with self.assertRaisesRegex(PublicationError, 'manifest NOT changed'):
            self.publish()
        self.assertEqual(self.server.files['manifest.json'], self.old_manifest)

    def test_invalid_local_generation_is_refused_before_upload(self):
        (self.model / self.new / 'active-0.json').write_text('{"ids": ["1"]}')
        with self.assertRaisesRegex(PublicationError, 'invalid'):
            self.publish()
        self.assertEqual(self.server.puts, [])

    def test_already_served_generation_only_verifies(self):
        self.serve(self.new, self.new_manifest)
        self.assertFalse(self.publish())
        self.assertEqual(self.server.puts, [])

    def test_resumed_publish_skips_identical_served_shards(self):
        self.server.files[f'{self.new}/core.json'] = (self.model / self.new / 'core.json').read_bytes()
        self.assertTrue(self.publish())
        self.assertNotIn(f'{self.new}/core.json', self.server.puts)
        self.assertEqual(self.server.puts[-1], 'manifest.json')

    def test_rollback_restores_the_recorded_manifest_and_keeps_both_generations(self):
        self.publish()
        del self.server.files[f'{self.old}/tags-0.json']  # lost from the server since
        self.server.puts.clear()
        self.assertTrue(rollback(self.server, self.server, self.model, self.domain, self.state, log=self.log.append))
        self.assertEqual(self.server.puts, [f'{self.old}/tags-0.json', 'manifest.json'])
        self.assertEqual(self.server.files['manifest.json'], self.old_manifest)
        self.assertIn(f'{self.new}/core.json', self.server.files)
        self.assertEqual(json.loads(self.state.read_text())['publications'][-1]['kind'], 'rollback')

    def test_rollback_from_a_saved_manifest_file_and_dry_run(self):
        self.serve(self.new, self.new_manifest)
        saved = Path(self.temp.name) / 'rollback-manifest.json'
        saved.write_bytes(self.old_manifest)
        with self.assertRaisesRegex(PublicationError, 'pass --manifest'):
            rollback(self.server, self.server, self.model, self.domain, self.state, log=self.log.append)
        self.assertFalse(rollback(self.server, self.server, self.model, self.domain, self.state,
                                  manifest_file=saved, dry_run=True, log=self.log.append))
        self.assertEqual(self.server.puts, [])
        self.assertTrue(rollback(self.server, self.server, self.model, self.domain, self.state,
                                 manifest_file=saved, log=self.log.append))
        self.assertEqual(self.server.puts, ['manifest.json'])


class OrdinaryUploadTests(unittest.TestCase):
    def test_full_site_upload_skips_the_gated_model_and_keeps_its_state(self):
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            (dist / 'data/similarity/abc').mkdir(parents=True)
            (dist / 'data/similarity/manifest.json').write_text('{}')
            (dist / 'data/similarity/abc/core.json').write_text('{}')
            (dist / 'data/events.json').write_text('[]')
            (dist / 'index.html').write_text('<html>')
            ftp, state = Mock(), {}
            previous = {'site/data/similarity/manifest.json': 'old'}
            upload_directory(ftp, dist, 'site', previous_state=previous, new_state=state,
                             exclude=[dist / 'data/similarity'])
            renamed = [call.args[1] for call in ftp.rename.call_args_list]
            self.assertEqual(sorted(renamed), ['events.json', 'index.html'])
            self.assertEqual(state['site/data/similarity/manifest.json'], 'old')


if __name__ == '__main__':
    unittest.main()
