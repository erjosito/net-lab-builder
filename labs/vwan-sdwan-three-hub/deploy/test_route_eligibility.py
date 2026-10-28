import contextlib
import copy
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import aspath_sweep as sweep
import control
import route_eligibility
import vpn_sdwan_boundary as boundary


class TransitEligibilityTests(unittest.TestCase):
    def test_transit_control_and_original_flag_restore(self):
        for canonical in (False, True):
            for incorrect_restore, accepted in ((False, True), (True, True), (False, False)):
                with self.subTest(incorrect_restore=incorrect_restore, accepted=accepted,
                                  canonical=canonical):
                    self.run_control(incorrect_restore, accepted, canonical)

    def test_unaccepted_labels_prevent_withdrawal(self):
        self.run_control(False, True, True, "normalized")

    def test_unrestored_labels_block_completion(self):
        self.run_control(False, True, True, "restored")

    def run_control(self, incorrect_restore, accepted, canonical, incorrect_labels=None):
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = pathlib.Path(temp)
            runtime = root / "deploy" / ".runtime-control"
            runtime.mkdir(parents=True)
            lease_path = runtime / "test.json"
            lease = dict(state="active", toolCallsUsed=0, mutationsUsed=0)
            control.save(lease_path, lease)
            before = {site: dict(sha256=site, stat={}, exports={},
                                 protocols={}, ikeEstablished=None)
                      for site in ("eu", "us", "jp", "cn")}
            local = dict(observer="jp", prefix="10.140.0.0/24",
                         nextHopType="VPN_S2S_Gateway", nextHops=["local"],
                         origin="local")
            remote = dict(local, nextHopType="Remote Hub", nextHops=["remote"],
                          origin="remote")
            hubs = [dict(name="hub-" + site, location="test",
                         properties=dict(allowBranchToBranchTraffic=False,
                                         hubRoutingPreference="ASPath"))
                    for site in sweep.SITES]
            routing = []
            for site in sweep.SITES:
                names = ["conn-spoke-" + site]
                if site != "jp":
                    names.append("conn-transit-" + site)
                routing.append({"value": [
                    dict(name=name, id="hub-" + site + "/" + name,
                         properties={"routingConfiguration": {
                             "associatedRouteTable": {"id": "table-" + site},
                             "propagatedRouteTables": {"labels": ["Default"], "ids": []}}})
                    for name in names]})
            routing.append(copy.deepcopy(routing[2]["value"][0]["properties"]
                                         ["routingConfiguration"]))
            normalized = copy.deepcopy(routing)
            for value in normalized[:3]:
                for connection in value["value"]:
                    connection["properties"]["routingConfiguration"][
                        "propagatedRouteTables"]["labels"] = ["default"]
            normalized[3]["propagatedRouteTables"]["labels"] = ["default"]
            restored_routing = copy.deepcopy(routing)
            if incorrect_labels == "normalized":
                normalized[0]["value"][0]["properties"]["routingConfiguration"][
                    "propagatedRouteTables"]["labels"] = ["Default"]
            if incorrect_labels == "restored":
                restored_routing[0]["value"][0]["properties"]["routingConfiguration"][
                    "propagatedRouteTables"]["labels"] = ["default"]

            def capture(label, *args, **kwargs):
                sweep.CURRENT = sweep.OUT / label
                sweep.CURRENT.mkdir(parents=True, exist_ok=True)
                enabled = (label == "transit-enabled" and accepted) or (
                    label == "restore" and incorrect_restore)
                control.save(sweep.CURRENT / "hub-metadata.json", {
                    "observed": {site: {"hub": {"properties": {
                        "allowBranchToBranchTraffic": enabled}}}
                        for site in sweep.SITES}})
                return dict(verdict="PASS", stable=True,
                            rows=[copy.deepcopy(remote if label == "withdraw-cn-jp" else local)])

            for obj, name, value in (
                (control, "ROOT", root / "deploy"), (control, "RUNTIME", runtime),
                (control, "LEASE", lease_path), (sweep, "OUT", root),
                (sweep, "CURRENT", root), (sweep, "SUB", None),
                (sweep, "RESTORING", False), (sweep, "RESTORE_DEADLINE", None),
                (boundary, "BASE", {}),
            ):
                stack.enter_context(patch.object(obj, name, value))
            stack.enter_context(patch.object(control, "guard", return_value=lease))
            stack.enter_context(patch.object(control, "account_id", return_value="test-sub"))
            stack.enter_context(patch.object(boundary, "invoke_all", return_value=before))
            invoke = stack.enter_context(patch.object(
                boundary, "invoke", return_value=before["jp"]))
            stack.enter_context(patch.object(sweep, "reserve_restore"))
            stack.enter_context(patch.object(sweep, "capture", side_effect=capture))
            if canonical:
                stack.enter_context(patch.object(
                    sweep, "az_batch", side_effect=[hubs, routing, normalized, restored_routing]))
            else:
                stack.enter_context(patch.object(sweep, "az_batch", return_value=hubs))
            vpn = stack.enter_context(patch.object(route_eligibility.propagation, "vpn_labels"))
            submit = stack.enter_context(patch.object(sweep, "submit"))
            arguments = [
                "route_eligibility", "--lease", "test.json", "--out", "scenario",
                "--enable-hub-transit"]
            if canonical:
                arguments.append("--canonical-labels")
            stack.enter_context(patch("sys.argv", arguments))
            output = io.StringIO()
            blocked = incorrect_restore or incorrect_labels == "restored"
            accepted_control = accepted and incorrect_labels != "normalized"
            with contextlib.redirect_stdout(output):
                if blocked or not accepted_control:
                    with self.assertRaises(SystemExit):
                        route_eligibility.main()
                else:
                    try:
                        route_eligibility.main()
                    except SystemExit:
                        self.fail(output.getvalue())
            verdict = json.loads((root / "show-output" / "scenario" /
                                  "eligibility-verdict.json").read_text())
            expected = "BLOCKED" if blocked else "PASS" if accepted_control else "INCONCLUSIVE"
            self.assertEqual(verdict["verdict"], expected,
                             verdict["errors"])
            self.assertEqual(verdict["restored"], not blocked)
            self.assertEqual(verdict["remoteCNEligible"],
                             True if accepted_control and not blocked else None)
            self.assertEqual(invoke.call_count, 2 if accepted_control else 0)
            self.assertEqual(vpn.call_count, 2 if canonical else 0)
            if canonical:
                self.assertEqual(vpn.call_args_list[0].args[0], ["default"])
                self.assertEqual(vpn.call_args_list[1].args[0], ["Default"])
            self.assertEqual(submit.call_count, 2)
            for call, expected in zip(submit.call_args_list, (True, False)):
                resources = call.args[0]["resources"]
                self.assertEqual(len(resources), 8 if canonical else 3)
                self.assertTrue(all(r["properties"]["allowBranchToBranchTraffic"] is expected
                                    for r in resources if r["type"] == "Microsoft.Network/virtualHubs"))
                for resource in resources:
                    if resource["type"].endswith("/hubVirtualNetworkConnections"):
                        hub = resource["name"].split("/")[0]
                        self.assertIn(route_eligibility.infra.rid("virtualHubs", hub),
                                      resource["dependsOn"])


if __name__ == "__main__":
    unittest.main()
