"""Bounded, read-only Azure billing collector. Python standard library only."""
import argparse
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ARM = "https://management.azure.com"
QUERY_VERSION = "2023-11-01"
DETAIL_VERSION = "2024-08-01"
LAB = Path(__file__).resolve().parents[1]


class Failure(Exception):
    def __init__(self, code, status=None, azure_code=None, category=None):
        self.code, self.status, self.azure_code, self.category = code, status, azure_code, category
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def valid_id(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise Failure("invalid_context") from None


def assert_lease():
    path = LAB / "deploy" / ".runtime-control" / "api-lease.json"
    try:
        lease = json.loads(path.read_text(encoding="utf-8-sig"))
        expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        if ((path.parent / "STOP").exists() or lease["state"] != "active" or
                dt.datetime.now(dt.timezone.utc) >= expiry or
                lease.get("actualToolCalls", 0) >= lease["maxToolCalls"] * .8):
            raise Failure("lease_inactive")
    except (OSError, ValueError, KeyError):
        raise Failure("lease_required") from None


def cli_json(args, timeout=15):
    binary = shutil.which("az")
    if not binary:
        raise Failure("native_cli_missing")
    if os.name == "nt":
        python = Path(binary).resolve().parent.parent / "python.exe"
        if not python.is_file():
            raise Failure("cli_python_missing")
        command = [str(python), "-m", "azure.cli"]
    else:
        if binary.lower().endswith((".exe", ".cmd", ".bat")):
            raise Failure("linux_cli_required")
        command = [binary]
    try:
        result = run_bounded(command + args + ["--output", "json", "--only-show-errors"], timeout)
    except subprocess.TimeoutExpired:
        raise Failure("cli_timeout") from None
    if result.returncode:
        raise Failure("cli_failed")
    try:
        return json.loads(result.stdout, parse_float=Decimal)
    except (ValueError, UnicodeError):
        raise Failure("cli_invalid_json") from None


def run_bounded(command, timeout):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name != "nt")
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=5, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.kill()
        process.communicate(timeout=5)
        raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, subscription, tenant, seconds=75):
        self.subscription = valid_id(subscription)
        self.tenant = valid_id(tenant)
        self.scope = f"/subscriptions/{self.subscription}"
        self.deadline = time.monotonic() + seconds
        self.opener = urllib.request.build_opener(NoRedirect())
        self.http = []
        self.context_verified = False
        self.guard = lambda: None
        self._token = None
        self._token_received_at = 0
        self._token_expires_at = 0
        self._token_deadline = 0

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Failure("elapsed_limit")
        return remaining

    def authorize(self):
        self.guard()
        remaining = self.remaining()
        now = time.time()
        if (self._token is not None and self._token_received_at <= now <
                self._token_expires_at - 120 and time.monotonic() < self._token_deadline):
            return self._token
        self._token = None
        account = cli_json(["account", "show", "--subscription", self.subscription],
                           min(15, remaining))
        if (str(account.get("id", "")).lower() != self.subscription or
                str(account.get("tenantId", "")).lower() != self.tenant or
                account.get("state") != "Enabled"):
            raise Failure("context_mismatch")
        token = cli_json(["account", "get-access-token", "--subscription", self.subscription,
                          "--resource", ARM],
                         min(15, self.remaining()))
        if (not token.get("accessToken") or str(token.get("tenant", "")).lower() != self.tenant or
                str(token.get("subscription", "")).lower() != self.subscription):
            raise Failure("token_context_mismatch")
        self.context_verified = True
        # Only the unambiguous UTC epoch is cacheable; legacy local expiresOn is not.
        try:
            expires_at = float(token.get("expires_on", 0))
        except (ValueError, TypeError, OverflowError):
            expires_at = 0
        now = time.time()
        if now + 120 < expires_at < float("inf"):
            self._token = token["accessToken"]
            self._token_received_at = now
            self._token_expires_at = expires_at
            self._token_deadline = time.monotonic() + expires_at - now - 120
        return token["accessToken"]

    def validate(self, url, endpoint):
        if any(char.isspace() or ord(char) < 32 for char in url):
            raise Failure("unsafe_continuation")
        parsed = urllib.parse.urlsplit(url)
        path = self.scope + endpoint
        if (parsed.scheme != "https" or parsed.netloc.lower() != "management.azure.com" or
                parsed.fragment or parsed.path.lower() != path.lower() or
                "%" in parsed.path):
            raise Failure("unsafe_continuation")
        params = urllib.parse.parse_qs(parsed.query)
        expected = QUERY_VERSION if endpoint.endswith("/query") else DETAIL_VERSION
        if params.get("api-version") != [expected]:
            raise Failure("continuation_version_changed")
        return url

    def request(self, method, url, body=None, endpoint=None):
        self.validate(url, endpoint)
        token = self.authorize()
        payload = None if body is None else json.dumps(body).encode()
        for attempt in range(2):
            request = urllib.request.Request(
                url, data=payload, method=method,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            try:
                with self.opener.open(request, timeout=min(20, self.remaining())) as response:
                    chunks, size = [], 0
                    while True:
                        self.remaining()
                        chunk = response.read1(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > 8 * 1024 * 1024:
                            raise Failure("page_byte_limit")
                    raw = b"".join(chunks)
                    self.http.append({"status": response.status})
                    if len(raw) > 8 * 1024 * 1024:
                        raise Failure("page_byte_limit")
                    if response.status == 204:
                        return {}
                    return json.loads(raw, parse_float=Decimal)
            except urllib.error.HTTPError as error:
                self.http.append({"status": error.code})
                retry = error.headers.get("Retry-After", "")
                if error.code == 429 and attempt == 0 and retry.isdigit():
                    delay = int(retry)
                    if delay <= 2 and delay < self.remaining():
                        time.sleep(delay)
                        continue
                azure_code = None
                category = None
                try:
                    error_object = json.loads(error.read(65536)).get("error", {})
                    value = error_object.get("code")
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}", value):
                        azure_code = value
                    message = str(error_object.get("message", "")).lower()
                    if ("please provide" in message and "usagestart" in message and
                            "usageend" in message):
                        category = "required_usage_date_range"
                    elif "cannot be set in the future" in message or "invalid date" in message:
                        category = "date_constraint"
                    elif "not supported" in message and "offer" in message:
                        category = "offer_or_scope_constraint"
                    else:
                        for text, label in [("api-version", "api_version"),
                                            ("date", "date_constraint"), ("filter", "filter_constraint"),
                                            ("expand", "expand_constraint"),
                                            ("subscription", "subscription_constraint")]:
                            if text in message:
                                category = label
                                break
                except (ValueError, TypeError, AttributeError):
                    pass
                raise Failure("rate_limited" if error.code == 429 else "http_error",
                              error.code, azure_code, category) from None
            except (TimeoutError, socket.timeout):
                raise Failure("http_timeout") from None
            except urllib.error.URLError as error:
                raise Failure("http_timeout" if isinstance(error.reason, TimeoutError)
                              else "network_error") from None
            except (ValueError, UnicodeError):
                raise Failure("http_invalid_json") from None


def day(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        raise Failure("invalid_date") from None


def decimal(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return str(number)
    except InvalidOperation:
        raise Failure("invalid_decimal") from None


def query_body(rg, start, end, grouping, meter_category=None):
    body = {"type": "ActualCost", "timeframe": "Custom",
            "timePeriod": {"from": start + "T00:00:00Z", "to": end + "T23:59:59Z"},
            "dataset": {"granularity": "Daily",
                        "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                        "filter": {"dimensions": {"name": "ResourceGroup", "operator": "In",
                                                   "values": [rg]}}}}
    if meter_category:
        body["dataset"]["filter"] = {"and": [
            body["dataset"]["filter"],
            {"dimensions": {"name": "MeterCategory", "operator": "In",
                            "values": [meter_category]}}]}
    if grouping != "none":
        body["dataset"]["grouping"] = [{"type": "Dimension", "name": "ResourceGroup"}]
        if grouping != "ResourceGroup":
            body["dataset"]["grouping"].append({"type": "Dimension", "name": grouping})
    return body


def details_url(scope, rg, start, end, variant="legacy-date", literal=False, top=1000,
                expand="properties/meterDetails"):
    clause = f"properties/resourceGroup eq '{rg}'"
    if variant == "legacy-date":
        next_day = (day(end) + dt.timedelta(days=1)).isoformat()
        clause += f" and properties/usageStart ge '{start}' and properties/usageEnd le '{next_day}'"
    elif variant == "modern-date":
        next_day = (day(end) + dt.timedelta(days=1)).isoformat()
        clause += f" and properties/date ge '{start}' and properties/date lt '{next_day}'"
    params = {"api-version": DETAIL_VERSION, "metric": "ActualCost",
              "$expand": expand, "$filter": clause, "$top": top}
    return ARM + scope + "/providers/Microsoft.Consumption/usageDetails?" + urllib.parse.urlencode(
        params, safe="$" if literal else "")


def query_columns(properties):
    names = [column["name"] for column in properties.get("columns", [])]
    if len(names) != len(set(names)):
        raise Failure("duplicate_query_columns")
    rows = []
    for row in properties.get("rows", []):
        if len(row) != len(names):
            raise Failure("query_row_shape")
        rows.append(dict(zip(names, row)))
    return names, rows


def identity(item, subscription, rg, inventory):
    props = item.get("properties", {})
    actual_rg = props.get("resourceGroup") or props.get("resourceGroupName")
    candidates = [props.get(key) for key in ("resourceId", "instanceId", "instanceName")]
    resource = next((value.lower().rstrip("/") for value in candidates
                     if isinstance(value, str) and value.lower().startswith("/subscriptions/")), None)
    if actual_rg and actual_rg.lower() != rg.lower():
        return None
    if resource is not None:
        prefix = f"/subscriptions/{subscription}/resourcegroups/{rg}/".lower()
        if not resource.startswith(prefix) or resource not in inventory:
            return None
        return resource
    name = props.get("instanceName")
    if actual_rg and actual_rg.lower() == rg.lower() and isinstance(name, str):
        matches = [value for value in inventory if value.rsplit("/", 1)[-1] == name.lower()]
        prefix = f"/subscriptions/{subscription}/resourcegroups/{rg}/".lower()
        if len(matches) == 1 and matches[0].startswith(prefix):
            return matches[0]
    return None


def usage_date(item):
    props = item.get("properties", {})
    value = props.get("date") or props.get("usageStart")
    if value is None:
        return None
    try:
        result = day(value)
        end = props.get("usageEnd")
        if end and day(end) > result + dt.timedelta(days=1):
            return None
        return result
    except Failure:
        return None


def normalize(item, resource):
    p = item["properties"]
    meter = p.get("meterDetails") or {}
    return {"sourceKind": item.get("kind"), "day": usage_date(item).isoformat(),
            "resourceId": resource, "resourceGroup": p.get("resourceGroup"),
            "quantity": decimal(p.get("quantity", p.get("usageQuantity"))),
            "unit": p.get("unitOfMeasure") or meter.get("unitOfMeasure") or meter.get("unit"),
            "effectivePrice": decimal(p.get("effectivePrice")),
            "unitPrice": decimal(p.get("unitPrice")),
            "cost": decimal(p.get("costInBillingCurrency", p.get("pretaxCost", p.get("cost")))),
            "currency": p.get("billingCurrency") or p.get("billingCurrencyCode") or p.get("currency"),
            "meterId": p.get("meterId"),
            "meterName": p.get("meterName") or meter.get("meterName"),
            "meterCategory": p.get("meterCategory") or meter.get("meterCategory"),
            "meterSubCategory": p.get("meterSubCategory") or meter.get("meterSubCategory"),
            "sourceRecordHash": digest(item)}


def cost_details_csv(raw, subscription, groups, inventory, start, end, max_rows=100000,
                     check=None, schema=None):
    """Project an in-memory report before retaining any non-inventory billing data."""
    if len(raw) > 50 * 1024 * 1024 or not 1 <= max_rows <= 100000:
        raise Failure("report_bounds")
    subscription = valid_id(subscription)
    return cost_details_csv_stream(io.BytesIO(raw), subscription, groups, inventory,
                                  start, end, max_rows, check, schema)


class BoundedReport(io.RawIOBase):
    def __init__(self, source, check=None, limit=50 * 1024 * 1024):
        self.source, self.check, self.limit, self.size = source, check, limit, 0

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.check:
            self.check()
        data = self.source.read(min(len(buffer), self.limit - self.size + 1))
        self.size += len(data)
        if self.size > self.limit:
            raise Failure("report_bounds")
        buffer[:len(data)] = data
        return len(data)


def cost_details_csv_stream(source, subscription, groups, inventory, start, end,
                            max_rows=100000, check=None, schema=None):
    """Stream CSV; only exact-inventory/date/Bandwidth projections survive."""
    if not 1 <= max_rows <= 100000:
        raise Failure("report_bounds")
    subscription = valid_id(subscription)
    wire = BoundedReport(source, check)
    bounded = io.BufferedReader(wire)
    magic = bounded.peek(4)[:4]
    if magic.startswith(b"\x1f\x8b"):
        import gzip
        bounded = io.BufferedReader(BoundedReport(gzip.GzipFile(fileobj=bounded), check))
    elif magic.startswith(b"PK"):
        import zipfile
        archive = zipfile.ZipFile(io.BytesIO(bounded.read()))
        entries = archive.infolist()
        if (len(entries) != 1 or not entries[0].filename.lower().endswith(".csv")
                or entries[0].file_size > 50 * 1024 * 1024 or entries[0].flag_bits & 1):
            raise Failure("report_archive_bounds")
        bounded = io.BufferedReader(BoundedReport(archive.open(entries[0]), check))
    elif magic.lstrip().startswith(b"<"):
        raise Failure("report_not_csv")
    text = io.TextIOWrapper(bounded, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text, strict=True)
    fields = reader.fieldnames or []
    if len(fields) > 128 or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _()/-]{0,100}",
                                               field.strip()) for field in fields):
        raise Failure("csv_header_bounds")
    names = [name.strip().casefold() for name in fields]
    aliases = {
        "resourceId": ("resourceid", "instanceid"),
        "resourceGroup": ("resourcegroup", "resourcegroupname"),
        "date": ("date", "usagedate"),
        "quantity": ("quantity", "usagequantity"),
        "unit": ("unitofmeasure",),
        "effectivePrice": ("effectiveprice",),
        "unitPrice": ("unitprice",),
        "cost": ("costinbillingcurrency", "pretaxcost", "cost"),
        "currency": ("billingcurrencycode", "billingcurrency", "currency"),
        "meterCategory": ("metercategory", "servicename"),
        "meterName": ("metername",),
    }
    mapping = {key: next((name for name in choices if name in names), None)
               for key, choices in aliases.items()}
    metadata = {"headers": fields, "schemaMapping": mapping,
                "reportFlavorCapability": (
                    "MCA-compatible fields; not an account/offer determination"
                    if {"billingprofileid", "costinbillingcurrency"}.issubset(names)
                    else "Legacy/EA-compatible aliases; not an account/offer determination")}
    if schema is not None:
        schema(metadata)
    if len(names) != len(set(names)):
        raise Failure("csv_duplicate_columns")
    if not all(mapping[key] for key in ("resourceId", "date", "quantity")):
        raise Failure("csv_required_columns_missing")
    result = {"rows": [], "received": 0, "discarded": 0, "columns": names,
              "schemaMapping": mapping, "discardCounts": {
                  "inventory": 0, "date": 0, "category": 0}, "datasetMaxUsageDate": None}
    for source in reader:
        if check is not None:
            check()
        result["received"] += 1
        if result["received"] > max_rows:
            raise Failure("report_row_limit")
        if None in source or any(value is None for value in source.values()):
            raise Failure("csv_row_shape")
        row = {key.strip().casefold(): value for key, value in source.items()}
        resource = (row.get(mapping["resourceId"]) or "").lower().rstrip("/")
        match = next(((alias, group) for alias, group in groups.items()
                      if resource.startswith(
                          f"/subscriptions/{subscription}/resourcegroups/{group}/".lower())), None)
        if resource not in inventory or match is None:
            result["discarded"] += 1
            result["discardCounts"]["inventory"] += 1
            continue
        actual_rg = row.get(mapping["resourceGroup"])
        if actual_rg and actual_rg.lower() != match[1].lower():
            raise Failure("csv_resource_group_mismatch")
        value = row[mapping["date"]]
        try:
            parsed_date = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed_date.tzinfo and parsed_date.utcoffset() != dt.timedelta(0):
                raise Failure("csv_non_utc_date")
            date = parsed_date.date()
        except ValueError:
            try:
                date = dt.datetime.strptime(value, "%m/%d/%Y").date()
            except ValueError:
                raise Failure("csv_lab_date_invalid") from None
        result["datasetMaxUsageDate"] = max(result["datasetMaxUsageDate"] or "",
                                             date.isoformat())
        if not day(start) <= date <= day(end):
            result["discarded"] += 1
            result["discardCounts"]["date"] += 1
            continue
        category = row.get(mapping["meterCategory"])
        if not any(row.get(key, "").strip().casefold() == "bandwidth"
                   for key in ("metercategory", "servicename")):
            result["discarded"] += 1
            result["discardCounts"]["category"] += 1
            continue
        currency = row.get(mapping["currency"])
        cost = row.get(mapping["cost"])
        result["rows"].append({
            "alias": match[0], "resourceId": resource, "day": date.isoformat(),
            "resourceGroup": match[1], "dateSource": mapping["date"],
            "quantity": decimal(row.get(mapping["quantity"]) or None),
            "unit": row.get(mapping["unit"]) or None,
            "effectivePrice": decimal(row.get(mapping["effectivePrice"]) or None),
            "unitPrice": decimal(row.get(mapping["unitPrice"]) or None),
            "cost": decimal(cost or None), "currency": currency or None,
            "costSource": mapping["cost"], "currencySource": mapping["currency"],
            "pricingCurrency": row.get("pricingcurrency") or None,
            "exchangeRatePricingToBilling": decimal(
                row.get("exchangeratepricingtobilling") or None),
            "meterCategory": category or None,
            "serviceName": row.get("servicename") or None,
            "meterName": row.get(mapping["meterName"]) or None,
            "sourceRecordHash": digest(source)})
    result["downloadBytes"] = wire.size
    return result


def collect(transport, args, inventory):
    detail = args.command == "details"
    endpoint = "/providers/" + ("Microsoft.Consumption/usageDetails" if detail
                               else "Microsoft.CostManagement/query")
    body = None if detail else query_body(args.resource_group, args.start, args.end, args.grouping,
                                          getattr(args, "meter_category", None))
    url = (details_url(transport.scope, args.resource_group, args.start, args.end,
                       args.filter_variant, args.literal_keys,
                       top=getattr(args, "page_size", 1000),
                       expand=getattr(args, "expand", "properties/meterDetails")) if detail else
           ARM + transport.scope + endpoint + "?api-version=" + QUERY_VERSION)
    request_hash = digest({"endpoint": endpoint, "body": body, "start": args.start,
                           "end": args.end, "filter": args.filter_variant,
                           "resourceGroup": args.resource_group})
    result = {"schemaVersion": 1, "metric": "ActualCost",
              "apiVersion": DETAIL_VERSION if detail else QUERY_VERSION,
              "requestHash": request_hash, "retrievedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "request": {"method": "GET" if detail else "POST", "endpoint": endpoint,
                          "body": body, "start": args.start, "end": args.end,
                          "filterVariant": args.filter_variant, "literalDollarKeys": args.literal_keys,
                          "pageSize": getattr(args, "page_size", 1000),
                          "expand": getattr(args, "expand", "properties/meterDetails") if detail else None},
              "state": "INCOMPLETE", "pages": 0, "received": 0, "discarded": 0,
              "duplicates": 0, "unattributedLabRows": 0, "rows": [], "http": transport.http}
    seen_links, seen_records = set(), {}
    for _ in range(args.max_pages):
        transport.remaining()
        if url in seen_links:
            result["reason"] = "continuation_cycle"
            return result
        seen_links.add(url)
        page = transport.request("GET" if detail else "POST", url, body, endpoint)
        result["pages"] += 1
        if detail:
            rows = page.get("value", [])
            result["received"] += len(rows)
            for item in rows:
                resource = identity(item, transport.subscription, args.resource_group, inventory)
                date = usage_date(item)
                if resource is None or date is None or not day(args.start) <= date <= day(args.end):
                    result["discarded"] += 1
                    p = item.get("properties", {})
                    row_rg = p.get("resourceGroup") or p.get("resourceGroupName")
                    if row_rg and row_rg.lower() == args.resource_group.lower() and (
                            resource is None or date is None):
                        result["unattributedLabRows"] += 1
                    continue
                normalized = normalize(item, resource)
                key = item.get("id")
                fingerprint = digest(item)
                if key and key in seen_records:
                    if seen_records[key] != fingerprint:
                        raise Failure("conflicting_record_identity")
                    result["duplicates"] += 1
                    continue
                if key:
                    seen_records[key] = fingerprint
                result["rows"].append(normalized)
            url = page.get("nextLink")
        else:
            properties = page.get("properties", {})
            columns, rows = query_columns(properties)
            if "columns" in result and result["columns"] != columns:
                raise Failure("query_columns_changed")
            result["columns"] = columns
            result["columnDefinitions"] = properties.get("columns", [])
            result["received"] += len(rows)
            for row in rows:
                if str(row.get("ResourceGroup", "")).lower() != args.resource_group.lower():
                    raise Failure("query_scope_unverified")
                if "UsageDate" not in row or "Currency" not in row or not (
                        "PreTaxCost" in row or "Cost" in row):
                    raise Failure("query_required_columns_missing")
                date_string = str(row["UsageDate"])
                try:
                    date = dt.datetime.strptime(date_string, "%Y%m%d").date()
                except ValueError:
                    raise Failure("query_date_invalid") from None
                if not day(args.start) <= date <= day(args.end):
                    raise Failure("query_date_mismatch")
                result["rows"].append(row)
            url = properties.get("nextLink")
        if not url:
            if result["unattributedLabRows"]:
                result["reason"] = "unattributed_lab_rows"
            else:
                result["state"] = "COMPLETE"
            return result
        transport.validate(url, endpoint)
    result["reason"] = "page_limit"
    return result


def probe(transport, args):
    endpoint = "/providers/Microsoft.CostManagement/query"
    query_day = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    body = query_body(args.resource_group, query_day, query_day, "none")
    result = {"schemaVersion": 1, "offerAlias": args.offer_alias,
              "retrievedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "subscriptionPinned": True, "expectedTenantMatched": False, "results": []}
    operations = [("Query", QUERY_VERSION, "POST", ARM + transport.scope + endpoint +
                   "?api-version=" + QUERY_VERSION, body, endpoint)]
    endpoint = "/providers/Microsoft.Consumption/usageDetails"
    operations.append(("Consumption", DETAIL_VERSION, "GET",
                       details_url(transport.scope, args.resource_group, args.start, args.end,
                                   args.filter_variant, args.literal_keys, top=1,
                                   expand=args.expand), None, endpoint))
    for api, version, method, url, payload, endpoint in operations:
        entry = {"api": api, "apiVersion": version, "filterVariant": args.filter_variant,
                 "literalDollarKeys": args.literal_keys,
                 "start": query_day if api == "Query" else args.start,
                 "end": query_day if api == "Query" else args.end,
                 "resourceGroup": "<nonexistent-lab-rg>", "requestBody": payload,
                 "expand": args.expand if api == "Consumption" else None,
                 "requestHash": digest({"method": method, "url": url, "body": payload})}
        # Only the fixed nonexistent name is permitted in the public request body.
        try:
            page = transport.request(method, url, payload, endpoint)
            entry["httpStatus"] = transport.http[-1]["status"]
            if api == "Query":
                props = page.get("properties", {})
                names, rows = query_columns(props)
                entry.update(rowCount=len(rows), columns=names, nextLinkPresent=bool(props.get("nextLink")))
            else:
                rows = page.get("value", [])
                props = [row.get("properties", {}) for row in rows]
                entry.update(rowCount=len(rows), kinds=sorted({str(row.get("kind")) for row in rows}),
                             fields=sorted({key for p in props for key in p
                                            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,60}", key)}),
                             allRowsMatchRG=all(str(p.get("resourceGroup", "")).lower() ==
                                                args.resource_group.lower() for p in props),
                             allRowsMatchDate=all(usage_date(row) is not None and
                                                 day(args.start) <= usage_date(row) <= day(args.end)
                                                 for row in rows),
                             nextLinkPresent=bool(page.get("nextLink")))
            entry["outcome"] = "ACCESS_OK_NOT_BILLING_PROOF"
        except Failure as error:
            entry.update(outcome=error.code, httpStatus=error.status, azureCode=error.azure_code,
                         errorCategory=error.category)
        result["results"].append(entry)
    result["expectedTenantMatched"] = transport.context_verified
    return result


def private_path(value):
    path = Path(value).resolve()
    try:
        path.relative_to((LAB / "private").resolve())
    except ValueError:
        raise Failure("output_must_be_lab_private") from None
    return path


def linux_path(value):
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/") if re.match(
        r"^[A-Za-z]:[\\/]", value) else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "query", "details", "cost-details"])
    parser.add_argument("--transport", choices=["native", "wsl"], default="native")
    parser.add_argument("--distribution", default="Ubuntu-24.04")
    parser.add_argument("--subscription")
    parser.add_argument("--expected-tenant")
    parser.add_argument("--context", help="Ignored private JSON: subscriptionId, expectedTenantId")
    parser.add_argument("--resource-group", default="rg-bandwidth-billing-preflight")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--inventory", help="Private JSON: resourceIds array; exact whitelist required")
    parser.add_argument("--output", help="New file under this lab's ignored private directory")
    parser.add_argument("--offer-alias", choices=["windows-main", "wsl-msdn", "unverified"],
                        default="unverified")
    parser.add_argument("--grouping", choices=["MeterId", "Meter", "MeterCategory", "ResourceGroup", "none"],
                        default="Meter")
    parser.add_argument("--meter-category", help="Explicit Query meter-category filter, e.g. Bandwidth")
    parser.add_argument("--filter-variant", choices=["rg-only", "legacy-date", "modern-date"],
                        default="legacy-date")
    parser.add_argument("--literal-keys", action="store_true")
    parser.add_argument("--expand", choices=["meterDetails", "properties/meterDetails"],
                        default="properties/meterDetails")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-seconds", type=int, default=75)
    args = parser.parse_args(argv)
    try:
        if args.transport == "wsl":
            if os.name != "nt":
                raise Failure("wsl_dispatch_requires_windows")
            forwarded = list(sys.argv[1:] if argv is None else argv)
            forwarded[forwarded.index("--transport") + 1] = "native"
            for flag in ("--context", "--inventory", "--output"):
                if flag in forwarded:
                    index = forwarded.index(flag) + 1
                    forwarded[index] = linux_path(forwarded[index])
            result = run_bounded(["wsl.exe", "-d", args.distribution, "--exec", "timeout",
                                  "--signal=TERM", "--kill-after=3s", "100s", "python3",
                                  linux_path(str(Path(__file__).resolve()))] + forwarded, 110)
            # The child only emits a sanitized summary; never relay arbitrary stderr.
            try:
                summary = json.loads(result.stdout)
            except (ValueError, UnicodeError):
                raise Failure("wsl_invalid_result") from None
            print(json.dumps(summary))
            return result.returncode
        if args.command == "cost-details":
            raise Failure("cost_details_async_not_implemented_use_documented_EA_MCA_route")
        if (not 1 <= args.max_pages <= 20 or not 1 <= args.page_size <= 1000 or
                not 1 <= args.max_seconds <= 90 or
                day(args.start) > day(args.end) or
                not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", args.resource_group)):
            raise Failure("invalid_bounds")
        if args.command == "probe" and args.resource_group != "rg-bandwidth-billing-preflight":
            raise Failure("probe_requires_nonexistent_rg")
        if args.command == "query" and args.grouping == "none":
            raise Failure("collection_requires_scope_grouping")
        if args.context:
            context = json.loads(private_path(args.context).read_text(encoding="utf-8-sig"))
            args.subscription = args.subscription or context["subscriptionId"]
            args.expected_tenant = args.expected_tenant or context["expectedTenantId"]
        transport = Transport(args.subscription, args.expected_tenant, args.max_seconds)
        transport.guard = assert_lease
        inventory = set()
        if args.command == "details":
            if not args.inventory:
                raise Failure("private_inventory_required")
            inventory = {value.lower().rstrip("/") for value in json.loads(
                private_path(args.inventory).read_text(encoding="utf-8-sig"))["resourceIds"]}
            if not inventory:
                raise Failure("empty_inventory")
        output = private_path(args.output) if args.output else None
        if args.command != "probe" and output is None:
            raise Failure("collection_requires_private_output")
        if output and output.exists():
            raise Failure("snapshot_already_exists")
        data = probe(transport, args) if args.command == "probe" else collect(transport, args, inventory)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, default=str)
        if args.command == "probe":
            print(json.dumps(data, default=str))
            return 0 if all(item["outcome"] == "ACCESS_OK_NOT_BILLING_PROOF"
                            for item in data["results"]) else 2
        print(json.dumps({key: data[key] for key in (
            "state", "pages", "received", "discarded", "duplicates", "unattributedLabRows")}))
        return 0 if data["state"] == "COMPLETE" else 3
    except subprocess.TimeoutExpired:
        print(json.dumps({"state": "ERROR", "code": "wsl_timeout"}))
        return 2
    except Failure as error:
        print(json.dumps({"state": "ERROR", "code": error.code, "httpStatus": error.status,
                          "azureCode": error.azure_code, "errorCategory": error.category}))
        return 2
    except (OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"state": "ERROR", "code": "invalid_input_or_io"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
