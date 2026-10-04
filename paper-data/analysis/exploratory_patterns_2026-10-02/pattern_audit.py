"""Read-only post-hoc pattern audit of the frozen hardware results.

This does not run a robot, change a manuscript, or rewrite an observation.
Only derived JSON/PNG artifacts are written beside this script. Cadence and
method contrasts are descriptive: suffix/direction matches are nominal blocks,
not randomized, identical obstacle presentations. No p-values are computed.
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
BLOCKS = (("A", 1), ("A", 2), ("B", 1), ("B", 2))
METRICS = ("mean_moving_age_ms", "minimum_command_estimated_separation_mm",
           "carry_to_delivery_s", "moving_old_evidence_percent")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values):
    return {"n": len(values), "mean": st.mean(values), "median": st.median(values),
            "min": min(values), "max": max(values),
            "sample_sd": st.stdev(values) if len(values) > 1 else None,
            "individual_values": list(values)}


def category(row):
    if row["mode"] != "stop":
        return "moving_decision"
    reason = row.get("stop_reason")
    if isinstance(reason, str) and reason.startswith("evidence:"):
        return "evidence_hold"
    return {"belief>=P_STOP": "score_hold", "geometry": "geometry_hold",
            "human": "human_hold", "goal_occupied": "destination_hold",
            "depth_only": "depth_only_hold"}.get(reason, "other_hold")


def reconstruct(meta):
    path = PACKAGE / "data" / meta["campaign"] / "logs" / (meta["run"] + ".json")
    sidecar = path.with_name(meta["run"] + "_timing.jsonl")
    record = json.loads(path.read_text())
    rows = record["log"]
    ledger = [json.loads(line) for line in sidecar.read_text().splitlines()]
    events = [row for row in ledger if row.get("type") == "event"]
    start = next(row["t"] for row in events if row.get("text", "").startswith("carrying"))
    end = next(row["t"] for row in reversed(events) if row.get("text") == "object delivered at goal")
    moving = [row for row in rows if row["mode"] != "stop"]
    hazard = [row for row in moving if row.get("haz") is not None]
    ages = [row["age_used"] for row in moving]
    assert ages and all(math.isfinite(age) and age >= 0 for age in ages)
    for row in rows:
        assert row["time_base"] == "capture_proxy"
        if row.get("ev_status") == "ok":
            assert abs(row["age_used"] - (row["t_decision"] - row["ev_t_capture"])) < 1e-8
    occupancy = Counter()
    old_moving_interval = 0.
    total_moving_interval = 0.
    for row, nxt in zip(rows[:-1], rows[1:]):
        interval = nxt["t_decision"] - row["t_decision"]
        assert interval > 0
        occupancy[category(row)] += interval
        if row["mode"] != "stop":
            total_moving_interval += interval
            old_moving_interval += interval * (row["age_used"] > .6)
    initial = rows[0]["t_decision"] - start
    tail = end - rows[-1]["t_decision"]
    assert initial >= 0 and tail >= 0
    assert abs(initial + sum(occupancy.values()) + tail - (end - start)) < 1e-7
    result = {"run": meta["run"], "campaign": meta["campaign"],
              "method": meta["method"], "rate": meta["rate"],
              "direction": meta["direction"], "repetition": int(meta["run"].rsplit("_", 1)[1]),
              "mean_moving_age_ms": st.mean(ages) * 1000,
              "median_moving_age_ms": st.median(ages) * 1000,
              "max_moving_age_ms": max(ages) * 1000,
              "mean_hazard_moving_age_ms": st.mean(row["age_used"] for row in hazard) * 1000 if hazard else None,
              "minimum_command_estimated_separation_mm": min(row["clr"] for row in hazard) * 1000 if hazard else None,
              "carry_to_delivery_s": end - start,
              "moving_old_evidence_percent": st.mean(age > .6 for age in ages) * 100,
              "hazard_moving_old_evidence_percent": st.mean(row["age_used"] > .6 for row in hazard) * 100 if hazard else None,
              "moving_decisions": len(moving), "hazard_moving_decisions": len(hazard),
              "moving_no_hazard_percent": 100 * (len(moving) - len(hazard)) / len(moving),
              "old_moving_decisions": sum(age > .6 for age in ages),
              "old_moving_with_hazard": sum(row["age_used"] > .6 for row in hazard),
              "old_moving_interval_percent": 100 * old_moving_interval / total_moving_interval,
              "software_occupancy_s": dict(occupancy),
              "initial_unassigned_s": initial, "final_unassigned_s": tail}
    previous_metrics = {"mean_moving_age_ms": ("mean_moving_evidence_age_s", 1000),
                        "minimum_command_estimated_separation_mm": ("min_command_estimated_edge_separation_mm", 1),
                        "carry_to_delivery_s": ("carry_to_delivery_s", 1),
                        "moving_old_evidence_percent": ("moving_age_above_0p6_percent", 1)}
    for key, (old_key, scale) in previous_metrics.items():
        assert result[key] is not None
        assert abs(result[key] - meta[old_key] * scale) < 1e-7, (meta["run"], key)
    return result


def cells(runs):
    result = []
    for rate in sorted({row["rate"] for row in runs}):
        for method in sorted({row["method"] for row in runs}):
            selected = [row for row in runs if (row["method"], row["rate"]) == (method, rate)]
            if not selected:
                continue
            result.append({"method": method, "rate": rate, "run_ids": [row["run"] for row in selected],
                           "n": len(selected),
                           "metrics": {key: describe([row[key] for row in selected]) for key in METRICS},
                           "mean_score_hold_interval_s": st.mean(row["software_occupancy_s"].get("score_hold", 0.) for row in selected),
                           "mean_moving_decision_interval_s": st.mean(row["software_occupancy_s"].get("moving_decision", 0.) for row in selected),
                           "mean_old_moving_interval_percent": st.mean(row["old_moving_interval_percent"] for row in selected),
                           "mean_moving_no_hazard_percent": st.mean(row["moving_no_hazard_percent"] for row in selected)})
    return result


def contrasts(values):
    result = describe(values)
    result.update({"positive": sum(value > 1e-9 for value in values),
                   "negative": sum(value < -1e-9 for value in values),
                   "ties": sum(abs(value) <= 1e-9 for value in values),
                   "leave_one_nominal_block_out_means": [st.mean(values[:i] + values[i+1:]) for i in range(len(values))]})
    return result


def analyze(primary, pilot):
    assert len(primary) == 24 and len(pilot) == 8
    assert all(len(group) == 4 for group in [[row for row in primary if (row["method"], row["rate"]) == (method, rate)] for method in METHODS for rate in RATES])
    index = {(row["method"], row["rate"], row["direction"], row["repetition"]): row for row in primary}
    cadence = {}
    for method in METHODS:
        cadence[method] = {key: contrasts([index[method, "slow", d, rep][key] - index[method, "normal", d, rep][key] for d, rep in BLOCKS]) for key in METRICS}
        cadence[method]["score_hold_interval_change_s"] = contrasts([
            index[method, "slow", d, rep]["software_occupancy_s"].get("score_hold", 0.) - index[method, "normal", d, rep]["software_occupancy_s"].get("score_hold", 0.) for d, rep in BLOCKS])
    difference_in_changes = {}
    for reference in ("Trust12", "Trust32"):
        difference_in_changes[reference] = {
            key: contrasts([a - b for a, b in zip(cadence["AEGIS"][key]["individual_values"], cadence[reference][key]["individual_values"])]) for key in METRICS}
    pairwise = {}
    for reference in ("Trust12", "Trust32"):
        for rate in RATES:
            pairwise[f"AEGIS-minus-{reference}-{rate}"] = {
                key: contrasts([index["AEGIS", rate, d, rep][key] - index[reference, rate, d, rep][key] for d, rep in BLOCKS]) for key in METRICS}
    pilot_index = {(row["method"], row["direction"], row["repetition"]): row for row in pilot}
    pilot_pairwise = {key: contrasts([pilot_index["AEGIS", d, rep][key] - pilot_index["Trust12", d, rep][key] for d, rep in BLOCKS]) for key in METRICS}
    exceptions = [{key: row[key] for key in ("run", "campaign", "moving_old_evidence_percent", "old_moving_decisions", "old_moving_with_hazard", "max_moving_age_ms")}
                  for row in primary + pilot if row["method"] == "AEGIS" and row["old_moving_decisions"]]
    time_change = cadence["AEGIS"]["carry_to_delivery_s"]["mean"]
    hold_change = cadence["AEGIS"]["score_hold_interval_change_s"]["mean"]
    return {"scope": "Post-hoc descriptive pattern analysis, 2 October 2026; no new hardware or simulation trial.",
            "hypothesis": "Spatial buffer size and motion-conditioned semantic freshness are distinct operating axes. With slower update cadence, AEGIS requests additional holds while average evidence age during moving decisions changes little; fixed buffers do not reproduce this temporal behavior.",
            "selection": {"primary_runs": 24, "slow_pilot_runs_analyzed_separately": 8,
                          "remaining_eligible_runs_not_pooled_into_comparison": 60,
                          "all_primary_and_pilot_runs_retained": True},
            "pairing": "Nominal direction/repetition matches only, in order A1,A2,B1,B2; not randomized or identical obstacle presentations.",
            "aggregation": "Equal weights for runs; ticks are not independent experiments.",
            "primary_cells": cells(primary), "slow_minus_normal_nominal_contrasts": cadence,
            "difference_in_cadence_changes_AEGIS_minus_reference": difference_in_changes,
            "primary_method_contrasts": pairwise, "pilot_cells_not_pooled": cells(pilot),
            "pilot_AEGIS_minus_Trust12_nominal_contrasts": pilot_pairwise,
            "AEGIS_time_change_decomposition": {"total_change_s": time_change, "score_hold_interval_change_s": hold_change,
                "arithmetic_share_of_total_change_percent": hold_change / time_change * 100,
                "remaining_interval_and_endpoint_change_s": time_change - hold_change,
                "interpretation": "Recorded software-state decomposition, not a causal attribution or a measurement of robot standstill."},
            "AEGIS_old_evidence_exceptions_retained": exceptions,
            "limitations": ["Only two cadence settings; no universal age bound or regime-transition curve has been identified.",
                "Motion-conditioned ages can decrease because motion is withheld; they do not measure all-time perception accuracy.",
                "An age timeout comparator can plausibly reproduce part of this pattern; continuous-margin/history advantages remain unisolated.",
                "Capture-proxy age is not validated exposure age, and separation is command-estimated rather than independent physical clearance.",
                "Software interval weighting is a robustness check, not a measured motion-time exposure metric.",
                "Operator-managed, nonrandomized same-session trials; post-hoc observations do not establish causality or population-level significance.",
                "Pilot consistency is not an independent-session validation.",
                "Missing detections bypass the score-hold branch; old-evidence exceptions must not be hidden."]}


def plot(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = "Palatino" if any(item.name == "Palatino" for item in font_manager.fontManager.ttflist) else "STIXGeneral"
    colors = {"AEGIS": "#294861", "Trust12": "#9a6038", "Trust32": "#655476"}
    settings = {"font.family": font, "font.size": 9, "axes.labelsize": 9,
                "axes.titlesize": 10, "axes.titleweight": "normal",
                "axes.spines.top": False, "axes.spines.right": False,
                "xtick.labelsize": 9, "ytick.labelsize": 8.5}
    with plt.rc_context(settings):
        fig, axes = plt.subplots(1, 3, figsize=(8.1, 3.0))
        keys = ("mean_moving_age_ms", "minimum_command_estimated_separation_mm", "carry_to_delivery_s")
        titles = ("(a) Evidence age during motion", "(b) Command-estimated separation", "(c) Carry-to-delivery time")
        labels = ("Slow minus normal (ms)", "Slow minus normal (mm)", "Slow minus normal (s)")
        limits = ((-70, 335), (-14, 13), (-7, 36))
        for ax, key, title, label, bounds in zip(axes, keys, titles, labels, limits):
            ax.axhline(0, color=".75", linewidth=.6, zorder=1)
            for x, method in enumerate(METHODS):
                info = output["slow_minus_normal_nominal_contrasts"][method][key]
                for offset, value, (direction, _) in zip((-.14, -.05, .05, .14), info["individual_values"], BLOCKS):
                    ax.scatter(x + offset, value, s=22, marker="o" if direction == "A" else "s",
                               facecolors="none", edgecolors=colors[method], linewidths=.8, zorder=3)
                ax.scatter(x, info["mean"], s=31, marker="D", color=colors[method], zorder=4)
                ax.annotate(f"{info['mean']:+.1f}", (x, max(info["individual_values"])),
                            xytext=(0, 7), textcoords="offset points", ha="center", fontsize=9, color=colors[method])
            ax.set_title(title, loc="left", pad=10)
            ax.set_xticks(range(3), METHODS)
            ax.tick_params(axis="x", length=0, pad=6)
            ax.set_xlim(-.48, 2.48)
            ax.set_ylim(*bounds)
            ax.set_ylabel(label, labelpad=6)
            ax.tick_params(axis="y", direction="out", length=3, width=.6)
            for spine in ax.spines.values():
                spine.set_linewidth(.6)
        fig.subplots_adjust(left=.08, right=.99, bottom=.19, top=.86, wspace=.46)
        target = HERE / "cadence_response_patterns.png"
        fig.savefig(target, dpi=240)
        plt.close(fig)
    output["figure"] = {"path": str(target.relative_to(PACKAGE)), "sha256": digest(target), "font": font,
                        "caption": "Post-hoc change from normal to slow semantic updates in the 24-run primary campaign. Open circles and squares are nominal A- and B-direction repetition matches; filled diamonds and numbers give equal-block means. Horizontal offsets are categorical jitter only; observed differences are not displaced. No uncertainty interval, randomization, causal inference, independent physical clearance, or physical motion-time claim is implied."}


def main():
    summary_path = ANALYSIS / "hardware_summary.json"
    manifest_path = ANALYSIS / "analysis_manifest.json"
    summary = json.loads(summary_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    assert digest(summary_path) == manifest["output_hashes"]["analysis/hardware_summary.json"]
    archived = {PACKAGE / name: value for name, value in manifest["archived_data"].items()}
    assert len(archived) == 184
    before = {path: digest(path) for path in archived}
    assert before == archived
    selected = [meta for meta in summary["all_included_records"] if meta["campaign"] in ("timed_margin_compare", "timed_compare_slow")]
    runs = [reconstruct(meta) for meta in selected]
    primary = [row for row in runs if row["campaign"] == "timed_margin_compare"]
    pilot = [row for row in runs if row["campaign"] == "timed_compare_slow"]
    result = analyze(primary, pilot)
    result["runs"] = runs
    plot(result)
    assert {path: digest(path) for path in archived} == before
    result["provenance"] = {"analysis_script_sha256": digest(Path(__file__)),
                            "hardware_summary_sha256": digest(summary_path),
                            "existing_manifest_sha256": digest(manifest_path),
                            "archived_files_verified_against_existing_manifest": len(archived),
                            "archived_files_unchanged_after_analysis": True,
                            "selected_source_hashes": {str(path.relative_to(PACKAGE)): before[path] for path in archived if path.parts[-3] in ("timed_margin_compare", "timed_compare_slow")}}
    target = HERE / "pattern_results.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for cell in result["primary_cells"]:
        print(cell["method"], cell["rate"], {key: round(cell["metrics"][key]["mean"], 3) for key in METRICS})
    print("AEGIS time decomposition:", result["AEGIS_time_change_decomposition"])
    print("Preserved exceptions:", result["AEGIS_old_evidence_exceptions_retained"])
    print("Results:", target)
    print("Figure:", result["figure"]["path"])


if __name__ == "__main__":
    main()
