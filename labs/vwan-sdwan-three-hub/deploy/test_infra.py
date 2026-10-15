import json
import unittest
from unittest.mock import patch

import infra
import control


class InfrastructureTests(unittest.TestCase):
    def gateway_fixture(self):
        return {"id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/vpnGateways/vpngw-jp",
                "location": "japaneast", "tags": {"owner": "jose"},
                "properties": {"provisioningState": "Succeeded", "vpnGatewayScaleUnit": 1,
                    "virtualHub": {"id": "actual-hub"}, "vpnConnections": [],
                    "bgpSettings": {"asn": 65515, "peerWeight": 0, "bgpPeeringAddresses": [
                        {"ipconfigurationId": "actual-generated-b", "defaultBgpIpAddresses": ["10.0.0.5"],
                         "customBgpIpAddresses": [], "tunnelIpAddresses": ["192.0.2.2"]},
                        {"ipconfigurationId": "actual-generated-a", "defaultBgpIpAddresses": ["10.0.0.4"],
                         "customBgpIpAddresses": [], "tunnelIpAddresses": ["192.0.2.1"]}]}}}

    def test_gateway_update_preserves_properties_and_joins_real_ids(self):
        gateway = self.gateway_fixture()
        before = json.dumps(gateway)
        body = infra.vpn_gateway_update(gateway)
        self.assertEqual(json.dumps(gateway), before)
        self.assertNotIn("id", body)
        self.assertEqual(body["tags"], gateway["tags"])
        for key in ("virtualHub", "vpnConnections", "vpnGatewayScaleUnit"):
            self.assertEqual(body["properties"][key], gateway["properties"][key])
        peers = body["properties"]["bgpSettings"]["bgpPeeringAddresses"]
        self.assertEqual({p["ipconfigurationId"]: p["customBgpIpAddresses"] for p in peers},
                         {"actual-generated-a": ["169.254.21.2"],
                          "actual-generated-b": ["169.254.21.6"]})
        document = infra.vpn_bindings(body, "192.0.2.10")
        self.assertEqual(len(document["resources"]), 3)

    def test_live_instances_join_public_and_private_tunnel_addresses(self):
        gateway = self.gateway_fixture()
        properties = gateway["properties"]
        properties["ipConfigurations"] = [
            {"id": "actual-generated-a", "publicIpAddress": "192.0.2.1", "privateIpAddress": "10.0.0.4"},
            {"id": "actual-generated-b", "publicIpAddress": "192.0.2.2", "privateIpAddress": "10.0.0.5"}]
        for peer in properties["bgpSettings"]["bgpPeeringAddresses"]:
            peer["tunnelIpAddresses"].insert(0, peer["defaultBgpIpAddresses"][0])
        body = infra.vpn_gateway_update(gateway)
        self.assertEqual(body["properties"]["ipConfigurations"], properties["ipConfigurations"])
        nsg = infra.vpn_bindings(body, "192.0.2.10")["resources"][2]
        ike = next(rule for rule in nsg["properties"]["securityRules"] if rule["name"] == "jp-ike")
        self.assertEqual(ike["properties"]["sourceAddressPrefixes"], ["192.0.2.1/32", "192.0.2.2/32"])
        properties["ipConfigurations"][0]["id"] = "invented"
        with self.assertRaises(ValueError):
            infra.vpn_gateway_update(gateway)

    def test_gateway_update_rejects_missing_duplicate_or_unready_instances(self):
        for field, value in (("ipconfigurationId", ""), ("ipconfigurationId", "actual-generated-b"),
                             ("tunnelIpAddresses", []), ("tunnelIpAddresses", ["192.0.2.2"])):
            gateway = self.gateway_fixture()
            gateway["properties"]["bgpSettings"]["bgpPeeringAddresses"][1][field] = value
            with self.assertRaises(ValueError):
                infra.vpn_gateway_update(gateway)
        gateway = self.gateway_fixture()
        gateway["properties"]["provisioningState"] = "Updating"
        with self.assertRaises(ValueError):
            infra.vpn_gateway_update(gateway)
        gateway = self.gateway_fixture()
        gateway["properties"]["bgpSettings"]["bgpPeeringAddresses"] = []
        with self.assertRaises(ValueError):
            infra.vpn_gateway_update(gateway)

    def test_gateway_update_uses_rest_full_body_and_counts_mutation(self):
        gateway = self.gateway_fixture()
        lease = {"operations": {}}
        def record(name):
            lease["operations"][name] = {}
        with patch("control.guard", return_value=lease), \
                patch("control.get_network_resource", return_value=gateway), \
                patch("control.save"), patch("control.record_operation", side_effect=record), \
                patch("control.az", return_value={"properties": {"provisioningState": "Updating"}}) as az:
            control.update_vpn_gateway()
        self.assertEqual(az.call_args.args[0][0:3], ["rest", "--method", "put"])
        self.assertIn("@", az.call_args.args[0][-1])
        self.assertTrue(az.call_args.kwargs["mutation"])
        self.assertEqual(lease["operations"]["threehub-vpn-gateway-update"]["resourceKind"], "vpnGateways")

    def test_existing_operation_deadline_cannot_be_reset(self):
        lease = {"operations": {"threehub-vpn-gateway": {"deadlineUtc": "original"}}}
        with patch("control.guard", return_value=lease), patch("control.save") as save:
            with self.assertRaisesRegex(RuntimeError, "must not be reset"):
                control.record_operation("threehub-vpn-gateway")
        save.assert_not_called()

    def test_gateway_update_wait_uses_resource_state_and_existing_deadline(self):
        lease = {"operations": {"threehub-vpn-gateway-update": {
            "resourceKind": "vpnGateways", "deadlineUtc": "2099-01-01T00:00:00Z"}}}
        before = json.dumps(lease)
        with patch("control.guard", return_value=lease), \
                patch("control.get_network_resource", return_value=self.gateway_fixture()), \
                patch("control.az") as az:
            control.wait_deployments(["threehub-vpn-gateway-update"])
        az.assert_not_called()
        self.assertEqual(json.dumps(lease), before)

    def test_gateway_checkpoint_sanitizes_secrets_and_keeps_existing_bindings(self):
        gateway = infra.vpn_gateway_update(self.gateway_fixture())
        gateway.update(id="gateway-id", name="vpngw-jp", type="Microsoft.Network/vpnGateways")
        document = infra.vpn_bindings(gateway, "192.0.2.10")
        site, connection, nsg = document["resources"]
        site["id"] = "site-id"
        for value in (site, connection, nsg):
            value["properties"]["provisioningState"] = "Succeeded"
        link = connection["properties"]["vpnLinkConnections"][0]["properties"]
        link.update(provisioningState="Succeeded", sharedKey="runtime-secret",
                    connectionStatus="Disconnected")
        snapshot = {"bindings": {"connections": ["retained"], "bgpPeers": ["retained"]},
                    "resources": [], "deployments": []}
        lease = {"operations": {name: {} for name in (
            "threehub-vpn-gateway", "threehub-vpn-gateway-update", "threehub-vpn-bindings")},
            "mutationsUsed": 3, "toolCallsUsed": 30}
        with patch("control.guard", return_value=lease), \
                patch("pathlib.Path.read_text", return_value=json.dumps(snapshot)), \
                patch("control.get_network_resource", side_effect=[gateway, site, connection, nsg]), \
                patch("control.az", return_value={"properties": {"provisioningState": "Succeeded"}}), \
                patch("control.account_id", return_value="sub"), patch("control.save") as save:
            control.gateway_checkpoint()
        saved_snapshot = save.call_args_list[-2].args[1]
        self.assertNotIn("runtime-secret", json.dumps(saved_snapshot))
        self.assertTrue(saved_snapshot["infrastructureReady"])
        self.assertEqual(saved_snapshot["bindings"]["connections"], ["retained"])
        self.assertEqual(saved_snapshot["bindings"]["vpnConnection"]["links"][0]["connectionStatus"],
                         "Disconnected")
        self.assertEqual(lease["state"], "completed")
        self.assertFalse(lease["queuedWork"])

    def test_nested_resource_ids_have_separate_names(self):
        self.assertEqual(
            infra.rid("virtualNetworks/virtualNetworkPeerings", "vnet-dc-eu/to-dc-us"),
            "[resourceId('Microsoft.Network/virtualNetworks/virtualNetworkPeerings', 'vnet-dc-eu', 'to-dc-us')]")

    def test_locked_inventory_and_anti_bypass(self):
        with patch("infra.save") as save:
            infra.compute()
        resources = save.call_args.args[1]["resources"]
        types = [x["type"] for x in resources]
        self.assertEqual(types.count("Microsoft.Network/virtualNetworks"), 9)
        self.assertEqual(types.count("Microsoft.Compute/virtualMachines"), 10)
        self.assertEqual(types.count("Microsoft.Network/virtualNetworks/virtualNetworkPeerings"), 26)
        self.assertEqual(types.count("Microsoft.Network/routeTables"), 2)
        self.assertEqual(types.count("Microsoft.Network/publicIPAddresses"), 10)
        self.assertNotIn("Microsoft.Network/virtualHubs/hubVirtualNetworkConnections", types)
        for resource in resources:
            if resource["type"] == "Microsoft.Compute/virtualMachines":
                props = resource["properties"]
                self.assertEqual(props["priority"], "Regular")
                self.assertEqual(props["storageProfile"]["osDisk"]["diskSizeGB"], 30)
                self.assertEqual(props["storageProfile"]["osDisk"]["managedDisk"]["storageAccountType"],
                                 "StandardSSD_LRS")
                self.assertTrue(props["osProfile"]["linuxConfiguration"]["disablePasswordAuthentication"])
                self.assertNotIn("zones", resource)

    def test_base_gateway_and_hub_shape(self):
        with patch("infra.save") as save:
            infra.base()
        resources = save.call_args.args[1]["resources"]
        hubs = [x for x in resources if x["type"] == "Microsoft.Network/virtualHubs"]
        self.assertEqual(len(hubs), 3)
        for hub in hubs:
            self.assertEqual(hub["properties"]["virtualRouterAutoScaleConfiguration"]["minCapacity"], 2)
            self.assertEqual(hub["properties"]["hubRoutingPreference"], "ExpressRoute")
        gateway = resources[-1]["properties"]
        self.assertEqual(gateway["vpnGatewayScaleUnit"], 1)
        self.assertNotIn("bgpPeeringAddresses", gateway["bgpSettings"])

    def test_no_public_management_or_unscoped_ike(self):
        for name, _, ip, router in infra.VMS:
            rules = infra.security_rules(name, ip, router)
            for rule in rules:
                props = rule["properties"]
                if props["direction"] == "Inbound" and props["access"] == "Allow":
                    self.assertNotEqual(props.get("sourceAddressPrefix"), "*")
                    self.assertNotEqual(props.get("sourceAddressPrefix"), "Internet")
                    self.assertNotIn(props.get("destinationPortRange"), ["22", "2222"])
            self.assertEqual(rules[-2]["properties"]["access"], "Deny")
            self.assertEqual(rules[-1]["properties"]["access"], "Deny")

    def test_wireguard_exact_peer_port_pairs_in_both_directions(self):
        for own in infra.ROUTER_IPS:
            rules = infra.security_rules("router-cn", own, True)
            wg = [r["properties"] for r in rules if "wireguard-link-" in r["name"]]
            self.assertEqual(len(wg), 6)
            for index, pair in enumerate(infra.WG_PAIRS):
                if infra.ROUTER_IPS.index(own) not in pair:
                    continue
                peer = next(infra.ROUTER_IPS[i] for i in pair if infra.ROUTER_IPS[i] != own)
                matches = [r for r in wg if r["destinationPortRange"] == str(51821 + index)]
                self.assertEqual({r["direction"] for r in matches}, {"Inbound", "Outbound"})
                for rule in matches:
                    self.assertEqual(rule["sourceAddressPrefix"],
                                     (peer if rule["direction"] == "Inbound" else own) + "/32")
                    self.assertEqual(rule["destinationAddressPrefix"],
                                     (own if rule["direction"] == "Inbound" else peer) + "/32")
                    self.assertLess(rule["priority"], 4000)

    def test_templates_are_json_serializable(self):
        for generate in [infra.base, infra.compute]:
            with patch("infra.save") as save:
                generate()
            json.dumps(save.call_args.args[1])

    def test_no_allow_for_deny_only_platform_dns_tag(self):
        with patch("infra.save") as save:
            infra.compute()
        for resource in save.call_args.args[1]["resources"]:
            if resource["type"] != "Microsoft.Network/networkSecurityGroups":
                continue
            rules = resource["properties"]["securityRules"]
            for rule in rules:
                props = rule["properties"]
                addresses = [props.get("destinationAddressPrefix")]
                addresses += props.get("destinationAddressPrefixes", [])
                addresses += [props.get("sourceAddressPrefix")]
                addresses += props.get("sourceAddressPrefixes", [])
                self.assertFalse(props["access"] == "Allow" and "AzurePlatformDNS" in addresses)
            web = next(rule["properties"] for rule in rules if rule["name"] == "bootstrap-web")
            self.assertEqual(web["destinationAddressPrefix"], "Internet")
            self.assertEqual(web["destinationPortRanges"], ["80", "443"])
            self.assertEqual(rules[-1]["properties"]["access"], "Deny")

    def test_completed_deployment_operation_without_target(self):
        lease = {"operations": {"threehub-compute": {"deadlineUtc": "2099-01-01T00:00:00Z"}}}
        with patch("control.guard", return_value=lease), patch("control.az", side_effect=[
            {"properties": {"provisioningState": "Succeeded"}},
            [{"properties": {"targetResource": None, "provisioningState": "Succeeded"}}],
        ]):
            control.wait_deployments(["threehub-compute"])

    def test_hub_bindings_are_explicit_and_scoped(self):
        hubs = {region: {"virtualRouterAsn": 65515,
                         "virtualRouterIps": ["10.250.0.4", "10.250.0.5"]}
                for region in infra.REGIONS}
        resources = infra.hub_bindings(hubs)["resources"]
        connections = infra.hub_connections()["resources"]
        bgp = [r for r in resources if r["type"].endswith("/bgpConnections")]
        self.assertEqual(len(connections), 5)
        self.assertEqual(len(bgp), 2)
        self.assertFalse(any(r["type"].endswith("/hubVirtualNetworkConnections") for r in resources))
        for connection in connections:
            self.assertNotIn("dc-", connection["properties"]["remoteVirtualNetwork"]["id"])
            self.assertEqual(connection["properties"]["routingConfiguration"]
                             ["propagatedRouteTables"]["labels"], ["Default"])
        for peer in bgp:
            self.assertEqual(peer["properties"]["hubVirtualNetworkConnection"]["id"].count(", "), 2)
        hubs["eu"]["virtualRouterIps"] = []
        with self.assertRaises(ValueError):
            infra.hub_bindings(hubs)

    def test_gateway_only_has_no_base_dependencies(self):
        resources = infra.vpn_gateway()["resources"]
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["type"], "Microsoft.Network/vpnGateways")
        self.assertNotIn("dependsOn", resources[0])
        self.assertNotIn("bgpPeeringAddresses", resources[0]["properties"]["bgpSettings"])

    def test_connection_phase_does_not_require_bgp_ips(self):
        document = infra.hub_connections()
        self.assertEqual(len(document["resources"]), 5)
        self.assertNotIn("bgpConnections", json.dumps(document))
        with patch("control.discover_hubs", return_value={
            region: {"properties": {"routingState": "Provisioned", "virtualRouterIps": []}}
            for region in infra.REGIONS
        }), patch("control.submit_template") as submit:
            control.deploy_connections()
        self.assertEqual(submit.call_args.args, ("threehub-connections", document))

    def test_bgp_refuses_unfinished_connections(self):
        with patch("control.az", return_value={"properties": {"provisioningState": "Running"}}), \
                patch("control.discover_hubs") as discover:
            with self.assertRaisesRegex(RuntimeError, "connections must succeed"):
                control.deploy_bindings()
            discover.assert_not_called()

    def test_live_get_uses_exact_child_resource_path(self):
        with patch("control.az", return_value={}) as az, patch("control.account_id", return_value="sub"):
            control.get_network_resource("virtualHubs", "hub-eu/bgpConnections/bgp-router-eu", "proof")
        self.assertEqual(az.call_args.args[0][4],
                         "https://management.azure.com/subscriptions/sub/resourceGroups/"
                         "rg-vwan-sdwan-threehub-20261014/providers/Microsoft.Network/"
                         "virtualHubs/hub-eu/bgpConnections/bgp-router-eu?api-version=2024-05-01")

    def test_dynamic_bgp_nsg_preserves_private_overlay(self):
        hubs = {r: {"properties": {"virtualRouterAsn": 65515,
                 "virtualRouterIps": ["10.250.0.69", "10.250.0.70"]}} for r in ("eu", "us")}
        for resource in infra.hub_bindings(hubs)["resources"]:
            if resource["type"] != "Microsoft.Network/networkSecurityGroups":
                continue
            rules = resource["properties"]["securityRules"]
            self.assertEqual(sum(r["name"].startswith("wireguard-link-") for r in rules), 3)
            self.assertEqual(sum(r["name"].startswith("out-wireguard-link-") for r in rules), 3)
            self.assertNotIn("AzurePlatformDNS", json.dumps(rules))
            bgp = next(r for r in rules if r["name"] == "hub-bgp")
            self.assertEqual(bgp["properties"]["sourceAddressPrefixes"],
                             ["10.250.0.69/32", "10.250.0.70/32"])
            self.assertEqual(rules[-1]["properties"]["access"], "Deny")

    def test_vpn_binding_joins_custom_addresses_not_array_order(self):
        gateway = {"properties": {"provisioningState": "Succeeded", "bgpSettings": {
            "bgpPeeringAddresses": [
                {"ipconfigurationId": "live-instance-1",
                 "customBgpIpAddresses": ["169.254.21.6"], "tunnelIpAddresses": ["192.0.2.2"]},
                {"ipconfigurationId": "live-instance-0",
                 "customBgpIpAddresses": ["169.254.21.2"], "tunnelIpAddresses": ["192.0.2.1"]}]}}}
        document = infra.vpn_bindings(gateway, "192.0.2.10")
        site, connection, nsg = document["resources"]
        self.assertEqual(len(site["properties"]["vpnSiteLinks"]), 1)
        self.assertEqual(site["properties"]["vpnSiteLinks"][0]["properties"]
                         ["bgpProperties"]["bgpPeeringAddress"], "169.254.21.1")
        link = connection["properties"]["vpnLinkConnections"][0]["properties"]
        self.assertEqual([x["ipConfigurationId"] for x in link["vpnGatewayCustomBgpAddresses"]],
                         ["live-instance-0", "live-instance-1"])
        self.assertEqual(link["sharedKey"], "[parameters('vpnSharedKey')]")
        self.assertEqual(document["parameters"]["vpnSharedKey"]["type"], "secureString")
        ike = next(r["properties"] for r in nsg["properties"]["securityRules"] if r["name"] == "jp-ike")
        self.assertEqual(ike["sourceAddressPrefixes"], ["192.0.2.1/32", "192.0.2.2/32"])
        gateway["properties"]["bgpSettings"]["bgpPeeringAddresses"][0]["customBgpIpAddresses"] = []
        with self.assertRaises(ValueError):
            infra.vpn_bindings(gateway, "192.0.2.10")


if __name__ == "__main__":
    unittest.main()
