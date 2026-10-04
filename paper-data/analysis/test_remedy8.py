"""Document-level regression checks for item 8; no robot/model execution."""
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent


def read(relative):
    return (ROOT / relative).read_text()


class RemedyEightTests(unittest.TestCase):
    def test_all_sixteen_original_reviewer_ids(self):
        response = read("review/CURRENT_REVIEWER_RESPONSE.md")
        ids = re.findall(r"^### (R[123]\.\d+) ", response, re.MULTILINE)
        expected = [f"R{reviewer}.{comment}" for reviewer, count in ((1, 7), (2, 3), (3, 6))
                    for comment in range(1, count + 1)]
        self.assertEqual(ids, expected)

    def test_reviewer_one_two_topics_not_swapped(self):
        response = read("review/CURRENT_REVIEWER_RESPONSE.md")
        for heading in (
            "R1.1 Evidence clock", "R1.2 Unsupported theoretical guarantee",
            "R1.3 Semantic validation", "R1.4 Small and unequal",
            "R1.5 Buffer sensitivity", "R1.6 Stronger comparator",
            "R1.7 Whole-robot", "R2.1 Deployed proposition condition",
            "R2.2 Inference-completion clock", "R2.3 Unverified startup",
        ):
            self.assertIn("### " + heading, response)
        self.assertIn("previous local map reversed R1/R2", response)

    def test_evidence_boundaries_table_and_text(self):
        main = read("manuscript/main.tex")
        self.assertIn(r"Table~\ref{tab:claim-boundaries}", main)
        self.assertEqual(main.count(r"\label{tab:claim-boundaries}"), 1)
        for row in ("Frame-linked proxy clock &", "Mean moving age and software holds &",
                    "Command-estimated separation &", "Human-reviewed replay &",
                    "Same-input timeout assay &"):
            self.assertIn(row, main)
        self.assertIn("not independently measured robot velocity", main)
        self.assertIn("not verified standstill", main)
        self.assertIn("not a new age-of-information principle or a validated safety theorem", main)

    def test_shadow_scope_and_sample_support(self):
        main = read("manuscript/main.tex")
        response = read("review/CURRENT_REVIEWER_RESPONSE.md")
        self.assertIn("recorded common guard outcomes held fixed", main)
        self.assertIn("from eight primary AEGIS runs", main)
        self.assertIn("59 exploratory transports and one initial capture-proxy pilot", response)
        self.assertIn("offline decisions and replay frames do not increase", response)
        self.assertIn("No alternative trajectory, delivery time or risk is inferred", response)
        self.assertIn("risk-quantification requirement remains unmet", response)

    def test_author_confirmations_not_invented(self):
        main = read("manuscript/main.tex")
        checklist = read("review/SUBMISSION_CHECKLIST.md")
        self.assertIn("No formal ethics waiver is claimed", main)
        self.assertIn("remains to be confirmed before submission", main)
        self.assertIn("OpenAI Codex assisted", main)
        confirmations = re.findall(r"^[1-5]\. \*\*", checklist, re.MULTILINE)
        self.assertEqual(len(confirmations), 5)
        self.assertIn("These items remain open", checklist)
        self.assertIn("neither category should be hidden by marking all reviewer requests complete", checklist)

    def test_data_and_publication_status_local(self):
        main = read("manuscript/main.tex")
        supplement = read("manuscript/supplementary.tex")
        self.assertIn("No public repository identifier or unrestricted data availability is claimed", main)
        self.assertIn("Source-path indexing is provenance, not portable public access", main)
        self.assertIn(r"\label{sec:publication-boundary}", supplement)
        self.assertIn("not an externally deposited dataset or a finalized submission", supplement)
        self.assertIn("unexecuted software revisions are not evidence", supplement)
        self.assertIn("Local paths and a locally tested ZIP do not establish reviewer access",
                      read("review/DATA_RELEASE_CHECKLIST.md"))

    def test_current_guides_and_historical_notices(self):
        readme = read("README_FA.md")
        self.assertIn("۳ اکتبر ۲۰۲۶", readme)
        self.assertIn("چهار پنل", readme)
        for filename in ("CURRENT_REVIEWER_RESPONSE.md", "SUBMISSION_CHECKLIST.md"):
            self.assertIn(filename, readme)
        for filename in ("FINAL_QA.md", "PROPOSAL_RESPONSE_FA.md",
                         "EDITORIAL_AUDIT.md", "REVISION_DECISIONS_FA.md"):
            notice = "\n".join(read("review/" + filename).splitlines()[:5])
            self.assertIn("CURRENT_REVIEWER_RESPONSE.md", notice)
            self.assertIn("remedy8_validation.json", notice)

    def test_all_archived_transport_sources_unchanged(self):
        manifest = json.loads(read("analysis/analysis_manifest.json"))
        self.assertEqual(len(manifest["archived_data"]), 184)
        for filename, expected in manifest["archived_data"].items():
            actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, filename)


if __name__ == "__main__":
    unittest.main()
