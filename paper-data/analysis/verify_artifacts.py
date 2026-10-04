"""Read-only verification of the hardware-only analysis and copied dataset."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    summary = json.loads((HERE / "hardware_summary.json").read_text())
    audit = json.loads((HERE / "inventory_source.json").read_text())
    exclusion = json.loads((HERE / "exclusions.json").read_text())
    manifest = json.loads((HERE / "analysis_manifest.json").read_text())
    old_runs = {r["run"]: r for r in audit["runs"]}
    included = summary["all_included_records"]
    assert len(included) == 92
    assert len(exclusion["excluded"]) == 4
    assert {r["run"] for r in included}.isdisjoint(r["run"] for r in exclusion["excluded"])
    assert {r["run"] for r in included} | {r["run"] for r in exclusion["excluded"]} == set(old_runs)
    assert sum(r["decisions"] for r in included) == 10199
    for run in included:
        old = old_runs[run["run"]]
        assert abs(run["carry_to_delivery_s"] - old["duration"]) < 1e-9
        assert abs(run["moving_age_above_0p6_percent"] - 100 * old["moving_old06_fraction"]) < 1e-9
        if run["min_command_estimated_edge_separation_mm"] is not None:
            assert abs(run["min_command_estimated_edge_separation_mm"] - old["min_command_clearance_mm"]) < 1e-9
        else:
            assert old["min_command_clearance_mm"] is None
        assert old["sidecar_exact"] and not old["bundle_link_errors"] and not old["causal_errors"]
    for path, digest in manifest["archived_data"].items():
        assert sha(PACKAGE / path) == digest
    assert len(manifest["archived_data"]) == 184
    for path, digest in manifest["output_hashes"].items():
        assert sha(PACKAGE / path) == digest, path
    for path, digest in manifest.get("presentation_sources", {}).items():
        assert sha(PACKAGE / path) == digest, path
    source_checked = 0
    for path, digest in audit["source_hashes"].items():
        if Path(path).exists():
            assert sha(Path(path)) == digest
            source_checked += 1
    for cell in summary["primary_cells"]:
        assert len(cell["run_ids"]) == 4
        assert sum("_toA_" in name for name in cell["run_ids"]) == 2
        assert sum("_toB_" in name for name in cell["run_ids"]) == 2
    for curve in summary["threshold_sensitivity"]:
        values = curve["mean_run_fraction_percent"]
        assert all(a >= b for a, b in zip(values[:-1], values[1:]))
        assert all(0 <= a <= 100 for a in values)
        at06 = values[curve["thresholds_s"].index(.6)]
        cell = next(c for c in summary["primary_cells"] if c["rate"] == curve["rate"] and c["method"] == curve["method"])
        assert abs(at06 - cell["moving_age_above_0p6_percent"]["mean"]) < 1e-9
    report = {"passed": True, "included_runs": 92, "excluded_runs": 4,
              "primary_runs": 24, "decision_records": 10199,
              "source_json_jsonl_hashes_checked_unchanged": source_checked,
              "byte_identical_included_copy_files_checked": 184,
              "primary_cell_count": 6, "runs_per_primary_cell": 4,
              "all_prior_audit_metrics_reproduced": True,
              "sensitivity_monotonic_and_agrees_at_0p6": True,
              "all_declared_figure_and_presentation_hashes_match": True,
              "limitation": "Internal consistency checks, not independent physical safety or sensor-exposure validation."}
    (HERE / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    verify()
