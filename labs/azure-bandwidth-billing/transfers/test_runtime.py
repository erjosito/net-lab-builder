"""Offline tests for bounded repeat power transitions and source-bound deadlines."""
from datetime import datetime, timedelta, timezone
import copy
import json
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
import uuid

import run
import stream


class LeaseLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = run.LAB / "private" / ("lock-unit-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.directory))
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(run, "PRIVATE", self.directory).start()
        mock.patch.object(run, "LEASE", self.directory / "lease.json").start()
        mock.patch.object(run, "EXECUTION_GUARD", None).start()
        current = run.now()
        self.lease = {"state": "active", "startedAtUtc": current.isoformat(),
                      "expiresAtUtc": (current + timedelta(hours=1)).isoformat(),
                      "maxToolCalls": 150, "actualToolCalls": 0, "maxMutations": 12,
                      "actualMutations": 0, "activeCommands": 0, "ownedProcessesIdle": True,
                      "commandTimeoutSeconds": 180,
                      "allowedMutations": ["start-a", "allow", "server", "deallocate-a"]}
        run.save(run.LEASE, self.lease)

    def test_real_parallel_guard_over_five_seconds_serializes_and_reenters(self):
        entered = threading.Event()
        failures = []
        first = True

        def guard(operation, seconds):
            nonlocal first
            with run.lease_lock(operation, seconds):
                if first:
                    first = False
                    entered.set()
                    time.sleep(5.3)

        def command(operation):
            try:
                run.Azure({}).cli([], operation, seconds=90)
            except BaseException as error:
                failures.append(error)

        with mock.patch.object(run, "EXECUTION_GUARD", side_effect=guard), \
                mock.patch("repeat.require_lease_binding"), \
                mock.patch.object(run.Azure, "_invoke", return_value={}):
            threads = [threading.Thread(target=command, args=(operation,))
                       for operation in ("start-a", "allow", "server")]
            threads[0].start()
            self.assertTrue(entered.wait(2))
            for thread in threads[1:]:
                thread.start()
            for thread in threads:
                thread.join(15)
            self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        lease = run.read(run.LEASE)
        self.assertEqual((lease["actualToolCalls"], lease["actualMutations"],
                          lease["activeCommands"], lease["ownedProcessesIdle"]), (3, 3, 0, True))
        self.assertFalse((self.directory / ".lease-lock").exists())

    def test_foreign_process_sentinel_fails_bounded_without_deletion(self):
        script = ("import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); p.mkdir(); "
                  "print('held',flush=True); time.sleep(30)")
        child = subprocess.Popen([sys.executable, "-c", script,
                                  str(self.directory / ".lease-lock")],
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "held")
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "lease_lock_busy"):
                with run.lease_lock():
                    self.fail("foreign sentinel adopted")
            self.assertLess(time.monotonic() - start, 7)
            self.assertTrue((self.directory / ".lease-lock").is_dir())
        finally:
            child.terminate()
            child.wait(timeout=5)
            child.stdout.close()

    def test_exception_release_and_stop_expiry_call_budget_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "critical"):
            with run.lease_lock():
                raise ValueError("critical")
        self.assertFalse((self.directory / ".lease-lock").exists())
        for mode in ("stop", "expiry", "calls"):
            lease = dict(self.lease)
            if mode == "expiry":
                lease["expiresAtUtc"] = run.now().isoformat()
            elif mode == "calls":
                lease["actualToolCalls"] = lease["maxToolCalls"]
            else:
                (self.directory / "STOP").write_text("STOP")
            run.save(run.LEASE, lease)
            with mock.patch.object(run.Azure, "_invoke") as invoke:
                with self.assertRaises(RuntimeError):
                    run.Azure({}).cli([], "start-a", 90)
                invoke.assert_not_called()
            (self.directory / "STOP").unlink(missing_ok=True)

    def test_owner_change_never_removes_foreign_sentinel(self):
        with self.assertRaisesRegex(RuntimeError, "lease_lock_owner_changed"):
            with run.lease_lock():
                (self.directory / ".lease-lock" / "owner.json").write_text('{"token":"foreign"}')
        self.assertTrue((self.directory / ".lease-lock" / "owner.json").is_file())


# Sanitized decisive fields from the saved 2026-10-16T17:11:20Z T response.
UNPUBLISHED_VIEW = {
    "id": "/subscriptions/sub/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a",
    "provisioningState": "Updating",
    "instanceView": {"statuses": [
        {"code": "ProvisioningState/updating", "displayStatus": "Updating", "level": "Info"}]}}


class RuntimeTests(unittest.TestCase):
    def test_no_wait_native_and_wsl_command_execution_preserves_explicit_subscription(self):
        for wsl in (False, True):
            for verb in ("start", "deallocate"):
                with self.subTest(wsl=wsl, verb=verb), \
                        mock.patch.object(run.shutil, "which", return_value=r"C:\cli\bin\az.cmd"), \
                        mock.patch.object(run.Path, "is_file", return_value=True), \
                        mock.patch.object(run, "bounded", return_value="") as bounded:
                    result = run.Azure({"subscriptionId": "explicit-sub"}, wsl=wsl)._invoke(
                        ["vm", verb, "-g", "approved-rg", "-n", "approved-vm", "--no-wait"],
                        verb + "-a", 90, None)
                argv, timeout, progress = bounded.call_args.args
                self.assertIsNone(result)
                self.assertEqual(timeout, 90)
                self.assertIn("--no-wait", argv)
                self.assertEqual(argv[argv.index("--subscription") + 1], "explicit-sub")
                self.assertIn("/usr/bin/az" if wsl else "azure.cli", argv)
                self.assertNotIn("login", argv)

    def test_pilot_bulk_and_legacy_profiles(self):
        for size, command in ((stream.GIB, 900), (stream.MAX_BYTES, 1580)):
            profile = run.repeat_runtime(size, stream.MAX_RATE)
            self.assertEqual(profile, {
                "commandSeconds": command, "foregroundSeconds": command - 50,
                "streamSeconds": command - 100, "restoreSeconds": 900,
                "runwaySeconds": command + 900, "startupSeconds": 300,
                "submissionSeconds": 90, "pollSeconds": 30})
            plan = {"repeat_session": "offline", "bytes": size, "rate": stream.MAX_RATE,
                    "runtime_profile": profile}
            self.assertEqual(run.runtime(plan), profile)
            for key in profile:
                for bad in (0, -1, profile[key] + 1):
                    changed = copy.deepcopy(plan)
                    changed["runtime_profile"][key] = bad
                    with self.assertRaisesRegex(RuntimeError, "profile_mismatch"):
                        run.runtime(changed)
        self.assertEqual(run.runtime({}), {
            "commandSeconds": 2500, "foregroundSeconds": 2450, "streamSeconds": 2400,
            "restoreSeconds": 900, "runwaySeconds": 3400})
        for size, rate in ((0, 1), (-1, 1), (1, 0), (1, -1), (True, 1),
                           (stream.MAX_BYTES + 1, 1), (1, stream.MAX_RATE + 1)):
            with self.assertRaisesRegex(RuntimeError, "invalid_repeat_runtime"):
                run.repeat_runtime(size, rate)

    def test_native_instance_view_shapes_and_unknown_fail_closed(self):
        statuses = {"statuses": [{"code": "ProvisioningState/succeeded"},
                                 {"code": "PowerState/running"}]}
        self.assertEqual(run.power_state(statuses), "PowerState/running")
        self.assertEqual(run.power_state({"instanceView": statuses}), "PowerState/running")
        for value in (None, {}, {"statuses": []}, {"instanceView": None},
                      {"statuses": [{"code": "PowerState/running"}] * 2},
                      UNPUBLISHED_VIEW):
            with self.assertRaises(RuntimeError):
                run.power_state(value)


class AsyncPowerTests(unittest.TestCase):
    def setUp(self):
        self.directory = run.LAB / "private" / ("async-unit-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.directory))
        self.elapsed = 0
        self.epoch = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        self.patch("PRIVATE", self.directory)
        self.patch("LEASE", self.directory / "lease.json")
        self.patch("now", lambda: self.epoch + timedelta(seconds=self.elapsed))
        self.patch("EXECUTION_GUARD", None)
        mock.patch.object(run.time, "monotonic", side_effect=lambda: self.elapsed).start()
        mock.patch.object(run.time, "sleep", side_effect=self.advance).start()
        self.addCleanup(mock.patch.stopall)
        self.lease = {
            "taskId": uuid.uuid4().hex, "state": "active", "maxToolCalls": 75,
            "actualToolCalls": 0, "maxMutations": 6, "actualMutations": 0,
            "activeCommands": 0, "ownedProcessesIdle": True, "commandTimeoutSeconds": 180,
            "allowedMutations": ["start-a", "start-t", "deallocate-a", "deallocate-t"],
            "startedAtUtc": self.epoch.isoformat(),
            "expiresAtUtc": (self.epoch + timedelta(minutes=30)).isoformat()}
        run.save(run.LEASE, self.lease)
        self.plan = {"id": uuid.uuid4().hex, "repeat_session": "offline",
                     "bytes": stream.GIB, "rate": stream.MAX_RATE,
                     "runtime_profile": run.repeat_runtime(stream.GIB, stream.MAX_RATE),
                     "readiness_started": self.epoch.isoformat(),
                     "startup_deadline": (self.epoch + timedelta(seconds=300)).isoformat(),
                     "A": {"vm": "vm-a", "resourceGroup": "rg-a", "subscriptionId": "sub"},
                     "T": {"vm": "vm-t", "resourceGroup": "rg-t", "subscriptionId": "sub"}}
        self.calls = []
        self.states = ["running"]
        self.hook = None
        self.client = run.Azure(self.plan["A"])
        mock.patch.object(run.Azure, "_invoke", autospec=True, side_effect=self.invoke).start()

    def patch(self, name, value):
        mock.patch.object(run, name, value).start()

    def advance(self, seconds):
        self.elapsed += seconds

    def invoke(self, client, argv, operation, seconds, directory):
        self.calls.append((list(argv), operation, seconds, self.elapsed))
        if self.hook:
            self.hook(argv, operation)
        if argv[:2] == ["vm", "get-instance-view"]:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            if isinstance(state, dict):
                return copy.deepcopy(state)
            return {"instanceView": {"statuses": [{"code": "PowerState/" + state}]}}
        return None  # Successful no-wait submission may have empty stdout.

    def restore_seconds(self, limit):
        run.guard("read-restore:deallocate-a", 0)
        return min(limit, 900 - self.elapsed)

    def transition(self, operation="start-a"):
        run.async_vm(self.directory, self.plan, "A", self.client, operation,
                     ["-g", "rg-a", "-n", "vm-a"], self.restore_seconds)

    def test_accepted_submission_is_not_running_then_next_poll_proves_running(self):
        self.states = ["starting", "running"]
        self.transition()
        self.assertEqual(self.calls[0][0], [
            "vm", "start", "-g", "rg-a", "-n", "vm-a", "--no-wait"])
        self.assertEqual(self.calls[0][2], 90)
        polls = [row for row in self.calls if row[0][1] == "get-instance-view"]
        self.assertEqual(len(polls), 2)
        self.assertEqual([row[2] for row in polls], [30, 30])
        self.assertGreaterEqual(polls[1][3] - polls[0][3], 30)
        self.assertEqual(run.read(run.LEASE)["actualToolCalls"], 3)
        self.assertEqual(run.read(run.LEASE)["actualMutations"], 1)
        binding = run.vm_phase_binding(self.plan, "A")
        self.assertTrue(run.read(run.running_proof_path(self.directory, binding))["verified"])
        with self.assertRaises(FileExistsError):
            self.transition()
        self.assertEqual(len(self.calls), 3)

    def test_never_running_has_no_proof_or_runcommand_and_finite_poll_budget(self):
        self.states = ["starting"]
        with self.assertRaisesRegex(RuntimeError, "observation_timeout"):
            self.transition()
        self.assertEqual(len(self.calls), 11)  # One submission and ten spaced GETs.
        self.assertLessEqual(self.elapsed, 300)
        self.assertFalse(list(self.directory.glob("running-*.private.json")))
        self.assertFalse(any("run-command" in row[0] for row in self.calls))

    def test_unpublished_then_running_requires_fresh_unique_state(self):
        self.states = [UNPUBLISHED_VIEW, "running"]
        self.transition()
        observation = run.read(next(self.directory.glob("*-observation.private.json")))
        self.assertEqual([p["state"] for p in observation["polls"]],
                         ["UNPUBLISHED", "PowerState/running"])
        self.assertEqual(observation["polls"][0]["view"], UNPUBLISHED_VIEW)
        self.assertEqual(self.calls[2][3] - self.calls[1][3], 30)
        self.assertEqual(sum(row[1] == "start-a" for row in self.calls), 1)
        proof = run.read(run.running_proof_path(
            self.directory, run.vm_phase_binding(self.plan, "A")))
        self.assertTrue(proof["verified"])

    def test_unpublished_then_deallocated_requires_fresh_unique_state(self):
        self.states = [UNPUBLISHED_VIEW, "deallocated"]
        self.transition("deallocate-a")
        observation = run.read(next(self.directory.glob("*-observation.private.json")))
        self.assertEqual([p["state"] for p in observation["polls"]],
                         ["UNPUBLISHED", "PowerState/deallocated"])
        self.assertEqual(self.calls[2][3] - self.calls[1][3], 30)
        self.assertEqual(sum(row[1] == "deallocate-a" for row in self.calls), 1)
        self.assertTrue(run.read(self.directory / "deallocate-a-verified.private.json")["verified"])

    def test_persistent_unpublished_times_out_without_positive_proof(self):
        for operation in ("start-a", "deallocate-a"):
            with self.subTest(operation=operation):
                self.elapsed = 0
                self.states = [UNPUBLISHED_VIEW]
                before = len(self.calls)
                with self.assertRaisesRegex(RuntimeError, "vm_state_observation_timeout"):
                    self.transition(operation)
                self.assertEqual(len(self.calls) - before, 11)
                self.assertLessEqual(self.elapsed, 300)
                observation = run.read(next(self.directory.glob(
                    operation + "*-observation.private.json")))
                self.assertFalse(observation["verified"])
                self.assertTrue(all(p["state"] == "UNPUBLISHED" for p in observation["polls"]))
                self.assertFalse(list(self.directory.glob("running-*.private.json")))
                self.assertFalse(list(self.directory.glob("*-verified.private.json")))
                self.assertFalse(any("run-command" in row[0] for row in self.calls))

    def test_malformed_or_ambiguous_observation_fails_closed_and_retains_raw(self):
        for statuses in (None, {}, [None], [{}], [{"code": None}], [{"code": ""}],
                         [{"code": "PowerState/"}], [{"code": "PowerState/running"}] * 2,
                         [{"code": "PowerState/running"}, {"code": "PowerState/deallocated"}],
                         [{"code": "PowerState/running"}, None]):
            with self.subTest(statuses=statuses):
                run.save(run.LEASE, self.lease)
                self.plan["readiness_started"] = (self.epoch + timedelta(
                    microseconds=len(self.calls) + 1)).isoformat()
                view = {"instanceView": {"statuses": statuses}}
                self.states = [view]
                before = len(self.calls)
                with self.assertRaises(RuntimeError):
                    self.transition()
                self.assertEqual(len(self.calls) - before, 2)
                observations = [run.read(p) for p in self.directory.glob(
                    "*-observation.private.json")]
                self.assertTrue(any(o["polls"][0]["view"] == view for o in observations))
                self.assertTrue(all(not o["verified"] for o in observations))
                self.assertFalse(list(self.directory.glob("running-*.private.json")))

    def test_ambiguous_submission_observes_without_resending_or_claiming_success(self):
        original = RuntimeError("first-original-submission-failure")
        def fail(argv, operation):
            if operation == "start-a":
                raise original
        self.hook = fail
        with self.assertRaises(RuntimeError) as caught:
            self.transition()
        self.assertIs(caught.exception, original)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(sum(row[1] == "start-a" for row in self.calls), 1)
        self.assertFalse(list(self.directory.glob("running-*.private.json")))
        observation = run.read(next(self.directory.glob("*-observation.private.json")))
        self.assertTrue(observation["verified"])
        self.assertIn(str(original), observation["failures"][0])

    def test_stop_expiry_and_eighty_percent_between_polls_prevent_further_reads(self):
        for mode in ("stop", "expiry", "calls"):
            with self.subTest(mode=mode):
                # Each case uses a distinct phase and immutable attempt.
                self.plan["readiness_started"] = (self.epoch + timedelta(
                    microseconds=len(self.calls) + 1)).isoformat()
                self.states = [UNPUBLISHED_VIEW]
                def cancel(seconds):
                    self.advance(seconds)
                    if mode == "stop":
                        (run.LEASE.parent / "STOP").write_text("STOP")
                    else:
                        lease = run.read(run.LEASE)
                        lease["expiresAtUtc" if mode == "expiry" else "actualToolCalls"] = (
                            run.now().isoformat() if mode == "expiry" else 60)
                        run.save(run.LEASE, lease)
                before = len(self.calls)
                with mock.patch.object(run.time, "sleep", side_effect=cancel), \
                        self.assertRaisesRegex(RuntimeError, "inactive_or_short|restoration_only"):
                    self.transition()
                self.assertEqual(len(self.calls) - before, 2)
                self.assertEqual(run.read(run.LEASE)["activeCommands"], 0)
                self.assertTrue(run.read(run.LEASE)["ownedProcessesIdle"])
                (run.LEASE.parent / "STOP").unlink(missing_ok=True)
                run.save(run.LEASE, self.lease)

    def test_unpublished_restore_honors_stop_call_budget_and_restore_deadline(self):
        for mode in ("stop", "calls", "deadline"):
            with self.subTest(mode=mode):
                self.elapsed = 0
                self.plan["readiness_started"] = (self.epoch + timedelta(
                    microseconds=len(self.calls) + 1)).isoformat()
                self.states = [UNPUBLISHED_VIEW]
                def cancel(seconds):
                    self.advance(seconds)
                    if mode == "stop":
                        (run.LEASE.parent / "STOP").write_text("STOP")
                    elif mode == "calls":
                        lease = run.read(run.LEASE)
                        lease["actualToolCalls"] = lease["maxToolCalls"]
                        run.save(run.LEASE, lease)
                before = len(self.calls)
                with mock.patch.object(run.time, "sleep", side_effect=cancel), \
                        mock.patch.object(self, "restore_seconds", side_effect=lambda limit: (
                            run.guard("read-restore:deallocate-a", 0) and
                            min(limit, (30 if mode == "deadline" else 900) - self.elapsed))), \
                        self.assertRaisesRegex(RuntimeError, "inactive_or_short|tool_budget|observation_timeout"):
                    self.transition("deallocate-a")
                self.assertEqual(len(self.calls) - before, 2)
                self.assertFalse(list(self.directory.glob("*-verified.private.json")))
                self.assertEqual(run.read(run.LEASE)["activeCommands"], 0)
                self.assertTrue(run.read(run.LEASE)["ownedProcessesIdle"])
                (run.LEASE.parent / "STOP").unlink(missing_ok=True)
                run.save(run.LEASE, self.lease)

    def test_stale_readiness_start_response_cannot_satisfy_current_phase(self):
        run.save(self.directory / "start-a.private.json", {"success": True})
        binding = run.vm_phase_binding(self.plan, "A")
        stale = dict(binding, taskId="old-readiness-task")
        run.save(run.running_proof_path(self.directory, stale),
                 {"verified": True, "binding": stale, "at": self.epoch.isoformat()})
        with self.assertRaises(FileNotFoundError):
            run.require_running(self.directory, self.plan)
        self.assertEqual(self.calls, [])

    def test_deallocate_is_async_and_receipt_requires_deallocated_get(self):
        self.states = ["deallocating", "deallocated"]
        self.transition("deallocate-a")
        self.assertIn("--no-wait", self.calls[0][0])
        self.assertEqual(self.calls[0][2], 90)
        self.assertEqual(len(self.calls), 3)
        proof = run.read(self.directory / "deallocate-a-verified.private.json")
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["phase_binding"], run.vm_phase_binding(self.plan, "A"))


if __name__ == "__main__":
    unittest.main()
