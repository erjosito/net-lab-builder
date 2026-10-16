import ast
import base64
import gzip
import json
import unittest

import design_snapshot as snapshot


class SnapshotTests(unittest.TestCase):
    def test_generated_python_and_safe_output_bound(self):
        for site in snapshot.ALL_SITES:
            for source in (False, True):
                text = snapshot.guest_script(site, source)
                body = text.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
                ast.parse(body, feature_version=(3, 10))
                self.assertIn("len(payload)<3500", text)
                self.assertNotIn("configure", text)
                self.assertNotIn("--load", text)

    def test_complete_compressed_marker_required(self):
        data = {"site": "eu", "config": "test\n" * 2000}
        encoded = base64.b64encode(gzip.compress(json.dumps(data).encode())).decode()
        self.assertEqual(snapshot.decode({"value": [{"message": "DESIGN_SNAPSHOT " + encoded + "\n"}]}), data)
        with self.assertRaisesRegex(RuntimeError, "snapshot missing"):
            snapshot.decode({"value": [{"message": encoded[10:]}]})


if __name__ == "__main__":
    unittest.main()
