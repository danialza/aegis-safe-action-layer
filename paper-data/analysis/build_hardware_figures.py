"""Reproduce the hardware-only manuscript summaries without changing source files.

Usage: /Users/danial/.ned3pro-venv/bin/python analysis/build_hardware_figures.py
Only JSON/JSONL logs are analysed; original videos are neither edited nor used as
independent ground truth. Every source log hash is checked against the prior
inventory and again after analysis. All outcome exclusions remain in the manifest.
"""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
AUDIT = PACKAGE.parent / "09_revision_implementation/derived_reviews/2026-09-24_all_timed_inventory/audit.json"
if not AUDIT.exists():
    AUDIT = HERE / "inventory_source.json"
FIGURES = PACKAGE / "figures"
METHODS = ("AEGIS", "Trust12", "Trust32")
RATES = ("normal", "slow")
COLORS = {"AEGIS": "#0072B2", "Trust12": "#D55E00", "Trust32": "#009E73"}
CAMPAIGNS = ("aegis_time", "timed_compare", "timed_compare_slow", "timed_margin_compare")
PRIMARY = "timed_margin_compare"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(values):
    assert values and all(math.isfinite(x) for x in values)
    return {"n": len(values), "mean": statistics.mean(values),
            "median": statistics.median(values), "min": min(values),
            "max": max(values), "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
            "individual_values": values}


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def source_path(original):
    original = Path(original)
    local = PACKAGE / "data" / original.parent.parent.name / "logs" / original.name
    return local if local.exists() else original


def plot_primary(primary):
    """Monochrome individual-run/mean plot; no bars, grids, or connecting lines."""
    from matplotlib import font_manager
    # Palatino matches the manuscript's mathpazo family. Explicit fallback is
    # serif and recorded in the figure QA; PDF embeds the selected font.
    font = "Palatino" if any(f.name == "Palatino" for f in font_manager.fontManager.ttflist) else "STIXGeneral"
    markers = {"AEGIS": "o", "Trust12": "s", "Trust32": "^"}
    metrics = ("min_command_estimated_edge_separation_mm", "carry_to_delivery_s",
               "moving_age_above_0p6_percent")
    titles = ("(a) Minimum command-estimated separation",
              "(b) Carry-to-delivery time",
              "(c) Motion using evidence older than 0.6 s")
    units = ("Separation (mm)", "Time (s)", "Moving decisions (%)")
    maxima = (100, 80, 80)
    ticks = (range(0, 101, 25), range(0, 81, 20), range(0, 81, 20))
    style = {"font.family": font, "font.size": 9,
             "font.weight": "normal", "axes.labelsize": 9, "axes.titlesize": 10,
             "axes.titleweight": "normal", "xtick.labelsize": 9,
             "ytick.labelsize": 9, "axes.spines.top": False,
             "axes.spines.right": False, "axes.grid": False,
             "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300}
    with plt.rc_context(style):
        fig, axes = plt.subplots(3, 1, figsize=(6.8, 4.9))
        for ci, (ax, metric) in enumerate(zip(axes, metrics)):
            ax.set_title(titles[ci], loc="left", pad=6, color="black")
            for ri, rate in enumerate(RATES):
                for mi, method in enumerate(METHODS):
                    x = ri * 1.16 + (mi - 1) * .30
                    runs = sorted((r for r in primary
                                   if r["rate"] == rate and r["method"] == method),
                                  key=lambda r: r["run"])
                    assert len(runs) == 4
                    values = [r[metric] for r in runs]
                    mean = statistics.mean(values)
                    # No displacement of measured values; horizontal offsets
                    # only separate observations within a method/cadence group.
                    ax.scatter([x + d for d in (-.105, -.045, .045, .105)],
                               values, s=18, marker=markers[method],
                               facecolors="none", edgecolors=".48",
                               linewidths=.65, zorder=3)
                    ax.scatter([x], [mean], s=34, marker=markers[method],
                               facecolors="black", edgecolors="black",
                               linewidths=.6, zorder=4)
                    ax.annotate(f"{mean:.1f}", (x, max(values)),
                                xytext=(0, 4), textcoords="offset points",
                                ha="center", va="bottom", fontsize=9, color="black")
            ax.set_xlim(-.52, 1.68)
            ax.set_ylim(-maxima[ci] * .065, maxima[ci])
            ax.set_yticks(ticks[ci])
            ax.set_xticks([0, 1.16], ["Normal updates", "Slow updates (0.8 s)"])
            ax.set_ylabel(units[ci], labelpad=7)
            ax.tick_params(axis="x", length=0, pad=5)
            ax.tick_params(axis="y", direction="out", length=3, width=.6)
            for side in ("left", "bottom"):
                ax.spines[side].set_color("black")
                ax.spines[side].set_linewidth(.6)
            ax.grid(False)
        handles = [Line2D([], [], marker=markers[m], markersize=5,
                          linestyle="none", color="black", label=m) for m in METHODS]
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, 1.005),
                   ncol=3, frameon=False, fontsize=9, handlelength=1,
                   columnspacing=3.0)
        fig.text(.54, .025, "Filled symbols and numbers: mean; open symbols: individual runs (n = 4).",
                 ha="center", va="center", fontsize=8.5, color="black")
        fig.subplots_adjust(left=.14, right=.98, top=.88, bottom=.105, hspace=.49)
        fig.savefig(FIGURES / "hardware_primary_comparison.pdf",
                    metadata={"Title": "Hardware primary comparison - 24 transport runs",
                              "Creator": "build_hardware_figures.py"})
        fig.savefig(FIGURES / "hardware_primary_comparison.png")
        plt.close(fig)


def build():
    FIGURES.mkdir(exist_ok=True, parents=True)
    inventory = json.loads(AUDIT.read_text())
    if AUDIT.resolve() != (HERE / "inventory_source.json").resolve():
        shutil.copy2(AUDIT, HERE / "inventory_source.json")
    source_hashes = dict(inventory["source_hashes"])
    assert len(source_hashes) == 192
    unavailable_sources = [p for p in source_hashes if not source_path(p).exists()]
    # The portable package deliberately carries only the 92 eligible transport
    # logs. Excluded originals remain documented by hash in inventory_source.
    excluded_names = {r["run"] for r in inventory["runs"] if not r["decisions"]}
    assert all(Path(p).name.removesuffix(".jsonl").removesuffix(".json").removesuffix("_timing") in excluded_names
               for p in unavailable_sources)
    assert all(sha256(source_path(p)) == digest for p, digest in source_hashes.items() if p not in unavailable_sources)
    runs, exclusions = [], []
    for listed in inventory["runs"]:
        assert listed["campaign"] in CAMPAIGNS
        path = source_path(listed["path"])
        if not listed["decisions"]:
            reason = ("pre-transport pickup failure" if listed["result"]["termination_reason"] == "pick_failed"
                      else "no carry decisions; run already near destination")
            exclusions.append({"run": listed["run"], "campaign": listed["campaign"],
                               "reason": reason, "source": listed["path"], "sha256": source_hashes[listed["path"]],
                               "recorded_result": listed["result"],
                               "excluded_from": "transport decision and transport-performance summaries only",
                               "source_preserved": True})
            continue
        source = json.loads(path.read_text())
        log = source["log"]
        sidecar = source_path(listed["sidecar"])
        timing = [json.loads(line) for line in sidecar.read_text().splitlines()]
        events = [r for r in timing if r.get("type") == "event"]
        decisions = [{k: v for k, v in r.items() if k != "type"}
                     for r in timing if r.get("type") == "decision"]
        assert decisions == log
        assert source["time_base"] == "capture_proxy"
        assert log
        assert source["result"]["pick_succeeded"]
        assert source["result"]["termination_reason"] == "delivered"
        assert all(r["age_used"] == r["t_decision"] - r["ev_t_capture"] for r in log)
        moving = [r for r in log if r["mode"] != "stop"]
        assert moving and all(r["ev_status"] == "ok" and r["age_used"] is not None for r in moving)
        hazard_moving = [r for r in moving if r.get("clr") is not None]
        # Verify the logged metric against the actual deployed formula. `tool`
        # is the open-loop command accumulator at the beginning of a decision.
        max_clr_error = max((abs(r["clr"] - (math.dist(r["tool"], r["haz"][:2]) - r["haz"][2]))
                            for r in hazard_moving), default=0.0)
        assert max_clr_error < 1e-12
        start = next(r["t"] for r in events if r["text"].startswith("carrying"))
        finish = next(r["t"] for r in reversed(events) if r["text"] == "object delivered at goal")
        ages = [r["age_used"] for r in moving]
        summary = {
            "run": listed["run"], "source": listed["path"], "campaign": listed["campaign"],
            "method": listed["method"], "direction": listed["direction"],
            "rate": "slow" if source["vlm_min_period_s"] == .8 else "normal",
            "vlm_start_to_start_min_period_s": source["vlm_min_period_s"],
            "decisions": len(log), "moving_decisions": len(moving),
            "hazard_moving_decisions": len(hazard_moving),
            "carry_to_delivery_s": finish - start,
            "min_command_estimated_edge_separation_mm": min(r["clr"] for r in hazard_moving) * 1000 if hazard_moving else None,
            "moving_age_above_0p6_percent": statistics.mean(age > .6 for age in ages) * 100,
            "hazard_moving_age_above_0p6_percent": statistics.mean(r["age_used"] > .6 for r in hazard_moving) * 100 if hazard_moving else None,
            "mean_moving_evidence_age_s": statistics.mean(ages),
            "max_moving_evidence_age_s": max(ages),
            "below_own_margin_hazard_moving_decisions": sum(r["clr"] < r["margin"] for r in hazard_moving),
            "human_verdict_moving_decisions": sum(r["ev_verdict"] == "human" for r in moving),
            "goal_resumed": bool(source["result"].get("goal_resumed")),
            "calculated_clr_max_residual_m": max_clr_error,
            "moving_ages_s": ages,
        }
        assert abs(summary["carry_to_delivery_s"] - listed["duration"]) < 1e-9
        if hazard_moving:
            assert abs(summary["min_command_estimated_edge_separation_mm"] - listed["min_command_clearance_mm"]) < 1e-9
        else:
            assert listed["min_command_clearance_mm"] is None
        runs.append(summary)
        archive = PACKAGE / "data" / listed["campaign"] / "logs"
        archive.mkdir(parents=True, exist_ok=True)
        for original, source_file in ((listed["path"], path), (listed["sidecar"], sidecar)):
            if source_file.resolve() != (archive / source_file.name).resolve():
                shutil.copy2(source_file, archive / source_file.name)
            assert sha256(archive / source_file.name) == source_hashes[original]
    assert len(runs) == 92 and len(exclusions) == 4
    primary = [r for r in runs if r["campaign"] == PRIMARY]
    assert len(primary) == 24
    metrics = ("min_command_estimated_edge_separation_mm", "carry_to_delivery_s", "moving_age_above_0p6_percent")
    cells = []
    for rate in RATES:
        for method in METHODS:
            rr = [r for r in primary if r["rate"] == rate and r["method"] == method]
            assert len(rr) == 4 and Counter(r["direction"] for r in rr) == {"A": 2, "B": 2}
            cells.append({"method": method, "rate": rate, "run_ids": [r["run"] for r in rr],
                          **{metric: summarize([r[metric] for r in rr]) for metric in metrics}})
    thresholds = [i / 100 for i in range(20, 121)]
    sensitivity = []
    for rate in RATES:
        for method in METHODS:
            rr = [r for r in primary if r["rate"] == rate and r["method"] == method]
            mean_percent = []
            individual = []
            for threshold in thresholds:
                values = [100 * statistics.mean(a > threshold for a in r["moving_ages_s"]) for r in rr]
                individual.append(values)
                mean_percent.append(statistics.mean(values))
            sensitivity.append({"method": method, "rate": rate, "thresholds_s": thresholds,
                                "mean_run_fraction_percent": mean_percent,
                                "individual_run_fractions_percent": individual,
                                "run_ids": [r["run"] for r in rr]})
    output = {"scope": "Hardware only; no legacy-clock or simulation evidence",
              "aggregation": "Unweighted mean across runs; no decision-count pooling across runs",
              "selection": "All 24 transport runs in timed_margin_compare, with all four runs per cell displayed",
              "inference": "Descriptive; no randomization assumption, significance test or confidence interval",
              "definitions": {
                  "time": "First carrying event to object-delivered event; includes final placement and intervening holds, excludes pickup and initial pause.",
                  "separation": "Per-run minimum of logged clr on mode != stop decisions with a hazard; clr is distance from internal command accumulator to estimated obstacle center minus estimated radius. Not actual TCP, whole-arm, continuous-path or independently measured separation.",
                  "older_evidence": "Per-run fraction of mode != stop decisions whose capture-proxy age is strictly greater than threshold; includes decisions with no detected hazard. Not time-weighted and not a probability of harm.",
                  "rate": "normal: zero imposed minimum inference-start period; slow: 0.8 s minimum start-to-start period, not an added 0.8 s inference latency.",
                  "scope": "Conditional transport comparison after successful pickup, not an end-to-end success-rate estimate.",
              }, "primary_cells": cells, "inventory": dict(Counter(r["campaign"] for r in runs)),
              "included_transport_runs": len(runs), "excluded_pretransport_or_no_carry_runs": len(exclusions),
              "decision_records": sum(r["decisions"] for r in runs),
              "all_included_records": [{k: v for k, v in r.items() if k != "moving_ages_s"} for r in runs],
              "threshold_sensitivity": sensitivity,
              "cautions": ["Capture proxy does not validate sensor-exposure-to-Pi delay.",
                           "Exploratory and pilot runs are not pooled into the 24-run main comparison.",
                           "All transport outcomes retained, including unfavorable metrics.",
                           "Delivery is a logged outcome, not independent proof of physical safety."]}
    dump(HERE / "hardware_summary.json", output)
    dump(HERE / "exclusions.json", {"scope": "Transparent non-transport exclusions; sources preserved",
                                    "screened": len(runs) + len(exclusions), "included": len(runs),
                                    "excluded": exclusions})
    tex_rows = []
    for cell in cells:
        sep = cell[metrics[0]]["mean"]
        duration = cell[metrics[1]]["mean"]
        old = cell[metrics[2]]["mean"]
        tex_rows.append(f"{cell['rate'].capitalize()} & {cell['method']} & 4 & {sep:.1f} & {duration:.1f} & {old:.1f} " + r"\\")
    (HERE / "primary_table_rows.tex").write_text("% Generated; columns: rate, method, n, minimum separation mm, duration s, moving older than 0.6 s (%)\n" + "\n".join(tex_rows) + "\n")
    table = [r"\begin{table}[H]", r"\centering", r"\small",
             r"\caption{Primary hardware comparison, conditional on successful pickup. Values are unweighted run means [minimum, maximum]; $n=4$ per cell (two runs in each direction). Separation is command--estimated obstacle-edge separation, not independently measured physical clearance. The age threshold is an analysis reference, not a safety limit.}",
             r"\label{tab:hardware-primary}", r"\begin{tabular}{llrccc}", r"\toprule",
             r"Setting & Method & $n$ & \shortstack{Min. separation\\(mm)} & \shortstack{Carry-to-delivery\\(s)} & \shortstack{Moving age $>0.6$ s\\(\%)} \\",
             r"\midrule"]
    for cell in cells:
        formatted = [f"{cell[m]['mean']:.1f} [{cell[m]['min']:.1f}, {cell[m]['max']:.1f}]" for m in metrics]
        table.append(f"{cell['rate'].capitalize()} & {cell['method']} & 4 & " + " & ".join(formatted) + r" \\")
    table += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (HERE / "results_table.tex").write_text("\n".join(table) + "\n")
    supplementary = [r"\begin{table}[H]", r"\centering", r"\small",
                     r"\caption{All 24 primary hardware transport runs. The repetition identifier is the original filename suffix. Metrics use the definitions in Table~\ref{tab:hardware-primary}; no run in the primary campaign was excluded.}",
                     r"\label{tab:hardware-individual}", r"\begin{tabular}{lllrrrr}", r"\toprule",
                     r"Setting & Method & To & Rep. & \shortstack{Min. sep.\\(mm)} & \shortstack{Time\\(s)} & \shortstack{Moving age $>0.6$ s\\(\%)} \\",
                     r"\midrule"]
    for rate in RATES:
        for method in METHODS:
            for r in sorted((r for r in primary if r["rate"] == rate and r["method"] == method), key=lambda r: r["run"]):
                supplementary.append(f"{rate.capitalize()} & {method} & {r['direction']} & {r['run'].rsplit('_', 1)[1]} & "
                                     + " & ".join(f"{r[m]:.1f}" for m in metrics) + r" \\")
    supplementary += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (HERE / "supplementary_table.tex").write_text("\n".join(supplementary) + "\n")
    plot_primary(primary)
    plot_sensitivity(thresholds, sensitivity)
    assert all(sha256(source_path(p)) == digest for p, digest in source_hashes.items() if p not in unavailable_sources)
    manifest = {"analysis_script": str(Path(__file__)), "analysis_script_sha256": sha256(__file__),
                "audit_source": str(AUDIT), "audit_source_sha256": sha256(AUDIT),
                "source_json_and_jsonl_sha256": source_hashes,
                "all_available_source_hashes_match_previous_inventory": True,
                "all_available_source_hashes_unchanged_after_analysis": True,
                "unavailable_excluded_sources_in_portable_reproduction": unavailable_sources,
                "input_video_files_modified": False, "source_logs_modified": False,
                "archived_data": {str(p.relative_to(PACKAGE)): sha256(p) for p in sorted((PACKAGE / "data").rglob("*.json*"))},
                "output_hashes": {str(p.relative_to(PACKAGE)): sha256(p)
                                  for p in [HERE / "hardware_summary.json", HERE / "exclusions.json",
                                            HERE / "primary_table_rows.tex", HERE / "results_table.tex",
                                            HERE / "supplementary_table.tex", *sorted(FIGURES.glob("*.pdf")),
                                            *sorted(FIGURES.glob("*.png"))]}}
    dump(HERE / "analysis_manifest.json", manifest)
    print(json.dumps({"screened": 96, "included_transport": len(runs), "excluded": len(exclusions),
                      "primary_cells": cells}, indent=2))


def plot_sensitivity(thresholds, sensitivity):
    from matplotlib import font_manager
    font = "Palatino" if any(f.name == "Palatino" for f in font_manager.fontManager.ttflist) else "STIXGeneral"
    markers = {"AEGIS": "o", "Trust12": "s", "Trust32": "^"}
    line_styles = {"AEGIS": "-", "Trust12": "--", "Trust32": ":"}
    shades = {"AEGIS": "#204A72", "Trust12": "#B85C16", "Trust32": "#704098"}
    style = {"font.family": font, "font.size": 9, "font.weight": "normal",
             "axes.labelsize": 9, "axes.titlesize": 10, "axes.titleweight": "normal",
             "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.grid": False,
             "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
             "ps.fonttype": 42, "savefig.dpi": 300}
    with plt.rc_context(style):
        fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.55), sharey=True)
        for ax, rate, letter in zip(axes, RATES, ("a", "b")):
            for mi, method in enumerate(METHODS):
                curve = next(r for r in sensitivity if r["rate"] == rate and r["method"] == method)
                # Markers identify methods even when the two Trust curves overlap.
                # Subsampling markers does not subsample or displace the curves.
                ax.plot(thresholds, curve["mean_run_fraction_percent"],
                        color=shades[method], lw=1.2, linestyle=line_styles[method],
                        marker=markers[method], markersize=3.5, markerfacecolor="white",
                        markeredgewidth=.65, markevery=(mi * 4 + 4, 18), label=method)
            # Algebraic onset depends on the stored OBJECT anchor. It is not
            # a universal timeout and applies only with a detected hazard.
            onsets = [.4 * math.log((.65 - h) / (.65 - .5)) for h in (.0325, 0)]
            ax.axvspan(*onsets, facecolor=".88", edgecolor="none", zorder=0)
            ax.axvline(.6, color=".6", linewidth=.7, linestyle="--", zorder=0)
            ax.set_title(f"({letter}) {'Normal updates' if rate == 'normal' else 'Slow updates (0.8 s)'}", loc="left", pad=7)
            ax.set_xlim(.2, 1.2)
            ax.set_ylim(-2, 102)
            ax.set_yticks(range(0, 101, 20))
            ax.set_xticks([.2, .4, .6, .8, 1.0, 1.2])
            ax.tick_params(direction="out", length=3, width=.6, pad=4)
            ax.grid(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_linewidth(.6)
                ax.spines[side].set_color("black")
        axes[0].set_ylabel("Moving decisions above threshold\n(equal-run mean, %)", labelpad=7)
        # Method key and explanatory notes live in the manuscript caption,
        # not in the image; only panel/axis labels remain inside the figure.
        fig.text(.55, .035, "Analysis threshold for evidence age (s)", ha="center", fontsize=9)
        fig.subplots_adjust(left=.12, right=.985, top=.87, bottom=.20, wspace=.16)
        fig.savefig(FIGURES / "evidence_age_threshold_sensitivity.pdf", metadata={"Title": "Evidence-age threshold sensitivity", "Creator": "build_hardware_figures.py"})
        fig.savefig(FIGURES / "evidence_age_threshold_sensitivity.png")
        plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-figure-only", action="store_true",
                        help="Redraw the primary figure from existing summaries; change no data, tables or sensitivity figure")
    parser.add_argument("--figures-only", action="store_true", help="Redraw both plots from existing summaries, without changing numerical products")
    parser.add_argument("--sensitivity-figure-only", action="store_true", help="Redraw Figure 4 only; preserve Figure 3 and all numerical products")
    args = parser.parse_args()
    if args.primary_figure_only or args.figures_only or args.sensitivity_figure_only:
        summary = json.loads((HERE / "hardware_summary.json").read_text())
        if not args.sensitivity_figure_only:
            plot_primary([r for r in summary["all_included_records"] if r["campaign"] == PRIMARY])
        if args.figures_only or args.sensitivity_figure_only:
            plot_sensitivity(summary["threshold_sensitivity"][0]["thresholds_s"], summary["threshold_sensitivity"])
    else:
        build()
