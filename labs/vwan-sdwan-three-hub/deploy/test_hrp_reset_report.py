import unittest
from unittest.mock import patch

import design_b2b as b2b
import hrp_reset_report as report


class ResetReportTests(unittest.TestCase):
    def outcome(self, local, failed=False, before_local=None, different=False):
        cells = [dict(source=a, destination=b, tcp="PASS", icmp="PASS")
                 for a in b2b.ENDPOINTS.values() for b in b2b.traffic_targets(a, True)]
        if failed:
            cells[0]["tcp"] = "FAIL"
        def load(case):
            initial = local if before_local is None else before_local
            path = "65011 65012" if different and "nva-first" in case[0] else "65011"
            return dict(firewalls={"rows": [{"site": "eu", "prefix": "10.110.0.0/24", "asPath": path}]},
                        traffic={"cells": cells},
                        local=initial if case[2] == "HRP-only" else local)
        with patch.object(report.report, "load", side_effect=load), \
                patch.object(report.b2b.reselection, "local_japan", side_effect=lambda data: data["local"]):
            return report.outcome()

    def test_wrong_route_winner_does_not_become_a_success_caveat(self):
        text = self.outcome(False)
        self.assertIn("not a sufficient deterministic recipe", text)
        self.assertNotIn("supports an operational", text)

    def test_positive_result_is_limited_to_tested_conditions(self):
        text = self.outcome(True)
        self.assertIn("two lab trials", text)
        self.assertIn("not a universal Azure guarantee", text)
        self.assertIn("do not establish that a reset is required", text)

    def test_route_success_does_not_hide_forwarding_failure(self):
        text = self.outcome(True, failed=True)
        self.assertIn("does not establish end-to-end B1 success", text)
        self.assertNotIn("Both corrected-workload captures pass", text)

    def test_recovery_caveat_requires_a_changed_winner(self):
        text = self.outcome(True, before_local=False)
        self.assertIn("supports an operational reset caveat", text)
        self.assertNotIn("do not establish that a reset is required", text)

    def test_japan_success_does_not_hide_other_route_order_dependence(self):
        text = self.outcome(True, different=True)
        self.assertIn("other DC-prefix firewall winners differed", text)
        self.assertNotIn("supports an operational reset caveat", text)

    def test_article_update_is_idempotent_and_replaces_old_primary(self):
        article = ("# Title\n\nIntro.\n\n## B1: Customer backbone through HRP\n\n"
                   "Old primary.\n\n## B2: Customer backbone through AS-path control\n\n"
                   "Keep B2.\n\n## Conclusions and boundaries\n\nKeep conclusions.\n")
        primary = "## B1: Customer backbone through HRP\n\nNew primary."
        with patch.object(report, "section", return_value=report.HEADING + "\n\nReset results."), \
                patch.object(report, "primary_b1", return_value=primary):
            once = report.update_article(article)
            twice = report.update_article(once)
        self.assertEqual(once, twice)
        self.assertNotIn("Old primary", once)
        self.assertEqual(once.count(report.HEADING), 1)
        self.assertEqual(once.count("## B1: Customer backbone through HRP"), 1)
        self.assertIn("Keep B2", once)
        self.assertIn("Keep conclusions", once)


if __name__ == "__main__":
    unittest.main()
