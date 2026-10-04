"""Offline retrospective frame-audit preparation/evaluation. No robot imports.

prepare: uniformly sample all available capture-proxy videos and create a blind
human-labelling page. evaluate: requires completed independent HUMAN annotations
before local FastVLM replay with a fingerprinted current checkpoint. Historical
weight identity is not established. Never fills missing ground truth.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "semantic_audit"
LABELS = {"hand", "no_hand", "uncertain"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def render_label_page(manifest=None):
    """Refresh UI only; never alter the frozen frame manifest or extracted images."""
    manifest = manifest or json.loads((DEST / "manifest.json").read_text())
    ui_rows = [{"id": r["id"], "image": r["image"]} for r in manifest["frames"]]
    ui = (ROOT / "analysis/semantic_label_template.html").read_text()
    ui = ui.replace("__FRAME_DATA__", json.dumps(ui_rows)).replace("__MANIFEST_SHA__", sha(DEST / "manifest.json"))
    (DEST / "label_frames.html").write_text(ui)
    return DEST / "label_frames.html"


def prepare(interval=2.0):
    import cv2
    assert interval >= 2
    DEST.mkdir(exist_ok=True)
    (DEST / "frames").mkdir(exist_ok=True)
    inventory = json.loads((ROOT / "analysis/inventory_source.json").read_text())
    frames, videos, missing = [], [], []
    for listed in sorted(inventory["runs"], key=lambda r: r["run"]):
        original = Path(listed["path"])
        local = ROOT / "data" / listed["campaign"] / "logs" / original.name
        source = local if local.exists() else original
        if not source.exists():
            missing.append({"run": listed["run"], "reason": "source log unavailable"})
            continue
        record = json.loads(source.read_text())
        video = Path(record.get("raw_video") or "__no_video__")
        if not video.is_file():
            missing.append({"run": listed["run"], "reason": "RAW video unavailable"})
            continue
        cap = cv2.VideoCapture(str(video))
        fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or fps <= 0 or count <= 0:
            cap.release()
            missing.append({"run": listed["run"], "reason": "video header/decoder unavailable"})
            continue
        step = math.ceil(interval * fps)
        # Deterministic within-run phase avoids choosing frames by labels/results.
        offset = int(hashlib.sha256(listed["run"].encode()).hexdigest()[:8], 16) % step
        digest = sha(video)
        videos.append({"run": listed["run"], "path": str(video), "sha256": digest,
                       "fps": fps, "frame_count": count, "step_frames": step, "offset_frames": offset})
        for idx in range(offset, count, step):
            frame_id = hashlib.sha256(f"{digest}:{idx}".encode()).hexdigest()[:18]
            target = DEST / "frames" / f"{frame_id}.jpg"
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                missing.append({"run": listed["run"], "frame": idx, "reason": "decode failure"})
                continue
            assert cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            frames.append({"id": frame_id, "run": listed["run"], "campaign": listed["campaign"],
                           "frame_index": idx, "container_time_s": idx / fps,
                           "image": str(target.relative_to(DEST)), "sha256": sha(target)})
        cap.release()
    assert frames
    # Identifier sort is unrelated to method, direction, or known hand content.
    frames.sort(key=lambda r: r["id"])
    manifest = {"design": "retrospective single-session audit, not a subject/session-disjoint generalization test",
                "sampling": "Uniform >=2s container-time spacing with deterministic run-specific phase; no semantic preselection.",
                "timing_limit": "Container frame time is not sensor exposure or controller event time.",
                "source_inventory_sha256": sha(ROOT / "analysis/inventory_source.json"),
                "interval_s": interval, "videos": videos, "frames": frames, "missing": missing,
                "status": "awaiting independent human labels; no recall or safety result exists"}
    write_json(DEST / "manifest.json", manifest)
    render_label_page(manifest)
    print(json.dumps({"frames": len(frames), "videos": len(videos), "missing_items": len(missing),
                      "human_label_page": str(DEST / "label_frames.html"), "status": manifest["status"]}, indent=2))


def checked_annotations(path, manifest):
    def require(condition, message):
        # Integrity checks must remain active even if Python uses optimization.
        if not condition:
            raise ValueError(message)
    payload = json.loads(Path(path).read_text())
    require(payload.get("annotator", "").strip(), "Human annotator identity is required")
    require(payload.get("label_source") == "human", "Model labels cannot serve as independent ground truth")
    require(payload.get("manifest_sha256") == sha(DEST / "manifest.json"), "Annotation manifest mismatch")
    rows = payload.get("labels", [])
    require(len({r["id"] for r in rows}) == len(rows), "Duplicate annotation IDs")
    by_id = {r["id"]: r["label"] for r in rows}
    expected = {r["id"] for r in manifest["frames"]}
    require(set(by_id) == expected, "Complete every frame; do not drop unlabelled cases selectively")
    require(all(label in LABELS for label in by_id.values()), "Unrecognized annotation label")
    for r in manifest["frames"]:
        require(sha(DEST / r["image"]) == r["sha256"], "Image hash mismatch: " + r["id"])
    return payload, by_id


def checkpoint_identity(snapshot_path, model_id):
    """Hash cached weights, processor/tokenizer/config files without loading a model."""
    snapshot = Path(snapshot_path).expanduser().resolve(strict=True)
    if not snapshot.is_dir():
        raise ValueError("The model snapshot must be an existing local directory")
    files = [p for p in sorted(snapshot.rglob("*")) if p.is_file()]
    weights = [p for p in files if p.suffix == ".safetensors"]
    if not weights or not (snapshot / "config.json").is_file():
        raise ValueError("The local checkpoint needs config.json and safetensors weights")
    if not any("tokenizer" in p.name or p.name in {"vocab.json", "vocab.txt", "spiece.model"} for p in files):
        raise ValueError("Local tokenizer files are required; no download is allowed")
    records = [{"path": str(p.relative_to(snapshot)), "bytes": p.stat().st_size,
                "sha256": sha(p)} for p in files]
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {"model_id": model_id, "local_snapshot": str(snapshot),
            "cache_revision": snapshot.name if re.fullmatch(r"[0-9a-f]{40}", snapshot.name) else None,
            "files": records, "file_manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            "historical_weights_verified": False,
            "scope": "Current cached checkpoint replay; no historical checkpoint fingerprint is available for equivalence verification."}


def environment_identity():
    libraries = {}
    for name in ("mlx", "mlx-vlm", "transformers", "huggingface-hub", "tokenizers",
                 "Pillow", "opencv-python", "numpy", "safetensors"):
        try:
            libraries[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            libraries[name] = None
    return {"python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "machine": platform.machine(),
            "libraries": libraries}


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p, denom = k / n, 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return [max(0., center-half), min(1., center+half)]


def strict_count(text):
    text = text.strip().lower().rstrip(".! ")
    words = {"zero": 0, "no": 0, "none": 0, "one": 1, "two": 2, "three": 3}
    if re.fullmatch(r"\d+", text):
        return int(text)
    return words.get(text)


def summarize(rows):
    import numpy as np
    positive = [r for r in rows if r["truth"] == "hand"]
    negative = [r for r in rows if r["truth"] == "no_hand"]
    tp = sum(r["prediction"] == "HUMAN" for r in positive)
    fp = sum(r["prediction"] == "HUMAN" for r in negative)
    groups = sorted({r["run"] for r in rows})
    by_group = {g: [r for r in rows if r["run"] == g] for g in groups}
    rng = np.random.default_rng(20260924)
    boot_recall, boot_fpr = [], []
    for _ in range(2000):
        sample = [r for g in rng.choice(groups, len(groups), replace=True) for r in by_group[g]]
        pp = [r for r in sample if r["truth"] == "hand"]
        nn = [r for r in sample if r["truth"] == "no_hand"]
        if pp:
            boot_recall.append(sum(r["prediction"] == "HUMAN" for r in pp) / len(pp))
        if nn:
            boot_fpr.append(sum(r["prediction"] == "HUMAN" for r in nn) / len(nn))
    latency = [r["inference_s"] for r in rows if not r.get("error") and r.get("inference_s") is not None]
    interval = lambda v: np.quantile(v, [.025, .975]).tolist() if v else None
    return {"label_counts": dict(Counter(r["truth"] for r in rows)), "runs": len(groups),
            "human_recall": tp/len(positive) if positive else None,
            "false_positive_rate": fp/len(negative) if negative else None,
            "true_human_positive_count": tp, "false_positive_count": fp,
            "naive_frame_wilson95_recall": wilson(tp, len(positive)),
            "naive_frame_wilson95_fpr": wilson(fp, len(negative)),
            "run_cluster_percentile95_recall": interval(boot_recall),
            "run_cluster_percentile95_fpr": interval(boot_fpr),
            "runs_with_hand_frames": len({r["run"] for r in positive}),
            "parser_noncanonical_responses": sum(r.get("strict_count") is None and not r.get("error") for r in rows),
            "errors": sum(bool(r.get("error")) for r in rows),
            "errors_by_truth": dict(Counter(r["truth"] for r in rows if r.get("error"))),
            "prediction_counts_by_truth": {truth: dict(Counter(r["prediction"] for r in rows if r["truth"] == truth)) for truth in sorted(LABELS)},
            "inference_mean_s": statistics.mean(latency) if latency else None,
            "inference_p95_s": float(np.quantile(latency, .95)) if latency else None,
            "latency_scope": "Successful warmed offline calls only; exceptions are counted separately, not mixed into inference latency.",
            "denominator_scope": "HUMAN recall and HUMAN false-positive rate include all hand/no_hand labelled frames respectively; ERROR is not a HUMAN prediction. Uncertain labels are excluded from both denominators and reported separately.",
            "interval_limit": "Frame Wilson intervals assume independence and are illustrative only; run bootstrap retains within-run clustering but not dependence of the single operator/session.",
            "small_positive_warning": len(positive) < 20,
            "scope": "Current-checkpoint replay of lossy decoded RAW-video frames, not exact live VLM inputs, live inference latency, first-intrusion delay, or independent-session generalization."}


def evaluate(annotation_path, run_model=False, model_snapshot=None):
    manifest = json.loads((DEST / "manifest.json").read_text())
    payload, labels = checked_annotations(annotation_path, manifest)
    print(json.dumps({"annotations_checked": len(labels), "counts": dict(Counter(labels.values()))}))
    if not run_model:
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    monitor_path = ROOT / "provenance_code/safebench/fastvlm_monitor.py"
    expected = {d["sha256"] for d in json.loads((ROOT / "provenance_code/metadata/snapshot_manifest.json").read_text())["verified_code_configuration_files"]
                if d["archive_path"].endswith("safebench/fastvlm_monitor.py")}
    if expected != {sha(monitor_path)}:
        raise ValueError("Frozen monitor has changed")
    spec = importlib.util.spec_from_file_location("frozen_frame_monitor", monitor_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if model_snapshot is None:
        from huggingface_hub import snapshot_download
        # Resolves an existing cached revision only; this never requests a download.
        model_snapshot = snapshot_download(
            repo_id=module.MODEL_ID, local_files_only=True,
            # Model loading does not require uncached repository README/license
            # metadata. Restrict to execution assets, still without networking.
            allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt",
                            "*.tiktoken", "*.jinja", "*.py"],
        )
    identity = checkpoint_identity(model_snapshot, module.MODEL_ID)
    out = DEST / ("evaluation_" + time.strftime("%Y%m%d_%H%M%S"))
    out.mkdir(exist_ok=False)
    write_json(out / "checkpoint_identity.json", identity)
    write_json(out / "frozen_spec.json", {"manifest_sha256": sha(DEST / "manifest.json"),
               "annotation_sha256": sha(annotation_path), "annotator": payload["annotator"],
               "monitor_sha256": sha(monitor_path), "script_sha256": sha(__file__),
               "model_id": module.MODEL_ID, "prompt": module.COUNT_Q,
               "checkpoint_file_manifest_sha256": identity["file_manifest_sha256"],
               "checkpoint_record_sha256": sha(out / "checkpoint_identity.json"),
               "historical_weights_verified": False, "environment": environment_identity(),
               "image_max_dimension": 256, "max_tokens": 6, "temperature": 0,
               "local_offline_only": True, "robot_connection": False,
               "image_scope": "Decoded RAW-video frames re-encoded as JPEG95, not the exact live VLM source arrays."})
    from PIL import Image
    # Pass the resolved local directory rather than a mutable remote model identifier.
    monitor = module.FastVLMMonitor(model_id=identity["local_snapshot"], imgpx=256, max_tokens=6)
    rows = []
    with (out / "predictions.jsonl").open("x", buffering=1) as stream:
        for f in manifest["frames"]:
            im = Image.open(DEST / f["image"]).convert("RGB")
            start = time.perf_counter()
            error, raw, parsed = None, None, None
            try:
                raw = monitor._raw(im)
                parsed = monitor._count(raw)  # exactly the deployed permissive parser
                prediction = "HUMAN" if parsed >= 1 else "OBJECT"
            except Exception as exc:
                prediction, error = "ERROR", str(exc)
            row = {"id": f["id"], "run": f["run"], "truth": labels[f["id"]],
                   "prediction": prediction, "parsed_count": parsed,
                   "strict_count": strict_count(raw) if raw is not None else None,
                   "raw_text": raw, "error": error, "inference_s": time.perf_counter()-start}
            rows.append(row)
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    after = checkpoint_identity(identity["local_snapshot"], module.MODEL_ID)
    if after["file_manifest_sha256"] != identity["file_manifest_sha256"]:
        write_json(out / "INVALID_checkpoint_changed.json", {"reason": "Checkpoint files changed during evaluation; do not report these predictions as a frozen replay."})
        raise RuntimeError("Checkpoint files changed during evaluation")
    write_json(out / "summary.json", summarize(rows))
    print(out)


def self_test():
    assert wilson(0, 0) is None
    assert wilson(0, 10)[0] == 0
    assert .69 < wilson(10, 10)[0] < .73
    assert strict_count("Two.") == 2 and strict_count("I see two hands") is None
    sample = [{"run": "r1", "truth": "hand", "prediction": "HUMAN", "strict_count": 1, "inference_s": .2},
              {"run": "r2", "truth": "no_hand", "prediction": "OBJECT", "strict_count": 0, "inference_s": .3}]
    result = summarize(sample)
    assert result["human_recall"] == 1 and result["false_positive_rate"] == 0
    mixed = sample + [{"run": "r2", "truth": "hand", "prediction": "ERROR", "error": "synthetic exception", "inference_s": 0.01}]
    result = summarize(mixed)
    assert result["human_recall"] == .5 and result["errors_by_truth"] == {"hand": 1}
    assert result["inference_mean_s"] == .25
    assert environment_identity()["libraries"]["numpy"]
    print("Synthetic unit checks passed; no synthetic values are stored as empirical results.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--interval", type=float, default=2.)
    ev = sub.add_parser("evaluate")
    ev.add_argument("annotations", type=Path)
    ev.add_argument("--run-model", action="store_true")
    ev.add_argument("--model-snapshot", type=Path, help="Optional existing local checkpoint directory; never downloaded")
    sub.add_parser("render-ui", help="Refresh only the label page from the unchanged manifest")
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "prepare": prepare(args.interval)
    elif args.command == "evaluate": evaluate(args.annotations, args.run_model, args.model_snapshot)
    elif args.command == "render-ui": print(render_label_page())
    else: self_test()
