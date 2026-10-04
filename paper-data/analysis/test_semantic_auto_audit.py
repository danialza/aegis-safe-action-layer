"""Synthetic code tests only; never contributes labels to the empirical audit."""
import json
from pathlib import Path
import tempfile
import unittest

from semantic_auto_audit import parse_reference, completed_rows, seal_check, save
from semantic_frame_audit import sha, checked_annotations


class AutoAuditTests(unittest.TestCase):
    def test_codes_and_abstention(self):
        self.assertEqual(parse_reference("G1")["presence"], "hand")
        self.assertEqual(parse_reference("G1")["cover"], "glove")
        self.assertEqual(parse_reference("G1")["visibility"], "partial")
        self.assertEqual(parse_reference(" B0\n")["visibility"], "full")
        self.assertEqual(parse_reference("N")["presence"], "no_hand")
        self.assertEqual(parse_reference("U")["presence"], "uncertain")
        for bad in ("", "None", "G1 because a glove", "N.", "U N", "B2", "0", "n"):
            self.assertEqual(parse_reference(bad)["presence"], "error")
            self.assertEqual(parse_reference(bad)["code"], "INVALID")

    def test_resume_prefix_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rows.jsonl"
            frames = [dict(id="a", sha256="image_a"), dict(id="b", sha256="image_b")]
            self.assertEqual(completed_rows(path, frames, "spec"), [])
            good = dict(id="a", image_sha256="image_a", spec_sha256="spec")
            path.write_text(json.dumps(good) + "\n")
            self.assertEqual(len(completed_rows(path, frames, "spec")), 1)
            for rows in ([good, good], [dict(good, id="b")], [dict(good, image_sha256="bad")],
                         [dict(good, spec_sha256="old")]):
                path.write_text("\n".join(map(json.dumps, rows)) + "\n")
                with self.assertRaises(ValueError):
                    completed_rows(path, frames, "spec")

    def test_seal_detects_mutation_and_wrong_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pred = root / "reference.jsonl"
            pred.write_text('{"synthetic": true}\n')
            save(root / "reference.sealed.json", dict(spec_sha256="s", predictions_sha256=sha(pred)))
            seal_check(root, "reference", "s")
            with self.assertRaises(ValueError):
                seal_check(root, "reference", "wrong")
            pred.write_text('{}\n')
            with self.assertRaises(ValueError):
                seal_check(root, "reference", "s")

    def test_model_labels_rejected_by_human_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "annotations.json"
            save(path, dict(annotator="automatic-model", label_source="model", labels=[]))
            with self.assertRaisesRegex(ValueError, "Model labels"):
                checked_annotations(path, {"frames": []})

    def test_exclusive_outputs_and_finite_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.json"
            save(path, {"test": 1}, True)
            with self.assertRaises(FileExistsError):
                save(path, {"test": 2}, True)
            with self.assertRaises(ValueError):
                save(Path(folder) / "nan.json", {"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
