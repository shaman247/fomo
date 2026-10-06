"""Regression coverage for two reviewed complete-window source deployments."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import site_profiles
try:
    from sources import baldwin_window as baldwin, stpaul_window as church
except ImportError:
    baldwin = church = None


class Response:
    def __init__(self, text='', error=False):
        self.text, self.error = text, error

    def raise_for_status(self):
        if self.error:
            raise RuntimeError('Publisher unavailable')


class Session:
    def __init__(self, responses):
        self.responses, self.headers, self.calls = iter(responses), {}, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return next(self.responses)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def baldwin_month(year, month, day, name='Book Discussion', classes='', url='book'):
    import calendar
    return (f'<h1>{calendar.month_name[month]} {year}</h1><main class="calendar-days">'
            f'<div class="day day-{year}-{month:02}-{day:02}"><div class="listing-event {classes}">'
            '<h2><span class="event-day">Published day</span><span class="event-time">2–3 PM</span>'
            '<span class="event-location">Small Meeting Room</span></h2>'
            f'<h3><a href="https://baldwinpl.assabetinteractive.com/calendar/{url}/">{name}</a></h3>'
            '<div class="event-description-excerpt">Own book topic</div></div></div></main>')


def church_month(month, records, mobile=True):
    data = json.dumps({'grid_date': f'2026-{month:02}-01'})
    parts = [f'<script data-js="tribe-events-view-data">{data}</script>', '<div class="tribe-events-calendar-month">']
    for day, slug, category in records:
        url = f'https://stpaulandstandrew.org/event/{slug}/2026-{month:02}-{day:02}/'
        parts.append(f'<article class="tribe-events-calendar-month__calendar-event tribe_events_cat-{category}">'
                     f'<a class="tribe-events-calendar-month__calendar-event-title-link" href="{url}">{slug}</a>'
                     '<div class="tribe-events-calendar-month__calendar-event-tooltip-datetime">'
                     f'<time datetime="2026-{month:02}-{day:02}">11am–noon</time></div>'
                     '<div class="tribe-events-calendar-month__calendar-event-tooltip-description">Join online or in person</div></article>')
        if mobile:
            parts.append('<article class="tribe-events-calendar-month-mobile-events__mobile-event">'
                         f'<a class="tribe-events-calendar-month-mobile-events__mobile-event-title-link" href="{url}">{slug}</a></article>')
    return ''.join(parts) + '</div>'


@unittest.skipIf(baldwin is None, 'Deployment plugins absent')
class BaldwinWindowTests(unittest.TestCase):
    def test_all_intersecting_months_and_year_rollover(self):
        self.assertEqual(list(baldwin.months_between(date(2026, 12, 1), date(2027, 2, 28))),
                         [(2026, 12), (2027, 1), (2027, 2)])
        session = Session([Response(baldwin_month(2026, m, 20, url=f'book-{m}')) for m in (10, 11, 12)])
        with patch.object(baldwin, 'get_active_date_window', return_value=(date(2026, 10, 1), date(2026, 12, 30))), patch.object(baldwin.requests, 'Session', return_value=session):
            md, count = baldwin.fetch_and_build_markdown(['https://baldwinpl.assabetinteractive.com/calendar/{{year}}-{{month}}/'])
        self.assertEqual(count, 3)
        self.assertIn('2026-12-20', md)
        self.assertTrue(session.calls[-1].endswith('2026-december/'))

    def test_later_month_failure_never_returns_partial_calendar(self):
        session = Session([Response(baldwin_month(2026, 10, 20)), Response(error=True)])
        with patch.object(baldwin, 'get_active_date_window', return_value=(date(2026, 10, 1), date(2026, 12, 30))), patch.object(baldwin.requests, 'Session', return_value=session):
            with self.assertRaises(RuntimeError):
                baldwin.fetch_and_build_markdown(['https://baldwinpl.assabetinteractive.com/calendar/2026-october/'])

    def test_offsite_detail_and_multiday_evidence_survive(self):
        row = baldwin.parse_month(baldwin_month(2026, 10, 20, classes='branch-off-site-location'), 2026, 10, date(2026, 10, 1), date(2026, 12, 30))[0]
        other = dict(row, date='2026-10-21', header='Until 3 PM')
        detail = baldwin.detail_text('<main><div class="single-event"><h2>Book Discussion</h2><h3>October20–21</h3><div class="event-description">At Baldwin Park, 3232 Grand Ave. <a href="https://example.org">Meeting directions</a></div><ul class="event-addtocalendar"><li>Calendar boilerplate</li></ul></div></main>')
        md, count = baldwin.build_markdown([row, other], {row['url']: detail})
        self.assertEqual(count, 1)
        self.assertIn('2026-10-20, 2026-10-21', md)
        self.assertIn('3232 Grand Ave', md)
        self.assertIn('https://example.org', md)
        self.assertNotIn('Calendar boilerplate', md)
        with self.assertRaises(ValueError):
            baldwin.parse_month(baldwin_month(2026, 11, 20), 2026, 10, date(2026, 10, 1), date(2026, 12, 30))


@unittest.skipIf(church is None, 'Deployment plugins absent')
class StPaulWindowTests(unittest.TestCase):
    def test_repeated_dates_arts_and_resource_exclusion(self):
        rows = church.parse_month(church_month(11, [(1, 'worship', 'worship'), (8, 'worship', 'worship'), (7, 'theatre', 'arts-cultural'), (5, 'pilates', 'community-resources')]), 2026, 11, date(2026, 10, 1), date(2026, 12, 30))
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['date'] for r in rows[:2]], ['2026-11-01', '2026-11-08'])
        self.assertTrue(any('theatre' in r['url'] for r in rows))

    def test_incomplete_grid_and_wrong_month_fail_closed(self):
        for html in (church_month(11, [(1, 'worship', 'worship')], mobile=False), church_month(12, []), '<html>403</html>'):
            with self.subTest(html=html[:40]), self.assertRaises(ValueError):
                church.parse_month(html, 2026, 11, date(2026, 10, 1), date(2026, 12, 30))

    def test_details_preserve_offsite_virtual_and_exact_schedule(self):
        detail = church.detail_text('<h1 class="tribe-events-single-event-title">Pajama Prayers</h1><div class="tribe-events-schedule">November3 8–9pm</div><div class="tribe-events-single-event-description">Online only. <a href="https://example.org/join">Join</a></div><div class="tribe-events-meta-group">Venue: Online</div>')
        self.assertIn('Online only', detail)
        self.assertIn('https://example.org/join', detail)
        self.assertIn('November3 8–9pm', detail)

    def test_configured_siblings_share_one_complete_fetch(self):
        profile = site_profiles.custom_fetch_profile(['https://stpaulandstandrew.org/calendar/', 'https://stpaulandstandrew.org/events/category/arts-cultural/list/'])
        self.assertIs(profile.fetcher, church.fetch_and_build_markdown)
        session = Session([Response(church_month(m, [(20, 'worship', 'worship')])) for m in (10, 11, 12)])
        detail = Response('<h1 class="tribe-events-single-event-title">Worship</h1><div class="tribe-events-schedule">11am–noon</div>')
        with patch.object(church, 'get_active_date_window', return_value=(date(2026, 10, 1), date(2026, 12, 30))), patch.object(church.requests, 'Session', return_value=session), patch.object(church.requests, 'get', return_value=detail):
            md, count = church.fetch_and_build_markdown(['https://stpaulandstandrew.org/calendar/', 'https://stpaulandstandrew.org/events/category/arts-cultural/list/'])
        self.assertEqual(count, 3)
        self.assertEqual(len(session.calls), 3)
        self.assertIn('2026-12-20', md)


if __name__ == '__main__':
    unittest.main()
