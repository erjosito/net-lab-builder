"""Resume only the exact tagged lab inventory; no replacement resources."""
import json

import control

EXPECTED = {
    "router-eu", "router-us", "router-jp", "router-cn",
    "probe-dc-eu", "probe-dc-us", "probe-dc-jp",
    "probe-spoke-eu", "probe-spoke-us", "probe-spoke-jp",
}


def main():
    control.LEASE = control.RUNTIME / "vm-resume-20261015.json"
    resources = control.az(["vm", "list", "-g", control.RG], "resume-inventory", timeout=120)
    if {vm["name"] for vm in resources} != EXPECTED:
        raise RuntimeError("Actual VM inventory differs from the ten approved lab VMs")
    for vm in resources:
        tags = vm.get("tags", {})
        if any(tags.get(key) != value for key, value in control.TAGS.items()):
            raise RuntimeError(f"{vm['name']}: task ownership tags do not match")
    control.az(["vm", "start", "--ids", *[vm["id"] for vm in resources]],
               "resume-start", mutation=True, timeout=600)
    actual = control.az(["vm", "list", "-g", control.RG, "--show-details"],
                        "resume-status", timeout=120, closure=True)
    summary = [{"name": vm["name"], "powerState": vm.get("powerState")} for vm in actual]
    running = len(actual) == 10 and all(vm.get("powerState") == "VM running" for vm in actual)
    lease = json.loads(control.LEASE.read_text())
    lease.update(state="completed" if running else "blocked",
                 resourceOperationsUsed=10, childProcesses="none",
                 result=summary)
    control.save(control.LEASE, lease)
    print(json.dumps(summary, indent=2))
    if not running:
        raise RuntimeError("Not all ten lab VMs are running")


if __name__ == "__main__":
    main()
