import ipaddress
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from execute import API, Executor, Gate, Job, PAIRS, PREFIXES, ROOT, SUBNETS


class ContractTests(unittest.TestCase):
    def test_exact_inventory(self):
        self.assertEqual(len(PREFIXES), 3)
        self.assertEqual(sum(map(len, SUBNETS.values())), 5)
        self.assertEqual(len(PAIRS), 4)
        self.assertEqual(PREFIXES["spoke2"], ["10.20.0.0/26", "192.168.0.0/16"])
        self.assertEqual(SUBNETS["spoke2"]["spoke10"], "10.20.0.0/27")
        self.assertTrue((ROOT / ".squad" / "live-lab-policy.md").is_file())

    def test_selected_and_excluded_ranges(self):
        parents = [ipaddress.ip_network(prefixes[0]) for prefixes in PREFIXES.values()]
        self.assertFalse(any(a.overlaps(b) for i, a in enumerate(parents) for b in parents[i + 1:]))
        for spoke in ("spoke1", "spoke2"):
            self.assertIn("192.168.0.0/16", PREFIXES[spoke])
            self.assertEqual(SUBNETS[spoke]["isolated192"], "192.168.1.0/24")
        for local, _, remote, local_names, remote_names in PAIRS:
            self.assertNotEqual(local, remote)
            self.assertNotIn("isolated192", local_names + remote_names)

    def test_absence_requires_service_not_found(self):
        self.assertTrue(Executor.absent({"exitCode": 1, "stderr": "(ResourceGroupNotFound) missing"}))
        self.assertFalse(Executor.absent({"exitCode": 1, "stderr": "(AuthorizationFailed) denied"}))
        self.assertFalse(Executor.absent({"exitCode": 0, "stderr": ""}))

    def test_parent_api_gate_passes_without_child_metadata(self):
        provider = {"registrationState": "Registered", "resourceTypes": [
            {"resourceType": "ViRtUaLnEtWoRkS", "apiVersions": [API]}]}
        Executor.provider_gate(provider)

    def test_parent_api_gate_requires_registered_and_pinned_parent(self):
        for state, types in (
                ("NotRegistered", [{"resourceType": "virtualNetworks", "apiVersions": [API]}]),
                ("Registered", [{"resourceType": "virtualNetworks", "apiVersions": ["2025-01-01"]}]),
                ("Registered", [{"resourceType": "virtualNetworks/virtualNetworkPeerings", "apiVersions": [API]}])):
            with self.subTest(state=state, types=types), self.assertRaises(Gate):
                Executor.provider_gate({"registrationState": state, "resourceTypes": types})

    def test_job_close_terminates_and_reaps_specific_child(self):
        job = Job()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            job.assign(child)
        finally:
            job.close()
            if child.poll() is None:
                child.wait(timeout=10)
            child.communicate(timeout=10)
        self.assertIsNotNone(child.returncode)

class RetentionTests(unittest.TestCase):
    def lease(self, retained=True):
        result = {
            "state": "ready", "taskId": "test-retained", "sentinelPath": "unused",
            "expiresAtUtc": "2099-01-01T00:00:00Z",
            "deploymentApproval": "Explicit redeploy and retain authorization",
            "cleanupApproval": False if retained else "Explicit scoped cleanup approval",
            "restoreTimeoutMinutes": 0 if retained else 10,
        }
        if retained:
            result["retentionPolicy"] = "keep_until_explicit_user_cleanup"
        return result

    def executor(self, retained=True):
        executor = Executor.__new__(Executor)
        executor.lease = self.lease(retained)
        executor.retained = Executor.retention_gate(executor.lease)
        executor.save = Mock()
        executor.persist = Mock()
        executor.checkpoint = Mock()
        executor.restore = Mock(return_value=True)
        executor.out = Path(".")
        executor.active, executor.pids = set(), []
        executor.rg_attempted = executor.baseline_absent = True
        executor.verdict, executor.reason = "PASS", "Test deployment"
        executor.writes, executor.batches, executor.commands = 8, {1, 2, 3, 4}, 25
        return executor

    def test_retained_success_and_failure_never_cleanup(self):
        for error in (None, Gate("BLOCKED", "Partial PUT failed"), RuntimeError("Unexpected failure")):
            with self.subTest(error=error):
                executor = self.executor()
                executor.experiment = Mock(side_effect=error)
                with patch("execute.ROOT") as root, patch("builtins.print"):
                    (root / "unused").exists.return_value = False
                    executor.run()
                executor.restore.assert_not_called()
                retention = next(call.args[1] for call in executor.save.call_args_list
                                 if call.args[0] == "retention.json")
                self.assertEqual(retention["deleteSubmissions"], 0)
                self.assertFalse(retention["deletionAuthorized"])
                self.assertEqual(executor.persist.call_args.kwargs["state"],
                                 "completed" if error is None else "blocked")
                self.assertTrue(executor.persist.call_args.kwargs["resourcesRetained"])

    def test_original_approved_cleanup_still_runs(self):
        executor = self.executor(retained=False)
        executor.experiment = Mock()
        with patch("execute.ROOT") as root, patch("builtins.print"):
            (root / "unused").exists.return_value = False
            executor.run()
        executor.restore.assert_called_once_with()
        self.assertEqual(executor.persist.call_args.kwargs["state"], "rolled-back")

    def test_retained_delete_dispatch_and_direct_restore_fail_closed(self):
        executor = self.executor()
        del executor.restore
        with patch("execute.LEASE") as lease, patch("execute.subprocess.Popen") as spawn:
            lease.read_text.return_value = json.dumps(executor.lease)
            with self.assertRaises(Gate):
                executor.command("delete-rg", ["rest", "--method", "DELETE", "--url", "unused"])
            with self.assertRaises(Gate):
                executor.restore()
            spawn.assert_not_called()

    def test_contradictory_retention_cleanup_leases_are_rejected(self):
        for field, value in (("cleanupApproval", "Old approval"), ("restoreTimeoutMinutes", 10),
                             ("retentionPolicy", "unknown")):
            lease = self.lease()
            lease[field] = value
            with self.subTest(field=field), self.assertRaises(Gate):
                Executor.retention_gate(lease)

    def test_retention_cannot_be_removed_during_run(self):
        executor = self.executor()
        with patch("execute.LEASE") as lease:
            lease.read_text.return_value = json.dumps(self.lease(retained=False))
            with self.assertRaisesRegex(Gate, "retention policy changed"):
                executor.check()


if __name__ == "__main__":
    unittest.main()
