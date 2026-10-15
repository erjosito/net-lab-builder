"""Offline preparation and explicit, separately leased Azure RunCommand steps."""
import argparse
import base64
import contextlib
import concurrent.futures
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
PRIVATE = LAB / "private" / "transfers"
LEASE = LAB / "deploy" / ".runtime-control" / "transfer-live-lease.json"
OPERATIONS = ("start-a", "start-t", "allow", "server", "client",
              "restore-nsg", "deallocate-t", "deallocate-a")
RESTORE = {"restore-nsg", "deallocate-t", "deallocate-a", "deallocate-c", "deallocate-b"}
READINESS_OPERATIONS = ("start-a", "start-t", "ready-a", "ready-t",
                        "deallocate-t", "deallocate-a")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def bounded(argv, seconds, progress=None):
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name != "nt")
    started = time.monotonic()
    try:
        while True:
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, seconds)
            try:
                out, err = process.communicate(timeout=min(30, remaining))
                break
            except subprocess.TimeoutExpired:
                if progress:
                    progress(process.pid, time.monotonic() - started)
    except BaseException:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=5, check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.communicate(timeout=5)
        raise
    if process.returncode:
        save(PRIVATE / "last-error.private.json",
             {"code": process.returncode, "stderr": err.decode(errors="replace"),
              "argv": argv, "timeout_seconds": seconds})
        raise RuntimeError("command_failed_see_private_error")
    return out.decode()


def linux_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


def openssl(args):
    if shutil.which("openssl"):
        return bounded(["openssl"] + args, 30)
    converted = [linux_path(x) if Path(x).is_absolute() else x for x in args]
    return bounded(["wsl.exe", "--distribution", "Ubuntu-24.04", "--exec",
                    "/usr/bin/openssl"] + converted, 30)


def certificates(directory, host):
    directory.mkdir(parents=True, exist_ok=True)
    ca, ca_key = directory / "ca.pem", directory / "ca.key"
    openssl(["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=ephemeral-transfer-ca", "-keyout", str(ca_key), "-out", str(ca),
             "-addext", "basicConstraints=critical,CA:TRUE",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
    for role in ("server", "client"):
        key, csr, cert = (directory / (role + suffix) for suffix in (".key", ".csr", ".pem"))
        ext = directory / (role + ".ext")
        ext.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                       + ("extendedKeyUsage=serverAuth\nsubjectAltName=IP:" + host + "\n"
                          if role == "server" else "extendedKeyUsage=clientAuth\n"))
        openssl(["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=transfer-" + role,
                 "-keyout", str(key), "-out", str(csr)])
        openssl(["x509", "-req", "-in", str(csr), "-CA", str(ca), "-CAkey", str(ca_key),
                 "-set_serial", "1" if role == "server" else "2", "-days", "1",
                 "-extfile", str(ext), "-out", str(cert)])
    for path in directory.iterdir():
        os.chmod(path, 0o600)


def names(plan):
    return plan.get("aliases", {"client": "A", "server": "T"})


def endpoint_names(plan):
    return tuple(names(plan)[role] for role in ("client", "server"))


def action(plan, operation):
    return operation.replace("-a", "-" + names(plan)["client"].lower()).replace(
        "-t", "-" + names(plan)["server"].lower())


def operations(plan, readiness=False):
    return tuple(action(plan, op) for op in
                 (READINESS_OPERATIONS if readiness else OPERATIONS))


def azure(plan, alias):
    platform = plan.get("platforms", {}).get(
        alias, "wsl_Ubuntu-24.04_native_cli" if alias == "T" else "windows_native_cli")
    require(platform in ("windows_native_cli", "wsl_Ubuntu-24.04_native_cli"),
            "invalid_native_platform")
    return Azure(plan[alias], platform == "wsl_Ubuntu-24.04_native_cli")


def control_gates(plan, restoring=False):
    if plan.get("scenario", "cross-tenant-same-region") != "cross-region-control":
        require(endpoint_names(plan) == ("A", "T"), "default_endpoint_roles_changed")
        return
    require(names(plan) == {"client": "C", "server": "B"} and plan["legs"] == ["up"],
            "control_requires_c_to_b_only")
    c, b = plan["C"], plan["B"]
    require(c["subscriptionId"] == b["subscriptionId"]
            and c["expectedTenantId"] == b["expectedTenantId"],
            "control_requires_same_core_context")
    active = read(LAB / "private" / "context.private.json")
    require(all(c[k] == active[k] for k in ("subscriptionId", "expectedTenantId"))
            and b["resourceGroup"] == active["resourceGroup"]
            and b["runId"] == active["runId"], "control_not_core_inventory")
    require(c["region"] == "northeurope" and b["region"] == "swedencentral"
            and c["resourceGroup"].lower() != b["resourceGroup"].lower()
            and c["runId"] != b["runId"], "control_region_or_isolated_rg_mismatch")
    for alias, cfg in (("C", c), ("B", b)):
        require(cfg["resourceGroup"] == "rg-" + cfg["runId"], "control_rg_run_mismatch")
        for key, kind in (("vm", "Microsoft.Compute/virtualMachines"),
                          ("nic", "Microsoft.Network/networkInterfaces"),
                          ("pip", "Microsoft.Network/publicIPAddresses"),
                          ("nsg", "Microsoft.Network/networkSecurityGroups")):
            expected = ("/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/"
                        + cfg["resourceGroup"] + "/providers/" + kind + "/" + cfg[key])
            require(cfg[key] == cfg["runId"] + "-" + key + "-" + alias.lower()
                    and cfg.get(key + "_id", "").lower() == expected.lower(),
                    "control_resource_identity_mismatch")
    require(plan["platforms"] == {"C": "windows_native_cli", "B": "windows_native_cli"},
            "control_requires_windows_native_contexts")
    require(plan["bytes"] == 5 * 1024 ** 3 and plan["rate"] == 2500000
            and plan["wire_cap"] == 6 * 1024 ** 3
            and 6 * 1024 ** 3 <= plan["core_remaining_bytes"] <= 23 * 1024 ** 3,
            "control_budget_mismatch")
    deadline = datetime.fromisoformat(plan["cleanup_deadline"].replace("Z", "+00:00"))
    require((restoring or now() < deadline)
            and deadline <= datetime(2026, 10, 18, 7, 33, tzinfo=timezone.utc),
            "control_lifetime_exceeded")


def target(context, inventory, suffix, region="swedencentral"):
    rows = inventory["resources"]
    result = dict(context)
    result["runId"] = inventory["runId"]
    result["resourceGroup"] = "rg-" + inventory["runId"]
    for key, kind, end in (("vm", "virtualMachines", "-vm-" + suffix),
                           ("nsg", "networkSecurityGroups", "-nsg-" + suffix),
                           ("pip", "publicIPAddresses", "-pip-" + suffix),
                           ("nic", "networkInterfaces", "-nic-" + suffix)):
        found = [r for r in rows if r["type"].endswith("/" + kind)
                 and r["name"].endswith(end)]
        require(len(found) == 1, "private_inventory_identity_missing")
        row = found[0]
        require(row["tags"] == {"lab": "true", "created_by": "copilot-lab",
                                "run_id": result["runId"]}
                and row["location"] == region, "inventory_ownership_mismatch")
        expected = ("/subscriptions/" + result["subscriptionId"] + "/resourceGroups/"
                    + result["resourceGroup"] + "/providers/" + row["type"] + "/" + row["name"])
        require(row["id"].lower() == expected.lower(), "inventory_resource_id_mismatch")
        result[key] = row["name"]
        result[key + "_id"] = row["id"]
    return result


def prepare(args):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    directory = PRIVATE / args.run
    require(not directory.exists(), "refuse_existing_run")
    active = read(LAB / "private" / "context.private.json")
    control = getattr(args, "control", False)
    if control:
        second = active
        ci = read(LAB / "private" / "control-inventory.private.json")
        core = read(LAB / "private" / "inventory.private.json")
        a = target(active, ci, "c", "northeurope")
        t = target(active, core, "b")
        a["region"], t["region"] = "northeurope", "swedencentral"
        ti = core
        require(ci["groupId"].lower() == (
            "/subscriptions/" + active["subscriptionId"] + "/resourceGroups/"
            + a["resourceGroup"]).lower(), "control_group_identity_mismatch")
        receiver = ci["receiverPublicIP"]
        require(receiver["id"].lower() == t["pip_id"].lower()
                and receiver["location"] == "swedencentral"
                and receiver["tags"] == {"lab": "true", "created_by": "copilot-lab",
                                         "run_id": t["runId"]}, "control_receiver_pip_mismatch")
    else:
        second = read(LAB / "private" / "wsl-cost-context.private.json")
        require(active["subscriptionId"] != second["subscriptionId"]
                and active["expectedTenantId"] != second["expectedTenantId"], "tenants_not_distinct")
        a = target(active, read(LAB / "private" / "inventory.private.json"), "a")
        ti = read(LAB / "private" / "msdn-inventory.private.json")
        t = target(second, ti, "t")
    candidates = ([receiver["ipAddress"]] if control else
                  [x["properties"].get("ipAddress") for x in ti.get("detailedResources", [])
                   if x["type"].endswith("/publicIPAddresses") and x["name"] == t["pip"]])
    require(len(candidates) == 1 and candidates[0], "server_ip_missing")
    server_ip = str(ipaddress.IPv4Address(candidates[0]))
    remaining = args.core_remaining_bytes
    cap = (6 if control else 12) * 1024 ** 3
    require(cap <= remaining <= (23 if control else 35) * 1024 ** 3,
            "core_global_remaining_wire_budget_too_small")
    plan = {"id": uuid.uuid4().hex, "A": a, "T": t, "server_ip": server_ip,
            "core_remaining_bytes": remaining, "prepared": now().isoformat(),
            "bytes": 5368709120, "rate": 2500000, "wire_cap": cap,
            "operations": list(OPERATIONS), "status": "prepared_not_live",
            "mutations_reserved": 10}
    if control:
        del plan["A"], plan["T"]
        plan.update(C=a, B=t, aliases={"client": "C", "server": "B"}, legs=["up"],
                    platforms={"C": "windows_native_cli", "B": "windows_native_cli"},
                    scenario="cross-region-control", cleanup_deadline=ci["cleanupDeadlineUtc"])
        control_gates(plan)
    plan["operations"] = list(operations(plan))
    directory.mkdir()
    certificates(directory / "tls", server_ip)
    save(directory / "plan.private.json", plan)
    commands = {}
    for operation in operations(plan):
        cfg = a if operation in (action(plan, "start-a"), "client",
                                 action(plan, "deallocate-a")) else t
        platform = "windows_native_cli" if cfg is a or control else "wsl_Ubuntu-24.04_native_cli"
        base = ["--resource-group", cfg["resourceGroup"], "--name", cfg["vm"]]
        if operation.startswith(("start-", "deallocate-")):
            argv = ["vm", "start" if operation.startswith("start-") else "deallocate"] + base
        elif operation in ("server", "client"):
            argv = ["vm", "run-command", "invoke"] + base + [
                "--command-id", "RunShellScript", "--scripts",
                "@" + str(directory / (operation + ".private.sh"))]
        else:
            argv = ["rest", "--method", "PUT", "--url",
                    "https://management.azure.com/subscriptions/" + cfg["subscriptionId"]
                    + "/resourceGroups/" + cfg["resourceGroup"]
                    + "/providers/Microsoft.Network/networkSecurityGroups/" + cfg["nsg"]
                    + "?api-version=2024-05-01", "--body",
                    "@" + str(directory / ("nsg-allow.private.json" if operation == "allow"
                                          else "nsg-restore.private.json"))]
        commands[operation] = {"platform": platform, "argv_before_native_path_conversion":
                               argv + ["--subscription", cfg["subscriptionId"],
                                       "--only-show-errors", "--output", "json"]}
    save(directory / "commands.private.json", commands)
    save(directory / "live-lease-template.private.json", {
        "taskId": "bandwidth-transfer-" + args.run, "ownerRole": "Tank",
        "objective": "C to B one-way cross-region mTLS" if control else
                     "A to T and T to A same-region public IPv4 mTLS only",
        "startedAtUtc": "SET_BY_FRESH_OWNER", "expiresAtUtc": "SET_60_MINUTES_AFTER_START",
        "allowedMutations": list(operations(plan)),
        "maxToolCalls": 150, "maxMutations": 10, "commandTimeoutSeconds": 3000,
        "namedCommandTimeoutSeconds": {"server": 2500, "client": 2500},
        "restoreTimeoutMinutes": 15, "state": "not-active-template",
        "actualToolCalls": 0, "actualMutations": 0, "activeCommands": 0,
        "ownedProcessesIdle": True})
    readiness_lease = {
        "taskId": "bandwidth-readiness-" + args.run, "ownerRole": "Tank",
        "objective": "Boot declared endpoints, read-only guest readiness, deallocate both; no payload or NSG write",
        "startedAtUtc": "SET_BY_FRESH_OWNER", "expiresAtUtc": "SET_30_MINUTES_AFTER_START",
        "allowedMutations": list(operations(plan, True)), "maxToolCalls": 75,
        "maxMutations": 6, "commandTimeoutSeconds": 180,
        "restoreTimeoutMinutes": 15, "state": "not-active-template",
        "actualToolCalls": 0, "actualMutations": 0, "activeCommands": 0,
        "ownedProcessesIdle": True}
    save(directory / "readiness-lease-template.private.json", readiness_lease)
    snapshot_lease = dict(readiness_lease, taskId="bandwidth-snapshot-" + args.run,
                          ownerRole="Niobe", objective="Fresh read-only endpoint snapshot and metrics",
                          allowedMutations=[], maxMutations=0)
    save(directory / "snapshot-lease-template.private.json", snapshot_lease)
    print("PREPARED private/transfers/" + args.run
          + "; no Azure calls; next readiness lease, snapshot lease, then fresh live lease")


@contextlib.contextmanager
def lease_lock():
    path = PRIVATE / ".lease-lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            path.mkdir()
            break
        except FileExistsError:
            require(time.monotonic() < deadline, "lease_lock_busy")
            time.sleep(.05)
    try:
        yield
    finally:
        path.rmdir()


def guard(operation=None, seconds=30):
    lease = read(LEASE)
    start = datetime.fromisoformat(lease["startedAtUtc"].replace("Z", "+00:00"))
    expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    require(start <= now() and 0 < (expiry - start).total_seconds() <= 3600,
            "lease_must_not_exceed_60_minutes")
    remaining = (datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00")) - now()
                 ).total_seconds()
    read_restore = bool(operation and operation.startswith("read-restore:"))
    restore = operation in RESTORE or read_restore
    require(lease["state"] == "active" and not (LEASE.parent / "STOP").exists()
            and remaining > seconds + 10, "inactive_or_short_lease")
    require(seconds <= lease["commandTimeoutSeconds"], "command_not_explicitly_bounded")
    if seconds > 1200:
        require(operation in lease.get("namedCommandTimeoutSeconds", {})
                and seconds <= lease["namedCommandTimeoutSeconds"][operation],
                "long_command_not_named_in_lease")
    require(lease.get("actualToolCalls", 0) < lease["maxToolCalls"], "tool_budget")
    if operation and not read_restore:
        require(operation in lease["allowedMutations"]
                and lease.get("actualMutations", 0) < lease["maxMutations"], "mutation_not_leased")
    if not restore:
        start = datetime.fromisoformat(lease["startedAtUtc"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        require(now() < start + (expiry - start) * .8
                and lease.get("actualToolCalls", 0) < lease["maxToolCalls"] * .8
                and (lease["maxMutations"] == 0
                     or lease.get("actualMutations", 0) < lease["maxMutations"] * .8),
                "restoration_only")
        require(remaining >= seconds + 900, "reserve_15_minutes_restoration")
    return lease


class Azure:
    def __init__(self, target_config, wsl=False):
        self.config = target_config
        self.wsl = wsl

    def cli(self, args, operation=None, seconds=30, directory=None):
        if self.wsl:
            prefix = ["wsl.exe", "--distribution", "Ubuntu-24.04", "--exec",
                      "/usr/bin/timeout", "--signal=TERM", "--kill-after=5s",
                      str(max(1, int(seconds) - 10)) + "s", "/usr/bin/az"]
        else:
            binary = shutil.which("az")
            require(binary, "windows_cli_missing")
            python = Path(binary).resolve().parent.parent / "python.exe"
            require(python.is_file(), "windows_cli_python_missing")
            prefix = [str(python), "-m", "azure.cli"]
        with lease_lock():
            lease = guard(operation, seconds)
            if operation in ("server", "client"):
                # Authorization and local preparation must not spend the restore reserve.
                guard(operation, 2500)
            lease["actualToolCalls"] = lease.get("actualToolCalls", 0) + 1
            if operation and not operation.startswith("read-restore:"):
                lease["actualMutations"] = lease.get("actualMutations", 0) + 1
            lease["activeCommands"] = lease.get("activeCommands", 0) + 1
            lease["ownedProcessesIdle"] = False
            save(LEASE, lease)
        try:
            progress = None
            if directory and operation in ("server", "client"):
                def progress(pid, elapsed):
                    save(directory / (operation + "-progress.private.json"),
                         {"at": now().isoformat(), "localPid": pid,
                          "elapsed_seconds": round(elapsed), "state": "running",
                          "socket_no_progress_limit_seconds": 60})
            output = bounded(prefix + args + ["--subscription", self.config["subscriptionId"],
                                              "--only-show-errors", "--output", "json"], seconds,
                             progress)
            result = json.loads(output) if output.strip() else None
            if directory:
                save(directory / ((operation or "query") + ".private.json"), result)
            return result
        finally:
            with lease_lock():
                lease = read(LEASE)
                lease["activeCommands"] -= 1
                lease["ownedProcessesIdle"] = lease["activeCommands"] == 0
                lease["lastCheckpointUtc"] = now().isoformat()
                save(LEASE, lease)

    def authorize(self, operation=None):
        account = self.cli(["account", "show"], operation="read-restore:" + operation
                           if operation in RESTORE else None)
        require(account["id"] == self.config["subscriptionId"]
                and account["tenantId"] == self.config["expectedTenantId"]
                and account["state"] == "Enabled", "native_context_mismatch")


def readiness_config(directory, role, plan):
    alias = names(plan)[role]
    nic = read(directory / (alias + "-nic-before.private.json"))
    ipconfig = nic["ipConfigurations"][0]
    return {"interface": plan.get("interface_" + role, "eth0"),
            "mac": nic["macAddress"].lower().replace("-", ":"),
            "local_ip": ipconfig["privateIPAddress"],
            "peer": plan["server_ip"] if role == "client" else plan["client_ip"]}


def guest_probe(config):
    """Read-only guest probe, also executed immediately before either payload process."""
    return (
        "import hashlib,json,os,pathlib,shutil,subprocess,sys,ssl\n"
        "c=" + repr(config) + "\n"
        "assert sys.version_info >= (3,8), 'python_version'\n"
        "assert os.geteuid() == 0, 'root_required'\n"
        "tools={}\n"
        "for n in ('python3','timeout','ip'):\n"
        " p=shutil.which(n); assert p, 'missing_tool'\n"
        " p=os.path.realpath(p)\n"
        " tools[n]={'path':p,'sha256':hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()}\n"
        "subprocess.run(['timeout','--signal=TERM','--kill-after=1s','2s','python3','-c',"
        "'import ssl,hashlib,http.client,http.server'],check=True,capture_output=True,timeout=5)\n"
        "i=c['interface']; assert i not in ('.','..') and '/' not in i, 'interface'\n"
        "root=pathlib.Path('/sys/class/net')/i\n"
        "mac=(root/'address').read_text().strip().lower(); assert mac==c['mac'], 'nic_changed'\n"
        "route=json.loads(subprocess.check_output(['ip','-j','-4','route','get',c['peer']],timeout=5))\n"
        "assert len(route)==1 and route[0]['dev']==i and route[0].get('prefsrc',"
        "route[0].get('src'))==c['local_ip'], 'route_changed'\n"
        "stats={k:int((root/'statistics'/(k+'_bytes')).read_text()) for k in ('rx','tx')}\n"
        "assert min(stats.values())>=0, 'nic_stats'\n"
        "result={'success':True,'role':'guest_readiness','tools':tools,'python':sys.version,"
        "'openssl':ssl.OPENSSL_VERSION,'binding':c,'route':route,'nic':stats}\n")


def vm_readiness_binding(vm):
    binding = {key: json.loads(json.dumps(vm[key]))
               for key in ("id", "vmId", "storageProfile")}
    disk = binding["storageProfile"]["osDisk"]["managedDisk"]
    require(all(isinstance(value, str) and value.strip()
                for value in (binding["id"], binding["vmId"], disk.get("id"))),
            "vm_disk_identity_required")
    binding["id"] = binding["id"].lower()
    binding["vmId"] = binding["vmId"].lower()
    # ARM resource IDs and the CLI-derived resourceGroup are case-insensitive.
    disk["id"] = disk["id"].lower()
    if "resourceGroup" in disk:
        disk["resourceGroup"] = disk["resourceGroup"].lower()
    return binding


def readiness_binding(directory, plan):
    return {"id": plan["id"], **{alias: plan[alias] for alias in endpoint_names(plan)},
            "scenario": plan.get("scenario", "cross-tenant-same-region"),
            "aliases": names(plan), "legs": plan.get("legs", ["up", "down"]),
            "platforms": {alias: azure(plan, alias).wsl for alias in endpoint_names(plan)},
            "bytes": plan["bytes"], "rate": plan["rate"], "wire_cap": plan["wire_cap"],
            "core_remaining_bytes": plan["core_remaining_bytes"],
            "cleanup_deadline": plan.get("cleanup_deadline"),
            "stream_sha256": hashlib.sha256((HERE / "stream.py").read_bytes()).hexdigest(),
            "runner_sha256": hashlib.sha256((HERE / "run.py").read_bytes()).hexdigest(),
            "guests": {role: readiness_config(directory, role, plan)
                       for role in ("client", "server")},
            "vms": {alias: vm_readiness_binding(
                        read(directory / (alias + "-vm-before.private.json")))
                    for alias in endpoint_names(plan)}}


def require_readiness(directory, plan):
    evidence = read(directory / "readiness.private.json")
    age = (now() - datetime.fromisoformat(evidence["completed_at"])).total_seconds()
    require(evidence.get("success") is True and 0 <= age < 86400
            and evidence["binding"] == readiness_binding(directory, plan)
            and all(evidence["deallocated"].get(alias) is True for alias in endpoint_names(plan)),
            "trusted_guest_readiness_required")
    return evidence


def guest_script(directory, role, plan, evidence=None):
    path = directory / (role + ".private.sh")
    if evidence is None:
        path.write_text("#!/bin/sh\n# Generated live material requires validated readiness.\n"
                        "echo guest_readiness_required >&2\nexit 1\n",
                        encoding="utf-8", newline="\n")
        return path
    guest = "/root/bwb-transfer-" + plan["id"]
    cfg = {"id": plan["id"], "bytes": plan["bytes"], "rate": plan["rate"],
           "wire_cap": plan["wire_cap"], "interface": plan.get("interface_" + role, "eth0"),
           "deadline": 2400, "idle": 60, "first_request_timeout": 180,
           "port": 443, "ca": guest + "/ca.pem",
           "cert": guest + "/" + role + ".pem", "key": guest + "/" + role + ".key",
           "report": guest + "/report.json", "expected_peer": plan["client_ip"]
           if role == "server" else plan["server_ip"]}
    cfg.update(aliases=names(plan), legs=plan.get("legs", ["up", "down"]))
    if role == "client":
        cfg["host"] = plan["server_ip"]
        cfg["readiness_attempts"] = 12
    bundle = {"stream.py": (HERE / "stream.py").read_text(), "config.json": json.dumps(cfg)}
    for name in ("ca.pem", role + ".pem", role + ".key"):
        bundle[name] = (directory / "tls" / name).read_text()
    encoded = base64.b64encode(json.dumps(bundle).encode()).decode()
    precheck = ("python3 - <<'PY'\n" + guest_probe(readiness_config(directory, role, plan))
                + "expected=" + repr(evidence["reports"][role]) + "\n"
                "for k in ('tools','python','openssl','binding','route'):\n"
                " assert result[k]==expected[k], 'guest_readiness_changed'\nPY\n")
    script = ("#!/bin/sh\nset -eu\numask 077\n"
              "command -v python3 >/dev/null\ncommand -v timeout >/dev/null\n"
              + precheck +
              "mkdir " + guest + "\ntrap 'rm -f " + guest + "/*.key' EXIT HUP INT TERM\n"
              "python3 - <<'PY'\nimport base64,json,pathlib,os\n"
              "root=pathlib.Path(" + repr(guest) + ")\n"
              "for name,text in json.loads(base64.b64decode(" + repr(encoded) + ")).items():\n"
              " p=root/name; p.write_text(text); os.chmod(p,0o600)\nPY\n"
              "timeout --signal=TERM --kill-after=10s 2450s python3 " + guest
              + "/stream.py " + role + " " + guest + "/config.json\n")
    path.write_text(script, encoding="utf-8", newline="\n")
    return path


def snapshot(directory, plan, a, t, readiness=False):
    control_gates(plan)
    plan.pop("snapshot_at", None)
    save(directory / "plan.private.json", plan)
    observed_at = now().isoformat()
    a.authorize()
    t.authorize()
    for alias, client in zip(endpoint_names(plan), (a, t)):
        cfg = client.config
        for key in ("vm", "nsg", "pip", "nic"):
            command = ["vm", "show"] if key == "vm" else ["network", key, "show"]
            if key == "pip":
                command = ["network", "public-ip", "show"]
            value = client.cli(command + ["--resource-group", cfg["resourceGroup"],
                                         "--name", cfg[key]])
            require(value["tags"] == {"lab": "true", "created_by": "copilot-lab",
                                     "run_id": cfg["runId"]}
                    and value["location"] == cfg.get("region", "swedencentral"),
                    "live_ownership_mismatch")
            if key + "_id" in cfg:
                require(value["id"].lower() == cfg[key + "_id"].lower(),
                        "live_resource_identity_mismatch")
            save(directory / (alias + "-" + key + "-before.private.json"), value)
            if key == "pip":
                ip = str(ipaddress.IPv4Address(value["ipAddress"]))
                if alias == names(plan)["server"]:
                    require(ip == plan["server_ip"], "server_ip_changed_reprepare")
                else:
                    plan["client_ip"] = ip
        vm = client.cli(["vm", "get-instance-view", "-g", cfg["resourceGroup"], "-n", cfg["vm"]])
        require(any(x["code"] == "PowerState/deallocated" for x in
                    vm.get("instanceView", vm)["statuses"]), "baseline_vm_not_deallocated")
        vm_info = read(directory / (alias + "-vm-before.private.json"))
        nic_info = read(directory / (alias + "-nic-before.private.json"))
        pip_info = read(directory / (alias + "-pip-before.private.json"))
        nsg_info = read(directory / (alias + "-nsg-before.private.json"))
        require(len(vm_info["networkProfile"]["networkInterfaces"]) == 1
                and vm_info["networkProfile"]["networkInterfaces"][0]["id"].lower()
                == nic_info["id"].lower()
                and nic_info["networkSecurityGroup"]["id"].lower() == nsg_info["id"].lower()
                and len(nic_info["ipConfigurations"]) == 1
                and nic_info["ipConfigurations"][0]["publicIPAddress"]["id"].lower()
                == pip_info["id"].lower(), "endpoint_nic_pip_nsg_binding_mismatch")
        require(len(nsg_info["securityRules"]) == 1
                and nsg_info["securityRules"][0]["priority"] == 100
                and nsg_info["securityRules"][0]["access"] == "Deny"
                and nsg_info["securityRules"][0]["direction"] == "Inbound",
                "unexpected_endpoint_inbound_baseline")
    nsg = read(directory / (names(plan)["server"] + "-nsg-before.private.json"))
    rules = nsg["securityRules"]
    require(len(rules) == 1 and rules[0]["priority"] == 100 and rules[0]["access"] == "Deny"
            and rules[0]["direction"] == "Inbound" and rules[0]["protocol"] == "*",
            "unexpected_nsg_baseline")
    mutable = ("name", "description", "protocol", "sourcePortRange", "destinationPortRange",
               "sourceAddressPrefix", "destinationAddressPrefix", "sourcePortRanges",
               "destinationPortRanges", "sourceAddressPrefixes", "destinationAddressPrefixes",
               "access", "priority", "direction")
    original = [{"name": r["name"], "properties": {k: v for k, v in r.items()
                  if k in mutable and k != "name" and v is not None}} for r in rules]
    restore = {"location": nsg["location"], "tags": nsg["tags"],
               "properties": {"securityRules": original}}
    allowed = json.loads(json.dumps(restore))
    for rule in allowed["properties"]["securityRules"]:
        if rule["properties"]["priority"] == 100:
            rule["properties"]["priority"] = 200
    allowed["properties"]["securityRules"].append({
        "name": "transfer-peer-443", "properties": {"priority": 100, "access": "Allow",
        "direction": "Inbound", "protocol": "Tcp", "sourcePortRange": "*",
        "destinationPortRange": "443", "sourceAddressPrefix": plan["client_ip"] + "/32",
        "destinationAddressPrefix": "*"}})
    save(directory / "nsg-restore.private.json", restore)
    save(directory / "nsg-allow.private.json", allowed)
    save(directory / "plan.private.json", plan)
    for role in ("server", "client"):
        guest_script(directory, role, plan)
    if not readiness:
        plan["snapshot_at"] = observed_at
        metrics(directory, plan)
        # Freshness starts at the first resource observations, not after metric latency.
    save(directory / "plan.private.json", plan)
    print("SNAPSHOT ready; inspect private ownership/IP/DNS/NIC/NSG and metrics gates before start")


def compact_report(result):
    candidates = []
    for value in result.get("value", []):
        for line in value.get("message", "").splitlines():
            if line.startswith("{"):
                try:
                    report = json.loads(line)
                except ValueError:
                    continue
                if "success" in report and "role" in report:
                    candidates.append(report)
    require(len(candidates) == 1, "missing_or_truncated_guest_report")
    return candidates[0]


def normalized_rules(rules):
    result = []
    for rule in rules:
        props = rule.get("properties", rule)
        row = {"name": rule["name"]}
        for key in ("priority", "description", "access", "direction", "protocol"):
            value = props.get(key)
            if value is not None:
                row[key] = value.lower() if key in ("access", "direction", "protocol") else value
        for key in ("sourcePortRange", "destinationPortRange",
                    "sourceAddressPrefix", "destinationAddressPrefix",
                    "sourceApplicationSecurityGroup", "destinationApplicationSecurityGroup"):
            values = props.get(key + ("es" if key.endswith("Prefix") else "s")) or []
            if props.get(key):
                values = list(values) + [props[key]]
            row[key] = sorted(json.dumps(value, sort_keys=True).lower() for value in values)
        result.append(row)
    return sorted(result, key=lambda row: row["name"])


def nsg_gate_binding(directory, plan):
    alias = names(plan)["server"]
    before = read(directory / (alias + "-nsg-before.private.json"))
    nic = read(directory / (alias + "-nic-before.private.json"))
    desired = read(directory / "nsg-allow.private.json")
    return {"id": plan["id"], "snapshot_at": plan["snapshot_at"],
            "nsg": before["id"].lower(), "nic": nic["id"].lower(),
            "location": desired["location"], "tags": desired["tags"],
            "rules": normalized_rules(desired["properties"]["securityRules"])}


def wait_nsg_allow(directory, plan, client):
    """One PUT only; read back completion and exact receiver NIC policy within setup time."""
    binding = nsg_gate_binding(directory, plan)
    started = time.monotonic()
    evidence = {"verified": False, "binding": binding, "polls": []}
    path = directory / "nsg-gate.private.json"
    save(path, evidence)

    def remaining():
        lease = guard("server", 2500)
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        return min(180 - (time.monotonic() - started),
                   (expiry - now()).total_seconds() - 3400)

    def query(kind):
        seconds = min(30, remaining())
        require(seconds > 0, "nsg_gate_setup_timeout")
        result = client.cli(["network", kind, "show", "-g", client.config["resourceGroup"],
                             "-n", client.config[kind]], seconds=seconds)
        guard("server", 2500)
        require(time.monotonic() - started < 180, "nsg_gate_setup_timeout")
        return result

    try:
        while True:
            after = query("nsg")
            evidence["polls"].append({"at": now().isoformat(), "nsg": after})
            save(path, evidence)
            require(after.get("id", "").lower() == binding["nsg"], "nsg_gate_identity_mismatch")
            states = [after.get("provisioningState")] + [
                rule.get("provisioningState") for rule in after.get("securityRules", [])]
            require(not any(state in ("Failed", "Canceled", "Cancelled") for state in states),
                    "nsg_gate_provisioning_failed")
            if all(state == "Succeeded" for state in states):
                require(normalized_rules(after.get("securityRules", [])) == binding["rules"]
                        and after.get("location") == binding["location"]
                        and after.get("tags") == binding["tags"], "nsg_gate_readback_mismatch")
                nic = query("nic")
                evidence["nic"] = nic
                require(nic.get("id", "").lower() == binding["nic"]
                        and nic.get("networkSecurityGroup", {}).get("id", "").lower()
                        == binding["nsg"], "nsg_gate_association_mismatch")
                evidence.update(verified=True, completed_at=now().isoformat())
                return
            require(all(state in ("Updating", "Creating", "Succeeded") for state in states),
                    "nsg_gate_unknown_provisioning_state")
            require(remaining() > 30, "nsg_gate_setup_timeout")
            time.sleep(30)
    except BaseException as error:
        evidence["failure"] = str(error)
        raise
    finally:
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save(path, evidence)


def require_nsg_allow(directory, plan):
    evidence = read(directory / "nsg-gate.private.json")
    age = (now() - datetime.fromisoformat(evidence["completed_at"])).total_seconds() \
        if evidence.get("completed_at") else -1
    require(evidence.get("verified") is True and 0 <= age < 200
            and evidence["binding"] == nsg_gate_binding(directory, plan),
            "completed_exact_nsg_gate_required")


def restore_nsg(directory, plan, client, started):
    """Submit once and verify the original policy within the shared restore reserve."""
    path = directory / "nsg-restored.private.json"
    evidence = {"verified": False, "polls": []}
    save(path, evidence)
    operation = "read-restore:restore-nsg"
    try:
        alias = names(plan)["server"]
        before = read(directory / (alias + "-nsg-before.private.json"))
        original_nic = read(directory / (alias + "-nic-before.private.json"))
        budget = 900
        if plan.get("restore_started"):
            budget = min(budget, 900 - (now() - datetime.fromisoformat(
                plan["restore_started"])).total_seconds())
        deadline = started + budget

        def remaining():
            lease = guard(operation, 0)
            expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
            return min(deadline - time.monotonic(), (expiry - now()).total_seconds() - 11)

        require(remaining() > 180, "nsg_restore_insufficient_budget")
        client.authorize("restore-nsg")
        require(remaining() > 180, "nsg_restore_insufficient_budget")
        cfg = client.config
        body = directory / "nsg-restore.private.json"
        url = ("https://management.azure.com/subscriptions/" + cfg["subscriptionId"]
               + "/resourceGroups/" + cfg["resourceGroup"]
               + "/providers/Microsoft.Network/networkSecurityGroups/" + cfg["nsg"]
               + "?api-version=2024-05-01")
        client.cli(["rest", "--method", "PUT", "--url", url, "--body",
                    "@" + (linux_path(body) if client.wsl else str(body))],
                   "restore-nsg", 180, directory)

        def query(kind):
            seconds = min(30, remaining())
            require(seconds > 0, "nsg_restore_timeout")
            result = client.cli(["network", kind, "show", "-g", cfg["resourceGroup"],
                                 "-n", cfg[kind]], operation=operation, seconds=seconds)
            require(remaining() > 0, "nsg_restore_timeout")
            return result

        while True:
            after = query("nsg")
            evidence["polls"].append({"at": now().isoformat(), "nsg": after})
            save(path, evidence)
            require(after.get("id", "").lower() == before["id"].lower(),
                    "nsg_restore_identity_mismatch")
            rules = after.get("securityRules", [])
            require(normalized_rules(rules) == normalized_rules(before["securityRules"])
                    and after.get("tags") == before["tags"]
                    and after.get("location") == before["location"],
                    "nsg_restore_readback_mismatch")
            identities = {rule["name"]: rule.get("id", "").lower() for rule in rules}
            require(all(not rule.get("id") or identities[rule["name"]] == rule["id"].lower()
                        for rule in before["securityRules"]), "nsg_restore_rule_identity_mismatch")
            states = [after.get("provisioningState")] + [
                rule.get("provisioningState") for rule in rules]
            require(all(state in ("Succeeded", "Updating", "Creating") for state in states),
                    "nsg_restore_provisioning_failed_or_unknown")
            if all(state == "Succeeded" for state in states):
                nic = query("nic")
                evidence["nic"] = nic
                require(nic.get("id", "").lower() == original_nic["id"].lower()
                        and nic.get("networkSecurityGroup", {}).get("id", "").lower()
                        == before["id"].lower(), "nsg_restore_association_mismatch")
                evidence.update(verified=True, at=now().isoformat())
                return
            require(remaining() > 30, "nsg_restore_timeout")
            time.sleep(30)
    except BaseException as error:
        evidence["failure"] = str(error)
        raise
    finally:
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save(path, evidence)


def metrics(directory, plan, restore=False):
    end_at = now()
    observed_at = datetime.fromisoformat(plan.get("live_started", plan["snapshot_at"]))
    # Azure Monitor rejects windows shorter than one minute, even at PT1M.
    start = min(observed_at, end_at - timedelta(minutes=1)).isoformat()
    end = end_at.isoformat()
    for alias in endpoint_names(plan):
        client = azure(plan, alias)
        resource = ("/subscriptions/" + plan[alias]["subscriptionId"] + "/resourceGroups/"
                    + plan[alias]["resourceGroup"] + "/providers/Microsoft.Compute/virtualMachines/"
                    + plan[alias]["vm"])
        operation = "read-restore:restore-nsg" if restore else None
        seconds = 60
        if restore and plan.get("restore_started"):
            seconds = min(seconds, 900 - (now() - datetime.fromisoformat(
                plan["restore_started"])).total_seconds())
            require(seconds > 0, "restore_reserve_exhausted")
        output = client.cli(["monitor", "metrics", "list", "--resource", resource,
                             "--metric", "Network In Total", "Network Out Total",
                             "--interval", "PT1M", "--aggregation", "Total",
                             "--start-time", start, "--end-time", end],
                            operation=operation, seconds=seconds)
        save(directory / (alias + ("-metrics-after.private.json" if restore
                                  else "-metrics-baseline.private.json")), output)


def execute(args):
    started = time.monotonic()
    directory = PRIVATE / args.run
    plan = read(directory / "plan.private.json")
    if args.action == "restore-nsg":
        save(directory / "nsg-restored.private.json", {"verified": False, "polls": []})
    if args.action == "verify":
        import stream
        verdict = stream.verify(read(directory / "client-report.private.json"),
                                read(directory / "server-report.private.json"))
        save(directory / "verdict.private.json", verdict)
        print(json.dumps(verdict))
        return
    control_gates(plan, restoring=args.action in RESTORE or args.action == "metrics")
    a, t = (azure(plan, alias) for alias in endpoint_names(plan))
    if args.action == "snapshot":
        lease = guard(None, 60)
        require(lease["maxMutations"] == 0 and not lease["allowedMutations"],
                "separate_read_only_snapshot_lease_required")
        successful = False
        try:
            snapshot(directory, plan, a, t)
            successful = True
        finally:
            with lease_lock():
                lease = read(LEASE)
                lease.update(state="completed" if successful else "blocked",
                             lastCheckpointUtc=now().isoformat(),
                             ownedProcessesIdle=lease.get("activeCommands", 0) == 0)
                save(LEASE, lease)
        return
    if args.action == "readiness":
        return readiness(args, directory, plan, a, t)
    if args.action == "live":
        return live(args, directory, plan)
    if args.action == "metrics":
        return metrics(directory, plan, restore=True)
    operation = args.action
    guard(operation, 2500 if operation in ("server", "client") else 180)
    require((directory / "client.private.sh").is_file(), "snapshot_required")
    require(operation in operations(plan) + operations(plan, True), "operation_not_in_plan")
    alias = names(plan)["client"] if operation in (
        action(plan, "start-a"), "client", action(plan, "ready-a"),
        action(plan, "deallocate-a")) else names(plan)["server"]
    client = a if alias == names(plan)["client"] else t
    if operation == "restore-nsg":
        restore_nsg(directory, plan, client, started)
        print("STEP returned: restore-nsg; verify private result; never automatically retry")
        return
    client.authorize(operation)
    cfg = client.config
    base = ["-g", cfg["resourceGroup"], "-n", cfg["vm"]]
    if operation.startswith(("start-", "deallocate-")):
        command = ["vm", "start" if operation.startswith("start-") else "deallocate"] + base
        client.cli(command, operation, 180, directory)
    elif operation == "allow":
        body = directory / "nsg-allow.private.json"
        url = ("https://management.azure.com/subscriptions/" + cfg["subscriptionId"]
               + "/resourceGroups/" + cfg["resourceGroup"]
               + "/providers/Microsoft.Network/networkSecurityGroups/" + cfg["nsg"]
               + "?api-version=2024-05-01")
        client.cli(["rest", "--method", "PUT", "--url", url, "--body",
                    "@" + (linux_path(body) if client.wsl else str(body))],
                   operation, 180, directory)
        wait_nsg_allow(directory, plan, client)
    elif operation in (action(plan, "ready-a"), action(plan, "ready-t")):
        role = "client" if alias == names(plan)["client"] else "server"
        script = directory / (operation + ".private.sh")
        script.write_text("#!/bin/sh\nset -eu\ncommand -v timeout >/dev/null\n"
                          "timeout --signal=TERM --kill-after=5s 30s python3 - <<'PY'\n"
                          + guest_probe(readiness_config(directory, role, plan))
                          + "print(json.dumps(result,separators=(',',':')))\nPY\n",
                          encoding="utf-8", newline="\n")
        path = linux_path(script) if client.wsl else str(script)
        result = client.cli(["vm", "run-command", "invoke"] + base
                            + ["--command-id", "RunShellScript", "--scripts", "@" + path],
                            operation, 180, directory)
        report = compact_report(result)
        require(report["role"] == "guest_readiness" and report["success"] is True
                and report["binding"] == readiness_config(directory, role, plan),
                "guest_readiness_failed")
        save(directory / (operation + "-report.private.json"), report)
    else:
        require_nsg_allow(directory, plan)
        evidence = require_readiness(directory, plan)
        guest_script(directory, operation, plan, evidence)
        script = directory / (operation + ".private.sh")
        cli_path = linux_path(script) if client.wsl else str(script)
        result = client.cli(["vm", "run-command", "invoke"] + base
                            + ["--command-id", "RunShellScript", "--scripts", "@" + cli_path],
                            operation, 2500, directory)
        require(result is not None, "runcommand_missing_result")
        report = compact_report(result)
        save(directory / (operation + "-report.private.json"), report)
        require(report["success"], "guest_transfer_failed_do_not_retry")
    if operation.startswith("deallocate-"):
        view = client.cli(["vm", "get-instance-view"] + base,
                          operation="read-restore:" + operation)
        require(any(x["code"] == "PowerState/deallocated" for x in
                    view.get("instanceView", view)["statuses"]), "deallocation_not_verified")
        save(directory / (operation + "-verified.private.json"),
             {"verified": True, "at": now().isoformat()})
    print("STEP returned: " + operation + "; verify private result; never automatically retry")


def parallel_steps(args, actions):
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(execute, argparse.Namespace(action=action, run=args.run))
                   for action in actions]
        for future in futures:
            future.result()


def readiness(args, directory, plan, a, t):
    lease = guard(action(plan, "ready-a"), 180)
    require(lease["maxMutations"] == 6 and lease.get("actualMutations", 0) == 0
            and set(lease["allowedMutations"]) == set(operations(plan, True)),
            "reserve_six_readiness_mutations")
    require(not (directory / "readiness.private.json").exists(),
            "readiness_already_attempted_use_new_run")
    evidence = {"success": False, "binding": None,
                "started_at": now().isoformat(), "deallocated": {}, "reports": {}}
    save(directory / "readiness.private.json", evidence)
    failures = []
    boot_attempted = False
    try:
        snapshot(directory, plan, a, t, readiness=True)
        evidence["binding"] = readiness_binding(directory, plan)
        boot_started = time.monotonic()
        boot_attempted = True
        parallel_steps(args, (action(plan, "start-a"), action(plan, "start-t")))
        evidence["parallel_boot_seconds"] = round(time.monotonic() - boot_started, 3)
        parallel_steps(args, (action(plan, "ready-a"), action(plan, "ready-t")))
        for role, operation in (("client", action(plan, "ready-a")),
                                ("server", action(plan, "ready-t"))):
            evidence["reports"][role] = read(directory / (operation + "-report.private.json"))
    except BaseException as error:
        failures.append(str(error))
    finally:
        for operation, alias in ((action(plan, "deallocate-t"), names(plan)["server"]),
                                  (action(plan, "deallocate-a"), names(plan)["client"])):
            if not boot_attempted:
                continue
            try:
                execute(argparse.Namespace(action=operation, run=args.run))
                evidence["deallocated"][alias] = True
            except Exception as error:
                failures.append(operation + ":" + str(error))
        evidence.update(success=not failures, failures=failures, completed_at=now().isoformat())
        save(directory / "readiness.private.json", evidence)
        with lease_lock():
            lease = read(LEASE)
            lease.update(state="completed" if not failures else "blocked",
                         lastCheckpointUtc=now().isoformat(),
                         ownedProcessesIdle=lease.get("activeCommands", 0) == 0)
            save(LEASE, lease)
    require(not failures, "readiness_failed_see_private_evidence_no_retry")
    print("READINESS PASS; both deallocated; no NSG write or payload; next read-only snapshot lease")


def payload_steps(args, directory, plan):
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(execute, argparse.Namespace(action=role, run=args.run)): role
                   for role in ("server", "client")}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except BaseException as error:
                failures.append(futures[future] + ":" + str(error))
                plan.update(status="failed_draining_peers", failures=list(failures),
                            failure_observed_at=now().isoformat())
                save(directory / "plan.private.json", plan)
                save(directory / "verdict.private.json",
                     {"transport": "FAIL", "billing": "INCONCLUSIVE",
                      "state": "draining_bounded_guests", "failures": list(failures),
                      "at": plan["failure_observed_at"]})
                print("TRANSPORT FAIL; draining bounded guests before verified deallocation",
                      file=sys.stderr, flush=True)
                # Do not cancel a local CLI and mistake that for stopping its guest.
                # The unclaimed server exits within 180s; active guests retain their hard bound.
    return failures


def live(args, directory, plan):
    control_gates(plan)
    if plan.get("scenario") == "cross-region-control":
        require(now() + timedelta(minutes=60) <
                datetime.fromisoformat(plan["cleanup_deadline"].replace("Z", "+00:00")),
                "control_live_would_cross_cleanup_deadline")
    lease = guard("server", seconds=2500)
    require(lease["maxMutations"] - lease.get("actualMutations", 0) >= 10
            and all(x in lease["allowedMutations"] for x in operations(plan)),
            "reserve_ten_named_mutations")
    require(plan.get("status") == "prepared_not_live"
            and plan.get("snapshot_at")
            and 0 <= (now() - datetime.fromisoformat(plan["snapshot_at"])).total_seconds() < 600,
            "fresh_snapshot_required")
    require(args.accept_live_gates, "live_gate_attestation_required")
    require_readiness(directory, plan)
    plan["status"] = "live_no_bulk_retry"
    plan["live_started"] = now().isoformat()
    save(directory / "plan.private.json", plan)
    failures = []
    payload_submitted = False

    def step(action):
        execute(argparse.Namespace(action=action, run=args.run))

    try:
        setup_started = time.monotonic()
        try:
            parallel_steps(args, (action(plan, "start-a"), action(plan, "start-t"), "allow"))
        finally:
            plan["setup_seconds"] = round(time.monotonic() - setup_started, 3)
            save(directory / "plan.private.json", plan)
        # Fail closed before either long command if setup consumed the 200-second margin.
        guard("server", seconds=2500)
        guard("client", seconds=2500)
        payload_submitted = True
        failures.extend(payload_steps(args, directory, plan))
        if not failures:
            step("verify")
    except BaseException as error:
        failures.append(str(error))
    finally:
        plan["restore_started"] = now().isoformat()
        save(directory / "plan.private.json", plan)
        # Verified power-off, not local CLI completion, is the final guest kill boundary.
        endpoints_stopped = True
        for operation in (action(plan, "deallocate-t"), action(plan, "deallocate-a")):
            try:
                step(operation)
            except Exception as error:
                endpoints_stopped = False
                failures.append(operation + ":" + str(error))
        try:
            require(not payload_submitted or endpoints_stopped,
                    "guest_quiescence_unverified_recovery_required")
            step("restore-nsg")
        except Exception as error:
            failures.append("restore-nsg:" + str(error))
        try:
            metrics(directory, plan, restore=True)
        except Exception as error:
            failures.append("metrics:" + str(error))
        plan["status"] = "blocked" if failures else "completed"
        plan["failures"] = failures
        plan["ended"] = now().isoformat()
        report_path = directory / "client-report.private.json"
        if report_path.exists():
            used = read(report_path)["nic"]["delta"]["wire_once"]
            plan["core_remaining_after"] = plan["core_remaining_bytes"] - used
            plan["core_wire_measured"] = used
        if plan.get("scenario") == "cross-region-control":
            plan["core_remaining_after"] = plan["core_remaining_bytes"] - plan["wire_cap"]
        save(directory / "plan.private.json", plan)
        with lease_lock():
            lease = read(LEASE)
            lease["state"] = plan["status"]
            lease["lastCheckpointUtc"] = now().isoformat()
            lease["ownedProcessesIdle"] = lease.get("activeCommands", 0) == 0
            save(LEASE, lease)
    require(not failures, "live_failed_see_private_plan_no_retry")
    print("TRANSPORT PASS; restored; billing INCONCLUSIVE pending mature billing controls")


def main():
    def interrupted(signum, frame):
        raise RuntimeError("owner_process_interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "readiness", "snapshot", "live", "verify",
                                          "metrics") + OPERATIONS +
                        ("ready-a", "ready-t", "start-c", "start-b", "ready-c", "ready-b",
                         "deallocate-c", "deallocate-b"))
    parser.add_argument("--run", required=True)
    parser.add_argument("--core-remaining-bytes", type=int, default=35 * 1024 ** 3)
    parser.add_argument("--accept-live-gates", action="store_true",
                        help="Attest fresh region/ownership/route/day/hour/budget gates in README")
    parser.add_argument("--control", action="store_true",
                        help="Prepare only approved one-way C/NorthEurope to B/SwedenCentral")
    args = parser.parse_args()
    require(re.fullmatch(r"[a-z0-9-]{1,64}", args.run), "invalid_private_run_directory")
    if args.action == "prepare":
        prepare(args)
    else:
        execute(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        print("BLOCKED " + (code if re.fullmatch(r"[a-z0-9_]+", code)
                           else type(error).__name__), file=sys.stderr)
        sys.exit(1)
