"""Junk filter: bare childcare-amenity titles and book-donation drop-off windows
(BL26 tail, 2026-10-16).

Positive rows are real crawl_events titles/descriptions from the 2026-10-16
measurement over all crawl history (see the regex blocks above
`_is_childcare_amenity` / `_is_book_donation_window` in processor.py). The
kept rows are the program shapes each gate must leave alone.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor


def rule(name, description=None):
    return processor.which_junk_rule(name, description)


class ChildcareAmenityTests(unittest.TestCase):

    def test_bare_titles_with_no_body_are_dropped(self):
        # w3278 "Child Care" x20, w2770 "Nursery", w1668 "Childcare", w1419
        # "Nursery Care" -- all with the merged placeholder body.
        for name in ('Child Care', 'Nursery', 'Childcare', 'Nursery Care',
                     'Nursery - Childcare'):
            with self.subTest(name=name):
                self.assertEqual(rule(name, 'No description available.'), 'childcare_amenity')
                self.assertEqual(rule(name, None), 'childcare_amenity')
        # w2770 placeholder body.
        self.assertEqual(rule('Nursery', 'Stay tuned for more information.'),
                         'childcare_amenity')

    def test_bare_titles_without_during_framing_are_dropped(self):
        for name, desc in (
            ('Nursery Care', 'Nursery care services provided for families during morning hours.'),
            ('Nursery Care', 'Nursery care for children up to age 4, professionally staffed '
                             'and located in the Sunday School wing.'),
            ('Nursery Care', 'Nursery care is available for children.'),
            ('Nursery-Preschool Care', 'For this service, nursery care for children ages 6 '
                                       'months to 5 years will be in the front of the Sanctuary.'),
            ('Childcare', 'Childcare is offered as part of the festival’s family events and is '
                          'listed for August 23 and September 6, 2026.'),
        ):
            with self.subTest(desc=desc):
                self.assertEqual(rule(name, desc), 'childcare_amenity')

    def test_during_performances_and_events(self):
        # Hudson Valley Shakespeare (w1668): the extended during-wording.
        self.assertEqual(rule(
            'Childcare', 'Childcare is offered during selected Hudson Valley Shakespeare '
                         'Festival events.'), 'childcare_amenity')
        self.assertEqual(rule(
            'Childcare', 'Childcare is offered during designated Hudson Valley Shakespeare '
                         'Festival programming.'), 'childcare_amenity')
        # Babysitting is outside the bare-title arm; the during arm still takes it.
        self.assertEqual(rule(
            'Babysitting', 'Free babysitting for ages 3-7 during Sunday matinee performances.'),
            'childcare_amenity')

    def test_courses_and_programs_are_kept(self):
        # A bare childcare title over a course/training body survives.
        self.assertIsNone(rule(
            'Child Care', 'A six-week course for prospective family child care providers '
                          'covering health and safety training and state licensing.'))
        self.assertIsNone(rule(
            'Childcare', 'Information session on the city child care subsidy and how to apply.'))
        # A bare "Babysitting" over a course body is the Red Cross class.
        self.assertIsNone(rule(
            'Babysitting', 'Teens learn basic child care, safety and first aid skills.'))
        # Any non-amenity word in the title still vetoes the rule.
        for name in ('Babysitting 101 Training Course', 'Childcare CPR Training',
                     'The Nursery: HAAi All Day Long', 'Toddler Storytime',
                     'Plant Nursery Tour', 'Learn to Babysit'):
            with self.subTest(name=name):
                self.assertIsNone(rule(name, None))
                self.assertIsNone(rule(name, 'Nursery care during worship services.'))


class BookDonationWindowTests(unittest.TestCase):

    def test_donation_titles_drop_on_the_title(self):
        for name, desc in (
            ('Book Donation Day', 'Support the library by bringing your gently used books to '
                                  'the Friends Book Shop.'),
            ('Book Donation Day: Friends of the Township of Ocean Library', None),
            ('The Friends of the Plumsted Library Book Donation/Drop-Off',
             'Drop off gently used, mold-free books, CDs, DVDs, puzzles, audiobooks on CD, '
             'and video games at the trailer behind Plumsted Library.'),
            # w3530: the body is the sale's own blurb; the dates (Sep 16-23) are
            # the intake window before the Sep 24-28 sale.
            ('Friends Book Sale Donations',
             'Sale Dates: September 24-28 Shoppers will find a large selection of books and '
             'media for all ages and genres.'),
        ):
            with self.subTest(name=name):
                self.assertEqual(rule(name, desc), 'book_donation_window')

    def test_collection_titles_need_the_body(self):
        self.assertEqual(rule(
            'Book Sale Collection',
            "The Friends of the Library collect like-new children's, teen and adult books for "
            "their upcoming sale on the Parmalee side of the library."), 'book_donation_window')
        self.assertEqual(rule(
            'Book Drop',
            'Help us spread the joy of reading by donating new or gently used books to be '
            'distributed to youth at the Youth Pride event.'), 'book_donation_window')
        self.assertIsNone(rule('Book Sale Collection', None))
        self.assertIsNone(rule('Book Drop', 'Pick up a free book!'))

    def test_book_donations_accepted_still_reported_by_name_rule(self):
        self.assertEqual(rule(
            'Book Donations Accepted',
            'The Friends of the Library accept donations of gently used books each month.'),
            'non_event_name')

    def test_programs_are_kept(self):
        for name, desc in (
            ('Celebration of the TECO-NY Book Donation to Queens College Library', None),
            ('Reading Rhythms "Books-giving" Book Swap and Donation Drive in Midtown: '
             'November 17th', 'Bring a gently used book to swap.'),
            ('Book Talk | Collecting Contemporaries: The Fuhrman Collection', None),
            ('Henry Wessel: Photographs and Books. From the Collection of Jack Gray',
             'A spotlight exhibition on photographs and books by Henry Wessel (1942–2018), '
             'curated by Grolier Club'),
            ("Books a Poppin' (Drop-in)", 'Drop in for stories and crafts.'),
            ('Book Drop-In Hours', None),
            ('Book Club (donations welcome)', None),
            ('Used Book Sale', 'Thousands of gently used books for sale, donated by patrons.'),
        ):
            with self.subTest(name=name):
                self.assertIsNone(rule(name, desc))


if __name__ == '__main__':
    unittest.main()
