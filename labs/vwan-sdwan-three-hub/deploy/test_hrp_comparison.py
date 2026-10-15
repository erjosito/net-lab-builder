import unittest
from unittest.mock import patch

import hrp_comparison


class HubPreferenceTests(unittest.TestCase):
    def test_vpn_gateway_arm_enum_is_written_to_all_three_hubs(self):
        with patch.object(hrp_comparison.sweep, "rest", return_value={
            "name": "hub-test", "location": "westeurope",
            "properties": {"hubRoutingPreference": "ASPath"}
        }), patch.object(hrp_comparison.sweep, "submit") as submit:
            hrp_comparison.set_preference("VpnGateway", "test")
        document = submit.call_args.args[0]
        self.assertEqual(len(document["resources"]), 3)
        self.assertTrue(all(r["properties"]["hubRoutingPreference"] == "VpnGateway"
                            for r in document["resources"]))
        self.assertTrue(submit.call_args.kwargs["mutation"])

    def test_display_label_vpn_is_rejected_before_live_requests(self):
        with patch.object(hrp_comparison.sweep, "rest") as rest:
            with self.assertRaisesRegex(ValueError, "hubRoutingPreference"):
                hrp_comparison.set_preference("Vpn", "test")
        rest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
