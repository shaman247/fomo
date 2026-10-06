import sys,unittest,json
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
 from sources import tastebuds_calendar as taste,union_pool_calendar as union
except ImportError:taste=union=None
@unittest.skipIf(taste is None,'city-specific source plugins unavailable')
class FinalLoadMoreTests(unittest.TestCase):
 def test_public_ids_follow_class_links_not_private_catalog(self):
  html='<a href="https://fareharbor.com/embeds/book/tastebudskitchen-nyc/?selected-items=1%2C2">Book Now</a><a href="https://fareharbor.com/embeds/book/tastebudskitchen-nyc/items/3/">Private Event</a>'
  self.assertEqual(taste.public_item_ids([html]),{1,2})
 def taste_payload(self,item=1):
  row=dict(pk=10,item={'uri':f'/api/v1/companies/tastebudskitchen-nyc/items/{item}/'},utc_start_at='2026-11-02T23:00:00+0000',utc_end_at='2026-11-03T01:00:00+0000',start_at='2026-11-02T18:00:00',end_at='2026-11-02T20:00:00',headline='Handmade Pasta • Ages 18+',book_url='/tastebudskitchen-nyc/items/1/availability/10/book/',status='closed')
  return [{'calendar':{'year':2026,'month':m,'weeks':[{'days':[{'month':'current','availabilities':[row]if m==11 else []}]}]}}for m in [10,11,12]]
 def test_complete_months_keep_closed_booking_and_discard_private_product(self):
  catalog={'items':[{'pk':1,'name':'Adult Cooking Class'},{'pk':2,'name':'Private Event'}]}
  body,count=taste.build_markdown(catalog,self.taste_payload(),{1},date(2026,10,1));self.assertEqual(count,1);self.assertIn('2026-11-02T18:00:00-05:00',body)
  _,count=taste.build_markdown(catalog,self.taste_payload(2),{1},date(2026,10,1));self.assertEqual(count,0)
 def test_missing_month_and_changed_public_product_fail(self):
  catalog={'items':[{'pk':1,'name':'Adult Cooking Class'}]}
  with self.assertRaises(ValueError):taste.build_markdown(catalog,self.taste_payload()[:-1],{1},date(2026,10,1))
  catalog['items'][0]['name']='Private Event'
  with self.assertRaises(ValueError):taste.build_markdown(catalog,self.taste_payload(),{1},date(2026,10,1))
 def event(self,identity='one'):
  return dict(id=identity,name='Concert',venue='Union Pool',url='https://dice.fm/event/'+identity,date='2026-11-03T00:00:00Z',date_end='2026-11-03T04:00:00Z',timezone='America/New_York',flags=['going_ahead'],status='off-sale',sold_out=True)
 def test_dice_two_pages_keep_full_schedule_and_soldout(self):
  pages=[{'data':[self.event()],'links':{'next':'next'}},{'data':[self.event('two')],'links':{}}]
  body,count=union.build_markdown(pages,date(2026,10,1));self.assertEqual(count,2);self.assertIn('2026-11-02T19:00:00-05:00',body)
 def test_dice_partial_and_duplicate_fail(self):
  with self.assertRaises(ValueError):union.build_markdown([{'data':[self.event()],'links':{'next':'next'}}],date(2026,10,1))
  with self.assertRaises(ValueError):union.build_markdown([{'data':[self.event(),self.event()],'links':{}}],date(2026,10,1))
 def test_production_chunking_preserves_each_dated_card(self):
  from extractor import chunk_content,cap_records_per_chunk,prune_chunks
  pages=[{'data':[dict(self.event(str(i)),description='Concert program. '*200)for i in range(45)],'links':{}}]
  body,count=union.build_markdown(pages,date(2026,10,1));chunks,_=chunk_content(body);kept,pruned=prune_chunks(cap_records_per_chunk(chunks,8),today=date(2026,10,1));self.assertFalse(pruned);self.assertEqual(sum(c.count('### [')for c in kept),count)
if __name__=='__main__':unittest.main()
