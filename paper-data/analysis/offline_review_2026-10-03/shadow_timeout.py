"""Read-only semantic-gate shadow assay on genuine logged AEGIS input streams.

This is not a simulated or physical experiment and does not replay the planner.
The logged score preserves AEGIS's actual hidden anchor/reset history. Comparator
permissions are evaluated on the SAME observed rows, not on invented comparator
trajectories or additional trials. Primary and earlier pilot streams stay separate.
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics as st

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
ANALYSIS = PACKAGE / "analysis"
P_PRIOR, P_STOP, T_DECAY, RELIABILITY = .65, .50, .40, .95
CLOCK_TOL_S, SENSING_STALE_S = .005, .6
ANALYTIC_TIMEOUT = -T_DECAY * math.log((P_PRIOR - P_STOP) / P_PRIOR)
TIMEOUTS = (("analytic", ANALYTIC_TIMEOUT), ("0.400", .4), ("0.500", .5),
            ("0.566", .566), ("0.587", .587), ("0.700", .7), ("0.800", .8))
BETAS = (.012, .032)
CODE_FILES = ("clasp_policy.py", "aegis_time.py", "timed_variants.py", "timed_compare_run.py")
HOLD_STATUSES = {"no_verdict", "vlm_error", "invalid_time", "out_of_order"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def times_valid(row):
    """Archived causal-order checks, plus finite decision time for this offline audit."""
    values = [row.get(k) for k in ("ev_t_capture", "ev_t_infer_start", "ev_t_infer_end", "t_decision")]
    if not all(finite(v) for v in values):
        return False
    capture, start, end, now = values
    return (capture <= start + CLOCK_TOL_S and end >= start
            and capture <= now + CLOCK_TOL_S and end <= now + CLOCK_TOL_S)


def common_guard(row):
    """Shared evidence/HUMAN/sensing/depth/destination holds, not planner geometry.

    Destination and stale-sensing branches do not expose the precise hs supplied to
    the gate. They are common held/excluded rows, never reconstructed geometry.
    A geometry stop is NOT made common: changing a margin could change the planner.
    """
    status = row.get("ev_status")
    if status in HOLD_STATUSES:
        return "evidence:" + status
    if status != "ok":
        return "unknown_evidence_status"
    if row.get("ev_error") is not None or row.get("ev_verdict") not in ("human", "object"):
        return "vlm_error"
    if not times_valid(row):
        return "invalid_time"
    age = row.get("age_used")
    if not finite(age) or abs(age - (row["t_decision"] - row["ev_t_capture"])) > 1e-8:
        return "invalid_age"
    sensing = row.get("sensing_age")
    if row.get("stop_reason") == "evidence:sensing_stale" or (finite(sensing) and sensing > SENSING_STALE_S):
        return "sensing_stale"
    if row.get("stop_reason") == "goal_occupied":
        return "goal_occupied"
    if row.get("ev_verdict") == "human":
        return "human"
    if row.get("depth_only"):
        return "depth_only"
    return None


def compare_row(row, timeout_s, beta_m):
    """Semantic permission only; no proposed commands or physical motion output."""
    if not finite(timeout_s) or timeout_s < 0 or not finite(beta_m) or beta_m < 0:
        raise ValueError("Timeout and fixed buffer must be finite and nonnegative")
    guard = common_guard(row)
    present = row.get("haz") is not None
    if guard is not None:
        return {"common_guard": guard, "hazard_present": present,
                "aegis_hold": True, "timeout_hold": True, "disagree": False,
                "eligible_object_hazard": False, "both_permitted": False,
                "aegis_margin_m": None, "timeout_margin_m": None}
    score = row.get("p")
    margin = row.get("margin")
    if not finite(score) or not 0 <= score <= 1 or not finite(margin) or margin < 0:
        raise ValueError("Missing/invalid genuine logged score or margin")
    # Match the actual AEGIS hazard-conditional score gate. Global timeout is not
    # used: no hazard bypasses both semantic-score and semantic-age holds.
    aegis_hold = present and score >= P_STOP
    timeout_hold = present and row["age_used"] >= timeout_s
    both_permitted = present and not aegis_hold and not timeout_hold
    return {"common_guard": None, "hazard_present": present,
            "aegis_hold": bool(aegis_hold), "timeout_hold": bool(timeout_hold),
            "disagree": bool(aegis_hold != timeout_hold),
            "eligible_object_hazard": present, "both_permitted": both_permitted,
            "aegis_margin_m": margin if present else 0.,
            "timeout_margin_m": beta_m if present else 0.}


def describe(values):
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {"n": len(values), "mean": st.mean(values), "min": min(values), "max": max(values),
            "sample_sd": st.stdev(values) if len(values) > 1 else None,
            "individual_values": list(values)}


def summarize_comparisons(comparisons):
    n = len(comparisons)
    eligible = [v for v in comparisons if v["eligible_object_hazard"]]
    permitted = [v for v in eligible if v["both_permitted"]]
    margins = [v["aegis_margin_m"] * 1000 for v in permitted]
    gaps = [(v["aegis_margin_m"] - v["timeout_margin_m"]) * 1000 for v in permitted]
    return {
        "all_decisions": n, "common_held_decisions": sum(v["common_guard"] is not None for v in comparisons),
        "common_guard_reasons": dict(Counter(v["common_guard"] for v in comparisons if v["common_guard"])),
        "no_hazard_and_common_clear_decisions": sum(not v["hazard_present"] and v["common_guard"] is None for v in comparisons),
        "eligible_object_hazard_decisions": len(eligible),
        "semantic_aegis_held_decisions": sum(v["aegis_hold"] for v in eligible),
        "semantic_timeout_held_decisions": sum(v["timeout_hold"] for v in eligible),
        "disagreements": sum(v["disagree"] for v in eligible),
        "aegis_only_holds": sum(v["aegis_hold"] and not v["timeout_hold"] for v in eligible),
        "timeout_only_holds": sum(v["timeout_hold"] and not v["aegis_hold"] for v in eligible),
        "disagreement_percent": 100 * sum(v["disagree"] for v in eligible) / len(eligible) if eligible else None,
        "both_permitted_object_hazard_decisions": len(permitted),
        "both_permitted_aegis_margin_mm": describe(margins),
        "both_permitted_margin_gap_aegis_minus_timeout_mm": describe(gaps),
        "both_permitted_aegis_margin_below_timeout_percent": 100 * st.mean(v < -1e-8 for v in gaps) if gaps else None,
    }


def static_constants(path):
    result = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def validate_archived_constants():
    clasp = static_constants(PACKAGE / "provenance_code/safebench/clasp_policy.py")
    clock = static_constants(PACKAGE / "provenance_code/safebench/aegis_time.py")
    assert all(clasp[name] == value for name, value in (("P_PRIOR", P_PRIOR), ("P_STOP", P_STOP),
               ("T_DECAY", T_DECAY), ("RELIABILITY", RELIABILITY)))
    assert clock["CLOCK_TOL_S"] == CLOCK_TOL_S and clock["SENSING_STALE_S"] == SENSING_STALE_S


def load_run(meta):
    source = PACKAGE / "data" / meta["campaign"] / "logs" / (meta["run"] + ".json")
    sidecar = source.with_name(source.stem + "_timing.jsonl")
    data = json.loads(source.read_text())
    ledger = [json.loads(line) for line in sidecar.read_text().splitlines()]
    decisions = [row for row in ledger if row.get("type") == "decision"]
    assert len(decisions) == len(data["log"])
    for row, copied in zip(data["log"], decisions):
        assert row == {k: v for k, v in copied.items() if k != "type"}
        assert row["time_base"] == "capture_proxy" and row["variant"] == "AEGIS-sensor-time"
        assert common_guard(row) not in ("unknown_evidence_status", "vlm_error", "invalid_time", "invalid_age")
        if common_guard(row) is None:
            expected = (.012 + .048 * row["p"]) if row["haz"] is not None else 0.
            assert abs(expected - row["margin"]) < 1e-12
            assert (row["stop_reason"] == "belief>=P_STOP") == (row["haz"] is not None and row["p"] >= P_STOP)
    params = data["clasp_params"]
    assert params["r_human"] == .06 and params["d_mech"] == .012 and params["epi"] == .012
    for name in CODE_FILES:
        archived = PACKAGE / "provenance_code/safebench" / name
        assert digest(archived) == data["provenance"]["files_sha256"]["safebench/" + name]
    return data["log"], source, sidecar


def run_assay(meta, rows):
    comparisons = {}
    output_rows = []
    for row_index, row in enumerate(rows):
        result = {"run": meta["run"], "campaign": meta["campaign"], "rate": meta["rate"],
                  "row_index": row_index, "t_decision": row["t_decision"], "age_used_s": row.get("age_used"),
                  "logged_score": row["p"], "logged_margin_m": row["margin"],
                  "logged_mode": row["mode"], "logged_stop_reason": row.get("stop_reason"),
                  "comparisons": {}}
        for timeout_name, timeout_s in TIMEOUTS:
            for beta in BETAS:
                key = f"Trust{int(beta * 1000)}+timeout-{timeout_name}"
                comparison = compare_row(row, timeout_s, beta)
                result["comparisons"][key] = comparison
                comparisons.setdefault(key, []).append(comparison)
        output_rows.append(result)
    metrics = {key: summarize_comparisons(values) for key, values in comparisons.items()}
    return {"run": meta["run"], "campaign": meta["campaign"], "rate": meta["rate"],
            "direction": meta["direction"], "repetition": int(meta["run"].rsplit("_", 1)[1]),
            "comparisons": metrics}, output_rows


def aggregate(runs):
    result = []
    for campaign, rate in sorted({(v["campaign"], v["rate"]) for v in runs}):
        selected = [v for v in runs if (v["campaign"], v["rate"]) == (campaign, rate)]
        cell = {"campaign": campaign, "rate": rate, "runs": len(selected),
                "run_ids": [v["run"] for v in selected], "comparisons": {}}
        for key in selected[0]["comparisons"]:
            values = [v["comparisons"][key] for v in selected]
            count_keys = ("all_decisions", "common_held_decisions", "eligible_object_hazard_decisions", "disagreements",
                          "aegis_only_holds", "timeout_only_holds", "both_permitted_object_hazard_decisions",
                          "semantic_aegis_held_decisions", "semantic_timeout_held_decisions")
            summary = {"pooled_row_counts_descriptive_only": {name: sum(v[name] for v in values) for name in count_keys},
                       "equal_run_disagreement_percent": describe([v["disagreement_percent"] for v in values]),
                       "equal_run_aegis_permission_percent_on_eligible_object_hazard": describe([
                           100 * (1 - v["semantic_aegis_held_decisions"] / v["eligible_object_hazard_decisions"]) for v in values]),
                       "equal_run_timeout_permission_percent_on_eligible_object_hazard": describe([
                           100 * (1 - v["semantic_timeout_held_decisions"] / v["eligible_object_hazard_decisions"]) for v in values])}
            for metric in ("both_permitted_aegis_margin_mm", "both_permitted_margin_gap_aegis_minus_timeout_mm"):
                summary["equal_run_" + metric] = describe([v[metric]["mean"] for v in values if v[metric]["mean"] is not None])
            summary["equal_run_both_permitted_aegis_margin_below_timeout_percent"] = describe([
                v["both_permitted_aegis_margin_below_timeout_percent"] for v in values if v["both_permitted_aegis_margin_below_timeout_percent"] is not None])
            cell["comparisons"][key] = summary
        result.append(cell)
    return result


def latex_table(cells):
    lines = [r"\begin{tabularx}{\textwidth}{lrrrr}", r"\toprule",
             r"Recorded AEGIS stream & $n$ runs & Eligible rows & Disagreements & Margin (mm)\\",
             r"\midrule"]
    for cell in cells:
        item = cell["comparisons"]["Trust32+timeout-analytic"]
        count = item["pooled_row_counts_descriptive_only"]
        label = ("Primary " + cell["rate"]) if cell["campaign"] == "timed_margin_compare" else "Earlier slow pilot"
        lines.append(f"{label} & {cell['runs']} & {count['eligible_object_hazard_decisions']} & "
                     f"{count['disagreements']} & {item['equal_run_both_permitted_aegis_margin_mm']['mean']:.1f}" + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabularx}"])
    return "\n".join(lines) + "\n"


def main():
    validate_archived_constants()
    summary_path = ANALYSIS / "hardware_summary.json"
    manifest_path = ANALYSIS / "analysis_manifest.json"
    summary, manifest = json.loads(summary_path.read_text()), json.loads(manifest_path.read_text())
    assert digest(summary_path) == manifest["output_hashes"]["analysis/hardware_summary.json"]
    protected = {PACKAGE / name: value for name, value in manifest["archived_data"].items()}
    before = {path: digest(path) for path in protected}
    assert before == protected and len(before) == 184
    code_paths = [PACKAGE / "provenance_code/safebench" / name for name in CODE_FILES]
    code_before = {path: digest(path) for path in code_paths}
    selected = [v for v in summary["all_included_records"] if v["method"] == "AEGIS"
                and v["campaign"] in ("timed_margin_compare", "timed_compare_slow")]
    assert len(selected) == 12
    runs, all_rows, selected_hashes = [], [], {}
    for meta in selected:
        rows, source, sidecar = load_run(meta)
        selected_hashes.update({str(p.relative_to(PACKAGE)): digest(p) for p in (source, sidecar)})
        result, derived_rows = run_assay(meta, rows)
        runs.append(result)
        all_rows.extend(derived_rows)
    cells = aggregate(runs)
    assert {path: digest(path) for path in protected} == before
    assert {path: digest(path) for path in code_paths} == code_before
    output = {
        "date": "2026-10-03", "analysis_type": "On-policy, same-input semantic-gate shadow assay; not a new trial",
        "selection": {"genuine_primary_AEGIS_runs": 8, "genuine_pilot_AEGIS_runs_separate": 4,
                      "all_eligible_rows_retained": True, "cross_feed_Trust_streams_not_used": True},
        "constants": {"P_PRIOR": P_PRIOR, "P_STOP": P_STOP, "T_DECAY_s": T_DECAY, "RELIABILITY": RELIABILITY,
                      "zero_OBJECT_anchor_analytic_timeout_s": ANALYTIC_TIMEOUT,
                      "first_OBJECT_anchor_timeout_s": -T_DECAY * math.log((P_PRIOR - P_STOP) / (P_PRIOR - (1 - RELIABILITY) * P_PRIOR)),
                      "timeout_sweep": dict(TIMEOUTS), "fixed_buffers_m": list(BETAS)},
        "definitions": {
            "permission": "Absence of common logged guards and absence of hazard-conditional semantic hold; not a planner command",
            "common_guards": "Evidence integrity, direct HUMAN, stale sensing, depth-only, and logged destination hold",
            "hazard_conditional_timeout": "Hold on OBJECT evidence if a hazard is present and age >= timeout; no-hazard matches AEGIS bypass",
            "geometry": "Planner/geometry stops are not held common because comparator margins can change routes",
            "margin_comparison": "Genuine logged AEGIS margin versus fixed beta only on OBJECT+hazard rows both semantic gates permit",
            "aggregation": "Equal weight per observed run; pooled row counts are descriptive accounting, not independent sample size",
            "state": "Use actual logged AEGIS score, not guessed anchor/reset states or synthetic state on Trust streams",
        },
        "cells": cells, "runs": runs,
        "limitations": [
            "The recorded AEGIS decisions influence trajectories, waiting, observations, and operator timing. These streams are not policy-independent exogenous tests.",
            "Settling gate snapshots and all hidden blob-reset/anchor history are not independently reconstructible for a full cross-feed replay; logged scores preserve actual on-policy state only.",
            "Destination and stale-sensing branches mask the underlying hazard snapshot; they are common held/excluded rows, not reconstructed geometry.",
            "No proposed planner path, physical movement, collision risk, delivery time, or closed-loop timeout success is inferred.",
            "One conditional timeout reproducing semantic permission does not prove full controllers equivalent; their margins and hypothetical planner routes may differ.",
            "Reported margin differences use estimated geometry and logged scores, not measured physical safety distances.",
            "There is no significance test, randomized baseline trial, or newly executed hardware/simulation result.",
        ],
        "provenance": {"analysis_script_sha256": digest(Path(__file__)), "hardware_summary_sha256": digest(summary_path),
                       "existing_manifest_sha256": digest(manifest_path), "archived_sources_verified": 184,
                       "archived_sources_unchanged": True, "selected_source_hashes": selected_hashes,
                       "archived_code_sha256": {str(p.relative_to(PACKAGE)): value for p, value in code_before.items()},
                       "archived_code_constants_and_claimed_run_hashes_verified": True},
    }
    json_path = HERE / "shadow_timeout_results.json"
    jsonl_path = HERE / "shadow_timeout_decisions.jsonl"
    tex_path = HERE / "shadow_timeout_table.tex"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    jsonl_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in all_rows) + "\n")
    tex_path.write_text(latex_table(cells))
    artifacts = {str(p.relative_to(PACKAGE)): digest(p) for p in (json_path, jsonl_path, tex_path)}
    (HERE / "shadow_timeout_manifest.json").write_text(json.dumps({"analysis_script_sha256": digest(Path(__file__)),
        "derived_artifact_sha256": artifacts, "raw_sources_unchanged": True}, indent=2) + "\n")
    for cell in cells:
        print(cell["campaign"], cell["rate"], cell["comparisons"]["Trust32+timeout-analytic"])
    print("Derived rows:", len(all_rows), "Results:", json_path)


if __name__ == "__main__":
    main()
