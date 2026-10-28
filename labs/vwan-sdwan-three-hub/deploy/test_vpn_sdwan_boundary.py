import copy
import unittest
from unittest.mock import patch

import vpn_sdwan_boundary as boundary


class DirectBoundaryTests(unittest.TestCase):
    def test_source_equality_uses_paths_not_volatile_cli_hashes(self):
        before = dict(sha256="original", stat={"mode": 384},
                      protocols={"azure_0": "Established"}, ikeEstablished=2,
                      exports={"azure_0": {"routes": {"10.140.0.0/24": [65014]},
                                           "rawSha256": "first"}})
        after = copy.deepcopy(before)
        after["exports"]["azure_0"]["rawSha256"] = "different"
        self.assertTrue(boundary.same_source(before, after))
        for key, value in (("sha256", "changed"), ("stat", {"mode": 420}),
                           ("protocols", {"azure_0": "Idle"}), ("ikeEstablished", 1),
                           ("exports", {}),
                           ("exports", {"azure_0": {"routes": {"10.140.0.0/24": [65012]}}})):
            changed = copy.deepcopy(after)
            changed[key] = value
            self.assertFalse(boundary.same_source(before, changed), key)

    def test_guest_metadata_precedes_atomic_replace(self):
        for site, asn in (("jp", 65013), ("eu", 65011)):
            text = boundary.script(site, 4)
            self.assertLess(text.index("os.chown(n"), text.index("os.replace(n,p)"))
            self.assertLess(text.index("os.chmod(n"), text.index("os.replace(n,p)"))
            self.assertEqual(text.count(f"bgp_path.prepend({asn});"), 4)
            self.assertIn("'^Reconfigured", text)
            self.assertNotIn("systemctl", text)
            self.assertNotIn("bgp_local_pref =", text)

    def test_restore_uses_original_hash_stat_and_bytes(self):
        text = boundary.script("jp", restore=True)
        self.assertIn("candidate=b.read_bytes()", text)
        self.assertIn("digest(p)==", text)
        self.assertIn("metadata(p)==m", text)
        self.assertIn("os.utime(n", text)

    def test_direct_action_uses_script_file_and_counts_mutation(self):
        calls = []
        with patch.object(boundary.control.pathlib.Path, "write_text"), \
             patch.object(boundary.sweep, "az", side_effect=lambda args, label, **kw:
                          calls.append((args, kw)) or {"value": []}):
            with self.assertRaisesRegex(RuntimeError, "explicit guest completion missing"):
                boundary.invoke("eu", "unit", count=4)
        args, flags = calls[0]
        self.assertEqual(args[:4], ["vm", "run-command", "invoke", "-g"])
        self.assertTrue(args[args.index("--scripts") + 1].startswith("@"))
        self.assertTrue(flags["mutation"])
        self.assertNotIn("deployment", args)


if __name__ == "__main__":
    unittest.main()
