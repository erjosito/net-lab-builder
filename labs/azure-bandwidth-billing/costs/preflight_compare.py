"""One bounded read-only preflight per invocation; no authentication changes."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

import cost_api as api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=["windows", "wsl"], required=True)
    parser.add_argument("--variant", choices=["rg-only", "legacy-date", "modern-date"],
                        default="rg-only")
    parser.add_argument("--literal-keys", action="store_true")
    parser.add_argument("--readiness", action="store_true")
    parser.add_argument("--start", default="2099-01-01")
    parser.add_argument("--output", required=True)
    parser.add_argument("--distribution", default="Ubuntu-24.04")
    args = parser.parse_args()
    try:
        lease_path = api.LAB / "deploy" / ".runtime-control" / "api-lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8-sig"))
        if ((lease_path.parent / "STOP").exists() or lease["state"] != "active" or
                dt.datetime.now(dt.timezone.utc) >=
                dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))):
            raise api.Failure("lease_inactive")
        output = api.private_path(args.output)
        if output.exists():
            raise api.Failure("snapshot_already_exists")
        if args.environment == "wsl" and os.name == "nt":
            forwarded = sys.argv[1:]
            index = forwarded.index("--output") + 1
            forwarded[index] = api.linux_path(str(output))
            command = ["wsl.exe", "-d", args.distribution, "--exec", "timeout", "--signal=TERM",
                       "--kill-after=3s", "100s", "python3", api.linux_path(str(Path(__file__).resolve()))]
            result = api.run_bounded(command + forwarded, 110)
            print(json.dumps(json.loads(result.stdout)))
            return result.returncode
        if args.environment == "windows":
            context = json.loads((api.LAB / "private" / "context.private.json").read_text(
                encoding="utf-8-sig"))
            sub, tenant = context["subscriptionId"], context["expectedTenantId"]
        else:
            # Discovery only; every subsequent command is pinned to these exact values.
            account = api.cli_json(["account", "show"])
            sub, tenant = account["id"], account["tenantId"]
            windows = json.loads((api.LAB / "private" / "context.private.json").read_text(
                encoding="utf-8-sig"))
            if sub.lower() == windows["subscriptionId"].lower() or tenant.lower() == windows[
                    "expectedTenantId"].lower():
                raise api.Failure("cross_tenant_context_not_distinct")
            context_file = api.LAB / "private" / "wsl-cost-context.private.json"
            if not context_file.exists():
                with context_file.open("x", encoding="utf-8") as stream:
                    json.dump({"subscriptionId": sub, "expectedTenantId": tenant}, stream)
        if args.readiness:
            transport = api.Transport(sub, tenant)
            transport.guard = api.assert_lease
            transport.authorize()
            results = {}
            for namespace in ["Microsoft.Compute", "Microsoft.Network"]:
                provider = api.cli_json(["provider", "show", "--namespace", namespace,
                                         "--subscription", sub], 15)
                results[namespace] = provider.get("registrationState")
            skus = api.cli_json(["vm", "list-skus", "--location", "swedencentral",
                                 "--resource-type", "virtualMachines", "--size", "Standard_B",
                                 "--all", "--subscription", sub], 25)
            ladder = []
            for name in ["Standard_B1s", "Standard_B2ts_v2"]:
                matches = [sku for sku in skus if sku.get("name") == name]
                ladder.append({"sku": name, "catalogPresent": bool(matches),
                               "restrictions": [restriction.get("reasonCode") for sku in matches
                                                for restriction in sku.get("restrictions", [])]})
            data = {"environment": args.environment, "tenantDistinctFromWindows": args.environment == "wsl",
                    "providers": results, "region": "swedencentral", "catalog": ladder,
                    "liveCapacity": "NOT_TESTED", "quota": "NOT_TESTED", "mutations": 0}
        else:
            # Future dates are deliberate negative controls, never a broad bill enumeration.
            command = ["probe", "--subscription", sub, "--expected-tenant", tenant,
                       "--start", args.start, "--end", args.start,
                       "--filter-variant", args.variant, "--max-seconds", "75",
                       "--offer-alias", "windows-main" if args.environment == "windows" else "wsl-msdn",
                       "--output", str(output)]
            if args.literal_keys:
                command.append("--literal-keys")
            return api.main(command)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        print(json.dumps(data))
        return 0
    except api.Failure as error:
        print(json.dumps({"state": "ERROR", "code": error.code}))
        return 2
    except Exception:
        print(json.dumps({"state": "ERROR", "code": "preflight_failed_no_raw_error"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
