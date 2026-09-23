"""A branch alias belongs to its publisher unless explicitly portable."""
import unittest
from unittest.mock import patch
import processor


def make_map(blocked=True, extra=False):
    place = dict(id=1,name="Trader Joe's at Union Square",short_name='',address='',
                 lat=40.,lng=-74.,emoji='X',alternate_names=[],
                 website_scoped_names={10:["Trader Joe's"]},
                 nonportable_scoped_names={10:["Trader Joe's"]} if blocked else {})
    if extra:
        place['website_scoped_names'][11] = ["Trader Joe's"]
    with patch.object(processor.db,'get_all_locations',return_value=[place]), \
         patch.object(processor.db,'get_website_locations_map',return_value={}), \
         patch.object(processor.db,'get_website_names',return_value={}), \
         patch.object(processor.db,'get_roving_organizer_websites',return_value=set()):
        return processor.build_locations_map(None)


def resolve(m,site,name="Trader Joe's"):
    return processor.get_location_id(name,None,'source','Some Event',m,website_id=site)


class AliasPortabilityTests(unittest.TestCase):
    def test_nonportable_alias_still_resolves_for_its_source(self):
        assert resolve(make_map(),10)['id']==1


    def test_nonportable_alias_declines_elsewhere_and_without_source(self):
        assert resolve(make_map(),20) is None
        assert resolve(make_map(),None) is None


    def test_existing_portable_behavior_is_preserved(self):
        assert resolve(make_map(blocked=False),20)['id']==1


    def test_other_portable_alias_cannot_reenable_blocked_shorthand(self):
        assert resolve(make_map(extra=True),20) is None
        assert resolve(make_map(extra=True),11)['id']==1


    def test_full_branch_name_still_resolves_globally(self):
        assert resolve(make_map(),20,"Trader Joe's at Union Square")['id']==1

class VenueSpecificityTests(unittest.TestCase):
    def build(self, names, home=None):
        locations=[dict(id=i,name=n,short_name=s,address='',lat=1.,lng=1.,emoji='X',
                        alternate_names=[],website_scoped_names={},
                        ambiguous_bare_names=['Green Room'] if i==1 and 'Green Room' in n else []) for i,n,s in names]
        with patch.object(processor.db,'get_all_locations',return_value=locations), \
             patch.object(processor.db,'get_website_locations_map',return_value={10:[locations[0]]} if home else {}), \
             patch.object(processor.db,'get_website_names',return_value={}), \
             patch.object(processor.db,'get_roving_organizer_websites',return_value=set()):
            return processor.build_locations_map(None)

    def test_bare_brand_declines_but_explicit_branch_survives_normalization(self):
        m=self.build([(1,'Green Room NYC','Green Room'),(2,'Green Room 42',''),(3,'Green Room Jersey City','')])
        self.assertIsNone(resolve(m,None,'Green Room'))
        self.assertEqual(resolve(m,None,'Green Room NYC')['id'],1)
        self.assertEqual(resolve(m,None,'Green Room Jersey City')['id'],3)

    def test_unreviewed_shorthand_does_not_inherit_the_guard(self):
        m=self.build([(1,'Basement NY','Basement'),(2,'Basement Chinatown','')])
        self.assertEqual(resolve(m,None,'BASEMENT')['id'],1)

    def test_owning_site_can_still_identify_its_branch(self):
        m=self.build([(1,'Green Room NYC','Green Room'),(2,'Green Room 42','')],home=True)
        self.assertEqual(resolve(m,10,'Green Room')['id'],1)

    def test_parent_first_child_name_beats_single_site_home(self):
        m=self.build([(1,'Brooklyn Bridge Park',''),(2,'Pier 3 at Brooklyn Bridge Park','')],home=True)
        result=resolve(m,10,'Brooklyn Bridge Park Pier 3 Central Lawn')
        self.assertEqual(result['id'],2)

    def test_unknown_child_keeps_parent_without_guessing(self):
        m=self.build([(1,'Brooklyn Bridge Park',''),(2,'Pier 3 at Brooklyn Bridge Park','')],home=True)
        self.assertEqual(resolve(m,10,'Brooklyn Bridge Park Pier 77')['id'],1)

    def test_ambiguous_children_keep_parent(self):
        m=self.build([(1,'Brooklyn Bridge Park',''),(2,'Pier 3 at Brooklyn Bridge Park',''),
                      (3,'Central Lawn at Brooklyn Bridge Park','')],home=True)
        self.assertEqual(resolve(m,10,'Brooklyn Bridge Park Pier 3 Central Lawn')['id'],1)


if __name__ == "__main__":
    unittest.main()
