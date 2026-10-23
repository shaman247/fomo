"""BL21: compute_voted_tags keeps a held tag while >= 15% of crawls carry it.

Adding a tag still needs max(2, ceil(30%)) crawl votes (or a curated tag in the
current crawl); a tag the event already holds survives down to
source_metadata.tag_keep_threshold. The title-only branch is unchanged.

Run: cd pipeline/tests && PYTHONPATH=..:../.. ../../venv/bin/python test_tag_vote_hysteresis.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merger import compute_voted_tags


class VoteCursor:
    """Answers compute_voted_tags' queries from counts, a crawl total and held names."""

    def __init__(self, counts, total, held=(), described=True):
        self.counts, self.total, self.held, self.described = counts, total, held, described
        self.result = None
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if 'SELECT EXISTS' in sql:
            self.result = [(int(self.described),)]
        elif 'GROUP BY cet.tag' in sql:
            self.result = list(self.counts.items())
        elif 'FROM event_tags' in sql:
            self.result = [(name,) for name in self.held]
        else:
            self.result = [(self.total,)]

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]


CURATED = {'Music', 'Live Music', 'DJ'}
ROOTS = {'music'}


def vote(counts, total_existing, current, held=(), described=None):
    cursor = VoteCursor(counts, total_existing, held)
    return set(compute_voted_tags(cursor, 1, current, CURATED, {}, ROOTS,
                                  current_described=described)), cursor


class HysteresisTests(unittest.TestCase):

    def test_held_tag_survives_between_keep_and_add_thresholds(self):
        # 10 crawls total (9 linked + current): add needs 3, keep needs 2.
        tags, _ = vote({'Music': 9, 'Live Music': 2}, 9, ['Music'], held={'Music', 'Live Music'})
        self.assertIn('Live Music', tags)

    def test_same_count_does_not_add_an_unheld_tag(self):
        tags, _ = vote({'Music': 9, 'Live Music': 2}, 9, ['Music'], held={'Music'})
        self.assertNotIn('Live Music', tags)

    def test_held_tag_below_keep_threshold_is_dropped(self):
        # 20 crawls: keep threshold ceil(3.0) = 3; 2 votes is not enough.
        tags, _ = vote({'Music': 19, 'DJ': 2}, 19, ['Music'], held={'Music', 'DJ'})
        self.assertNotIn('DJ', tags)

    def test_held_keyword_also_gets_hysteresis(self):
        tags, _ = vote({'Music': 9, 'vinyl night': 2}, 9, ['Music'],
                       held={'Music', 'vinyl night'})
        self.assertIn('vinyl night', tags)

    def test_add_rule_and_current_curated_exemption_unchanged(self):
        tags, _ = vote({'Music': 9, 'DJ': 3}, 9, ['Music', 'Live Music'], held={'Music'})
        self.assertEqual(tags, {'Music', 'DJ', 'Live Music'})

    def test_title_only_branch_ignores_held_tags(self):
        cursor = VoteCursor({}, 0, held={'Music', 'DJ'}, described=False)
        tags = set(compute_voted_tags(cursor, 1, ['Music'], CURATED, {}, ROOTS,
                                      current_described=False))
        self.assertEqual(tags, {'Music'})
        self.assertFalse(any('FROM event_tags' in sql for sql in cursor.sql))


if __name__ == '__main__':
    unittest.main()
