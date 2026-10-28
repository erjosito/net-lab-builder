import unittest
from unittest.mock import patch

import propagation_repair as repair


class PropagationRepairTests(unittest.TestCase):
    def test_label_change_preserves_routing_properties_and_serializes_each_hub(self):
        collections = [{"value": [
            dict(name=f"connection-{n}", id=f"actual-id-{site}-{n}", properties={
                "remoteVirtualNetwork": {"id": "actual-vnet"},
                "allowHubToRemoteVnetTransit": True,
                "allowRemoteVnetToUseHubVnetGateways": False,
                "enableInternetSecurity": False, "provisioningState": "Succeeded",
                "routingConfiguration": {
                    "associatedRouteTable": {"id": "actual-table"},
                    "propagatedRouteTables": {"labels": ["Default"], "ids": [{"id": "actual-table"}]}
                }
            }) for n in range(2 if site != "jp" else 1)
        ]} for site in ("eu", "us", "jp")]
        original = repair.connection_resources(collections)
        changed = repair.connection_resources(collections, "default")
        self.assertEqual(len(changed), 5)
        self.assertEqual(original[0]["properties"]["routingConfiguration"]
                         ["propagatedRouteTables"]["labels"], ["Default"])
        for resource in changed:
            self.assertEqual(resource["properties"]["routingConfiguration"]
                             ["propagatedRouteTables"]["labels"], ["default"])
            self.assertNotIn("provisioningState", resource["properties"])
            self.assertIs(resource["properties"]["allowHubToRemoteVnetTransit"], True)
            self.assertIs(resource["properties"]["allowRemoteVnetToUseHubVnetGateways"], False)
        self.assertNotIn("dependsOn", changed[0])
        self.assertEqual(changed[1]["dependsOn"], ["actual-id-eu-0"])
        self.assertNotIn("dependsOn", changed[2])

    def test_vpn_update_only_sets_labels_and_filters_secret_bearing_output(self):
        with patch.object(repair.sweep, "az") as az:
            repair.vpn_labels(["default"], "test")
        args = az.call_args.args[0]
        self.assertEqual(args[args.index("--labels") + 1], "default")
        self.assertEqual(args[args.index("--query") + 1], "routingConfiguration")
        self.assertNotIn("--shared-key", args)
        self.assertTrue(az.call_args.kwargs["mutation"])


if __name__ == "__main__":
    unittest.main()
