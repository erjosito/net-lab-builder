import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import guest
import restart_recover as recovery


class RestartRecoveryTests(unittest.TestCase):
    def test_blocked_closure_rejects_mutation_before_any_live_call(self):
        with patch.object(recovery.control, "account_id", return_value="subscription"):
            runner = recovery.Recovery(Path("."), read_only_closure=True)
        with self.assertRaisesRegex(RuntimeError, "cannot mutate"):
            runner.az(["vm", "run-command"], "forbidden", mutation=True)

    def test_read_only_script_checks_runtime_and_protected_backups_first(self):
        text = recovery.read_script("jp")
        self.assertLess(text.index("command -v"), text.index("BOUNDARY_COMPLETE"))
        self.assertIn("/var/lib/threehub/aspath-jp-baseline.conf", text)
        self.assertIn("if False:", text)
        self.assertNotIn("systemctl restart", text)

    def test_restore_requires_explicit_protected_backup_and_exact_original(self):
        original = {"sha256": "a" * 64, "stat": {"uid": 113, "gid": 122,
                                                "mode": 384, "mtimeNs": 123}}
        with self.assertRaisesRegex(RuntimeError, "Explicit protected"):
            recovery.restore_script("jp", "/other.conf", original)
        text = recovery.restore_script("jp", recovery.backup_paths("jp")[1], original)
        self.assertIn("b=Path('/var/lib/threehub/aspath-jp-baseline.conf')", text)
        self.assertIn("a" * 64, text)
        self.assertLess(text.index("os.chown(n"), text.index("os.replace(n,p)"))
        self.assertIn("candidate=b.read_bytes()", text)

    def test_actual_prepends_are_rejected_without_trusting_count_field(self):
        paths = {p: ([] if s == "jp" else [guest.ASNS[s]]) for s, p in guest.DC.items()}
        original = dict(sha256="a", stat={}, protocols={f"mesh_{i}": "Established"
                        for i in range(5)}, ikeEstablished=2,
                        exports={peer: {"routes": copy.deepcopy(paths)}
                                 for peer in ("azure_0", "azure_1")})
        self.assertEqual(recovery.baseline_errors("jp", original, original), [])
        changed = copy.deepcopy(original)
        changed["exports"]["azure_1"]["routes"][guest.DC["eu"]].insert(0, 65013)
        self.assertIn("actual two-peer exports", recovery.baseline_errors("jp", changed, original)[0])

    def test_missing_or_duplicate_completion_is_not_success(self):
        for text in ("", 'BOUNDARY_COMPLETE {}\nBOUNDARY_COMPLETE {}'):
            with self.assertRaises(RuntimeError):
                recovery.parse_marker(text, "BOUNDARY_COMPLETE")

    def test_missing_mesh_route_does_not_imply_prepend_or_configuration_change(self):
        paths = {p: ([] if s == "eu" else [guest.ASNS[s]]) for s, p in guest.DC.items()}
        original = dict(sha256="unchanged", stat={"mode": 384},
                        protocols={f"peer_{i}": "Established" for i in range(5)},
                        ikeEstablished=None,
                        exports={peer: {"routes": copy.deepcopy(paths)}
                                 for peer in ("azure_0", "azure_1")})
        actual = copy.deepcopy(original)
        actual["protocols"]["peer_0"] = "Connect"
        for export in actual["exports"].values():
            del export["routes"][guest.DC["jp"]]
        errors = recovery.baseline_errors("eu", actual, original)
        self.assertTrue(any("missing or unexpected routes" in e for e in errors))
        self.assertFalse(any("not zero prepend" in e for e in errors))
        self.assertFalse(recovery.configuration_differs(actual, original))

    def test_actual_bad_path_without_file_change_cannot_authorize_restore(self):
        original = dict(sha256="unchanged", stat={"mode": 384}, exports={})
        actual = copy.deepcopy(original)
        actual["exports"] = {"azure_0": {"routes": {guest.DC["jp"]: [65011, 65013]}}}
        self.assertFalse(recovery.configuration_differs(actual, original))
        for key, changed in (("sha256", "different"), ("stat", {"mode": 420})):
            with self.subTest(key=key):
                changed_actual = copy.deepcopy(actual)
                changed_actual[key] = changed
                self.assertTrue(recovery.configuration_differs(changed_actual, original))


if __name__ == "__main__":
    unittest.main()
