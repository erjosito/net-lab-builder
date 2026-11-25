import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent
CONTROL = ROOT / ".runtime-control"
STATE_BUCKET = "gcp-vnbgp-state-20261124-tfstate"
LAB_GROUP = "rg-vnbgp-20261124"
SUBSCRIPTION_NAME = "Litware-MngEnvMCAP642473-jomore"


def gcloud_command(*arguments):
    native = shutil.which("gcloud.cmd")
    if native:
        return [native, *arguments]
    return ["wsl.exe", "--", "gcloud", *arguments]


def run(command, *, timeout=90, env=None):
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        script = (
            "function Stop-Tree([int]$processId) { "
            "Get-CimInstance Win32_Process -Filter \"ParentProcessId = $processId\" | "
            "ForEach-Object { Stop-Tree $_.ProcessId }; "
            "Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }; "
            f"Stop-Tree {process.pid}"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                       capture_output=True, timeout=30, check=True)
        process.communicate(timeout=30)
        raise RuntimeError(f"Command exceeded its {timeout}s bound; process tree stopped.")
    if process.returncode:
        raise RuntimeError(f"{command[0]} failed: {stderr or stdout}")
    return stdout


def check_lease():
    lease = json.loads((CONTROL / "lease.json").read_text())
    expiry = datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    if (CONTROL / "STOP").exists() or lease["state"] != "active":
        raise RuntimeError("The live lease is not active or STOP exists.")
    remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise RuntimeError("The live lease has expired.")
    return remaining


def check_changes(changes):
    if any("delete" in change["actions"] for change in changes):
        raise RuntimeError("Plan includes destruction or replacement; do not apply.")
    if any(
        change["address"].startswith("megaport_") and "create" in change["actions"]
        for change in changes
    ):
        raise RuntimeError(
            "Megaport creates require an explicitly validated PAYG/no-renewal "
            "API order followed by import; this provider cannot set renewal."
        )
    if any(
        change["address"].startswith("megaport_") and "update" in change["actions"]
        for change in changes
    ):
        raise RuntimeError(
            "Megaport updates are blocked: API-ordered products are inventory-only "
            "in Terraform; verify PAYG/no-renewal and generated peering separately."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "plan", "apply", "inventory"])
    parser.add_argument("--stage", choices=["preflight", "foundation", "provider", "connection"],
                        default="foundation")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    CONTROL.mkdir(exist_ok=True)
    remaining = check_lease()
    if args.timeout > remaining - 60:
        raise RuntimeError("Requested command timeout exceeds the remaining lease reserve.")
    env = os.environ.copy()
    env.pop("TF_LOG", None)
    env.pop("TF_LOG_PATH", None)
    account = json.loads(run([
        "az.cmd", "account", "show", "--subscription", SUBSCRIPTION_NAME, "-o", "json"
    ]))
    env["ARM_SUBSCRIPTION_ID"] = account["id"]
    env["ARM_TENANT_ID"] = account["tenantId"]
    token = run(gcloud_command("auth", "print-access-token")).strip()
    env["GOOGLE_OAUTH_ACCESS_TOKEN"] = token
    command = ["terraform", args.action, "-no-color"]
    if args.action == "init":
        command += [
            "-input=false", "-reconfigure",
            f"-backend-config=bucket={STATE_BUCKET}",
            "-backend-config=prefix=vnet-vpn-custom-bgp",
        ]
    elif args.action == "inventory":
        command = ["terraform", "show", "-json"]
    else:
        billing = json.loads(run(gcloud_command(
            "billing", "accounts", "list",
            "--filter=open=true", "--format=json",
        )))
        if len(billing) != 1:
            raise RuntimeError("Expected exactly one open billing account; select explicitly.")
        env["TF_VAR_billing_account"] = billing[0]["name"].removeprefix("billingAccounts/")
        exists = run([
            "az.cmd", "group", "exists", "--subscription", account["id"],
            "--name", LAB_GROUP, "-o", "tsv",
        ]).strip() == "true"
        keys = []
        if exists:
            keys = json.loads(run([
                "az.cmd", "vm", "list", "--subscription", account["id"],
                "--resource-group", LAB_GROUP, "--query",
                "[?name=='probe-vnbgp-20261124'].osProfile.linuxConfiguration.ssh.publicKeys[0].keyData",
                "-o", "json",
            ]))
        if keys:
            env["TF_VAR_ssh_public_key"] = keys[0]
        else:
            public = CONTROL / "probe-key.pub"
            if not public.exists():
                run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "vnet-lab",
                     "-f", str(CONTROL / "probe-key")])
            env["TF_VAR_ssh_public_key"] = public.read_text().strip()
        plan = CONTROL / f"{args.stage}.tfplan"
        if args.action == "plan":
            command += [
                "-input=false", "-lock-timeout=30s", f"-out={plan}",
                f"-var=deploy_megaport={'true' if args.stage in ['provider', 'connection'] else 'false'}",
                f"-var=connect_expressroute={'true' if args.stage == 'connection' else 'false'}",
            ]
            if args.stage == "preflight":
                command.append("-target=azurerm_resource_group.lab")
        else:
            if not plan.exists():
                raise RuntimeError("A reviewed saved plan for this stage is required.")
            changes = json.loads((CONTROL / f"{args.stage}-changes.json").read_text())
            check_changes(changes)
            command += ["-input=false", "-lock-timeout=30s", str(plan)]
    check_lease()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log = CONTROL / f"{stamp}-{args.action}-{args.stage}.log"
    try:
        output = run(command, timeout=args.timeout, env=env)
    except RuntimeError as error:
        log.write_text(str(error), encoding="utf-8")
        raise RuntimeError(f"Terraform failed; private diagnostic: {log.name}") from None
    log.write_text(output, encoding="utf-8")
    if args.action == "inventory":
        state = json.loads(output)
        resources = []

        def collect(module):
            resources.extend(
                {"address": r["address"], "type": r["type"],
                 "name": r.get("values", {}).get("name") or r.get("values", {}).get("product_name")}
                for r in module.get("resources", [])
            )
            for child in module.get("child_modules", []):
                collect(child)

        collect(state.get("values", {}).get("root_module", {}))
        print(json.dumps(resources, indent=2))
    elif args.action == "plan":
        detail = json.loads(run(["terraform", "show", "-json", str(plan)], env=env))
        changes = [
            {"address": r["address"], "actions": r["change"]["actions"]}
            for r in detail.get("resource_changes", [])
            if r["change"]["actions"] != ["no-op"]
        ]
        (CONTROL / f"{args.stage}-changes.json").write_text(json.dumps(changes, indent=2))
        print(json.dumps(changes, indent=2))
        check_changes(changes)
    else:
        summaries = re.findall(r"(?m)^(?:Apply complete!|Terraform has been successfully).*$", output)
        print("\n".join(summaries) or f"{args.action}: completed; private log {log.name}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
