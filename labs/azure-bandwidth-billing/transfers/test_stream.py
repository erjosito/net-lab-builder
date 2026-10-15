"""Small localhost-only contract tests; generated certificates remain lab-private."""
import contextlib
import http.client
import json
import socket
import ssl
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import run
import stream

ROOT = run.PRIVATE / "local-tests"


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
                       {"bytes": 1.5}, {"readiness_attempts": 13}):
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


class WrapperTests(unittest.TestCase):
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
        with self.assertRaises(subprocess.TimeoutExpired):
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
                mock.patch.object(run, "execute", side_effect=fail_at_start), \
                mock.patch.object(run, "lease_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(run, "read", return_value={"activeCommands": 0}), \
                mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaises(RuntimeError):
                run.live(args, ROOT, plan)
        self.assertEqual(calls, ["start-a", "start-t", "restore-nsg",
                                 "deallocate-t", "deallocate-a"])
        self.assertEqual(plan["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
