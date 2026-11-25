import unittest

import overlay_guest


def inventory():
    return {
        "gateway": {"bgpSettings": {"bgpPeeringAddresses": [
            {"ipconfigurationId": "/gateway/ipConfigurations/vpn1",
             "tunnelIpAddresses": ["8.8.4.4", "10.244.255.5"],
             "defaultBgpIpAddresses": ["10.244.255.6"],
             "customBgpIpAddresses": ["169.254.22.2"]},
            {"ipconfigurationId": "/gateway/ipConfigurations/vpn0",
             "tunnelIpAddresses": ["8.8.8.8", "10.244.255.4"],
             "defaultBgpIpAddresses": ["10.244.255.7"],
             "customBgpIpAddresses": ["169.254.21.2"]},
        ]}},
        "cpe": {"networkInterfaces": [{"accessConfigs": [{"natIP": "1.1.1.1"}]}]},
    }


class GuestConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.psks = {"internet": "1" * 64, "private": "2" * 64}

    def render(self, stage):
        return overlay_guest.files(inventory(), self.psks, stage)

    def test_static_baseline_has_one_tunnel_and_no_bgp_adjacencies(self):
        files = self.render("internet")
        self.assertEqual(files["/etc/swanctl/conf.d/vnbgp.conf"].count("local_addrs ="), 1)
        self.assertNotIn("remote-as", files["/etc/frr/frr.conf"])
        self.assertIn("dev xfrm-internet", files["/usr/local/sbin/vnbgp-network"])

    def test_private_migration_keeps_internet_identity_and_adds_instances_in_order(self):
        baseline = self.render("internet")["/etc/swanctl/conf.d/vnbgp.conf"]
        first = self.render("private-first")
        both = self.render("private")
        self.assertEqual(first["/etc/swanctl/conf.d/vnbgp.conf"].count("local_addrs ="), 2)
        self.assertEqual(both["/etc/swanctl/conf.d/vnbgp.conf"].count("local_addrs ="), 3)
        internet_block = baseline.split("  internet {", 1)[1].split("}\nsecrets", 1)[0]
        self.assertIn(internet_block.rstrip("}\n"), both["/etc/swanctl/conf.d/vnbgp.conf"])
        network = both["/usr/local/sbin/vnbgp-network"]
        self.assertIn("10.244.255.7/32 dev xfrm-private0 src 10.245.254.6", network)
        self.assertIn("10.244.255.6/32 dev xfrm-private1 src 10.245.254.6", network)
        self.assertNotIn("169.254.21.2/32", network)

    def test_backup_enablement_changes_bgp_without_replacing_ipsec_or_psks(self):
        private, backup = self.render("private"), self.render("backup")
        self.assertEqual(
            private["/etc/swanctl/conf.d/vnbgp.conf"],
            backup["/etc/swanctl/conf.d/vnbgp.conf"],
        )
        self.assertIn("169.254.21.2/32 dev xfrm-internet src 169.254.21.1",
                      backup["/usr/local/sbin/vnbgp-network"])
        network = backup["/usr/local/sbin/vnbgp-network"]
        self.assertLess(
            network.index("ip address replace 169.254.21.1/32"),
            network.index("169.254.21.2/32 dev xfrm-internet src 169.254.21.1"),
        )
        self.assertNotIn("ip route replace 10.244.0.0/16",
                         backup["/usr/local/sbin/vnbgp-network"])
        self.assertIn("ip route del 10.244.0.0/16",
                      backup["/usr/local/sbin/vnbgp-network"])
        frr = backup["/etc/frr/frr.conf"]
        self.assertEqual(frr.count("remote-as 65515"), 3)
        self.assertIn("set as-path prepend 64513 64513\n", frr)
        self.assertIn("set local-preference 200", frr)
        self.assertIn("set local-preference 100", frr)


if __name__ == "__main__":
    unittest.main()
