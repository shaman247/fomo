"""Reviewed source boundaries: seasons, per-site elections and lineup identities."""
import sys
import unittest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from sources import astoria_masons, eastville, wilderstein
except ImportError:
    astoria_masons = eastville = wilderstein = None


@unittest.skipIf(astoria_masons is None, 'deployment source plugins unavailable')
class VotingSourceTests(unittest.TestCase):
    def event(self, day, venue='Advance Masonic Temple', month=10, hour=9):
        start = datetime(2026, month, day, hour, tzinfo=ZoneInfo('America/New_York'))
        return {'id': str(start), 'title': f'Early Voting {start:%b} {day}th',
                'startDate': start.timestamp()*1000, 'endDate': (start.timestamp()+3600)*1000,
                'location': {'addressTitle': venue, 'addressLine1': '21-14 30th Avenue',
                             'addressLine2': 'Queens, New York, 11102'},
                'fullUrl': '/events/'+str(day)}

    def test_month_boundary_and_each_days_own_clock(self):
        a=self.event(31); b=self.event(1,month=11,hour=14)
        text,count=astoria_masons.render({'upcoming':[b,a]})
        self.assertEqual(count,1)
        self.assertIn('2026-10-31 09:00AM',text)
        self.assertIn('2026-11-01 02:00PM',text)

    def test_distinct_sites_and_election_periods_stay_separate(self):
        rows=[self.event(1),self.event(1,venue='Other Temple'),self.event(24)]
        self.assertEqual(astoria_masons.render({'upcoming':rows})[1],3)

    def test_unrelated_program_remains_separate(self):
        a=self.event(24);b=self.event(25);b['title']='Blood Drive'
        self.assertEqual(astoria_masons.render({'upcoming':[a,b]})[1],2)


@unittest.skipIf(eastville is None, 'deployment source plugins unavailable')
class ShowSourceTests(unittest.TestCase):
    def card(self,name,day='2026-10-01',clock='8:00 PM',desc='Weekend Warmup comedy in Brooklyn! FEATURING SPECIAL GUEST COMEDIANS'):
        return dict(name=name,day=day,time=clock,description=desc,url='https://www.eastvillecomedy.com/events/'+name)

    def test_explicit_published_parent_uses_brand_keeps_lineup(self):
        rows=[self.card('A, B, C'),self.card('Stand Up Shenanigans',day='2026-10-08')]
        rows[0]['show_name']='Stand Up Shenanigans'
        text,count=eastville.render(rows)
        self.assertEqual(count,2)
        self.assertEqual(text.count('## [Stand Up Shenanigans]'),2)
        self.assertIn("This session's performer lineup: A, B, C",text)

    def test_reviewed_past_power_hour_details_cannot_expand_old_weekly_prose(self):
        for number in (4,5,6):
            self.assertTrue(eastville.historical_schedule_detail(
                f'https://www.eastvillecomedy.com/events/brooklyn-power-hour-{number}'))
        self.assertFalse(eastville.historical_schedule_detail(
            'https://www.eastvillecomedy.com/events/brooklyn-power-hour-17'))
        self.assertFalse(eastville.historical_schedule_detail(
            'https://example.org/events/brooklyn-power-hour-6'))

    def test_month_horizon_crosses_year_and_can_span_four_months(self):
        with patch.object(eastville,'FUTURE_WINDOW_DAYS',90):
            self.assertEqual(eastville.calendar_months(date(2026,10,1)),
                             [date(2026,10,1),date(2026,11,1),date(2026,12,1)])
            self.assertEqual(eastville.calendar_months(date(2026,11,30)),
                             [date(2026,11,1),date(2026,12,1),date(2027,1,1),date(2027,2,1)])

    def test_fetch_reads_parent_label_even_for_exceptional_clock(self):
        html='<h1>Upcoming Comedy Shows</h1><article class="show-card" data-show-date="2026-10-02"><div aria-label="Friday, October 2 at 8:00 PM"></div><h3><a href="/events/lineup">A, B, C</a></h3><p>Featuring A B C</p></article>'
        parent='<h1>A, B, C</h1><a aria-label="Event Show" href="/shows/friday-night">This event is part of: Friday Night Comedy</a>'
        class Today(date):
            @classmethod
            def today(cls):return cls(2026,10,1)
        with patch.object(eastville,'date',Today),patch.object(eastville,'FUTURE_WINDOW_DAYS',1),patch.object(eastville,'get_text',side_effect=[html,parent]) as fetch:
            text,count=eastville.fetch()
        self.assertEqual(count,1)
        self.assertIn('## [Friday Night Comedy]',text)
        self.assertIn('2026-10-02 at 8:00 PM',text)
        self.assertEqual(fetch.call_count,2)

    def test_explicit_parent_show_overrides_regular_clock(self):
        card=self.card('A, B, C',day='2026-10-02',clock='8:00 PM',desc='Featuring A B C')
        card['show_name']='Friday Night Comedy'
        self.assertIn('## [Friday Night Comedy]',eastville.render([card])[0])

    def test_no_brand_from_clock_or_ambiguous_program(self):
        rows=[self.card('A, B, C',desc='Featuring A B C'),self.card('Stand Up Shenanigans')]
        self.assertIn('## [A, B, C]',eastville.render(rows)[0])
        rows=[self.card('A, B, C'),self.card('Stand Up Shenanigans'),self.card('Saturday Prime Time Comedy')]
        self.assertIn('## [A, B, C]',eastville.render(rows)[0])

    def test_headliners_and_different_times_never_relabelled(self):
        rows=[self.card('Special comedy show: A, B, C'),self.card('Stand Up Shenanigans'),self.card('D, E, F',clock='9:00 PM')]
        text,_=eastville.render(rows)
        self.assertIn('## [Special comedy show: A, B, C]',text)
        self.assertIn('## [D, E, F]',text)


@unittest.skipIf(wilderstein is None, 'deployment source plugins unavailable')
class SeasonSourceTests(unittest.TestCase):
    def test_calendar_always_includes_current_official_dated_season(self):
        with patch.object(wilderstein,'get_text',side_effect=['<main><h2 class="entry-title">Calendar</h2><div class="entry-content"><h3 class="wp-block-heading">Mansion Tours</h3>Tour every Thursday. Special party October 7.</div></main>', '<main>2026 Tour Season: May 1 through October 31. Noon, 1pm, 2pm, 3pm.</main>']):
            body,_=wilderstein.fetch()
        self.assertIn('Special party October 7',body)
        self.assertIn('2026 Tour Season: May 1 through October 31',body)

    def test_blocked_calendar_cannot_hide_other_programs_behind_valid_tours(self):
        with patch.object(wilderstein,'get_text',side_effect=['<body>Access denied</body>','<main>2026 Tour Season: May 1 through October 31.</main>']):
            with self.assertRaises(ValueError):wilderstein.fetch()

    def test_missing_season_fails_instead_of_unbounded_recurrence(self):
        with patch.object(wilderstein,'get_text',side_effect=['<main><h2 class="entry-title">Calendar</h2><div class="entry-content"><h3 class="wp-block-heading">Mansion Tours</h3>Tour every Thursday</div></main>','<main>Visit us</main>']):
            with self.assertRaises(ValueError):wilderstein.fetch()

if __name__=='__main__':unittest.main()
