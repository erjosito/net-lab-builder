"""Bounded overlay operations; secrets travel over SSH stdin, never argv."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

import run_terraform as runner

ROOT = runner.ROOT
CONTROL = runner.CONTROL
PROJECT = "gcp-vnbgp-20261124"
CPE = "cpe-vnbgp-20261124"
ZONE = "europe-north2-a"


def now():
    return datetime.now(timezone.utc).isoformat()


def record_mutations(count, operation):
    runner.check_lease()
    path = CONTROL / "lease.json"
    lease = json.loads(path.read_text())
    used = lease.get("completedMutations", 0)
    if used >= lease["maxMutations"] * .8 or used + count > lease["maxMutations"]:
        raise RuntimeError("Mutation budget/reserve reached.")
    lease["completedMutations"] = used + count
    lease["lastCheckpointUtc"] = now()
    lease.setdefault("operations", []).append({"at": now(), "operation": operation, "count": count})
    path.write_text(json.dumps(lease, indent=2) + "\n")


def checked_run(command, *, timeout=90, **kwargs):
    remaining = runner.check_lease()
    if timeout > remaining - 60:
        raise RuntimeError("Command would consume the lease closure reserve.")
    return runner.run(command, timeout=timeout, **kwargs)


def inventory():
    return json.loads((CONTROL / "overlay-inventory.json").read_text())


def ssh(script, *, timeout=120):
    sdk = Path(runner.gcloud_command()[0]).parent.parent
    serial = (CONTROL / "cpe-serial-current.txt").read_text()
    fingerprints = set(re.findall(
        r"(SHA256:[A-Za-z0-9+/]+) root@" + re.escape(CPE) + r" \(ED25519\)", serial,
    ))
    if len(fingerprints) != 1:
        raise RuntimeError("A unique authenticated serial-console SSH fingerprint is required.")
    proxy = subprocess.list2cmdline([
        str(sdk / "platform" / "bundledpython" / "python.exe"), "-S",
        str(sdk / "lib" / "gcloud.py"), "compute", "start-iap-tunnel", CPE, "%port",
        "--listen-on-stdin", f"--project={PROJECT}", f"--zone={ZONE}", "--verbosity=warning",
    ])
    command = [
        str(sdk / "bin" / "sdk" / "plink.exe"), "-T", "-batch",
        "-i", str(CONTROL / "cpe-key.ppk"), "-proxycmd", proxy,
        "-hostkey", fingerprints.pop(),
        f"azurelabuser@compute.{inventory()['cpe']['id']}", "sudo bash -s",
    ]
    return checked_run(command, timeout=timeout, input_text=script)


def vpn_psks():
    path = CONTROL / "overlay-secrets.json"
    if path.exists():
        return json.loads(path.read_text())
    names = json.loads(checked_run([
        "az.cmd", "network", "vpn-connection", "list",
        "--subscription", runner.SUBSCRIPTION_NAME, "-g", runner.LAB_GROUP,
        "--query", "[].name", "-o", "json",
    ]))
    values = {}
    for key in ["internet", "private"]:
        name = f"conn-{key}-vnbgp-20261124"
        if name in names:
            response = json.loads(checked_run([
                "az.cmd", "network", "vpn-connection", "shared-key", "show",
                "--subscription", runner.SUBSCRIPTION_NAME, "-g", runner.LAB_GROUP,
                "--connection-name", name, "-o", "json",
            ]))
            if not response.get("value"):
                raise RuntimeError(f"No shared key returned for existing {key} connection.")
            values[key] = response["value"]
        else:
            values[key] = secrets.token_hex(32)
    path.write_text(json.dumps(values), encoding="utf-8")
    return values


def terraform_env():
    env = os.environ.copy()
    account = json.loads(checked_run([
        "az.cmd", "account", "show", "--subscription", runner.SUBSCRIPTION_NAME, "-o", "json",
    ]))
    env["ARM_SUBSCRIPTION_ID"] = account["id"]
    env["ARM_TENANT_ID"] = account["tenantId"]
    env["GOOGLE_OAUTH_ACCESS_TOKEN"] = checked_run(
        runner.gcloud_command("auth", "print-access-token"),
    ).strip()
    billing = json.loads(checked_run(runner.gcloud_command(
        "billing", "accounts", "list", "--filter=open=true", "--format=json",
    )))
    if len(billing) != 1:
        raise RuntimeError("Expected one explicitly discoverable billing account.")
    env["TF_VAR_billing_account"] = billing[0]["name"].removeprefix("billingAccounts/")
    env["TF_VAR_ssh_public_key"] = checked_run([
        "az.cmd", "vm", "show", "--subscription", runner.SUBSCRIPTION_NAME,
        "-g", runner.LAB_GROUP, "-n", "probe-vnbgp-20261124",
        "--query", "osProfile.linuxConfiguration.ssh.publicKeys[0].keyData", "-o", "tsv",
    ]).strip()
    env["TF_VAR_vpn_psks"] = json.dumps(vpn_psks())
    return env


def checked_changes(detail, stage):
    if detail["variables"]["overlay_stage"]["value"] != stage:
        raise RuntimeError("Saved plan does not match the requested overlay stage.")
    changes = []
    for item in detail.get("resource_changes", []):
        change = item["change"]
        if change["actions"] == ["no-op"]:
            continue
        changes.append({"address": item["address"], "actions": change["actions"]})
        if not item["address"].startswith((
            "azurerm_local_network_gateway.cpe[",
            "azurerm_virtual_network_gateway_connection.overlay[",
        )):
            raise RuntimeError(f"Unexpected prerequisite change: {item['address']}")
        if item["address"].startswith("azurerm_virtual_network_gateway_connection.overlay["):
            before, after = change.get("before"), change.get("after")
            if before and after and before["shared_key"] != after["shared_key"]:
                raise RuntimeError("Existing VPN shared keys must not be rotated by this workflow.")
    runner.check_changes(changes)
    return changes


def plan(stage, retain_static=False):
    env = terraform_env()
    path = CONTROL / f"overlay-{stage}.tfplan"
    output = checked_run([
        "terraform", "plan", "-no-color", "-input=false", "-lock-timeout=30s",
        "-var=deploy_megaport=true", "-var=connect_expressroute=true",
        f"-var=overlay_stage={stage}", f"-out={path}",
        f"-var=retain_internet_static={'true' if retain_static else 'false'}",
        "-target=azurerm_local_network_gateway.cpe",
        "-target=azurerm_virtual_network_gateway_connection.overlay",
    ], env=env, timeout=300)
    (CONTROL / f"overlay-{stage}-plan.log").write_text(output, encoding="utf-8")
    detail = json.loads(checked_run(["terraform", "show", "-json", str(path)], env=env))
    changes = checked_changes(detail, stage)
    (CONTROL / f"overlay-{stage}-changes.json").write_text(json.dumps(changes, indent=2))
    print(json.dumps(changes, indent=2))


def apply(stage):
    env = terraform_env()
    detail = json.loads(checked_run([
        "terraform", "show", "-json", str(CONTROL / f"overlay-{stage}.tfplan"),
    ], env=env))
    changes = checked_changes(detail, stage)
    record_mutations(len(changes), f"Apply reviewed {stage} overlay-only plan")
    output = checked_run([
        "terraform", "apply", "-no-color", "-input=false", "-lock-timeout=30s", "-parallelism=1",
        str(CONTROL / f"overlay-{stage}.tfplan"),
    ], env=env, timeout=1200)
    (CONTROL / f"overlay-{stage}-apply.log").write_text(output, encoding="utf-8")
    (CONTROL / "overlay-stage.json").write_text(json.dumps({"stage": stage, "at": now()}))
    print("\n".join(line for line in output.splitlines() if "Apply complete!" in line))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "apply", "inspect", "guest", "complete-internet"])
    parser.add_argument("--stage", choices=["internet", "private-first", "private", "backup"], default="backup")
    parser.add_argument("--retain-static", action="store_true")
    args = parser.parse_args()
    if args.stage == "private-first" and args.action in ["plan", "apply"]:
        parser.error("private-first is CPE-only; use private --retain-static for its Azure plan.")
    if args.action == "complete-internet" and args.stage != "backup":
        parser.error("complete-internet requires the backup stage.")
    if args.action == "plan":
        plan(args.stage, args.retain_static)
    elif args.action == "apply":
        apply(args.stage)
    elif args.action == "inspect":
        output = ssh(
            "set -eu\nhostname\nip -br address\nip route show\n"
            "systemctl is-active strongswan frr\nswanctl --list-sas\n"
            "pgrep -a bgpd || test \"$?\" = 1\n",
        )
        (CONTROL / f"guest-{args.stage}-inspect.txt").write_text(output, encoding="utf-8")
        print(output)
    else:
        from overlay_guest import install_script
        record_mutations(1, f"Install persistent {args.stage} CPE configuration")
        output = ssh(install_script(inventory(), json.loads(
            (CONTROL / "overlay-secrets.json").read_text(),
        ), args.stage, add_only=args.action == "complete-internet"), timeout=180)
        (CONTROL / f"guest-{args.stage}-install.txt").write_text(output, encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
