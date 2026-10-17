import unittest

import design_b2b as b2b
import b2b_report


class B2BTests(unittest.TestCase):
    def test_matrix_has_42_unique_directions(self):
        addresses = tuple(b2b.ENDPOINTS.values())
        self.assertEqual(len(set(addresses)), 7)
        self.assertEqual(len({(a, b) for a in addresses for b in addresses if a != b}), 42)

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
                     b2b.traffic_script("10.110.0.10")):
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
