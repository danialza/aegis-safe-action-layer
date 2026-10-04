"""Regression tests for the scoped shadow semantic gate, not a robot controller."""
import math
import unittest

import shadow_timeout as audit


def row(age=.4, p=.4, present=True, **updates):
    result = {"ev_status": "ok", "ev_verdict": "object", "ev_error": None,
              "ev_t_capture": 10., "ev_t_infer_start": 10.05, "ev_t_infer_end": 10.2,
              "t_decision": 10. + age, "age_used": age, "sensing_age": .1,
              "haz": [.2, .0, .04] if present else None, "p": p,
              "margin": .012 + .048 * p if present else 0., "depth_only": False, "stop_reason": None}
    result.update(updates)
    return result


class ShadowTimeoutTests(unittest.TestCase):
    def test_analytic_threshold_has_correct_zero_anchor_score(self):
        value = audit.P_PRIOR * (1 - math.exp(-audit.ANALYTIC_TIMEOUT / audit.T_DECAY))
        self.assertAlmostEqual(value, audit.P_STOP, places=14)
        self.assertAlmostEqual(audit.ANALYTIC_TIMEOUT, .5865348275173707, places=14)

    def test_both_below_threshold_permit(self):
        result = audit.compare_row(row(), audit.ANALYTIC_TIMEOUT, .032)
        self.assertFalse(result["aegis_hold"])
        self.assertFalse(result["timeout_hold"])
        self.assertTrue(result["both_permitted"])
        self.assertAlmostEqual(result["aegis_margin_m"], .0312)

    def test_timeout_inclusive_boundary(self):
        result = audit.compare_row(row(age=audit.ANALYTIC_TIMEOUT, p=.5), audit.ANALYTIC_TIMEOUT, .012)
        self.assertTrue(result["aegis_hold"])
        self.assertTrue(result["timeout_hold"])
        self.assertFalse(result["disagree"])

    def test_one_side_can_hold(self):
        result = audit.compare_row(row(age=.568, p=.501), audit.ANALYTIC_TIMEOUT, .032)
        self.assertTrue(result["aegis_hold"])
        self.assertFalse(result["timeout_hold"])
        self.assertTrue(result["disagree"])
        inverse = audit.compare_row(row(age=.6, p=.4), audit.ANALYTIC_TIMEOUT, .032)
        self.assertFalse(inverse["aegis_hold"])
        self.assertTrue(inverse["timeout_hold"])

    def test_absent_hazard_does_not_receive_global_timeout(self):
        result = audit.compare_row(row(age=1., p=0., present=False), audit.ANALYTIC_TIMEOUT, .032)
        self.assertFalse(result["aegis_hold"])
        self.assertFalse(result["timeout_hold"])
        self.assertFalse(result["eligible_object_hazard"])

    def test_direct_human_holds_even_with_no_geometric_hazard(self):
        result = audit.compare_row(row(present=False, ev_verdict="human"), .8, .032)
        self.assertEqual(result["common_guard"], "human")
        self.assertTrue(result["aegis_hold"] and result["timeout_hold"])

    def test_integrity_states_hold(self):
        for status in audit.HOLD_STATUSES:
            with self.subTest(status=status):
                result = audit.compare_row(row(ev_status=status), .8, .032)
                self.assertEqual(result["common_guard"], "evidence:" + status)
                self.assertTrue(result["aegis_hold"] and result["timeout_hold"])

    def test_bad_causal_times_and_missing_times_hold(self):
        for updates in ({"ev_t_capture": None}, {"ev_t_capture": float("nan")},
                        {"ev_t_capture": 11.}, {"ev_t_infer_end": 10.01},
                        {"ev_t_infer_end": 10.6}, {"t_decision": float("inf")}):
            with self.subTest(updates=updates):
                self.assertEqual(audit.compare_row(row(**updates), .8, .032)["common_guard"], "invalid_time")

    def test_time_tolerance_matches_archive(self):
        self.assertTrue(audit.times_valid(row(ev_t_capture=10.054, ev_t_infer_start=10.05)))
        self.assertFalse(audit.times_valid(row(ev_t_capture=10.056, ev_t_infer_start=10.05)))

    def test_age_consistency_and_errors_hold(self):
        self.assertEqual(audit.compare_row(row(age_used=.5), .8, .032)["common_guard"], "invalid_age")
        self.assertEqual(audit.compare_row(row(ev_error="inference failed"), .8, .032)["common_guard"], "vlm_error")
        self.assertEqual(audit.compare_row(row(ev_verdict=None), .8, .032)["common_guard"], "vlm_error")

    def test_destination_depth_and_sensing_are_common(self):
        for updates, reason in (({"stop_reason": "goal_occupied"}, "goal_occupied"),
                                ({"depth_only": True}, "depth_only"),
                                ({"sensing_age": .601}, "sensing_stale")):
            with self.subTest(reason=reason):
                self.assertEqual(audit.compare_row(row(**updates), .8, .032)["common_guard"], reason)

    def test_geometry_stop_is_not_asserted_as_counterfactual_common_stop(self):
        result = audit.compare_row(row(stop_reason="geometry"), .8, .032)
        self.assertIsNone(result["common_guard"])
        self.assertTrue(result["both_permitted"])

    def test_invalid_threshold_buffer_score_rejected(self):
        for timeout, beta in ((-.1, .032), (.5, float("nan")), (float("inf"), .032)):
            with self.assertRaises(ValueError):
                audit.compare_row(row(), timeout, beta)
        missing_score = row()
        missing_score["p"] = None
        with self.assertRaises(ValueError):
            audit.compare_row(missing_score, .5, .032)

    def test_archived_constants(self):
        audit.validate_archived_constants()

    def test_primary_and_pilot_selection_regression(self):
        import json
        summary = json.loads((audit.ANALYSIS / "hardware_summary.json").read_text())
        selected = [v for v in summary["all_included_records"] if v["method"] == "AEGIS"
                    and v["campaign"] in ("timed_margin_compare", "timed_compare_slow")]
        self.assertEqual(len(selected), 12)
        records = []
        for meta in selected:
            rows, _, _ = audit.load_run(meta)
            records.append(audit.run_assay(meta, rows)[0])
        cells = audit.aggregate(records)
        expected = {("timed_margin_compare", "normal"): (311, 0, 301),
                    ("timed_margin_compare", "slow"): (991, 0, 287),
                    ("timed_compare_slow", "slow"): (987, 1, 276)}
        for cell in cells:
            item = cell["comparisons"]["Trust32+timeout-analytic"]["pooled_row_counts_descriptive_only"]
            self.assertEqual(cell["runs"], 4)
            self.assertEqual((item["eligible_object_hazard_decisions"], item["disagreements"],
                              item["both_permitted_object_hazard_decisions"]), expected[cell["campaign"], cell["rate"]])


if __name__ == "__main__":
    unittest.main()
