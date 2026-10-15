"""Offline contract fixtures. No CLI invocation or real-context reads."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import msdn


class Safety(unittest.TestCase):
    def test_template(self):
        template = json.loads(Path(__file__).with_name("msdn-main.json").read_text())
        resources = template["resources"]
        self.assertEqual(len(resources), 6)  # Five resources + OS-disk tagging extension.
        self.assertEqual(template["parameters"]["adminPublicKey"]["type"], "securestring")
        for resource in resources[:-1]:
            self.assertEqual(resource["tags"], "[variables('tags')]")
            self.assertNotIn("zones", resource)
        vnet, pip, nsg, nic, vm, disk_tags = resources
        self.assertFalse(vnet["properties"]["subnets"][0]["properties"]["defaultOutboundAccess"])
        self.assertEqual(nsg["properties"]["securityRules"][0]["properties"]["access"], "Deny")
        self.assertEqual(nsg["properties"]["securityRules"][0]["properties"]["priority"], 100)
        self.assertEqual(pip["sku"]["name"], "Standard")
        self.assertEqual(vm["properties"]["storageProfile"]["osDisk"]["diskSizeGB"], 30)
        self.assertEqual(disk_tags["properties"]["tags"], "[variables('tags')]")
        self.assertNotIn("customData", vm["properties"]["osProfile"])

    def test_catalog_nonzonal(self):
        row = {"name": "Standard_B1s", "capabilities": [{"name": "MemoryGB", "value": "1"}],
               "restrictions": [{"type": "Zone", "reasonCode": "NotAvailableForSubscription"}]}
        self.assertTrue(msdn.available(row))
        row["restrictions"][0]["type"] = "Location"
        self.assertFalse(msdn.available(row))
        row["restrictions"] = []
        row["name"] = "Standard_B1ls"
        self.assertFalse(msdn.available(row))

    def test_cleanup_ownership(self):
        client = type("Client", (), {"sub": "sub", "tenant": "tenant"})()
        state = {"runId": "bwt-123456abcdef", "resourceGroup": "rg-bwt-123456abcdef",
                 "subscriptionId": "sub", "expectedTenantId": "tenant", "createdByThisRun": True}
        self.assertEqual(msdn.owned(state, client)["lab"], "true")
        for key, wrong in (("createdByThisRun", False), ("resourceGroup", "preexisting"),
                           ("subscriptionId", "other"), ("expectedTenantId", "other"),
                           ("runId", "../unsafe")):
            bad = dict(state, **{key: wrong})
            with self.assertRaises(RuntimeError):
                msdn.owned(bad, client)

    def test_guard_expiry_stop_and_budgets(self):
        clock = dt.datetime(2026, 10, 15, 8, 20, tzinfo=dt.timezone.utc)
        lease = {"expiresAtUtc": "2026-10-15T08:46:00Z", "state": "active",
                 "commandTimeoutSeconds": 600, "actualMutations": 0, "maxMutations": 6,
                 "actualToolCalls": 0, "maxToolCalls": 100}
        with patch.object(msdn, "now", return_value=clock), \
                patch.object(msdn, "read", return_value=lease), \
                patch.object(Path, "exists", return_value=False):
            msdn.guard(mutation=True)
            lease["actualMutations"] = 5
            with self.assertRaises(RuntimeError):
                msdn.guard(mutation=True)
            msdn.guard(restore=True, mutation=True)
            lease["actualMutations"] = 6
            with self.assertRaises(RuntimeError):
                msdn.guard(restore=True, mutation=True)
            lease["actualMutations"] = 0
            lease["state"] = "completed"
            with self.assertRaises(RuntimeError):
                msdn.guard()
            lease["state"] = "active"
            with patch.object(Path, "exists", return_value=True):
                with self.assertRaises(RuntimeError):
                    msdn.guard(restore=True)
            with patch.object(msdn, "now", return_value=clock + dt.timedelta(minutes=27)):
                with self.assertRaises(RuntimeError):
                    msdn.guard(restore=True)

    def test_foreign_cleanup_inventory_rejected(self):
        state = {"runId": "bwt-123456abcdef", "resourceGroup": "rg-bwt-123456abcdef",
                 "subscriptionId": "sub", "expectedTenantId": "tenant", "createdByThisRun": True}
        tags = msdn.owned(state, type("C", (), {"sub": "sub", "tenant": "tenant"})())
        group = {"id": "/subscriptions/sub/resourceGroups/" + state["resourceGroup"], "tags": tags}
        foreign = {"id": group["id"] + "/providers/Microsoft.Compute/disks/foreign",
                   "type": "Microsoft.Compute/disks", "tags": tags, "location": "swedencentral"}
        client = type("C", (), {"sub": "sub", "tenant": "tenant"})()
        client.cli = lambda args, **kwargs: group if args[0] == "group" else [foreign]
        with self.assertRaises(RuntimeError):
            msdn.snapshot(client, copy.deepcopy(state))

    def test_delete_requires_distinct_cleanup_authorization(self):
        client = object.__new__(msdn.Client)
        with patch.object(msdn, "guard", return_value={"allowedMutations": [
                "create a new tagged MSDN lab resource group"]}):
            with self.assertRaisesRegex(RuntimeError, "operation_not_authorized_by_lease"):
                client.mutate(["group", "delete", "--name", "anything"])

    def test_native_argv_always_pins_subscription(self):
        client = object.__new__(msdn.Client)
        client.sub = "explicit-subscription"
        with patch.object(msdn, "guard", return_value={}), \
                patch.object(msdn, "read", return_value={}), \
                patch.object(msdn, "save"), \
                patch.object(msdn, "bounded", return_value={}) as run:
            client.cli(["account", "show"])
            argv = run.call_args.args[0]
            self.assertEqual(argv[0], "/usr/bin/az")
            self.assertEqual(argv[argv.index("--subscription") + 1], client.sub)
            self.assertNotIn("shell", argv)

    def test_token_tenant_and_subscription_must_match(self):
        client = object.__new__(msdn.Client)
        client.sub, client.tenant = "sub", "tenant"
        account = {"id": "sub", "tenantId": "tenant", "state": "Enabled"}
        token = {"subscription": "sub", "tenant": "wrong", "accessToken": "fixture-only"}
        with patch.object(client, "cli", side_effect=[account, token]):
            with self.assertRaisesRegex(RuntimeError, "token_context_mismatch"):
                client.authorize()


if __name__ == "__main__":
    unittest.main()
