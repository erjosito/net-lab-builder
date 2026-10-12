import json
import unittest

from transport import explicit_rejection
from runner import stable


class ServiceRejectionTests(unittest.TestCase):
    def test_disk_ownership_timestamp_casing_is_service_metadata(self):
        before = {"properties": {"uniqueId": "same", "LastOwnershipUpdateTime": "before"}}
        after = {"properties": {"uniqueId": "same", "LastOwnershipUpdateTime": "after"}}
        self.assertEqual(stable(before), stable(after))
        after["properties"]["uniqueId"] = "replaced"
        self.assertNotEqual(stable(before), stable(after))

    def test_structured_enum_rejection_without_http_prefix(self):
        error = {"error": {"code": "InvalidRequestFormat", "details": [
            {"code": "InvalidJson",
             "message": "Error converting VNetPeering to contract NextHopType."}
        ]}}
        self.assertTrue(explicit_rejection("ERROR: (" + json.dumps(error) + ")"))

    def test_unrelated_error_is_not_rejection(self):
        for message in ("connection timed out", '{"error":{"code":"Unauthorized"}}',
                        '{"error":{"code":"InvalidRequestFormat"}}',
                        'ERROR: ({"error":invalid)'):
            with self.subTest(message=message):
                self.assertFalse(explicit_rejection(message))


if __name__ == "__main__":
    unittest.main()
