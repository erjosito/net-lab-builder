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
RESTORE = {"restore-nsg", "restore-subnet-nsg", "deallocate-t", "deallocate-a",
           "deallocate-c", "deallocate-b"}
READINESS_OPERATIONS = ("start-a", "start-t", "ready-a", "ready-t",
                        "deallocate-t", "deallocate-a")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def source_identity():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ("run.py", "stream.py")}


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
    result = tuple(action(plan, op) for op in
                   (READINESS_OPERATIONS if readiness else OPERATIONS))
    if not readiness and plan.get("receiver_subnet_nsg"):
        result = result[:2] + ("allow-subnet",) + result[2:6] + (
            "restore-subnet-nsg",) + result[6:]
    return result


def control_wire_cap(payload):
    require(type(payload) is int and 0 < payload <= 5 * 1024 ** 3,
            "invalid_control_payload_bytes")
    # Round 20% wire headroom up to whole GiB; 1 GiB -> 2 GiB, 5 GiB -> 6 GiB.
    gib = 1024 ** 3
    return ((payload * 6 + 5 * gib - 1) // (5 * gib)) * gib


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
    require(plan["rate"] == 2500000
            and plan["wire_cap"] == control_wire_cap(plan["bytes"])
            and plan["wire_cap"] <= plan["core_remaining_bytes"] <= 23 * 1024 ** 3,
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
    payload = getattr(args, "control_payload_bytes", None)
    require(payload is None or control, "control_payload_requires_control")
    payload = 5 * 1024 ** 3 if payload is None else payload
    if control:
        control_wire_cap(payload)
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
    cap = control_wire_cap(payload) if control else 12 * 1024 ** 3
    require(cap <= remaining <= (23 if control else 35) * 1024 ** 3,
            "core_global_remaining_wire_budget_too_small")
    plan = {"id": uuid.uuid4().hex, "A": a, "T": t, "server_ip": server_ip,
            "core_remaining_bytes": remaining, "prepared": now().isoformat(),
            "bytes": payload, "rate": 2500000, "wire_cap": cap,
            "operations": list(OPERATIONS), "status": "prepared_not_live",
            "mutations_reserved": 12, "prepared_sources": source_identity(),
            "aliases": {"client": "A", "server": "T"}, "legs": ["up", "down"],
            "platforms": {"A": "windows_native_cli", "T": "wsl_Ubuntu-24.04_native_cli"}}
    import stream
    plan["payload_sha256"] = stream.digest(payload)
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
        "allowedMutations": list(operations(plan)) + ["allow-subnet", "restore-subnet-nsg"],
        "maxToolCalls": 150, "maxMutations": 12, "commandTimeoutSeconds": 3000,
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

    def cli(self, args, operation=None, seconds=90, directory=None):
        with lease_lock():
            if operation is None or operation.startswith("read-restore:"):
                lease = guard(operation, 0)
                expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
                reserve = 11 + (0 if operation else 900)
                seconds = min(seconds, 90, lease["commandTimeoutSeconds"],
                              (expiry - now()).total_seconds() - reserve)
                require(seconds > 0, "read_deadline_exhausted")
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
            return self._invoke(args, operation, seconds, directory)
        finally:
            with lease_lock():
                lease = read(LEASE)
                lease["activeCommands"] -= 1
                lease["ownedProcessesIdle"] = lease["activeCommands"] == 0
                lease["lastCheckpointUtc"] = now().isoformat()
                save(LEASE, lease)

    def _invoke(self, args, operation, seconds, directory):
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

    def authorize(self, operation=None, seconds=90):
        account = self.cli(["account", "show"], operation="read-restore:" + operation
                           if operation in RESTORE else None, seconds=seconds)
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
            "payload_sha256": plan.get("payload_sha256"),
            "core_remaining_bytes": plan["core_remaining_bytes"],
            "cleanup_deadline": plan.get("cleanup_deadline"),
            "network_bindings": plan.get("network_bindings"),
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


def owned_network(value, cfg, inventory, kind):
    expected_tags = {"lab": "true", "created_by": "copilot-lab", "run_id": cfg["runId"]}
    prefix = ("/subscriptions/" + cfg["subscriptionId"] + "/resourceGroups/"
              + cfg["resourceGroup"] + "/providers/Microsoft.Network/" + kind + "/").lower()
    identity = value.get("id", "").lower()
    rows = [row for row in inventory["resources"] if row["id"].lower() == identity]
    require(identity.startswith(prefix) and "/" not in identity[len(prefix):]
            and len(rows) == 1 and inventory["runId"] == cfg["runId"]
            and rows[0]["tags"] == expected_tags and value.get("tags") == expected_tags
            and rows[0]["location"] == value.get("location") == cfg.get("region", "swedencentral"),
            "subnet_network_ownership_mismatch")
    require(value.get("provisioningState") == "Succeeded", "subnet_network_not_succeeded")


def require_standard_defaults(nsg):
    expected = []
    for name, priority, direction, access, source, destination in (
            ("AllowVnetInBound", 65000, "Inbound", "Allow", "VirtualNetwork", "VirtualNetwork"),
            ("AllowAzureLoadBalancerInBound", 65001, "Inbound", "Allow", "AzureLoadBalancer", "*"),
            ("DenyAllInBound", 65500, "Inbound", "Deny", "*", "*"),
            ("AllowVnetOutBound", 65000, "Outbound", "Allow", "VirtualNetwork", "VirtualNetwork"),
            ("AllowInternetOutBound", 65001, "Outbound", "Allow", "*", "Internet"),
            ("DenyAllOutBound", 65500, "Outbound", "Deny", "*", "*")):
        expected.append({"name": name, "priority": priority, "direction": direction,
                         "access": access, "protocol": "*", "sourcePortRange": "*",
                         "destinationPortRange": "*", "sourceAddressPrefix": source,
                         "destinationAddressPrefix": destination})
    observed = normalized_rules(nsg.get("defaultSecurityRules", []))
    for rule in observed:
        rule.pop("description", None)
    require(observed == normalized_rules(expected)
            and all(rule.get("provisioningState") == "Succeeded"
                    for rule in nsg["defaultSecurityRules"] + nsg.get("securityRules", []))
            and nsg.get("provisioningState") == "Succeeded"
            and not nsg.get("flushConnection", False), "unknown_default_nsg_policy")


def subnet_association(nic, subnet):
    require(len(nic.get("ipConfigurations", [])) == 1, "unknown_subnet_configuration")
    identity = nic["ipConfigurations"][0].get("subnet", {}).get("id", "")
    require(identity and subnet.get("id", "").lower() == identity.lower()
            and subnet.get("provisioningState") == "Succeeded", "subnet_association_mismatch")
    return {"nic": nic["id"].lower(), "nic_nsg": nic["networkSecurityGroup"]["id"].lower(),
            "subnet": identity.lower(),
            **{key: (subnet.get(key) or {}).get("id", "").lower()
               for key in ("networkSecurityGroup", "routeTable", "natGateway")}}


def snapshot_subnet(directory, plan, alias, client):
    cfg = client.config
    nic = read(directory / (alias + "-nic-before.private.json"))
    identity = nic["ipConfigurations"][0].get("subnet", {}).get("id", "")
    require(re.fullmatch(r".+/providers/Microsoft.Network/virtualNetworks/[^/]+/subnets/[^/]+",
                         identity, re.IGNORECASE), "unknown_subnet_configuration")
    inventory_name = ("control-inventory.private.json" if alias == "C" else
                      "msdn-inventory.private.json" if alias == "T" else "inventory.private.json")
    inventory = read(LAB / "private" / inventory_name)
    parent = client.cli(["network", "vnet", "show", "--ids", identity.rsplit("/subnets/", 1)[0]])
    owned_network(parent, cfg, inventory, "virtualNetworks")
    save(directory / (alias + "-vnet-before.private.json"), parent)
    subnet = client.cli(["network", "vnet", "subnet", "show", "--ids", identity])
    binding = subnet_association(nic, subnet)
    require(not binding["routeTable"] and not binding["natGateway"],
            "unknown_subnet_egress_configuration")
    save(directory / (alias + "-subnet-before.private.json"), subnet)
    nsg_id = binding["networkSecurityGroup"]
    if nsg_id:
        nsg = client.cli(["network", "nsg", "show", "--ids", nsg_id])
        owned_network(nsg, cfg, inventory, "networkSecurityGroups")
        require_standard_defaults(nsg)
        require(nsg["id"].lower() == nsg_id, "subnet_nsg_identity_mismatch")
        if nsg_id != cfg["nsg_id"].lower():
            require(nsg.get("securityRules") == [], "unknown_subnet_nsg_policy")
        save(directory / (alias + "-subnet-nsg-before.private.json"), nsg)
        binding["subnet_nsg_baseline"] = {
            "id": nsg_id, "tags": nsg["tags"], "location": nsg["location"],
            "rules": normalized_rules(nsg["securityRules"]),
            "defaults": normalized_rules(nsg.get("defaultSecurityRules", []))}
    before = read(directory / (alias + "-nsg-before.private.json"))
    require_standard_defaults(before)
    binding["nic_nsg_baseline"] = {
        "id": before["id"].lower(), "tags": before["tags"], "location": before["location"],
        "rules": normalized_rules(before["securityRules"]),
        "defaults": normalized_rules(before.get("defaultSecurityRules", []))}
    return binding


def receiver_policy(directory, plan, subnet=False):
    alias = names(plan)["server"]
    nsg = read(directory / (alias + ("-subnet-nsg" if subnet else "-nsg")
                            + "-before.private.json"))
    return nsg


def policy_bodies(directory, plan, nsg, subnet=False, write=True):
    mutable = ("name", "description", "protocol", "sourcePortRange", "destinationPortRange",
               "sourceAddressPrefix", "destinationAddressPrefix", "sourcePortRanges",
               "destinationPortRanges", "sourceAddressPrefixes", "destinationAddressPrefixes",
               "access", "priority", "direction")
    original = [{"name": r["name"], "properties": {k: v for k, v in r.items()
                 if k in mutable and k != "name" and v is not None}} for r in nsg["securityRules"]]
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
    prefix = "subnet-nsg" if subnet else "nsg"
    if write:
        save(directory / (prefix + "-restore.private.json"), restore)
        save(directory / (prefix + "-allow.private.json"), allowed)
    return restore, allowed


def snapshot(directory, plan, a, t, readiness=False):
    control_gates(plan)
    plan.pop("snapshot_at", None)
    plan["snapshot_sources"] = source_identity()
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
        deny = nsg_info["securityRules"][0]
        require(normalized_rules([deny]) == normalized_rules([{
            "name": deny["name"], "priority": 100, "access": "Deny", "direction": "Inbound",
            "protocol": "*", "sourceAddressPrefix": "*", "destinationAddressPrefix": "*",
            "sourcePortRange": "*", "destinationPortRange": "*"}]),
            "unknown_endpoint_nsg_policy")
    plan["network_bindings"] = {
        alias: snapshot_subnet(directory, plan, alias, client)
        for alias, client in zip(endpoint_names(plan), (a, t))}
    server_binding = plan["network_bindings"][names(plan)["server"]]
    plan["receiver_subnet_nsg"] = (
        server_binding["networkSecurityGroup"]
        if server_binding["networkSecurityGroup"] != server_binding["nic_nsg"] else "")
    plan["operations"] = list(operations(plan))
    nsg = read(directory / (names(plan)["server"] + "-nsg-before.private.json"))
    rules = nsg["securityRules"]
    require(len(rules) == 1 and rules[0]["priority"] == 100 and rules[0]["access"] == "Deny"
            and rules[0]["direction"] == "Inbound" and rules[0]["protocol"] == "*",
            "unexpected_nsg_baseline")
    policy_bodies(directory, plan, nsg)
    if plan["receiver_subnet_nsg"]:
        policy_bodies(directory, plan, receiver_policy(directory, plan, True), True)
        commands = read(directory / "commands.private.json")
        for operation, suffix in (("allow-subnet", "allow"), ("restore-subnet-nsg", "restore")):
            commands[operation] = {
                "platform": plan.get("platforms", {}).get(
                    names(plan)["server"], "wsl_Ubuntu-24.04_native_cli"
                    if names(plan)["server"] == "T" else "windows_native_cli"),
                "argv_before_native_path_conversion": [
                    "rest", "--method", "PUT", "--url",
                    "https://management.azure.com" + plan["receiver_subnet_nsg"]
                    + "?api-version=2024-05-01", "--body",
                    "@" + str(directory / ("subnet-nsg-" + suffix + ".private.json")),
                    "--subscription", t.config["subscriptionId"],
                    "--only-show-errors", "--output", "json"]}
        save(directory / "commands.private.json", commands)
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


def nsg_gate_binding(directory, plan, subnet=False):
    alias = names(plan)["server"]
    before = receiver_policy(directory, plan, subnet)
    nic = read(directory / (alias + "-nic-before.private.json"))
    desired = read(directory / ("subnet-nsg-allow.private.json" if subnet
                                else "nsg-allow.private.json"))
    return {"id": plan["id"], "snapshot_at": plan["snapshot_at"],
            "nsg": before["id"].lower(), "nic": nic["id"].lower(),
            "location": desired["location"], "tags": desired["tags"],
            "rules": normalized_rules(desired["properties"]["securityRules"]),
            "context": plan.get(alias), "network": plan.get("network_bindings"),
            "sources": plan.get("snapshot_sources"),
            "bytes": plan.get("bytes"), "wire_cap": plan.get("wire_cap"),
            "aliases": names(plan)}


def check_receiver_association(directory, plan, client, query, nic=None):
    binding = plan.get("network_bindings", {}).get(names(plan)["server"])
    if binding is None:
        return
    nic = query("nic") if nic is None else nic
    subnet = query("subnet")
    observed = subnet_association(nic, subnet)
    require(all(observed[key] == binding[key] for key in observed),
            "receiver_network_association_mismatch")


def network_query(client, plan, kind, seconds, operation=None, subnet=False):
    if kind == "subnet":
        identity = plan["network_bindings"][names(plan)["server"]]["subnet"]
        args = ["network", "vnet", "subnet", "show", "--ids", identity]
    elif kind == "nsg" and subnet:
        args = ["network", "nsg", "show", "--ids", plan["receiver_subnet_nsg"]]
    else:
        args = ["network", kind, "show", "-g", client.config["resourceGroup"],
                "-n", client.config[kind]]
    return client.cli(args, operation=operation, seconds=seconds)


def put_policy_once(directory, plan, client, operation, body, identity, seconds):
    if plan.get("network_bindings"):
        subnet = operation in ("allow-subnet", "restore-subnet-nsg")
        before = receiver_policy(directory, plan, subnet)
        baseline = plan["network_bindings"][names(plan)["server"]][
            "subnet_nsg_baseline" if subnet else "nic_nsg_baseline"]
        require(before["id"].lower() == identity.lower() == baseline["id"]
                and before["tags"] == baseline["tags"] and before["location"] == baseline["location"]
                and normalized_rules(before["securityRules"]) == baseline["rules"]
                and normalized_rules(before.get("defaultSecurityRules", [])) == baseline["defaults"],
                "bound_nsg_baseline_changed")
        original, allowed = policy_bodies(directory, plan, before, subnet, write=False)
        require(read(body) == (original if operation in RESTORE else allowed),
                "exact_nsg_write_policy_required")
        try:
            with (directory / (operation + "-attempt.private.json")).open("x") as marker:
                json.dump({"operation": operation, "at": now().isoformat(),
                           "id": plan["id"], "resource": identity}, marker)
        except FileExistsError:
            raise RuntimeError("nsg_write_already_attempted_no_retry") from None
    client.cli(["rest", "--method", "PUT", "--url",
                "https://management.azure.com" + identity + "?api-version=2024-05-01",
                "--body", "@" + (linux_path(body) if client.wsl else str(body))],
               operation, seconds, directory)


def preflight_receiver(directory, plan, client, seconds):
    def query(kind):
        guard("server", 2500)
        return network_query(client, plan, kind, seconds())

    check_receiver_association(directory, plan, client, query)
    binding = plan["network_bindings"][names(plan)["server"]]
    for subnet in (False, True) if plan.get("receiver_subnet_nsg") else (False,):
        observed = network_query(client, plan, "nsg", seconds(), subnet=subnet)
        baseline = binding["subnet_nsg_baseline" if subnet else "nic_nsg_baseline"]
        require(observed.get("id", "").lower() == baseline["id"]
                and observed.get("tags") == baseline["tags"]
                and observed.get("location") == baseline["location"]
                and observed.get("provisioningState") == "Succeeded"
                and all(rule.get("provisioningState") == "Succeeded"
                        for rule in observed["securityRules"])
                and normalized_rules(observed["securityRules"]) == baseline["rules"]
                and normalized_rules(observed.get("defaultSecurityRules", []))
                == baseline["defaults"], "receiver_baseline_changed")
    guard("server", 2500)


def wait_nsg_allow(directory, plan, client, subnet=False):
    """One PUT only; read back completion and exact receiver NIC policy within setup time."""
    binding = nsg_gate_binding(directory, plan, subnet) if subnet else nsg_gate_binding(directory, plan)
    started = time.monotonic()
    evidence = {"verified": False, "binding": binding, "polls": []}
    path = directory / ("subnet-nsg-gate.private.json" if subnet else "nsg-gate.private.json")
    save(path, evidence)

    def remaining():
        lease = guard("server", 2500)
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        return min(180 - (time.monotonic() - started),
                   (expiry - now()).total_seconds() - 3400)

    def query(kind):
        seconds = min(90, remaining())
        require(seconds > 0, "nsg_gate_setup_timeout")
        result = network_query(client, plan, kind, seconds, subnet=subnet)
        guard("server", 2500)
        require(remaining() > 0, "nsg_gate_setup_timeout")
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
                if plan.get("network_bindings"):
                    before = receiver_policy(directory, plan, subnet)
                    require(normalized_rules(after.get("defaultSecurityRules", []))
                            == normalized_rules(before.get("defaultSecurityRules", [])),
                            "nsg_gate_default_policy_mismatch")
                nic = query("nic")
                evidence["nic"] = nic
                require(nic.get("id", "").lower() == binding["nic"]
                        and nic.get("networkSecurityGroup", {}).get("id", "").lower()
                        == (plan[names(plan)["server"]]["nsg_id"] if subnet else
                            binding["nsg"]).lower(), "nsg_gate_association_mismatch")
                check_receiver_association(directory, plan, client, query, nic)
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


def require_nsg_allow(directory, plan, subnet=False):
    if plan.get("network_bindings"):
        require(plan.get("snapshot_sources") == source_identity(), "source_changed_new_snapshot_required")
    evidence = read(directory / ("subnet-nsg-gate.private.json" if subnet
                                else "nsg-gate.private.json"))
    age = (now() - datetime.fromisoformat(evidence["completed_at"])).total_seconds() \
        if evidence.get("completed_at") else -1
    require(evidence.get("verified") is True and 0 <= age < 200
            and evidence["binding"] == (nsg_gate_binding(directory, plan, True) if subnet
                                        else nsg_gate_binding(directory, plan)),
            "completed_exact_nsg_gate_required")
    if not subnet and plan.get("receiver_subnet_nsg"):
        require_nsg_allow(directory, plan, True)


def restore_nsg(directory, plan, client, started, subnet=False, phase="all", deadline=None):
    """Submit once and verify the original policy within the shared restore reserve."""
    mutation = "restore-subnet-nsg" if subnet else "restore-nsg"
    if phase != "poll" and plan.get("network_bindings"):
        require(not (directory / (mutation + "-attempt.private.json")).exists(),
                "nsg_write_already_attempted_no_retry")
    path = directory / ("subnet-nsg-restored.private.json" if subnet else "nsg-restored.private.json")
    evidence = read(path) if phase == "poll" else {"verified": False, "polls": []}
    save(path, evidence)
    operation = "read-restore:" + mutation
    try:
        alias = names(plan)["server"]
        before = receiver_policy(directory, plan, subnet)
        original_nic = read(directory / (alias + "-nic-before.private.json"))
        budget = 900
        if plan.get("restore_started"):
            budget = min(budget, 900 - (now() - datetime.fromisoformat(
                plan["restore_started"])).total_seconds())
        deadline = min(deadline, time.monotonic() + budget) if deadline is not None else started + budget

        def remaining():
            lease = guard(operation, 0)
            expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
            return min(deadline - time.monotonic(), (expiry - now()).total_seconds() - 11)

        if phase != "poll":
            require(remaining() > (180 if phase == "all" else 0),
                    "nsg_restore_insufficient_budget")
            client.authorize(mutation, seconds=min(90, remaining()))
            require(remaining() > (180 if phase == "all" else 0),
                    "nsg_restore_insufficient_budget")

        def query(kind):
            seconds = min(90, remaining())
            require(seconds > 0, "nsg_restore_timeout")
            result = network_query(client, plan, kind, seconds, operation=operation, subnet=subnet)
            require(remaining() > 0, "nsg_restore_timeout")
            return result

        if phase != "poll" and plan.get("network_bindings"):
            current = query("nsg")
            require(current.get("id", "").lower() == before["id"].lower()
                    and current.get("tags") == before["tags"]
                    and current.get("location") == before["location"],
                    "nsg_restore_ownership_changed")
            check_receiver_association(directory, plan, client, query)
            require(remaining() > (180 if phase == "all" else 0),
                    "nsg_restore_insufficient_budget")
        if phase != "poll":
            body = directory / ("subnet-nsg-restore.private.json" if subnet else "nsg-restore.private.json")
            seconds = 180 if phase == "all" else min(180, remaining())
            require(seconds > 0, "nsg_restore_timeout")
            evidence["submission_attempted"] = True
            save(path, evidence)
            put_policy_once(directory, plan, client, mutation, body, before["id"], seconds)
            require(remaining() > 0, "nsg_restore_timeout")
            if phase == "submit":
                return
        else:
            require(evidence.get("submission_attempted"), "nsg_restore_not_submitted")
            seconds = min(90, remaining())
            require(seconds > 0, "nsg_restore_timeout")
            client.authorize(mutation, seconds=seconds)

        while True:
            after = query("nsg")
            evidence["polls"].append({"at": now().isoformat(), "nsg": after})
            save(path, evidence)
            require(after.get("id", "").lower() == before["id"].lower(),
                    "nsg_restore_identity_mismatch")
            rules = after.get("securityRules", [])
            require(normalized_rules(rules) == normalized_rules(before["securityRules"])
                    and after.get("tags") == before["tags"]
                    and after.get("location") == before["location"]
                    and normalized_rules(after.get("defaultSecurityRules", []))
                    == normalized_rules(before.get("defaultSecurityRules", [])),
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
                        == original_nic["networkSecurityGroup"]["id"].lower(),
                        "nsg_restore_association_mismatch")
                check_receiver_association(directory, plan, client, query, nic)
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
    if args.action == "verify":
        import stream
        expected = dict(plan)
        if "payload_sha256" not in expected:
            expected["payload_sha256"] = stream.digest(plan["bytes"])
        verdict = stream.verify(read(directory / "client-report.private.json"),
                                read(directory / "server-report.private.json"), expected)
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
    restore_deadline = vars(args).get("restore_deadline")
    restore_phase = vars(args).get("restore_phase", "all")

    def restore_seconds(limit):
        seconds = limit
        if plan.get("restore_started"):
            seconds = min(seconds, 900 - (now() - datetime.fromisoformat(
                plan["restore_started"])).total_seconds())
        if restore_deadline is not None:
            seconds = min(seconds, restore_deadline - time.monotonic())
        lease = guard("read-restore:" + operation, 0)
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        seconds = min(seconds, (expiry - now()).total_seconds() - 11)
        require(seconds > 0, "restore_reserve_exhausted")
        return seconds

    guard(operation, 0 if restore_deadline is not None else
          2500 if operation in ("server", "client") else 180)
    require((directory / "client.private.sh").is_file(), "snapshot_required")
    require(operation in operations(plan) + operations(plan, True), "operation_not_in_plan")
    alias = names(plan)["client"] if operation in (
        action(plan, "start-a"), "client", action(plan, "ready-a"),
        action(plan, "deallocate-a")) else names(plan)["server"]
    client = a if alias == names(plan)["client"] else t
    if operation in ("restore-nsg", "restore-subnet-nsg"):
        if plan.get("network_bindings"):
            for suffix, endpoint in zip(("a", "t"), endpoint_names(plan)):
                evidence = read(directory / (action(plan, "deallocate-" + suffix)
                                             + "-verified.private.json"))
                cutoff = plan.get("restore_started", plan.get("live_started", plan["snapshot_at"]))
                require(evidence.get("verified") is True
                        and evidence.get("binding") == {"id": plan["id"], "endpoint": plan[endpoint]}
                        and now() >= datetime.fromisoformat(evidence["at"])
                        >= datetime.fromisoformat(cutoff),
                        "guest_quiescence_unverified_recovery_required")
        options = {"phase": restore_phase, "deadline": restore_deadline} \
            if restore_deadline is not None else {}
        restore_nsg(directory, plan, client, started, subnet=True, **options) \
            if operation == "restore-subnet-nsg" else restore_nsg(
                directory, plan, client, started, **options)
        print("STEP returned: " + operation + "; never automatically retry")
        return
    authorization_seconds = 90
    if operation in ("server", "client") or (
            plan.get("live_started") and operation not in RESTORE):
        lease = guard("server", 2500)
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        authorization_seconds = min(authorization_seconds, (expiry - now()).total_seconds() - 3400)
        require(authorization_seconds > 0, "nsg_gate_setup_timeout")
    if operation in RESTORE and plan.get("restore_started"):
        authorization_seconds = min(authorization_seconds, 900 - (now() - datetime.fromisoformat(
            plan["restore_started"])).total_seconds())
        require(authorization_seconds > 0, "restore_reserve_exhausted")
    if restore_deadline is not None:
        authorization_seconds = restore_seconds(authorization_seconds)
    client.authorize(operation, seconds=authorization_seconds)
    cfg = client.config
    base = ["-g", cfg["resourceGroup"], "-n", cfg["vm"]]
    if operation.startswith(("start-", "deallocate-")):
        command = ["vm", "start" if operation.startswith("start-") else "deallocate"] + base
        client.cli(command, operation, restore_seconds(180)
                   if restore_deadline is not None else 180, directory)
    elif operation in ("allow", "allow-subnet"):
        require(plan.get("network_bindings"), "fresh_subnet_snapshot_required")
        require(plan.get("snapshot_sources") == source_identity(), "source_changed_new_snapshot_required")
        def setup_seconds():
            lease = guard("server", 2500)
            expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
            seconds = min(90, (expiry - now()).total_seconds() - 3400)
            require(seconds > 0, "nsg_gate_setup_timeout")
            return seconds
        if operation == "allow-subnet" or not plan.get("receiver_subnet_nsg"):
            preflight_receiver(directory, plan, client, setup_seconds)
        else:
            require_nsg_allow(directory, plan, True)
        subnet = operation == "allow-subnet"
        body = directory / ("subnet-nsg-allow.private.json" if subnet else "nsg-allow.private.json")
        put_policy_once(directory, plan, client, operation, body,
                        plan["receiver_subnet_nsg"] if subnet else cfg["nsg_id"],
                        setup_seconds())
        wait_nsg_allow(directory, plan, client, True) if subnet else wait_nsg_allow(directory, plan, client)
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
        seconds = 90
        if plan.get("restore_started"):
            seconds = min(seconds, 900 - (now() - datetime.fromisoformat(
                plan["restore_started"])).total_seconds())
            require(seconds > 0, "restore_reserve_exhausted")
        if restore_deadline is not None:
            seconds = restore_seconds(seconds)
        view = client.cli(["vm", "get-instance-view"] + base,
                          operation="read-restore:" + operation, seconds=seconds)
        if restore_deadline is not None:
            restore_seconds(90)
        require(any(x["code"] == "PowerState/deallocated" for x in
                    view.get("instanceView", view)["statuses"]), "deallocation_not_verified")
        save(directory / (operation + "-verified.private.json"),
             {"verified": True, "at": now().isoformat(),
              "binding": {"id": plan.get("id"), "endpoint": plan.get(alias)}})
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

    def step(action, **options):
        execute(argparse.Namespace(action=action, run=args.run, **options))

    try:
        setup_started = time.monotonic()
        try:
            def allow_layers():
                if plan.get("receiver_subnet_nsg"):
                    step("allow-subnet")
                step("allow")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                boot = pool.submit(parallel_steps, args,
                                   (action(plan, "start-a"), action(plan, "start-t")))
                policy = pool.submit(allow_layers)
                for future in (boot, policy):
                    future.result()
        finally:
            plan["setup_seconds"] = round(time.monotonic() - setup_started, 3)
            save(directory / "plan.private.json", plan)
        # Fail closed before either long command if setup consumed the 200-second margin.
        guard("server", seconds=2500)
        guard("client", seconds=2500)
        failures.extend(payload_steps(args, directory, plan))
        if not failures:
            step("verify")
    except BaseException as error:
        failures.append(str(error))
    finally:
        plan["restore_started"] = now().isoformat()
        expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        restore_deadline = time.monotonic() + max(
            0, min(900, (expiry - now()).total_seconds() - 11))
        save(directory / "plan.private.json", plan)
        # Verified power-off, not local CLI completion, is the final guest kill boundary.
        endpoints_stopped = True
        for operation in (action(plan, "deallocate-t"), action(plan, "deallocate-a")):
            try:
                step(operation, restore_deadline=time.monotonic() + max(
                    0, restore_deadline - time.monotonic()) / 4)
            except Exception as error:
                endpoints_stopped = False
                failures.append(operation + ":" + str(error))
                print("BLOCKED " + failures[-1], file=sys.stderr, flush=True)
        restorations = ("restore-nsg", "restore-subnet-nsg") if plan.get(
            "receiver_subnet_nsg") else ("restore-nsg",)
        phases = ("submit", "poll") if plan.get("network_bindings") or len(
            restorations) > 1 else ("all",)
        for phase in phases:
            for index, operation in enumerate(restorations):
                try:
                    require(endpoints_stopped, "guest_quiescence_unverified_recovery_required")
                    options = {}
                    if phase != "all":
                        remaining = max(0, restore_deadline - time.monotonic())
                        # Keep half for completion; no authorization, GET or PUT can
                        # consume a later layer's independent submission allocation.
                        share = remaining / ((len(restorations) - index)
                                             * (2 if phase == "submit" else 1))
                        options = {"restore_phase": phase,
                                   "restore_deadline": time.monotonic() + share}
                    step(operation, **options)
                except Exception as error:
                    failures.append(operation + ":" + phase + ":" + str(error))
                    print("BLOCKED " + failures[-1], file=sys.stderr, flush=True)
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
                         "deallocate-c", "deallocate-b", "allow-subnet", "restore-subnet-nsg"))
    parser.add_argument("--run", required=True)
    parser.add_argument("--core-remaining-bytes", type=int, default=35 * 1024 ** 3)
    parser.add_argument("--accept-live-gates", action="store_true",
                        help="Attest fresh region/ownership/route/day/hour/budget gates in README")
    parser.add_argument("--control", action="store_true",
                        help="Prepare only approved one-way C/NorthEurope to B/SwedenCentral")
    parser.add_argument("--control-payload-bytes", type=int,
                        help="Prepare --control only: positive payload bytes, at most 5 GiB")
    args = parser.parse_args()
    require(re.fullmatch(r"[a-z0-9-]{1,64}", args.run), "invalid_private_run_directory")
    if args.action == "prepare":
        prepare(args)
    else:
        require(args.control_payload_bytes is None, "control_payload_prepare_only")
        execute(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        print("BLOCKED " + (code if re.fullmatch(r"[a-z0-9_]+", code)
                           else type(error).__name__), file=sys.stderr)
        sys.exit(1)
