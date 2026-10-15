"""Bounded Azure CLI commands scoped to the current infrastructure lease."""
import argparse
import datetime as dt
import json
import pathlib
import secrets
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime-control"
LEASE = RUNTIME / "lease.json"
RG = "rg-vwan-sdwan-threehub-20261014"
TAGS = {"lab": "true", "created_by": "copilot-lab", "run_id": "20261014-threehub",
        "owner": "jose", "ephemeral": "true"}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def guard(new_work=True):
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    now = dt.datetime.now(dt.timezone.utc)
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    allowed_states = ("active",) if new_work else ("active", "blocked")
    if (RUNTIME / "STOP").exists() or lease["state"] not in allowed_states or now >= expiry:
        raise RuntimeError("Lease stopped or expired")
    start = dt.datetime.fromisoformat(lease.get("startedAtUtc", "2026-10-14T15:43:53Z" if LEASE.name == "recovery-lease.json" else "2026-10-14T15:33:14Z").replace("Z", "+00:00"))
    if new_work and (now - start).total_seconds() >= 0.8 * (expiry - start).total_seconds():
        raise RuntimeError("80% elapsed budget: closure only")
    if new_work and (lease.get("mutationsUsed", 0) >= 0.8 * lease["maxMutations"]
                     or lease.get("toolCallsUsed", 0) >= 0.8 * lease["maxToolCalls"]):
        raise RuntimeError("80% operation budget: closure only")
    return lease


def az(args, label, mutation=False, timeout=1200, closure=False):
    lease = guard(not closure)
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    timeout = min(timeout, lease["commandTimeoutSeconds"],
                  max(1, (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    if mutation:
        lease["mutationsUsed"] = lease.get("mutationsUsed", 0) + 1
    lease["toolCallsUsed"] = lease.get("toolCallsUsed", 0) + 1
    lease["lastCheckpointUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(LEASE, lease)
    command = [shutil.which("az"), *args, "--only-show-errors", "-o", "json"]
    if (RUNTIME / "account.json").exists() and args[0] != "account":
        command.extend(["--subscription", account_id()])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    save(RUNTIME / "child-process.json", {"pid": process.pid, "label": label, "state": "running"})
    deadline = time.monotonic() + timeout
    try:
        while True:
            guard(False)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                out, err = process.communicate(timeout=min(10, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except (subprocess.TimeoutExpired, RuntimeError):
        # Windows taskkill is PID-scoped and kills the complete CLI process tree.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=30)
        process.communicate(timeout=30)
        lease["state"] = "blocked"
        lease["failure"] = f"{label}: command timeout or lease stop"
        save(LEASE, lease)
        raise
    finally:
        save(RUNTIME / "child-process.json", {"pid": process.pid, "label": label, "state": "terminated"})
    (RUNTIME / f"{label}.stdout.json").write_bytes(out)
    (RUNTIME / f"{label}.stderr.txt").write_bytes(err)
    print(f"{label}: exit={process.returncode}", flush=True)
    if process.returncode:
        print(err.decode(errors="replace"), file=sys.stderr)
        lease["state"] = "blocked"
        lease["failure"] = f"{label}: exit {process.returncode}"
        save(LEASE, lease)
        raise RuntimeError(lease["failure"])
    guard(False)
    return json.loads(out or b"null")


def az_batch(commands, timeout=300, closure=False):
    """Run independent read-only commands with one serialized lease reservation."""
    lease = guard(not closure)
    if not commands or len({label for _, label in commands}) != len(commands):
        raise ValueError("A nonempty batch with unique labels is required")
    if lease.get("toolCallsUsed", 0) + len(commands) > lease["maxToolCalls"]:
        raise RuntimeError("Batch exceeds the absolute call budget")
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    timeout = min(timeout, lease["commandTimeoutSeconds"],
                  max(1, (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    lease["toolCallsUsed"] = lease.get("toolCallsUsed", 0) + len(commands)
    lease["lastCheckpointUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(LEASE, lease)
    processes, results = [], []
    deadline = time.monotonic() + timeout
    try:
        for args, label in commands:
            guard(False)
            command = [shutil.which("az"), *args, "--only-show-errors", "-o", "json"]
            if (RUNTIME / "account.json").exists() and args[0] != "account":
                command.extend(["--subscription", account_id()])
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append((process, label))
            save(RUNTIME / "child-process.json", {
                "state": "running", "children": [{"pid": p.pid, "label": n} for p, n in processes]
            })
        for process, label in processes:
            while True:
                guard(False)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"{label}: batch command timeout")
                try:
                    out, err = process.communicate(timeout=min(10, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            (RUNTIME / f"{label}.stdout.json").write_bytes(out)
            (RUNTIME / f"{label}.stderr.txt").write_bytes(err)
            print(f"{label}: exit={process.returncode}", flush=True)
            if process.returncode:
                raise RuntimeError(f"{label}: {err.decode(errors='replace')}")
            results.append(json.loads(out or b"null"))
        return results
    except Exception as exc:
        lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
        lease.update(state="blocked", failure=str(exc))
        save(LEASE, lease)
        raise
    finally:
        for process, _ in processes:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=30)
                process.communicate(timeout=30)
        save(RUNTIME / "child-process.json", {"state": "terminated", "children": []})


def preflight():
    account = az(["account", "show"], "account")
    save(RUNTIME / "account.json", {"subscriptionId": account["id"]})
    exists = az(["group", "exists", "--name", RG], "group-absence")
    if exists:
        raise RuntimeError("Resource group already exists; refusing creation")
    az(["group", "create", "--name", RG, "--location", "japaneast",
        "--tags", *[f"{k}={v}" for k, v in TAGS.items()]], "group-create", mutation=True)
    key = pathlib.Path.home() / ".ssh" / "id_rsa.pub"
    for region, sku in [("japaneast", "Standard_B2ts_v2"),
                        ("westeurope", "Standard_B2ts_v2"),
                        ("northcentralus", "Standard_B2als_v2")]:
        az(["vm", "create", "-g", RG, "-n", f"capacity-{region}", "-l", region,
            "--image", "Ubuntu2204", "--size", sku, "--admin-username", "azurelabuser",
            "--ssh-key-values", str(key), "--validate"], f"capacity-{region}", timeout=180)
    save(RUNTIME / "capacity-passed.json", {"regions": ["japaneast", "westeurope", "northcentralus"],
                                          "validatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat()})


def deploy_base():
    if not (RUNTIME / "capacity-passed.json").exists():
        raise RuntimeError("Live capacity preflight must pass before manifest generation")
    from infra import base
    base()
    az(["deployment", "group", "validate", "-g", RG, "--template-file", str(ROOT / "base.json")],
       "base-validate", timeout=180)
    az(["deployment", "group", "create", "-g", RG, "--name", "threehub-base",
        "--template-file", str(ROOT / "base.json"), "--no-wait"], "base-submit", mutation=True)


def deploy_compute():
    from infra import compute
    compute()
    params = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
              "contentVersion": "1.0.0.0", "parameters": {
                  "sshPublicKey": {"value": (pathlib.Path.home() / ".ssh" / "id_rsa.pub").read_text().strip()}}}
    save(RUNTIME / "compute.parameters.json", params)
    args = ["-g", RG, "--template-file", str(ROOT / "compute.json"),
            "--parameters", "@" + str(RUNTIME / "compute.parameters.json")]
    az(["deployment", "group", "validate", *args], "compute-validate", timeout=180)
    az(["deployment", "group", "create", *args, "--name", "threehub-compute", "--no-wait"],
       "compute-submit", mutation=True)
    record_operation("threehub-compute")


def record_operation(name):
    lease = guard(False)
    if name in lease.get("operations", {}):
        raise RuntimeError(f"{name}: existing operation deadline must not be reset")
    now = dt.datetime.now(dt.timezone.utc)
    lease.setdefault("operations", {})[name] = {
        "submittedAtUtc": now.isoformat(),
        "deadlineUtc": (now + dt.timedelta(
            seconds=lease["managedOperationTimeoutSeconds"])).isoformat()}
    save(LEASE, lease)


def wait_deployments(names):
    lease = guard(False)
    pending = set(names)
    last_report = time.monotonic()
    last_calls = lease.get("toolCallsUsed", 0)
    while pending:
        guard(False)
        for name in sorted(pending):
            lease = guard(False)
            operation = (lease["transferredOperation"] if name == "threehub-base"
                         else lease["operations"][name])
            deadline = dt.datetime.fromisoformat(operation["deadlineUtc"].replace("Z", "+00:00"))
            if dt.datetime.now(dt.timezone.utc) >= deadline:
                lease.update(state="blocked", failure=f"{name}: absolute operation deadline")
                save(LEASE, lease)
                raise RuntimeError(lease["failure"])
            stamp = int(time.time())
            if operation.get("resourceKind") == "vpnGateways":
                gateway = get_network_resource("vpnGateways", "vpngw-jp",
                                               f"{name}-progress-{stamp}")
                state = gateway["properties"]["provisioningState"]
                progress = [("vpngw-jp", state)]
            else:
                deployment = az(["deployment", "group", "show", "-g", RG, "-n", name],
                                f"{name}-status-{stamp}", closure=True)
                state = deployment["properties"]["provisioningState"]
                operations = az(["deployment", "operation", "group", "list", "-g", RG, "-n", name],
                                f"{name}-progress-{stamp}", closure=True)
                progress = [((x["properties"].get("targetResource") or {}).get("resourceName"),
                             x["properties"].get("provisioningState")) for x in operations]
            print(f"{name}: {state}; progress={progress}", flush=True)
            if time.monotonic() - last_report >= 900 or lease.get("toolCallsUsed", 0) - last_calls >= 25:
                lease = guard(False)
                print(f"LIVE {lease['taskId']} | managed acceptance | "
                      f"calls {lease.get('toolCallsUsed', 0)}/{lease['maxToolCalls']} | "
                      f"mutations {lease.get('mutationsUsed', 0)}/{lease['maxMutations']} | "
                      f"state running | next monitor {','.join(sorted(pending))}", flush=True)
                last_report, last_calls = time.monotonic(), lease.get("toolCallsUsed", 0)
            if state in ("Failed", "Canceled") or any(status == "Failed" for _, status in progress):
                lease = guard(False)
                lease.update(state="blocked", failure=f"{name}: resource acceptance failed")
                save(LEASE, lease)
                raise RuntimeError(lease["failure"])
            if state == "Succeeded":
                pending.remove(name)
        if pending:
            for _ in range(12):
                guard(False)
                time.sleep(10)


def deploy_bindings(vpn=False):
    from infra import hub_bindings, vpn_bindings
    if vpn:
        gateway = az(["rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{account_id()}/resourceGroups/{RG}"
            "/providers/Microsoft.Network/vpnGateways/vpngw-jp?api-version=2024-05-01"],
            "vpn-gateway-discovered")
        pip = az(["network", "public-ip", "show", "-g", RG, "-n", "pip-router-jp"],
                 "jp-router-pip-discovered")
        document = vpn_bindings(gateway, pip["ipAddress"])
        parameters = RUNTIME / "vpn.parameters.json"
        if not parameters.exists():
            save(parameters, {"parameters": {"vpnSharedKey": {"value": secrets.token_urlsafe(48)}}})
        name = "threehub-vpn-bindings"
        extra = ["--parameters", "@" + str(parameters)]
    else:
        connections = az(["deployment", "group", "show", "-g", RG, "-n", "threehub-connections"],
                         "connections-bgp-order-check")
        if connections["properties"]["provisioningState"] != "Succeeded":
            raise RuntimeError("Five VNet connections must succeed before BGP submission")
        hubs = discover_hubs()
        save(RUNTIME / "hub-bindings-discovered.json", hubs)
        document = hub_bindings(hubs)
        name = "threehub-hub-bindings"
        extra = []
    path = RUNTIME / f"{name}.json"
    save(path, document)
    args = ["-g", RG, "--template-file", str(path), *extra]
    if vpn:
        az(["deployment", "group", "what-if", *args, "--no-pretty-print"],
           f"{name}-what-if", timeout=180)
    az(["deployment", "group", "validate", *args], f"{name}-validate", timeout=180)
    az(["deployment", "group", "create", *args, "--name", name, "--no-wait"],
       f"{name}-submit", mutation=True)
    record_operation(name)


def discover_hubs(closure=False):
    return {region: az(["rest", "--method", "get", "--url",
        f"https://management.azure.com/subscriptions/{account_id()}/resourceGroups/{RG}"
        f"/providers/Microsoft.Network/virtualHubs/hub-{region}?api-version=2024-05-01"],
        f"binding-recovery-hub-{region}", closure=closure) for region in ("eu", "us", "jp")}


def deploy_connections():
    from infra import hub_connections
    hubs = discover_hubs(closure=True)
    if any(hub["properties"].get("routingState") != "Provisioned" for hub in hubs.values()):
        raise RuntimeError("Hub routing must be Provisioned before VNet connections")
    submit_template("threehub-connections", hub_connections())


def deploy_vpn_gateway():
    from infra import vpn_gateway
    inventory = az(["resource", "list", "-g", RG,
                    "--resource-type", "Microsoft.Network/vpnGateways"], "gateway-absence")
    if inventory:
        raise RuntimeError("Gateway already exists; refusing gateway-only creation")
    submit_template("threehub-vpn-gateway", vpn_gateway())


def update_vpn_gateway():
    from infra import vpn_gateway_update
    lease = guard()
    if "threehub-vpn-gateway-update" in lease.get("operations", {}):
        raise RuntimeError("This lease already submitted the gateway update")
    gateway = get_network_resource("vpnGateways", "vpngw-jp", "gateway-update-discovered")
    body = vpn_gateway_update(gateway)
    path = RUNTIME / "gateway-update-body.json"
    save(path, body)
    name = "threehub-vpn-gateway-update"
    result = az(["rest", "--method", "put", "--url",
                 f"https://management.azure.com{gateway['id']}?api-version=2024-05-01",
                 "--headers", "Content-Type=application/json", "--body", "@" + str(path)],
                "gateway-update-submit", mutation=True)
    record_operation(name)
    lease = guard(False)
    lease["operations"][name]["resourceKind"] = "vpnGateways"
    save(LEASE, lease)
    if result["properties"].get("provisioningState") == "Failed":
        lease.update(state="blocked", failure="Gateway APIPA update resource acceptance failed")
        save(LEASE, lease)
        raise RuntimeError(lease["failure"])


def submit_template(name, document):
    path = RUNTIME / f"{name}.json"
    save(path, document)
    args = ["-g", RG, "--template-file", str(path)]
    az(["deployment", "group", "validate", *args], f"{name}-validate", timeout=180)
    az(["deployment", "group", "create", *args, "--name", name, "--no-wait"],
       f"{name}-submit", mutation=True)
    record_operation(name)


def recovery_checkpoint():
    lease = guard(False)
    snapshot = json.loads((ROOT.parent / "infrastructure-handoff.json").read_text())
    resources = az(["resource", "list", "-g", RG], "binding-recovery-inventory", closure=True)
    deployments = az(["deployment", "group", "list", "-g", RG],
                     "binding-recovery-deployments", closure=True)
    states = {x["name"]: x["properties"]["provisioningState"] for x in deployments}
    hubs = discover_hubs(closure=True)
    discovered = {region: {k: hub["properties"].get(k) for k in
                  ("virtualRouterAsn", "virtualRouterIps", "routingState", "provisioningState")}
                  for region, hub in hubs.items()}
    endpoints = {"discoveredHubs": discovered, "connections": [], "bgpPeers": []}
    for region in ("eu", "us", "jp"):
        for kind in (("transit", "spoke") if region != "jp" else ("spoke",)):
            name = f"hub-{region}/conn-{kind}-{region}"
            if states.get("threehub-connections") == "Succeeded":
                connection = get_network_resource("virtualHubs", name.replace("/", "/hubVirtualNetworkConnections/"),
                                                  f"binding-final-conn-{kind}-{region}")
                endpoints["connections"].append({"name": name, **connection["properties"]})
        if region != "jp" and states.get("threehub-hub-bindings") == "Succeeded":
            name = f"hub-{region}/bgp-router-{region}"
            peer = get_network_resource("virtualHubs", name.replace("/", "/bgpConnections/"),
                                        f"binding-final-bgp-{region}")
            endpoints["bgpPeers"].append({"name": name, **peer["properties"]})
    if any(x["type"] == "Microsoft.Network/vpnGateways" and x["name"] == "vpngw-jp"
           for x in resources):
        gateway = get_network_resource("vpnGateways", "vpngw-jp", "binding-final-gateway")
        endpoints["vpnGateway"] = {"name": "vpngw-jp", **gateway["properties"]}
    if states.get("threehub-vpn-bindings") == "Succeeded":
        connection = get_network_resource("vpnGateways", "vpngw-jp/vpnConnections/conn-dc-jp",
                                          "binding-final-vpn")
        site = get_network_resource("vpnSites", "site-dc-jp", "binding-final-site")
        endpoints["vpnSite"] = {"name": "site-dc-jp", **site["properties"]}
        endpoints["vpnConnection"] = {
            "name": "vpngw-jp/conn-dc-jp",
            "provisioningState": connection["properties"].get("provisioningState"),
            "links": [{"name": link["name"], **{k: link["properties"].get(k) for k in
                      ("provisioningState", "connectionStatus", "enableBgp", "vpnGatewayCustomBgpAddresses")}}
                      for link in connection["properties"].get("vpnLinkConnections", [])]}
    expected = ("threehub-connections", "threehub-hub-bindings",
                "threehub-vpn-gateway", "threehub-vpn-bindings")
    missing = [name for name in expected if states.get(name) != "Succeeded"]
    endpoints["state"] = "ready" if not missing else "partially completed"
    snapshot.update(
        state="completed" if not missing else "blocked",
        infrastructureReady=not missing, recordedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),
        missing=["Guest BIRD/WireGuard/StrongSwan configuration", *missing],
        resources=[{"name": x["name"], "type": x["type"], "location": x["location"], "id": x["id"]}
                   for x in resources],
        resourceCounts={kind: sum(x["type"] == kind for x in resources)
                        for kind in set(x["type"] for x in resources)},
        deployments=[{"name": name, "state": state} for name, state in states.items()],
        bindings=endpoints, failure=lease.get("failure"),
        bindingRecoveryMutations=lease.get("mutationsUsed", 0),
        bindingRecoveryMutationBreakdown={name: 1 for name in lease.get("operations", {})},
        nextObjective=("Separate guest lease: configure existing BIRD/WireGuard/StrongSwan from actual bindings; no scenario tests or RI"
                       if not missing else
                       "Fresh recovery owner/lease: create only JP VPN gateway without initial custom mappings; discover actual instance IDs/PIPs, "
                       "assign custom BGP addresses in a separately counted update, then deploy VPN bindings. No base/compute rerun or guest HTTP gate."),
        childProcesses="terminated",
        transferredBaseDeadlineUtc=None,
        evidence=[r"deploy\.runtime-control\binding-recovery-deployments.stdout.json",
                  r"deploy\.runtime-control\binding-final-gateway.stdout.json",
                  r"deploy\.runtime-control\binding-final-vpn.stdout.json"],
        runtimeVpnSecretFile=(r"deploy\.runtime-control\vpn.parameters.json (ignored; reuse for guest)"
                              if (RUNTIME / "vpn.parameters.json").exists() else None))
    save(ROOT.parent / "infrastructure-handoff.json",
         json.loads(json.dumps(snapshot).replace(account_id(), "<SUBSCRIPTION_ID>")))
    lease = guard(False)
    lease["state"] = snapshot["state"]
    lease["lastCheckpointUtc"] = snapshot["recordedAtUtc"]
    lease["closedAtUtc"] = snapshot["recordedAtUtc"]
    save(LEASE, lease)
    print(json.dumps({"state": snapshot["state"], "infraMissing": missing,
                      "mutations": lease.get("mutationsUsed", 0),
                      "calls": lease.get("toolCallsUsed", 0)}), flush=True)


def get_network_resource(kind, name, label):
    return az(["rest", "--method", "get", "--url",
               f"https://management.azure.com/subscriptions/{account_id()}/resourceGroups/{RG}"
               f"/providers/Microsoft.Network/{kind}/{name}?api-version=2024-05-01"], label, closure=True)


def gateway_checkpoint():
    lease = guard(False)
    snapshot = json.loads((ROOT.parent / "infrastructure-handoff.json").read_text())
    gateway = get_network_resource("vpnGateways", "vpngw-jp", "gateway-final-resource")
    create = az(["deployment", "group", "show", "-g", RG, "-n", "threehub-vpn-gateway"],
                "gateway-final-create", closure=True)
    bindings = az(["deployment", "group", "show", "-g", RG, "-n", "threehub-vpn-bindings"],
                  "gateway-final-bindings", closure=True)
    site = get_network_resource("vpnSites", "site-dc-jp", "gateway-final-site")
    connection = get_network_resource("vpnGateways", "vpngw-jp/vpnConnections/conn-dc-jp",
                                      "gateway-final-connection")
    nsg = get_network_resource("networkSecurityGroups", "nsg-router-jp", "gateway-final-nsg")
    from infra import vpn_bindings
    expected = vpn_bindings(gateway, site["properties"]["vpnSiteLinks"][0]["properties"]["ipAddress"])
    expected_ike = [rule for rule in expected["resources"][2]["properties"]["securityRules"]
                    if rule["name"] in ("jp-ike", "out-jp-ike")]
    actual_rules = nsg["properties"]["securityRules"]
    valid_ike = all(any(rule["name"] == wanted["name"] and all(
        rule["properties"].get(key) == value for key, value in wanted["properties"].items())
        for rule in actual_rules) for wanted in expected_ike)
    states = {"threehub-vpn-gateway": create["properties"]["provisioningState"],
              "threehub-vpn-gateway-update": gateway["properties"]["provisioningState"],
              "threehub-vpn-bindings": bindings["properties"]["provisioningState"],
              "site-dc-jp": site["properties"]["provisioningState"],
              "conn-dc-jp": connection["properties"]["provisioningState"],
              "nsg-router-jp": nsg["properties"]["provisioningState"]}
    links = connection["properties"].get("vpnLinkConnections", [])
    expected_selections = expected["resources"][1]["properties"]["vpnLinkConnections"][0][
        "properties"]["vpnGatewayCustomBgpAddresses"]
    actual_selections = links[0]["properties"].get("vpnGatewayCustomBgpAddresses", []) if links else []
    site_bgp = site["properties"]["vpnSiteLinks"][0]["properties"]["bgpProperties"]
    accepted = (all(state == "Succeeded" for state in states.values()) and valid_ike
                and len(links) == 1 and links[0]["properties"].get("enableBgp") is True
                and links[0]["properties"].get("provisioningState") == "Succeeded"
                and sorted(actual_selections, key=lambda value: value["ipConfigurationId"])
                == sorted(expected_selections, key=lambda value: value["ipConfigurationId"])
                and site_bgp.get("asn") == 65013 and site_bgp.get("bgpPeeringAddress") == "169.254.21.1")
    endpoints = snapshot["bindings"]
    endpoints.update(
        state="ready" if accepted else "partially completed",
        vpnGateway={"name": "vpngw-jp", **{key: gateway["properties"].get(key) for key in
                    ("provisioningState", "vpnGatewayScaleUnit", "bgpSettings")}},
        vpnSite={"name": "site-dc-jp", **site["properties"]},
        vpnConnection={"name": "vpngw-jp/conn-dc-jp",
            "provisioningState": connection["properties"].get("provisioningState"),
            "links": [{"name": link["name"], **{key: link["properties"].get(key) for key in
                ("provisioningState", "connectionStatus", "enableBgp",
                 "vpnGatewayCustomBgpAddresses", "vpnConnectionProtocolType", "ipsecPolicies")}}
                for link in links]},
        japanIkeRules={"gatewayScoped": valid_ike, "rules": expected_ike})
    for value in (gateway, site):
        if not any(item["id"].lower() == value["id"].lower() for item in snapshot["resources"]):
            snapshot["resources"].append({key: value[key] for key in ("id", "name", "type", "location")})
    snapshot["resourceCounts"] = {
        kind: sum(item["type"] == kind for item in snapshot["resources"])
        for kind in {item["type"] for item in snapshot["resources"]}}
    deployment_states = {item["name"]: item["state"] for item in snapshot["deployments"]}
    deployment_states.update({name: state for name, state in states.items()
                              if name in ("threehub-vpn-gateway", "threehub-vpn-bindings")})
    snapshot["deployments"] = [{"name": name, "state": state}
                               for name, state in deployment_states.items()]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    lease = guard(False)
    for name in lease.get("operations", {}):
        lease["operations"][name]["terminalState"] = states.get(name)
    failure = None if accepted else "Japan VPN final acceptance assertion failed"
    snapshot.update(state="completed" if accepted else "blocked", infrastructureReady=accepted,
        recordedAtUtc=now, failure=failure, missing=["Guest BIRD/WireGuard/StrongSwan configuration"],
        nextObjective="Separate guest lease: configure existing BIRD/WireGuard/StrongSwan from actual bindings; no scenarios or RI",
        nextGuestObjective="Configure six private WireGuard links, filtered BIRD on existing routers and two JP XFRM/StrongSwan tunnels; verify persistence only",
        gatewayRecoveryMutations=lease.get("mutationsUsed", 0),
        gatewayRecoveryToolCalls=lease.get("toolCallsUsed", 0), gatewayRecoveryTerminalStates=states,
        runtimeVpnSecretFile=r"deploy\.runtime-control\vpn.parameters.json (ignored; reuse for guest)",
        childProcesses="terminated", evidence=[
            r"deploy\.runtime-control\gateway-final-resource.stdout.json",
            r"deploy\.runtime-control\gateway-final-connection.stdout.json",
            r"deploy\.runtime-control\gateway-final-site.stdout.json",
            r"deploy\.runtime-control\gateway-final-nsg.stdout.json"])
    save(ROOT.parent / "infrastructure-handoff.json",
         json.loads(json.dumps(snapshot).replace(account_id(), "<SUBSCRIPTION_ID>")))
    lease.update(state=snapshot["state"], failure=failure, lastCheckpointUtc=now, closedAtUtc=now,
                 childProcesses="terminated", queuedWork=False)
    save(LEASE, lease)
    print(json.dumps({"state": lease["state"], "states": states,
                      "mutations": lease["mutationsUsed"], "calls": lease["toolCallsUsed"]}), flush=True)


def checkpoint():
    lease = guard(False)
    resources = az(["resource", "list", "-g", RG], "final-resource-inventory", closure=True)
    deployments = az(["deployment", "group", "list", "-g", RG], "final-deployments", closure=True)
    details = {}
    for deployment in deployments:
        name = deployment["name"]
        operations = az(["deployment", "operation", "group", "list", "-g", RG, "-n", name],
                        f"final-{name}-operations", closure=True)
        details[name] = [{"resource": (x["properties"].get("targetResource") or {}).get("resourceName"),
                         "type": (x["properties"].get("targetResource") or {}).get("resourceType"),
                         "state": x["properties"].get("provisioningState"),
                         "error": x["properties"].get("statusMessage")}
                        for x in operations]
    counts = {}
    for resource in resources:
        counts[resource["type"]] = counts.get(resource["type"], 0) + 1
    states = {x["name"]: x["properties"]["provisioningState"] for x in deployments}
    compute_passed = states.get("threehub-compute") == "Succeeded"
    missing = ["Guest BIRD/WireGuard/StrongSwan configuration"]
    if not compute_passed:
        missing.append("Compute resource acceptance")
    if states.get("threehub-hub-bindings") != "Succeeded":
        missing.append("Five hub VNet connections and two hub BGP connections")
    if states.get("threehub-vpn-bindings") != "Succeeded":
        missing.append("JP VPN site and connection")
    bootstrap_path = RUNTIME / "bootstrap-http-results.json"
    bootstrap_results = json.loads(bootstrap_path.read_text()) if bootstrap_path.exists() else []
    snapshot = {"resourceGroup": RG, "runId": TAGS["run_id"], "state": lease["state"],
                "recordedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "resources": [{"name": x["name"], "type": x["type"], "location": x["location"],
                               "id": x["id"], "provisioningState": x.get("provisioningState")}
                              for x in resources],
                "deployments": [{"name": x["name"], "state": x["properties"]["provisioningState"]}
                                for x in deployments],
                "resourceCounts": counts, "deploymentOperations": details,
                "directedPeerings": {
                    "succeeded": sum(x["type"] == "Microsoft.Network/virtualNetworks/virtualNetworkPeerings"
                                     and x["state"] == "Succeeded"
                                     for x in details.get("threehub-compute", [])),
                    "expected": 26},
                "missing": missing,
                "bootstrapHttp": bootstrap_results,
                "liveComputeValidation": "Passed; deployment resource acceptance "
                                         + ("passed" if compute_passed else "not confirmed"),
                "failure": lease.get("failure"),
                "recoveryMutations": lease.get("mutationsUsed", 0),
                "priorMutations": lease.get("transferredOperation", {}).get("priorMutations", 0),
                "transferredBaseDeadlineUtc": lease.get("transferredOperation", {}).get("deadlineUtc"),
                "bindings": {"state": "not submitted", "discoveredHubs": {
                    region: {k: json.loads((RUNTIME / f"hub-{region}-routing-readiness.stdout.json").read_text()).get(k)
                             for k in ["virtualRouterAsn", "virtualRouterIps", "routingState", "provisioningState"]}
                    for region in ["eu", "us", "jp"]
                    if (RUNTIME / f"hub-{region}-routing-readiness.stdout.json").exists()}},
                "nextObjective": "New owner/lease: bind missing live hub/VPN infrastructure; "
                                 "guest HTTP is separate and not an infrastructure prerequisite",
                "nextGuestObjective": "Blocked until infrastructure succeeds; separate lease to configure "
                                      "six WireGuard links and filtered BIRD plus two JP XFRM/IPsec tunnels "
                                      "from actual discovered endpoints; no scenario matrix or RI",
                "evidence": [r"deploy\.runtime-control\compute-validate.stdout.json",
                             r"deploy\.runtime-control\final-threehub-compute-operations.stdout.json"],
                "childProcesses": "terminated"}
    sanitized = json.loads(json.dumps(snapshot).replace(account_id(), "<SUBSCRIPTION_ID>"))
    save(ROOT.parent / "infrastructure-handoff.json", sanitized)
    print(json.dumps({"state": snapshot["state"], "counts": counts,
                      "deployments": snapshot["deployments"], "failure": snapshot["failure"]}, indent=2))


def account_id():
    return json.loads((RUNTIME / "account.json").read_text())["subscriptionId"]


def cleanup(confirmed=False):
    exists = az(["group", "exists", "-n", RG], "cleanup-exists")
    if not exists:
        print("Resource group absent; nothing to delete.")
        return
    group = az(["group", "show", "-n", RG], "cleanup-group")
    if any(group.get("tags", {}).get(k) != v for k, v in TAGS.items()):
        raise RuntimeError("Cleanup ownership tags do not match; refusing deletion")
    inventory = az(["resource", "list", "-g", RG], "cleanup-inventory")
    print(json.dumps([{"name": x["name"], "type": x["type"]} for x in inventory], indent=2))
    if not confirmed:
        print("Preview only. A fresh cleanup lease and explicit confirmation are required.")
        return
    lease = guard()
    if not any("cleanup" in x.lower() or "delete" in x.lower() for x in lease["allowedMutations"]):
        raise RuntimeError("This lease does not authorize resource-group cleanup")
    if any(x["type"].lower() == "microsoft.network/azurefirewalls" for x in inventory):
        raise RuntimeError("Secured lab requires firewall-before-policy cleanup under its own lease")
    az(["group", "delete", "-n", RG, "--yes", "--no-wait"], "cleanup-submit", mutation=True)
    deadline = time.monotonic() + lease["restoreTimeoutMinutes"] * 60
    while time.monotonic() < deadline:
        guard(False)
        time.sleep(min(120, max(0, deadline - time.monotonic())))
        if not az(["group", "exists", "-n", RG], f"cleanup-check-{int(time.monotonic())}", closure=True):
            lease = guard(False)
            lease["state"] = "completed"
            save(LEASE, lease)
            return
    lease = guard(False)
    lease.update(state="blocked", failure="Cleanup absence not confirmed within restore budget")
    save(LEASE, lease)
    raise RuntimeError(lease["failure"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["preflight", "base", "compute", "checkpoint", "cleanup",
                                        "wait", "connections", "vpn-gateway", "gateway-update", "bindings", "vpn-bindings",
                                        "recovery-checkpoint", "gateway-checkpoint"])
    parser.add_argument("--deployments", nargs="+")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--lease-file", type=pathlib.Path, default=LEASE)
    options = parser.parse_args()
    selected = options.lease_file.resolve()
    if selected.parent != RUNTIME.resolve():
        parser.error("--lease-file must be in this lab's .runtime-control directory")
    LEASE = selected
    if options.phase == "cleanup":
        cleanup(options.confirmed)
    elif options.phase == "wait":
        wait_deployments(options.deployments or ["threehub-base", "threehub-compute"])
    elif options.phase in ("bindings", "vpn-bindings"):
        deploy_bindings(options.phase == "vpn-bindings")
    else:
        {"preflight": preflight, "base": deploy_base, "compute": deploy_compute,
         "checkpoint": checkpoint, "connections": deploy_connections,
         "vpn-gateway": deploy_vpn_gateway, "gateway-update": update_vpn_gateway,
         "recovery-checkpoint": recovery_checkpoint,
         "gateway-checkpoint": gateway_checkpoint}[options.phase]()
