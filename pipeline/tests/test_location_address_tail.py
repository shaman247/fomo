"""Tests for stripping a trailing postal address off a venue name.

Some sources render the venue as "<Name>, <full street address ... ZIP>" —
posh.vip's "Pier 78 at Hudson River Park — 455 12th Ave, New York, NY 10018,
USA", Painting Lounge's "Midtown: 40 W 38th St, 2nd Fl, New York NY 10018".
The address tail swamps every name comparison, so these never match even when
the venue exists in `locations`.

The fix is a LAST-RESORT retry in `get_location_id` (Step 8), not an up-front
normalization. A/B over all 30,119 distinct crawl_event location_names
(2026-08-05):

    strip up front : 49 wins, 16 REGRESSIONS, 3 wrong re-pins
    retry-on-miss  : 49 wins,  0 regressions, 0 re-pins

The regressions are the reason for the design: when the venue name is not
itself a known location, the ADDRESS is the only thing that resolves it
("Low Plaza, 535 W. 116 St." → loc 467 via the address tier). Retrying only
after every other tier has failed cannot disturb those.

The ZIP requirement is what keeps room/branch/stage/cross-street suffixes safe.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import _strip_trailing_postal_address as strip_addr


class TestStripsGenuineAddressTails(unittest.TestCase):
    def test_em_dash_posh_shape(self):
        self.assertEqual(
            strip_addr('Pier 78 at Hudson River Park — 455 12th Ave, New York, NY 10018, USA'),
            'Pier 78 at Hudson River Park')

    def test_comma_separated_venue_and_address(self):
        self.assertEqual(
            strip_addr('Dock72, Brooklyn Navy Yard, 1 Dock 72 Way, Brooklyn, NY 11205'),
            'Dock72, Brooklyn Navy Yard')

    def test_colon_separated_branch_label(self):
        """Painting Lounge names its branches "<Neighborhood>: <address>"."""
        self.assertEqual(
            strip_addr('Midtown: 40 W 38th St, 2nd Fl, New York NY 10018'), 'Midtown')
        self.assertEqual(
            strip_addr('Chelsea: 39 W 14th St, Suite 401, New York NY 10011'), 'Chelsea')

    def test_trailing_country_is_consumed(self):
        self.assertEqual(
            strip_addr("Sparrow's Nest Studio, 35 W 35th St. 12th Floor, New York, NY 10001, USA"),
            "Sparrow's Nest Studio")

    def test_zip_plus_four(self):
        self.assertEqual(
            strip_addr('Greenlight Bookstore, 686 Fulton Street, Brooklyn, NY 11217-1609'),
            'Greenlight Bookstore')

    def test_apostrophes_and_unicode_survive(self):
        self.assertEqual(
            strip_addr('St. Joseph’s Co-Cathedral, 856 Pacific Street, Brooklyn, NY 11238'),
            'St. Joseph’s Co-Cathedral')


class TestPreservesNonAddressSuffixes(unittest.TestCase):
    """No ZIP => not an address tail => must be left completely alone.

    Every string here is real data from `crawl_events.location_name`; each one
    would be corrupted by a naive "strip after the dash" rule.
    """

    UNTOUCHED = [
        'Bartow Community Center - Room 31',
        'Montague Store - 122 Montague St.',
        'Smith Store - 225 Smith St.',
        'NY - 14TH ST. Mainstage',
        'Livestream NY - 14TH ST. Mainstage',
        'Theater For the New City - Stage 3',
        'Multi-Use Room - 2nd Fl in Sorrentino Recreation Center',
        'Entrance - West 100 Street and Central Park West in Central Park',
        'Entrance - 34th Avenue between 77th and 78th Streets in Travers Park',
        'Colson Patisserie - 9th St. Park Slope',
        'La Clef, au 34, rue Daubenton – Paris 5e',
        'Clinton Hall — 36th Street',
        'Tishman Auditorium - Kennedy 100MPR',
        'SOHO - 478 West Broadway',
    ]

    def test_suffixes_without_a_zip_are_untouched(self):
        for name in self.UNTOUCHED:
            with self.subTest(name=name):
                self.assertEqual(strip_addr(name), name)


class TestNeverProducesAStub(unittest.TestCase):
    def test_bare_address_is_returned_unchanged(self):
        """Nothing precedes the address, so there is no venue name to recover."""
        for name in ('31 Chambers Street, New York, NY 10007',
                     '160 5th Ave New York NY 10010 United States',
                     '155 WEST ROE BLVD., PATCHOGUE, NY 11772'):
            with self.subTest(name=name):
                self.assertEqual(strip_addr(name), name)

    def test_empty_and_none(self):
        self.assertEqual(strip_addr(''), '')
        self.assertIsNone(strip_addr(None))

    def test_result_shorter_than_three_chars_is_rejected(self):
        self.assertEqual(strip_addr('A, 1 Main St, Brooklyn, NY 11201'),
                         'A, 1 Main St, Brooklyn, NY 11201')


if __name__ == '__main__':
    unittest.main()
