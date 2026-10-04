"""Freeze a stratified human review sample and validate genuine human exports.

No robot connection, inference, original-data edits, inferred human labels, or
accuracy estimation occurs here. Model outcomes determine sampling strata only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
import re

from semantic_auto_report import digest, load_run, read_json

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "semantic_auto_audit/run_20260924_203640"
DEST = ROOT / "semantic_human_review/review_426_v1"
TEMPLATE = ROOT / "analysis/semantic_human_template.html"
SCHEMA = "aegis-human-review-v1"
SAMPLE_SEED = 20260924
SHUFFLE_SEED = 20260925
STRATA = ("disagreement", "both_positive", "both_negative")
EXPECTED_POPULATION = {"disagreement": 76, "both_positive": 50, "both_negative": 2032}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def stratum_of(row):
    reference = row["reference"]["presence"]
    monitor = row["monitor"]["prediction"]
    if reference not in {"hand", "no_hand"} or monitor not in {"HUMAN", "OBJECT"}:
        raise ValueError("This frozen three-stratum design requires definite, successful predictions")
    if (reference == "hand") != (monitor == "HUMAN"):
        return "disagreement"
    return "both_positive" if reference == "hand" else "both_negative"


def select_sample(rows, negative_n=300, sample_seed=SAMPLE_SEED, shuffle_seed=SHUFFLE_SEED):
    """Uniform without-replacement negative sample; complete other two strata."""
    if type(negative_n) is not int or negative_n <= 0:
        raise ValueError("negative_n must be a positive integer")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate source IDs")
    grouped = {name: [] for name in STRATA}
    for row in sorted(rows, key=lambda r: r["id"]):
        grouped[stratum_of(row)].append(row)
    if negative_n > len(grouped["both_negative"]):
        raise ValueError("Negative sample exceeds available population")
    selected = grouped["disagreement"] + grouped["both_positive"]
    selected += random.Random(sample_seed).sample(grouped["both_negative"], negative_n)
    random.Random(shuffle_seed).shuffle(selected)
    population = {name: len(grouped[name]) for name in STRATA}
    sample_counts = dict(Counter(stratum_of(row) for row in selected))
    sample_counts = {name: sample_counts.get(name, 0) for name in STRATA}
    return selected, population, sample_counts


def make_frame_rows(selected, mapping, population, sample_counts):
    result = []
    for row in selected:
        meta = mapping[row["id"]]
        group = stratum_of(row)
        n, N = sample_counts[group], population[group]
        alias = "case_" + hashlib.sha256((SCHEMA + ":" + row["id"]).encode()).hexdigest()[:20]
        result.append({
            "case_id": alias, "original_id": row["id"],
            "image": "../../semantic_audit/" + meta["image"],
            "image_sha256": meta["sha256"], "run": meta["run"], "campaign": meta["campaign"],
            "frame_index": meta["frame_index"], "container_time_s": meta["container_time_s"],
            "stratum": group, "inclusion_probability": n / N, "inclusion_weight": N / n,
        })
    return result


def prepare(source=SOURCE, dest=DEST, template=TEMPLATE):
    source, dest, template = Path(source).resolve(), Path(dest).resolve(), Path(template).resolve()
    if dest.exists():
        raise ValueError("Refusing to overwrite an existing frozen review directory: " + str(dest))
    if not template.is_file():
        raise ValueError("Human UI template is not ready; no output created")
    template_text = template.read_text()
    for token in ("__FRAME_DATA__", "__MANIFEST_SHA__"):
        if token not in template_text:
            raise ValueError("Template missing replacement token " + token)
    spec, rows = load_run(source)
    root = source.parent.parent
    source_manifest = root / "semantic_audit/manifest.json"
    if digest(source_manifest) != spec["source_manifest_sha256"]:
        raise ValueError("Original frame manifest differs from the automatic audit specification")
    summary = read_json(source / "summary.json")
    for name, expected in summary["input_hashes"].items():
        if Path(name).name != name or digest(source / name) != expected:
            raise ValueError("Completed automatic report input hash mismatch: " + name)
    selected, population, sample_counts = select_sample(rows)
    if population != EXPECTED_POPULATION:
        raise ValueError("Population differs from the agreed 76/50/2032 review design")
    original = read_json(source_manifest)
    original_by_id = {r["id"]: r for r in original["frames"]}
    mapping = {r["id"]: r for r in read_json(source / "frame_mapping.json")}
    if len(original_by_id) != len(original["frames"]) or set(original_by_id) != set(mapping):
        raise ValueError("Original manifest and model frame mapping ID sets differ")
    for key, row in mapping.items():
        if row != original_by_id[key]:
            raise ValueError("Original manifest and model frame metadata differ: " + key)
    files = ["spec.json", "frame_mapping.json", "reference.jsonl", "monitor.jsonl",
             "reference.sealed.json", "monitor.sealed.json", "summary.json",
             "reference_checkpoint.json", "monitor_checkpoint.json"]
    provenance = {
        "automatic_audit_directory": str(source),
        "automatic_audit_hashes": {name: digest(source / name) for name in files},
        "source_frame_manifest": str(source_manifest),
        "source_frame_manifest_sha256": digest(source_manifest),
        "sampling_code_sha256": digest(__file__),
        "automatic_report_code_sha256": digest(Path(__file__).with_name("semantic_auto_report.py")),
        "template_sha256_at_freeze": digest(template),
    }
    manifest = {
        "schema_version": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Frozen model-stratified human adjudication sample; no human labels are generated.",
        "provenance": provenance,
        "sampling": {
            "population_size": len(rows), "sample_size": len(selected),
            "population_counts": population, "sample_counts": sample_counts,
            "negative_sample_seed": SAMPLE_SEED, "blind_order_seed": SHUFFLE_SEED,
            "algorithm": "Python random.Random.sample without replacement after source-ID sorting; separate random.Random.shuffle",
            "design": "Census of disagreements and both-positive agreements; SRS of 300 both-negative agreements.",
            "frozen_before_human_labels": True,
            "analysis_requirement": "Use stratum inclusion weights for finite-population estimates. The raw enriched-sample fraction is not population accuracy.",
        },
        "blinding": {
            "ui_fields": ["id", "image"],
            "hidden_from_annotation_ui": ["model responses", "stratum", "run", "campaign", "time", "sampling weight"],
            "limitation": "Prior viewing of automatic outputs cannot be undone. Annotators must declare prior_model_exposure; analyst manifest is not annotation material.",
        },
        "scope": "Retrospective video-derived frames from the existing session. Not live-input reconstruction, new subjects/sessions, or physical safety validation. Human uncertain labels remain unresolved, never assumed negative.",
        "frames": make_frame_rows(selected, mapping, population, sample_counts),
    }
    ui_frames = [{"id": r["case_id"], "image": r["image"]} for r in manifest["frames"]]
    # No destination is created until all source, sampling and template checks pass.
    dest.mkdir(parents=True)
    write_json(dest / "manifest.json", manifest)
    write_json(dest / "ui_frames.json", ui_frames)
    rendered = template_text.replace("__FRAME_DATA__", json.dumps(ui_frames, ensure_ascii=False))
    rendered = rendered.replace("__MANIFEST_SHA__", digest(dest / "manifest.json"))
    (dest / "label_review.html").write_text(rendered)
    (dest / "README.md").write_text(readme_text())
    return {"destination": str(dest), "sample_counts": sample_counts,
            "population_counts": population, "total": len(selected),
            "review_manifest_sha256": digest(dest / "manifest.json"),
            "status": "awaiting genuine human annotations; no accuracy estimate computed"}


def readme_text():
    return """# Frozen human review / بازبینی انسانی

## فارسی

فقط `label_review.html` را برای برچسب‌گذاری باز کنید؛ فایل manifest برای تحلیل‌گر است و گروه نمونه‌گیری را آشکار می‌کند. ۴۲۶ تصویر به ترتیب مخلوط نمایش داده می‌شوند: تمام ۷۶ اختلاف دو مدل، تمام ۵۰ توافق مثبت و نمونهٔ تصادفی ۳۰۰تایی از ۲۰۳۲ توافق منفی. هیچ جواب مدل یا برچسب پیشنهادی در صفحه نمایش داده نمی‌شود.

برای هر تصویر فقط آنچه دیده می‌شود ثبت کنید: «دست هست»، «دست نیست» یا «نامشخص». دستکشِ پوشیده‌شده روی دست، دست محسوب می‌شود؛ گریپر و دستکش خالی دست نیستند. پوشش پوست با دستکش به‌تنهایی پوشیدگی دید نیست؛ پوشیدگی یعنی بخشی از دست پشت جسم، ربات یا لبهٔ تصویر پنهان باشد. اگر چند دست دیده می‌شود، وجود دست کافی است؛ «کامل» یعنی حداقل یک دست کامل دیده می‌شود. در صورت ترکیب پوست برهنه و دستکش در دست‌های دیده‌شده، گزینهٔ ترکیبی را ثبت کنید.

نام/شناسهٔ برچسب‌زن و اینکه قبلاً جواب مدل‌ها را دیده‌اید ثبت شود. اگر گزارش یا نمونه‌های دارای جواب مدل‌ها را قبلاً دیده‌اید، گزینهٔ «بله» را انتخاب کنید؛ صفحهٔ بدون جواب مدل، مواجههٔ قبلی را از بین نمی‌برد. ذخیرهٔ مرورگر جای فایل خروجی را نمی‌گیرد: مرتب خروجی JSON دانلود کنید. برای برچسب‌زن دوم فایل و شناسهٔ جدا و پروفایل مرورگر/ذخیرهٔ محلی خالی و مستقل نگه دارید؛ قبل از مقایسهٔ نظرها، پاسخ یکدیگر را نبینید. هنگام برچسب‌گذاری سراغ گزارش مدل‌ها نروید. این مرحله برچسب انسانی را خودکار تولید نمی‌کند و پاسخ تمام ایرادهای داوری نیست.

## English

The design is frozen before human review. Sampling: census of all 76 disagreements and all 50 positive agreements, plus simple random sampling without replacement of 300/2032 negative agreements. Negative sampling seed: 20260924; independent display shuffle seed: 20260925. Inclusion probabilities are 1, 1, and 300/2032; weights are 1, 1, and 2032/300. Analyst metadata and predictions are excluded from the annotation UI.

Do not estimate population accuracy by counting unweighted answers in this enriched sample. A subsequent analysis must retain uncertain labels as unresolved, report their weighted prevalence/coverage, use the known inclusion probabilities, quantify uncertainty and account for correlated frames/runs. In particular, zero observed errors in the sampled negative stratum is not proof that no unsampled errors exist.

This is retrospective human review of compressed, same-session video frames and current-model replay. It does not validate sensor-exposure timing, exact historical live inputs, new-subject/new-session performance, physical or whole-arm safety, or comparative AEGIS efficacy. Prior exposure to model outputs is declared, not erased by this blind UI: a reviewer who saw the report/examples must choose yes. Do not consult model outputs while annotating. A separate second reviewer is recommended, using an isolated blank browser/local-storage profile; preserve independent exports and disagreements before adjudication.

Export schema: aegis-human-review-v1. `label_source` must be human. Required top-level keys: schema_version, label_source, review_manifest_sha256, annotator, prior_model_exposure (yes/no/unsure), labels, saved_at. Each label requires id, label (hand/no_hand/uncertain), cover, visibility, note, reviewed_at. For hand: cover is bare/glove/mixed/uncertain and visibility is full/partial/uncertain. For no_hand or uncertain: cover and visibility must be null. Timestamps must be timezone-aware ISO-8601 strings. Partial exports can be validated; final completeness requires --require-complete.

Run validation from the project root using the existing Python environment:

    python analysis/semantic_human_review.py validate /path/to/human-export.json
    python analysis/semantic_human_review.py validate /path/to/human-export.json --require-complete

The validator checks manifest identity, source image hashes, IDs, duplicate labels, human provenance declaration, annotator/exposure fields, condition combinations, timestamps, and completeness when requested. It cannot certify that a human actually performed the review or that the judgment is correct. It produces no empirical accuracy metric and never changes originals.
"""


def require_iso(value, field):
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        raise ValueError(field + " requires an ISO timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(field + " requires an ISO timestamp") from exc
    if stamp.utcoffset() is None:
        raise ValueError(field + " must include a timezone")


def validate_export(labels_path, manifest_path=DEST / "manifest.json", require_complete=False):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported review manifest schema")
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Review manifest frames must be nonempty")
    expected = {}
    # Derive the image root from the review location; images must never escape it.
    image_root = (manifest_path.parent / "../../semantic_audit/frames").resolve(strict=True)
    for frame in frames:
        key = frame.get("case_id")
        if not isinstance(key, str) or not key or key in expected:
            raise ValueError("Invalid or duplicate review manifest case ID")
        path = PurePosixPath(frame.get("image", ""))
        if path.parts[:4] != ("..", "..", "semantic_audit", "frames") or len(path.parts) != 5:
            raise ValueError("Review image path must identify one semantic_audit/frames file")
        image = manifest_path.parent.joinpath(*path.parts).resolve(strict=True)
        if not image.is_relative_to(image_root) or digest(image) != frame.get("image_sha256"):
            raise ValueError("Review source image hash/path mismatch: " + key)
        expected[key] = frame
    payload = read_json(labels_path)
    fields = {"schema_version", "label_source", "review_manifest_sha256", "annotator",
              "prior_model_exposure", "labels", "saved_at"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("Human export has missing or unsupported top-level fields")
    if payload["schema_version"] != SCHEMA or payload["label_source"] != "human":
        raise ValueError("Export must declare the human review schema and label_source=human")
    if payload["review_manifest_sha256"] != digest(manifest_path):
        raise ValueError("Human export review manifest hash mismatch")
    if not isinstance(payload["annotator"], str) or not payload["annotator"].strip():
        raise ValueError("Annotator identity is required")
    if payload["prior_model_exposure"] not in {"yes", "no", "unsure"}:
        raise ValueError("Prior model exposure must be yes, no or unsure")
    require_iso(payload["saved_at"], "saved_at")
    labels = payload["labels"]
    if not isinstance(labels, list):
        raise ValueError("labels must be a list")
    seen = set()
    for row in labels:
        if not isinstance(row, dict) or set(row) != {"id", "label", "cover", "visibility", "note", "reviewed_at"}:
            raise ValueError("Annotation has missing or unsupported fields")
        key = row["id"]
        if not isinstance(key, str) or key not in expected:
            raise ValueError("Unknown annotation ID")
        if key in seen:
            raise ValueError("Duplicate annotation ID: " + key)
        seen.add(key)
        if row["label"] not in {"hand", "no_hand", "uncertain"}:
            raise ValueError("Invalid human presence label")
        if row["label"] == "hand":
            if row["cover"] not in {"bare", "glove", "mixed", "uncertain"}:
                raise ValueError("Visible hand needs a valid covering label")
            if row["visibility"] not in {"full", "partial", "uncertain"}:
                raise ValueError("Visible hand needs a valid visibility label")
        elif row["cover"] is not None or row["visibility"] is not None:
            raise ValueError("Non-hand/uncertain presence must have null cover and visibility")
        if not isinstance(row["note"], str):
            raise ValueError("Annotation note must be a string")
        require_iso(row["reviewed_at"], "reviewed_at")
    if require_complete and set(expected) != seen:
        raise ValueError(f"Incomplete human review: {len(seen)}/{len(expected)} labels")
    return {"valid": True, "human_declaration_only": True, "annotator": payload["annotator"],
            "prior_model_exposure": payload["prior_model_exposure"], "reviewed": len(seen),
            "total": len(expected), "complete": set(expected) == seen,
            "uncertain_count": sum(r["label"] == "uncertain" for r in labels),
            "status": "export integrity verified; no accuracy or safety estimate computed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--source", type=Path, default=SOURCE)
    prep.add_argument("--dest", type=Path, default=DEST)
    prep.add_argument("--template", type=Path, default=TEMPLATE)
    validate = commands.add_parser("validate")
    validate.add_argument("labeljson", type=Path)
    validate.add_argument("--manifest", type=Path, default=DEST / "manifest.json")
    validate.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.dest, args.template) if args.command == "prepare" else validate_export(args.labeljson, args.manifest, args.require_complete)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, "ERROR: " + str(exc) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
