"""Reproducible item-8 document QA, separate from scientific validation.

Visual QA records an explicitly reported inspection of rendered local PDFs;
it cannot automatically assess scientific correctness or author permissions.
No robot controller, model, original video or source log is executed/changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
SUITES = (
    (ANALYSIS, ("test_primary_figure", "test_sensitivity_figure", "test_semantic_paper",
                "test_semantic_human_merge", "test_semantic_human_review",
                "test_semantic_human_recheck", "test_semantic_auto_report",
                "test_semantic_auto_audit")),
    (ANALYSIS / "exploratory_patterns_2026-10-02", ("test_pattern_audit",)),
    (ANALYSIS / "offline_review_2026-10-03", ("test_shadow_timeout", "test_stage_age_audit",
                                              "test_proxy_sensitivity", "test_review_figure")),
    (ANALYSIS, ("test_remedy8",)),
    (ANALYSIS, ("test_method_clarifications",)),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(args, cwd):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(args, cwd=cwd, env=environment, capture_output=True, text=True,
                            timeout=60)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def page_list(text):
    return sorted({int(value) for value in text.split(",") if value.strip()})


def check(args):
    suites = []
    for directory, modules in SUITES:
        output = execute([sys.executable, "-m", "unittest", *modules], directory)
        count = re.search(r"Ran (\d+) tests? in", output)
        assert count and re.search(r"^OK$", output, re.MULTILINE), output
        suites.append({"directory": str(directory.relative_to(ROOT)), "modules": list(modules),
                       "tests_passed": int(count.group(1)), "passed": True})
    assert sum(suite["tests_passed"] for suite in suites) == 109
    execute([sys.executable, str(ANALYSIS / "verify_artifacts.py")], ROOT)
    execute([sys.executable, str(ANALYSIS / "check_manuscript.py")], ROOT)
    source = json.loads((ANALYSIS / "validation_report.json").read_text())
    manuscript = json.loads((ANALYSIS / "manuscript_validation.json").read_text())
    assert source["passed"] and manuscript["passed"]
    assert source["byte_identical_included_copy_files_checked"] == 184
    visual = {"reported_complete": False,
              "scope": "Manual inspection of rendered pages, not physical validation."}
    if args.visual_review_dir:
        directory = Path(args.visual_review_dir).resolve()
        directory.relative_to(ROOT / "tmp/pdfs")
        visual.update({"reported_complete": True, "directory": str(directory.relative_to(ROOT)),
                       "all_pages_inspected_via_contact_sheets": True, "documents": {}})
        for stem in ("main", "supplementary"):
            pages = sorted(directory.glob(stem + "-*.png"))
            pages = [path for path in pages if "contact" not in path.name]
            contacts = sorted(directory.glob(stem + "-contact-*.png"))
            count = manuscript["pdfs"][stem]["pages"]
            assert len(pages) == count and len(contacts) == (count + 3) // 4
            details = page_list(getattr(args, "inspected_" + stem + "_pages"))
            assert details and all(1 <= page <= count for page in details)
            visual["documents"][stem] = {
                "pages_rendered_and_inspected": count,
                "pdf_sha256": manuscript["pdfs"][stem]["pdf_sha256"],
                "enlarged_page_inspections": details,
                "contact_sheet_sha256": {path.name: sha(path) for path in contacts},
            }
    documents = ("README_FA.md", "manuscript/main.tex", "manuscript/supplementary.tex",
                 "review/CURRENT_REVIEWER_RESPONSE.md", "review/SUBMISSION_CHECKLIST.md",
                 "review/DATA_RELEASE_CHECKLIST.md", "review/COVER_LETTER_DRAFT.md",
                 "review/REVIEWER_RESPONSE_UPDATE_2026-09-25.md", "review/FINAL_QA.md",
                 "review/PROPOSAL_RESPONSE_FA.md", "review/EDITORIAL_AUDIT.md",
                 "review/REVISION_DECISIONS_FA.md", "analysis/check_remedy8.py",
                 "analysis/test_remedy8.py", "analysis/check_manuscript.py",
                 "analysis/test_method_clarifications.py", "analysis/build_workflow.py")
    report = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed_document_consistency_checks": True,
        "item_8_completed_scope": "Feasible editorial, claim-boundary and local publication-document work only.",
        "correct_original_reviewer_comment_counts": {"R1": 7, "R2": 3, "R3": 6},
        "reviewer_response_is_local_unsent_draft": True,
        "all_primary_and_adverse_in_scope_observations_retained": True,
        "archived_log_files_checked_byte_identical": 184,
        "available_original_json_jsonl_hashes_checked_unchanged": source["source_json_jsonl_hashes_checked_unchanged"],
        "original_video_log_controller_or_human_export_edits": False,
        "test_suites": suites, "total_tests_passed": sum(s["tests_passed"] for s in suites),
        "method_clarifications_checked": [
            "RGB precedence and confirmed depth-only fallback",
            "Planning-centre cache regeneration versus current-radius target guard",
            "Non-score residual includes move-labelled occupancy change",
        ],
        "document_sha256": {name: sha(ROOT / name) for name in documents},
        "pdfs": manuscript["pdfs"], "visual_review": visual,
        "external_author_confirmations_still_open": [
            "Institutional ethics applicability and supporting basis",
            "Operator consent and identifiable media distribution permissions",
            "All-author approval, contribution roles and declaration/AI-use details",
            "Concrete permitted recipient-accessible data route and licences",
            "Actual submission/resubmission route, manuscript ID and author declarations",
        ],
        "broader_scientific_requests_not_created_by_editing": [
            "Independent exposure-time and physical clearance/stopping measurements",
            "More diverse independent hardware sessions and semantic validation",
            "Prospectively labeled first-human-intrusion validation",
            "Executed published delay-aware comparator and closed-loop timeout comparison",
        ],
        "no_external_submission_deposit_or_author_approval_claimed": True,
        "portable_source_status": "See analysis/portable_source_validation.json and the tested source-ZIP hash.",
        "scope": "These are reproducibility and editorial checks, not new physical evidence or a guarantee of journal acceptance.",
    }
    destination = ANALYSIS / "remedy8_validation.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-review-dir", help="Fresh render directory actually inspected by the reviewing agent.")
    parser.add_argument("--inspected-main-pages", default="")
    parser.add_argument("--inspected-supplementary-pages", default="")
    check(parser.parse_args())
