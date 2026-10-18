"""Public CLI integration fixtures. No Azure requests or authentication changes."""
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch
import urllib.error
import uuid

import cost_api as api
import preflight_compare
from test_cost_api import SUB, TENANT, RG, RID, args

POLL = (api.ARM + f"/subscriptions/{SUB}/providers/Microsoft.CostManagement/"
        "costDetailsOperationStatus/11111111-1111-1111-1111-111111111111"
        "?api-version=" + api.REPORT_VERSION)
BLOB = "https://synthetic.blob.core.windows.net/reports/one.csv?sig=SECRET"
RAW = ("ResourceId,resourceGroupName,date,quantity,unitOfMeasure,effectivePrice,"
       "costInBillingCurrency,billingCurrency,meterCategory,meterName\n"
       f"{RID}, {RG},10/15/2026,0.6551259830594063,1 GB,0.02,"
       "0.013102519661188125,USD,Bandwidth,Transfer\n").replace(f", {RG},", f",{RG},").encode()


class Response(io.BytesIO):
    def __init__(self, value=b"", status=200, headers=None):
        super().__init__(json.dumps(value).encode() if isinstance(value, dict) else value)
        self.status, self.headers = status, headers or {}


def completed(blobs=None):
    blobs = blobs or [{"blobLink": BLOB, "byteCount": len(RAW)}]
    return {"status": "Completed", "manifest": {
        "dataFormat": "Csv", "compressData": False, "blobCount": len(blobs),
        "byteCount": sum(b["byteCount"] for b in blobs), "blobs": blobs,
        "requestContext": {"requestScope": f"subscriptions/{SUB}",
                           "requestBody": {"metric": "ActualCost",
                                           "timePeriod": {"start": "2026-10-15",
                                                          "end": "2026-10-16"}}}}}


class PublicWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = api.LAB / "private" / ("offline-cli-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.lab = patch("cost_api.LAB", self.root)
        self.lab.start()
        self.private = self.root / "private"
        self.private.mkdir()
        self.context = self.private / "context.json"
        self.context.write_text(json.dumps({"subscriptionId": SUB, "expectedTenantId": TENANT,
                                            "resourceGroup": RG}), encoding="utf-8")
        self.inventory = self.private / "inventory.json"
        self.inventory.write_text(json.dumps({"resources": [{"id": RID}]}), encoding="utf-8")
        self.output = self.private / "report.json"
        self.csv = self.private / "report.csv"

    def tearDown(self):
        self.lab.stop()
        shutil.rmtree(self.root)

    def command(self, command="cost-details", extra=None):
        values = [command, "--context", str(self.context), "--inventory", str(self.inventory),
                  "--start", "2026-10-15", "--end", "2026-10-16",
                  "--output", str(self.output)]
        if command == "cost-details":
            values += ["--csv-output", str(self.csv)]
        return values + (extra or [])

    def run_cli(self, responses, command=None):
        opener = Mock()
        opener.open.side_effect = responses
        account = {"id": SUB, "tenantId": TENANT, "state": "Enabled"}
        token = {"subscription": SUB, "tenant": TENANT, "accessToken": "ARM_SECRET",
                 "expires_on": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).timestamp()}
        with patch("cost_api.urllib.request.build_opener", return_value=opener), patch(
                "cost_api.cli_json", side_effect=[account, token]) as cli, patch(
                "cost_api.time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO) as out:
            code = api.main(command or self.command())
        return code, json.loads(out.getvalue()), opener, cli, sleep

    def test_public_202_location_retry_poll_manifest_blob_and_auto_lease(self):
        code, summary, opener, cli, sleep = self.run_cli([
            Response(status=202, headers={"Location": POLL, "Retry-After": "20"}),
            Response(status=202, headers={
                "Retry-After": "31", "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "35"}),
            Response(completed()), Response(RAW)])
        self.assertEqual(code, 0)
        self.assertTrue(summary["extractionComplete"])
        self.assertFalse(summary["ingestionFinal"])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [30, 35])
        self.assertEqual(cli.call_count, 2)
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[1].full_url, POLL)
        self.assertEqual(requests[-1].headers, {})
        data = json.loads(self.output.read_text())
        self.assertEqual(data["rows"][0]["quantity"], "0.6551259830594063")
        self.assertIn("0.013102519661188125", self.csv.read_text())
        for secret in ("ARM_SECRET", "sig=", "SECRET", "operationStatus/"):
            self.assertNotIn(secret, self.output.read_text() + self.csv.read_text() + json.dumps(summary))
        leases = list((self.root / "deploy" / ".runtime-control").glob("cost-cli-*.json"))
        self.assertEqual(len(leases), 1)
        lease = json.loads(leases[0].read_text())
        self.assertEqual((lease["state"], lease["actualHttpRequests"]), ("idle", 4))
        self.assertFalse((leases[0].parent / "cost-cli-owner.json").exists())

    def test_immediate_completion_downloads_all_blobs_no_row_dedup(self):
        blobs = [{"blobLink": BLOB, "byteCount": len(RAW)},
                 {"blobLink": BLOB.replace("one.csv", "two.csv"), "byteCount": len(RAW)}]
        code, summary, opener, _, sleep = self.run_cli([
            Response(completed(blobs)), Response(RAW), Response(RAW)])
        self.assertEqual((code, summary["retained"], opener.open.call_count), (0, 2, 3))
        sleep.assert_not_called()

    def test_request_timeout_default_and_explicit_reach_arm_and_blob(self):
        for command in ("query", "details", "cost-details"):
            for timeout in (20, 120):
                with self.subTest(command=command, timeout=timeout):
                    extra = [] if timeout == 20 else [
                        "--request-timeout-seconds", "120", "--max-seconds", "300"]
                    responses = ([Response(completed()), Response(RAW)] if command == "cost-details"
                                 else [Response({"value": []})] if command == "details"
                                 else [Response({"properties": {"columns": [], "rows": []}})])
                    code, _, opener, cli, sleep = self.run_cli(
                        responses, self.command(command, extra))
                    self.assertEqual(code, 0)
                    self.assertEqual([call.kwargs["timeout"] for call in opener.open.call_args_list],
                                     [timeout] * len(responses))
                    self.assertEqual([call.args[1] for call in cli.call_args_list], [15, 15])
                    sleep.assert_not_called()
                    if command == "cost-details":
                        self.assertEqual(opener.open.call_args.args[0].full_url, BLOB)
                        self.assertEqual(opener.open.call_args.args[0].headers, {})
                        self.csv.unlink()
                    self.output.unlink()

    def test_invalid_request_timeouts_fail_before_auth_http_or_wsl_dispatch(self):
        for command in ("query", "details", "cost-details"):
            for transport in ("native", "wsl"):
                for value in ("0", "-1", "1.5", "abc", "nan", "inf"):
                    with self.subTest(command=command, transport=transport, value=value), patch(
                            "cost_api.cli_json") as cli, patch(
                            "cost_api.urllib.request.build_opener") as opener, patch(
                            "cost_api.run_bounded") as runner, patch(
                            "sys.stdout", new_callable=io.StringIO) as out, patch(
                            "sys.stderr", new_callable=io.StringIO):
                        command_args = self.command(command, [
                            "--transport", transport, "--request-timeout-seconds", value])
                        if value in ("0", "-1"):
                            self.assertEqual(api.main(command_args), 2)
                            self.assertEqual(json.loads(out.getvalue())["code"], "invalid_bounds")
                        else:
                            with self.assertRaises(SystemExit) as error:
                                api.main(command_args)
                            self.assertEqual(error.exception.code, 2)
                        cli.assert_not_called()
                        opener.assert_not_called()
                        runner.assert_not_called()
                        self.assertFalse((self.root / "deploy").exists())

    def test_request_timeout_poll_and_blob_use_remaining_deadline(self):
        clock = [100.0]
        responses = [Response(status=202, headers={"Location": POLL}),
                     Response(completed()), Response(RAW)]
        def open_request(*unused, **kwargs):
            index = 3 - len(responses)
            clock[0] += (20, 60, 0)[index]
            return responses.pop(0)
        def sleep(seconds):
            clock[0] += seconds
        with patch("cost_api.time.monotonic", side_effect=lambda: clock[0]), patch(
                "cost_api.time.sleep", side_effect=sleep), patch(
                "cost_api.cli_json", side_effect=[
                    {"id": SUB, "tenantId": TENANT, "state": "Enabled"},
                    {"subscription": SUB, "tenant": TENANT, "accessToken": "ARM_SECRET",
                     "expires_on": (dt.datetime.now(dt.timezone.utc) +
                                    dt.timedelta(hours=1)).timestamp()}]), patch(
                "cost_api.urllib.request.build_opener") as build_opener, patch(
                "sys.stdout", new_callable=io.StringIO):
            opener = build_opener.return_value
            opener.open.side_effect = open_request
            self.assertEqual(api.main(self.command(extra=[
                "--request-timeout-seconds", "120", "--max-seconds", "150"])), 0)
        self.assertEqual([call.kwargs["timeout"] for call in opener.open.call_args_list],
                         [120, 100, 40])
        self.assertEqual(clock[0], 210)
        self.output.unlink()
        self.csv.unlink()
        code, summary, opener, _, sleep = self.run_cli(
            [Response(status=202, headers={"Location": POLL})], self.command(extra=[
                "--request-timeout-seconds", "120", "--max-seconds", "30"]))
        self.assertEqual((code, summary["reason"], opener.open.call_count),
                         (3, "pending_deadline", 1))
        self.assertLessEqual(opener.open.call_args.kwargs["timeout"], 30)
        sleep.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows dispatch contract")
    def test_wsl_request_timeout_serialized_for_all_collection_commands(self):
        for command in ("query", "details", "cost-details"):
            for extra in ([], ["--request-timeout-seconds", "120"],
                          ["--request-timeout-seconds=120"]):
                with self.subTest(command=command, extra=extra), patch(
                        "cost_api.run_bounded", return_value=subprocess.CompletedProcess(
                            [], 0, b'{"state":"COMPLETE"}', b"")) as runner, patch(
                        "cost_api.cli_json") as cli, patch(
                        "cost_api.urllib.request.build_opener") as opener, patch(
                        "sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(api.main(self.command(command, [
                        "--transport", "wsl", "--max-seconds", "300"] + extra)), 0)
                    forwarded, timeout = runner.call_args.args
                    self.assertEqual(forwarded[forwarded.index("--transport") + 1], "native")
                    self.assertEqual(timeout, 340)
                    if extra:
                        self.assertEqual(forwarded[
                            forwarded.index("--request-timeout-seconds") + 1], "120")
                    else:
                        self.assertNotIn("--request-timeout-seconds", forwarded)
                    cli.assert_not_called()
                    opener.assert_not_called()

    def test_unrelated_values_discarded_before_persistence(self):
        foreign = RAW.splitlines()[0] + b"\n" + (
            RID + "unowned," + RG + ",10/15/2026,PRIVATE,PRIVATE,PRIVATE,PRIVATE,"
            "PRIVATE,Bandwidth,PRIVATE\n").encode() + RAW.splitlines()[1] + b"\n"
        manifest = completed([{"blobLink": BLOB, "byteCount": len(foreign)}])
        code, summary, _, _, _ = self.run_cli([Response(manifest), Response(foreign)])
        self.assertEqual((code, summary["received"], summary["discarded"]), (0, 2, 1))
        self.assertNotIn("PRIVATE", self.output.read_text() + self.csv.read_text())

    def test_pending_poll_limit_is_incomplete_no_csv(self):
        code, summary, opener, _, _ = self.run_cli([
            Response(status=202, headers={"Location": POLL}),
            Response(status=202)], self.command(extra=["--max-polls", "1"]))
        self.assertEqual((code, summary["state"], summary["reason"]), (3, "INCOMPLETE", "poll_limit"))
        self.assertEqual(opener.open.call_count, 2)
        self.assertFalse(self.csv.exists())

    def test_pending_deadline_no_poll_and_429_403_stop_no_empty_success(self):
        code, summary, opener, _, sleep = self.run_cli([
            Response(status=202, headers={"Location": POLL, "Retry-After": "600"})])
        self.assertEqual((code, summary["reason"], opener.open.call_count), (3, "pending_deadline", 1))
        sleep.assert_not_called()
        self.output.unlink()
        for status in (429, 403):
            code, summary, opener, _, _ = self.run_cli([
                urllib.error.HTTPError(POLL, status, "SECRET", {"Retry-After": "0"}, None)])
            self.assertEqual(code, 3)
            self.assertEqual(summary["httpStatus"], status)
            self.assertEqual(opener.open.call_count, 1)
            self.assertFalse(self.csv.exists())
            self.output.unlink()

    def test_report_url_scope_operation_version_and_blob_safety(self):
        transport = api.Transport(SUB, TENANT)
        for url in (POLL.replace(SUB, TENANT), POLL.replace(api.REPORT_VERSION, "2024-01-01"),
                    POLL.replace("costDetailsOperationStatus/", "query/"),
                    POLL.replace("management.azure.com", "evil.example"),
                    POLL + "&extra=1", POLL + "#fragment"):
            with self.assertRaises(api.Failure):
                transport.validate_report(url)
        for url in (BLOB.replace(".blob.core.windows.net", ".evil.example"),
                    BLOB.replace("https:", "http:"), BLOB.replace("reports/", "reports/../"),
                    BLOB.replace("windows.net", "windows.net:443"), BLOB + "#fragment",
                    BLOB.replace("synthetic.", "u:p@synthetic.")):
            with self.assertRaises(api.Failure):
                api.validate_blob(url)
        code, summary, opener, _, _ = self.run_cli([
            Response(status=202, headers={"Location": POLL.replace(SUB, TENANT)})])
        self.assertEqual((code, summary["reason"], opener.open.call_count), (3, "unsafe_report_url", 1))

    def test_changed_operation_location_rejected(self):
        code, summary, opener, _, _ = self.run_cli([
            Response(status=202, headers={"Location": POLL}),
            Response(status=202, headers={"Location": POLL.replace("Status", "Results")})])
        self.assertEqual((code, summary["reason"], opener.open.call_count),
                         (3, "operation_location_changed", 2))

    def test_manifest_empty_duplicate_format_and_failed_status(self):
        cases = []
        empty = completed()
        empty["manifest"].update(blobs=[], blobCount=0)
        cases.append(empty)
        duplicate = completed([{"blobLink": BLOB, "byteCount": len(RAW)},
                               {"blobLink": BLOB + "different", "byteCount": len(RAW)}])
        cases.append(duplicate)
        wrong = completed()
        wrong["manifest"]["dataFormat"] = "Json"
        cases.append(wrong)
        cases.append({"status": "Failed", "error": {"message": "SECRET"}})
        for value in cases:
            code, summary, opener, _, _ = self.run_cli([Response(value)])
            self.assertEqual((code, summary["state"], opener.open.call_count), (3, "INCOMPLETE", 1))
            self.assertFalse(self.csv.exists())
            self.assertNotIn("SECRET", self.output.read_text())
            self.output.unlink()

    def test_invalid_csv_byte_mismatch_and_row_budget_fail_closed(self):
        for raw, extra in ((b"ResourceId,Date,Quantity\n", []),
                           (RAW, ["--max-rows", "1"])):
            content = raw if not extra else raw + raw.splitlines()[1] + b"\n"
            value = completed([{"blobLink": BLOB, "byteCount": len(content)}])
            code, summary, _, _, _ = self.run_cli(
                [Response(value), Response(content)], self.command(extra=extra))
            self.assertEqual((code, summary["state"]), (3, "INCOMPLETE"))
            self.assertFalse(self.csv.exists())
            self.output.unlink()
        code, summary, _, _, _ = self.run_cli([Response(completed()), Response(RAW + b"\n")])
        self.assertEqual((code, summary["reason"]), (3, "report_byte_count_mismatch"))

    def test_complete_empty_header_only_csv_is_not_billing_zero(self):
        raw = RAW.splitlines()[0] + b"\n"
        code, summary, _, _, _ = self.run_cli([
            Response(completed([{"blobLink": BLOB, "byteCount": len(raw)}])), Response(raw)])
        self.assertEqual((code, summary["retained"]), (0, 0))
        self.assertFalse(summary["ingestionFinal"])
        self.assertEqual(len(self.csv.read_text().splitlines()), 1)

    def test_query_resourceid_meter_reordered_columns_unknown_owned_incomplete(self):
        query_args = args("query")
        query_args.start, query_args.end = "2026-10-15", "2026-10-16"
        query_args.group_by = ["ResourceId", "Meter"]
        query_args.meter_category = "Bandwidth"
        names = ["Meter", "ResourceId", "UsageDate", "Currency", "PreTaxCost"]
        page = {"properties": {"columns": [{"name": n} for n in names],
                               "rows": [["Transfer", RID, 20261016, "USD", "0.01"],
                                        ["PRIVATE", RID + "unknown", 20261016, "USD", "PRIVATE"],
                                        ["PRIVATE", RID.replace(SUB, TENANT), 20261016, "USD", "PRIVATE"]]}}
        transport = api.Transport(SUB, TENANT)
        transport.request = Mock(return_value=page)
        result = api.collect(transport, query_args, {RID.lower()})
        self.assertEqual((result["state"], result["discarded"], result["unattributedLabRows"]),
                         ("INCOMPLETE", 2, 1))
        self.assertEqual(result["rows"][0]["ResourceGroup"], RG)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(transport.request.call_args.args[2]["dataset"]["grouping"],
                         [{"type": "Dimension", "name": "ResourceId"},
                          {"type": "Dimension", "name": "Meter"}])
        code, summary, _, _, _ = self.run_cli([Response(page)], self.command(
            "query", ["--group-by", "ResourceId", "Meter", "--meter-category", "Bandwidth"]))
        self.assertEqual((code, summary["state"]), (3, "INCOMPLETE"))

    def test_inventory_both_formats_scope_and_duplicates(self):
        for value in ({"resourceIds": [RID]}, {"resources": [{"id": RID}]}):
            self.inventory.write_text(json.dumps(value))
            self.assertEqual(api.load_inventory(str(self.inventory), SUB, RG), {RID.lower()})
        for values in ([RID, RID.upper()], [RID.replace(SUB, TENANT)],
                       [RID.replace(RG, "foreign")], [RID + "/../a"]):
            self.inventory.write_text(json.dumps({"resourceIds": values}))
            with self.assertRaises(api.Failure):
                api.load_inventory(str(self.inventory), SUB, RG)

    def test_public_outputs_exclusive_atomic_and_preexisting_preserved(self):
        self.csv.write_text("EXISTING")
        code, _, opener, cli, _ = self.run_cli([])
        self.assertEqual(code, 2)
        self.assertEqual(self.csv.read_text(), "EXISTING")
        self.assertFalse(self.output.exists())
        opener.open.assert_not_called()
        cli.assert_not_called()
        self.csv.unlink()
        real_link = os.link
        count = [0]
        def fail_second(source, target):
            count[0] += 1
            if count[0] == 2:
                raise OSError("injected")
            real_link(source, target)
        with patch("cost_api.os.link", side_effect=fail_second), self.assertRaises(OSError):
            api.write_outputs({"rows": []}, self.output, self.csv)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.csv.exists())
        self.assertFalse(list(self.private.glob("*.part")))

    def test_stop_and_other_billing_owner_block_default_no_http(self):
        runtime = self.root / "deploy" / ".runtime-control"
        runtime.mkdir(parents=True)
        (runtime / "STOP").write_text("stop")
        code, _, opener, _, _ = self.run_cli([])
        self.assertEqual(code, 2)
        opener.open.assert_not_called()
        (runtime / "STOP").unlink()
        (runtime / "api-lease.json").write_text(json.dumps({
            "state": "active", "expiresAtUtc": (
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()}))
        code, summary, opener, _, _ = self.run_cli([])
        self.assertEqual((code, summary["code"]), (2, "billing_lease_already_active"))
        opener.open.assert_not_called()

    def test_explicit_lease_attaches_without_overwriting(self):
        runtime = self.root / "deploy" / ".runtime-control"
        runtime.mkdir(parents=True)
        path = runtime / "api-lease.json"
        original = json.dumps({"state": "active", "maxToolCalls": 20, "maxMutations": 0,
                               "expiresAtUtc": (dt.datetime.now(dt.timezone.utc) +
                                                dt.timedelta(hours=1)).isoformat()})
        path.write_text(original)
        code, _, _, _, _ = self.run_cli([Response(completed()), Response(RAW)],
                                       self.command(extra=["--lease", str(path)]))
        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(), original)

    def test_explicit_lease_lower_http_and_timeout_budgets_win(self):
        runtime = self.root / "deploy" / ".runtime-control"
        runtime.mkdir(parents=True)
        path = runtime / "api-lease.json"
        path.write_text(json.dumps({
            "state": "active", "maxToolCalls": 20, "maxMutations": 0,
            "maxHttpRequests": 1, "commandTimeoutSeconds": 10,
            "expiresAtUtc": (dt.datetime.now(dt.timezone.utc) +
                             dt.timedelta(hours=1)).isoformat()}))
        code, summary, opener, _, _ = self.run_cli(
            [Response(completed())], self.command(extra=[
                "--lease", str(path), "--request-timeout-seconds", "120"]))
        self.assertEqual((code, summary["reason"], opener.open.call_count),
                         (3, "http_request_limit", 1))
        self.assertLessEqual(opener.open.call_args.kwargs["timeout"], 10)

    @unittest.skipUnless(os.name == "nt", "Windows dispatch contract")
    def test_wsl_report_deadline_paths_and_args_forwarded(self):
        command = self.command(extra=["--transport", "wsl", "--max-seconds", "300",
                                      "--max-http-requests", "6"])
        result = subprocess.CompletedProcess([], 0, b'{"state":"COMPLETE"}', b"SECRET")
        with patch("cost_api.run_bounded", return_value=result) as runner, patch(
                "sys.stdout", new_callable=io.StringIO):
            self.assertEqual(api.main(command), 0)
        actual, timeout = runner.call_args.args
        self.assertIn("330s", actual)
        self.assertEqual(timeout, 340)
        self.assertEqual(actual[actual.index("--transport") + 1], "native")
        for flag in ("--context", "--inventory", "--csv-output", "--output"):
            self.assertTrue(actual[actual.index(flag) + 1].startswith("/mnt/"))

    def test_retry_uses_longest_header_explicit_zero_and_http_budget(self):
        self.assertEqual(api.retry_seconds({"Retry-After": "1",
            "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "60"}), 60)
        transport = api.Transport(SUB, TENANT)
        transport.authorize = lambda: "SECRET"
        transport.max_retries = 0
        transport.opener.open = Mock(side_effect=urllib.error.HTTPError(
            POLL, 429, "SECRET", {"Retry-After": "0"}, None))
        with self.assertRaisesRegex(api.Failure, "rate_limited"):
            transport.request("GET", POLL, endpoint="report-poll")
        self.assertEqual(transport.http_requests, 1)
        transport = api.Transport(SUB, TENANT)
        transport.authorize = lambda: "SECRET"
        endpoint = "/providers/Microsoft.CostManagement/query"
        url = api.ARM + transport.scope + endpoint + "?api-version=" + api.QUERY_VERSION
        transport.opener.open = Mock(side_effect=[
            urllib.error.HTTPError(url, 429, "SECRET", {"Retry-After": "1"}, None),
            Response({})])
        with patch("cost_api.time.sleep") as sleep:
            self.assertEqual(transport.request("POST", url, {}, endpoint), {})
        self.assertEqual(transport.http_requests, 2)
        sleep.assert_called_once_with(1)
        code, summary, opener, _, _ = self.run_cli(
            [Response(completed())], self.command(extra=["--max-http-requests", "1"]))
        self.assertEqual((code, summary["reason"], opener.open.call_count),
                         (3, "http_request_limit", 1))

    def test_query_429_persists_safe_metadata_preserves_error_exit_and_clienttype(self):
        headers = {"Retry-After": "60", "x-ms-request-id": SUB,
                   "Date": "Sun, 18 Oct 2026 00:00:00 GMT",
                   "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "120",
                   "Location": POLL + "&t=OPAQUE&c=SECRET&s=TOKEN&h=SECRET",
                   "Authorization": "Bearer SECRET", "Set-Cookie": "TOKEN"}
        code, summary, opener, _, sleep = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", headers,
                                   io.BytesIO(b'{"error":{"code":"TooManyRequests",'
                                              b'"message":"SECRET"}}'))],
            self.command("query"))
        self.assertEqual((code, summary["state"], summary["code"], summary["httpStatus"]),
                         (2, "ERROR", "rate_limited", 429))
        self.assertEqual(summary["azureCode"], "TooManyRequests")
        self.assertIsNone(summary["errorCategory"])
        metadata = summary["responseMetadata"]
        self.assertEqual((metadata["retrySource"], metadata["retryAfterSeconds"]), ("known", 120))
        self.assertEqual(dt.datetime.fromisoformat(metadata["suggestedRetryAtUtc"]) -
                         dt.datetime.fromisoformat(metadata["receivedAtUtc"]), dt.timedelta(seconds=120))
        data = json.loads(self.output.read_text())
        self.assertEqual((data["state"], data["reason"], data["pages"], data["rows"]),
                         ("INCOMPLETE", "rate_limited", 0, []))
        self.assertEqual(data["responseMetadata"], metadata)
        self.assertEqual(data["http"], [{"status": 429, "responseMetadata": metadata}])
        self.assertEqual((data["httpRequests"], data["httpRequestCounts"]), (1, {"query": 1}))
        self.assertEqual(opener.open.call_args.args[0].get_header("Clienttype"),
                         api.QUERY_CLIENT_TYPE)
        sleep.assert_not_called()
        for secret in ("SECRET", "TOKEN", "OPAQUE", "Location", "sig=", "ARM_SECRET"):
            self.assertNotIn(secret, self.output.read_text() + json.dumps(summary))

    def test_query_unknown_retry_exposes_no_invented_cooldown_or_retry(self):
        for headers in (None, {}, {"Retry-After": "invalid"},
                        {"x-ms-ratelimit-microsoft.costmanagement-qpu-consumed": "60"}):
            with self.subTest(headers=headers):
                code, summary, opener, _, sleep = self.run_cli([
                    urllib.error.HTTPError(POLL, 429, "SECRET", headers, None)],
                    self.command("query"))
                self.assertEqual((code, summary["code"], opener.open.call_count),
                                 (2, "rate_limited", 1))
                metadata = summary["responseMetadata"]
                self.assertEqual(metadata["retrySource"], "unknown")
                self.assertIsNone(metadata["retryAfterSeconds"])
                self.assertIsNone(metadata["suggestedRetryAtUtc"])
                self.assertEqual(json.loads(self.output.read_text())["responseMetadata"], metadata)
                sleep.assert_not_called()
                self.output.unlink()

    def test_query_bad_or_past_http_date_cannot_retry_into_complete(self):
        now = dt.datetime(2026, 10, 18, 0, 20, tzinfo=dt.timezone.utc)

        class FixedDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        url = api.ARM + f"/subscriptions/{SUB}" + api.QUERY_ENDPOINT + (
            "?api-version=" + api.QUERY_VERSION)
        for value in ("Sun, 18 Oct 2026 00:21:00 GMTjunk",
                      "Sun, 18 Oct 2026 00:21:00 GMT junk",
                      "Sun, 18 Oct 2026 00:00:00 GMT Sun, 18 Oct 2026 01:00:00 GMT",
                      "Sun, 18 Oct 2026 00:00:00 GMT"):
            for mixed in (False, True):
                with self.subTest(value=value, mixed=mixed):
                    headers = {"Retry-After": value}
                    if mixed:
                        headers.update({
                            "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "120",
                            "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "90",
                            "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "NaN"})
                    with patch("cost_api.dt.datetime", FixedDatetime):
                        code, summary, opener, _, sleep = self.run_cli([
                            urllib.error.HTTPError(url, 429, "SECRET", headers, None),
                            Response({"properties": {"columns": [], "rows": []}})],
                            self.command("query"))
                    self.assertEqual((code, summary["state"], summary["code"],
                                      summary["httpStatus"], opener.open.call_count),
                                     (2, "ERROR", "rate_limited", 429, 1))
                    metadata = summary["responseMetadata"]
                    self.assertEqual(metadata["retrySource"], "known" if mixed else "unknown")
                    self.assertEqual(metadata["retryAfterSeconds"], 120 if mixed else None)
                    self.assertEqual(metadata["suggestedRetryAtUtc"],
                                     "2026-10-18T00:22:00+00:00" if mixed else None)
                    self.assertNotIn("retry-after", metadata["safeHeaders"])
                    data = json.loads(self.output.read_text())
                    self.assertEqual((data["state"], data["reason"], data["rows"]),
                                     ("INCOMPLETE", "rate_limited", []))
                    self.assertEqual((data["httpRequests"], data["httpRequestCounts"]),
                                     (1, {"query": 1}))
                    self.assertEqual(data["http"], [{"status": 429, "responseMetadata": metadata}])
                    request = opener.open.call_args.args[0]
                    self.assertEqual(request.full_url, url)
                    self.assertEqual(request.get_header("Clienttype"), api.QUERY_CLIENT_TYPE)
                    sleep.assert_not_called()
                    self.assertFalse(self.csv.exists())
                    self.output.unlink()

    def test_rfc850_long_cooldown_cannot_retry_into_complete(self):
        now = dt.datetime(2026, 10, 18, 0, 20, tzinfo=dt.timezone.utc)
        target = dt.datetime(2069, 10, 18, 0, 20, tzinfo=dt.timezone.utc)

        class FixedDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        url = api.ARM + f"/subscriptions/{SUB}" + api.QUERY_ENDPOINT + (
            "?api-version=" + api.QUERY_VERSION)
        for mixed in (False, True):
            headers = {"Retry-After": "Friday, 18-Oct-69 00:20:00 GMT",
                       "Location": BLOB, "x-debug": "SECRET"}
            if mixed:
                headers["x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after"] = "0"
            with self.subTest(mixed=mixed), patch("cost_api.dt.datetime", FixedDatetime):
                code, summary, opener, _, sleep = self.run_cli([
                    urllib.error.HTTPError(url, 429, "SECRET", headers, None),
                    Response({"properties": {"columns": [], "rows": []}})],
                    self.command("query", ["--max-seconds", "1"]))
                self.assertEqual((code, summary["state"], summary["code"],
                                  summary["httpStatus"], opener.open.call_count),
                                 (2, "ERROR", "rate_limited", 429, 1))
                metadata = summary["responseMetadata"]
                self.assertEqual(metadata["retrySource"], "known")
                self.assertEqual(metadata["retryAfterSeconds"], (target - now).total_seconds())
                self.assertEqual(metadata["suggestedRetryAtUtc"], target.isoformat())
                data = json.loads(self.output.read_text())
                self.assertEqual((data["state"], data["reason"], data["rows"]),
                                 ("INCOMPLETE", "rate_limited", []))
                self.assertEqual((data["httpRequests"], data["httpRequestCounts"]),
                                 (1, {"query": 1}))
                self.assertEqual(data["http"], [{"status": 429, "responseMetadata": metadata}])
                self.assertEqual(opener.open.call_args.args[0].get_header("Clienttype"),
                                 api.QUERY_CLIENT_TYPE)
                sleep.assert_not_called()
                for secret in ("SECRET", "sig=", "Location", "ARM_SECRET"):
                    self.assertNotIn(secret, self.output.read_text() + json.dumps(summary))
                self.output.unlink()

    def test_rfc850_long_cooldown_exceeds_remaining_time_without_budget_extension(self):
        now = dt.datetime(2026, 10, 18, 0, 20, tzinfo=dt.timezone.utc)

        class FixedDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        transport = api.Transport(SUB, TENANT, seconds=75)
        deadline = transport.deadline
        transport.authorize = Mock(return_value="ARM_SECRET")
        transport.remaining = Mock(return_value=75)
        transport.retry_delay_limit = float("inf")
        url = api.ARM + transport.scope + api.QUERY_ENDPOINT + "?api-version=" + api.QUERY_VERSION
        transport.opener.open = Mock(side_effect=[
            urllib.error.HTTPError(url, 429, "SECRET", {
                "Retry-After": "Friday, 18-Oct-69 00:20:00 GMT",
                "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "0"}, None),
            Response({})])
        with patch("cost_api.dt.datetime", FixedDatetime), patch("cost_api.time.sleep") as sleep:
            with self.assertRaisesRegex(api.Failure, "rate_limited") as caught:
                transport.request("POST", url, {}, api.QUERY_ENDPOINT)
        self.assertGreater(caught.exception.response_metadata["retryAfterSeconds"], 75)
        self.assertEqual(transport.deadline, deadline)
        self.assertEqual((transport.http_requests, transport.opener.open.call_count), (1, 1))
        self.assertEqual(transport.http_request_counts, {"query": 1})
        self.assertGreaterEqual(transport.remaining.call_count, 3)
        sleep.assert_not_called()

    def test_429_body_read_failure_cannot_drop_already_received_headers(self):
        body = Mock()
        body.read.side_effect = TimeoutError("SECRET")
        code, summary, opener, _, sleep = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "60"}, body)],
            self.command("query"))
        self.assertEqual((code, summary["code"], opener.open.call_count), (2, "rate_limited", 1))
        self.assertEqual(summary["responseMetadata"]["retryAfterSeconds"], 60)
        self.assertIsNone(summary["azureCode"])
        self.assertEqual(json.loads(self.output.read_text())["http"][-1]["status"], 429)
        self.assertNotIn("SECRET", self.output.read_text() + json.dumps(summary))
        sleep.assert_not_called()

    def test_query_retried_429_and_exhausted_budget_keep_history_and_true_counts(self):
        for max_requests, responses, reason, count in (
                (1, [urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None)],
                 "http_request_limit", 1),
                (2, [urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None),
                     urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "60"}, None)],
                 "rate_limited", 2),
                (2, [urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None),
                     TimeoutError("SECRET")], "http_timeout", 2)):
            with self.subTest(reason=reason):
                code, summary, opener, _, sleep = self.run_cli(responses, self.command(
                    "query", ["--max-http-requests", str(max_requests)]))
                self.assertEqual((code, summary["code"], opener.open.call_count), (2, reason, count))
                data = json.loads(self.output.read_text())
                self.assertEqual((data["httpRequests"], data["httpRequestCounts"]),
                                 (count, {"query": count}))
                self.assertEqual(data["http"][0]["responseMetadata"]["retryAfterSeconds"], 0)
                self.assertEqual(data["http"][0]["responseMetadata"]["retrySource"], "known")
                self.assertTrue(all(call.args[0].get_header("Clienttype") == api.QUERY_CLIENT_TYPE
                                    for call in opener.open.call_args_list))
                sleep.assert_called_once_with(0)
                self.output.unlink()

    def test_query_success_after_retry_retains_prior429_not_a_usage_counter(self):
        code, summary, opener, _, _ = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None),
            Response({"properties": {"columns": [], "rows": []}})], self.command("query"))
        self.assertEqual((code, summary["state"], summary["httpRequests"]), (0, "COMPLETE", 2))
        data = json.loads(self.output.read_text())
        self.assertEqual([entry["status"] for entry in data["http"]], [429, 200])
        self.assertEqual(data["httpRequestCounts"], {"query": 2})
        self.assertEqual(data["received"], 0)
        self.assertEqual(opener.open.call_count, 2)

    def test_429_metadata_consistent_generation_poll_download_no_clienttype(self):
        for operation, prefix in (
                ("generation", []),
                ("poll", [Response(status=202, headers={"Location": POLL})]),
                ("download", [Response(completed())])):
            with self.subTest(operation=operation):
                headers = {"Retry-After": "60", "x-ms-request-id": SUB, "Location": BLOB,
                           "x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after": "90"}
                code, summary, opener, _, _ = self.run_cli(prefix + [
                    urllib.error.HTTPError(POLL, 429, "SECRET", headers, None)])
                self.assertEqual((code, summary["state"], summary["httpStatus"]), (3, "INCOMPLETE", 429))
                self.assertEqual(summary["responseMetadata"]["retryAfterSeconds"], 90)
                data = json.loads(self.output.read_text())
                self.assertEqual(data["http"][-1]["responseMetadata"], summary["responseMetadata"])
                self.assertEqual(data["httpRequestCounts"][operation], 1)
                self.assertEqual(data["httpRequests"], opener.open.call_count)
                requests = [call.args[0] for call in opener.open.call_args_list]
                self.assertTrue(all(not request.has_header("Clienttype") for request in requests))
                if operation == "download":
                    self.assertEqual(requests[-1].headers, {})
                self.assertFalse(self.csv.exists())
                for secret in ("SECRET", "sig=", BLOB, POLL):
                    self.assertNotIn(secret, self.output.read_text() + json.dumps(summary))
                self.output.unlink()

    def test_report_poll_retries_and_download_requests_count_actual_attempts(self):
        code, summary, opener, _, sleep = self.run_cli([
            Response(status=202, headers={"Location": POLL}),
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None),
            Response(completed()), Response(RAW)], self.command(extra=["--max-retries", "1"]))
        self.assertEqual((code, summary["httpRequests"], opener.open.call_count), (0, 4, 4))
        self.assertEqual(summary["httpRequestCounts"], {"generation": 1, "poll": 2, "download": 1})
        data = json.loads(self.output.read_text())
        self.assertEqual((data["polls"], data["blobsDownloaded"]), (1, 1))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [30, 0])

    def test_generation_never_retries_even_with_explicit_retry_budget(self):
        code, summary, opener, _, sleep = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "0"}, None)],
            self.command(extra=["--max-retries", "3"]))
        self.assertEqual((code, summary["httpRequests"], opener.open.call_count), (3, 1, 1))
        sleep.assert_not_called()

    def test_consumption_requests_do_not_receive_query_clienttype(self):
        code, summary, opener, _, _ = self.run_cli([Response({"value": []})], self.command("details"))
        self.assertEqual((code, summary["httpRequestCounts"]), (0, {"consumption": 1}))
        self.assertFalse(opener.open.call_args.args[0].has_header("Clienttype"))

    def test_query_continuations_and_probe_only_tag_query_calls(self):
        continuation = (api.ARM + f"/subscriptions/{SUB}" + api.QUERY_ENDPOINT +
                        "?api-version=" + api.QUERY_VERSION + "&$skiptoken=SECRET")
        code, summary, opener, _, _ = self.run_cli([
            Response({"properties": {"columns": [], "rows": [], "nextLink": continuation}}),
            Response({"properties": {"columns": [], "rows": []}})], self.command("query"))
        self.assertEqual((code, summary["pages"], summary["httpRequests"]), (0, 2, 2))
        self.assertTrue(all(call.args[0].get_header("Clienttype") == api.QUERY_CLIENT_TYPE
                            for call in opener.open.call_args_list))
        self.assertNotIn("SECRET", self.output.read_text() + json.dumps(summary))
        self.output.unlink()
        command = ["probe", "--context", str(self.context), "--start", "2026-10-15",
                   "--end", "2026-10-16", "--resource-group", "rg-bandwidth-billing-preflight"]
        code, summary, opener, _, _ = self.run_cli([
            Response({"properties": {"columns": [], "rows": []}}), Response({"value": []})], command)
        self.assertEqual((code, summary["httpRequestCounts"]), (0, {"query": 1, "consumption": 1}))
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(requests[0].get_header("Clienttype"), api.QUERY_CLIENT_TYPE)
        self.assertFalse(requests[1].has_header("Clienttype"))

    def test_query_http_date_response_exposes_utc_retry_instant_without_sleeping(self):
        retry_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) + dt.timedelta(minutes=5)
        header = api.email.utils.format_datetime(retry_at, usegmt=True)
        code, summary, opener, _, sleep = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": header}, None)],
            self.command("query"))
        self.assertEqual((code, opener.open.call_count), (2, 1))
        metadata = summary["responseMetadata"]
        self.assertEqual(dt.datetime.fromisoformat(metadata["suggestedRetryAtUtc"]), retry_at)
        self.assertEqual(metadata["retrySource"], "known")
        sleep.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows dispatch contract")
    def test_wsl_query_uses_same_source_native_adapter_and_safe_metadata_summary(self):
        code, summary, _, _, _ = self.run_cli([
            urllib.error.HTTPError(POLL, 429, "SECRET", {"Retry-After": "120"}, None)],
            self.command("query", ["--max-retries", "0"]))
        result = subprocess.CompletedProcess([], code, json.dumps(summary).encode(), b"ARM_SECRET")
        command = self.command("query", ["--transport", "wsl", "--max-retries", "0",
                                         "--max-http-requests", "1"])
        with patch("cost_api.run_bounded", return_value=result) as runner, patch(
                "cost_api.cli_json") as cli, patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(api.main(command), code)
        self.assertEqual(json.loads(out.getvalue()), summary)
        self.assertNotIn("ARM_SECRET", out.getvalue())
        forwarded = runner.call_args.args[0]
        self.assertEqual(forwarded[forwarded.index("python3") + 1],
                         api.linux_path(str(api.Path(api.__file__).resolve())))
        self.assertEqual(forwarded[forwarded.index("--transport") + 1], "native")
        self.assertEqual(forwarded[forwarded.index("--max-retries") + 1], "0")
        self.assertEqual(forwarded[forwarded.index("--max-http-requests") + 1], "1")
        cli.assert_not_called()

    def test_preflight_retains_explicit_coordinator_lease(self):
        runtime = self.root / "deploy" / ".runtime-control"
        runtime.mkdir(parents=True)
        lease = runtime / "api-lease.json"
        lease.write_text(json.dumps({"state": "active", "expiresAtUtc": (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()}))
        (self.private / "context.private.json").write_text(self.context.read_text())
        with patch("sys.argv", ["preflight_compare.py", "--environment", "windows",
                                "--output", str(self.output)]), patch(
                "cost_api.main", return_value=0) as main:
            self.assertEqual(preflight_compare.main(), 0)
        forwarded = main.call_args.args[0]
        self.assertEqual(forwarded[forwarded.index("--lease") + 1], str(lease))

    def test_corrupt_compression_and_shared_decoded_cap_are_incomplete(self):
        for raw in (b"PKinvalidzip", b"\x1f\x8binvalidgzip"):
            value = completed([{"blobLink": BLOB, "byteCount": len(raw)}])
            code, summary, _, _, _ = self.run_cli([Response(value), Response(raw)])
            self.assertEqual((code, summary["state"]), (3, "INCOMPLETE"))
            self.assertFalse(self.csv.exists())
            self.output.unlink()
        with self.assertRaisesRegex(api.Failure, "report_decoded_byte_limit"):
            api.cost_details_csv_stream(io.BytesIO(RAW), SUB, {"lab": RG}, {RID.lower()},
                                        "2026-10-15", "2026-10-16", decoded_budget=[1])
        with self.assertRaisesRegex(api.Failure, "report_wire_byte_limit"):
            api.cost_details_csv_stream(io.BytesIO(RAW), SUB, {"lab": RG}, {RID.lower()},
                                        "2026-10-15", "2026-10-16", wire_budget=[1])

    def test_shared_row_cap_allows_header_only_last_partition_at_exact_limit(self):
        empty = RAW.splitlines()[0] + b"\n"
        blobs = [{"blobLink": BLOB, "byteCount": len(RAW)},
                 {"blobLink": BLOB.replace("one.csv", "empty.csv"), "byteCount": len(empty)}]
        code, summary, _, _, _ = self.run_cli([
            Response(completed(blobs)), Response(RAW), Response(empty)],
            self.command(extra=["--max-rows", "1"]))
        self.assertEqual((code, summary["retained"], summary["received"]), (0, 1, 1))

    def test_query_now_cap_unique_dimensions_and_columns_reordered_between_pages(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        body = api.query_body(RG, today, today, "Meter")
        self.assertLessEqual(dt.datetime.fromisoformat(body["timePeriod"]["to"]),
                             dt.datetime.now(dt.timezone.utc))
        with self.assertRaisesRegex(api.Failure, "invalid_query_grouping"):
            api.query_body(RG, today, today, "Meter", group_by=["Meter", "Meter"])
        transport = api.Transport(SUB, TENANT)
        endpoint = "/providers/Microsoft.CostManagement/query"
        url = api.ARM + transport.scope + endpoint + "?api-version=" + api.QUERY_VERSION
        first_names = ["ResourceGroup", "Meter", "UsageDate", "Currency", "PreTaxCost"]
        second_names = list(reversed(first_names))
        values = dict(ResourceGroup=RG, Meter="Transfer", UsageDate=20261014,
                      Currency="USD", PreTaxCost="0.01")
        transport.request = Mock(side_effect=[
            {"properties": {"columns": [{"name": name} for name in first_names],
                            "rows": [[values[name] for name in first_names]],
                            "nextLink": url + "&$skiptoken=one"}},
            {"properties": {"columns": [{"name": name} for name in second_names],
                            "rows": [[values[name] for name in second_names]]}}])
        result = api.collect(transport, args("query"), set())
        self.assertEqual((result["state"], len(result["rows"])), ("COMPLETE", 2))


if __name__ == "__main__":
    unittest.main()
