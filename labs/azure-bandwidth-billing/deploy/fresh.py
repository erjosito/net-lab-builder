"""Fresh three-slot infrastructure lifecycle. No traffic or authentication changes."""

import argparse
import base64
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT.parent / "private"
STOP = ROOT / ".runtime-control" / "STOP"
DEADLINE = "2026-10-18T07:33:00Z"
NETWORK = "2024-05-01"
COMPUTE = "2024-07-01"
DISK = "2024-03-02"
GROUP_API = "2022-09-01"
DEPLOY_API = "2022-09-01"
RESOURCE_API = "2021-04-01"
REGIONS = {"A": "swedencentral", "C": "northeurope", "T": "swedencentral"}
CATALOG_NAMES = {f"catalog-{alias.lower()}" for alias in REGIONS}
CREATION_RUNWAY_MINUTES = {
    "creation_validation_submission": 5, "vm_polling": 15, "restore_estimate": 5}
KINDS = {
    "vnet": "Microsoft.Network/virtualNetworks",
    "pip": "Microsoft.Network/publicIPAddresses",
    "nic": "Microsoft.Network/networkInterfaces",
    "nsg": "Microsoft.Network/networkSecurityGroups",
    "subnet-nsg": "Microsoft.Network/networkSecurityGroups",
    "vm": "Microsoft.Compute/virtualMachines",
    "os": "Microsoft.Compute/disks",
}


class Blocked(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


def date(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise Blocked("UTC offset required")
    return result.astimezone(timezone.utc)


def require(condition, message):
    if not condition:
        raise Blocked(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def byte_hash(value):
    return hashlib.sha256(value).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def exclusive_bytes(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name(path.name + "." + uuid.uuid4().hex + ".new")
    try:
        with stage.open("xb") as stream:
            stream.write(value)
        os.link(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def exclusive_json(path, value):
    exclusive_bytes(path, json_bytes(value))


def private_path(value):
    path = Path(value).resolve()
    require(path.is_relative_to(PRIVATE.resolve()), "Evidence path must be inside this lab private directory")
    return path


def write(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, value)


def atomic_json(path, value):
    stage = path.with_suffix(path.suffix + ".new")
    stage.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    # Windows scanners can briefly hold the destination; never retry an ARM operation.
    for attempt in range(5):
        try:
            os.replace(stage, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.05 * (2 ** attempt))


def names(slot):
    alias = slot["slot"].lower()
    run = slot["runId"]
    require(slot["vmName"] == f"{run}-vm-{alias}", "VM name mismatch")
    return {kind: (f"{run}-subnet-policy-{alias}" if kind == "subnet-nsg"
                   else f"{run}-{kind}-{alias}") for kind in KINDS}


def group_id(slot):
    return f'/subscriptions/{slot["subscriptionId"]}/resourceGroups/{slot["resourceGroup"]}'


def expected(slot):
    return {f'{group_id(slot)}/providers/{kind}/{names(slot)[key]}'.lower(): kind
            for key, kind in KINDS.items()}


def resource_tags(slot):
    return {"lab": "true", "created_by": "copilot-lab", "run_id": slot["runId"]}


def catalog_arguments(slot):
    require(slot["slot"] in REGIONS and slot["region"] == REGIONS[slot["slot"]]
            and slot["sku"] == "Standard_B2ts_v2", "Unapproved catalog slot/region/SKU")
    return ["vm", "list-skus", "--location", slot["region"], "--resource-type",
            "virtualMachines", "--size", "Standard_B2ts_v2", "--all"]


def group_tags(slot, created, deadline):
    return {**resource_tags(slot), "createdUtc": created, "cleanupDeadlineUtc": deadline}


def inbound_deny():
    return {"name": "DenyAllInboundUntilHarnessApproved", "properties": {
        "priority": 100, "direction": "Inbound", "access": "Deny", "protocol": "*",
        "sourcePortRange": "*", "destinationPortRange": "*",
        "sourceAddressPrefix": "*", "destinationAddressPrefix": "*"}}


def load_slots(handoff):
    slots = handoff["slots"]
    require(len(slots) == 3 and [s["slot"] for s in slots] == ["A", "C", "T"],
            "Exactly the ordered fresh A/C/T slots are required")
    for slot in slots:
        context = read(private_path(slot["contextPath"]))
        for key in ("runId", "resourceGroup", "subscriptionId"):
            require(context[key] == slot[key], "Context/handoff mismatch")
        require(context["expectedTenantId"] == slot["tenantId"], "Tenant mismatch")
        require(re.fullmatch(r"bwb-[0-9a-f]{12}", slot["runId"]), "Invalid run ID")
        require(slot["resourceGroup"] == "rg-" + slot["runId"], "Group/run mismatch")
        require(slot["vmName"] == f'{slot["runId"]}-vm-{slot["slot"].lower()}', "VM name mismatch")
        require(slot["region"] == REGIONS[slot["slot"]] and slot["sku"] == "Standard_B2ts_v2",
                "Unapproved region or SKU; no fallback")
        for key in ("subscriptionId", "tenantId"):
            require(re.fullmatch(r"[0-9a-fA-F-]{36}", slot[key]), "Invalid identity")
        private_path(slot["inventoryPath"])
    require(len({s["runId"] for s in slots}) == 3, "Duplicate run IDs")
    require(slots[0]["subscriptionId"] == slots[1]["subscriptionId"] != slots[2]["subscriptionId"],
            "Core and MSDN subscription separation required")
    require(slots[0]["tenantId"] == slots[1]["tenantId"] != slots[2]["tenantId"],
            "Core and MSDN tenant separation required")
    return slots


def align_handoff(source, output):
    """Copy planned preflight inputs into a new namespace, without granting authority."""
    source = private_path(source)
    output = private_path(output)
    require(not output.exists(), "Alignment directory exists; never replace inputs")
    raw = source.read_bytes()
    handoff = json.loads(raw.decode("utf-8-sig"))
    aligned = copy.deepcopy(handoff)
    hashes = {str(source): byte_hash(raw)}
    contexts = {}
    for slot in aligned["slots"]:
        alias = slot["slot"].lower()
        canonical = f'{slot["runId"]}-vm-{alias}'
        require(slot["vmName"] in (canonical, f'vm-{slot["runId"]}-{alias}'),
                "Only canonical or legacy planned VM names may be aligned")
        require(not private_path(slot["inventoryPath"]).exists() and not state_path(slot).exists(),
                "Alignment requires planned slots without inventory or ownership receipts")
        path = private_path(slot["contextPath"])
        context_raw = path.read_bytes()
        hashes[str(path)] = byte_hash(context_raw)
        context = json.loads(context_raw.decode("utf-8-sig"))
        require("vmName" not in context or context["vmName"] == slot["vmName"],
                "Context/handoff VM name mismatch")
        context["vmName"] = slot["vmName"] = canonical
        slot["contextPath"] = str(output / (alias + "-context.private.json"))
        slot["inventoryPath"] = str(output / (alias + "-inventory.private.json"))
        contexts[slot["contextPath"]] = context
    aligned["alignment"] = {"sourceHashes": hashes, "alignedAtUtc": stamp(),
                            "canonicalVmNames": {s["slot"]: s["vmName"] for s in aligned["slots"]}}
    aligned["slotsHash"] = digest(aligned["slots"])
    # Validate the new explicit names against the copied context bytes before publication.
    for slot in aligned["slots"]:
        context = contexts[slot["contextPath"]]
        require(all(context[k] == slot[k] for k in ("runId", "resourceGroup", "subscriptionId"))
                and context["expectedTenantId"] == slot["tenantId"], "Context/handoff mismatch")
    for path, sha in hashes.items():
        require(byte_hash(Path(path).read_bytes()) == sha, "Source changed during alignment")
    output.mkdir(parents=True)
    for path, context in contexts.items():
        exclusive_json(path, context)
    load_slots(aligned)
    exclusive_json(output / "handoff.private.json", aligned)


def make_template():
    """Adapt the existing single-VM ARM template; never clone the old A/B/P topology."""
    template = copy.deepcopy(read(ROOT / "msdn-main.json"))
    params = template["parameters"]
    params["vmSize"]["allowedValues"] = ["Standard_B2ts_v2"]
    params.update({
        "endpointAlias": {"type": "string", "allowedValues": ["a", "c", "t"]},
        "location": {"type": "string", "allowedValues": ["swedencentral", "northeurope"]},
        "createdUtc": {"type": "string"},
        "cleanupDeadlineUtc": {"type": "string"},
    })
    template["variables"]["location"] = "[parameters('location')]"
    template["variables"]["tags"] = {
        "lab": "true", "created_by": "copilot-lab", "run_id": "[parameters('runId')]"}
    text = json.dumps(template).replace("'-vnet-t'", "'-vnet-', parameters('endpointAlias')")
    for kind in ("pip", "nsg", "nic", "os"):
        text = text.replace(f"'-{kind}-t'", f"'-{kind}-', parameters('endpointAlias')")
    text = text.replace("concat(parameters('runId'), '-vm-t')",
                        "concat(parameters('runId'), '-vm-', parameters('endpointAlias'))")
    text = text.replace('"bwb-t"', '"[concat(\'bwb-\', parameters(\'endpointAlias\'))]"')
    template = json.loads(text)
    resources = template["resources"]
    next(r for r in resources if r["type"] == KINDS["vm"])["properties"]["storageProfile"]["dataDisks"] = []
    nsg = next(r for r in resources if r["type"] == KINDS["nsg"])
    nsg["properties"]["securityRules"] = [inbound_deny()]
    subnet_nsg = copy.deepcopy(nsg)
    subnet_nsg["properties"]["securityRules"] = []
    subnet_nsg["name"] = "[concat(parameters('runId'), '-subnet-policy-', parameters('endpointAlias'))]"
    resources.insert(0, subnet_nsg)
    vnet = next(r for r in resources if r["type"] == KINDS["vnet"])
    subnet_nsg_id = ("[resourceId('Microsoft.Network/networkSecurityGroups', "
                     "concat(parameters('runId'), '-subnet-policy-', parameters('endpointAlias')))]")
    vnet["dependsOn"] = [subnet_nsg_id]
    vnet["properties"]["subnets"][0]["properties"]["networkSecurityGroup"] = {"id": subnet_nsg_id}
    template["outputs"]["state"]["value"] = "One isolated endpoint; NIC deny inbound; subnet NSG empty; no harness."
    return template


def verify_inventory(slot, state, group, resources, complete=True):
    require(state.get("absenceProven") is True and state.get("createdVerified") is True,
            "No durable absence and successful creation proof")
    require(state["slotHash"] == digest(slot) and state["ownershipHash"] == digest(state["ownership"]),
            "Ownership record tampered or context changed")
    require(group["id"].lower() == group_id(slot).lower(), "Unexpected group ID")
    require(state["ownership"] == group_tags(slot, state["ownership"]["createdUtc"],
                                            state["ownership"]["cleanupDeadlineUtc"]),
            "Invalid group ownership receipt")
    require(group.get("tags") == state["ownership"],
            "Group ownership tags changed")
    allowed = expected(slot)
    seen = set()
    for resource in resources:
        rid = resource["id"].lower()
        require(rid in allowed and rid not in seen, "Unknown or duplicate resource; whole-group deletion blocked")
        require(resource["type"].lower() == allowed[rid].lower(), "Resource type mismatch")
        require(resource["name"].lower() == rid.rsplit("/", 1)[-1], "Resource name mismatch")
        require(resource["location"] == slot["region"], "Resource region mismatch")
        require(resource.get("tags") == resource_tags(slot),
                "Resource ownership tags changed")
        seen.add(rid)
    require(not complete or seen == set(allowed), "Incomplete deployed inventory")
    return resources


class Lease:
    def __init__(self, path, action):
        self.path = Path(path).resolve()
        require(self.path.parent == (ROOT / ".runtime-control").resolve(), "Lease must be in runtime-control")
        self.action = action
        self.check()

    def check(self, new=False, restore=False):
        lease = read(self.path)
        start, end = date(lease["startedAtUtc"]), date(lease["expiresAtUtc"])
        require(not STOP.exists() and lease["state"] == "active", "STOP or inactive lease")
        require(start <= now() < end and end - start <= timedelta(minutes=60), "Lease expired/invalid")
        require(lease["action"] == self.action and lease["ownerRole"] == "Tank", "Wrong lease objective")
        if restore:
            require("restoreStartedAtUtc" not in lease or
                    now() < date(lease["restoreStartedAtUtc"]) + timedelta(minutes=lease["restoreTimeoutMinutes"]),
                    "Restore budget expired; fresh recovery owner required")
        require(0 < lease["maxToolCalls"] <= 150 and 0 <= lease["maxMutations"] <= 12,
                "Lease limits exceed hard bounds")
        require(0 < lease["commandTimeoutSeconds"] <= 1200
                and 0 < lease["restoreTimeoutMinutes"] <= 15, "Invalid timeout limits")
        named = lease.get("namedCommandTimeoutSeconds", {})
        require(type(named) is dict and all(
            key in CATALOG_NAMES and type(value) is int and 0 < value <= 600
            for key, value in named.items()), "Invalid named command timeout allowance")
        require(lease["actualToolCalls"] < lease["maxToolCalls"], "Call budget exhausted")
        if new and not restore:
            require(now() < start + (end - start) * .8
                    and lease["actualToolCalls"] < .8 * lease["maxToolCalls"]
                    and (not lease["maxMutations"]
                         or lease["actualMutations"] < .8 * lease["maxMutations"]),
                    "80 percent boundary: checkpoint and fresh recovery lease required")
        return lease

    def save(self, lease):
        atomic_json(self.path, lease)

    def reserve(self, operation=None, restore=False, diagnostic=None):
        lease = self.check(new=True, restore=restore)
        if operation:
            require(operation in lease["allowedMutations"], "Mutation not explicitly authorized")
            require(lease["actualMutations"] < lease["maxMutations"], "Mutation maximum reached")
            lease["actualMutations"] += 1
        lease["actualToolCalls"] += 1
        lease["ownedProcessesIdle"] = False
        lease["lastCheckpointUtc"] = stamp()
        lease["currentCommand"] = diagnostic or ("mutation" if operation else "read")
        lease["lastCommandKind"] = "diagnostic-readonly" if diagnostic else (
            "mutation" if operation else "read")
        lease["lastRole"] = lease["ownerRole"]
        self.save(lease)
        return lease

    def creation_runway(self):
        lease = self.check(new=True)
        phase_end = min(date(lease["expiresAtUtc"]),
                        date(lease["startedAtUtc"]) + timedelta(minutes=60))
        require((phase_end - now()).total_seconds() >=
                60 * sum(CREATION_RUNWAY_MINUTES.values()),
                "Insufficient creation/validation/deployment/restore runway; no group creation")

    def idle(self):
        lease = read(self.path)
        lease["ownedProcessesIdle"] = True
        lease["lastCheckpointUtc"] = stamp()
        self.save(lease)

    def finish(self, status):
        lease = read(self.path)
        lease.update(state=status, ownedProcessesIdle=True, lastCheckpointUtc=stamp())
        self.save(lease)


def wsl_path(path):
    value = str(Path(path).resolve())
    require(re.match(r"^[a-zA-Z]:\\", value), "WSL input must be an absolute drive path")
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")


def cli_prefix(slot, config):
    if slot["slot"] == "T":
        require(config["msdnCliArgvPrefix"] == ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "/usr/bin/az"],
                "Unapproved WSL CLI backend")
        return config["msdnCliArgvPrefix"]
    az = Path(config["nativeCoreCli"])
    require(az.name.lower() == "az.cmd", "Expected native Windows CLI entry point")
    python = az.parent.parent / "python.exe"
    require(python.is_file(), "Installed Azure CLI Python unavailable; do not install")
    return [str(python), "-m", "azure.cli"]


def kill_tree(process):
    if process.poll() is not None:
        return
    # No detached shells; taskkill targets only this exact process tree.
    if os.name == "nt":
        try:
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
    else:
        process.kill()
    process.wait(timeout=10)


class Azure:
    def __init__(self, handoff, lease):
        self.config, self.lease = handoff, lease
        self.approval = None
        self.created_groups = {}
        self.creation_intents = {}
        self.attempt_output = None
        self.handoff_path = None
        self.gate_path = None
        self.initial_config_hash = digest(handoff)
        self.context_hashes = {s["contextPath"]: byte_hash(private_path(s["contextPath"]).read_bytes())
                               for s in handoff["slots"]}

    def before_mutation(self, slot, restore=False):
        self.identity(slot, restore=restore)
        require(digest(self.config) == self.initial_config_hash, "Backend/context configuration changed")
        for path, sha in self.context_hashes.items():
            require(byte_hash(private_path(path).read_bytes()) == sha, "Context source changed")
        if self.approval is not None:
            self.approval.check()

    def cli(self, slot, arguments, operation=None, restore=False, missing=None, diagnostic=None):
        if diagnostic is not None:
            require(diagnostic == f'catalog-{slot["slot"].lower()}'
                    and diagnostic in CATALOG_NAMES and not operation and not restore
                    and arguments == catalog_arguments(slot), "Invalid named catalog diagnostic")
        if operation:
            self.before_mutation(slot, restore)
        if operation == "create-group-a":
            self.lease.creation_runway()
        lease = self.lease.reserve(operation, restore, diagnostic)
        maximum = lease.get("namedCommandTimeoutSeconds", {}).get(diagnostic, 120) if diagnostic else 120
        seconds = min(lease["commandTimeoutSeconds"], maximum,
                      (date(lease["expiresAtUtc"]) - now()).total_seconds())
        require(seconds > 0, "No command time remaining")
        command_deadline = time.monotonic() + seconds
        process = None
        try:
            if operation and operation.startswith(("validate-", "deploy-")):
                require(self.approval is not None, "Reviewed ARM input capture required")
                arguments = self.approval.submission(slot, arguments)
            command = cli_prefix(slot, self.config) + arguments + [
                "--subscription", slot["subscriptionId"], "--only-show-errors", "--output", "json"]
            if slot["slot"] == "T":
                require(seconds >= 15, "Insufficient time for bounded WSL child shutdown")
                command = command[:4] + ["/usr/bin/timeout", "--kill-after=5s",
                                         str(int(seconds) - 10) + "s"] + command[4:]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while True:
                self.lease.check(restore=restore)
                remaining = command_deadline - time.monotonic()
                require(remaining > 0, "Azure CLI timeout; exact child tree terminated; no retry")
                try:
                    # communicate drains both pipes and retains prior bytes across timeouts.
                    out, err = process.communicate(timeout=min(2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            require(time.monotonic() <= command_deadline,
                    "Azure CLI timeout; exact child tree terminated; no retry")
            self.lease.check(restore=restore)
            if process.returncode:
                text = err.decode("utf-8", errors="replace")
                if missing and re.search(r"\b" + re.escape(missing) + r"\b", text):
                    return None
                raise Blocked("Azure CLI failed; no retry. Private checkpoint retained; fresh owner required")
            return json.loads(out.decode("utf-8-sig")) if out.strip() else None
        except subprocess.TimeoutExpired:
            raise Blocked("Azure CLI timeout; exact child tree terminated; no retry") from None
        finally:
            if process is not None:
                kill_tree(process)
            self.lease.idle()

    def get(self, slot, resource, version=GROUP_API, missing=None, restore=False):
        require((resource.lower() == group_id(slot).lower()
                 or resource.lower().startswith(group_id(slot).lower() + "/"))
                and "?" not in resource and ".." not in resource, "GET outside exact owned group")
        return self.cli(slot, ["rest", "--method", "get", "--url",
                              f"https://management.azure.com{resource}?api-version={version}"],
                        missing=missing, restore=restore)

    def identity(self, slot, restore=False):
        value = self.cli(slot, ["account", "show"], restore=restore)
        require(isinstance(value, dict)
                and value.get("id") == slot["subscriptionId"]
                and value.get("tenantId") == slot["tenantId"]
                and value.get("state") == "Enabled", "CLI backend/subscription/tenant mismatch")
        token = self.cli(slot, ["account", "get-access-token", "--resource",
                                "https://management.azure.com/"], restore=restore)
        try:
            require(isinstance(token, dict)
                    and token.get("subscription") == slot["subscriptionId"]
                    and token.get("tenant") == slot["tenantId"]
                    and token.get("tokenType") == "Bearer"
                    and isinstance(token.get("accessToken"), str)
                    and token["accessToken"].strip(), "ARM token identity mismatch")
            parts = token["accessToken"].split(".")
            require(len(parts) == 3 and all(re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parts),
                    "Malformed ARM token")
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            require(isinstance(claims, dict) and claims.get("tid") == slot["tenantId"]
                    and claims.get("aud") in ("https://management.azure.com/",
                                               "https://management.core.windows.net/")
                    and type(claims.get("exp")) is int
                    and claims["exp"] > now().timestamp() + 120
                    and str(token["expires_on"]).isdigit()
                    and int(token["expires_on"]) > now().timestamp() + 120
                    and (claims.get("nbf") is None or
                         type(claims["nbf"]) is int and claims["nbf"] <= now().timestamp()),
                    "Expired or mismatched ARM token")
        except (KeyError, ValueError, TypeError):
            raise Blocked("Malformed ARM token") from None
        finally:
            # Only proof of successful validation survives; never retain token material.
            token = None

    def group(self, slot, missing=False, restore=False):
        return self.get(slot, group_id(slot), missing="ResourceGroupNotFound" if missing else None,
                        restore=restore)

    def roots(self, slot, restore=False):
        value = self.get(slot, group_id(slot) + "/resources", RESOURCE_API, restore=restore)
        require(not value.get("nextLink"), "Unexpected paginated inventory; freeze")
        return value["value"]

    def poll(self, slot, resource, version, mode, restore=False):
        lease = self.lease.check(restore=restore)
        limit = min(date(lease["expiresAtUtc"]), now() + timedelta(
            minutes=lease["restoreTimeoutMinutes"] if restore else 15))
        last, changed = None, now()
        while now() < limit:
            self.lease.check(restore=restore)
            value = self.get(slot, resource, version,
                             missing="ResourceGroupNotFound" if mode == "deleted" else None,
                             restore=restore)
            if mode == "deleted" and value is None:
                return
            if mode == "deleted":
                status = value.get("properties", {}).get("provisioningState", "Deleting")
            elif mode == "deallocated":
                status = next((s["code"] for s in value["statuses"]
                               if s["code"].startswith("PowerState/")), "pending")
                if status == "PowerState/deallocated":
                    return value
            else:
                status = value["properties"]["provisioningState"]
                if status == "Succeeded":
                    return value
                require(status not in ("Failed", "Canceled"), "Deployment failed; fresh recovery owner required")
            if status != last:
                last, changed = status, now()
            require(now() - changed < timedelta(minutes=10), "No progress for ten minutes")
            require(now() + timedelta(seconds=30) < limit, "Polling deadline; fresh recovery owner required")
            self.lease.check(restore=restore)
            time.sleep(30)
        raise Blocked("Polling deadline reached")


def validate_gate(gate, slots, lease):
    current = now()
    for field in ("pricesVerifiedAtUtc", "fxVerifiedAtUtc", "approvedAtUtc"):
        require(current - timedelta(hours=1) <= date(gate[field]) <= current,
                "Missing/stale future-owner cost approval or price/FX refresh")
        require(date(gate[field]).date() == current.date(), "Refresh approval on UTC day boundary")
    require(gate["reviewPassed"] is True and gate["deploymentApproved"] is True,
            "Future owner review and deployment approval required")
    require(gate["handoffHash"] == digest(slots), "Gate not bound to exact fresh slots")
    require(gate["combinedCapUSD"] == 45 and gate["coreCapUSD"] == 23
            and gate["msdnCapUSDEquivalent"] == 22 and gate["msdnCapEUR"] <= 19.62,
            "Approved caps must not be raised")
    fx = gate["usdPerEur"]
    require(isinstance(fx, (float, int)) and fx > 0
            and gate["msdnCapEUR"] * fx <= 22.000001, "Invalid currency/FX cap")
    require(gate["wireGBPerContextMaximum"] == 220 and gate["payloadGBPerDirection"] == 100
            and gate["allocatedHoursPerSlotMaximum"] == 12 and gate["resourceTTLHoursMaximum"] == 48,
            "Payload, wire or lifetime limits differ from approved contract")
    require(gate["coreBillingCurrency"] == "USD" and gate["msdnBillingCurrency"] == "EUR",
            "Unknown billing currency")
    prices = gate["prices"]
    require(set(prices) == {"A", "C", "T"}, "Three exact price records required")
    costs = {}
    for alias in REGIONS:
        p = prices[alias]
        require(p["currency"] == ("EUR" if alias == "T" else "USD")
                and p["region"] == REGIONS[alias] and p["sku"] == "Standard_B2ts_v2",
                "Price currency/SKU/region mismatch")
        for key in ("computePerHour", "diskPerMonth", "diskOperationsPer10000", "pipPerHour",
                    "internetWorstPerGB"):
            require(isinstance(p[key], (float, int)) and p[key] > 0, "Unknown/nonpositive price")
        require(p["internetWorstPerGB"] >= (.0766 if alias == "T" else .087),
                "Do not assume a free tier or a reduced internet rate")
        costs[alias] = (12 * p["computePerHour"] + 48 * p["diskPerMonth"] / 672
                        + 48 * p["pipPerHour"] + 48 * 61000 / 10000 * p["diskOperationsPer10000"])
    core = 220 * max(prices[a]["internetWorstPerGB"] for a in ("A", "C")) + 2.5
    msdn = 220 * max(prices["T"]["internetWorstPerGB"], .087 / fx) + 2.5 / fx
    require(core <= 23 and msdn <= gate["msdnCapEUR"] and core + msdn * fx <= 45,
            "Full traffic plus conservative infrastructure exceeds approved caps")
    require(costs["A"] + costs["C"] <= 2.5 and costs["T"] * fx <= 2.5,
            "Infrastructure exceeds reserved envelope")
    require(current < date(gate["cleanupDeadlineUtc"]) <= date(DEADLINE)
            and date(gate["cleanupDeadlineUtc"]) <= current + timedelta(hours=48),
            "Cleanup deadline missing/expired/extended")
    evidence = {}
    for path, sha in gate["evidenceHashes"].items():
        require(hashlib.sha256(private_path(path).read_bytes()).hexdigest() == sha,
                "Private price/FX evidence hash mismatch")
        require(Path(path).name not in evidence, "Duplicate evidence basename")
        evidence[Path(path).name] = read(path)
    verify_prices(evidence, prices, fx)
    require(lease["maxMutations"] == 12 and lease["actualMutations"] == 0
            and lease["actualToolCalls"] == 0, "Fresh deployment needs exactly twelve reserved mutations")
    require(set(lease["allowedMutations"]) == {
        f"{verb}-{a.lower()}" for a in REGIONS for verb in ("create-group", "validate", "deploy", "deallocate")},
        "Lease must authorize only the twelve explicit operations")


def verify_prices(evidence, prices, fx):
    required = {f"{kind}-{currency}.json" for kind in ("compute", "disk", "pip", "bandwidth")
                for currency in ("USD", "EUR")} | {"fx-source.json", "disk-cap-source.json"}
    require(required <= set(evidence), "Missing exact USD/EUR retail, FX or disk-cap evidence")
    for name in required:
        value = evidence[name]
        require(now() - timedelta(hours=1) <= date(value["retrievedAtUtc"]) <= now()
                and date(value["retrievedAtUtc"]).date() == now().date(), "Underlying price/FX evidence stale")
        if "-source" not in name:
            require(value["incomplete"] is False and not value["response"].get("NextPageLink")
                    and value["url"].startswith("https://prices.azure.com/api/retail/prices"),
                    "Incomplete or unexpected retail evidence")
    source = evidence["fx-source.json"]
    require(source["source"] == "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
            and float(source["usdPerEur"]) == fx
            and 0 <= (now().date() - datetime.fromisoformat(source["quoteDate"]).date()).days <= 4,
            "FX source/quote mismatch")
    disk_cap = evidence["disk-cap-source.json"]
    require(disk_cap["conservativeTransactionsPerHourUsed"] >= 61000 and disk_cap["E4GiB"] == 32,
            "Disk operations cap source invalid")
    selectors = {
        "computePerHour": ("compute", "Virtual Machines Bsv2 Series", "B2ts v2", "1 Hour"),
        "diskPerMonth": ("disk", "Standard SSD Managed Disks", "E4 LRS Disk", "1/Month"),
        "diskOperationsPer10000": ("disk", "Standard SSD Managed Disks", "E4 LRS Disk Operations", "10K"),
        "pipPerHour": ("pip", "IP Addresses", "Standard IPv4 Static Public IP", "1 Hour"),
        "internetWorstPerGB": ("bandwidth", "Rtn Preference: MGN", "Standard Data Transfer Out", "1 GB"),
    }
    for alias, price in prices.items():
        currency = price["currency"]
        for key, (kind, product, meter, unit) in selectors.items():
            response = evidence[f"{kind}-{currency}.json"]["response"]
            require(response["BillingCurrency"] == currency, "Evidence currency mismatch")
            candidates = [x["retailPrice"] for x in response["Items"]
                          if x["currencyCode"] == currency and x["type"] == "Consumption"
                          and x["productName"] == product and x["meterName"] == meter
                          and x["unitOfMeasure"] == unit
                          and (x.get("location") == "Zone 1" or x["armRegionName"] == REGIONS[alias]
                               if kind == "bandwidth"
                               else x["armRegionName"] == REGIONS[alias])]
            require(candidates and price[key] >= max(candidates), "Price below exact current retail meter")


def state_path(slot):
    return private_path(slot["inventoryPath"]).with_name(slot["slot"].lower() + "-ownership.private.json")


def read_state(slot):
    state = read(state_path(slot))
    require(state["slotHash"] == digest(slot), "Ownership state belongs to another slot")
    return state


def save_inventory(azure, slot, state, complete=True, restore=False):
    group = azure.group(slot, restore=restore)
    resources = azure.roots(slot, restore=restore)
    inventory = {"runId": slot["runId"], "groupId": group_id(slot), "capturedAtUtc": stamp(),
                 "resources": resources, "ownershipHash": state["ownershipHash"], "ready": False}
    verify_inventory(slot, state, group, resources, complete)
    if complete:
        inventory["bindings"] = verify_bindings(azure, slot, restore)
    inventory["ready"] = complete
    if complete:
        path = private_path(slot["inventoryPath"])
        if path.exists():
            require(azure.lease.action != "deploy", "Inventory conflict; never replace a verified snapshot")
            path = path.with_name(path.stem + "-capture-" + uuid.uuid4().hex + ".json")
        exclusive_json(path, inventory)
    return inventory


def verify_bindings(azure, slot, restore=False):
    ids = {key: f'{group_id(slot)}/providers/{kind}/{names(slot)[key]}' for key, kind in KINDS.items()}
    nic = azure.get(slot, ids["nic"], NETWORK, restore=restore)
    vnet = azure.get(slot, ids["vnet"], NETWORK, restore=restore)
    vm = azure.get(slot, ids["vm"], COMPUTE, restore=restore)
    np = nic["properties"]
    ipconfigs = np["ipConfigurations"]
    require(len(ipconfigs) == 1, "Unexpected NIC IP configurations")
    ipconfig = ipconfigs[0]["properties"]
    subnets = vnet["properties"]["subnets"]
    require(len(subnets) == 1 and subnets[0]["name"] == "lab", "Unexpected subnet")
    subnet = subnets[0]["properties"]
    require(np["networkSecurityGroup"]["id"].lower() == ids["nsg"].lower()
            and subnet["networkSecurityGroup"]["id"].lower() == ids["subnet-nsg"].lower()
            and ipconfig["subnet"]["id"].lower() == (ids["vnet"] + "/subnets/lab").lower()
            and ipconfig["publicIPAddress"]["id"].lower() == ids["pip"].lower(),
            "NIC/subnet/PIP ownership binding mismatch")
    require(not vnet["properties"].get("virtualNetworkPeerings")
            and not subnet.get("natGateway") and not subnet.get("routeTable")
            and subnet.get("defaultOutboundAccess") is False,
            "Unexpected peering/NAT/route table or implicit outbound")
    require(not np.get("enableIPForwarding") and not np.get("enableAcceleratedNetworking")
            and not np.get("ipConfigurations", [{}])[0].get("properties", {}).get("loadBalancerBackendAddressPools"),
            "Unexpected NIC forwarding/acceleration/load balancer")
    vp = vm["properties"]
    require(vp["hardwareProfile"]["vmSize"] == slot["sku"] and not vm.get("zones")
            and vp.get("priority", "Regular") == "Regular", "Unexpected SKU/zone/Spot")
    vnics = vp["networkProfile"]["networkInterfaces"]
    storage = vp.get("storageProfile")
    require(isinstance(storage, dict), "Missing VM storage profile")
    os_disk = storage.get("osDisk")
    require(isinstance(os_disk, dict), "Missing VM OS disk reference")
    managed = os_disk.get("managedDisk")
    require(isinstance(managed, dict) and isinstance(managed.get("id"), str)
            and len(vnics) == 1 and vnics[0]["id"].lower() == ids["nic"].lower()
            and managed["id"].lower() == ids["os"].lower(),
            "VM NIC/disk binding mismatch")
    require(type(storage.get("dataDisks")) is list and storage["dataDisks"] == [],
            "Unexpected data disks")
    # VM GET returns a reference, not necessarily the disk's size or SKU.
    disk = azure.get(slot, ids["os"], DISK, restore=restore)
    require(isinstance(disk, dict)
            and isinstance(disk.get("id"), str) and disk["id"].lower() == ids["os"].lower()
            and isinstance(disk.get("type"), str) and disk["type"].lower() == KINDS["os"].lower()
            and disk.get("name") == names(slot)["os"]
            and disk.get("tags") == resource_tags(slot) and disk.get("location") == slot["region"]
            and isinstance(disk.get("managedBy"), str)
            and disk["managedBy"].lower() == ids["vm"].lower(),
            "OS disk ownership/VM binding mismatch")
    properties, sku = disk.get("properties"), disk.get("sku")
    require(isinstance(properties, dict) and type(properties.get("diskSizeGB")) is int
            and properties["diskSizeGB"] == 30
            and isinstance(sku, dict) and sku.get("name") == "StandardSSD_LRS",
            "Unexpected authoritative OS disk size/SKU")
    require(("diskSizeGB" not in os_disk
             or type(os_disk["diskSizeGB"]) is int and os_disk["diskSizeGB"] == properties["diskSizeGB"])
            and ("storageAccountType" not in managed or managed["storageAccountType"] == sku["name"]),
            "VM OS disk reference contradicts authoritative disk")
    for key in ("nsg", "subnet-nsg"):
        nsg = azure.get(slot, ids[key], NETWORK, restore=restore)
        rules = nsg["properties"]["securityRules"]
        observed = [{"name": rule["name"], "properties": {
            k: v for k, v in rule["properties"].items()
            if k != "provisioningState" and v is not None and v != []}} for rule in rules]
        require(observed == ([inbound_deny()] if key == "nsg" else []),
                "NIC deny/subnet empty baseline changed; readiness blocked")
    return ids


def deployment_parameters(slot, state, public_key):
    return {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
            "contentVersion": "1.0.0.0", "parameters": {k: {"value": v} for k, v in {
                "runId": slot["runId"], "vmSize": slot["sku"], "adminPublicKey": public_key,
                "endpointAlias": slot["slot"].lower(), "location": slot["region"],
                "createdUtc": state["ownership"]["createdUtc"],
                "cleanupDeadlineUtc": state["ownership"]["cleanupDeadlineUtc"]}.items()}}


def arm_file(slot, path):
    return wsl_path(path) if slot["slot"] == "T" else str(path)


APPROVAL_FIELDS = {"reviewPassed", "deploymentApproved", "approvedAtUtc",
                   "preparedInputsPath", "approvedInputsHash"}
LEASE_PROGRESS = {"actualToolCalls", "actualMutations", "ownedProcessesIdle",
                  "lastCheckpointUtc", "restoreStartedAtUtc", "currentCommand",
                  "lastCommandKind", "lastRole"}


def quote_binding(gate):
    return digest({k: v for k, v in gate.items() if k not in APPROVAL_FIELDS})


def prepare(handoff, gate, output, handoff_path):
    """Capture reviewable bytes offline; this never grants deployment approval."""
    slots = load_slots(handoff)
    require(gate.get("reviewPassed") is False and gate.get("deploymentApproved") is False,
            "Prepare needs an unapproved gate; never regenerate approved inputs")
    require(not output.exists(), "Preparation directory exists; never replace reviewed inputs")
    key_path = Path(gate["sshPublicKeyPath"])
    require(key_path.suffix == ".pub" and key_path.is_file(), "Existing public key required")
    public_key = key_path.read_text(encoding="utf-8").strip()
    require(re.fullmatch(r"(ssh-rsa|ssh-ed25519|ecdsa-sha2-nistp256) [A-Za-z0-9+/=]+(?: [^\r\n]+)?", public_key),
            "Invalid SSH public key")
    created = stamp()
    require(now() < date(gate["cleanupDeadlineUtc"]) <= date(DEADLINE), "Invalid cleanup deadline")
    deadline = min(date(gate["cleanupDeadlineUtc"]), now() + timedelta(hours=48)).isoformat()
    sources = [Path(__file__).resolve(), ROOT / "msdn-main.json", private_path(handoff_path),
               key_path] + [private_path(s["contextPath"]) for s in slots]
    sources += [private_path(p) for p in gate["evidenceHashes"]]
    source_hashes = {str(p.resolve()): byte_hash(p.read_bytes()) for p in sources}
    require(read(handoff_path) == handoff, "Handoff changed during preparation")
    output.mkdir(parents=True)
    template_path = output / "single-vm.private.json"
    exclusive_json(template_path, make_template())
    files = {str(template_path): byte_hash(template_path.read_bytes())}
    parameters = {}
    for slot in slots:
        alias = slot["slot"].lower()
        parameters[alias] = str(output / (alias + "-parameters.private.json"))
        state = {"ownership": group_tags(slot, created, deadline)}
        exclusive_json(parameters[alias], deployment_parameters(slot, state, public_key))
        files[parameters[alias]] = byte_hash(Path(parameters[alias]).read_bytes())
    capture = {"preparedAtUtc": created, "handoff": handoff, "quoteHash": quote_binding(gate),
               "sourceHashes": source_hashes, "fileHashes": files,
               "templatePath": str(template_path), "parameterPaths": parameters}
    for path, sha in source_hashes.items():
        require(byte_hash(Path(path).read_bytes()) == sha, "Source changed during preparation")
    exclusive_json(output / "approval.private.json", capture)


class ApprovedInputs:
    def __init__(self, azure, slots, gate):
        self.azure, self.slots, self.gate = azure, slots, gate
        capture_path = private_path(gate["preparedInputsPath"])
        raw = capture_path.read_bytes()
        require(byte_hash(raw) == gate["approvedInputsHash"], "Approved input capture hash mismatch")
        self.capture = json.loads(raw)
        require(self.capture["handoff"] == azure.config and self.capture["handoff"]["slots"] == slots,
                "Approved handoff/backend mismatch")
        require(self.capture["quoteHash"] == quote_binding(gate), "Approved quote/limits changed")
        prepared = date(self.capture["preparedAtUtc"])
        require(now() - timedelta(hours=1) <= prepared <= date(gate["approvedAtUtc"]) <= now(),
                "Preparation must precede fresh operator approval")
        self.gate_hash, self.config_hash, self.slot_hash = digest(gate), digest(azure.config), digest(slots)
        self.lease_hash = self.lease_binding()
        self.hashes = {str(capture_path): byte_hash(raw), **self.capture["sourceHashes"],
                       **self.capture["fileHashes"]}
        require(azure.handoff_path is not None, "Exact preflight handoff file binding required")
        required_sources = {str(Path(__file__).resolve()), str((ROOT / "msdn-main.json").resolve()),
                            str(private_path(azure.handoff_path)),
                            str(Path(gate["sshPublicKeyPath"]).resolve())}
        required_sources |= {str(private_path(s["contextPath"])) for s in slots}
        required_sources |= {str(private_path(p)) for p in gate["evidenceHashes"]}
        require(set(self.capture["sourceHashes"]) == required_sources,
                "Approved source/context/evidence hashes missing or unexpected")
        require(set(self.capture["parameterPaths"]) == {"a", "c", "t"},
                "Approved parameters missing")
        required_files = {self.capture["templatePath"], *self.capture["parameterPaths"].values()}
        require(set(self.capture["fileHashes"]) == required_files and len(required_files) == 4
                and all(private_path(p).parent == capture_path.parent for p in required_files),
                "Approved ARM files must be four distinct private capture files")
        if azure.gate_path is not None:
            self.hashes[str(private_path(azure.gate_path))] = byte_hash(Path(azure.gate_path).read_bytes())
            require(read(azure.gate_path) == gate, "Gate file differs from approved gate")
        self.check()
        self.template = self.read_file(self.capture["templatePath"])
        self.parameters = {a: self.read_file(p) for a, p in self.capture["parameterPaths"].items()}
        require(json.loads(self.template) == make_template(), "Approved template differs from pinned source")
        public_key = Path(gate["sshPublicKeyPath"]).read_text(encoding="utf-8").strip()
        deadline = min(date(gate["cleanupDeadlineUtc"]), date(DEADLINE),
                       prepared + timedelta(hours=48)).isoformat()
        for slot in slots:
            expected_state = {"ownership": group_tags(slot, self.capture["preparedAtUtc"], deadline)}
            require(json.loads(self.parameters[slot["slot"].lower()]) ==
                    deployment_parameters(slot, expected_state, public_key),
                    "Approved parameter slot/alias/identity/time binding mismatch")
        self.check()

    def read_file(self, path):
        path = private_path(path)
        raw = path.read_bytes()
        require(byte_hash(raw) == self.capture["fileHashes"][str(path)],
                "Approved ARM file hash mismatch")
        return raw

    def lease_binding(self):
        return digest({k: v for k, v in self.azure.lease.check(restore=True).items()
                       if k not in LEASE_PROGRESS})

    def check(self):
        require(digest(self.gate) == self.gate_hash and digest(self.azure.config) == self.config_hash
                and digest(self.slots) == self.slot_hash, "Approved in-memory inputs changed")
        for field in ("approvedAtUtc", "pricesVerifiedAtUtc", "fxVerifiedAtUtc"):
            approved = date(self.gate[field])
            require(now() - timedelta(hours=1) <= approved <= now()
                    and approved.date() == now().date(), "Approval expired before mutation")
        require(now() < date(self.gate["cleanupDeadlineUtc"]), "Cleanup deadline reached")
        require(self.lease_binding() == self.lease_hash, "Lease approval fields changed")
        for path, sha in self.hashes.items():
            require(byte_hash(Path(path).read_bytes()) == sha, "Approved source/input hash drift")

    def materialize(self, output):
        exclusive_bytes(output / "single-vm.private.json", self.template)
        for alias, raw in self.parameters.items():
            exclusive_bytes(output / (alias + "-parameters.private.json"), raw)
        for path in [output / "single-vm.private.json"] + [
                output / (a + "-parameters.private.json") for a in self.parameters]:
            self.hashes[str(path)] = byte_hash(path.read_bytes())
        self.check()

    def submission(self, slot, arguments):
        self.check()
        alias = slot["slot"].lower()
        expected_template = self.azure.attempt_output / "single-vm.private.json"
        expected_params = self.azure.attempt_output / (alias + "-parameters.private.json")
        require(arguments[arguments.index("--template-file") + 1] == arm_file(slot, expected_template)
                and arguments[arguments.index("--parameters") + 1] == "@" + arm_file(slot, expected_params),
                "ARM submission path differs from approved inputs")
        directory = self.azure.attempt_output / ("submission-" + uuid.uuid4().hex)
        directory.mkdir()
        template, params = directory / "template.json", directory / "parameters.json"
        exclusive_bytes(template, self.template)
        exclusive_bytes(params, self.parameters[alias])
        self.hashes[str(template)] = byte_hash(self.template)
        self.hashes[str(params)] = byte_hash(self.parameters[alias])
        result = list(arguments)
        result[result.index("--template-file") + 1] = arm_file(slot, template)
        result[result.index("--parameters") + 1] = "@" + arm_file(slot, params)
        self.check()
        return result


def deploy(azure, slots, gate, output):
    validate_gate(gate, slots, azure.lease.check())
    approval = ApprovedInputs(azure, slots, gate)
    azure.approval = approval
    require(not output.exists(), "Output directory exists; no redeploy/resume")
    for slot in slots:
        require(not state_path(slot).exists() and not private_path(slot["inventoryPath"]).exists(),
                "Fresh slot already has ownership/inventory; no redeployment")
    output.mkdir(parents=True)
    azure.attempt_output = output
    template_path = output / "single-vm.private.json"
    approval.materialize(output)
    states = {}
    # Catalogue gates and all absence checks precede the first mutation.
    for slot in slots:
        azure.identity(slot)
        catalog = azure.cli(slot, catalog_arguments(slot),
                            diagnostic=f'catalog-{slot["slot"].lower()}')
        selected = [s for s in catalog if s["name"] == slot["sku"]]
        require(len(selected) == 1 and all(
            r["type"] == "Zone" and not {"1", "2", "3"} <= set(r.get("restrictionInfo", {}).get("zones", []))
            for r in selected[0].get("restrictions", [])),
                "Catalog gate failed; no SKU or region fallback")
        require(azure.group(slot, missing=True) is None, "Group already exists; never claim or delete it")
        write(output / (slot["slot"].lower() + "-catalog.private.json"), catalog)
    azure.lease.creation_runway()
    for slot in slots:
        alias = slot["slot"].lower()
        params = json.loads(approval.parameters[alias])["parameters"]
        created, deadline = params["createdUtc"]["value"], params["cleanupDeadlineUtc"]["value"]
        ownership = group_tags(slot, created, deadline)
        state = {"slotHash": digest(slot), "ownership": ownership, "ownershipHash": digest(ownership),
                 "absenceProven": True, "absenceObservedUtc": stamp(), "createdVerified": False,
                 "status": "create-intent", "groupId": group_id(slot)}
        # Recheck absence immediately before durable intent and submission.
        require(azure.group(slot, missing=True) is None, "Group appeared; freeze")
        exclusive_json(state_path(slot), state)
        azure.creation_intents[alias] = copy.deepcopy(state)
        azure.cli(slot, ["group", "create", "--name", slot["resourceGroup"], "--location", slot["region"],
                         "--tags"] + [f"{k}={v}" for k, v in ownership.items()],
                  operation=f"create-group-{alias}")
        group = azure.group(slot)
        require(group["id"].lower() == group_id(slot).lower()
                and group.get("tags") == ownership,
                "Created group ownership verification failed")
        state.update(createdVerified=True, status="group-created")
        write(state_path(slot), state)
        azure.created_groups[alias] = state
        states[alias] = state
        params_path = output / (alias + "-parameters.private.json")
        azure.cli(slot, ["deployment", "group", "validate", "--resource-group", slot["resourceGroup"],
                         "--template-file", arm_file(slot, template_path),
                         "--parameters", "@" + arm_file(slot, params_path)],
                  operation=f"validate-{alias}")
        state["validationPassedAtUtc"] = stamp()
        write(state_path(slot), state)
    # Lock only after all three catalogue and ARM validation gates passed.
    manifest = {"slots": slots, "templateHash": byte_hash(approval.template), "gateHash": digest(gate),
                "validationPassed": True, "actualAllocationProven": False, "lockedAtUtc": stamp()}
    write(output / "manifest.private.json", manifest)
    for slot in slots:
        alias = slot["slot"].lower()
        state = states[alias]
        require(not azure.roots(slot), "Group must still be empty before deployment")
        state["status"] = "deployment-submit-intent"
        write(state_path(slot), state)
        azure.cli(slot, ["deployment", "group", "create", "--resource-group", slot["resourceGroup"],
                         "--name", slot["runId"] + "-fresh", "--mode", "Incremental",
                         "--template-file", arm_file(slot, template_path),
                         "--parameters", "@" + arm_file(slot, output / (alias + "-parameters.private.json")),
                         "--no-wait"], operation=f"deploy-{alias}")
        state["status"] = "deployment-submitted"
        write(state_path(slot), state)
    # The last three mutations are explicitly reserved restore/deallocation operations.
    for slot in slots:
        deployment_id = (group_id(slot) + "/providers/Microsoft.Resources/deployments/" +
                         slot["runId"] + "-fresh")
        proof = azure.poll(slot, deployment_id, DEPLOY_API, "deployment", restore=True)
        state = states[slot["slot"].lower()]
        state["deploymentProof"] = {"id": deployment_id, "observedAtUtc": stamp(),
                                    "provisioningState": proof["properties"]["provisioningState"]}
        write(state_path(slot), state)
    lease = azure.lease.check(restore=True)
    lease["restoreStartedAtUtc"] = stamp()
    azure.lease.save(lease)
    for slot in slots:
        deallocate(azure, slot, states[slot["slot"].lower()])
    peers = {}
    for slot in slots:
        state = states[slot["slot"].lower()]
        inventory = save_inventory(azure, slot, state, restore=True)
        pip_id = next(r["id"] for r in inventory["resources"] if r["type"] == KINDS["pip"])
        pip = azure.get(slot, pip_id, NETWORK, restore=True)
        require(pip["sku"]["name"] == "Standard" and pip["sku"]["tier"] == "Regional"
                and pip["properties"]["publicIPAddressVersion"] == "IPv4"
                and pip["properties"]["publicIPAllocationMethod"] == "Static",
                "Unexpected PIP SKU/allocation/address family")
        address = ipaddress.ip_address(pip["properties"]["ipAddress"])
        require(address.version == 4 and address.is_global, "Missing actual global IPv4 peer address")
        peers[slot["slot"]] = str(address)
        context = read(slot["contextPath"])
        context.update(region=slot["region"], vmName=slot["vmName"],
                       platform="wsl" if slot["slot"] == "T" else "windows",
                       backend="wsl" if slot["slot"] == "T" else "native",
                       resourceIds={k: f'{group_id(slot)}/providers/{v}/{names(slot)[k]}'
                                    for k, v in KINDS.items()})
        write(output / (slot["slot"].lower() + "-deployed-context.private.json"), context)
    write(output / "peers.private.json", peers)
    manifest.update(actualAllocationProven=True, deallocationVerifiedAtUtc=stamp())
    write(output / "manifest.private.json", manifest)


def deallocate(azure, slot, state):
    inventory = save_inventory(azure, slot, state, complete=False, restore=True)
    vm_id = f'{group_id(slot)}/providers/{KINDS["vm"]}/{slot["vmName"]}'
    require(any(r["id"].lower() == vm_id.lower() for r in inventory["resources"]),
            "No exact owned VM; do not deallocate")
    azure.cli(slot, ["vm", "deallocate", "--ids", vm_id, "--no-wait"],
              operation="deallocate-" + slot["slot"].lower(), restore=True)
    proof = azure.poll(slot, vm_id + "/instanceView", COMPUTE, "deallocated", restore=True)
    state.update(status="deallocated", deallocatedAtUtc=stamp(), instanceViewProof=proof)
    write(state_path(slot), state)


def verify_cleanup_bindings(azure, slot, resources):
    ids = {key: f'{group_id(slot)}/providers/{kind}/{names(slot)[key]}'.lower()
           for key, kind in KINDS.items()}
    for resource in resources:
        kind = resource["type"]
        if kind not in (KINDS["vm"], KINDS["nic"], KINDS["vnet"], KINDS["nsg"]):
            continue
        value = azure.get(slot, resource["id"], COMPUTE if kind == KINDS["vm"] else NETWORK)
        properties = value["properties"]
        if kind == KINDS["nsg"]:
            require(all(ref["id"].lower() == ids["nic"] for ref in properties.get("networkInterfaces", []))
                    and all(ref["id"].lower() == ids["vnet"] + "/subnets/lab"
                            for ref in properties.get("subnets", [])),
                    "External NSG association blocks cleanup; do not inspect the external resource")
            continue
        if kind == KINDS["vnet"]:
            require(not properties.get("virtualNetworkPeerings"), "Peering blocks group cleanup")
            subnets = properties["subnets"]
            require(len(subnets) == 1 and subnets[0]["name"] == "lab", "Unknown subnet blocks group cleanup")
            subnet = subnets[0]["properties"]
            require(subnet["networkSecurityGroup"]["id"].lower() == ids["subnet-nsg"]
                    and not subnet.get("natGateway") and not subnet.get("routeTable")
                    and not subnet.get("privateEndpoints") and not subnet.get("serviceAssociationLinks"),
                    "Unknown subnet attachment blocks cleanup; do not read or alter it")
        elif kind == KINDS["nic"]:
            configurations = properties["ipConfigurations"]
            require(properties["networkSecurityGroup"]["id"].lower() == ids["nsg"]
                    and len(configurations) == 1 and not properties.get("privateEndpoint"),
                    "Unknown NIC attachment blocks cleanup")
            config = configurations[0]["properties"]
            require(config["subnet"]["id"].lower() == ids["vnet"] + "/subnets/lab"
                    and config["publicIPAddress"]["id"].lower() == ids["pip"]
                    and not config.get("loadBalancerBackendAddressPools")
                    and not config.get("loadBalancerInboundNatRules")
                    and not config.get("applicationGatewayBackendAddressPools"),
                    "Unknown NIC binding blocks cleanup; do not read or alter it")
        else:
            nics = properties["networkProfile"]["networkInterfaces"]
            storage = properties["storageProfile"]
            require(len(nics) == 1 and nics[0]["id"].lower() == ids["nic"]
                    and storage["osDisk"]["managedDisk"]["id"].lower() == ids["os"]
                    and not storage.get("dataDisks"), "Unknown VM attachment blocks cleanup")


def cleanup(azure, slots, execute):
    lease = azure.lease.check()
    require(lease["maxMutations"] <= 6, "Cleanup lease maximum is six mutations")
    if execute:
        require(set(lease["allowedMutations"]) == {
            "delete-group-" + a.lower() for a in REGIONS}, "Cleanup permits only exact fresh group deletion")
        require(lease["cleanupApproval"] == "delete only the fresh task-created exact inventoried groups",
                "Explicit standing task-created cleanup authorization required")
    previews = []
    for slot in slots:
        azure.identity(slot)
        state = read_state(slot)
        if state.get("status") == "deleted":
            require(azure.group(slot, missing=True) is None, "Previously deleted group reappeared")
            continue
        group = azure.group(slot)
        resources = azure.roots(slot)
        verify_inventory(slot, state, group, resources, complete=False)
        verify_cleanup_bindings(azure, slot, resources)
        current = {"group": group_id(slot), "ids": sorted(r["id"].lower() for r in resources),
                   "ownershipHash": state["ownershipHash"]}
        preview = {"snapshot": current, "hash": digest(current), "previewedAtUtc": stamp()}
        preview_path = state_path(slot).with_name(slot["slot"].lower() + "-cleanup-preview.private.json")
        if execute:
            previous = read(preview_path)
            require(previous["hash"] == digest(previous["snapshot"]) == preview["hash"]
                    and now() - timedelta(minutes=30) <= date(previous["previewedAtUtc"]) <= now(),
                    "Fresh exact cleanup preview required; changed inventory blocks deletion")
            require(lease["previewHashes"][slot["slot"]] == preview["hash"],
                    "Cleanup lease not bound to reviewed preview")
        else:
            write(preview_path, preview)
        previews.append((slot, state))
    if not execute:
        return
    for slot, state in previews:
        # Revalidate immediately before each individual deletion; no approval from stale snapshots.
        group, resources = azure.group(slot), azure.roots(slot)
        verify_inventory(slot, state, group, resources, complete=False)
        verify_cleanup_bindings(azure, slot, resources)
        previous = read(state_path(slot).with_name(slot["slot"].lower() + "-cleanup-preview.private.json"))
        require(sorted(r["id"].lower() for r in resources) == previous["snapshot"]["ids"],
                "Inventory changed after preview")
        state["status"] = "delete-submit-intent"
        write(state_path(slot), state)
        azure.cli(slot, ["group", "delete", "--name", slot["resourceGroup"], "--yes", "--no-wait"],
                  operation="delete-group-" + slot["slot"].lower())
        azure.poll(slot, group_id(slot), GROUP_API, "deleted", restore=True)
        state.update(status="deleted", deletedAtUtc=stamp())
        write(state_path(slot), state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["align-handoff", "prepare", "deploy", "inventory",
                                          "preview-cleanup", "cleanup", "restore"])
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--lease")
    parser.add_argument("--gate")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    lease, azure = None, None
    try:
        if args.action == "align-handoff":
            require(args.output and not args.lease and not args.gate,
                    "Offline alignment needs a new output directory, no gate or lease")
            align_handoff(args.handoff, args.output)
            print("ALIGNED: offline planned-name copy only; no preparation, approval or deployment.")
            return 0
        handoff = read(private_path(args.handoff))
        slots = load_slots(handoff)
        if args.action == "prepare":
            require(args.gate and args.output and not args.lease, "Offline prepare needs gate/output, no live lease")
            prepare(handoff, read(private_path(args.gate)), private_path(args.output), private_path(args.handoff))
            print("PREPARED: offline input capture only; independent review and explicit gate approval still required.")
            return 0
        require(args.lease, "Live infrastructure actions require an explicit lease")
        lease = Lease(args.lease, args.action)
        require(read(args.lease)["handoffHash"] == digest(slots), "Lease/handoff mismatch")
        azure = Azure(handoff, lease)
        azure.handoff_path = private_path(args.handoff)
        azure.gate_path = private_path(args.gate) if args.gate else None
        if args.action == "deploy" and azure is not None:
            require(args.gate and args.output, "Deploy needs private gate and new private output directory")
            deploy(azure, slots, read(private_path(args.gate)), private_path(args.output))
        elif args.action in ("cleanup", "preview-cleanup"):
            cleanup(azure, slots, args.action == "cleanup")
        else:
            require(read(args.lease)["maxMutations"] <= (3 if args.action == "restore" else 0),
                    "Read-only inventory or three-operation restore lease required")
            if args.action == "restore":
                restore_lease = lease.check()
                restore_lease["restoreStartedAtUtc"] = stamp()
                lease.save(restore_lease)
            for slot in slots:
                azure.identity(slot)
                state = read_state(slot)
                if args.action == "restore":
                    deallocate(azure, slot, state)
                else:
                    save_inventory(azure, slot, state)
        lease.finish("completed")
        print("PASS: fresh infrastructure action complete; private evidence saved; no traffic executed.")
        return 0
    except (Blocked, KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        if lease:
            # One bounded read-only checkpoint, never an inline cleanup/retry.
            if args.action == "deploy" and azure is not None and azure.attempt_output is not None:
                for slot in slots:
                    try:
                        state = azure.created_groups.get(slot["slot"].lower())
                        if state is None:
                            continue
                        lease.check(restore=True)
                        resources = azure.roots(slot, restore=True)
                        exclusive_json(azure.attempt_output / (
                            slot["slot"].lower() + "-blocked-" + uuid.uuid4().hex + ".private.json"), {
                            "runId": slot["runId"], "groupId": group_id(slot),
                            "capturedAtUtc": stamp(), "resources": resources, "ready": False,
                            "status": "BLOCKED", "ownershipHash": state["ownershipHash"],
                            "createdThisInvocation": True})
                    except (Blocked, KeyError, ValueError, OSError, subprocess.SubprocessError):
                        break
            lease.finish("blocked")
        # Do not echo CLI output, paths, IDs, peer addresses or opaque service URLs.
        print("BLOCKED: " + (str(error) if isinstance(error, Blocked) else type(error).__name__) +
              "; freeze mutations; fresh recovery owner required.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
