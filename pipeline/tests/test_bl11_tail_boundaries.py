"""Card integrity across chunk cuts: BL11 residuals fixed 2026-10-07.

Fixtures are trimmed real crawl excerpts (`fixtures/bl11_tail_boundaries.json`);
each case names the capture it came from. Every assertion here failed on the
engine before these fixes (Kids in Motion only under some PYTHONHASHSEED values).
"""
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import extractor as ex
from extractor import (cap_occurrences_per_chunk, carry_boundary_context,
                       chunk_is_beyond_window)

FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'bl11_tail_boundaries.json')
                      .read_text(encoding='utf-8'))


def _first_heading(chunk):
    return next((l for l in chunk.split('\n') if ex._is_heading_line(l)), None)


class WeekdayContradictedYearTests(unittest.TestCase):
    # Lincoln Center Presents cr127681 (2026-09-28): `#### Monday, September 28,
    # 2027` cards under `## Monday September 28, 2026`. September 28 is a Monday
    # in 2026, not 2027.
    case = FIXTURES['lincoln_wrong_year_cards']
    crawled = date(2026, 9, 28)

    def test_cards_are_read_in_the_year_their_weekday_names(self):
        self.assertFalse(chunk_is_beyond_window(self.case['content'], self.crawled))

    def test_truly_far_cards_are_still_pruned(self):
        # Feb-Mar 2027 cards printed as 2028: beyond the window either way.
        self.assertTrue(chunk_is_beyond_window(self.case['spring'], self.crawled))

    def test_a_weekday_typo_does_not_move_the_year(self):
        # SOPAC cr127306 printed `SUN, MAR 6, 2027` (a Saturday); no adjacent
        # year makes March 6 a Sunday, so the printed year stands.
        self.assertEqual(ex._weekday_year_corrections('SUN, MAR 6, 2027 at 2PM'), [])
        self.assertEqual(ex._weekday_year_corrections('Monday, September 28, 2027'),
                         [(date(2027, 9, 28), date(2026, 9, 28))])


class OccurrenceCapTests(unittest.TestCase):
    def test_a_cards_own_leadin_is_not_repeated_onto_other_pieces(self):
        # Brooklyn Children's Museum cr127245: the chunk opens on its first
        # card's `Friday, November 27` + image; that lead-in was stamped onto
        # the piece opening on the December 18 card.
        content = FIXTURES['bcm_leadin_preamble']['content']
        first = content.split('\n')[0]
        for budget in range(10, 120, 5):
            pieces = cap_occurrences_per_chunk([content], budget=budget)
            for piece in pieces[1:]:
                self.assertFalse(piece.startswith(first), f'budget {budget}')

    def test_the_moved_card_gets_its_own_date(self):
        content = FIXTURES['bcm_leadin_preamble']['content']
        lines = content.split('\n')
        for budget in range(10, 120, 5):
            raw = cap_occurrences_per_chunk([content], budget=budget)
            # Without a repeated preamble the pieces are contiguous source slices.
            self.assertEqual('\n'.join(raw), content)
            carried = carry_boundary_context(raw)
            offset = 0
            for before, after in zip(raw, carried):
                piece = before.split('\n')
                title = next((i for i, l in enumerate(piece) if l.startswith('## [')), None)
                if title is not None:
                    own = next(l for l in reversed(lines[:offset + title])
                               if ex._is_boundary_date_line(l))
                    head = after.split('\n')
                    t = next(i for i, l in enumerate(head) if l.startswith('## ['))
                    leading = [l for l in head[:t] if ex._is_boundary_date_line(l)]
                    self.assertEqual(leading[-1:], [own], f'budget {budget}')
                offset += len(piece)

    def test_date_and_time_headings_are_not_split_points(self):
        # Mount Vernon Public Library cr127259: `##  [Crochet Group](…)` /
        # `####  Thursday, October 15, 2026` / `#### 1:00 pm - 3:00 pm`.
        content = FIXTURES['mount_vernon_detail_headings']['content']
        for budget in range(10, 200, 10):
            pieces = cap_occurrences_per_chunk([content], budget=budget)
            self.assertEqual(''.join(p.replace('\n', '') for p in pieces),
                             content.replace('\n', ''))
            for piece in pieces:
                plines = piece.split('\n')
                first = next(i for i, l in enumerate(plines) if ex._is_heading_line(l))
                self.assertFalse(ex._is_card_detail_heading(plines, first), (budget, plines[first]))
                self.assertIsNone(ex._BOUNDARY_TIME_RE.fullmatch(ex._boundary_text(plines[first])))
                self.assertFalse(ex._is_boundary_date_line(plines[first]), (budget, plines[first]))


class LeadinWalkTests(unittest.TestCase):
    def test_walk_crosses_a_venue_line_between_date_and_title(self):
        # Brooklyn Society for Ethical Culture cr124275: `03 November` /
        # `7:00 pm - 8:30 pm` / `Brooklyn Ethical` / image / `#### [Title](…)`.
        content = FIXTURES['bsec_venue_between_date_and_title']['content']
        kept, carried = ex._split_trailing_record(content, len(content), ('h', 4, True))
        self.assertEqual(carried.split('\n')[:3], ['15 September', '7:00 pm - 8:30 pm', 'Brooklyn Ethical'])
        self.assertTrue(kept.rstrip().startswith('#### [Issues and Action Discussion Circle]'))
        self.assertTrue(kept.rstrip().endswith('(https://bsec.org/events/issues-and-action-discussion-circle/)'))

    def test_walk_stops_at_a_previous_cards_link(self):
        content = FIXTURES['bsec_venue_between_date_and_title']['content']
        lines = content.split('\n')
        title = next(i for i, l in enumerate(lines) if 'Brooklyn Women’s Chorus' in l)
        start = ex._leadin_walk_start(lines, title)
        self.assertTrue(lines[start - 1].startswith('[View Detail]'))


class GoverningDateTests(unittest.TestCase):
    def _split_at(self, content, marker):
        i = content.index(marker)
        return [content[:i].rstrip('\n'), content[i:]]

    def test_no_date_is_copied_across_site_navigation(self):
        # Powerhouse Arts cr128804: the last card's `Nov 4` was copied onto
        # `## stay connected` across the footer's link menus.
        chunks = self._split_at(FIXTURES['powerhouse_footer']['content'], '## stay connected')
        self.assertEqual(carry_boundary_context(chunks), chunks)

    def test_a_card_with_its_own_date_below_gets_no_other_date(self):
        # Ballet Hispánico cr122551: `## EN FAMILIA / FAMILY MATINEE` /
        # `### Saturday, April 10, 2027 | 2:00PM` was given `Sunday, April 11, 2 PM`.
        chunks = self._split_at(FIXTURES['ballet_own_date_below']['content'], '* * *')
        self.assertNotIn('Sunday, April 11, 2 PM', carry_boundary_context(chunks)[1])


class CardSignatureDeterminismTests(unittest.TestCase):
    def test_tied_votes_pick_the_heading_that_opens_the_card(self):
        # NYC Parks Kids in Motion cr127583: `### [Kids In Motion: …](…)` and its
        # `#### at <Playground>` subtitle share every vote.
        lines = FIXTURES['kids_in_motion_tied_votes']['content'].split('\n')
        self.assertEqual(ex._leadin_card_signature(lines), ('h', 3, True))

    def test_signature_does_not_depend_on_hash_seed(self):
        script = ('import json, sys; sys.path.insert(0, sys.argv[1]); import extractor as ex; '
                  'c = json.load(open(sys.argv[2], encoding="utf-8"))["kids_in_motion_tied_votes"]["content"]; '
                  'print(ex._leadin_card_signature(c.split("\\n")))')
        fixture = Path(__file__).parent / 'fixtures' / 'bl11_tail_boundaries.json'
        seen = set()
        for seed in ('0', '1', '2', '3'):
            out = subprocess.run([sys.executable, '-c', script, str(PIPELINE), str(fixture)],
                                 env={**os.environ, 'PYTHONHASHSEED': seed},
                                 capture_output=True, text=True, check=True)
            seen.add(out.stdout.strip().splitlines()[-1])
        self.assertEqual(seen, {"('h', 3, True)"})


if __name__ == '__main__':
    unittest.main()
