"""Fresh three-endpoint repeat session; offline preparation, explicitly leased steps.

No resource creation, authentication changes, transport retries, or legacy state reuse.
"""
import argparse
import copy
import contextlib
import contextvars
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import functools
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

import run
import stream

ROOT = run.LAB / "private" / "repeat-session"
TARGET = 100_000_000_000
WIRE_LIMIT = 440_000_000_000
RECOVERY_WIRE_LIMIT = 460_000_000_000
READINESS_RECOVERY_WIRE_LIMIT = 470_000_000_000
MAX_LINEAGE = 32
MAX_EVIDENCE_FILES = 10000
BOOTSTRAP = 8_000_000_000
SLOT_SECONDS = 12 * 3600
MAX_SLOT_SECONDS = 24 * 3600
RUNNER_GATE = threading.RLock()
PHASE_SCOPE = None
VALIDATION_PASS = contextvars.ContextVar("repeat_validation_pass", default=None)
ALLOCATION_RESERVE = 5400  # Separate 30-minute readiness and 60-minute traffic leases.
PHASES = {"same-region": "A", "cross-region": "C"}
KINDS = {"Microsoft.Compute/virtualMachines", "Microsoft.Compute/disks",
         "Microsoft.Network/networkInterfaces", "Microsoft.Network/publicIPAddresses",
         "Microsoft.Network/networkSecurityGroups", "Microsoft.Network/virtualNetworks"}
APPROVAL_DEADLINE = datetime(2026, 10, 18, 7, 33, tzinfo=timezone.utc)


@contextlib.contextmanager
def validation_pass():
    """A byte snapshot belongs to one verification invocation, never a stat cache."""
    existing = VALIDATION_PASS.get()
    if existing is not None:
        yield existing
        return
    snapshot = {}
    token = VALIDATION_PASS.set(snapshot)
    try:
        yield snapshot
    finally:
        VALIDATION_PASS.reset(token)


def full_validation(function):
    @functools.wraps(function)
    def verified(*args, **kwargs):
        with validation_pass():
            return function(*args, **kwargs)
    return verified


@dataclass(frozen=True)
class PhaseProof:
    directory: Path
    lease: Path
    config_hash: str
    source_bytes: bytes
    predecessor_bytes: bytes
    evidence_bytes: tuple

    def predecessor(self):
        value = json.loads(self.predecessor_bytes)
        return (Path(value[0]), value[1]) if value else None


def skeleton():
    """Illustrative fake IDs only; never an approval or preflight result."""
    current = run.now()
    run.require(current < APPROVAL_DEADLINE, "original_cleanup_approval_expired")
    end = min(current + timedelta(hours=47), APPROVAL_DEADLINE).isoformat()
    config = {"schema": "bounded-repeat-v1", "createdAtUtc": current.isoformat(),
              "cleanupDeadlineUtc": end, "rateBytesPerSecond": stream.MAX_RATE,
              "chunkBytes": stream.MAX_BYTES, "contexts": {}, "endpoints": {},
              "approval": {"status": "pending", "issuedAtUtc": current.isoformat(),
                           "expiresAtUtc": end, "applicationBytesPerLeg": TARGET,
                           "wireCeilingBytes": WIRE_LIMIT, "totalUsdEquivalentCap": 45,
                           "resourceIds": []}}
    for key, digit, cap in (("core", "1", 23), ("msdn", "2", 22)):
        fake = digit * 8 + "-" + digit * 4 + "-" + digit * 4 + "-" + digit * 4 + "-" + digit * 12
        config["contexts"][key] = {
            "subscriptionId": fake, "expectedTenantId": fake,
            "platform": "windows_native_cli" if key == "core" else "wsl_Ubuntu-24.04_native_cli",
            "preflight": {"validated": False, "evidenceReference": "NOT-VALIDATED-EXAMPLE",
                          "validatedAtUtc": current.isoformat(), "validUntilUtc": end,
                          "currency": "USD", "currencyCap": cap, "usdEquivalentCap": cap,
                          "txPerDecimalGB": "0", "vmPerHour": "0", "fixedInfraReserve": "0"}}
    for alias, region in (("A", "swedencentral"), ("C", "northeurope"), ("T", "swedencentral")):
        cfg = config["contexts"]["msdn" if alias == "T" else "core"]
        rid = "example-not-deployed-" + alias.lower()
        group = "/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/rg-" + rid
        inventory = {"runId": rid, "groupId": group, "capturedAtUtc": current.isoformat(),
                     "resources": []}
        for suffix, kind in (("vm", "Microsoft.Compute/virtualMachines"),
                             ("disk", "Microsoft.Compute/disks"),
                             ("nic", "Microsoft.Network/networkInterfaces"),
                             ("pip", "Microsoft.Network/publicIPAddresses"),
                             ("nsg", "Microsoft.Network/networkSecurityGroups"),
                             ("vnet", "Microsoft.Network/virtualNetworks")):
            name = rid + "-" + suffix + "-" + alias.lower()
            identity = group + "/providers/" + kind + "/" + name
            inventory["resources"].append({
                "id": identity, "name": name, "type": kind, "location": region,
                "tags": {"lab": "true", "created_by": "copilot-lab", "run_id": rid}})
            config["approval"]["resourceIds"].append(identity)
        config["endpoints"][alias] = {"region": region, "inventory": inventory,
                                      "publicIPv4": "192.0.2." + str(ord(alias))}
    return config


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    run.require(result.tzinfo is not None, "utc_timezone_required")
    return result.astimezone(timezone.utc)


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise RuntimeError("invalid_money") from None
    run.require(result.is_finite() and result >= 0, "invalid_money")
    return result


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def lease_authority(lease):
    mutable = {"state", "actualToolCalls", "actualMutations", "activeCommands",
               "ownedProcessesIdle", "lastCheckpointUtc"}
    return identity({key: value for key, value in lease.items() if key not in mutable})


def sources():
    return dict(run.source_identity(), repeat=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def atomic(path, value, exclusive=False):
    path = Path(path)
    stage = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        with stage.open("x", encoding="utf-8") as handle:
            os.chmod(stage, 0o600)
            handle.write(json.dumps(value, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            # The enclosing exclusive directory/lock prevents another session writer.
            run.require(not path.exists(), "refuse_existing_state")
        first_error = None
        deadline = None
        for attempt in range(41):
            try:
                os.replace(stage, path)
                break
            except OSError as error:
                if os.name != "nt" or getattr(error, "winerror", None) not in (5, 32, 33):
                    raise
                if first_error is None:
                    first_error = error
                    deadline = time.monotonic() + 1
                remaining = deadline - time.monotonic()
                if attempt == 40 or remaining <= 0:
                    raise first_error
                # Only retry the already-fsynced local metadata rename, never Azure work.
                time.sleep(min(.025, remaining))
    finally:
        if stage.exists():
            stage.unlink()


@contextlib.contextmanager
def locked(directory):
    lock = directory / ".ledger-lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError("ledger_locked_manual_recovery_no_replay") from None
    try:
        yield
    finally:
        lock.rmdir()


def chunk_sizes(chunk_bytes=5 * stream.GIB):
    run.require(type(chunk_bytes) is int and stream.GIB <= chunk_bytes <= stream.MAX_BYTES,
                "chunk_must_be_1_to_5_gib")
    remaining = TARGET - stream.GIB
    full, final = divmod(remaining, chunk_bytes)
    return [stream.GIB] + [chunk_bytes] * full + ([final] if final else [])


def wire_reserve(size):
    # 7.5% per chunk plus handshake allowance; bootstrap stays inside the 10% whole ceiling.
    return (size * 2 * 1075 + 999) // 1000 + 2 * 1024 ** 2


def money_mode(config):
    mode = config.get("moneyBudgetMode", "enforced")
    approval = config["approval"]
    run.require(mode in ("enforced", "monitor-only")
                and approval.get("moneyBudgetMode", "enforced") == mode,
                "explicit_matching_money_budget_mode_required")
    if mode == "monitor-only":
        run.require(approval["status"] == "approved"
                    and approval.get("totalUsdEquivalentCap") is None
                    and all(context["preflight"].get(field) is None
                            for context in config["contexts"].values()
                            for field in ("currencyCap", "usdEquivalentCap")),
                    "approved_monitor_only_requires_absent_or_null_caps")
    return mode


def money_estimate(config, wire, pairs):
    return {key: {"currency": cfg["preflight"]["currency"],
                  "tx_per_decimal_gb": str(number(cfg["preflight"]["txPerDecimalGB"])),
                  "vm_per_hour": str(number(cfg["preflight"]["vmPerHour"])),
                  "fixed_infra_reserve": str(number(cfg["preflight"]["fixedInfraReserve"])),
                  "conservative_planning_reserve": str(
                      number(cfg["preflight"]["fixedInfraReserve"])
                      + number(cfg["preflight"]["txPerDecimalGB"]) * wire / 10 ** 9
                      + number(cfg["preflight"]["vmPerHour"]) * ALLOCATION_RESERVE * pairs / 3600)}
            for key, cfg in config["contexts"].items()}


def prior_allocations(config):
    approval = config["approval"]
    supplied = "priorAllocatedSeconds" in config or "priorAllocatedSeconds" in approval
    if not supplied:
        return {"A": 0, "C": 0, "T": 0}
    prior = config.get("priorAllocatedSeconds")
    run.require(isinstance(prior, dict) and set(prior) == {"A", "C", "T"}
                and all(type(value) is int and 0 <= value <= slot_seconds(config)
                        for value in prior.values()),
                "invalid_prior_allocated_seconds")
    approved = approval.get("priorAllocatedSeconds")
    run.require(isinstance(approved, dict) and set(approved) == set(prior)
                and all(type(value) is int for value in approved.values())
                and approved == prior
                and all(isinstance(approval.get(field), str) and approval[field].strip()
                        for field in ("evidenceReference", "predecessorIdentifier")),
                "approved_prior_allocation_evidence_required")
    return dict(prior)


def slot_seconds(config):
    value = config.get("allocatedSecondsPerVm", SLOT_SECONDS)
    run.require(type(value) is int and SLOT_SECONDS <= value <= MAX_SLOT_SECONDS,
                "invalid_allocated_seconds_per_vm")
    if "allocatedSecondsPerVm" in config:
        approval = config["approval"]
        run.require(approval.get("allocatedSecondsPerVm") == value
                    and type(approval.get("allocatedSecondsPerVm")) is int
                    and approval.get("status") == "approved"
                    and bool(approval.get("evidenceReference")),
                    "explicit_runtime_approval_required")
    return value


def projections_fit(config, projections):
    prior = prior_allocations(config)
    return (prior["T"] + sum(projections.values()) < slot_seconds(config)
            and all(prior[PHASES[phase]] + seconds < slot_seconds(config)
                    for phase, seconds in projections.items()))


def wire_limit(config):
    value = config.get("wireCeilingBytes", WIRE_LIMIT)
    run.require(type(value) is int
                and (WIRE_LIMIT <= value <= RECOVERY_WIRE_LIMIT
                     or value == READINESS_RECOVERY_WIRE_LIMIT)
                and config["approval"].get("wireCeilingBytes") == value,
                "explicit_wire_ceiling_approval_required")
    if value != WIRE_LIMIT:
        run.require(config.get("continuation", {}).get("schema") == "closed-recovery-v1"
                    and config["approval"].get("continuationHash") == identity(config["continuation"])
                    and config["approval"].get("status") == "approved"
                    and bool(config["approval"].get("evidenceReference")),
                    "certified_recovery_wire_approval_required")
    if value == READINESS_RECOVERY_WIRE_LIMIT:
        run.require(config["continuation"].get("readiness_closure") is not None
                    and slot_seconds(config) == MAX_SLOT_SECONDS
                    and money_mode(config) == "monitor-only",
                    "exact_readiness_recovery_amendment_required")
    return value


def validate_config(config, fresh=True, approved=True):
    mode = money_mode(config)
    prior_allocations(config)
    run.require(config["schema"] == "bounded-repeat-v1", "repeat_schema_required")
    created = timestamp(config["createdAtUtc"])
    deadline = timestamp(config["cleanupDeadlineUtc"])
    run.require(created <= run.now() < deadline
                <= min(created + timedelta(hours=48), APPROVAL_DEADLINE),
                "repeat_ttl_exceeded")
    approval = config["approval"]
    run.require((approval["status"] == "approved" or not approved)
                and timestamp(approval["issuedAtUtc"]) <= run.now()
                < timestamp(approval["expiresAtUtc"]) <= deadline
                and approval["applicationBytesPerLeg"] == TARGET
                and approval["wireCeilingBytes"] == wire_limit(config)
                and (mode == "monitor-only" or approval["totalUsdEquivalentCap"] == 45),
                "fresh_exact_repeat_approval_required")
    sizes = chunk_sizes(config.get("chunkBytes", 5 * stream.GIB))
    rate = config.get("rateBytesPerSecond", stream.RATE)
    run.require(type(rate) is int and 0 < rate <= stream.MAX_RATE, "invalid_repeat_rate")
    # Even perfect transport cannot make the old default fit the shared T 12-hour slot.
    run.require(2 * TARGET / rate < slot_seconds(config), "rate_cannot_fit_twelve_hour_t_slot")
    run.require(BOOTSTRAP + 2 * sum(map(wire_reserve, sizes)) <= wire_limit(config),
                "whole_session_wire_reservation_exceeded")
    contexts, endpoints = config["contexts"], config["endpoints"]
    run.require(set(contexts) == {"core", "msdn"} and set(endpoints) == {"A", "C", "T"},
                "exact_three_endpoint_roles_required")
    run.require(contexts["core"]["subscriptionId"] != contexts["msdn"]["subscriptionId"]
                and contexts["core"]["expectedTenantId"] != contexts["msdn"]["expectedTenantId"],
                "repeat_requires_unequal_tenants_and_subscriptions")
    for key, usd in (("core", 23), ("msdn", 22)):
        cfg = contexts[key]
        p = cfg["preflight"]
        run.require(all(re.fullmatch(r"[a-fA-F0-9-]{36}", cfg[field])
                        for field in ("subscriptionId", "expectedTenantId")),
                    "context_uuid_required")
        run.require(p["validated"] is True and bool(p["evidenceReference"])
                    and timestamp(p["validatedAtUtc"]) <= run.now()
                    < timestamp(p["validUntilUtc"]) <= deadline
                    and bool(p["currency"])
                    and number(p["txPerDecimalGB"]) > 0
                    and number(p["vmPerHour"]) > 0,
                    "validated_preflight_currency_caps_required")
        number(p["fixedInfraReserve"])
        if mode == "enforced":
            run.require(p["usdEquivalentCap"] == usd and number(p["currencyCap"]) > 0,
                        "validated_preflight_currency_caps_required")
            if p["currency"] == "USD":
                run.require(number(p["currencyCap"]) <= usd, "usd_context_cap_exceeded")
        run.require(cfg["platform"] in ("windows_native_cli", "wsl_Ubuntu-24.04_native_cli"),
                    "invalid_native_platform")
    all_ids, runs, groups = [], [], []
    for alias, region in (("A", "swedencentral"), ("C", "northeurope"), ("T", "swedencentral")):
        endpoint = endpoints[alias]
        cfg = contexts["msdn" if alias == "T" else "core"]
        inventory = endpoint["inventory"]
        age = (run.now() - timestamp(inventory["capturedAtUtc"])).total_seconds()
        run.require(0 <= age < (86400 if fresh else 172800), "fresh_inventory_required")
        binding = run.target(cfg, inventory, alias.lower(), region)
        run.require(endpoint["region"] == region
                    and inventory["groupId"].lower() == (
                        "/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/"
                        + binding["resourceGroup"]).lower(), "fresh_group_identity_mismatch")
        ipaddress.IPv4Address(endpoint["publicIPv4"])
        kinds = []
        for row in inventory["resources"]:
            expected = (inventory["groupId"] + "/providers/" + row["type"] + "/" + row["name"])
            run.require(row["type"] in KINDS and "/" not in row["name"]
                        and row["id"].lower() == expected.lower()
                        and row["location"] == region
                        and row["tags"] == {"lab": "true", "created_by": "copilot-lab",
                                            "run_id": inventory["runId"]},
                        "extra_or_unowned_repeat_resource")
            kinds.append(row["type"])
            all_ids.append(row["id"].lower())
        run.require(set(kinds) == KINDS and all(
            kinds.count(kind) == 1 for kind in KINDS
            if not kind.endswith("/networkSecurityGroups")) and 6 <= len(kinds) <= 7,
            "exact_endpoint_inventory_required")
        runs.append(inventory["runId"])
        groups.append(inventory["groupId"].lower())
    run.require(len(set(runs)) == len(set(groups)) == 3
                and len(set(all_ids)) == len(all_ids), "fresh_isolated_three_groups_required")
    approved = approval["resourceIds"]
    run.require(len(approved) == len(all_ids)
                and set(x.lower() for x in approved) == set(all_ids),
                "approval_resource_set_mismatch")
    return sizes


def plan_summary(config):
    sizes = validate_config(config, approved=False)
    predecessor = continuation(config)
    inherited = predecessor[1] if predecessor else None
    wire = schedule_wire(config, inherited)
    failed = sum(c["state"] == "failed_or_unknown"
                 for c in inherited["chunks"].values()) if inherited else 0
    return {"mode": "read_only_plan_no_authority", "application_bytes_per_leg": TARGET,
            "legs": ["A->T", "T->A", "C->T", "T->C"],
            "total_application_bytes": 4 * TARGET, "bytes_per_request": sizes,
            "requests_per_leg": len(sizes), "pilot_included": True,
            "rate_bytes_per_second": config.get("rateBytesPerSecond", stream.RATE),
            "wire_reserved_whole_session": wire, "wire_ceiling_bytes": wire_limit(config),
            "money_budget_mode": money_mode(config),
            "prior_allocated_seconds": prior_allocations(config),
            "allocated_seconds_per_vm": slot_seconds(config),
            "inherited_chunks": list(predecessor[1]["chunks"]) if predecessor else [],
            "money_estimate_whole_session": money_estimate(
                config, wire, 2 * len(sizes) + failed),
            "live_allowed": False}


def schedule_wire(config, ledger=None):
    sizes = chunk_sizes(config.get("chunkBytes", stream.MAX_BYTES))
    if ledger is None:
        return BOOTSTRAP + 2 * sum(map(wire_reserve, sizes))
    return ledger["wire_reserved"] + sum(sum(map(wire_reserve, sizes[sum(
        c["phase"] == phase and c["state"] == "complete"
        for c in ledger["chunks"].values()):])) for phase in PHASES)


def prepare(config, directory):
    validate_config(config)
    predecessor = continuation(config)
    projections = verified_projections(predecessor[0], config, predecessor[1]) if predecessor else {}
    if predecessor:
        inherited = predecessor[1]
        run.require(schedule_wire(config, inherited) <= wire_limit(config),
                    "recovery_whole_session_wire_cap")
    directory.parent.mkdir(parents=True, exist_ok=True)
    if predecessor:
        previous, inherited = predecessor
        run.require(previous.parent.resolve() == directory.parent.resolve()
                    and previous.resolve() != directory.resolve(),
                    "successor_requires_same_session_root")
        claims = directory.parent / ".continuation-claims"
        claims.mkdir(exist_ok=True)
        claim = claims / identity(str(previous.resolve()))
        claim.mkdir()  # Exclusive, durable no-fork claim; failure never refunds authority.
        atomic(claim / "successor.private.json",
               {"directory": str(directory.resolve()), "config_hash": identity(config)}, True)
    directory.mkdir()  # Exclusive; never adopt an old namespace.
    (directory / "chunks").mkdir()
    (directory / "control").mkdir()
    atomic(directory / "config.private.json", config, True)
    ledger = {"schema": "bounded-repeat-ledger-v1", "config_hash": identity(config),
              "sources": sources(), "wire_reserved": BOOTSTRAP, "wire_measured": 0,
              "money_reserved": {}, "allocated_seconds": prior_allocations(config),
              "prior_allocated_seconds": prior_allocations(config),
              "chunks": {}, "leases": [], "projections": {}, "active_phase": None,
              "state": "prepared"}
    for key, cfg in config["contexts"].items():
        p = cfg["preflight"]
        amount = number(p["fixedInfraReserve"]) + number(p["txPerDecimalGB"]) * BOOTSTRAP / 10 ** 9
        run.require(money_mode(config) == "monitor-only" or amount <= number(p["currencyCap"]),
                    "bootstrap_infra_currency_cap")
        ledger["money_reserved"][key] = str(amount)
    if predecessor:
        ledger.update({field: copy.deepcopy(inherited[field]) for field in (
            "wire_reserved", "wire_measured", "money_reserved", "allocated_seconds",
            "chunks", "leases", "owners", "projections")})
        ledger["projections"] = projections
    atomic(directory / "ledger.private.json", ledger, True)


def evidence_manifest(directory):
    directory = directory.resolve()
    snapshot = VALIDATION_PASS.get()
    if snapshot is not None and directory in snapshot:
        return {name: hashlib.sha256(raw).hexdigest()
                for name, raw in snapshot[directory]}
    files = {}
    captured = []
    for path in sorted(directory.rglob("*")):
        run.require(not path.is_symlink(), "evidence_symlink_forbidden")
        if path.is_file():
            run.require(len(files) < MAX_EVIDENCE_FILES, "lineage_file_bound")
            name, raw = str(path.relative_to(directory)), path.read_bytes()
            files[name] = hashlib.sha256(raw).hexdigest()
            captured.append((name, raw))
    if snapshot is not None:
        snapshot[directory] = tuple(captured)
    return files


def chunk_origin(directory, chunk):
    if chunk.get("lease_path"):
        origin = Path(chunk["lease_path"]).resolve().parent.parent
        run.require(origin.parent == directory.resolve().parent, "foreign_chunk_origin")
        return origin
    return directory


def closed_failure(chunk_dir, plan, chunk):
    lease = run.read(chunk["lease_path"])
    require_closed(lease, 150, failed=True)
    run.require(lease["taskId"] == chunk["lease"] and chunk["attempts"] == 1
                and plan["status"] in ("blocked", "rolled_back")
                and chunk.get("allocated_seconds", ALLOCATION_RESERVE) == ALLOCATION_RESERVE
                and timestamp(lease["startedAtUtc"]) <= timestamp(plan["live_started"])
                <= timestamp(plan["restore_started"]) <= timestamp(plan["ended"])
                <= timestamp(lease["expiresAtUtc"]), "failed_closure_required")
    for alias in run.endpoint_names(plan):
        proof = run.read(chunk_dir / ("deallocate-" + alias.lower() + "-verified.private.json"))
        run.require(proof.get("verified") is True
                    and proof.get("binding") == {"id": plan["id"], "endpoint": plan[alias]}
                    and timestamp(plan["restore_started"]) <= timestamp(proof["at"])
                    <= timestamp(plan["ended"]), "failed_deallocation_required")
    for prefix in ("nsg", "subnet-nsg") if plan.get("receiver_subnet_nsg") else ("nsg",):
        proof = run.read(chunk_dir / (prefix + "-restored.private.json"))
        run.require(proof.get("verified") is True
                    and timestamp(plan["restore_started"]) <= timestamp(proof["at"])
                    <= timestamp(plan["ended"]), "failed_nsg_restore_required")
    return {"id": chunk["id"], "lease_hash": identity(lease),
            "application_credit": 0, "wire_reserved": chunk["wire_reserved"],
            "allocated_seconds_per_vm": ALLOCATION_RESERVE, "actual_wire_bytes": None}


def private_binding(binding, label):
    run.require(isinstance(binding, dict) and set(binding) == {"path", "sha256"},
                label + "_binding_required")
    path = Path(binding["path"])
    run.require(path.is_absolute()
                and path.resolve().is_relative_to((run.LAB / "private").resolve())
                and not path.is_symlink(), label + "_private_path_required")
    raw = path.read_bytes()
    run.require(hashlib.sha256(raw).hexdigest() == binding["sha256"],
                label + "_hash_changed")
    snapshot = VALIDATION_PASS.get()
    if snapshot is not None:
        snapshot[path.resolve()] = ((path.name, raw),)
    return json.loads(raw.decode("utf-8-sig"))


def closed_readiness_failure(directory, key, config, ledger, plan, binding):
    """Certify a closed, unlaunched phase without inventing traffic receipts."""
    chunk, phase = ledger["chunks"][key], ledger["active_phase"]
    run.require(phase and phase.get("action") == "readiness"
                and phase.get("state") == "blocked" and phase["chunk"] == key
                and chunk["attempts"] == 0 and not chunk.get("phases")
                and "lease" not in chunk and "lease_path" not in chunk
                and not chunk.get("wire_measured")
                and plan["status"] == "prepared_not_live"
                and not plan.get("live_started")
                and chunk.get("allocated_seconds", ALLOCATION_RESERVE) == ALLOCATION_RESERVE,
                "closed_failed_readiness_required")
    lease_path = Path(phase["lease_path"])
    run.require(lease_path.resolve().parent == (directory / "control").resolve(),
                "readiness_lease_namespace_changed")
    lease = run.read(lease_path)
    require_closed(lease, 75, failed=True)
    run.require(lease["state"] == "blocked" and lease["taskId"] == phase["taskId"]
                and lease_authority(lease) == phase["authority_hash"]
                and lease["taskId"] in ledger["leases"]
                and lease["maxMutations"] == 6
                and set(lease["allowedMutations"]) == set(run.operations(plan, True)),
                "readiness_closed_lease_changed")
    chunk_dir = directory / "chunks" / key
    receipt = run.read(chunk_dir / "readiness.private.json")
    expected_binding = run.readiness_binding(chunk_dir, plan)
    expected_binding.update(runner_sha256=ledger["sources"]["run.py"],
                            stream_sha256=ledger["sources"]["stream.py"])
    run.require(receipt["success"] is False and bool(receipt.get("failures"))
                and receipt["binding"] == expected_binding
                and timestamp(lease["startedAtUtc"]) <= timestamp(receipt["started_at"])
                <= timestamp(plan["restore_started"]) <= timestamp(receipt["completed_at"])
                <= timestamp(lease["expiresAtUtc"])
                and all(receipt["deallocated"].get(alias) is True
                        for alias in run.endpoint_names(plan)),
                "failed_readiness_receipt_changed")
    for alias in run.endpoint_names(plan):
        proof = run.read(chunk_dir / ("deallocate-" + alias.lower() + "-verified.private.json"))
        run.require(proof.get("verified") is True
                    and proof.get("binding") == {"id": plan["id"], "endpoint": plan[alias]}
                    and timestamp(plan["restore_started"]) <= timestamp(proof["at"])
                    <= timestamp(receipt["completed_at"]), "failed_readiness_deallocation_required")
    run.require(not any((chunk_dir / name).exists() for name in (
        "client-report.private.json", "server-report.private.json",
        "client.private.json", "server.private.json", "allow.private.json",
        "allow-subnet.private.json")),
        "readiness_payload_or_nsg_write_forbidden")
    attestation = private_binding(binding, "readiness_closure")
    run.require(attestation.get("schema") == "repeat-readiness-closure-v1"
                and attestation.get("validationKind") == "independent-read-only"
                and isinstance(attestation.get("validatedBy"), str)
                and re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", attestation["validatedBy"])
                and attestation.get("sessionDirectory") == str(directory.resolve())
                and attestation.get("configHash") == identity(config)
                and attestation.get("ledgerHash") == identity(ledger)
                and attestation.get("chunk") == key
                and attestation.get("leaseHash") == identity(lease)
                and attestation.get("readinessHash") == identity(receipt),
                "exact_independent_readiness_closure_required")
    closure = private_binding(attestation["closure"], "readiness_restore")
    run.require(closure.get("success") is True
                and closure.get("all21OriginalOwnedRootsVerified") is True
                and closure.get("totalAzureMutations") == 0
                and set(closure["endpoints"]) == {"A", "C", "T"}
                and all(endpoint.get("deallocated") is True
                        and endpoint.get("ownedRootCount") == 7
                        and endpoint.get("originalVmIdentityAndStorageProfile") is True
                        and endpoint.get("originalDiskAttachment") is True
                        and endpoint.get("nicAndSubnetNsgRulesAndAssociationsMatchBaseline") is True
                        for endpoint in closure["endpoints"].values())
                and timestamp(receipt["completed_at"]) <= timestamp(closure["startedAtUtc"])
                <= timestamp(closure["completedAtUtc"]) <= run.now(),
                "independent_full_restore_required")
    require_closed(closure["lease"], 75)
    run.require(closure["lease"]["maxMutations"] == 0
                and closure["lease"]["actualMutations"] == 0
                and closure["lease"]["taskId"] != lease["taskId"],
                "independent_read_only_closure_lease_required")
    evidence = attestation.get("evidenceHashes")
    run.require(isinstance(evidence, dict) and 1 <= len(evidence) <= 100,
                "readiness_closure_evidence_required")
    for path, digest in evidence.items():
        private_binding({"path": path, "sha256": digest}, "readiness_closure_evidence")
    return {"kind": "closed-readiness-failure", "id": chunk["id"],
            "lease_hash": identity(lease), "readiness_hash": identity(receipt),
            "closure_hash": binding["sha256"], "application_credit": 0,
            "wire_reserved": chunk["wire_reserved"],
            "allocated_seconds_per_vm": ALLOCATION_RESERVE, "actual_wire_bytes": None}


def renewal_evidence(old, binding, fresh=True):
    """Verify independent attestation bytes; approval remains a separate trust gate."""
    run.require(isinstance(binding, dict) and set(binding) == {"path", "sha256"},
                "renewal_attestation_binding_required")
    path = Path(binding["path"])
    private = (run.LAB / "private").resolve()
    run.require(path.is_absolute() and path.resolve().is_relative_to(private)
                and not path.is_symlink(), "private_renewal_attestation_required")
    raw = path.read_bytes()
    run.require(hashlib.sha256(raw).hexdigest() == binding["sha256"],
                "renewal_attestation_hash_changed")
    snapshot = VALIDATION_PASS.get()
    if snapshot is not None:
        snapshot[path.resolve()] = ((path.name, raw),)
    attestation = json.loads(raw.decode("utf-8-sig"))
    run.require(set(attestation) == {
        "schema", "status", "validationKind", "validatedBy", "validatedAtUtc",
        "validUntilUtc", "predecessorConfigHash", "contexts", "endpoints", "evidenceHashes"}
        and attestation["schema"] == "repeat-preflight-renewal-v1"
        and attestation["status"] == "PASS"
        and attestation["validationKind"] == "independent-read-only"
        and isinstance(attestation["validatedBy"], str)
        and re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", attestation["validatedBy"])
        and attestation["predecessorConfigHash"] == identity(old),
        "independent_renewal_attestation_required")
    checked = timestamp(attestation["validatedAtUtc"])
    expires = timestamp(attestation["validUntilUtc"])
    run.require(checked < expires <= timestamp(old["cleanupDeadlineUtc"]),
                "renewal_attestation_time_invalid")
    if fresh:
        run.require(checked <= run.now() < expires,
                    "fresh_renewal_attestation_required")
    evidence = attestation["evidenceHashes"]
    run.require(isinstance(evidence, dict) and 1 <= len(evidence) <= 100,
                "renewal_evidence_hashes_required")
    for name, digest in evidence.items():
        source = Path(name)
        run.require(source.is_absolute() and source.resolve().is_relative_to(private)
                    and not source.is_symlink(), "renewal_evidence_hash_changed")
        raw = source.read_bytes()
        run.require(source.is_absolute() and source.resolve().is_relative_to(private)
                    and not source.is_symlink()
                    and source.resolve() != path.resolve()
                    and re.fullmatch(r"[a-f0-9]{64}", digest)
                    and hashlib.sha256(raw).hexdigest() == digest,
                    "renewal_evidence_hash_changed")
        if snapshot is not None:
            snapshot[source.resolve()] = ((source.name, raw),)
    candidate = copy.deepcopy(old)
    for field in ("contexts", "endpoints"):
        candidate[field] = attestation[field]
    original, renewed = copy.deepcopy(old), copy.deepcopy(candidate)
    run.require(set(renewed["contexts"]) == set(original["contexts"])
                and set(renewed["endpoints"]) == set(original["endpoints"]),
                "renewal_identity_changed")
    for key, context in renewed["contexts"].items():
        previous = original["contexts"][key]["preflight"]
        current = context["preflight"]
        run.require(current["validated"] is True
                    and bool(current["evidenceReference"])
                    and current["evidenceReference"] in evidence
                    and current["evidenceReference"] != previous["evidenceReference"]
                    and timestamp(previous["validatedAtUtc"])
                    < timestamp(current["validatedAtUtc"]) <= checked
                    and checked - timestamp(current["validatedAtUtc"]) < timedelta(hours=1)
                    and expires <= timestamp(current["validUntilUtc"])
                    <= timestamp(old["cleanupDeadlineUtc"]),
                    "renewal_requires_new_context_validation")
        for field in ("evidenceReference", "validatedAtUtc", "validUntilUtc"):
            current.pop(field)
            previous.pop(field)
    for alias, endpoint in renewed["endpoints"].items():
        previous = original["endpoints"][alias]["inventory"]
        current = endpoint["inventory"]
        run.require(timestamp(previous["capturedAtUtc"])
                    < timestamp(current["capturedAtUtc"]) <= checked
                    and checked - timestamp(current["capturedAtUtc"]) < timedelta(hours=1),
                    "renewal_requires_new_owned_inventory")
        current.pop("capturedAtUtc")
        previous.pop("capturedAtUtc")
    run.require(renewed == original, "renewal_identity_changed")
    return attestation


@full_validation
def certify_predecessor(directory, _seen=(), renewal=None, _successor_sources=None,
                        readiness_closure=None):
    """Read-only certificate; no source rebinding or historical artifact writes."""
    config = run.read(directory / "config.private.json")
    ledger = run.read(directory / "ledger.private.json")
    directory = directory.resolve()
    run.require(str(directory) not in _seen and len(_seen) < MAX_LINEAGE, "lineage_cycle_or_depth")
    seen = (*_seen, str(directory))
    run.require(ledger["config_hash"] == identity(config), "predecessor_config_changed")
    validate_ledger(config, ledger)
    predecessor = continuation(config, seen)
    if config.get("continuation", {}).get("preflight_renewal") is not None:
        run.require(ledger["sources"] == config["continuation"]["successor_sources"],
                    "renewal_successor_sources_changed")
    inherited = predecessor[1]["chunks"] if predecessor else {}
    run.require(all(ledger["chunks"].get(key) == chunk for key, chunk in inherited.items()),
                "inherited_progress_changed")
    run.require(ledger["chunks"]
                and all(chunk["state"] in ("complete", "failed_or_unknown")
                        for chunk in ledger["chunks"].values()),
                "predecessor_not_idle_and_complete")
    failures, salvaged = {}, {}
    active = ledger["active_phase"]
    for key, chunk in ledger["chunks"].items():
        if key in inherited:
            continue
        chunk_dir = directory / "chunks" / key
        plan = run.read(chunk_dir / "plan.private.json")
        expected = make_plan(config, directory, key, chunk)
        run.require(all(plan.get(field) == value for field, value in expected.items()),
                    "predecessor_plan_binding_changed")
        pins = {name: ledger["sources"][name] for name in ("run.py", "stream.py")}
        run.require(plan.get("prepared_sources") == pins
                    and plan.get("snapshot_sources", pins) == pins,
                    "predecessor_plan_sources_changed")
        if chunk["state"] == "failed_or_unknown":
            if chunk["attempts"] == 0:
                failures[key] = closed_readiness_failure(
                    directory, key, config, ledger, plan, readiness_closure)
                continue
            elif plan["status"] == "completed":
                salvaged[key] = certified_salvage(chunk_dir, plan, chunk)
                failures[key] = {"id": chunk["id"], "application_credit": 0,
                                 "wire_reserved": chunk["wire_reserved"],
                                 "allocated_seconds_per_vm": ALLOCATION_RESERVE}
            else:
                failures[key] = closed_failure(chunk_dir, plan, chunk)
        else:
            certify_completed(chunk_dir, plan, chunk)
        run.require(set(chunk.get("phases", {})) == {"readiness", "snapshot"},
                    "predecessor_phase_receipts_required")
        for receipt in chunk["phases"].values():
            phase_lease = run.read(receipt["lease_path"])
            require_closed(phase_lease, 75)
            run.require(identity(phase_lease) == receipt["lease_hash"]
                        and phase_lease["taskId"] == receipt["taskId"],
                        "predecessor_phase_receipt_changed")
    if active:
        run.require(active.get("state") == "blocked" and active["chunk"] in failures
                    and (failures[active["chunk"]].get("kind") == "closed-readiness-failure"
                         or (active["taskId"] == ledger["chunks"][active["chunk"]]["lease"]
                             and active["lease_path"] ==
                             ledger["chunks"][active["chunk"]]["lease_path"]))
                    and lease_authority(run.read(active["lease_path"])) == active["authority_hash"],
                    "predecessor_active_phase")
    has_failed = any(chunk["state"] == "failed_or_unknown" for chunk in ledger["chunks"].values())
    run.require(ledger["state"] != "blocked" or has_failed, "predecessor_not_idle_and_complete")
    certificate = {"directory": str(directory), "files": evidence_manifest(directory),
                   "sources": ledger["sources"]}
    if has_failed:
        certificate.update(schema="closed-recovery-v1", closed_failures=failures)
    if readiness_closure is not None:
        run.require(any(value.get("kind") == "closed-readiness-failure"
                        for value in failures.values()), "unused_readiness_closure")
        certificate["readiness_closure"] = readiness_closure
        certificate["successor_sources"] = (sources() if _successor_sources is None
                                            else _successor_sources)
    if salvaged:
        candidate = copy.deepcopy(ledger)
        candidate["chunks"].update(salvaged)
        projection = verified_projections(directory, config, candidate, enforce=False)
        run.require(not projections_fit(config, projection),
                    "salvage_requires_posttransport_projection_failure")
        certificate["salvaged_completions"] = salvaged
    if renewal is not None:
        renewal_evidence(config, renewal, fresh=not _seen)
        certificate["preflight_renewal"] = renewal
        certificate["successor_sources"] = (sources() if _successor_sources is None
                                            else _successor_sources)
    return certificate


def certified_salvage(chunk_dir, plan, chunk):
    """Derive successor-only credit; retain the entire failed reservation."""
    a, t, _ = verified_completion(chunk_dir, plan)
    lease = run.read(chunk["lease_path"])
    require_closed(lease, 150, failed=True)
    run.require(lease["state"] == "blocked" and lease["taskId"] == chunk["lease"]
                and chunk["attempts"] == 1
                and timestamp(lease["startedAtUtc"]) <= timestamp(plan["live_started"])
                <= timestamp(plan["ended"]) <= timestamp(lease["expiresAtUtc"]),
                "salvage_closed_projection_lease_required")
    result = copy.deepcopy(chunk)
    alias = PHASES[chunk["phase"]]
    result.update(state="complete", allocated_seconds=ALLOCATION_RESERVE,
                  wire_measured=a["nic"]["delta"]["wire_once"],
                  endedAtUtc=plan["ended"], verdict=stream.verify(a, t, plan),
                  tx_by_producer={alias: a["nic"]["delta"]["tx"], "T": t["nic"]["delta"]["tx"]},
                  guest_nic={alias: a["nic"]["delta"], "T": t["nic"]["delta"]},
                  network_hash=identity(plan["network_bindings"]),
                  endpoint_hash_proofs={"client": identity(a["legs"]), "server": identity(t["legs"])},
                  certified_salvage=True)
    return result


def certify_completed(chunk_dir, plan, chunk):
    a, t, elapsed = verified_completion(chunk_dir, plan)
    alias = PHASES[chunk["phase"]]
    run.require(chunk["allocated_seconds"] == math.ceil(elapsed)
                    and chunk["wire_measured"] == a["nic"]["delta"]["wire_once"]
                    and chunk["endpoint_hash_proofs"] == {
                        "client": identity(a["legs"]), "server": identity(t["legs"])}
                    and chunk["guest_nic"] == {alias: a["nic"]["delta"], "T": t["nic"]["delta"]}
                    and chunk["tx_by_producer"] == {
                        alias: a["nic"]["delta"]["tx"], "T": t["nic"]["delta"]["tx"]}
                    and chunk["verdict"] == stream.verify(a, t, plan),
                    "predecessor_completed_evidence_changed")
    lease = run.read(chunk["lease_path"])
    require_closed(lease, 150)
    run.require(lease["taskId"] == chunk["lease"]
                    and timestamp(lease["startedAtUtc"]) <= timestamp(plan["live_started"])
                    <= timestamp(plan["ended"]) <= timestamp(lease["expiresAtUtc"]),
                    "predecessor_traffic_lease_changed")


@full_validation
def continuation(config, _seen=()):
    certificate = config.get("continuation")
    if certificate is None:
        return None
    approval = config["approval"]
    run.require(approval.get("status") == "approved"
                and approval.get("continuationHash") == identity(certificate),
                "approved_continuation_certificate_required")
    directory = Path(certificate["directory"])
    run.require(certificate["files"] == evidence_manifest(directory),
                "predecessor_evidence_hash_changed")
    old = run.read(directory / "config.private.json")
    ledger = run.read(directory / "ledger.private.json")
    run.require(ledger["config_hash"] == identity(old)
                and ledger["sources"] == certificate["sources"],
                "predecessor_source_or_config_changed")
    candidate, original = copy.deepcopy(config), copy.deepcopy(old)
    renewal = certificate.get("preflight_renewal")
    if certificate.get("readiness_closure") is not None:
        run.require(bool(_seen) or certificate.get("successor_sources") == sources(),
                    "readiness_successor_sources_changed")
    if renewal is not None:
        attestation = renewal_evidence(old, renewal, fresh=not _seen)
        pins = certificate.get("successor_sources")
        run.require(isinstance(pins, dict) and set(pins) == set(sources())
                    and all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
                            for value in pins.values())
                    and (bool(_seen) or pins == sources()), "renewal_successor_sources_changed")
        run.require(approval.get("preflightRenewalHash") == renewal["sha256"]
                    and bool(approval.get("evidenceReference"))
                    and config["contexts"] == attestation["contexts"]
                    and config["endpoints"] == attestation["endpoints"],
                    "explicit_exact_preflight_renewal_approval_required")
        run.require(timestamp(old["approval"]["issuedAtUtc"])
                    < timestamp(approval["issuedAtUtc"])
                    and timestamp(attestation["validatedAtUtc"])
                    <= timestamp(approval["issuedAtUtc"])
                    < timestamp(approval["expiresAtUtc"])
                    <= timestamp(attestation["validUntilUtc"]),
                    "renewal_approval_time_invalid")
        candidate["contexts"] = copy.deepcopy(old["contexts"])
        candidate["endpoints"] = copy.deepcopy(old["endpoints"])
        for field in ("issuedAtUtc", "expiresAtUtc"):
            candidate["approval"][field] = old["approval"][field]
    for cfg in (candidate, original):
        cfg.pop("continuation", None)
        cfg.pop("allocatedSecondsPerVm", None)
        for field in ("continuationHash", "allocatedSecondsPerVm", "evidenceReference"):
            cfg["approval"].pop(field, None)
        if renewal is not None:
            cfg["approval"].pop("preflightRenewalHash", None)
        if certificate.get("schema") == "closed-recovery-v1":
            cfg.pop("wireCeilingBytes", None)
            cfg["approval"].pop("wireCeilingBytes", None)
    run.require(candidate == original and slot_seconds(config) >= slot_seconds(old),
                "continuation_may_only_amend_runtime")
    run.require(wire_limit(config) >= wire_limit(old), "recovery_wire_ceiling_decreased")
    run.require(certify_predecessor(directory, _seen, renewal=renewal,
                                   _successor_sources=certificate.get("successor_sources"),
                                   readiness_closure=certificate.get("readiness_closure")) == certificate,
                "predecessor_certificate_changed")
    claim = directory.parent / ".continuation-claims" / identity(str(directory.resolve()))
    if claim.exists():
        run.require(run.read(claim / "successor.private.json")["config_hash"] == identity(config),
                    "successor_claim_binding_changed")
    ledger = copy.deepcopy(ledger)
    for key, completion in certificate.get("salvaged_completions", {}).items():
        ledger["wire_measured"] += completion["wire_measured"] - ledger["chunks"][key].get("wire_measured", 0)
        ledger["chunks"][key] = copy.deepcopy(completion)
    validate_ledger(config, ledger)
    return directory, ledger


def verified_projections(directory, config, ledger, enforce=True):
    recovery = config.get("continuation", {}).get("schema") == "closed-recovery-v1"
    projections = {} if recovery else dict(ledger["projections"])
    for key, chunk in ledger["chunks"].items():
        if chunk["state"] != "complete":
            continue
        chunk_dir = chunk_origin(directory, chunk) / "chunks" / key
        plan = run.read(chunk_dir / "plan.private.json")
        report, _, elapsed = verified_completion(chunk_dir, plan)
        durations = [(timestamp(row["ended"]) - timestamp(row["started"])).total_seconds()
                     for row in report["legs"].values()]
        effective = min(config["rateBytesPerSecond"],
                        *(chunk["bytes"] / duration for duration in durations))
        phase = chunk["phase"]
        phase_chunks = [c for c in ledger["chunks"].values() if c["phase"] == phase]
        completed = [c for c in phase_chunks if c["state"] == "complete"]
        remaining = TARGET - sum(c["bytes"] for c in completed) if recovery else TARGET
        pairs = len(chunk_sizes(config.get("chunkBytes", stream.MAX_BYTES)))
        if recovery:
            pairs -= len(completed)
        projection = math.ceil(1.25 * (
            remaining / effective + pairs * max(0, elapsed - max(durations))))
        projections[phase] = max(projections.get(phase, 0), projection)
    if recovery:
        for phase in PHASES:
            chunks = [chunk for chunk in ledger["chunks"].values() if chunk["phase"] == phase]
            spent = sum(chunk.get("allocated_seconds", ALLOCATION_RESERVE) for chunk in chunks)
            projections[phase] += spent
    run.require(set(projections) == set(PHASES) and (
                not enforce or projections_fit(config, projections)),
                "continuation_projection_exceeds_runtime")
    return projections


def validate_ledger(config, ledger):
    sizes = chunk_sizes(config.get("chunkBytes", stream.MAX_BYTES))
    wire, measured = BOOTSTRAP, 0
    allocations = prior_allocations(config)
    run.require(ledger.get("prior_allocated_seconds", {"A": 0, "C": 0, "T": 0})
                == allocations, "prior_allocation_binding_changed")
    ids = []
    phase_indices = {phase: [] for phase in PHASES}
    for key, chunk in ledger["chunks"].items():
        phase, index = chunk["phase"], chunk["index"]
        base = phase + "-" + str(index).zfill(3)
        run.require(phase in PHASES and type(index) is int and 0 <= index < len(sizes)
                    and (key == base or re.fullmatch(re.escape(base) + r"-recovery-[1-9][0-9]*", key))
                    and chunk["bytes"] == sizes[index]
                    and chunk["wire_reserved"] == wire_reserve(sizes[index])
                    and chunk["state"] in ("reserved", "attempted", "complete", "failed_or_unknown")
                    and type(chunk["attempts"]) is int and chunk["attempts"] in (0, 1)
                    and (chunk["state"] not in ("attempted", "complete") or chunk["attempts"] == 1)
                    and re.fullmatch(r"[a-f0-9]{32}", chunk["id"]), "corrupt_chunk_ledger")
        if key != base:
            run.require(config.get("continuation", {}).get("schema") == "closed-recovery-v1"
                        and any(previous_key != key and previous["phase"] == phase
                                and previous["index"] == index
                                and previous["state"] == "failed_or_unknown"
                                for previous_key, previous in ledger["chunks"].items()),
                        "recovery_requires_preserved_failed_attempt")
        ids.append(chunk["id"])
        if chunk["state"] != "failed_or_unknown":
            phase_indices[phase].append(index)
        wire += chunk["wire_reserved"]
        used = chunk.get("wire_measured", 0)
        run.require(type(used) is int and 0 <= used <= chunk["wire_reserved"], "corrupt_wire_measurement")
        measured += used
        elapsed = chunk.get("allocated_seconds", ALLOCATION_RESERVE)
        run.require(type(elapsed) is int and 0 < elapsed <= ALLOCATION_RESERVE,
                    "corrupt_allocation_measurement")
        for role in (PHASES[phase], "T"):
            allocations[role] += elapsed
    run.require(len(ids) == len(set(ids)) and all(sorted(indices) == list(range(len(indices)))
                for indices in phase_indices.values()), "duplicate_or_skipped_chunk_id")
    run.require(ledger["wire_reserved"] == wire <= wire_limit(config)
                and ledger["wire_measured"] == measured <= wire
                and ledger["allocated_seconds"] == allocations
                and max(allocations.values()) <= slot_seconds(config), "global_counters_inconsistent")
    for context in ("core", "msdn"):
        p = config["contexts"][context]["preflight"]
        expected = (number(p["fixedInfraReserve"]) + number(p["txPerDecimalGB"]) * wire / 10 ** 9
                    + number(p["vmPerHour"]) * ALLOCATION_RESERVE * len(ids) / 3600)
        run.require(number(ledger["money_reserved"][context]) == expected
                    and (money_mode(config) == "monitor-only" or expected <= number(p["currencyCap"])),
                    "global_currency_counters_inconsistent")


@full_validation
def load(directory, active=True, full=False):
    config = run.read(directory / "config.private.json")
    ledger = run.read(directory / "ledger.private.json")
    scope = PHASE_SCOPE
    scoped = (not full and scope is not None
              and scope.directory == directory.resolve()
              and scope.lease == run.LEASE.resolve())
    if active:
        validate_config(config, fresh=False)
        run.require(ledger["sources"] == sources()
                    and (not scoped or ledger["sources"] == json.loads(scope.source_bytes)),
                    "immutable_session_or_source_changed")
    if scoped:
        run.require(identity(config) == scope.config_hash, "phase_config_changed")
    run.require(ledger["config_hash"] == identity(config), "immutable_session_or_source_changed")
    validate_ledger(config, ledger)
    predecessor = scope.predecessor() if scoped else continuation(config)
    if predecessor:
        previous, inherited = predecessor
        claim = directory.parent / ".continuation-claims" / identity(str(previous.resolve()))
        run.require(run.read(claim / "successor.private.json") == {
            "directory": str(directory.resolve()), "config_hash": identity(config)},
            "successor_claim_binding_changed")
        run.require(all(ledger["chunks"].get(key) == chunk
                        for key, chunk in inherited["chunks"].items()),
                    "inherited_progress_changed")
    return config, ledger


def validate_plan(plan, restoring=False):
    directory = Path(plan["repeat_session"])
    config, ledger = load(directory)
    chunk = ledger["chunks"][plan["repeat_chunk"]]
    expected = make_plan(config, directory, plan["repeat_chunk"], chunk)
    for key in expected:
        run.require(plan.get(key) == expected[key], "repeat_plan_binding_changed")
    run.require(chunk["state"] in ("reserved", "attempted", "complete"),
                "repeat_chunk_blocked_no_replay")
    if not restoring:
        run.require(ledger["state"] != "blocked" and (
            not ledger["active_phase"] or ledger["active_phase"]["chunk"] == plan["repeat_chunk"]),
            "repeat_session_blocked_or_foreign_owner")


def make_plan(config, directory, key, chunk):
    alias = PHASES[chunk["phase"]]
    endpoints, contexts = config["endpoints"], config["contexts"]
    pair = (alias, "T")
    result = {"id": chunk["id"], "repeat_session": str(directory.resolve()),
              "repeat_chunk": key, "scenario": "repeat-" + chunk["phase"],
              "aliases": {"client": alias, "server": "T"}, "legs": ["up", "down"],
              "server_ip": endpoints["T"]["publicIPv4"],
              "bytes": chunk["bytes"], "rate": config.get("rateBytesPerSecond", stream.RATE),
              "wire_cap": chunk["wire_reserved"], "core_remaining_bytes": wire_limit(config),
              "payload_sha256": chunk.get("payload_sha256"),
              "cleanup_deadline": config["cleanupDeadlineUtc"], "platforms": {},
              "inventories": {}}
    result["runtime_profile"] = run.repeat_runtime(result["bytes"], result["rate"])
    for role in pair:
        endpoint = endpoints[role]
        context = contexts["msdn" if role == "T" else "core"]
        result[role] = run.target(context, endpoint["inventory"], role.lower(), endpoint["region"])
        result[role]["region"] = endpoint["region"]
        result["platforms"][role] = context["platform"]
        result["inventories"][role] = endpoint["inventory"]
    return result


def reserve(directory, phase):
    with locked(directory):
        config, ledger = load(directory)
        run.require(ledger["state"] != "blocked" and not ledger["active_phase"],
                    "repeat_session_blocked_or_owned")
        sizes = chunk_sizes(config.get("chunkBytes", 5 * stream.GIB))
        certified_failed = set()
        if "continuation" in config:
            certified_failed = {key for key, c in run.read(
                Path(config["continuation"]["directory"]) / "ledger.private.json")["chunks"].items()
                if c["state"] == "failed_or_unknown"}
        pending = [c for key, c in ledger["chunks"].items()
                   if c["state"] != "complete" and key not in certified_failed]
        run.require(not pending, "unresolved_chunk_no_resend_or_refund")
        index = sum(c["phase"] == phase and c["state"] == "complete"
                    for c in ledger["chunks"].values())
        run.require(index < len(sizes), "phase_already_complete")
        if index:
            run.require(set(ledger["projections"]) == set(PHASES)
                        and projections_fit(config, ledger["projections"]),
                        "both_pilots_must_project_inside_twelve_hours")
        key = phase + "-" + str(index).zfill(3)
        base, generation = key, 0
        while key in ledger["chunks"]:
            generation += 1
            key = base + "-recovery-" + str(generation)
        wire = wire_reserve(sizes[index])
        run.require(ledger["wire_reserved"] + wire <= wire_limit(config), "global_wire_cap")
        money = dict(ledger["money_reserved"])
        for context, roles in (("core", [PHASES[phase]]), ("msdn", ["T"])):
            p = config["contexts"][context]["preflight"]
            amount = (number(money[context]) + number(p["txPerDecimalGB"]) * wire / 10 ** 9
                      + number(p["vmPerHour"]) * ALLOCATION_RESERVE / 3600)
            run.require(money_mode(config) == "monitor-only" or amount <= number(p["currencyCap"]),
                        "context_currency_cap")
            money[context] = str(amount)
            for role in roles:
                run.require(ledger["allocated_seconds"][role] + ALLOCATION_RESERVE <= slot_seconds(config),
                            "allocated_slot_cap")
                ledger["allocated_seconds"][role] += ALLOCATION_RESERVE
        chunk = {"phase": phase, "index": index, "id": uuid.uuid4().hex,
                 "bytes": sizes[index], "wire_reserved": wire, "state": "reserved",
                 "attempts": 0, "reservedAtUtc": run.now().isoformat()}
        ledger["chunks"][key] = chunk
        ledger.update(wire_reserved=ledger["wire_reserved"] + wire, money_reserved=money)
        atomic(directory / "ledger.private.json", ledger)
    # Reservation is durable before hashing, certificate generation, guests or contact.
    chunk_dir = directory / "chunks" / key
    chunk_dir.mkdir()
    chunk["payload_sha256"] = stream.digest(chunk["bytes"])
    with locked(directory):
        _, ledger = load(directory)
        ledger["chunks"][key] = chunk
        atomic(directory / "ledger.private.json", ledger)
    plan = make_plan(config, directory, key, chunk)
    plan.update(status="prepared_not_live", prepared_sources=run.source_identity(),
                mutations_reserved=12, operations=list(run.operations(plan)))
    run.certificates(chunk_dir / "tls", plan["server_ip"])
    atomic(chunk_dir / "plan.private.json", plan, True)
    commands = {}
    for operation in run.operations(plan, True):
        if not operation.startswith(("start-", "deallocate-")):
            continue
        alias = run.names(plan)["client"] if operation.endswith(
            run.names(plan)["client"].lower()) else "T"
        cfg = plan[alias]
        commands[operation] = {
            "platform": plan["platforms"][alias],
            "argv_before_native_path_conversion": [
                "vm", "start" if operation.startswith("start-") else "deallocate",
                "-g", cfg["resourceGroup"], "-n", cfg["vm"], "--no-wait",
                "--subscription", cfg["subscriptionId"], "--only-show-errors", "--output", "json"]}
    atomic(chunk_dir / "commands.private.json", commands, True)
    return key


def active_guard(directory, operation=None, seconds=0):
    config, ledger = load(directory)
    run.require(not (directory / "control" / "STOP").exists()
                and not (run.LAB / "deploy" / ".runtime-control" / "STOP").exists(),
                "repeat_stop")
    run.require(run.now() + timedelta(seconds=seconds) < timestamp(config["cleanupDeadlineUtc"]),
                "command_would_cross_repeat_ttl")
    run.require(ledger["state"] != "blocked" or operation in run.RESTORE
                or bool(operation and operation.startswith("read-restore:")),
                "repeat_session_blocked")
    lease = run.read(run.LEASE)
    run.require(lease["state"] == "active" and run.now() < timestamp(lease["expiresAtUtc"])
                <= timestamp(config["cleanupDeadlineUtc"]),
                "repeat_lease_stopped_or_expired")
    require_lease_binding(directory, lease, ledger)


def require_lease_binding(directory, lease, ledger=None):
    ledger = ledger if ledger is not None else run.read(directory / "ledger.private.json")
    phase = ledger["active_phase"]
    if phase:
        run.require(phase["taskId"] == lease["taskId"]
                    and phase["lease_path"] == str(run.LEASE.resolve())
                    and phase["authority_hash"] == lease_authority(lease),
                    "active_phase_lease_binding_changed")


@contextlib.contextmanager
def runner(directory, lease):
    global PHASE_SCOPE
    remaining = (timestamp(run.read(lease)["expiresAtUtc"]) - run.now()).total_seconds() - 10
    run.require(RUNNER_GATE.acquire(timeout=max(0, min(5, remaining))), "runner_context_busy")
    old = run.PRIVATE, run.LEASE, run.EXECUTION_GUARD, run.FULL_VALIDATION_GUARD, PHASE_SCOPE
    checkpoint_at, checkpoint_calls, warned = run.now(), 0, False

    def circuit(operation, seconds):
        nonlocal checkpoint_at, checkpoint_calls, warned
        active_guard(directory, operation, seconds)
        current = run.read(lease)
        start, end = map(timestamp, (current["startedAtUtc"], current["expiresAtUtc"]))
        elapsed = (run.now() - start).total_seconds()
        limit = (end - start).total_seconds()
        calls, mutations = current.get("actualToolCalls", 0), current.get("actualMutations", 0)
        eighty = (elapsed >= limit * .8 or calls >= current["maxToolCalls"] * .8
                  or (current["maxMutations"] and mutations >= current["maxMutations"] * .8))
        if (calls - checkpoint_calls >= 25 or (run.now() - checkpoint_at).total_seconds() >= 900
                or (eighty and not warned)):
            print("LIVE repeat | bounded-phase | " + str(round(elapsed)) + "/" + str(round(limit))
                  + "s | calls " + str(calls) + "/" + str(current["maxToolCalls"])
                  + " | mutations " + str(mutations) + "/" + str(current["maxMutations"])
                  + " | state " + ("restoring" if eighty else "running")
                  + " | next " + ("authorized closure only" if eighty else "current bounded step"),
                  flush=True)
            checkpoint_at, checkpoint_calls, warned = run.now(), calls, eighty

    try:
        run.PRIVATE, run.LEASE, run.EXECUTION_GUARD = directory / "chunks", lease, circuit
        PHASE_SCOPE = None
        with validation_pass() as evidence:
            config, ledger = load(directory, full=True)
            predecessor = continuation(config)
            frozen = [str(predecessor[0]), predecessor[1]] if predecessor else None
            PHASE_SCOPE = PhaseProof(
                directory.resolve(), lease.resolve(), identity(config),
                json.dumps(ledger["sources"], sort_keys=True).encode(),
                json.dumps(frozen, sort_keys=True).encode(),
                tuple((str(path), entries) for path, entries in evidence.items()))
        def mutation_validation(operation=None, seconds=0):
            # Historical authority is the immutable admission byte snapshot, not
            # mutable files or a timestamp cache. Current authority is never cached.
            run.require(PHASE_SCOPE is not None, "phase_proof_missing")
            active_guard(directory, operation, seconds)
        run.FULL_VALIDATION_GUARD = mutation_validation
        yield
    finally:
        (run.PRIVATE, run.LEASE, run.EXECUTION_GUARD,
         run.FULL_VALIDATION_GUARD, PHASE_SCOPE) = old
        RUNNER_GATE.release()


def execute(directory, key, action, lease_path):
    run.require(action in ("readiness", "snapshot", "pilot", "batch"), "invalid_repeat_action")
    begin(directory, key, action, lease_path)
    print("LIVE repeat | " + action + " | state running | next existing guarded runner", flush=True)
    try:
        with runner(directory, lease_path):
            run.execute(argparse.Namespace(action="live" if action in ("pilot", "batch") else action,
                                           run=key, accept_live_gates=True))
            if action in ("pilot", "batch"):
                finish(directory, key)
            else:
                load(directory, full=True)
                plan = run.read(directory / "chunks" / key / "plan.private.json")
                run.require_readiness(directory / "chunks" / key, plan)
                with locked(directory):
                    _, ledger = load(directory)
                    lease = run.read(lease_path)
                    require_closed(lease, 75)
                    run.require(ledger["active_phase"]["authority_hash"] == lease_authority(lease),
                                "active_phase_lease_binding_changed")
                    ledger["chunks"][key].setdefault("phases", {})[action] = {
                        "taskId": lease["taskId"], "lease_path": str(lease_path.resolve()),
                        "lease_hash": identity(lease)}
                    ledger["active_phase"] = None
                    atomic(directory / "ledger.private.json", ledger)
    except BaseException:
        if run.read(directory / "ledger.private.json")["chunks"][key]["state"] == "complete":
            # Verified closure is durable; a future-work forecast cannot revoke it.
            raise
        fail(directory, key)
        with runner(directory, lease_path):
            with run.lease_lock("read-restore:accounting"):
                lease = run.read(lease_path)
                require_lease_binding(directory, lease)
                lease.update(state="blocked", lastCheckpointUtc=run.now().isoformat(),
                             ownedProcessesIdle=lease.get("activeCommands", 0) == 0)
                atomic(lease_path, lease)
        print("BLOCKED repeat; no replay/refund; independent fresh recovery owner required",
              file=sys.stderr, flush=True)
        raise
    print("LIVE repeat | " + action + " | state stopped | next separate fresh phase lease", flush=True)


def claim(directory, key, lease_path):
    """Claim traffic only after source-bound, deallocated readiness and snapshot."""
    _, ledger = load(directory)
    action = "pilot" if ledger["chunks"][key]["index"] == 0 else "batch"
    begin(directory, key, action, lease_path)


def require_closed(lease, calls, failed=False):
    run.require(lease["state"] in (("completed", "rolled_back", "blocked") if failed else ("completed",))
                and lease["activeCommands"] == 0
                and lease["ownedProcessesIdle"] is True
                and lease["actualToolCalls"] <= lease["maxToolCalls"] <= calls
                and lease["actualMutations"] <= lease["maxMutations"],
                "closed_idle_bounded_lease_required")


def require_prepared_traffic(directory, key, chunk, plan):
    chunk_dir = directory / "chunks" / key
    run.require(set(chunk.get("phases", {})) == {"readiness", "snapshot"},
                "separate_readiness_and_snapshot_required")
    for receipt in chunk["phases"].values():
        lease = run.read(receipt["lease_path"])
        require_closed(lease, 75)
        run.require(lease["taskId"] == receipt["taskId"] and identity(lease) == receipt["lease_hash"],
                    "phase_receipt_changed")
    run.require_readiness(chunk_dir, plan)
    run.require(plan["status"] == "prepared_not_live"
                and plan.get("snapshot_sources") == run.source_identity()
                and plan.get("snapshot_at")
                and 0 <= (run.now() - timestamp(plan["snapshot_at"])).total_seconds() < 600,
                "fresh_snapshot_required")


def lease_template(directory, key, action):
    run.require(action in ("readiness", "snapshot", "pilot", "batch"), "invalid_repeat_action")
    config, _ = load(directory)
    plan = run.read(directory / "chunks" / key / "plan.private.json")
    profile = run.runtime(plan)
    traffic = action in ("pilot", "batch")
    start = run.now()
    return {"taskId": "REPLACE-UNIQUE-TASK", "ownerId": "REPLACE-FRESH-PHASE-OWNER",
            "ownerRole": "Niobe" if action == "snapshot" else "Tank",
            "objective": "repeat:" + directory.name + ":" + key + ":" + action,
            "state": "pending", "startedAtUtc": start.isoformat(),
            "expiresAtUtc": min(start + timedelta(minutes=60 if traffic else 30),
                                timestamp(config["cleanupDeadlineUtc"])).isoformat(),
            "maxToolCalls": 150 if traffic else 75,
            "maxMutations": 12 if traffic else 6 if action == "readiness" else 0,
            "runtime_profile": profile,
            "commandTimeoutSeconds": profile["commandSeconds"] if traffic else 180,
            "namedCommandTimeoutSeconds": {
                "server": profile["commandSeconds"], "client": profile["commandSeconds"]}
            if traffic else {},
            "restoreTimeoutMinutes": 15,
            "forbiddenWork": ["resource creation", "authentication changes", "bulk evidence",
                              "documentation", "automatic payload retry"],
            "allowedMutations": list(run.operations(plan, True)) if action == "readiness" else
                                list(run.operations(plan)) if traffic else [],
            "rollback": "verified-deallocation-then-original-nsgs-or-blocked-independent-recovery",
            "acceptLiveGates": False, "actualToolCalls": 0, "actualMutations": 0,
            "activeCommands": 0, "ownedProcessesIdle": True,
            "lastCheckpointUtc": start.isoformat()}


def begin(directory, key, action, lease_path):
    with locked(directory):
        config, ledger = load(directory)
        run.require(not ledger["active_phase"] and ledger["state"] != "blocked",
                    "prior_phase_unresolved_no_replay")
        run.require(lease_path.resolve().parent == (directory / "control").resolve(),
                    "fresh_repeat_control_namespace_required")
        chunk = ledger["chunks"][key]
        run.require(chunk["state"] == "reserved" and chunk["attempts"] == 0,
                    "chunk_attempted_no_replay")
        plan = run.read(directory / "chunks" / key / "plan.private.json")
        validate_plan(plan)
        traffic = action in ("pilot", "batch")
        run.require(not traffic or (action == "pilot") == (chunk["index"] == 0),
                    "pilot_or_batch_index_mismatch")
        run.require(action not in chunk.get("phases", {}), "phase_already_completed_no_replay")
        if action == "snapshot":
            run.require("readiness" in chunk.get("phases", {}), "readiness_phase_required")
        if traffic:
            require_prepared_traffic(directory, key, chunk, plan)
        lease = run.read(lease_path)
        template = lease_template(directory, key, action)
        run.require(lease["taskId"] not in ledger["leases"]
                    and all(type(lease.get(field)) is int for field in (
                        "maxToolCalls", "maxMutations", "commandTimeoutSeconds",
                        "restoreTimeoutMinutes", "actualToolCalls", "actualMutations",
                        "activeCommands"))
                    and lease["ownerRole"] == template["ownerRole"]
                    and lease.get("ownerId") and lease["ownerId"] != "REPLACE-FRESH-PHASE-OWNER"
                    and lease["ownerId"] not in ledger.get("owners", [])
                    and lease.get("objective") == template["objective"]
                    and lease.get("rollback") == template["rollback"]
                    and lease.get("restoreTimeoutMinutes") == 15
                    and lease["commandTimeoutSeconds"] == template["commandTimeoutSeconds"]
                    and lease.get("runtime_profile") == template["runtime_profile"]
                    and lease.get("namedCommandTimeoutSeconds") == template["namedCommandTimeoutSeconds"]
                    and (75 <= lease["maxToolCalls"] <= 150 if traffic else
                         30 <= lease["maxToolCalls"] <= 75)
                    and lease["maxMutations"] == template["maxMutations"]
                    and set(lease["allowedMutations"]) == set(template["allowedMutations"])
                    and lease.get("actualToolCalls", 0) == lease.get("actualMutations", 0) == 0
                    and lease.get("activeCommands", 0) == 0
                    and lease.get("ownedProcessesIdle") is True
                    and (not traffic or lease.get("acceptLiveGates") is True),
                    "new_bounded_idle_phase_lease_required")
        run.require(timestamp(lease["expiresAtUtc"]) - timestamp(lease["startedAtUtc"])
                    <= timedelta(minutes=60 if traffic else 30), "phase_elapsed_bound")
        with runner(directory, lease_path):
            active_guard(directory)
            run.guard("server" if traffic else None,
                      run.runtime(plan)["commandSeconds"] if traffic else 180)
        run.require(timestamp(lease["expiresAtUtc"]) <= timestamp(config["cleanupDeadlineUtc"]),
                    "lease_would_cross_repeat_ttl")
        if traffic:
            chunk.update(state="attempted", attempts=1, lease=lease["taskId"],
                         lease_path=str(lease_path.resolve()))
        ledger["leases"].append(lease["taskId"])
        ledger.setdefault("owners", []).append(lease["ownerId"])
        ledger["active_phase"] = {"chunk": key, "taskId": lease["taskId"], "action": action,
                                  "lease_path": str(lease_path.resolve()),
                                  "authority_hash": lease_authority(lease)}
        atomic(directory / "ledger.private.json", ledger)


def fail(directory, key):
    with locked(directory):
        ledger = run.read(directory / "ledger.private.json")
        if ledger["chunks"][key]["state"] == "complete":
            return
        ledger["chunks"][key]["state"] = "failed_or_unknown"
        ledger["state"] = "blocked"
        if ledger["active_phase"]:
            ledger["active_phase"]["state"] = "blocked"
        atomic(directory / "ledger.private.json", ledger)


def metric_rows(report):
    rows = []
    for metric in report["value"]:
        name = metric["name"]["value"]
        run.require(name in ("Network In Total", "Network Out Total"), "unknown_network_metric")
        for series in metric["timeseries"]:
            for point in series["data"]:
                total = point.get("total")
                if total is not None:
                    run.require(type(total) in (int, float) and math.isfinite(total)
                                and total >= 0, "invalid_network_metric")
                    rows.append({"metric": name, "timestamp": timestamp(point["timeStamp"]).isoformat(),
                                 "total": total})
    run.require(len(rows) <= 2880, "network_metric_evidence_bound")
    return rows


def finish(directory, key):
    try:
        _finish(directory, key)
    except BaseException:
        fail(directory, key)
        raise


def _finish(directory, key):
    load(directory, full=True)
    chunk_dir = directory / "chunks" / key
    plan = run.read(chunk_dir / "plan.private.json")
    validate_plan(plan)
    a, t, elapsed = verified_completion(chunk_dir, plan)
    verdict = stream.verify(a, t, plan)
    live_start, live_end = timestamp(plan["live_started"]), timestamp(plan["ended"])
    with locked(directory):
        _record_completion(directory, key, chunk_dir, plan, a, t, elapsed, verdict,
                           live_start, live_end)


def verified_completion(chunk_dir, plan):
    a, t = (run.read(chunk_dir / (role + "-report.private.json"))
            for role in ("client", "server"))
    verdict = stream.verify(a, t, plan)
    run.require(plan["status"] == "completed" and not plan["failures"],
                "transport_and_restoration_required")
    for alias in run.endpoint_names(plan):
        evidence = run.read(chunk_dir / ("deallocate-" + alias.lower() + "-verified.private.json"))
        run.require(evidence.get("verified") is True
                    and evidence.get("binding") == {"id": plan["id"], "endpoint": plan[alias]}
                    and timestamp(plan["restore_started"]) <= timestamp(evidence["at"])
                    <= timestamp(plan["ended"]), "final_deallocation_proof_required")
    for prefix in ("nsg", "subnet-nsg") if plan.get("receiver_subnet_nsg") else ("nsg",):
        evidence = run.read(chunk_dir / (prefix + "-restored.private.json"))
        run.require(evidence.get("verified") is True
                    and timestamp(plan["restore_started"]) <= timestamp(evidence["at"])
                    <= timestamp(plan["ended"]), "final_nsg_restore_proof_required")
    run.require(all(report["requests"] == 2 and len(report["legs"]) == 2 for report in (a, t)),
                "exact_two_requests_per_chunk_required")
    ready = run.read(chunk_dir / "readiness.private.json")
    live_start, live_end = timestamp(plan["live_started"]), timestamp(plan["ended"])
    ready_start, ready_end = timestamp(ready["started_at"]), timestamp(ready["completed_at"])
    run.require(ready["success"] is True and ready_start <= ready_end <= live_start <= live_end
                and all(ready["deallocated"].get(alias) is True for alias in run.endpoint_names(plan))
                and all(live_start <= timestamp(row["started"]) < timestamp(row["ended"]) <= live_end
                        for report in (a, t) for row in report["legs"].values()),
                "invalid_readiness_or_traffic_timeline")
    elapsed = ((timestamp(ready["completed_at"]) - timestamp(ready["started_at"])).total_seconds()
               + (timestamp(plan["ended"]) - timestamp(plan["live_started"])).total_seconds())
    run.require(0 < elapsed <= ALLOCATION_RESERVE, "allocation_reservation_exceeded")
    return a, t, elapsed


def _record_completion(directory, key, chunk_dir, plan, a, t, elapsed, verdict,
                       live_start, live_end):
        config, ledger = load(directory, full=True)
        verified_completion(chunk_dir, plan)
        chunk = ledger["chunks"][key]
        run.require(chunk["state"] == "attempted" and chunk["attempts"] == 1
                    and ledger["active_phase"]
                    and ledger["active_phase"]["chunk"] == key,
                    "chunk_completion_not_replayable")
        lease = run.read(chunk["lease_path"])
        run.require(lease["taskId"] == chunk["lease"] and lease["state"] == "completed"
                    and lease["activeCommands"] == 0 and lease["ownedProcessesIdle"] is True
                    and lease["actualToolCalls"] <= lease["maxToolCalls"] <= 150
                    and lease["actualMutations"] <= lease["maxMutations"] <= 12,
                    "closed_idle_bounded_lease_required")
        run.require(ledger["active_phase"]["authority_hash"] == lease_authority(lease),
                    "active_phase_lease_binding_changed")
        run.require(timestamp(lease["startedAtUtc"]) <= live_start <= live_end
                    <= timestamp(lease["expiresAtUtc"]), "traffic_outside_lease")
        alias = PHASES[chunk["phase"]]
        chunk.update(state="complete", allocated_seconds=math.ceil(elapsed),
                     wire_measured=a["nic"]["delta"]["wire_once"],
                     endedAtUtc=plan["ended"], verdict=verdict,
                     tx_by_producer={alias: a["nic"]["delta"]["tx"], "T": t["nic"]["delta"]["tx"]},
                     guest_nic={alias: a["nic"]["delta"], "T": t["nic"]["delta"]},
                     network_hash=identity(plan["network_bindings"]),
                     endpoint_hash_proofs={role: identity(report["legs"])
                                           for role, report in (("client", a), ("server", t))},
                     network_metrics={role: metric_rows(run.read(
                         chunk_dir / (role + "-metrics-after.private.json"))) for role in (alias, "T")})
        ledger["wire_measured"] += chunk["wire_measured"]  # Client RX+TX once, not both endpoints.
        ledger["active_phase"] = None
        for role in (alias, "T"):
            ledger["allocated_seconds"][role] += math.ceil(elapsed) - ALLOCATION_RESERVE
        if chunk["index"] == 0 or "continuation" in config:
            sizes = chunk_sizes(config.get("chunkBytes", 5 * stream.GIB))
            durations = [(timestamp(row["ended"]) - timestamp(row["started"])).total_seconds()
                         for row in a["legs"].values()]
            bulk = max(durations)
            run.require(bulk > 0, "pilot_duration_required")
            measured_rate = min(chunk["bytes"] / duration for duration in durations if duration > 0)
            effective = min(measured_rate, config.get("rateBytesPerSecond", stream.RATE))
            overhead = max(0, elapsed - bulk)
            # 25% margin; all 20 pairs, both concurrent directions, each phase separately.
            projection = math.ceil(1.25 * (TARGET / effective + len(sizes) * overhead))
            ledger["projections"][chunk["phase"]] = max(
                ledger["projections"].get(chunk["phase"], 0), projection)
            if config.get("continuation", {}).get("schema") == "closed-recovery-v1":
                ledger["projections"] = verified_projections(directory, config, ledger, enforce=False)
            if not projections_fit(config, ledger["projections"]):
                ledger["state"] = "blocked"
        atomic(directory / "ledger.private.json", ledger)
        run.require(ledger["state"] != "blocked", "pilot_projection_exceeds_t_slot_stop")


def status(directory):
    config, ledger = load(directory, active=False)
    progress = {leg: 0 for leg in ("A->T", "T->A", "C->T", "T->C")}
    rows, tx = [], {"A": 0, "C": 0, "T": 0}
    for key, chunk in ledger["chunks"].items():
        alias = PHASES[chunk["phase"]]
        if chunk["state"] == "complete":
            for leg in (alias + "->T", "T->" + alias):
                progress[leg] += chunk["bytes"]
            for producer, count in chunk["tx_by_producer"].items():
                tx[producer] += count
        rows.append({"chunk": key, "state": chunk["state"], "attempts": chunk["attempts"],
                     "bytes_per_leg": chunk["bytes"], "payload_sha256": chunk.get("payload_sha256"),
                     "ended_at_utc": chunk.get("endedAtUtc"),
                     "usage_utc_day": chunk.get("endedAtUtc", "")[:10],
                     "guest_nic": chunk.get("guest_nic"),
                     "network_hash": chunk.get("network_hash"),
                     "endpoint_hash_proofs": chunk.get("endpoint_hash_proofs"),
                     "network_metrics": chunk.get("network_metrics")})
    return {"state": ledger["state"], "progress_application_bytes": progress,
            "complete": ledger["state"] != "blocked" and all(
                value == TARGET for value in progress.values()),
            "wire_reserved": ledger["wire_reserved"], "wire_measured_once": ledger["wire_measured"],
            "tx_by_producer": tx, "allocated_seconds": ledger["allocated_seconds"],
            "prior_allocated_seconds": prior_allocations(config),
            "allocated_seconds_per_vm": slot_seconds(config),
            "wire_ceiling_bytes": wire_limit(config),
            "continuation_certificate_hash": config["approval"].get("continuationHash"),
            "pilot_projected_seconds": ledger["projections"], "chunks": rows,
            "money_budget_mode": money_mode(config),
            "money_estimate_to_date": money_estimate(
                config, ledger["wire_reserved"], len(ledger["chunks"])),
            "billing": "INCONCLUSIVE", "source_hashes": ledger["sources"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("skeleton", "plan", "prepare", "prepare-chunk", "readiness",
                                           "snapshot", "pilot", "batch", "resume", "status",
                                           "lease-template", "certify-continuation"))
    parser.add_argument("--session", required=True)
    parser.add_argument("--config")
    parser.add_argument("--renewal-attestation",
                        help="Private independent read-only PASS attestation; certification only")
    parser.add_argument("--readiness-closure",
                        help="Hash-bound independent closed-readiness restore attestation; certification only")
    parser.add_argument("--phase", choices=tuple(PHASES))
    parser.add_argument("--chunk")
    parser.add_argument("--lease")
    parser.add_argument("--lease-kind", choices=("readiness", "snapshot", "pilot", "batch"))
    args = parser.parse_args()
    run.require(not args.renewal_attestation or args.action == "certify-continuation",
                "renewal_attestation_certification_only")
    run.require(not args.readiness_closure or args.action == "certify-continuation",
                "readiness_closure_certification_only")
    run.require(re.fullmatch(r"[a-z0-9-]{1,64}", args.session), "invalid_session_name")
    directory = ROOT / args.session
    if args.action == "skeleton":
        print(json.dumps(skeleton(), indent=2))
    elif args.action in ("plan", "prepare"):
        run.require(args.config, "private_config_required")
        config = run.read(args.config)
        if args.action == "plan":
            print(json.dumps(plan_summary(config), indent=2))
        else:
            prepare(config, directory)
            print("PREPARED; no Azure calls; fresh leases and deployment gates still required")
    elif args.action in ("prepare-chunk", "resume"):
        run.require(args.phase, "phase_required")
        print(reserve(directory, args.phase))
    elif args.action == "status":
        print(json.dumps(status(directory), indent=2))
    elif args.action == "certify-continuation":
        renewal = None
        if args.renewal_attestation:
            path = Path(args.renewal_attestation).absolute()
            run.require(path.resolve().is_relative_to((run.LAB / "private").resolve())
                        and not path.is_symlink(), "private_renewal_attestation_required")
            renewal = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        closure = None
        if args.readiness_closure:
            path = Path(args.readiness_closure).absolute()
            run.require(path.resolve().is_relative_to((run.LAB / "private").resolve())
                        and not path.is_symlink(), "readiness_closure_private_path_required")
            closure = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        print(json.dumps(certify_predecessor(directory, renewal=renewal,
                                            readiness_closure=closure), indent=2))
    elif args.action == "lease-template":
        run.require(args.chunk and args.lease_kind, "chunk_and_lease_kind_required")
        print(json.dumps(lease_template(directory, args.chunk, args.lease_kind), indent=2))
    else:
        run.require(args.chunk and args.lease, "chunk_and_fresh_phase_lease_required")
        execute(directory, args.chunk, args.action, Path(args.lease))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        text = str(error)
        print("BLOCKED " + (text if re.fullmatch(r"[a-z0-9_]+", text)
                           else type(error).__name__), file=sys.stderr)
        sys.exit(1)
