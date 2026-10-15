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
        for incorrect_restore, accepted in ((False, True), (True, True), (False, False)):
            with self.subTest(incorrect_restore=incorrect_restore, accepted=accepted):
                self.run_control(incorrect_restore, accepted)

    def run_control(self, incorrect_restore, accepted):
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
            stack.enter_context(patch.object(sweep, "az_batch", return_value=hubs))
            submit = stack.enter_context(patch.object(sweep, "submit"))
            stack.enter_context(patch("sys.argv", [
                "route_eligibility", "--lease", "test.json", "--out", "scenario",
                "--enable-hub-transit"]))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                if incorrect_restore or not accepted:
                    with self.assertRaises(SystemExit):
                        route_eligibility.main()
                else:
                    try:
                        route_eligibility.main()
                    except SystemExit:
                        self.fail(output.getvalue())
            verdict = json.loads((root / "show-output" / "scenario" /
                                  "eligibility-verdict.json").read_text())
            expected = "BLOCKED" if incorrect_restore else "PASS" if accepted else "INCONCLUSIVE"
            self.assertEqual(verdict["verdict"], expected,
                             verdict["errors"])
            self.assertEqual(verdict["restored"], not incorrect_restore)
            self.assertEqual(verdict["remoteCNEligible"],
                             True if accepted and not incorrect_restore else None)
            self.assertEqual(invoke.call_count, 2 if accepted else 0)
            self.assertEqual(submit.call_count, 2)
            for call, expected in zip(submit.call_args_list, (True, False)):
                self.assertTrue(all(resource["properties"]["allowBranchToBranchTraffic"] is expected
                                    for resource in call.args[0]["resources"]))


if __name__ == "__main__":
    unittest.main()
