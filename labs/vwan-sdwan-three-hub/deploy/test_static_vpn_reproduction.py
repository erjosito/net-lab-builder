import ast
import contextlib
import copy
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import static_vpn_reproduction as scenario
import aspath_sweep as sweep


class StaticVpnTests(unittest.TestCase):
    def test_only_target_injected_and_both_export_filters_changed(self):
        for prepends in (0, 3):
            changes, addition = scenario.config_changes("eu", prepends)
            self.assertEqual(len(changes), 2)
            self.assertEqual(changes[0][1].count("bgp_path.prepend(65011);"), prepends)
            self.assertIn("if net = " + scenario.TARGET, changes[0][1])
            self.assertIn("if net = " + scenario.TARGET, changes[1][1])
            self.assertIn("blackhole", addition)
            self.assertNotIn("bgp_local_pref", addition)
            original = sweep.FILTER + "\n    export filter {\n"
            for search, replacement in changes:
                self.assertEqual(original.count(search), 1)
                original = original.replace(search, replacement, 1)
            self.assertIn(sweep.FILTER.splitlines()[1], original)

    def test_japan_routes_are_static_tunnel_routes_without_ipsec_changes(self):
        changes, addition = scenario.config_changes("jp")
        self.assertEqual(changes, [])
        for prefix in ("10.10.0.0/24", "10.20.0.0/24", "10.30.0.0/24"):
            self.assertIn(f'route {prefix} via "xfrm41";', addition)
        for forbidden in ("sharedKey", "swanctl", "systemctl", "azure_export"):
            self.assertNotIn(forbidden, addition)

    def test_generated_guest_python_parses_and_preserves_exact_restore(self):
        for site in ("eu", "jp"):
            for restore in (False, True):
                text = scenario.guest_script(site, {"sha256": "original", "stat": {}},
                                             prepends=3, restore=restore)
                python = text.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
                ast.parse(python, feature_version=(3, 10))
                self.assertLess(text.index("os.chown(n"), text.index("os.replace(n,p)"))
                self.assertIn("digest(b)==original_sha", text)
                self.assertIn("metadata(p)==original_stat", text)
                self.assertIn("len(payload.encode())<3500", text)
                self.assertIn("targetAddressPresent=present", text)
                self.assertNotIn("swanctl','--load", text)

    def test_complete_guest_marker_required(self):
        with self.assertRaisesRegex(RuntimeError, "explicit complete"):
            scenario.completed({"value": [{"message": "done"}]}, "STATIC_VPN_COMPLETE")
        value = {"value": [{"message": "STATIC_VPN_COMPLETE " + json.dumps({"done": True})}]}
        self.assertEqual(scenario.completed(value, "STATIC_VPN_COMPLETE"), {"done": True})

    def test_remote_route_requires_exact_japan_identity(self):
        self.assertTrue(scenario.is_remote_vpn({"origin": "/vpnGateways/vpngw-jp"}))
        self.assertTrue(scenario.is_remote_vpn(
            {"nextHopType": "Remote Hub", "nextHops": ["/virtualHubs/hub-jp"]}))
        self.assertFalse(scenario.is_remote_vpn(
            {"nextHopType": "HubBgpConnection", "origin": "/virtualHubs/hub-eu"}))
        self.assertFalse(scenario.is_remote_vpn({"nextHopType": "Remote Hub"}))

    def test_injection_needs_real_blackhole_and_both_actual_export_paths(self):
        for prepends in (0, 3):
            result = {"routes": [{"dst": scenario.TARGET, "type": "blackhole"}],
                      "exports": {p: {scenario.TARGET: [65011] * prepends}
                                  for p in ("azure_0", "azure_1")}}
            scenario.validate_injection(result, prepends)
            with self.assertRaisesRegex(RuntimeError, "AS path"):
                scenario.validate_injection(result, 3 if prepends == 0 else 0)
            result["routes"] = []
            with self.assertRaisesRegex(RuntimeError, "kernel FIB"):
                scenario.validate_injection(result, prepends)

    def test_failures_restore_without_running_unproven_injection(self):
        for failed in (None, "eligibility", "traffic", "restore"):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp, \
                    contextlib.ExitStack() as stack:
                root = pathlib.Path(temp)
                runtime = root / "deploy" / ".runtime-control"
                runtime.mkdir(parents=True)
                lease = dict(toolCallsUsed=0, mutationsUsed=0, restoreTimeoutMinutes=20)
                lease_path = runtime / "test.json"
                lease_path.write_text(json.dumps(lease))
                source = {s: dict(sha256=s, stat={}, protocols={}, exports={}, ikeEstablished=None)
                          for s in (*sweep.SITES, "cn")}
                proof = root / "verified.json"
                proof.write_text(json.dumps(dict(verdict="PASS", baselineVerified=True, sourceProofs=source)))
                settings = [None, dict(links=[dict(name="link-jp", bgp=True)], routing={})]
                static = copy.deepcopy(settings)
                static[0] = {"addressPrefixes": [scenario.TARGET]}
                static[1]["links"][0]["bgp"] = False
                for obj, key, value in (
                    (scenario.control, "ROOT", root / "deploy"),
                    (scenario.control, "RUNTIME", runtime),
                    (scenario.control, "LEASE", lease_path),
                    (sweep, "OUT", root), (sweep, "CURRENT", root),
                    (sweep, "SUB", "unit"), (sweep, "RESTORING", False),
                    (sweep, "RESTORE_DEADLINE", None), (scenario.boundary, "BASE", {})
                ):
                    stack.enter_context(patch.object(obj, key, value))
                stack.enter_context(patch.object(scenario.control, "guard", return_value=lease))
                stack.enter_context(patch.object(scenario.control, "account_id", return_value="unit"))
                stack.enter_context(patch.object(sweep, "az", return_value=scenario.control.TAGS))
                stack.enter_context(patch.object(sweep, "hub_metadata"))
                stack.enter_context(patch.object(scenario.boundary, "invoke_all", return_value=source))
                stack.enter_context(patch.object(sweep, "capture",
                    return_value=dict(verdict="PASS", rows=[])))
                stack.enter_context(patch.object(scenario, "require_target_absent"))
                stack.enter_context(patch.object(sweep, "reserve_restore"))
                stack.enter_context(patch.object(sweep, "bounded_wait"))
                stack.enter_context(patch.object(scenario, "read_settings",
                    side_effect=[settings, static, settings]))
                bgp = stack.enter_context(patch.object(scenario, "set_bgp"))
                def mutate(site, *args, **kwargs):
                    if failed == "restore" and kwargs.get("restore"):
                        raise RuntimeError("restore rejected")
                    return {}
                mutation = stack.enter_context(patch.object(scenario, "mutate_guest", side_effect=mutate))
                stack.enter_context(patch.object(scenario, "collect_target", return_value=dict(
                    stable=True, complete=failed != "eligibility",
                    rows=[dict(observer=s, origin="/vpnGateways/vpngw-jp",
                               nextHopType="VPN_S2S_Gateway") for s in sweep.SITES])))
                stack.enter_context(patch.object(scenario, "probe_target", return_value=[
                    dict(source=source, destination=scenario.ADDRESS,
                         tcp="FAIL" if failed == "traffic" else "PASS", icmp="PASS")
                    for source in scenario.SOURCE_PROBES.values()]))
                stack.enter_context(patch("sys.argv", [
                    "scenario", "--lease", "test.json", "--out", "unit",
                    "--baseline-proof", str(proof)]))
                with contextlib.redirect_stdout(io.StringIO()):
                    if failed:
                        with self.assertRaises(SystemExit):
                            scenario.main()
                    else:
                        scenario.main()
                verdict = json.loads((root / "show-output" / "unit" / "reproduction-verdict.json").read_text())
                self.assertEqual(verdict["verdict"], "PASS" if failed is None else
                                 "BLOCKED" if failed == "restore" else "INCONCLUSIVE")
                self.assertEqual(verdict["restored"], failed != "restore")
                if failed in ("eligibility", "traffic"):
                    self.assertFalse(any(c.args[0] == "eu" for c in mutation.call_args_list))
                if failed != "restore":
                    self.assertEqual([c.args[0] for c in bgp.call_args_list], [False, True])


if __name__ == "__main__":
    unittest.main()
