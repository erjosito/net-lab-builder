import unittest

import hub_transit


class HubTransitTests(unittest.TestCase):
    def test_remote_control_ignores_local_and_unrelated_prefixes(self):
        values = [{"value": [{"addressPrefixes": [
            "10.10.0.0/24", "10.20.0.0/24", "10.30.0.0/24", "10.140.0.0/24"
        ]}]} for _ in range(3)]
        self.assertEqual(hub_transit.remote_spokes(values), {
            "eu": ["10.20.0.0/24", "10.30.0.0/24"],
            "us": ["10.10.0.0/24", "10.30.0.0/24"],
            "jp": ["10.10.0.0/24", "10.20.0.0/24"],
        })


if __name__ == "__main__":
    unittest.main()
