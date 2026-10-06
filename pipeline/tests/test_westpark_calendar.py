import sys,unittest
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from sources.westpark_calendar import build_months,months
except ImportError:build_months=None
@unittest.skipIf(build_months is None,'city-specific source plugin unavailable')
class WestParkCalendarTests(unittest.TestCase):
    def captures(self):
        def stamp(month,day,hour=0):return datetime(2026,month,day,hour,tzinfo=ZoneInfo('America/New_York')).timestamp()*1000
        event={'id':'one','title':'Offsite Show','startDate':stamp(11,7,19),'endDate':stamp(11,7,20),'fullUrl':'/calendar/show','body':'<p>Program</p>','location':{'addressTitle':'Dixon Place','addressLine1':'161A Chrystie Street'}}
        return [((2026,m),{'monthFilter':stamp(m,1),'calendarView':True,'items':[event]if m==11 else[]})for m in(10,11,12)]
    def test_complete_months_and_actual_venue(self):
        body,count=build_months(self.captures(),date(2026,10,1));self.assertEqual(count,1);self.assertIn('Dixon Place',body);self.assertIn('2026-11-07T19:00:00-05:00',body)
    def test_empty_month_is_valid(self):
        c=self.captures();c[1][1].pop('items');c[1][1]['empty']=True;self.assertEqual(build_months(c,date(2026,10,1))[1],0)
    def test_missing_or_wrong_month_fails(self):
        for c in(self.captures()[:2],list(reversed(self.captures()))):
            with self.assertRaises(ValueError):build_months(c,date(2026,10,1))
        c=self.captures();c[1][1]['monthFilter']=c[0][1]['monthFilter']
        with self.assertRaises(ValueError):build_months(c,date(2026,10,1))
    def test_year_boundary(self):self.assertEqual(list(months(date(2026,12,1),date(2027,2,1))),[(2026,12),(2027,1),(2027,2)])
if __name__=='__main__':unittest.main()
