"""Independently verify the preserved user baseline after a design experiment."""
import argparse
import json

import aspath_sweep as sweep
import control
import design_comparison as comparison
import design_snapshot as snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(False)
    if lease.get("toolCallsUsed", 0) or lease["maxMutations"] != 0:
        raise RuntimeError("Fresh independent read-only lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    before = json.loads((control.ROOT.parent / "show-output" / args.baseline /
                         "baseline-verdict.json").read_text().replace("<SUBSCRIPTION_ID>", sweep.SUB))
    if before["verdict"] != "PASS":
        raise RuntimeError("Accepted baseline required")
    before = before["result"]
    sweep.RESTORING = True
    result, errors = {}, []
    try:
        result["hubs"] = snapshot.metadata("verify")
        if any(result["hubs"][s]["preference"] != before["hubs"][s]["preference"]
               for s in sweep.SITES):
            raise RuntimeError("Original per-hub HRPs differ")
        result["sources"] = snapshot.nvas("verify-source", source=True)
        if any(not comparison.source_unchanged(before["sources"][s], result["sources"][s])
               for s in snapshot.ALL_SITES):
            raise RuntimeError("Original guest source, metadata or sessions differ")
        result["firewalls"] = snapshot.firewall_routes("verify", result["hubs"])
        if result["firewalls"]["rows"] != before["firewalls"]["rows"]:
            raise RuntimeError("Original stable firewall winners differ")
    except Exception as exc:
        errors.append(str(exc))
    verdict = "PASS" if not errors else "BLOCKED"
    lease = json.loads(control.LEASE.read_text())
    sweep.save("verification-verdict.json", dict(verdict=verdict, errors=errors, result=result,
               timestampUtc=sweep.utc(), mutationsUsed=0, callsUsed=lease["toolCallsUsed"], children=[]))
    lease.update(state="completed" if not errors else "blocked", verdict=verdict,
                 completedAtUtc=sweep.utc(), children=[])
    control.save(control.LEASE, lease)
    print("FINAL " + verdict + " independent exact user baseline verification", flush=True)
    if errors:
        raise SystemExit("; ".join(errors))


if __name__ == "__main__":
    main()
