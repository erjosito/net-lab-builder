"""Offline repeat ledger and real runner adapter tests; no Azure calls."""
import copy
import ast
import base64
import contextlib
from datetime import datetime, timedelta, timezone
import json
import io
import itertools
import os
from pathlib import Path
import shutil
import re
import sys
import threading
import unittest
from unittest import mock
import uuid

import repeat
import run
import stream


def fixture():
    current = run.now()
    end = min(current + timedelta(hours=47), repeat.APPROVAL_DEADLINE).isoformat()
    config = {"schema": "bounded-repeat-v1", "createdAtUtc": current.isoformat(),
              "cleanupDeadlineUtc": end,
              "rateBytesPerSecond": stream.MAX_RATE, "contexts": {}, "endpoints": {},
              "approval": {"status": "approved", "issuedAtUtc": current.isoformat(),
                           "expiresAtUtc": end,
                           "applicationBytesPerLeg": repeat.TARGET,
                           "wireCeilingBytes": repeat.WIRE_LIMIT,
                           "totalUsdEquivalentCap": 45, "resourceIds": []}}
    for key, digit, cap in (("core", "1", 23), ("msdn", "2", 22)):
        config["contexts"][key] = {
            "subscriptionId": digit * 8 + "-" + digit * 4 + "-" + digit * 4
                              + "-" + digit * 4 + "-" + digit * 12,
            "expectedTenantId": str(int(digit) + 2) * 8 + "-" + digit * 4 + "-" + digit * 4
                                + "-" + digit * 4 + "-" + digit * 12,
            "platform": "windows_native_cli",
            "preflight": {"validated": True, "evidenceReference": "OFFLINE-TEST-NOT-AUTHORITY",
                          "validatedAtUtc": current.isoformat(),
                          "validUntilUtc": end,
                          "currency": "USD", "currencyCap": cap, "usdEquivalentCap": cap,
                          "txPerDecimalGB": ".02", "vmPerHour": ".01",
                          "fixedInfraReserve": "1.00"}}
    kinds = (("vm", "Microsoft.Compute/virtualMachines"),
             ("disk", "Microsoft.Compute/disks"),
             ("nic", "Microsoft.Network/networkInterfaces"),
             ("pip", "Microsoft.Network/publicIPAddresses"),
             ("nsg", "Microsoft.Network/networkSecurityGroups"),
             ("vnet", "Microsoft.Network/virtualNetworks"))
    for alias, region in (("A", "swedencentral"), ("C", "northeurope"), ("T", "swedencentral")):
        cfg = config["contexts"]["msdn" if alias == "T" else "core"]
        run_id = "test-fresh-" + alias.lower()
        group = "/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/rg-" + run_id
        rows = []
        for suffix, kind in kinds:
            name = run_id + "-" + suffix + "-" + alias.lower()
            rows.append({"id": group + "/providers/" + kind + "/" + name, "type": kind,
                         "name": name, "location": region,
                         "tags": {"lab": "true", "created_by": "copilot-lab", "run_id": run_id}})
        config["endpoints"][alias] = {
            "region": region, "publicIPv4": "192.0.2." + str(ord(alias)),
            "inventory": {"runId": run_id, "groupId": group, "resources": rows,
                          "capturedAtUtc": current.isoformat()}}
        config["approval"]["resourceIds"].extend(row["id"] for row in rows)
    return config


class RepeatTests(unittest.TestCase):
    def setUp(self):
        actual_now = run.now
        started = actual_now()
        epoch = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        mock.patch.object(run, "now", side_effect=lambda: epoch + (actual_now() - started)).start()
        self.root = run.LAB / "private" / ("repeat-unit-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.directory = self.root / "fresh"
        self.config = fixture()
        self.azure = mock.patch.object(run.Azure, "_invoke", autospec=True,
                                       side_effect=AssertionError("Azure forbidden offline")).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(lambda: shutil.rmtree(self.root))
        self.cert = mock.patch.object(run, "certificates").start()
        self.digest = mock.patch.object(stream, "digest", return_value="a" * 64).start()

    def prepare(self):
        repeat.prepare(self.config, self.directory)

    def reserve(self, phase="same-region"):
        return repeat.reserve(self.directory, phase)

    def ledger(self):
        return run.read(self.directory / "ledger.private.json")

    def lease(self, action="pilot", key=None, **values):
        started = run.now()
        key = key or next(reversed(self.ledger()["chunks"]))
        lease = repeat.lease_template(self.directory, key, action)
        lease.update({"taskId": uuid.uuid4().hex, "ownerId": uuid.uuid4().hex,
                 "startedAtUtc": started.isoformat(),
                 "expiresAtUtc": (started + timedelta(minutes=60 if action in
                                  ("pilot", "batch") else 30)).isoformat(),
                 "state": "active", "acceptLiveGates": True,
                 "ownedProcessesIdle": True, "activeCommands": 0,
                 "actualToolCalls": 0, "actualMutations": 0})
        lease.update(values)
        path = self.directory / "control" / (lease["taskId"] + ".json")
        run.save(path, lease)
        return path

    def claim(self, key, lease):
        # Ledger-only fixtures; end-to-end adapter tests below use real readiness gates.
        with mock.patch.object(repeat, "require_prepared_traffic"):
            repeat.claim(self.directory, key, lease)

    def completed_fixture(self, phase="same-region", bulk_seconds=64):
        key = self.reserve(phase)
        current = run.now()
        live_seconds = max(90, bulk_seconds + 26)
        lease_start = current - timedelta(seconds=live_seconds + 120)
        lease_path = self.lease(action="pilot" if self.ledger()["chunks"][key]["index"] == 0
                               else "batch", startedAtUtc=lease_start.isoformat(),
                               expiresAtUtc=(lease_start + timedelta(hours=1)).isoformat())
        with mock.patch.object(run, "guard", return_value=run.read(lease_path)):
            self.claim(key, lease_path)
        lease = run.read(lease_path)
        lease.update(state="completed", actualToolCalls=48, actualMutations=10,
                     startedAtUtc=lease_start.isoformat(),
                     expiresAtUtc=(lease_start + timedelta(hours=1)).isoformat())
        run.save(lease_path, lease)
        chunk_dir = self.directory / "chunks" / key
        plan = run.read(chunk_dir / "plan.private.json")
        plan.update(status="completed", failures=[],
                    live_started=(current - timedelta(seconds=live_seconds)).isoformat(),
                    ended=current.isoformat(), restore_started=current.isoformat(),
                    network_bindings={"id": "/subscriptions/PRIVATE"})
        run.save(chunk_dir / "plan.private.json", plan)
        for alias in run.endpoint_names(plan):
            run.save(chunk_dir / ("deallocate-" + alias.lower() + "-verified.private.json"),
                     {"verified": True, "at": current.isoformat(),
                      "binding": {"id": plan["id"], "endpoint": plan[alias]}})
        run.save(chunk_dir / "nsg-restored.private.json",
                 {"verified": True, "at": current.isoformat()})
        run.save(chunk_dir / "readiness.private.json",
                 {"success": True, "deallocated": {phase_alias: True for phase_alias in
                                                   (repeat.PHASES[phase], "T")},
                  "started_at": (current - timedelta(seconds=live_seconds + 60)).isoformat(),
                  "completed_at": (current - timedelta(seconds=live_seconds + 30)).isoformat()})
        alias = repeat.PHASES[phase]
        report = {"success": True, "declared_legs": ["up", "down"],
                  "aliases": {"client": alias, "server": "T"}, "requests": 2, "legs": {},
                  "nic": {"delta": {"rx": plan["bytes"] + 100, "tx": plan["bytes"] + 100,
                                    "wire_once": plan["bytes"] * 2 + 200}}}
        for leg, producer, consumer in (("up", alias, "T"), ("down", "T", alias)):
            report["legs"][leg] = {
                "id": plan["id"] + "-" + leg, "producer": producer, "consumer": consumer,
                "bytes": plan["bytes"], "sha256": plan["payload_sha256"], "status": "ok",
                "retries": 0, "started": (current - timedelta(seconds=bulk_seconds)).isoformat(),
                "ended": current.isoformat()}
        for role in ("client", "server"):
            run.save(chunk_dir / (role + "-report.private.json"), report)
        for endpoint in (alias, "T"):
            run.save(chunk_dir / (endpoint + "-metrics-after.private.json"),
                     {"value": [{"id": "/subscriptions/PRIVATE", "name": {"value": "Network In Total"},
                                 "timeseries": [{"data": [
                                     {"timeStamp": current.isoformat(), "total": 12}]}]}]})
        return key

    def test_exact_decimal_pilot_and_remainder(self):
        sizes = repeat.chunk_sizes()
        self.assertEqual(len(sizes), 20)
        self.assertEqual(sizes, [stream.GIB] + [5 * stream.GIB] * 18 + [2_289_494_016])
        self.assertEqual(sum(sizes), 100_000_000_000)
        self.assertEqual(sum(repeat.chunk_sizes(stream.GIB)), repeat.TARGET)
        self.assertEqual(sum(repeat.chunk_sizes(stream.GIB)) % stream.GIB, 142_010_368)
        for value in (0, stream.GIB - 1, stream.MAX_BYTES + 1, True, 1.5):
            with self.assertRaises(RuntimeError):
                repeat.chunk_sizes(value)

    @unittest.skipUnless(os.name == "nt", "Windows metadata sharing semantics")
    def test_metadata_replace_transient_windows_denials_then_success(self):
        path = self.root / "metadata.json"
        replace = os.replace
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                run.save(path, {"old": True})
                error = PermissionError("metadata temporarily held")
                error.winerror = code
                failures = [error]

                def replace_once(source, target):
                    if failures:
                        raise failures.pop()
                    return replace(source, target)

                with mock.patch.object(repeat.os, "replace", side_effect=replace_once) as rename, \
                        mock.patch.object(repeat.time, "sleep") as sleep:
                    repeat.atomic(path, {"new": True})
                self.assertEqual(rename.call_count, 2)
                sleep.assert_called_once_with(.025)
                self.assertEqual(run.read(path), {"new": True})
                self.assertFalse(list(self.root.glob("*.pending")))

    @unittest.skipUnless(os.name == "nt", "Windows metadata sharing semantics")
    def test_metadata_replace_permanent_denial_bounded_original_error_old_file_preserved(self):
        path = self.root / "metadata.json"
        original = b'{"old": true}\n'
        path.write_bytes(original)
        first = PermissionError("original metadata denial")
        first.winerror = 32
        later = PermissionError("later metadata denial")
        later.winerror = 5
        with mock.patch.object(repeat.os, "replace", side_effect=[first] + [later] * 40) as rename, \
                mock.patch.object(repeat.time, "monotonic", return_value=10), \
                mock.patch.object(repeat.time, "sleep") as sleep:
            with self.assertRaises(PermissionError) as raised:
                repeat.atomic(path, {"new": True})
        self.assertIs(raised.exception, first)
        self.assertEqual(rename.call_count, 41)
        self.assertEqual(sleep.call_count, 40)
        self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), 1.000001)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(list(self.root.glob("*.pending")))

    @unittest.skipUnless(os.name == "nt", "Windows metadata sharing semantics")
    def test_metadata_replace_deadline_exhaustion_preserves_atomic_old_file(self):
        path = self.root / "metadata.json"
        run.save(path, {"old": True})
        error = PermissionError("metadata held past deadline")
        error.winerror = 33
        with mock.patch.object(repeat.os, "replace", side_effect=error) as rename, \
                mock.patch.object(repeat.time, "monotonic", side_effect=[10, 10, 11]), \
                mock.patch.object(repeat.time, "sleep") as sleep:
            with self.assertRaises(PermissionError) as raised:
                repeat.atomic(path, {"new": True})
        self.assertIs(raised.exception, error)
        self.assertEqual(rename.call_count, 2)
        sleep.assert_called_once_with(.025)
        self.assertEqual(run.read(path), {"old": True})
        self.assertFalse(list(self.root.glob("*.pending")))

    def test_metadata_replace_other_os_errors_fail_immediately(self):
        path = self.root / "metadata.json"
        for code in (None, 2, 19, 87):
            with self.subTest(winerror=code):
                run.save(path, {"old": True})
                error = OSError("not a transient metadata sharing error")
                if code is not None:
                    error.winerror = code
                with mock.patch.object(repeat.os, "replace", side_effect=error) as rename, \
                        mock.patch.object(repeat.time, "sleep") as sleep:
                    with self.assertRaises(OSError) as raised:
                        repeat.atomic(path, {"new": True})
                self.assertIs(raised.exception, error)
                rename.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(run.read(path), {"old": True})
                self.assertFalse(list(self.root.glob("*.pending")))

    def continuation_fixture(self):
        self.prepare()
        for phase in repeat.PHASES:
            key = self.completed_fixture(phase)
            repeat.finish(self.directory, key)
            ledger = self.ledger()
            chunk = ledger["chunks"][key]
            chunk["phases"] = {}
            for action in ("readiness", "snapshot"):
                lease = run.read(chunk["lease_path"])
                lease.update(taskId=uuid.uuid4().hex, maxToolCalls=75,
                             maxMutations=6, actualMutations=4)
                path = self.directory / "control" / (lease["taskId"] + ".json")
                run.save(path, lease)
                chunk["phases"][action] = {"taskId": lease["taskId"],
                    "lease_path": str(path), "lease_hash": repeat.identity(lease)}
            run.save(self.directory / "ledger.private.json", ledger)
        config = copy.deepcopy(self.config)
        config["continuation"] = repeat.certify_predecessor(self.directory)
        config["allocatedSecondsPerVm"] = 57600
        config["approval"].update(allocatedSecondsPerVm=57600,
            evidenceReference="OFFLINE-COORDINATOR-DECISION-NOT-USER-CHOICE",
            continuationHash=repeat.identity(config["continuation"]))
        return config, self.root / "successor"

    def test_continuation_preserves_progress_wire_allocation_and_next_index(self):
        config, successor = self.continuation_fixture()
        manifest = repeat.evidence_manifest(self.directory)
        old = self.ledger()
        repeat.prepare(config, successor)
        _, ledger = repeat.load(successor)
        for field in ("chunks", "wire_reserved", "wire_measured", "allocated_seconds",
                      "prior_allocated_seconds", "money_reserved"):
            self.assertEqual(ledger[field], old[field])
        summary = repeat.status(successor)
        self.assertEqual(summary["allocated_seconds_per_vm"], 57600)
        self.assertEqual(set(summary["progress_application_bytes"].values()), {stream.GIB})
        self.assertEqual(repeat.reserve(successor, "same-region"), "same-region-001")
        next_plan = run.read(successor / "chunks" / "same-region-001" / "plan.private.json")
        self.assertEqual(next_plan["bytes"], 5 * stream.GIB)
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)
        self.assertEqual(repeat.status(successor)["progress_application_bytes"],
                         summary["progress_application_bytes"])
        self.assertEqual(ledger["wire_reserved"], repeat.BOOTSTRAP + 2 * repeat.wire_reserve(stream.GIB))
        self.assertEqual(sum(repeat.chunk_sizes()), repeat.TARGET)
        self.assertFalse(list((successor / "control").iterdir()))

    def renewal_fixture(self, recovery=False):
        old_expiry = (run.now() + timedelta(minutes=2)).isoformat()
        self.config["approval"]["expiresAtUtc"] = old_expiry
        for context in self.config["contexts"].values():
            context["preflight"]["validUntilUtc"] = old_expiry
        config, successor = (self.recovery_fixture()[:2] if recovery
                             else self.continuation_fixture())
        current = run.now() + timedelta(minutes=5)
        mock.patch.object(run, "now", return_value=current).start()
        contexts = copy.deepcopy(config["contexts"])
        endpoints = copy.deepcopy(config["endpoints"])
        evidence = {}
        for key, context in contexts.items():
            path = self.root / (key + "-readonly-evidence.private.json")
            run.save(path, {"context": key, "result": "OFFLINE-NOT-AUTHORITY"})
            evidence[str(path)] = repeat.hashlib.sha256(path.read_bytes()).hexdigest()
            context["preflight"].update(evidenceReference=str(path),
                validatedAtUtc=current.isoformat(), validUntilUtc=config["cleanupDeadlineUtc"])
        for endpoint in endpoints.values():
            endpoint["inventory"]["capturedAtUtc"] = current.isoformat()
        attestation = {
            "schema": "repeat-preflight-renewal-v1", "status": "PASS",
            "validationKind": "independent-read-only", "validatedBy": "offline-validator",
            "validatedAtUtc": current.isoformat(), "validUntilUtc": config["cleanupDeadlineUtc"],
            "predecessorConfigHash": repeat.identity(self.config),
            "contexts": contexts, "endpoints": endpoints, "evidenceHashes": evidence}
        path = self.root / "renewal.private.json"
        run.save(path, attestation)
        binding = {"path": str(path), "sha256": repeat.hashlib.sha256(path.read_bytes()).hexdigest()}
        config.update(contexts=contexts, endpoints=endpoints,
                      allocatedSecondsPerVm=86400)
        config["continuation"] = repeat.certify_predecessor(self.directory, renewal=binding)
        config["approval"].update(allocatedSecondsPerVm=86400,
            issuedAtUtc=current.isoformat(), preflightRenewalHash=binding["sha256"],
            expiresAtUtc=config["cleanupDeadlineUtc"],
            continuationHash=repeat.identity(config["continuation"]))
        return config, successor, binding

    def test_renewal_conserves_recovery_identity_counters_sources_and_no_fork(self):
        config, successor, binding = self.renewal_fixture(recovery=True)
        original = self.ledger()
        manifest = repeat.evidence_manifest(self.directory)
        repeat.prepare(config, successor)
        _, ledger = repeat.load(successor)
        for field in ("chunks", "wire_reserved", "wire_measured", "money_reserved",
                      "allocated_seconds", "prior_allocated_seconds", "leases", "owners"):
            self.assertEqual(ledger[field], original[field])
        self.assertEqual(ledger["sources"], repeat.sources())
        self.assertEqual(config["continuation"]["successor_sources"], repeat.sources())
        self.assertEqual(config["continuation"]["sources"], original["sources"])
        self.assertEqual(repeat.slot_seconds(config), 86400)
        self.assertEqual(repeat.wire_limit(config), 460_000_000_000)
        self.assertEqual(repeat.BOOTSTRAP, 8_000_000_000)
        self.assertEqual(repeat.TARGET, 100_000_000_000)
        self.assertEqual(config["cleanupDeadlineUtc"], self.config["cleanupDeadlineUtc"])
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)
        with self.assertRaises(FileExistsError):
            repeat.prepare(config, self.root / "renewal-fork")
        ledger_path = successor / "ledger.private.json"
        for field, key in (("wire_reserved", None), ("wire_measured", None),
                           ("money_reserved", "core"), ("allocated_seconds", "T")):
            changed = copy.deepcopy(ledger)
            if key is None:
                changed[field] -= 1
            elif field == "money_reserved":
                changed[field][key] = str(repeat.number(changed[field][key]) - 1)
            else:
                changed[field][key] -= 1
            run.save(ledger_path, changed)
            with self.subTest(counter=field), self.assertRaises(RuntimeError):
                repeat.load(successor)
        run.save(ledger_path, ledger)
        self.assertEqual(repeat.reserve(successor, "same-region"), "same-region-001-recovery-1")
        self.azure.assert_not_called()

    def test_renewal_rejects_immutable_and_approval_field_tampers_before_claim(self):
        config, successor, _ = self.renewal_fixture()
        changes = [
            lambda c: c["approval"].pop("preflightRenewalHash"),
            lambda c: c["approval"].update(preflightRenewalHash="0" * 64),
            lambda c: c["approval"].update(status="pending"),
            lambda c: c["continuation"]["successor_sources"].update(repeat="0" * 64),
            lambda c: c.update(createdAtUtc=run.now().isoformat()),
            lambda c: c.update(cleanupDeadlineUtc="2026-10-18T07:32:00Z"),
            lambda c: c.update(rateBytesPerSecond=stream.MAX_RATE - 1),
            lambda c: c.update(chunkBytes=stream.GIB),
            lambda c: c.update(priorAllocatedSeconds={"A": 0, "C": 0, "T": 0}),
            lambda c: c["approval"].update(applicationBytesPerLeg=repeat.TARGET + 1),
            lambda c: c["contexts"]["core"]["preflight"].update(currency="EUR"),
            lambda c: c["contexts"]["core"]["preflight"].update(txPerDecimalGB=".03"),
            lambda c: c["endpoints"]["A"].update(publicIPv4="192.0.2.99"),
            lambda c: c["endpoints"]["A"]["inventory"]["resources"][0].update(sku="changed"),
        ]
        for change in changes:
            candidate = copy.deepcopy(config)
            change(candidate)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                repeat.prepare(candidate, successor)
            self.assertFalse(successor.exists())
            claim = self.root / ".continuation-claims" / repeat.identity(str(self.directory.resolve()))
            self.assertFalse(claim.exists())

    def test_renewal_rejects_forged_or_relabelled_attestation_even_when_rehashed(self):
        config, successor, binding = self.renewal_fixture()
        path = Path(binding["path"])
        original = path.read_bytes()
        valid = run.read(path)
        changes = [
            lambda a: a.update(status="FAIL"),
            lambda a: a.update(validationKind="self-certified"),
            lambda a: a.update(predecessorConfigHash="0" * 64),
            lambda a: a.update(evidenceHashes={}),
            lambda a: a["evidenceHashes"].update({next(iter(a["evidenceHashes"])): "0" * 64}),
            lambda a: a["contexts"]["core"]["preflight"].update(
                validatedAtUtc=self.config["contexts"]["core"]["preflight"]["validatedAtUtc"]),
            lambda a: a["contexts"]["core"]["preflight"].update(
                evidenceReference="UNBOUND-OLD-VALIDATION"),
            lambda a: a["endpoints"]["A"]["inventory"].update(
                capturedAtUtc=self.config["endpoints"]["A"]["inventory"]["capturedAtUtc"]),
            lambda a: a["contexts"]["core"].update(expectedTenantId="3" * 36),
            lambda a: a["contexts"]["core"]["preflight"].update(vmPerHour=".99"),
            lambda a: a["contexts"]["core"]["preflight"].update(currencyCap=999),
            lambda a: a["endpoints"]["A"]["inventory"]["resources"][0].update(location="northeurope"),
            lambda a: a["endpoints"]["A"]["inventory"]["resources"][0]["tags"].update(run_id="foreign"),
            lambda a: a["endpoints"]["A"]["inventory"]["resources"][0].update(id="/foreign"),
            lambda a: a["endpoints"]["A"]["inventory"]["resources"][0].update(sku="Standard_B99"),
            lambda a: a.update(validUntilUtc=(run.now() - timedelta(seconds=1)).isoformat()),
        ]
        for change in changes:
            attestation = copy.deepcopy(valid)
            change(attestation)
            run.save(path, attestation)
            forged = dict(binding, sha256=repeat.hashlib.sha256(path.read_bytes()).hexdigest())
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                repeat.certify_predecessor(self.directory, renewal=forged)
        path.write_bytes(original)
        run.save(path, dict(valid, status="FAIL"))
        with self.assertRaisesRegex(RuntimeError, "attestation_hash_changed"):
            repeat.prepare(config, successor)

    def test_renewal_expiry_rechecked_but_historical_certification_remains_possible(self):
        config, successor, binding = self.renewal_fixture()
        repeat.prepare(config, successor)
        # A fresh successor is still valid after one hour: no sliding/reissued validation.
        with mock.patch.object(run, "now", return_value=run.now() + timedelta(hours=2)):
            repeat.load(successor)
        expired = repeat.timestamp(config["contexts"]["core"]["preflight"]["validUntilUtc"])
        with mock.patch.object(run, "now", return_value=expired):
            with self.assertRaises(RuntimeError):
                repeat.load(successor)
            with self.assertRaisesRegex(RuntimeError, "fresh_renewal"):
                repeat.certify_predecessor(self.directory, renewal=binding)
            # Recursing over an expired ancestor verifies bytes, not fresh live authority.
            repeat.certify_predecessor(successor)
        evidence = Path(next(iter(run.read(binding["path"])["evidenceHashes"])))
        evidence.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "renewal_evidence_hash_changed"):
            repeat.load(successor)

    def test_renewal_source_drift_and_naked_time_extension_rejected(self):
        config, successor, _ = self.renewal_fixture()
        old = copy.deepcopy(config)
        old["continuation"] = repeat.certify_predecessor(self.directory)
        old["approval"]["continuationHash"] = repeat.identity(old["continuation"])
        with self.assertRaisesRegex(RuntimeError, "may_only_amend_runtime"):
            repeat.prepare(old, successor)
        pins = dict(repeat.sources(), repeat="b" * 64)
        with mock.patch.object(repeat, "sources", return_value=pins):
            with self.assertRaisesRegex(RuntimeError, "renewal_successor_sources_changed"):
                repeat.prepare(config, successor)
        repeat.prepare(config, successor)
        ledger = run.read(successor / "ledger.private.json")
        ledger["sources"] = pins
        run.save(successor / "ledger.private.json", ledger)
        with self.assertRaisesRegex(RuntimeError, "renewal_successor_sources_changed"):
            repeat.certify_predecessor(successor)

    def test_renewal_public_certification_rebinds_only_successor_source_pins(self):
        config, successor, binding = self.renewal_fixture()
        old = self.ledger()
        old["sources"]["repeat"] = "f" * 64  # Synthetic immutable historical source.
        run.save(self.directory / "ledger.private.json", old)
        manifest = repeat.evidence_manifest(self.directory)
        config["continuation"] = repeat.certify_predecessor(self.directory, renewal=binding)
        config["approval"]["continuationHash"] = repeat.identity(config["continuation"])
        repeat.prepare(config, successor)
        self.assertEqual(repeat.load(successor)[1]["sources"], repeat.sources())
        self.assertEqual(config["continuation"]["sources"]["repeat"], "f" * 64)
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)
        self.assertEqual(self.ledger(), old)

    def test_renewal_public_cli_certificate_only_and_no_plaintext_evidence(self):
        config, successor, binding = self.renewal_fixture()
        output = io.StringIO()
        argv = ["repeat.py", "certify-continuation", "--session", self.directory.name,
                "--renewal-attestation", binding["path"]]
        with mock.patch.object(repeat, "ROOT", self.root), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            repeat.main()
        certificate = json.loads(output.getvalue())
        self.assertEqual(certificate, config["continuation"])
        self.assertNotIn("OFFLINE-NOT-AUTHORITY", output.getvalue())
        self.assertNotIn("contexts", certificate)
        self.assertFalse(successor.exists())
        for action in ("prepare", "status", "plan"):
            with mock.patch.object(sys, "argv", [*argv[:1], action, *argv[2:]]):
                with self.assertRaisesRegex(RuntimeError, "certification_only"):
                    repeat.main()
        with mock.patch.object(sys, "argv", [*argv[:-1], str(run.LAB / "README.md")]):
            with self.assertRaisesRegex(RuntimeError, "private_renewal_attestation_required"):
                repeat.main()
        self.azure.assert_not_called()

    def test_runtime_cap_requires_exact_explicit_approval_and_has_hard_upper_bound(self):
        for value in (True, 43200.0, 43199, 86401, "57600"):
            candidate = copy.deepcopy(self.config)
            candidate["allocatedSecondsPerVm"] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                repeat.validate_config(candidate)
        self.config["allocatedSecondsPerVm"] = 57600
        with self.assertRaisesRegex(RuntimeError, "explicit_runtime"):
            repeat.validate_config(self.config)
        self.config["approval"].update(allocatedSecondsPerVm=57600, evidenceReference="TEST")
        repeat.validate_config(self.config)
        self.assertTrue(repeat.projections_fit(self.config, {"same-region": 28000, "cross-region": 28000}))
        self.assertFalse(repeat.projections_fit(self.config, {"same-region": 29000, "cross-region": 29000}))

    def test_24_hour_coordinator_amendment_keeps_default_and_absolute_deadline(self):
        self.assertEqual(repeat.slot_seconds(self.config), 43200)
        self.config["allocatedSecondsPerVm"] = 86400
        self.config["approval"].update(allocatedSecondsPerVm=86400, evidenceReference="COORDINATOR")
        repeat.validate_config(self.config)
        self.config["cleanupDeadlineUtc"] = "2026-10-18T07:33:01Z"
        with self.assertRaisesRegex(RuntimeError, "ttl"):
            repeat.validate_config(self.config)

    def test_phase_poll_ancestry_count_and_mutation_terminal_tamper_boundaries(self):
        config, successor = self.continuation_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.reserve()
        lease = self.lease("readiness", key)
        with mock.patch.object(repeat, "certify_predecessor",
                               wraps=repeat.certify_predecessor) as full:
            with repeat.runner(successor, lease):
                admission = full.call_count
                for _ in range(100):
                    run.guard(None, 0)
                self.assertEqual(full.call_count, admission)
                run.FULL_VALIDATION_GUARD()
                self.assertEqual(full.call_count, admission)
                proof = repeat.PHASE_SCOPE
                self.assertIsInstance(proof.evidence_bytes, tuple)
                self.assertTrue(proof.evidence_bytes)
                print("GUARD_PROFILE " + json.dumps({
                    "polls": 100, "admissionAncestryValidations": admission,
                    "pollAncestryValidations": 0,
                    "mutationAncestryValidations": full.call_count - admission}))
                historical = Path(config["continuation"]["directory"]) / "chunks" / "same-region-000"
                path = historical / "client-report.private.json"
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    run.guard(None, 0)
                    # The immutable phase snapshot cannot be changed by writing
                    # the historical namespace. Terminal credit still reopens it.
                    run.FULL_VALIDATION_GUARD()
                    self.assertIs(repeat.PHASE_SCOPE, proof)
                    self.azure.assert_not_called()
                    with self.assertRaisesRegex(RuntimeError, "predecessor_evidence"):
                        repeat.finish(successor, key)
                finally:
                    path.write_bytes(original)

    def test_twenty_mutations_reuse_twenty_second_admission_proof(self):
        config, successor = self.continuation_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.reserve()
        lease = self.lease("readiness", key, maxMutations=100, maxToolCalls=150)
        original = repeat.certify_predecessor
        validation_cost = []
        def expensive(*args, **kwargs):
            validation_cost.append(20)
            return original(*args, **kwargs)
        with mock.patch.object(repeat, "certify_predecessor", side_effect=expensive):
            with repeat.runner(successor, lease):
                admission_cost = sum(validation_cost)
                with mock.patch.object(run.Azure, "_invoke", return_value={}):
                    for _ in range(20):
                        run.Azure({}).cli([], operation="ready-a", seconds=180)
                self.assertEqual(sum(validation_cost), admission_cost)
                self.assertEqual(run.read(lease)["actualMutations"], 20)
                self.assertEqual(run.read(lease)["activeCommands"], 0)
                pins = repeat.sources()
                with mock.patch.object(repeat, "sources", return_value=dict(pins, repeat="0" * 64)):
                    with self.assertRaisesRegex(RuntimeError, "source_changed"):
                        run.Azure({}).cli([], operation="ready-a", seconds=180)
                path = successor / "config.private.json"
                original_config = run.read(path)
                run.save(path, dict(original_config, extra="changed"))
                with self.assertRaisesRegex(RuntimeError, "phase_config_changed"):
                    run.Azure({}).cli([], operation="ready-a", seconds=180)
                run.save(path, original_config)
                value = run.read(lease)
                for changes in ({"state": "blocked"},
                                {"expiresAtUtc": run.now().isoformat()},
                                {"actualToolCalls": 150}):
                    run.save(lease, dict(value, **changes))
                    with self.assertRaises(RuntimeError):
                        run.Azure({}).cli([], operation="ready-a", seconds=180)
                    run.save(lease, value)
                stop = successor / "control" / "STOP"
                stop.touch()
                with self.assertRaisesRegex(RuntimeError, "repeat_stop"):
                    run.Azure({}).cli([], operation="ready-a", seconds=180)
                stop.unlink()
                self.assertEqual(run.read(lease)["actualMutations"], 20)
        self.azure.assert_not_called()

    def readiness_failure_fixture(self):
        self.config["moneyBudgetMode"] = "monitor-only"
        self.config["approval"].update(moneyBudgetMode="monitor-only", totalUsdEquivalentCap=None)
        for context in self.config["contexts"].values():
            context["preflight"].update(currencyCap=None, usdEquivalentCap=None)
        config, successor = self.continuation_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.reserve("cross-region")
        lease_path = self.lease("readiness", key)
        repeat.begin(self.directory, key, "readiness", lease_path)
        lease = run.read(lease_path)
        lease.update(state="blocked", actualToolCalls=18, actualMutations=6)
        run.save(lease_path, lease)
        repeat.fail(self.directory, key)
        ledger = self.ledger()
        chunk_dir = self.directory / "chunks" / key
        plan = run.read(chunk_dir / "plan.private.json")
        current = run.now().isoformat()
        plan["restore_started"] = current
        run.save(chunk_dir / "plan.private.json", plan)
        binding = {"runner_sha256": ledger["sources"]["run.py"],
                   "stream_sha256": ledger["sources"]["stream.py"]}
        receipt = {"success": False, "binding": binding, "failures": ["lease_lock_deadline"],
                   "started_at": lease["startedAtUtc"], "completed_at": current,
                   "deallocated": {"C": True, "T": True}}
        run.save(chunk_dir / "readiness.private.json", receipt)
        for alias in ("C", "T"):
            run.save(chunk_dir / ("deallocate-" + alias.lower() + "-verified.private.json"),
                     {"verified": True, "at": current,
                      "binding": {"id": plan["id"], "endpoint": plan[alias]}})
        closure = {"success": True, "all21OriginalOwnedRootsVerified": True,
                   "totalAzureMutations": 0, "startedAtUtc": current, "completedAtUtc": current,
                   "lease": dict(lease, taskId="independent-closure", maxMutations=0,
                                 actualMutations=0, state="completed"),
                   "endpoints": {alias: {
                       "deallocated": True, "ownedRootCount": 7,
                       "originalVmIdentityAndStorageProfile": True,
                       "originalDiskAttachment": True,
                       "nicAndSubnetNsgRulesAndAssociationsMatchBaseline": True}
                       for alias in ("A", "C", "T")}}
        path = self.root / "closure.private.json"
        run.save(path, closure)
        bound = {"path": str(path), "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest()}
        attestation = {"schema": "repeat-readiness-closure-v1",
                       "validationKind": "independent-read-only", "validatedBy": "Niobe-test",
                       "sessionDirectory": str(self.directory.resolve()),
                       "configHash": repeat.identity(self.config), "ledgerHash": repeat.identity(ledger),
                       "chunk": key, "leaseHash": repeat.identity(lease),
                       "readinessHash": repeat.identity(receipt), "closure": bound,
                       "evidenceHashes": {str(path): bound["sha256"]}}
        path = self.root / "readiness-closure.private.json"
        run.save(path, attestation)
        return key, {"path": str(path),
                     "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest()}, binding

    def test_closed_readiness_recovery_conserves_no_fork_nonce_and_unknown_wire(self):
        key, binding, ready_binding = self.readiness_failure_fixture()
        before, manifest = self.ledger(), repeat.evidence_manifest(self.directory)
        with mock.patch.object(run, "readiness_binding", return_value=ready_binding):
            certificate = repeat.certify_predecessor(self.directory, readiness_closure=binding)
            failure = certificate["closed_failures"][key]
            self.assertEqual(failure["kind"], "closed-readiness-failure")
            self.assertIsNone(failure["actual_wire_bytes"])
            self.assertEqual(failure["application_credit"], 0)
            self.assertEqual(failure["allocated_seconds_per_vm"], 5400)
            config = copy.deepcopy(self.config)
            config["continuation"] = certificate
            config["wireCeilingBytes"] = 470_000_000_000
            config["allocatedSecondsPerVm"] = 86400
            config["approval"].update(continuationHash=repeat.identity(certificate),
                wireCeilingBytes=470_000_000_000, allocatedSecondsPerVm=86400,
                evidenceReference="COORDINATOR-EXACT-470GB")
            successor = self.root / "readiness-recovery"
            repeat.prepare(config, successor)
            _, ledger = repeat.load(successor)
            for field in ("chunks", "wire_reserved", "wire_measured", "allocated_seconds",
                          "money_reserved", "leases", "owners"):
                self.assertEqual(ledger[field], before[field])
            self.assertIsNone(ledger["active_phase"])
            fresh = repeat.reserve(successor, "cross-region")
            self.assertEqual(fresh, key + "-recovery-1")
            self.assertNotEqual(run.read(successor / "ledger.private.json")["chunks"][fresh]["id"],
                                before["chunks"][key]["id"])
            with self.assertRaises(FileExistsError):
                repeat.prepare(config, self.root / "forbidden-fork")
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)

    def test_closed_readiness_rejects_unclosed_credit_and_closure_tamper(self):
        _, binding, ready_binding = self.readiness_failure_fixture()
        ledger_path = self.directory / "ledger.private.json"
        original = self.ledger()
        key = original["active_phase"]["chunk"]
        with mock.patch.object(run, "readiness_binding", return_value=ready_binding):
            with self.assertRaisesRegex(RuntimeError, "readiness_closure_binding_required"):
                repeat.certify_predecessor(self.directory)
            for change in (
                lambda value: value["chunks"][key].update(attempts=1),
                lambda value: value["chunks"][key].update(wire_measured=1),
                lambda value: value["active_phase"].update(state="active"),
            ):
                candidate = copy.deepcopy(original)
                change(candidate)
                run.save(ledger_path, candidate)
                with self.assertRaises((RuntimeError, KeyError)):
                    repeat.certify_predecessor(self.directory, readiness_closure=binding)
                run.save(ledger_path, original)
            path = Path(binding["path"])
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "readiness_closure_hash_changed"):
                repeat.certify_predecessor(self.directory, readiness_closure=binding)

    def test_readiness_admission_exact_boundary_and_both_deadline_diagnostics(self):
        self.prepare()
        key = self.reserve()
        lease = self.lease("readiness", key,
                           startedAtUtc="2026-10-17T16:55:08.961775Z",
                           expiresAtUtc="2026-10-17T17:25:08.961775Z")
        with mock.patch.object(run, "PRIVATE", self.directory / "chunks"), \
             mock.patch.object(run, "LEASE", lease):
            with mock.patch.object(run, "now", return_value=repeat.timestamp(
                    "2026-10-17T17:07:08.961775Z")):
                with self.assertRaisesRegex(RuntimeError, "lease_lock_deadline"):
                    with run.lease_lock("ready-c", 180):
                        self.fail("boundary admitted")
            gate = mock.Mock()
            gate.acquire.return_value = True
            with mock.patch.object(run, "now", return_value=repeat.timestamp(
                    "2026-10-17T17:00:00Z")), \
                 mock.patch.object(run, "LEASE_GATE", gate), \
                 mock.patch.object(run.time, "monotonic", side_effect=itertools.count(0, 301)):
                with self.assertRaisesRegex(RuntimeError, "lease_lock_deadline"):
                    with run.lease_lock("ready-c", 180):
                        self.fail("elapsed local wait admitted")
            records = [run.read(path) for path in
                       (run.PRIVATE / ".lease-diagnostics").glob("*.json")]
            self.assertEqual({record["event"] for record in records},
                             {"lease_lock_deadline_before_gate", "lease_lock_deadline_after_gate"})
            self.assertTrue(all(record["traceback"] for record in records))

    def test_lock_provenance_survives_release_reentrancy_and_foreign_holder(self):
        self.prepare()
        key = self.reserve()
        lease = self.lease("readiness", key)
        with mock.patch.object(run, "PRIVATE", self.directory / "chunks"), \
             mock.patch.object(run, "LEASE", lease):
            with run.lease_lock("ready-c", 180):
                with run.lease_lock("ready-t", 180):
                    self.assertTrue((run.PRIVATE / ".lease-lock" / "owner.json").exists())
            self.assertFalse((run.PRIVATE / ".lease-lock").exists())
            path = run.PRIVATE / ".lease-lock"
            path.mkdir()
            foreign = {"token": "foreign", "pid": 123, "thread": 456, "operation": "ready-t"}
            run.save(path / "owner.json", foreign)
            with mock.patch.object(run.time, "monotonic", side_effect=itertools.count(0, 10)):
                with self.assertRaisesRegex(RuntimeError, "lease_lock_busy"):
                    with run.lease_lock("ready-c", 180):
                        self.fail("foreign lock adopted")
            records = [run.read(item) for item in
                       (run.PRIVATE / ".lease-diagnostics").glob("*.json")]
            self.assertEqual(next(item for item in records if item["event"] ==
                                  "lease_lock_busy")["owner"], foreign)
            self.assertTrue(any(item["event"] == "lease_lock_release"
                                and item["owner"]["token"] != "foreign" for item in records))

    def test_completion_accounting_drains_after_peer_expiry_while_waiting(self):
        self.prepare()
        key = self.reserve()
        lease = self.lease("readiness", key)
        gate = mock.Mock()
        gate.acquire.return_value = True
        with mock.patch.object(run, "PRIVATE", self.directory / "chunks"), \
             mock.patch.object(run, "LEASE", lease), \
             mock.patch.object(run, "LEASE_GATE", gate), \
             mock.patch.object(run.time, "monotonic", side_effect=itertools.count(0, 4000)):
            with run.lease_lock("read-restore:accounting"):
                self.assertTrue((run.PRIVATE / ".lease-lock" / "owner.json").exists())
            self.assertFalse((run.PRIVATE / ".lease-lock").exists())
            gate.acquire.assert_called_once_with(timeout=300)

    def test_parallel_admission_and_peer_drain_do_not_hide_second_failure(self):
        self.prepare()
        with mock.patch.object(run, "PRIVATE", self.directory / "chunks"), \
             mock.patch.object(run, "guard", return_value={}) as guard, \
             mock.patch.object(run, "execute", side_effect=RuntimeError("peer_failed")) as execute:
            with self.assertRaisesRegex(RuntimeError, "peer_failed"):
                run.parallel_steps(type("Args", (), {"run": "offline"})(), ("ready-c", "ready-t"))
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(guard.call_count, 2)
            records = [run.read(path) for path in
                       (run.PRIVATE / ".lease-diagnostics").glob("*.json")]
            self.assertEqual({record["operation"] for record in records}, {"ready-c", "ready-t"})
            self.assertTrue(all(record["event"] == "parallel_peer_failed" for record in records))
            execute.reset_mock()
            guard.side_effect = RuntimeError("reserve_15_minutes_restoration")
            with self.assertRaisesRegex(RuntimeError, "reserve_15"):
                run.parallel_steps(type("Args", (), {"run": "offline"})(), ("ready-c", "ready-t"))
            execute.assert_not_called()

    def test_fast_scope_stop_counters_and_revocation_are_not_cached(self):
        self.prepare()
        key = self.reserve()
        lease = self.lease("readiness", key)
        repeat.begin(self.directory, key, "readiness", lease)
        with repeat.runner(self.directory, lease):
            value = run.read(lease)
            for field, changed in (("actualToolCalls", value["maxToolCalls"]),
                                   ("state", "blocked"), ("ownerId", "revoked")):
                candidate = dict(value, **{field: changed})
                repeat.atomic(lease, candidate)
                with self.subTest(field=field), self.assertRaises(RuntimeError):
                    run.guard(None, 0)
                repeat.atomic(lease, value)
            stop = self.directory / "control" / "STOP"
            stop.touch()
            with self.assertRaises(RuntimeError):
                run.guard(None, 0)
            stop.unlink()

    def test_full_transport_then_projection_failure_keeps_credit_and_closed_lease(self):
        config, successor, _ = self.recovery_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.completed_fixture()
        with mock.patch.object(repeat, "verified_projections",
                               return_value={"same-region": 60000, "cross-region": 20000}):
            with self.assertRaisesRegex(RuntimeError, "pilot_projection"):
                repeat.finish(successor, key)
        ledger = self.ledger()
        self.assertEqual(ledger["chunks"][key]["state"], "complete")
        self.assertIsNone(ledger["active_phase"])
        self.assertEqual(run.read(ledger["chunks"][key]["lease_path"])["state"], "completed")
        self.assertEqual(repeat.status(successor)["progress_application_bytes"]["A->T"],
                         stream.GIB + stream.MAX_BYTES)
        with self.assertRaises(RuntimeError):
            self.reserve()

    def salvage_fixture(self):
        config, successor, key = self.recovery_fixture()
        plan_path = self.directory / "chunks" / key / "plan.private.json"
        plan = run.read(plan_path)
        current = repeat.timestamp(plan["ended"])
        plan.update(status="completed", failures=[],
                    live_started=(current - timedelta(seconds=2000)).isoformat())
        run.save(plan_path, plan)
        path = plan_path.parent / "readiness.private.json"
        ready = run.read(path)
        ready.update(started_at=(current - timedelta(seconds=2060)).isoformat(),
                     completed_at=(current - timedelta(seconds=2030)).isoformat())
        run.save(path, ready)
        ledger = self.ledger()
        path = Path(ledger["chunks"][key]["lease_path"])
        lease = run.read(path)
        lease.update(startedAtUtc=(current - timedelta(seconds=2200)).isoformat(),
                     expiresAtUtc=(current + timedelta(seconds=1400)).isoformat())
        run.save(path, lease)
        ledger["active_phase"]["authority_hash"] = repeat.lease_authority(lease)
        run.save(self.directory / "ledger.private.json", ledger)
        return config, successor, key

    def test_certified_salvage_conserves_reservations_and_rejects_duplicate_or_tamper(self):
        config, successor, key = self.salvage_fixture()
        old = self.ledger()
        manifest = repeat.evidence_manifest(self.directory)
        certificate = repeat.certify_predecessor(self.directory)
        self.assertIn(key, certificate["salvaged_completions"])
        self.assertEqual(certificate["salvaged_completions"][key]["allocated_seconds"], 5400)
        self.assertEqual(self.ledger(), old)
        config["continuation"] = certificate
        config["allocatedSecondsPerVm"] = 86400
        config["approval"].update(allocatedSecondsPerVm=86400,
                                  continuationHash=repeat.identity(certificate))
        repeat.prepare(config, successor)
        _, inherited = repeat.load(successor)
        for field in ("wire_reserved", "allocated_seconds", "money_reserved"):
            self.assertEqual(inherited[field], old[field])
        self.assertEqual(inherited["wire_measured"], old["wire_measured"]
                         + certificate["salvaged_completions"][key]["wire_measured"])
        self.assertEqual(repeat.status(successor)["progress_application_bytes"]["A->T"],
                         stream.GIB + stream.MAX_BYTES)
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)
        with self.assertRaises(FileExistsError):
            repeat.prepare(config, self.root / "salvage-fork")
        plan_path = self.directory / "chunks" / key / "client-report.private.json"
        report = run.read(plan_path)
        report["legs"]["up"]["sha256"] = "b" * 64
        run.save(plan_path, report)
        with self.assertRaises((RuntimeError, ValueError)):
            repeat.certify_predecessor(self.directory)

    def test_runner_context_is_exclusive_and_restored(self):
        self.prepare()
        key = self.reserve()
        lease = self.lease("readiness", key)
        original = run.PRIVATE, run.LEASE, run.EXECUTION_GUARD, run.FULL_VALIDATION_GUARD
        with repeat.runner(self.directory, lease):
            result = []
            def competing():
                with self.assertRaisesRegex(RuntimeError, "runner_context_busy"):
                    with repeat.runner(self.directory, lease):
                        result.append("unsafe")
            thread = threading.Thread(target=competing)
            thread.start()
            thread.join(7)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, [])
        self.assertEqual(original, (run.PRIVATE, run.LEASE, run.EXECUTION_GUARD,
                                    run.FULL_VALIDATION_GUARD))

    def recovery_fixture(self):
        config, successor = self.continuation_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.completed_fixture()
        ledger = self.ledger()
        chunk = ledger["chunks"][key]
        chunk["state"] = "failed_or_unknown"
        chunk["phases"] = {}
        for action in ("readiness", "snapshot"):
            lease = run.read(chunk["lease_path"])
            lease.update(taskId=uuid.uuid4().hex, maxToolCalls=75, actualToolCalls=40,
                         maxMutations=6, actualMutations=4)
            path = self.directory / "control" / (lease["taskId"] + ".json")
            run.save(path, lease)
            chunk["phases"][action] = {"taskId": lease["taskId"], "lease_path": str(path),
                                       "lease_hash": repeat.identity(lease)}
        ledger["state"] = "blocked"
        ledger["active_phase"]["state"] = "blocked"
        run.save(self.directory / "ledger.private.json", ledger)
        path = self.directory / "chunks" / key / "plan.private.json"
        plan = run.read(path)
        plan.update(status="blocked", failures=["lease_lock_busy"])
        run.save(path, plan)
        path = Path(chunk["lease_path"])
        lease = run.read(path)
        lease["state"] = "blocked"
        run.save(path, lease)
        recovery = copy.deepcopy(config)
        recovery["continuation"] = repeat.certify_predecessor(self.directory)
        recovery["wireCeilingBytes"] = repeat.RECOVERY_WIRE_LIMIT
        recovery["approval"].update(wireCeilingBytes=repeat.RECOVERY_WIRE_LIMIT,
            continuationHash=repeat.identity(recovery["continuation"]),
            evidenceReference="OFFLINE-COORDINATOR-RECOVERY-DECISION")
        return recovery, self.root / "recovery", key

    def test_closed_failed_nested_recovery_conserves_and_uses_fresh_nonce(self):
        config, successor, failed = self.recovery_fixture()
        before, manifest = self.ledger(), repeat.evidence_manifest(self.directory)
        repeat.prepare(config, successor)
        _, ledger = repeat.load(successor)
        for field in ("chunks", "wire_reserved", "wire_measured", "allocated_seconds",
                      "money_reserved", "prior_allocated_seconds", "leases", "owners"):
            self.assertEqual(ledger[field], before[field])
        self.assertIsNone(ledger["active_phase"])
        summary = repeat.status(successor)
        self.assertEqual(sum(summary["progress_application_bytes"].values()), 4 * stream.GIB)
        key = repeat.reserve(successor, "same-region")
        self.assertEqual(key, failed + "-recovery-1")
        _, after = repeat.load(successor)
        self.assertNotEqual(after["chunks"][key]["id"], before["chunks"][failed]["id"])
        self.assertEqual(after["chunks"][failed], before["chunks"][failed])
        self.assertEqual(after["wire_reserved"], before["wire_reserved"]
                         + repeat.wire_reserve(stream.MAX_BYTES))
        self.assertEqual(after["allocated_seconds"]["T"],
                         before["allocated_seconds"]["T"] + repeat.ALLOCATION_RESERVE)
        self.assertEqual(repeat.evidence_manifest(self.directory), manifest)
        self.assertEqual(repeat.status(successor)["progress_application_bytes"],
                         summary["progress_application_bytes"])

    def test_recovery_lineage_has_no_one_generation_limit_and_rejects_fork(self):
        config, successor, _ = self.recovery_fixture()
        repeat.prepare(config, successor)
        next_config = copy.deepcopy(config)
        next_config["continuation"] = repeat.certify_predecessor(successor)
        next_config["approval"]["continuationHash"] = repeat.identity(next_config["continuation"])
        third = self.root / "third"
        repeat.prepare(next_config, third)
        repeat.load(third)
        with self.assertRaises(FileExistsError):
            repeat.prepare(next_config, self.root / "fork")
        self.assertEqual(repeat.status(third)["progress_application_bytes"],
                         repeat.status(successor)["progress_application_bytes"])

    def test_recovered_completion_credits_once_and_projects_exact_remaining_schedule(self):
        config, successor, failed = self.recovery_fixture()
        repeat.prepare(config, successor)
        self.directory, self.config = successor, config
        key = self.completed_fixture()
        self.assertEqual(key, failed + "-recovery-1")
        repeat.finish(successor, key)
        summary = repeat.status(successor)
        self.assertEqual(sum(summary["progress_application_bytes"].values()), 14 * stream.GIB)
        self.assertEqual(self.ledger()["chunks"][failed]["state"], "failed_or_unknown")
        self.assertEqual(repeat.reserve(successor, "same-region"), "same-region-002")
        with self.assertRaises(RuntimeError):
            repeat.finish(successor, key)

    def test_recovery_rejects_unclosed_failed_evidence_and_active_owner(self):
        _, _, key = self.recovery_fixture()
        path = Path(self.ledger()["chunks"][key]["lease_path"])
        original = run.read(path)
        for changes in ({"activeCommands": 1}, {"ownedProcessesIdle": False}, {"state": "active"}):
            run.save(path, dict(original, **changes))
            with self.assertRaises(RuntimeError):
                repeat.certify_predecessor(self.directory)
        run.save(path, original)
        proof_path = self.directory / "chunks" / key / "deallocate-a-verified.private.json"
        proof = run.read(proof_path)
        proof["verified"] = False
        run.save(proof_path, proof)
        with self.assertRaisesRegex(RuntimeError, "failed_deallocation"):
            repeat.certify_predecessor(self.directory)

    def test_recovery_rejects_counter_reductions_inherited_bytes_and_duplicate_credit(self):
        config, successor, key = self.recovery_fixture()
        repeat.prepare(config, successor)
        path = successor / "ledger.private.json"
        original = run.read(path)
        changes = [
            lambda l: l.update(wire_reserved=l["wire_reserved"] - 1),
            lambda l: l["allocated_seconds"].update(T=l["allocated_seconds"]["T"] - 5400),
            lambda l: l["chunks"][key].update(allocated_seconds=1),
            lambda l: l["chunks"]["same-region-000"].update(bytes=stream.GIB + 1),
            lambda l: l["chunks"].update({"same-region-000-recovery-1":
                                           copy.deepcopy(l["chunks"]["same-region-000"])}),
        ]
        for change in changes:
            ledger = copy.deepcopy(original)
            change(ledger)
            run.save(path, ledger)
            with self.assertRaises(RuntimeError):
                repeat.load(successor)

    def test_recovery_rejects_hash_cycles_depth_and_unauthorized_wire(self):
        config, successor, _ = self.recovery_fixture()
        changes = [
            lambda c: c["continuation"]["files"].update({"ledger.private.json": "0" * 64}),
            lambda c: c.update(wireCeilingBytes=repeat.RECOVERY_WIRE_LIMIT + 1),
            lambda c: c["approval"].update(wireCeilingBytes=repeat.WIRE_LIMIT),
            lambda c: c["approval"].pop("continuationHash"),
        ]
        for change in changes:
            candidate = copy.deepcopy(config)
            change(candidate)
            with self.assertRaises(RuntimeError):
                repeat.prepare(candidate, successor)
            self.assertFalse(successor.exists())
        with self.assertRaisesRegex(RuntimeError, "lineage_cycle"):
            repeat.certify_predecessor(self.directory, (str(self.directory.resolve()),))
        with self.assertRaisesRegex(RuntimeError, "lineage_cycle"):
            repeat.certify_predecessor(self.directory, tuple(str(i) for i in range(repeat.MAX_LINEAGE)))
        with mock.patch.object(repeat, "MAX_EVIDENCE_FILES", 1):
            with self.assertRaisesRegex(RuntimeError, "lineage_file_bound"):
                repeat.certify_predecessor(self.directory)
        low = copy.deepcopy(config)
        low.pop("wireCeilingBytes")
        low["approval"]["wireCeilingBytes"] = repeat.WIRE_LIMIT
        with self.assertRaisesRegex(RuntimeError, "whole_session_wire_cap"):
            repeat.prepare(low, successor)

    def test_continuation_rejects_changed_hash_and_unapproved_or_decreased_carry(self):
        config, successor = self.continuation_fixture()
        changes = [
            lambda c: c["approval"].pop("continuationHash"),
            lambda c: c["continuation"]["sources"].update(repeat="0" * 64),
            lambda c: c["continuation"]["files"].pop("ledger.private.json"),
            lambda c: c.update(priorAllocatedSeconds={"A": 0, "C": 0, "T": 0}),
            lambda c: c.update(chunkBytes=stream.GIB),
            lambda c: c["approval"].update(applicationBytesPerLeg=repeat.TARGET - 1),
            lambda c: c.update(cleanupDeadlineUtc="2026-10-18T07:34:00Z"),
        ]
        for change in changes:
            candidate = copy.deepcopy(config)
            change(candidate)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                repeat.prepare(candidate, successor)
            self.assertFalse(successor.exists())
        repeat.prepare(config, successor)
        plan_path = self.directory / "chunks" / "same-region-000" / "plan.private.json"
        plan_path.write_text(plan_path.read_text() + "\n")
        with self.assertRaisesRegex(RuntimeError, "predecessor_evidence_hash"):
            repeat.load(successor)

    def test_continuation_rejects_fork_double_credit_and_failed_partial(self):
        config, successor = self.continuation_fixture()
        repeat.prepare(config, successor)
        with self.assertRaises(FileExistsError):
            repeat.prepare(config, self.root / "fork")
        ledger = run.read(successor / "ledger.private.json")
        ledger["chunks"]["same-region-000"]["bytes"] += 1
        run.save(successor / "ledger.private.json", ledger)
        with self.assertRaises(RuntimeError):
            repeat.load(successor)
        old = self.ledger()
        old["chunks"]["same-region-000"]["state"] = "failed_or_unknown"
        run.save(self.directory / "ledger.private.json", old)
        with self.assertRaises(RuntimeError):
            repeat.certify_predecessor(self.directory)

    def test_certificate_rechecks_reports_and_restoration_not_just_ledger(self):
        self.continuation_fixture()
        path = self.directory / "chunks" / "same-region-000" / "client-report.private.json"
        report = run.read(path)
        report["legs"]["up"]["bytes"] -= 1
        run.save(path, report)
        with self.assertRaises((RuntimeError, ValueError)):
            repeat.certify_predecessor(self.directory)

    def test_plan_four_cross_tenant_legs_and_no_state(self):
        self.config["approval"]["status"] = "pending"
        summary = repeat.plan_summary(self.config)
        self.assertEqual(summary["legs"], ["A->T", "T->A", "C->T", "T->C"])
        self.assertEqual(summary["total_application_bytes"], 400_000_000_000)
        self.assertFalse(summary["live_allowed"])
        self.assertLessEqual(summary["wire_reserved_whole_session"], repeat.WIRE_LIMIT)
        self.assertFalse(self.directory.exists())
        with self.assertRaisesRegex(RuntimeError, "approval"):
            self.prepare()

    def test_rate_opt_in_preserves_legacy_default_and_bounds(self):
        cfg = {"id": "a" * 32, "bytes": 1, "wire_cap": 100}
        stream.validate(cfg)
        self.assertEqual(stream.RATE, 2_500_000)
        with self.assertRaises(ValueError):
            stream.validate(dict(cfg, rate=stream.RATE + 1))
        stream.validate(dict(cfg, rate=stream.MAX_RATE, rate_ceiling=stream.MAX_RATE))
        for value in (stream.MAX_RATE + 1, 0, float("nan"), True):
            with self.assertRaises(ValueError):
                stream.validate(dict(cfg, rate=stream.MAX_RATE, rate_ceiling=value))
        self.config.pop("rateBytesPerSecond")
        with self.assertRaisesRegex(RuntimeError, "twelve_hour"):
            repeat.validate_config(self.config)

    def test_inventory_and_tenant_constraints(self):
        changes = [
            lambda c: c["contexts"]["msdn"].update(
                expectedTenantId=c["contexts"]["core"]["expectedTenantId"]),
            lambda c: c["endpoints"]["C"].update(region="swedencentral"),
            lambda c: c["endpoints"]["C"]["inventory"]["resources"][0].update(tags={}),
            lambda c: c["approval"]["resourceIds"].pop(),
            lambda c: c["endpoints"]["A"]["inventory"]["resources"].append(
                dict(c["endpoints"]["A"]["inventory"]["resources"][0])),
            lambda c: c["endpoints"]["T"]["inventory"].update(
                capturedAtUtc=(run.now() - timedelta(days=2)).isoformat()),
        ]
        for change in changes:
            candidate = copy.deepcopy(self.config)
            change(candidate)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                repeat.validate_config(candidate)

    def test_currency_infra_and_preflight_bounds(self):
        for key, value in (("currencyCap", "NaN"), ("currencyCap", "24"),
                           ("fixedInfraReserve", "24"), ("validated", False),
                           ("usdEquivalentCap", 65), ("txPerDecimalGB", 0)):
            candidate = copy.deepcopy(self.config)
            candidate["contexts"]["core"]["preflight"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                repeat.prepare(candidate, self.directory)
            if self.directory.exists():
                shutil.rmtree(self.directory)
        candidate = copy.deepcopy(self.config)
        candidate["contexts"]["msdn"]["preflight"].update(
            currency="SEK", currencyCap="220", txPerDecimalGB=".2", vmPerHour=".1")
        repeat.validate_config(candidate)  # Consumes validated currency cap; no invented FX.

    def monitor_only(self, null_caps=False):
        self.config["moneyBudgetMode"] = "monitor-only"
        self.config["approval"]["moneyBudgetMode"] = "monitor-only"
        self.config["approval"].pop("totalUsdEquivalentCap")
        for context in self.config["contexts"].values():
            for field in ("currencyCap", "usdEquivalentCap"):
                context["preflight"].pop(field)
        if null_caps:
            self.config["approval"]["totalUsdEquivalentCap"] = None
            for context in self.config["contexts"].values():
                context["preflight"].update(currencyCap=None, usdEquivalentCap=None)

    def test_monitor_only_explicit_approved_mode_accepts_missing_or_null_caps(self):
        for null_caps in (False, True):
            with self.subTest(null_caps=null_caps):
                self.config = fixture()
                self.monitor_only(null_caps)
                self.config["contexts"]["core"]["preflight"]["fixedInfraReserve"] = "100"
                summary = repeat.plan_summary(self.config)
                self.assertEqual(summary["money_budget_mode"], "monitor-only")
                self.assertFalse(summary["live_allowed"])
                self.prepare()
                key = self.reserve()
                self.assertGreater(repeat.number(self.ledger()["money_reserved"]["core"]), 100)
                self.assertEqual(self.ledger()["chunks"][key]["attempts"], 0)
                self.assertEqual(repeat.status(self.directory)["money_budget_mode"], "monitor-only")
                self.azure.assert_not_called()
                shutil.rmtree(self.directory)

    def test_monitor_only_requires_matching_approved_mode_and_no_magic_caps(self):
        for mode in ("missing_config_mode", "missing_approval_mode", "pending", "typo",
                     "null_mode", "zero_cap", "infinite_cap", "nan_cap", "old_context_cap",
                     "old_total_cap", "old_usd_cap"):
            with self.subTest(mode=mode):
                self.config = fixture()
                self.monitor_only()
                if mode == "missing_config_mode":
                    self.config.pop("moneyBudgetMode")
                elif mode == "missing_approval_mode":
                    self.config["approval"].pop("moneyBudgetMode")
                elif mode == "pending":
                    self.config["approval"]["status"] = "pending"
                elif mode == "typo":
                    self.config["moneyBudgetMode"] = "monitor"
                elif mode == "null_mode":
                    self.config["moneyBudgetMode"] = None
                elif mode == "old_total_cap":
                    self.config["approval"]["totalUsdEquivalentCap"] = 45
                elif mode == "old_usd_cap":
                    self.config["contexts"]["core"]["preflight"]["usdEquivalentCap"] = 23
                else:
                    self.config["contexts"]["core"]["preflight"]["currencyCap"] = {
                        "zero_cap": 0, "infinite_cap": "Infinity", "nan_cap": "NaN",
                        "old_context_cap": 23}[mode]
                with self.assertRaises(RuntimeError):
                    repeat.plan_summary(self.config)
                with self.assertRaises(RuntimeError):
                    self.prepare()
                self.assertFalse(self.directory.exists())
                self.azure.assert_not_called()

    def test_enforced_default_retains_old_caps_and_all_dispatch_checks(self):
        self.assertEqual(repeat.money_mode(self.config), "enforced")
        self.config["contexts"]["core"]["preflight"]["fixedInfraReserve"] = "22"
        self.config["contexts"]["core"]["preflight"]["txPerDecimalGB"] = ".1"
        self.prepare()  # 22 + .8 bootstrap fits, but next full pair cannot.
        before = self.ledger()
        with self.assertRaisesRegex(RuntimeError, "context_currency_cap"):
            self.reserve()
        self.assertEqual(before, self.ledger())
        self.azure.assert_not_called()

    def test_monitor_only_money_integrity_immutable_choice_and_failed_unknown_freeze(self):
        self.monitor_only()
        self.prepare()
        key = self.reserve()
        initial = self.ledger()
        tampered = copy.deepcopy(initial)
        tampered["money_reserved"]["core"] = "0"
        repeat.atomic(self.directory / "ledger.private.json", tampered)
        with self.assertRaisesRegex(RuntimeError, "currency_counters"):
            self.reserve()
        repeat.atomic(self.directory / "ledger.private.json", initial)
        changed = copy.deepcopy(self.config)
        changed["moneyBudgetMode"] = "enforced"
        repeat.atomic(self.directory / "config.private.json", changed)
        with self.assertRaises(RuntimeError):
            self.reserve()
        repeat.atomic(self.directory / "config.private.json", self.config)
        repeat.fail(self.directory, key)
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            self.reserve("cross-region")
        self.assertEqual(self.ledger()["money_reserved"], initial["money_reserved"])
        self.assertEqual(self.ledger()["wire_reserved"], initial["wire_reserved"])
        self.azure.assert_not_called()

    def test_monitor_only_keeps_finite_positive_rates_and_fresh_price_evidence(self):
        for field, value in (("txPerDecimalGB", "NaN"), ("vmPerHour", "Infinity"),
                             ("txPerDecimalGB", 0), ("vmPerHour", -1),
                             ("fixedInfraReserve", "NaN"), ("validated", False),
                             ("evidenceReference", "")):
            with self.subTest(field=field, value=value):
                self.config = fixture()
                self.monitor_only()
                self.config["contexts"]["core"]["preflight"][field] = value
                with self.assertRaises(RuntimeError):
                    self.prepare()
                self.assertFalse(self.directory.exists())

    def test_monitor_only_does_not_relax_volume_rate_ttl_resources_or_vm_slots(self):
        for mode in ("application", "wire", "rate", "deadline", "resource", "slot"):
            with self.subTest(mode=mode):
                self.config = fixture()
                self.monitor_only()
                if mode == "application":
                    self.config["approval"]["applicationBytesPerLeg"] += 1
                elif mode == "wire":
                    self.config["approval"]["wireCeilingBytes"] += 1
                elif mode == "rate":
                    self.config["rateBytesPerSecond"] = stream.MAX_RATE + 1
                elif mode == "deadline":
                    self.config["cleanupDeadlineUtc"] = (
                        repeat.APPROVAL_DEADLINE + timedelta(seconds=1)).isoformat()
                elif mode == "resource":
                    self.config["approval"]["resourceIds"].pop()
                if mode == "slot":
                    self.prepare()
                    ledger = self.ledger()
                    ledger["allocated_seconds"]["T"] = repeat.SLOT_SECONDS
                    repeat.atomic(self.directory / "ledger.private.json", ledger)
                    with self.assertRaises(RuntimeError):
                        self.reserve()
                    shutil.rmtree(self.directory)
                else:
                    with self.assertRaises(RuntimeError):
                        self.prepare()
                    self.assertFalse(self.directory.exists())
                self.azure.assert_not_called()

    def test_monitor_only_complete_forty_pairs_reports_original_rates_above_old_caps(self):
        self.monitor_only(null_caps=True)
        self.config["contexts"]["core"]["preflight"].update(
            txPerDecimalGB=".087", vmPerHour=".0114", fixedInfraReserve="2.05")
        self.config["contexts"]["msdn"]["preflight"].update(
            currency="EUR", txPerDecimalGB=".077623126339",
            vmPerHour=".009635974305", fixedInfraReserve=".95")
        summary = repeat.plan_summary(self.config)
        self.test_all_forty_mocked_pairs_exact_four_legs_global_wire_and_no_azure()
        status = repeat.status(self.directory)
        self.assertEqual(status["money_estimate_to_date"], summary["money_estimate_whole_session"])
        self.assertEqual(status["money_estimate_to_date"]["msdn"]["currency"], "EUR")
        for context, former_cap in (("core", 23), ("msdn", 19.62)):
            estimate = repeat.number(status["money_estimate_to_date"][context]["conservative_planning_reserve"])
            self.assertGreater(estimate, repeat.number(former_cap))
        self.assertEqual(status["money_budget_mode"], "monitor-only")
        self.assertEqual(status["billing"], "INCONCLUSIVE")

    def test_atomic_reservation_precedes_hash_and_certificate_contact(self):
        self.prepare()
        def digest(_):
            ledger = self.ledger()
            self.assertEqual(len(ledger["chunks"]), 1)
            self.assertGreater(ledger["wire_reserved"], repeat.BOOTSTRAP)
            self.assertGreater(float(ledger["money_reserved"]["core"]), 1)
            return "b" * 64
        self.digest.side_effect = digest
        key = self.reserve()
        before = self.ledger()
        self.assertEqual(before["chunks"][key]["attempts"], 0)
        with self.assertRaisesRegex(RuntimeError, "unresolved_chunk"):
            self.reserve()
        self.assertEqual(before, self.ledger())
        self.azure.assert_not_called()

    def test_crash_after_reservation_has_no_refund_or_resend(self):
        self.prepare()
        self.digest.side_effect = RuntimeError("simulated_crash")
        with self.assertRaisesRegex(RuntimeError, "simulated_crash"):
            self.reserve()
        ledger = self.ledger()
        with self.assertRaisesRegex(RuntimeError, "unresolved_chunk"):
            self.reserve()
        self.assertEqual(ledger, self.ledger())
        self.assertEqual(len(ledger["chunks"]), 1)

    def test_claim_duplicate_lease_crash_and_failure_never_replay(self):
        self.prepare()
        key = self.reserve()
        self.claim(key, self.lease())
        attempted = self.ledger()
        self.assertEqual(attempted["chunks"][key]["attempts"], 1)
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.claim(key, self.lease())
        repeat.fail(self.directory, key)
        failed = self.ledger()
        self.assertEqual(failed["wire_reserved"], attempted["wire_reserved"])
        self.assertEqual(failed["money_reserved"], attempted["money_reserved"])
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            self.reserve()

    def test_stop_expiry_and_eighty_percent_guard_before_ledger_mutation(self):
        for mode in ("stop", "expired", "eighty", "calls", "not_active", "hour"):
            with self.subTest(mode=mode):
                self.prepare()
                key = self.reserve()
                values = {}
                if mode == "expired":
                    values.update(startedAtUtc=(run.now() - timedelta(minutes=61)).isoformat(),
                                  expiresAtUtc=(run.now() - timedelta(minutes=1)).isoformat())
                elif mode == "eighty":
                    values.update(startedAtUtc=(run.now() - timedelta(minutes=49)).isoformat(),
                                  expiresAtUtc=(run.now() + timedelta(minutes=10)).isoformat())
                elif mode == "calls":
                    values["actualToolCalls"] = 120
                elif mode == "not_active":
                    values["state"] = "not-active-template"
                elif mode == "hour":
                    values["expiresAtUtc"] = (run.now() + timedelta(minutes=61)).isoformat()
                path = self.lease(**values)
                if mode == "stop":
                    (self.directory / "control" / "STOP").write_text("STOP")
                before = self.ledger()
                with self.assertRaises(RuntimeError):
                    self.claim(key, path)
                self.assertEqual(before, self.ledger())
                shutil.rmtree(self.directory)

    def test_whole_wire_currency_allocation_and_ttl_bounds(self):
        for field, value in (("wire_reserved", repeat.WIRE_LIMIT),
                             ("money_reserved", {"core": "23", "msdn": "22"}),
                             ("allocated_seconds", {"A": repeat.SLOT_SECONDS, "C": 0, "T": 0})):
            with self.subTest(field=field):
                self.prepare()
                ledger = self.ledger()
                ledger[field] = value
                repeat.atomic(self.directory / "ledger.private.json", ledger)
                with self.assertRaises(RuntimeError):
                    self.reserve()
                self.assertEqual(ledger, self.ledger())
                shutil.rmtree(self.directory)
        self.config["cleanupDeadlineUtc"] = (run.now() + timedelta(hours=49)).isoformat()
        with self.assertRaisesRegex(RuntimeError, "ttl"):
            self.prepare()

    def test_both_pilot_projection_gate_before_full_chunks(self):
        self.prepare()
        key = self.reserve()
        ledger = self.ledger()
        ledger["chunks"][key].update(state="complete", attempts=1)
        ledger["projections"] = {"same-region": 1000}
        repeat.atomic(self.directory / "ledger.private.json", ledger)
        with self.assertRaisesRegex(RuntimeError, "both_pilots"):
            self.reserve()
        repeat.reserve(self.directory, "cross-region")

    def carry(self, **values):
        prior = dict(A=6300, C=900, T=6300)
        prior.update(values)
        self.config["priorAllocatedSeconds"] = prior
        self.config["approval"].update(
            priorAllocatedSeconds=dict(prior), evidenceReference="OFFLINE-CARRY-PROOF",
            predecessorIdentifier="OFFLINE-BLOCKED-PREDECESSOR")
        return prior

    def test_prepare_approved_carry_status_and_immutable_binding(self):
        prior = self.carry()
        self.prepare()
        self.assertEqual(self.ledger()["allocated_seconds"], prior)
        self.assertEqual(self.ledger()["prior_allocated_seconds"], prior)
        self.assertEqual(repeat.status(self.directory)["prior_allocated_seconds"], prior)
        self.assertEqual(repeat.plan_summary(self.config)["prior_allocated_seconds"], prior)
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.reserve()
        self.assertEqual(self.ledger()["allocated_seconds"]["T"],
                         prior["T"] + repeat.ALLOCATION_RESERVE)
        cfg = run.read(self.directory / "config.private.json")
        cfg["priorAllocatedSeconds"]["A"] = 0
        repeat.atomic(self.directory / "config.private.json", cfg)
        with self.assertRaises(RuntimeError):
            self.reserve("cross-region")

    def test_prior_allocation_invalid_inputs_fail_before_preparation(self):
        for change in (
                lambda c: c["priorAllocatedSeconds"].pop("A"),
                lambda c: c["priorAllocatedSeconds"].update(B=0),
                lambda c: c["priorAllocatedSeconds"].update(T=-1),
                lambda c: c["priorAllocatedSeconds"].update(T=43201),
                lambda c: c["priorAllocatedSeconds"].update(T=True),
                lambda c: c["priorAllocatedSeconds"].update(T=1.5),
                lambda c: c["priorAllocatedSeconds"].update(T="6300"),
                lambda c: c["approval"]["priorAllocatedSeconds"].update(T=True),
                lambda c: c["approval"]["priorAllocatedSeconds"].update(T=0),
                lambda c: c["approval"].pop("priorAllocatedSeconds"),
                lambda c: c.pop("priorAllocatedSeconds"),
                lambda c: c["approval"].pop("evidenceReference"),
                lambda c: c["approval"].update(predecessorIdentifier=" ")):
            candidate = fixture()
            self.carry()
            candidate.update(copy.deepcopy(self.config))
            change(candidate)
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, "prior"):
                repeat.prepare(candidate, self.directory)
            self.assertFalse(self.directory.exists())

    def test_originating_command_error_survives_restore_and_is_per_lease(self):
        lease = {"taskId": "PRIVATE-TASK", "startedAtUtc": run.now().isoformat(), "state": "active"}
        context = {"lease": lease, "operation": "allow", "context": {"private": "context"}}
        process = mock.Mock(returncode=8)
        process.communicate.return_value = (b"PUT Updating", b"originating native error \xff")
        with mock.patch.object(run, "PRIVATE", self.root), \
                mock.patch.object(run.COMMAND_CONTEXT, "value", context, create=True), \
                mock.patch.object(run.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "command_failed") as origin:
                run.bounded(["native", "PRIVATE-ARGV"], 30)
            namespace = run.error_namespace(lease)
            first_path = namespace / "first-error.private.json"
            original = first_path.read_bytes()
            first = run.read(first_path)
            self.assertEqual(first["stdout"], "PUT Updating")
            self.assertEqual(first["code"], 8)
            self.assertIn("\ufffd", first["stderr"])
            self.assertEqual(first["lease"]["taskId"], "PRIVATE-TASK")
            self.assertEqual(first["operation"], "allow")
            self.assertNotIn("PRIVATE-", str(origin.exception))
            self.assertTrue((self.root / first["artifact"]).is_file())
            context["operation"] = "read-restore:restore-nsg"
            process.returncode = 124
            process.communicate.return_value = (b"", b"later restore timeout")
            with self.assertRaises(RuntimeError):
                run.bounded(["native", "restore"], 30)
            self.assertEqual(first_path.read_bytes(), original)
            self.assertEqual(len(list(namespace.glob("*.private.json"))), 3)
            self.assertEqual(run.read(self.root / "last-error.private.json")["code"], 124)
            context["operation"] = "restore-nsg"
            process.returncode = 9
            process.communicate.return_value = (b"", b"another restore failure")
            with self.assertRaises(RuntimeError):
                run.bounded(["native", "restore-put"], 30)
            self.assertEqual(first_path.read_bytes(), original)
            self.assertEqual(len(list(namespace.glob("*.private.json"))), 4)
            context["lease"] = dict(lease, taskId="ANOTHER-PRIVATE-TASK")
            with self.assertRaises(RuntimeError):
                run.bounded(["native", "next-attempt"], 30)
            self.assertEqual(run.read(run.error_namespace(context["lease"]) /
                                      "first-error.private.json")["code"], 9)
            self.assertEqual(first_path.read_bytes(), original)

    def test_timeout_preserves_partial_output_and_safe_exception_after_shutdown(self):
        import subprocess
        process = mock.Mock(returncode=-9)
        process.communicate.return_value = (b"partial stdout \xff", b"partial stderr \xfe")
        context = {"lease": {"taskId": "PRIVATE-TASK"}, "operation": "allow"}
        with mock.patch.object(run, "PRIVATE", self.root), \
                mock.patch.object(run.COMMAND_CONTEXT, "value", context, create=True), \
                mock.patch.object(run.subprocess, "Popen", return_value=process), \
                mock.patch.object(run.subprocess, "run"), \
                mock.patch.object(run.os, "killpg", create=True), \
                mock.patch.object(run.time, "monotonic", side_effect=[0, 2, 3]), \
                self.assertRaises(subprocess.TimeoutExpired) as caught:
            run.bounded(["native", "PRIVATE-SCRIPT-OR-TOKEN"], 1)
        process.kill.assert_called_once()
        process.communicate.assert_called_once_with(timeout=5)
        self.assertNotIn("PRIVATE-", str(caught.exception))
        record = run.read(self.root / caught.exception.private_artifact)
        self.assertEqual(record["kind"], "timeout")
        self.assertEqual(record["stdout"], "partial stdout \ufffd")
        self.assertEqual(record["stderr"], "partial stderr \ufffd")
        self.assertEqual(caught.exception.output, b"partial stdout \xff")

    def test_success_and_access_token_outputs_are_not_logged(self):
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (b"BEARER", b"")
        with mock.patch.object(run, "PRIVATE", self.root), \
                mock.patch.object(run.subprocess, "Popen", return_value=process):
            self.assertEqual(run.bounded(["native", "get-access-token"], 30), "BEARER")
            self.assertFalse((self.root / "command-errors").exists())
            process.returncode = 1
            process.communicate.return_value = (b"BEARER", b"BEARER")
            with self.assertRaises(RuntimeError):
                run.bounded(["native", "get-access-token"], 30)
            record = run.read(self.root / "last-error.private.json")
            self.assertNotIn("BEARER", json.dumps(record))

    def test_prior_carry_cumulative_reservation_cap_each_role(self):
        for role, phase in (("A", "same-region"), ("C", "cross-region"), ("T", "same-region")):
            with self.subTest(role=role):
                self.carry(**{role: repeat.SLOT_SECONDS - repeat.ALLOCATION_RESERVE + 1})
                self.prepare()
                before = self.ledger()
                with self.assertRaisesRegex(RuntimeError, "allocated_slot_cap"):
                    self.reserve(phase)
                self.assertEqual(before, self.ledger())
                shutil.rmtree(self.directory)

    def test_pilot_projection_includes_prior_shared_t_and_a_c_slots(self):
        for role, phase in (("T", "same-region"), ("A", "same-region"), ("C", "cross-region")):
            with self.subTest(role=role):
                self.carry(**{role: 32000})
                self.prepare()
                key = self.completed_fixture(phase, bulk_seconds=100)
                with self.assertRaisesRegex(RuntimeError, "pilot_projection"):
                    repeat.finish(self.directory, key)
                self.assertEqual(self.ledger()["state"], "blocked")
                shutil.rmtree(self.directory)

    def test_shared_t_projection_sums_both_phases_plus_carry_before_bulk(self):
        self.carry(T=20000)
        self.prepare()
        first = self.completed_fixture(bulk_seconds=100)
        repeat.finish(self.directory, first)
        second = self.completed_fixture("cross-region", bulk_seconds=100)
        with self.assertRaisesRegex(RuntimeError, "pilot_projection"):
            repeat.finish(self.directory, second)
        ledger = self.ledger()
        self.assertLess(sum(ledger["projections"].values()), repeat.SLOT_SECONDS)
        self.assertGreaterEqual(20000 + sum(ledger["projections"].values()), repeat.SLOT_SECONDS)
        with self.assertRaises(RuntimeError):
            self.reserve()

    def test_live_public_entry_missing_prerequisites_blocks_before_contact_or_state(self):
        self.prepare()
        key = self.reserve()
        before = self.ledger()
        for action in ("readiness", "snapshot", "pilot", "batch"):
            with self.assertRaises((RuntimeError, FileNotFoundError)):
                repeat.execute(self.directory, key, action, self.directory / "absent.json")
        self.assertEqual(before, self.ledger())
        self.azure.assert_not_called()

    def test_source_and_config_binding_and_exclusive_prepare(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            self.prepare()
        cfg = run.read(self.directory / "config.private.json")
        cfg["rateBytesPerSecond"] -= 1
        repeat.atomic(self.directory / "config.private.json", cfg)
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            self.reserve()

    def test_public_status_sanitized_and_wire_not_double_counted(self):
        self.prepare()
        key = self.reserve()
        ledger = self.ledger()
        chunk = ledger["chunks"][key]
        chunk.update(state="complete", attempts=1, endedAtUtc="2026-10-16T09:00:00+00:00",
                     tx_by_producer={"A": 100, "T": 200}, wire_measured=300)
        ledger["wire_measured"] = 300
        repeat.atomic(self.directory / "ledger.private.json", ledger)
        status = repeat.status(self.directory)
        self.assertEqual(status["wire_measured_once"], 300)
        self.assertEqual(status["tx_by_producer"], {"A": 100, "C": 0, "T": 200})
        self.assertEqual(status["progress_application_bytes"]["A->T"], stream.GIB)
        self.assertEqual(status["progress_application_bytes"]["T->A"], stream.GIB)
        self.assertEqual(status["progress_application_bytes"]["C->T"], 0)
        self.assertFalse(status["complete"])
        text = json.dumps(status)
        for fragment in ("192.0.2.", "/subscriptions/", "expectedTenantId", "currencyCap"):
            self.assertNotIn(fragment, text)

    def test_mocked_completion_hash_proofs_metrics_and_projection(self):
        self.prepare()
        key = self.completed_fixture()
        reserved = self.ledger()
        repeat.finish(self.directory, key)
        ledger = self.ledger()
        self.assertEqual(ledger["wire_reserved"], reserved["wire_reserved"])
        self.assertEqual(ledger["money_reserved"], reserved["money_reserved"])
        self.assertEqual(ledger["allocated_seconds"]["T"], 120)
        self.assertEqual(ledger["wire_measured"], stream.GIB * 2 + 200)
        self.assertIsNone(ledger["active_phase"])
        self.assertIn("same-region", ledger["projections"])
        status = repeat.status(self.directory)
        row = status["chunks"][0]
        self.assertEqual(len(row["network_hash"]), 64)
        self.assertEqual(len(row["endpoint_hash_proofs"]["client"]), 64)
        self.assertEqual(row["network_metrics"]["A"][0]["total"], 12)
        self.assertNotIn("/subscriptions/", json.dumps(status))
        other = self.completed_fixture("cross-region")
        repeat.finish(self.directory, other)
        full = self.reserve()
        self.assertEqual(self.ledger()["chunks"][full]["bytes"], stream.MAX_BYTES)
        self.assertEqual(self.ledger()["chunks"][full]["index"], 1)

    def test_slow_pilot_stops_with_no_fallback_upgrade_or_refund(self):
        self.prepare()
        key = self.completed_fixture(bulk_seconds=1000)
        before = self.ledger()
        with self.assertRaisesRegex(RuntimeError, "pilot_projection"):
            repeat.finish(self.directory, key)
        ledger = self.ledger()
        self.assertEqual(ledger["state"], "blocked")
        self.assertEqual(ledger["chunks"][key]["state"], "complete")
        self.assertEqual(ledger["wire_reserved"], before["wire_reserved"])
        self.assertEqual(ledger["money_reserved"], before["money_reserved"])
        with self.assertRaises(RuntimeError):
            self.reserve("cross-region")

    def test_failed_or_extra_requests_cannot_complete(self):
        for mode in ("failed", "extra", "hash", "unclosed"):
            with self.subTest(mode=mode):
                self.prepare()
                key = self.completed_fixture()
                chunk_dir = self.directory / "chunks" / key
                report = run.read(chunk_dir / "client-report.private.json")
                if mode == "failed":
                    report["success"] = False
                elif mode == "extra":
                    report["requests"] = 3
                elif mode == "hash":
                    report["legs"]["up"]["sha256"] = "b" * 64
                else:
                    path = Path(self.ledger()["chunks"][key]["lease_path"])
                    lease = run.read(path)
                    lease["activeCommands"] = 1
                    run.save(path, lease)
                run.save(chunk_dir / "client-report.private.json", report)
                before = self.ledger()
                with self.assertRaises((RuntimeError, ValueError)):
                    repeat.finish(self.directory, key)
                after = self.ledger()
                self.assertEqual(after["state"], "blocked")
                self.assertEqual(before["wire_reserved"], after["wire_reserved"])
                self.assertEqual(before["money_reserved"], after["money_reserved"])
                shutil.rmtree(self.directory)

    def test_all_forty_mocked_pairs_exact_four_legs_global_wire_and_no_azure(self):
        self.prepare()
        for phase in repeat.PHASES:
            repeat.finish(self.directory, self.completed_fixture(phase))
        sizes = repeat.chunk_sizes()
        for phase in repeat.PHASES:
            for size in sizes[1:]:
                seconds = size / stream.MAX_RATE
                repeat.finish(self.directory, self.completed_fixture(phase, seconds))
        status = repeat.status(self.directory)
        self.assertTrue(status["complete"])
        self.assertEqual(set(status["progress_application_bytes"].values()), {repeat.TARGET})
        self.assertEqual(sum(status["progress_application_bytes"].values()), 400_000_000_000)
        self.assertEqual(len(status["chunks"]), 40)
        self.assertEqual(sum(row["attempts"] for row in status["chunks"]), 40)
        self.assertEqual(status["wire_reserved"], 438_083_886_082)
        self.assertEqual(status["wire_measured_once"], 400_000_008_000)
        self.assertEqual(sum(status["tx_by_producer"].values()), status["wire_measured_once"])
        self.assertLess(status["allocated_seconds"]["T"], repeat.SLOT_SECONDS)
        self.azure.assert_not_called()

    def test_counter_reset_and_expired_readonly_status(self):
        self.prepare()
        self.reserve()
        before = self.ledger()
        ledger = copy.deepcopy(before)
        ledger["wire_reserved"] = repeat.BOOTSTRAP
        repeat.atomic(self.directory / "ledger.private.json", ledger)
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            repeat.status(self.directory)
        repeat.atomic(self.directory / "ledger.private.json", before)
        with mock.patch.object(run, "now", return_value=run.now() + timedelta(days=3)):
            self.assertFalse(repeat.status(self.directory)["complete"])
            with self.assertRaisesRegex(RuntimeError, "ttl"):
                self.reserve()

    def test_skeleton_has_no_authority_and_no_state(self):
        candidate = repeat.skeleton()
        self.assertEqual(candidate["approval"]["status"], "pending")
        self.assertTrue(all(not context["preflight"]["validated"]
                            for context in candidate["contexts"].values()))
        self.assertFalse(self.directory.exists())
        with self.assertRaises(RuntimeError):
            repeat.prepare(candidate, self.directory)

    def test_original_absolute_cutoff_rejects_future_48_hour_canary_before_prepare(self):
        future = repeat.APPROVAL_DEADLINE + timedelta(seconds=1)
        with mock.patch.object(run, "now", return_value=future):
            candidate = fixture()
            end = (future + timedelta(hours=47)).isoformat()
            candidate["cleanupDeadlineUtc"] = end
            candidate["approval"]["expiresAtUtc"] = end
            for context in candidate["contexts"].values():
                context["preflight"]["validUntilUtc"] = end
            with self.assertRaisesRegex(RuntimeError, "repeat_ttl_exceeded"):
                repeat.prepare(candidate, self.directory)
        self.assertFalse(self.directory.exists())
        self.digest.assert_not_called()
        self.cert.assert_not_called()
        self.azure.assert_not_called()

    def test_absolute_and_creation_boundaries_and_skeleton_do_not_renew_approval(self):
        cutoff = repeat.APPROVAL_DEADLINE
        before = cutoff - timedelta(microseconds=1)
        with mock.patch.object(run, "now", return_value=before):
            candidate = fixture()
            repeat.validate_config(candidate)
            self.assertEqual(repeat.timestamp(repeat.skeleton()["cleanupDeadlineUtc"]), cutoff)
        for instant in (cutoff, cutoff + timedelta(seconds=1)):
            with mock.patch.object(run, "now", return_value=instant):
                with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                    repeat.validate_config(candidate)
                with self.assertRaisesRegex(RuntimeError, "original_cleanup_approval_expired"):
                    repeat.skeleton()
        early = cutoff - timedelta(days=4)
        with mock.patch.object(run, "now", return_value=early):
            self.assertEqual(repeat.timestamp(repeat.skeleton()["cleanupDeadlineUtc"]),
                             early + timedelta(hours=47))
            candidate = fixture()
            candidate["cleanupDeadlineUtc"] = (early + timedelta(hours=48)).isoformat()
            repeat.validate_config(candidate)
            candidate["cleanupDeadlineUtc"] = (
                early + timedelta(hours=48, microseconds=1)).isoformat()
            with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                repeat.validate_config(candidate)

    def test_prepared_deadline_is_immutable_even_when_shortened(self):
        self.prepare()
        changed = copy.deepcopy(self.config)
        changed["cleanupDeadlineUtc"] = (
            repeat.timestamp(changed["cleanupDeadlineUtc"]) - timedelta(seconds=1)).isoformat()
        changed["approval"]["expiresAtUtc"] = changed["cleanupDeadlineUtc"]
        for context in changed["contexts"].values():
            context["preflight"]["validUntilUtc"] = changed["cleanupDeadlineUtc"]
        repeat.atomic(self.directory / "config.private.json", changed)
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            self.reserve()
        self.digest.assert_not_called()
        self.azure.assert_not_called()

    def test_lease_template_and_guard_cannot_cross_absolute_deadline(self):
        self.prepare()
        key = self.reserve()
        before = repeat.APPROVAL_DEADLINE - timedelta(minutes=10)
        with mock.patch.object(run, "now", return_value=before):
            for action in ("readiness", "snapshot", "pilot", "batch"):
                lease = repeat.lease_template(self.directory, key, action)
                self.assertEqual(repeat.timestamp(lease["expiresAtUtc"]), repeat.APPROVAL_DEADLINE)
            lease = self.lease(key=key, expiresAtUtc=(
                repeat.APPROVAL_DEADLINE + timedelta(seconds=1)).isoformat())
            with repeat.runner(self.directory, lease):
                with self.assertRaisesRegex(RuntimeError, "expired"):
                    repeat.active_guard(self.directory)
            lease = self.lease(key=key, expiresAtUtc=repeat.APPROVAL_DEADLINE.isoformat())
            with repeat.runner(self.directory, lease):
                with self.assertRaisesRegex(RuntimeError, "command_would_cross_repeat_ttl"):
                    repeat.active_guard(self.directory, seconds=600)


class AdapterTests(unittest.TestCase):
    setUp = RepeatTests.setUp
    prepare = RepeatTests.prepare
    reserve = RepeatTests.reserve
    ledger = RepeatTests.ledger
    lease = RepeatTests.lease

    def cloud(self, subnet_nsg=True):
        import test_stream
        defaults = test_stream.SubnetPolicyTests()
        defaults.setUp()
        self.calls, self.objects, self.power, self.reports = [], {}, {}, {}
        self.failure = None
        self.config["contexts"]["msdn"]["platform"] = "wsl_Ubuntu-24.04_native_cli"
        for alias, endpoint in self.config["endpoints"].items():
            cfg = run.target(self.config["contexts"]["msdn" if alias == "T" else "core"],
                             endpoint["inventory"], alias.lower(), endpoint["region"])
            common = {"location": endpoint["region"],
                      "tags": {"lab": "true", "created_by": "copilot-lab", "run_id": cfg["runId"]},
                      "provisioningState": "Succeeded"}
            rows = endpoint["inventory"]["resources"]
            by_type = {r["type"].split("/")[-1]: r for r in rows}
            for key in ("vm", "nic", "pip", "nsg"):
                self.objects[cfg[key + "_id"].lower()] = dict(common, id=cfg[key + "_id"])
            vm, nic, pip, nsg = (self.objects[cfg[k + "_id"].lower()]
                                 for k in ("vm", "nic", "pip", "nsg"))
            vm.update(vmId=alias.lower() * 32,
                      networkProfile={"networkInterfaces": [{"id": cfg["nic_id"]}]},
                      storageProfile={"osDisk": {"managedDisk": {"id": by_type["disks"]["id"]}},
                                      "dataDisks": []})
            pip.update(ipAddress=endpoint["publicIPv4"])
            vnet = dict(common, id=by_type["virtualNetworks"]["id"])
            subnet = {"id": vnet["id"] + "/subnets/lab", "provisioningState": "Succeeded"}
            self.objects[vnet["id"].lower()] = vnet
            self.objects[subnet["id"].lower()] = subnet
            nic.update(macAddress="00-00-00-00-00-" + str(ord(alias)),
                       networkSecurityGroup={"id": cfg["nsg_id"]},
                       ipConfigurations=[{"privateIPAddress": "10.0.0.4",
                                          "publicIPAddress": {"id": cfg["pip_id"]},
                                          "subnet": {"id": subnet["id"]}}])
            nsg.update(securityRules=copy.deepcopy(defaults.original["securityRules"]),
                       defaultSecurityRules=copy.deepcopy(defaults.original["defaultSecurityRules"]))
            if subnet_nsg:
                extra = dict(common, id=cfg["nsg_id"] + "-subnet", securityRules=[],
                             defaultSecurityRules=copy.deepcopy(nsg["defaultSecurityRules"]))
                subnet["networkSecurityGroup"] = {"id": extra["id"]}
                self.objects[extra["id"].lower()] = extra
                rows.append(dict(extra, name=cfg["nsg"] + "-subnet",
                                 type="Microsoft.Network/networkSecurityGroups"))
                self.config["approval"]["resourceIds"].append(extra["id"])
            self.power[alias] = "deallocated"
        self.azure.side_effect = self.invoke
        self.cert.side_effect = self.fake_certificates

    def fake_certificates(self, directory, host):
        directory.mkdir()
        for name in ("ca.pem", "client.pem", "client.key", "server.pem", "server.key"):
            (directory / name).write_text("OFFLINE TEST ONLY")

    def invoke(self, client, argv, operation, seconds, directory):
        alias = client.config["vm"][-1].upper()
        self.assertEqual(client.wsl, alias == "T")
        self.calls.append((alias, list(argv), operation))
        if self.failure:
            self.failure(alias, argv, operation, directory)
        if argv == ["account", "show"]:
            return {"id": client.config["subscriptionId"],
                    "tenantId": client.config["expectedTenantId"], "state": "Enabled"}
        if argv[:2] == ["vm", "get-instance-view"]:
            return {"statuses": [{"code": "PowerState/" + self.power[alias]}]}
        if argv[:2] in (["vm", "start"], ["vm", "deallocate"]):
            self.assertIn("--no-wait", argv)
            self.assertGreater(seconds, 0)
            self.assertLessEqual(seconds, 90)
            self.power[alias] = "running" if argv[1] == "start" else "deallocated"
            return {}
        if argv[:2] == ["vm", "run-command"]:
            plan = run.read(directory / "plan.private.json")
            if operation.startswith("ready-"):
                report = {"success": True, "role": "guest_readiness",
                          "binding": run.readiness_config(directory, "server" if alias == "T"
                                                          else "client", plan)}
            else:
                report = self.payload_report(plan, operation)
                self.reports[operation] = report
                script = (directory / (operation + ".private.sh")).read_text()
                encoded = re.search(r"base64\.b64decode\(([^)]+)\)", script).group(1)
                bundle = json.loads(base64.b64decode(ast.literal_eval(encoded)))
                cfg = json.loads(bundle["config.json"])
                stream.validate(cfg)
                self.assertEqual(cfg["rate_ceiling"], stream.MAX_RATE)
                self.assertEqual(cfg["rate"], stream.MAX_RATE)
                self.assertEqual(cfg["aliases"], plan["aliases"])
                self.assertEqual(bundle["stream.py"], (run.HERE / "stream.py").read_text())
                profile = run.runtime(plan)
                self.assertIn(str(profile["foregroundSeconds"]) + "s", script)
                self.assertEqual(cfg["deadline"], profile["streamSeconds"])
                self.assertEqual(seconds, profile["commandSeconds"])
                self.assertIn("OFFLINE TEST ONLY", bundle[operation + ".key"])
            return {"value": [{"message": json.dumps(report)}]}
        if argv[:3] == ["monitor", "metrics", "list"]:
            return {"value": [{"name": {"value": "Network Out Total"},
                               "timeseries": [{"data": [{"timeStamp": run.now().isoformat(),
                                                         "total": 42}]}]}]}
        if argv[0] == "rest":
            identity = argv[argv.index("--url") + 1].split("?")[0].split(
                "https://management.azure.com")[1].lower()
            self.assertEqual(argv[argv.index("--body") + 1].startswith("@/mnt/"), os.name == "nt")
            prefix = "subnet-nsg" if "subnet" in operation else "nsg"
            body = run.read(directory / (prefix + ("-restore" if operation in run.RESTORE
                                                   else "-allow") + ".private.json"))
            obj = self.objects[identity]
            obj["securityRules"] = [dict(r["properties"], name=r["name"],
                                         provisioningState="Succeeded")
                                    for r in body["properties"]["securityRules"]]
            return {"provisioningState": "Succeeded"}
        if "--ids" in argv:
            identity = argv[argv.index("--ids") + 1]
        else:
            kind = "vm" if argv[0] == "vm" else "pip" if argv[1] == "public-ip" else argv[1]
            identity = client.config[kind + "_id"]
        return copy.deepcopy(self.objects[identity.lower()])

    def payload_report(self, plan, role):
        started = run.now().isoformat()
        report = {"success": True, "role": role, "declared_legs": ["up", "down"],
                  "aliases": plan["aliases"], "requests": 2,
                  "nic": {"delta": {"rx": plan["bytes"] + 100, "tx": plan["bytes"] + 100,
                                    "wire_once": plan["bytes"] * 2 + 200}}, "legs": {}}
        for leg, producer, consumer in (("up", plan["aliases"]["client"], "T"),
                                       ("down", "T", plan["aliases"]["client"])):
            report["legs"][leg] = {
                "id": plan["id"] + "-" + leg, "producer": producer, "consumer": consumer,
                "bytes": plan["bytes"], "sha256": plan["payload_sha256"], "status": "ok",
                "retries": 0, "started": started, "ended": run.now().isoformat()}
        return report

    def cli(self, key, action, lease):
        with mock.patch.object(repeat, "ROOT", self.root), \
                mock.patch.object(sys, "argv", ["repeat.py", action, "--session", "fresh",
                                              "--chunk", key, "--lease", str(lease)]):
            repeat.main()

    def ready_snapshot(self, phase="same-region"):
        key = self.reserve(phase)
        for action in ("readiness", "snapshot"):
            before = len(self.calls)
            lease = self.lease(action, key)
            try:
                self.cli(key, action, lease)
            except Exception:
                evidence = run.read(self.directory / "chunks" / key / "readiness.private.json")
                self.fail("adapter_readiness_or_snapshot_failure:" + repr(evidence.get("failures")))
            closed = run.read(lease)
            self.assertEqual(closed["state"], "completed")
            self.assertEqual(closed["actualToolCalls"], len(self.calls) - before)
            self.assertEqual(closed["activeCommands"], 0)
            self.assertTrue(closed["ownedProcessesIdle"])
        return key

    def test_expired_absolute_deadline_all_public_phases_stop_before_contact_or_reservation(self):
        self.cloud()
        self.prepare()
        key = self.reserve()
        leases = {action: self.lease(action, key) for action in
                  ("readiness", "snapshot", "pilot", "batch")}
        before = self.ledger()
        self.calls.clear()
        for instant in (repeat.APPROVAL_DEADLINE, repeat.APPROVAL_DEADLINE + timedelta(seconds=1)):
            with mock.patch.object(run, "now", return_value=instant):
                for action, lease in leases.items():
                    with self.subTest(instant=instant, action=action):
                        with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                            self.cli(key, action, lease)
                with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                    self.reserve()
                with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                    repeat.claim(self.directory, key, leases["pilot"])
                with self.assertRaisesRegex(RuntimeError, "repeat_ttl"):
                    with repeat.runner(self.directory, leases["pilot"]):
                        repeat.active_guard(self.directory)
                (self.directory / "control" / "STOP").write_text("STOP")
                with self.assertRaises(RuntimeError):
                    with repeat.runner(self.directory, leases["pilot"]):
                        repeat.active_guard(self.directory, "restore-nsg")
                (self.directory / "control" / "STOP").unlink()
        self.assertEqual(before, self.ledger())
        self.assertEqual(self.calls, [])
        self.assertEqual(set(self.power.values()), {"deallocated"})

    def test_readiness_rejects_unapproved_storage_on_either_endpoint_before_any_mutation(self):
        modes = ("replacement", "foreign_rg", "foreign_subscription", "missing", "empty",
                 "bad_type", "child_id", "missing_managed", "missing_profile",
                 "data_disk", "data_false", "data_missing")
        for alias in ("A", "T"):
            for mode in modes:
                with self.subTest(alias=alias, mode=mode):
                    self.cloud(subnet_nsg=False)
                    self.prepare()
                    key = self.reserve()
                    plan = run.read(self.directory / "chunks" / key / "plan.private.json")
                    vm = self.objects[plan[alias]["vm_id"].lower()]
                    storage = vm["storageProfile"]
                    managed = storage["osDisk"]["managedDisk"]
                    if mode == "replacement":
                        managed["id"] += "-replacement"
                    elif mode == "foreign_rg":
                        managed["id"] = managed["id"].replace("/rg-test-fresh-", "/rg-foreign-")
                    elif mode == "foreign_subscription":
                        managed["id"] = managed["id"].replace(
                            plan[alias]["subscriptionId"], "foreign-sub")
                    elif mode == "missing":
                        managed.pop("id")
                    elif mode == "empty":
                        managed["id"] = ""
                    elif mode == "bad_type":
                        managed["id"] = False
                    elif mode == "child_id":
                        managed["id"] += "/child"
                    elif mode == "missing_managed":
                        storage["osDisk"].pop("managedDisk")
                    elif mode == "missing_profile":
                        vm.pop("storageProfile")
                    elif mode == "data_disk":
                        storage["dataDisks"] = [{"managedDisk": {"id": managed["id"] + "-data"}}]
                    elif mode == "data_false":
                        storage["dataDisks"] = False
                    else:
                        storage.pop("dataDisks")
                    with self.assertRaisesRegex(RuntimeError, "readiness_failed"):
                        self.cli(key, "readiness", self.lease("readiness", key))
                    failures = run.read(self.directory / "chunks" / key /
                                        "readiness.private.json")["failures"]
                    self.assertTrue(any("disk" in item or "storage" in item for item in failures),
                                    failures)
                    self.assertFalse(any(call[2] for call in self.calls), self.calls)
                    self.assertEqual(set(self.power.values()), {"deallocated"})
                    shutil.rmtree(self.directory)

    def test_snapshot_rejects_later_storage_swap_without_starting_either_endpoint(self):
        self.cloud()
        self.prepare()
        key = self.reserve()
        self.cli(key, "readiness", self.lease("readiness", key))
        plan = run.read(self.directory / "chunks" / key / "plan.private.json")
        self.objects[plan["T"]["vm_id"].lower()]["storageProfile"]["osDisk"]["managedDisk"]["id"] += "-swap"
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "approved_os_disk_inventory_mismatch"):
            self.cli(key, "snapshot", self.lease("snapshot", key))
        self.assertFalse(any(call[2] for call in self.calls), self.calls)
        self.assertEqual(set(self.power.values()), {"deallocated"})

    def test_minimal_approved_storage_case_canonicalization_and_inventory_fail_closed(self):
        config = fixture()
        endpoint = config["endpoints"]["A"]
        inventory = endpoint["inventory"]
        cfg = run.target(config["contexts"]["core"], inventory, "a")
        disk = next(row for row in inventory["resources"]
                    if row["type"] == "Microsoft.Compute/disks")
        vm = {"storageProfile": {"osDisk": {"managedDisk": {"id": disk["id"].upper()}},
                                 "dataDisks": []}}
        run.approved_os_disk(vm, cfg, inventory)
        # An inventory-approved disk need not use the VM's suffix.
        disk["name"] = "actual-legacy-managed-os"
        disk["id"] = disk["id"].rsplit("/", 1)[0] + "/" + disk["name"]
        vm["storageProfile"]["osDisk"]["managedDisk"]["id"] = disk["id"]
        run.approved_os_disk(vm, cfg, inventory)
        for mode in ("missing", "ambiguous", "wrong_type", "wrong_tags", "wrong_region",
                     "wrong_run", "wrong_root"):
            candidate = copy.deepcopy(inventory)
            row = next(row for row in candidate["resources"]
                       if row["type"] == "Microsoft.Compute/disks")
            if mode == "missing":
                candidate["resources"].remove(row)
            elif mode == "ambiguous":
                candidate["resources"].append(copy.deepcopy(row))
            elif mode == "wrong_type":
                row["type"] = "Microsoft.Network/disks"
            elif mode == "wrong_tags":
                row["tags"] = {}
            elif mode == "wrong_region":
                row["location"] = "northeurope"
            elif mode == "wrong_run":
                candidate["runId"] = "foreign"
            else:
                candidate["groupId"] += "-foreign"
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "inventory"):
                run.approved_os_disk(vm, cfg, candidate)

    def test_public_cli_real_readiness_snapshot_pilot_each_phase_and_exact_call_budget(self):
        self.cloud()
        self.prepare()
        for phase, alias in repeat.PHASES.items():
            before = len(self.calls)
            key = self.ready_snapshot(phase)
            # Each asynchronous boot adds a required current-phase instance-view GET.
            self.assertEqual(len(self.calls) - before, 54)
            self.assertEqual(self.ledger()["chunks"][key]["attempts"], 0)
            lease = self.lease(key=key)
            before = len(self.calls)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.cli(key, "pilot", lease)
            calls = self.calls[before:]
            self.assertEqual(len(calls), 50)
            self.assertNotIn("/subscriptions/", output.getvalue())
            self.assertIn("calls 25/150", output.getvalue())
            closed = run.read(lease)
            self.assertEqual(closed["actualToolCalls"], 50)
            self.assertEqual(closed["actualMutations"], 10)
            self.assertEqual(closed["state"], "completed")
            self.assertEqual(closed["activeCommands"], 0)
            self.assertTrue(closed["ownedProcessesIdle"])
            ops = [call[2] for call in calls]
            self.assertLess(ops.index("allow-subnet"), ops.index("allow"))
            self.assertLess(ops.index("allow"), ops.index("client"))
            first_restore = ops.index("restore-nsg")
            for operation in ("server", "client", "deallocate-t", "deallocate-" + alias.lower()):
                self.assertLess(ops.index(operation), first_restore)
            self.assertLess(first_restore, ops.index("restore-subnet-nsg"))
            self.assertEqual(set(self.power.values()), {"deallocated"})
            plan = run.read(self.directory / "chunks" / key / "plan.private.json")
            self.assertNotEqual(plan[alias]["expectedTenantId"], plan["T"]["expectedTenantId"])
            self.assertNotEqual(plan[alias]["subscriptionId"], plan["T"]["subscriptionId"])
            self.assertEqual(plan[alias]["region"],
                             "northeurope" if alias == "C" else "swedencentral")
            self.assertEqual(self.ledger()["chunks"][key]["state"], "complete")
        self.assertEqual(set(self.ledger()["projections"]), set(repeat.PHASES))
        key = self.ready_snapshot()
        self.assertEqual(self.ledger()["chunks"][key]["index"], 1)
        self.assertEqual(self.ledger()["chunks"][key]["bytes"], stream.MAX_BYTES)
        with self.assertRaisesRegex(RuntimeError, "index_mismatch"):
            self.cli(key, "pilot", self.lease(key=key))
        lease = self.lease("batch", key)
        self.cli(key, "batch", lease)
        self.assertEqual(run.read(lease)["actualToolCalls"], 50)
        self.assertEqual(self.ledger()["chunks"][key]["state"], "complete")

    def test_single_layer_call_budget_and_failed_restore_never_refunds_or_replays(self):
        self.cloud(subnet_nsg=False)
        self.prepare()
        key = self.ready_snapshot()
        lease = self.lease(key=key)
        before = len(self.calls)
        def fail_restore(alias, argv, operation, directory):
            if operation == "restore-nsg":
                raise RuntimeError("offline_restore_failure")
        self.failure = fail_restore
        reserved = self.ledger()
        with self.assertRaisesRegex(RuntimeError, "live_failed"):
            self.cli(key, "pilot", lease)
        after = self.ledger()
        self.assertEqual(after["state"], "blocked")
        self.assertEqual(after["chunks"][key]["attempts"], 1)
        self.assertEqual(after["money_reserved"], reserved["money_reserved"])
        self.assertEqual(after["wire_reserved"], reserved["wire_reserved"])
        self.assertEqual(after["allocated_seconds"], reserved["allocated_seconds"])
        self.assertEqual(run.read(lease)["activeCommands"], 0,
                         run.read(self.directory / "chunks" / key / "plan.private.json")["failures"])
        self.assertEqual(run.read(lease)["state"], "blocked")
        self.assertEqual(sum(row[2] == "restore-nsg" for row in self.calls[before:]), 1)
        with self.assertRaises(RuntimeError):
            self.cli(key, "pilot", self.lease(key=key))

    def test_single_layer_success_fits_explicit_75_call_lease(self):
        self.cloud(subnet_nsg=False)
        self.prepare()
        key = self.ready_snapshot()
        lease = self.lease(key=key, maxToolCalls=75)
        before = len(self.calls)
        self.cli(key, "pilot", lease)
        self.assertEqual(len(self.calls) - before, 35)
        self.assertEqual(run.read(lease)["state"], "completed")
        self.assertEqual(run.read(lease)["actualMutations"], 8)

    def test_stop_during_setup_blocks_guests_and_restore_without_relaxing_stop(self):
        self.cloud()
        self.prepare()
        key = self.ready_snapshot()
        lease = self.lease(key=key)
        def stop(alias, argv, operation, directory):
            if operation == "allow":
                (self.directory / "control" / "STOP").write_text("STOP")
        self.failure = stop
        before = len(self.calls)
        with self.assertRaisesRegex(RuntimeError, "live_failed"):
            self.cli(key, "pilot", lease)
        calls = self.calls[before:]
        self.assertFalse(any(row[2] in ("client", "server", "restore-nsg") for row in calls))
        self.assertEqual(run.read(lease)["state"], "blocked")
        self.assertEqual(run.read(lease)["activeCommands"], 0)
        self.assertEqual(self.ledger()["state"], "blocked")
        self.assertEqual(self.ledger()["chunks"][key]["attempts"], 1)

    def test_fresh_lease_exact_objective_owner_and_phase_receipts_required(self):
        self.cloud()
        self.prepare()
        key = self.reserve()
        before = self.ledger()
        for values in ({"maxToolCalls": 25}, {"objective": "unrelated"},
                       {"maxMutations": 13}, {"acceptLiveGates": False}):
            with self.assertRaises(RuntimeError):
                self.cli(key, "pilot", self.lease(key=key, **values))
            self.assertEqual(self.ledger(), before)
        first = self.lease("readiness", key)
        self.cli(key, "readiness", first)
        with self.assertRaises(RuntimeError):
            self.cli(key, "snapshot", self.lease("snapshot", key,
                                                ownerId=run.read(first)["ownerId"]))
        self.cli(key, "snapshot", self.lease("snapshot", key))
        before = self.ledger()
        for values in ({"maxToolCalls": 25}, {"objective": "unrelated"},
                       {"maxMutations": 13}, {"acceptLiveGates": False}):
            with self.assertRaises(RuntimeError):
                self.cli(key, "pilot", self.lease(key=key, **values))
            self.assertEqual(self.ledger(), before)
        receipt = self.ledger()["chunks"][key]["phases"]["snapshot"]
        closed = run.read(receipt["lease_path"])
        closed["actualToolCalls"] -= 1
        run.save(receipt["lease_path"], closed)
        with self.assertRaisesRegex(RuntimeError, "receipt_changed"):
            self.cli(key, "pilot", self.lease(key=key))
        self.assertEqual(self.ledger()["chunks"][key]["attempts"], 0)

    def test_pending_public_template_has_no_authority(self):
        self.prepare()
        key = self.reserve()
        with mock.patch.object(repeat, "ROOT", self.root), \
                mock.patch.object(sys, "argv", ["repeat.py", "lease-template", "--session", "fresh",
                                              "--chunk", key, "--lease-kind", "pilot"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            repeat.main()
        lease = json.loads(output.getvalue())
        self.assertEqual(lease["state"], "pending")
        self.assertEqual(lease["maxToolCalls"], 150)
        self.assertEqual(lease["namedCommandTimeoutSeconds"], {"server": 900, "client": 900})
        self.assertFalse(lease["acceptLiveGates"])
        self.azure.assert_not_called()

    def test_plan_profile_and_exact_named_lease_mismatches_fail_before_contact(self):
        self.prepare()
        key = self.reserve()
        plan_path = self.directory / "chunks" / key / "plan.private.json"
        original = run.read(plan_path)
        for field in original["runtime_profile"]:
            changed = copy.deepcopy(original)
            changed["runtime_profile"][field] += 1
            run.save(plan_path, changed)
            with self.assertRaisesRegex(RuntimeError, "plan_binding_changed"):
                repeat.validate_plan(changed)
        run.save(plan_path, original)
        for changes in ({"commandTimeoutSeconds": 2500},
                        {"namedCommandTimeoutSeconds": {"server": 2500, "client": 2500}},
                        {"runtime_profile": dict(original["runtime_profile"], restoreSeconds=899)}):
            with mock.patch.object(repeat, "require_prepared_traffic"), \
                    self.assertRaisesRegex(RuntimeError, "new_bounded_idle_phase"):
                repeat.begin(self.directory, key, "pilot", self.lease(key=key, **changes))
        self.azure.assert_not_called()
        self.assertEqual(self.ledger()["chunks"][key]["attempts"], 0)

    def test_ambiguous_start_observes_but_blocks_payload_and_preserves_original(self):
        self.cloud()
        self.prepare()
        key = self.ready_snapshot()
        lease = self.lease(key=key)
        before = len(self.calls)
        def ambiguous(alias, argv, operation, directory):
            if operation == "start-a":
                self.power[alias] = "running"
                raise RuntimeError("FIRST-ambiguous-native-start")
        self.failure = ambiguous
        with self.assertRaisesRegex(RuntimeError, "live_failed"):
            self.cli(key, "pilot", lease)
        calls = self.calls[before:]
        self.assertEqual(sum(row[2] == "start-a" for row in calls), 1)
        self.assertFalse(any(row[2] in ("server", "client") for row in calls))
        self.assertEqual(set(self.power.values()), {"deallocated"})
        self.assertEqual(run.read(lease)["state"], "blocked")
        self.assertEqual(run.read(lease)["activeCommands"], 0)
        plan = run.read(self.directory / "chunks" / key / "plan.private.json")
        self.assertEqual(plan["failures"][0], "FIRST-ambiguous-native-start")
        ops = [row[2] for row in calls]
        for operation in ("deallocate-a", "deallocate-t"):
            self.assertLess(ops.index("read-restore:" + operation), ops.index("restore-nsg"))
        commands = run.read(self.directory / "chunks" / key / "commands.private.json")
        for operation in ("start-a", "start-t", "deallocate-a", "deallocate-t"):
            self.assertIn("--no-wait", commands[operation]["argv_before_native_path_conversion"])

    def test_pending_start_timeout_expiry_and_eighty_percent_close_without_payload(self):
        for mode in ("timeout", "expiry", "calls"):
            with self.subTest(mode=mode):
                if self.directory.exists():
                    shutil.rmtree(self.directory)
                self.config = fixture()
                self.cloud()
                self.prepare()
                key = self.ready_snapshot()
                lease_path = self.lease(key=key)
                before = len(self.calls)
                epoch, elapsed = run.now(), [0]
                from test_runtime import UNPUBLISHED_VIEW
                native = self.azure.side_effect
                def pending(client, argv, operation, seconds, directory):
                    result = native(client, argv, operation, seconds, directory)
                    if client.config["vm"].endswith("a") \
                            and argv[:2] == ["vm", "get-instance-view"] and operation is None:
                        return copy.deepcopy(UNPUBLISHED_VIEW)
                    return result
                self.azure.side_effect = pending
                real_sleep = run.time.sleep
                def advance(seconds):
                    if seconds != 30:
                        real_sleep(seconds)
                        return
                    elapsed[0] += 4000 if mode == "expiry" and seconds == 30 else seconds
                    real_sleep(.1)  # Let the other VM and NSG workers acquire real file locks.
                    if mode == "calls" and seconds == 30:
                        with run.lease_lock("read-restore:accounting"):
                            lease = run.read(lease_path)
                            lease["actualToolCalls"] = 120
                            run.save(lease_path, lease)
                with mock.patch.object(run, "now", side_effect=lambda: epoch + timedelta(
                        seconds=elapsed[0])), \
                        mock.patch.object(run.time, "monotonic", side_effect=lambda: elapsed[0]), \
                        mock.patch.object(run.time, "sleep", side_effect=advance), \
                        self.assertRaisesRegex(RuntimeError, "live_failed"):
                    self.cli(key, "pilot", lease_path)
                calls = self.calls[before:]
                self.assertEqual(sum(row[2] == "start-a" for row in calls), 1)
                self.assertFalse(any(row[2] in ("server", "client") for row in calls))
                plan = run.read(self.directory / "chunks" / key / "plan.private.json")
                self.assertTrue(plan["failures"])
                self.assertIn("restore_started", plan)
                closed = run.read(lease_path)
                self.assertEqual(closed["state"], "blocked")
                self.assertEqual(closed["activeCommands"], 0)
                self.assertTrue(closed["ownedProcessesIdle"])
                self.assertLessEqual(closed["actualToolCalls"], closed["maxToolCalls"])
                self.assertEqual(self.ledger()["chunks"][key]["attempts"], 1)
                if mode == "timeout":
                    self.assertEqual(set(self.power.values()), {"deallocated"})
                    self.assertIn("vm_state_observation_timeout", plan["failures"][0])
                else:
                    self.assertTrue(any("restore" in failure or "deallocate" in failure
                                        for failure in plan["failures"])
                                    or set(self.power.values()) == {"deallocated"})
                shutil.rmtree(self.directory)

    def test_repeat_child_circuit_terminates_on_stop_or_expiry_and_restores_globals(self):
        import subprocess
        for mode in ("stop", "expiry"):
            with self.subTest(mode=mode):
                self.prepare()
                key = self.reserve()
                lease_path = self.lease(key=key)
                old = run.PRIVATE, run.LEASE, run.EXECUTION_GUARD
                children = []
                def cancel():
                    if mode == "stop":
                        (self.directory / "control" / "STOP").write_text("STOP")
                    else:
                        lease = run.read(lease_path)
                        lease["expiresAtUtc"] = (run.now() - timedelta(seconds=1)).isoformat()
                        repeat.atomic(lease_path, lease)
                timer = threading.Timer(.25, cancel)
                timer.start()
                original_popen = subprocess.Popen
                def spawn(*args, **kwargs):
                    process = original_popen(*args, **kwargs)
                    children.append(process)
                    return process
                try:
                    with repeat.runner(self.directory, lease_path), \
                            mock.patch.object(run.subprocess, "Popen", side_effect=spawn), \
                            self.assertRaisesRegex(RuntimeError, "repeat_stop|expired"):
                        run.bounded([sys.executable, "-c", "import time; time.sleep(30)"], 10)
                finally:
                    timer.join(2)
                self.assertFalse(timer.is_alive())
                self.assertEqual((run.PRIVATE, run.LEASE, run.EXECUTION_GUARD), old)
                self.assertTrue(children)
                self.assertTrue(all(process.poll() is not None for process in children))
                shutil.rmtree(self.directory)

    def test_claimed_lease_cannot_be_replaced_or_extended_and_restores_remain_bounded(self):
        self.prepare()
        key = self.reserve()
        lease_path = self.lease(key=key)
        RepeatTests.claim(self, key, lease_path)
        with repeat.runner(self.directory, lease_path):
            lease = run.read(lease_path)
            lease.update(actualToolCalls=120, actualMutations=10)
            repeat.atomic(lease_path, lease)
            with self.assertRaisesRegex(RuntimeError, "restoration_only"):
                run.guard("server", 30)
            run.guard("restore-nsg", 30)
            run.guard("read-restore:restore-nsg", 30)
            lease["maxToolCalls"] = 151
            repeat.atomic(lease_path, lease)
            with self.assertRaisesRegex(RuntimeError, "binding_changed"):
                run.guard("restore-nsg", 30)
            lease["maxToolCalls"] = 150
            lease["taskId"] = "different-task"
            repeat.atomic(lease_path, lease)
            with self.assertRaisesRegex(RuntimeError, "binding_changed"):
                run.guard("restore-nsg", 30)
            with self.assertRaisesRegex(RuntimeError, "binding_changed"):
                run.save(lease_path, dict(lease, state="blocked"))
            self.assertEqual(run.read(lease_path)["state"], "active")

    def test_parallel_native_calls_keep_atomic_lease_counters_and_idle_state(self):
        import concurrent.futures
        self.prepare()
        key = self.reserve()
        lease = self.lease(key=key)
        RepeatTests.claim(self, key, lease)
        plan = run.read(self.directory / "chunks" / key / "plan.private.json")
        self.azure.side_effect = None
        self.azure.return_value = {}
        with repeat.runner(self.directory, lease):
            client = run.azure(plan, "A")
            def query(_):
                for _ in range(5):
                    client.cli(["offline-test-only"], seconds=1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(query, range(4)))
            closed = run.read(lease)
        self.assertEqual(closed["actualToolCalls"], 20)
        self.assertEqual(closed["activeCommands"], 0)
        self.assertTrue(closed["ownedProcessesIdle"])
        self.assertEqual(closed["actualMutations"], 0)


if __name__ == "__main__":
    unittest.main()
