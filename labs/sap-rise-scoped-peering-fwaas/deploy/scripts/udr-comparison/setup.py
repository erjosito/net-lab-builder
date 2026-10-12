"""Explicit one-item setup/restore, snapshot first. No cloud calls on import/help.

Lease extras: phase, startedAtUtc, subscriptionId, allowedMutations (item names,
or restore:<entry-number>:<inverse-number>), approvedGuestChanges (guest item names). Standard
live-lab budget/owner/expiry/STOP fields are mandatory. Reuse --out across leases.
Unknown outcomes are deliberately NOT auto-retried/restored: hand to recovery.

Execution (replace LEASE/OUT; use fresh approved lease at each group boundary):
  python -B setup.py --phase apply --item ITEM --lease LEASE --out OUT
Groups of at most three forward operations, each reserving all inverses:
  start-hub, start-spoke, start-workload (start forwarding NVAs before workload)
  source-table, source-subnet, source-nic
  source-association, source-vm --sku APPROVED_SKU --ssh-public-key EXISTING_PUBLIC_KEY (1+2)
  hub-table, hub-association, hub-route
  spoke-route, workload-route
  hub-nsg-icmp, hub-nsg-tcp; spoke-nsg-icmp, spoke-nsg-tcp
Only if snapshot review proves necessary, approve individual guest items:
  ROLE-policy-default before ROLE-policy-workload/source/peer (one each);
  ROLE-nat-forward/return (one each). ROLE is hub or spoke.
The design explicitly chooses isolated policy table 4242: retain that design,
do NOT silently substitute main-table /32s potentially exported by BIRD.
NSG changes also require review; do not add rules if existing policy suffices.
All setup remains constant across A/B/A2. Source table propagation is disabled
at creation, including A. No ARS/ER/peering/BIRD changes exist in this script.
  python -B setup.py --phase B --item source-route --lease LEASE --out OUT
  python -B setup.py --phase A2 --item source-route --lease LEASE --out OUT
  python -B setup.py --phase restore --item INDEX --lease LEASE --out OUT
Restore applied entries from changes.json in descending index order, at most
three inverses per lease; A2 removes only the source /32, never propagation.
Journal contains exact IDs, before snapshots, commands and ordered inverses.
An UNKNOWN outcome needs read-only reconciliation by a recovery owner, not
replay. The coordinator closes every lease after Niobe's acceptance boundary.
"""
import argparse
import json
import shlex
from pathlib import Path
from runtime import RG, Runtime, arguments, load, save

NET = ["network"]
VM = {"hub": "vm-hub-nva", "spoke": "vm-spoke-nva"}
GATEWAY = {"hub": "10.40.1.1", "spoke": "10.60.0.1"}
DEST = {"hub": ["10.60.1.4", "10.60.0.4", "10.40.2.4"],
        "spoke": ["10.40.2.4", "10.40.1.4", "10.60.1.4"]}
TABLES = {"source": "rt-ab-hub-test", "hub": "rt-ab-hub-nva",
          "spoke": "rt-spoke-nva-return", "workload": "rt-spoke-workload"}
SUBNETS = {"source": ("vnet-hub", "snet-hub-test"),
           "hub": ("vnet-hub", "snet-hub-nva"),
           "spoke": ("vnet-sap-rise", "snet-spoke-nva"),
           "workload": ("vnet-sap-rise", "snet-workload")}
ROUTES = {"source": ("ab-workload-via-hub", "10.60.1.4/32", "10.40.1.4"),
          "hub": ("ab-workload-via-spoke", "10.60.1.4/32", "10.60.0.4"),
          "spoke": ("ab-source-via-hub", "10.40.2.4/32", "10.40.1.4"),
          "workload": ("ab-source-via-spoke", "10.40.2.4/32", "10.60.0.4")}


def az(kind, op, name, *extra):
    return ["network", *kind.split(), op, "-g", RG, "-n", name, *extra]


def finish(script):
    return "set -eu\n" + script + "\nprintf '\\nUDR_STATUS=0\\n'\n"


def guest_item(item):
    role, action = item.split("-", 1)
    if role not in VM:
        raise ValueError("Guest role must be hub or spoke")
    if action == "policy-default":
        before = "ip -j route show table all"
        check = "! ip route show table all | grep -q 'table 4242'"
        forward = f"ip route add table 4242 default via {GATEWAY[role]} dev eth0"
        inverse = forward.replace(" add ", " del ", 1)
    elif action.startswith("policy-"):
        index = {"workload": 0 if role == "hub" else 2,
                 "peer": 1, "source": 2 if role == "hub" else 0}[action[7:]]
        pref, dest = 10420 + index, DEST[role][index]
        before = "ip -j rule show"
        check = f"! ip rule show | grep -q '^{pref}:'\nip route show table 4242 | grep -q '^default via {GATEWAY[role]} dev eth0'"
        forward = f"ip rule add pref {pref} to {dest}/32 lookup 4242"
        inverse = forward.replace(" add ", " del ", 1)
    elif action in ("nat-forward", "nat-return"):
        src, dst = ("10.40.2.4", "10.60.1.4") if action == "nat-forward" else ("10.60.1.4", "10.40.2.4")
        match = f"-s {src}/32 -d {dst}/32 -m comment --comment udr-ab-{action} -j ACCEPT"
        before = "iptables-save -t nat"
        check = f"! iptables -t nat -C POSTROUTING {match}"
        forward = f"iptables -t nat -I POSTROUTING 1 {match}"
        inverse = f"iptables -t nat -D POSTROUTING {match}"
    else:
        raise ValueError("Unknown guest action")
    return VM[role], before, check, forward, inverse


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["preflight", "apply", "B", "A2", "restore"], required=True)
    p.add_argument("--item", help="One named operation, or journal entry number for restore")
    p.add_argument("--sku", help="Previously approved SKU; no fallback")
    p.add_argument("--ssh-public-key", help="Existing public key file, never private key")
    arguments(p)
    a = p.parse_args()
    r = Runtime(a, "Tank")
    journal_path = Path(a.out) / "changes.json"
    journal = load(journal_path) if journal_path.exists() else []
    lease = r.guard()
    base = f"/subscriptions/{lease['subscriptionId']}/resourceGroups/{RG}/providers/"

    def show(kind, name, *extra):
        return r.command("before-" + a.item + "-" + name, az(kind, "show", name, *extra))

    def listed(kind, name):
        values = r.command("inventory-" + a.item + "-" + name, ["network", *kind.split(), "list", "-g", RG])
        return next((v for v in values if v["name"] == name), None)

    def apply(resource_id, before, forward, inverse, guest=None, cost=1):
        entry = {"item": a.item, "resourceId": resource_id, "before": before,
                 "forward": forward, "inverse": inverse, "guest": guest,
                 "cost": cost, "status": "pending", "lease": str(Path(a.lease))}
        journal.append(entry)
        save(journal_path, journal)
        try:
            if guest:
                r.guest(a.item, guest, finish(forward), cost=cost, inverse_cost=len(inverse))
            else:
                r.command(a.item, forward, cost=cost, inverse_cost=len(inverse), timeout=420)
            entry["status"] = "applied"
        except BaseException:
            entry["status"] = "unknown"
            raise
        finally:
            save(journal_path, journal)
        print(json.dumps({"entry": len(journal)-1, "item": a.item, "status": entry["status"],
                          "restore": inverse}))

    if a.phase == "preflight":
        a.item = "preflight"
        for vnet in ("vnet-hub", "vnet-sap-rise"):
            r.command(vnet, az("vnet", "show", vnet))
        for role, name in TABLES.items():
            listed("route-table", name)
        for name in ("nic-hub-test", "nic-hub-nva", "nic-spoke-nva", "nic-workload-probe"):
            listed("nic", name)
        return
    if not a.item:
        p.error("--item is required outside preflight")
    if a.phase in ("restore", "A2"):
        if a.phase == "A2":
            table = show("route-table", TABLES["source"])
            if table["disableBgpRoutePropagation"] is not True:
                raise RuntimeError("Source propagation drift: A2 comparison blocked")
            candidates = [i for i, e in enumerate(journal) if e["item"] == "source-route" and e["status"] == "applied"]
            if len(candidates) != 1:
                raise RuntimeError("Expected exactly one applied B route")
            index = candidates[0]
        else:
            index = int(a.item)
        entry = journal[index]
        if entry["status"] != "applied":
            raise RuntimeError("Only proven applied entries can be restored; unknown requires recovery")
        if a.phase == "restore" and any(e["status"] == "applied" for e in journal[index+1:]):
            raise RuntimeError("Restore in reverse journal order")
        for number, inverse in enumerate(entry["inverse"]):
            label = f"restore:{index}:{number}"
            entry["status"] = "restore-pending"
            save(journal_path, journal)
            if entry["guest"]:
                r.guest(label, entry["guest"], finish(inverse), cost=1, closing=True)
            else:
                r.command(label, inverse, cost=1, closing=True, timeout=420)
        entry["status"] = "restored"
        save(journal_path, journal)
        return
    if a.phase == "B" and a.item != "source-route":
        raise RuntimeError("B may only add source-route")
    if a.phase == "apply" and a.item == "source-route":
        raise RuntimeError("Source UDR can only be installed in explicit B phase")
    if any(e["item"] == a.item and e["status"] != "restored" for e in journal):
        raise RuntimeError("Already attempted; do not silently retry")
    item = a.item
    if item in ("start-hub", "start-spoke", "start-workload"):
        name = "vm-workload-probe" if item == "start-workload" else VM[item[6:]]
        before = r.command("before-" + item, ["vm", "get-instance-view", "-g", RG, "-n", name])
        if not any(s["code"] == "PowerState/deallocated" for s in before["instanceView"]["statuses"]):
            raise RuntimeError("VM is not deallocated; no start/restore recorded")
        apply(base + "Microsoft.Compute/virtualMachines/" + name, before,
              ["vm", "start", "-g", RG, "-n", name, "--no-wait"], [["vm", "deallocate", "-g", RG, "-n", name]])
    elif item in ("source-table", "hub-table"):
        role = item.split("-")[0]
        name = TABLES[role]
        if listed("route-table", name):
            raise RuntimeError("Table exists: reuse after inspection, do not overwrite")
        apply(base + "Microsoft.Network/routeTables/" + name, None,
              az("route-table", "create", name, "-l", "swedencentral",
                 "--disable-bgp-route-propagation", "true" if role == "source" else "false"),
              [az("route-table", "delete", name)])
    elif item == "source-subnet":
        vnet = show("vnet", "vnet-hub")
        if any(s["name"] == "snet-hub-test" for s in vnet["subnets"]):
            raise RuntimeError("Source subnet exists; inspect and reuse explicitly")
        table = show("route-table", TABLES["source"])
        if table["disableBgpRoutePropagation"] is not True:
            raise RuntimeError("Source propagation MUST be disabled")
        apply(base + "Microsoft.Network/virtualNetworks/vnet-hub/subnets/snet-hub-test", None,
              az("vnet subnet", "create", "snet-hub-test", "--vnet-name", "vnet-hub",
                 "--address-prefixes", "10.40.2.0/27"),
              [az("vnet subnet", "delete", "snet-hub-test", "--vnet-name", "vnet-hub")])
    elif item == "source-nic":
        if listed("nic", "nic-hub-test"):
            raise RuntimeError("NIC exists; inspect and reuse")
        apply(base + "Microsoft.Network/networkInterfaces/nic-hub-test", None,
              az("nic", "create", "nic-hub-test", "-l", "swedencentral", "--vnet-name", "vnet-hub",
                 "--subnet", "snet-hub-test", "--private-ip-address", "10.40.2.4",
                 "--ip-forwarding", "false"),
              [az("nic", "delete", "nic-hub-test")])
    elif item == "source-vm":
        if not a.sku or not a.ssh_public_key:
            p.error("source-vm requires approved --sku and --ssh-public-key")
        key = Path(a.ssh_public_key).read_text(encoding="utf-8").strip()
        if not key.startswith(("ssh-rsa ", "ssh-ed25519 ", "ecdsa-sha2-")) or "PRIVATE" in key:
            raise ValueError("Expected public SSH key only")
        for kind, name in (("vm", "vm-hub-test"), ("disk", "osdisk-udr-hub-test")):
            values = r.command("inventory-" + kind, [kind, "list", "-g", RG])
            if any(v["name"] == name for v in values):
                raise RuntimeError(kind + " exists: refuse replacement")
        nic = show("nic", "nic-hub-test")
        if nic.get("virtualMachine") or nic["ipConfigurations"][0]["privateIPAddress"] != "10.40.2.4":
            raise RuntimeError("Source NIC occupied or wrong IP")
        subnet = show("vnet subnet", "snet-hub-test", "--vnet-name", "vnet-hub")
        table = show("route-table", TABLES["source"])
        if (subnet.get("routeTable") or {}).get("id", "").lower() != table["id"].lower() or table["disableBgpRoutePropagation"] is not True:
            raise RuntimeError("Source table must be associated with propagation disabled before VM creation")
        resource_id = base + "Microsoft.Compute/virtualMachines/vm-hub-test"
        body = {"location": "swedencentral",
            "tags": {"lab": "sap-rise-scoped-peering-fwaas", "owner": "jose", "ephemeral": "true"},
            "properties": {"hardwareProfile": {"vmSize": a.sku},
                "storageProfile": {
                    "imageReference": {"publisher": "Canonical", "offer": "0001-com-ubuntu-server-jammy",
                                       "sku": "22_04-lts-gen2", "version": "latest"},
                    "osDisk": {"name": "osdisk-udr-hub-test", "createOption": "FromImage",
                               "deleteOption": "Detach", "managedDisk": {"storageAccountType": "StandardSSD_LRS"}}},
                "osProfile": {"computerName": "vm-hub-test", "adminUsername": "azurelabuser",
                    "linuxConfiguration": {"disablePasswordAuthentication": True,
                        "ssh": {"publicKeys": [{"path": "/home/azurelabuser/.ssh/authorized_keys", "keyData": key}]}}},
                "networkProfile": {"networkInterfaces": [
                    {"id": nic["id"], "properties": {"primary": True, "deleteOption": "Detach"}}]}}}
        # Direct VM PUT avoids az vm create's extra deployment-record mutation.
        forward = ["rest", "--method", "put", "--url",
                   "https://management.azure.com" + resource_id + "?api-version=2024-07-01",
                   "--body", json.dumps(body)]
        apply(resource_id, None, forward,
              [["vm", "delete", "-g", RG, "-n", "vm-hub-test", "--yes"],
               ["disk", "delete", "-g", RG, "-n", "osdisk-udr-hub-test", "--yes"]], cost=2)
    elif item in ("hub-association", "source-association"):
        role = item.split("-")[0]
        vnet, subnet = SUBNETS[role]
        before = show("vnet subnet", subnet, "--vnet-name", vnet)
        table = show("route-table", TABLES[role])
        if role == "source" and table["disableBgpRoutePropagation"] is not True:
            raise RuntimeError("Source propagation MUST be disabled")
        old = (before.get("routeTable") or {}).get("id")
        if old:
            raise RuntimeError("Association already exists: do not replace")
        apply(before["id"], before,
              az("vnet subnet", "update", subnet, "--vnet-name", vnet, "--route-table", table["id"]),
              [az("vnet subnet", "update", subnet, "--vnet-name", vnet, "--remove", "routeTable")])
    elif item.endswith("-route") and item.split("-")[0] in ROUTES:
        role = item.split("-")[0]
        table = show("route-table", TABLES[role])
        vnet, subnet = SUBNETS[role]
        association = show("vnet subnet", subnet, "--vnet-name", vnet)
        if (association.get("routeTable") or {}).get("id", "").lower() != table["id"].lower():
            raise RuntimeError("Expected table not associated")
        if role == "source" and table["disableBgpRoutePropagation"] is not True:
            raise RuntimeError("Source propagation MUST remain disabled in A/B/A2")
        name, prefix, hop = ROUTES[role]
        if any(v["name"] == name or v["addressPrefix"] == prefix for v in table["routes"]):
            raise RuntimeError("Route name/prefix collision; refuse replacement")
        apply(table["id"] + "/routes/" + name, table,
              az("route-table route", "create", name, "--route-table-name", TABLES[role],
                 "--address-prefix", prefix, "--next-hop-type", "VirtualAppliance", "--next-hop-ip-address", hop),
              [az("route-table route", "delete", name, "--route-table-name", TABLES[role])])
    elif item.startswith(("hub-nsg-", "spoke-nsg-")):
        role, _, protocol = item.split("-")
        if protocol not in ("icmp", "tcp"):
            raise ValueError("NSG protocol must be icmp or tcp")
        nsg = "nsg-" + role + "-nva"
        before = show("nsg", nsg)
        priority = "200" if protocol == "icmp" else "201"
        name = "Allow-UdrAB-" + ("ICMP" if protocol == "icmp" else "TCP22")
        if any(v["name"] == name or v["priority"] == int(priority) for v in before["securityRules"]):
            raise RuntimeError("NSG rule name/priority collision")
        peers = ["10.40.2.4/32", "10.40.1.4/32", "10.60.0.4/32", "10.60.1.4/32"]
        apply(before["id"] + "/securityRules/" + name, before,
              az("nsg rule", "create", name, "--nsg-name", nsg, "--priority", priority,
                 "--direction", "Inbound", "--access", "Allow", "--protocol", protocol,
                 "--source-address-prefixes", *peers, "--destination-address-prefixes", *peers,
                 "--source-port-ranges", "*", "--destination-port-ranges", "*" if protocol == "icmp" else "22"),
              [az("nsg rule", "delete", name, "--nsg-name", nsg)])
    else:
        if item not in lease.get("approvedGuestChanges", []):
            raise RuntimeError("Guest delta requires explicit snapshot-reviewed approvedGuestChanges")
        vm, before_script, check, forward, inverse = guest_item(item)
        before = r.guest("before-" + item, vm, finish(before_script))
        if len(before.encode()) >= 3500:
            raise RuntimeError("Snapshot too large; collect chunks before approving changes")
        apply(base + "Microsoft.Compute/virtualMachines/" + vm, before,
              check + "\n" + forward, [inverse], guest=vm)


if __name__ == "__main__":
    main()
