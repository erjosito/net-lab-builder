import copy
import unittest
from unittest.mock import patch

import design_hrp_bgp_reset as reset


class ResetTests(unittest.TestCase):
    def test_actions_target_only_azure_bgp_protocols(self):
        for site in reset.sweep.SITES:
            for action in ("inspect", "disable", "enable"):
                text = reset.session_script(site, action)
                body = text.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
                compile(body, "<BGP-only-control>", "exec")
                self.assertIn("for peer in ('azure_0','azure_1')", body)
                self.assertNotIn("systemctl','restart", body)
                self.assertNotIn("swanctl','--terminate", body)
                self.assertNotIn("swanctl','--initiate", body)
                self.assertIn("assert ready", body)
        with self.assertRaises(ValueError):
            reset.session_script("cn", "disable")
        with self.assertRaises(ValueError):
            reset.session_script("jp", "restart-ipsec")

    def test_both_advertisement_orders_cover_all_six_sessions(self):
        self.assertEqual(reset.ORDERS["japan-first"][0], "jp")
        self.assertEqual(reset.ORDERS["nva-first"][-1], "jp")
        for sites in reset.ORDERS.values():
            self.assertEqual(set(sites), set(reset.sweep.SITES))
            self.assertEqual(len(sites) * 2, 6)

    def test_transport_guard_rejects_actual_mesh_restarts(self):
        before = {site: dict(birdPid=10, sha256="same", stat={"mtimeNs": 5},
                            after={"rows": {"mesh_test": {"info": "Established", "since": "10:00:00.123"}}})
                  for site in reset.sweep.SITES}
        before["jp"]["ipsecConfigurationSha256"] = "same-ipsec"
        after = copy.deepcopy(before)
        after["eu"]["after"]["rows"]["mesh_test"]["since"] = "10:00:00.124"
        reset.assert_transport_unchanged(before, after)
        after["eu"]["after"]["rows"]["mesh_test"]["since"] = "10:01:00.123"
        with self.assertRaises(RuntimeError):
            reset.assert_transport_unchanged(before, after)
        after = copy.deepcopy(before)
        after["jp"]["ipsecConfigurationSha256"] = "changed"
        with self.assertRaises(RuntimeError):
            reset.assert_transport_unchanged(before, after)

    def test_all_routes_must_withdraw_before_any_reenable(self):
        with patch.object(reset, "firewall_now", side_effect=[[{"prefix": "10.130.0.0/24"}], []]), \
                patch.object(reset.sweep, "save"), patch.object(reset.sweep, "bounded_wait") as wait:
            reset.confirm_all_withdrawn({})
            wait.assert_called_once_with(30)
        with patch.object(reset, "firewall_now", return_value=[{"prefix": "10.130.0.0/24"}]), \
                patch.object(reset.sweep, "save"), patch.object(reset.sweep, "bounded_wait"):
            with self.assertRaises(RuntimeError):
                reset.confirm_all_withdrawn({})


if __name__ == "__main__":
    unittest.main()
