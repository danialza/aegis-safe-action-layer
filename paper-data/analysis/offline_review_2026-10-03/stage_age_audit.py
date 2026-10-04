"""Read-only timestamp-stage and sample-support audit of 32 frozen transports.

Primary24 and the earlier slow pilot8 are always separate. Derived outcomes are
conditional on the recorded decisions, not a new hardware experiment, physical
motion exposure, or an independent latency measurement. No controller imports.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics as st


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
ANALYSIS = PACKAGE / "analysis"
METHODS = ("AEGIS", "Trust12", "Trust32")
RATES = ("normal", "slow")
STAGES = ("proxy_to_infer_start_ms", "inference_ms", "infer_end_to_decision_ms")
CAUSAL_TOLERANCE_MS = 5.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quantile(values, q):
    """Hyndman--Fan type7 / NumPy linear quantile; no NumPy dependency."""
    values = sorted(values)
    if not values:
        return None
    assert 0 <= q <= 1
    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def describe(values):
    assert all(isinstance(value, (int, float)) and math.isfinite(value) for value in values)
    if not values:
        return {"n": 0, "mean": None, "median": None, "p95": None,
                "min": None, "max": None, "sample_sd": None,
                "individual_values": []}
    return {"n": len(values), "mean": st.mean(values), "median": st.median(values),
            "p95": quantile(values, .95), "min": min(values), "max": max(values),
            "sample_sd": st.stdev(values) if len(values) > 1 else None,
            "individual_values": list(values)}


def stages(row):
    keys = ("ev_t_capture", "ev_t_infer_start", "ev_t_infer_end", "t_decision", "age_used")
    assert all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key]) for key in keys)
    result = {
        "proxy_to_infer_start_ms": (row["ev_t_infer_start"] - row["ev_t_capture"]) * 1000,
        "inference_ms": (row["ev_t_infer_end"] - row["ev_t_infer_start"]) * 1000,
        "infer_end_to_decision_ms": (row["t_decision"] - row["ev_t_infer_end"]) * 1000,
        "total_age_ms": row["age_used"] * 1000,
        "proxy_to_infer_end_ms": (row["ev_t_infer_end"] - row["ev_t_capture"]) * 1000,
    }
    residual = sum(result[key] for key in STAGES) - result["total_age_ms"]
    assert abs(residual) < 1e-6, residual
    assert abs(row["age_used"] - (row["t_decision"] - row["ev_t_capture"])) < 1e-8
    return result, residual


def population(rows):
    computed = [stages(row)[0] for row in rows]
    # Empty conditional populations stay null; they are never assigned age0.
    info = {"decisions": len(rows),
            "total_age_ms": describe([row["total_age_ms"] for row in computed]),
            "stages_ms": {key: describe([row[key] for row in computed]) for key in STAGES},
            "proxy_to_infer_end_ms": describe([row["proxy_to_infer_end_ms"] for row in computed]),
            "age_above_600ms_count": sum(row["age_used"] > .6 for row in rows),
            "age_above_600ms_percent": st.mean(row["age_used"] > .6 for row in rows) * 100 if rows else None,
            "negative_stage_counts": {key: sum(row[key] < 0 for row in computed) for key in STAGES},
            "beyond_5ms_negative_counts": {key: sum(row[key] < -CAUSAL_TOLERANCE_MS for row in computed) for key in STAGES}}
    # Individual ages/stage values are reproducible in raw logs; keep the JSON
    # compact while retaining every run's statistics and exact source hashes.
    for distribution in [info["total_age_ms"], info["proxy_to_infer_end_ms"], *info["stages_ms"].values()]:
        distribution.pop("individual_values")
    if rows:
        assert abs(sum(info["stages_ms"][key]["mean"] for key in STAGES) - info["total_age_ms"]["mean"]) < 1e-6
    return info


def reconstruct(meta, pattern):
    path = PACKAGE / "data" / meta["campaign"] / "logs" / (meta["run"] + ".json")
    sidecar = path.with_name(meta["run"] + "_timing.jsonl")
    record = json.loads(path.read_text())
    rows = record["log"]
    ledger = [json.loads(line) for line in sidecar.read_text().splitlines()]
    decisions = [{key: value for key, value in row.items() if key != "type"}
                 for row in ledger if row.get("type") == "decision"]
    assert rows == decisions
    vlm = {row["seq"]: row for row in ledger if row.get("type") == "vlm"}
    valid = [row for row in rows if row.get("ev_status") == "ok"]
    moving = [row for row in valid if row["mode"] != "stop"]
    assert moving and len(moving) == sum(row["mode"] != "stop" for row in rows)
    present = [row for row in moving if row.get("haz") is not None]
    absent = [row for row in moving if row.get("haz") is None]
    assert all((row.get("haz") is None) == (row.get("clr") is None) for row in moving)
    residuals, negatives = [], []
    for index, row in enumerate(rows):
        assert row["time_base"] == "capture_proxy"
        if row.get("ev_status") != "ok":
            continue
        components, residual = stages(row)
        residuals.append(abs(residual))
        bundle = vlm[row["ev_seq"]]
        assert row["ev_frame_id"] == bundle["frame_id"]
        for field in ("t_capture", "t_infer_start", "t_infer_end", "verdict", "hands", "error"):
            assert row["ev_" + field] == bundle[field]
        for key in STAGES:
            if components[key] < 0:
                negatives.append({"decision_index": index, "stage": key,
                                  "value_ms": components[key],
                                  "beyond_5ms_tolerance": components[key] < -CAUSAL_TOLERANCE_MS})
    assert residuals
    populations = {"all_valid": population(valid), "moving_valid": population(moving),
                   "moving_hazard_present": population(present), "moving_hazard_absent": population(absent)}
    mean_age = populations["moving_valid"]["total_age_ms"]["mean"]
    minimum_separation = min(row["clr"] for row in present) * 1000 if present else None
    assert abs(mean_age - meta["mean_moving_evidence_age_s"] * 1000) < 1e-7
    assert abs(mean_age - pattern["mean_moving_age_ms"]) < 1e-7
    assert abs(minimum_separation - meta["min_command_estimated_edge_separation_mm"]) < 1e-7
    assert abs(minimum_separation - pattern["minimum_command_estimated_separation_mm"]) < 1e-7
    unique_rows = {row["ev_seq"]: row for row in valid}
    unique_stage = [stages(row)[0] for row in unique_rows.values()]
    unique_summary = {
        key: describe([row[key] for row in unique_stage])
        for key in ("proxy_to_infer_start_ms", "inference_ms", "proxy_to_infer_end_ms")}
    for info in unique_summary.values():
        info.pop("individual_values")
    return {"run": meta["run"], "campaign": meta["campaign"], "method": meta["method"],
            "rate": meta["rate"], "direction": meta["direction"],
            "repetition": int(meta["run"].rsplit("_", 1)[1]),
            "all_decisions": len(rows), "invalid_decisions": len(rows) - len(valid),
            "moving_nohazard_percent": len(absent) / len(moving) * 100,
            "distinct_evidence_sequences_used": len(unique_rows),
            "distinct_used_evidence_stage_ms": unique_summary,
            "populations": populations,
            "moving_command_estimated_separation_mm": describe([row["clr"] * 1000 for row in present]),
            "minimum_command_estimated_separation_mm": minimum_separation,
            "carry_to_delivery_s": meta["carry_to_delivery_s"],
            "maximum_row_age_reconciliation_residual_ms": max(residuals),
            "negative_stage_observations_retained": negatives}


def run_metrics(row):
    moving = row["populations"]["moving_valid"]
    result = {"mean_moving_age_ms": moving["total_age_ms"]["mean"],
              "median_moving_age_ms": moving["total_age_ms"]["median"],
              "p95_moving_age_ms": moving["total_age_ms"]["p95"],
              "max_moving_age_ms": moving["total_age_ms"]["max"],
              "mean_proxy_to_infer_end_ms": moving["proxy_to_infer_end_ms"]["mean"],
              "moving_nohazard_percent": row["moving_nohazard_percent"],
              "moving_decisions": moving["decisions"],
              "hazard_present_moving_decisions": row["populations"]["moving_hazard_present"]["decisions"],
              "minimum_command_estimated_separation_mm": row["minimum_command_estimated_separation_mm"],
              "carry_to_delivery_s": row["carry_to_delivery_s"]}
    result.update({"mean_" + key: moving["stages_ms"][key]["mean"] for key in STAGES})
    return result


def cells(runs, by_direction=False):
    result = []
    directions = ("A", "B") if by_direction else (None,)
    for rate in RATES:
        for method in METHODS:
            for direction in directions:
                selected = sorted([row for row in runs if row["rate"] == rate and row["method"] == method
                                   and (direction is None or row["direction"] == direction)],
                                  key=lambda row: (row["direction"], row["repetition"]))
                if not selected:
                    continue
                metrics = [run_metrics(row) for row in selected]
                conditional = {}
                for name in selected[0]["populations"]:
                    populated = [row for row in selected if row["populations"][name]["decisions"]]
                    info = [row["populations"][name] for row in populated]
                    conditional[name] = {
                        "n_nonempty_runs": len(populated),
                        "run_ids": [row["run"] for row in populated],
                        "decision_count_for_support_only": sum(row["decisions"] for row in info),
                        "metrics": {
                            "mean_age_ms": describe([row["total_age_ms"]["mean"] for row in info]),
                            "median_age_ms": describe([row["total_age_ms"]["median"] for row in info]),
                            "p95_age_ms": describe([row["total_age_ms"]["p95"] for row in info]),
                            **{"mean_" + key: describe([row["stages_ms"][key]["mean"] for row in info])
                               for key in STAGES}}}
                result.append({"method": method, "rate": rate, "direction": direction,
                               "n_runs": len(selected), "run_ids": [row["run"] for row in selected],
                               "metrics": {key: describe([row[key] for row in metrics]) for key in metrics[0]},
                               "populations_equal_run": conditional,
                               "distinct_used_evidence_stages_equal_run": {
                                   key: describe([row["distinct_used_evidence_stage_ms"][key]["mean"] for row in selected])
                                   for key in ("proxy_to_infer_start_ms", "inference_ms", "proxy_to_infer_end_ms")},
                               "count_sums_for_sample_support_only": {
                                   name: sum(row["populations"][name]["decisions"] for row in selected)
                                   for name in selected[0]["populations"]}})
    return result


def tex_tables(result):
    primary = [r"% Decision-conditioned stages; equal-run means, n=4 per cell.",
               r"\begin{tabularx}{\linewidth}{ll>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X}",
               r"\toprule",
               r"Cadence&Method&Proxy to start (ms)&Inference (ms)&End to decision (ms)&Total age (ms)\\", r"\midrule"]
    for cell in result["primary_cells"]:
        fields = ("mean_proxy_to_infer_start_ms", "mean_inference_ms", "mean_infer_end_to_decision_ms", "mean_moving_age_ms")
        primary.append(" & ".join([cell["rate"].title(), cell["method"]]
                       + [f"{cell['metrics'][key]['mean']:.1f}" for key in fields]) + r"\\")
    primary.extend([r"\bottomrule", r"\end{tabularx}"])

    per_run = [r"\begin{table}[H]", r"\centering\small\setlength{\tabcolsep}{3pt}",
               r"\caption{Primary per-run moving-decision support and capture-proxy ages. P95 uses the linear type-7 empirical quantile. No-hazard decisions are retained in the age distribution; absence is not a confirmed obstacle-free scene.}\label{tab:stage-age-support}",
               r"\begin{tabularx}{\linewidth}{lllr*{5}{>{\raggedleft\arraybackslash}X}}", r"\toprule",
               r"Cadence&Method&Goal&Rep.&Moving $n$&No hazard (\%)&Mean (ms)&Median (ms)&P95 (ms)\\", r"\midrule"]
    selected = sorted(result["runs"], key=lambda row: (RATES.index(row["rate"]), METHODS.index(row["method"]), row["direction"], row["repetition"]))
    for row in selected:
        if row["campaign"] != "timed_margin_compare":
            continue
        moving = row["populations"]["moving_valid"]
        values = [row["rate"].title(), row["method"], row["direction"], str(row["repetition"]), str(moving["decisions"]),
                  f"{row['moving_nohazard_percent']:.1f}"] + [f"{moving['total_age_ms'][key]:.1f}" for key in ("mean", "median", "p95")]
        per_run.append(" & ".join(values) + r"\\")
    per_run.extend([r"\bottomrule", r"\end{tabularx}", r"\end{table}"])

    directional = [r"\begin{table}[H]", r"\centering\small\setlength{\tabcolsep}{3pt}",
                   r"\caption{Direction-stratified primary results. Age columns summarize two run-level mean ages per row; SD is the sample standard deviation between runs, not a confidence interval. Stage columns are equal-run means during moving decisions.}\label{tab:stage-age-direction}",
                   r"\begin{tabularx}{\linewidth}{lllr*{5}{>{\raggedleft\arraybackslash}X}}", r"\toprule",
                   r"Cadence&Method&Goal&Runs&Age (ms)&SD (ms)&Proxy--start (ms)&Inference (ms)&End--decision (ms)\\", r"\midrule"]
    for cell in result["primary_direction_cells"]:
        values = [cell["rate"].title(), cell["method"], cell["direction"], str(cell["n_runs"]),
                  f"{cell['metrics']['mean_moving_age_ms']['mean']:.1f}", f"{cell['metrics']['mean_moving_age_ms']['sample_sd']:.1f}"]
        values += [f"{cell['metrics']['mean_' + key]['mean']:.1f}" for key in STAGES]
        directional.append(" & ".join(values) + r"\\")
    directional.extend([r"\bottomrule", r"\end{tabularx}", r"\end{table}"])
    outputs = {"stage_age_primary_table.tex": primary, "stage_age_per_run_table.tex": per_run,
               "stage_age_direction_table.tex": directional}
    for name, lines in outputs.items():
        (HERE / name).write_text("\n".join(lines) + "\n")
    return {str((HERE / name).relative_to(PACKAGE)): digest(HERE / name) for name in outputs}


def build():
    summary_path = ANALYSIS / "hardware_summary.json"
    manifest_path = ANALYSIS / "analysis_manifest.json"
    pattern_path = ANALYSIS / "exploratory_patterns_2026-10-02/pattern_results.json"
    summary = json.loads(summary_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    patterns = json.loads(pattern_path.read_text())
    assert digest(summary_path) == manifest["output_hashes"]["analysis/hardware_summary.json"]
    assert digest(summary_path) == patterns["provenance"]["hardware_summary_sha256"]
    selected_hashes = patterns["provenance"]["selected_source_hashes"]
    assert len(selected_hashes) == 64
    before = {name: digest(PACKAGE / name) for name in selected_hashes}
    assert before == selected_hashes
    pattern_index = {row["run"]: row for row in patterns["runs"]}
    metas = [row for row in summary["all_included_records"] if row["campaign"] in ("timed_margin_compare", "timed_compare_slow")]
    assert len(metas) == 32
    runs = [reconstruct(row, pattern_index[row["run"]]) for row in metas]
    primary = [row for row in runs if row["campaign"] == "timed_margin_compare"]
    pilot = [row for row in runs if row["campaign"] == "timed_compare_slow"]
    result = {
        "scope": "Post-hoc read-only age-stage, dispersion, and sample-support audit; no new robot or simulated transport.",
        "definitions": {
            "stages": {"proxy_to_infer_start_ms": "Source-frame capture proxy to inference start: request/transfer/queue/scheduling aggregate, not exposure-to-receipt latency.",
                       "inference_ms": "Inference start to completion for the accepted evidence used in this decision.",
                       "infer_end_to_decision_ms": "Inference completion to the recorded control decision: accepted-verdict reuse/scheduling time, not inference duration."},
            "population": "Moving is mode != stop; valid is ev_status == ok. Hazard-present means a detected hazard is recorded, not independent obstacle presence.",
            "aggregation": "Within a run, decisions have equal weight. Across a cell, runs have equal weight. Reused bundles repeat at decisions; stage means are conditional on the decisions, not throughput benchmarks.",
            "dispersion": "Sample SD between run-level means; descriptive, no confidence interval or p-value.",
            "quantiles": "Within-run empirical linear Hyndman--Fan type7 (NumPy method=linear), position=(n-1)q.",
            "negative_stages": "Signed stages are never zero-clamped or imputed. All negatives retained; < -5 ms is beyond logged causal-check tolerance.",
            "pilot": "Earlier slow pilot8 is analyzed separately from primary24, not independent-session validation or added repetitions."},
        "selection": {"primary_runs": 24, "pilot_runs_not_pooled": 8, "all_selected_runs_retained": True},
        "primary_cells": cells(primary), "primary_direction_cells": cells(primary, True),
        "pilot_cells_not_pooled": cells(pilot), "pilot_direction_cells_not_pooled": cells(pilot, True),
        "runs": runs,
        "validation": {"selected_decisions": sum(row["all_decisions"] for row in runs),
                       "selected_moving_decisions": sum(row["populations"]["moving_valid"]["decisions"] for row in runs),
                       "invalid_decisions": sum(row["invalid_decisions"] for row in runs),
                       "maximum_row_reconciliation_residual_ms": max(row["maximum_row_age_reconciliation_residual_ms"] for row in runs),
                       "negative_stage_observations_count": sum(len(row["negative_stage_observations_retained"]) for row in runs),
                       "sidecar_decisions_and_producing_evidence_links_verified": True},
        "limitations": ["All timing is capture-proxy based; no validation of true exposure time or transfer-clock error is introduced.",
                        "Motion-conditioned statistics can improve because older decisions are held; they do not measure all-time semantic accuracy.",
                        "Hazard-absent rows are not confirmed obstacle-free rows; missing detections remain in age and support results.",
                        "No causal, physical-risk, independent clearance, whole-arm, or physical standstill conclusion follows.",
                        "Direction-stratified n=2 is descriptive; nonrandomized operator presentation and policy-dependent waiting remain confounded."]}
    assert len(result["primary_cells"]) == 6 and all(row["n_runs"] == 4 for row in result["primary_cells"])
    assert len(result["primary_direction_cells"]) == 12 and all(row["n_runs"] == 2 for row in result["primary_direction_cells"])
    assert len(result["pilot_cells_not_pooled"]) == 2
    output_hashes = tex_tables(result)
    assert {name: digest(PACKAGE / name) for name in before} == before
    result["provenance"] = {"analysis_script_sha256": digest(Path(__file__)),
                            "hardware_summary_sha256": digest(summary_path), "pattern_results_sha256": digest(pattern_path),
                            "selected_source_hashes": before, "selected_source_files_verified": len(before),
                            "selected_sources_unchanged": True, "generated_tables": output_hashes}
    target = HERE / "stage_age_results.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    for cell in result["primary_cells"]:
        print(cell["method"], cell["rate"], {key: round(cell["metrics"][key]["mean"], 3) for key in
              ("mean_proxy_to_infer_start_ms", "mean_inference_ms", "mean_infer_end_to_decision_ms", "mean_moving_age_ms", "moving_nohazard_percent")},
              "age SD", round(cell["metrics"]["mean_moving_age_ms"]["sample_sd"], 3))
    print(json.dumps(result["validation"], indent=2))
    print(target)
    return result


if __name__ == "__main__":
    build()
