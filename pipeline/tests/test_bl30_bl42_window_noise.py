"""Beyond-window pruning reads past date noise (BL30 + BL42, 2026-10-12).

`chunk_is_beyond_window` kept all-2027 chunks because of dates that say nothing
about when the chunk's events happen: WordPress/Tribe bookkeeping stamps
(Ridgefield Playhouse cr-130650), dates inside URL slugs (Mount Vernon Public
Library cr-131420), year-less but weekday-pinned dates (Brooklyn Community Pride
Center cr-131417, LIU cr-131348) and a 2017 sentence in a Meetup blurb (Do the
Write Thing cr-130867). Excerpts below are trimmed from those captures.
"""
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor as ex

TODAY = date(2026, 10, 12)  # horizon = today + 90 + 30 = 2027-02-09


def _tribe_record(event_id, start):
    # One Tribe REST record: the post's own date/modified stamps, a venue
    # object created in 2018, a URL with a year in it, and the real start date.
    return (
        '{"id":%d,"author":"18","status":"publish","date":"2026-09-08 07:03:03",'
        '"date_utc":"2026-09-08 11:03:03","modified":"2026-09-15 08:37:53",'
        '"modified_utc":"2026-09-15 12:37:53",'
        '"url":"https:\\/\\/ridgefieldplayhouse.org\\/event\\/show-%d-ridgefield-ct-2027\\/",'
        '"title":"Show %d","start_date":"%s 14:00:00","end_date":"%s 15:05:00",'
        '"utc_start_date":"%s 19:00:00",'
        '"venue":{"id":77,"author":"1","status":"publish","date":"2018-07-31 19:34:15",'
        '"date_utc":"2018-07-31 19:34:15","modified":"2018-07-31 19:34:15",'
        '"modified_utc":"2018-07-31 19:34:15","venue":"The Ridgefield Playhouse"}}'
        % (event_id, event_id, event_id, start, start, start))


MOUNT_VERNON_CARD = (
    '##  [Crochet Group](https://mountvernonpubliclibrary.org/events/crochet-club-'
    '2026-07-02-2026-07-09-2026-10-08-2026-10-18-2027-03-25/)\n'
    '####  Thursday, March %d, 2027 \n#### 1:00 pm - 3:00 pm\n'
    'Come to the library to work on your crochet project.\n'
    '[Read more...](https://mountvernonpubliclibrary.org/events/crochet-club-'
    '2026-07-02-2026-07-09-2026-10-08-2026-10-18-2027-03-25/)\n')


class NoiseIsIgnoredTests(unittest.TestCase):

    def test_tribe_rest_bookkeeping_dates_do_not_hold_a_2027_chunk(self):
        chunk = ','.join(_tribe_record(45920 + i, f'2027-03-{7 + i:02d}') for i in range(3))
        self.assertFalse(ex.chunk_is_chrome_only(chunk))
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_tribe_rest_in_window_start_still_keeps(self):
        chunk = ','.join(_tribe_record(1 + i, d) for i, d in
                         enumerate(['2027-03-07', '2026-11-14', '2027-03-21']))
        self.assertFalse(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_url_slug_dates_are_ignored(self):
        chunk = ''.join(MOUNT_VERNON_CARD % d for d in (18, 25, 31))
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_weekday_pins_a_yearless_date(self):
        chunk = '\n'.join(f'[Tabletop Role Playing Games](https://x.org/e/{i})\n{d}\nBrooklyn Pride Center'
                          for i, d in enumerate(['Thu, Mar 04', 'Thu, Mar 11', 'Wed, Mar 24']))
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_weekday_pinned_title_date(self):
        chunk = ('### [Make up day for Monday, May 31](https://calendar.liu.edu/event/x)\n'
                 'Fri, Jun 4, 2027\nFri, Jun 11, 2027\nFri, Jun 18, 2027\n')
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_stale_prose_dates_are_ignored(self):
        blurb = ('Do the Write Thing will begin meeting on September 10, 2017. '
                 'Absolute last minute deadline, September 1, but sooner is better.')
        chunk = '\n'.join(f'{blurb} Sun, {d}, 2027 · 1:00 PM EST' for d in ('May 9', 'May 23', 'Jun 6'))
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_rescheduled_from_date_is_ignored(self):
        chunk = ('This event is rescheduled from October 22, 2026. ' +
                 ' '.join(f'Show on March {d}, 2027.' for d in (4, 5, 6)))
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))


class InWindowEvidenceKeepsTests(unittest.TestCase):
    FAR = ' '.join(f'Show on March {d}, 2027.' for d in (4, 5, 6))

    def test_yearless_upcoming_date_keeps(self):
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' Storytime Oct 20 10am', TODAY))

    def test_yearless_weekday_date_in_window_keeps(self):
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' Tue, Oct 20 10am', TODAY))

    def test_yearless_range_start_keeps(self):
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' On view Sep 26 – Jan 4', TODAY))

    def test_run_end_keeps(self):
        self.assertFalse(ex.chunk_is_beyond_window(
            self.FAR + ' The 2026–2027 season continues through May 21, 2027.', TODAY))

    def test_dated_range_is_not_a_run_end(self):
        chunk = self.FAR + ' Festival March 3, 2027 through March 5, 2027.'
        self.assertTrue(ex.chunk_is_beyond_window(chunk, TODAY))

    def test_recent_past_date_keeps(self):
        # A run that opened this summer may still be going.
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' Opened July 18, 2026.', TODAY))

    def test_unpinnable_weekday_keeps(self):
        # "Fri, Oct 20" fits no year in 2025-2027: the weekday is a typo, so the
        # date cannot be placed and the chunk stays.
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' Fri, Oct 20', TODAY))

    def test_in_window_json_epoch_keeps(self):
        self.assertFalse(ex.chunk_is_beyond_window(self.FAR + ' {"startDate":1792105200117}', TODAY))


class OccurrenceBudgetIgnoresSlugDatesTests(unittest.TestCase):
    """The occurrence budget counts a URL once (BL30/BL42 follow-up, 2026-10-18).

    Mount Vernon's slugs carry each series' whole date history, so the budget
    read every Crochet Group card as ~50 dates and cut cr-131420's tail into
    9 pieces of 4 cards, 3 of them too small to prune (one visible date each).
    """

    def _slug(self, n):
        return '-'.join(f'2026-{1 + k % 12:02d}-{1 + k % 28:02d}' for k in range(n))

    def _card(self, day):
        slug = self._slug(40)
        return (f'##  [Crochet Group](https://mountvernonpubliclibrary.org/events/crochet-club-{slug}/)\n'
                f'####  Thursday, March {day}, 2027 \n#### 1:00 pm - 3:00 pm\n'
                'Come to the library to work on your crochet project.\n'
                f'[Read more...](https://mountvernonpubliclibrary.org/events/crochet-club-{slug}/)\n')

    def test_dated_url_counts_once(self):
        card = self._card(4)
        self.assertGreater(ex.count_date_tokens(card), 80)
        # one printed date + two links that carry dates
        self.assertEqual(ex.count_listed_dates(card), 3)

    def test_text_without_urls_counts_as_before(self):
        text = 'Sat, Oct 24 and Sun, Oct 25 2026-10-31'
        self.assertEqual(ex.count_listed_dates(text), ex.count_date_tokens(text))

    def test_slug_dates_do_not_split_a_chunk(self):
        chunk = '\n'.join(self._card(1 + i % 28) for i in range(12))
        self.assertGreater(ex.count_date_tokens(chunk), 250)
        self.assertEqual(ex.cap_occurrences_per_chunk([chunk], budget=250), [chunk])

    def test_cards_dated_only_in_links_still_split(self):
        # A feed whose cards carry their date only in the link still demands one
        # occurrence per card, so the budget still cuts it.
        chunk = '\n'.join(f'### [Show {i}](https://x.org/e/show-2026-11-{1 + i % 28:02d}/)\nDoors 7pm'
                          for i in range(30))
        self.assertEqual(ex.count_listed_dates(chunk), 30)
        self.assertGreater(len(ex.cap_occurrences_per_chunk([chunk], budget=10)), 1)


if __name__ == '__main__':
    unittest.main()
