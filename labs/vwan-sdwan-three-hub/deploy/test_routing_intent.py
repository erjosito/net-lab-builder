import copy
import unittest
from unittest.mock import patch

import routing_intent


class RoutingIntentTests(unittest.TestCase):
    def test_new_resources_require_owned_group_and_absent_targets(self):
        with patch.object(routing_intent.sweep, "az", side_effect=[
                routing_intent.control.TAGS, []]):
            routing_intent.assert_owned_deployment_scope()
        with patch.object(routing_intent.sweep, "az", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "ownership tags"):
                routing_intent.assert_owned_deployment_scope()
        with patch.object(routing_intent.sweep, "az", side_effect=[
                routing_intent.control.TAGS,
                [{"name": "fw-jp", "type": "Microsoft.Network/azureFirewalls"}]]):
            with self.assertRaisesRegex(RuntimeError, "overwrite"):
                routing_intent.assert_owned_deployment_scope()

    def test_three_standard_hub_firewalls_and_private_intents(self):
        resources = routing_intent.secured_template()["resources"]
        firewalls = [r for r in resources if r["type"].endswith("/azureFirewalls")]
        intents = [r for r in resources if r["type"].endswith("/routingIntent")]
        self.assertEqual(len(firewalls), 3)
        self.assertEqual(len(intents), 3)
        for fw in firewalls:
            self.assertEqual(fw["properties"]["sku"], {"name": "AZFW_Hub", "tier": "Standard"})
            self.assertEqual(fw["properties"]["hubIPAddresses"]["publicIPs"]["count"], 1)
            self.assertNotIn("ipConfigurations", fw["properties"])
        for intent in intents:
            policies = intent["properties"]["routingPolicies"]
            self.assertEqual(len(policies), 1)
            self.assertEqual(policies[0]["destinations"], ["PrivateTraffic"])
            self.assertIn("azureFirewalls", intent["dependsOn"][0])

    def test_firewall_rule_scope_and_no_private_snat(self):
        resources = routing_intent.secured_template()["resources"]
        policy = resources[0]["properties"]
        self.assertIn("10.0.0.0/8", policy["snat"]["privateRanges"])
        rule = resources[1]["properties"]["ruleCollections"][0]["rules"][0]
        self.assertEqual(rule["sourceAddresses"], routing_intent.PRIVATE_PREFIXES)
        self.assertEqual(rule["destinationAddresses"], routing_intent.PRIVATE_PREFIXES)
        self.assertEqual(rule["destinationPorts"], ["5201"])
        self.assertEqual(rule["ipProtocols"], ["TCP"])
        icmp = resources[1]["properties"]["ruleCollections"][0]["rules"][1]
        self.assertEqual(icmp["ipProtocols"], ["ICMP"])
        self.assertEqual(icmp["destinationPorts"], ["*"])

    def test_actual_firewall_binding_and_policy_required(self):
        fid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/azureFirewalls/fw-eu"
        hub = {"properties": {"azureFirewall": {"id": fid}}}
        firewall = {"properties": {"provisioningState": "Succeeded"}}
        intent = {"value": [{"properties": {"routingPolicies": [
            {"destinations": ["PrivateTraffic"], "nextHop": fid}
        ]}}]}
        routing_intent.assert_secured(hub, intent, firewall, fid)
        for changed in ({}, {"value": []}, copy.deepcopy(intent)):
            if changed.get("value"):
                changed["value"][0]["properties"]["routingPolicies"][0]["destinations"] = ["Internet"]
            with self.assertRaises(RuntimeError):
                routing_intent.assert_secured(hub, changed, firewall, fid)


if __name__ == "__main__":
    unittest.main()
