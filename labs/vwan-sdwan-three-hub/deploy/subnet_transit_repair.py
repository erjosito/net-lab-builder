"""Read-only subnet NSG discrimination; no repair without a proven denial.

Run ``inspect`` and then ``probes`` only under an active lease. ``close`` records
an inconclusive, mutation-free handoff from existing evidence without Azure calls.
"""
import argparse
import datetime as dt
import json

import control
import infra

OUT = control.ROOT.parent / "show-output" / "subnet-transit-repair"
LEASE = control.RUNTIME / "subnet-transit-repair-lease.json"
BASE = "https://management.azure.com"


def setup(closure=False):
    control.LEASE = LEASE
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    lease.setdefault("startedAtUtc", "2026-10-14T20:00:06Z")
    control.save(LEASE, lease)
    control.guard(not closure)
    OUT.mkdir(exist_ok=True)


def call(args, label, mutation=False, closure=False):
    result = control.az(args, "subnet-" + label, mutation=mutation,
                        timeout=600, closure=closure)
    text = json.dumps(result, indent=2).replace(control.account_id(), "<SUBSCRIPTION_ID>")
    (OUT / (label + ".json")).write_text(text + "\n", encoding="utf-8")
    control.save(OUT / (label + "-command.json"), {
        "timestampUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": ["az", *[arg.replace(control.account_id(), "<SUBSCRIPTION_ID>")
                            for arg in args]], "mutation": mutation})
    return result


def url(kind):
    return (f"{BASE}/subscriptions/{control.account_id()}/resourceGroups/"
            f"{control.RG}/providers/Microsoft.Network/{kind}?api-version={infra.API}")


def inspect():
    for kind, label in (("virtualNetworks", "before-vnets"),
                        ("networkSecurityGroups", "before-nsgs"),
                        ("networkInterfaces", "before-nics"),
                        ("routeTables", "before-route-tables")):
        call(["rest", "--method", "GET", "--url", url(kind)], label)
    for name in ("probe-dc-us", "router-us", "router-eu"):
        call(["network", "nic", "list-effective-nsg", "-g", control.RG,
              "-n", "nic-" + name], "before-effective-" + name)
    call(["network", "nic", "show-effective-route-table", "-g", control.RG,
          "-n", "nic-probe-dc-us"], "before-effective-routes-probe-dc-us")
    flow("before")


def flow(phase, closure=False):
    return call(["network", "watcher", "test-ip-flow", "-g", control.RG,
                 "--vm", "probe-dc-us", "--nic", "nic-probe-dc-us",
                 "--direction", "Outbound", "--protocol", "TCP",
                 "--local", "10.120.0.10:52000", "--remote", "10.10.0.10:5201"],
                phase + "-ip-flow", closure=closure)


def probes():
    pairs = [
        ("probe-dc-us", "10.120.0.10", ["10.10.0.10"]),
        ("probe-dc-eu", "10.110.0.10", ["10.20.0.10"]),
        ("router-cn", "10.140.0.4", ["10.20.0.10"]),
        ("probe-spoke-eu", "10.10.0.10", ["10.120.0.10"]),
        ("probe-spoke-us", "10.20.0.10", ["10.110.0.10", "10.140.0.4"]),
    ]
    for vm, source, destinations in pairs:
        script = ["#!/bin/sh", "date -u +%FT%TZ",
                  "systemctl is-active lab-http.service",
                  "curl -fsS --max-time 3 http://127.0.0.1:5201/"]
        for destination in destinations:
            script.extend([
                f"echo FLOW {source}:52000 {destination}:5201 TCP",
                f"ip route get {destination} from {source}",
                f"curl -sS -f --noproxy '*' --interface {source} --local-port 52000 "
                f"--connect-timeout 3 --max-time 5 http://{destination}:5201/",
                "echo TCP_EXIT=$?",
                f"ping -n -c 1 -W 2 -I {source} {destination}",
                "echo ICMP_EXIT=$?",
            ])
        script.append("exit 0")
        path = control.RUNTIME / ("subnet-before-probe-" + vm + ".sh")
        path.write_text("\n".join(script) + "\n", encoding="utf-8")
        result = call(["vm", "run-command", "invoke", "-g", control.RG, "-n", vm,
                       "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                      "before-probe-" + vm)
        print(json.dumps(result), flush=True)


def close():
    lease = control.guard(False)
    child = json.loads((control.RUNTIME / "child-process.json").read_text())
    if child["state"] != "terminated" or lease.get("mutationsUsed", 0):
        raise RuntimeError("This closure requires zero mutations and no live child")
    before = json.loads((OUT / "before-ip-flow.json").read_text())
    routes = json.loads((OUT / "before-effective-routes-probe-dc-us.json").read_text())
    vnets = json.loads((OUT / "before-vnets.json").read_text())["value"]
    nsgs = json.loads((OUT / "before-nsgs.json").read_text())["value"]
    scope = []
    for vnet in vnets:
        subnet = vnet["properties"]["subnets"][0]
        nsg_id = subnet["properties"]["networkSecurityGroup"]["id"]
        nsg = next(item for item in nsgs if item["id"].lower() == nsg_id.lower())
        associations = nsg["properties"].get("subnets", [])
        scope.append({
            "vnet": vnet["name"], "subnet": subnet["name"], "nsg": nsg["name"],
            "runTagMatches": vnet.get("tags") == control.TAGS and nsg.get("tags") == control.TAGS,
            "exclusiveTaskSubnet": len(associations) == 1
            and associations[0]["id"].lower() == subnet["id"].lower()
            and not nsg["properties"].get("networkInterfaces"),
            "systemCreatedAt": nsg.get("systemData", {}).get("createdAt"),
            "customRuleCount": len(nsg["properties"]["securityRules"]),
        })
    proof = {
        "timestampUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "taskId": lease["taskId"], "verdict": "INCONCLUSIVE", "state": "blocked",
        "flow": {"direction": "Outbound", "protocol": "TCP",
                 "source": "10.120.0.10:52000", "destination": "10.10.0.10:5201",
                 "result": before},
        "sourceUdr": [r for r in routes["value"] if "10.10.0.0/24" in r["addressPrefix"]],
        "scope": scope, "subnetNsgCount": len(scope),
        "missingProof": [
            "VirtualNetwork source/destination expansions absent in the three effective NSG responses",
            "systemData creation timestamps absent on all nine VNets and subnet NSGs",
            "No exact-flow subnet Deny rule observed",
        ],
        "failure": lease.get("failure"),
        "repairAuthorizedByEvidence": False,
        "azureCalls": lease.get("toolCallsUsed", 0), "mutations": 0,
        "forwardBeforeAfter": "Not run: lease blocked by failed raw-API read; B0 remains historical FAIL",
        "rollback": "Not required: no ARM submission or persistent guest writes",
        "baselinePreservation": "No hub, AS_PATH, BIRD, IPsec, WireGuard, route, NSG or policy writes",
        "children": [], "queuedWork": False,
    }
    control.save(OUT / "verdict.json", proof)
    label = "subnet-before-raw-effective-probe-dc-us"
    error = control.RUNTIME / (label + ".stderr.txt")
    if error.exists():
        (OUT / "raw-api-error.txt").write_text(
            error.read_text(encoding="utf-8", errors="replace")
            .replace(control.account_id(), "<SUBSCRIPTION_ID>"), encoding="utf-8")
    lease.update(state="blocked", verdict="INCONCLUSIVE", mutationsUsed=0,
                 closedAtUtc=proof["timestampUtc"], lastCheckpointUtc=proof["timestampUtc"],
                 childProcesses=[], queuedWork=False,
                 evidence=r"show-output\subnet-transit-repair\verdict.json")
    control.save(LEASE, lease)
    print(json.dumps(proof, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inspect", "probes", "close"))
    args = parser.parse_args()
    setup(closure=args.phase == "close")
    if args.phase == "inspect":
        inspect()
    elif args.phase == "probes":
        probes()
    else:
        close()


if __name__ == "__main__":
    main()
