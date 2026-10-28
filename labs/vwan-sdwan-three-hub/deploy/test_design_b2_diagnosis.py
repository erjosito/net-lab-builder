import unittest
from unittest.mock import patch

import design_b2_diagnosis as diagnosis
import design_backbone as backbone
import infra


class DiagnosisTests(unittest.TestCase):
    def test_workload_evidence_queries_fabric_and_guest_separately(self):
        calls, scripts = [], []

        def azure(args, label):
            calls.append(args)
            return {"properties": {}} if "rest" in args else {"value": []}

        def guest(label, values, marker):
            scripts.extend(values.values())
            return {"probe-dc-jp": {}}

        with patch.object(diagnosis.sweep, "az", side_effect=azure), \
                patch.object(diagnosis.sweep, "save"), \
                patch.object(diagnosis.b2b, "guest_batch", side_effect=guest):
            result = diagnosis.workload_evidence("test")
        self.assertEqual(set(result), {"subnet", "effectiveRoutes", "guest"})
        self.assertIn("rest", calls[0])
        self.assertIn("?api-version=2024-05-01", calls[0][-1])
        self.assertIn("show-effective-route-table", calls[1])
        self.assertIn("nic-probe-dc-jp", calls[1])
        body = scripts[0].split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
        compile(body, "<workload-diagnostic>", "exec")
        self.assertNotIn("ipsec", body)

    def test_measurement_requests_only_dc_azure_traffic(self):
        with patch.object(diagnosis.b2b, "capture", return_value={}) as capture, \
                patch.object(diagnosis, "workload_evidence", return_value={}), \
                patch.object(diagnosis.sweep, "save"):
            diagnosis.measured("test", {}, True)
        capture.assert_called_once_with("test", {}, True, dc_azure_only=True)

    def test_focused_udr_contains_only_spokes_not_mesh_outer_endpoints(self):
        with patch.object(backbone, "UDR_PREFIXES", tuple(infra.SPOKE_PREFIXES)):
            table = backbone.route_table("unused")
        routes = table["properties"]["routes"]
        self.assertEqual(len(routes), 3)
        self.assertEqual({r["properties"]["addressPrefix"] for r in routes}, set(infra.SPOKE_PREFIXES))
        self.assertEqual({r["properties"]["nextHopIpAddress"] for r in routes}, {"10.130.0.4"})
        self.assertNotIn("10.140.0.0/24", {r["properties"]["addressPrefix"] for r in routes})


if __name__ == "__main__":
    unittest.main()
