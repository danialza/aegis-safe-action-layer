"""Local, blinded cross-model audit. Automatic references are NOT human truth.

Leaves the historical data, human-labelling workflow and manuscript untouched.
Run init once, then reference, then monitor, then semantic_auto_report.py.
Only init reads run names; the reference worker receives hash IDs and images.
Model weights must already exist locally. No uploads, robot imports or downloads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from semantic_frame_audit import (ROOT, DEST, checkpoint_identity,
                                  environment_identity, sha, strict_count)

MODEL_ID = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
REFERENCE_REVISION = "46d4cf06a06ffc1a766c214174f9cbed2f45bcab"
MONITOR = ROOT / "provenance_code/safebench/fastvlm_monitor.py"
PROMPT = """Inspect this single photograph for a visible human hand or fingers.
A hand wearing a glove counts as a human hand. Robot arms, robot grippers,
objects, empty gloves, and an isolated forearm with no visible hand do not count.
Do not infer a hidden hand just because an arm or an object is present.
Classify only what is visibly supported. Reply with exactly ONE code:
N = no visible human hand or fingers.
U = cannot determine whether any human hand or fingers are visible.
B0 = visible bare hand; at least one hand is fully visible.
B1 = visible bare hand; every visible hand is partly hidden or cut off by the image edge.
G0 = visible worn glove; at least one gloved hand is fully visible.
G1 = visible worn glove; every visible gloved hand is partly hidden or cut off by the image edge.
H0 = visible hand but covering is mixed or unclear; at least one hand is fully visible.
H1 = visible hand but covering is mixed or unclear; every visible hand is partly hidden or cut off.
A glove covering skin is not by itself an occlusion: partial means physically
hidden behind something or cropped by the image boundary. Reply only the code."""


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_reference(raw):
    code = raw.strip()
    base = dict(code=code, presence="uncertain", cover=None, visibility=None)
    if code == "N":
        return dict(base, presence="no_hand")
    if code == "U":
        return base
    if code in {"B0", "B1", "G0", "G1", "H0", "H1"}:
        return dict(base, presence="hand", cover={"B": "bare", "G": "glove", "H": "unspecified"}[code[0]],
                    visibility="full" if code[1] == "0" else "partial")
    return dict(base, code="INVALID", presence="error")


def monitor_module():
    expected = {r["sha256"] for r in read(ROOT / "provenance_code/metadata/snapshot_manifest.json")["verified_code_configuration_files"]
                if r["archive_path"].endswith("safebench/fastvlm_monitor.py")}
    require(expected == {sha(MONITOR)}, "Archived monitor code changed")
    spec = importlib.util.spec_from_file_location("auto_audit_frozen_monitor", MONITOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def init_run(reference_snapshot, monitor_snapshot):
    source = read(DEST / "manifest.json")
    require(len(source["frames"]) > 0, "Empty manifest")
    frames, mapping = [], []
    ids = set()
    for row in source["frames"]:
        require(row["id"] not in ids, "Duplicate frame ID")
        ids.add(row["id"])
        image = (DEST / row["image"]).resolve(strict=True)
        require(image.is_relative_to(DEST.resolve()), "Image outside source audit")
        require(sha(image) == row["sha256"], "Image changed: " + row["id"])
        frames.append({"id": row["id"], "image": str(image), "sha256": row["sha256"]})
        mapping.append(dict(row))
    reference = checkpoint_identity(reference_snapshot, MODEL_ID)
    require(reference["cache_revision"] == REFERENCE_REVISION, "Unexpected reference revision")
    module = monitor_module()
    monitor = checkpoint_identity(monitor_snapshot, module.MODEL_ID)
    require(reference["file_manifest_sha256"] != monitor["file_manifest_sha256"], "Self-reference prohibited")
    base = ROOT / "semantic_auto_audit"
    base.mkdir(exist_ok=True)
    out = base / ("run_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(exist_ok=False)
    save(out / "blind_frames.json", {"frames": frames}, True)
    save(out / "frame_mapping.json", mapping, True)
    save(out / "reference_checkpoint.json", reference, True)
    save(out / "monitor_checkpoint.json", monitor, True)
    spec = {"created_utc": now(), "label_source": "model", "total_frames": len(frames),
            "source_manifest_sha256": sha(DEST / "manifest.json"),
            "human_ui_sha256": sha(DEST / "label_frames.html"),
            "blind_manifest_sha256": sha(out / "blind_frames.json"),
            "mapping_sha256": sha(out / "frame_mapping.json"),
            "runner_sha256": sha(__file__), "helper_sha256": sha(ROOT / "analysis/semantic_frame_audit.py"),
            "frozen_monitor_sha256": sha(MONITOR), "environment": environment_identity(),
            "reference_checkpoint_record_sha256": sha(out / "reference_checkpoint.json"),
            "monitor_checkpoint_record_sha256": sha(out / "monitor_checkpoint.json"),
            "reference": {"model_id": MODEL_ID, "revision": REFERENCE_REVISION, "prompt": PROMPT,
                          "image_max_dimension": 448, "max_tokens": 8, "batch_size": 8,
                          "greedy_sampling": True, "parser": "strict exact code; invalid is error, not absence"},
            "monitor": {"model_id": module.MODEL_ID, "prompt": module.COUNT_Q,
                        "image_max_dimension": 256, "max_tokens": 6, "temperature": 0,
                        "parser": "archived permissive count parser, unchanged"},
            "scope": "Automatic cross-model agreement on same-session lossy video frames. No verified human truth, live error rate, independent-session generalization or physical-safety inference.",
            "reference_blinding": "Image pixels and opaque hash IDs only; no method, run name, log, label or FastVLM output given to reference model.",
            "historical_weights_verified": False, "robot_connection": False,
            "network_during_inference": False}
    save(out / "spec.json", spec, True)
    save(out / "progress.json", {"stage": "initialized", "total": len(frames), "utc": now()})
    print(out, flush=True)


@contextmanager
def lock(out):
    with (out / ".worker.lock").open("a") as file:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)


def validate_run(out):
    spec = read(out / "spec.json")
    for path, expected in ((Path(__file__), spec["runner_sha256"]),
                           (ROOT / "analysis/semantic_frame_audit.py", spec["helper_sha256"]),
                           (MONITOR, spec["frozen_monitor_sha256"]),
                           (DEST / "manifest.json", spec["source_manifest_sha256"]),
                           (out / "blind_frames.json", spec["blind_manifest_sha256"]),
                           (out / "frame_mapping.json", spec["mapping_sha256"])):
        require(sha(path) == expected, "Frozen asset changed: " + str(path))
    require(spec["environment"] == environment_identity(), "Runtime environment changed")
    frames = read(out / "blind_frames.json")["frames"]
    require(len(frames) == spec["total_frames"], "Frame count changed")
    require(len({f["id"] for f in frames}) == len(frames), "Duplicate frames")
    for frame in frames:
        require(set(frame) == {"id", "image", "sha256"}, "Reference input must remain blind")
        require(sha(frame["image"]) == frame["sha256"], "Source image changed")
    return spec, frames


def verify_checkpoint(out, role, spec):
    record = out / f"{role}_checkpoint.json"
    require(sha(record) == spec[f"{role}_checkpoint_record_sha256"], "Checkpoint record changed")
    identity = read(record)
    current = checkpoint_identity(identity["local_snapshot"], identity["model_id"])
    require(current["file_manifest_sha256"] == identity["file_manifest_sha256"], "Checkpoint files changed")
    return identity


def completed_rows(path, frames, spec_sha):
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    require(len(rows) <= len(frames), "Too many saved rows")
    require([r["id"] for r in rows] == [f["id"] for f in frames[:len(rows)]], "Saved rows are not the frozen ordered prefix")
    for row, frame in zip(rows, frames):
        require(row["spec_sha256"] == spec_sha and row["image_sha256"] == frame["sha256"], "Saved row provenance mismatch")
    return rows


def seal_check(out, role, spec_sha):
    seal = read(out / f"{role}.sealed.json")
    require(seal["spec_sha256"] == spec_sha, "Wrong sealed specification")
    require(seal["predictions_sha256"] == sha(out / f"{role}.jsonl"), "Sealed predictions changed")
    return seal


def worker(out, role, limit=None):
    out = out.resolve(strict=True)
    with lock(out):
        spec, frames = validate_run(out)
        spec_sha = sha(out / "spec.json")
        if (out / f"{role}.sealed.json").exists():
            seal_check(out, role, spec_sha)
            print(f"{role}: already complete and sealed", flush=True)
            return
        if role == "monitor":
            seal = seal_check(out, "reference", spec_sha)
            require(seal["rows"] == len(frames), "Reference must finish before comparison")
        identity = verify_checkpoint(out, role, spec)
        rows = completed_rows(out / f"{role}.jsonl", frames, spec_sha)
        start_index = len(rows)
        if start_index == len(frames):
            # Recover safely if the previous process ended after its final row,
            # before writing the completion seal. Never rerun completed images.
            save(out / f"{role}.sealed.json", {"spec_sha256": spec_sha, "rows": len(frames),
                 "predictions_sha256": sha(out / f"{role}.jsonl"), "completed_utc": now()}, True)
            print(f"{role}: complete prefix verified and sealed", flush=True)
            return
        stop_index = min(len(frames), start_index + limit) if limit is not None else len(frames)
        require(stop_index > start_index, "No new frames requested")
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
            os.environ[key] = "1"
        from PIL import Image
        if role == "reference":
            from mlx_vlm import load
            from mlx_vlm.generate import batch_generate
            model, processor = load(identity["local_snapshot"], trust_remote_code=False)
            batch_size = spec["reference"]["batch_size"]
        else:
            module = monitor_module()
            monitor = module.FastVLMMonitor(model_id=identity["local_snapshot"], imgpx=256, max_tokens=6)
            batch_size = 1
        phase_start = time.perf_counter()
        with (out / f"{role}.jsonl").open("a", buffering=1) as output:
            for offset in range(start_index, stop_index, batch_size):
                batch = frames[offset:min(offset+batch_size, stop_index)]
                images = [Image.open(f["image"]).convert("RGB") for f in batch]
                tick = time.perf_counter()
                if role == "reference":
                    for im in images:
                        im.thumbnail((448, 448))
                    # Library applies the chat template separately to each image.
                    # There is no cross-image conversation and no controller context.
                    result = batch_generate(model, processor, images=images,
                                            prompts=[spec["reference"]["prompt"]] * len(batch),
                                            max_tokens=8, verbose=False, greedy_sampling=True)
                    require(len(result.texts) == len(batch), "Wrong batch response count")
                    elapsed = time.perf_counter() - tick
                    predictions = [dict(parse_reference(raw), raw_text=raw,
                                        error=None if parse_reference(raw)["code"] != "INVALID" else "noncanonical response",
                                        inference_s=elapsed/len(batch), batch_wall_s=elapsed,
                                        batch_size=len(batch), label_source="model") for raw in result.texts]
                else:
                    error, raw, count = None, None, None
                    try:
                        raw = monitor._raw(images[0])
                        count = monitor._count(raw)
                        prediction = "HUMAN" if count >= 1 else "OBJECT"
                    except Exception as exc:
                        error, prediction = str(exc), "ERROR"
                    predictions = [dict(prediction=prediction, raw_text=raw, parsed_count=count,
                                        strict_count=strict_count(raw) if raw is not None else None,
                                        error=error, inference_s=time.perf_counter()-tick,
                                        label_source="model")]
                for frame, pred in zip(batch, predictions):
                    row = dict(id=frame["id"], image_sha256=frame["sha256"], spec_sha256=spec_sha,
                               generated_utc=now(), **pred)
                    output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                done = offset + len(batch)
                if done % 32 == 0 or done == stop_index:
                    progress = dict(stage=role, completed=done, total=len(frames), utc=now(),
                                    elapsed_this_process_s=time.perf_counter()-phase_start)
                    save(out / "progress.json", progress)
                    print(json.dumps(progress), flush=True)
        verify_checkpoint(out, role, spec)
        if stop_index == len(frames):
            save(out / f"{role}.sealed.json", {"spec_sha256": spec_sha, "rows": len(frames),
                 "predictions_sha256": sha(out / f"{role}.jsonl"), "completed_utc": now()}, True)
            print(f"{role}: complete and sealed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--reference-snapshot", type=Path, required=True)
    init.add_argument("--monitor-snapshot", type=Path, required=True)
    for phase in ("reference", "monitor"):
        p = sub.add_parser(phase)
        p.add_argument("run_dir", type=Path)
        p.add_argument("--limit", type=int)
    all_phases = sub.add_parser("run", help="Resume reference, replay monitor, then make final report in separate processes")
    all_phases.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        init_run(args.reference_snapshot, args.monitor_snapshot)
    elif args.command == "run":
        for phase in ("reference", "monitor"):
            subprocess.run([sys.executable, __file__, phase, str(args.run_dir)], check=True)
        subprocess.run([sys.executable, str(ROOT / "analysis/semantic_auto_report.py"), str(args.run_dir)], check=True)
        save(args.run_dir / "progress.json", {"stage": "complete", "utc": now(),
             "total": read(args.run_dir / "spec.json")["total_frames"],
             "scope": "Cross-model agreement only; not human-verified diagnostic accuracy."})
    else:
        require(args.limit is None or args.limit > 0, "Limit must be positive")
        worker(args.run_dir, args.command, args.limit)


if __name__ == "__main__":
    main()
