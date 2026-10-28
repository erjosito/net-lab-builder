import ast
import hashlib
import unittest

import design_backbone as backbone
import guest


class BackboneTests(unittest.TestCase):
    def test_policy_preserves_export_loop_guard_and_excludes_own_dc(self):
        for site in ("eu", "us", "jp"):
            text = guest.bird(site, {"eu": ["10.250.0.69", "10.250.0.70"],
                                     "us": ["10.251.0.69", "10.251.0.70"]},
                              [{"bgp": "169.254.21.2", "id": 41},
                               {"bgp": "169.254.21.6", "id": 42}])
            value = backbone.policy(text, site)
            head, _, tail = value.partition("protocol bgp azure_0 {")
            self.assertEqual(tail.count("bgp_local_pref = 400;"), 2)
            self.assertNotIn(guest.DC[site], tail)
            self.assertIn('(proto = "own_dc" || proto ~ "mesh_*")', head)
            self.assertNotIn('proto ~ "azure_*") then accept', head)
            if site == "jp":
                self.assertEqual(head.count("bgp_path.prepend(65013);"), 3)
                self.assertIn("if net != 10.130.0.0/24", head)
            else:
                self.assertEqual(head, text.partition("protocol bgp azure_0 {")[0])

    def test_workload_udr_excludes_wireguard_outer_endpoints(self):
        routes = backbone.route_table("unused")["properties"]["routes"]
        self.assertEqual(len(routes), 5)
        self.assertNotIn("10.140.0.0/24", [r["properties"]["addressPrefix"] for r in routes])
        self.assertTrue(all(r["properties"]["nextHopIpAddress"] == "10.130.0.4" for r in routes))

    def test_generated_script_is_python310_and_restores_metadata(self):
        before = dict(config="original\n", sha256=hashlib.sha256(b"original\n").hexdigest(),
                      stat=dict(uid=113, gid=122, mode=384, mtimeNs=123456789))
        for restore in (False, True):
            script = backbone.config_script(before, "candidate\n", restore)
            ast.parse(script.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0], feature_version=(3, 10))
            self.assertIn("os.chown(candidate", script)
            self.assertIn("os.utime(candidate,ns=", script)
            self.assertIn("BACKBONE_CONFIG_COMPLETE", script)


if __name__ == "__main__":
    unittest.main()
