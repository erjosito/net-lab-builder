import argparse
import copy
import csv
from decimal import Decimal
import io
import json
import unittest
from unittest.mock import patch
import urllib.error

import cost_api as api

SUB = "11111111-1111-1111-1111-111111111111"
TENANT = "22222222-2222-2222-2222-222222222222"
RG = "rg-test"
RID = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Compute/virtualMachines/a"
ENDPOINT = "/providers/Microsoft.Consumption/usageDetails"
URL = api.ARM + f"/subscriptions/{SUB}" + ENDPOINT + "?api-version=" + api.DETAIL_VERSION


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


class CollectorTests(unittest.TestCase):
    def transport(self, pages):
        transport = api.Transport(SUB, TENANT)
        transport.request = unittest.mock.Mock(side_effect=pages)
        return transport

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
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            code = api.main(["cost-details", "--start", "2026-10-14", "--end", "2026-10-14"])
        self.assertEqual(code, 2)
        self.assertIn("not_implemented", out.getvalue())
        with patch("cost_api.Path.exists", return_value=True), patch(
                "sys.stdout", new_callable=io.StringIO) as out:
            code = api.main(["query", "--subscription", SUB, "--expected-tenant", TENANT,
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
