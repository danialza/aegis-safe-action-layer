"""Synthetic integrity tests; never writes real annotations or audit outputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from semantic_human_review import SCHEMA, digest, make_frame_rows, select_sample, stratum_of, validate_export, write_json


class SamplingTests(unittest.TestCase):
    def rows(self):
        def row(i, p, v):
            return {"id": str(i), "reference": {"presence": p}, "monitor": {"prediction": v}}
        return [row(0, "hand", "OBJECT"), row(1, "no_hand", "HUMAN"),
                row(2, "hand", "HUMAN")] + [row(i, "no_hand", "OBJECT") for i in range(3, 13)]

    def test_reproducible_independent_of_input_order(self):
        first = select_sample(self.rows(), negative_n=3)
        self.assertEqual(first, select_sample(list(reversed(self.rows())), negative_n=3))
        selected, population, counts = first
        self.assertEqual(population, {"disagreement": 2, "both_positive": 1, "both_negative": 10})
        self.assertEqual(counts, {"disagreement": 2, "both_positive": 1, "both_negative": 3})
        self.assertEqual(len({r["id"] for r in selected}), 6)
        self.assertTrue({"0", "1", "2"}.issubset({r["id"] for r in selected}))

    def test_weights_and_aliases(self):
        selected, population, counts = select_sample(self.rows(), negative_n=3)
        mapping = {r["id"]: {"image": "frames/" + r["id"] + ".jpg", "sha256": "x",
                             "run": "r", "campaign": "c", "frame_index": 1, "container_time_s": 1.0}
                   for r in selected}
        frames = make_frame_rows(selected, mapping, population, counts)
        self.assertEqual(len({r["case_id"] for r in frames}), 6)
        self.assertAlmostEqual(sum(r["inclusion_weight"] for r in frames), 13)
        for frame in frames:
            self.assertTrue(frame["case_id"].startswith("case_"))
            self.assertAlmostEqual(frame["inclusion_weight"] * frame["inclusion_probability"], 1)
            self.assertEqual(set({"id": frame["case_id"], "image": frame["image"]}), {"id", "image"})

    def test_reject_nondefinite_duplicate_or_overlarge(self):
        with self.assertRaises(ValueError):
            stratum_of({"reference": {"presence": "uncertain"}, "monitor": {"prediction": "OBJECT"}})
        with self.assertRaises(ValueError):
            select_sample(self.rows() + [self.rows()[0]], negative_n=3)
        with self.assertRaises(ValueError):
            select_sample(self.rows(), negative_n=11)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dest = self.root / "semantic_human_review/review_426_v1"
        self.dest.mkdir(parents=True)
        images = self.root / "semantic_audit/frames"
        images.mkdir(parents=True)
        self.image = images / "test.jpg"
        self.image.write_bytes(b"synthetic-image-content")
        self.manifest = self.dest / "manifest.json"
        write_json(self.manifest, {"schema_version": SCHEMA, "frames": [
            {"case_id": "case_a", "image": "../../semantic_audit/frames/test.jpg", "image_sha256": digest(self.image)},
            {"case_id": "case_b", "image": "../../semantic_audit/frames/test.jpg", "image_sha256": digest(self.image)},
        ]})
        self.payload = {"schema_version": SCHEMA, "label_source": "human", "review_manifest_sha256": digest(self.manifest),
                        "annotator": "Synthetic test reviewer", "prior_model_exposure": "unsure",
                        "saved_at": "2026-09-24T21:00:00Z", "labels": [
                            {"id": "case_a", "label": "hand", "cover": "glove", "visibility": "partial",
                             "note": "synthetic", "reviewed_at": "2026-09-24T20:59:00+00:00"}]}
        self.export = self.root / "labels.json"

    def tearDown(self):
        self.temp.cleanup()

    def check(self, payload=None, require_complete=False):
        write_json(self.export, self.payload if payload is None else payload)
        return validate_export(self.export, self.manifest, require_complete)

    def test_partial_accepted_but_final_requires_complete(self):
        result = self.check()
        self.assertEqual(result["reviewed"], 1)
        self.assertFalse(result["complete"])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.check(require_complete=True)
        other = copy.deepcopy(self.payload["labels"][0])
        other.update(id="case_b", label="uncertain", cover=None, visibility=None)
        self.payload["labels"].append(other)
        self.assertTrue(self.check(require_complete=True)["complete"])
        self.assertEqual(self.check()["uncertain_count"], 1)

    def test_empty_partial_is_not_complete(self):
        self.payload["labels"] = []
        self.assertEqual(self.check()["reviewed"], 0)

    def test_reject_model_labels_manifest_mismatch_and_missing_identity(self):
        for key, value in [("label_source", "model"), ("review_manifest_sha256", "bad"),
                           ("annotator", "  "), ("prior_model_exposure", "unknown"), ("saved_at", "2026-09-24T21:00:00")]:
            with self.subTest(key=key):
                payload = copy.deepcopy(self.payload)
                payload[key] = value
                with self.assertRaises(ValueError):
                    self.check(payload)

    def test_reject_duplicate_unknown_and_wrong_condition(self):
        cases = []
        duplicate = copy.deepcopy(self.payload)
        duplicate["labels"].append(copy.deepcopy(duplicate["labels"][0]))
        cases.append(duplicate)
        for key, value in [("id", "unknown"), ("cover", None), ("visibility", "hidden"),
                           ("label", "no_hand"), ("note", None), ("reviewed_at", "yesterday")]:
            payload = copy.deepcopy(self.payload)
            payload["labels"][0][key] = value
            cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.check(payload)

    def test_reject_missing_or_extra_fields(self):
        payload = copy.deepcopy(self.payload)
        del payload["labels"][0]["reviewed_at"]
        with self.assertRaises(ValueError):
            self.check(payload)
        payload = copy.deepcopy(self.payload)
        payload["model_prediction"] = "HUMAN"
        with self.assertRaises(ValueError):
            self.check(payload)

    def test_image_tampering_rejected(self):
        self.image.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "image hash"):
            self.check()


if __name__ == "__main__":
    unittest.main()
