"""Numbered comedy courses, student performances and teachers have identities."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import merger
import processor
from event_name_guards import class_show_identity_mismatch

COURSE = "Clown Level 1: Welcome to Clown Town w/ Hannah Mitchell (Oct-Dec '26) (Monday)"
SHOW = 'Clown Level 1 Class Show (Hannah Mitchell, Monday)'
MOLLY = 'Class Show: Molly Ledbetter Improv Level 1 (Wednesday Class)'
KENNY = "Kenny Park Yi's Improv Level 1 Class Show"

class ClassShowIdentityTests(unittest.TestCase):
    def test_real_failures_before_guard(self):
        with patch.object(merger,'class_show_identity_mismatch',return_value=False):
            self.assertTrue(merger.are_names_similar(COURSE,SHOW))
            self.assertTrue(merger.are_names_similar(MOLLY,KENNY))

    def test_courses_and_performances_remain_separate_in_both_orders(self):
        pairs=[(COURSE,SHOW),
            ("Sketch: Level 2 w/ Alise Morales (Oct-Dec '26) (Wednesday)",
             "Alise Morales' Sketch Level 2 Class Show (1/2)"),
            ("[Oct-Dec] Sketch: Level 2 w/ Alise Morales (Thursdays)",
             "Nick Mestad's Sketch Level 2 Class Show (1/2)"),
            ('Musical Improv Level 2: Technique with Philip Markle',
             'Musical Improv Level 2 Class Show (Philip Markle)')]
        for a,b in pairs:
            for left,right in ((a,b),(b,a)):
                with self.subTest(left=left,right=right):
                    self.assertFalse(merger.are_names_similar(left,right))

    def test_different_explicit_teachers_do_not_merge(self):
        for a,b in [(MOLLY,KENNY),
            ("Molly Ledbetter Improv Level 1 Class Show (Monday Section)",
             "Onyi Okoli's Improv Level 1 Class Show (Monday Section)"),
            ('Improv Level 3 Class Show w/ Tej Khanna',
             'Improv Level 3 Class Show (John Randall)')]:
            self.assertTrue(class_show_identity_mismatch(a,b))
            self.assertTrue(class_show_identity_mismatch(b,a))
            self.assertFalse(merger.are_names_similar(a,b))

    def test_same_teacher_aliases_and_missing_evidence_are_preserved(self):
        pairs=[(MOLLY,'Molly Ledbetter Improv Level 1 Class Show (Wednesday Section)'),
            ('Improv Level 3 Class Show w/ Tej Khanna',"Tej Khanna's Improv Level 3 Class Show"),
            (SHOW,"Hannah Mitchell's Clown Level 1 Class Show"),
            ('Improv Level 1 Class Show','Improv Level 1 Class Show (Wednesday Class)'),
            ('Master Class with Jane Smith','Master Class Show'),
            ('Improv Level 1 with Jane Smith','Improv Level 1 with John Brown')]
        for a,b in pairs:
            with self.subTest(a=a,b=b):
                self.assertFalse(class_show_identity_mismatch(a,b))
                self.assertFalse(class_show_identity_mismatch(b,a))
        self.assertTrue(merger.are_names_similar(*pairs[0]))
        self.assertTrue(merger.are_names_similar(*pairs[1]))

    def test_unnumbered_course_requires_complete_title_and_teacher(self):
        course = "Gimme That Queer Sh!t w/ Lou Gonzalez Jr. (Oct-Dec '26) (Sunday)"
        show = "Lou Gonzalez Jr.'s Gimme That Queer Sh!t Class Show"
        for left, right in ((course, show), (show, course)):
            self.assertTrue(class_show_identity_mismatch(left, right))
            self.assertFalse(merger.are_names_similar(left, right))
        for other in ("Gimme That Queer Sh!t Class Show",
                      "Lou Gonzalez Jr.'s Another Queer Program Class Show",
                      "Jane Smith's Gimme That Queer Sh!t Class Show"):
            self.assertFalse(class_show_identity_mismatch(course, other))
        self.assertFalse(class_show_identity_mismatch(
            "Workshop with Jane Smith", "Jane Smith's Workshop Class Show"))

    def test_source_grouping_keeps_shared_url_course_and_show_apart(self):
        # Containment can fuse the two before they ever reach canonical merging.
        names=['Improv Level 1 with Jane Smith',
               'Improv Level 1 with Jane Smith Class Show']
        rows=[dict(name=n,location='Theater',location_id=1,url='https://example.org/course',
                   start_date='2026-11-01',start_time='7pm',end_date='',end_time='') for n in names]
        for ordered in (rows,rows[::-1]):
            grouped=processor.group_event_occurrences(ordered,'https://example.org/course')
            self.assertEqual(len(grouped),2)
        self.assertEqual(len(processor.group_event_occurrences([rows[0],dict(rows[0],start_date='2026-11-08')])),1)

if __name__=='__main__':unittest.main()
