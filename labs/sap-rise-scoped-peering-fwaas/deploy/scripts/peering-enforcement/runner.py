"""One coordinator-leased phase per process. --plan is entirely offline."""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import sys
import uuid

from transport import Blocked, Lock, RG, Transport, load, now, save, sibling

API = "2025-01-01"
COMPUTE_API = "2024-07-01"
DISK_API = "2024-03-02"
SOURCE_TABLE = "rt-enforcement-source"
SOURCE_VM = "vm-hub-test"
SOURCE_DISK = "osdisk-enforcement-hub-test"
SOURCE_NIC = "nic-hub-test"
RULE = "Allow-PeeringEnforcement-ICMP"
IPS = ["10.40.2.4", "10.40.1.4", "10.60.0.4", "10.60.1.4"]
VMS = ["vm-hub-nva", "vm-spoke-nva", "vm-workload-probe"]
NIC_NAMES = [SOURCE_NIC, "nic-hub-nva", "nic-spoke-nva", "nic-workload-probe"]
PEERS = [("vnet-hub", "peer-hub-to-sap-rise"),
         ("vnet-sap-rise", "peer-sap-rise-to-hub")]
SEQUENCE = ["inventory", "G1", "G2", "G3", "G4", "collect-viability",
            "G5", "collect-return", "G6-add", "collect-bypass", "G6-remove",
            "G7-add", "collect-vnetlocal", "G7-remove",
            "G8-add", "collect-vnetpeering", "G8-remove",
            "G9", "collect-subnet", "G10", "G11-add", "collect-full",
            "G11-remove", "G12", "collect-restored", "G13", "G14", "G15", "G16", "verify"]
PEER_WRITABLE = ("allowVirtualNetworkAccess", "allowForwardedTraffic", "allowGatewayTransit",
                 "useRemoteGateways", "doNotVerifyRemoteGateways", "remoteVirtualNetwork",
                 "peerCompleteVnets", "localSubnetNames", "remoteSubnetNames",
                 "enableOnlyIPv6Peering")


def props(resource):
    return resource.get("properties", resource)


def named(values, name):
    found = [x for x in values if x["name"].lower() == name.lower()]
    if len(found) != 1:
        raise Blocked("Expected exactly one resource: " + name)
    return found[0]


def peer_body(resource, full=False):
    p = props(resource)
    body = {k: copy.deepcopy(p[k]) for k in PEER_WRITABLE if k in p}
    if "remoteVirtualNetwork" not in body:
        raise Blocked("Peering has no remote VNet ID")
    body["remoteVirtualNetwork"] = {"id": body["remoteVirtualNetwork"]["id"]}
    if body.get("peerCompleteVnets") is True:
        for key in ("localSubnetNames", "remoteSubnetNames"):
            if body.get(key) in (None, []):
                body.pop(key, None)
    if full:
        body["peerCompleteVnets"] = True
        body.pop("localSubnetNames", None)
        body.pop("remoteSubnetNames", None)
    return {"properties": body}


def stable(value):
    """Compare original configurations, ignoring only enumerated service state."""
    ignored = {"etag", "provisioningState", "resourceGuid", "peeringState", "peeringSyncLevel",
               "remoteAddressSpace", "remoteVirtualNetworkAddressSpace", "localAddressSpace",
               "localVirtualNetworkAddressSpace", "remoteBgpCommunities", "instanceView",
               "diskState", "statuses",
               "macAddress", "lastModifiedAt", "lastModifiedBy", "lastModifiedByType",
               "timeModified", "completionPercent", "lastOwnershipUpdateTime",
               "LastOwnershipUpdateTime"}
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in ignored}
    if isinstance(value, list):
        items = [stable(x) for x in value]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    return value


def verify_original_identities(original, fresh):
    for collection, identity in (("vms", "vmId"), ("nics", "resourceGuid"), ("disks", "uniqueId")):
        for before in original[collection]:
            after = named(fresh[collection], before["name"])
            if (before["id"].lower() != after["id"].lower()
                    or props(before).get(identity) != props(after).get(identity)):
                raise Blocked("Original resource was replaced: " + before["id"])


def api_for(resource_id, compute=False):
    if compute:
        return DISK_API if "/disks" in resource_id.lower() else COMPUTE_API
    return API


def rest(method, resource_id, body=None, compute=False):
    result = ["rest", "--method", method, "--url",
              "https://management.azure.com" + resource_id + "?api-version=" +
              api_for(resource_id, compute)]
    if body is not None:
        result += ["--body", json.dumps(body, separators=(",", ":"))]
    return result


def ids(subscription):
    uuid.UUID(subscription)
    root = f"/subscriptions/{subscription}/resourceGroups/{RG}/providers/"
    return root + "Microsoft.Network/", root + "Microsoft.Compute/"


def inventory(r):
    net, compute = ids(r.initial["subscriptionId"])
    result = {}
    for key, resource_id in (("vnets", net + "virtualNetworks"), ("nics", net + "networkInterfaces"),
                             ("nsgs", net + "networkSecurityGroups"), ("tables", net + "routeTables"),
                             ("vms", compute + "virtualMachines"), ("disks", compute + "disks")):
        data = r.command("inventory-" + key, rest("get", resource_id, compute=key in ("vms", "disks")))
        if data.get("nextLink"):
            raise Blocked("Inventory pagination needs a separately bounded inventory")
        result[key] = data["value"]
    result["power"] = r.command("inventory-power", ["vm", "list", "-g", RG, "--show-details"])
    result["resources"] = r.command("inventory-identities", ["resource", "list", "-g", RG])
    return result


def baseline_check(snapshot):
    for key, forbidden in (("vms", SOURCE_VM), ("disks", SOURCE_DISK),
                           ("nics", SOURCE_NIC), ("tables", SOURCE_TABLE)):
        if any(x["name"] == forbidden for x in snapshot[key]):
            raise Blocked("Temporary resource already exists: " + forbidden)
    hub = props(named(snapshot["vnets"], "vnet-hub"))
    if any(x["name"] == "snet-hub-test" for x in hub["subnets"]):
        raise Blocked("Source subnet already exists")
    for vnet, prefix in (("vnet-hub", "10.40.0.0/16"), ("vnet-sap-rise", "10.60.0.0/16")):
        if props(named(snapshot["vnets"], vnet)).get("addressSpace", {}).get("addressPrefixes") != [prefix]:
            raise Blocked("Original VNet address space differs: " + vnet)
    for index, (vnet, peer) in enumerate(PEERS):
        p = props(named(props(named(snapshot["vnets"], vnet))["virtualNetworkPeerings"], peer))
        if (p.get("peerCompleteVnets") is not False
                or p.get("localSubnetNames") != [["snet-hub-nva"], ["snet-spoke-nva"]][index]
                or p.get("remoteSubnetNames") != [["snet-spoke-nva"], ["snet-hub-nva"]][index]
                or p.get("remoteVirtualNetwork", {}).get("id", "").lower() !=
                named(snapshot["vnets"], PEERS[1-index][0])["id"].lower()
                or not p.get("allowVirtualNetworkAccess") or not p.get("allowForwardedTraffic")
                or p.get("allowGatewayTransit") or p.get("useRemoteGateways")):
            raise Blocked("Original scoped peering differs from design")
    if len(snapshot["vms"]) != 4:
        raise Blocked("Expected four original VMs, including CE")
    for vm in snapshot["vms"]:
        if named(snapshot["power"], vm["name"]).get("powerState") != "VM deallocated":
            raise Blocked("Original VM not deallocated: " + vm["name"])
        nic_ids = [x["id"].lower() for x in props(vm).get("networkProfile", {}).get("networkInterfaces", [])]
        disk_id = props(vm).get("storageProfile", {}).get("osDisk", {}).get("managedDisk", {}).get("id", "")
        if (not nic_ids or not set(nic_ids).issubset({x["id"].lower() for x in snapshot["nics"]})
                or disk_id.lower() not in {x["id"].lower() for x in snapshot["disks"]}):
            raise Blocked("Original VM/NIC/OS-disk identity chain missing: " + vm["name"])
    for name in VMS:
        named(snapshot["vms"], name)
    for table, prefix, hop in (("rt-spoke-nva-return", "172.40.100.0/24", "10.40.1.4"),
                               ("rt-spoke-workload", "0.0.0.0/0", "10.60.0.4")):
        p = props(named(snapshot["tables"], table))
        routes = p.get("routes", [])
        if p.get("disableBgpRoutePropagation") is not True or len(routes) != 1:
            raise Blocked("Original route table differs: " + table)
        route = props(routes[0])
        if (route.get("addressPrefix"), route.get("nextHopType"), route.get("nextHopIpAddress")) != (
                prefix, "VirtualAppliance", hop):
            raise Blocked("Original route differs: " + table)
    for role, vnet, subnet, table in (
            ("hub", "vnet-hub", "snet-hub-nva", None),
            ("spoke", "vnet-sap-rise", "snet-spoke-nva", "rt-spoke-nva-return"),
            ("workload", "vnet-sap-rise", "snet-workload", "rt-spoke-workload")):
        sub = props(named(props(named(snapshot["vnets"], vnet))["subnets"], subnet))
        expected_prefix = {"hub": "10.40.1.0/27", "spoke": "10.60.0.0/27", "workload": "10.60.1.0/24"}[role]
        if sub.get("addressPrefix") != expected_prefix and sub.get("addressPrefixes") != [expected_prefix]:
            raise Blocked("Original subnet prefix differs: " + subnet)
        table_id = sub.get("routeTable", {}).get("id", "")
        if (table and not table_id.endswith("/" + table)) or (not table and table_id):
            raise Blocked("Original subnet association differs: " + subnet)
        nsg_id = sub.get("networkSecurityGroup", {}).get("id")
        if not nsg_id or not any(x["id"].lower() == nsg_id.lower() for x in snapshot["nsgs"]):
            raise Blocked("Missing actual subnet NSG: " + subnet)
        if role == "hub" and not nsg_id.endswith("/nsg-hub-nva"):
            raise Blocked("Source must reuse the original nsg-hub-nva")
        nic = props(named(snapshot["nics"], "nic-" + ("workload-probe" if role == "workload" else role + "-nva")))
        if nic.get("enableIPForwarding", False) != (role != "workload"):
            raise Blocked("Original NIC forwarding mismatch")
        configurations = nic.get("ipConfigurations", [])
        expected_ip = {"hub": IPS[1], "spoke": IPS[2], "workload": IPS[3]}[role]
        if (len(configurations) != 1 or props(configurations[0]).get("privateIPAddress") != expected_ip
                or not props(configurations[0]).get("subnet", {}).get("id", "").endswith("/subnets/" + subnet)):
            raise Blocked("Original NIC IP/subnet differs")


def operation(label, resource_id, body, before=None, cost=1, compute=False, inverse=True):
    method = "delete" if body is None else "put"
    op = {"label": label, "id": resource_id, "body": body, "before": before, "cost": cost,
          "compute": compute, "argv": rest(method, resource_id, body, compute), "inverse": []}
    if inverse:
        op["inverse"] = [{"label": "undo:" + label, "id": resource_id, "body": before,
                          "compute": compute, "cost": 1,
                          "argv": rest("delete" if before is None else "put", resource_id, before, compute)}]
    return op


def plan(phase, snapshot, state, subscription, key=None, priority=None):
    net, compute = ids(subscription)
    vmid = compute + "virtualMachines/" + SOURCE_VM
    diskid = compute + "disks/" + SOURCE_DISK
    subnetid = net + "virtualNetworks/vnet-hub/subnets/snet-hub-test"
    nicid = net + "networkInterfaces/" + SOURCE_NIC
    tableid = net + "routeTables/" + SOURCE_TABLE
    tags = {"lab": "sap-rise-scoped-peering-fwaas", "owner": "jose", "ephemeral": "true"}

    def new(label, resource_id, body, **kw):
        return operation(phase + ":" + label, resource_id, body, **kw)

    def original_peer(vnet, peer):
        return named(props(named(snapshot["vnets"], vnet))["virtualNetworkPeerings"], peer)

    def previous(group):
        return [e for e in state["journal"] if e["phase"] == group and e["status"] == "applied"]

    if phase == "G1":
        return [
            new("table", tableid, {"location": "swedencentral", "tags": tags,
                                  "properties": {"disableBgpRoutePropagation": True, "routes": []}}),
            new("subnet", subnetid, {"properties": {"addressPrefix": "10.40.2.0/27",
                "routeTable": {"id": tableid},
                "networkSecurityGroup": {"id": net + "networkSecurityGroups/nsg-hub-nva"}}}),
            new("nic", nicid, {"location": "swedencentral", "tags": tags,
                "properties": {"enableIPForwarding": False, "ipConfigurations": [
                    {"name": "ipconfig1", "properties": {"privateIPAllocationMethod": "Static",
                     "privateIPAddress": IPS[0], "subnet": {"id": subnetid}}}]}})]
    if phase == "G2":
        if not key or not key.startswith(("ssh-rsa ", "ssh-ed25519 ", "ecdsa-sha2-")) or "PRIVATE" in key:
            raise Blocked("Existing SSH public key required")
        body = {"location": "swedencentral", "tags": tags, "properties": {
            "hardwareProfile": {"vmSize": "Standard_B2ts_v2"},
            "storageProfile": {"imageReference": {"publisher": "Canonical",
                "offer": "0001-com-ubuntu-server-jammy", "sku": "22_04-lts-gen2", "version": "latest"},
                "osDisk": {"name": SOURCE_DISK, "createOption": "FromImage", "deleteOption": "Detach",
                           "managedDisk": {"storageAccountType": "StandardSSD_LRS"}}},
            "osProfile": {"computerName": SOURCE_VM, "adminUsername": "azurelabuser",
                "linuxConfiguration": {"disablePasswordAuthentication": True, "ssh": {
                    "publicKeys": [{"path": "/home/azurelabuser/.ssh/authorized_keys", "keyData": key}]}}},
            "networkProfile": {"networkInterfaces": [{"id": nicid,
                "properties": {"primary": True, "deleteOption": "Detach"}}]}}}
        op = new("vm-and-disk", vmid, body, cost=2, compute=True)
        op["resourceCosts"] = [{"id": vmid, "cost": 1, "before": None},
                               {"id": diskid, "cost": 1, "before": None}]
        op["additionalReads"] = 1
        op["inverse"].append({"label": "undo:G2:disk", "id": diskid, "body": None,
                             "compute": True, "cost": 1, "argv": rest("delete", diskid, compute=True)})
        op["wait"] = ["vm", "wait", "-g", RG, "-n", SOURCE_VM, "--created", "--interval", "30", "--timeout", "600"]
        return [op]
    if phase in ("G3", "G16"):
        result = []
        for name in VMS:
            closing = phase == "G16"
            op = new(name, compute + "virtualMachines/" + name, {"power": "deallocated" if closing else "running"},
                     before={"power": "running" if closing else "deallocated"}, compute=True, inverse=not closing)
            op["argv"] = ["vm", "deallocate" if closing else "start", "-g", RG, "-n", name]
            op["power"] = True
            op["timeout"] = 600
            if not closing:
                op["inverse"][0]["argv"] = ["vm", "deallocate", "-g", RG, "-n", name]
                op["inverse"][0]["power"] = True
                op["inverse"][0]["timeout"] = 600
            result.append(op)
        return result
    if phase == "G4":
        if priority is None or not 100 <= priority <= 4096:
            raise Blocked("Azure NSG priority 90 is invalid. Supply explicitly approved --icmp-priority 100..4096")
        result = []
        for vnet, subnet in (("vnet-hub", "snet-hub-nva"), ("vnet-sap-rise", "snet-spoke-nva"),
                             ("vnet-sap-rise", "snet-workload")):
            sub = props(named(props(named(snapshot["vnets"], vnet))["subnets"], subnet))
            nsgid = sub["networkSecurityGroup"]["id"]
            nsg = next(x for x in snapshot["nsgs"] if x["id"].lower() == nsgid.lower())
            if any(props(x).get("priority") == priority or x["name"] == RULE for x in props(nsg).get("securityRules", [])):
                raise Blocked("NSG priority/name collision")
            body = {"properties": {"priority": priority, "direction": "Inbound", "access": "Allow",
                "protocol": "Icmp", "sourceAddressPrefixes": [x + "/32" for x in IPS],
                "destinationAddressPrefixes": [x + "/32" for x in IPS],
                "sourcePortRange": "*", "destinationPortRange": "*"}}
            result.append(new(nsg["name"], nsgid + "/securityRules/" + RULE, body))
        if len({x["id"].lower() for x in result}) != 3:
            raise Blocked("Expected three distinct NSGs")
        return result
    if phase == "G5":
        return [new(role, net + "routeTables/" + table + "/routes/enforcement-source-via-" + role,
                    {"properties": {"addressPrefix": IPS[0] + "/32", "nextHopType": "VirtualAppliance",
                                    "nextHopIpAddress": hop}})
                for role, table, hop in (("spoke", "rt-spoke-workload", IPS[2]),
                                         ("hub", "rt-spoke-nva-return", IPS[1]))]
    if phase in ("G6-add", "G7-add", "G8-add"):
        hop = {"G6-add": "VirtualAppliance", "G7-add": "VnetLocal", "G8-add": "VNetPeering"}[phase]
        body = {"properties": {"addressPrefix": IPS[3] + "/32", "nextHopType": hop}}
        if phase == "G6-add":
            body["properties"]["nextHopIpAddress"] = IPS[2]
        op = new("route", tableid + "/routes/enforcement-" + phase[:2].lower(), body)
        op["trial"] = phase != "G6-add"
        return [op]
    if phase in ("G6-remove", "G7-remove", "G8-remove", "G9", "G13"):
        origin = {"G9": "G5", "G13": "G4"}.get(phase, phase.replace("-remove", "-add"))
        return [new(str(i), e["id"], None, before=e["body"], inverse=phase not in ("G13",))
                for i, e in enumerate(reversed(previous(origin)))]
    if phase in ("G10", "G11-add", "G11-remove", "G12"):
        result = []
        for vnet, peer in PEERS:
            original = peer_body(original_peer(vnet, peer))
            full = peer_body(original_peer(vnet, peer), full=True)
            before, body = {"G10": (original, None), "G11-add": (None, full),
                            "G11-remove": (full, None), "G12": (None, original)}[phase]
            result.append(new(peer, net + "virtualNetworks/" + vnet + "/virtualNetworkPeerings/" + peer,
                              body, before=before))
        return result
    if phase == "G14":
        original = previous("G2")
        if len(original) != 1:
            raise Blocked("No proven source VM creation")
        result = [new("vm", vmid, None, before=original[0]["body"], compute=True, inverse=False),
                  new("disk", diskid, None, before={"createdBy": "G2"}, compute=True, inverse=False)]
        result[0]["identity"] = {k: props(original[0].get("after", {}))[k] for k in ("vmId",)
                                 if k in props(original[0].get("after", {}))}
        result[1]["identity"] = {k: props(original[0].get("diskAfter", {}))[k] for k in ("uniqueId",)
                                 if k in props(original[0].get("diskAfter", {}))}
        return result
    if phase == "G15":
        return [new(str(i), e["id"], None, before=e["body"], inverse=False)
                for i, e in enumerate(reversed(previous("G1")))]
    raise Blocked("No mutation plan for phase " + phase)


def resource(r, op, label, closing=False):
    if op.get("power"):
        data = r.command(label, ["vm", "get-instance-view", "-g", RG, "-n", op["id"].rsplit("/", 1)[1]],
                         closing=closing)
        statuses = data.get("instanceView", data).get("statuses", [])
        states = [x["code"].split("/", 1)[1] for x in statuses if x["code"].startswith("PowerState/")]
        if len(states) != 1:
            raise Blocked("Missing VM power state")
        return {"power": states[0]}
    data = r.command(label, rest("get", op["id"].rsplit("/", 1)[0], compute=op.get("compute", False)),
                     closing=closing)
    if data.get("nextLink"):
        raise Blocked("Resource list pagination; do not assume absence")
    values = [x for x in data["value"] if x["id"].lower() == op["id"].lower()]
    if len(values) > 1:
        raise Blocked("Duplicate resource ID")
    return values[0] if values else None


def matches(actual, expected):
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if isinstance(expected, dict):
        return all(k in actual and matches(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(matches(a, b) for a, b in zip(actual, expected))
    return actual == expected


def verify_op(r, op, label, closing=False):
    current = resource(r, op, label, closing)
    if not matches(current, op["body"]):
        raise Blocked("Resource verification failed: " + op["id"])
    if current and props(current).get("provisioningState", "Succeeded") != "Succeeded":
        raise Blocked("Provisioning not complete: " + op["id"])
    return current


def wait_op(r, op, closing=False, result=None):
    if op.get("power"):
        return
    if op["body"] is not None and result and props(result).get("provisioningState") == "Succeeded":
        return
    argv = op.get("wait") or [
        "resource", "wait", "--ids", op["id"], "--api-version",
        api_for(op["id"], op.get("compute", False)),
        "--deleted" if op["body"] is None else "--created", "--interval", "30", "--timeout", "120"]
    r.command("wait-" + op["label"], argv, closing=closing, timeout=600 if op.get("wait") else 120)


def rollback(r, entries):
    errors = []
    deadline = now().timestamp() + min(300, r.initial["restoreTimeoutMinutes"] * 60)
    r.restore_deadline = deadline
    for entry in reversed(entries):
        if entry["status"] != "applied":
            continue
        if not entry["inverse"]:
            errors.append("Closure already changed original-state direction: " + entry["label"])
            continue
        entry["rollback"] = []
        for inverse in entry["inverse"]:
            record = dict(inverse, status="pending", before=entry["body"])
            entry["rollback"].append(record)
            r.persist()
            try:
                if now().timestamp() >= deadline:
                    raise Blocked("Restore time ceiling")
                result = r.command(inverse["label"], inverse["argv"], cost=inverse["cost"], closing=True,
                                   timeout=min(inverse.get("timeout", 120), max(1, deadline - now().timestamp())))
                record["status"] = "submitted"
                wait_op(r, inverse, closing=True, result=result)
                verify_op(r, inverse, "verify-" + inverse["label"], closing=True)
                record["status"] = "restored"
            except BaseException as exc:
                record["status"] = "unknown"
                errors.append(str(exc))
                r.persist()
                return errors
            r.persist()
        entry["status"] = "restored"
        r.persist()
    return errors


def execute(r, operations):
    if r.args.phase == "G2":
        net, compute = ids(r.initial["subscriptionId"])
        disk = {"id": compute + "disks/" + SOURCE_DISK, "compute": True}
        if resource(r, disk, "preflight-source-disk") is not None:
            raise Blocked("Named source OS disk already exists")
        nic = r.command("preflight-source-nic", rest("get", net + "networkInterfaces/" + SOURCE_NIC))
        if props(nic).get("virtualMachine"):
            raise Blocked("Source NIC already attached")
        subnet = r.command("preflight-source-subnet",
                           rest("get", net + "virtualNetworks/vnet-hub/subnets/snet-hub-test"))
        if props(subnet).get("routeTable", {}).get("id") != net + "routeTables/" + SOURCE_TABLE:
            raise Blocked("Source route-table association drift")
    r.authorize(operations)
    entries = []
    try:
        for op in operations:
            if r.args.phase == "G14" and not op.get("identity"):
                raise Blocked("Temporary compute identity was not captured; no deletion")
            current = resource(r, op, "before-" + op["label"])
            expected = op["before"]
            if op.get("identity") and not matches(props(current or {}), op["identity"]):
                raise Blocked("Temporary resource identity changed: " + op["id"])
            if op["id"].endswith("/" + SOURCE_DISK) and expected == {"createdBy": "G2"}:
                if current is None or current.get("managedBy"):
                    raise Blocked("Source disk absent/attached")
            elif not matches(current, expected):
                raise Blocked("Before-state drift: " + op["id"])
            entry = copy.deepcopy(op)
            entry.update(phase=r.args.phase, before=current, status="pending",
                         lease=r.initial["taskId"], utc=now().isoformat())
            entries.append(entry)
            r.state["journal"].append(entry)
            r.persist()
            try:
                result = r.command(op["label"], op["argv"], cost=op["cost"],
                                   timeout=op.get("timeout", 120), trial=op.get("trial", False))
                if result and result.get("_rejected"):
                    entry["status"] = "rejected"
                    entry["verification"] = "pending"
                    r.audit["reserved"] -= sum(x["cost"] for x in op["inverse"])
                    r.persist()
                    if resource(r, op, "verify-rejected-" + op["label"]) is not None:
                        raise Blocked("Rejected write left a resource; reconciliation needed")
                    entry["verification"] = "absent"
                else:
                    wait_op(r, op, result=result)
                    entry["after"] = verify_op(r, op, "after-" + op["label"])
                    if r.args.phase == "G2":
                        if not props(entry["after"]).get("vmId"):
                            raise Blocked("Created VM identity is not proven")
                        _, compute = ids(r.initial["subscriptionId"])
                        disk = resource(r, {"id": compute + "disks/" + SOURCE_DISK, "compute": True},
                                        "after-source-disk")
                        if disk is None or not props(disk).get("uniqueId"):
                            raise Blocked("Created disk identity is not proven")
                        entry["diskAfter"] = disk
                    entry["status"] = "applied"
                r.persist()
            except BaseException:
                if entry["status"] == "rejected":
                    entry["verification"] = "unknown"
                else:
                    entry["status"] = "unknown"
                r.persist()
                raise
    except BaseException:
        r.state["rollbackErrors"] = rollback(r, entries)
        raise


def guest_script(command, seconds=30, chunk=0):
    # Reuse the prior collector's bounded in-memory transport, not its CLI entry point.
    module = sibling("runtime")
    old = sys.modules.get("runtime")
    sys.modules["runtime"] = module
    try:
        collector = sibling("collect")
    finally:
        if old is None:
            del sys.modules["runtime"]
        else:
            sys.modules["runtime"] = old
    return collector.guest_script(command, seconds, chunk)


def guest(r, label, vm, script, require_success=True):
    data = r.command(label, ["vm", "run-command", "invoke", "-g", RG, "-n", vm,
                             "--command-id", "RunShellScript", "--scripts", script], timeout=300)
    text = "\n".join(x.get("message", "") for x in data.get("value", []))
    if ("UDR_STATUS=0" not in text or any(x.get("code", "").endswith("/failed") for x in data.get("value", []))
            or (require_success and ("COMMAND_STATUS=0" not in text or "OUTPUT_PAGED" in text))):
        raise Blocked("Guest control failed/paged; no repair attempted: " + label)
    return text


def collect(r):
    phase = r.args.phase
    route_results = {}
    if phase in ("collect-subnet", "collect-full", "collect-restored"):
        check_scope(r)
    if phase == "collect-viability":
        nics = r.command("nic-identities", ["network", "nic", "list", "-g", RG])
        save(r.out / "nic-identities.json", nics)
    else:
        # The accepted identity checkpoint remains invariant: intervening phases
        # touch only route entries, peering relationships, and guest reads.
        nics = load(r.out / "nic-identities.json")
    for name, address in zip(NIC_NAMES, IPS):
        nic = named(nics, name)
        if props(props(nic)["ipConfigurations"][0]).get("privateIPAddress") != address:
            raise Blocked("Collector endpoint identity/IP mismatch: " + name)
    for nic in NIC_NAMES:
        data = r.command("routes-" + nic, ["network", "nic", "show-effective-route-table", "-g", RG, "-n", nic])
        rows = list(data.get("value", []))
        seen = set()
        while data.get("nextLink"):
            link = data["nextLink"]
            net, _ = ids(r.initial["subscriptionId"])
            if link in seen or not link.lower().startswith(("https://management.azure.com" + net).lower()):
                raise Blocked("Unsafe/repeated effective-route continuation")
            seen.add(link)
            data = r.command("routes-" + nic + "-page-" + str(len(seen)),
                             ["rest", "--method", "get", "--url", link])
            rows.extend(data.get("value", []))
        route_results[nic] = {"value": rows}
    save(r.out / phase / "route-counts.json",
         {nic: len(data.get("value", [])) for nic, data in route_results.items()})
    if phase == "collect-full":
        for nic, destination, prefix in ((SOURCE_NIC, IPS[3], "10.60.0.0/16"),
                                        ("nic-workload-probe", IPS[0], "10.40.0.0/16")):
            selected = selected_routes(route_results[nic], destination)
            if not selected or any(p != prefix or h.lower() != "vnetpeering" for p, h, _ in selected):
                raise Blocked("Full-peering endpoint route selection is not direct")
    if phase == "collect-return":
        for nic, hop in (("nic-workload-probe", IPS[2]), ("nic-spoke-nva", IPS[1])):
            selected = selected_routes(route_results[nic], IPS[0])
            if not selected or any(p != IPS[0] + "/32" or h != "VirtualAppliance" or hop not in ips
                                   for p, h, ips in selected):
                raise Blocked("Standing return route is not selected")
    if phase in ("collect-vnetlocal", "collect-vnetpeering"):
        group = "G7-add" if phase == "collect-vnetlocal" else "G8-add"
        if any(e["phase"] == group and e["status"] == "rejected" for e in r.state["journal"]):
            return
    if phase in ("collect-viability", "collect-return"):
        for vm, target, gateway in ((VMS[0], IPS[0], "10.40.1.1"), (VMS[1], IPS[3], "10.60.0.1")):
            if phase == "collect-viability":
                command = ["bash", "-c", "set -e; ip route get " + target +
                           "; timeout 12 ping -n -c 5 -W 1 " + target]
            else:
                destination = IPS[0]
                command = ["bash", "-c", "set -e; ip route get " + destination +
                           " | tee /dev/stderr | grep -F 'via " + gateway + "'; "
                           "test \"$(sysctl -n net.ipv4.ip_forward)\" = 1; "
                           "sysctl net.ipv4.conf.all.rp_filter net.ipv4.conf.eth0.rp_filter; "
                           "iptables-save -t filter; iptables-save -t nat"]
            guest(r, "control-" + vm, vm, guest_script(command))
        if phase == "collect-viability":
            guest(r, "source-tools", SOURCE_VM,
                  guest_script(["bash", "-c", "set -e; command -v ping; command -v mtr; "
                                "timeout 12 ping -n -c 5 -W 1 " + IPS[1]]))
            return
        return
    command = ["bash", "-c", "date -u; ip route get " + IPS[3] +
               "; timeout 10 ping -n -c 5 -W 1 " + IPS[3] +
               "; echo PING_STATUS=$?; timeout 18 mtr -n -r -c 5 --max-ttl 8 " + IPS[3] +
               "; echo MTR_STATUS=$?"]
    guest(r, "source-icmp", SOURCE_VM, guest_script(command, 30))


def check_scope(r):
    original = load(r.out / "originals.json")
    net, _ = ids(r.initial["subscriptionId"])
    for vnet, peer in PEERS:
        resource_id = net + "virtualNetworks/" + vnet + "/virtualNetworkPeerings/" + peer
        current = r.command("scope-" + peer, rest("get", resource_id))
        if (props(current).get("peeringState") != "Connected"
                or props(current).get("peeringSyncLevel") not in (None, "FullyInSync")):
            r.command("wait-connected-" + peer, ["resource", "wait", "--ids", resource_id,
                "--api-version", API, "--custom",
                "properties.peeringState=='Connected' && (properties.peeringSyncLevel=='FullyInSync' || properties.peeringSyncLevel==null)",
                "--interval", "30", "--timeout", "120"])
            current = r.command("connected-" + peer, rest("get", resource_id))
        expected = peer_body(named(props(named(original["vnets"], vnet))["virtualNetworkPeerings"], peer),
                             full=r.args.phase == "collect-full")
        if (peer_body(current) != expected or props(current).get("peeringState") != "Connected"
                or props(current).get("peeringSyncLevel") not in (None, "FullyInSync")):
            raise Blocked("Peering is not the exact connected/in-sync checkpoint")


def selected_routes(data, destination):
    found = []
    for route in data.get("value", []):
        if route.get("state", "").lower() != "active":
            continue
        prefixes = route.get("addressPrefix", [])
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        for prefix in prefixes:
            try:
                network = ipaddress.ip_network(prefix)
            except ValueError:
                continue
            if ipaddress.ip_address(destination) in network:
                hops = route.get("nextHopIpAddress", [])
                found.append((network.prefixlen, prefix, route["nextHopType"],
                              [hops] if isinstance(hops, str) else hops))
    longest = max((x[0] for x in found), default=-1)
    return [(p, h, ips) for length, p, h, ips in found if length == longest]


def check_direct_tables(r):
    net, _ = ids(r.initial["subscriptionId"])
    for table, target, expected_count in ((SOURCE_TABLE, IPS[3], 0),
                                          ("rt-spoke-workload", IPS[0], 1),
                                          ("rt-spoke-nva-return", IPS[0], 1)):
        data = r.command("direct-check-" + table, rest("get", net + "routeTables/" + table))
        p = props(data)
        if not p.get("disableBgpRoutePropagation") or len(p.get("routes", [])) != expected_count:
            raise Blocked("Direct baseline table contains unexpected routes/propagation")
        for route in p.get("routes", []):
            prefix = props(route).get("addressPrefix")
            if prefix and prefix != "0.0.0.0/0" and ipaddress.ip_address(target) in ipaddress.ip_network(prefix):
                raise Blocked("More-specific return/forward route masks direct comparison")


def require_phase(state, phase, lease):
    if state["status"] != "active" or state["completed"] != SEQUENCE[:SEQUENCE.index(phase)]:
        raise Blocked("Blocked chain or wrong phase order; no replay or automatic recovery")
    if state["subscriptionId"] != lease["subscriptionId"]:
        raise Blocked("Subscription changed")
    if state["completed"] and lease.get("acceptedCheckpoint") != state["completed"][-1]:
        raise Blocked("Coordinator must explicitly accept preceding checkpoint")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=SEQUENCE)
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True, help="NEW experiment root for inventory; same root thereafter")
    parser.add_argument("--ssh-public-key")
    parser.add_argument("--icmp-priority", type=int)
    parser.add_argument("--plan", action="store_true", help="Pure offline plan; no lease consumption or cloud")
    parser.add_argument("--plan-file", help="Optional local full-command plan; stdout remains under 4KB")
    args = parser.parse_args()
    out = Path(args.out)
    lease = load(args.lease)
    if args.plan and args.phase == "inventory":
        print(json.dumps({"phase": "inventory", "owner": "Niobe", "reads": 8, "mutations": 0}))
        return 0
    state_path = out / "state.json"
    snapshot_path = out / "originals.json"
    if args.phase == "inventory":
        if out.exists():
            raise Blocked("Inventory requires a NEW output root")
        state = {"startedAtUtc": now().isoformat(), "subscriptionId": lease["subscriptionId"],
                 "calls": 0, "mutations": 0, "completed": [], "journal": [], "status": "active"}
        snapshot = None
    else:
        state, snapshot = load(state_path), load(snapshot_path)
        if state["subscriptionId"] != lease["subscriptionId"]:
            raise Blocked("Subscription changed")
    key = Path(args.ssh_public_key).read_text(encoding="utf-8").strip() if args.ssh_public_key else None
    operations = [] if args.phase in ("inventory", "verify") or args.phase.startswith("collect") else plan(
        args.phase, snapshot, state, lease["subscriptionId"], key, args.icmp_priority)
    if args.plan:
        if args.plan_file:
            save(args.plan_file, operations)
        print(json.dumps({"phase": args.phase,
                          "allowedMutations": [x["label"] for op in operations for x in [op, *op["inverse"]]],
                          "forwardCost": sum(x["cost"] for x in operations),
                          "inverseCost": sum(y["cost"] for x in operations for y in x["inverse"])}, indent=2))
        return 0
    require_phase(state, args.phase, lease)
    if args.phase == "G4" and lease.get("icmpPriority") != args.icmp_priority:
        raise Blocked("NSG priority must be explicitly approved in lease")
    out.mkdir(parents=True, exist_ok=True)
    lock = Lock(out / "experiment.lock")
    if state_path.exists() and load(state_path) != state:
        lock.close()
        raise Blocked("Experiment state changed before lock; no stale plan execution")
    r = None
    try:
        r = Transport(args, state)
        save(out / args.phase / "plan.json", operations)
        if args.phase == "inventory":
            snapshot = inventory(r)
            save(snapshot_path, snapshot)
            baseline_check(snapshot)
        elif args.phase == "verify":
            fresh = inventory(r)
            save(out / "final.json", fresh)
            verify_original_identities(snapshot, fresh)
            if stable(fresh) != stable(snapshot):
                raise Blocked("Final original resource/configuration/power comparison differs")
            save(out / "restore-verification.json", {"status": "PASS", "utc": now().isoformat()})
        elif args.phase.startswith("collect"):
            if args.phase in ("collect-subnet", "collect-full", "collect-restored"):
                check_direct_tables(r)
            collect(r)
        else:
            execute(r, operations)
        state["completed"].append(args.phase)
        state["checkpoint"] = args.phase
        state["originalRestored"] = args.phase == "verify"
        if args.phase == "verify":
            state["status"] = "restored"
        r.finish("completed")
        print(json.dumps({"phase": args.phase, "status": "CHECKPOINT", "mutations": r.audit["mutations"],
                          "originalRestored": args.phase == "verify", "out": str(out)}))
        return 0
    except BaseException as exc:
        state["status"] = "blocked"
        state["error"] = str(exc)
        save(state_path, state)
        if r:
            r.finish("blocked")
        print(json.dumps({"status": "BLOCKED", "error": str(exc), "out": str(out)}))
        return 2
    finally:
        lock.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Blocked, KeyError, ValueError, OSError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}))
        sys.exit(2)
