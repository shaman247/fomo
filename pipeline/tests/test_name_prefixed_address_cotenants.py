"""A name-prefixed location is a co-tenant of its building's strict address key.

`_extract_street_address` needs a leading house number, so "Madison Square
Park, 11 Madison Ave, ..." never enters the strict tier and Eleven Madison Park
owns "11 madison ave" alone. The prefixed row is now recorded as a co-tenant
(same place only: "1 museum dr" is Greenwich CT and Roslyn NY). A source that
names the co-tenant gets it. A bare address still means the owner, because a
blanket AMBIGUOUS unpinned as many right matches as wrong ones (2026-10-07).
"""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processor


def build(places):
    for p in places:
        p.setdefault('lat', 40.74)
        p.setdefault('lng', -73.99)
        p.update(short_name='', emoji='X', alternate_names=[], website_scoped_names={})
    with patch.object(processor.db, 'get_all_locations', return_value=places), \
            patch.object(processor.db, 'get_website_locations_map', return_value={}), \
            patch.object(processor.db, 'get_website_names', return_value={}), \
            patch.object(processor.db, 'get_roving_organizer_websites', return_value=set()):
        return processor.build_locations_map(None)


EMP = dict(id=9897, name='Eleven Madison Park', address='11 Madison Ave, New York, NY 10010')
MSP = dict(id=512, name='Madison Square Park',
           address='Madison Square Park, 11 Madison Ave, New York, NY 10010, USA', lng=-73.988)


class PrefixedAddressKeyTests(unittest.TestCase):
    def test_keys_of_a_name_prefixed_address(self):
        self.assertEqual(processor._name_prefixed_address_keys(MSP['address']), {'11 madison ave'})

    def test_bare_address_has_no_prefixed_keys(self):
        self.assertEqual(processor._name_prefixed_address_keys(EMP['address']), set())

    def test_skips_a_bare_number_part(self):
        self.assertIn('338 moffat st', processor._name_prefixed_address_keys(
            'l, 6409, 338 Moffat St, Brooklyn, NY 11237, USA'))

    def test_name_only_address_has_no_keys(self):
        self.assertEqual(processor._name_prefixed_address_keys('Bryant Park, New York, NY'), set())


class AddressCotenantTests(unittest.TestCase):
    def test_same_building_registers_cotenant_not_ambiguity(self):
        lm = build([dict(EMP), dict(MSP)])
        self.assertEqual(lm['addresses']['11 madison ave']['id'], 9897)
        self.assertEqual([c['id'] for c in lm['address_cotenants']['11 madison ave']], [512])

    def test_order_does_not_matter(self):
        lm = build([dict(MSP), dict(EMP)])
        self.assertEqual(lm['addresses']['11 madison ave']['id'], 9897)
        self.assertEqual([c['id'] for c in lm['address_cotenants']['11 madison ave']], [512])

    def test_prefixed_row_never_owns_the_key(self):
        lm = build([dict(MSP)])
        self.assertNotIn('11 madison ave', lm['addresses'])

    def test_bare_address_keeps_its_owner(self):
        # Hidden Jewel Box inside Port Authority, Kingsland Wildflowers under
        # Last Frontier's deliberately prefixed row: a bare address means the
        # owner (measured 2026-10-07; a blanket AMBIGUOUS unpinned 51 right ones).
        lm = build([dict(id=7648, name='The Hidden Jewel Box Theater',
                         address='625 8th Ave, New York, NY 10018, USA'),
                    dict(id=5732, name='Port Authority Bus Terminal',
                         address='Port Authority Bus Terminal, 625 8th Ave, New York, NY 10018, USA')])
        result = processor.get_location_id('625 8th Ave', '', '', 'Knock Twice Comedy Show', lm)
        self.assertEqual((result['id'], result['step']), (7648, 'address'))

    def test_named_cotenant_takes_the_address(self):
        lm = build([dict(id=5032, name='Cipriani South Street', address='10 South St, New York, NY 10004'),
                    dict(id=9361, name='Battery Maritime Building',
                         address='Battery Maritime Building Slip 5, 10 South St, New York, NY 10005, USA')])
        result = processor.get_location_id('10 South Street', 'Battery Maritime Building lobby', '',
                                           'Governors Island School Field Trip', lm)
        self.assertEqual(result['id'], 9361)

    def test_named_owner_wins_over_named_cotenant(self):
        lm = build([dict(id=207, name='City Winery', address='25 11th Ave, New York, NY 10011, USA'),
                    dict(id=663, name='Pier 57', address='Pier 57, 25 11th Ave, New York, NY 10011, USA')])
        self.assertEqual(processor._address_tier_match(
            lm, '25 11th ave', 'City Winery at Pier 57, 25 11th Ave')['id'], 207)
        self.assertEqual(processor._address_tier_match(
            lm, '25 11th ave', 'Pier 57, 25 11th Ave')['id'], 663)
        self.assertEqual(processor._address_tier_match(lm, '25 11th ave', '25 11th Ave')['id'], 207)

    def test_two_named_cotenants_keep_the_owner(self):
        lm = build([dict(id=1597, name='Village Community Boathouse', address='353 West Street, New York, NY 10014'),
                    dict(id=401, name='Hudson River Park', address='Hudson River Park, 353 West St, New York, NY 10014, USA'),
                    dict(id=8269, name='Pier 40', address='Pier 40, 353 West St, New York, NY 10014, USA')])
        self.assertEqual(processor._address_tier_match(
            lm, '353 w st', 'Pier 40 at Hudson River Park')['id'], 1597)

    def test_ambiguous_key_stays_ambiguous(self):
        lm = build([dict(id=1, name='Venue One', address='63 Flushing Ave, Brooklyn, NY 11205'),
                    dict(id=2, name='Venue Two', address='63 Flushing Ave, Brooklyn, NY 11205'),
                    dict(id=3, name='Building Three', address='Building Three, 63 Flushing Ave, Brooklyn, NY 11205')])
        self.assertIs(processor._address_tier_match(lm, '63 flushing ave', 'Building Three'),
                      processor._AMBIGUOUS_ADDRESS)

    def test_other_state_is_not_a_cotenant(self):
        lm = build([dict(id=6823, name='Bruce Museum', address='1 Museum Dr, Greenwich, CT 06830, USA',
                         lat=41.02, lng=-73.62),
                    dict(id=3638, name='Nassau County Museum of Art',
                         address='Nassau County Museum of Art One, 1 Museum Dr, Roslyn, NY 11576, USA',
                         lat=40.81, lng=-73.64)])
        self.assertNotIn('1 museum dr', lm['address_cotenants'])

    def test_other_town_far_away_is_not_a_cotenant(self):
        lm = build([dict(id=9050, name='The Boat Yard', address='1 Ocean Pkwy, Massapequa, NY 11758, USA',
                         lat=40.63, lng=-73.42),
                    dict(id=1968, name='Jones Beach State Park',
                         address='Jones Beach State Park, 1 Ocean Pkwy, Wantagh, NY 11793, USA',
                         lat=40.60, lng=-73.50)])
        self.assertNotIn('1 ocean pkwy', lm['address_cotenants'])

    def test_differently_spelled_city_close_by_is_a_cotenant(self):
        lm = build([dict(id=11041, name='Pier 5 at Brooklyn Bridge Park',
                         address='334 Furman St, Brooklyn Heights, NY 11201', lat=40.6940, lng=-73.9990),
                    dict(id=10221, name='Liberty Lawn',
                         address='Liberty Lawn, Brooklyn Bridge Park Pier 6, 334 Furman St, Brooklyn, NY 11201, USA',
                         lat=40.6925, lng=-74.0010)])
        self.assertEqual([c['id'] for c in lm['address_cotenants']['334 furman st']], [10221])


if __name__ == '__main__':
    unittest.main()
