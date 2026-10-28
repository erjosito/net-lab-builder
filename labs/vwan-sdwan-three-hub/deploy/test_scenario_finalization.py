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
import hrp_comparison
import route_eligibility
import routing_intent
import vpn_sdwan_boundary as boundary


class ScenarioFinalizationTests(unittest.TestCase):
    def test_expired_eligibility_run_still_records_blocked_restore(self):
        self.run_expired(route_eligibility, "eligibility-verdict.json")

    def test_expired_hrp_run_still_records_blocked_restore(self):
        self.run_expired(hrp_comparison, "comparison-verdict.json")

    def run_expired(self, module, verdict_name):
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
            baseline = dict(verdict="PASS", rows=[], stable=True)
            stack.enter_context(patch.object(control, "ROOT", root / "deploy"))
            stack.enter_context(patch.object(control, "RUNTIME", runtime))
            stack.enter_context(patch.object(control, "LEASE", lease_path))
            stack.enter_context(patch.object(
                control, "guard", side_effect=[
                    lease, lease, RuntimeError("Lease stopped or expired")]))
            stack.enter_context(patch.object(control, "account_id", return_value="test-sub"))
            stack.enter_context(patch.object(sweep, "OUT", root))
            stack.enter_context(patch.object(sweep, "CURRENT", root))
            stack.enter_context(patch.object(sweep, "SUB", None))
            stack.enter_context(patch.object(sweep, "RESTORING", False))
            stack.enter_context(patch.object(sweep, "RESTORE_DEADLINE", None))
            stack.enter_context(patch.object(boundary, "BASE", {}))
            stack.enter_context(patch.object(boundary, "invoke_all", return_value=before))
            stack.enter_context(patch.object(sweep, "reserve_restore"))

            def expire(*args, **kwargs):
                control.save(lease_path, dict(lease, state="blocked",
                                             failure="Lease stopped or expired"))
                raise RuntimeError("Lease stopped or expired")

            capture = stack.enter_context(patch.object(
                sweep, "capture", side_effect=[baseline, RuntimeError("Lease stopped or expired")]))
            def invoke_guest(*args, **kwargs):
                return expire() if kwargs.get("restore") else before["eu"]

            invoke = stack.enter_context(patch.object(
                boundary, "invoke", side_effect=invoke_guest))
            stack.enter_context(patch("sys.argv", [
                module.__name__, "--lease", "test.json", "--out", "scenario"]))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                module.main()
            verdict = json.loads((root / "show-output" / "scenario" / verdict_name).read_text())
            self.assertEqual(verdict["verdict"], "BLOCKED")
            self.assertFalse(verdict["restored"])
            self.assertTrue(any(e.startswith("RESTORE:") for e in verdict["errors"]))
            self.assertEqual(json.loads(lease_path.read_text())["state"], "blocked")
            self.assertEqual(capture.call_count, 2)
            self.assertEqual(invoke.call_count, 2)

    def test_unstable_restored_routes_are_not_accepted(self):
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
            baseline = dict(verdict="PASS", rows=[], stable=True)
            unstable = dict(baseline, verdict="INCONCLUSIVE", stable=False)
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
            stack.enter_context(patch.object(boundary, "invoke", return_value=before["jp"]))
            stack.enter_context(patch.object(sweep, "reserve_restore"))
            stack.enter_context(patch.object(sweep, "capture", side_effect=[
                baseline, copy.deepcopy(baseline), unstable]))
            stack.enter_context(patch("sys.argv", [
                "route_eligibility", "--lease", "test.json", "--out", "scenario"]))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                route_eligibility.main()
            verdict = json.loads((root / "show-output" / "scenario" /
                                  "eligibility-verdict.json").read_text())
            self.assertEqual(verdict["verdict"], "BLOCKED")
            self.assertFalse(verdict["restored"])

    def test_expired_routing_intent_run_still_records_blocked(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = pathlib.Path(temp)
            runtime = root / "deploy" / ".runtime-control"
            runtime.mkdir(parents=True)
            lease_path = runtime / "test.json"
            lease = dict(state="blocked", toolCallsUsed=1, mutationsUsed=0)
            control.save(lease_path, lease)
            for obj, name, value in (
                (control, "ROOT", root / "deploy"), (control, "RUNTIME", runtime),
                (control, "LEASE", lease_path), (sweep, "OUT", root),
                (sweep, "CURRENT", root), (sweep, "SUB", None),
            ):
                stack.enter_context(patch.object(obj, name, value))
            stack.enter_context(patch.object(control, "guard", side_effect=[
                dict(state="active", toolCallsUsed=0, mutationsUsed=0),
                RuntimeError("Lease stopped or expired")]))
            stack.enter_context(patch.object(control, "account_id", return_value="test-sub"))
            stack.enter_context(patch.object(sweep, "hub_metadata",
                                             side_effect=RuntimeError("Lease stopped or expired")))
            stack.enter_context(patch("sys.argv", [
                "routing_intent", "--lease", "test.json", "--out", "scenario"]))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                routing_intent.main()
            verdict = json.loads((root / "show-output" / "scenario" /
                                  "deployment-verdict.json").read_text())
            self.assertEqual(verdict["verdict"], "BLOCKED")
            self.assertFalse(verdict["retainedForTesting"])
            self.assertEqual(json.loads(lease_path.read_text())["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
