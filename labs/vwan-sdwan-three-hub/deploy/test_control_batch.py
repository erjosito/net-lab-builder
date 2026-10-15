import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

import control


class BatchTests(unittest.TestCase):
    def test_processes_start_before_collection_and_reserve_calls_once(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = pathlib.Path(temp)
            lease = {"toolCallsUsed": 0, "maxToolCalls": 10, "commandTimeoutSeconds": 300,
                     "expiresAtUtc": "2099-01-01T00:00:00Z"}
            first, second = Mock(pid=1, returncode=0), Mock(pid=2, returncode=0)
            events = []
            for p in (first, second):
                p.communicate.side_effect = lambda **kw: events.append("read") or (b'{"value":[]}', b"")
                p.poll.return_value = 0
            def spawn(*args, **kwargs):
                events.append("spawn")
                return first if events.count("spawn") == 1 else second
            with patch.object(control, "RUNTIME", runtime), \
                 patch.object(control, "LEASE", runtime / "lease.json"), \
                 patch.object(control, "guard", return_value=lease), \
                 patch.object(control.shutil, "which", return_value="az"), \
                 patch.object(control.subprocess, "Popen", side_effect=spawn):
                result = control.az_batch([(["account", "show"], "one"),
                                           (["account", "show"], "two")])
            self.assertEqual(result, [{"value": []}, {"value": []}])
            self.assertEqual(events[:2], ["spawn", "spawn"])
            self.assertEqual(lease["toolCallsUsed"], 2)
            self.assertEqual(json.loads((runtime / "child-process.json").read_text())["children"], [])

    def test_budget_or_duplicate_labels_prevent_spawning(self):
        lease = {"toolCallsUsed": 9, "maxToolCalls": 10}
        with patch.object(control, "guard", return_value=lease), \
             patch.object(control.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "absolute call budget"):
                control.az_batch([([], "one"), ([], "two")])
            with self.assertRaises(ValueError):
                control.az_batch([([], "same"), ([], "same")])
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
