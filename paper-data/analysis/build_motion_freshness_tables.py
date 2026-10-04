"""Generate manuscript tables from the verified, post-hoc cadence-pattern audit.

No observation, controller, or existing hardware summary is rewritten.
"""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
PATTERNS = HERE / "exploratory_patterns_2026-10-02"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    path = PATTERNS / "pattern_results.json"
    result = json.loads(path.read_text())
    assert digest(PATTERNS / "pattern_audit.py") == result["provenance"]["analysis_script_sha256"]
    assert digest(HERE / "hardware_summary.json") == result["provenance"]["hardware_summary_sha256"]
    before = {name: digest(PACKAGE / name) for name in result["provenance"]["selected_source_hashes"]}
    assert before == result["provenance"]["selected_source_hashes"] and len(before) == 64
    rows = ["% Derived from the post-hoc pattern audit; equal run weights, n=4 per cell.",
            r"\begin{tabularx}{\linewidth}{ll>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X>{\raggedleft\arraybackslash}X}",
            r"\toprule", r"Cadence&Method&Separation (mm)&Mean age (ms)&Carry-to-delivery (s)&Age $>0.6$ s (\%)\\", r"\midrule"]
    fields = ("minimum_command_estimated_separation_mm", "mean_moving_age_ms", "carry_to_delivery_s", "moving_old_evidence_percent")
    for rate in ("normal", "slow"):
        for method in ("AEGIS", "Trust12", "Trust32"):
            cell = next(row for row in result["primary_cells"] if (row["method"], row["rate"]) == (method, rate))
            assert cell["n"] == 4
            rows.append("&".join([rate.title(), method] + [f"{cell['metrics'][key]['mean']:.1f}" for key in fields]) + r"\\")
    rows.extend([r"\bottomrule", r"\end{tabularx}"])
    primary = HERE / "motion_freshness_primary_rows.tex"
    primary.write_text("\n".join(rows) + "\n")
    table = [r"\begin{table}[H]", r"\centering\small",
             r"\caption{Motion-conditioned capture-proxy age in each primary run. Mean age uses all moving decisions, including those without a detected hazard; it is decision-weighted within each run. Each row is one transport, not an independent set of controller ticks.}\label{tab:motion-age-runs}",
             r"\begin{tabular}{lllrrr}", r"\toprule",
             r"Cadence & Method & Goal & Rep. & Moving decisions & Mean age (ms)\\", r"\midrule"]
    for rate in ("normal", "slow"):
        for method in ("AEGIS", "Trust12", "Trust32"):
            selected = sorted((row for row in result["runs"] if (row["campaign"], row["rate"], row["method"]) == ("timed_margin_compare", rate, method)), key=lambda row: (row["direction"], row["repetition"]))
            assert len(selected) == 4
            for row in selected:
                table.append(" & ".join([rate.title(), method, row["direction"], str(row["repetition"]), str(row["moving_decisions"]), f"{row['mean_moving_age_ms']:.1f}"]) + r"\\")
    table.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    per_run = HERE / "motion_freshness_per_run_table.tex"
    per_run.write_text("\n".join(table) + "\n")
    blocks = [r"\begin{table}[H]", r"\centering\small",
              r"\caption{Descriptive command-estimated separation differences in nominal cadence--direction--repetition blocks (AEGIS minus reference, mm). Filename matching does not establish randomized identical obstacle presentations.}\label{tab:nominal-pairs}",
              r"\begin{tabular}{lllrr}", r"\toprule",
              r"Cadence & Goal & Rep. & AEGIS$-$Trust12 & AEGIS$-$Trust32\\", r"\midrule"]
    for rate in ("normal", "slow"):
        for index, (direction, repetition) in enumerate((("A", 1), ("A", 2), ("B", 1), ("B", 2))):
            values = [result["primary_method_contrasts"][f"AEGIS-minus-{reference}-{rate}"]["minimum_command_estimated_separation_mm"]["individual_values"][index] for reference in ("Trust12", "Trust32")]
            blocks.append(" & ".join([rate.title(), direction, str(repetition)] + [f"{value:.3f}" for value in values]) + r"\\")
    blocks.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    block_table = HERE / "motion_freshness_nominal_block_table.tex"
    block_table.write_text("\n".join(blocks) + "\n")
    figure_source = PACKAGE / result["figure"]["path"]
    assert digest(figure_source) == result["figure"]["sha256"]
    figure = PACKAGE / "figures/cadence_response_patterns.png"
    shutil.copy2(figure_source, figure)
    assert {name: digest(PACKAGE / name) for name in before} == before
    manifest = {"scope": "Generated manuscript fragments; descriptive post-hoc audit, no new trial or altered observation.",
                "builder_sha256": digest(Path(__file__)), "pattern_results_sha256": digest(path),
                "source_hashes_verified": len(before), "sources_unchanged": True,
                "outputs": {str(target.relative_to(PACKAGE)): digest(target) for target in (primary, per_run, block_table, figure)}}
    (HERE / "motion_freshness_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    build()
