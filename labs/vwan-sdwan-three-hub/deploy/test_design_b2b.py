import unittest

import design_b2b as b2b
import b2b_report


class B2BTests(unittest.TestCase):
    def test_selection_comparison_ignores_only_display_timestamp(self):
        before = dict(jp=[dict(prefix="10.30.0.0/24", protocol="azure_1", asPath=[65515],
                               localPreference=300, selectionMarker="!",
                               headline="unicast [azure_1 21:30:14.189] ! (100/?)")])
        after = dict(jp=[dict(before["jp"][0], headline="unicast [azure_1 21:30:14.190] ! (100/?)")])
        self.assertEqual(b2b.selection_state(before), b2b.selection_state(after))
        for key, value in (("protocol", "azure_0"), ("localPreference", 400),
                           ("asPath", [65515, 65011]), ("selectionMarker", "*"),
                           ("headline", "unicast [azure_1 21:30:14.190] ! (200/?)")):
            changed = dict(jp=[dict(after["jp"][0], **{key: value})])
            self.assertNotEqual(b2b.selection_state(before), b2b.selection_state(changed))

    def test_retained_article_sections_do_not_duplicate_old_results(self):
        old = ("## One topology, two possible backbones\nTopology.\n\n"
               "## What the three designs configure\nStale results.\n\n"
               "## Retrieve effective routes\nCommands.\n\n## Old footer\nStale footer.\n")
        self.assertEqual(b2b_report.retained_section(old, "One topology, two possible backbones"), "Topology.")
        self.assertEqual(b2b_report.retained_section(old, "Retrieve effective routes"), "Commands.")
        with self.assertRaises(ValueError):
            b2b_report.retained_section(old, "Missing")

    def test_matrix_has_42_unique_directions(self):
        addresses = tuple(b2b.ENDPOINTS.values())
        self.assertEqual(len(set(addresses)), 7)
        self.assertEqual(len({(a, b) for a in addresses for b in addresses if a != b}), 42)

    def test_dc_azure_scope_has_exact_24_directions(self):
        pairs = {(a, b) for a in b2b.ENDPOINTS.values() for b in b2b.traffic_targets(a, True)}
        self.assertEqual(len(pairs), 24)
        self.assertEqual(len(b2b.traffic_targets("10.110.0.10", True)), 3)
        self.assertEqual(len(b2b.traffic_targets("10.10.0.10", True)), 4)
        self.assertNotIn(("10.110.0.10", "10.130.0.10"), pairs)
        self.assertNotIn(("10.10.0.10", "10.20.0.10"), pairs)
        with self.assertRaises(ValueError):
            b2b.traffic_targets("192.0.2.1")

    def test_acceptance_excludes_unrequested_failures(self):
        cells = [dict(source=a, destination=b, tcp="PASS", icmp="PASS")
                 for a in b2b.ENDPOINTS.values() for b in b2b.traffic_targets(a)]
        for cell in cells:
            if cell["destination"] not in b2b.traffic_targets(cell["source"], True):
                cell.update(tcp="FAIL", icmp="FAIL")
        result = b2b_report.acceptance(dict(cells=cells))
        self.assertEqual((result["tcpPass"], result["icmpPass"], result["expectedDirections"]), (24, 24, 24))
        self.assertEqual(result["verdict"], "PASS")
        result["cells"][0]["tcp"] = "FAIL"
        self.assertEqual(b2b_report.acceptance(dict(cells=cells))["verdict"], "FAIL")
        with self.assertRaises(ValueError):
            b2b_report.acceptance(dict(cells=result["cells"][:-1]))
        with self.assertRaises(ValueError):
            b2b_report.acceptance(dict(cells=result["cells"] + result["cells"][:1]))

    def test_effective_route_uses_active_longest_prefix(self):
        routes = dict(value=[
            dict(addressPrefix=["10.0.0.0/8"], state="Active", nextHopType="None"),
            dict(addressPrefix=["10.10.0.0/24"], state="Invalid", nextHopType="VirtualAppliance"),
        ])
        self.assertEqual(b2b_report.effective_match(routes, "10.10.0.10")["nextHopType"], "None")
        routes["value"][1]["state"] = "Active"
        self.assertEqual(b2b_report.effective_match(routes, "10.10.0.10")["nextHopType"], "VirtualAppliance")
        with self.assertRaises(ValueError):
            b2b_report.effective_match(routes, "192.0.2.1")
        routes["value"].append(routes["value"][1])
        with self.assertRaises(ValueError):
            b2b_report.effective_match(routes, "10.10.0.10")

    def test_traffic_is_sourced_and_checks_listener(self):
        text = b2b.traffic_script("10.110.0.10")
        self.assertIn("'--interface',source", text)
        self.assertIn("'ping','-n','-I',source", text)
        self.assertIn("'systemctl','is-active','lab-http'", text)
        self.assertIn("tcp['stdout']=='200 '+source+' '+destination", text)

    def test_capture_is_bounded_and_pid_scoped(self):
        text = b2b.capture_script("B1")
        self.assertIn("'timeout','240','tcpdump'", text)
        self.assertIn("Capture not responsive", text)
        self.assertIn("Capture PID identity differs", b2b.capture_script("B1", True))
        with self.assertRaises(ValueError):
            b2b.capture_script("../bad")

    def test_guest_python_compiles(self):
        for text in (b2b.capture_script("B1"), b2b.capture_script("B1", True),
                     b2b.traffic_script("10.110.0.10"), b2b.traffic_script("10.110.0.10", True)):
            compile(text.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0], "<guest>", "exec")

    def test_selected_route_keeps_resolution_distinct_from_bgp_hop(self):
        text = """10.130.0.0/24 unicast [mesh_jp 01:02:03] * (100)
 dev wgeujp
 Type: BGP univ
 BGP.as_path: 65013
 BGP.next_hop: 172.31.0.6
 BGP.local_pref: 100
                     unicast [azure_0 01:02:03] (100)
 via 10.210.0.1 on eth0
 BGP.next_hop: 10.210.0.1
"""
        row = b2b_report.selected_details(text, "10.130.0.0/24")
        self.assertEqual(row["resolution"], "dev wgeujp")
        self.assertEqual(row["nextHop"], "172.31.0.6")
        self.assertEqual(row["asPath"], [65013])

    def test_static_route_attributes_are_not_invented(self):
        text = """10.130.0.0/24 unicast [own_dc 01:02:03] * (200)
 dev eth0
 Type: static univ
"""
        row = b2b_report.selected_details(text, "10.130.0.0/24")
        self.assertEqual(row["nextHop"], "n/a")
        self.assertIsNone(row["localPreference"])


if __name__ == "__main__":
    unittest.main()
