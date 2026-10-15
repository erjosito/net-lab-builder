"""Offline preparation and explicit, separately leased Azure RunCommand steps."""
import argparse
import base64
import contextlib
import concurrent.futures
from datetime import datetime, timezone
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
RESTORE = {"restore-nsg", "deallocate-t", "deallocate-a"}


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
             {"code": process.returncode, "stderr": err.decode(errors="replace")})
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


def target(context, inventory, suffix):
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
                and row["location"] == "swedencentral", "inventory_ownership_mismatch")
        result[key] = row["name"]
    return result


def prepare(args):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    directory = PRIVATE / args.run
    require(not directory.exists(), "refuse_existing_run")
    active = read(LAB / "private" / "context.private.json")
    second = read(LAB / "private" / "wsl-cost-context.private.json")
    require(active["subscriptionId"] != second["subscriptionId"]
            and active["expectedTenantId"] != second["expectedTenantId"], "tenants_not_distinct")
    a = target(active, read(LAB / "private" / "inventory.private.json"), "a")
    ti = read(LAB / "private" / "msdn-inventory.private.json")
    t = target(second, ti, "t")
    candidates = [x["properties"].get("ipAddress") for x in ti.get("detailedResources", [])
                  if x["type"].endswith("/publicIPAddresses")]
    require(len(candidates) == 1 and candidates[0], "server_ip_missing")
    server_ip = str(ipaddress.IPv4Address(candidates[0]))
    directory.mkdir()
    certificates(directory / "tls", server_ip)
    remaining = args.core_remaining_bytes
    require(12 * 1024 ** 3 <= remaining <= 35 * 1024 ** 3,
            "core_global_remaining_wire_budget_too_small")
    plan = {"id": uuid.uuid4().hex, "A": a, "T": t, "server_ip": server_ip,
            "core_remaining_bytes": remaining, "prepared": now().isoformat(),
            "bytes": 5368709120, "rate": 2500000, "wire_cap": 12 * 1024 ** 3,
            "operations": list(OPERATIONS), "status": "prepared_not_live",
            "mutations_reserved": 10}
    save(directory / "plan.private.json", plan)
    commands = {}
    for operation in OPERATIONS:
        cfg = a if operation in ("start-a", "client", "deallocate-a") else t
        platform = "windows_native_cli" if cfg is a else "wsl_Ubuntu-24.04_native_cli"
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
        "objective": "A to T and T to A same-region public IPv4 mTLS only",
        "startedAtUtc": "SET_BY_FRESH_OWNER", "expiresAtUtc": "SET_60_MINUTES_AFTER_START",
        "allowedMutations": list(OPERATIONS) + ["emergency-deallocate-t", "emergency-deallocate-a"],
        "maxToolCalls": 150, "maxMutations": 10, "commandTimeoutSeconds": 3000,
        "namedCommandTimeoutSeconds": {"server": 2500, "client": 2500},
        "restoreTimeoutMinutes": 15, "state": "not-active-template",
        "actualToolCalls": 0, "actualMutations": 0, "activeCommands": 0,
        "ownedProcessesIdle": True})
    print("PREPARED private/transfers/" + args.run
          + "; no Azure calls; next fresh live lease then snapshot")


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
                and lease.get("actualMutations", 0) < lease["maxMutations"] * .8,
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


def guest_script(directory, role, plan):
    guest = "/root/bwb-transfer-" + plan["id"]
    cfg = {"id": plan["id"], "bytes": plan["bytes"], "rate": plan["rate"],
           "wire_cap": plan["wire_cap"], "interface": plan.get("interface_" + role, "eth0"),
           "deadline": 2400, "idle": 60, "port": 443, "ca": guest + "/ca.pem",
           "cert": guest + "/" + role + ".pem", "key": guest + "/" + role + ".key",
           "report": guest + "/report.json", "expected_peer": plan["client_ip"]
           if role == "server" else plan["server_ip"]}
    if role == "client":
        cfg["host"] = plan["server_ip"]
        cfg["readiness_attempts"] = 12
    bundle = {"stream.py": (HERE / "stream.py").read_text(), "config.json": json.dumps(cfg)}
    for name in ("ca.pem", role + ".pem", role + ".key"):
        bundle[name] = (directory / "tls" / name).read_text()
    encoded = base64.b64encode(json.dumps(bundle).encode()).decode()
    script = ("#!/bin/sh\nset -eu\numask 077\n"
              "command -v python3 >/dev/null\ncommand -v timeout >/dev/null\n"
              "mkdir " + guest + "\ntrap 'rm -f " + guest + "/*.key' EXIT HUP INT TERM\n"
              "python3 - <<'PY'\nimport base64,json,pathlib,os\n"
              "root=pathlib.Path(" + repr(guest) + ")\n"
              "for name,text in json.loads(base64.b64decode(" + repr(encoded) + ")).items():\n"
              " p=root/name; p.write_text(text); os.chmod(p,0o600)\nPY\n"
              "timeout --signal=TERM --kill-after=10s 2450s python3 " + guest
              + "/stream.py " + role + " " + guest + "/config.json\n")
    path = directory / (role + ".private.sh")
    path.write_text(script, encoding="utf-8", newline="\n")
    return path


def snapshot(directory, plan, a, t):
    a.authorize()
    t.authorize()
    for alias, client in (("A", a), ("T", t)):
        cfg = client.config
        for key in ("vm", "nsg", "pip", "nic"):
            command = ["vm", "show"] if key == "vm" else ["network", key, "show"]
            if key == "pip":
                command = ["network", "public-ip", "show"]
            value = client.cli(command + ["--resource-group", cfg["resourceGroup"],
                                         "--name", cfg[key]])
            require(value["tags"] == {"lab": "true", "created_by": "copilot-lab",
                                     "run_id": cfg["runId"]}
                    and value["location"] == "swedencentral", "live_ownership_mismatch")
            save(directory / (alias + "-" + key + "-before.private.json"), value)
            if key == "pip":
                ip = str(ipaddress.IPv4Address(value["ipAddress"]))
                if alias == "T":
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
    nsg = read(directory / "T-nsg-before.private.json")
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
    plan["snapshot_at"] = now().isoformat()
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


def metrics(directory, plan, restore=False):
    start = plan.get("live_started", plan["snapshot_at"])
    end = now().isoformat()
    for alias in ("A", "T"):
        client = Azure(plan[alias], alias == "T")
        resource = ("/subscriptions/" + plan[alias]["subscriptionId"] + "/resourceGroups/"
                    + plan[alias]["resourceGroup"] + "/providers/Microsoft.Compute/virtualMachines/"
                    + plan[alias]["vm"])
        operation = "read-restore:restore-nsg" if restore else None
        output = client.cli(["monitor", "metrics", "list", "--resource", resource,
                             "--metric", "Network In Total", "Network Out Total",
                             "--interval", "PT1M", "--aggregation", "Total",
                             "--start-time", start, "--end-time", end],
                            operation=operation, seconds=60)
        save(directory / (alias + ("-metrics-after.private.json" if restore
                                  else "-metrics-baseline.private.json")), output)


def execute(args):
    directory = PRIVATE / args.run
    plan = read(directory / "plan.private.json")
    a, t = Azure(plan["A"]), Azure(plan["T"], True)
    if args.action == "snapshot":
        return snapshot(directory, plan, a, t)
    if args.action == "verify":
        import stream
        verdict = stream.verify(read(directory / "client-report.private.json"),
                                read(directory / "server-report.private.json"))
        save(directory / "verdict.private.json", verdict)
        print(json.dumps(verdict))
        return
    if args.action == "live":
        return live(args, directory, plan)
    if args.action == "metrics":
        return metrics(directory, plan, restore=True)
    operation = args.action
    guard(operation, 2500 if operation in ("server", "client") else 180)
    require((directory / "client.private.sh").is_file(), "snapshot_required")
    alias = "A" if operation in ("start-a", "client", "deallocate-a") else "T"
    client = a if alias == "A" else t
    client.authorize(operation)
    cfg = client.config
    base = ["-g", cfg["resourceGroup"], "-n", cfg["vm"]]
    if operation.startswith(("start-", "deallocate-")):
        command = ["vm", "start" if operation.startswith("start-") else "deallocate"] + base
        client.cli(command, operation, 180, directory)
    elif operation in ("allow", "restore-nsg"):
        body = directory / ("nsg-allow.private.json" if operation == "allow"
                            else "nsg-restore.private.json")
        url = ("https://management.azure.com/subscriptions/" + cfg["subscriptionId"]
               + "/resourceGroups/" + cfg["resourceGroup"]
               + "/providers/Microsoft.Network/networkSecurityGroups/" + cfg["nsg"]
               + "?api-version=2024-05-01")
        client.cli(["rest", "--method", "PUT", "--url", url, "--body",
                    "@" + linux_path(body)], operation, 180, directory)
        if operation == "restore-nsg":
            after = client.cli(["network", "nsg", "show", "-g", cfg["resourceGroup"],
                                "-n", cfg["nsg"]], operation="read-restore:restore-nsg")
            before = read(directory / "T-nsg-before.private.json")
            def clean(rules):
                return sorted([{"name": r["name"], **{k: v for k, v in r.items()
                               if k not in ("id", "type", "etag", "resourceGroup",
                                            "provisioningState", "name")}}
                               for r in rules], key=lambda r: r["name"])
            require(clean(after["securityRules"]) == clean(before["securityRules"]),
                    "nsg_exact_restore_not_verified")
            require(after["tags"] == before["tags"] and after["location"] == before["location"],
                    "nsg_metadata_restore_not_verified")
            save(directory / "nsg-restored.private.json", {"verified": True, "at": now().isoformat()})
    else:
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


def live(args, directory, plan):
    lease = guard("server", seconds=2500)
    require(lease["maxMutations"] - lease.get("actualMutations", 0) >= 10
            and all(x in lease["allowedMutations"] for x in OPERATIONS),
            "reserve_ten_named_mutations")
    require(plan.get("status") == "prepared_not_live"
            and plan.get("snapshot_at")
            and (now() - datetime.fromisoformat(plan["snapshot_at"])).total_seconds() < 600,
            "fresh_snapshot_required")
    require(args.accept_live_gates, "live_gate_attestation_required")
    plan["status"] = "live_no_bulk_retry"
    plan["live_started"] = now().isoformat()
    save(directory / "plan.private.json", plan)
    failures = []

    def step(action):
        execute(argparse.Namespace(action=action, run=args.run))

    try:
        metrics(directory, plan)
        for action in ("start-a", "start-t", "allow"):
            step(action)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            server_future = pool.submit(step, "server")
            client_future = pool.submit(step, "client")
            for future in (client_future, server_future):
                future.result()
        step("verify")
    except BaseException as error:
        failures.append(str(error))
    finally:
        # Every restore is attempted once even if another restore step fails.
        for action in ("restore-nsg", "deallocate-t", "deallocate-a"):
            try:
                step(action)
            except Exception as error:
                failures.append(action + ":" + str(error))
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
    parser.add_argument("action", choices=("prepare", "snapshot", "live", "verify", "metrics")
                        + OPERATIONS)
    parser.add_argument("--run", required=True)
    parser.add_argument("--core-remaining-bytes", type=int, default=35 * 1024 ** 3)
    parser.add_argument("--accept-live-gates", action="store_true",
                        help="Attest fresh region/ownership/route/day/hour/budget gates in README")
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
