"""Checks for the derived exploratory analysis; no robot/controller imports."""
import json
from pathlib import Path
import statistics as st
import unittest

from pattern_audit import BLOCKS, METRICS, METHODS, digest


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]


class PatternAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((HERE / "pattern_results.json").read_text())
        cls.primary = [row for row in cls.result["runs"] if row["campaign"] == "timed_margin_compare"]
        cls.index = {(row["method"], row["rate"], row["direction"], row["repetition"]): row for row in cls.primary}

    def test_all_primary_runs_and_separate_pilot(self):
        self.assertEqual(len(self.primary), 24)
        self.assertEqual(len(self.result["runs"]), 32)
        self.assertEqual(len({row["run"] for row in self.result["runs"]}), 32)
        self.assertEqual(len(self.result["primary_cells"]), 6)
        self.assertEqual(len(self.result["pilot_cells_not_pooled"]), 2)
        for cell in self.result["primary_cells"] + self.result["pilot_cells_not_pooled"]:
            self.assertEqual(cell["n"], 4)
            self.assertEqual(len(cell["run_ids"]), 4)

    def test_equal_run_means(self):
        for cell in self.result["primary_cells"]:
            rows = [row for row in self.primary if (row["method"], row["rate"]) == (cell["method"], cell["rate"])]
            for metric in METRICS:
                self.assertAlmostEqual(cell["metrics"][metric]["mean"], st.mean(row[metric] for row in rows), places=9)

    def test_nominal_contrasts_and_difference_in_changes(self):
        for method in METHODS:
            for metric in METRICS:
                expected = [self.index[method, "slow", d, rep][metric] - self.index[method, "normal", d, rep][metric] for d, rep in BLOCKS]
                actual = self.result["slow_minus_normal_nominal_contrasts"][method][metric]
                self.assertEqual(actual["individual_values"], expected)
                self.assertAlmostEqual(actual["mean"], st.mean(expected), places=9)
        for reference in ("Trust12", "Trust32"):
            for metric in METRICS:
                expected = st.mean(self.index["AEGIS", "slow", d, rep][metric] - self.index["AEGIS", "normal", d, rep][metric]
                                   - self.index[reference, "slow", d, rep][metric] + self.index[reference, "normal", d, rep][metric] for d, rep in BLOCKS)
                actual = self.result["difference_in_cadence_changes_AEGIS_minus_reference"][reference][metric]["mean"]
                self.assertAlmostEqual(actual, expected, places=9)

    def test_time_decomposition_is_arithmetic_not_physical(self):
        d = self.result["AEGIS_time_change_decomposition"]
        self.assertAlmostEqual(d["total_change_s"], d["score_hold_interval_change_s"] + d["remaining_interval_and_endpoint_change_s"], places=9)
        self.assertIn("not a causal attribution", d["interpretation"])
        for row in self.result["runs"]:
            self.assertAlmostEqual(row["carry_to_delivery_s"], sum(row["software_occupancy_s"].values()) + row["initial_unassigned_s"] + row["final_unassigned_s"], places=7)

    def test_missing_detection_exceptions_are_retained(self):
        exceptions = self.result["AEGIS_old_evidence_exceptions_retained"]
        self.assertEqual({row["run"] for row in exceptions}, {"AEGIS-slow_toA_2", "AEGIS-slowupdates-0.8s_toB_1"})
        self.assertEqual(sum(row["old_moving_decisions"] for row in exceptions), 22)
        self.assertTrue(all(row["old_moving_with_hazard"] == 0 for row in exceptions))
        self.assertTrue(all(row["max_moving_age_ms"] > 1000 for row in exceptions))

    def test_source_and_derived_hashes(self):
        manifest = json.loads((PACKAGE / "analysis/analysis_manifest.json").read_text())
        self.assertEqual(len(manifest["archived_data"]), 184)
        for name, expected in manifest["archived_data"].items():
            self.assertEqual(digest(PACKAGE / name), expected)
        self.assertEqual(digest(HERE / "pattern_audit.py"), self.result["provenance"]["analysis_script_sha256"])
        self.assertEqual(digest(PACKAGE / self.result["figure"]["path"]), self.result["figure"]["sha256"])


if __name__ == "__main__":
    unittest.main()
