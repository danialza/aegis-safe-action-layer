"""Independent checks for the read-only timing-stage audit."""
import json
from pathlib import Path
import statistics as st
import unittest

from stage_age_audit import CAUSAL_TOLERANCE_MS, PACKAGE, STAGES, digest, quantile, population, stages


HERE = Path(__file__).resolve().parent


class StageAgeAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((HERE / "stage_age_results.json").read_text())
        cls.runs = {row["run"]: row for row in cls.result["runs"]}

    def test_primary_and_pilot_are_separate_and_balanced(self):
        self.assertEqual(len(self.runs), 32)
        self.assertEqual(len(self.result["primary_cells"]), 6)
        self.assertEqual(len(self.result["primary_direction_cells"]), 12)
        self.assertEqual(len(self.result["pilot_cells_not_pooled"]), 2)
        self.assertTrue(all(row["n_runs"] == 4 for row in self.result["primary_cells"]))
        self.assertTrue(all(row["n_runs"] == 2 for row in self.result["primary_direction_cells"]))
        primary = {name for row in self.result["primary_cells"] for name in row["run_ids"]}
        pilot = {name for row in self.result["pilot_cells_not_pooled"] for name in row["run_ids"]}
        self.assertEqual((len(primary), len(pilot), len(primary & pilot)), (24, 8, 0))

    def test_reconciliation_and_sidecar_links_each_raw_row(self):
        total = 0
        for run in self.runs.values():
            path = PACKAGE / "data" / run["campaign"] / "logs" / (run["run"] + ".json")
            raw = json.loads(path.read_text())["log"]
            ledger = [json.loads(line) for line in path.with_name(path.stem + "_timing.jsonl").read_text().splitlines()]
            evidence = {row["seq"]: row for row in ledger if row.get("type") == "vlm"}
            for row in raw:
                total += 1
                self.assertEqual(row["ev_status"], "ok")
                components, residual = stages(row)
                self.assertLess(abs(residual), 1e-6)
                self.assertAlmostEqual(sum(components[key] for key in STAGES), row["age_used"] * 1000, places=6)
                self.assertEqual(row["ev_frame_id"], evidence[row["ev_seq"]]["frame_id"])
        self.assertEqual(total, 4530)
        self.assertEqual(total, self.result["validation"]["selected_decisions"])

    def test_stage_cell_means_sum_to_age_and_use_equal_runs(self):
        for cell in self.result["primary_cells"] + self.result["pilot_cells_not_pooled"]:
            means = [self.runs[name]["populations"]["moving_valid"]["total_age_ms"]["mean"] for name in cell["run_ids"]]
            self.assertAlmostEqual(st.mean(means), cell["metrics"]["mean_moving_age_ms"]["mean"], places=9)
            self.assertAlmostEqual(st.stdev(means), cell["metrics"]["mean_moving_age_ms"]["sample_sd"], places=9)
            total = sum(cell["metrics"]["mean_" + key]["mean"] for key in STAGES)
            self.assertAlmostEqual(total, cell["metrics"]["mean_moving_age_ms"]["mean"], places=6)

    def test_sample_support_missing_hazards_are_retained(self):
        total_moving = 0
        for run in self.runs.values():
            populations = run["populations"]
            moving = populations["moving_valid"]["decisions"]
            present = populations["moving_hazard_present"]["decisions"]
            absent = populations["moving_hazard_absent"]["decisions"]
            self.assertEqual(moving, present + absent)
            self.assertAlmostEqual(absent / moving * 100, run["moving_nohazard_percent"], places=9)
            total_moving += moving
        self.assertEqual(total_moving, 2314)
        exception = self.runs["AEGIS-slow_toA_2"]["populations"]
        self.assertEqual(exception["moving_hazard_present"]["age_above_600ms_count"], 0)
        self.assertEqual(exception["moving_hazard_absent"]["age_above_600ms_count"], 12)

    def test_conditional_cells_use_nonempty_runs_without_imputation(self):
        for cell in self.result["primary_cells"]:
            for name, info in cell["populations_equal_run"].items():
                populated = [self.runs[run_id]["populations"][name] for run_id in info["run_ids"]]
                self.assertEqual(info["n_nonempty_runs"], len(populated))
                self.assertTrue(all(row["decisions"] > 0 for row in populated))
                self.assertAlmostEqual(info["metrics"]["mean_age_ms"]["mean"],
                                       st.mean(row["total_age_ms"]["mean"] for row in populated), places=9)
                self.assertEqual(info["decision_count_for_support_only"], sum(row["decisions"] for row in populated))

    def test_linear_quantiles_and_empty_null_not_zero(self):
        self.assertAlmostEqual(quantile([0, 10, 20], .95), 19)
        self.assertEqual(quantile([7], .95), 7)
        self.assertIsNone(quantile([], .95))
        empty = population([])
        self.assertIsNone(empty["total_age_ms"]["mean"])
        self.assertIsNone(empty["age_above_600ms_percent"])

    def test_negative_stage_is_preserved_not_clamped(self):
        row = {"ev_t_capture": 10.0, "ev_t_infer_start": 10.04,
               "ev_t_infer_end": 10.34, "t_decision": 10.337,
               "age_used": 10.337 - 10.0}
        components, residual = stages(row)
        self.assertAlmostEqual(components["infer_end_to_decision_ms"], -3, places=8)
        self.assertLess(abs(residual), 1e-6)
        info = population([row])
        self.assertEqual(info["negative_stage_counts"]["infer_end_to_decision_ms"], 1)
        self.assertEqual(info["beyond_5ms_negative_counts"]["infer_end_to_decision_ms"], 0)
        row["t_decision"] -= .005
        row["age_used"] -= .005
        self.assertLess(stages(row)[0]["infer_end_to_decision_ms"], -CAUSAL_TOLERANCE_MS)
        self.assertEqual(self.result["validation"]["negative_stage_observations_count"], 0)

    def test_original_and_pattern_metrics_reproduced(self):
        patterns = json.loads((PACKAGE / "analysis/exploratory_patterns_2026-10-02/pattern_results.json").read_text())
        for row in patterns["runs"]:
            run = self.runs[row["run"]]
            self.assertAlmostEqual(run["populations"]["moving_valid"]["total_age_ms"]["mean"], row["mean_moving_age_ms"], places=8)
            self.assertAlmostEqual(run["minimum_command_estimated_separation_mm"], row["minimum_command_estimated_separation_mm"], places=8)
        a = next(cell for cell in self.result["primary_cells"] if (cell["method"], cell["rate"]) == ("AEGIS", "normal"))
        b = next(cell for cell in self.result["primary_cells"] if (cell["method"], cell["rate"]) == ("AEGIS", "slow"))
        self.assertAlmostEqual(a["metrics"]["mean_moving_age_ms"]["sample_sd"], 7.48, delta=.02)
        self.assertAlmostEqual(b["metrics"]["mean_moving_age_ms"]["sample_sd"], 46.18, delta=.02)

    def test_source_and_output_hashes_unchanged(self):
        provenance = self.result["provenance"]
        self.assertEqual(len(provenance["selected_source_hashes"]), 64)
        for name, expected in provenance["selected_source_hashes"].items():
            self.assertEqual(digest(PACKAGE / name), expected)
        self.assertEqual(digest(HERE / "stage_age_audit.py"), provenance["analysis_script_sha256"])
        for name, expected in provenance["generated_tables"].items():
            self.assertEqual(digest(PACKAGE / name), expected)


if __name__ == "__main__":
    unittest.main()
