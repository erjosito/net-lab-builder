import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import configure_overlay


class SharedKeyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.control = Path(self.directory.name)
        self.patch = patch.object(configure_overlay, "CONTROL", self.control)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def test_existing_connections_rehydrate_keys_instead_of_rotating_on_a_new_laptop(self):
        with patch.object(configure_overlay, "checked_run", side_effect=[
            '["conn-internet-vnbgp-20261124", "conn-private-vnbgp-20261124"]',
            '{"value":"existing-internet-key"}', '{"value":"existing-private-key"}',
        ]) as run, patch.object(configure_overlay.secrets, "token_hex") as generate:
            keys = configure_overlay.vpn_psks()
        self.assertEqual(keys, {
            "internet": "existing-internet-key", "private": "existing-private-key",
        })
        generate.assert_not_called()
        self.assertEqual(run.call_count, 3)

    def test_missing_existing_key_does_not_fall_back_to_a_new_secret(self):
        with patch.object(configure_overlay, "checked_run", side_effect=[
            '["conn-internet-vnbgp-20261124"]', '{}',
        ]), self.assertRaisesRegex(RuntimeError, "No shared key"):
            configure_overlay.vpn_psks()
        self.assertFalse((self.control / "overlay-secrets.json").exists())

    def test_only_a_not_yet_created_connection_receives_a_new_key(self):
        with patch.object(configure_overlay, "checked_run", side_effect=[
            '["conn-internet-vnbgp-20261124"]', '{"value":"existing-internet-key"}',
        ]), patch.object(configure_overlay.secrets, "token_hex", return_value="new-key") as generate:
            keys = configure_overlay.vpn_psks()
        self.assertEqual(keys, {"internet": "existing-internet-key", "private": "new-key"})
        generate.assert_called_once_with(32)
        self.assertEqual(json.loads((self.control / "overlay-secrets.json").read_text()), keys)


class SavedPlanGateTests(unittest.TestCase):
    def detail(self, *, address='azurerm_virtual_network_gateway_connection.overlay["internet"]',
               before="same", after="same"):
        return {
            "variables": {"overlay_stage": {"value": "backup"}},
            "resource_changes": [{
                "address": address,
                "change": {
                    "actions": ["update"],
                    "before": {"shared_key": before},
                    "after": {"shared_key": after},
                },
            }],
        }

    def test_existing_psk_rotation_is_refused_even_for_an_overlay_resource(self):
        with self.assertRaisesRegex(RuntimeError, "must not be rotated"):
            configure_overlay.checked_changes(self.detail(after="different"), "backup")

    def test_actual_plan_is_gated_again_instead_of_trusting_an_older_summary(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected prerequisite"):
            configure_overlay.checked_changes(self.detail(address="google_compute_address.cpe"), "backup")
        with self.assertRaisesRegex(RuntimeError, "requested overlay stage"):
            configure_overlay.checked_changes(self.detail(), "internet")


if __name__ == "__main__":
    unittest.main()
