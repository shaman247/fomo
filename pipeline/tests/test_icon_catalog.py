import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icon_catalog import resolve_icon,unknown_emoji,record_unknown,FALLBACK_ID
class IconCatalogTests(unittest.TestCase):
    def test_exact_aliases_keep_sequences_flags_and_skin_tones(self):
        self.assertEqual(resolve_icon('🖨️'),resolve_icon('🖨'))
        self.assertEqual(resolve_icon('🇺🇸'),'noto-1f1fa-1f1f8')
        self.assertEqual(resolve_icon('👩🏽‍💻'),'noto-1f469-1f3fd-200d-1f4bb')
        self.assertNotEqual(resolve_icon('🇺🇸'),resolve_icon('🇮🇹'))
    def test_saved_choices_take_precedence_without_name_inference(self):
        self.assertEqual(resolve_icon('🎲','game-go'),'game-go')
        self.assertEqual(resolve_icon('🎲','missing'),'noto-1f3b2')
        self.assertEqual(resolve_icon('new-emoji'),FALLBACK_ID)
    def test_known_and_empty_values_do_not_write(self):
        cursor=Mock()
        for emoji in ('🎨','🇺🇸',None,''):
            self.assertFalse(record_unknown(cursor,emoji,'crawl_events',123))
        cursor.execute.assert_not_called()
    def test_unknown_is_queued_with_context_and_never_auto_approved(self):
        cursor=Mock()
        self.assertTrue(record_unknown(cursor,'unknown-value','crawl_events',123,'Test event'))
        sql,params=cursor.execute.call_args.args
        self.assertIn('ON DUPLICATE KEY UPDATE',sql)
        self.assertNotIn('status=',sql)
        self.assertEqual(params[1:],('unknown-value','crawl_events',123,'Test event'))
        self.assertTrue(unknown_emoji('unknown-value'))
if __name__=='__main__':unittest.main()
