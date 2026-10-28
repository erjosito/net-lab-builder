import copy
import unittest

from nat_deploy import HERE, Deployment, read, template_gate, whatif_gate


class NatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = read(HERE / "nat-spec.json")
        cls.template = read(HERE / "nat-template.json")

    def test_exact_validated_recipe_and_scope(self):
        template_gate(self.plan, self.template)

    def test_network_or_extra_resource_rejected(self):
        template = copy.deepcopy(self.template)
        template["resources"].append({"type": "Microsoft.Network/virtualNetworks", "name": "hub"})
        with self.assertRaises(AssertionError):
            template_gate(self.plan, template)

    def test_wrong_ip_or_missing_forwarding_rejected(self):
        for field, value in (("enableIPForwarding", False),):
            template = copy.deepcopy(self.template)
            nic = next(r for r in template["resources"] if r["name"] == "vm-spoke1-spoke10-nic")
            nic["properties"][field] = value
            with self.assertRaises(AssertionError):
                template_gate(self.plan, template)

    def test_whatif_requires_only_exact_creates(self):
        changes = [{"resourceId": "/scope/" + t[k], "changeType": "Create"}
                   for t in self.plan["targets"] for k in ("name", "nic")]
        whatif_gate({"status": "Succeeded", "changes": changes}, self.plan)
        for kind in ("Modify", "Delete", "Deploy"):
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                whatif_gate({"status": "Succeeded", "changes": changes + [
                    {"resourceId": "/scope/hub", "changeType": kind}]}, self.plan)

    def test_delete_dispatch_is_always_forbidden(self):
        executor = Deployment.__new__(Deployment)
        executor.check = lambda: None
        for args in (["group", "delete"], ["rest", "--method", "DELETE"]):
            with self.assertRaisesRegex(AssertionError, "Forbidden dispatch"):
                executor.command("forbidden", args)


if __name__ == "__main__":
    unittest.main()
