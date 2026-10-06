import sys,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from sources.embedded_google_calendars import expand_calendar,calendar_ids,build_markdown
except ImportError:expand_calendar=None
@unittest.skipIf(expand_calendar is None,'city-specific source plugin unavailable')
class EmbeddedGoogleCalendarTests(unittest.TestCase):
    def ics(self,*events):return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'+''.join('BEGIN:VEVENT\r\n'+e.replace('\n','\r\n')+'\r\nEND:VEVENT\r\n'for e in events)+'END:VCALENDAR\r\n'
    def test_explicit_recurrence_exdate_and_dst(self):
        rows=expand_calendar(self.ics('UID:a\nSUMMARY:Class\nDTSTART;TZID=America/New_York:20261025T100000\nDTEND;TZID=America/New_York:20261025T110000\nRRULE:FREQ=WEEKLY;COUNT=3\nEXDATE;TZID=America/New_York:20261101T100000'),date(2026,10,1))
        self.assertEqual(len(rows),2);self.assertTrue(rows[0]['start'].endswith('-04:00'));self.assertTrue(rows[1]['start'].endswith('-05:00'));self.assertIn('T10:00:00',rows[1]['start'])
    def test_changed_and_cancelled_instances_replace_master(self):
        master='UID:a\nSUMMARY:Class\nDTSTART;TZID=America/New_York:20261004T100000\nDTEND;TZID=America/New_York:20261004T110000\nRRULE:FREQ=WEEKLY;COUNT=3'
        changed='UID:a\nSUMMARY:Class\nRECURRENCE-ID;TZID=America/New_York:20261011T100000\nDTSTART;TZID=America/New_York:20261011T130000\nDTEND;TZID=America/New_York:20261011T140000'
        cancelled='UID:a\nSUMMARY:Class\nRECURRENCE-ID;TZID=America/New_York:20261018T100000\nDTSTART;TZID=America/New_York:20261018T100000\nSTATUS:CANCELLED'
        rows=expand_calendar(self.ics(master,changed,cancelled),date(2026,10,1));self.assertEqual(len(rows),2);self.assertTrue(any('T13:00:00'in r['start']for r in rows));self.assertFalse(any('2026-10-18'in r['start']for r in rows))
    def test_all_day_exclusive_end_and_date_until(self):
        rows=expand_calendar(self.ics('UID:a\nSUMMARY:Festival\nDTSTART;VALUE=DATE:20261002\nDTEND;VALUE=DATE:20261004\nRRULE:FREQ=WEEKLY;UNTIL=20261009'),date(2026,10,1));self.assertEqual(len(rows),2);self.assertTrue(rows[0]['end_is_exclusive']);self.assertTrue(rows[0]['all_day'])
    def test_duplicate_and_range_override_fail(self):
        e='UID:a\nSUMMARY:Class\nDTSTART:20261001T100000Z'
        for data in(self.ics(e,e),self.ics(e+'\nRECURRENCE-ID;RANGE=THISANDFUTURE:20261001T100000Z')):
            with self.assertRaises(ValueError):expand_calendar(data,date(2026,10,1))
    def test_embed_ids_and_malformed_feed(self):
        self.assertEqual(calendar_ids('<iframe src="https://calendar.google.com/calendar/embed?src=one%40example.com&amp;src=two%40example.com"></iframe>'),['one@example.com','two@example.com'])
        with self.assertRaises(ValueError):calendar_ids('<p>No calendar</p>')
        with self.assertRaises(ValueError):expand_calendar('<html>failed</html>',date(2026,10,1))
    def test_grouping_preserves_uid_and_dates(self):
        rows=expand_calendar(self.ics('UID:a\nSUMMARY:Class\nDTSTART:20261001T100000Z\nRRULE:FREQ=DAILY;COUNT=2'),date(2026,10,1));body,count=build_markdown('School','https://example.com',[('one@example.com',rows)]);self.assertEqual(count,2);self.assertEqual(body.count('### Class'),1);self.assertEqual(body.count('**Published occurrence**'),2)
    def test_utc_stamped_feed_renders_local_wall_time(self):
        rows=expand_calendar(self.ics('UID:a\nSUMMARY:Show\nDTSTART:20261120T230000Z\nDTEND:20261121T000000Z'),date(2026,10,1))
        self.assertEqual(rows[0]['start'],'2026-11-20T18:00:00-05:00');self.assertEqual(rows[0]['end'],'2026-11-20T19:00:00-05:00')
    def test_site_profiles_scope_each_listing_page(self):
        from sources.embedded_google_calendars import PROFILES
        def hit(url):return [p.name for p in PROFILES if p.matches(url)]
        self.assertEqual(hit('http://www.hartbarnyc.com/shows'),['embedded_google_hartbarnyc'])
        self.assertEqual(hit('https://www.cb9m.org/cal_events'),['embedded_google_cb9m'])
        self.assertEqual(hit('https://www.nyjaincenter.org/Calendar'),['embedded_google_nyjaincenter'])
        self.assertEqual(hit('https://mkad.art/events/'),['embedded_google_mkad'])
        self.assertEqual(hit('https://villagecommunityboathouse.org/calendar'),['embedded_google_villagecommunityboathouse'])
        for other in('https://www.hartbarnyc.com/drinks','https://www.cb9m.org/announcements','https://example.com/cal_events'):
            self.assertEqual(hit(other),[])
if __name__=='__main__':unittest.main()
