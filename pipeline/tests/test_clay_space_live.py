import asyncio,copy,unittest
try:
    from sources import clay_space_live as source
except ImportError:
    source=None

def fixture():
    slot={'product_detail_date':'September 14–December 14, 2026','title_text':'Monday','primary_text':['6:30pm–9:30pm']}
    row={'id':123,'pdp_url':'/clay-space-llc/schedules/activity-set/123','activity':{'name':'Center & Throw'},'class_times':[slot],'cta_button_info':{'text':'Join Waitlist'}}
    props={'staticData':{'id':123,'provider':{'slug':'clay-space-llc'},'activity':{'name':'Center & Throw','class_times':[slot],'holidays':['2026-11-23'],'must_book_all_days':True},'location':{'name':'Clay Space','address':'275 Calyer Street'}}}
    return row,props

@unittest.skipIf(source is None,'Deployment source not installed')
class ClayLiveTests(unittest.TestCase):
    def test_scope_and_live_embed_binding(self):
        self.assertTrue(source.PROFILE.matches(source.OFFICIAL))
        self.assertFalse(source.PROFILE.matches(source.OFFICIAL+'-archive'))
        self.assertFalse(source.PROFILE.matches('https://www.clayspacebk.com/workshops-register'))
        valid='<script src="https://hisawyer.com/embed/8zX89k86gCB49asUv1OXS8emf-lf7p-f.js"></script>'
        self.assertIn('widget_tags=falladult',source.live_listing_url(lambda u:valid))
        with self.assertRaises(ValueError):source.live_listing_url(lambda u:valid.replace('8zX89','new'))
    def test_identity_holidays_and_waitlist_are_owned(self):
        row,props=fixture();md,n=source.build_markdown([row],{123:props})
        self.assertEqual(n,1);self.assertIn('Join Waitlist',md);self.assertIn('2026-11-23',md);self.assertIn('must_book_all_days: true',md)
        for change in ({'id':456},{'provider':{'slug':'other'}}):
            p=copy.deepcopy(props);p['staticData'].update(change)
            with self.assertRaises(ValueError):source.build_section(row,p)
        props['staticData']['activity']['holidays']=None
        with self.assertRaises(ValueError):source.build_section(row,props)
    def test_incomplete_inventory_fails_closed(self):
        row,_=fixture();page={'data':{'pagination':{'page':1,'per_page':10,'total_count':1,'total_pages':1},'results':[row]}}
        self.assertEqual(len(source.validate_inventory([page])),1)
        page['data']['pagination']['total_count']=2
        with self.assertRaises(ValueError):source.validate_inventory([page])
        with self.assertRaises(ValueError):source.build_markdown([row],{})

    def test_transient_failure_retries_complete_capture_only_once(self):
        calls=[]
        async def capture():
            calls.append(1)
            if len(calls)==1:
                raise ValueError('inventory HTTP503')
            return ('all sections and details',16)
        self.assertEqual(asyncio.run(source.complete_capture_with_retry(capture)),('all sections and details',16))
        self.assertEqual(len(calls),2)
        calls.clear()
        async def incomplete():
            calls.append(1)
            raise ValueError('missing own holiday evidence')
        with self.assertRaisesRegex(ValueError,'failed twice'):
            asyncio.run(source.complete_capture_with_retry(incomplete))
        self.assertEqual(len(calls),2)
