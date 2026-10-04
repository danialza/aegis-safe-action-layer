"""Add the cutoff-free age outcome to the primary plot, without new trials.

Uses frozen run-level hardware summaries and the verified 2 October audit.
Only the new figure and its manifest are written; source observations are read-only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent if (HERE.parent.parent / "data").exists() else HERE.parents[1] / "10_hardware_manuscript_2026-09-24"
OUT = (HERE.parent.parent / "figures") if (HERE.parent.parent / "data").exists() else HERE.parent / "source/figures"
METHODS = ("AEGIS", "Trust12", "Trust32")
RATES = ("normal", "slow")
METRICS = ("mean_moving_age_ms", "minimum_command_estimated_separation_mm",
           "carry_to_delivery_s", "moving_old_evidence_percent")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runs():
    source = ROOT / "analysis/exploratory_patterns_2026-10-02/pattern_results.json"
    audit = json.loads(source.read_text())
    for name, expected in audit["provenance"]["selected_source_hashes"].items():
        assert sha(ROOT / name) == expected, name
    records = [row for row in audit["runs"] if row["campaign"] == "timed_margin_compare"]
    assert len(records) == 24
    return records, source, audit["provenance"]["selected_source_hashes"]


def draw(runs):
    font = "Palatino" if any(f.name == "Palatino" for f in font_manager.fontManager.ttflist) else "STIXGeneral"
    markers = {"AEGIS": "o", "Trust12": "s", "Trust32": "^"}
    titles = ("(a) Mean evidence age at moving decisions",
              "(b) Minimum command-estimated separation",
              "(c) Carry-to-delivery time",
              "(d) Moving decisions using evidence older than 0.6 s")
    units = ("Mean age (ms)", "Separation (mm)", "Time (s)", "Moving decisions (%)")
    maxima = (850, 100, 80, 80)
    ticks = ((0, 200, 400, 600, 800), (0, 25, 50, 75, 100),
             (0, 20, 40, 60, 80), (0, 20, 40, 60, 80))
    style = {"font.family": font, "font.size": 9, "font.weight": "normal",
             "axes.labelsize": 9, "axes.titlesize": 9.5, "axes.titleweight": "normal",
             "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.spines.top": False,
             "axes.spines.right": False, "axes.grid": False,
             "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300}
    with plt.rc_context(style):
        fig, axes = plt.subplots(4, 1, figsize=(6.8, 6.9))
        for index, (ax, key) in enumerate(zip(axes, METRICS)):
            ax.set_title(titles[index], loc="left", pad=6)
            for ri, rate in enumerate(RATES):
                for mi, method in enumerate(METHODS):
                    x = ri * 1.16 + (mi - 1) * .30
                    selected = sorted((row for row in runs if (row["method"], row["rate"]) == (method, rate)),
                                      key=lambda row: row["run"])
                    assert len(selected) == 4
                    values = [row[key] for row in selected]
                    mean = statistics.mean(values)
                    ax.scatter([x + offset for offset in (-.105, -.045, .045, .105)], values,
                               s=18, marker=markers[method], facecolors="none", edgecolors=".48",
                               linewidths=.65, zorder=3)
                    ax.scatter([x], [mean], s=34, marker=markers[method], facecolors="black",
                               edgecolors="black", linewidths=.6, zorder=4)
                    ax.annotate(f"{mean:.1f}", (x, max(values)), xytext=(0, 4),
                                textcoords="offset points", ha="center", va="bottom", fontsize=9)
            ax.set_xlim(-.52, 1.68)
            ax.set_ylim(-maxima[index] * .065, maxima[index])
            ax.set_yticks(ticks[index])
            ax.set_xticks([0, 1.16], ["Normal updates", "Slow updates (0.8 s)"])
            ax.set_ylabel(units[index], labelpad=7)
            ax.tick_params(axis="x", length=0, pad=5)
            ax.tick_params(axis="y", direction="out", length=3, width=.6)
            for side in ("left", "bottom"):
                ax.spines[side].set_linewidth(.6)
            ax.grid(False)
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], linestyle="none", marker=markers[m], markersize=5.5,
                          markerfacecolor="black", markeredgecolor="black", label=m) for m in METHODS]
        handles.append(Line2D([], [], linestyle="none", marker="o", markersize=4.5, markerfacecolor="none",
                              markeredgecolor=".48", label="Individual runs"))
        fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(.56, 1.0),
                   handletextpad=.3, columnspacing=1.4, fontsize=9)
        fig.subplots_adjust(left=.145, right=.98, top=.925, bottom=.07, hspace=.57)
    return fig, font


def main():
    runs, source, hashes = load_runs()
    fig, font = draw(runs)
    outputs = [OUT / "hardware_primary_with_age.pdf", OUT / "hardware_primary_with_age.png"]
    fig.savefig(outputs[0], metadata={"Title": "Primary hardware comparison with moving-decision age",
                                      "Creator": "Offline review figure; no new hardware data"})
    fig.savefig(outputs[1])
    plt.close(fig)
    assert {name: sha(ROOT / name) for name in hashes} == hashes
    report = {"scope": "New presentation of existing 24 primary transports; four runs per cell.",
              "script_sha256": sha(Path(__file__)), "pattern_results_sha256": sha(source),
              "observations_unchanged": True, "verified_source_files": len(hashes),
              "font": font, "metrics": METRICS,
              "outputs": {path.name: sha(path) for path in outputs},
              "style": "Monochrome, regular serif fonts, one-line method legend added; all run values preserved."}
    (HERE / "primary_figure_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
