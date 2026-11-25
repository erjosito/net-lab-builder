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
        for name in ["internet", "private0", "private1"]:
            previous = private["/etc/swanctl/conf.d/vnbgp.conf"].split(f"  {name} {{\n", 1)[1]
            updated = backup["/etc/swanctl/conf.d/vnbgp.conf"].split(f"  {name} {{\n", 1)[1]
            self.assertEqual(previous.split("\n  }\n", 1)[0], updated.split("\n  }\n", 1)[0])
        self.assertEqual(
            private["/etc/swanctl/conf.d/vnbgp.conf"].split("\nsecrets", 1)[1],
            backup["/etc/swanctl/conf.d/vnbgp.conf"].split("\nsecrets", 1)[1],
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
        self.assertEqual(frr.count("remote-as 65515"), 4)
        self.assertIn("set as-path prepend 64513 64513\n", frr)
        self.assertIn("set local-preference 200", frr)
        self.assertIn("set local-preference 100", frr)

    def test_second_internet_instance_uses_public_identity_and_shared_lng_source(self):
        rendered = self.render("backup")
        specs = overlay_guest.tunnel_specs(inventory())
        self.assertEqual(len({s["id"] for s in specs}), 4)
        second = next(s for s in specs if s["name"] == "internet1")
        self.assertEqual(second["instance"], "vpn1")
        self.assertEqual(second["outer"], "8.8.4.4")
        self.assertEqual(second["bgp"], "169.254.22.2")
        self.assertEqual(second["source"], "169.254.21.1")
        connection = rendered["/etc/swanctl/conf.d/vnbgp.conf"].split("  internet1 {\n", 1)[1]
        self.assertIn("id = 1.1.1.1\n", connection)
        self.assertIn("remote_addrs = 8.8.4.4", connection)
        network = rendered["/usr/local/sbin/vnbgp-network"]
        self.assertIn("8.8.4.4/32 via \"$GW\" dev \"$NIC\" src 10.245.0.10", network)
        self.assertIn("169.254.22.2/32 dev xfrm-internet1 src 169.254.21.1", network)
        self.assertLess(
            network.index("ip address replace 169.254.21.1/32"),
            network.index("169.254.22.2/32 dev xfrm-internet1"),
        )
        frr = rendered["/etc/frr/frr.conf"]
        self.assertIn("neighbor 169.254.22.2 update-source 169.254.21.1", frr)
        self.assertIn("neighbor 169.254.22.2 route-map INTERNET-IN in", frr)
        self.assertIn("neighbor 169.254.22.2 route-map INTERNET-OUT out", frr)
        self.assertIn(
            "for child in internet private0 private1 internet1;",
            overlay_guest.install_script(inventory(), self.psks, "backup"),
        )

    def test_add_only_install_avoids_existing_peer_routes_and_global_frr_reload(self):
        script = overlay_guest.install_script(inventory(), self.psks, "backup", add_only=True)
        self.assertNotIn("systemctl reload frr", script)
        self.assertNotIn("systemctl restart", script)
        self.assertNotIn("/usr/local/sbin/vnbgp-network", script.splitlines())
        self.assertNotIn("ip route replace 10.244.255.", script)
        self.assertIn("169.254.22.2/32 dev xfrm-internet1 src 169.254.21.1", script)
        self.assertIn("neighbor 169.254.22.2 remote-as 65515", script)
        self.assertLess(
            script.index("neighbor 169.254.22.2 route-map INTERNET-OUT out"),
            script.index("neighbor 169.254.22.2 activate"),
        )
        self.assertIn("swanctl --load-conns", script)
        self.assertNotIn("swanctl --load-all", script)
        self.assertLess(script.index("ip -4 address show dev lo"), script.index("printf %s"))


if __name__ == "__main__":
    unittest.main()
