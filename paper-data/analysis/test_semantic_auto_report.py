"""Synthetic unit checks only; creates no empirical/model results."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import semantic_auto_report as report


class AutoReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / "semantic_auto_audit/run_synthetic"
        self.run.mkdir(parents=True)
        (self.root / "semantic_audit/frames").mkdir(parents=True)
        self.mapping, self.refs, self.monitors = [], [], []
        for idx, (code, presence, prediction) in enumerate([
            ("G1", "hand", "HUMAN"), ("B0", "hand", "ERROR"),
            ("N", "no_hand", "OBJECT"), ("N", "no_hand", "HUMAN"),
            ("U", "uncertain", "OBJECT"), ("ERROR", "error", "ERROR")]):
            key = f"test{idx}"
            content = ("synthetic bytes " + key).encode()
            (self.root / "semantic_audit/frames" / (key + ".jpg")).write_bytes(content)
            self.mapping.append({"id": key, "run": "r" + str(idx % 2), "campaign": "synthetic",
                                 "container_time_s": idx * 2., "image": "frames/" + key + ".jpg",
                                 "sha256": hashlib.sha256(content).hexdigest()})
            self.refs.append({"id": key, "image_sha256": hashlib.sha256(content).hexdigest(),
                              "label_source": "model", "code": code, "presence": presence,
                              "cover": "glove" if code == "G1" else "bare" if code == "B0" else None,
                              "visibility": "partial" if code == "G1" else "full" if code == "B0" else None,
                              "raw_text": code, "error": "synthetic error" if code == "ERROR" else None,
                              "inference_s": .1})
            self.monitors.append({"id": key, "prediction": prediction, "raw_text": "1" if prediction == "HUMAN" else "0",
                                  "image_sha256": hashlib.sha256(content).hexdigest(),
                                  "parsed_count": 1 if prediction == "HUMAN" else 0,
                                  "strict_count": None if prediction == "ERROR" else 1 if prediction == "HUMAN" else 0,
                                  "error": "synthetic error" if prediction == "ERROR" else None, "inference_s": .2})
        self.write_inputs()

    def tearDown(self):
        self.temp.cleanup()

    def write_inputs(self, bind_spec=True):
        (self.run / "frame_mapping.json").write_text(json.dumps(self.mapping))
        (self.run / "spec.json").write_text(json.dumps({"synthetic_test_only": True,
            "total_frames": len(self.mapping), "mapping_sha256": report.digest(self.run / "frame_mapping.json")}))
        for name, rows in (("reference", self.refs), ("monitor", self.monitors)):
            if bind_spec:
                for row in rows:
                    row["spec_sha256"] = report.digest(self.run / "spec.json")
            (self.run / (name + ".jsonl")).write_text("".join(json.dumps(row) + "\n" for row in rows))
            (self.run / (name + ".sealed.json")).write_text(json.dumps({"spec_sha256": report.digest(self.run / "spec.json"),
                "rows": len(self.mapping), "predictions_sha256": report.digest(self.run / (name + ".jsonl"))}))

    def test_accounting_and_error_denominators(self):
        _, rows = report.load_run(self.run)
        s = report.summarize(rows)
        self.assertEqual(s["frame_count"], 6)
        self.assertEqual(s["accounting_disjoint"], {"all_frames": 6, "both_definite_and_successful": 3,
                         "definite_reference_monitor_error": 1, "reference_uncertain_any_monitor": 1,
                         "reference_error_any_monitor": 1})
        self.assertEqual(s["agreement_among_successful_definite_pairs"]["value"], 2/3)
        self.assertEqual(s["agreement_among_all_definite_reference_including_monitor_errors"]["value"], .5)
        self.assertEqual(s["monitor_HUMAN_rate_among_model_reference_hand_including_monitor_errors"]["denominator"], 2)
        self.assertEqual(s["monitor_error_fraction_all_frames"]["numerator"], 2)

    def test_empty_positive_returns_null(self):
        _, rows = report.load_run(self.run)
        s = report.summarize([r for r in rows if r["reference"]["presence"] == "no_hand"])
        self.assertIsNone(s["monitor_HUMAN_rate_among_model_reference_hand_including_monitor_errors"]["value"])
        self.assertEqual(s["monitor_HUMAN_rate_among_model_reference_hand_including_monitor_errors"]["denominator"], 0)
        self.assertIsNone(report.summarize([])["agreement_among_successful_definite_pairs"]["value"])

    def test_duplicate_ids_rejected(self):
        self.refs.append(dict(self.refs[0]))
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "duplicate ID"):
            report.load_run(self.run)

    def test_missing_ids_rejected(self):
        self.monitors.pop()
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "missing IDs=1"):
            report.load_run(self.run)

    def test_unknown_ids_rejected(self):
        self.monitors[0]["id"] = "not_mapped"
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "unknown IDs=1"):
            report.load_run(self.run)

    def test_human_claim_rejected(self):
        self.refs[0]["label_source"] = "human"
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "label_source=model"):
            report.load_run(self.run)

    def test_error_cannot_become_negative(self):
        self.monitors[1]["prediction"] = "OBJECT"
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "Monitor error"):
            report.load_run(self.run)

    def test_bad_image_hash_rejected(self):
        self.refs[0]["image_sha256"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "image hash mismatch"):
            report.load_run(self.run)

    def test_nan_rejected(self):
        self.refs[0]["inference_s"] = float("nan")
        self.write_inputs()
        with self.assertRaises(ValueError):
            report.load_run(self.run)

    def test_sealed_outputs_cannot_change(self):
        with (self.run / "reference.jsonl").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "sealed prediction hash mismatch"):
            report.load_run(self.run)

    def test_missing_seal_rejected(self):
        (self.run / "monitor.sealed.json").unlink()
        with self.assertRaises(FileNotFoundError):
            report.load_run(self.run)

    def test_code_condition_mismatch_rejected(self):
        self.refs[0]["visibility"] = "full"
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "code/condition mismatch"):
            report.load_run(self.run)

    def test_required_provenance_fields(self):
        original = json.dumps([self.mapping, self.refs, self.monitors])
        for location, field in (("spec", "total_frames"), ("spec", "mapping_sha256"),
                                ("reference", "spec_sha256"), ("monitor", "spec_sha256"),
                                ("monitor", "image_sha256"), ("mapping", "sha256")):
            with self.subTest(location=location, field=field):
                self.mapping, self.refs, self.monitors = json.loads(original)
                self.write_inputs()
                if location == "spec":
                    spec = json.loads((self.run / "spec.json").read_text())
                    spec.pop(field)
                    (self.run / "spec.json").write_text(json.dumps(spec))
                else:
                    {"reference": self.refs, "monitor": self.monitors, "mapping": self.mapping}[location][0].pop(field)
                    self.write_inputs(bind_spec=location not in {"reference", "monitor"} or field != "spec_sha256")
                with self.assertRaises(ValueError):
                    report.load_run(self.run)
        self.mapping, self.refs, self.monitors = json.loads(original)
        self.mapping[0]["sha256"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "Frozen mapping image hash mismatch"):
            report.load_run(self.run)

    def test_report_preserves_inputs_and_escapes_raw_text(self):
        self.refs[0]["raw_text"] = "</script><script>bad()</script>"
        self.write_inputs()
        paths = [self.run / name for name in ("spec.json", "frame_mapping.json", "reference.jsonl", "monitor.jsonl")]
        before = {str(p): report.digest(p) for p in paths}
        result = report.build_report(self.run)
        self.assertFalse(result["independent_ground_truth_available"])
        self.assertEqual(before, {str(p): report.digest(p) for p in paths})
        page = (self.run / "report.html").read_text()
        self.assertNotIn("</script><script>bad()", page)
        self.assertIn("\\u003c/script>", page)
        self.assertIn("../../semantic_audit/frames/test0.jpg", page)
        self.assertEqual(set(result["by_model_estimated_cover"]), {"glove", "bare", "not_assigned"})
        self.assertTrue((self.run / "report_FA.md").is_file())
        self.assertTrue((self.run / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
