"""Active location chunks must follow event foreign keys, never shared geocodes."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exporter import get_active_locations


class ActiveLocationIdentityTests(unittest.TestCase):
    def test_shared_building_is_not_exported_for_its_tenant(self):
        building = dict(id=2163, lat=40.7, lng=-74)
        loft = dict(id=7002, lat=40.7, lng=-74)
        self.assertEqual(get_active_locations(
            [dict(place_id=7002, lat=40.7, lng=-74)], [building, loft]), [loft])

    def test_foreign_key_wins_over_coordinate_rounding_and_zero_values(self):
        venue = dict(id=1, lat=0, lng=0)
        self.assertEqual(get_active_locations(
            [dict(place_id=1, lat=0.0001, lng=0.0001)], [venue]), [venue])

    def test_missing_id_never_infers_a_tenant_from_coordinates(self):
        venue = dict(id=1, lat=40.7, lng=-74)
        self.assertEqual(get_active_locations(
            [dict(place_id=2, lat=40.7, lng=-74), dict(lat=40.7, lng=-74)], [venue]), [])

    def test_chunk_contains_each_referenced_venue_once(self):
        venues = [dict(id=i, lat=40.7, lng=-74) for i in range(1, 4)]
        self.assertEqual(get_active_locations(
            [dict(place_id=i) for i in [2, 1, 2]], venues), venues[:2])
