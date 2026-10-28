import unittest

import design_hrp_reselection as reselection


class ReselectionTests(unittest.TestCase):
    def test_withdrawal_changes_only_azure_export_filter(self):
        text = ("filter azure_export {\n  accept;\n}\n"
                "filter mesh_export {\n  accept;\n}\n"
                "export filter azure_export;\n")
        changed = reselection.withdraw_japan(text)
        self.assertEqual(changed.replace("  if net = 10.130.0.0/24 then reject;\n", ""), text)
        with self.assertRaises(ValueError):
            reselection.withdraw_japan(changed)
        with self.assertRaises(ValueError):
            reselection.withdraw_japan("unrecognized")

    def test_exact_original_wire_path_required(self):
        rows = [dict(observer=s, prefix="10.130.0.0/24", nextHopType="HubBgpConnection",
                     asPath="-".join([str(asn)] * 4 + ["65013"]))
                for s, asn in (("eu", 65011), ("us", 65012))]
        result = dict(firewalls=dict(rows=rows))
        self.assertTrue(reselection.local_japan(result))
        rows[0]["nextHopType"] = "Remote Hub"
        self.assertFalse(reselection.local_japan(result))

    def test_one_asn_difference_control(self):
        rows = [
            dict(observer="eu", prefix="10.130.0.0/24", nextHopType="HubBgpConnection",
                 asPath="65011-65011-65011-65013"),
            dict(observer="us", prefix="10.130.0.0/24", nextHopType="HubBgpConnection",
                 asPath="65012-65012-65012-65012-65013"),
        ]
        result = dict(firewalls=dict(rows=rows))
        self.assertTrue(reselection.local_japan(result, eu_extra=2))
        self.assertFalse(reselection.local_japan(result))


if __name__ == "__main__":
    unittest.main()
