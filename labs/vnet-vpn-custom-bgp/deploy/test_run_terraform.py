import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import run_terraform


class GcloudCommandTests(unittest.TestCase):
    def test_native_sdk_is_preferred_without_starting_wsl(self):
        with patch.object(run_terraform.shutil, "which", return_value=r"C:\SDK\gcloud.cmd"):
            self.assertEqual(
                run_terraform.gcloud_command("auth", "print-access-token"),
                [r"C:\SDK\gcloud.cmd", "auth", "print-access-token"],
            )

    def test_wsl_remains_the_fallback_for_existing_laptops(self):
        with patch.object(run_terraform.shutil, "which", return_value=None):
            self.assertEqual(
                run_terraform.gcloud_command("beta", "billing", "accounts", "list"),
                ["wsl.exe", "--", "gcloud", "beta", "billing", "accounts", "list"],
            )


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


class PlanGateTests(unittest.TestCase):
    def test_megaport_creates_are_blocked_before_provider_defaults_can_order(self):
        for address in ['megaport_mcr.lab[0]', 'megaport_vxc.azure["primary"]']:
            with self.subTest(address=address), self.assertRaisesRegex(RuntimeError, "PAYG"):
                run_terraform.check_changes([{"address": address, "actions": ["create"]}])

    def test_replacements_remain_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "destruction"):
            run_terraform.check_changes([
                {"address": "azurerm_linux_virtual_machine.probe", "actions": ["delete", "create"]}
            ])

    def test_imported_megaport_updates_cannot_rewrite_generated_peering(self):
        for address in ['megaport_mcr.lab[0]', 'megaport_vxc.gcp[0]']:
            with self.subTest(address=address), self.assertRaisesRegex(RuntimeError, "inventory-only"):
                run_terraform.check_changes([{"address": address, "actions": ["update"]}])

    def test_foundation_creates_and_imported_product_noops_are_allowed(self):
        run_terraform.check_changes([
            {"address": "google_compute_instance.cpe", "actions": ["create"]},
            {"address": "megaport_mcr.lab[0]", "actions": ["no-op"]},
        ])


if __name__ == "__main__":
    unittest.main()
