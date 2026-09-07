"""Tests for the "<venue> at <container>" tiers (Steps 3.6 and 5e) in get_location_id.

Run: ./venv/bin/python pipeline/tests/test_venue_at_container.py

Guards the 2026-09-07 fix. Once Industry City's page carried each event once,
the extractor wrote "Fort Hamilton Distillery at Industry City" for the tenant
venues and 16 of 48 rows resolved to NULL: the tenant alias and the campus
name both existed, the combined string matched neither, and Step 1b only
handles curated child alts behind a dash/colon. The shape is general ("Pier 97
at Hudson River Park", "David H. Koch Theater at Lincoln Center"), so:

  * Step 3.6 resolves the LEFT half when it EXACTLY names a location
    (website-scoped / names / alternate_names — never short_names) that sits
    inside the container (child by name/address, or within 1 km) — or when the
    container is simply unknown;
  * Step 5e, last resort, resolves the CONTAINER half alone when the venue half
    is unknown ("Purslane Cafe at Prospect Park Boathouse" -> the Boathouse).

The decoys below pin the refusals: an organization AT a venue ("Jersey City
Theater Center at White Eagle Hall") must not pin to the organization's own
office across town; a weak short_name ("The Plaza at City Point") must not pick
some other Plaza; a generic left half ("Theater at ...") must fall to the container.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import processor
from test_parent_qualified_sublocation import _StubCursor

# id, name, short_name, address, lat, lng, emoji
_LOCATIONS = [
    (410, 'Industry City', None, '220 36th St, Brooklyn, NY 11232, USA', 40.65647, -74.00676, '🏭'),
    (7105, 'Fort Hamilton Distillery', None, '68 34th St Building 6, Brooklyn, NY 11232, USA',
     40.656937, -74.006272, '🥃'),
    (401, 'Hudson River Park', None, 'Hudson River Park, New York, NY 10014, USA', 40.7359, -74.0106, '🌳'),
    # named as a child of its container (address carries the park), 2.5 km from the park centroid
    (10180, 'Pier 97', None, 'Pier 97, Hudson River Park, W 57th St, New York, NY 10019, USA',
     40.7715, -73.9950, '🌳'),
    (968, 'White Eagle Hall', None, '337 Newark Ave, Jersey City, NJ 07302, USA', 40.7267, -74.0563, '🎭'),
    # an ORGANIZATION with its own row 3 km from the venue it performs at
    (5129, 'Jersey City Theater Center', None, '165 Newark Ave, Jersey City, NJ 07302, USA',
     40.7195, -74.0432, '🎭'),
    (60, 'Prospect Park Boathouse', None, '101 East Dr, Brooklyn, NY 11225, USA', 40.6606, -73.9647, '🏛️'),
    (2255, 'City Point', None, '445 Albee Square W, Brooklyn, NY 11201, USA', 40.6906, -73.9830, '🛍️'),
    # weak short_name decoy: some other "Plaza" miles away
    (6167, 'Plaza at Harlem River', 'The Plaza', '1 Bronx Terminal Way, Bronx, NY 10451, USA',
     40.8262, -73.9282, '🏢'),
    # single-token venue decoys: a bar called Oberon, and a venue-TYPE alias
    (3235, 'Oberon', None, '196 N 10th St, Brooklyn, NY 11211, USA', 40.7196, -73.9560, '🍸'),
    (223, 'Coney Island Amphitheater', None, '3052 W 21st St, Brooklyn, NY 11224, USA',
     40.5743, -73.9852, '🎤'),
]
_ALTERNATES = [
    (7105, 'Fort Hamilton Distillery', 53),      # the tenant's w53-scoped alias
    (60, 'Boathouse', None),
    (223, 'Amphitheater', None),
]
_WEBSITE_LOCATIONS = [
    (53, 410, 'Industry City', 40.65647, -74.00676, '🏭'),   # w53 single-venue: the campus
]


class VenueAtContainerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lm = processor.build_locations_map(
            _StubCursor(_LOCATIONS, _ALTERNATES, _WEBSITE_LOCATIONS))

    def resolve(self, location_name, website_id=None):
        got = processor.get_location_id(location_name, None, None, None, self.lm,
                                        website_id=website_id)
        return (got['id'], got.get('step')) if got else (None, None)

    # -- Step 3.6: the venue half wins ------------------------------------
    def test_tenant_at_campus_pins_to_the_tenant(self):
        """The Industry City case, and it must beat the single-venue site's
        authority (Step 3.5 would otherwise answer with the campus)."""
        self.assertEqual((7105, 'venue_at_container'),
                         self.resolve('Fort Hamilton Distillery at Industry City', website_id=53))

    def test_at_sign_is_the_same_connector(self):
        self.assertEqual((7105, 'venue_at_container'),
                         self.resolve('Fort Hamilton Distillery @ Industry City', website_id=53))

    def test_child_named_after_its_container_beyond_1km(self):
        """Pier 97 is 2.5 km from the park centroid but its address names the
        park, so `_child_of_parent` admits it."""
        self.assertEqual((10180, 'venue_at_container'),
                         self.resolve('Pier 97 at Hudson River Park'))

    def test_unknown_container_still_resolves_a_known_venue(self):
        self.assertEqual((10180, 'venue_at_container'),
                         self.resolve('Pier 97 at W 57th Street'))

    # -- the guards --------------------------------------------------------
    def test_organization_at_a_venue_pins_to_the_venue(self):
        """Left half names a real location that is NOT inside the container:
        Step 3.6 declines and Step 5e answers with the container."""
        self.assertEqual((968, 'container_of_venue'),
                         self.resolve('Jersey City Theater Center at White Eagle Hall'))

    def test_weak_short_name_never_picks_the_venue_half(self):
        """'The Plaza' exists only as a short_name of an unrelated venue."""
        self.assertEqual((2255, 'container_of_venue'), self.resolve('The Plaza at City Point'))

    def test_generic_left_half_falls_to_the_container(self):
        self.assertEqual((60, 'container_of_venue'),
                         self.resolve('Purslane Cafe at Prospect Park Boathouse'))
        self.assertEqual((60, 'container_of_venue'), self.resolve('Cafe at Boathouse'))

    def test_single_token_venue_with_unknown_container_is_refused(self):
        """With nothing to check the venue against, a one-word or venue-type
        left half is too weak to pin on its own."""
        self.assertEqual((None, None), self.resolve('Oberon at the New Museum'))
        self.assertEqual((None, None), self.resolve('The Amphitheater at Hebert Von King Park'))

    def test_generic_container_is_refused(self):
        self.assertEqual((None, None), self.resolve('Wafels at Park'))

    def test_full_string_exact_match_still_wins_first(self):
        """A curated full-string alias outranks the split (Step 1/2 run first)."""
        lm = processor.build_locations_map(_StubCursor(
            _LOCATIONS, _ALTERNATES + [(410, 'Fort Hamilton Distillery at Industry City', 99)],
            _WEBSITE_LOCATIONS))
        got = processor.get_location_id('Fort Hamilton Distillery at Industry City', None, None,
                                        None, lm, website_id=99)
        self.assertEqual(410, got['id'])
        self.assertEqual('website_alt', got['step'])

    def test_plain_names_unchanged(self):
        self.assertEqual((410, 'exact_names'), self.resolve('Industry City'))
        self.assertEqual((7105, 'exact_names'), self.resolve('Fort Hamilton Distillery'))


if __name__ == '__main__':
    unittest.main()
