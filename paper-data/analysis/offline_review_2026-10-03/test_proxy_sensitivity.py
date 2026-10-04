"""Checks for the frozen-mask hypothetical timing-offset analysis."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import proxy_sensitivity as ps


class ProxySensitivityTests(unittest.TestCase):
    def test_common_offset_mean_difference_is_invariant(self):
        aegis = (0.4, 0.5, 0.6)
        reference = (0.6, 0.7, 0.8)
        observed_gap = ps.offset_metrics(aegis, 0)["mean_age_s"] - ps.offset_metrics(reference, 0)["mean_age_s"]
        for offset in ps.COMMON_OFFSETS_S:
            gap = ps.offset_metrics(aegis, offset)["mean_age_s"] - ps.offset_metrics(reference, offset)["mean_age_s"]
            self.assertAlmostEqual(gap, observed_gap)

    def test_strict_threshold_and_changed_fraction(self):
        ages = (0.4, 0.5, 0.6, 0.7)
        self.assertEqual(ps.offset_metrics(ages, 0)["above_threshold_percent"], 25)
        self.assertEqual(ps.offset_metrics(ages, 0.1)["above_threshold_percent"], 50)
        self.assertEqual(ps.offset_metrics(ages, 0.3)["above_threshold_percent"], 100)
        self.assertEqual(ages, (0.4, 0.5, 0.6, 0.7))

    def test_correct_differential_sign_and_break_even(self):
        ae, ref = 0.4235, 0.6826
        break_even = ref - ae
        self.assertEqual(ps.gap_rank(ps.relative_mean_gap(ae, ref, break_even)), "equal_mean_age")
        self.assertEqual(ps.gap_rank(ps.relative_mean_gap(ae, ref, 0.2)), "AEGIS_lower_mean_age")
        self.assertEqual(ps.gap_rank(ps.relative_mean_gap(ae, ref, 0.3)), "reference_lower_mean_age")
        self.assertAlmostEqual(ps.relative_mean_gap(ae, ref, -0.1), ae - ref - 0.1)

    def test_moving_mask_and_input_are_not_mutated(self):
        record = {"time_base": "capture_proxy", "log": [
            {"time_base": "capture_proxy", "mode": "move", "age_used": 0.4},
            {"time_base": "capture_proxy", "mode": "stop", "age_used": 0.99},
            {"time_base": "capture_proxy", "mode": "forward", "age_used": 0.7}]}
        before = copy.deepcopy(record)
        ages, indices = ps.extract_moving_ages(record)
        self.assertEqual(indices, (0, 2))
        self.assertEqual(ages, (0.4, 0.7))
        ps.offset_metrics(ages, 0.3)
        self.assertEqual(record, before)

    def test_rejects_invalid_common_offsets_or_clock(self):
        for offset in (-0.1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                ps.offset_metrics((0.4,), offset)
        with self.assertRaises(ValueError):
            ps.extract_moving_ages({"time_base": "legacy", "log": []})
        with self.assertRaises(ValueError):
            ps.extract_moving_ages({"time_base": "capture_proxy", "log": [
                {"time_base": "capture_proxy", "mode": "move", "age_used": 0.4,
                 "ev_status": "ok", "t_decision": 1, "ev_t_capture": 0.5}]})

    def test_archived_results_complete_and_sources_unchanged(self):
        runs, before = ps.load_verified_runs()
        source_runs = copy.deepcopy(runs)
        result = ps.analyze(runs)
        self.assertEqual(runs, source_runs)
        self.assertEqual(result["primary"]["n_runs"], 24)
        self.assertEqual(result["slow_pilot_not_pooled"]["n_runs"], 8)
        self.assertEqual(len(before), 66)
        self.assertEqual({name: ps.digest(ps.PACKAGE / name) for name in before}, before)
        for key in ("primary", "slow_pilot_not_pooled"):
            cohort = result[key]
            for contrast in cohort["method_differential_offset_contrasts"]:
                self.assertEqual(len(contrast["nominal_blocks"]), 4)
                self.assertEqual(len(contrast["relative_offset_scenarios"]), 9)
                self.assertAlmostEqual(contrast["mean_gap_break_even_differential_offset_s"],
                                       contrast["observed_reference_mean_age_s"] - contrast["observed_AEGIS_mean_age_s"])
            rates = {scenario["rate"] for scenario in cohort["common_offset_scenarios"]}
            for rate in rates:
                scenarios = [scenario for scenario in cohort["common_offset_scenarios"] if scenario["rate"] == rate]
                baseline = scenarios[0]
                for scenario in scenarios:
                    self.assertEqual(scenario["mean_age_rank_lower_is_fresher"], baseline["mean_age_rank_lower_is_fresher"])
                    self.assertEqual(scenario["AEGIS_minus_reference_mean_age_s"], baseline["AEGIS_minus_reference_mean_age_s"])
                    self.assertTrue(all(cell["n_runs"] == 4 for cell in scenario["cells"]))
                    cells = {cell["method"]: cell for cell in scenario["cells"]}
                    for reference, invariant_gap in scenario["AEGIS_minus_reference_mean_age_s"].items():
                        # Check the independently recomputed shifted-cell means,
                        # not just the analytical invariant stored in the report.
                        actual_gap = cells["AEGIS"]["mean_age_s"]["mean"] - cells[reference]["mean_age_s"]["mean"]
                        self.assertAlmostEqual(actual_gap, invariant_gap)
                for method in baseline["mean_age_rank_lower_is_fresher"]:
                    fractions = [next(cell for cell in scenario["cells"] if cell["method"] == method)
                                 ["above_threshold_percent"]["mean"] for scenario in scenarios]
                    self.assertEqual(fractions, sorted(fractions))
        tex = ps.table_tex(result)
        self.assertIn(r"\begin{table}[H]", tex)
        self.assertIn(r"\label{tab:proxy-offset}", tex)
        self.assertIn("Pilot (separate)", tex)
        self.assertTrue(tex.endswith("\\end{table}\n"))

    def test_derived_output_build_keeps_input_files_unchanged(self):
        _, before = ps.load_verified_runs()
        with tempfile.TemporaryDirectory(prefix="aegis-proxy-sensitivity-test-") as directory:
            result = ps.build(output_dir=Path(directory))
            manifest = json.loads((Path(directory) / "proxy_sensitivity_manifest.json").read_text())
            self.assertTrue(manifest["inputs_unchanged"])
            self.assertEqual(manifest["source_hashes_before"], manifest["source_hashes_after"])
            self.assertEqual(result["provenance"]["source_hashes_before"], before)
        self.assertEqual({name: ps.digest(ps.PACKAGE / name) for name in before}, before)


if __name__ == "__main__":
    unittest.main()
