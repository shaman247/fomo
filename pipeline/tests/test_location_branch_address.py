"""An explicit address disambiguates branches without substituting co-tenants."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import processor

class BranchAddressTests(unittest.TestCase):
    def mapping(self, shared=False, scoped=False):
        places=[dict(id=1,name='Running Co.',address='222 Grand St, Brooklyn, NY 11211'),
                dict(id=2,name='Running Co. (Park Slope)',address='480 Bergen St, Brooklyn, NY 11217'),
                dict(id=3,name='Another Venue',address=('480 Bergen St, Brooklyn, NY 11217' if shared else '50 Main St, Brooklyn, NY 11201'))]
        for p in places:p.update(short_name='',lat=40.,lng=-74.,emoji='X',alternate_names=[],website_scoped_names={})
        if scoped:places[0]['website_scoped_names']={77:['Running Co.']}
        with patch.object(processor.db,'get_all_locations',return_value=places),patch.object(processor.db,'get_website_locations_map',return_value={}),patch.object(processor.db,'get_website_names',return_value={}),patch.object(processor.db,'get_roving_organizer_websites',return_value=set()):
            return processor.build_locations_map(None)
    def resolve(self,address,shared=False,name='Running Co.'):
        return processor.get_location_id(name,address,'','Workshop',self.mapping(shared))
    def test_bare_brand_uses_unique_branch_address(self):
        result=self.resolve('480 Bergen Street, Brooklyn, NY 11217')
        self.assertEqual(result['id'],2)
        self.assertEqual(result['step'],'branch_address')
    def test_shared_building_does_not_guess_branch(self):
        self.assertEqual(self.resolve('480 Bergen St, Brooklyn, NY 11217',shared=True)['id'],1)
    def test_unrelated_address_does_not_override_name(self):
        self.assertEqual(self.resolve('50 Main St, Brooklyn, NY 11201')['id'],1)
    def test_explicit_branch_name_is_preserved(self):
        self.assertEqual(self.resolve('222 Grand St, Brooklyn, NY 11211',name='Running Co. (Park Slope)')['id'],2)
    def test_branch_address_beats_bare_brand_scoped_alias(self):
        # BL87: w459's scoped "ShopRite" -> Greenway Plaza must not override a
        # listing whose own address is the Tuckahoe Rd branch.
        result=processor.get_location_id('Running Co.','480 Bergen St, Brooklyn, NY 11217','','Workshop',self.mapping(scoped=True),website_id=77)
        self.assertEqual((result['id'],result['step']),(2,'branch_address'))
    def test_scoped_alias_still_answers_without_an_address(self):
        result=processor.get_location_id('Running Co.','','','Workshop',self.mapping(scoped=True),website_id=77)
        self.assertEqual((result['id'],result['step']),(1,'website_alt'))
    def test_room_is_not_an_address(self):
        self.assertEqual(self.resolve('Second floor')['id'],1)

if __name__=='__main__':unittest.main()
