"""Postal ingestion boundaries must preserve configured coverage carve-ins."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geographic_coverage import CoverageArea
try:
    from sources import libnet_api
except ImportError:
    libnet_api = None

HOST = "theoceancountylibrary.libnet.info"


def event(identifier, branch, series=None):
    return {
        "id": identifier, "recurring_id": series, "location": branch,
        "title": f"Library program {identifier}", "event_type": "INPERSON",
        "event_start": "2026-10-15 10:00:00", "time_string": "10-11am",
        "url": f"https://{HOST}/event/{identifier}",
    }


@unittest.skipIf(libnet_api is None, 'deployment-specific source plugin not installed')
class LibnetCoverageTests(unittest.TestCase):
    def test_outside_branches_are_removed_before_extraction(self):
        branches = ["Stafford Branch", "Barnegat Branch", "Long Beach Island Branch",
                    "Little Egg Harbor Branch", "Tuckerton Branch"]
        rows = [event(str(i), branch) for i, branch in enumerate(branches)]
        rows.append(event("keep", "Toms River Branch"))
        with patch.object(libnet_api, "_fetch_events", return_value=rows):
            for _ in range(2):
                text, count = libnet_api.fetch_and_build_markdown([f"https://{HOST}/events"])
                self.assertEqual(count, 1)
                self.assertIn("/event/keep", text)
                for branch in branches:
                    self.assertNotIn(branch, text)

    def test_configured_carve_ins_survive(self):
        coverage = CoverageArea()
        for branch in ["Plumsted Branch", "Jackson Branch", "Toms River Branch",
                       "Waretown Branch", "Upper Shores Branch"]:
            with self.subTest(branch=branch):
                self.assertEqual(coverage.classify_address(
                    libnet_api._coverage_address(HOST, event("1", branch)))[0], "in")

    def test_moving_series_loses_only_outside_occurrences(self):
        rows = [event("outside", "Stafford Branch", "tour"),
                event("inside", "Plumsted Branch", "tour")]
        with patch.object(libnet_api, "_fetch_events", return_value=rows):
            text, count = libnet_api.fetch_and_build_markdown([f"https://{HOST}/events"])
        self.assertEqual(count, 1)
        self.assertIn("/event/inside", text)
        self.assertIn("Plumsted", text)
        self.assertNotIn("Stafford", text)
        self.assertNotIn("/event/outside", text)

    def test_unknown_offsite_and_other_hosts_are_not_suppressed(self):
        coverage = CoverageArea()
        for host, row in [(HOST, event("unknown", "New Branch")),
                          (HOST, dict(event("offsite", "Offsite"), venues="Stafford Branch")),
                          ("other.libnet.info", event("other", "Stafford Branch"))]:
            self.assertTrue(libnet_api._in_coverage(host, row, coverage))

    def test_missing_config_does_not_exclude_all_events(self):
        self.assertTrue(libnet_api._in_coverage(HOST, event("1", "Stafford Branch"), CoverageArea({})))

    def test_another_city_can_cover_ocean_exclusions(self):
        coverage = CoverageArea({"zip3": {"NJ": ["080"]}})
        self.assertTrue(libnet_api._in_coverage(HOST, event("1", "Stafford Branch"), coverage))
        self.assertFalse(libnet_api._in_coverage(HOST, event("2", "Toms River Branch"), coverage))

    def test_taconic_and_asbury_are_explicitly_in_current_config(self):
        coverage = CoverageArea()
        for address in ["1 Clermont Ave, Germantown, NY 12526",
                        "253 NY-344, Copake Falls, NY 12517",
                        "508 3rd Ave, Asbury Park, NJ 07712"]:
            self.assertEqual(coverage.classify_address(address)[0], "in")
        self.assertEqual(coverage.classify_address("Kinderhook, NY 12106")[0], "out")


if __name__ == "__main__":
    unittest.main()
