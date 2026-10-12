"""Pure unit tests; no CLI, cloud, guest, or filesystem writes."""
import ast
import datetime as dt
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import collect
import runtime
import setup


class OfflineTests(unittest.TestCase):
    def test_compile(self):
        for file in Path(__file__).parent.glob("*.py"):
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))

    def test_guest_policy_local_gateway_and_inverse(self):
        for role in setup.VM:
            for action in ("policy-default", "policy-workload", "policy-source", "policy-peer"):
                _, _, _, forward, inverse = setup.guest_item(role + "-" + action)
                self.assertNotIn("onlink", forward)
                self.assertNotIn("/16", forward)
                self.assertIn("4242", forward)
                self.assertIn(" del ", inverse)
            for action in ("nat-forward", "nat-return"):
                _, _, _, forward, inverse = setup.guest_item(role + "-" + action)
                self.assertIn("-I POSTROUTING 1", forward)
                self.assertIn("-D POSTROUTING", inverse)
                self.assertNotIn("MASQUERADE", forward)

    def test_probes_and_transport(self):
        for kind in ("ping", "tcp", "mtr-icmp", "mtr-tcp", "trace-icmp", "trace-tcp", "packets"):
            command, seconds = collect.command_for(kind, "10.60.1.4", "in")
            self.assertLessEqual(seconds, 20)
            script = collect.guest_script(command, seconds, 0)
            self.assertIn("COMMAND_STATUS", script)
            self.assertIn("2800", script)
            self.assertNotIn("apt", script)
        for kind in ("mtr-icmp", "mtr-tcp"):
            command, _ = collect.command_for(kind, "10.60.1.4", "in")
            self.assertEqual(command[command.index("-c")+1], "5")
            self.assertEqual(command[command.index("--max-ttl")+1], "8")

    def test_guard_fails_closed(self):
        now = dt.datetime.now(dt.timezone.utc)
        lease = {"state": "active", "ownerRole": "Tank", "phase": "apply",
                 "taskId": "offline-test", "subscriptionId": "test",
                 "startedAtUtc": (now-dt.timedelta(seconds=10)).isoformat(),
                 "expiresAtUtc": (now+dt.timedelta(minutes=10)).isoformat(), "maxToolCalls": 30}
        r = runtime.Runtime.__new__(runtime.Runtime)
        r.owner = "Tank"
        r.args = SimpleNamespace(phase="apply")
        r.lease_path = Path("unused.json")
        r.audit = {"calls": []}
        with patch("runtime.load", return_value=lease), patch.object(Path, "exists", return_value=False):
            self.assertEqual(r.guard()["state"], "active")
            lease["state"] = "stop-requested"
            with self.assertRaises(RuntimeError):
                r.guard()
            lease["state"] = "active"
            lease["expiresAtUtc"] = (now-dt.timedelta(seconds=1)).isoformat()
            with self.assertRaises(RuntimeError):
                r.guard()

    def test_budget_rejects_before_subprocess(self):
        r = runtime.Runtime.__new__(runtime.Runtime)
        r.args = SimpleNamespace(phase="apply")
        r.audit = {"calls": [], "mutations": 3, "reserved": 3, "forward": 3}
        lease = {"allowedMutations": ["operation"], "maxMutations": 6}
        with patch.object(r, "guard", return_value=lease), patch("runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                r.command("operation", [], cost=1, inverse_cost=1)
            popen.assert_not_called()
        r.audit = {"calls": [], "mutations": 0, "reserved": 0, "forward": 0}
        lease["allowedMutations"] = []
        with patch.object(r, "guard", return_value=lease), patch("runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                r.command("operation", [], cost=1, inverse_cost=1)
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
