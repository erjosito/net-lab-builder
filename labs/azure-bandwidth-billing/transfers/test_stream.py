"""Small localhost-only contract tests; generated certificates remain lab-private."""
import contextlib
import atexit
import http.client
import json
import socket
import shutil
import ssl
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import run
import stream

ROOT = run.PRIVATE / ("local-tests-" + uuid.uuid4().hex)
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)


class StreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ROOT.mkdir(parents=True, exist_ok=True)
        run.certificates(ROOT / "tls", "127.0.0.1")

    def config(self, role, **extra):
        result = {"id": "a" * 32, "bytes": 32768, "rate": stream.RATE,
                  "deadline": 5, "idle": .3, "wire_cap": 1024 ** 2, "interface": "test",
                  "bind": "127.0.0.1", "host": "127.0.0.1", "port": 0,
                  "expected_peer": "127.0.0.1", "report": str(ROOT / (role + ".json")),
                  "ca": str(ROOT / "tls" / "ca.pem"),
                  "cert": str(ROOT / "tls" / (role + ".pem")),
                  "key": str(ROOT / "tls" / (role + ".key"))}
        result.update(extra)
        return result

    @contextlib.contextmanager
    def server(self, **extra):
        server = stream.TransferServer(self.config("server", **extra),
                                       lambda _: {"rx": 10, "tx": 20})
        thread = threading.Thread(target=server.run)
        thread.start()
        try:
            yield server
        finally:
            server.done.set()
            server.guard.stop()
            thread.join(3)
            self.assertFalse(thread.is_alive(), "server did not stop")

    def connection(self, server, cert=True):
        ctx = stream.context(self.config("client")) if cert else ssl.create_default_context(
            cafile=str(ROOT / "tls" / "ca.pem"))
        return http.client.HTTPSConnection("127.0.0.1", server.server_port, context=ctx, timeout=2)

    def test_concurrent_exact_hashes_lifecycle(self):
        with self.server() as server:
            result = stream.client(self.config("client", port=server.server_port),
                                   lambda _: {"rx": 1, "tx": 2})
            self.assertTrue(result["success"], result)
            worst_probe_report = dict(result, readiness_probes=result["readiness_probes"] * 12)
            self.assertLess(len(json.dumps(worst_probe_report, separators=(",", ":"))), 3500)
        report = run.read(ROOT / "server.json")
        self.assertEqual(stream.verify(result, report)["transport"], "PASS")
        self.assertEqual(report["requests"], 2)
        self.assertEqual(len(report["legs"]), 2)
        self.assertEqual(server.attempts, 2, "readiness must reuse the upload connection")
        self.assertEqual(report["handshake_or_empty_probes"], 0)

    def test_missing_client_certificate_rejected(self):
        with self.server() as server:
            connection = self.connection(server, False)
            with self.assertRaises((ssl.SSLError, OSError, http.client.HTTPException)):
                connection.request("GET", "/" + "a" * 32 + "/down")
                connection.getresponse()
            connection.close()
            self.assertEqual(server.claimed, set())

    def test_wrong_server_san_rejected(self):
        with self.server() as server:
            ctx = stream.context(self.config("client"))
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as raw:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    ctx.wrap_socket(raw, server_hostname="not-the-server.invalid")

    def test_two_slots_bound_and_stop(self):
        with self.server() as server:
            ctx = stream.context(self.config("client"))
            sockets = []
            try:
                for _ in range(2):
                    raw = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
                    sockets.append(ctx.wrap_socket(raw, server_hostname="127.0.0.1"))
                raw = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
                with raw, self.assertRaises((ssl.SSLError, OSError)):
                    ctx.wrap_socket(raw, server_hostname="127.0.0.1")
            finally:
                for connection in sockets:
                    connection.close()
            self.assertTrue(server.done.wait(1))

    def test_strict_upload_lengths_and_chunking(self):
        for headers in ({"Content-Length": "32769"}, {"Content-Length": "-1"},
                        {"Transfer-Encoding": "chunked"}, {}):
            with self.subTest(headers=headers), self.server() as server:
                connection = self.connection(server)
                connection.putrequest("POST", "/" + "a" * 32 + "/up")
                for key, value in headers.items():
                    connection.putheader(key, value)
                connection.endheaders()
                try:
                    self.assertEqual(connection.getresponse().status, 400)
                except (OSError, http.client.HTTPException):
                    pass  # Fail-closed cancellation may close before an error response.
                connection.close()
                self.assertNotIn("up", server.claimed)

    def test_corrupt_payload_fails(self):
        with self.server() as server:
            connection = self.connection(server)
            connection.request("POST", "/" + "a" * 32 + "/up", b"x" * 32768,
                               headers={"Content-Length": "32768"})
            with contextlib.suppress(OSError, http.client.HTTPException):
                connection.getresponse().read()
            connection.close()
        report = run.read(ROOT / "server.json")
        self.assertFalse(report["success"])
        self.assertIn("hash_or_count_mismatch", report["legs"]["up"]["status"])

    def test_truncated_upload_fails_and_exits(self):
        with self.server() as server:
            connection = self.connection(server)
            connection.request("POST", "/" + "a" * 32 + "/up", b"x",
                               headers={"Content-Length": "32768"})
            time.sleep(.5)
            connection.close()
        self.assertFalse(run.read(ROOT / "server.json")["success"])

    def test_no_progress_timeout(self):
        with self.server() as server:
            connection = self.connection(server)
            connection.request("POST", "/" + "a" * 32 + "/up", b"",
                               headers={"Content-Length": "32768"})
            time.sleep(.5)
            connection.close()
        self.assertFalse(run.read(ROOT / "server.json")["success"])

    def test_client_failure_cancels_both(self):
        with self.server() as server:
            server.expected = "0" * 64
            result = stream.client(self.config("client", port=server.server_port),
                                   lambda _: {"rx": 0, "tx": 0})
            self.assertFalse(result["success"])
            self.assertEqual(set(result["legs"]), {"up", "down"})
            self.assertTrue(all(r["retries"] == 0 for r in result["legs"].values()))
        self.assertFalse(run.read(ROOT / "server.json")["success"])

    def test_server_total_deadline_no_requests(self):
        with self.server(deadline=.1) as server:
            self.assertTrue(server.guard.cancel.wait(1))
        self.assertFalse(run.read(ROOT / "server.json")["success"])

    def test_first_request_timeout_stops_unclaimed_listener(self):
        started = time.monotonic()
        with self.server(first_request_timeout=.1, idle=2) as server:
            self.assertTrue(server.guard.cancel.wait(1))
        report = run.read(ROOT / "server.json")
        self.assertFalse(report["success"])
        self.assertEqual(report["failure"], "first_request_timeout")
        self.assertEqual(report["requests"], 0)
        self.assertLess(time.monotonic() - started, 1)

    def test_first_request_timeout_closes_tls_handshake_and_empty_authenticated_peer(self):
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                started = time.monotonic()
                with self.server(first_request_timeout=.5, idle=2) as server:
                    connection = (self.connection(server) if authenticated else
                                  socket.create_connection(("127.0.0.1", server.server_port)))
                    try:
                        if authenticated:
                            connection.connect()
                        self.assertTrue(server.guard.cancel.wait(1.5))
                    finally:
                        connection.close()
                self.assertEqual(run.read(ROOT / "server.json")["requests"], 0)
                self.assertLess(time.monotonic() - started, 1.5)

    def test_first_request_deadline_does_not_shorten_valid_bulk(self):
        for declared in (["up"], ["down"], ["up", "down"]):
            with self.subTest(legs=declared), self.server(
                    first_request_timeout=.5, idle=2, rate=32768, legs=declared) as server:
                started = time.monotonic()
                result = stream.client(self.config("client", port=server.server_port,
                                                   rate=32768, idle=2, legs=declared),
                                       lambda _: {"rx": 0, "tx": 0})
                self.assertTrue(result["success"], result)
                self.assertGreater(time.monotonic() - started, .5)
        self.assertLess(180 + stream.MAX_BYTES / stream.RATE, 2400)

    def test_one_shot_rejects_second_get(self):
        with self.server() as server:
            for index in range(2):
                connection = self.connection(server)
                connection.request("GET", "/" + "a" * 32 + "/down")
                try:
                    response = connection.getresponse()
                    response.read()
                    if index == 0:
                        self.assertEqual(response.status, 200)
                    else:
                        self.assertNotEqual(response.status, 200)
                except (OSError, http.client.HTTPException):
                    self.assertEqual(index, 1)
                connection.close()
            self.assertEqual(server.claimed, {"down"})

    def test_bounds_and_nic_no_double_sum(self):
        self.assertEqual(stream.delta({"rx": 10, "tx": 20}, {"rx": 40, "tx": 60}),
                         {"rx": 30, "tx": 40, "wire_once": 70})
        with self.assertRaises(RuntimeError):
            stream.delta({"rx": 10, "tx": 20}, {"rx": 9, "tx": 20})
        for values in ({"bytes": 0}, {"bytes": stream.MAX_BYTES + 1}, {"rate": stream.RATE + 1},
                       {"deadline": 2701}, {"idle": 121}, {"wire_cap": 13 * stream.GIB},
                       {"bytes": 1.5}, {"readiness_attempts": 13},
                       {"first_request_timeout": 0}, {"first_request_timeout": 181}):
            with self.assertRaises(ValueError):
                stream.validate(self.config("client", **values))
        with self.assertRaises(ValueError):
            stream.nic("../../invalid")

    def test_pacing_math_and_cap(self):
        guard = stream.Guard(self.config("client"), lambda _: {"rx": 0, "tx": 0})
        started = time.monotonic()
        guard.pace(125000, started)
        self.assertGreaterEqual(time.monotonic() - started, .045)
        guard.last_check = 0
        with mock.patch.object(guard, "counter", return_value={"rx": 1024 ** 2, "tx": 0}):
            with self.assertRaises(RuntimeError):
                guard.check()

    def test_verify_mismatch(self):
        report = {"success": True, "legs": {}, "nic": {"delta": {"wire_once": 1}}}
        leg = {"id": "i", "producer": "A", "consumer": "T", "bytes": 1,
               "sha256": "f", "status": "ok", "retries": 0}
        report["legs"] = {"up": dict(leg), "down": dict(leg)}
        other = json.loads(json.dumps(report))
        other["legs"]["down"]["sha256"] = "different"
        with self.assertRaises(ValueError):
            stream.verify(report, other)

    def test_one_way_control_exact_upload_no_reverse_bulk(self):
        declared = {"legs": ["up"], "aliases": {"client": "C", "server": "B"}}
        with self.server(**declared) as server:
            result = stream.client(self.config("client", port=server.server_port, **declared),
                                   lambda _: {"rx": 1, "tx": 2})
            self.assertTrue(result["success"], result)
        report = run.read(ROOT / "server.json")
        self.assertEqual(server.claimed, {"up"})
        self.assertEqual(server.attempts, 1)
        self.assertEqual(result["requests"], 1)
        self.assertEqual(report["requests"], 1)
        self.assertEqual(result["role"], "client_C")
        self.assertEqual(report["role"], "server_B")
        self.assertEqual(result["legs"]["up"]["producer"], "C")
        self.assertEqual(report["legs"]["up"]["consumer"], "B")
        self.assertEqual(result["legs"]["up"]["bytes"], 32768)
        self.assertEqual(result["legs"]["up"]["sha256"], stream.digest(32768))
        self.assertEqual(stream.verify(result, report)["wire_once_C"], 0)
        changed = json.loads(json.dumps(report))
        changed["declared_legs"] = ["up", "down"]
        with self.assertRaisesRegex(ValueError, "declared_evidence_mismatch"):
            stream.verify(result, changed)
        changed = json.loads(json.dumps(report))
        changed["legs"]["up"]["producer"] = "A"
        with self.assertRaises(ValueError):
            stream.verify(result, changed)

    def test_download_only_reuses_authenticated_connection(self):
        with self.server(legs=["down"]) as server:
            result = stream.client(self.config("client", port=server.server_port, legs=["down"]),
                                   lambda _: {"rx": 0, "tx": 0})
            self.assertTrue(result["success"], result)
        self.assertEqual(server.attempts, 1)
        self.assertEqual(stream.verify(result, run.read(ROOT / "server.json"))["transport"], "PASS")

    def test_undeclared_reverse_request_rejected_before_production(self):
        with self.server(legs=["up"]) as server:
            connection = self.connection(server)
            connection.request("GET", "/" + "a" * 32 + "/down")
            with contextlib.suppress(OSError, http.client.HTTPException):
                self.assertEqual(connection.getresponse().status, 400)
            connection.close()
        report = run.read(ROOT / "server.json")
        self.assertFalse(report["success"])
        self.assertEqual(report["legs"]["down"]["bytes"], 0)
        self.assertEqual(server.claimed, set())

    def test_declared_legs_and_aliases_fail_closed(self):
        for value in ([], ["up", "up"], ["down", "up"], ["other"], "up", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                stream.validate(self.config("client", legs=value))
        for value in ({"client": "C", "server": "C"}, {"client": "C"},
                      {"client": "../C", "server": "B"}, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                stream.validate(self.config("client", aliases=value))


class WrapperTests(unittest.TestCase):
    def control(self):
        plan = {"id": "c" * 32, "scenario": "cross-region-control", "legs": ["up"],
                "aliases": {"client": "C", "server": "B"},
                "platforms": {"C": "windows_native_cli", "B": "windows_native_cli"},
                "bytes": 5 * stream.GIB, "rate": stream.RATE, "wire_cap": 6 * stream.GIB,
                "core_remaining_bytes": 23 * stream.GIB,
                "cleanup_deadline": "2026-10-18T07:33:00Z"}
        for alias, region, run_id in (("C", "northeurope", "bwb-222222222222"),
                                       ("B", "swedencentral", "bwb-111111111111")):
            cfg = {"subscriptionId": "core", "expectedTenantId": "tenant", "region": region,
                   "runId": run_id, "resourceGroup": "rg-" + run_id}
            for key, kind in (("vm", "Microsoft.Compute/virtualMachines"),
                              ("nic", "Microsoft.Network/networkInterfaces"),
                              ("pip", "Microsoft.Network/publicIPAddresses"),
                              ("nsg", "Microsoft.Network/networkSecurityGroups")):
                cfg[key] = run_id + "-" + key + "-" + alias.lower()
                cfg[key + "_id"] = ("/subscriptions/core/resourceGroups/" + cfg["resourceGroup"]
                                   + "/providers/" + kind + "/" + cfg[key])
            plan[alias] = cfg
        return plan

    def test_control_roles_contexts_operations_and_budgets(self):
        plan = self.control()
        with mock.patch.object(run, "read", return_value=plan["B"]):
            run.control_gates(plan)
        self.assertEqual(run.endpoint_names(plan), ("C", "B"))
        self.assertEqual(run.operations(plan), ("start-c", "start-b", "allow", "server", "client",
                                                "restore-nsg", "deallocate-b", "deallocate-c"))
        self.assertEqual(run.operations(plan, True), ("start-c", "start-b", "ready-c", "ready-b",
                                                      "deallocate-b", "deallocate-c"))
        self.assertFalse(run.azure(plan, "C").wsl)
        self.assertFalse(run.azure(plan, "B").wsl)
        self.assertFalse(run.azure({"A": {}}, "A").wsl)
        self.assertTrue(run.azure({"T": {}}, "T").wsl)
        self.assertEqual(run.operations({}), run.OPERATIONS)
        self.assertEqual(23 * stream.GIB - plan["wire_cap"], 17 * stream.GIB)

    def test_control_all_gates_reject_tampering(self):
        cases = [
            ("legs", ["up", "down"]), ("bytes", 1), ("rate", stream.RATE + 1),
            ("wire_cap", 12 * stream.GIB), ("core_remaining_bytes", 35 * stream.GIB),
            ("core_remaining_bytes", 5 * stream.GIB),
            ("cleanup_deadline", "2026-10-19T07:33:00Z"),
            ("cleanup_deadline", "2026-10-14T07:33:00Z"),
            ("aliases", {"client": "A", "server": "T"}),
            ("platforms", {"C": "windows_native_cli", "B": "wsl_Ubuntu-24.04_native_cli"})]
        for key, value in cases:
            plan = self.control()
            plan[key] = value
            with self.subTest(key=key, value=value), \
                    mock.patch.object(run, "read", return_value=self.control()["B"]), \
                    self.assertRaises(RuntimeError):
                run.control_gates(plan)
        for alias, key, value in (
                ("C", "region", "swedencentral"), ("B", "region", "northeurope"),
                ("C", "subscriptionId", "MSDN"), ("C", "expectedTenantId", "other"),
                ("C", "resourceGroup", self.control()["B"]["resourceGroup"]),
                ("C", "vm_id", "foreign"), ("B", "pip_id", ""),
                ("B", "runId", "other"), ("C", "vm", "fake-a")):
            plan = self.control()
            plan[alias][key] = value
            with self.subTest(alias=alias, key=key), \
                    mock.patch.object(run, "read", return_value=self.control()["B"]), \
                    self.assertRaises(RuntimeError):
                run.control_gates(plan)

    def test_control_live_failure_restores_b_not_t(self):
        plan = self.control()
        plan.update(status="prepared_not_live", snapshot_at=run.now().isoformat())
        lease = self.lease()
        lease["allowedMutations"] = list(run.operations(plan))
        calls = []

        def step(args):
            calls.append(args.action)
            if args.action == "start-b":
                raise RuntimeError("deliberate_start_failure")

        with mock.patch.object(run, "control_gates"), \
                mock.patch.object(run, "guard", return_value=lease), \
                mock.patch.object(run, "save"), mock.patch.object(run, "metrics"), \
                mock.patch.object(run, "require_readiness"), \
                mock.patch.object(run, "execute", side_effect=step), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "read", return_value={"activeCommands": 0}), \
                mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaises(RuntimeError):
                run.live(mock.Mock(run="control", accept_live_gates=True), ROOT, plan)
        self.assertEqual(set(calls[:3]), {"start-c", "start-b", "allow"})
        self.assertEqual(calls[3:], ["deallocate-b", "deallocate-c", "restore-nsg"])

    def test_control_preparation_is_offline_and_real_alias_native_commands(self):
        self.control_preparation()

    def test_one_gib_control_preparation_exact_source_bound_plan_and_reservation(self):
        self.control_preparation(stream.GIB)

    def control_preparation(self, payload=None):
        plan = self.control()
        c, b = plan["C"], plan["B"]
        receiver = {"id": b["pip_id"], "location": "swedencentral", "ipAddress": "192.0.2.5",
                    "tags": {"lab": "true", "created_by": "copilot-lab", "run_id": b["runId"]}}
        ci = {"runId": c["runId"], "groupId": c["vm_id"].split("/providers/")[0],
              "cleanupDeadlineUtc": plan["cleanup_deadline"], "receiverPublicIP": receiver}
        files = {run.LAB / "private" / "context.private.json": b,
                 run.LAB / "private" / "control-inventory.private.json": ci,
                 run.LAB / "private" / "inventory.private.json": {"runId": b["runId"]}}
        args = mock.Mock(run="offline-control", control=True, control_payload_bytes=payload,
                         core_remaining_bytes=(5 if payload else 23) * stream.GIB)
        targets = iter((dict(c), dict(b)))
        written = {}
        with mock.patch.object(run, "read", side_effect=lambda p: files[p]), \
                mock.patch.object(run, "target", side_effect=lambda *a: next(targets)), \
                mock.patch.object(Path, "exists", return_value=False), \
                mock.patch.object(Path, "mkdir"), mock.patch.object(run, "certificates") as certs, \
                mock.patch.object(run, "save", side_effect=lambda p, v: written.update({p.name: v})), \
                mock.patch.object(run.Azure, "cli", side_effect=AssertionError("Azure forbidden")):
            run.prepare(args)
        saved = written["plan.private.json"]
        self.assertNotIn("A", saved)
        self.assertNotIn("T", saved)
        self.assertEqual(saved["legs"], ["up"])
        self.assertEqual(saved["bytes"], payload or 5 * stream.GIB)
        self.assertEqual(saved["wire_cap"], (2 if payload else 6) * stream.GIB)
        self.assertEqual(saved["C"], c)
        self.assertEqual(saved["B"], b)
        self.assertEqual(saved["aliases"], {"client": "C", "server": "B"})
        if payload:
            self.assertEqual(saved["payload_sha256"], stream.digest(payload))
            self.assertEqual(saved["core_remaining_bytes"] - saved["wire_cap"], 3 * stream.GIB)
        certs.assert_called_once_with(run.PRIVATE / args.run / "tls", "192.0.2.5")
        commands = written["commands.private.json"]
        self.assertEqual(set(commands), set(run.operations(plan)))
        self.assertTrue(all(cmd["platform"] == "windows_native_cli" for cmd in commands.values()))
        self.assertIn(c["vm"], commands["client"]["argv_before_native_path_conversion"])
        self.assertIn(b["vm"], commands["server"]["argv_before_native_path_conversion"])
        self.assertEqual(written["live-lease-template.private.json"]["allowedMutations"],
                         list(run.operations(plan)) + ["allow-subnet", "restore-subnet-nsg"])
        self.assertEqual(written["live-lease-template.private.json"]["maxMutations"], 12)
        self.assertEqual(written["live-lease-template.private.json"]["maxToolCalls"], 150)
        self.assertEqual(written["live-lease-template.private.json"]["commandTimeoutSeconds"], 3000)
        self.assertEqual(written["live-lease-template.private.json"]["namedCommandTimeoutSeconds"],
                         {"server": 2500, "client": 2500})
        self.assertEqual(written["readiness-lease-template.private.json"]["allowedMutations"],
                         list(run.operations(plan, True)))
        self.assertEqual(written["snapshot-lease-template.private.json"]["maxMutations"], 0)

    def test_control_deployment_derives_minimal_existing_template(self):
        original = (run.LAB / "deploy" / "msdn-main.json").read_text()
        template = json.loads(original.replace("-t", "-c"))
        template["variables"]["location"] = "northeurope"
        self.assertEqual(len(template["resources"]), 6)
        self.assertNotIn("-t", json.dumps(template))
        vm = next(r for r in template["resources"] if r["type"] == "Microsoft.Compute/virtualMachines")
        self.assertEqual(vm["properties"]["storageProfile"]["imageReference"]["sku"], "22_04-lts-gen2")
        self.assertEqual(vm["properties"]["storageProfile"]["osDisk"]["diskSizeGB"], 30)
        self.assertNotIn("priority", vm["properties"])
        self.assertNotIn("customData", vm["properties"]["osProfile"])
        nsg = next(r for r in template["resources"] if r["type"].endswith("networkSecurityGroups"))
        self.assertEqual(nsg["properties"]["securityRules"][0]["properties"]["access"], "Deny")

    def test_control_snapshot_binds_resources_regions_and_c_only_allow(self):
        plan = self.control()
        plan["server_ip"] = "192.0.2.5"
        files = {run.LAB / "private" / "context.private.json": plan["B"]}
        clients, resources = [], {}
        for alias, ip in (("C", "192.0.2.4"), ("B", "192.0.2.5")):
            cfg = plan[alias]
            common = {"tags": {"lab": "true", "created_by": "copilot-lab", "run_id": cfg["runId"]},
                      "location": cfg["region"]}
            rows = {
                "vm": dict(common, id=cfg["vm_id"], networkProfile={
                    "networkInterfaces": [{"id": cfg["nic_id"]}]}),
                "nsg": dict(common, id=cfg["nsg_id"], securityRules=[{
                    "name": "deny", "priority": 100, "access": "Deny", "protocol": "*",
                    "direction": "Inbound", "sourceAddressPrefix": "*",
                    "destinationAddressPrefix": "*", "sourcePortRange": "*",
                    "destinationPortRange": "*"}]),
                "pip": dict(common, id=cfg["pip_id"], ipAddress=ip),
                "nic": dict(common, id=cfg["nic_id"], networkSecurityGroup={"id": cfg["nsg_id"]},
                            ipConfigurations=[{"publicIPAddress": {"id": cfg["pip_id"]}}])}
            disk_name = cfg["runId"] + "-approved-os"
            disk_id = ("/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/"
                       + cfg["resourceGroup"] + "/providers/Microsoft.Compute/disks/" + disk_name)
            rows["vm"]["storageProfile"] = {
                "osDisk": {"managedDisk": {"id": disk_id}}, "dataDisks": []}
            inventory_name = "control-inventory.private.json" if alias == "C" else "inventory.private.json"
            files[run.LAB / "private" / inventory_name] = {
                "runId": cfg["runId"], "resources": [
                    dict(common, id=disk_id, name=disk_name, type="Microsoft.Compute/disks")]}
            resources[alias] = rows

            def query(argv, rows=rows):
                if argv[:2] == ["vm", "get-instance-view"]:
                    return {"statuses": [{"code": "PowerState/deallocated"}]}
                key = "vm" if argv[0] == "vm" else argv[1]
                return rows["pip" if key == "public-ip" else key]

            client = mock.Mock(config=cfg)
            client.cli.side_effect = query
            clients.append(client)
        with mock.patch.object(run, "read", side_effect=lambda p: files[p]), \
                mock.patch.object(run, "save", side_effect=lambda p, v: files.update({p: v})), \
                mock.patch.object(run, "snapshot_subnet", return_value={
                    "networkSecurityGroup": "", "nic_nsg": "nic-nsg"}), \
                mock.patch.object(run, "metrics"), mock.patch.object(run, "guest_script"):
            run.snapshot(ROOT, plan, *clients)
            rule = files[ROOT / "nsg-allow.private.json"]["properties"]["securityRules"][-1]
            self.assertEqual(rule["properties"]["sourceAddressPrefix"], "192.0.2.4/32")
            self.assertEqual(rule["properties"]["destinationPortRange"], "443")
            self.assertEqual(files[ROOT / "nsg-restore.private.json"]["location"], "swedencentral")
            resources["C"]["vm"]["location"] = "swedencentral"
            with self.assertRaisesRegex(RuntimeError, "live_ownership_mismatch"):
                run.snapshot(ROOT, plan, *clients)

    def test_control_expired_ttl_does_not_block_authorized_restore(self):
        plan = self.control()
        with mock.patch.object(run, "read", return_value=plan["B"]), \
                mock.patch.object(run, "now", return_value=run.datetime(
                    2026, 10, 18, 8, tzinfo=run.timezone.utc)):
            with self.assertRaisesRegex(RuntimeError, "control_lifetime_exceeded"):
                run.control_gates(plan)
            run.control_gates(plan, restoring=True)

    def test_control_inventory_rejects_wrong_resource_identity_and_tags(self):
        plan = self.control()
        context = plan["C"]
        rows = []
        for key, kind in (("vm", "Microsoft.Compute/virtualMachines"),
                          ("nic", "Microsoft.Network/networkInterfaces"),
                          ("pip", "Microsoft.Network/publicIPAddresses"),
                          ("nsg", "Microsoft.Network/networkSecurityGroups")):
            rows.append({"id": context[key + "_id"], "type": kind, "name": context[key],
                         "location": "northeurope", "tags": {
                             "lab": "true", "created_by": "copilot-lab", "run_id": context["runId"]}})
        inventory = {"runId": context["runId"], "resources": rows}
        self.assertEqual(run.target(context, inventory, "c", "northeurope")["vm_id"],
                         context["vm_id"])
        for key, value in (("id", "foreign"), ("location", "swedencentral"), ("tags", {})):
            original = rows[0][key]
            rows[0][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                run.target(context, inventory, "c", "northeurope")
            rows[0][key] = original

    def test_no_live_lease_extension_or_future_start(self):
        from datetime import timedelta
        for start, duration in ((run.now(), 3601), (run.now() + timedelta(minutes=1), 3600)):
            lease = self.lease()
            lease.update(startedAtUtc=start.isoformat(),
                         expiresAtUtc=(start + timedelta(seconds=duration)).isoformat())
            with mock.patch.object(run, "read", return_value=lease), \
                    self.assertRaisesRegex(RuntimeError, "lease_must_not_exceed"):
                run.guard("server", 2500)

    def lease(self):
        from datetime import timedelta
        now = run.now()
        return {"state": "active", "startedAtUtc": now.isoformat(),
                "expiresAtUtc": (now + timedelta(minutes=60)).isoformat(),
                "commandTimeoutSeconds": 2500, "maxToolCalls": 100, "maxMutations": 10,
                "namedCommandTimeoutSeconds": {"server": 2500, "client": 2500},
                "actualToolCalls": 0, "actualMutations": 0,
                "allowedMutations": list(run.OPERATIONS)}

    def test_explicit_lease_guards_no_closed_other_lease(self):
        lease = self.lease()
        with mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(Path, "exists", return_value=False):
            self.assertEqual(run.guard("server", 2500), lease)
            with self.assertRaises(RuntimeError):
                run.guard("not-approved", 30)
            lease["state"] = "completed"
            with self.assertRaises(RuntimeError):
                run.guard("client", 30)

    def test_child_command_timeout_terminates(self):
        with mock.patch.object(run, "command_error", return_value="private-error"), \
                self.assertRaises(subprocess.TimeoutExpired):
            run.bounded([sys.executable, "-c", "import time; time.sleep(5)"], .05)

    def test_wsl_cli_stays_native_and_subscription_explicit(self):
        lease = self.lease()
        client = run.Azure({"subscriptionId": "subscription-test"}, wsl=True)
        with mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "guard", return_value=lease), \
                mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(run, "save"), \
                mock.patch.object(run, "bounded", return_value="{}") as bounded:
            client.cli(["account", "show"])
        argv = bounded.call_args.args[0]
        self.assertIn("/usr/bin/az", argv)
        self.assertIn("/usr/bin/timeout", argv)
        self.assertEqual(argv[argv.index("--subscription") + 1], "subscription-test")
        self.assertNotIn("set", argv)
        self.assertNotIn("login", argv)
        self.assertTrue(lease["ownedProcessesIdle"])

    def test_failed_command_preserves_exact_argv_and_service_error(self):
        process = mock.Mock(returncode=1)
        error = b"ERROR: (BadRequest) End time must be at least 1 minute later"
        process.communicate.return_value = (b"", error)
        argv = ["native-python", "-m", "azure.cli", "monitor", "metrics", "list"]
        with mock.patch.object(run.subprocess, "Popen", return_value=process), \
                mock.patch.object(run, "command_error", return_value="private-error") as saved:
            with self.assertRaisesRegex(RuntimeError, "command_failed_see_private_error"):
                run.bounded(argv, 60)
        self.assertEqual(saved.call_args.args[:2], (argv, 60))
        self.assertEqual(saved.call_args.args[3:], (1, b"", error, "exit"))

    def test_metrics_minimum_window_and_unchanged_live_window(self):
        from datetime import timedelta
        end = run.now()
        plan = {"snapshot_at": (end - timedelta(seconds=26)).isoformat()}
        for alias in ("A", "T"):
            plan[alias] = {"subscriptionId": alias, "resourceGroup": "owned", "vm": "vm"}
        client = mock.Mock()
        client.cli.return_value = {"value": []}
        for elapsed, restore in ((26, False), (60, False), (120, False), (26, True),
                                 (2400, True)):
            with self.subTest(elapsed=elapsed, restore=restore):
                plan.pop("live_started", None)
                if restore:
                    plan["live_started"] = (end - timedelta(seconds=elapsed)).isoformat()
                else:
                    plan["snapshot_at"] = (end - timedelta(seconds=elapsed)).isoformat()
                client.reset_mock()
                with mock.patch.object(run, "now", return_value=end), \
                        mock.patch.object(run, "Azure", return_value=client), \
                        mock.patch.object(run, "save") as saved:
                    run.metrics(ROOT, plan, restore=restore)
                self.assertEqual(client.cli.call_count, 2)
                for call in client.cli.call_args_list:
                    argv = call.args[0]
                    start = run.datetime.fromisoformat(argv[argv.index("--start-time") + 1])
                    stop = run.datetime.fromisoformat(argv[argv.index("--end-time") + 1])
                    self.assertEqual((stop - start).total_seconds(), max(60, elapsed))
                    self.assertEqual(argv[argv.index("--interval") + 1], "PT1M")
                    self.assertEqual(call.kwargs["seconds"], 60)
                    self.assertEqual(call.kwargs["operation"],
                                     "read-restore:restore-nsg" if restore else None)
                self.assertEqual(saved.call_count, 2)

    def test_metrics_error_is_not_a_successful_baseline(self):
        plan = {"snapshot_at": run.now().isoformat(),
                "A": {"subscriptionId": "A", "resourceGroup": "owned", "vm": "vm"}}
        client = mock.Mock()
        client.cli.side_effect = RuntimeError("command_failed_see_private_error")
        with mock.patch.object(run, "Azure", return_value=client), \
                mock.patch.object(run, "save") as saved:
            with self.assertRaisesRegex(RuntimeError, "command_failed_see_private_error"):
                run.metrics(ROOT, plan)
        client.cli.assert_called_once()
        saved.assert_not_called()

    def vm(self):
        return {"id": "/subscriptions/sub/resourceGroups/owned/providers/Microsoft.Compute/"
                       "virtualMachines/vm", "vmId": "unique-vm",
                "storageProfile": {"dataDisks": [], "diskControllerType": "SCSI",
                                   "osDisk": {"caching": "ReadWrite", "managedDisk": {
                                       "id": "/subscriptions/sub/resourceGroups/owned/providers/"
                                             "Microsoft.Compute/disks/os",
                                       "resourceGroup": "owned"}}}}

    def test_vm_binding_accepts_observed_arm_resource_group_case_only(self):
        original = self.vm()
        changed = self.vm()
        disk = changed["storageProfile"]["osDisk"]["managedDisk"]
        disk["id"] = disk["id"].replace("/owned/", "/OWNED/")
        disk["resourceGroup"] = "OWNED"
        self.assertEqual(run.vm_readiness_binding(original), run.vm_readiness_binding(changed))
        self.assertEqual(disk["resourceGroup"], "OWNED", "must not rewrite raw evidence")

    def test_vm_binding_rejects_replacement_and_other_storage_changes(self):
        for field in ("id", "vmId", "disk", "caching"):
            with self.subTest(field=field):
                original = self.vm()
                changed = self.vm()
                if field in ("id", "vmId"):
                    changed[field] += "-replacement"
                elif field == "disk":
                    changed["storageProfile"]["osDisk"]["managedDisk"]["id"] += "-replacement"
                else:
                    changed["storageProfile"]["osDisk"]["caching"] = "None"
                self.assertNotEqual(run.vm_readiness_binding(original),
                                    run.vm_readiness_binding(changed))

    def test_vm_binding_requires_nonempty_vm_and_disk_identifiers(self):
        for field in ("id", "vmId", "disk"):
            for value in ("", None):
                with self.subTest(field=field, value=value):
                    vm = self.vm()
                    if field == "disk":
                        vm["storageProfile"]["osDisk"]["managedDisk"]["id"] = value
                    else:
                        vm[field] = value
                    with self.assertRaisesRegex(RuntimeError, "vm_disk_identity_required"):
                        run.vm_readiness_binding(vm)
        vm = self.vm()
        del vm["storageProfile"]["osDisk"]["managedDisk"]["id"]
        with self.assertRaisesRegex(RuntimeError, "vm_disk_identity_required"):
            run.vm_readiness_binding(vm)

    def test_restoration_only_reads_do_not_need_new_work_budget(self):
        lease = self.lease()
        lease["actualMutations"] = 8
        lease["actualToolCalls"] = 85
        with mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaises(RuntimeError):
                run.guard("start-a", 30)
            self.assertEqual(run.guard("read-restore:restore-nsg", 30), lease)
            self.assertEqual(run.guard("deallocate-a", 30), lease)

    def test_extract_compact_runcommand_report_and_truncation(self):
        report = {"success": True, "role": "client_A", "legs": {}}
        result = {"value": [{"message": "Enable succeeded:\n[stdout]\n"
                            + json.dumps(report) + "\n\n[stderr]\n"}]}
        self.assertEqual(run.compact_report(result), report)
        with self.assertRaises(RuntimeError):
            run.compact_report({"value": [{"message": '{"success":trunc'}]})

    def test_live_failure_always_restores_once_no_retry(self):
        plan = {"status": "prepared_not_live", "snapshot_at": run.now().isoformat(),
                "core_remaining_bytes": 35 * stream.GIB}
        calls = []

        def fail_at_start(args):
            calls.append(args.action)
            if args.action == "start-t":
                raise RuntimeError("deliberate_start_failure")

        args = mock.Mock(run="mock-run", accept_live_gates=True)
        with mock.patch.object(run, "guard", return_value=self.lease()), \
                mock.patch.object(run, "save"), mock.patch.object(run, "metrics"), \
                mock.patch.object(run, "require_readiness"), \
                mock.patch.object(run, "execute", side_effect=fail_at_start), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "read", return_value={"activeCommands": 0}), \
                mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaises(RuntimeError):
                run.live(args, ROOT, plan)
        self.assertEqual(set(calls[:3]), {"start-a", "start-t", "allow"})
        self.assertEqual(calls[3:], ["deallocate-t", "deallocate-a", "restore-nsg"])
        self.assertEqual(plan["status"], "blocked")

    def test_read_only_lease_does_not_require_mutation_attestation(self):
        lease = self.lease()
        lease.update(maxMutations=0, allowedMutations=[])
        with mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(Path, "exists", return_value=False):
            self.assertEqual(run.guard(None, 60), lease)
            with self.assertRaises(RuntimeError):
                run.guard("start-a", 30)

    def test_literal_live_margin_200_seconds_not_extended(self):
        from datetime import timedelta
        instant = run.now()
        lease = self.lease()
        lease.update(startedAtUtc=instant.isoformat(),
                     expiresAtUtc=(instant + timedelta(seconds=3600)).isoformat())
        with mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(Path, "exists", return_value=False):
            with mock.patch.object(run, "now", return_value=instant + timedelta(seconds=199)):
                run.guard("server", 2500)
            with mock.patch.object(run, "now", return_value=instant + timedelta(seconds=201)):
                with self.assertRaisesRegex(RuntimeError, "reserve_15_minutes"):
                    run.guard("server", 2500)

    def test_readiness_success_six_operations_and_deallocated(self):
        lease = self.lease()
        lease.update(allowedMutations=list(run.READINESS_OPERATIONS), maxMutations=6)
        calls = []
        reports = {"success": True, "role": "guest_readiness"}
        args = mock.Mock(run="mock-run")
        with mock.patch.object(run, "guard", return_value=lease), \
                mock.patch.object(run, "snapshot"), \
                mock.patch.object(run, "readiness_binding", return_value={"id": "test"}), \
                mock.patch.object(run, "execute", side_effect=lambda a: calls.append(a.action)), \
                mock.patch.object(run, "save") as saved, \
                mock.patch.object(run, "read", side_effect=lambda p: lease if p == run.LEASE
                                  else reports), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(Path, "exists", return_value=False):
            run.readiness(args, ROOT, {}, None, None)
        self.assertEqual(set(calls[:2]), {"start-a", "start-t"})
        self.assertEqual(set(calls[2:4]), {"ready-a", "ready-t"})
        self.assertEqual(calls[4:], ["deallocate-t", "deallocate-a"])
        evidence = [c.args[1] for c in saved.call_args_list
                    if c.args[0] == ROOT / "readiness.private.json"][-1]
        self.assertTrue(evidence["success"])
        self.assertEqual(evidence["deallocated"], {"A": True, "T": True})
        self.assertEqual(lease["state"], "completed")

    def test_readiness_failure_deallocates_both_without_nsg_or_retry(self):
        lease = self.lease()
        lease.update(allowedMutations=list(run.READINESS_OPERATIONS), maxMutations=6)
        calls = []

        def step(args):
            calls.append(args.action)
            if args.action == "ready-t":
                raise RuntimeError("probe_failure")

        with mock.patch.object(run, "guard", return_value=lease), \
                mock.patch.object(run, "snapshot"), \
                mock.patch.object(run, "readiness_binding", return_value={}), \
                mock.patch.object(run, "execute", side_effect=step), \
                mock.patch.object(run, "save"), mock.patch.object(run, "read", return_value=lease), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "readiness_failed"):
                run.readiness(mock.Mock(run="mock-run"), ROOT, {}, None, None)
        self.assertEqual(set(calls), set(run.READINESS_OPERATIONS))
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[-2:], ["deallocate-t", "deallocate-a"])
        self.assertEqual(lease["state"], "blocked")

    def test_attestation_binding_age_and_restore_are_required(self):
        from datetime import timedelta
        evidence = {"success": True, "completed_at": run.now().isoformat(),
                    "binding": {"id": "test"}, "deallocated": {"A": True, "T": True}}
        with mock.patch.object(run, "read", return_value=evidence), \
                mock.patch.object(run, "readiness_binding", return_value={"id": "test"}):
            self.assertEqual(run.require_readiness(ROOT, {}), evidence)
            evidence["binding"] = {"id": "changed"}
            with self.assertRaises(RuntimeError):
                run.require_readiness(ROOT, {})
            evidence["binding"] = {"id": "test"}
            evidence["deallocated"]["T"] = False
            with self.assertRaises(RuntimeError):
                run.require_readiness(ROOT, {})
            evidence["deallocated"]["T"] = True
            evidence["completed_at"] = (run.now() - timedelta(days=1)).isoformat()
            with self.assertRaises(RuntimeError):
                run.require_readiness(ROOT, {})

    def test_guest_probe_is_read_only_and_revalidated_before_materialization(self):
        cfg = {"interface": "eth0", "mac": "00:00:00:00:00:01",
               "local_ip": "10.0.0.4", "peer": "192.0.2.1"}
        probe = run.guest_probe(cfg)
        compile(probe, "guest-probe", "exec")
        self.assertIn("'route','get'", probe)
        self.assertIn("'nic_changed'", probe)
        self.assertIn("'nic_stats'", probe)
        for forbidden in ("write_text", "apt install", "apt-get", "pip install", "ssh "):
            self.assertNotIn(forbidden, probe)
        plan = {"id": "a" * 32, "bytes": 1, "rate": 1, "wire_cap": 100,
                "client_ip": "192.0.2.2", "server_ip": "192.0.2.1"}
        evidence = {"reports": {"client": {"binding": cfg}}}
        with mock.patch.object(run, "readiness_config", return_value=cfg), \
                mock.patch.object(Path, "read_text", return_value="test"), \
                mock.patch.object(Path, "write_text") as written:
            run.guest_script(ROOT, "client", plan, evidence)
        script = written.call_args.args[0]
        self.assertLess(script.index("guest_readiness_changed"), script.index("mkdir /root"))
        self.assertIn("2450s", script)
        with mock.patch.object(Path, "write_text") as written:
            run.guest_script(ROOT, "client", plan)
        self.assertIn("exit 1", written.call_args.args[0])
        self.assertNotIn("stream.py", written.call_args.args[0],
                         "snapshot scripts must be inert until readiness is validated")

    def test_snapshot_requires_no_guest_attestation_and_metrics_finish_before_publish(self):
        files = {}
        plan = {"id": "a" * 32, "server_ip": "192.0.2.1", "snapshot_at": "old"}
        clients = []
        for alias in ("A", "T"):
            cfg = {"subscriptionId": "test-sub", "resourceGroup": "test", "runId": alias,
                   "vm": "vm", "nsg": "nsg",
                   "pip": "pip", "nic": "nic"}
            tags = {"lab": "true", "created_by": "copilot-lab", "run_id": alias}
            common = {"tags": tags, "location": "swedencentral"}
            rows = {
                "vm": dict(common, id="vm", networkProfile={"networkInterfaces": [{"id": "nic"}]}),
                "nsg": dict(common, id="nsg", securityRules=[{
                    "name": "deny", "priority": 100, "access": "Deny",
                    "direction": "Inbound", "protocol": "*", "sourceAddressPrefix": "*",
                    "destinationAddressPrefix": "*", "sourcePortRange": "*",
                    "destinationPortRange": "*"}]),
                "pip": dict(common, id="pip", ipAddress="192.0.2.1"),
                "nic": dict(common, id="nic", networkSecurityGroup={"id": "nsg"},
                            ipConfigurations=[{"publicIPAddress": {"id": "pip"}}])}
            disk_id = ("/subscriptions/test-sub/resourceGroups/test/providers/"
                       "Microsoft.Compute/disks/approved-os")
            rows["vm"]["storageProfile"] = {
                "osDisk": {"managedDisk": {"id": disk_id}}, "dataDisks": []}
            inventory_name = "msdn-inventory.private.json" if alias == "T" else "inventory.private.json"
            files[run.LAB / "private" / inventory_name] = {
                "runId": alias, "resources": [
                    dict(common, id=disk_id, name="approved-os", type="Microsoft.Compute/disks")]}

            def query(argv, rows=rows):
                if argv[:2] == ["vm", "get-instance-view"]:
                    return {"statuses": [{"code": "PowerState/deallocated"}]}
                key = "vm" if argv[0] == "vm" else argv[1]
                return rows["pip" if key == "public-ip" else key]

            client = mock.Mock(config=cfg)
            client.cli.side_effect = query
            clients.append(client)

        def saved(path, value):
            files[path] = json.loads(json.dumps(value))

        def baseline(*args):
            self.assertNotIn("snapshot_at", files[ROOT / "plan.private.json"])

        with mock.patch.object(run, "save", side_effect=saved), \
                mock.patch.object(run, "read", side_effect=lambda p: files[p]), \
                mock.patch.object(run, "snapshot_subnet", return_value={
                    "networkSecurityGroup": "", "nic_nsg": "nic-nsg"}), \
                mock.patch.object(run, "guest_script"), \
                mock.patch.object(run, "metrics", side_effect=baseline) as metrics, \
                mock.patch.object(run, "require_readiness",
                                  side_effect=AssertionError("must not require guest attestation")):
            run.snapshot(ROOT, plan, *clients)
            metrics.assert_called_once()
            self.assertIn("snapshot_at", files[ROOT / "plan.private.json"])
            run.snapshot(ROOT, plan, *clients, readiness=True)
            metrics.assert_called_once()
            self.assertNotIn("snapshot_at", files[ROOT / "plan.private.json"],
                             "readiness must not qualify as the live snapshot")
            metrics.side_effect = RuntimeError("metrics_failed")
            with self.assertRaisesRegex(RuntimeError, "metrics_failed"):
                run.snapshot(ROOT, plan, *clients)
            self.assertNotIn("snapshot_at", files[ROOT / "plan.private.json"],
                             "a partial snapshot must invalidate previous freshness")
        for client in clients:
            for call in client.cli.call_args_list:
                self.assertNotIn("run-command", call.args[0])
                self.assertNotIn("PUT", call.args[0])

    def test_probe_rejects_changed_nic_or_route_without_guest_writes(self):
        cfg = {"interface": "eth0", "mac": "00:00:00:00:00:01",
               "local_ip": "10.0.0.4", "peer": "192.0.2.1"}
        route = [{"dev": "eth0", "prefsrc": "10.0.0.4"}]
        for mismatch in ("none", "mac", "route"):
            with self.subTest(mismatch=mismatch), \
                    mock.patch("os.geteuid", return_value=0, create=True), \
                    mock.patch("shutil.which", return_value=sys.executable), \
                    mock.patch.object(Path, "read_bytes", return_value=b"tool"), \
                    mock.patch.object(Path, "read_text", autospec=True, side_effect=lambda p:
                                      ("wrong" if mismatch == "mac" else cfg["mac"])
                                      if p.name == "address" else "1"), \
                    mock.patch("subprocess.run"), \
                    mock.patch("subprocess.check_output", return_value=json.dumps(
                        [{"dev": "wrong", "prefsrc": "10.0.0.4"}]
                        if mismatch == "route" else route).encode()):
                if mismatch == "none":
                    result = {}
                    exec(run.guest_probe(cfg), result)
                    self.assertTrue(result["result"]["success"])
                else:
                    with self.assertRaises(AssertionError):
                        exec(run.guest_probe(cfg), {})


class OrchestrationGateTests(unittest.TestCase):
    def setUp(self):
        self.instant = run.now()
        self.clock = 0
        self.lease = {
            "state": "active", "startedAtUtc": self.instant.isoformat(),
            "expiresAtUtc": (self.instant + run.timedelta(seconds=3600)).isoformat(),
            "commandTimeoutSeconds": 2500, "maxToolCalls": 150, "maxMutations": 10,
            "namedCommandTimeoutSeconds": {"server": 2500, "client": 2500},
            "actualToolCalls": 0, "actualMutations": 0,
            "allowedMutations": list(run.OPERATIONS), "activeCommands": 0}
        self.rule = {"name": "transfer-peer-443", "priority": 100, "access": "Allow",
                     "direction": "Inbound", "protocol": "Tcp", "sourcePortRange": "*",
                     "destinationPortRange": "443", "sourceAddressPrefix": "192.0.2.4/32",
                     "destinationAddressPrefix": "*", "provisioningState": "Succeeded"}
        self.deny = dict(self.rule, name="deny", priority=200, access="Deny",
                         protocol="*", sourceAddressPrefix="*", destinationPortRange="*")
        self.nsg = {"id": "nsg-id", "location": "swedencentral", "tags": {"lab": "true"},
                    "provisioningState": "Succeeded", "securityRules": [self.deny, self.rule]}
        self.nic = {"id": "nic-id", "networkSecurityGroup": {"id": "nsg-id"}}
        self.binding = {"nsg": "nsg-id", "nic": "nic-id", "location": "swedencentral",
                        "tags": {"lab": "true"},
                        "rules": run.normalized_rules(self.nsg["securityRules"])}
        self.client = mock.Mock(config={"resourceGroup": "owned", "nsg": "nsg", "nic": "nic"})
        self.saved = {}

    @contextlib.contextmanager
    def gates(self):
        def sleep(seconds):
            self.clock += seconds

        def saved(path, value):
            self.saved[path.name] = json.loads(json.dumps(value))

        with mock.patch.object(run, "now", side_effect=lambda: self.instant
                               + run.timedelta(seconds=self.clock)), \
                mock.patch.object(run.time, "monotonic", side_effect=lambda: self.clock), \
                mock.patch.object(run.time, "sleep", side_effect=sleep), \
                mock.patch.object(run, "read", return_value=self.lease), \
                mock.patch.object(Path, "exists", return_value=False), \
                mock.patch.object(run, "nsg_gate_binding", return_value=self.binding), \
                mock.patch.object(run, "save", side_effect=saved):
            yield

    def test_nsg_updating_parent_or_rule_waits_then_exact_readback(self):
        for parent in (False, True):
            pending = json.loads(json.dumps(self.nsg))
            if parent:
                pending["provisioningState"] = "Updating"
            else:
                pending["securityRules"][0]["provisioningState"] = "Updating"
            self.client.reset_mock()
            self.client.cli.side_effect = [pending, self.nsg, self.nic]
            self.clock = 0
            with self.subTest(parent=parent), self.gates():
                run.wait_nsg_allow(ROOT, {}, self.client)
            evidence = self.saved["nsg-gate.private.json"]
            self.assertTrue(evidence["verified"])
            self.assertEqual(evidence["elapsed_seconds"], 30)
            self.assertEqual(len(evidence["polls"]), 2)
            self.assertTrue(all("PUT" not in call.args[0]
                                for call in self.client.cli.call_args_list))

    @contextlib.contextmanager
    def restore_gates(self):
        def read(path):
            if path == run.LEASE:
                return self.lease
            return self.nic if "-nic-before" in path.name else self.nsg

        self.client.config["subscriptionId"] = "owned-subscription"
        self.client.wsl = False
        with self.gates(), mock.patch.object(run, "read", side_effect=read):
            yield

    def assert_single_restore_put(self):
        puts = [call for call in self.client.cli.call_args_list if "PUT" in call.args[0]]
        self.assertEqual(len(puts), 1)
        self.assertTrue(all(call.args[0][0] in ("rest", "network")
                            for call in self.client.cli.call_args_list))
        for call in self.client.cli.call_args_list:
            if call.args[0][0] == "network":
                self.assertEqual(call.kwargs["operation"], "read-restore:restore-nsg")
                self.assertLessEqual(call.kwargs["seconds"], 90)

    def test_restore_parent_or_rule_updating_requires_final_success_and_association(self):
        for parent in (False, True):
            pending = json.loads(json.dumps(self.nsg))
            if parent:
                pending["provisioningState"] = "Updating"
            else:
                pending["securityRules"][0]["provisioningState"] = "Updating"
            self.clock = 0
            self.client.reset_mock()

            def response(argv, *args, **kwargs):
                self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
                return next(results)

            results = iter([{"provisioningState": "Updating"}, pending, self.nsg, self.nic])
            self.client.cli.side_effect = response
            with self.subTest(parent=parent), self.restore_gates():
                run.restore_nsg(ROOT, {}, self.client, self.clock)
            self.assertTrue(self.saved["nsg-restored.private.json"]["verified"])
            self.assertEqual(self.clock, 30)
            self.assert_single_restore_put()

    def test_restore_never_completes_or_read_times_out_blocks_without_put_retry(self):
        pending = dict(self.nsg, provisioningState="Updating")
        for timeout in (False, True):
            self.clock = 0
            self.client.reset_mock()
            self.client.cli.side_effect = lambda argv, *a, **kw: (
                {"provisioningState": "Updating"} if argv[0] == "rest" else pending)
            if timeout:
                self.client.cli.side_effect = [None, subprocess.TimeoutExpired(["read-nsg"], 30)]
            with self.subTest(timeout=timeout), self.restore_gates(), \
                    self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                run.restore_nsg(ROOT, {}, self.client, self.clock)
            self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
            self.assertLessEqual(self.clock, 900)
            self.assert_single_restore_put()

    def test_execute_restore_uses_completion_poll_not_put_or_updating_readback(self):
        plan = {"A": self.client.config, "T": self.client.config}
        pending = dict(self.nsg, provisioningState="Updating")
        self.client.cli.side_effect = [pending, pending, self.nsg, self.nic]

        def read(path):
            if path == run.LEASE:
                return self.lease
            if path.name == "plan.private.json":
                return plan
            return self.nic if "-nic-before" in path.name else self.nsg

        with self.restore_gates(), mock.patch.object(run, "read", side_effect=read), \
                mock.patch.object(run, "azure", return_value=self.client), \
                mock.patch.object(Path, "is_file", return_value=True):
            run.execute(mock.Mock(action="restore-nsg", run="offline"))
        self.assertTrue(self.saved["nsg-restored.private.json"]["verified"])
        self.assertEqual(self.clock, 30)
        self.client.authorize.assert_called_once_with("restore-nsg", seconds=90)
        self.assert_single_restore_put()

    def test_restore_terminal_unknown_identity_semantics_metadata_and_nic_mismatch_block(self):
        variants = [dict(self.nsg, provisioningState=state)
                    for state in ("Failed", "Canceled", "Cancelled", "Unknown", None)]
        variants += [dict(self.nsg, id="foreign"), dict(self.nsg, tags={}),
                     dict(self.nsg, location="foreign"), dict(self.nsg, securityRules=[])]
        for state in ("Failed", "Canceled", "Unknown", None):
            after = json.loads(json.dumps(self.nsg))
            after["securityRules"][0]["provisioningState"] = state
            variants.append(after)
        for parent in ("Failed", "Updating"):
            after = json.loads(json.dumps(self.nsg))
            after["securityRules"][0]["provisioningState"] = parent
            after["securityRules"][0]["priority"] = 999
            variants.append(after)
        cases = [(after, self.nic) for after in variants] + [
            (self.nsg, dict(self.nic, id="foreign")),
            (self.nsg, dict(self.nic, networkSecurityGroup={"id": "foreign"}))]
        for after, nic in cases:
            self.client.reset_mock()
            self.client.cli.side_effect = [None, after, nic]
            with self.subTest(after=after, nic=nic), self.restore_gates(), \
                    self.assertRaises(RuntimeError):
                run.restore_nsg(ROOT, {}, self.client, self.clock)
            self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
            self.assert_single_restore_put()

    def test_restore_shared_reserve_expiry_stop_and_post_authorization_budget_block(self):
        for mode in ("shared", "expiry", "stop", "authorization", "read-late"):
            self.clock = 0
            self.client.reset_mock()
            self.client.authorize.side_effect = None
            self.client.cli.side_effect = None
            plan = {}
            if mode == "shared":
                plan["restore_started"] = (self.instant - run.timedelta(seconds=721)).isoformat()
            if mode == "expiry":
                self.clock = 3420
            if mode == "authorization":
                self.client.authorize.side_effect = lambda op, **kw: setattr(self, "clock", 721)
            if mode == "read-late":
                def late(argv, *a, **kw):
                    if argv[0] == "network":
                        self.clock = 901
                    return self.nsg
                self.client.cli.side_effect = late
            with self.subTest(mode=mode), self.restore_gates():
                stop = mock.patch.object(Path, "exists", return_value=True) \
                    if mode == "stop" else contextlib.nullcontext()
                with stop, self.assertRaises(RuntimeError):
                    run.restore_nsg(ROOT, plan, self.client, self.clock)
            self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
            if mode != "read-late":
                self.client.cli.assert_not_called()
            else:
                self.assert_single_restore_put()

    def test_nsg_failed_canceled_unknown_and_missing_state_fail_closed(self):
        for state in ("Failed", "Canceled", "Unknown", None):
            after = dict(self.nsg, provisioningState=state)
            self.client.cli.side_effect = [after]
            with self.subTest(state=state), self.gates(), self.assertRaises(RuntimeError):
                run.wait_nsg_allow(ROOT, {}, self.client)
            self.assertFalse(self.saved["nsg-gate.private.json"]["verified"])

    def test_nsg_exact_rule_and_receiver_binding_mismatches_fail_closed(self):
        for field, value in (("sourceAddressPrefix", "192.0.2.99/32"),
                             ("priority", 200), ("destinationPortRange", "80"),
                             ("protocol", "*"), ("access", "Deny"), ("direction", "Outbound")):
            after = json.loads(json.dumps(self.nsg))
            after["securityRules"][1][field] = value
            self.client.cli.side_effect = [after]
            with self.subTest(field=field), self.gates(), \
                    self.assertRaisesRegex(RuntimeError, "readback_mismatch"):
                run.wait_nsg_allow(ROOT, {}, self.client)
        for after, nic in ((dict(self.nsg, id="foreign"), self.nic),
                           (self.nsg, dict(self.nic, id="foreign")),
                           (self.nsg, dict(self.nic, networkSecurityGroup={"id": "foreign"}))):
            self.client.cli.side_effect = [after, nic]
            with self.gates(), self.assertRaisesRegex(RuntimeError, "mismatch"):
                run.wait_nsg_allow(ROOT, {}, self.client)

    def test_nsg_poll_and_read_timeouts_never_resubmit(self):
        pending = dict(self.nsg, provisioningState="Updating")
        for error in (None, subprocess.TimeoutExpired(["read-nsg"], 30)):
            self.clock = 0
            self.client.reset_mock()
            self.client.cli.side_effect = error or (lambda *a, **kw: pending)
            with self.subTest(read_timeout=error is not None), self.gates(), \
                    self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                run.wait_nsg_allow(ROOT, {}, self.client)
            evidence = self.saved["nsg-gate.private.json"]
            self.assertFalse(evidence["verified"])
            self.assertLessEqual(self.clock, 180)
            self.assertTrue(all("PUT" not in call.args[0]
                                for call in self.client.cli.call_args_list))

    def test_nsg_poll_respects_remaining_setup_and_3400_second_reserve(self):
        self.clock = 185
        self.client.cli.return_value = dict(self.nsg, provisioningState="Updating")
        with self.gates(), self.assertRaisesRegex(RuntimeError, "nsg_gate_setup_timeout"):
            run.wait_nsg_allow(ROOT, {}, self.client)
        self.assertEqual(self.client.cli.call_args.kwargs["seconds"], 15)
        self.assertEqual(self.clock, 185, "no 30s sleep may spend the submission reserve")

    def test_nsg_slow_exact_reads_succeed_with_90_second_ceiling(self):
        results = iter([self.nsg, self.nic])

        def response(argv, **kwargs):
            self.assertEqual(kwargs["seconds"], 90)
            self.clock += 40
            return next(results)

        self.client.cli.side_effect = response
        with self.gates():
            run.wait_nsg_allow(ROOT, {}, self.client)
        self.assertTrue(self.saved["nsg-gate.private.json"]["verified"])
        self.assertEqual(self.clock, 80)

    def test_nsg_reads_clip_to_phase_and_reserve_and_reject_late_success(self):
        for initial, first, expected in ((0, 120, 60), (100, 70, 30)):
            self.clock = initial
            self.client.reset_mock()

            def response(argv, **kwargs):
                if argv[1] == "nsg":
                    self.clock += first
                    return self.nsg
                self.assertEqual(kwargs["seconds"], expected)
                self.clock += expected
                return self.nic

            self.client.cli.side_effect = response
            with self.subTest(initial=initial), self.gates(), self.assertRaises(RuntimeError):
                run.wait_nsg_allow(ROOT, {}, self.client)
            self.assertFalse(self.saved["nsg-gate.private.json"]["verified"])

    def test_nsg_expired_submission_margin_never_queries(self):
        self.clock = 201
        with self.gates(), self.assertRaisesRegex(RuntimeError, "reserve_15_minutes"):
            run.wait_nsg_allow(ROOT, {}, self.client)
        self.client.cli.assert_not_called()
        self.assertFalse(self.saved["nsg-gate.private.json"]["verified"])

    def test_restore_slow_exact_reads_succeed_with_90_second_ceiling(self):
        def response(argv, *args, **kwargs):
            if argv[0] == "rest":
                self.assertEqual(args[1], 180)
                return None
            self.assertEqual(kwargs["seconds"], 90)
            self.clock += 40
            return self.nsg if argv[1] == "nsg" else self.nic

        self.client.cli.side_effect = response
        with self.restore_gates():
            run.restore_nsg(ROOT, {}, self.client, self.clock)
        self.assertTrue(self.saved["nsg-restored.private.json"]["verified"])
        self.assertEqual(self.clock, 80)
        self.assert_single_restore_put()

    def test_restore_reads_clip_shared_deadline_and_lease_without_verifying_updating(self):
        for mode in ("shared", "lease"):
            self.clock = 0 if mode == "shared" else 3300
            self.client.reset_mock()
            plan = {"restore_started": (self.instant - run.timedelta(seconds=600)).isoformat()} \
                if mode == "shared" else {}
            expected = 60 if mode == "shared" else 49

            def response(argv, *args, **kwargs):
                if argv[0] == "rest":
                    self.clock += 240
                    return None
                self.assertEqual(kwargs["seconds"], expected)
                self.clock += expected
                return dict(self.nsg, provisioningState="Updating")

            self.client.cli.side_effect = response
            with self.subTest(mode=mode), self.restore_gates(), self.assertRaises(RuntimeError):
                run.restore_nsg(ROOT, plan, self.client, self.clock)
            self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
            self.assert_single_restore_put()

    def test_restore_nic_read_clips_shared_deadline_and_rejects_late_exact_success(self):
        plan = {"restore_started": (self.instant - run.timedelta(seconds=660)).isoformat()}

        def response(argv, *args, **kwargs):
            if argv[0] == "rest":
                self.clock += 180
                return None
            if argv[1] == "nsg":
                self.assertEqual(kwargs["seconds"], 60)
                self.clock += 40
                return self.nsg
            self.assertEqual(kwargs["seconds"], 20)
            self.clock += 20
            return self.nic

        self.client.cli.side_effect = response
        with self.restore_gates(), self.assertRaisesRegex(RuntimeError, "nsg_restore_timeout"):
            run.restore_nsg(ROOT, plan, self.client, self.clock)
        self.assertFalse(self.saved["nsg-restored.private.json"]["verified"])
        self.assert_single_restore_put()

    def test_ordinary_reads_clip_90_second_ceiling_and_expiry_before_dispatch(self):
        client = run.Azure({"subscriptionId": "owned"}, wsl=True)
        for operation, clock, expected in ((None, 0, 90), (None, 2650, 39),
                                           ("read-restore:restore-nsg", 3540, 49),
                                           (None, 3601, None)):
            self.clock = clock
            with self.subTest(operation=operation, clock=clock), self.gates(), \
                    mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                    mock.patch.object(run, "bounded", return_value="{}") as bounded:
                if expected is None:
                    with self.assertRaises(RuntimeError):
                        client.cli(["network", "nic", "show"], operation=operation)
                    bounded.assert_not_called()
                else:
                    client.cli(["network", "nic", "show"], operation=operation, seconds=180)
                    self.assertEqual(bounded.call_args.args[1], expected)
        self.assertEqual(self.lease["actualMutations"], 0)

    def test_deallocation_reads_and_authorization_clip_original_restore_clock(self):
        plan = {"A": self.client.config, "T": self.client.config,
                "restore_started": (self.instant - run.timedelta(seconds=850)).isoformat()}
        self.client.config["vm"] = "vm"

        def response(argv, *args, **kwargs):
            if argv[1] == "deallocate":
                self.assertEqual(args[1], 180)
                self.clock += 20
                return None
            self.assertEqual(kwargs["seconds"], 30)
            return {"statuses": [{"code": "PowerState/deallocated"}]}

        self.client.cli.side_effect = response
        with self.gates(), mock.patch.object(run, "read", side_effect=lambda path:
                                             self.lease if path == run.LEASE else plan), \
                mock.patch.object(run, "azure", return_value=self.client), \
                mock.patch.object(Path, "is_file", return_value=True):
            run.execute(mock.Mock(action="deallocate-t", run="offline"))
        self.client.authorize.assert_called_once_with("deallocate-t", seconds=50)
        self.assertTrue(self.saved["deallocate-t-verified.private.json"]["verified"])

    def test_expired_restore_clock_prevents_deallocation_authorization(self):
        plan = {"A": self.client.config, "T": self.client.config,
                "restore_started": (self.instant - run.timedelta(seconds=901)).isoformat()}
        with self.gates(), mock.patch.object(run, "read", side_effect=lambda path:
                                             self.lease if path == run.LEASE else plan), \
                mock.patch.object(run, "azure", return_value=self.client), \
                mock.patch.object(Path, "is_file", return_value=True), \
                self.assertRaisesRegex(RuntimeError, "restore_reserve_exhausted"):
            run.execute(mock.Mock(action="deallocate-t", run="offline"))
        self.client.authorize.assert_not_called()
        self.client.cli.assert_not_called()

    def test_guest_authorization_clips_setup_budget_and_cost_blocks_submission(self):
        plan = {"A": {"subscriptionId": "owned", "expectedTenantId": "tenant",
                      "resourceGroup": "owned", "vm": "vm"},
                "T": {"subscriptionId": "owned", "expectedTenantId": "tenant",
                      "resourceGroup": "owned", "vm": "vm"}}
        for operation in ("server", "client"):
            self.clock = 160
            client = run.Azure(plan["T"], wsl=True)

            def response(argv, seconds, progress=None):
                self.assertEqual(seconds, 40)
                self.assertIn("account", argv)
                self.clock += 41
                return json.dumps({"id": "owned", "tenantId": "tenant", "state": "Enabled"})

            with self.subTest(operation=operation), self.gates(), \
                    mock.patch.object(run, "read", side_effect=lambda path:
                                      self.lease if path == run.LEASE else plan), \
                    mock.patch.object(run, "azure", return_value=client), \
                    mock.patch.object(run, "require_nsg_allow"), \
                    mock.patch.object(run, "require_readiness"), \
                    mock.patch.object(run, "guest_script"), \
                    mock.patch.object(Path, "is_file", return_value=True), \
                    mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                    mock.patch.object(run, "bounded", side_effect=response) as bounded:
                with self.assertRaisesRegex(RuntimeError, "reserve_15_minutes"):
                    run.execute(mock.Mock(action=operation, run="offline"))
                self.assertEqual(bounded.call_count, 1)

    def test_nsg_normalization_preserves_every_relevant_allow_field(self):
        nested = {"name": self.rule["name"], "properties": {
            k: v for k, v in self.rule.items() if k not in ("name", "provisioningState")}}
        nested["properties"]["protocol"] = "tcp"
        nested["properties"]["sourceAddressPrefixes"] = [
            nested["properties"].pop("sourceAddressPrefix")]
        nested["properties"]["destinationPortRanges"] = [
            nested["properties"].pop("destinationPortRange")]
        self.assertEqual(run.normalized_rules([nested]), run.normalized_rules([self.rule]))
        nested["properties"]["sourceApplicationSecurityGroups"] = [{"id": "unexpected"}]
        self.assertNotEqual(run.normalized_rules([nested]), run.normalized_rules([self.rule]))

    def test_stale_unverified_or_differently_bound_gate_cannot_dispatch(self):
        evidence = {"verified": True, "binding": self.binding,
                    "completed_at": self.instant.isoformat()}
        with self.gates(), mock.patch.object(run, "read", return_value=evidence):
            run.require_nsg_allow(ROOT, {})
            for key, value in (("verified", False), ("binding", {}), ("completed_at",
                                (self.instant - run.timedelta(seconds=201)).isoformat())):
                changed = dict(evidence, **{key: value})
                with mock.patch.object(run, "read", return_value=changed), \
                        self.assertRaisesRegex(RuntimeError, "completed_exact_nsg_gate"):
                    run.require_nsg_allow(ROOT, {})

    def test_runcommand_rechecks_full_reserve_after_authorization(self):
        plan = {"A": {"subscriptionId": "a", "resourceGroup": "owned", "vm": "vm"},
                "T": {"subscriptionId": "t", "resourceGroup": "owned", "vm": "vm"}}
        client = run.Azure(plan["T"], wsl=True)
        with self.gates(), \
                mock.patch.object(run, "read", side_effect=lambda path:
                                  self.lease if path == run.LEASE else plan), \
                mock.patch.object(run, "azure", return_value=client), \
                mock.patch.object(client, "authorize", side_effect=lambda op, **kw:
                                  setattr(self, "clock", 201)), \
                mock.patch.object(run, "require_nsg_allow"), \
                mock.patch.object(run, "require_readiness"), \
                mock.patch.object(run, "guest_script"), \
                mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "bounded") as bounded:
            with self.assertRaisesRegex(RuntimeError, "reserve_15_minutes"):
                run.execute(mock.Mock(action="server", run="offline"))
            bounded.assert_not_called()

    def exercise_live(self, step, fails=True):
        plan = {"status": "prepared_not_live", "snapshot_at": self.instant.isoformat(),
                "core_remaining_bytes": 35 * stream.GIB}
        with mock.patch.object(run, "guard", return_value=self.lease), \
                mock.patch.object(run, "save", side_effect=lambda p, v:
                                  self.saved.update({p.name: json.loads(json.dumps(v))})), \
                mock.patch.object(run, "metrics"), mock.patch.object(run, "require_readiness"), \
                mock.patch.object(run, "execute", side_effect=step), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "read", return_value=self.lease), \
                mock.patch.object(Path, "exists", return_value=False), \
                mock.patch.object(run.sys.stderr, "write"):
            outcome = self.assertRaisesRegex(RuntimeError, "live_failed") \
                if fails else contextlib.nullcontext()
            with outcome:
                run.live(mock.Mock(run="offline", accept_live_gates=True), ROOT, plan)
        return plan

    def test_live_restore_completion_blocks_closure_until_succeeded_after_both_deallocations(self):
        for success in (False, True):
            self.clock = 0
            self.client.reset_mock()
            pending = dict(self.nsg, provisioningState="Updating")
            self.client.cli.side_effect = [None, pending, self.nsg if success else
                                           dict(self.nsg, provisioningState="Failed"), self.nic]
            calls = []

            def step(args):
                calls.append(args.action)
                if args.action == "restore-nsg":
                    self.assertEqual(calls[-3:], ["deallocate-t", "deallocate-a", "restore-nsg"])
                    self.assertNotEqual(self.saved["plan.private.json"]["status"], "completed")
                    with self.restore_gates():
                        run.restore_nsg(ROOT, self.saved["plan.private.json"],
                                        self.client, self.clock)

            with self.gates():
                plan = self.exercise_live(step, fails=not success)
            self.assertEqual(plan["status"], "completed" if success else "blocked")
            self.assertEqual(self.saved["nsg-restored.private.json"]["verified"], success)
            self.assertEqual(calls.count("server"), 1)
            self.assertEqual(calls.count("client"), 1)
            self.assert_single_restore_put()

    def test_nsg_gate_failures_restore_once_and_never_dispatch_guests(self):
        for reason in ("nsg_gate_provisioning_failed", "nsg_gate_readback_mismatch",
                       "nsg_gate_setup_timeout", subprocess.TimeoutExpired(["read-nic"], 90)):
            calls = []

            def step(args):
                calls.append(args.action)
                if args.action == "allow":
                    raise reason if isinstance(reason, BaseException) else RuntimeError(reason)

            plan = self.exercise_live(step)
            self.assertNotIn("server", calls)
            self.assertNotIn("client", calls)
            self.assertEqual(calls.count("allow"), 1)
            self.assertEqual(calls[-3:], ["deallocate-t", "deallocate-a", "restore-nsg"])
            self.assertEqual(plan["status"], "blocked")
            self.assertIn("setup_seconds", plan)

    def test_either_peer_failure_persists_fail_before_bounded_drain_and_cleanup(self):
        for failed in ("server", "client"):
            peer_started = threading.Event()
            peer_done = threading.Event()
            workers = []
            calls = []

            def step(args):
                role = args.action
                calls.append(role)
                if role not in ("server", "client"):
                    if role.startswith(("deallocate-", "restore-")):
                        self.assertTrue(peer_done.is_set(), "cleanup preceded guest drain")
                    return
                workers.append(threading.current_thread())
                if role == failed:
                    self.assertTrue(peer_started.wait(1))
                    raise RuntimeError("decisive_failure")
                peer_started.set()
                deadline = time.monotonic() + 1
                while self.saved.get("verdict.private.json", {}).get("transport") != "FAIL":
                    self.assertLess(time.monotonic(), deadline, "FAIL hidden behind peer wait")
                    time.sleep(.005)
                self.assertEqual(self.saved["plan.private.json"]["status"], "failed_draining_peers")
                peer_done.set()

            self.saved.clear()
            plan = self.exercise_live(step)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertNotIn("verify", calls)
            self.assertEqual(calls[-3:], ["deallocate-t", "deallocate-a", "restore-nsg"])
            self.assertEqual(plan["status"], "blocked")

    def test_unacknowledged_guest_cannot_restore_nsg_until_verified_poweroff(self):
        calls = []

        def step(args):
            calls.append(args.action)
            if args.action in ("client", "deallocate-t"):
                raise RuntimeError("lost_ack")

        plan = self.exercise_live(step)
        self.assertIn("deallocate-a", calls)
        self.assertNotIn("restore-nsg", calls)
        self.assertTrue(any("guest_quiescence_unverified" in item for item in plan["failures"]))
        self.assertEqual(plan["status"], "blocked")


class SubnetPolicyTests(unittest.TestCase):
    def test_policy_clone_preserves_exact_deny_and_matches_tls_port_and_peer(self):
        original = json.loads(json.dumps(self.original))
        restore, allowed = run.policy_bodies(self.directory, self.plan, self.original, write=False)
        self.assertEqual(self.original, original)
        self.assertEqual(restore["properties"]["securityRules"][0]["properties"]["priority"], 100)
        self.assertEqual(allowed["properties"]["securityRules"][0]["properties"]["priority"], 200)
        rule = allowed["properties"]["securityRules"][-1]["properties"]
        self.assertEqual(rule["destinationPortRange"], "443")
        self.assertEqual(rule["sourceAddressPrefix"], self.plan["client_ip"] + "/32")
        self.assertEqual(rule["protocol"], "Tcp")
        self.assertEqual(len(allowed["properties"]["securityRules"]), 2)
        allowed["properties"]["securityRules"][0]["properties"]["access"] = "Allow"
        self.assertEqual(restore["properties"]["securityRules"][0]["properties"]["access"], "Deny")
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(run.guest_script))
        cfg = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "cfg"
                           for target in node.targets))
        port = next(value.value for key, value in zip(cfg.keys, cfg.values)
                    if isinstance(key, ast.Constant) and key.value == "port")
        self.assertEqual(str(port), rule["destinationPortRange"])
        self.assertIn("CERT_REQUIRED", (run.HERE / "stream.py").read_text())

    def setUp(self):
        self.directory = run.PRIVATE / "mock-subnet-v4"
        self.plan = WrapperTests().control()
        self.sources = run.source_identity()
        self.plan.update(client_ip="192.0.2.4", server_ip="192.0.2.5",
                         snapshot_at=run.now().isoformat(), snapshot_sources=self.sources)
        self.cfg = self.plan["B"]
        self.tags = {"lab": "true", "created_by": "copilot-lab", "run_id": self.cfg["runId"]}
        root = self.cfg["nsg_id"].rsplit("/networkSecurityGroups/", 1)[0]
        self.vnet = root + "/virtualNetworks/owned"
        self.subnet = {"id": self.vnet + "/subnets/lab", "provisioningState": "Succeeded",
                       "networkSecurityGroup": {"id": root + "/networkSecurityGroups/subnet"}}
        self.nic = {"id": self.cfg["nic_id"], "networkSecurityGroup": {"id": self.cfg["nsg_id"]},
                    "ipConfigurations": [{"subnet": {"id": self.subnet["id"]}}]}
        defaults = []
        for name, priority, direction, access, source, destination in (
                ("AllowVnetInBound", 65000, "Inbound", "Allow", "VirtualNetwork", "VirtualNetwork"),
                ("AllowAzureLoadBalancerInBound", 65001, "Inbound", "Allow", "AzureLoadBalancer", "*"),
                ("DenyAllInBound", 65500, "Inbound", "Deny", "*", "*"),
                ("AllowVnetOutBound", 65000, "Outbound", "Allow", "VirtualNetwork", "VirtualNetwork"),
                ("AllowInternetOutBound", 65001, "Outbound", "Allow", "*", "Internet"),
                ("DenyAllOutBound", 65500, "Outbound", "Deny", "*", "*")):
            defaults.append({"name": name, "priority": priority, "direction": direction,
                             "access": access, "sourceAddressPrefix": source,
                             "destinationAddressPrefix": destination, "sourcePortRange": "*",
                             "destinationPortRange": "*", "protocol": "*",
                             "provisioningState": "Succeeded"})
        common = {"location": "swedencentral", "tags": self.tags, "provisioningState": "Succeeded"}
        self.parent = dict(common, id=self.vnet)
        self.extra = dict(common, id=self.subnet["networkSecurityGroup"]["id"], securityRules=[],
                          defaultSecurityRules=defaults)
        self.original = dict(common, id=self.cfg["nsg_id"], defaultSecurityRules=defaults,
                             securityRules=[{
                                 "name": "deny", "priority": 100, "access": "Deny",
                                 "direction": "Inbound", "protocol": "*", "sourcePortRange": "*",
                                 "destinationPortRange": "*", "sourceAddressPrefix": "*",
                                 "destinationAddressPrefix": "*", "provisioningState": "Succeeded"}])
        self.inventory = {"runId": self.cfg["runId"], "resources": [
            dict(value, type="Microsoft.Network/" + kind)
            for value, kind in ((self.parent, "virtualNetworks"), (self.extra, "networkSecurityGroups"))]}
        self.files = {
            run.LAB / "private" / "inventory.private.json": self.inventory,
            self.directory / "B-nic-before.private.json": self.nic,
            self.directory / "B-nsg-before.private.json": self.original,
            self.directory / "plan.private.json": self.plan}
        self.current = {self.original["id"]: self.original, self.extra["id"]: self.extra}
        self.client = mock.Mock(config=self.cfg, wsl=False)
        self.client.cli.side_effect = self.query
        self.puts = []
        self.markers = set()

    def query(self, argv, *args, **kwargs):
        if argv[0] == "rest":
            identity = argv[argv.index("--url") + 1].split("?")[0].removeprefix(
                "https://management.azure.com")
            identity = next(key for key in self.current if key.lower() == identity.lower())
            body = self.files[Path(argv[argv.index("--body") + 1][1:])]
            self.puts.append((identity, args[0], json.loads(json.dumps(body))))
            current = dict(self.current[identity], **body)
            current.pop("properties", None)
            current["securityRules"] = [
                dict(rule["properties"], name=rule["name"], provisioningState="Succeeded")
                for rule in body["properties"]["securityRules"]]
            self.current[identity] = current
            return {"provisioningState": "Updating"}
        if argv[:2] == ["vm", "get-instance-view"]:
            return {"statuses": [{"code": "PowerState/deallocated"}]}
        if argv[:2] == ["vm", "deallocate"]:
            return {}
        if argv[1] == "nic":
            return self.nic
        if argv[1:3] == ["vnet", "subnet"]:
            return self.subnet
        if argv[1] == "vnet":
            return self.parent
        identity = argv[argv.index("--ids") + 1] if "--ids" in argv else self.cfg["nsg_id"]
        return next(value for key, value in self.current.items() if key.lower() == identity.lower())

    @contextlib.contextmanager
    def mocks(self):
        lease = WrapperTests().lease()
        lease.update(maxMutations=12, allowedMutations=list(run.operations(self.plan)),
                     activeCommands=0)
        def read(path):
            return lease if path == run.LEASE else self.files[path]
        def opened(path, mode):
            import io
            self.assertEqual(mode, "x")
            if path in self.markers:
                raise FileExistsError()
            self.markers.add(path)
            return io.StringIO()
        with mock.patch.object(run, "read", side_effect=read), \
                mock.patch.object(run, "save", side_effect=lambda p, v: self.files.update({p: v})), \
                mock.patch.object(run, "guard", return_value=lease), \
                mock.patch.object(run, "control_gates"), \
                mock.patch.object(run, "source_identity", return_value=self.sources), \
                mock.patch.object(run, "azure", return_value=self.client), \
                mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(Path, "exists", autospec=True,
                                  side_effect=lambda path: path in self.markers), \
                mock.patch.object(Path, "open", autospec=True, side_effect=opened):
            yield

    def discover(self):
        binding = run.snapshot_subnet(self.directory, self.plan, "B", self.client)
        self.plan["network_bindings"] = {"B": binding}
        self.plan["receiver_subnet_nsg"] = (
            binding["networkSecurityGroup"]
            if binding["networkSecurityGroup"] != binding["nic_nsg"] else "")
        run.policy_bodies(self.directory, self.plan, self.original)
        if self.plan["receiver_subnet_nsg"]:
            run.policy_bodies(self.directory, self.plan, self.extra, True)
        return binding

    def step(self, operation):
        run.execute(mock.Mock(action=operation, run=self.directory.name))

    def test_owned_subnet_discovery_binds_both_policies_and_parent(self):
        with self.mocks():
            binding = self.discover()
        self.assertEqual(binding["subnet"], self.subnet["id"].lower())
        self.assertEqual(binding["subnet_nsg_baseline"]["rules"], [])
        self.assertEqual(binding["nic_nsg_baseline"]["rules"],
                         run.normalized_rules(self.original["securityRules"]))
        self.assertEqual(self.files[self.directory / "B-vnet-before.private.json"], self.parent)
        self.assertEqual(len(run.operations(self.plan)), 10)
        self.assertEqual(len(run.operations(self.plan, True)), 6)
        self.assertFalse(self.puts)

    def test_default_at_and_control_client_subnets_use_their_own_inventory(self):
        for alias, inventory in (("A", "inventory.private.json"),
                                 ("T", "msdn-inventory.private.json"),
                                 ("C", "control-inventory.private.json")):
            self.setUp()
            self.files[run.LAB / "private" / inventory] = self.inventory
            for key, value in (("nic", self.nic), ("nsg", self.original)):
                self.files[self.directory / (alias + "-" + key + "-before.private.json")] = value
            with self.subTest(alias=alias), self.mocks():
                binding = run.snapshot_subnet(self.directory, self.plan, alias, self.client)
                self.assertEqual(binding["subnet"], self.subnet["id"].lower())
                self.assertIn(self.directory / (alias + "-subnet-nsg-before.private.json"), self.files)
            self.assertFalse(self.puts)

    def test_foreign_unowned_missing_inventory_wrong_run_or_parent_fail_without_mutation(self):
        for mode in ("untagged", "foreign-run", "unlisted", "inventory-run", "parent", "foreign-id"):
            self.setUp()
            if mode == "untagged":
                self.extra["tags"] = {}
            elif mode == "foreign-run":
                self.extra["tags"] = dict(self.tags, run_id="foreign")
            elif mode == "unlisted":
                self.inventory["resources"].pop()
            elif mode == "inventory-run":
                self.inventory["runId"] = "foreign"
            elif mode == "parent":
                self.parent["tags"] = {}
            else:
                self.extra["id"] = "/subscriptions/foreign/networkSecurityGroups/subnet"
            with self.subTest(mode=mode), self.mocks(), self.assertRaises(RuntimeError):
                self.discover()
            self.assertFalse(self.puts)

    def test_no_subnet_nsg_and_shared_nsg_deduplicate_writes(self):
        for shared in (False, True):
            self.setUp()
            self.subnet["networkSecurityGroup"] = {"id": self.cfg["nsg_id"]} if shared else None
            if shared:
                self.inventory["resources"].append(self.original)
            with self.subTest(shared=shared), self.mocks():
                self.discover()
                self.assertFalse(self.plan["receiver_subnet_nsg"])
                self.step("allow")
                self.step("deallocate-b")
                self.step("deallocate-c")
                self.step("restore-nsg")
            self.assertEqual([op for _, op, _ in self.puts], ["allow", "restore-nsg"])
            self.assertEqual(len(run.operations(self.plan)), 8)

    def test_unknown_subnet_custom_default_policy_and_bad_association_fail_closed(self):
        for mode in ("custom", "defaults", "state", "association", "missing-subnet", "nat", "udr"):
            self.setUp()
            if mode == "custom":
                self.extra["securityRules"] = self.original["securityRules"]
            elif mode == "defaults":
                self.extra["defaultSecurityRules"] = []
            elif mode == "state":
                self.extra["provisioningState"] = "Updating"
            elif mode == "association":
                self.subnet["id"] += "-foreign"
            elif mode == "missing-subnet":
                self.nic["ipConfigurations"][0].pop("subnet")
            else:
                self.subnet["natGateway" if mode == "nat" else "routeTable"] = {"id": "unknown"}
            with self.subTest(mode=mode), self.mocks(), self.assertRaises(RuntimeError):
                self.discover()
            self.assertFalse(self.puts)

    def test_two_layers_exact_allow_success_readback_and_once_each_restore(self):
        with self.mocks():
            self.discover()
            self.step("allow-subnet")
            with self.assertRaises((KeyError, RuntimeError)):
                run.require_nsg_allow(self.directory, self.plan)
            self.step("allow")
            run.require_nsg_allow(self.directory, self.plan)
            for prefix in ("nsg", "subnet-nsg"):
                self.assertTrue(self.files[self.directory / (prefix + "-gate.private.json")]["verified"])
            self.assertEqual(self.current[self.original["id"]]["securityRules"][0]["priority"], 200)
            with self.assertRaises(KeyError):
                self.step("restore-subnet-nsg")
            self.step("deallocate-b")
            self.step("deallocate-c")
            self.step("restore-nsg")
            self.step("restore-subnet-nsg")
            for prefix in ("nsg", "subnet-nsg"):
                self.assertTrue(self.files[self.directory / (prefix + "-restored.private.json")]["verified"])
            with self.assertRaisesRegex(RuntimeError, "already_attempted"):
                self.step("restore-subnet-nsg")
            self.assertTrue(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
        self.assertEqual([op for _, op, _ in self.puts],
                         ["allow-subnet", "allow", "restore-nsg", "restore-subnet-nsg"])
        for _, op, body in self.puts[:2]:
            rule = body["properties"]["securityRules"][-1]["properties"]
            self.assertEqual(rule, {"priority": 100, "access": "Allow", "direction": "Inbound",
                                   "protocol": "Tcp", "sourcePortRange": "*",
                                   "destinationPortRange": "443", "sourceAddressPrefix": "192.0.2.4/32",
                                   "destinationAddressPrefix": "*"})
        self.assertEqual(run.normalized_rules(self.current[self.original["id"]]["securityRules"]),
                         run.normalized_rules(self.original["securityRules"]))
        self.assertEqual(self.current[self.extra["id"]]["securityRules"], [])

    def test_association_or_policy_drift_blocks_before_any_put(self):
        for mode in ("association", "rules", "tags", "source"):
            self.setUp()
            with self.mocks():
                self.discover()
                if mode == "association":
                    self.subnet["networkSecurityGroup"] = {"id": "foreign"}
                elif mode == "rules":
                    self.current[self.extra["id"]] = dict(self.extra, securityRules=self.original["securityRules"])
                elif mode == "tags":
                    self.current[self.extra["id"]] = dict(self.extra, tags={})
                else:
                    self.plan["snapshot_sources"] = {}
                with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                    self.step("allow-subnet")
            self.assertFalse(self.puts)

    def test_subnet_gate_requires_succeeded_and_exact_association(self):
        for mode in ("failed", "missing", "association"):
            self.setUp()
            with self.mocks():
                self.discover()
                def bad_query(argv, *args, **kwargs):
                    result = self.query(argv, *args, **kwargs)
                    if argv[0] == "rest":
                        if mode == "association":
                            self.subnet["networkSecurityGroup"] = {"id": "foreign"}
                        else:
                            self.current[self.extra["id"]]["provisioningState"] = (
                                "Failed" if mode == "failed" else None)
                    return result
                self.client.cli.side_effect = bad_query
                with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                    self.step("allow-subnet")
                self.assertFalse(self.files[self.directory / "subnet-nsg-gate.private.json"]["verified"])
                self.assertEqual(len(self.puts), 1)

    def test_tampered_allow_or_restore_body_cannot_broaden_bound_policy(self):
        for restoring in (False, True):
            self.setUp()
            with self.mocks():
                self.discover()
                if restoring:
                    self.step("deallocate-b")
                    self.step("deallocate-c")
                body = self.files[self.directory / (
                    "subnet-nsg-restore.private.json" if restoring else "subnet-nsg-allow.private.json")]
                if restoring:
                    body["tags"] = {}
                else:
                    body["properties"]["securityRules"][-1]["properties"]["sourceAddressPrefix"] = "*"
                with self.subTest(restoring=restoring), self.assertRaisesRegex(
                        RuntimeError, "exact_nsg_write_policy"):
                    self.step("restore-subnet-nsg" if restoring else "allow-subnet")
            self.assertFalse(self.puts)

    def test_foreign_owner_before_restore_and_stale_poweroff_receipt_fail_closed(self):
        for foreign in (False, True):
            self.setUp()
            with self.mocks():
                self.discover()
                self.step("deallocate-b")
                self.step("deallocate-c")
                if foreign:
                    self.current[self.extra["id"]] = dict(self.extra, tags={})
                else:
                    self.files[self.directory / "deallocate-b-verified.private.json"]["at"] = (
                        run.now() - run.timedelta(days=1)).isoformat()
                with self.subTest(foreign=foreign), self.assertRaisesRegex(
                        RuntimeError, "ownership_changed|quiescence_unverified"):
                    self.step("restore-subnet-nsg")
            self.assertFalse(self.puts)

    def exercise_fair_live_restoration(self, response=None, shared=False, lease_seconds=None):
        instant = run.now()
        self.clock = 0
        self.calls = []
        execute = run.execute

        def step(args):
            self.calls.append((args.action, vars(args).get("restore_phase")))
            if args.action in ("allow", "allow-subnet") or args.action.startswith(
                    ("deallocate-", "restore-")):
                execute(args)

        if shared:
            self.subnet["networkSecurityGroup"] = {"id": self.cfg["nsg_id"]}
            self.inventory["resources"].append(self.original)
        with self.mocks(), \
                mock.patch.object(run, "now", side_effect=lambda:
                                  instant + run.timedelta(seconds=self.clock)), \
                mock.patch.object(run.time, "monotonic", side_effect=lambda: self.clock), \
                mock.patch.object(run.time, "sleep", side_effect=lambda seconds:
                                  setattr(self, "clock", self.clock + seconds)), \
                mock.patch.object(run, "execute", side_effect=step), \
                mock.patch.object(run, "require_readiness"), \
                mock.patch.object(run, "metrics"), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()):
            self.discover()
            run.guard.return_value["allowedMutations"] = list(run.operations(self.plan))
            if lease_seconds is not None:
                run.guard.return_value["expiresAtUtc"] = (
                    instant + run.timedelta(seconds=lease_seconds)).isoformat()
            self.plan["status"] = "prepared_not_live"
            if response:
                self.client.cli.side_effect = response
            try:
                run.live(run.argparse.Namespace(run=self.directory.name, accept_live_gates=True),
                         self.directory, self.plan)
            except RuntimeError as error:
                self.assertIn("live_failed", str(error))
                self.assertEqual(self.plan["status"], "blocked")
        return self.plan

    def test_fair_live_nic_updating_submits_both_before_any_completion_poll(self):
        def response(argv, *args, **kwargs):
            if kwargs.get("operation") == "read-restore:restore-nsg":
                if argv[:2] == ["network", "nsg"] and any(
                        op == "restore-nsg" for _, op, _ in self.puts):
                    self.assertEqual([op for _, op, _ in self.puts][-2:],
                                     ["restore-nsg", "restore-subnet-nsg"])
                    return dict(self.current[self.original["id"]], provisioningState="Updating")
            return self.query(argv, *args, **kwargs)

        plan = self.exercise_fair_live_restoration(response)
        self.assertEqual([op for _, op, _ in self.puts],
                         ["allow-subnet", "allow", "restore-nsg", "restore-subnet-nsg"])
        self.assertEqual([phase for op, phase in self.calls if op.startswith("restore-")],
                         ["submit", "submit", "poll", "poll"])
        self.assertTrue(any("nsg_restore_timeout" in item for item in plan["failures"]))
        self.assertFalse(self.files[self.directory / "nsg-restored.private.json"]["verified"])
        self.assertTrue(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
        self.assertLessEqual(self.clock, 900)

    def test_fair_live_first_put_failure_or_timeout_does_not_skip_second(self):
        for timeout in (False, True):
            self.setUp()
            attempted = []

            def response(argv, *args, **kwargs):
                if argv[0] == "rest" and args[0].startswith("restore-"):
                    attempted.append(args[0])
                    if args[0] == "restore-nsg":
                        if timeout:
                            self.clock += args[1]
                            raise subprocess.TimeoutExpired(["mock-put"], args[1])
                        raise RuntimeError("mock_restore_put_failed")
                return self.query(argv, *args, **kwargs)

            with self.subTest(timeout=timeout):
                plan = self.exercise_fair_live_restoration(response)
                self.assertEqual(attempted, ["restore-nsg", "restore-subnet-nsg"])
                self.assertEqual(plan["status"], "blocked")
                self.assertTrue(any("restore-nsg:submit:" in row for row in plan["failures"]))
                self.assertTrue(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
                self.assertFalse(self.files[self.directory / "nsg-restored.private.json"]["verified"])
                self.assertLessEqual(self.clock, 900)

    def test_fair_live_shared_nsg_restores_once_and_both_deallocations_precede_put(self):
        plan = self.exercise_fair_live_restoration(shared=True)
        self.assertEqual(plan["status"], "completed")
        self.assertEqual([op for _, op, _ in self.puts], ["allow", "restore-nsg"])
        actions = [op for op, _ in self.calls]
        first_restore = actions.index("restore-nsg")
        for operation in ("deallocate-b", "deallocate-c"):
            self.assertLess(actions.index(operation), first_restore)
        self.assertEqual(len(run.operations(plan)), 8)

    def test_fair_live_authorization_or_ownership_read_timeout_keeps_other_submission(self):
        for mode in ("authorization", "ownership"):
            self.setUp()

            def authorize(operation, seconds=90):
                if operation == "restore-nsg":
                    self.clock += seconds
                    raise subprocess.TimeoutExpired(["mock-authorization"], seconds)

            def response(argv, *args, **kwargs):
                if kwargs.get("operation") == "read-restore:restore-nsg":
                    self.clock += kwargs["seconds"]
                    raise subprocess.TimeoutExpired(["mock-ownership"], kwargs["seconds"])
                return self.query(argv, *args, **kwargs)

            if mode == "authorization":
                self.client.authorize.side_effect = authorize
            with self.subTest(mode=mode):
                plan = self.exercise_fair_live_restoration(response if mode == "ownership" else None)
                self.assertEqual(plan["status"], "blocked")
                self.assertEqual([op for _, op, _ in self.puts][-1], "restore-subnet-nsg")
                self.assertTrue(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
                self.assertLess(self.clock, 900)

    def test_fair_live_put_timeout_is_clipped_to_short_lease_and_other_put_is_attempted(self):
        attempted = []

        def response(argv, *args, **kwargs):
            if argv[0] == "rest" and args[0].startswith("restore-"):
                attempted.append(args[0])
                if args[0] == "restore-nsg":
                    self.assertLessEqual(args[1], (200 - 11) / 4)
                    self.clock += args[1]
                    raise subprocess.TimeoutExpired(["mock-put"], args[1])
            return self.query(argv, *args, **kwargs)

        plan = self.exercise_fair_live_restoration(response, lease_seconds=200)
        self.assertEqual(attempted, ["restore-nsg", "restore-subnet-nsg"])
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
        self.assertLess(self.clock, 189)

    def test_fair_live_deadline_expiry_is_blocked_not_verified_or_retried(self):
        def response(argv, *args, **kwargs):
            result = self.query(argv, *args, **kwargs)
            if argv[0] == "rest" and args[0] == "restore-nsg":
                self.clock += 900
            return result

        plan = self.exercise_fair_live_restoration(response)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("restore-subnet-nsg:submit:" in row for row in plan["failures"]))
        self.assertFalse(self.files[self.directory / "nsg-restored.private.json"]["verified"])
        self.assertFalse(self.files[self.directory / "subnet-nsg-restored.private.json"]["verified"])
        self.assertEqual(sum(op == "restore-nsg" for _, op, _ in self.puts), 1)
        self.assertEqual(sum(op == "restore-subnet-nsg" for _, op, _ in self.puts), 0)

    def test_fair_live_deallocation_timeout_attempts_other_and_never_restores_unsafe(self):
        deallocations = []

        def response(argv, *args, **kwargs):
            if argv[:2] == ["vm", "deallocate"]:
                deallocations.append(args[0])
                if len(deallocations) == 1:
                    self.clock += args[1]
                    raise subprocess.TimeoutExpired(["mock-deallocate"], args[1])
            return self.query(argv, *args, **kwargs)

        plan = self.exercise_fair_live_restoration(response)
        self.assertEqual(deallocations, ["deallocate-b", "deallocate-c"])
        self.assertEqual(plan["status"], "blocked")
        self.assertFalse(any(op.startswith("restore-") for _, op, _ in self.puts))
        self.assertLess(self.clock, 900)

    def test_fair_live_partial_allow_put_failure_restores_both_without_guests(self):
        def response(argv, *args, **kwargs):
            result = self.query(argv, *args, **kwargs)
            if argv[0] == "rest" and args[0] == "allow":
                raise subprocess.TimeoutExpired(["mock-allow"], args[1])
            return result

        plan = self.exercise_fair_live_restoration(response)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual([op for _, op, _ in self.puts],
                         ["allow-subnet", "allow", "restore-nsg", "restore-subnet-nsg"])
        self.assertNotIn("server", [op for op, _ in self.calls])
        self.assertNotIn("client", [op for op, _ in self.calls])
        for prefix in ("nsg", "subnet-nsg"):
            self.assertTrue(self.files[self.directory / (prefix + "-restored.private.json")]["verified"])

    def test_subnet_restore_updating_readback_is_not_success(self):
        with self.mocks(), mock.patch.object(run.time, "sleep") as sleep:
            self.discover()
            self.step("allow-subnet")
            self.step("allow")
            self.step("deallocate-b")
            self.step("deallocate-c")
            pending = False
            def updating(argv, *args, **kwargs):
                nonlocal pending
                result = self.query(argv, *args, **kwargs)
                if argv[0] == "rest":
                    pending = True
                elif pending and argv[1] == "nsg":
                    pending = False
                    return dict(result, provisioningState="Updating")
                return result
            self.client.cli.side_effect = updating
            self.step("restore-subnet-nsg")
            evidence = self.files[self.directory / "subnet-nsg-restored.private.json"]
            self.assertTrue(evidence["verified"])
            self.assertEqual([row["nsg"]["provisioningState"] for row in evidence["polls"]],
                             ["Updating", "Succeeded"])
            sleep.assert_called_once_with(30)
            self.assertEqual(sum(op == "restore-subnet-nsg" for _, op, _ in self.puts), 1)


class ControlPayloadTests(unittest.TestCase):
    def test_control_bounded_proportional_caps_and_remaining(self):
        for payload, cap in ((1, stream.GIB), (stream.GIB, 2 * stream.GIB),
                             (5 * stream.GIB, 6 * stream.GIB)):
            plan = WrapperTests().control()
            plan.update(bytes=payload, wire_cap=cap, core_remaining_bytes=5 * stream.GIB
                        if payload == stream.GIB else 23 * stream.GIB)
            self.assertEqual(run.control_wire_cap(payload), cap)
            with mock.patch.object(run, "read", return_value=plan["B"]):
                run.control_gates(plan)
            if payload == stream.GIB:
                self.assertEqual(plan["core_remaining_bytes"] - cap, 3 * stream.GIB)
        for value in (0, -1, True, 1.0, 5 * stream.GIB + 1):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                run.control_wire_cap(value)

    def test_payload_option_cannot_expand_default_at_budget(self):
        with mock.patch.object(Path, "mkdir"), mock.patch.object(Path, "exists", return_value=False), \
                mock.patch.object(run, "read", return_value={}), \
                self.assertRaisesRegex(RuntimeError, "control_payload_requires_control"):
            run.prepare(mock.Mock(run="mock", control=False, control_payload_bytes=stream.GIB))

    def test_verifier_uses_declared_count_hash_wirecap_not_fixed_five_gib(self):
        payload = stream.GIB
        plan = {"id": "a" * 32, "bytes": payload, "payload_sha256": "expected",
                "wire_cap": 2 * stream.GIB, "legs": ["up"],
                "aliases": {"client": "C", "server": "B"}}
        report = {"success": True, "declared_legs": ["up"], "aliases": plan["aliases"],
                  "nic": {"delta": {"wire_once": payload + 100}},
                  "legs": {"up": {"id": plan["id"] + "-up", "producer": "C", "consumer": "B",
                                  "bytes": payload, "sha256": "expected", "status": "ok", "retries": 0}}}
        self.assertEqual(stream.verify(report, report, plan)["transport"], "PASS")
        for key, value in (("bytes", 5 * stream.GIB), ("sha256", "wrong"), ("id", "other-up")):
            changed = json.loads(json.dumps(report))
            changed["legs"]["up"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "declared_payload"):
                stream.verify(changed, changed, plan)
        report["nic"]["delta"]["wire_once"] = plan["wire_cap"]
        with self.assertRaisesRegex(ValueError, "declared_payload"):
            stream.verify(report, report, plan)


if __name__ == "__main__":
    unittest.main()
