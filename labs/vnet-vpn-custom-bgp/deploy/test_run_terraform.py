import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import run_terraform


class LeaseGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.control = Path(self.directory.name)
        self.patch = patch.object(run_terraform, "CONTROL", self.control)
        self.patch.start()
        self.write_lease()

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def write_lease(self, *, minutes=10, state="active"):
        (self.control / "lease.json").write_text(json.dumps({
            "state": state,
            "expiresAtUtc": (
                datetime.now(timezone.utc) + timedelta(minutes=minutes)
            ).isoformat(),
        }))

    def test_active_unexpired_lease_reports_remaining_budget(self):
        self.assertGreater(run_terraform.check_lease(), 0)

    def test_expired_and_closed_leases_block_execution(self):
        for minutes, state in [(-1, "active"), (10, "rolled-back")]:
            with self.subTest(minutes=minutes, state=state):
                self.write_lease(minutes=minutes, state=state)
                with self.assertRaises(RuntimeError):
                    run_terraform.check_lease()

    def test_stop_sentinel_blocks_an_active_lease(self):
        (self.control / "STOP").touch()
        with self.assertRaises(RuntimeError):
            run_terraform.check_lease()


if __name__ == "__main__":
    unittest.main()
