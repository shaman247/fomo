import copy
import sys
import unittest
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from sources import snug_harbor as source
except ImportError:
    source = None

@unittest.skipIf(source is None, 'deployment-specific source plugin not installed')
class SnugSlotsTests(unittest.TestCase):
    def test_explicit_departures_override_envelope_and_keep_halloween_exception(self):
        rows=[self.slot(1,'2026-10-02',name='Spooky Snug Harbor Tour',start='19:30:00',end='22:30:00'),
              self.slot(2,'2026-10-31',name='Spooky Snug Harbor Tour',start='21:00:00',end='22:30:00')]
        for row in rows:
            row.update(post_id=4511,post_permalink=f"https://snug-harbor.org/event/spooky-snug-harbor-tour/?slot_id={row['id']}")
        detail={'id':4511,'content':{'rendered':'<p>When: The first session runs from 7:30 PM to 9:00 PM. '
                'The second session runs from 9:00 PM to 10:30 PM. Friday, October 2, 2026 '
                'Saturday, October 31, 2026 – Halloween Special 9:00-10:30 PM Where: Visitor booth</p>'}}
        payload=dict(success=True,data=rows)
        expanded=source.with_explicit_departures(payload,{4511:detail})
        text,count=source.render_slots(expanded,date(2026,10,1),date(2026,12,30))
        self.assertEqual(count,3)
        self.assertEqual(expanded['data'][0]['_session_clocks'],[['19:30:00','21:00:00'],['21:00:00','22:30:00']])
        self.assertEqual(expanded['data'][1]['_session_clocks'],[['21:00:00','22:30:00']])
        self.assertNotIn('_session_clocks',payload['data'][0])
        with self.assertRaises(ValueError):source.with_explicit_departures(payload,{})
        altered=copy.deepcopy(payload);altered['data'][0]['date']='2026-10-09'
        with self.assertRaises(ValueError):source.with_explicit_departures(altered,{4511:detail})
        detail['content']['rendered']=detail['content']['rendered'].replace('The second session','Another session')
        with self.assertRaises(ValueError):source.with_explicit_departures(payload,{4511:detail})

    def slot(self,sid,day,name='Course5 | Virtual Session',start='19:00:00',end='21:00:00'):
        return dict(id=sid,post_id=4591,name=name,date=day,time_start=start,time_end=end,
                    status='Active',post_permalink=f'https://snug-harbor.org/class/course5/?slot_id={sid}',details={})
    def render(self,slots):return source.render_slots(dict(success=True,data=slots),date(2026,10,1),date(2026,12,30))
    def test_shared_post_does_not_transfer_delivery_or_clock(self):
        rows=[self.slot(22991,'2026-10-24','Course5 | in-person','10:00:00','12:00:00'),self.slot(22992,'2026-11-16'),self.slot(22993,'2026-12-28')]
        text,count=self.render(rows);self.assertEqual(count,3)
        blocks=text.split('\n\n');self.assertIn('10:00:00',blocks[0]);self.assertNotIn('19:00:00',blocks[0]);self.assertIn('Venue: Online',blocks[2]);self.assertIn('2026-12-28',blocks[2]);self.assertIn('slot_id=22993',blocks[2])
    def test_explicit_online_cooking_is_remote_but_virtual_subject_is_not(self):
        text,_=self.render([self.slot(1,'2026-10-01','Sylvia Center: Online Cooking Demonstration')])
        self.assertIn('Venue: Online',text)
        text,_=self.render([self.slot(2,'2026-10-01','Virtual Reality Workshop')])
        self.assertIn('Venue: Snug Harbor Cultural Center',text)

    def test_many_sparse_dates_never_become_a_continuous_run(self):
        start=date(2026,10,1);rows=[self.slot(i+1,str(start+timedelta(days=7*i))) for i in range(12)]
        text,count=self.render(rows);self.assertEqual(count,12);self.assertEqual(text.count('Date:'),12);self.assertNotIn('On view daily',text)
    def test_unknown_end_stays_unknown_and_duplicates_require_consistency(self):
        s=self.slot(1,'2026-10-01',end='');text,count=self.render([s,s]);self.assertEqual(count,1);self.assertNotIn('End time:',text)
        altered=dict(s,time_start='20:00:00')
        with self.assertRaises(ValueError):self.render([s,altered])
    def test_malformed_or_truncated_source_fails_closed(self):
        s=self.slot(1,'2026-10-01');s['post_permalink']='https://snug-harbor.org/class/course5/'
        with self.assertRaises(ValueError):self.render([s])
        with self.assertRaises(ValueError):self.render([self.slot(1,'2026-10-01')]*1000)
        with self.assertRaises(ValueError):source.render_slots({},date(2026,10,1),date(2026,12,30))
    def test_source_scope_and_past_or_cancelled_slots(self):
        self.assertTrue(source.PROFILE.matches(source.BASE+'/events-calendar/'))
        self.assertFalse(source.PROFILE.matches(source.BASE+'/class/course5/'))
        a=self.slot(1,'2026-09-30');b=self.slot(2,'2026-10-01');b['status']='Cancelled'
        self.assertEqual(self.render([a,b]),('',0))

if __name__=='__main__':unittest.main()
