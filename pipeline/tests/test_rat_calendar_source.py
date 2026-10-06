import unittest
from datetime import date
try:
    from sources.rat_calendar import checked_events,event_block
except ImportError:
    checked_events=event_block=None

@unittest.skipIf(checked_events is None,'Deployment source not installed')
class RatCalendarTests(unittest.TestCase):
    def test_complete_month_inventory_required(self):
        good={'events':[{'id':'one'}],'dates':{'calendar':{'referenceDate':'2026-11-01T04:00:00.000Z','events':{'day':['one']}}}}
        self.assertEqual(len(checked_events(good,2026,11)),1)
        with self.assertRaises(ValueError):checked_events(good,2026,12)
        good['events']=[]
        with self.assertRaises(ValueError):checked_events(good,2026,11)

    def test_own_slug_and_dst_overnight_unknown_end(self):
        e={'id':'one','title':'Own Show','slug':'own-show-2','scheduling':{'config':{'startDate':'2026-11-02T04:30:00Z','endDate':'2026-11-02T06:30:00Z','timeZoneId':'America/New_York'}}}
        block=event_block(e,date(2026,10,1),date(2026,12,30))
        self.assertIn('/event-details/own-show-2',block)
        self.assertIn('2026-11-01T23:30:00-05:00',block)
        self.assertIn('2026-11-02T01:30:00-05:00',block)
        e['scheduling']['config']['endDateHidden']=True
        self.assertNotIn('01:30',event_block(e,date(2026,10,1),date(2026,12,30)))
