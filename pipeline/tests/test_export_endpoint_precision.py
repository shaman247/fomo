"""Synthesized span endpoints are exported as precision marks, not dates (BL12).

Run: ./venv/bin/python pipeline/tests/test_export_endpoint_precision.py
"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import exporter

D = date.fromisoformat


def raw(kind, sd, ed):
    return json.dumps({'occurrence_provenance': {'version': 1, 'entries': [], 'endpoints': [
        {'slot': [sd, '', ed, ''], 'kind': kind}]}})


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, args=()):
        self.sql = sql

    def fetchall(self):
        return self.rows


def load(rows):
    return exporter.load_endpoint_precision(Cursor(rows), D('2026-10-23'), D('2027-01-21'))


class EndpointPrecisionTests(unittest.TestCase):
    def test_marked_as_of_start(self):
        rows = [(1, D('2026-10-19'), D('2026-11-08'), D('2026-10-19'), D('2026-10-19'),
                 raw('start_as_of_crawl', '2026-10-19', '2026-11-08'))]
        self.assertEqual(load(rows), {(1, '2026-10-19', '2026-11-08'): {'start': 'as_of'}})

    def test_marked_open_run_horizon(self):
        rows = [(2, D('2026-10-20'), D('2026-12-19'), D('2026-10-20'), D('2026-10-20'),
                 raw('end_open_run_horizon', '2026-10-20', '2026-12-19'))]
        self.assertEqual(load(rows), {(2, '2026-10-20', '2026-12-19'): {'end': 'open'}})

    def test_legacy_crawl_recognised_by_arithmetic(self):
        # Paley 273483: crawled 2026-10-01, end = crawl + 60 days, no markers yet.
        rows = [(3, D('2026-09-18'), D('2026-11-30'), D('2026-10-01'), D('2026-10-01'), None),
                (4, D('2026-10-02'), D('2027-01-03'), D('2026-10-02'), D('2026-10-02'), None)]
        self.assertEqual(load(rows), {(3, '2026-09-18', '2026-11-30'): {'end': 'open'},
                                      (4, '2026-10-02', '2027-01-03'): {'start': 'as_of'}})

    def test_post_marker_crawl_without_mark_is_exact(self):
        # Published end that happens to fall 60 days after a marked-era crawl.
        rows = [(5, D('2026-10-10'), D('2026-12-19'), D('2026-10-20'), D('2026-10-20'), None)]
        self.assertEqual(load(rows), {})

    def test_one_publishing_owner_keeps_endpoint_exact(self):
        rows = [(6, D('2026-10-19'), D('2026-11-08'), D('2026-10-19'), D('2026-10-19'),
                 raw('start_as_of_crawl', '2026-10-19', '2026-11-08')),
                (6, D('2026-10-19'), D('2026-11-08'), D('2026-10-22'), D('2026-10-22'), None)]
        self.assertEqual(load(rows), {})


if __name__ == '__main__':
    unittest.main()
