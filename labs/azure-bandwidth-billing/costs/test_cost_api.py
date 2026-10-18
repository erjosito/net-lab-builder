import argparse
import copy
import csv
import datetime as dt
from decimal import Decimal
from email.message import Message
import io
import json
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

import cost_api as api

SUB = "11111111-1111-1111-1111-111111111111"
TENANT = "22222222-2222-2222-2222-222222222222"
RG = "rg-test"
RID = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Compute/virtualMachines/a"
ENDPOINT = "/providers/Microsoft.Consumption/usageDetails"
URL = api.ARM + f"/subscriptions/{SUB}" + ENDPOINT + "?api-version=" + api.DETAIL_VERSION
REPORT_POLL = (api.ARM + f"/subscriptions/{SUB}/providers/Microsoft.CostManagement/"
               "costDetailsOperationResults/33333333-3333-3333-3333-333333333333")
# Synthetic values preserve the prior working Location's parameter names and lengths.
REPORT_POLL_PARAMS = {"api-version": api.REPORT_VERSION, "t": "638962560000000000",
                      "c": "A_" * 1296, "s": "B-" * 171, "h": "C_" * 21 + "D"}
REPORT_LOCATION = REPORT_POLL + "?" + urllib.parse.urlencode(REPORT_POLL_PARAMS)


def row(**changes):
    p = {"resourceId": RID, "resourceGroup": RG, "date": "2026-10-14T00:00:00Z",
         "quantity": Decimal("5.36870912"), "unitOfMeasure": "GB", "effectivePrice": "0.02",
         "costInBillingCurrency": "0.1073741824", "billingCurrency": "USD", "meterId": "meter"}
    p.update(changes)
    return {"id": "record-1", "kind": "modern", "properties": p}


def args(command="details", pages=3):
    return argparse.Namespace(command=command, resource_group=RG, start="2026-10-14",
                              end="2026-10-14", grouping="MeterId", max_pages=pages,
                              filter_variant="legacy-date", literal_keys=False)


class RetryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
        now = self.now

        class FixedDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        self.clock = patch("cost_api.dt.datetime", FixedDatetime)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_all_cost_management_scopes_choose_longest_not_usage_counters(self):
        headers = {"Retry-After": "12",
                   "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "60",
                   "X-MS-RATELIMIT-MICROSOFT.COSTMANAGEMENT-ENTITY-RETRY-AFTER": "30",
                   "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "90",
                   "x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after": "120",
                   "x-ms-ratelimit-microsoft.costmanagement-qpu-consumed": "999999",
                   "x-ms-ratelimit-remaining-tenant-reads": "999999"}
        metadata = api.response_metadata(headers)
        self.assertEqual(api.retry_seconds(headers), 120)
        self.assertEqual(metadata["retryAfterSeconds"], 120)
        self.assertEqual(metadata["retrySource"], "known")
        self.assertEqual(metadata["suggestedRetryAtUtc"], "2026-10-18T00:02:00+00:00")
        self.assertEqual(len(metadata["safeHeaders"]), 5)

    def test_http_date_and_delta_compare_at_one_receipt_instant(self):
        headers = {"Retry-After": "Sun, 18 Oct 2026 00:03:00 GMT",
                   "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "120"}
        metadata = api.response_metadata(headers)
        self.assertEqual(metadata["retryAfterSeconds"], 180)
        self.assertEqual(metadata["receivedAtUtc"], self.now.isoformat())
        self.assertEqual(metadata["suggestedRetryAtUtc"], "2026-10-18T00:03:00+00:00")
        headers["Retry-After"] = "Sat, 17 Oct 2026 23:59:00 GMT"
        self.assertEqual(api.retry_seconds(headers), 120)
        self.assertIsNone(api.retry_seconds({"Retry-After": headers["Retry-After"]}))

    def test_complete_http_date_formats_and_invalid_suffixes(self):
        for value in ("Sun, 18 Oct 2026 00:03:00 GMT",
                      "Sunday, 18-Oct-26 00:03:00 GMT", "Sun Oct 18 00:03:00 2026"):
            with self.subTest(value=value):
                self.assertEqual(api.retry_seconds({"Retry-After": value}), 180)
                for suffix in ("junk", " junk", " Sun, 18 Oct 2026 01:00:00 GMT", ", 600"):
                    metadata = api.response_metadata({"Retry-After": value + suffix})
                    self.assertEqual(metadata["retrySource"], "unknown")
                    self.assertIsNone(metadata["retryAfterSeconds"])
                    self.assertIsNone(metadata["suggestedRetryAtUtc"])
                    self.assertEqual(metadata["safeHeaders"], {})

    def test_past_date_is_unknown_but_mixed_valid_scopes_choose_longest(self):
        for value in ("Sat, 17 Oct 2026 23:59:00 GMT",
                      "Sun, 18 Oct 2026 00:03:00 GMT junk",
                      "Sun, 18 Oct 2026 00:00:00 GMT Sun, 18 Oct 2026 01:00:00 GMT"):
            with self.subTest(value=value):
                headers = {"Retry-After": value}
                metadata = api.response_metadata(headers)
                self.assertEqual(metadata["retrySource"], "unknown")
                self.assertIsNone(metadata["retryAfterSeconds"])
                self.assertIsNone(metadata["suggestedRetryAtUtc"])
                self.assertEqual(metadata["safeHeaders"], {})
                headers.update({
                    "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "120",
                    "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "90",
                    "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "-1"})
                metadata = api.response_metadata(headers)
                self.assertEqual(api.retry_seconds(headers), 120)
                self.assertEqual(metadata["retryAfterSeconds"], 120)
                self.assertEqual(metadata["retrySource"], "known")
                self.assertEqual(metadata["suggestedRetryAtUtc"], "2026-10-18T00:02:00+00:00")
                self.assertEqual(set(metadata["safeHeaders"]), {
                    "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after",
                    "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after"})

    def test_rfc850_years_68_and_69_use_http_rolling_window(self):
        for year in (2068, 2069):
            target = dt.datetime(year, 10, 18, 0, 3, tzinfo=dt.timezone.utc)
            for value in (target.strftime("%A, %d-%b-%y %H:%M:%S GMT"),
                          target.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                          target.strftime("%a %b %d %H:%M:%S %Y")):
                with self.subTest(value=value):
                    metadata = api.response_metadata({
                        "Retry-After": value,
                        "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "0"})
                    self.assertEqual(metadata["retrySource"], "known")
                    self.assertEqual(metadata["retryAfterSeconds"],
                                     (target - self.now).total_seconds())
                    self.assertEqual(metadata["suggestedRetryAtUtc"], target.isoformat())

    def test_rfc850_fifty_year_boundary_uses_complete_utc_instant(self):
        received = dt.datetime(2026, 10, 18, 13, 14, 15, tzinfo=dt.timezone.utc)
        boundary = received.replace(year=2076)
        for microsecond in (0, 500000):
            instant = received.replace(microsecond=microsecond)
            for seconds in (-1, 0, 1):
                target = boundary + dt.timedelta(seconds=seconds)
                value = target.strftime("%A, %d-%b-%y %H:%M:%S GMT")
                for offset in (0, 330, -420):
                    local = instant.astimezone(dt.timezone(dt.timedelta(minutes=offset)))
                    with self.subTest(seconds=seconds, offset=offset, microsecond=microsecond):
                        hints = api.retry_hints({"Retry-After": value}, local)
                        if seconds > 0:
                            self.assertEqual(hints, [])
                        else:
                            self.assertEqual(hints[0][2], (target - instant).total_seconds())

    def test_rfc850_century_rollover_and_utc_year_boundary(self):
        for instant, target in (
                ((1999, 12, 31, 23, 59, 59), (2000, 2, 29, 12, 0, 0)),
                ((2049, 12, 31, 23, 59, 59), (2099, 12, 31, 23, 59, 59)),
                ((2050, 1, 1, 0, 0, 0), (2100, 1, 1, 0, 0, 0)),
                ((2090, 10, 18, 12, 0, 0), (2110, 10, 18, 12, 0, 0)),
                ((2099, 12, 31, 23, 59, 59), (2100, 1, 1, 0, 0, 0))):
            received = dt.datetime(*instant, tzinfo=dt.timezone.utc)
            future = dt.datetime(*target, tzinfo=dt.timezone.utc)
            value = future.strftime("%A, %d-%b-%y %H:%M:%S GMT")
            for offset in (0, 330, -420):
                local = received.astimezone(dt.timezone(dt.timedelta(minutes=offset)))
                with self.subTest(instant=instant, target=target, offset=offset):
                    hints = api.retry_hints({"Retry-After": value}, local)
                    self.assertEqual(hints[0][2], (future - received).total_seconds())
        received = dt.datetime(2049, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        self.assertEqual(api.retry_hints(
            {"Retry-After": "Friday, 01-Jan-00 00:00:00 GMT"}, received), [])

    def test_rfc850_leap_day_boundary_and_invalid_resolved_century(self):
        received = dt.datetime(2024, 2, 29, 12, tzinfo=dt.timezone.utc)
        target = dt.datetime(2074, 2, 28, 12, tzinfo=dt.timezone.utc)
        hints = api.retry_hints(
            {"Retry-After": target.strftime("%A, %d-%b-%y %H:%M:%S GMT")}, received)
        self.assertEqual(hints[0][2], (target - received).total_seconds())
        for value, instant in (
                ("Thursday, 01-Mar-74 12:00:00 GMT", received),
                ("Monday, 29-Feb-00 12:00:00 GMT",
                 dt.datetime(2050, 3, 1, 12, tzinfo=dt.timezone.utc))):
            with self.subTest(value=value):
                self.assertEqual(api.retry_hints({"Retry-After": value}, instant), [])

    def test_http_date_naive_receipt_never_uses_machine_local_timezone(self):
        for value in ("Sun, 18 Oct 2026 00:03:00 GMT",
                      "Sunday, 18-Oct-26 00:03:00 GMT", "Sun Oct 18 00:03:00 2026"):
            self.assertEqual(api.retry_hints(
                {"Retry-After": value}, self.now.replace(tzinfo=None)), [])

    def test_invalid_missing_nonfinite_or_negative_unknown(self):
        values = (None, "", "SECRET", "-1", "nan", "inf", "1e309", "1e20",
                  "Sun, 18 Oct 2026 00:03:00", "0.5")
        for value in values:
            with self.subTest(value=value):
                metadata = api.response_metadata({"Retry-After": value})
                self.assertIsNone(api.retry_seconds({"Retry-After": value}))
                self.assertEqual(metadata["retrySource"], "unknown")
                self.assertIsNone(metadata["suggestedRetryAtUtc"])
                self.assertEqual(metadata["safeHeaders"], {})
        for headers in (None, {}, {"x-ms-retry-after-ms": "1000"},
                        {"x-ms-ratelimit-microsoft.costmanagement-qpu-consumed": "45"}):
            with self.subTest(headers=headers):
                metadata = api.response_metadata(headers)
                self.assertIsNone(metadata["retryAfterSeconds"])
                self.assertEqual(metadata["retrySource"], "unknown")

    def test_valid_zero_and_finite_shared_fraction_are_known(self):
        for headers, delay in (({"Retry-After": "0"}, 0), ({"Retry-After": " 60 "}, 60),
                               ({"x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after":
                                 "0.25"}, .25)):
            with self.subTest(headers=headers):
                metadata = api.response_metadata(headers)
                self.assertEqual(metadata["retryAfterSeconds"], delay)
                self.assertEqual(metadata["retrySource"], "known")
                self.assertEqual(dt.datetime.fromisoformat(metadata["suggestedRetryAtUtc"]),
                                 self.now + dt.timedelta(seconds=delay))

    def test_invalid_shared_hints_do_not_hide_other_valid_headers(self):
        for value in ("-1", "NaN", "Infinity", "SECRET", None):
            with self.subTest(value=value):
                headers = {"Retry-After": "5",
                           "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": value}
                self.assertEqual(api.retry_seconds(headers), 5)
                self.assertEqual(api.response_metadata(headers)["safeHeaders"], {"retry-after": "5"})

    def test_finite_unrepresentable_delay_cannot_shorten_known_cooldown(self):
        headers = {"Retry-After": "60",
                   "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "1e20"}
        metadata = api.response_metadata(headers)
        self.assertEqual(api.retry_seconds(headers), 1e20)
        self.assertEqual(metadata["retryAfterSeconds"], 1e20)
        self.assertEqual(metadata["retrySource"], "known")
        self.assertIsNone(metadata["suggestedRetryAtUtc"])
        headers = {"Retry-After": "100000000000000000000"}
        self.assertEqual(api.retry_seconds(headers), 1e20)

    def test_allowlist_excludes_opaque_urls_tokens_and_arbitrary_headers(self):
        headers = {"Retry-After": "60", "Date": "Sun, 18 Oct 2026 00:00:00 GMT",
                   "X-MS-Request-ID": SUB, "x-ms-correlation-request-id": TENANT,
                   "request-id": SUB, "x-ms-client-request-id": "SECRET",
                   "Location": REPORT_LOCATION, "Authorization": "Bearer TOKEN",
                   "Set-Cookie": "SECRET", "x-ms-token": "SECRET",
                   "t": "638962560000000000", "c": "OPAQUE", "s": "OPAQUE", "h": "OPAQUE",
                   "SAS": "sig=SECRET", "x-ms-unknown-retry-after": "600",
                   "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "sig=SECRET"}
        safe = api.response_metadata(headers)["safeHeaders"]
        self.assertEqual(set(safe), {"retry-after", "date", "x-ms-request-id",
                                     "x-ms-correlation-request-id", "request-id"})
        for secret in ("SECRET", "TOKEN", "OPAQUE", "638962560000000000", "sig=", "Location"):
            self.assertNotIn(secret, json.dumps(api.response_metadata(headers)))
        self.assertEqual(api.response_metadata({"x-ms-request-id": "TOKEN",
                                                "Date": "SECRET"})["safeHeaders"], {})

    def test_duplicate_retry_headers_keep_longest(self):
        headers = Message()
        headers["Retry-After"] = "60"
        headers["Retry-After"] = "10"
        metadata = api.response_metadata(headers)
        self.assertEqual(metadata["retryAfterSeconds"], 60)
        self.assertEqual(metadata["safeHeaders"], {"retry-after": "60"})


class CollectorTests(unittest.TestCase):
    def transport(self, pages):
        transport = api.Transport(SUB, TENANT)
        transport.request = unittest.mock.Mock(side_effect=pages)
        return transport

    def test_report_location_actual_signed_contract_and_arm_path_case(self):
        transport = api.Transport(SUB, TENANT)
        for location in (REPORT_LOCATION, REPORT_LOCATION.replace(
                "/providers/Microsoft.CostManagement/costDetailsOperationResults/",
                "/PROVIDERS/MICROSOFT.COSTMANAGEMENT/COSTDETAILSOPERATIONRESULTS/"),
                REPORT_POLL + "?api-version=" + api.REPORT_VERSION,
                REPORT_POLL.replace("costDetailsOperationResults", "costDetailsOperationStatus") +
                "?api-version=" + api.REPORT_VERSION):
            with self.subTest(location=location[:len(REPORT_POLL)]):
                self.assertEqual(transport.validate_report(location), location)

    def test_report_location_rejects_foreign_malformed_or_extra_contract(self):
        transport = api.Transport(SUB, TENANT)
        invalid = [
            REPORT_LOCATION.replace("https:", "http:"),
            REPORT_LOCATION.replace("management.azure.com", "other.management.azure.com"),
            REPORT_LOCATION.replace("management.azure.com", "management.azure.com.evil.test"),
            REPORT_LOCATION.replace("management.azure.com", "user@management.azure.com"),
            REPORT_LOCATION.replace("management.azure.com", "management.azure.com:443"),
            REPORT_LOCATION + "#fragment", REPORT_LOCATION + "#",
            REPORT_LOCATION.replace(SUB, TENANT),
            REPORT_LOCATION.replace("/providers/", "/resourceGroups/other/providers/"),
            REPORT_LOCATION.replace("costDetailsOperationResults", "query"),
            REPORT_LOCATION.replace("costDetailsOperationResults", "operations"),
            REPORT_LOCATION.replace("costDetailsOperationResults/", "costDetailsOperationResults/../"),
            REPORT_LOCATION.replace("costDetailsOperationResults/", "costDetailsOperationResults/%2e%2e/"),
            REPORT_LOCATION.replace("costDetailsOperationResults/", "costDetailsOperationResults/%252e%252e/"),
            REPORT_LOCATION.replace("33333333-3333-3333-3333-333333333333", "not-a-uuid"),
            REPORT_LOCATION.replace(api.REPORT_VERSION, "2022-05-01"),
            REPORT_LOCATION + "&api-version=" + api.REPORT_VERSION,
            REPORT_LOCATION + "&scope=" + SUB,
            REPORT_LOCATION + "&unknown=",
            REPORT_LOCATION + "&h=another",
            REPORT_LOCATION + "&malformed",
            REPORT_LOCATION.replace("costDetailsOperationResults", "costDetailsOperationStatus"),
        ]
        for bad_path in (
                "costDetailsOperationResults/not-a-uuid",
                "costDetailsOperationResults/33333333333333333333333333333333",
                "costDetailsOperationResults/%333333333-3333-3333-3333-333333333333",
                "costDetailsOperationResults/../33333333-3333-3333-3333-333333333333",
                "costDetailsOperationResults/33333333-3333-3333-3333-333333333333/extra",
                "query/33333333-3333-3333-3333-333333333333"):
            invalid.append(api.ARM + transport.scope + "/providers/Microsoft.CostManagement/" +
                           bad_path + "?api-version=" + api.REPORT_VERSION)
        for key, value in (("t", "1"), ("t", "a" * 18), ("c", "A" * 8193),
                           ("s", "A" * 1025), ("h", "A" * 44),
                           ("c", "../other"), ("s", "A+B"), ("h", "A/B")):
            params = dict(REPORT_POLL_PARAMS, **{key: value})
            invalid.append(REPORT_POLL + "?" + urllib.parse.urlencode(params))
        for key in ("t", "c", "s", "h"):
            for remove in (True, False):
                params = REPORT_POLL_PARAMS.copy()
                if remove:
                    del params[key]
                else:
                    params[key] = ""
                invalid.append(REPORT_POLL + "?" + urllib.parse.urlencode(params))
        for location in invalid:
            with self.subTest(location=location[:len(REPORT_POLL)], query_length=len(location)):
                with self.assertRaisesRegex(api.Failure, "unsafe_report_url"):
                    transport.validate_report(location)
        with self.assertRaisesRegex(api.Failure, "unsafe_report_url"):
            transport.validate_report(
                api.ARM + transport.scope + api.REPORT_ENDPOINT + "?" +
                urllib.parse.urlencode(REPORT_POLL_PARAMS), generation=True)

    def test_report_generation_signed_location_poll_download_no_blob_arm_auth(self):
        raw = ("ResourceId,Date,Quantity,MeterCategory,CostInBillingCurrency,BillingCurrency\n"
               f"{RID},2026-10-14,1,Bandwidth,0.02,USD\n").encode()
        blob = "https://testaccount.blob.core.windows.net/reports/test.csv?sig=synthetic"
        manifest = {"dataFormat": "Csv", "compressData": False, "blobCount": 1,
                    "byteCount": len(raw), "blobs": [{"blobLink": blob, "byteCount": len(raw)}]}

        def response(status, headers, body):
            stream = io.BytesIO(body)
            stream.status, stream.headers = status, headers
            return stream

        transport = api.Transport(SUB, TENANT, seconds=300)
        transport.authorize = unittest.mock.Mock(return_value="SYNTHETIC-ARM-TOKEN")
        transport.opener.open = unittest.mock.Mock(side_effect=[
            response(202, {"Location": REPORT_LOCATION, "Retry-After": "30"}, b"{}"),
            response(200, {}, json.dumps({"status": "Completed", "manifest": manifest}).encode()),
            response(200, {}, raw)])
        request_args = args("cost-details")
        request_args.max_polls, request_args.max_rows = 2, 100
        with patch("cost_api.time.sleep") as sleep:
            result = api.collect_report(transport, request_args, {RID.lower()})
        self.assertEqual(result["state"], "COMPLETE", result.get("reason"))
        self.assertTrue(result["extractionComplete"])
        self.assertFalse(result["ingestionFinal"])
        self.assertEqual((result["polls"], result["blobsDownloaded"], result["retained"]), (1, 1, 1))
        self.assertEqual(result["rows"][0]["quantity"], "1")
        sleep.assert_called_once_with(30)
        requests = [call.args[0] for call in transport.opener.open.call_args_list]
        self.assertEqual([request.full_url for request in requests[1:]], [REPORT_LOCATION, blob])
        self.assertEqual([request.method for request in requests], ["POST", "GET", "GET"])
        self.assertEqual(transport.authorize.call_count, 2)
        self.assertTrue(all(request.has_header("Authorization") for request in requests[:2]))
        self.assertFalse(requests[2].has_header("Authorization"))
        self.assertNotIn("SYNTHETIC-ARM-TOKEN", json.dumps(result))
        self.assertNotIn(REPORT_LOCATION, json.dumps(result))
        self.assertNotIn(blob, json.dumps(result))

    def test_ignored_filter_rejected_before_storage(self):
        values = [row(resourceGroup="foreign"), row(resourceId=RID + "unknown"),
                  row(date="2026-10-13"), row(resourceId=None, instanceName="ambiguous"),
                  row(resourceId=RID.replace(SUB, TENANT)), row()]
        result = api.collect(self.transport([{"value": values}]), args(), {RID.lower()})
        self.assertEqual((result["state"], result["discarded"], len(result["rows"])),
                         ("INCOMPLETE", 5, 1))
        self.assertNotIn("foreign", json.dumps(result, default=str))

    def test_modern_name_resolution_requires_known_rg_unique_inventory(self):
        value = row(resourceId=None, instanceName="a")
        self.assertEqual(api.identity(value, SUB, RG, {RID.lower()}), RID.lower())
        self.assertIsNone(api.identity(row(resourceId=None, instanceName="a", resourceGroup=None),
                                       SUB, RG, {RID.lower()}))
        self.assertIsNone(api.identity(value, SUB, RG, {RID.lower(),
                          RID.lower().replace("virtualmachines", "disks")}))

    def test_native_token_pinning_and_expected_tenant(self):
        transport = api.Transport(SUB, TENANT)
        with patch("cost_api.cli_json", side_effect=[
            {"id": SUB, "tenantId": TENANT, "state": "Enabled"},
            {"subscription": SUB, "tenant": TENANT, "accessToken": "SECRET"}]) as cli:
            self.assertEqual(transport.authorize(), "SECRET")
            self.assertNotIn("--tenant", cli.call_args_list[1].args[0])
            self.assertIn("--subscription", cli.call_args_list[1].args[0])
        with patch("cost_api.cli_json", return_value={
                "id": SUB, "tenantId": SUB, "state": "Enabled"}):
            with self.assertRaisesRegex(api.Failure, "context_mismatch"):
                transport.authorize()

    def test_legacy_and_modern_decimal_units(self):
        modern = api.normalize(row(), RID)
        legacy = row(date=None, usageStart="2026-10-14", usageEnd="2026-10-15",
                     quantity=None)
        legacy["kind"] = "legacy"
        legacy["properties"].pop("quantity")
        legacy["properties"].pop("costInBillingCurrency")
        legacy["properties"].pop("unitOfMeasure")
        legacy["properties"].pop("effectivePrice")
        legacy["properties"].update(usageQuantity="12.34567890123456789", pretaxCost="0",
                                    meterDetails={"unit": "1 GB", "meterName": "Transfer"})
        normalized = api.normalize(legacy, RID)
        self.assertEqual(modern["quantity"], "5.36870912")
        self.assertEqual(normalized["quantity"], "12.34567890123456789")
        self.assertEqual(normalized["unit"], "1 GB")
        self.assertIsNone(normalized["effectivePrice"])
        self.assertEqual(normalized["cost"], "0")

    def test_token_cache_expiry_guard_and_clock_rollback(self):
        account = {"id": SUB, "tenantId": TENANT, "state": "Enabled"}
        token = {"subscription": SUB, "tenant": TENANT, "accessToken": "SECRET",
                 "expires_on": "5000"}
        transport = api.Transport(SUB, TENANT)
        transport.guard = unittest.mock.Mock()
        with patch("cost_api.time.time", return_value=1000), patch(
                "cost_api.cli_json", side_effect=[account, token]) as cli:
            self.assertEqual(transport.authorize(), "SECRET")
            self.assertEqual(transport.authorize(), "SECRET")
            self.assertEqual(cli.call_count, 2)
            self.assertEqual(transport.guard.call_count, 2)
        for clock in (900, 4880):
            with patch("cost_api.time.time", return_value=clock), patch(
                    "cost_api.cli_json", return_value={
                        "id": SUB, "tenantId": SUB, "state": "Enabled"}):
                with self.assertRaisesRegex(api.Failure, "context_mismatch"):
                    transport.authorize()
        transport = api.Transport(SUB, TENANT)
        with patch("cost_api.time.time", return_value=1000), patch(
                "cost_api.cli_json", side_effect=[account, token]):
            transport.authorize()
        transport._token_deadline = 0
        with patch("cost_api.time.time", return_value=1000), patch(
                "cost_api.cli_json", return_value=account) as cli:
            with self.assertRaisesRegex(api.Failure, "token_context_mismatch"):
                transport.authorize()
            self.assertEqual(cli.call_count, 2)

    def test_token_without_epoch_or_near_expiry_not_cached(self):
        account = {"id": SUB, "tenantId": TENANT, "state": "Enabled"}
        for expiry in (None, "bad", "NaN", "Infinity", "1100"):
            transport = api.Transport(SUB, TENANT)
            token = {"subscription": SUB, "tenant": TENANT, "accessToken": "SECRET",
                     "expires_on": expiry}
            with patch("cost_api.time.time", return_value=1000), patch(
                    "cost_api.cli_json", side_effect=[account, token, account, token]) as cli:
                transport.authorize()
                transport.authorize()
                self.assertEqual(cli.call_count, 4)

    def test_cost_details_csv_header_case_decimal_and_inventory_filter(self):
        header = ("resourceId,date,quantity,unitOfMeasure,effectivePrice,"
                  "costInBillingCurrency,billingCurrencyCode,meterCategory,meterName\n")
        csv = (header + f"{RID}unknown,2026-10-15,PRIVATE,GB,PRIVATE,PRIVATE,USD,Bandwidth,Other\n"
               + f"{RID},2026-10-13,7,GB,0.02,0.14,USD,Bandwidth,Transfer\n"
               + f"{RID},2026-10-14,1.073741824,GB,0.02,0.02147483648,USD,Bandwidth,Transfer\n")
        result = api.cost_details_csv(csv.encode(), SUB, {"C": RG}, {RID.lower()},
                                      "2026-10-14", "2026-10-14")
        self.assertEqual((result["received"], result["discarded"]), (3, 2))
        value = result["rows"][0]
        self.assertEqual((value["quantity"], value["effectivePrice"], value["cost"]),
                         ("1.073741824", "0.02", "0.02147483648"))
        self.assertEqual(value["alias"], "C")
        self.assertNotIn("PRIVATE", json.dumps(result))
        legacy = (f"InstanceId,Date,Quantity,Cost,Currency,ServiceName\n"
                  f"{RID},10/14/2026,1,0,USD,Bandwidth\n").encode("utf-8-sig")
        value = api.cost_details_csv(legacy, SUB, {"A": RG}, {RID.lower()},
                                    "2026-10-14", "2026-10-14")["rows"][0]
        self.assertEqual(value["cost"], "0")
        self.assertIsNone(value["unit"])
        self.assertIsNone(value["effectivePrice"])

    def test_cost_details_csv_fail_closed_schema_dates_and_bounds(self):
        for raw, reason in [
                (b"Date,Quantity\n2026-10-14,1\n", "csv_required_columns_missing"),
                (b"ResourceId,resourceId,Date,Quantity\n", "csv_duplicate_columns"),
                (f"ResourceId,Date,Quantity\n{RID},bad,1\n".encode(), "csv_lab_date_invalid"),
                (f"ResourceId,Date,Quantity\n{RID},2026-10-14\n".encode(), "csv_row_shape"),
                (f"ResourceId,Date,Quantity,ResourceGroup\n{RID},2026-10-14,1,foreign\n".encode(),
                 "csv_resource_group_mismatch")]:
            with self.assertRaisesRegex(api.Failure, reason):
                api.cost_details_csv(raw, SUB, {"A": RG}, {RID.lower()},
                                     "2026-10-14", "2026-10-14")
        with self.assertRaisesRegex(api.Failure, "report_row_limit"):
            api.cost_details_csv(
                f"ResourceId,Date,Quantity\n{RID},2026-10-14,1\n{RID},2026-10-14,1\n".encode(),
                SUB, {"A": RG}, {RID.lower()}, "2026-10-14", "2026-10-14", max_rows=1)

    def test_adjacent_usage_days_retained_without_combining_or_receipt_inference(self):
        raw = ("ResourceId,Date,Quantity,MeterCategory,UsageStart,UsageEnd\n"
               f"{RID},2026-10-14,9,Bandwidth,,\n"
               f"{RID},10/15/2026,0,Bandwidth,,\n"
               f"{RID},2026-10-16,1.000000000000000001,Bandwidth,"
               "2026-10-15T23:00:00Z,2026-10-16T00:00:00Z\n"
               f"{RID},2026-10-17,8,Bandwidth,,\n").encode()
        result = api.cost_details_csv(raw, SUB, {"C": RG}, {RID.lower()},
                                      "2026-10-15", "2026-10-16")
        self.assertEqual([r["day"] for r in result["rows"]],
                         ["2026-10-15", "2026-10-16"])
        self.assertEqual([r["quantity"] for r in result["rows"]],
                         ["0", "1.000000000000000001"])
        self.assertEqual(result["discardCounts"]["date"], 2)
        self.assertEqual(result["ownedRowsByDate"]["2026-10-16"], 1)
        self.assertEqual(result["rows"][0]["dateOriginal"], "10/15/2026")
        self.assertEqual(result["rows"][1]["usageEnd"], "2026-10-16T00:00:00Z")
        self.assertEqual(result["rows"][1]["dateSemantics"],
                         "usage_or_purchase_date_not_receipt_date")
        strict = api.cost_details_csv(raw, SUB, {"C": RG}, {RID.lower()},
                                      "2026-10-15", "2026-10-15")
        self.assertEqual(strict["discardCounts"]["date"], 3)
        self.assertEqual(len(strict["rows"]), 1)

    def test_absent_adjacent_day_is_not_a_zero_quantity_record(self):
        raw = (f"ResourceId,Date,Quantity,MeterCategory\n"
               f"{RID},2026-10-15,0,Bandwidth\n").encode()
        result = api.cost_details_csv(raw, SUB, {"C": RG}, {RID.lower()},
                                      "2026-10-15", "2026-10-16")
        self.assertEqual(len(result["rows"]), 1)
        self.assertNotIn("2026-10-16", result["ownedRowsByDate"])
        self.assertIsNone(result["rows"][0]["usageStart"])

    def test_actual_mca_header_fixture_with_only_synthetic_values(self):
        headers = (
            "invoiceId previousInvoiceId billingAccountId billingAccountName billingProfileId "
            "billingProfileName invoiceSectionId invoiceSectionName resellerName resellerMpnId "
            "costCenter billingPeriodEndDate billingPeriodStartDate servicePeriodEndDate "
            "servicePeriodStartDate date serviceFamily productOrderId productOrderName "
            "consumedService meterId meterName meterCategory meterSubCategory meterRegion "
            "ProductId ProductName SubscriptionId subscriptionName publisherType publisherId "
            "publisherName resourceGroupName ResourceId resourceLocation location effectivePrice "
            "quantity unitOfMeasure chargeType billingCurrency pricingCurrency costInBillingCurrency "
            "costInPricingCurrency costInUsd paygCostInBillingCurrency paygCostInUsd "
            "exchangeRatePricingToBilling exchangeRateDate isAzureCreditEligible serviceInfo1 "
            "serviceInfo2 additionalInfo tags PayGPrice frequency term reservationId reservationName "
            "pricingModel unitPrice costAllocationRuleName benefitId benefitName provider").split()
        values = dict(ResourceId=RID.upper(), resourceGroupName=RG.upper(), date="10/15/2026",
                      quantity="0.000002", unitOfMeasure="1 GB", effectivePrice="0.02",
                      unitPrice="0.02", costInBillingCurrency="0.00000004",
                      billingCurrency="USD", meterCategory="Bandwidth", meterName="Synthetic")
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerow(values)
        captured = []
        result = api.cost_details_csv(output.getvalue().encode("utf-8-sig"), SUB, {"C": RG},
                                      {RID.lower()}, "2026-10-15", "2026-10-15",
                                      schema=captured.append)
        self.assertEqual(captured[0]["headers"], headers)
        self.assertEqual(result["schemaMapping"]["resourceGroup"], "resourcegroupname")
        value = result["rows"][0]
        self.assertEqual((value["quantity"], value["unit"], value["effectivePrice"]),
                         ("0.000002", "1 GB", "0.02"))
        self.assertEqual((value["costSource"], value["currencySource"]),
                         ("costinbillingcurrency", "billingcurrency"))

    def test_legacy_usage_aliases_and_bandwidth_service_exact_filter(self):
        raw = (" InstanceId , UsageDate , UsageQuantity ,PreTaxCost,Currency,ServiceName\n"
               f"{RID},10/15/2026,1.1234567890123456789,0,USD,Bandwidth\n"
               f"{RID},10/15/2026,PRIVATE,PRIVATE,USD,NotBandwidth\n").encode()
        result = api.cost_details_csv(raw, SUB, {"A": RG}, {RID.lower()},
                                      "2026-10-15", "2026-10-15")
        self.assertEqual(result["discardCounts"]["category"], 1)
        self.assertEqual(result["rows"][0]["quantity"], "1.1234567890123456789")
        self.assertEqual(result["rows"][0]["cost"], "0")
        self.assertIsNone(result["rows"][0]["effectivePrice"])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_actual_headers_persist_callback_even_missing_required_alias(self):
        captured = []
        with self.assertRaisesRegex(api.Failure, "csv_required_columns_missing"):
            api.cost_details_csv(b"UnknownDate,UnknownResource,Quantity\n", SUB, {"A": RG},
                                 {RID.lower()}, "2026-10-15", "2026-10-15",
                                 schema=captured.append)
        self.assertEqual(captured[0]["headers"], ["UnknownDate", "UnknownResource", "Quantity"])
        self.assertIsNone(captured[0]["schemaMapping"]["date"])

    def test_compression_and_stream_wire_byte_count(self):
        import gzip
        import zipfile
        raw = (f"ResourceId,Date,Quantity,MeterCategory\n"
               f"{RID},2026-10-15,1,Bandwidth\n").encode()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr("data.csv", raw)
        for data in (raw, gzip.compress(raw), archive.getvalue()):
            result = api.cost_details_csv_stream(io.BytesIO(data), SUB, {"A": RG},
                                                {RID.lower()}, "2026-10-15", "2026-10-15")
            self.assertEqual(result["downloadBytes"], len(data))
            self.assertEqual(result["rows"][0]["quantity"], "1")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("data.csv", raw)
            zipped.writestr("other.csv", raw)
        with self.assertRaisesRegex(api.Failure, "report_archive_bounds"):
            api.cost_details_csv(archive.getvalue(), SUB, {"A": RG}, {RID.lower()},
                                 "2026-10-15", "2026-10-15")

    def test_stream_limit_deadline_and_non_utc_fail_closed(self):
        with self.assertRaisesRegex(api.Failure, "report_bounds"):
            io.BufferedReader(api.BoundedReport(io.BytesIO(b"12345"), limit=4)).read()
        def elapsed():
            raise api.Failure("elapsed_limit")
        with self.assertRaisesRegex(api.Failure, "elapsed_limit"):
            api.cost_details_csv_stream(io.BytesIO(b""), SUB, {"A": RG}, {RID.lower()},
                                        "2026-10-15", "2026-10-15", check=elapsed)
        with self.assertRaisesRegex(api.Failure, "csv_non_utc_date"):
            api.cost_details_csv(
                f"ResourceId,Date,Quantity\n{RID},2026-10-15T23:00:00-04:00,1\n".encode(),
                SUB, {"A": RG}, {RID.lower()}, "2026-10-15", "2026-10-15")
        with self.assertRaisesRegex(api.Failure, "report_not_csv"):
            api.cost_details_csv(b"<xml>not a report</xml>", SUB, {"A": RG}, {RID.lower()},
                                 "2026-10-15", "2026-10-15")

    def test_continuation_host_scope_version_and_redirect(self):
        transport = api.Transport(SUB, TENANT)
        for bad in (URL.replace("management.azure.com", "evil.example"),
                    URL.replace(SUB, TENANT), URL.replace("https:", "http:"),
                    URL.replace(api.DETAIL_VERSION, "1900-01-01"), URL + "#fragment",
                    URL + "&$skiptoken=opaque token", URL + "\r\n",
                    URL.replace("management.azure.com", "management.azure.com@evil.example")):
            with self.assertRaises(api.Failure):
                transport.validate(bad, ENDPOINT)
        self.assertEqual(transport.validate(URL, ENDPOINT), URL)
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, "", {}, URL))

    def test_truncation_and_duplicate_identity(self):
        result = api.collect(self.transport([{"value": [row()], "nextLink": URL}]),
                             args(pages=1), {RID.lower()})
        self.assertEqual(result["state"], "INCOMPLETE")
        result = api.collect(self.transport([{"value": [row()], "nextLink": URL},
                                             {"value": [row()]}]), args(), {RID.lower()})
        self.assertEqual((len(result["rows"]), result["duplicates"]), (1, 1))
        changed = row(quantity="7")
        with self.assertRaisesRegex(api.Failure, "conflicting_record_identity"):
            api.collect(self.transport([{"value": [row(), changed]}]), args(), {RID.lower()})

    def test_query_columns_reordered_post_body_retained(self):
        page = {"properties": {"columns": [{"name": n} for n in
                  ["Currency", "MeterId", "UsageDate", "ResourceGroup", "PreTaxCost"]],
                  "rows": [["USD", "meter", 20261014, RG, Decimal("0.01")]]}}
        following = api.ARM + f"/subscriptions/{SUB}/providers/Microsoft.CostManagement/query?api-version={api.QUERY_VERSION}&$skiptoken=opaque"
        first = copy.deepcopy(page)
        first["properties"]["nextLink"] = following
        transport = self.transport([first, page])
        result = api.collect(transport, args("query"), set())
        self.assertEqual(result["rows"][0]["PreTaxCost"], Decimal("0.01"))
        calls = transport.request.call_args_list
        self.assertEqual(calls[0].args[0], "POST")
        self.assertEqual(calls[1].args[1], following)
        self.assertEqual(calls[0].args[2], calls[1].args[2])
        self.assertNotIn("UsageQuantity", json.dumps(calls[0].args[2]))

    def test_query_unknown_scope_date_and_grouping_no_silent_fallback(self):
        for rg, date in [("foreign", 20261014), (RG, 20261013)]:
            page = {"properties": {"columns": [{"name": n} for n in
                     ["ResourceGroup", "UsageDate", "Currency", "PreTaxCost"]],
                     "rows": [[rg, date, "USD", 0]]}}
            with self.assertRaises(api.Failure):
                api.collect(self.transport([page]), args("query"), set())
        self.assertEqual(api.query_body(RG, "2026-10-14", "2026-10-14", "Meter")[
            "dataset"]["grouping"][1]["name"], "Meter")
        self.assertEqual(api.query_body(RG, "2026-10-14", "2026-10-14", "ResourceGroup")[
            "dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceGroup"}])
        body = api.query_body(RG, "2026-10-14", "2026-10-14", "Meter", "Bandwidth")
        self.assertEqual(body["dataset"]["filter"], {"and": [
            {"dimensions": {"name": "ResourceGroup", "operator": "In", "values": [RG]}},
            {"dimensions": {"name": "MeterCategory", "operator": "In",
                            "values": ["Bandwidth"]}}]})

    def test_http_failure_timeout_no_credentials_output(self):
        for error, expected in [
                (urllib.error.HTTPError(URL + "&secret=SAS", 403, "TOKEN", {}, None), "http_error"),
                (TimeoutError("Bearer SECRET"), "http_timeout"),
                (urllib.error.HTTPError(URL, 429, "secret", {"Retry-After": "600"}, None), "rate_limited")]:
            transport = api.Transport(SUB, TENANT)
            transport.authorize = lambda: "SECRET"
            transport.opener.open = unittest.mock.Mock(side_effect=error)
            with self.assertRaises(api.Failure) as caught:
                transport.request("GET", URL, endpoint=ENDPOINT)
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertNotIn("SAS", str(caught.exception))

    def test_snapshot_existing_and_private_boundary(self):
        with self.assertRaises(api.Failure):
            api.private_path(str(api.LAB / "costs" / "bad.json"))
        with patch("cost_api.load_inventory", return_value={RID.lower()}), patch(
                "sys.stdout", new_callable=io.StringIO) as out:
            code = api.main(["cost-details", "--subscription", SUB, "--expected-tenant", TENANT,
                             "--resource-group", RG, "--start", "2026-10-14", "--end", "2026-10-14",
                             "--inventory", str(api.LAB / "private" / "inventory.json"),
                             "--output", str(api.LAB / "private" / "new.json")])
        self.assertEqual(code, 2)
        self.assertNotIn("not_implemented", out.getvalue())
        self.assertIn("cost_details_requires_csv_output", out.getvalue())
        with patch("cost_api.Path.exists", return_value=True), patch(
                "sys.stdout", new_callable=io.StringIO) as out:
            code = api.main(["query", "--subscription", SUB, "--expected-tenant", TENANT,
                             "--resource-group", RG,
                             "--start", "2026-10-14", "--end", "2026-10-14",
                             "--output", str(api.LAB / "private" / "existing.json")])
        self.assertEqual(code, 2)
        self.assertIn("snapshot_already_exists", out.getvalue())

    def test_msdn_required_dates_are_not_offer_rejection(self):
        messages = [
            ("Billing Period is not supported in (2024-08-01) API Version for "
             "Subscription Scope With Web Direct Offer. Please provide the UsageStart "
             "and UsageEnd dates in the $filter key as parameters.",
             "required_usage_date_range"),
            ("Invalid date. Start date (UTC): 2099-01-01 cannot be set in the future",
             "date_constraint"),
        ]
        for message, expected in messages:
            error = urllib.error.HTTPError(
                URL, 400, "", {}, io.BytesIO(json.dumps(
                    {"error": {"code": "400", "message": message}}).encode()))
            transport = api.Transport(SUB, TENANT)
            transport.authorize = lambda: "SECRET"
            transport.opener.open = unittest.mock.Mock(side_effect=error)
            with self.assertRaises(api.Failure) as caught:
                transport.request("GET", URL, endpoint=ENDPOINT)
            self.assertEqual(caught.exception.category, expected)
            self.assertEqual(caught.exception.azure_code, "400")

    def test_elapsed_and_invalid_interval_are_not_complete(self):
        transport = api.Transport(SUB, TENANT)
        transport.deadline = 0
        with self.assertRaisesRegex(api.Failure, "elapsed_limit"):
            api.collect(transport, args(), {RID.lower()})
        self.assertIsNone(api.usage_date(row(date=None, usageStart=None)))
        self.assertIsNone(api.usage_date(row(date="2026-10-14", usageEnd="2026-10-17")))


if __name__ == "__main__":
    unittest.main()
