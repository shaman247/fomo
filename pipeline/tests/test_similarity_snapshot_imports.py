"""Snapshot eligibility must not import the browser/extraction runtime."""
import subprocess
import sys
import unittest
from pathlib import Path


class SnapshotImportTests(unittest.TestCase):
    def test_snapshot_reader_does_not_require_crawler_stack(self):
        root = Path(__file__).resolve().parents[2]
        probe = '''
import importlib.abc
import sys
sys.path.insert(0, 'pipeline')
class NoBrowserStack(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'exporter', 'processor', 'crawler', 'crawl4ai'}:
            raise AssertionError('Snapshot imported browser stack: ' + fullname)
sys.meta_path.insert(0, NoBrowserStack())
import db
db.create_connection = lambda: None
from similarity import read_snapshot
try:
    read_snapshot()
except RuntimeError as exc:
    assert str(exc) == 'Database unavailable; no model was changed', str(exc)
else:
    raise AssertionError('Expected the mocked database boundary')
'''
        result = subprocess.run([sys.executable, '-c', probe], cwd=root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
