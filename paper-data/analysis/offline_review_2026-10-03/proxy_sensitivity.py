"""Hypothetical capture-proxy offset sensitivity on frozen observed decisions.

Only archived package JSON/JSONL inputs are read. No controller, robot, detector,
source log, timestamp, manuscript, or existing result is modified. The primary
24 runs and slow-update pilot 8 runs remain separate. Offsets are assumptions,
not measurements or empirical bounds on exposure-to-proxy delay.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics as st


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
CAMPAIGNS = ("timed_margin_compare", "timed_compare_slow")
METHODS = ("AEGIS", "Trust12", "Trust32")
COMMON_OFFSETS_S = (0.0, 0.05, 0.1, 0.2, 0.3)
DIFFERENTIAL_OFFSETS_S = (-0.3, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.3)
BLOCKS = (("A", 1), ("A", 2), ("B", 1), ("B", 2))
REPORTING_THRESHOLD_S = 0.6


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values):
    values = tuple(values)
    return {"n": len(values), "mean": st.mean(values), "min": min(values),
            "max": max(values),
            "sample_sd": st.stdev(values) if len(values) > 1 else None,
            "individual_values": list(values)}


def extract_moving_ages(record):
    """Return observed non-stop ages and indices without altering any record."""
    if record["time_base"] != "capture_proxy":
        raise ValueError("Only archived capture-proxy records are in scope")
    selected = []
    for index, row in enumerate(record["log"]):
        if row["time_base"] != "capture_proxy":
            raise ValueError("Mixed time bases are not permitted")
        if row.get("ev_status") == "ok":
            reconstructed = row["t_decision"] - row["ev_t_capture"]
            if not math.isclose(row["age_used"], reconstructed, rel_tol=0, abs_tol=1e-8):
                raise ValueError("Recorded age differs from its capture-proxy definition")
        if row["mode"] != "stop":
            age = float(row["age_used"])
            if not math.isfinite(age) or age < 0:
                raise ValueError("Moving decisions must have finite nonnegative proxy ages")
            selected.append((index, age))
    if not selected:
        raise ValueError("No observed moving decisions")
    return tuple(age for _, age in selected), tuple(index for index, _ in selected)


def offset_metrics(ages, offset_s, threshold_s=REPORTING_THRESHOLD_S):
    """Add an assumed common nonnegative delay to the same observed ages."""
    if not math.isfinite(offset_s) or offset_s < 0:
        raise ValueError("Common added offsets must be finite and nonnegative")
    adjusted = tuple(age + offset_s for age in ages)
    if not adjusted:
        raise ValueError("No ages to summarize")
    above = sum(age > threshold_s for age in adjusted)
    return {"mean_age_s": st.mean(adjusted),
            "moving_decisions": len(adjusted),
            "above_threshold_decisions": above,
            "above_threshold_percent": 100 * above / len(adjusted)}


def relative_mean_gap(aegis_mean_s, reference_mean_s, differential_offset_s):
    """AEGIS-minus-reference gap when Delta = delta_AEGIS - delta_reference.

    Signed Delta determines the difference only. It does not identify either
    absolute corrected age or a threshold fraction, and is never inserted into
    source timestamps or interpreted as a negative exposure age.
    """
    return aegis_mean_s - reference_mean_s + differential_offset_s


def gap_rank(gap_s):
    if abs(gap_s) <= 1e-12:
        return "equal_mean_age"
    return "AEGIS_lower_mean_age" if gap_s < 0 else "reference_lower_mean_age"


def load_verified_runs(package=PACKAGE):
    summary_path = package / "analysis/hardware_summary.json"
    manifest_path = package / "analysis/analysis_manifest.json"
    summary = json.loads(summary_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if digest(summary_path) != manifest["output_hashes"]["analysis/hardware_summary.json"]:
        raise ValueError("Hardware summary does not match existing manifest")
    selected = [meta for meta in summary["all_included_records"]
                if meta["campaign"] in CAMPAIGNS]
    if len(selected) != 32:
        raise ValueError("Expected all 24 primary and all 8 slow-pilot runs")
    source_hashes = {}
    for meta in selected:
        prefix = f"data/{meta['campaign']}/logs/{meta['run']}"
        for suffix in (".json", "_timing.jsonl"):
            name = prefix + suffix
            observed = digest(package / name)
            if observed != manifest["archived_data"][name]:
                raise ValueError(f"Archived source hash mismatch: {name}")
            source_hashes[name] = observed
    before = {"analysis/hardware_summary.json": digest(summary_path),
              "analysis/analysis_manifest.json": digest(manifest_path), **source_hashes}
    runs = []
    for meta in selected:
        name = f"data/{meta['campaign']}/logs/{meta['run']}.json"
        record = json.loads((package / name).read_text())
        ages, indices = extract_moving_ages(record)
        mean_age = st.mean(ages)
        old_fraction = offset_metrics(ages, 0)["above_threshold_percent"]
        if not math.isclose(mean_age, meta["mean_moving_evidence_age_s"], abs_tol=1e-9):
            raise ValueError("Reconstruction differs from existing per-run mean")
        if not math.isclose(old_fraction, meta["moving_age_above_0p6_percent"], abs_tol=1e-9):
            raise ValueError("Reconstruction differs from existing per-run age fraction")
        runs.append({"run": meta["run"], "campaign": meta["campaign"],
                     "method": meta["method"], "rate": meta["rate"],
                     "direction": meta["direction"],
                     "repetition": int(meta["run"].rsplit("_", 1)[1]),
                     "ages_s": ages, "observed_mean_age_s": mean_age,
                     "moving_decisions": len(ages),
                     "moving_indices_sha256": hashlib.sha256(
                         json.dumps(indices, separators=(",", ":")).encode()).hexdigest()})
    return runs, before


def analyze_cohort(runs, cohort):
    rates = [rate for rate in ("normal", "slow") if any(row["rate"] == rate for row in runs)]
    methods = [method for method in METHODS if any(row["method"] == method for row in runs)]
    index = {(row["method"], row["rate"], row["direction"], row["repetition"]): row for row in runs}
    common = []
    differential = []
    per_run = []
    for row in runs:
        per_run.append({key: row[key] for key in (
            "run", "campaign", "method", "rate", "direction", "repetition",
            "observed_mean_age_s", "moving_decisions", "moving_indices_sha256")})
        per_run[-1]["common_offset_metrics"] = [
            {"assumed_added_offset_s": offset, **offset_metrics(row["ages_s"], offset)}
            for offset in COMMON_OFFSETS_S]
    for rate in rates:
        observed = {method: st.mean(index[method, rate, direction, repetition]["observed_mean_age_s"]
                                   for direction, repetition in BLOCKS) for method in methods}
        for offset in COMMON_OFFSETS_S:
            cells = []
            for method in methods:
                selected = [index[method, rate, direction, repetition] for direction, repetition in BLOCKS]
                metrics = [offset_metrics(row["ages_s"], offset) for row in selected]
                cells.append({"method": method, "n_runs": len(selected),
                              "run_ids": [row["run"] for row in selected],
                              "mean_age_s": describe(metric["mean_age_s"] for metric in metrics),
                              "above_threshold_percent": describe(metric["above_threshold_percent"]
                                                                  for metric in metrics),
                              "observed_moving_decisions_total": sum(row["moving_decisions"] for row in selected)})
            common.append({"rate": rate, "assumed_common_added_offset_s": offset,
                           "cells": cells,
                           "mean_age_rank_lower_is_fresher": sorted(methods, key=lambda method: observed[method]),
                           "AEGIS_minus_reference_mean_age_s": {
                               reference: relative_mean_gap(observed["AEGIS"], observed[reference], 0)
                               for reference in methods if reference != "AEGIS"}})
        for reference in methods:
            if reference == "AEGIS":
                continue
            nominal_blocks = []
            for direction, repetition in BLOCKS:
                ae = index["AEGIS", rate, direction, repetition]
                ref = index[reference, rate, direction, repetition]
                nominal_blocks.append({"direction": direction, "repetition": repetition,
                                       "AEGIS_run": ae["run"], "reference_run": ref["run"],
                                       "reference_minus_AEGIS_mean_age_s": ref["observed_mean_age_s"] - ae["observed_mean_age_s"]})
            gap = observed[reference] - observed["AEGIS"]
            minimum_gap = min(block["reference_minus_AEGIS_mean_age_s"] for block in nominal_blocks)
            differential.append({"rate": rate, "reference": reference,
                                 "observed_AEGIS_mean_age_s": observed["AEGIS"],
                                 "observed_reference_mean_age_s": observed[reference],
                                 "observed_reference_minus_AEGIS_mean_age_s": gap,
                                 "mean_gap_break_even_differential_offset_s": gap,
                                 "minimum_nominal_block_reference_minus_AEGIS_gap_s": minimum_gap,
                                 "all_four_nominal_blocks_AEGIS_lower_observed_mean_age": minimum_gap > 0,
                                 "nominal_blocks": nominal_blocks,
                                 "relative_offset_scenarios": [
                                     {"assumed_AEGIS_minus_reference_offset_s": delta,
                                      "AEGIS_minus_reference_adjusted_mean_age_s": relative_mean_gap(
                                          observed["AEGIS"], observed[reference], delta),
                                      "mean_age_order": gap_rank(relative_mean_gap(
                                          observed["AEGIS"], observed[reference], delta)),
                                      "nominal_blocks_AEGIS_lower_adjusted_mean_age": sum(
                                          delta < block["reference_minus_AEGIS_mean_age_s"] - 1e-12
                                          for block in nominal_blocks)} for delta in DIFFERENTIAL_OFFSETS_S]})
    return {"cohort": cohort, "n_runs": len(runs), "per_run": per_run,
            "common_offset_scenarios": common, "method_differential_offset_contrasts": differential}


def analyze(runs):
    primary = [row for row in runs if row["campaign"] == "timed_margin_compare"]
    pilot = [row for row in runs if row["campaign"] == "timed_compare_slow"]
    if len(primary) != 24 or len(pilot) != 8:
        raise ValueError("Primary and pilot cohorts must be complete and separate")
    return {"scope": "Offline sensitivity of recorded capture-proxy ages, with observed non-stop decisions frozen; no controller rerun or new physical result.",
            "selection": {"primary_runs": 24, "slow_pilot_runs_analyzed_separately": 8,
                          "all_primary_and_pilot_runs_retained": True},
            "definitions": {
                "observed_moving_decisions": "Existing log rows with mode != stop, including rows without a detected hazard; indices and decision counts fixed for every scenario.",
                "common_offset": "a_i(c) = recorded_age_i + c; the same assumed added c applies to every decision, method and run. c is not a measured delay or a bound.",
                "differential_offset": "Delta = delta_AEGIS - delta_reference; adjusted AEGIS-minus-reference mean gap = observed gap + Delta. Negative Delta means larger unmeasured added delay for the reference, not negative exposure age.",
                "relative_offset_tail_not_identified": "A relative Delta alone does not identify absolute corrected ages or >0.6 s fractions. Those fractions are evaluated only for explicitly common absolute added offsets.",
                "aggregation": "Decision-weighted within each run, then equal-weight average over four runs per method/cadence cell. No across-run decision pooling.",
                "threshold": "Strict age >0.6 s reporting reference, not a validated safety boundary.",
                "break_even": "Delta_star = mean_reference - mean_AEGIS. At equality means tie; a larger Delta makes AEGIS mean age higher. Minimum signed nominal-block gap is descriptive, not a statistical error bound.",
                "pairing": "A1,A2,B1,B2 filename/direction/repetition matches are nominal, not randomized or identical obstacle presentations."},
            "hypothetical_common_added_offsets_s": list(COMMON_OFFSETS_S),
            "hypothetical_differential_offsets_s": list(DIFFERENTIAL_OFFSETS_S),
            "reporting_threshold_s": REPORTING_THRESHOLD_S,
            "primary": analyze_cohort(primary, "24-run primary campaign"),
            "slow_pilot_not_pooled": analyze_cohort(pilot, "8-run slow-update pilot, separate from primary"),
            "limitations": [
                "No exposure-ground-truth timestamp or empirical exposure-to-proxy error bound is available; offsets are unmeasured illustrative assumptions.",
                "A common constant offset preserves all mean differences and mean-age rankings algebraically, but changes the >0.6 s reporting fractions.",
                "Method-dependent added delay can erase or reverse the mean-age difference; a common-offset result is not evidence that such differential bias is absent.",
                "Observed movement selection is frozen. This analysis does not recalculate controller decisions, margins, alternate trajectories, transport time or physical safety.",
                "Frame-specific jitter and run-specific offsets are not modeled by this constant-offset exercise.",
                "Four nonrandomized, operator-managed same-session runs per cell provide descriptive observations, not causal or population inference."]}


def table_tex(result):
    lines = ["% Generated hypothetical proxy-offset sensitivity; existing observed movement mask frozen.",
             r"\begin{table}[H]", r"\centering\footnotesize",
             r"\caption{Hypothetical timing-offset sensitivity on frozen observed moving decisions. Entries in the upper panels are equal-run mean age (ms) / percentage of moving decisions with age strictly above 0.6~s, averaged across four runs per cell. Added offsets are unmeasured assumptions, not exposure timestamps or empirical error bounds. A common constant preserves mean differences but changes threshold fractions. The lower panel gives signed break-even $\Delta^*=\overline a_{\rm ref}-\overline a_{\rm AEGIS}$ for $\Delta=\delta_{\rm AEGIS}-\delta_{\rm ref}$; larger $\Delta$ makes AEGIS mean age higher. Nominal-block minima are descriptive only. No controller or physical trajectory is rerun.}\label{tab:proxy-offset}",
             r"\begin{tabular}{llrrr}", r"\toprule",
             r"Cohort / cadence & Added $c$ (ms) & AEGIS & Trust12 & Trust32\\", r"\midrule"]
    for key, prefix in (("primary", "Primary"), ("slow_pilot_not_pooled", "Pilot (separate)")):
        for scenario in result[key]["common_offset_scenarios"]:
            cells = {cell["method"]: cell for cell in scenario["cells"]}
            entries = []
            for method in METHODS:
                cell = cells.get(method)
                entries.append("---" if cell is None else
                               f"{cell['mean_age_s']['mean'] * 1000:.1f} / {cell['above_threshold_percent']['mean']:.1f}")
            lines.append(" & ".join([f"{prefix}, {scenario['rate']}",
                                      f"{scenario['assumed_common_added_offset_s'] * 1000:.0f}"] + entries) + r"\\")
        lines.append(r"\midrule")
    lines.extend([r"Cohort / cadence & Reference & $\Delta^*$ (ms) & Min. block (ms) & All four $>0$?\\",
                  r"\midrule"])
    for key, prefix in (("primary", "Primary"), ("slow_pilot_not_pooled", "Pilot (separate)")):
        for contrast in result[key]["method_differential_offset_contrasts"]:
            lines.append(" & ".join([f"{prefix}, {contrast['rate']}", contrast["reference"],
                                      f"{contrast['mean_gap_break_even_differential_offset_s'] * 1000:+.1f}",
                                      f"{contrast['minimum_nominal_block_reference_minus_AEGIS_gap_s'] * 1000:+.1f}",
                                      "Yes" if contrast["all_four_nominal_blocks_AEGIS_lower_observed_mean_age"] else "No"]) + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines) + "\n"


def build(package=PACKAGE, output_dir=HERE):
    runs, before = load_verified_runs(package)
    result = analyze(runs)
    after = {name: digest(package / name) for name in before}
    if before != after:
        raise ValueError("An input changed during analysis")
    result["provenance"] = {"analysis_script_sha256": digest(Path(__file__)),
                            "source_hashes_before": before, "source_hashes_after": after,
                            "archived_JSON_JSONL_files_verified": len(before) - 2,
                            "inputs_unchanged": True,
                            "only_archived_package_sources_read": True}
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "proxy_sensitivity_results.json"
    table_path = output_dir / "proxy_sensitivity_table.tex"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    table_path.write_text(table_tex(result))
    final = {name: digest(package / name) for name in before}
    if final != before:
        raise ValueError("An input changed while derived outputs were written")
    manifest = {"scope": result["scope"], "inputs_unchanged": True,
                "source_hashes_before": before, "source_hashes_after": final,
                "analysis_script_sha256": digest(Path(__file__)),
                "output_hashes": {str(path.relative_to(output_dir)): digest(path)
                                  for path in (result_path, table_path)}}
    manifest_path = output_dir / "proxy_sensitivity_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    for key in ("primary", "slow_pilot_not_pooled"):
        for contrast in result[key]["method_differential_offset_contrasts"]:
            print(key, contrast["rate"], contrast["reference"],
                  "break-even Delta (ms):", round(contrast["mean_gap_break_even_differential_offset_s"] * 1000, 3),
                  "minimum nominal-block gap (ms):", round(contrast["minimum_nominal_block_reference_minus_AEGIS_gap_s"] * 1000, 3))
    print("Verified unchanged input hashes:", len(before))
    print("Results:", result_path)
    print("Table:", table_path)
    return result


if __name__ == "__main__":
    build()
