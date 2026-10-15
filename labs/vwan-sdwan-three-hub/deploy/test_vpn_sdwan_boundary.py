import unittest
from unittest.mock import patch

import vpn_sdwan_boundary as boundary


class DirectBoundaryTests(unittest.TestCase):
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
