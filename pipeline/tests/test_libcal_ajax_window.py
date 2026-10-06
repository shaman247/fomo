"""libcal_ajax covers the full FUTURE_WINDOW_DAYS window (was a 45-day loop).

The plugin reads the count-capped 'Upcoming Events' list for the near dates
and per-day lists from that list's (possibly partial) last date onward.
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from constants import FUTURE_WINDOW_DAYS
try:
    from sources import libcal_ajax as plugin
except ImportError:
    plugin = None

TODAY = date(2026, 10, 2)
HOST = 'npl.libcal.com'


def ev(eid, d, title='Program', **kw):
    out = {'id': eid, 'ymd': d.strftime('%Y%m%d'),
           'startdt': f'{d.isoformat()} 10:00:00', 'title': title,
           'url': f'https://{HOST}/event/{eid}', 'location': 'Main Library',
           'start': '10:00am', 'end': '11:00am', 'dayfull': d.strftime('%A')}
    out.update(kw)
    return out


class FakeLibCal:
    """Serves /ajax/calendar/list pages from a per-day inventory."""

    def __init__(self, by_day, upcoming=None, upcoming_error=False):
        self.by_day = by_day          # date -> list of events listed that day
        self.upcoming = upcoming      # list served for date=0000-00-00
        self.upcoming_error = upcoming_error
        self.calls = []

    def __call__(self, host, date_param, page):
        self.calls.append((date_param, page))
        if date_param == '0000-00-00':
            if self.upcoming_error:
                raise ValueError('bad json')
            rows = self.upcoming or []
        else:
            rows = self.by_day.get(date.fromisoformat(date_param), [])
        per = plugin._PERPAGE
        return {'total_results': len(rows), 'perpage': per,
                'results': rows[(page - 1) * per:page * per]}

    def day_calls(self):
        return sorted({date.fromisoformat(dp) for dp, _ in self.calls
                       if dp != '0000-00-00'})


@unittest.skipIf(plugin is None, 'deployment-specific source plugin not installed')
class LibCalWindowTests(unittest.TestCase):

    def collect(self, fake):
        with patch.object(plugin, '_get_list_page', fake):
            return plugin._collect_occurrences(HOST, TODAY, plugin._WINDOW_DAYS)

    def test_window_is_the_pipeline_window(self):
        self.assertEqual(plugin._WINDOW_DAYS, FUTURE_WINDOW_DAYS)

    def test_reaches_window_end_beyond_upcoming_cap(self):
        end = TODAY + timedelta(days=FUTURE_WINDOW_DAYS)
        weekly = [TODAY + timedelta(days=7 * i) for i in range(14)]
        by_day = {d: [ev(f'w{i}', d, 'Job Search Drop-In')] for i, d in enumerate(weekly)}
        by_day.setdefault(end, []).append(ev('last', end))
        by_day[end + timedelta(days=1)] = [ev('past-window', end + timedelta(days=1))]
        # Upcoming list stops after 5 weeks (count cap).
        upcoming = [e for d in sorted(by_day) if TODAY < d <= TODAY + timedelta(days=35)
                    for e in by_day[d]]
        fake = FakeLibCal(by_day, upcoming)
        ids = [o['id'] for o in self.collect(fake)]
        self.assertIn('last', ids)
        self.assertIn('w12', ids)            # Dec 18 occurrence of a weekly series
        self.assertNotIn('past-window', ids)
        self.assertEqual(len(ids), len(set(ids)))
        # Per-day only for today and from the upcoming list's last date on.
        days = fake.day_calls()
        self.assertEqual(days[0], TODAY)
        self.assertEqual(days[1], TODAY + timedelta(days=35))
        self.assertEqual(days[-1], end)
        self.assertEqual(len(days), 1 + (FUTURE_WINDOW_DAYS - 35 + 1))

    def test_partial_last_upcoming_day_is_refetched(self):
        d = TODAY + timedelta(days=10)
        full = [ev(f'd{i}', d) for i in range(5)]
        upcoming = [ev('early', TODAY + timedelta(days=3))] + full[:2]
        fake = FakeLibCal({d: full, TODAY + timedelta(days=3): [upcoming[0]]}, upcoming)
        ids = [o['id'] for o in self.collect(fake)]
        self.assertEqual(sorted(i for i in ids if i.startswith('d')),
                         ['d0', 'd1', 'd2', 'd3', 'd4'])
        self.assertEqual(ids.count('early'), 1)
        self.assertNotIn(TODAY + timedelta(days=3), fake.day_calls())

    def test_today_comes_from_day_list_and_ongoing_events_are_skipped(self):
        started = ev('exhibit', TODAY - timedelta(days=20))
        morning = ev('morning', TODAY)
        upcoming = [started, ev('tomorrow', TODAY + timedelta(days=1)),
                    ev('cap', TODAY + timedelta(days=5))]
        fake = FakeLibCal({TODAY: [morning, started]}, upcoming)
        ids = [o['id'] for o in self.collect(fake)]
        self.assertIn('morning', ids)
        self.assertIn('tomorrow', ids)
        self.assertNotIn('exhibit', ids)

    def test_day_with_more_than_one_page(self):
        d = TODAY + timedelta(days=60)
        rows = [ev(f'x{i}', d) for i in range(plugin._PERPAGE + 30)]
        fake = FakeLibCal({d: rows}, [])
        ids = {o['id'] for o in self.collect(fake)}
        self.assertEqual(len(ids), plugin._PERPAGE + 30)
        self.assertIn((d.isoformat(), 2), fake.calls)

    def test_short_page_ends_paging_despite_overcounted_total(self):
        d = TODAY + timedelta(days=60)
        fake = FakeLibCal({d: [ev('a', d)]}, [])
        real = fake.__call__

        def overcount(host, date_param, page):
            data = real(host, date_param, page)
            data['total_results'] += 1   # LibCal counts a hidden row
            return data

        with patch.object(plugin, '_get_list_page', overcount):
            plugin._collect_occurrences(HOST, TODAY, plugin._WINDOW_DAYS)
        self.assertNotIn((d.isoformat(), 2), fake.calls)

    def test_upcoming_failure_falls_back_to_every_day(self):
        end = TODAY + timedelta(days=FUTURE_WINDOW_DAYS)
        fake = FakeLibCal({end: [ev('last', end)]}, upcoming_error=True)
        with patch('builtins.print'):
            ids = [o['id'] for o in self.collect(fake)]
        self.assertEqual(ids, ['last'])
        self.assertEqual(len(fake.day_calls()), FUTURE_WINDOW_DAYS + 1)

    def test_transient_error_is_retried_once(self):
        calls = []

        def flaky(url, timeout=30, headers=None):
            calls.append(url)
            if len(calls) == 1:
                raise TimeoutError('slow')
            return {'total_results': 0, 'results': []}

        with patch.object(plugin, 'get_json', flaky), patch.object(plugin, '_RETRY_DELAY', 0):
            self.assertEqual(plugin._get_list_page(HOST, '2026-10-02', 1)['results'], [])
        self.assertEqual(len(calls), 2)

    def test_markdown_lists_december_dates_in_order(self):
        dates = [TODAY + timedelta(days=7 * i) for i in range(12)]
        by_day = {d: [ev(f'm{i}', d, 'Maker Space')] for i, d in enumerate(dates)}
        upcoming = [e for d in dates[:4] for e in by_day[d]]
        fake = FakeLibCal(by_day, upcoming)
        with patch.object(plugin, '_get_list_page', fake), \
                patch.object(plugin, 'date', wraps=date) as fake_date:
            fake_date.today.return_value = TODAY
            body, count = plugin.fetch_and_build_markdown([f'https://{HOST}/calendar/?cid=-1&t=d'])
        self.assertEqual(count, 1)
        listed = [line[2:12] for line in body.splitlines() if line.startswith('- 2026')]
        self.assertEqual(listed, [d.isoformat() for d in dates])
        self.assertIn('2026-12-18', listed)


@unittest.skipIf(plugin is None, 'deployment-specific source plugin not installed')
class LibCalOnlineEventTests(unittest.TestCase):
    """online_event rows are emitted (2026-10-06): online-only -> 'Online'
    placeholder + Format line; hybrid keeps its physical branch."""

    def build(self, host, rows):
        d = TODAY + timedelta(days=3)
        fake = FakeLibCal({d: rows}, [])
        with patch.object(plugin, '_get_list_page', fake), \
                patch.object(plugin, 'date', wraps=date) as fake_date:
            fake_date.today.return_value = TODAY
            return plugin.fetch_and_build_markdown([f'https://{host}/calendar/?cid=-1&t=d'])

    def cards(self, body):
        return {c.split(']')[0].lstrip('['): c for c in body.split('### ')[1:]}

    def test_online_only_and_hybrid_are_emitted(self):
        d = TODAY + timedelta(days=3)
        rows = [
            ev('v', d, 'Chair Yoga (Virtual)', location='', calendar='Events Calendar',
               campus='', online_event=True),
            ev('h', d, 'Tai-Chi (HYBRID)', location='Community Room',
               calendar='Events Calendar', campus='', online_event=True),
            ev('p', d, 'Story Time', location='Community Room', calendar='Events Calendar'),
        ]
        body, count = self.build('eastmeadow.libcal.com', rows)
        self.assertEqual(count, 3)
        cards = self.cards(body)
        self.assertIn('**Venue**: Online\n**Format**: Online only', cards['Chair Yoga (Virtual)'])
        self.assertIn('**Venue**: Community Room\n**Format**: Hybrid', cards['Tai-Chi (HYBRID)'])
        self.assertNotIn('**Format**', cards['Story Time'])

    def test_online_only_bypasses_single_building_canon(self):
        d = TODAY + timedelta(days=3)
        rows = [ev('v', d, 'Webinar', location='', calendar='Program Events',
                   online_event=True),
                ev('h', d, 'Yoga', location='Helen Kraus Room', online_event=True)]
        cards = self.cards(self.build('rvcpl.libcal.com', rows)[0])
        self.assertIn('**Venue**: Online', cards['Webinar'])
        self.assertIn('**Venue**: Rockville Centre Public Library\n**Format**: Hybrid',
                      cards['Yoga'])

    def test_monmouth_online_placeholders(self):
        d = TODAY + timedelta(days=3)
        cal = 'Monmouth County Library Events'
        rows = [
            ev('a', d, 'Virtual Author Talk', location='ONLINE', campus='ONLINE',
               calendar=cal, online_event=True),
            ev('b', d, 'Support Group', location='Headquarters, Manalapan, ONLINE',
               campus='Headquarters, Manalapan', calendar=cal, online_event=True),
            ev('c', d, 'Hybrid Book Discussion', location='ONLINE',
               campus='Headquarters, Manalapan', calendar=cal, online_event=True),
        ]
        cards = self.cards(self.build('monmouthcountylib.libcal.com', rows)[0])
        self.assertIn('**Venue**: Online\n', cards['Virtual Author Talk'])
        for title in ('Support Group', 'Hybrid Book Discussion'):
            self.assertIn('**Venue**: Monmouth County Library Headquarters\n**Format**: Hybrid',
                          cards[title])

    def test_same_title_online_and_in_person_stay_separate(self):
        d = TODAY + timedelta(days=3)
        rows = [ev('a', d, 'Book Club', location='Community Room'),
                ev('b', d, 'Book Club', location='', online_event=True)]
        body, count = self.build('eastmeadow.libcal.com', rows)
        self.assertEqual(count, 2)


if __name__ == '__main__':
    unittest.main()
