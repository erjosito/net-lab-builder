"""Pure offline tests: all persistence and process transport are mocked."""
import ast
import copy
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import runner
import transport


SUB = "00000000-0000-0000-0000-000000000000"


def fixture():
    net, compute = runner.ids(SUB)
    nsgs, subnets = [], {}
    for role, vnet, subnet, prefix, table in (
            ("hub-nva", "vnet-hub", "snet-hub-nva", "10.40.1.0/27", None),
            ("spoke-nva", "vnet-sap-rise", "snet-spoke-nva", "10.60.0.0/27", "rt-spoke-nva-return"),
            ("workload-probe", "vnet-sap-rise", "snet-workload", "10.60.1.0/24", "rt-spoke-workload")):
        nsg = {"name": "nsg-" + role, "id": net + "networkSecurityGroups/nsg-" + role,
               "properties": {"securityRules": []}}
        nsgs.append(nsg)
        p = {"addressPrefix": prefix, "networkSecurityGroup": {"id": nsg["id"]}}
        if table:
            p["routeTable"] = {"id": net + "routeTables/" + table}
        subnets.setdefault(vnet, []).append({"name": subnet,
            "id": net + "virtualNetworks/" + vnet + "/subnets/" + subnet, "properties": p})
    vnets = []
    for i, (vnet, peer) in enumerate(runner.PEERS):
        other = runner.PEERS[1-i][0]
        p = {"peerCompleteVnets": False, "allowVirtualNetworkAccess": True,
             "allowForwardedTraffic": True, "allowGatewayTransit": False, "useRemoteGateways": False,
             "localSubnetNames": [["snet-hub-nva"], ["snet-spoke-nva"]][i],
             "remoteSubnetNames": [["snet-spoke-nva"], ["snet-hub-nva"]][i],
             "remoteVirtualNetwork": {"id": net + "virtualNetworks/" + other},
             "peeringState": "Connected", "peeringSyncLevel": "FullyInSync",
             "remoteAddressSpace": {"addressPrefixes": ["read-only"]}}
        vnets.append({"name": vnet, "id": net + "virtualNetworks/" + vnet, "properties": {
            "addressSpace": {"addressPrefixes": ["10.40.0.0/16" if i == 0 else "10.60.0.0/16"]},
            "subnets": subnets[vnet], "virtualNetworkPeerings": [
                {"name": peer, "id": net + "virtualNetworks/" + vnet + "/virtualNetworkPeerings/" + peer,
                 "properties": p}]}})
    tables = []
    for name, prefix, hop in (("rt-spoke-nva-return", "172.40.100.0/24", "10.40.1.4"),
                               ("rt-spoke-workload", "0.0.0.0/0", "10.60.0.4")):
        tables.append({"name": name, "id": net + "routeTables/" + name, "properties": {
            "disableBgpRoutePropagation": True, "routes": [{"name": "original", "properties": {
                "addressPrefix": prefix, "nextHopType": "VirtualAppliance", "nextHopIpAddress": hop}}]}})
    vms = [{"name": n, "id": compute + "virtualMachines/" + n, "properties": {
        "networkProfile": {"networkInterfaces": [{"id": net + "networkInterfaces/" + n.replace("vm-", "nic-")}]},
        "storageProfile": {"osDisk": {"managedDisk": {"id": compute + "disks/disk-" + n}}}}}
        for n in [*runner.VMS, "vm-ce"]]
    nics = [{"name": n.replace("vm-", "nic-"), "id": net + "networkInterfaces/" + n.replace("vm-", "nic-"),
             "properties": {"enableIPForwarding": n in runner.VMS[:2]}} for n in [*runner.VMS, "vm-ce"]]
    for nic, ip, vnet, subnet in zip(nics, runner.IPS[1:], ["vnet-hub", "vnet-sap-rise", "vnet-sap-rise"],
                                    ["snet-hub-nva", "snet-spoke-nva", "snet-workload"]):
        nic["properties"]["ipConfigurations"] = [{"properties": {"privateIPAddress": ip,
            "subnet": {"id": net + "virtualNetworks/" + vnet + "/subnets/" + subnet}}}]
    return {"vnets": vnets, "nsgs": nsgs, "tables": tables, "vms": vms, "nics": nics,
            "disks": [{"name": "disk-" + vm["name"], "id": compute + "disks/disk-" + vm["name"]} for vm in vms],
            "resources": [], "power": [{"name": n["name"], "powerState": "VM deallocated"} for n in vms]}


class FakeRuntime:
    def __init__(self, phase, state=None):
        self.args = SimpleNamespace(phase=phase)
        self.state = state or {"journal": []}
        self.audit = {"reserved": 0}
        self.initial = {"subscriptionId": SUB, "taskId": "offline", "restoreTimeoutMinutes": 5}
        self.calls = []
        self.fail = None
        self.reject = False
        self.current = {}
        self.out = Path("unused-offline-output")

    def persist(self):
        pass

    def authorize(self, operations):
        self.audit["reserved"] = sum(x["cost"] for op in operations for x in op["inverse"])

    def command(self, label, argv, **kwargs):
        self.calls.append((label, argv, kwargs))
        if label == self.fail:
            raise transport.Blocked("injected failure")
        if kwargs.get("trial") and self.reject:
            return {"_rejected": True}
        if argv[0] == "rest":
            method = argv[argv.index("--method")+1]
            resource_id = argv[argv.index("--url")+1].split("management.azure.com")[1].split("?")[0]
            if method == "get":
                return {"value": [v for k, v in self.current.items() if k.rsplit("/", 1)[0] == resource_id]}
            if method == "delete":
                self.current.pop(resource_id, None)
            elif method == "put":
                body = json.loads(argv[argv.index("--body")+1])
                self.current[resource_id] = dict(body, id=resource_id, name=resource_id.rsplit("/", 1)[1])
        return {}


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture()
        self.state = {"journal": []}

    def plan(self, phase, priority=100):
        return runner.plan(phase, self.snapshot, self.state, SUB, "ssh-ed25519 AAAA offline", priority)

    def test_syntax_and_no_cloud_on_import(self):
        for file in Path(__file__).parent.glob("*.py"):
            ast.parse(file.read_text(encoding="utf-8"))

    def test_original_baseline_guards(self):
        runner.baseline_check(self.snapshot)
        self.snapshot["power"][0]["powerState"] = "VM running"
        with self.assertRaises(transport.Blocked):
            runner.baseline_check(self.snapshot)

    def test_all_group_budgets_and_successful_total(self):
        total = 0
        for phase in runner.SEQUENCE:
            if not phase.startswith("G"):
                continue
            operations = self.plan(phase)
            forward = sum(x["cost"] for x in operations)
            inverse = sum(y["cost"] for x in operations for y in x["inverse"])
            self.assertLessEqual(forward, 3, phase)
            self.assertLessEqual(forward + inverse, 6, phase)
            total += forward
            self.state["journal"].extend(dict(x, phase=phase, status="applied") for x in operations)
        self.assertEqual(total, 40)

    def test_source_network_is_atomic_three_resource_plan(self):
        ops = self.plan("G1")
        self.assertEqual(len(ops), 3)
        self.assertTrue(ops[0]["body"]["properties"]["disableBgpRoutePropagation"])
        p = ops[1]["body"]["properties"]
        self.assertEqual(p["addressPrefix"], "10.40.2.0/27")
        self.assertTrue(p["routeTable"]["id"].endswith("/rt-enforcement-source"))
        self.assertTrue(p["networkSecurityGroup"]["id"].endswith("/nsg-hub-nva"))
        self.assertEqual(ops[2]["body"]["properties"]["ipConfigurations"][0]["properties"]["privateIPAddress"], "10.40.2.4")
        self.assertNotIn("publicIP", json.dumps(ops))

    def test_vm_cost_image_disk_and_no_deployment(self):
        op = self.plan("G2")[0]
        self.assertEqual(op["cost"], 2)
        self.assertEqual(len(op["inverse"]), 2)
        p = op["body"]["properties"]
        self.assertEqual(p["hardwareProfile"]["vmSize"], "Standard_B2ts_v2")
        self.assertEqual(p["storageProfile"]["osDisk"]["name"], runner.SOURCE_DISK)
        self.assertEqual(p["storageProfile"]["imageReference"]["sku"], "22_04-lts-gen2")
        self.assertIn("600", op["wait"])
        self.assertEqual(op["argv"][:3], ["rest", "--method", "put"])
        self.assertIn("api-version=2024-03-02", op["inverse"][1]["argv"][4])

    def test_power_order_and_timeout(self):
        ops = self.plan("G3")
        self.assertEqual([x["id"].rsplit("/", 1)[1] for x in ops], runner.VMS)
        self.assertTrue(all(x["timeout"] == 600 for x in ops))
        self.assertNotIn("--no-wait", json.dumps(ops))

    def test_nsg_priority_and_actual_names(self):
        with self.assertRaises(transport.Blocked):
            self.plan("G4", 90)
        ops = self.plan("G4")
        self.assertTrue(ops[2]["id"].endswith("/nsg-workload-probe/securityRules/" + runner.RULE))
        for op in ops:
            p = op["body"]["properties"]
            self.assertEqual(p["protocol"], "Icmp")
            self.assertEqual(p["sourceAddressPrefixes"], [x + "/32" for x in runner.IPS])

    def test_trials_are_service_rest_and_distinct(self):
        for phase, hop in (("G6-add", "VirtualAppliance"), ("G7-add", "VnetLocal"), ("G8-add", "VNetPeering")):
            op = self.plan(phase)[0]
            self.assertEqual(op["body"]["properties"]["nextHopType"], hop)
            self.assertIn("api-version=2025-01-01", op["argv"][4])
            self.assertTrue(op["id"].endswith("/enforcement-" + phase[:2].lower()))
            if phase != "G6-add":
                self.assertNotIn("nextHopIpAddress", op["body"]["properties"])

    def test_full_peering_drops_only_subnet_scope_and_runtime(self):
        original = runner.props(self.snapshot["vnets"][0])["virtualNetworkPeerings"][0]
        full = runner.peer_body(original, full=True)["properties"]
        self.assertTrue(full["peerCompleteVnets"])
        self.assertNotIn("localSubnetNames", full)
        self.assertNotIn("remoteSubnetNames", full)
        self.assertNotIn("remoteAddressSpace", full)
        self.assertNotIn("peeringState", full)
        for name in ("allowVirtualNetworkAccess", "allowForwardedTraffic", "allowGatewayTransit", "useRemoteGateways"):
            self.assertEqual(full[name], original["properties"][name])
        self.assertEqual(self.plan("G10")[0]["inverse"][0]["body"], runner.peer_body(original))
        self.assertEqual(self.plan("G12")[0]["body"], runner.peer_body(original))

    def test_journal_success_and_own_group_rollback(self):
        r = FakeRuntime("G1")
        r.fail = "G1:nic"
        with self.assertRaises(transport.Blocked):
            runner.execute(r, self.plan("G1"))
        self.assertEqual([x["status"] for x in r.state["journal"]], ["restored", "restored", "unknown"])
        mutations = [x[0] for x in r.calls if x[2].get("cost")]
        self.assertEqual(mutations, ["G1:table", "G1:subnet", "G1:nic", "undo:G1:subnet", "undo:G1:table"])
        self.assertFalse(r.current)
        self.assertTrue(all("before" in x and "inverse" in x for x in r.state["journal"]))

    def test_failure_does_not_rollback_prior_checkpoint(self):
        r = FakeRuntime("G1")
        prior = {"phase": "older", "status": "applied", "label": "untouched", "inverse": []}
        r.state["journal"].append(prior)
        r.fail = "G1:subnet"
        with self.assertRaises(transport.Blocked):
            runner.execute(r, self.plan("G1"))
        self.assertEqual(prior["status"], "applied")
        self.assertNotIn("rollback", prior)

    def test_rejected_trial_is_counted_but_not_unknown_or_deleted(self):
        r = FakeRuntime("G8-add")
        r.reject = True
        runner.execute(r, self.plan("G8-add"))
        self.assertEqual(r.state["journal"][0]["status"], "rejected")
        self.assertEqual(sum(x[2].get("cost", 0) for x in r.calls), 1)
        self.assertEqual(r.audit["reserved"], 0)
        ops = runner.plan("G8-remove", self.snapshot, r.state, SUB)
        self.assertEqual(ops, [])

    def test_accepted_trial_has_separate_cleanup(self):
        r = FakeRuntime("G7-add")
        runner.execute(r, self.plan("G7-add"))
        self.assertEqual(r.state["journal"][0]["status"], "applied")
        self.assertEqual(len(r.current), 1)
        r.args.phase = "G7-remove"
        runner.execute(r, runner.plan("G7-remove", self.snapshot, r.state, SUB))
        self.assertFalse(r.current)

    def test_rejection_remains_known_when_absence_read_fails(self):
        r = FakeRuntime("G8-add")
        r.reject = True
        r.fail = "verify-rejected-G8-add:route"
        with self.assertRaises(transport.Blocked):
            runner.execute(r, self.plan("G8-add"))
        self.assertEqual(r.state["journal"][0]["status"], "rejected")
        self.assertEqual(r.state["journal"][0]["verification"], "unknown")

    def test_before_drift_never_submits(self):
        r = FakeRuntime("G1")
        op = self.plan("G1")[0]
        r.current[op["id"]] = dict(op["body"], id=op["id"])
        with self.assertRaises(transport.Blocked):
            runner.execute(r, [op])
        self.assertFalse(any(x[2].get("cost") for x in r.calls))

    def test_explicit_rejection_is_not_cli_or_network_error(self):
        self.assertTrue(transport.explicit_rejection('ERROR: Bad Request({"error":{"code":"InvalidRoute"}})'))
        for error in ("ERROR: invalid choice: VNetPeering", "connection reset", "AuthorizationFailed",
                      "Gateway Timeout", "HTTP 503", "Bad Request from an unrelated proxy"):
            self.assertFalse(transport.explicit_rejection(error))

    def test_final_comparison_keeps_power_ids_and_disk_sku(self):
        a = {"powerState": "VM deallocated", "storageAccountType": "StandardSSD_LRS", "id": "original"}
        for key, value in (("powerState", "VM running"), ("storageAccountType", "Premium_LRS"), ("id", "replacement")):
            b = dict(a, **{key: value})
            self.assertNotEqual(runner.stable(a), runner.stable(b))
        self.assertEqual(runner.stable(dict(a, etag="1")), runner.stable(dict(a, etag="2")))
        self.assertNotEqual(runner.stable({"vmId": "a"}), runner.stable({"vmId": "b"}))

    def test_original_nic_identity_cannot_be_hidden_by_runtime_normalization(self):
        original = self.snapshot
        original["nics"][0]["properties"]["resourceGuid"] = "original-nic"
        fresh = copy.deepcopy(original)
        runner.verify_original_identities(original, fresh)
        fresh["nics"][0]["properties"]["resourceGuid"] = "replacement-nic"
        with self.assertRaises(transport.Blocked):
            runner.verify_original_identities(original, fresh)

    def test_state_sequence_acceptance_and_blocked_chain(self):
        state = {"status": "active", "completed": ["inventory"], "subscriptionId": SUB}
        lease = {"subscriptionId": SUB, "acceptedCheckpoint": "inventory"}
        runner.require_phase(state, "G1", lease)
        with self.assertRaises(transport.Blocked):
            runner.require_phase(state, "G2", lease)
        lease["acceptedCheckpoint"] = "wrong"
        with self.assertRaises(transport.Blocked):
            runner.require_phase(state, "G1", lease)
        lease["acceptedCheckpoint"] = "inventory"
        state["status"] = "blocked"
        with self.assertRaises(transport.Blocked):
            runner.require_phase(state, "G1", lease)

    def test_effective_route_selection_rejects_masking_route(self):
        data = {"value": [{"state": "Active", "addressPrefix": ["10.60.0.0/16"],
                           "nextHopType": "VNetPeering"},
                          {"state": "Active", "addressPrefix": ["10.60.1.4/32"],
                           "nextHopType": "VirtualAppliance", "nextHopIpAddress": ["10.60.0.4"]}]}
        self.assertEqual(runner.selected_routes(data, "10.60.1.4")[0][0], "10.60.1.4/32")

    def test_guard_stop_expiry_owner_scope_and_eighty_percent(self):
        now = transport.now()
        lease = {"taskId": "offline", "phase": "G1", "ownerRole": "Tank", "subscriptionId": SUB,
                 "state": "active", "startedAtUtc": now.isoformat(),
                 "expiresAtUtc": (now + dt.timedelta(minutes=15)).isoformat(),
                 "maxToolCalls": 25, "maxMutations": 6, "commandTimeoutSeconds": 600,
                 "restoreTimeoutMinutes": 5}
        r = transport.Transport.__new__(transport.Transport)
        r.args = SimpleNamespace(phase="G1")
        r.owner, r.initial, r.lease_path = "Tank", copy.deepcopy(lease), Path("unused.json")
        r.state = {"startedAtUtc": now.isoformat(), "calls": 0}
        r.audit = {"calls": 0, "mutations": 0}
        with patch("transport.load", return_value=lease), patch.object(Path, "exists", return_value=False):
            r.guard()
            r.audit["calls"] = 20
            with self.assertRaises(transport.Blocked):
                r.guard()
            r.guard(closing=True)
            r.audit["calls"] = 0
            lease["state"] = "stop-requested"
            with self.assertRaises(transport.Blocked):
                r.guard(closing=True)
            lease["state"] = "active"
            with patch.object(Path, "exists", return_value=True), self.assertRaises(transport.Blocked):
                r.guard()
            lease["ownerRole"] = "Niobe"
            with self.assertRaises(transport.Blocked):
                r.guard()
            lease["ownerRole"] = "Tank"
            with patch("transport.now", return_value=now + dt.timedelta(minutes=16)), self.assertRaises(transport.Blocked):
                r.guard()

    def test_authorization_reserves_every_inverse_and_calls(self):
        r = transport.Transport.__new__(transport.Transport)
        r.audit = {"calls": 0}
        r.state = {"mutations": 0}
        r.persist = Mock()
        ops = self.plan("G1")
        labels = [x["label"] for op in ops for x in [op, *op["inverse"]]]
        lease = {"allowedMutations": labels, "maxMutations": 6, "maxToolCalls": 25}
        with patch.object(r, "guard", return_value=lease):
            r.authorize(ops)
            self.assertEqual(r.audit["reserved"], 3)
            lease["maxToolCalls"] = 20
            with self.assertRaises(transport.Blocked):
                r.authorize(ops)
            lease["maxToolCalls"] = 25
            lease["allowedMutations"] = labels[:-1]
            with self.assertRaises(transport.Blocked):
                r.authorize(ops)

    def test_bounded_guest_output_default_icmp_and_no_persistent_jobs(self):
        script = runner.guest_script(["ping", "-c", "5", "10.60.1.4"])
        self.assertIn("2800", script)
        self.assertIn("timeout=30", script)
        self.assertIn("killpg", script)
        self.assertNotIn("nohup", script)

    def transport_stub(self):
        r = transport.Transport.__new__(transport.Transport)
        r.args = SimpleNamespace(phase="G8-add")
        r.owner, r.out, r.az = "Tank", Path("unused-offline-output"), ["never-execute"]
        r.state = {"calls": 0, "mutations": 0}
        r.audit = {"calls": 0, "mutations": 0, "forward": 0, "reserved": 1}
        r.persist = Mock()
        lease = {"allowedMutations": ["trial", "undo"], "subscriptionId": SUB,
                 "maxMutations": 6, "commandTimeoutSeconds": 600,
                 "expiresAtUtc": (transport.now() + dt.timedelta(minutes=15)).isoformat()}
        r.guard = Mock(return_value=lease)
        return r

    def test_transport_records_service_rejection_and_reserves_count(self):
        r = self.transport_stub()
        process = Mock(pid=123, returncode=1)
        process.communicate.return_value = ("", 'ERROR: Bad Request({"error":{"code":"InvalidRoute"}})')
        written = []
        with patch("transport.subprocess.Popen", return_value=process) as popen, \
                patch("transport.save", side_effect=lambda path, value: written.append(copy.deepcopy(value))):
            result = r.command("trial", ["rest", "--method", "put"], cost=1, trial=True)
        self.assertTrue(result["_rejected"])
        self.assertEqual(r.state["mutations"], 1)
        self.assertEqual(r.audit["forward"], 1)
        self.assertEqual(written[-1]["status"], "rejected")
        self.assertEqual(written[-1]["httpStatus"], 400)
        self.assertEqual(popen.call_count, 1)
        self.assertNotIn("shell", popen.call_args.kwargs)

    def test_transport_authorization_and_ceiling_before_process(self):
        r = self.transport_stub()
        with patch("transport.subprocess.Popen") as popen, patch("transport.save"):
            with self.assertRaises(transport.Blocked):
                r.command("unapproved", [], cost=1)
            r.state["mutations"] = 48
            with self.assertRaises(transport.Blocked):
                r.command("trial", [], cost=1)
            popen.assert_not_called()
            self.assertEqual(r.audit["mutations"], 0)

    def test_timeout_kills_only_specific_child_and_records_unknown(self):
        r = self.transport_stub()
        process = Mock(pid=12345)
        process.poll.return_value = None
        process.communicate.return_value = ("partial", "timeout")
        written = []
        with patch("transport.subprocess.Popen", return_value=process), \
                patch("transport.subprocess.run") as terminate, \
                patch("transport.os.killpg", create=True) as killpg, \
                patch("transport.time.monotonic", side_effect=[0, 121]), \
                patch("transport.save", side_effect=lambda path, value: written.append(copy.deepcopy(value))):
            with self.assertRaises(TimeoutError):
                r.command("trial", [], cost=1, timeout=120)
        if transport.os.name == "nt":
            self.assertIn("12345", terminate.call_args.args[0][-1])
            self.assertEqual(terminate.call_args.kwargs["timeout"], 10)
        else:
            self.assertEqual(killpg.call_args.args[0], 12345)
        self.assertEqual(written[-1]["status"], "unknown")
        self.assertEqual(written[-1]["stdout"], "partial")
        self.assertEqual(r.state["mutations"], 1)

    def test_successful_put_can_skip_redundant_wait(self):
        r = FakeRuntime("G1")
        runner.wait_op(r, self.plan("G1")[0], result={"properties": {"provisioningState": "Succeeded"}})
        self.assertEqual(r.calls, [])


if __name__ == "__main__":
    unittest.main()
