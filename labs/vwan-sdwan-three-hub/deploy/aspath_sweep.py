"""One leased ASPath/JP-only experiment; exact-file restore is mandatory."""
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
import time

import control
import effective_routes
import guest
import infra

SITES = ("eu", "us", "jp")
PREFIXES = tuple(guest.DC.values())
OUT = control.ROOT.parent / "show-output" / "unsecured-aspath-jp"
CURRENT = OUT
SUB = None
RESTORING = False
RESTORE_DEADLINE = None
SOURCE_BASE = {}
BASELINE_HASH = "89b67f35ed1750b258c61e3760f9c290da6f865f5580a56b7e6553625d45e006"
REUSE_COMMANDS = False
BACKUP = "/var/lib/threehub/aspath-jp-baseline.conf"
FILTER = ('filter azure_export {\n'
          '  if net ~ [10.110.0.0/24, 10.120.0.0/24, 10.130.0.0/24, 10.140.0.0/24] &&\n'
          '     (proto = "own_dc" || proto ~ "mesh_*") then accept;\n'
          '  reject;\n}')


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(name, value):
    CURRENT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2) if not isinstance(value, str) else value
    (CURRENT / name).write_text(text.replace(SUB or "<unset>", "<SUBSCRIPTION_ID>") + "\n", encoding="utf-8")


def checkpoint(phase, state, next_action):
    lease = control.guard(False)
    start = dt.datetime.fromisoformat(lease["startedAtUtc"].replace("Z", "+00:00"))
    end = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    print(f"LIVE {lease['taskId']} | {phase} | "
          f"{(dt.datetime.now(dt.timezone.utc)-start).total_seconds()/60:.1f}/{(end-start).total_seconds()/60:.0f}min | "
          f"calls {lease.get('toolCallsUsed',0)}/{lease['maxToolCalls']} | "
          f"mutations {lease.get('mutationsUsed',0)}/{lease['maxMutations']} | state {state} | next {next_action}", flush=True)


def az(args, label, mutation=False):
    lease = control.guard(False)
    # After mutation five only the current bounded capture and restore may proceed.
    if mutation and not RESTORING:
        control.guard(True)
    elif not RESTORING and lease.get("mutationsUsed", 0) < 5:
        control.guard(True)
    if lease.get("toolCallsUsed", 0) >= lease["maxToolCalls"]:
        raise RuntimeError("Absolute call budget exhausted")
    timeout = 600
    if RESTORE_DEADLINE is not None:
        timeout = min(timeout, RESTORE_DEADLINE - time.monotonic())
        if timeout <= 0:
            raise RuntimeError("Absolute restore deadline reached")
    began = utc()
    value = control.az(args, "aspath-" + label, mutation=mutation, timeout=timeout, closure=True)
    raw = (control.RUNTIME / f"aspath-{label}.stdout.json").read_text(encoding="utf-8-sig")
    save(label + ".json", {"timestampUtc": began, "finishedUtc": utc(), "command": args,
                         "stdout": raw, "result": value, "sha256": hashlib.sha256(raw.encode()).hexdigest()})
    lease = control.guard(False)
    if lease["toolCallsUsed"] % 25 == 0 or mutation:
        checkpoint(label, "restoring" if RESTORING else "running", "bounded capture / authorized restore")
    return value


def az_batch(commands):
    lease = control.guard(False)
    if not RESTORING:
        control.guard(True)
    timeout = 300
    if RESTORE_DEADLINE is not None:
        timeout = min(timeout, RESTORE_DEADLINE - time.monotonic())
        if timeout <= 0:
            raise RuntimeError("Absolute restore deadline reached")
    began = utc()
    values = control.az_batch([(args, "aspath-" + label) for args, label in commands],
                              timeout=timeout, closure=True)
    for (args, label), value in zip(commands, values):
        raw = (control.RUNTIME / f"aspath-{label}.stdout.json").read_text(encoding="utf-8-sig")
        save(label + ".json", {"timestampUtc": began, "finishedUtc": utc(), "command": args,
                              "stdout": raw, "result": value,
                              "sha256": hashlib.sha256(raw.encode()).hexdigest()})
    if lease.get("toolCallsUsed", 0) // 25 != control.guard(False)["toolCallsUsed"] // 25:
        checkpoint("parallel reads", "running", "bounded capture / authorized restore")
    return values


def network_url(kind, name):
    return f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{control.RG}/providers/Microsoft.Network/{kind}/{name}"


def rest(url, label, query=None):
    path = control.RUNTIME / "aspath-query.json"
    control.save(path, query or {"api-version": "2024-05-01"})
    return az(["rest", "--method", "get", "--url", url, "--url-parameters", "@" + str(path)], label)


def hub_resource(value):
    result = {k: copy.deepcopy(value[k]) for k in ("name", "location", "tags") if k in value}
    result.update(type="Microsoft.Network/virtualHubs", apiVersion="2024-05-01")
    result["properties"] = copy.deepcopy(value["properties"])
    for key in ("provisioningState", "routingState", "virtualRouterIps", "virtualRouterAsn"):
        result["properties"].pop(key, None)
    result["properties"]["hubRoutingPreference"] = "ASPath"
    return result


def submit(document, params, label, mutation=False):
    template = control.RUNTIME / f"aspath-{label}-template.json"
    parameters = control.RUNTIME / f"aspath-{label}-parameters.json"
    control.save(template, document)
    control.save(parameters, params)
    return az(["deployment", "group", "create", "-g", control.RG, "--name", "aspath-" + label,
               "--template-file", str(template), "--parameters", "@" + str(parameters)], label, mutation)


def modify_script(count, withdraw_cn=False):
    replacement = FILTER.replace("then accept;", "then {\n" +
                                 "".join("    bgp_path.prepend(65013);\n" for _ in range(count)) +
                                 "    accept;\n  }")
    if withdraw_cn:
        replacement = replacement.replace("filter azure_export {\n",
                                          "filter azure_export {\n  if net = 10.140.0.0/24 then reject;\n")
    return f"""python3 - <<'PY'
from pathlib import Path
base = Path('{BACKUP}').read_text()
old = {FILTER!r}
assert base.count(old) == 1, 'Baseline export filter differs'
assert base.count('export filter azure_export;') == 2, 'Both peers must share the filter'
assert 'bgp_path.prepend' not in base, 'Baseline is not zero prepend'
Path('/var/lib/threehub/aspath-jp-candidate.conf').write_text(base.replace(old, {replacement!r}))
PY
bird -p -c /var/lib/threehub/aspath-jp-candidate.conf
cp -p {BACKUP} /etc/bird/bird.conf.aspath-next
cat /var/lib/threehub/aspath-jp-candidate.conf > /etc/bird/bird.conf.aspath-next
mv -f /etc/bird/bird.conf.aspath-next /etc/bird/bird.conf
configured=$(birdc configure)
printf '%s\\n' "$configured"
printf '%s\\n' "$configured" | grep -q '^Reconfigured'
"""


def export_script(peer, action=""):
    return f"""#!/bin/bash
set -euo pipefail
exec 2>&1
{action}
echo SOURCE_BEGIN
date -u +%FT%TZ
sha256sum /etc/bird/bird.conf {BACKUP}
birdc show protocols
echo EXPORT_BEGIN
birdc show route export azure_{peer} all
echo EXPORT_END
echo SOURCE_END
"""


def source(label, count=None, initialize=False, restore=False, withdraw_cn=False):
    action = ""
    if initialize:
        action = f"""
python3 - <<'PY'
from pathlib import Path
import hashlib
t = Path('/etc/bird/bird.conf').read_text()
assert t.count({FILTER!r}) == 1 and t.count('export filter azure_export;') == 2
assert 'bgp_path.prepend' not in t
assert hashlib.sha256(Path('/etc/bird/bird.conf').read_bytes()).hexdigest() == {BASELINE_HASH!r}
backup = Path('{BACKUP}')
if backup.exists():
    assert backup.read_bytes() == Path('/etc/bird/bird.conf').read_bytes(), 'Existing backup differs'
PY
if test ! -e {BACKUP}; then cp -p /etc/bird/bird.conf {BACKUP}; fi
"""
    elif restore:
        action = f"""bird -p -c {BACKUP}
cp -p {BACKUP} /etc/bird/bird.conf.aspath-next
mv -f /etc/bird/bird.conf.aspath-next /etc/bird/bird.conf
configured=$(birdc configure)
printf '%s\\n' "$configured"
printf '%s\\n' "$configured" | grep -q '^Reconfigured'
cmp -s {BACKUP} /etc/bird/bird.conf
"""
    elif count is not None:
        action = modify_script(count, withdraw_cn)
    command_label = "boundary-before" if REUSE_COMMANDS else label
    document, params = guest.managed_template({"router-jp": export_script(0, action)}, "aspath-" + command_label + "-a")
    first = document["resources"][0]
    first["properties"]["timeoutInSeconds"] = 120
    second = copy.deepcopy(first)
    second["name"] = "router-jp/guest-aspath-" + command_label + "-b"
    vm, command = first["name"].split("/")
    second["dependsOn"] = [f"[resourceId('Microsoft.Compute/virtualMachines/runCommands', '{vm}', '{command}')]"]
    second["properties"]["source"]["script"] = "[parameters('peer1')]"
    document["resources"].append(second)
    document["parameters"]["peer1"] = {"type": "secureString"}
    params["parameters"]["peer1"] = {"value": export_script(1)}
    submit(document, params, "source-" + label, count is not None or restore)
    outputs = []
    for index, resource in enumerate(document["resources"]):
        response = rest(f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{control.RG}"
                        f"/providers/Microsoft.Compute/virtualMachines/{resource['name'].split('/')[0]}"
                        f"/runCommands/{resource['name'].split('/')[1]}", f"source-{label}-peer{index}",
                        {"api-version": "2024-03-01", "$expand": "instanceView"})
        view = response.get("properties", {}).get("instanceView", {})
        text = view.get("output", "")
        save(f"bird-export-peer{index}.txt", text)
        if view.get("exitCode") != 0 or view.get("executionState") != "Succeeded" or "SOURCE_END" not in text:
            raise RuntimeError(f"{label}: incomplete source output or guest failure")
        outputs.append(text)
    a, b = [x.split("EXPORT_BEGIN\n", 1)[1].split("EXPORT_END", 1)[0] for x in outputs]
    # Ignore only the BIRD banner; all route blocks/path attributes must match.
    if a.splitlines()[1:] != b.splitlines()[1:]:
        raise RuntimeError("Azure peers have different export route blocks")
    exported = {}
    prefix = None
    for line in a.splitlines():
        match = re.match(r"(10\.\d+\.0\.0/24)\s", line)
        if match:
            prefix = match.group(1)
            exported[prefix] = ""
        if "BGP.as_path:" in line and prefix:
            exported[prefix] = line.split("BGP.as_path:", 1)[1].strip()
    expected_prefixes = set(PREFIXES) - ({"10.140.0.0/24"} if withdraw_cn else set())
    if set(exported) != expected_prefixes:
        raise RuntimeError("Source export differs from the exact approved DC prefix set")
    if initialize:
        SOURCE_BASE.update(exported)
    else:
        expected = {prefix: " ".join(["65013"] * (count or 0) + path.split())
                    for prefix, path in SOURCE_BASE.items() if prefix in expected_prefixes}
        if exported != expected:
            raise RuntimeError(f"Actual BIRD AS paths differ from {count or 0} additional prepends")
    save("source-path-verification.json", {"additionalPrepends": count or 0, "paths": exported,
                                          "bothPeersIdentical": True, "withdrawCN": withdraw_cn,
                                          "noEdgeASNInvented": True})
    return outputs


def protocols(label):
    sources = {}
    for site in (*SITES, "cn"):
        sources["router-" + site] = """#!/bin/bash
set -euo pipefail
echo PROOF_BEGIN
sha256sum /etc/bird/bird.conf
birdc show protocols
""" + ("swanctl --list-sas | grep -E 'ESTABLISHED|INSTALLED'\n" if site == "jp" else "") + "echo PROOF_END\n"
    document, params = guest.managed_template(sources, "aspath-proof-" + ("boundary-before" if REUSE_COMMANDS else label))
    for resource in document["resources"]:
        resource["properties"]["timeoutInSeconds"] = 120
    submit(document, params, "protocols-" + label)
    proofs = {}
    for resource in document["resources"]:
        name, command = resource["name"].split("/")
        response = rest(f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{control.RG}"
                        f"/providers/Microsoft.Compute/virtualMachines/{name}/runCommands/{command}",
                        f"protocols-{label}-{name}", {"api-version": "2024-03-01", "$expand": "instanceView"})
        view = response.get("properties", {}).get("instanceView", {})
        text = view.get("output", "")
        save(name + "-protocols.txt", text)
        expected = 3 if name == "router-cn" else 5
        established = len(re.findall(r"^(?:mesh_\S+|azure_\S+)\s+BGP\s+\S+\s+up\s+\S+\s+Established", text, re.M))
        if "PROOF_END" not in text or view.get("exitCode") != 0 or established != expected:
            raise RuntimeError(f"{name}: BGP proof incomplete: {established}/{expected}")
        proofs[name] = {"established": established, "sha256": re.search(r"([a-f0-9]{64})\s+/etc/bird/bird.conf", text).group(1)}
        if name == "router-jp":
            proofs[name]["ikeEstablished"] = len(re.findall(r"ESTABLISHED", text))
            if proofs[name]["ikeEstablished"] != 2:
                raise RuntimeError("JP must retain both Established IKE SAs")
    save("protocol-proof.json", proofs)
    return proofs


def normalize(value, site):
    rows = []
    for entry in value["value"]:
        for prefix in entry.get("addressPrefixes", []):
            if prefix in PREFIXES:
                rows.append({"observer": site, "prefix": prefix, "asPath": entry.get("asPath"),
                             "origin": entry.get("routeOrigin"), "nextHopType": entry.get("nextHopType"),
                             "nextHops": entry.get("nextHops")})
    return sorted(rows, key=lambda x: x["prefix"])


def complete_rows(rows, withdraw_cn=False):
    for site in SITES:
        actual = [r["prefix"] for r in rows if r["observer"] == site]
        expected = set(PREFIXES)
        if withdraw_cn and site == "jp" and "10.140.0.0/24" not in actual:
            expected.remove("10.140.0.0/24")
        if len(actual) != len(expected) or set(actual) != expected:
            return False
    return len(rows) in ((11, 12) if withdraw_cn else (12,))


def reserve_restore(lease, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    reserve = dt.timedelta(minutes=lease["restoreTimeoutMinutes"], seconds=600)
    if now + reserve >= expiry:
        raise RuntimeError("Budget reserve: insufficient time for one bounded step plus complete restore")


def bounded_wait(seconds):
    if RESTORE_DEADLINE is not None and time.monotonic() + seconds >= RESTORE_DEADLINE:
        raise RuntimeError("Restore deadline cannot accommodate paired snapshots")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        control.guard(False)
        time.sleep(min(10, deadline - time.monotonic()))


def hub_metadata(preference="ASPath", routing_intent=False):
    observed = {}
    for site in SITES:
        hub = rest(network_url("virtualHubs", "hub-" + site), "hub-" + site + "-actual")
        intent = rest(network_url("virtualHubs", f"hub-{site}/routingIntent"), "ri-" + site + "-actual")
        properties = hub.get("properties")
        intents = intent.get("value")
        observed[site] = {"hub": hub, "routingIntentResponse": intent,
                          "observedHubRoutingPreference": (properties or {}).get("hubRoutingPreference"),
                          "observedRoutingIntent": intents}
    save("hub-metadata.json", {"timestampUtc": utc(), "observed": observed,
                               "expected": {"hubRoutingPreference": preference,
                                            "routingIntentEnabled": routing_intent}})
    if any(x["observedHubRoutingPreference"] != preference or
           (not isinstance(x["observedRoutingIntent"], list)) or
           bool(x["observedRoutingIntent"]) != routing_intent
           for x in observed.values()):
        raise RuntimeError("Actual hub GET preference/intent differs from expected state")
    if routing_intent:
        for site, value in observed.items():
            entries = value["observedRoutingIntent"]
            policies = entries[0].get("properties", {}).get("routingPolicies", []) if len(entries) == 1 else []
            expected = (f"/subscriptions/{SUB}/resourceGroups/{control.RG}"
                        f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")
            if (len(policies) != 1 or policies[0].get("destinations") != ["PrivateTraffic"] or
                    policies[0].get("nextHop", "").lower() != expected.lower()):
                raise RuntimeError(f"{site}: actual RI does not match expected private firewall next hop")
    return observed


def capture(label, count, withdraw_cn=False, ingress="JP", preference="ASPath",
            firewall_ids=None, parallel=False):
    global CURRENT
    CURRENT = OUT / label
    CURRENT.mkdir(parents=True, exist_ok=True)
    metadata = (hub_metadata() if preference == "ASPath" and firewall_ids is None
                else hub_metadata(preference, firewall_ids is not None))
    save("manifest.json", {"timestampUtc": utc(), "observedHubMetadata": metadata,
                           "expectedHRP": preference, "expectedRoutingIntentEnabled": firewall_ids is not None,
                           "withdrawCN": withdraw_cn,
                           "additionalASN": count, "ingress": ingress, "prefixes": PREFIXES,
                           "source": "firewall effectiveRoutes" if firewall_ids is not None
                           else "spoke-connection effectiveRoutes"})
    def snapshot(number):
        result = []
        if parallel:
            commands = [
                (effective_routes.arguments(SUB, control.RG, site,
                                            firewall_id=firewall_ids[site] if firewall_ids else None),
                 f"effective-{site}-snapshot{number}") for site in SITES]
            values = az_batch(commands)
            for site, value in zip(SITES, values):
                if not isinstance(value, dict) or not isinstance(value.get("value"), list):
                    raise RuntimeError(f"{site}: missing completed effectiveRoutes response")
                result.extend(normalize(value, site))
            save(f"winners-snapshot{number}.json", result)
            return result
        for site in SITES:
            kwargs = {"firewall_id": firewall_ids[site]} if firewall_ids is not None else {}
            value = effective_routes.collect(az, SUB, control.RG, site,
                                             f"effective-{site}-snapshot{number}", **kwargs)
            result.extend(normalize(value, site))
        save(f"winners-snapshot{number}.json", result)
        return result
    first, second = effective_routes.two_snapshots(snapshot, wait=bounded_wait)
    complete = complete_rows(first, withdraw_cn) and complete_rows(second, withdraw_cn)
    stable = first == second
    verdict = "PASS" if complete and stable else "INCONCLUSIVE"
    save("analysis.json", {"verdict": verdict, "complete12": complete, "stable": stable,
                           "minimumSnapshotSpacingSeconds": 120,
                           "defaultTablesSkipped": "Not decisive; provider queries previously stalled",
                           "rows": second, "noDataPlaneClaim": True})
    print(f"STEP {label}: {verdict}; 12rows={complete}; stable={stable}; evidence={CURRENT}", flush=True)
    return {"count": count, "verdict": verdict, "rows": second, "stable": stable,
            "withdrawCN": withdraw_cn}


def summarize(results):
    table = []
    for site in SITES:
        for prefix in PREFIXES:
            sequence = []
            for result in results:
                matches = [r for r in result["rows"] if r["observer"] == site and r["prefix"] == prefix]
                sequence.append({"count": result["count"], "stable": result["stable"],
                                 "winner": matches[0] if len(matches) == 1 else None})
            baseline = sequence[0]["winner"] if sequence else None
            switches = [x["count"] for x in sequence[1:] if baseline and x["winner"] and
                        (x["winner"]["nextHopType"], x["winner"]["nextHops"], x["winner"]["origin"]) !=
                        (baseline["nextHopType"], baseline["nextHops"], baseline["origin"])]
            table.append({"observer": site, "prefix": prefix, "firstObservedSwitch": min(switches) if switches else None,
                          "boundedNoSwitchThrough": max(x["count"] for x in sequence) if sequence and not switches else None,
                          "sequence": sequence})
    return table


def main():
    global SUB, CURRENT, RESTORING, RESTORE_DEADLINE
    control.LEASE = control.RUNTIME / "aspath-jp-sweep-lease.json"
    lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
    lease.setdefault("startedAtUtc", lease["lastCheckpointUtc"])
    lease.setdefault("toolCallsUsed", 0)
    lease.setdefault("mutationsUsed", 0)
    control.save(control.LEASE, lease)
    SUB = control.account_id()
    if OUT.exists():
        raise RuntimeError("New evidence directory required; refusing replay")
    OUT.mkdir(parents=True)
    CURRENT = OUT / "preflight"
    checkpoint("start", "running", "backup/export proof then one hub ARM batch")
    results, errors, original_hash, restored_hash, changed = [], [], None, None, False
    before_protocols, after_protocols = {}, {}
    try:
        outputs = source("before", initialize=True)
        original_hash = re.search(r"([a-f0-9]{64})\s+/etc/bird/bird.conf", outputs[0]).group(1)
        before_protocols = protocols("before")
        hubs = {site: rest(network_url("virtualHubs", "hub-" + site), "hub-" + site + "-before") for site in SITES}
        for site in SITES:
            intent = rest(network_url("virtualHubs", f"hub-{site}/routingIntent"), "ri-" + site)
            if intent.get("value"):
                raise RuntimeError("Routing intent is present")
        submit(infra.template([hub_resource(hubs[s]) for s in SITES]), {"parameters": {}}, "all-hubs-aspath", True)
        for site in SITES:
            current = rest(network_url("virtualHubs", "hub-" + site), "hub-" + site + "-aspath")
            if current["properties"].get("hubRoutingPreference") != "ASPath":
                raise RuntimeError("Hub preference not applied")
        CURRENT = OUT / "0"
        source("zero")
        results.append(capture("0", 0))
        for count in range(1, 5):
            reserve_restore(control.guard(True))
            CURRENT = OUT / str(count)
            changed = True
            source(str(count), count=count)
            results.append(capture(str(count), count))
        checkpoint("80% mutations", "restoring", "exact-file JP restore only")
    except Exception as exc:
        errors.append(str(exc))
        print(f"STEP ERROR: INCONCLUSIVE {type(exc).__name__}: {exc}", flush=True)
    finally:
        RESTORING = True
        CURRENT = OUT / "restore0"
        if changed:
            restore_started = time.monotonic()
            RESTORE_DEADLINE = restore_started + 900
            try:
                outputs = source("restore", restore=True)
                restored_hash = re.search(r"([a-f0-9]{64})\s+/etc/bird/bird.conf", outputs[0]).group(1)
                if restored_hash != original_hash:
                    raise RuntimeError("Restore hash differs")
                restored = capture("restore0", 0)
                after_protocols = protocols("after")
                if before_protocols != after_protocols:
                    raise RuntimeError("Router file/protocol proof changed after restore")
                if not restored["stable"] or not complete_rows(restored["rows"]):
                    raise RuntimeError("Restored routes missing/unstable")
                if time.monotonic() - restore_started > 900:
                    raise RuntimeError("Restore exceeded 15 minutes")
            except Exception as exc:
                errors.append("RESTORE: " + str(exc))
        CURRENT = OUT
        lease = json.loads(control.LEASE.read_text())
        restored_ok = not changed or restored_hash == original_hash and not any(e.startswith("RESTORE:") for e in errors)
        verdict = "PASS" if len(results) == 5 and all(x["verdict"] == "PASS" for x in results) and restored_ok and not errors else "INCONCLUSIVE" if restored_ok else "BLOCKED"
        summary = {"timestampUtc": utc(), "verdict": verdict, "completedCounts": [r["count"] for r in results],
                   "HRP": "ASPath", "routingIntent": False, "mutationsUsed": lease["mutationsUsed"],
                   "callsUsed": lease["toolCallsUsed"], "originalHash": original_hash, "restoredHash": restored_hash,
                   "restored": restored_ok, "errors": errors, "thresholds": summarize(results), "children": [],
                   "budgetStopReason": lease.get("failure"),
                   "protocolProofBefore": before_protocols, "protocolProofAfter": after_protocols,
                   "forwarding": "B0 10/24 FAIL remains separate; no forwarding test or repair performed",
                   "losingAzurePaths": "Not exposed by effectiveRoutes; BIRD export evidence is source evidence only"}
        save("sweep-verdict.json", summary)
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored_ok else "blocked",
                     verdict=verdict, completedAtUtc=utc(), originalHash=original_hash, restoredHash=restored_hash,
                     children=[], evidence=str(OUT.relative_to(control.ROOT.parent)))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} counts={summary['completedCounts']} mutations={lease['mutationsUsed']} "
              f"restored={restored_ok} evidence={OUT}", flush=True)


def winning_identity(row):
    return row["nextHopType"], row["nextHops"], row["origin"]


def switched(baseline, candidate):
    old = {(r["observer"], r["prefix"]): winning_identity(r) for r in baseline["rows"]}
    return [r for r in candidate["rows"] if old.get((r["observer"], r["prefix"])) != winning_identity(r)]


def boundary_main():
    global OUT, CURRENT, SUB, RESTORING, RESTORE_DEADLINE, REUSE_COMMANDS
    control.LEASE = control.RUNTIME / "verified-aspath-boundary-lease.json"
    lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
    if (lease["taskId"] != "vwan-three-hub-verified-japan-boundary-20261014"
            or lease["ownerRole"] != "Trinity" or lease["state"] != "active"
            or lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0)):
        raise RuntimeError("Fresh accepted Trinity boundary lease required; no replay")
    lease.setdefault("startedAtUtc", lease["lastCheckpointUtc"])
    lease.update(toolCallsUsed=0, mutationsUsed=0)
    control.save(control.LEASE, lease)
    control.guard(True)
    REUSE_COMMANDS = True
    SUB = control.account_id()
    OUT = control.ROOT.parent / "show-output" / "verified-aspath-jp-boundary"
    if OUT.exists():
        raise RuntimeError("New boundary evidence directory required")
    OUT.mkdir(parents=True)
    CURRENT = OUT / "preflight"
    CURRENT.mkdir()
    checkpoint("start", "running", "fresh baseline metadata/source/all-router proof")
    results, errors, before, after = [], [], {}, {}
    dirty, restored_ok, eligibility, threshold = False, False, None, None
    baseline = None

    def apply_count(count):
        nonlocal dirty
        global CURRENT
        reserve_restore(control.guard(True))
        CURRENT = OUT / str(count)
        dirty = True
        source(str(count), count=count)
        result = capture(str(count), count)
        results.append(result)
        if result["verdict"] != "PASS":
            raise RuntimeError(f"Count {count}: incomplete or unstable effective winners")
        return result

    def restore(label):
        nonlocal dirty, restored_ok
        global CURRENT, RESTORING, RESTORE_DEADLINE
        RESTORING = True
        RESTORE_DEADLINE = time.monotonic() + 900
        CURRENT = OUT / label
        outputs = source(label, restore=True)
        actual = re.search(r"([a-f0-9]{64})\s+/etc/bird/bird.conf", outputs[0]).group(1)
        if actual != BASELINE_HASH:
            raise RuntimeError("Exact JP restore hash differs")
        dirty = False
        restored_ok = False
        result = capture(label, 0)
        if result["verdict"] != "PASS" or result["rows"] != baseline["rows"]:
            restored_ok = False
            raise RuntimeError("Restored effective winner/path matrix differs from fresh baseline")
        restored_ok = True
        RESTORING, RESTORE_DEADLINE = False, None
        return result

    try:
        source("boundary-before", initialize=True)
        before = protocols("boundary-before")
        baseline = capture("0", 0)
        results.append(baseline)
        if baseline["verdict"] != "PASS":
            raise RuntimeError("Fresh baseline route matrix incomplete or unstable")
        four = apply_count(4)
        eight = apply_count(8)
        changes = switched(baseline, eight)
        print(f"VERDICT boundary: {'SWITCH' if changes else 'NO_SWITCH_THROUGH_8'}; "
              f"actual all-hub ASPath/no-RI GET proof; evidence={OUT}", flush=True)
        if changes and not switched(baseline, four):
            middle = apply_count(6)
            if switched(baseline, middle):
                fifth = apply_count(5)
                threshold = 5 if switched(baseline, fifth) else 6
            else:
                seventh = apply_count(7)
                threshold = 7 if switched(baseline, seventh) else 8
            print(f"VERDICT first observed integer winner boundary={threshold} "
                  "(monotonicity within sampled bracket assumed)", flush=True)
        restore("restore0")
        if not changes:
            reserve_restore(control.guard(True))
            CURRENT = OUT / "withdraw-cn"
            dirty, restored_ok = True, False
            source("withdraw-cn", count=0, withdraw_cn=True)
            withdrawal = capture("withdraw-cn", 0, withdraw_cn=True)
            jp_cn = [r for r in withdrawal["rows"]
                     if r["observer"] == "jp" and r["prefix"] == "10.140.0.0/24"]
            eligibility = {"verdict": withdrawal["verdict"], "jpCNWinner": jp_cn,
                           "remoteCandidateObserved": bool(jp_cn),
                           "interpretation": ("Remote CN winning route is eligible after JP Azure-only withdrawal"
                                              if jp_cn else "CN route absent at JP after Azure-only withdrawal; no eligible remote winner observed"),
                           "notProofOfHiddenLosingCandidates": True}
            save("candidate-verdict.json", eligibility)
            print(f"VERDICT CN eligibility: {eligibility['interpretation']}; "
                  f"stable={withdrawal['stable']}; evidence={CURRENT}", flush=True)
            if withdrawal["verdict"] != "PASS":
                raise RuntimeError("CN withdrawal paired matrix incomplete/unstable")
            checkpoint("80% mutations", "restoring", "exact original JP export restore only")
            restore("restore-final")
        RESTORING = True
        RESTORE_DEADLINE = time.monotonic() + 900
        CURRENT = OUT / "closure"
        after = protocols("boundary-after")
        if before != after:
            restored_ok = False
            raise RuntimeError("Four router hashes/BGP/IKE proof differs from baseline")
    except Exception as exc:
        errors.append(str(exc))
        print(f"VERDICT INCONCLUSIVE: {exc}; restoring only", flush=True)
    finally:
        if dirty:
            try:
                restore("restore-error")
                RESTORING = True
                CURRENT = OUT / "closure"
                after = protocols("boundary-after-error")
                if before != after:
                    restored_ok = False
                    raise RuntimeError("Closure router proof differs")
            except Exception as exc:
                restored_ok = False
                errors.append("RESTORE: " + str(exc))
        CURRENT = OUT
        lease = json.loads(control.LEASE.read_text())
        restored_ok = restored_ok and bool(before) and before == after
        verdict = "PASS" if restored_ok and not errors else "INCONCLUSIVE" if restored_ok else "BLOCKED"
        summary = {"timestampUtc": utc(), "verdict": verdict, "completedCounts": [r["count"] for r in results],
                   "mutationsUsed": lease["mutationsUsed"], "callsUsed": lease["toolCallsUsed"],
                   "restored": restored_ok, "originalHash": BASELINE_HASH,
                   "restoredHash": after.get("router-jp", {}).get("sha256"),
                   "actualHRPProof": "Each state hub-metadata.json contains all three full live hub GETs and RI GETs; expected values separately asserted",
                   "thresholds": summarize(results), "firstIntegerBoundary": threshold,
                   "candidateVisibility": eligibility, "protocolProofBefore": before, "protocolProofAfter": after,
                   "errors": errors, "children": [], "noDataPlaneClaim": True,
                   "historicalEvidence": "Unchanged; old per-step metadata rejection remains valid"}
        save("sweep-verdict.json", summary)
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored_ok else "blocked",
                     verdict=verdict, completedAtUtc=utc(), children=[], evidence=str(OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} counts={summary['completedCounts']} calls={lease['toolCallsUsed']}/150 "
              f"mutations={lease['mutationsUsed']}/6 restored={restored_ok} evidence={OUT}", flush=True)


if __name__ == "__main__":
    import sys
    boundary_main() if "--boundary" in sys.argv else main()
