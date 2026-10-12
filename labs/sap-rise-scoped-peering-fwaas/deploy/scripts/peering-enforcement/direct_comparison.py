"""New direct-isolation experiment after a reconciled startup timeout.

Both NVAs stay deallocated. Reuse only the proven source resources; never resume
or alter the blocked startup chain. Each phase requires its own coordinator lease.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import runner as core
from transport import Blocked, Lock, Transport, explicit_rejection, load, now, save

SEQUENCE = [
    "G4", "collect-subnet", "G7-add", "collect-vnetlocal", "G7-remove",
    "G8-add", "collect-vnetpeering", "G8-remove", "G10", "G11-add",
    "collect-full", "G11-remove", "G12", "collect-restored",
    "G13", "G14", "G15", "power-close", "verify",
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True, choices=SEQUENCE + ["collect-reconcile-rejection"])
    p.add_argument("--lease", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--prior", required=True)
    p.add_argument("--icmp-priority", type=int)
    p.add_argument("--plan", action="store_true")
    a = p.parse_args()
    out, prior = Path(a.out), Path(a.prior)
    lease = load(a.lease)
    original = load(prior / "originals.json")
    if a.phase == "collect-reconcile-rejection":
        state = load(out / "state.json")
        expected = SEQUENCE[:SEQUENCE.index("G8-add")]
        if (state["status"] != "blocked" or state["completed"] != expected
                or lease.get("acceptedCheckpoint") != "G7-remove"
                or lease.get("reconcilePhase") != "G8-add"):
            raise Blocked("Explicit one-time rejected-request reconciliation required")
        evidence = load(out / "G8-add" / "02-G8-add-route.json")
        if evidence.get("exitCode") != 1 or not explicit_rejection(evidence.get("stderr", "")):
            raise Blocked("No explicit service-side invalid next-hop rejection")
        lock = Lock(out / "experiment.lock")
        r = None
        try:
            r = Transport(a, state)
            net, _ = core.ids(lease["subscriptionId"])
            table = r.command("reconcile-source-table",
                              core.rest("get", net + "routeTables/" + core.SOURCE_TABLE))
            if core.props(table).get("routes"):
                raise Blocked("Trial route absence not proven")
            record = {"utc": now().isoformat(), "phase": "G8-add",
                      "outcome": "service-rejected-route-absent", "priorError": state["error"],
                      "lease": lease["taskId"], "writeReplayed": False}
            state.setdefault("reconciliations", []).append(record)
            save(out / "rejection-reconciliation.json", record)
            state["status"] = "active"
            state["completed"].append("G8-add")
            state["checkpoint"] = "G8-add"
            r.finish("completed")
        finally:
            lock.close()
        return
    if (out / "state.json").exists():
        state = load(out / "state.json")
    else:
        old = load(prior / "state.json")
        recovery = load(prior / "recovery-verification.json")
        if a.phase != "G4" or old["status"] != "blocked" or not recovery:
            raise Blocked("Require reconciled startup and explicit new experiment")
        state = {
            "startedAtUtc": old["startedAtUtc"], "subscriptionId": old["subscriptionId"],
            "calls": old["calls"] + 8, "mutations": old["mutations"],
            "completed": [], "status": "active", "prior": str(prior),
            "journal": [copy.deepcopy(e) for e in old["journal"]
                        if e["phase"] in ("G1", "G2") and e["status"] == "applied"],
        }
    if state["status"] != "active" or state["completed"] != SEQUENCE[:SEQUENCE.index(a.phase)]:
        raise Blocked("Wrong phase or blocked direct experiment")
    if lease.get("acceptedCheckpoint") != (state["completed"][-1] if state["completed"] else "recovery"):
        raise Blocked("Coordinator checkpoint acceptance missing")
    if state["subscriptionId"] != lease["subscriptionId"]:
        raise Blocked("Subscription changed")
    operations = []
    if a.phase == "power-close":
        _, compute = core.ids(lease["subscriptionId"])
        op = core.operation("power-close:workload", compute + "virtualMachines/vm-workload-probe",
                            {"power": "deallocated"}, before={"power": "running"},
                            compute=True, inverse=False)
        op.update(power=True, timeout=600,
                  argv=["vm", "deallocate", "-g", core.RG, "-n", "vm-workload-probe"])
        operations = [op]
    elif not a.phase.startswith("collect") and a.phase != "verify":
        operations = core.plan(a.phase, original, state, lease["subscriptionId"], priority=a.icmp_priority)
        if a.phase == "G4":
            operations = [op for op in operations if "nsg-spoke-nva/" not in op["id"]]
            if len(operations) != 2 or lease.get("icmpPriority") != a.icmp_priority:
                raise Blocked("Approve exactly the source and workload ICMP rules")
    if a.plan:
        print(json.dumps({"phase": a.phase, "allowedMutations":
            [x["label"] for op in operations for x in [op, *op["inverse"]]]}))
        return
    out.mkdir(parents=True, exist_ok=True)
    lock = Lock(out / "experiment.lock")
    r = None
    try:
        r = Transport(a, state)
        save(out / "originals.json", original)
        save(out / a.phase / "plan.json", operations)
        if a.phase == "verify":
            fresh = core.inventory(r)
            save(out / "final.json", fresh)
            core.verify_original_identities(original, fresh)
            if core.stable(original) != core.stable(fresh):
                raise Blocked("Original state comparison differs")
            save(out / "restore-verification.json",
                 {"status": "PASS", "utc": now().isoformat(), "remainingProcesses": []})
        elif a.phase.startswith("collect"):
            if a.phase in ("collect-subnet", "collect-full", "collect-restored"):
                core.check_direct_tables(r)
                core.check_scope(r)
            power = r.command("power-controls", ["vm", "list", "-g", core.RG, "--show-details"])
            for name in ("vm-hub-nva", "vm-spoke-nva", "vm-ce-onprem"):
                if core.named(power, name).get("powerState") != "VM deallocated":
                    raise Blocked("Direct comparison requires all three non-endpoints off")
            for name in ("vm-hub-test", "vm-workload-probe"):
                if core.named(power, name).get("powerState") != "VM running":
                    raise Blocked("Endpoint is not running")
            for nic, target, prefix in (
                ("nic-hub-test", "10.60.1.4", "10.60.0.0/16"),
                ("nic-workload-probe", "10.40.2.4", "10.40.0.0/16"),
            ):
                routes = r.command("routes-" + nic,
                    ["network", "nic", "show-effective-route-table", "-g", core.RG, "-n", nic])
                if routes.get("nextLink"):
                    raise Blocked("Unexpected pagination; preserve response and stop")
                if a.phase == "collect-full":
                    selected = core.selected_routes(routes, target)
                    if not selected or any(p != prefix or h.lower() != "vnetpeering"
                                           for p, h, _ in selected):
                        raise Blocked("Full-peering endpoint path is not direct")
            trial = {"collect-vnetlocal": "G7-add", "collect-vnetpeering": "G8-add"}.get(a.phase)
            rejected = trial and (
                any(e["phase"] == trial and e["status"] == "rejected" for e in state["journal"])
                or any(e["phase"] == trial and e["outcome"] == "service-rejected-route-absent"
                       for e in state.get("reconciliations", [])))
            if not rejected:
                command = ["bash", "-c",
                    "date -u; ip route get 10.60.1.4; timeout 10 ping -n -c 5 -W 1 10.60.1.4; "
                    "echo PING_STATUS=$?; if command -v mtr >/dev/null; then "
                    "timeout 18 mtr -n -r -c 5 --max-ttl 8 10.60.1.4; echo MTR_STATUS=$?; "
                    "else echo MTR_UNAVAILABLE; fi"]
                core.guest(r, "source-icmp", "vm-hub-test", core.guest_script(command, 30))
        else:
            core.execute(r, operations)
        state["completed"].append(a.phase)
        state["checkpoint"] = a.phase
        state["originalRestored"] = a.phase == "verify"
        if a.phase == "verify":
            state["status"] = "restored"
        r.finish("completed")
    except BaseException as exc:
        state["status"], state["error"] = "blocked", str(exc)
        save(out / "state.json", state)
        if r:
            r.finish("blocked")
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    main()
