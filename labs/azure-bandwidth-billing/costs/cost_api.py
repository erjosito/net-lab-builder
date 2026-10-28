"""Bounded, read-only Azure billing collector. Python standard library only."""
import argparse
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import email.utils
import hashlib
import http.client
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
import zipfile
import zlib

ARM = "https://management.azure.com"
QUERY_VERSION = "2023-11-01"
DETAIL_VERSION = "2024-08-01"
REPORT_VERSION = "2025-03-01"
REPORT_ENDPOINT = "/providers/Microsoft.CostManagement/generateCostDetailsReport"
QUERY_ENDPOINT = "/providers/Microsoft.CostManagement/query"
QUERY_CLIENT_TYPE = "GitHubCopilotForAzure"
LAB = Path(__file__).resolve().parents[1]


class Failure(Exception):
    def __init__(self, code, status=None, azure_code=None, category=None, response_metadata=None):
        self.code, self.status, self.azure_code, self.category = code, status, azure_code, category
        self.response_metadata = response_metadata
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
    def __init__(self, subscription, tenant, seconds=75, request_timeout_seconds=20):
        self.subscription = valid_id(subscription)
        self.tenant = valid_id(tenant)
        self.scope = f"/subscriptions/{self.subscription}"
        self.deadline = time.monotonic() + seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.opener = urllib.request.build_opener(NoRedirect())
        self.http = []
        self.context_verified = False
        self.guard = lambda: None
        self._token = None
        self._token_received_at = 0
        self._token_expires_at = 0
        self._token_deadline = 0
        self.max_http_requests = 100
        self.max_retries = 1
        self.retry_delay_limit = 2
        self.http_requests = 0
        self.http_request_counts = {}
        self.on_http = lambda: None

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
        if (not isinstance(account, dict) or
                str(account.get("id", "")).lower() != self.subscription or
                str(account.get("tenantId", "")).lower() != self.tenant or
                account.get("state") != "Enabled"):
            raise Failure("context_mismatch")
        token = cli_json(["account", "get-access-token", "--subscription", self.subscription,
                          "--resource", ARM],
                         min(15, self.remaining()))
        if (not isinstance(token, dict) or not isinstance(token.get("accessToken"), str) or
                not token.get("accessToken") or str(token.get("tenant", "")).lower() != self.tenant or
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
        if endpoint == REPORT_ENDPOINT:
            return self.validate_report(url, generation=True)
        if endpoint == "report-poll":
            return self.validate_report(url)
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

    def validate_report(self, url, generation=False):
        parsed = safe_url(url, "unsafe_report_url")
        prefix = self.scope + "/providers/Microsoft.CostManagement/"
        operation = parsed.path[len(prefix):]
        operation_id = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
        pattern = ("generateCostDetailsReport" if generation else
                   r"(?:costDetailsOperationStatus|costDetailsOperationResults|operationResults)/"
                   + operation_id)
        if (parsed.netloc != "management.azure.com" or "#" in url or
                not parsed.path.lower().startswith(prefix.lower()) or
                not re.fullmatch(pattern, operation, re.IGNORECASE | re.ASCII)):
            raise Failure("unsafe_report_url")
        try:
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True,
                                          strict_parsing=True, max_num_fields=5)
        except ValueError:
            raise Failure("unsafe_report_url") from None
        if params.get("api-version") != [REPORT_VERSION]:
            raise Failure("unsafe_report_url")
        if params != {"api-version": [REPORT_VERSION]}:
            # Azure's returned results Location carries opaque signed context, not ARM selectors.
            signed = {"t": r"[0-9]{18}", "c": r"[A-Za-z0-9_-]{1,8192}",
                      "s": r"[A-Za-z0-9_-]{1,1024}", "h": r"[A-Za-z0-9_-]{43}"}
            if (generation or not operation.lower().startswith("costdetailsoperationresults/") or
                    set(params) != {"api-version", *signed} or
                    any(len(params[key]) != 1 or not re.fullmatch(pattern, params[key][0])
                        for key, pattern in signed.items())):
                raise Failure("unsafe_report_url")
        return url

    def request(self, method, url, body=None, endpoint=None, *, envelope=False,
                consume=None, retries=None):
        blob = consume is not None
        if blob:
            validate_blob(url)
        else:
            self.validate(url, endpoint)
        token = None if blob else self.authorize()
        payload = None if body is None else json.dumps(body).encode()
        retry_count = self.max_retries if retries is None else retries
        for attempt in range(retry_count + 1):
            self.guard()
            self.remaining()
            if self.http_requests >= self.max_http_requests:
                raise Failure("http_request_limit")
            self.http_requests += 1
            self.on_http()
            request_headers = {} if blob else {"Authorization": "Bearer " + token,
                                               "Content-Type": "application/json"}
            if not blob and endpoint == QUERY_ENDPOINT:
                request_headers["ClientType"] = QUERY_CLIENT_TYPE
            request = urllib.request.Request(
                url, data=payload, method=method,
                headers=request_headers)
            operation = ("download" if blob else "query" if endpoint == QUERY_ENDPOINT else
                         "generation" if endpoint == REPORT_ENDPOINT else
                         "poll" if endpoint == "report-poll" else "consumption")
            self.http_request_counts[operation] = self.http_request_counts.get(operation, 0) + 1
            try:
                with self.opener.open(
                        request, timeout=min(self.request_timeout_seconds, self.remaining())) as response:
                    self.http.append({"status": response.status, "responseMetadata":
                                      response_metadata(response.headers)})
                    if consume is not None:
                        if response.status != 200:
                            raise Failure("unexpected_blob_status", response.status)
                        return consume(response)
                    if not envelope and response.status not in (200, 204):
                        raise Failure("unexpected_http_status", response.status)
                    headers = dict(response.headers.items())
                    chunks, size = [], 0
                    while True:
                        self.guard()
                        self.remaining()
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > 8 * 1024 * 1024:
                            raise Failure("page_byte_limit")
                    raw = b"".join(chunks)
                    if len(raw) > 8 * 1024 * 1024:
                        raise Failure("page_byte_limit")
                    page = json.loads(raw, parse_float=Decimal) if raw else {}
                    if not isinstance(page, dict):
                        raise Failure("http_invalid_json")
                    return (response.status, headers, page) if envelope else page
            except urllib.error.HTTPError as error:
                metadata = response_metadata(error.headers)
                self.http.append({"status": error.code, "responseMetadata": metadata})
                delay = metadata["retryAfterSeconds"]
                if error.code == 429 and attempt < retry_count and delay is not None:
                    if delay <= self.retry_delay_limit and delay + 1 < self.remaining():
                        self.guard()
                        error.close()
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
                except (ValueError, TypeError, AttributeError, OSError, http.client.HTTPException):
                    pass
                finally:
                    error.close()
                raise Failure("rate_limited" if error.code == 429 else "http_error",
                              error.code, azure_code, category, metadata) from None
            except (TimeoutError, socket.timeout):
                raise Failure("http_timeout") from None
            except urllib.error.URLError as error:
                raise Failure("http_timeout" if isinstance(error.reason, TimeoutError)
                              else "network_error") from None
            except (ValueError, UnicodeError):
                raise Failure("http_invalid_json") from None
            except http.client.HTTPException:
                raise Failure("http_incomplete_response") from None


def safe_url(url, code):
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        raise Failure(code)
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
                or parsed.fragment or "%" in parsed.path or "\\" in parsed.path
                or any(part in (".", "..", "") for part in parsed.path[1:].split("/"))):
            raise Failure(code)
        return parsed
    except ValueError:
        raise Failure(code) from None


def compare_operation_locations(original, replacement):
    """Compare in memory only; these diagnostics never authorize a replacement."""
    unavailable = {"available": False, "reason": "invalid_url_or_query"}
    try:
        urls = [safe_url(value, "unsafe_report_url") for value in (original, replacement)]
        if any("#" in value for value in (original, replacement)):
            return unavailable
        params = []
        for url in urls:
            if re.search(r"%(?![0-9a-fA-F]{2})", url.query):
                return unavailable
            query = urllib.parse.parse_qs(url.query, keep_blank_values=True,
                                          strict_parsing=True, max_num_fields=5, errors="strict")
            if ("api-version" not in query or
                    any(not key or len(values) != 1 or not values[0]
                        for key, values in query.items())):
                return unavailable
            params.append(query)
    except (Failure, ValueError, UnicodeError):
        return unavailable
    operation_id = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    pattern = (r"(/subscriptions/" + operation_id + r")/providers/Microsoft\.CostManagement/"
               r"(costDetailsOperationStatus|costDetailsOperationResults|operationResults)/("
               + operation_id + ")")
    operations = [re.fullmatch(pattern, url.path, re.IGNORECASE | re.ASCII) for url in urls]
    if not all(operations):
        return {"available": False, "reason": "unrecognized_operation_path"}
    before, after = urls
    first, second = (match.groups() for match in operations)
    return {
        "available": True,
        "sameHttpsScheme": before.scheme == after.scheme == "https",
        "sameTrustedArmOrigin": before.netloc == after.netloc == "management.azure.com",
        "samePath": before.path == after.path,
        "sameScope": first[0].lower() == second[0].lower(),
        "sameOperationKind": first[1].lower() == second[1].lower(),
        "sameOperationId": first[2].lower() == second[2].lower(),
        "sameApiVersion": params[0].get("api-version") == params[1].get("api-version"),
        "sameQueryFieldSet": params[0].keys() == params[1].keys(),
        "sameQueryValues": params[0] == params[1],
        "signedComponentsChanged": {
            key: params[0].get(key) != params[1].get(key) for key in ("t", "c", "s", "h")},
    }


def validate_blob(url):
    parsed = safe_url(url, "unsafe_blob_link")
    params = urllib.parse.parse_qs(parsed.query)
    if (not re.fullmatch(r"[a-z0-9]{3,24}\.blob\.core\.windows\.net", parsed.netloc)
            or len(parsed.path.strip("/").split("/")) < 2 or len(params.get("sig", [])) != 1):
        raise Failure("unsafe_blob_link")
    return url


def retry_hints(headers, received):
    hints = []
    if received.tzinfo is None or received.utcoffset() is None:
        return hints
    received = received.astimezone(dt.timezone.utc)
    for key, value in (headers or {}).items():
        key = key.lower()
        if key != "retry-after" and not re.fullmatch(
                r"x-ms-ratelimit-microsoft\.costmanagement-[a-z0-9-]{1,80}-retry-after", key):
            continue
        try:
            text = str(value).strip()
            if key == "retry-after" and not re.fullmatch(r"[0-9]+", text):
                day = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
                month = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                clock = r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
                date_match = re.fullmatch(
                        rf"(?:{day}, [0-9]{{2}} {month} [0-9]{{4}} {clock} GMT|"
                        rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
                        rf"[0-9]{{2}}-{month}-(?P<obsolete_year>[0-9]{{2}}) {clock} GMT|"
                        rf"{day} {month} (?: [1-9]|[0-9]{{2}}) {clock} [0-9]{{4}})", text)
                if not date_match:
                    continue
                parsed = email.utils.parsedate_to_datetime(text)
                if date_match["obsolete_year"] is not None:
                    # RFC 9110 uses a receipt-relative 50-year window, not email's fixed pivot.
                    year = (received.year + 50) // 100 * 100 + int(date_match["obsolete_year"])
                    if (year, parsed.month, parsed.day, parsed.time()) > (
                            received.year + 50, received.month, received.day, received.time()):
                        year -= 100
                    parsed = parsed.replace(year=year)
                # The validated obsolete asctime form has implicit GMT.
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                delay = (parsed - received).total_seconds()
                normalized = email.utils.format_datetime(parsed.astimezone(dt.timezone.utc),
                                                        usegmt=True)
            else:
                delay = float(text)
                normalized = format(delay, ".17g")
            if not 0 <= delay < float("inf"):
                continue
            hints.append((key, normalized, delay))
        except (ValueError, TypeError, OverflowError, AttributeError):
            continue
    return hints


def retry_seconds(headers):
    hints = retry_hints(headers, dt.datetime.now(dt.timezone.utc))
    return max(hint[2] for hint in hints) if hints else None


def response_metadata(headers):
    received = dt.datetime.now(dt.timezone.utc)
    hints = retry_hints(headers, received)
    safe = {}
    for key, value, delay in sorted(hints, key=lambda hint: hint[2]):
        safe[key] = value
    for key, value in (headers or {}).items():
        key = key.lower()
        if key in ("x-ms-request-id", "x-ms-correlation-request-id", "request-id"):
            if isinstance(value, str) and re.fullmatch(
                    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
                safe[key] = value
        elif key == "date":
            try:
                parsed = email.utils.parsedate_to_datetime(value)
                if parsed.tzinfo is not None:
                    safe[key] = email.utils.format_datetime(parsed.astimezone(dt.timezone.utc),
                                                           usegmt=True)
            except (ValueError, TypeError, OverflowError, AttributeError):
                pass
    delay = max(hint[2] for hint in hints) if hints else None
    retry_at = None
    if delay is not None:
        try:
            retry_at = (received + dt.timedelta(seconds=delay)).isoformat()
        except OverflowError:
            pass
    return {"receivedAtUtc": received.isoformat(), "safeHeaders": safe,
            "retryAfterSeconds": delay,
            "suggestedRetryAtUtc": retry_at,
            "retrySource": "known" if hints else "unknown"}


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


def query_body(rg, start, end, grouping, meter_category=None, group_by=None,
               include_usage_quantity=False):
    until = min(dt.datetime.combine(day(end), dt.time(23, 59, 59), dt.timezone.utc),
                dt.datetime.now(dt.timezone.utc)).isoformat()
    body = {"type": "ActualCost", "timeframe": "Custom",
            "timePeriod": {"from": start + "T00:00:00Z", "to": until},
            "dataset": {"granularity": "Daily",
                        "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                        "filter": {"dimensions": {"name": "ResourceGroup", "operator": "In",
                                                   "values": [rg]}}}}
    if meter_category:
        body["dataset"]["filter"] = {"and": [
            body["dataset"]["filter"],
            {"dimensions": {"name": "MeterCategory", "operator": "In",
                            "values": [meter_category]}}]}
    if group_by:
        if (len(group_by) > 2 or len(set(group_by)) != len(group_by) or
                any(name not in ("ResourceGroup", "ResourceId", "Meter", "MeterId",
                                 "MeterCategory") for name in group_by)):
            raise Failure("invalid_query_grouping")
        body["dataset"]["grouping"] = [{"type": "Dimension", "name": name} for name in group_by]
    elif grouping != "none":
        body["dataset"]["grouping"] = [{"type": "Dimension", "name": "ResourceGroup"}]
        if grouping != "ResourceGroup":
            body["dataset"]["grouping"].append({"type": "Dimension", "name": grouping})
    if include_usage_quantity:
        if not any(item["name"] in ("Meter", "MeterId")
                   for item in body["dataset"].get("grouping", [])):
            raise Failure("usage_quantity_requires_meter_grouping")
        body["dataset"]["aggregation"]["totalQuantity"] = {
            "name": "UsageQuantity", "function": "Sum"}
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
    if not isinstance(properties, dict):
        raise Failure("query_invalid_schema")
    definitions = properties.get("columns", [])
    source_rows = properties.get("rows", [])
    if (not isinstance(definitions, list) or len(definitions) > 128 or
            not isinstance(source_rows, list) or
            not all(isinstance(column, dict) and "name" in column for column in definitions)):
        raise Failure("query_invalid_schema")
    names = [column["name"] for column in definitions]
    if not all(isinstance(name, str) for name in names):
        raise Failure("query_invalid_schema")
    if len(names) != len(set(names)):
        raise Failure("duplicate_query_columns")
    rows = []
    for row in source_rows:
        if not isinstance(row, list) or len(row) != len(names):
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
    def __init__(self, source, check=None, limit=50 * 1024 * 1024, budget=None,
                 budget_code="report_decoded_byte_limit"):
        self.source, self.check, self.limit, self.size = source, check, limit, 0
        self.budget = budget
        self.budget_code = budget_code

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.check:
            self.check()
        data = self.source.read(min(len(buffer), self.limit - self.size + 1))
        self.size += len(data)
        if self.budget is not None:
            self.budget[0] -= len(data)
            if self.budget[0] < 0:
                raise Failure(self.budget_code)
        if self.size > self.limit:
            raise Failure("report_bounds")
        buffer[:len(data)] = data
        return len(data)


def cost_details_csv_stream(source, subscription, groups, inventory, start, end,
                            max_rows=100000, check=None, schema=None, decoded_budget=None,
                            wire_budget=None, row_budget=None):
    """Stream CSV; only exact-inventory/date/Bandwidth projections survive."""
    if not 1 <= max_rows <= 100000:
        raise Failure("report_bounds")
    subscription = valid_id(subscription)
    wire = BoundedReport(source, check, budget=wire_budget, budget_code="report_wire_byte_limit")
    bounded = io.BufferedReader(wire)
    magic = bounded.peek(4)[:4]
    if magic.startswith(b"\x1f\x8b"):
        import gzip
        bounded = io.BufferedReader(BoundedReport(gzip.GzipFile(fileobj=bounded), check))
    elif magic.startswith(b"PK"):
        archive = zipfile.ZipFile(io.BytesIO(bounded.read()))
        entries = archive.infolist()
        if (len(entries) != 1 or not entries[0].filename.lower().endswith(".csv")
                or entries[0].file_size > 50 * 1024 * 1024 or entries[0].flag_bits & 1):
            raise Failure("report_archive_bounds")
        bounded = io.BufferedReader(BoundedReport(archive.open(entries[0]), check))
    elif magic.lstrip().startswith(b"<"):
        raise Failure("report_not_csv")
    if decoded_budget is not None:
        bounded = io.BufferedReader(BoundedReport(bounded, check, budget=decoded_budget))
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
                  "inventory": 0, "date": 0, "category": 0}, "datasetMaxUsageDate": None,
              "ownedRowsByDate": {}}
    for source in reader:
        if check is not None:
            check()
        result["received"] += 1
        if row_budget is not None:
            row_budget[0] -= 1
            if row_budget[0] < 0:
                raise Failure("report_row_limit")
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
        result["ownedRowsByDate"][date.isoformat()] = (
            result["ownedRowsByDate"].get(date.isoformat(), 0) + 1)
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
            "dateOriginal": value,
            "dateSemantics": "usage_or_purchase_date_not_receipt_date",
            "usageStart": None, "usageEnd": None,
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
        for name in ("usageStart", "usageEnd"):
            original = row.get(name.casefold())
            if original:
                try:
                    dt.datetime.fromisoformat(original.replace("Z", "+00:00"))
                except ValueError:
                    raise Failure("csv_usage_interval_invalid") from None
                result["rows"][-1][name] = original
    result["downloadBytes"] = wire.size
    return result


def collect(transport, args, inventory):
    include_quantity = getattr(args, "include_usage_quantity", False)
    if include_quantity and args.command != "query":
        raise Failure("usage_quantity_requires_query")
    detail = args.command == "details"
    endpoint = "/providers/" + ("Microsoft.Consumption/usageDetails" if detail
                               else "Microsoft.CostManagement/query")
    body = None if detail else query_body(args.resource_group, args.start, args.end, args.grouping,
                                          getattr(args, "meter_category", None),
                                          getattr(args, "group_by", None), include_quantity)
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
    result["ingestionFinal"] = False
    if include_quantity:
        result.update(usageQuantityRequested=True, usageQuantityUnit="NOT_RETURNED")
        quantity_meter = next(item["name"] for item in body["dataset"]["grouping"]
                              if item["name"] in ("Meter", "MeterId"))
    seen_links, seen_records = set(), {}
    for _ in range(args.max_pages):
        transport.remaining()
        if url in seen_links:
            result["reason"] = "continuation_cycle"
            return result
        seen_links.add(url)
        try:
            page = transport.request("GET" if detail else "POST", url, body, endpoint)
        except Failure as error:
            result.update(reason=error.code, httpStatus=error.status, azureCode=error.azure_code,
                          errorCategory=error.category)
            if error.response_metadata is not None:
                result["responseMetadata"] = error.response_metadata
            return result
        result["pages"] += 1
        if detail:
            rows = page.get("value", [])
            result["received"] += len(rows)
            if result["received"] > getattr(args, "max_rows", 100000):
                raise Failure("report_row_limit")
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
            if include_quantity:
                quantity_column = next((column for column in properties.get("columns", [])
                                        if column["name"] == "UsageQuantity"), None)
                if quantity_column is None:
                    raise Failure("query_usage_quantity_column_missing")
                if quantity_column.get("type") != "Number":
                    raise Failure("query_usage_quantity_column_type")
                if quantity_meter not in columns:
                    raise Failure("query_usage_quantity_meter_missing")
            if "columns" in result and set(result["columns"]) != set(columns):
                raise Failure("query_columns_changed")
            result["columns"] = columns
            result["columnDefinitions"] = properties.get("columns", [])
            result["received"] += len(rows)
            if result["received"] > getattr(args, "max_rows", 100000):
                raise Failure("report_row_limit")
            for row in rows:
                resource = row.get("ResourceId")
                if resource is not None:
                    if not isinstance(resource, str):
                        raise Failure("query_scope_unverified")
                    resource = resource.lower().rstrip("/")
                    prefix = f"/subscriptions/{transport.subscription}/resourcegroups/{args.resource_group}/".lower()
                    if not resource.startswith(prefix):
                        result["discarded"] += 1
                        continue
                    if resource not in inventory:
                        result["discarded"] += 1
                        result["unattributedLabRows"] += 1
                        continue
                    row["ResourceId"] = resource
                    row.setdefault("ResourceGroup", resource.split("/")[4])
                elif getattr(args, "group_by", None) and "ResourceId" in args.group_by:
                    raise Failure("query_required_resource_id_missing")
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
                if include_quantity:
                    meter = row[quantity_meter]
                    if not isinstance(meter, str) or not meter.strip():
                        raise Failure("query_usage_quantity_meter_invalid")
                    quantity = row["UsageQuantity"]
                    if (isinstance(quantity, bool) or
                            not isinstance(quantity, (int, float, Decimal)) or
                            not Decimal(str(quantity)).is_finite()):
                        raise Failure("query_usage_quantity_invalid")
                result["rows"].append({key: value for key, value in row.items() if key in (
                    "ResourceGroup", "ResourceId", "Meter", "MeterId", "MeterCategory",
                    "UsageDate", "Currency", "PreTaxCost", "Cost") or
                    (include_quantity and key == "UsageQuantity")})
                if len(result["rows"]) > getattr(args, "max_rows", 100000):
                    raise Failure("report_row_limit")
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
            if error.response_metadata is not None:
                entry["responseMetadata"] = error.response_metadata
        result["results"].append(entry)
    result["expectedTenantMatched"] = transport.context_verified
    return result


def private_path(value):
    path = Path(value).resolve()
    try:
        base = (LAB / "private").resolve()
        if base.parent != LAB.resolve() or base.name.lower() != "private":
            raise Failure("private_root_symlink_not_allowed")
        path.relative_to(base)
    except ValueError:
        raise Failure("output_must_be_lab_private") from None
    return path


def linux_path(value):
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/") if re.match(
        r"^[A-Za-z]:[\\/]", value) else value


def load_inventory(value, subscription, rg):
    data = json.loads(private_path(value).read_text(encoding="utf-8-sig"))
    values = data.get("resourceIds")
    if values is None:
        resources = data.get("resources")
        if not isinstance(resources, list):
            raise Failure("invalid_inventory")
        values = [item.get("id") if isinstance(item, dict) else None for item in resources]
    if not isinstance(values, list) or not values or len(values) > 10000:
        raise Failure("empty_or_invalid_inventory")
    result = set()
    prefix = f"/subscriptions/{subscription}/resourcegroups/{rg}/providers/".lower()
    for value in values:
        if not isinstance(value, str):
            raise Failure("invalid_inventory")
        normalized = value.lower().rstrip("/")
        if (not normalized.startswith(prefix) or "%" in normalized or "\\" in normalized
                or any(c.isspace() or ord(c) < 32 for c in normalized)
                or any(part in ("", ".", "..") for part in normalized[1:].split("/"))):
            raise Failure("inventory_scope_mismatch")
        if normalized in result:
            raise Failure("duplicate_inventory_resource")
        result.add(normalized)
    return result


class InvocationLease:
    """The public CLI owns a distinct bounded lease, never a coordinator's lease."""
    def __init__(self, supplied, seconds, requests):
        self.runtime = LAB / "deploy" / ".runtime-control"
        self.supplied = supplied
        self.path = None
        self.lock = None
        self.data = None
        self.owned_created = False
        self.seconds, self.requests = seconds, requests

    def start(self):
        try:
            self.runtime.resolve().relative_to(LAB.resolve())
        except ValueError:
            raise Failure("runtime_must_be_lab_local") from None
        if self.supplied:
            path = Path(self.supplied).resolve()
            try:
                path.relative_to(self.runtime.resolve())
            except ValueError:
                raise Failure("lease_must_be_lab_runtime") from None
            self.path = path
            supplied = json.loads(path.read_text(encoding="utf-8-sig"))
            if supplied.get("maxMutations") != 0:
                raise Failure("read_only_lease_required")
            self.guard()
            return
        self.runtime.mkdir(parents=True, exist_ok=True)
        lock = self.runtime / "cost-cli-owner.json"
        try:
            with lock.open("x", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid()}, stream)
        except FileExistsError:
            raise Failure("billing_cli_owner_active") from None
        self.lock = lock
        try:
            files = list(self.runtime.glob("*.json"))
            if len(files) > 256:
                raise Failure("runtime_control_file_limit")
            for path in files:
                if not re.search(r"api|billing|cost|manual|usage", path.name, re.I):
                    continue
                if path == lock:
                    continue
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if data.get("state") not in ("active", "stop-requested"):
                    continue
                expiry = dt.datetime.fromisoformat(data["expiresAtUtc"].replace("Z", "+00:00"))
                if expiry > dt.datetime.now(dt.timezone.utc):
                    raise Failure("billing_lease_already_active")
            now = dt.datetime.now(dt.timezone.utc)
            self.path = self.runtime / ("cost-cli-" + uuid.uuid4().hex + ".json")
            self.data = {"taskId": self.path.stem, "ownerRole": "public-cost-cli",
                         "objective": "bounded read-only billing collection",
                         "state": "active", "maxMutations": 0, "actualMutations": 0,
                         "maxToolCalls": self.requests + 1, "actualToolCalls": 0,
                         "maxHttpRequests": self.requests, "actualHttpRequests": 0,
                         "commandTimeoutSeconds": self.seconds,
                         "restoreTimeoutMinutes": 0,
                         "expiresAtUtc": (now + dt.timedelta(seconds=min(1800, self.seconds + 30))).isoformat(),
                         "lastCheckpointUtc": now.isoformat()}
            with self.path.open("x", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2)
            self.owned_created = True
            self.guard()
        except Exception:
            self.close()
            raise

    def guard(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            expiry = dt.datetime.fromisoformat(data["expiresAtUtc"].replace("Z", "+00:00"))
            if ((self.runtime / "STOP").exists() or data["state"] != "active" or
                    expiry <= dt.datetime.now(dt.timezone.utc) or
                    data.get("actualToolCalls", 0) >= data["maxToolCalls"]):
                raise Failure("lease_inactive")
        except (OSError, KeyError, ValueError, TypeError):
            raise Failure("lease_required") from None

    def close(self, transport=None):
        try:
            if self.owned_created:
                self.data.update(state="idle", closedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),
                                 actualHttpRequests=transport.http_requests if transport else 0,
                                 actualToolCalls=transport.http_requests if transport else 0)
                with self.path.open("w", encoding="utf-8") as stream:
                    json.dump(self.data, stream, indent=2)
        finally:
            if self.lock is not None:
                self.lock.unlink(missing_ok=True)
                self.lock = None

    def record(self, transport):
        self.guard()
        if self.data is not None:
            self.data.update(actualHttpRequests=transport.http_requests,
                             actualToolCalls=transport.http_requests,
                             lastCheckpointUtc=dt.datetime.now(dt.timezone.utc).isoformat())
            with self.path.open("w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2)

    def limit_transport(self, transport):
        self.guard()
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        expiry = dt.datetime.fromisoformat(data["expiresAtUtc"].replace("Z", "+00:00"))
        seconds = min(self.seconds, data.get("commandTimeoutSeconds", self.seconds),
                      (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds())
        requests = min(self.requests, data["maxToolCalls"] - data.get("actualToolCalls", 0),
                       data.get("maxHttpRequests", self.requests) - data.get("actualHttpRequests", 0))
        if seconds <= 0 or requests < 1:
            raise Failure("lease_budget_exhausted")
        transport.deadline = min(transport.deadline, time.monotonic() + seconds)
        transport.max_http_requests = min(transport.max_http_requests, requests)


CSV_FIELDS = ("day", "alias", "resourceId", "resourceGroup", "meterCategory", "meterName",
              "quantity", "unit", "effectivePrice", "unitPrice", "cost", "currency",
              "dateOriginal", "usageStart", "usageEnd", "sourceRecordHash")


def write_outputs(data, output, csv_output=None):
    """Stage only filtered data, then publish using exclusive hard links."""
    staged, published = [], []
    try:
        for target, is_csv in ((output, False), (csv_output, True)):
            if target is None:
                continue
            target = private_path(str(target))
            if target.exists():
                raise Failure("snapshot_already_exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            target = private_path(str(target))
            stage = target.with_name("." + uuid.uuid4().hex + ".part")
            with stage.open("x", encoding="utf-8", newline="") as stream:
                staged.append((stage, target))
                if is_csv:
                    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(data["rows"])
                else:
                    json.dump(data, stream, indent=2, default=str)
                stream.flush()
                os.fsync(stream.fileno())
        for stage, target in staged:
            private_path(str(target))
            os.link(stage, target)
            published.append((stage, target))
    except Exception:
        for stage, target in published:
            if target.exists() and os.path.samefile(stage, target):
                target.unlink()
        raise
    finally:
        for stage, _ in staged:
            stage.unlink(missing_ok=True)


def collect_report(transport, args, inventory):
    requested = {"metric": "ActualCost", "timePeriod": {"start": args.start, "end": args.end}}
    result = {"schemaVersion": 2, "metric": "ActualCost", "apiVersion": REPORT_VERSION,
              "state": "INCOMPLETE", "extractionComplete": False, "ingestionFinal": False,
              "request": requested, "localRetention": {"start": args.start, "end": args.end,
                                                     "inclusive": True},
              "reportEndSemantics": "UNKNOWN_NOT_PROOF_OF_FULL_DAY_COVERAGE",
              "generationRequestedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "received": 0, "discarded": 0, "rows": [], "http": transport.http,
              "downloadBytes": 0, "polls": 0, "blobsDownloaded": 0,
              "discardCounts": {"inventory": 0, "date": 0, "category": 0},
              "ownedRowsByDate": {}, "datasetMaxUsageDate": None}
    try:
        status, headers, page = transport.request(
            "POST", ARM + transport.scope + REPORT_ENDPOINT + "?api-version=" + REPORT_VERSION,
            requested, REPORT_ENDPOINT, envelope=True, retries=0)
        location = next((v for k, v in headers.items() if k.lower() == "location"), None)
        if location:
            transport.validate_report(location)
        while status == 202 or str(page.get("status", "")).casefold() in (
                "running", "inprogress", "notstarted", "pending"):
            if not location:
                raise Failure("missing_operation_url")
            if result["polls"] >= args.max_polls:
                raise Failure("poll_limit")
            delay = max(30, retry_seconds(headers) or 30)
            transport.guard()
            if delay + 1 >= transport.remaining():
                raise Failure("pending_deadline")
            time.sleep(delay)
            transport.guard()
            status, headers, page = transport.request(
                "GET", location, endpoint="report-poll", envelope=True)
            result["polls"] += 1
            next_location = next((v for k, v in headers.items() if k.lower() == "location"), None)
            if next_location and next_location != location:
                result["operationLocationComparison"] = compare_operation_locations(
                    location, next_location)
                raise Failure("operation_location_changed")
        if status != 200 or page.get("status") != "Completed":
            error = page.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}", code) else None
            raise Failure("report_provisioning_failed", status, code)
        manifest = page.get("manifest")
        if not isinstance(manifest, dict) or str(manifest.get("dataFormat")).casefold() != "csv":
            raise Failure("unexpected_manifest_format")
        blobs = manifest.get("blobs")
        if (not isinstance(blobs, list) or not blobs or len(blobs) > 20 or
                type(manifest.get("blobCount")) is not int or
                manifest.get("blobCount") != len(blobs) or
                not isinstance(manifest.get("compressData"), bool)):
            raise Failure("invalid_manifest")
        returned = manifest.get("requestContext")
        if returned:
            if not isinstance(returned, dict):
                raise Failure("manifest_context_mismatch")
            scope = str(returned.get("requestScope", "")).strip("/").lower()
            echo = returned.get("requestBody", {})
            if not isinstance(echo, dict) or not isinstance(echo.get("timePeriod"), dict):
                raise Failure("manifest_context_mismatch")
            if (scope != transport.scope.strip("/").lower() or echo.get("metric") != "ActualCost"
                    or any(echo.get(key) for key in ("invoiceId", "billingPeriod"))
                    or any(day(echo.get("timePeriod", {}).get(key, "")) != day(requested["timePeriod"][key])
                           for key in ("start", "end"))):
                raise Failure("manifest_context_mismatch")
            returned_period = {key: echo["timePeriod"][key] for key in ("start", "end")}
            for value in returned_period.values():
                if not isinstance(value, str):
                    raise Failure("manifest_context_mismatch")
                dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            result["returnedPeriod"] = returned_period
        else:
            result["returnedPeriod"] = None
        links, identities = [], set()
        expected_bytes = 0
        for blob in blobs:
            if not isinstance(blob, dict):
                raise Failure("invalid_manifest")
            link = validate_blob(blob.get("blobLink"))
            parsed = urllib.parse.urlsplit(link)
            identity = (parsed.netloc, parsed.path)
            if identity in identities:
                raise Failure("duplicate_report_blob")
            identities.add(identity)
            count = blob.get("byteCount")
            if type(count) is not int or not 0 < count <= 50 * 1024 * 1024:
                raise Failure("manifest_byte_bounds")
            expected_bytes += count
            links.append(link)
        if expected_bytes > 50 * 1024 * 1024 or manifest.get("byteCount", expected_bytes) != expected_bytes:
            raise Failure("manifest_byte_bounds")
        result["manifest"] = {key: manifest.get(key) for key in (
            "blobCount", "byteCount", "dataFormat", "compressData", "manifestVersion")}
        decoded_budget, wire_budget, row_budget = [50 * 1024 * 1024], [50 * 1024 * 1024], [args.max_rows]
        def check():
            transport.guard()
            transport.remaining()
        for blob, link in zip(blobs, links):
            projected = transport.request("GET", link, consume=lambda response:
                cost_details_csv_stream(response, transport.subscription, {"lab": args.resource_group},
                                        inventory, args.start, args.end,
                                        args.max_rows, check, decoded_budget=decoded_budget,
                                        wire_budget=wire_budget, row_budget=row_budget))
            if projected["downloadBytes"] != blob["byteCount"]:
                raise Failure("report_byte_count_mismatch")
            if not all(projected["schemaMapping"][key] for key in (
                    "resourceId", "date", "quantity", "meterCategory", "cost", "currency")):
                raise Failure("csv_required_columns_missing")
            for key in ("received", "discarded", "downloadBytes"):
                result[key] += projected[key]
            result["rows"].extend(projected["rows"])
            result["blobsDownloaded"] += 1
            for key, count in projected["discardCounts"].items():
                result["discardCounts"][key] += count
            for key, count in projected["ownedRowsByDate"].items():
                result["ownedRowsByDate"][key] = result["ownedRowsByDate"].get(key, 0) + count
            result["datasetMaxUsageDate"] = max(result["datasetMaxUsageDate"] or "",
                                                  projected["datasetMaxUsageDate"] or "") or None
        result.update(state="COMPLETE", extractionComplete=True,
                      retained=len(result["rows"]),
                      completedUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    except Failure as error:
        result.update(reason=error.code, httpStatus=error.status, azureCode=error.azure_code)
        if error.response_metadata is not None:
            result["responseMetadata"] = error.response_metadata
    except (csv.Error, UnicodeError, OSError, EOFError, ValueError, TypeError, KeyError,
            zipfile.BadZipFile, zlib.error):
        result.update(reason="report_invalid_data")
    result.update(httpRequests=transport.http_requests,
                  httpRequestCounts=dict(transport.http_request_counts))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "query", "details", "cost-details"])
    parser.add_argument("--transport", choices=["native", "wsl"], default="native")
    parser.add_argument("--distribution", default="Ubuntu-24.04")
    parser.add_argument("--subscription")
    parser.add_argument("--expected-tenant")
    parser.add_argument("--context", help="Ignored private JSON: subscriptionId, expectedTenantId")
    parser.add_argument("--resource-group", help="Defaults to context.resourceGroup; probe uses nonexistent RG")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--inventory", help="Private JSON: resourceIds array or deployment resources objects")
    parser.add_argument("--output", help="New file under this lab's ignored private directory")
    parser.add_argument("--csv-output", help="Required for cost-details: new filtered CSV under lab private/")
    parser.add_argument("--lease", help="Optional existing bounded read-only lease under deploy/.runtime-control")
    parser.add_argument("--offer-alias", choices=["windows-main", "wsl-msdn", "unverified"],
                        default="unverified")
    parser.add_argument("--grouping", choices=["MeterId", "Meter", "MeterCategory", "ResourceGroup", "none"],
                        default="Meter")
    parser.add_argument("--meter-category", help="Explicit Query meter-category filter, e.g. Bandwidth")
    parser.add_argument("--include-usage-quantity", action="store_true",
                        help="Query only: request numeric UsageQuantity per meter; units not returned")
    parser.add_argument("--group-by", nargs="+",
                        choices=["ResourceId", "ResourceGroup", "Meter", "MeterId", "MeterCategory"],
                        help="One or two unique Query dimensions; overrides legacy --grouping")
    parser.add_argument("--filter-variant", choices=["rg-only", "legacy-date", "modern-date"],
                        default="legacy-date")
    parser.add_argument("--literal-keys", action="store_true")
    parser.add_argument("--expand", choices=["meterDetails", "properties/meterDetails"],
                        default="properties/meterDetails")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-seconds", type=int, help="Default query 75, report 300; maximum 1800")
    parser.add_argument("--request-timeout-seconds", type=int, default=20,
                        help="Positive per-request HTTP socket timeout; default 20, bounded by remaining time")
    parser.add_argument("--max-http-requests", type=int, default=6)
    parser.add_argument("--max-polls", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=100000)
    parser.add_argument("--max-retries", type=int, help="429 retries: query default 1, report default 0")
    args = parser.parse_args(argv)
    lease, transport = None, None
    try:
        args.max_seconds = args.max_seconds if args.max_seconds is not None else (
            300 if args.command == "cost-details" else 75)
        args.max_retries = args.max_retries if args.max_retries is not None else (
            0 if args.command == "cost-details" else 1)
        if (args.request_timeout_seconds <= 0 or
                not 1 <= args.max_seconds <= 1800 or not 1 <= args.max_http_requests <= 100 or
                not 1 <= args.max_polls <= 20 or not 1 <= args.max_rows <= 100000 or
                not 0 <= args.max_retries <= 3):
            raise Failure("invalid_bounds")
        if args.include_usage_quantity:
            if args.command != "query":
                raise Failure("usage_quantity_requires_query")
            dimensions = args.group_by or (
                ["ResourceGroup", args.grouping] if args.grouping != "none" else [])
            if args.group_by and (len(dimensions) > 2 or len(set(dimensions)) != len(dimensions)):
                raise Failure("invalid_query_grouping")
            if not any(name in ("Meter", "MeterId") for name in dimensions):
                raise Failure("usage_quantity_requires_meter_grouping")
            if not any(name in ("ResourceId", "ResourceGroup") for name in dimensions):
                raise Failure("collection_requires_scope_grouping")
        if args.transport == "wsl":
            if os.name != "nt":
                raise Failure("wsl_dispatch_requires_windows")
            forwarded = []
            for value in (sys.argv[1:] if argv is None else argv):
                if value.startswith("--") and "=" in value:
                    forwarded.extend(value.split("=", 1))
                else:
                    forwarded.append(value)
            forwarded[forwarded.index("--transport") + 1] = "native"
            for flag in ("--context", "--inventory", "--output", "--csv-output", "--lease"):
                if flag in forwarded:
                    index = forwarded.index(flag) + 1
                    forwarded[index] = linux_path(str(Path(forwarded[index]).resolve()))
            timeout = args.max_seconds + 30
            result = run_bounded(["wsl.exe", "-d", args.distribution, "--exec", "timeout",
                                  "--signal=TERM", "--kill-after=3s", f"{timeout}s", "python3",
                                  linux_path(str(Path(__file__).resolve()))] + forwarded, timeout + 10)
            # The child only emits a sanitized summary; never relay arbitrary stderr.
            try:
                summary = json.loads(result.stdout)
            except (ValueError, UnicodeError):
                raise Failure("wsl_invalid_result") from None
            print(json.dumps(summary))
            return result.returncode
        if args.context:
            context = json.loads(private_path(args.context).read_text(encoding="utf-8-sig"))
            args.subscription = args.subscription or context["subscriptionId"]
            args.expected_tenant = args.expected_tenant or context["expectedTenantId"]
            args.resource_group = args.resource_group or context.get("resourceGroup")
        if args.command == "probe":
            args.resource_group = args.resource_group or "rg-bandwidth-billing-preflight"
        if (not 1 <= args.max_pages <= 20 or not 1 <= args.page_size <= 1000 or
                day(args.start) > day(args.end) or
                args.start != day(args.start).isoformat() or args.end != day(args.end).isoformat() or
                not args.resource_group or
                not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", args.resource_group)):
            raise Failure("invalid_bounds")
        if args.command != "probe" and day(args.end) > dt.datetime.now(dt.timezone.utc).date():
            raise Failure("future_report_date")
        if args.command == "probe" and args.resource_group != "rg-bandwidth-billing-preflight":
            raise Failure("probe_requires_nonexistent_rg")
        if args.command == "query" and args.grouping == "none" and not args.group_by:
            raise Failure("collection_requires_scope_grouping")
        if args.group_by:
            query_body(args.resource_group, args.start, args.end, args.grouping,
                       args.meter_category, args.group_by, args.include_usage_quantity)
            if "ResourceId" not in args.group_by and "ResourceGroup" not in args.group_by:
                raise Failure("collection_requires_scope_grouping")
        transport = Transport(args.subscription, args.expected_tenant, args.max_seconds,
                              request_timeout_seconds=args.request_timeout_seconds)
        transport.max_http_requests = args.max_http_requests
        transport.max_retries = args.max_retries
        transport.retry_delay_limit = float("inf") if args.command == "cost-details" else 2
        inventory = set()
        if args.command in ("details", "cost-details") or (
                args.group_by and "ResourceId" in args.group_by):
            if not args.inventory:
                raise Failure("private_inventory_required")
        if args.inventory:
            inventory = load_inventory(args.inventory, transport.subscription, args.resource_group)
        output = private_path(args.output) if args.output else None
        csv_output = private_path(args.csv_output) if args.csv_output else None
        if args.command == "cost-details" and csv_output is None:
            raise Failure("cost_details_requires_csv_output")
        if csv_output and args.command != "cost-details":
            raise Failure("csv_output_requires_cost_details")
        if args.command != "probe" and output is None:
            raise Failure("collection_requires_private_output")
        if (output and output.exists()) or (csv_output and csv_output.exists()):
            raise Failure("snapshot_already_exists")
        if csv_output and csv_output == output:
            raise Failure("distinct_output_paths_required")
        lease = InvocationLease(args.lease, args.max_seconds, args.max_http_requests)
        lease.start()
        lease.limit_transport(transport)
        transport.guard = lease.guard
        transport.on_http = lambda: lease.record(transport)
        data = (probe(transport, args) if args.command == "probe" else
                collect_report(transport, args, inventory) if args.command == "cost-details" else
                collect(transport, args, inventory))
        data.update(httpRequests=transport.http_requests,
                    httpRequestCounts=dict(transport.http_request_counts))
        if output:
            write_outputs(data, output, csv_output if data.get("state") == "COMPLETE" else None)
        if args.command == "probe":
            print(json.dumps(data, default=str))
            return 0 if all(item["outcome"] == "ACCESS_OK_NOT_BILLING_PROOF"
                            for item in data["results"]) else 2
        if args.command in ("query", "details") and "httpStatus" in data:
            summary = {"state": "ERROR", "code": data["reason"],
                       "httpStatus": data["httpStatus"], "azureCode": data["azureCode"],
                       "errorCategory": data["errorCategory"],
                       "httpRequests": data["httpRequests"],
                       "httpRequestCounts": data["httpRequestCounts"]}
            if "responseMetadata" in data:
                summary["responseMetadata"] = data["responseMetadata"]
            print(json.dumps(summary))
            return 2
        print(json.dumps({key: data[key] for key in (
            "state", "pages", "received", "discarded", "duplicates", "unattributedLabRows",
            "extractionComplete", "ingestionFinal", "retained", "reason", "httpStatus",
            "responseMetadata", "operationLocationComparison", "httpRequests", "httpRequestCounts",
            "usageQuantityRequested", "usageQuantityUnit")
                          if key in data}))
        return 0 if data["state"] == "COMPLETE" else 3
    except subprocess.TimeoutExpired:
        print(json.dumps({"state": "ERROR", "code": "wsl_timeout"}))
        return 2
    except Failure as error:
        summary = {"state": "ERROR", "code": error.code, "httpStatus": error.status,
                   "azureCode": error.azure_code, "errorCategory": error.category}
        if error.response_metadata is not None:
            summary["responseMetadata"] = error.response_metadata
        if transport is not None:
            summary.update(httpRequests=transport.http_requests,
                           httpRequestCounts=dict(transport.http_request_counts))
        print(json.dumps(summary))
        return 2
    except (OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"state": "ERROR", "code": "invalid_input_or_io"}))
        return 2
    finally:
        if lease is not None:
            lease.close(transport)


if __name__ == "__main__":
    sys.exit(main())
