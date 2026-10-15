import copy
import unittest

import control
import direct_action_mesh as mesh
import guest
import infra


class DirectActionTests(unittest.TestCase):
    def fixture(self):
        return [{"name": f"nsg-router-{site}", "location": "japaneast",
                 "tags": dict(control.TAGS),
                 "properties": {"securityRules": [
                     infra.rule("keep-existing", 1000, "Udp", ["10.0.0.1/32"],
                                ["10.0.0.2/32"], ["4500"]),
                     infra.rule("deny-other", 4000, "*", ["*"], ["*"], ["*"], access="Deny"),
                 ]}} for site in guest.SITES]

    def test_preserves_existing_rules_and_uses_free_priorities(self):
        actual = self.fixture()
        before = copy.deepcopy(actual)
        document, diffs = mesh.nsg_document(actual)
        self.assertEqual(actual, before)
        self.assertEqual(len(document["resources"]), 4)
        for resource in document["resources"]:
            rules = resource["properties"]["securityRules"]
            self.assertEqual(rules[:2], before[0]["properties"]["securityRules"])
            added = rules[2:]
            self.assertEqual(len(added), 6)
            self.assertTrue(all(r["properties"]["priority"] < 4000 for r in added))
            self.assertTrue(all(r["properties"]["sourceAddressPrefix"].endswith("/32") for r in added))
            self.assertTrue(all(r["properties"]["destinationAddressPrefix"].endswith("/32") for r in added))
        self.assertEqual(set(diffs), set(guest.SITES))

    def test_refuses_unowned_resources(self):
        actual = self.fixture()
        actual[0]["tags"]["run_id"] = "other-lab"
        with self.assertRaisesRegex(RuntimeError, "unowned"):
            mesh.nsg_document(actual)

    def test_azure_empty_array_normalization_is_not_a_rule_change(self):
        original = self.fixture()[0]["properties"]["securityRules"]
        returned = copy.deepcopy(original)
        for rule in returned:
            rule["properties"].update(sourceAddressPrefixes=[], destinationPortRanges=[],
                                      provisioningState="Succeeded")
        self.assertEqual(mesh.canonical_rules(original), mesh.canonical_rules(returned))
        returned[0]["properties"]["destinationPortRange"] = "51820"
        self.assertNotEqual(mesh.canonical_rules(original), mesh.canonical_rules(returned))

    def test_transport_migration_does_not_restart_services(self):
        script = mesh.guest_script("jp", "apply", {})
        self.assertNotIn("systemctl restart", script)
        self.assertNotIn("wg-quick down", script)
        self.assertNotIn("wg-quick up", script)
        self.assertNotIn("swanctl --load", script)
        self.assertIn("os.chown(n,s.st_uid,s.st_gid)", script)
        self.assertIn("assert identity(bird)==before", script)


if __name__ == "__main__":
    unittest.main()
