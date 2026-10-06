"""Source grouping must preserve evidence needed by canonical format matching."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import processor

class ProgramGroupingTests(unittest.TestCase):
    def rows(self, companion='Talk'):
        base=dict(name='Taking a Broad View',location='Museum',location_id=1,
                  url='https://example.org/program',description='Program details')
        return [dict(base,tags=['Exhibition'],start_date='2026-10-01',start_time='',end_date='2026-12-01',end_time=''),
                dict(base,tags=[companion],start_date='2026-10-01',start_time='2pm',end_date='',end_time='3pm')]
    def test_old_exact_name_same_url_grouping_loses_distinction(self):
        with patch.object(processor,'conflicting_program_profiles',return_value=False):
            self.assertEqual(len(processor.group_event_occurrences(self.rows())),1)
        self.assertEqual(len(processor.group_event_occurrences(self.rows())),2)
    def test_both_orders_and_multiple_companion_dates(self):
        for kind in ('Talk','Tour'):
            rows=self.rows(kind)
            for items in (rows,rows[::-1]):
                result=processor.group_event_occurrences(copy.deepcopy(items+[dict(rows[1],start_date='2026-10-02')]))
                self.assertEqual(len(result),2)
                by_format={r['tags'][0]:r for r in result}
                self.assertEqual(len(by_format['Exhibition']['occurrences']),1)
                self.assertEqual(len(by_format[kind]['occurrences']),2)
    def test_containment_titles_cannot_bypass_format_guard(self):
        rows=self.rows('Tour');rows[1]['name']+=' Gallery Tour'
        self.assertEqual(len(processor.group_event_occurrences(rows)),2)
    def test_missing_mixed_and_same_formats_preserve_existing_grouping(self):
        for formats in ([],['Exhibition','Talk'],['Exhibition']):
            rows=self.rows();rows[1]['tags']=formats
            self.assertEqual(len(processor.group_event_occurrences(rows)),1)
        rows=self.rows();rows[1]['start_time']='';rows[1]['end_time']=''
        self.assertEqual(len(processor.group_event_occurrences(rows)),1)


class CompanionGroupingTests(unittest.TestCase):
    def test_discrete_run_is_protected_before_all_its_rows_have_grouped(self):
        rows=[dict(name='The Unintended Blues',location='Gallery',location_id=1,
                   tags=['Exhibition'],url='https://example.org/program',
                   start_date=day,start_time='12pm',end_date='',end_time='5pm')
              for day in ('2026-09-18','2026-09-19','2026-09-26')]
        closing=dict(rows[0],name='The Unintended Blues: Closing Weekend',
                     start_date='2026-09-26')
        for ordered in ([closing,*rows],[*rows,closing]):
            result=processor.group_event_occurrences(copy.deepcopy(ordered))
            self.assertEqual(len(result),2)
            self.assertEqual(sorted(len(r['occurrences']) for r in result),[1,3])

    def test_named_curator_coffee_keeps_identity_even_with_exhibition_tag(self):
        rows=[dict(name='Dis-dressed',location='Museum',location_id=1,
                   tags=['Exhibition'],url='https://example.org/dis-dressed',
                   start_date='2026-10-03',start_time='',end_date='2026-12-06',end_time=''),
              dict(name='Dis-dressed: Coffee with a Curator',location='Museum',location_id=1,
                   tags=['Exhibition'],url='https://example.org/dis-dressed',
                   start_date='2026-11-07',start_time='12pm',end_date='',end_time='')]
        for ordered in (rows, rows[::-1]):
            result=processor.group_event_occurrences(copy.deepcopy(ordered))
            self.assertEqual(len(result),2)
            self.assertTrue(all(len(e['occurrences'])==1 for e in result))


if __name__ == '__main__':
    unittest.main()
