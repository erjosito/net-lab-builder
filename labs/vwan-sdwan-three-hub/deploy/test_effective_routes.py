import copy
import datetime as dt
import pathlib
import unittest
from unittest.mock import patch

import aspath_sweep
import effective_routes


class EffectiveRouteTests(unittest.TestCase):
    def test_actual_arm_ids_and_completed_response(self):
        for connection in (True, False):
            calls = []
            def az(args, label):
                calls.append(args)
                return {"value": []}
            self.assertEqual(effective_routes.collect(az, "sub", "rg", "jp", "test", connection), {"value": []})
            resource = calls[0][calls[0].index("--resource-id") + 1]
            self.assertTrue(resource.startswith("/subscriptions/"))
            self.assertNotIn("https", resource)
        with self.assertRaises(RuntimeError):
            effective_routes.collect(lambda *args: None, "sub", "rg", "jp", "empty")

    def test_two_full_snapshots_at_least_120_seconds_apart(self):
        elapsed, observations = [0], []
        def capture(number):
            observations.append((number, elapsed[0]))
            elapsed[0] += 42
            return [{"observer": s, "prefix": p} for s in aspath_sweep.SITES for p in aspath_sweep.PREFIXES]
        def wait(seconds):
            elapsed[0] += seconds
        first, second = effective_routes.two_snapshots(capture, wait, lambda: elapsed[0])
        self.assertEqual((len(first), len(second)), (12, 12))
        self.assertGreaterEqual(observations[1][1] - observations[0][1], 120)

    def test_firewall_resource_type_and_arm_id(self):
        calls = []
        firewall = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/azureFirewalls/fw-jp"
        effective_routes.collect(lambda args, label: calls.append(args) or {"value": []},
                                 "sub", "rg", "jp", "secured", firewall_id=firewall)
        self.assertEqual(calls[0][calls[0].index("--resource-id") + 1], firewall)
        self.assertEqual(calls[0][calls[0].index("--resource-type") + 1], "AzureFirewall")
        with self.assertRaises(ValueError):
            effective_routes.collect(None, "sub", "rg", "jp", "invalid",
                                     firewall_id="https://management.azure.com" + firewall)

    def test_capture_does_not_query_stalling_default_tables(self):
        rows = {"value": [{"addressPrefixes": [p]} for p in aspath_sweep.PREFIXES]}
        with patch.object(aspath_sweep, "hub_metadata", return_value={}), \
             patch.object(aspath_sweep, "save"), \
             patch.object(aspath_sweep.pathlib.Path, "mkdir"), \
             patch.object(aspath_sweep, "bounded_wait"), \
             patch.object(effective_routes, "collect", return_value=rows) as collect:
            self.assertEqual(aspath_sweep.capture("unit", 0)["verdict"], "PASS")
            self.assertEqual(collect.call_count, 6)
            self.assertTrue(all(len(c.args) == 5 for c in collect.call_args_list))

    def test_only_prepend_export_changes(self):
        for count in range(1, 9):
            script = aspath_sweep.modify_script(count)
            self.assertEqual(script.count("bgp_path.prepend(65013);"), count)
            self.assertNotIn("bgp_local_pref =", script)
            self.assertNotIn("systemctl", script)
            self.assertIn("bird -p -c", script)
            self.assertIn("birdc configure", script)
            self.assertIn("cp -p", script)
            self.assertNotIn("install -m 640", script)
            self.assertIn("grep -q '^Reconfigured'", script)

    def test_hub_properties_not_reset(self):
        original = {"name": "hub-jp", "location": "japaneast", "tags": {"lab": "true"},
                    "properties": {"addressPrefix": "10.0.0.0/23", "routeTable": {"routes": []},
                                   "virtualWan": {"id": "/wan"}, "hubRoutingPreference": "ExpressRoute",
                                   "virtualRouterIps": ["1"], "provisioningState": "Succeeded"}}
        before = copy.deepcopy(original)
        result = aspath_sweep.hub_resource(original)
        self.assertEqual(original, before)
        self.assertEqual(result["properties"]["routeTable"], original["properties"]["routeTable"])
        self.assertEqual(result["properties"]["hubRoutingPreference"], "ASPath")
        self.assertNotIn("virtualRouterIps", result["properties"])

    def test_baseline_collectors_use_shared_arm_id_helper_and_two_connections(self):
        root = pathlib.Path(__file__).parent
        for name in ("baseline.py", "baseline_finish.py"):
            text = (root / name).read_text()
            self.assertIn("effective_routes.collect(", text)
            self.assertIn('"snapshot1", True', text)
            self.assertIn('"snapshot2", True', text)
            self.assertNotIn('"--resource-id", resource', text)

    def test_source_dependencies_use_separate_child_resource_names(self):
        templates = []
        with patch.object(aspath_sweep, "submit", side_effect=lambda document, *args: templates.append(document)), \
             patch.object(aspath_sweep, "rest", side_effect=RuntimeError("stop before output read")):
            with self.assertRaises(RuntimeError):
                aspath_sweep.source("unit")
        dependency = templates[0]["resources"][1]["dependsOn"][0]
        self.assertEqual(dependency,
                         "[resourceId('Microsoft.Compute/virtualMachines/runCommands', 'router-jp', 'guest-aspath-unit-a')]")
        self.assertTrue(all(x["type"] == "secureString" for x in templates[0]["parameters"].values()))

    def test_step_reserves_full_restore_window(self):
        lease = {"expiresAtUtc": "2026-10-14T19:26:00Z", "restoreTimeoutMinutes": 15}
        aspath_sweep.reserve_restore(lease, dt.datetime(2026, 10, 14, 19, 0, tzinfo=dt.timezone.utc))
        with self.assertRaises(RuntimeError):
            aspath_sweep.reserve_restore(lease, dt.datetime(2026, 10, 14, 19, 2, tzinfo=dt.timezone.utc))

    def test_duplicate_prefixes_cannot_prove_twelve_winners(self):
        rows = [{"observer": s, "prefix": p} for s in aspath_sweep.SITES for p in aspath_sweep.PREFIXES]
        self.assertTrue(aspath_sweep.complete_rows(rows))
        rows[1] = rows[0].copy()
        self.assertFalse(aspath_sweep.complete_rows(rows))

    def test_actual_full_hub_and_ri_gets_required_each_state(self):
        calls, saved = [], {}
        def rest(url, label):
            calls.append(url)
            if url.endswith("/routingIntent"):
                return {"value": []}
            return {"properties": {"hubRoutingPreference": "ASPath", "unrelated": {"preserved": True}}}
        with patch.object(aspath_sweep, "rest", side_effect=rest), \
             patch.object(aspath_sweep, "save", side_effect=lambda n, v: saved.update({n: v})):
            observed = aspath_sweep.hub_metadata()
            self.assertEqual(len(calls), 6)
            self.assertEqual(set(observed), set(aspath_sweep.SITES))
            self.assertTrue(observed["jp"]["hub"]["properties"]["unrelated"]["preserved"])
            self.assertIn("expected", saved["hub-metadata.json"])
        for bad in ({"properties": {"hubRoutingPreference": "VPN"}}, {},
                    {"value": [{"name": "intent"}]}):
            with patch.object(aspath_sweep, "rest", return_value=bad), \
                 patch.object(aspath_sweep, "save"), self.assertRaises(RuntimeError):
                aspath_sweep.hub_metadata()

    def test_metadata_mismatch_prevents_effective_route_collection(self):
        with patch.object(aspath_sweep, "hub_metadata", side_effect=RuntimeError("mismatch")), \
             patch.object(effective_routes, "collect") as collect, \
             patch.object(aspath_sweep.pathlib.Path, "mkdir"):
            with self.assertRaises(RuntimeError):
                aspath_sweep.capture("unit", 4)
            collect.assert_not_called()

    def test_withdrawal_exemption_only_jp_cn(self):
        rows = [{"observer": s, "prefix": p} for s in aspath_sweep.SITES for p in aspath_sweep.PREFIXES]
        rows = [r for r in rows if not (r["observer"] == "jp" and r["prefix"] == "10.140.0.0/24")]
        self.assertTrue(aspath_sweep.complete_rows(rows, True))
        self.assertFalse(aspath_sweep.complete_rows(rows))
        rows.pop(0)
        self.assertFalse(aspath_sweep.complete_rows(rows, True))
        script = aspath_sweep.modify_script(0, True)
        self.assertIn("if net = 10.140.0.0/24 then reject;", script)
        self.assertNotIn("filter mesh_export", script)
        self.assertNotIn("systemctl", script)

    def test_boundary_reuses_managed_command_slots(self):
        templates = []
        with patch.object(aspath_sweep, "REUSE_COMMANDS", True), \
             patch.object(aspath_sweep, "submit", side_effect=lambda document, *args: templates.append(document)), \
             patch.object(aspath_sweep, "rest", side_effect=RuntimeError("stop before output")):
            for label in ("4", "8", "restore-final"):
                with self.assertRaises(RuntimeError):
                    aspath_sweep.source(label)
        self.assertEqual(len({tuple(r["name"] for r in d["resources"]) for d in templates}), 1)


if __name__ == "__main__":
    unittest.main()
