"""Offline regression suite: every Azure call is an in-process fake."""

import copy
import base64
import hashlib
import io
import importlib
import json
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone
import uuid

import fresh


CLOCK = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)


def arm_token(slot, **changes):
    claims = {"tid": slot["tenantId"], "aud": "https://management.azure.com/",
              "exp": int((CLOCK + timedelta(hours=1)).timestamp())}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return {"tenant": slot["tenantId"], "subscription": slot["subscriptionId"],
            "tokenType": "Bearer", "expires_on": claims["exp"],
            "accessToken": "e30." + encoded + ".c2ln", **changes}


def actual_disk_shape(slot):
    """Minimal A/C/T recovery GET shape, with synthetic identities and no private values."""
    ids = {key: f'{fresh.group_id(slot)}/providers/{kind}/{fresh.names(slot)[key]}'
           for key, kind in fresh.KINDS.items()}
    storage = {"osDisk": {"managedDisk": {"id": ids["os"]}}, "dataDisks": []}
    disk = {"id": ids["os"], "name": fresh.names(slot)["os"], "type": fresh.KINDS["os"],
            "location": slot["region"], "tags": fresh.resource_tags(slot),
            "managedBy": ids["vm"], "sku": {"name": "StandardSSD_LRS"},
            "properties": {"diskSizeGB": 30}}
    return storage, disk


class FakeAzure(fresh.Azure):
    def __init__(self, config, lease):
        super().__init__(config, lease)
        self.groups, self.items, self.events = {}, {}, []
        self.fail_validation = False
        self.token_changes = {}

    def cli(self, slot, arguments, operation=None, restore=False, missing=None, diagnostic=None):
        if operation:
            self.before_mutation(slot, restore)
        self.lease.reserve(operation, restore, diagnostic)
        self.lease.idle()
        alias = slot["slot"]
        self.events.append((alias, tuple(arguments), operation))
        if arguments[:2] == ["account", "show"]:
            return {"id": slot["subscriptionId"], "tenantId": slot["tenantId"], "state": "Enabled"}
        if arguments[:2] == ["account", "get-access-token"]:
            return arm_token(slot, **self.token_changes.get(alias, {}))
        if arguments[:2] == ["vm", "list-skus"]:
            return [{"name": slot["sku"], "restrictions": []}]
        if operation and operation.startswith("create-group"):
            tokens = arguments[arguments.index("--tags") + 1:]
            self.groups[alias] = {"id": fresh.group_id(slot), "tags": dict(x.split("=", 1) for x in tokens)}
            self.items[alias] = []
        if operation and operation.startswith("validate") and self.fail_validation:
            raise fresh.Blocked("Synthetic validation failed")
        if operation and operation.startswith("deploy"):
            self.items[alias] = [{
                "id": rid, "name": rid.rsplit("/", 1)[-1], "type": kind,
                "location": slot["region"], "tags": fresh.resource_tags(slot)}
                for rid, kind in fresh.expected(slot).items()]
        if operation and operation.startswith("delete-group"):
            del self.groups[alias]
        return None

    def group(self, slot, missing=False, restore=False):
        self.lease.check(restore=restore)
        return self.groups.get(slot["slot"])

    def roots(self, slot, restore=False):
        self.lease.check(restore=restore)
        return copy.deepcopy(self.items.get(slot["slot"], []))

    def poll(self, slot, resource, version, mode, restore=False):
        self.lease.check(restore=restore)
        self.events.append((slot["slot"], (mode,), None))
        return ({"statuses": [{"code": "PowerState/deallocated"}]} if mode == "deallocated"
                else {"properties": {"provisioningState": "Succeeded"}})

    def get(self, slot, resource, version=fresh.GROUP_API, missing=None, restore=False):
        self.lease.check(restore=restore)
        ids = {key: f'{fresh.group_id(slot)}/providers/{kind}/{fresh.names(slot)[key]}'
               for key, kind in fresh.KINDS.items()}
        resource = next((value for value in ids.values() if value.lower() == resource.lower()), resource)
        if resource == ids["pip"]:
            return {"sku": {"name": "Standard", "tier": "Regional"}, "properties": {
                "ipAddress": "20.1.2.3", "publicIPAddressVersion": "IPv4",
                "publicIPAllocationMethod": "Static"}}
        if resource in (ids["nsg"], ids["subnet-nsg"]):
            return {"properties": {"securityRules": (
                [fresh.inbound_deny()] if resource == ids["nsg"] else [])}}
        if resource == ids["vnet"]:
            return {"properties": {"subnets": [{"name": "lab", "properties": {
                "networkSecurityGroup": {"id": ids["subnet-nsg"]}, "defaultOutboundAccess": False}}]}}
        if resource == ids["nic"]:
            return {"properties": {"networkSecurityGroup": {"id": ids["nsg"]}, "ipConfigurations": [{
                "properties": {"subnet": {"id": ids["vnet"] + "/subnets/lab"},
                               "publicIPAddress": {"id": ids["pip"]}}}]}}
        if resource == ids["vm"]:
            return {"properties": {"hardwareProfile": {"vmSize": slot["sku"]},
                    "networkProfile": {"networkInterfaces": [{"id": ids["nic"]}]},
                    "storageProfile": actual_disk_shape(slot)[0]}}
        if resource == ids["os"]:
            return actual_disk_shape(slot)[1]
        raise AssertionError("Unexpected fake GET")


class FreshTests(unittest.TestCase):
    def setUp(self):
        self.work = fresh.ROOT / (".fresh-test-work-" + uuid.uuid4().hex)
        self.work.mkdir()
        self.lease_path = fresh.ROOT / ".runtime-control" / ("fresh-test-" + uuid.uuid4().hex + ".json")
        self.lease_path.parent.mkdir(exist_ok=True)
        self.patches = [patch.object(fresh, "PRIVATE", self.work),
                        patch.object(fresh, "STOP", self.work / "STOP"),
                        patch.object(fresh, "now", return_value=CLOCK)]
        for item in self.patches:
            item.start()
        self.slots = []
        for i, alias in enumerate(("A", "C", "T")):
            run = "bwb-" + str(i + 1) * 12
            slot = {"slot": alias, "region": fresh.REGIONS[alias], "sku": "Standard_B2ts_v2",
                    "runId": run, "resourceGroup": "rg-" + run, "vmName": f"{run}-vm-{alias.lower()}",
                    "subscriptionId": ("1" if alias != "T" else "2") * 8 + "-1111-1111-1111-" + "1" * 12,
                    "tenantId": ("3" if alias != "T" else "4") * 8 + "-1111-1111-1111-" + "1" * 12,
                    "contextPath": str(self.work / (alias + "-context.json")),
                    "inventoryPath": str(self.work / (alias + "-inventory.json"))}
            fresh.write(slot["contextPath"], {k: slot[k] for k in ("runId", "resourceGroup", "subscriptionId")} |
                        {"expectedTenantId": slot["tenantId"]})
            self.slots.append(slot)
        self.config = {"slots": self.slots, "nativeCoreCli": r"C:\cli\wbin\az.cmd",
                       "msdnCliArgvPrefix": ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "/usr/bin/az"]}
        self.lease_data = {
            "action": "deploy", "ownerRole": "Tank", "state": "active", "taskId": "offline-test",
            "startedAtUtc": CLOCK.isoformat(), "expiresAtUtc": (CLOCK + timedelta(minutes=60)).isoformat(),
            "maxToolCalls": 150, "actualToolCalls": 0, "maxMutations": 12, "actualMutations": 0,
            "commandTimeoutSeconds": 120, "restoreTimeoutMinutes": 15,
            "allowedMutations": [f"{v}-{a.lower()}" for a in fresh.REGIONS
                                 for v in ("create-group", "validate", "deploy", "deallocate")],
            "handoffHash": fresh.digest(self.slots), "ownedProcessesIdle": True}
        self.save_lease()
        self.lease = fresh.Lease(self.lease_path, "deploy")
        self.azure = FakeAzure(self.config, self.lease)
        self.gate = self.make_gate()
        self.handoff_path = self.work / "handoff.json"
        fresh.write(self.handoff_path, self.config)
        self.azure.handoff_path = self.handoff_path
        unapproved = copy.deepcopy(self.gate)
        unapproved.update(reviewPassed=False, deploymentApproved=False)
        fresh.prepare(self.config, unapproved, self.work / "prepared", self.handoff_path)
        capture = self.work / "prepared" / "approval.private.json"
        self.gate.update(preparedInputsPath=str(capture), approvedInputsHash=fresh.byte_hash(capture.read_bytes()))

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.lease_path.unlink(missing_ok=True)
        self.lease_path.with_suffix(".new").unlink(missing_ok=True)
        self.lease_path.with_suffix(".json.new").unlink(missing_ok=True)
        shutil.rmtree(self.work)

    def save_lease(self):
        self.lease_path.write_text(json.dumps(self.lease_data), encoding="utf-8")

    def make_gate(self):
        key = self.work / "existing.pub"
        key.write_text("ssh-ed25519 AAAA existing key comment\n", encoding="utf-8")
        gate = {
            "pricesVerifiedAtUtc": fresh.stamp(), "fxVerifiedAtUtc": fresh.stamp(), "approvedAtUtc": fresh.stamp(),
            "reviewPassed": True, "deploymentApproved": True, "handoffHash": fresh.digest(self.slots),
            "combinedCapUSD": 45, "coreCapUSD": 23, "msdnCapUSDEquivalent": 22, "msdnCapEUR": 19.62,
            "usdPerEur": 1.1208, "wireGBPerContextMaximum": 220, "payloadGBPerDirection": 100,
            "allocatedHoursPerSlotMaximum": 12, "resourceTTLHoursMaximum": 48,
            "coreBillingCurrency": "USD", "msdnBillingCurrency": "EUR",
            "cleanupDeadlineUtc": fresh.DEADLINE, "sshPublicKeyPath": str(key),
            "prices": {}, "evidenceHashes": {}}
        for alias in fresh.REGIONS:
            eur = alias == "T"
            gate["prices"][alias] = {
                "currency": "EUR" if eur else "USD", "region": fresh.REGIONS[alias], "sku": "Standard_B2ts_v2",
                "computePerHour": .0095 if eur else (.0114 if alias == "C" else .0108),
                "diskPerMonth": 2.1119 if eur else 2.4, "diskOperationsPer10000": .0018 if eur else .002,
                "pipPerHour": .0044 if eur else .005, "internetWorstPerGB": .0766 if eur else .087}
        return gate

    def run_deploy(self, output=None):
        with patch.object(fresh, "verify_prices"):
            fresh.deploy(self.azure, self.slots, self.gate, output or self.work / "deployment")

    def test_template_roles_and_dependencies(self):
        template = fresh.make_template()
        self.assertEqual(template["$schema"],
                         "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#")
        self.assertEqual(template["contentVersion"], "1.0.0.0")
        self.assertEqual(template["parameters"]["adminPublicKey"]["type"], "securestring")
        self.assertEqual(template["parameters"]["endpointAlias"]["allowedValues"], ["a", "c", "t"])
        self.assertEqual(len(template["resources"]), 7)
        self.assertEqual(sum(r["type"] == fresh.KINDS["nsg"] for r in template["resources"]), 2)
        self.assertEqual(template["parameters"]["vmSize"]["allowedValues"], ["Standard_B2ts_v2"])
        for alias in ("a", "c", "t"):
            slot = next(s for s in self.slots if s["slot"].lower() == alias)
            expanded = set()
            for resource in template["resources"]:
                self.assertNotIn("copy", resource)
                self.assertNotIn("zones", resource)
                if resource["type"] != "Microsoft.Resources/tags":
                    self.assertIn("tags", resource)
                    values = {"runId": slot["runId"], "endpointAlias": alias}
                    tokens = re.findall(r"parameters\('([^']+)'\)|'([^']*)'", resource["name"])
                    expanded.add("".join(values[p] if p else literal for p, literal in tokens))
            self.assertEqual(expanded, {fresh.names(slot)[k] for k in fresh.KINDS if k != "os"})
            nsgs = [r for r in template["resources"] if r["type"] == fresh.KINDS["nsg"]]
            self.assertEqual(nsgs[0]["properties"]["securityRules"], [])
            self.assertEqual(nsgs[1]["properties"]["securityRules"], [fresh.inbound_deny()])
            vm = next(r for r in template["resources"] if r["type"] == fresh.KINDS["vm"])
            self.assertIn("'-vm-'", vm["name"])
            self.assertEqual(vm["properties"]["storageProfile"]["dataDisks"], [])
            self.assertEqual(vm["properties"]["storageProfile"]["osDisk"]["diskSizeGB"], 30)
            vnet = next(r for r in template["resources"] if r["type"] == fresh.KINDS["vnet"])
            self.assertIn("-subnet-policy-", vnet["dependsOn"][0])
            self.assertIn("-subnet-policy-", vnet["properties"]["subnets"][0]["properties"]["networkSecurityGroup"]["id"])
        self.assertEqual(template["variables"]["tags"], {
            "lab": "true", "created_by": "copilot-lab", "run_id": "[parameters('runId')]"})

    def test_legacy_or_unexpected_vm_name_rejected_not_silently_reinterpreted(self):
        for vm_name in ("vm-" + self.slots[0]["runId"] + "-a", "some-other-vm"):
            handoff = copy.deepcopy(self.config)
            handoff["slots"][0]["vmName"] = vm_name
            with self.assertRaisesRegex(fresh.Blocked, "VM name"):
                fresh.load_slots(handoff)
            with self.assertRaisesRegex(fresh.Blocked, "VM name"):
                fresh.names(handoff["slots"][0])

    def test_offline_align_cli_copies_planned_names_contexts_and_provenance_exclusively(self):
        handoff = copy.deepcopy(self.config)
        for slot in handoff["slots"]:
            slot["vmName"] = f'vm-{slot["runId"]}-{slot["slot"].lower()}'
            context = fresh.read(slot["contextPath"])
            context["vmName"] = slot["vmName"]
            fresh.write(slot["contextPath"], context)
        source = self.work / "legacy-planned-handoff.json"
        fresh.write(source, handoff)
        sources = [source] + [fresh.Path(s["contextPath"]) for s in handoff["slots"]]
        before = {str(p): p.read_bytes() for p in sources}
        output = self.work / "new-aligned"
        with patch.object(fresh, "Azure", side_effect=AssertionError("No Azure")), \
                patch.object(fresh, "prepare", side_effect=AssertionError("No preparation")), \
                patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(fresh.main(["align-handoff", "--handoff", str(source),
                                         "--output", str(output)]), 0)
        aligned = fresh.read(output / "handoff.private.json")
        self.assertEqual(fresh.load_slots(aligned), aligned["slots"])
        self.assertEqual(aligned["slotsHash"], fresh.digest(aligned["slots"]))
        self.assertEqual(aligned["alignment"]["sourceHashes"],
                         {p: fresh.byte_hash(raw) for p, raw in before.items()})
        for slot in aligned["slots"]:
            self.assertEqual(slot["vmName"], f'{slot["runId"]}-vm-{slot["slot"].lower()}')
            self.assertEqual(fresh.read(slot["contextPath"])["vmName"], slot["vmName"])
            self.assertEqual(fresh.Path(slot["inventoryPath"]).parent, output)
            self.assertFalse(fresh.Path(slot["inventoryPath"]).exists())
        for path, raw in before.items():
            self.assertEqual(fresh.Path(path).read_bytes(), raw)
        published = {p: p.read_bytes() for p in output.glob("*.json")}
        with self.assertRaisesRegex(fresh.Blocked, "directory exists"):
            fresh.align_handoff(source, output)
        self.assertEqual(published, {p: p.read_bytes() for p in output.glob("*.json")})
        self.assertEqual(len(published), 4)

    def test_alignment_rejects_actual_inventory_or_ownership_receipts(self):
        for path in (fresh.Path(self.slots[0]["inventoryPath"]), fresh.state_path(self.slots[0])):
            fresh.write(path, {"mustNotBeAdopted": True})
            with self.assertRaisesRegex(fresh.Blocked, "planned slots"):
                fresh.align_handoff(self.handoff_path, self.work / "rejected-alignment")
            path.unlink()

    def test_pure_fresh_inventory_passes_real_transfer_and_repeat_contracts(self):
        self.run_deploy()
        transfers = fresh.ROOT.parent / "transfers"
        # Restore both module cache and import path, including any preexisting runner modules.
        with patch.dict(sys.modules), patch.object(sys, "path", [str(transfers), *sys.path]):
            for name in ("run", "repeat", "stream"):
                sys.modules.pop(name, None)
            run = importlib.import_module("run")
            repeat = importlib.import_module("repeat")
            with patch.object(run, "now", return_value=CLOCK), \
                    patch.object(fresh.subprocess, "Popen", side_effect=AssertionError("No processes")):
                config = repeat.skeleton()
                config["approval"]["resourceIds"] = []
                for key, slot in (("core", self.slots[0]), ("msdn", self.slots[2])):
                    context = config["contexts"][key]
                    context.update(subscriptionId=slot["subscriptionId"], expectedTenantId=slot["tenantId"])
                    context["preflight"].update(validated=True, evidenceReference="OFFLINE-FAKE",
                                                txPerDecimalGB=".087", vmPerHour=".0114")
                for slot in self.slots:
                    alias = slot["slot"]
                    inventory = fresh.read(slot["inventoryPath"])
                    self.assertEqual(len(inventory["resources"]), 7)
                    self.assertTrue(inventory["ready"])
                    self.assertEqual(inventory["bindings"]["os"].lower(),
                                     actual_disk_shape(slot)[1]["id"].lower())
                    config["endpoints"][alias].update(inventory=inventory)
                    config["approval"]["resourceIds"].extend(r["id"] for r in inventory["resources"])
                    context = config["contexts"]["msdn" if alias == "T" else "core"]
                    binding = run.target(context, inventory, alias.lower(), slot["region"])
                    binding["region"] = slot["region"]
                    self.assertEqual(binding["vm"], slot["vmName"])
                    self.assertEqual(binding["nsg"], fresh.names(slot)["nsg"])
                    vm = {"storageProfile": actual_disk_shape(slot)[0]}
                    run.approved_os_disk(vm, binding, inventory)
                    for row in inventory["resources"]:
                        if row["type"].startswith("Microsoft.Network/"):
                            run.owned_network({**row, "provisioningState": "Succeeded"}, binding,
                                              inventory, row["type"].split("/")[-1])
                self.assertTrue(repeat.validate_config(config, approved=False))
                nsgs = [r for r in fresh.make_template()["resources"] if r["type"] == fresh.KINDS["nsg"]]
                subnet, nic = nsgs
                expected_deny = {"name": "DenyAllInboundUntilHarnessApproved", "priority": 100,
                                 "access": "Deny", "direction": "Inbound", "protocol": "*",
                                 "sourceAddressPrefix": "*", "destinationAddressPrefix": "*",
                                 "sourcePortRange": "*", "destinationPortRange": "*"}
                self.assertEqual(run.normalized_rules(nic["properties"]["securityRules"]),
                                 run.normalized_rules([expected_deny]))
                self.assertEqual(subnet["properties"]["securityRules"], [])
                for resource in (nic, subnet):
                    flat = [{**r["properties"], "name": r["name"]}
                            for r in resource["properties"]["securityRules"]]
                    restore, allowed = run.policy_bodies(self.work, {"client_ip": "192.0.2.1"},
                        {"location": "swedencentral", "tags": fresh.resource_tags(self.slots[0]),
                         "securityRules": flat}, write=False)
                    self.assertEqual(run.normalized_rules(restore["properties"]["securityRules"]),
                                     run.normalized_rules(resource["properties"]["securityRules"]))
                    self.assertEqual(allowed["properties"]["securityRules"][-1]["properties"]["priority"], 100)
                    if flat:
                        self.assertEqual(allowed["properties"]["securityRules"][0]["properties"]["priority"], 200)

    def test_actual_vm_reference_omissions_require_owned_disk_get_for_all_slots(self):
        for slot in self.slots:
            with self.subTest(slot=slot["slot"]):
                storage, disk = actual_disk_shape(slot)
                self.assertNotIn("diskSizeGB", storage["osDisk"])
                self.assertNotIn("storageAccountType", storage["osDisk"]["managedDisk"])
                with patch.object(self.azure, "get", wraps=self.azure.get) as get:
                    bindings = fresh.verify_bindings(self.azure, slot, restore=True)
                get.assert_any_call(slot, disk["id"], fresh.DISK, restore=True)
                self.assertEqual(len(get.call_args_list), 6)
                self.assertEqual(bindings, {key: f'{fresh.group_id(slot)}/providers/{kind}/{fresh.names(slot)[key]}'
                                           for key, kind in fresh.KINDS.items()})
                self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_vm_reference_optional_fields_must_agree_with_authoritative_disk(self):
        slot = self.slots[0]
        original_get = self.azure.get
        for size, sku, accepted in ((30, "StandardSSD_LRS", True), (31, "StandardSSD_LRS", False),
                                    (None, "StandardSSD_LRS", False), ("30", "StandardSSD_LRS", False),
                                    (30.0, "StandardSSD_LRS", False), (30, "Premium_LRS", False),
                                    (30, None, False)):
            with self.subTest(size=size, sku=sku):
                def changed(s, resource, *args, **kwargs):
                    value = original_get(s, resource, *args, **kwargs)
                    if resource.endswith("/" + slot["vmName"]):
                        os_disk = value["properties"]["storageProfile"]["osDisk"]
                        os_disk["diskSizeGB"] = size
                        os_disk["managedDisk"]["storageAccountType"] = sku
                    return value
                with patch.object(self.azure, "get", side_effect=changed):
                    if accepted:
                        fresh.verify_bindings(self.azure, slot)
                    else:
                        with self.assertRaisesRegex(fresh.Blocked, "contradicts"):
                            fresh.verify_bindings(self.azure, slot)

    def test_foreign_or_malformed_vm_disk_reference_blocks_before_disk_get(self):
        slot = self.slots[0]
        original_get = self.azure.get
        for managed, data in (({"id": "/foreign/disk"}, []), ({"id": None}, []),
                              ({}, []), (None, []), ({"id": actual_disk_shape(slot)[1]["id"]}, [{}]),
                              ({"id": actual_disk_shape(slot)[1]["id"]}, None)):
            with self.subTest(managed=managed, data=data):
                def changed(s, resource, *args, **kwargs):
                    self.assertFalse(resource.endswith("/" + fresh.names(slot)["os"]))
                    value = original_get(s, resource, *args, **kwargs)
                    if resource.endswith("/" + slot["vmName"]):
                        storage = value["properties"]["storageProfile"]
                        storage["osDisk"]["managedDisk"], storage["dataDisks"] = managed, data
                    return value
                with patch.object(self.azure, "get", side_effect=changed):
                    with self.assertRaises(fresh.Blocked):
                        fresh.verify_bindings(self.azure, slot)
                self.assertFalse(fresh.Path(slot["inventoryPath"]).exists())

    def test_authoritative_disk_fields_missing_malformed_or_foreign_block(self):
        slot = self.slots[0]
        original_get = self.azure.get
        cases = [(("id",), "/foreign/disk"), (("id",), None), (("name",), "other"),
                 (("type",), "Microsoft.Network/networkInterfaces"), (("type",), None),
                 (("location",), "northeurope"), (("tags",), {}), (("managedBy",), "/foreign/vm"),
                 (("managedBy",), None), (("properties",), None), (("sku",), None),
                 (("properties", "diskSizeGB"), None), (("properties", "diskSizeGB"), "30"),
                 (("properties", "diskSizeGB"), 30.0), (("properties", "diskSizeGB"), True),
                 (("properties", "diskSizeGB"), 31), (("sku", "name"), "Premium_LRS"),
                 (("sku", "name"), None)]
        for path, bad in cases:
            for missing in (False, True):
                with self.subTest(path=path, bad=bad, missing=missing):
                    def changed(s, resource, *args, **kwargs):
                        value = original_get(s, resource, *args, **kwargs)
                        if resource.endswith("/" + fresh.names(slot)["os"]):
                            parent = value
                            for key in path[:-1]:
                                parent = parent[key]
                            if missing:
                                del parent[path[-1]]
                            else:
                                parent[path[-1]] = bad
                        return value
                    with patch.object(self.azure, "get", side_effect=changed):
                        with self.assertRaises(fresh.Blocked):
                            fresh.verify_bindings(self.azure, slot)
                    self.assertFalse(fresh.Path(slot["inventoryPath"]).exists())
                    self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_full_lifecycle_order_output_and_exact_mutations(self):
        self.run_deploy()
        operations = [e[2] for e in self.azure.events if e[2]]
        self.assertEqual(len(operations), 12)
        self.assertLess(max(operations.index("validate-" + a) for a in ("a", "c", "t")),
                        min(operations.index("deploy-" + a) for a in ("a", "c", "t")))
        self.assertEqual(operations[-3:], ["deallocate-a", "deallocate-c", "deallocate-t"])
        self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 12)
        self.assertTrue(fresh.read(self.work / "deployment" / "manifest.private.json")["actualAllocationProven"])
        for slot in self.slots:
            inventory = fresh.read(slot["inventoryPath"])
            self.assertEqual(len(inventory["resources"]), 7)
            self.assertTrue(inventory["ready"])
            self.assertIn("capturedAtUtc", inventory)
            self.assertTrue(all(row["tags"] == fresh.resource_tags(slot) for row in inventory["resources"]))
            self.assertEqual(set(self.azure.groups[slot["slot"]]["tags"]),
                             {"lab", "created_by", "run_id", "createdUtc", "cleanupDeadlineUtc"})
        self.assertEqual(set(fresh.read(self.work / "deployment" / "peers.private.json")), {"A", "C", "T"})

    def test_existing_group_refused_before_mutation(self):
        self.azure.groups["T"] = {"id": "unowned"}
        with self.assertRaisesRegex(fresh.Blocked, "already exists"):
            self.run_deploy()
        self.assertFalse(any(e[2] for e in self.azure.events))

    def test_failed_validation_never_locks_or_deploys(self):
        self.azure.fail_validation = True
        with self.assertRaisesRegex(fresh.Blocked, "validation"):
            self.run_deploy()
        self.assertFalse((self.work / "deployment" / "manifest.private.json").exists())
        self.assertFalse(any(e[2] and e[2].startswith("deploy-") for e in self.azure.events))
        self.assertTrue(fresh.read(fresh.state_path(self.slots[0]))["createdVerified"])

    def test_context_and_subscription_mismatch(self):
        self.assertEqual(fresh.load_slots(self.config), self.slots)
        context = fresh.read(self.slots[0]["contextPath"])
        context["expectedTenantId"] = self.slots[2]["tenantId"]
        fresh.write(self.slots[0]["contextPath"], context)
        with self.assertRaisesRegex(fresh.Blocked, "Tenant"):
            fresh.load_slots(self.config)
        azure = fresh.Azure(self.config, self.lease)
        with patch.object(azure, "cli", return_value={"id": "wrong", "tenantId": "wrong", "state": "Enabled"}):
            with self.assertRaises(fresh.Blocked):
                azure.identity(self.slots[0])

    def test_lease_stop_expiry_call_write_and_eighty_percent_bounds(self):
        (self.work / "STOP").write_text("stop", encoding="utf-8")
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve()
        (self.work / "STOP").unlink()
        self.lease_data["actualMutations"] = 10
        self.save_lease()
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve("deploy-t")
        self.lease.reserve("deallocate-a", restore=True)
        self.lease_data["expiresAtUtc"] = CLOCK.isoformat()
        self.save_lease()
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve("deallocate-c", restore=True)
        self.lease_data["expiresAtUtc"] = (CLOCK + timedelta(minutes=60)).isoformat()
        self.lease_data["actualToolCalls"] = 150
        self.save_lease()
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve(restore=True)

    def test_mutation_authorization_and_maximum(self):
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve("allocate-t")
        self.lease_data["actualMutations"] = 12
        self.save_lease()
        with self.assertRaises(fresh.Blocked):
            self.lease.reserve("deallocate-t", restore=True)

    def test_budget_stale_fx_and_overrun_block_before_cli(self):
        with patch.object(fresh, "verify_prices"):
            fresh.validate_gate(self.gate, self.slots, self.lease_data)
            for key, value in (("combinedCapUSD", 46), ("usdPerEur", 0),
                               ("cleanupDeadlineUtc", "2026-10-19T00:00:00Z"),
                               ("fxVerifiedAtUtc", "2026-10-15T09:00:00Z")):
                bad = copy.deepcopy(self.gate)
                bad[key] = value
                with self.assertRaises(fresh.Blocked):
                    fresh.validate_gate(bad, self.slots, self.lease_data)
            self.gate["prices"]["C"]["computePerHour"] = 1
            with self.assertRaises(fresh.Blocked):
                fresh.validate_gate(self.gate, self.slots, self.lease_data)
            reserve_gate = self.make_gate()
            for alias in ("A", "C"):
                reserve_gate["prices"][alias]["internetWorstPerGB"] = .094
            with self.assertRaisesRegex(fresh.Blocked, "Full traffic"):
                fresh.validate_gate(reserve_gate, self.slots, self.lease_data)

    def test_precise_price_evidence_selection_currency_freshness_and_hash(self):
        evidence = {}
        selectors = {
            "compute": [("computePerHour", "Virtual Machines Bsv2 Series", "B2ts v2", "1 Hour")],
            "disk": [("diskPerMonth", "Standard SSD Managed Disks", "E4 LRS Disk", "1/Month"),
                     ("diskOperationsPer10000", "Standard SSD Managed Disks", "E4 LRS Disk Operations", "10K")],
            "pip": [("pipPerHour", "IP Addresses", "Standard IPv4 Static Public IP", "1 Hour")],
            "bandwidth": [("internetWorstPerGB", "Rtn Preference: MGN", "Standard Data Transfer Out", "1 GB")]}
        for currency in ("USD", "EUR"):
            for kind, entries in selectors.items():
                items = []
                for alias in ("A", "C"):
                    p = self.gate["prices"]["T" if currency == "EUR" else alias]
                    for key, product, meter, unit in entries:
                        items.append({"currencyCode": currency, "type": "Consumption", "productName": product,
                                      "meterName": meter, "unitOfMeasure": unit, "retailPrice": p[key],
                                      "armRegionName": fresh.REGIONS[alias],
                                      "location": "SE Central" if alias == "A" else "EU North"})
                evidence[f"{kind}-{currency}.json"] = {
                    "retrievedAtUtc": fresh.stamp(), "incomplete": False,
                    "url": "https://prices.azure.com/api/retail/prices",
                    "response": {"BillingCurrency": currency, "Items": items}}
        evidence["fx-source.json"] = {
            "retrievedAtUtc": fresh.stamp(), "quoteDate": "2026-10-15", "usdPerEur": 1.1208,
            "source": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"}
        evidence["disk-cap-source.json"] = {
            "retrievedAtUtc": fresh.stamp(), "conservativeTransactionsPerHourUsed": 61000, "E4GiB": 32}
        fresh.verify_prices(evidence, self.gate["prices"], 1.1208)
        for key, value in evidence.items():
            path = self.work / key
            fresh.write(path, value)
            self.gate["evidenceHashes"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        fresh.validate_gate(self.gate, self.slots, self.lease_data)
        self.gate["evidenceHashes"][str(self.work / "compute-USD.json")] = "wrong"
        with self.assertRaisesRegex(fresh.Blocked, "hash"):
            fresh.validate_gate(self.gate, self.slots, self.lease_data)
        bad = copy.deepcopy(evidence)
        bad["compute-USD.json"]["response"]["Items"][0]["meterName"] += " Spot"
        with self.assertRaises(fresh.Blocked):
            fresh.verify_prices(bad, self.gate["prices"], 1.1208)
        bad = copy.deepcopy(evidence)
        bad["fx-source.json"]["retrievedAtUtc"] = "2026-10-15T12:00:00Z"
        with self.assertRaises(fresh.Blocked):
            fresh.verify_prices(bad, self.gate["prices"], 1.1208)
        bad = copy.deepcopy(evidence)
        bad["pip-EUR.json"]["response"]["BillingCurrency"] = "USD"
        with self.assertRaises(fresh.Blocked):
            fresh.verify_prices(bad, self.gate["prices"], 1.1208)

    def test_unknown_inventory_tamper_and_no_absence_block(self):
        self.run_deploy()
        slot = self.slots[0]
        state = fresh.read_state(slot)
        resources = self.azure.roots(slot, restore=True)
        for change in ("unknown", "tags", "hash", "absence"):
            s, rs = copy.deepcopy(state), copy.deepcopy(resources)
            if change == "unknown":
                rs.append({"id": fresh.group_id(slot) + "/providers/Unknown/unknown/x"})
            elif change == "tags":
                rs[0]["tags"]["run_id"] = "foreign"
            elif change == "hash":
                s["ownershipHash"] = "changed"
            else:
                s["absenceProven"] = False
            with self.assertRaises(fresh.Blocked):
                fresh.verify_inventory(slot, s, self.azure.groups["A"], rs)

    def test_group_five_root_three_tags_are_exact_for_complete_and_partial_inventory(self):
        self.run_deploy()
        slot = self.slots[0]
        state = fresh.read_state(slot)
        resources = self.azure.roots(slot, restore=True)
        group = self.azure.groups["A"]
        for complete in (True, False):
            for scope, field in (("group", "extra"), ("group", "createdUtc"),
                                 ("root", "extra"), ("root", "run_id"),
                                 ("root", "createdUtc"), ("root", "cleanupDeadlineUtc")):
                with self.subTest(complete=complete, scope=scope, field=field):
                    g, rows = copy.deepcopy(group), copy.deepcopy(resources)
                    changed = g["tags"] if scope == "group" else rows[0]["tags"]
                    changed[field] = "unexpected"
                    with self.assertRaisesRegex(fresh.Blocked, "ownership tags"):
                        fresh.verify_inventory(slot, state, g, rows, complete=complete)
        receipt = copy.deepcopy(state)
        receipt["ownership"]["extra"] = "not-approved"
        receipt["ownershipHash"] = fresh.digest(receipt["ownership"])
        with self.assertRaisesRegex(fresh.Blocked, "ownership receipt"):
            fresh.verify_inventory(slot, receipt, group, resources, complete=False)

    def test_readiness_requires_exact_nic_deny_and_separate_empty_subnet(self):
        slot = self.slots[0]
        original_get = self.azure.get
        for kind, change in (("nsg", "missing"), ("nsg", "allow"), ("nsg", "priority"),
                             ("nsg", "protocol"), ("nsg", "source"), ("nsg", "extra"),
                             ("subnet-nsg", "deny")):
            with self.subTest(kind=kind, change=change):
                def changed(s, resource, *args, **kwargs):
                    value = original_get(s, resource, *args, **kwargs)
                    if resource.endswith("/" + fresh.names(slot)[kind]):
                        rules = value["properties"]["securityRules"]
                        if change == "missing":
                            rules.clear()
                        elif change == "deny":
                            rules.append(fresh.inbound_deny())
                        elif change == "extra":
                            rules.append(fresh.inbound_deny())
                        else:
                            field, bad = {"allow": ("access", "Allow"), "priority": ("priority", 200),
                                          "protocol": ("protocol", "Tcp"),
                                          "source": ("sourceAddressPrefix", "192.0.2.1/32")}[change]
                            rules[0]["properties"][field] = bad
                    return value
                with patch.object(self.azure, "get", side_effect=changed):
                    with self.assertRaisesRegex(fresh.Blocked, "baseline"):
                        fresh.verify_bindings(self.azure, slot)

    def test_preview_readonly_then_owned_cleanup(self):
        self.run_deploy()
        self.azure.approval = None  # Separate CLI invocations do not reuse deployment approval objects.
        for action, maximum in (("preview-cleanup", 0), ("cleanup", 6)):
            self.lease_data.update(action=action, actualToolCalls=0, actualMutations=0, maxMutations=maximum,
                                   allowedMutations=["delete-group-" + a for a in ("a", "c", "t")],
                                   cleanupApproval="delete only the fresh task-created exact inventoried groups")
            if action == "cleanup":
                self.lease_data["previewHashes"] = {
                    s["slot"]: fresh.read(fresh.state_path(s).with_name(
                        s["slot"].lower() + "-cleanup-preview.private.json"))["hash"] for s in self.slots}
            self.save_lease()
            self.azure.lease = fresh.Lease(self.lease_path, action)
            fresh.cleanup(self.azure, self.slots, action == "cleanup")
            self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0 if maximum == 0 else 3)
        self.assertEqual(self.azure.groups, {})

    def test_arm_token_rejection_precedes_all_resource_writes(self):
        cases = [
            {"tenant": self.slots[0]["tenantId"]},
            {"subscription": self.slots[0]["subscriptionId"]},
            {"accessToken": ""}, {"accessToken": "not-a-token"},
            {"accessToken": "e30.invalid.c2ln"}, {"tokenType": "Other"},
            {"expires_on": int(CLOCK.timestamp())}, {"expires_on": "invalid"},
        ]
        for index, changes in enumerate(cases):
            with self.subTest(case=index):
                self.azure.token_changes["T"] = changes
                with self.assertRaises(fresh.Blocked):
                    self.run_deploy(self.work / ("rejected-token-" + str(index)))
                self.assertFalse(any(e[2] for e in self.azure.events))
                self.assertEqual(self.azure.groups, {})
                self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_jwt_claims_are_checked_not_only_cli_metadata(self):
        for changes in ({"tid": "foreign"}, {"aud": "https://example.invalid/"},
                        {"exp": int(CLOCK.timestamp())}):
            claims = {"tid": self.slots[0]["tenantId"], "aud": "https://management.azure.com/",
                      "exp": int((CLOCK + timedelta(hours=1)).timestamp()), **changes}
            encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            self.azure.token_changes["A"] = {"accessToken": "e30." + encoded + ".c2ln"}
            with self.assertRaises(fresh.Blocked):
                self.azure.identity(self.slots[0])
        self.assertFalse(any(e[2] for e in self.azure.events))

    def test_native_and_wsl_explicit_arm_token_commands_and_recheck(self):
        cli = self.work / "installed-cli"
        (cli / "wbin").mkdir(parents=True)
        (cli / "python.exe").write_bytes(b"")
        config = copy.deepcopy(self.config)
        config["nativeCoreCli"] = str(cli / "wbin" / "az.cmd")
        commands = []
        bad = [False]

        def popen(command, **kwargs):
            commands.append(command)
            slot = self.slots[2] if command[0] == "wsl.exe" else self.slots[0]
            result = (arm_token(slot, accessToken="" if bad[0] else arm_token(slot)["accessToken"])
                      if "get-access-token" in command else
                      {"id": slot["subscriptionId"], "tenantId": slot["tenantId"], "state": "Enabled"})
            process = Mock(returncode=0)
            process.poll.return_value = 0
            process.communicate.return_value = (json.dumps(result).encode(), b"")
            return process

        azure = fresh.Azure(config, self.lease)
        with patch.object(fresh.subprocess, "Popen", side_effect=popen):
            for slot in (self.slots[0], self.slots[2]):
                azure.identity(slot)
            tokens = [c for c in commands if "get-access-token" in c]
            self.assertEqual(tokens[0][:3], [str(cli / "python.exe"), "-m", "azure.cli"])
            self.assertEqual(tokens[1][:5], ["wsl.exe", "-d", "Ubuntu-24.04", "--exec",
                                            "/usr/bin/timeout"])
            self.assertIn("/usr/bin/az", tokens[1])
            for command, slot in zip(tokens, (self.slots[0], self.slots[2])):
                self.assertEqual(command[command.index("--subscription") + 1], slot["subscriptionId"])
                self.assertEqual(command[command.index("--resource") + 1], "https://management.azure.com/")
                self.assertNotIn("accessToken", " ".join(command))
            bad[0] = True
            for slot in (self.slots[0], self.slots[2]):
                with self.assertRaises(fresh.Blocked):
                    azure.cli(slot, ["group", "create"], operation="create-group-" + slot["slot"].lower())
        self.assertFalse(any("create" in c for c in commands))
        self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_approved_capture_required_and_never_silently_regenerated(self):
        self.gate["approvedInputsHash"] = "unreviewed"
        with self.assertRaisesRegex(fresh.Blocked, "capture hash"):
            self.run_deploy()
        self.assertFalse(self.azure.events)
        with self.assertRaisesRegex(fresh.Blocked, "unapproved"):
            fresh.prepare(self.config, self.gate, self.work / "another-prepared", self.handoff_path)

    def test_initial_source_drift_blocks_before_any_azure_call(self):
        original_read = fresh.Path.read_bytes
        source = fresh.Path(fresh.__file__).resolve()

        def changed_read(path):
            raw = original_read(path)
            return raw + b" " if path == source else raw

        with patch.object(fresh.Path, "read_bytes", changed_read):
            with self.assertRaisesRegex(fresh.Blocked, "hash drift"):
                self.run_deploy()
        self.assertFalse(self.azure.events)
        self.assertFalse(self.azure.groups)
        self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_post_validation_drift_blocks_next_mutation(self):
        targets = ("template", "parameters", "context", "handoff", "source", "base-template",
                   "gate", "gatefile", "quote", "lease", "capture", "token")
        original_read = fresh.Path.read_bytes
        original_gate = copy.deepcopy(self.gate)
        for target in targets:
            with self.subTest(target=target):
                self.save_lease()
                self.azure = FakeAzure(self.config, fresh.Lease(self.lease_path, "deploy"))
                self.azure.handoff_path = self.handoff_path
                self.azure.gate_path = self.work / "reviewed-gate.json"
                fresh.write(self.azure.gate_path, self.gate)
                output = self.work / ("drift-" + target)
                changed = [False]
                cli = self.azure.cli

                def simulate_drift(slot, arguments, operation=None, **kwargs):
                    result = cli(slot, arguments, operation, **kwargs)
                    if operation == "validate-t":
                        changed[0] = True
                    return result

                paths = {
                    "template": output / "single-vm.private.json",
                    "parameters": output / "a-parameters.private.json",
                    "context": fresh.Path(self.slots[0]["contextPath"]),
                    "handoff": self.handoff_path, "source": fresh.Path(fresh.__file__).resolve(),
                    "base-template": fresh.ROOT / "msdn-main.json",
                    "gatefile": self.azure.gate_path,
                    "capture": fresh.Path(self.gate["preparedInputsPath"]),
                }

                def changed_read(path):
                    raw = original_read(path)
                    return raw + b" " if changed[0] and path == paths.get(target) else raw

                def check_with_drift():
                    if changed[0] and target == "gate":
                        self.gate["deploymentApproved"] = False
                    if changed[0] and target == "quote":
                        self.gate["prices"]["A"]["computePerHour"] += .001
                    if changed[0] and target == "token":
                        self.azure.token_changes["A"] = {"accessToken": ""}
                    if changed[0] and target == "lease":
                        lease = fresh.read(self.lease_path)
                        lease["allowedMutations"].append("unapproved")
                        fresh.atomic_json(self.lease_path, lease)

                roots = self.azure.roots
                with patch.object(self.azure, "cli", side_effect=simulate_drift), \
                        patch.object(fresh.Path, "read_bytes", changed_read), \
                        patch.object(self.azure, "roots", side_effect=lambda *a, **kw:
                                     (check_with_drift(), roots(*a, **kw))[1]):
                    with self.assertRaises(fresh.Blocked):
                        self.run_deploy(output)
                self.assertTrue(changed[0])
                self.assertFalse(any(e[2] and e[2].startswith("deploy-") for e in self.azure.events))
                self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 6)
                self.gate = copy.deepcopy(original_gate)
                for slot in self.slots:
                    fresh.state_path(slot).unlink(missing_ok=True)

    def test_rejected_redeployment_preserves_all_existing_evidence_bytes(self):
        self.run_deploy()
        paths = [fresh.Path(s[k]) for s in self.slots for k in ("inventoryPath", "contextPath")]
        paths += [fresh.state_path(s) for s in self.slots]
        paths += list((self.work / "deployment").glob("*.json"))
        before = {p: p.read_bytes() for p in paths}
        gate_path = self.work / "approved-gate.json"
        fresh.write(gate_path, self.gate)
        for failure in ("existing-output", "existing-inventory", "bad-approval"):
            with self.subTest(failure=failure):
                self.save_lease()
                gate = copy.deepcopy(self.gate)
                if failure == "bad-approval":
                    gate["deploymentApproved"] = False
                fresh.write(gate_path, gate)
                output = self.work / ("deployment" if failure == "existing-output" else "new-attempt")
                with patch.object(fresh, "Azure", return_value=FakeAzure(
                        self.config, fresh.Lease(self.lease_path, "deploy"))) as factory, \
                        patch.object(fresh, "verify_prices"), patch("sys.stderr", new=io.StringIO()):
                    result = fresh.main(["deploy", "--handoff", str(self.handoff_path),
                                         "--gate", str(gate_path), "--lease", str(self.lease_path),
                                         "--output", str(output)])
                self.assertEqual(result, 2)
                self.assertEqual(factory.return_value.created_groups, {})
                self.assertFalse(any(e[2] for e in factory.return_value.events))
                for path, raw in before.items():
                    self.assertEqual(path.read_bytes(), raw)

    def test_failed_new_attempt_checkpoints_only_newly_verified_groups(self):
        gate_path = self.work / "approved-gate.json"
        fresh.write(gate_path, self.gate)
        self.azure.fail_validation = True
        with patch.object(fresh, "Azure", return_value=self.azure), patch.object(fresh, "verify_prices"), \
                patch("sys.stderr", new=io.StringIO()):
            result = fresh.main(["deploy", "--handoff", str(self.handoff_path), "--gate", str(gate_path),
                                 "--lease", str(self.lease_path), "--output", str(self.work / "failure")])
        self.assertEqual(result, 2)
        self.assertEqual(set(self.azure.created_groups), {"a"})
        self.assertFalse(any(fresh.Path(s["inventoryPath"]).exists() for s in self.slots))
        snapshots = list((self.work / "failure").glob("*-blocked-*.private.json"))
        self.assertEqual(len(snapshots), 1)
        self.assertTrue(fresh.read(snapshots[0])["createdThisInvocation"])

    def test_inventory_conflicts_and_failed_refresh_cannot_clobber_ready_bytes(self):
        self.run_deploy()
        slot = self.slots[0]
        path = fresh.Path(slot["inventoryPath"])
        raw = path.read_bytes()
        with self.assertRaisesRegex(fresh.Blocked, "Inventory conflict"):
            fresh.save_inventory(self.azure, slot, fresh.read_state(slot), restore=True)
        self.assertEqual(path.read_bytes(), raw)
        self.azure.items["A"].append({"id": "unowned"})
        with self.assertRaises(fresh.Blocked):
            fresh.save_inventory(self.azure, slot, fresh.read_state(slot), restore=True)
        self.assertEqual(path.read_bytes(), raw)

    def test_arm_cli_uses_exclusive_approved_byte_snapshots_for_both_backends(self):
        azure = fresh.Azure(self.config, self.lease)
        azure.handoff_path = self.handoff_path
        azure.approval = fresh.ApprovedInputs(azure, self.slots, self.gate)
        output = self.work / "submission-test"
        output.mkdir()
        azure.attempt_output = output
        azure.approval.materialize(output)
        commands = []

        def popen(command, **kwargs):
            commands.append(command)
            slot = self.slots[2] if command[0] == "wsl.exe" else self.slots[0]
            if "get-access-token" in command:
                result = arm_token(slot)
            elif "account" in command:
                result = {"id": slot["subscriptionId"], "tenantId": slot["tenantId"], "state": "Enabled"}
            else:
                result = {}
            process = Mock(returncode=0)
            process.poll.return_value = 0
            process.communicate.return_value = (json.dumps(result).encode(), b"")
            return process

        def prefix(slot, config):
            return config["msdnCliArgvPrefix"] if slot["slot"] == "T" else ["installed-python", "-m", "azure.cli"]

        with patch.object(fresh.subprocess, "Popen", side_effect=popen), \
                patch.object(fresh, "cli_prefix", side_effect=prefix):
            for slot in (self.slots[0], self.slots[2]):
                alias = slot["slot"].lower()
                azure.cli(slot, ["deployment", "group", "validate", "--template-file",
                                 fresh.arm_file(slot, output / "single-vm.private.json"),
                                 "--parameters", "@" + fresh.arm_file(
                                     slot, output / (alias + "-parameters.private.json"))],
                          operation="validate-" + alias)
        submissions = [c for c in commands if "validate" in c]
        self.assertEqual(len(submissions), 2)
        for command, slot in zip(submissions, (self.slots[0], self.slots[2])):
            template = command[command.index("--template-file") + 1]
            params = command[command.index("--parameters") + 1]
            self.assertIn("submission-", template)
            self.assertIn("submission-", params)
            self.assertTrue(params.startswith("@"))
            self.assertNotIn("AAAA", " ".join(command))
        copies = list(output.glob("submission-*"))
        self.assertEqual(len(copies), 2)
        for directory in copies:
            self.assertEqual((directory / "template.json").read_bytes(), azure.approval.template)
        self.assertEqual({(d / "parameters.json").read_bytes() for d in copies},
                         {azure.approval.parameters[a] for a in ("a", "t")})
        self.assertEqual(fresh.read(self.lease_path)["actualToolCalls"], 6)

    def test_failure_after_ready_exports_preserves_their_exact_bytes(self):
        gate_path = self.work / "approved-gate.json"
        fresh.write(gate_path, self.gate)
        original_get, original_write = self.azure.get, fresh.exclusive_json
        ready = {}

        def fail_last_pip(slot, resource, *args, **kwargs):
            if slot["slot"] == "T" and "/publicipaddresses/" in resource.lower():
                raise fresh.Blocked("Synthetic post-export failure")
            return original_get(slot, resource, *args, **kwargs)

        def record(path, value):
            original_write(path, value)
            if value.get("ready") is True:
                ready[fresh.Path(path)] = fresh.Path(path).read_bytes()

        with patch.object(fresh, "Azure", return_value=self.azure), patch.object(fresh, "verify_prices"), \
                patch.object(self.azure, "get", side_effect=fail_last_pip), \
                patch.object(fresh, "exclusive_json", side_effect=record), \
                patch("sys.stderr", new=io.StringIO()):
            result = fresh.main(["deploy", "--handoff", str(self.handoff_path), "--gate", str(gate_path),
                                 "--lease", str(self.lease_path), "--output", str(self.work / "late-failure")])
        self.assertEqual(result, 2)
        self.assertEqual(len(ready), 3)
        for path, raw in ready.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(len(list((self.work / "late-failure").glob("*-blocked-*.private.json"))), 3)

    def test_unknown_group_creation_never_claims_success_or_exports_inventory(self):
        gate_path = self.work / "approved-gate.json"
        fresh.write(gate_path, self.gate)
        cli = self.azure.cli

        def fail_create(slot, arguments, operation=None, **kwargs):
            if operation == "create-group-a":
                self.azure.before_mutation(slot)
                self.lease.reserve(operation)
                raise fresh.Blocked("Synthetic unknown PUT outcome")
            return cli(slot, arguments, operation, **kwargs)

        with patch.object(fresh, "Azure", return_value=self.azure), patch.object(fresh, "verify_prices"), \
                patch.object(self.azure, "cli", side_effect=fail_create), \
                patch("sys.stderr", new=io.StringIO()):
            result = fresh.main(["deploy", "--handoff", str(self.handoff_path), "--gate", str(gate_path),
                                 "--lease", str(self.lease_path), "--output", str(self.work / "unknown-create")])
        self.assertEqual(result, 2)
        self.assertFalse(self.azure.created_groups)
        self.assertEqual(set(self.azure.creation_intents), {"a"})
        self.assertFalse(fresh.read_state(self.slots[0])["createdVerified"])
        self.assertFalse(any(fresh.Path(s["inventoryPath"]).exists() for s in self.slots))
        self.assertFalse(list((self.work / "unknown-create").glob("*-blocked-*.private.json")))

    def test_cleanup_extra_resource_blocks_all_deletes(self):
        self.run_deploy()
        self.lease_data.update(action="preview-cleanup", actualToolCalls=0, actualMutations=0, maxMutations=0)
        self.save_lease()
        self.azure.lease = fresh.Lease(self.lease_path, "preview-cleanup")
        self.azure.items["T"].append({"id": fresh.group_id(self.slots[2]) + "/providers/Unknown/unknown/x"})
        with self.assertRaisesRegex(fresh.Blocked, "Unknown"):
            fresh.cleanup(self.azure, self.slots, False)
        self.assertFalse(any(e[2] and e[2].startswith("delete") for e in self.azure.events))

    def test_cleanup_unknown_external_binding_blocks_without_external_get(self):
        self.run_deploy()
        slot = self.slots[0]
        original_get = self.azure.get
        seen = []

        def changed(s, resource, *args, **kwargs):
            seen.append(resource)
            result = original_get(s, resource, *args, **kwargs)
            if "/virtualnetworks/" in resource.lower():
                result["properties"]["subnets"][0]["properties"]["networkSecurityGroup"]["id"] = "unknown-external-nsg"
            return result

        self.lease_data.update(action="preview-cleanup", actualToolCalls=0, actualMutations=0, maxMutations=0)
        self.save_lease()
        self.azure.lease = fresh.Lease(self.lease_path, "preview-cleanup")
        with patch.object(self.azure, "get", side_effect=changed):
            with self.assertRaisesRegex(fresh.Blocked, "Unknown subnet attachment"):
                fresh.cleanup(self.azure, self.slots, False)
        self.assertNotIn("unknown-external-nsg", seen)

    def test_native_wsl_argv_and_timeout_child_cleanup(self):
        azure = fresh.Azure(self.config, self.lease)
        process = Mock()
        process.communicate.return_value = (b"{}", b"")
        process.returncode = 0
        process.poll.return_value = 0
        with patch.object(fresh.subprocess, "Popen", return_value=process) as popen:
            azure.cli(self.slots[2], ["account", "show"])
            args = popen.call_args.args[0]
            self.assertEqual(args[:5], ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "/usr/bin/timeout"])
            self.assertIn("/usr/bin/az", args)
            self.assertIn("--subscription", args)
            self.assertNotIn("set", args)
            self.assertLessEqual(process.communicate.call_args.kwargs["timeout"], 120)
        elapsed = [0]

        def timeout(**kwargs):
            elapsed[0] += kwargs["timeout"]
            raise subprocess.TimeoutExpired("fake", kwargs["timeout"])

        process.communicate.side_effect = timeout
        with patch.object(fresh.subprocess, "Popen", return_value=process), \
                patch.object(fresh, "cli_prefix", return_value=["fake-python"]), \
                patch.object(fresh.time, "monotonic", side_effect=lambda: elapsed[0]), \
                patch.object(fresh, "kill_tree") as kill:
            with self.assertRaisesRegex(fresh.Blocked, "timeout"):
                azure.cli(self.slots[0], ["account", "show"])
            kill.assert_called_once_with(process)
        self.assertTrue(fresh.read(self.lease_path)["ownedProcessesIdle"])
        bad = copy.deepcopy(self.config)
        bad["msdnCliArgvPrefix"][-1] = "/mnt/c/az.cmd"
        with self.assertRaises(fresh.Blocked):
            fresh.cli_prefix(self.slots[2], bad)

    def test_rest_scope_boundary_and_no_inline_public_key(self):
        azure = fresh.Azure(self.config, self.lease)
        with patch.object(azure, "cli"):
            with self.assertRaises(fresh.Blocked):
                azure.get(self.slots[0], fresh.group_id(self.slots[0]) + "-old")
        self.run_deploy()
        for _, argv, operation in self.azure.events:
            self.assertNotIn("AAAA", " ".join(argv))
            if operation and operation.startswith(("deploy-", "validate-")):
                self.assertTrue(argv[argv.index("--parameters") + 1].startswith("@"))

    def test_poll_interval_progress_and_stop_before_next_get(self):
        azure = fresh.Azure(self.config, self.lease)
        clock = [CLOCK]

        def sleep(seconds):
            self.assertGreaterEqual(seconds, 30)
            clock[0] += timedelta(seconds=seconds)

        with patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                patch.object(fresh.time, "sleep", side_effect=sleep), \
                patch.object(azure, "get", side_effect=[
                    {"properties": {"provisioningState": "Running"}},
                    {"properties": {"provisioningState": "Succeeded"}}]) as get:
            azure.poll(self.slots[0], fresh.group_id(self.slots[0]), fresh.DEPLOY_API, "deployment")
            self.assertEqual(get.call_count, 2)
        clock[0] = CLOCK

        def stop(seconds):
            (self.work / "STOP").write_text("stop", encoding="utf-8")
            sleep(seconds)

        with patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                patch.object(fresh.time, "sleep", side_effect=stop), \
                patch.object(azure, "get", return_value={"properties": {"provisioningState": "Running"}}) as get:
            with self.assertRaisesRegex(fresh.Blocked, "STOP"):
                azure.poll(self.slots[0], fresh.group_id(self.slots[0]), fresh.DEPLOY_API, "deployment")
            self.assertEqual(get.call_count, 1)

    def test_no_progress_poll_has_bounded_deadline(self):
        azure = fresh.Azure(self.config, self.lease)
        clock = [CLOCK]
        with patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                patch.object(fresh.time, "sleep",
                             side_effect=lambda seconds: clock.__setitem__(0, clock[0] + timedelta(seconds=seconds))), \
                patch.object(azure, "get", return_value={"properties": {"provisioningState": "Running"}}) as get:
            with self.assertRaisesRegex(fresh.Blocked, "No progress"):
                azure.poll(self.slots[0], fresh.group_id(self.slots[0]), fresh.DEPLOY_API, "deployment")
            self.assertLessEqual(get.call_count, 21)

    def test_cli_failure_does_not_echo_private_payload(self):
        azure = fresh.Azure(self.config, self.lease)
        process = Mock()
        process.communicate.return_value = (b"", b"opaque-private-service-url-and-identifiers")
        process.returncode = 1
        process.poll.return_value = 1
        with patch.object(fresh.subprocess, "Popen", return_value=process):
            with self.assertRaises(fresh.Blocked) as caught:
                azure.cli(self.slots[2], ["account", "show"])
        self.assertNotIn("opaque-private", str(caught.exception))

    def probe_command_timeout(self, slot, arguments, diagnostic=None):
        azure = fresh.Azure(self.config, self.lease)
        elapsed = [0]
        process = Mock()

        def communicate(timeout):
            self.assertLessEqual(timeout, 2)
            elapsed[0] += timeout
            raise subprocess.TimeoutExpired("private arguments", timeout)

        process.communicate.side_effect = communicate
        with patch.object(fresh.subprocess, "Popen", return_value=process) as popen, \
                patch.object(fresh, "cli_prefix", return_value=["fake"]), \
                patch.object(fresh.time, "monotonic", side_effect=lambda: elapsed[0]), \
                patch.object(fresh, "kill_tree") as kill:
            with self.assertRaisesRegex(fresh.Blocked, "timeout"):
                azure.cli(slot, arguments, diagnostic=diagnostic)
            popen.assert_called_once()
            kill.assert_called_once_with(process)
        self.assertEqual(fresh.read(self.lease_path)["actualToolCalls"], 1)
        self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)
        return elapsed[0], popen.call_args.args[0]

    def test_ordinary_and_unnamed_catalog_stay_at_120_with_allowances(self):
        for arguments in (["account", "show"], fresh.catalog_arguments(self.slots[0]),
                          ["deployment", "group", "show"]):
            with self.subTest(arguments=arguments):
                self.lease_data.update(commandTimeoutSeconds=1200,
                                       namedCommandTimeoutSeconds=dict.fromkeys(fresh.CATALOG_NAMES, 600))
                self.save_lease()
                elapsed, _ = self.probe_command_timeout(self.slots[0], arguments)
                self.assertEqual(elapsed, 120)

    def test_all_exact_named_catalogs_get_600_and_safe_progress(self):
        for slot in self.slots:
            diagnostic = "catalog-" + slot["slot"].lower()
            with self.subTest(diagnostic=diagnostic):
                self.lease_data.update(commandTimeoutSeconds=1200,
                                       namedCommandTimeoutSeconds=dict.fromkeys(fresh.CATALOG_NAMES, 600))
                self.save_lease()
                elapsed, argv = self.probe_command_timeout(slot, fresh.catalog_arguments(slot), diagnostic)
                self.assertEqual(elapsed, 600)
                if slot["slot"] == "T":
                    self.assertIn("590s", argv)
                    self.assertIn("--kill-after=5s", argv)
                progress = fresh.read(self.lease_path)
                self.assertEqual(progress["currentCommand"], diagnostic)
                self.assertEqual(progress["lastCommandKind"], "diagnostic-readonly")
                self.assertEqual(progress["lastRole"], "Tank")
                self.assertTrue(progress["ownedProcessesIdle"])

    def test_catalog_timeout_requires_allowance_and_obeys_lease_and_remaining_time(self):
        for command_limit, remaining, named, expected in (
                (1200, 3600, {}, 120),
                (120, 3600, {"catalog-a": 600}, 120),
                (1200, 300, {"catalog-a": 600}, 300),
                (1200, 3600, {"catalog-a": 240}, 240)):
            with self.subTest(command_limit=command_limit, remaining=remaining, named=named):
                self.lease_data.update(commandTimeoutSeconds=command_limit, namedCommandTimeoutSeconds=named,
                                       expiresAtUtc=(CLOCK + timedelta(seconds=remaining)).isoformat())
                self.save_lease()
                elapsed, _ = self.probe_command_timeout(
                    self.slots[0], fresh.catalog_arguments(self.slots[0]), "catalog-a")
                self.assertEqual(elapsed, expected)

    def test_invalid_named_allowances_block_before_launch(self):
        for named in ({"catalog-x": 600}, {"catalog-a": -1}, {"catalog-a": 0},
                      {"catalog-a": 601}, {"catalog-a": 600.0}, {"catalog-a": True},
                      {"catalog-a": "600"}, [], None):
            with self.subTest(named=named):
                self.lease_data["namedCommandTimeoutSeconds"] = named
                self.save_lease()
                with patch.object(fresh.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(fresh.Blocked, "named command timeout"):
                        fresh.Azure(self.config, self.lease).cli(self.slots[0], ["account", "show"])
                    popen.assert_not_called()

    def test_named_catalog_rejects_wrong_arguments_slot_sku_and_mutation_authority(self):
        exact = fresh.catalog_arguments(self.slots[0])
        bad_sku = dict(self.slots[0], sku="Standard_B2s")
        bad_region = dict(self.slots[0], region="westus")
        for slot, arguments, diagnostic, operation in (
                (self.slots[0], exact + ["--extra"], "catalog-a", None),
                (self.slots[0], exact, "catalog-c", None),
                (self.slots[0], exact, "catalog-x", None),
                (self.slots[1], exact, "catalog-c", None),
                (bad_sku, exact, "catalog-a", None),
                (bad_region, exact, "catalog-a", None),
                (self.slots[0], ["account", "show"], "catalog-a", None),
                (self.slots[0], exact, "catalog-a", "create-group-a")):
            with self.subTest(slot=slot["slot"], diagnostic=diagnostic, arguments=arguments):
                with patch.object(fresh.subprocess, "Popen") as popen:
                    with self.assertRaises(fresh.Blocked):
                        fresh.Azure(self.config, self.lease).cli(
                            slot, arguments, diagnostic=diagnostic, operation=operation)
                    popen.assert_not_called()
        self.assertEqual(fresh.read(self.lease_path)["actualToolCalls"], 0)

    def test_stop_or_expiry_during_communicate_kills_tree_and_blocks(self):
        for guard in ("STOP", "expiry"):
            with self.subTest(guard=guard):
                self.save_lease()
                fresh.STOP.unlink(missing_ok=True)
                clock = [CLOCK]
                process = Mock()

                def communicate(timeout):
                    self.assertEqual(timeout, 2)
                    if guard == "STOP":
                        fresh.STOP.write_text("stop", encoding="utf-8")
                    else:
                        clock[0] += timedelta(minutes=61)
                    raise subprocess.TimeoutExpired("private", timeout)

                process.communicate.side_effect = communicate
                with patch.object(fresh.subprocess, "Popen", return_value=process), \
                        patch.object(fresh, "cli_prefix", return_value=["fake"]), \
                        patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                        patch.object(fresh, "kill_tree") as kill:
                    with self.assertRaisesRegex(fresh.Blocked, "STOP|expired"):
                        fresh.Azure(self.config, self.lease).cli(self.slots[0], ["account", "show"])
                    kill.assert_called_once_with(process)
                self.assertEqual(process.communicate.call_count, 1)
                self.assertEqual(fresh.read(self.lease_path)["actualToolCalls"], 1)
                self.assertTrue(fresh.read(self.lease_path)["ownedProcessesIdle"])
        fresh.STOP.unlink(missing_ok=True)

    def test_repeated_communicate_timeouts_preserve_complete_json_without_duplicate_partials(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        complete = b'[{"name":"Standard_B2ts_v2","restrictions":[]}]'
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("private", 2, output=complete[:10]),
            subprocess.TimeoutExpired("private", 2, output=complete[:30]),
            (complete, b"")]
        with patch.object(fresh.subprocess, "Popen", return_value=process), \
                patch.object(fresh, "cli_prefix", return_value=["fake"]), \
                patch.object(fresh.time, "monotonic", return_value=0), \
                patch.object(fresh, "kill_tree") as kill:
            result = fresh.Azure(self.config, self.lease).cli(
                self.slots[0], fresh.catalog_arguments(self.slots[0]), diagnostic="catalog-a")
        self.assertEqual(result, json.loads(complete))
        self.assertEqual(process.communicate.call_count, 3)
        kill.assert_called_once_with(process)
        self.assertEqual(fresh.read(self.lease_path)["actualToolCalls"], 1)

    def test_named_allowances_are_immutable_but_safe_diagnostic_progress_is_not(self):
        self.lease_data["namedCommandTimeoutSeconds"] = dict.fromkeys(fresh.CATALOG_NAMES, 600)
        self.save_lease()
        approval = fresh.ApprovedInputs(self.azure, self.slots, self.gate)
        self.lease.reserve(diagnostic="catalog-a")
        self.lease.idle()
        approval.check()
        lease = fresh.read(self.lease_path)
        lease["namedCommandTimeoutSeconds"]["catalog-a"] = 599
        self.lease.save(lease)
        with self.assertRaisesRegex(fresh.Blocked, "Lease approval fields changed"):
            approval.check()

    def test_identity_and_named_catalog_charge_exactly_three_calls(self):
        self.lease_data.update(commandTimeoutSeconds=1200,
                               namedCommandTimeoutSeconds=dict.fromkeys(fresh.CATALOG_NAMES, 600))
        self.save_lease()
        slot = self.slots[0]
        results = [
            {"id": slot["subscriptionId"], "tenantId": slot["tenantId"], "state": "Enabled"},
            arm_token(slot), [{"name": slot["sku"], "restrictions": []}]]
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.side_effect = [(json.dumps(result).encode(), b"") for result in results]
        azure = fresh.Azure(self.config, self.lease)
        with patch.object(fresh.subprocess, "Popen", return_value=process) as popen, \
                patch.object(fresh, "cli_prefix", return_value=["fake"]):
            azure.identity(slot)
            self.assertEqual(azure.cli(slot, fresh.catalog_arguments(slot), diagnostic="catalog-a"), results[2])
        self.assertEqual(popen.call_count, 3)
        lease = fresh.read(self.lease_path)
        self.assertEqual(lease["actualToolCalls"], 3)
        self.assertEqual(lease["actualMutations"], 0)
        self.assertEqual(lease["currentCommand"], "catalog-a")
        self.assertNotIn("accessToken", json.dumps(lease))

    def test_first_group_runway_is_rechecked_after_fresh_mutation_identity(self):
        azure = fresh.Azure(self.config, self.lease)
        clock = [CLOCK]

        def identity_checks(*args):
            clock[0] += timedelta(minutes=36)

        with patch.object(azure, "before_mutation", side_effect=identity_checks), \
                patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                patch.object(fresh.subprocess, "Popen") as popen:
            self.lease.creation_runway()
            with self.assertRaisesRegex(fresh.Blocked, "runway"):
                azure.cli(self.slots[0], ["group", "create"], operation="create-group-a")
            popen.assert_not_called()
        self.assertEqual(fresh.read(self.lease_path)["actualMutations"], 0)

    def test_slow_catalogs_require_runway_before_any_group_or_ownership_intent(self):
        for catalog_seconds, overhead_seconds, succeeds in ((600, 0, True), (600, 80, True),
                                                          (600, 101, False)):
            with self.subTest(overhead_seconds=overhead_seconds):
                self.save_lease()
                clock = [CLOCK]
                original_cli = self.azure.cli

                def slow_catalog(slot, arguments, **kwargs):
                    result = original_cli(slot, arguments, **kwargs)
                    if arguments[:2] == ["vm", "list-skus"]:
                        clock[0] += timedelta(seconds=catalog_seconds + overhead_seconds)
                    return result

                output = self.work / ("slow-" + str(overhead_seconds))
                with patch.object(fresh, "now", side_effect=lambda: clock[0]), \
                        patch.object(self.azure, "cli", side_effect=slow_catalog):
                    if succeeds:
                        self.run_deploy(output)
                    else:
                        with self.assertRaisesRegex(fresh.Blocked, "runway"):
                            self.run_deploy(output)
                if succeeds:
                    for slot in self.slots:
                        fresh.state_path(slot).unlink()
                        fresh.Path(slot["inventoryPath"]).unlink()
                    self.azure.groups.clear()
                    self.azure.items.clear()
                    self.azure.events.clear()
                    self.azure.creation_intents.clear()
                    self.azure.created_groups.clear()
                else:
                    self.assertEqual(sum(e[1][:2] == ("vm", "list-skus")
                                         for e in self.azure.events), 3)
                    self.assertFalse(any(e[2] for e in self.azure.events))
                    self.assertFalse(self.azure.creation_intents)
                    self.assertFalse(any(fresh.state_path(s).exists() for s in self.slots))


if __name__ == "__main__":
    unittest.main()
