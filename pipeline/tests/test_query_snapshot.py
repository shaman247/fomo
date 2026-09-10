import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from query_snapshot import write_query_snapshot
import uploader


class QuerySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'pipeline').mkdir()
        self.data = self.root / 'src/data'
        self.data.mkdir(parents=True)
        records = {'manifest.json': {'days': ['2026-09-09'], 'remainderChunks': [], 'exportedAt': '2026-09-09T00:00:00Z'},
                   'tag_hierarchy.json': {'tags': []}, 'organizers.json': {},
                   'events.day0.json': [], 'events.day0.desc.json': {}, 'locations.day0.json': []}
        for name, value in records.items():
            (self.data / name).write_text(json.dumps(value))

    def test_inventory_changes_with_data_and_excludes_stale_chunks(self):
        (self.data / 'events.stale.json').write_text('[]')
        first = write_query_snapshot(self.data, 'fixture')
        self.assertNotIn('events.stale.json', first['files'])
        self.assertEqual(first['sourceExportedAt'], '2026-09-09T00:00:00Z')
        self.assertEqual(first['revision'], write_query_snapshot(self.data, 'fixture')['revision'])
        (self.data / 'events.day0.json').write_text('[{"id":42}]')
        self.assertNotEqual(first['revision'], write_query_snapshot(self.data, 'fixture')['revision'])
        self.assertTrue((self.data / 'query.schema.json').exists())

    def test_missing_companion_does_not_replace_last_manifest(self):
        write_query_snapshot(self.data, 'fixture')
        original = (self.data / 'query-manifest.json').read_bytes()
        (self.data / 'events.day0.desc.json').unlink()
        with self.assertRaises(FileNotFoundError):
            write_query_snapshot(self.data, 'fixture')
        self.assertEqual((self.data / 'query-manifest.json').read_bytes(), original)

    def upload(self, fail=False):
        uploaded = []
        class FTP:
            def __init__(self, *args, **kwargs): pass
            def login(self, *args): pass
            def cwd(self, *args): pass
            def quit(self): pass
            def storbinary(self, command, file):
                if fail and command.endswith('events.day0.json'):
                    raise OSError('simulated failure')
                uploaded.append(command.removeprefix('STOR '))
        with patch.object(uploader, 'SCRIPT_DIR', str(self.root / 'pipeline')), patch.object(uploader, 'FTP', FTP), patch.object(uploader, 'load_dotenv'), patch.dict(os.environ, {'FTP_HOST': 'fixture.invalid', 'FTP_USER': 'fixture', 'FTP_PASSWORD': 'fixture'}):
            success = uploader.upload()
        return success, uploaded

    def test_upload_includes_catalog_and_publishes_inventory_last(self):
        success, uploaded = self.upload()
        self.assertTrue(success)
        self.assertEqual(uploaded[-1], 'query-manifest.json')
        for name in ['manifest.json', 'tag_hierarchy.json', 'organizers.json', 'query.schema.json']:
            self.assertIn(name, uploaded)

    def test_failed_payload_prevents_inventory_publication(self):
        success, uploaded = self.upload(fail=True)
        self.assertFalse(success)
        self.assertNotIn('query-manifest.json', uploaded)
        self.assertIn('organizers.json', uploaded)
