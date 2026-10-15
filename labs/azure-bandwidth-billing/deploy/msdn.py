"""One isolated WSL endpoint; native Linux CLI, explicit context, bounded ownership."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

LAB = Path(__file__).resolve().parents[1]
PRIVATE = LAB / "private"
LEASE = LAB / "deploy" / ".runtime-control" / "msdn-lease.json"
CONTEXT = PRIVATE / "wsl-cost-context.private.json"
STATE = PRIVATE / "msdn-inventory.private.json"
ARM = "https://management.azure.com"
LOCATION = "swedencentral"
KINDS = {
    "Microsoft.Network/virtualNetworks": "vnet-t",
    "Microsoft.Network/publicIPAddresses": "pip-t",
    "Microsoft.Network/networkSecurityGroups": "nsg-t",
    "Microsoft.Network/networkInterfaces": "nic-t",
    "Microsoft.Compute/virtualMachines": "vm-t",
    "Microsoft.Compute/disks": "os-t",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return dt.datetime.now(dt.timezone.utc)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def check(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def guard(restore=False, mutation=False, seconds=30):
    lease = read(LEASE)
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    remaining = (expiry - now()).total_seconds()
    check(lease["state"] == "active" and not (LEASE.parent / "STOP").exists()
          and remaining > seconds + 5, "inactive_or_expiring_lease")
    check(seconds <= lease["commandTimeoutSeconds"], "command_timeout_exceeds_lease")
    check(lease.get("actualToolCalls", 0) < lease["maxToolCalls"], "tool_call_limit")
    if mutation:
        check(lease.get("actualMutations", 0) < lease["maxMutations"], "mutation_limit")
    if not restore:
        start = expiry - dt.timedelta(minutes=30)
        check(now() < start + dt.timedelta(minutes=24), "restoration_only_elapsed")
        check(lease.get("actualMutations", 0) < lease["maxMutations"] * .8
              and lease.get("actualToolCalls", 0) < lease["maxToolCalls"] * .8,
              "restoration_only_budget")
    return lease


def bounded(argv, seconds):
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        out, err = process.communicate(timeout=seconds)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=5)
        raise
    if process.returncode:
        # Error details remain private: Azure errors can contain subscription/resource IDs.
        save(PRIVATE / "msdn-last-error.private.json",
             {"atUtc": now().isoformat(), "exitCode": process.returncode,
              "stderr": err.decode(errors="replace")})
        raise RuntimeError("native_cli_failed_see_private_error")
    return json.loads(out) if out.strip() else None


class Client:
    def __init__(self):
        check(os.name != "nt" and Path("/usr/bin/az").is_file(), "native_wsl_only")
        self.context = read(CONTEXT)
        self.sub = str(uuid.UUID(self.context["subscriptionId"]))
        self.tenant = str(uuid.UUID(self.context["expectedTenantId"]))
        windows = read(PRIVATE / "context.private.json")
        check(self.sub != windows["subscriptionId"] and self.tenant != windows["expectedTenantId"],
              "windows_context_not_distinct")

    def cli(self, args, seconds=30, restore=False, mutation=False):
        lease = guard(restore, mutation, seconds)
        lease["actualToolCalls"] = lease.get("actualToolCalls", 0) + 1
        lease["ownedProcessesIdle"] = False
        if mutation:
            lease["actualMutations"] = lease.get("actualMutations", 0) + 1
        save(LEASE, lease)
        try:
            return bounded(["/usr/bin/az"] + args + ["--subscription", self.sub,
                           "--output", "json", "--only-show-errors"], seconds)
        finally:
            lease = read(LEASE)
            lease["ownedProcessesIdle"] = True
            lease["lastCheckpointUtc"] = now().isoformat()
            save(LEASE, lease)

    def authorize(self, restore=False):
        account = self.cli(["account", "show"], seconds=15, restore=restore)
        check(account.get("id") == self.sub and account.get("tenantId") == self.tenant
              and account.get("state") == "Enabled", "account_context_mismatch")
        token = self.cli(["account", "get-access-token", "--resource", ARM],
                         seconds=15, restore=restore)
        check(token.get("subscription") == self.sub and token.get("tenant") == self.tenant
              and token.get("accessToken"), "token_context_mismatch")
        return token["accessToken"]

    def mutate(self, args, seconds=60, restore=False):
        permissions = {
            ("group", "create"): "create a new tagged MSDN lab resource group",
            ("deployment", "group", "validate"): "validate the one-VM ARM template",
            ("deployment", "group", "create"): "deploy the approved endpoint with required ownership tags",
            ("vm", "deallocate"): "deallocate the created VM before returning",
            ("group", "delete"): "delete the exact inventoried MSDN lab resource group",
        }
        operation = tuple(args[:3]) if args[:2] == ["deployment", "group"] else tuple(args[:2])
        lease = guard(restore, mutation=True, seconds=seconds)
        check(operation in permissions and permissions[operation] in lease.get("allowedMutations", []),
              "operation_not_authorized_by_lease")
        self.authorize(restore)
        guard(restore, mutation=True, seconds=seconds)
        return self.cli(args, seconds, restore, mutation=True)

    def catalog(self):
        token = self.authorize()
        guard(seconds=120)
        deadline = time.monotonic() + 120
        prefix = ARM + "/subscriptions/" + self.sub
        url = prefix + "/providers/Microsoft.Compute/skus?" + urllib.parse.urlencode(
            {"api-version": "2021-07-01", "$filter": "location eq 'swedencentral'"})
        rows = []
        for page in range(10):
            check(time.monotonic() < deadline, "catalog_deadline")
            request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
            with urllib.request.build_opener(NoRedirect()).open(
                    request, timeout=min(25, deadline - time.monotonic())) as r:
                data = json.load(r)
            rows.extend(x for x in data.get("value", []) if x.get("resourceType") == "virtualMachines"
                        and x.get("name") in ("Standard_B1ls", "Standard_B1s", "Standard_B2ts_v2"))
            url = data.get("nextLink")
            if not url:
                break
            parsed = urllib.parse.urlsplit(url)
            check(parsed.scheme == "https" and parsed.netloc == "management.azure.com"
                  and parsed.path.lower() == ("/subscriptions/" + self.sub
                  + "/providers/Microsoft.Compute/skus").lower()
                  and not parsed.fragment and not parsed.username, "unsafe_catalog_continuation")
        else:
            raise RuntimeError("catalog_page_limit")
        return rows


def available(row):
    if row.get("name") == "Standard_B1ls":
        return False  # 0.5 GiB is below the approved TLS/agent minimum.
    caps = {x["name"]: x["value"] for x in row.get("capabilities", [])}
    return (float(caps.get("MemoryGB", 0)) >= 1
            and not any(x.get("type", "").lower() == "location"
                        for x in row.get("restrictions", [])))


def owned(state, client):
    check(re.fullmatch(r"bwt-[0-9a-f]{12}", state["runId"]) is not None, "invalid_run")
    check(state["resourceGroup"] == "rg-" + state["runId"]
          and state["subscriptionId"] == client.sub
          and state["expectedTenantId"] == client.tenant
          and state.get("createdByThisRun") is True, "ownership_not_proven")
    return {"lab": "true", "created_by": "copilot-lab", "run_id": state["runId"]}


def snapshot(client, state, restore=False, complete=False, persist=True):
    tags = owned(state, client)
    group = client.cli(["group", "show", "--name", state["resourceGroup"]], restore=restore)
    check(group["id"].lower() == ("/subscriptions/" + client.sub + "/resourceGroups/"
                                 + state["resourceGroup"]).lower()
          and group.get("tags") == tags, "group_ownership_mismatch")
    rows = client.cli(["resource", "list", "--resource-group", state["resourceGroup"]],
                      restore=restore)
    expected = {("/subscriptions/" + client.sub + "/resourceGroups/" + state["resourceGroup"]
                 + "/providers/" + kind + "/" + state["runId"] + "-" + suffix).lower(): kind
                for kind, suffix in KINDS.items()}
    for row in rows:
        check(row["id"].lower() in expected
              and row["type"].lower() == expected[row["id"].lower()].lower()
              and row.get("tags") == tags and row.get("location", "").lower() == LOCATION,
              "foreign_or_untagged_resource")
    if complete:
        check({x["id"].lower() for x in rows} == set(expected), "incomplete_inventory")
    if persist:
        state["resources"] = rows
        state["snapshotAtUtc"] = now().isoformat()
        if restore and complete:
            details = [client.cli(["resource", "show", "--ids", row["id"]], restore=True)
                       for row in rows]
            check(all(x.get("tags") == tags and
                      x.get("properties", {}).get("provisioningState") == "Succeeded"
                      for x in details), "resource_detail_verification_failed")
            state["detailedResources"] = details
        save(STATE, state)
    return rows


def restore_vm(client, state):
    # Exact VM identity is established from a newly created group, not a subscription search.
    tags = owned(state, client)
    vm = state["runId"] + "-vm-t"
    group = client.cli(["group", "show", "--name", state["resourceGroup"]], restore=True)
    check(group.get("tags") == tags, "restore_group_ownership_mismatch")
    exists = client.cli(["vm", "list", "--resource-group", state["resourceGroup"]], restore=True)
    check(all(x["name"] == vm and x.get("tags") == tags for x in exists),
          "unexpected_vm_restore_blocked")
    if not exists:
        state["restoreState"] = "no_vm_present"
        save(STATE, state)
        return
    client.mutate(["vm", "deallocate", "--resource-group", state["resourceGroup"], "--name", vm],
                  seconds=180, restore=True)
    view = client.cli(["vm", "get-instance-view", "--resource-group", state["resourceGroup"],
                       "--name", vm], seconds=45, restore=True)
    codes = [x["code"] for x in view.get("instanceView", view).get("statuses", [])]
    check("PowerState/deallocated" in codes, "deallocation_not_verified")
    state["power"] = codes
    state["deallocatedAtUtc"] = now().isoformat()
    state["restoreState"] = "deallocated"
    save(STATE, state)
    print("RESTORED PowerState/deallocated at " + state["deallocatedAtUtc"], flush=True)


def preflight(client):
    rows = client.catalog()
    selected = next((name for name in ("Standard_B1s", "Standard_B2ts_v2")
                     if any(x["name"] == name and available(x) for x in rows)), None)
    check(selected is not None, "no_approved_sku")
    # Both sizes were independently quoted at $0.0108/h in SC on 2026-10-15.
    for provider in ("Microsoft.Compute", "Microsoft.Network"):
        result = client.cli(["provider", "show", "--namespace", provider])
        check(result.get("registrationState") == "Registered", "provider_not_registered")
    key = Path.home() / ".ssh" / "id_rsa.pub"
    if not key.is_file():
        key = LAB.parents[3] / ".ssh" / "id_rsa.pub"
    check(key.is_file(), "existing_public_key_missing")
    public = key.read_text().strip()
    check(public.startswith(("ssh-rsa ", "ssh-ed25519 ", "ecdsa-sha2-"))
          and "\n" not in public and "PRIVATE" not in public, "invalid_public_key")
    gate = {"atUtc": now().isoformat(), "subscriptionId": client.sub,
            "expectedTenantId": client.tenant, "vmSize": selected, "location": LOCATION,
            "publicKeyPath": str(key), "catalog": rows}
    save(PRIVATE / "msdn-gate.private.json", gate)
    print("PREFLIGHT PASS " + selected + " swedencentral; distinct subscription and tenant")


def deploy(client, confirm):
    check(confirm == "DEPLOY-ONE-MSDN-ENDPOINT", "explicit_deployment_confirmation_required")
    check(not STATE.exists(), "existing_inventory_refuse_blind_redeploy")
    gate = read(PRIVATE / "msdn-gate.private.json")
    check(gate["subscriptionId"] == client.sub and gate["expectedTenantId"] == client.tenant
          and gate["location"] == LOCATION and gate["vmSize"] in ("Standard_B1s", "Standard_B2ts_v2")
          and (now() - dt.datetime.fromisoformat(gate["atUtc"])).total_seconds() < 900,
          "stale_or_wrong_gate")
    lease = guard(seconds=600)
    check(lease["maxMutations"] - lease.get("actualMutations", 0) >= 4,
          "reserve_four_mutation_commands")
    check((dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
           - now()).total_seconds() > 900, "insufficient_deploy_restore_time")
    run = "bwt-" + uuid.uuid4().hex[:12]
    state = {"runId": run, "resourceGroup": "rg-" + run, "subscriptionId": client.sub,
             "expectedTenantId": client.tenant, "location": LOCATION, "vmSize": gate["vmSize"],
             "createdByThisRun": False, "resources": []}
    check(client.cli(["group", "exists", "--name", state["resourceGroup"]]) is False,
          "preexisting_group_refused")
    save(STATE, state)
    tags = ["lab=true", "created_by=copilot-lab", "run_id=" + run]
    parameters = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
                  "contentVersion": "1.0.0.0", "parameters": {
                      "runId": {"value": run}, "vmSize": {"value": gate["vmSize"]},
                      "adminPublicKey": {"value": Path(gate["publicKeyPath"]).read_text().strip()}}}
    params = PRIVATE / "msdn-deployment.params.json"
    save(params, parameters)
    try:
        result = client.mutate(["group", "create", "--name", state["resourceGroup"],
                                "--location", LOCATION, "--tags"] + tags)
        check(result.get("tags") == {"lab": "true", "created_by": "copilot-lab", "run_id": run},
              "created_group_tag_mismatch")
        state["createdByThisRun"] = True
        state["createdAtUtc"] = now().isoformat()
        state["deleteByUtc"] = (now() + dt.timedelta(hours=72)).isoformat()
        save(STATE, state)
        base = ["deployment", "group"]
        args = ["--resource-group", state["resourceGroup"], "--name", run,
                "--template-file", str(LAB / "deploy" / "msdn-main.json"),
                "--parameters", "@" + str(params)]
        client.mutate(base + ["validate"] + args, seconds=90)
        state["validatedAtUtc"] = now().isoformat()
        save(STATE, state)
        result = client.mutate(base + ["create"] + args, seconds=240)
        check(result.get("properties", {}).get("provisioningState") == "Succeeded",
              "deployment_not_succeeded")
        state["provisioningState"] = "Succeeded"
        state["allocatedAtUtc"] = now().isoformat()
        save(STATE, state)
        snapshot(client, state, complete=True)
        print("DEPLOY PASS " + state["vmSize"] + "; six resources; restoring", flush=True)
    finally:
        if state["createdByThisRun"]:
            restore_vm(client, state)
            snapshot(client, state, restore=True,
                     complete=state.get("provisioningState") == "Succeeded")


def cleanup(client, action, confirm):
    state = read(STATE)
    client.authorize()
    tags = owned(state, client)
    exists = client.cli(["group", "exists", "--name", state["resourceGroup"]])
    if not exists:
        check(state.get("deletedAtUtc") is not None, "unexplained_missing_owned_group")
        print("CLEANUP already verified absent")
        return
    recorded = {x["id"].lower() for x in state["resources"]}
    rows = snapshot(client, state, persist=False)
    check({x["id"].lower() for x in rows} == recorded, "inventory_changed_cleanup_blocked")
    check(state.get("createdAtUtc") and tags["run_id"] == state["runId"], "missing_creation_proof")
    print("PREVIEW owned group + " + str(len(rows)) + " recorded resources; no foreign resources")
    if action == "cleanup":
        check(confirm == state["runId"], "explicit_cleanup_run_confirmation_required")
        client.mutate(["group", "delete", "--name", state["resourceGroup"], "--yes"], seconds=600)
        check(client.cli(["group", "exists", "--name", state["resourceGroup"]],
                         restore=True) is False, "deletion_not_verified")
        state["deletedAtUtc"] = now().isoformat()
        save(STATE, state)
        print("CLEANUP verified absent")


def main():
    def interrupted(signum, frame):
        raise RuntimeError("external_command_cancelled")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "deploy", "preview-cleanup", "cleanup", "restore"])
    parser.add_argument("--confirm")
    args = parser.parse_args()
    try:
        client = Client()
        if args.action == "preflight":
            preflight(client)
        elif args.action == "deploy":
            deploy(client, args.confirm)
        elif args.action == "restore":
            restore_vm(client, read(STATE))
        else:
            cleanup(client, args.action, args.confirm)
    except Exception as error:
        # Only bounded symbolic failures cross the WSL/Windows boundary.
        message = str(error)
        print("BLOCKED " + (message if re.fullmatch(r"[a-z0-9_]+", message) else type(error).__name__),
              file=sys.stderr)
        if args.action == "deploy":
            lease = read(LEASE)
            if lease["state"] == "active":
                lease.update(state="blocked", ownedProcessesIdle=True,
                             failureCode=message if re.fullmatch(r"[a-z0-9_]+", message)
                             else type(error).__name__, lastCheckpointUtc=now().isoformat())
                save(LEASE, lease)
        return 1
    if args.action == "deploy":
        lease = read(LEASE)
        lease.update(state="completed", ownedProcessesIdle=True,
                     lastCheckpointUtc=now().isoformat())
        save(LEASE, lease)
    return 0


if __name__ == "__main__":
    sys.exit(main())
