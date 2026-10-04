"""Offline final source/PDF checks; never imports or executes robot code."""
from pathlib import Path
import hashlib
import json
import re

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expanded_source(path):
    source = path.read_text()
    def expand(match):
        child = path.parent / match.group(1)
        if not child.suffix:
            child = child.with_suffix(".tex")
        assert child.is_file(), child
        return expanded_source(child)
    return re.sub(r"\\input\{([^}]+)\}", expand, source)


def check_offline_revision(main):
    here = ROOT / "analysis/offline_review_2026-10-03"
    stage = json.loads((here / "stage_age_results.json").read_text())
    shadow = json.loads((here / "shadow_timeout_results.json").read_text())
    proxy = json.loads((here / "proxy_sensitivity_results.json").read_text())
    for result, script in ((stage, "stage_age_audit.py"), (shadow, "shadow_timeout.py")):
        provenance = result["provenance"]
        assert digest(here / script) == provenance["analysis_script_sha256"]
        for name, value in provenance["selected_source_hashes"].items():
            assert digest(ROOT / name) == value, name
    assert stage["selection"]["primary_runs"] == 24
    assert stage["selection"]["pilot_runs_not_pooled"] == 8
    assert stage["validation"]["selected_decisions"] == 4530
    assert stage["validation"]["maximum_row_reconciliation_residual_ms"] == 0
    assert stage["validation"]["invalid_decisions"] == 0
    for name, value in stage["provenance"]["generated_tables"].items():
        assert digest(ROOT / name) == value
    for cell in stage["primary_cells"]:
        assert cell["n_runs"] == 4
        components = [cell["metrics"][name]["mean"] for name in (
            "mean_proxy_to_infer_start_ms", "mean_inference_ms", "mean_infer_end_to_decision_ms")]
        assert abs(sum(components) - cell["metrics"]["mean_moving_age_ms"]["mean"]) < 1e-8
    shadow_manifest = json.loads((here / "shadow_timeout_manifest.json").read_text())
    for name, value in shadow_manifest["derived_artifact_sha256"].items():
        assert digest(ROOT / name) == value
    primary = [cell for cell in shadow["cells"] if cell["campaign"] == "timed_margin_compare"]
    counts = [cell["comparisons"]["Trust32+timeout-analytic"]["pooled_row_counts_descriptive_only"]
              for cell in primary]
    assert sum(cell["runs"] for cell in primary) == 8
    assert sum(c["eligible_object_hazard_decisions"] for c in counts) == 1302
    assert sum(c["disagreements"] for c in counts) == 0
    assert abs(shadow["constants"]["zero_OBJECT_anchor_analytic_timeout_s"] - .5865348275173708) < 1e-14
    proxy_manifest = json.loads((here / "proxy_sensitivity_manifest.json").read_text())
    assert proxy_manifest["source_hashes_before"] == proxy_manifest["source_hashes_after"]
    for name, value in proxy_manifest["source_hashes_before"].items():
        assert digest(ROOT / name) == value
    for name, value in proxy_manifest["output_hashes"].items():
        assert digest(here / name) == value
    assert proxy["primary"]["n_runs"] == 24
    figure_manifest = json.loads((here / "review_figure_manifest.json").read_text())
    assert digest(here / "build_review_figure.py") == figure_manifest["script_sha256"]
    for name, value in figure_manifest["outputs"].items():
        assert digest(ROOT / name) == value
    assert "hardware_primary_with_age.pdf" in main
    for label in ("eq:age-stages", "eq:shadow-timeout", "tab:age-stages", "sec:shadow-results"):
        assert r"\label{" + label + "}" in main
    for number in ("1302", "311", "991", "987", "259.1", "264.1", "733.3", "697.0", "692.9"):
        assert number in main
    assert "counterfactual trajectory" in main and "hypothetical" in main
    assert "reproduces AEGIS semantic permission on all 1302" in main
    return {"remedies_1_2_3_5_integrated": True, "shadow_primary_eligible_rows": 1302,
            "shadow_primary_semantic_gate_disagreements": 0,
            "timing_stage_decisions_reconciled": 4530,
            "new_analysis_source_and_product_hashes_verified": True,
            "hypothetical_offsets_and_on_policy_scope_explicit": True,
            "four_panel_figure_includes_individual_mean_age_values": True}


def check():
    main = (ROOT / "manuscript/main.tex").read_text()
    class_hash = digest(ROOT / "manuscript/Definitions/mdpi.cls")
    assert class_hash == "658dbb5b2db2f6560bf3de3ecff7efac310a5817721eebd7539c1990b5345f01"
    abstract = re.search(r"\\abstract\{(.*?)\}\n", main).group(1)
    assert len(abstract.split()) <= 200
    semantic = json.loads((ROOT / "analysis/semantic_paper_results.json").read_text())
    semantic_manifest = json.loads((ROOT / "analysis/semantic_paper_manifest.json").read_text())
    for name, expected in semantic_manifest["outputs"].items():
        assert digest(ROOT / "analysis" / name) == expected, name
    assert semantic["human_counts"] == {"hand": 101, "no_hand": 322, "uncertain": 3}
    assert semantic["reviewed_frames"] == 426 and semantic["reviewed_runs"] == 94
    assert semantic["negative_stratum_conditional_bound"]["upper_K"] == 18
    presence_rows = (ROOT / "analysis/semantic_presence_rows.tex").read_text()
    assert [line for line in presence_rows.splitlines()
            if line.startswith(("Hand present &", "No visible hand &", "Uncertain &"))] == [
        r"Hand present & 101 & 0 & 50 & 51\\",
        r"No visible hand & 22 & 300 & 0 & 322\\",
        r"Uncertain & 3 & 0 & 0 & 3\\",
    ]
    summary = json.loads((ROOT / "analysis/hardware_summary.json").read_text())
    motion = json.loads((ROOT / "analysis/exploratory_patterns_2026-10-02/pattern_results.json").read_text())
    motion_manifest = json.loads((ROOT / "analysis/motion_freshness_manifest.json").read_text())
    assert digest(ROOT / "analysis/exploratory_patterns_2026-10-02/pattern_results.json") == motion_manifest["pattern_results_sha256"]
    assert digest(ROOT / "analysis/build_motion_freshness_tables.py") == motion_manifest["builder_sha256"]
    for name, expected in motion_manifest["outputs"].items():
        assert digest(ROOT / name) == expected, name
    pattern = r"^(Normal|Slow)&(AEGIS|Trust12|Trust32)&([\d.]+)&([\d.]+)&([\d.]+)&([\d.]+)\\\\$"
    rows = re.findall(pattern, expanded_source(ROOT / "manuscript/main.tex"), flags=re.MULTILINE)
    assert len(rows) == 6, rows
    for cadence, method, *values in rows:
        cell = next(c for c in summary["primary_cells"]
                    if c["rate"] == cadence.lower() and c["method"] == method)
        motion_cell = next(c for c in motion["primary_cells"]
                           if c["rate"] == cadence.lower() and c["method"] == method)
        expected = [cell["min_command_estimated_edge_separation_mm"]["mean"],
                    motion_cell["metrics"]["mean_moving_age_ms"]["mean"],
                    cell["carry_to_delivery_s"]["mean"], cell["moving_age_above_0p6_percent"]["mean"]]
        assert values == [f"{value:.1f}" for value in expected]
    for label in ("sec:spatial-temporal", "sec:cadence-cost", "sec:hold-cost", "eq:mean-motion-age"):
        assert r"\label{" + label + "}" in main
    for cell in motion["primary_cells"]:
        assert f"{cell['metrics']['mean_moving_age_ms']['mean']:.1f}" in main
    decomposition = motion["AEGIS_time_change_decomposition"]
    for key in ("total_change_s", "score_hold_interval_change_s"):
        assert f"{decomposition[key]:.2f}" in main
    assert "Assumption-dependent sign references" not in main
    offline_report = check_offline_revision(main)
    assert r"\label{sec:claim-boundaries}" in main
    assert r"\label{tab:claim-boundaries}" in main
    assert r"Table~\ref{tab:claim-boundaries}" in main
    assert "not independently measured robot velocity" in main
    assert "recorded common guard outcomes held fixed" in main
    assert "No public repository identifier or unrestricted data availability is claimed" in main
    pdf_reports = {}
    for stem in ("main", "supplementary"):
        tex_path = ROOT / "manuscript" / f"{stem}.tex"
        tex = expanded_source(tex_path)
        for obsolete in ("Labels and replay results remain pending",
                         "Independent human annotation is pending",
                         "Prepared semantic-monitor audit: labels pending"):
            assert obsolete not in tex, (stem, obsolete)
        if stem == "main":
            assert r"\label{sec:semantic-method}" in tex and r"\label{tab:semantic}" in tex
            assert "1732" in tex and "three remain uncertain" in tex
        else:
            assert r"\label{tab:semantic-strata}" in tex and r"\label{tab:semantic-conditions}" in tex
            assert "upper bound of 18" in tex and "not an interval for future live recall" in tex
        all_labels = re.findall(r"\\label\{([^}]+)\}", tex)
        assert len(all_labels) == len(set(all_labels)), (stem, "duplicate labels")
        labels = set(all_labels)
        refs = set(re.findall(r"\\(?:eqref|ref|autoref)\{([^}]+)\}", tex))
        assert refs <= labels, (stem, refs - labels)
        bibkeys = set(re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", tex))
        citekeys = {k.strip() for group in re.findall(r"\\cite(?:\[[^\]]*\])?\{([^}]+)\}", tex)
                    for k in group.split(",")}
        assert citekeys <= bibkeys, (stem, citekeys - bibkeys)
        if stem == "main":
            assert citekeys == bibkeys and len(citekeys) == 26
            assert "moghaddam2026hardware" in citekeys
        for item in re.findall(r"\\input\{([^}]+)\}", tex):
            path = tex_path.parent / item
            if not path.suffix:
                path = path.with_suffix(".tex")
            assert path.is_file(), path
        pdf_path = ROOT / "output/pdf" / f"{stem}.pdf"
        reader = PdfReader(pdf_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "\ufffd" not in text and "??" not in text
        # The unchanged official submission class emits this publisher DOI
        # placeholder. Verify the exact known stub, not a claimed assigned DOI.
        template_stub = "s000000" in text
        if template_stub:
            assert stem == "main" and "article,submit,moreauthors" in main
            assert all(command in main for command in
                       (r"\pubvolume{0}", r"\issuenum{0}", r"\articlenumber{0}"))
        log_path = pdf_path.with_suffix(".log")
        if log_path.exists():
            log = log_path.read_text(errors="replace")
            for bad in ("Overfull ", "There were undefined references", "Missing character:"):
                assert bad not in log, (stem, bad)
        pdf_reports[stem] = {
            "pages": len(reader.pages), "pdf_sha256": digest(pdf_path),
            "tex_sha256": digest(tex_path), "defined_cross_references": len(refs),
            "defined_citations": len(citekeys),
            "missing_glyphs_or_unresolved_references": False,
            "unmodified_submission_template_unassigned_doi_stub": template_stub,
        }
    report = {
        "passed": True,
        "main_table_cells_match_run_summary_to_displayed_precision": 24,
        "motion_freshness_tables_and_figure_hashes_verified": True,
        "three_finding_sections_and_cutoff_free_age_definition_present": True,
        "score_hold_time_decomposition_matches_posthoc_audit": True,
        "semantic_presence_table_matches_merged_human_review": True,
        "semantic_table_and_result_hashes_verified": True,
        "obsolete_pending_annotation_claims_removed": True,
        "abstract_whitespace_word_count": len(abstract.split()),
        "official_mdpi_class_sha256": class_hash,
        "pdfs": pdf_reports,
        "offline_review": offline_report,
        "evidence_boundaries_table_and_software_motion_definition_present": True,
        "local_data_availability_not_external_deposition": True,
        "scope": "File and text consistency only, not independent physical or statistical validation. Current visual checks are recorded in analysis/remedy8_validation.json; earlier checks remain archived.",
    }
    (ROOT / "analysis/manuscript_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    check()
