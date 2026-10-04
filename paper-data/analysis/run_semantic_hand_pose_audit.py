#!/usr/bin/env python3
"""Run the optional local Apple Vision diagnostic on the entire frame inventory.

This reports detector outputs only: no ground-truth labels or accuracy metrics.
Original frames, manifest and human annotations remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new_json(path: Path, content: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(content, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    original = ROOT / "semantic_audit/manifest.json"
    source = ROOT / "analysis/semantic_hand_pose.swift"
    binary = ROOT / "semantic_auto_audit/bin/semantic_hand_pose"
    original_bytes = original.read_bytes()
    inventory = json.loads(original_bytes)
    rows = [
        {
            "id": row["id"],
            "image": str((original.parent / row["image"]).resolve()),
            "sha256": row["sha256"],
        }
        for row in inventory["frames"]
    ]
    assert len(rows) == 2158, "Inventory changed; review before re-running this frozen audit"
    assert len({row["id"] for row in rows}) == len(rows)
    now = datetime.now(timezone.utc)
    destination = ROOT / "semantic_auto_audit" / f"apple_vision_all_{now:%Y%m%dT%H%M%S_%fZ}"
    destination.mkdir(parents=False, exist_ok=False)
    blind = destination / "blind_manifest.json"
    output = destination / "hand_pose_all.jsonl"
    save_new_json(blind, {"frames": rows})
    provenance = {
        "started_at_utc": now.isoformat(),
        "source_manifest": str(original),
        "source_manifest_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "blind_manifest_sha256": sha256(blind),
        "helper_source": str(source),
        "helper_source_sha256": sha256(source),
        "binary": str(binary),
        "binary_sha256": sha256(binary),
        "orchestrator_source_sha256": sha256(Path(__file__)),
        "frame_count": len(rows),
        "selection": "All frames in the frozen original manifest, in original order; no semantic selection",
        "label_source": "automated_detector",
        "interpretation": "Supplemental detector output only. no_detection is NOT no_hand. Not reference ground truth or accuracy validation.",
    }
    save_new_json(destination / "provenance.json", provenance)
    print(f"OUTPUT_DIRECTORY={destination}", flush=True)
    started = time.monotonic()
    with (destination / "stdout.txt").open("x") as stdout, (destination / "stderr.txt").open("x") as stderr:
        result = subprocess.run([str(binary), str(blind), str(output)], stdout=stdout, stderr=stderr, check=False)
    records = [json.loads(line) for line in output.read_text().splitlines()] if output.exists() else []
    frame_rows = [row for row in records if row.get("record_type") == "frame"]
    statuses = Counter(row["status"] for row in frame_rows)
    expected_ids = [row["id"] for row in rows]
    produced_ids = [row["id"] for row in frame_rows]
    complete = expected_ids == produced_ids
    summary = {
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_wall_s": time.monotonic() - started,
        "exit_code": result.returncode,
        "expected_frames": len(rows),
        "processed_frames": len(frame_rows),
        "complete_original_order": complete,
        "status_counts": {status: statuses[status] for status in ("detection", "no_detection", "partial_error", "error")},
        "total_returned_hand_observations": sum(row.get("num_detections") or 0 for row in frame_rows),
        "label_source": "automated_detector",
        "interpretation": "These are detector-output counts, not true hand prevalence, recall, precision or accuracy. no_detection is NOT no_hand.",
        "outputs_sha256": sha256(output) if output.exists() else None,
        "detector_metadata": next((row for row in records if row.get("record_type") == "metadata"), None),
        "detector_summary": next((row for row in records if row.get("record_type") == "summary"), None),
    }
    save_new_json(destination / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return result.returncode if complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
