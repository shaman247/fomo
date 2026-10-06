"""Regression tests for extractor.dedupe_repeated_paragraphs (2026-10-05).

On 2026-10-04 the pre-chunking dedupe dropped Resident Advisor's untitled
Venue/Date/Start/Min Age/Tickets blocks for every party after the first at the
same venue on the same night, because the blocks were byte-identical. Six
events were extracted undated. A repeated block is now kept when it carries a
date and sits directly under a record title it has not appeared under before;
repeated chrome is still removed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import extractor  # noqa: E402

FIELDS = ('**Venue**: San Antonios — 247 Eldridge St, New York, NY 10002, US\n'
          '**Date**: October 9, 2026\n'
          '**Start**: 5pm — **End**: 3am\n'
          '**Min Age**: 21+\n'
          '**Tickets**: https://www.iboatnyc.com/')

FOOTER = ('Sign up for our newsletter to hear about upcoming shows, member presales '
          'and special offers. We never share your email address with anyone. '
          '(c) 2026 Example Venue, all rights reserved.')


def record(title, url, body=FIELDS):
    return f'### [{title}]({url})\n\n{body}\n\n[View Event Details]({url})'


class DistinctRecordsKeepTheirFieldBlocks(unittest.TestCase):

    def test_identical_field_blocks_under_different_titles_are_all_kept(self):
        text = '\n\n---\n\n'.join([
            record('Medellin Fridays', 'https://ra.co/events/1'),
            record('Y2K Party', 'https://ra.co/events/2'),
            record('Reggaeton Night', 'https://ra.co/events/3'),
        ])
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual((out, removed), (text, 0))
        self.assertEqual(out.count('**Date**: October 9, 2026'), 3)

    def test_blocks_reached_across_a_short_image_line_are_kept(self):
        image = '![flyer](https://img.example.org/x.jpg)'
        text = (f'## Party A\n\n{image}\n\n{FIELDS}\n\n'
                f'## Party B\n\n{image}\n\n{FIELDS}')
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(removed, 0)
        self.assertEqual(out.count('**Date**'), 2)

    def test_bold_title_lines_count_as_record_titles(self):
        text = f'**Party A**\n\n{FIELDS}\n\n**Party B**\n\n{FIELDS}'
        self.assertEqual(extractor.dedupe_repeated_paragraphs(text), (text, 0))

    def test_same_record_listed_twice_is_still_collapsed(self):
        # Identical title AND identical block: the same event rendered twice.
        one = record('Deep Listening', 'https://ra.co/events/9')
        text = one + '\n\n---\n\n' + one
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(out.count('**Date**'), 1)
        self.assertEqual(removed, len(FIELDS))


class RepeatedChromeIsStillRemoved(unittest.TestCase):

    def test_repeated_footer_is_dropped_even_under_different_headings(self):
        text = (f'## Show A\nOct 3 8pm\n\n{FOOTER}\n\n'
                f'## Show B\nOct 4 8pm\n\n{FOOTER}')
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(out.count('Sign up for our newsletter'), 1)
        self.assertEqual(removed, len(FOOTER))

    def test_dated_nav_menu_on_concatenated_pages_is_dropped(self):
        # Intrepid (w220): a nav menu listing dated items repeats on each page of
        # a paginated crawl; the page break's "skip" link line is not a title and
        # a long title-less paragraph separates it from the last heading.
        nav = ('Menu\nMain navigation\n  * [Fleet Week, May 20](https://x.org/fw)\n'
               '  * [Visit](https://x.org/visit)\n  * [Membership](https://x.org/join)\n'
               '  * [Calendar](https://x.org/calendar)')
        cookie = ('### Cookie List\nWe use strictly necessary cookies to run this site and '
                  'optional cookies to measure traffic; you can change preferences anytime.')
        skip = '[ Skip to main content ](https://x.org/events?page=2)'
        text = f'{nav}\n\n## Event 1\nOct 3\n\n{cookie}\n\n{FOOTER}\n\n{skip}\n\n{nav}'
        out, _ = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(out.count('Main navigation'), 1)

    def test_dateless_repeat_under_new_title_is_dropped(self):
        policy = ('In order for you to join us, we require a physical, valid, scannable '
                  'US Government issued ID or foreign passport for admission; no exceptions.')
        text = f'### Party A\n\n{policy}\n\n### Party B\n\n{policy}'
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(out.count('In order for you to join us'), 1)
        self.assertEqual(removed, len(policy))

    def test_whole_card_with_its_own_title_rendered_twice_is_dropped(self):
        # Carousel + list: the card carries its own heading, so a copy is the
        # same card even when a different heading precedes it.
        card = ('[ ![](https://img.example.org/c.jpg) ](https://x.org/e/1)\n'
                '### [Interest Meeting](https://x.org/e/1)\nThu, Oct 1 4pm EDT\n'
                'Virtual event, register to receive the meeting link.')
        text = f'## Featured\n\n{card}\n\n## All Events\n\n{card}'
        out, removed = extractor.dedupe_repeated_paragraphs(text)
        self.assertEqual(out.count('Interest Meeting'), 1)
        self.assertEqual(removed, len(card))


if __name__ == '__main__':
    unittest.main()
