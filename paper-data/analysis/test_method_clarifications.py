"""Offline document regressions; parse archival source but never execute it.

These checks verify the three October 4 method clarifications. They do not
validate detector accuracy, physical stopping, or alternative controller runs.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


def read(relative):
    return (ROOT / relative).read_text()


def constant(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


class MethodClarificationTests(unittest.TestCase):
    def test_rgb_precedence_and_confirmed_depth_are_explicit(self):
        main = read("manuscript/main.tex")
        supplement = read("manuscript/supplementary.tex")
        tree = ast.parse(read("provenance_code/safebench/reactive_run.py"))
        self.assertEqual(constant(tree, "DEPTH_MATCH_DISTANCE_M"), .055)
        self.assertEqual(constant(tree, "DEPTH_ONLY_CONFIRM_FRAMES"), 3)
        for source in (main, supplement):
            self.assertIn("RGB takes precedence", source)
            self.assertIn("unmatched depth candidate is discarded", source)
            self.assertIn("no RGB candidate is selected", source)
        self.assertIn("fusion retains the RGB centre and takes the larger radius", supplement)
        self.assertIn("three consecutive processed-frame detections", supplement)
        self.assertIn("successive centres within 40 mm", supplement)
        self.assertNotIn("An unmatched depth-only detection is stop-only", main)
        self.assertIn("Confirmed depth-only / blocked goal", read("analysis/build_workflow.py"))

    def test_radius_alone_is_not_a_cache_regeneration_trigger(self):
        source = read("provenance_code/safebench/reactive_exec.py")
        tree = ast.parse(source)
        self.assertEqual(constant(tree, "REPLAN_MOVE"), .03)
        advance = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef) and node.name == "_advance")
        need = next(node for node in advance.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "need"
                            for target in node.targets))
        names = {node.id for node in ast.walk(need.value) if isinstance(node, ast.Name)}
        self.assertIn("center", names)
        self.assertIn("REPLAN_MOVE", names)
        self.assertTrue(names.isdisjoint({"r", "Reff"}))
        main = read("manuscript/main.tex")
        supplement = read("manuscript/supplementary.tex")
        self.assertIn("semantic margin alone do not regenerate the cached path", main)
        self.assertIn("planning centre changes by more than 30 mm", main)
        self.assertIn("current augmented radius nevertheless enters", main)
        self.assertIn("velocity-predicted", main)
        self.assertIn("class-dependent-allowance changes alone do not regenerate", supplement)
        self.assertIn("retain its earlier planning radius", supplement)

    def test_residual_includes_move_and_other_components(self):
        results = json.loads(read("analysis/exploratory_patterns_2026-10-02/pattern_results.json"))
        decomposition = results["AEGIS_time_change_decomposition"]
        cells = {cell["rate"]: cell for cell in results["primary_cells"]
                 if cell["method"] == "AEGIS"}
        residual = decomposition["total_change_s"] - decomposition["score_hold_interval_change_s"]
        move = (cells["slow"]["mean_moving_decision_interval_s"]
                - cells["normal"]["mean_moving_decision_interval_s"])
        other = residual - move
        self.assertAlmostEqual(residual, .42993949353694916, places=12)
        self.assertEqual([round(residual, 2), round(move, 2), round(other, 2)], [.43, -.26, .69])
        main = read("manuscript/main.tex")
        supplement = read("manuscript/supplementary.tex")
        self.assertIn("All non-score categories and endpoint gaps together", main)
        self.assertIn("This includes a decrease of approximately 0.26 s", main)
        self.assertIn("increase by approximately 0.69 s", main)
        self.assertIn("That latter residual includes a 0.26 s decrease", supplement)
        self.assertIn("a 0.69 s increase", supplement)

    def test_archived_data_and_verified_controller_bytes_unchanged(self):
        manifest = json.loads(read("analysis/analysis_manifest.json"))
        self.assertEqual(len(manifest["archived_data"]), 184)
        for filename, expected in manifest["archived_data"].items():
            self.assertEqual(hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(), expected, filename)
        snapshot = json.loads(read("provenance_code/metadata/snapshot_manifest.json"))
        for entry in snapshot["verified_code_configuration_files"]:
            self.assertEqual(hashlib.sha256((ROOT / entry["archive_path"]).read_bytes()).hexdigest(),
                             entry["sha256"], entry["archive_path"])


if __name__ == "__main__":
    unittest.main()
