import unittest
from pathlib import Path

import design_customer as customer


class CustomerTests(unittest.TestCase):
    def test_prepend_controls_preserve_every_other_policy(self):
        root = Path(__file__).resolve().parents[1] / "show-output/hrp-design-live-baseline-20261016/sources"
        for site in ("eu", "us"):
            text = (root / f"router-{site}.conf").read_text().rstrip("\n") + "\n"
            suffix = text.partition("filter mesh_export {")[2]
            for extra in (0, 2):
                changed = customer.policy(text, site, extra)
                self.assertEqual(changed.count("bgp_path.prepend("), extra)
                self.assertEqual(changed.partition("filter mesh_export {")[2], suffix)
                self.assertIn('proto = "own_dc" || proto ~ "mesh_*"', changed)
                self.assertIn("accept;", changed.partition("filter mesh_export {")[0])

    def test_changed_manual_export_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "preserved"):
            customer.policy("filter azure_export {}\nfilter mesh_export {}", "eu", 2)
        with self.assertRaises(ValueError):
            customer.policy("unused", "jp", 2)


if __name__ == "__main__":
    unittest.main()
