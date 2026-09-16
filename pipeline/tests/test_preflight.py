"""Disk limits must stop work before a database connection or crawl starts."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preflight


class DiskPreflightTests(unittest.TestCase):
    def check(self, free_gib, **kwargs):
        lines = []
        usage = Mock(free=int(free_gib * preflight.GIB))
        with patch.object(preflight.shutil, 'disk_usage', return_value=usage), \
                patch.object(preflight, 'largest_scratch_directories', return_value=([], None)) as scan:
            ok = preflight.run_disk_preflight(report=lines.append, **kwargs)
        return ok, '\n'.join(lines), scan

    def test_healthy_run_skips_expensive_directory_scan(self):
        ok, output, scan = self.check(70)
        self.assertTrue(ok)
        self.assertIn('OK', output)
        scan.assert_not_called()

    def test_warning_reports_scratch_but_allows_run(self):
        ok, output, scan = self.check(10)
        self.assertTrue(ok)
        self.assertIn('WARNING', output)
        scan.assert_called_once()

    def test_critical_space_stops_run(self):
        ok, output, _ = self.check(4.9)
        self.assertFalse(ok)
        self.assertIn('stopped before database work', output)

    def test_exact_thresholds(self):
        self.assertTrue(self.check(5)[0])
        self.assertIn('WARNING', self.check(5)[1])
        self.assertIn('OK', self.check(20)[1])

    def test_explicit_scratch_report_on_healthy_disk(self):
        ok, _, scan = self.check(70, report_scratch=True)
        self.assertTrue(ok)
        scan.assert_called_once()

    def test_unknown_disk_space_stops_run(self):
        with patch.object(preflight.shutil, 'disk_usage', side_effect=OSError('unavailable')):
            self.assertFalse(preflight.run_disk_preflight(report=lambda _: None))

    def test_bad_thresholds_fail(self):
        with self.assertRaises(ValueError):
            self.check(70, min_free_gib=20, warn_free_gib=5)

    def test_directory_scan_sorts_and_excludes_total(self):
        root = Path('/fixture')
        result = Mock(returncode=0, stdout='1024\t/fixture/.scratch/small\n'
                      '4096\t/fixture/.scratch/large\n5120\t/fixture/.scratch\n')
        with patch.object(Path, 'is_dir', return_value=True), \
                patch.object(preflight.subprocess, 'run', return_value=result):
            rows, warning = preflight.largest_scratch_directories(root)
        self.assertIsNone(warning)
        self.assertEqual([path.name for path, _ in rows], ['large', 'small'])

    def test_directory_scan_timeout_does_not_hide_disk_failure(self):
        with patch.object(Path, 'is_dir', return_value=True), \
                patch.object(preflight.subprocess, 'run',
                             side_effect=preflight.subprocess.TimeoutExpired('du', 10)):
            rows, warning = preflight.largest_scratch_directories('/fixture')
        self.assertEqual(rows, [])
        self.assertIn('unavailable', warning)

    def test_pipeline_modes_stop_before_database_connection(self):
        import main
        with patch.object(main, 'run_disk_preflight', return_value=False), \
                patch.object(main.db, 'create_connection') as connect:
            self.assertFalse(asyncio.run(main.run_pipeline()))
            self.assertFalse(main.run_merge_only())
            self.assertFalse(main.run_export_dataset_only())
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
