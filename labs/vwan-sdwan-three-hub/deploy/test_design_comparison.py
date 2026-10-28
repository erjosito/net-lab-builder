import unittest

import design_comparison as comparison


class DesignComparisonTests(unittest.TestCase):
    def test_selected_route_does_not_take_attributes_from_losing_candidate(self):
        text = """10.130.0.0/24 unicast [azure_0 today] * (100) [AS65013i]
 BGP.as_path: 65515 65520 65520 65013
 BGP.local_pref: 400
                    unicast [mesh_jp today] (100) [AS65013i]
 BGP.as_path: 65013
 BGP.local_pref: 100
10.140.0.0/24 unicast [mesh_cn today] * (100)
"""
        value = comparison.selected_route(text, "10.130.0.0/24")
        self.assertEqual(value["protocol"], "azure_0")
        self.assertEqual(value["asPath"], [65515, 65520, 65520, 65013])
        self.assertEqual(value["localPreference"], 400)
        with self.assertRaisesRegex(RuntimeError, "missing"):
            comparison.selected_route(text, "10.120.0.0/24")

    def test_exact_mixed_user_hub_preferences_preserved(self):
        hubs = {s: dict(hub=dict(name="hub-" + s, location="test",
                                properties=dict(hubRoutingPreference=p)))
                for s, p in zip(comparison.sweep.SITES, ("ASPath", "ASPath", "ExpressRoute"))}
        resources = comparison.original_hubs(hubs)
        self.assertEqual([r["properties"]["hubRoutingPreference"] for r in resources],
                         ["ASPath", "ASPath", "ExpressRoute"])

    def test_selected_route_with_failed_kernel_export_is_explicit(self):
        text = """10.30.0.0/24 unicast [azure_1 today] ! (100/?) [AS65515i]
 BGP.as_path: 65515
 BGP.local_pref: 300
                     unicast [azure_0 today] (100/?)
 BGP.as_path: 65515 65520
 BGP.local_pref: 100
"""
        value = comparison.selected_route(text, "10.30.0.0/24")
        self.assertEqual(value["protocol"], "azure_1")
        self.assertEqual(value["asPath"], [65515])
        self.assertEqual(value["selectionMarker"], "!")
        self.assertTrue(value["kernelExportFailed"])


if __name__ == "__main__":
    unittest.main()
