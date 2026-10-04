"""Offline, source-preserving manuscript packaging. Never import robot code.

Run `python analysis/package_revision.py` to refresh verified provenance copies
and build both ZIPs, or pass --snapshot-only to stop before ZIP generation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

PACKAGE = Path(__file__).resolve().parent.parent
ORIGINAL_ROOT = PACKAGE.parent.parent / "vlm-codex"
SOURCE_ZIP = Path("/Users/danial/Downloads/Danial___Safety_Awareness_Robot.zip")
PROVENANCE = PACKAGE / "provenance_code"
META = PROVENANCE / "metadata"
OUTPUT = PACKAGE / "output"
SECRET_ASSIGNMENT = re.compile(r'''(?im)^\s*(?:password|passwd|api_key|access_token|secret)\s*=\s*["'][^"']+''')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def safe_relative(text):
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Not a safe package-relative path: {text}")
    return path


def copy_verified(source, relative, expected, scope):
    relative = safe_relative(relative)
    target = PROVENANCE / relative
    if source.exists() and sha(source) == expected:
        candidate = source
    elif target.exists() and sha(target) == expected:
        candidate = target
    else:
        raise ValueError(f"No exact historical hash match for {relative}")
    if candidate.suffix in {".py", ".sh", ".json"}:
        if SECRET_ASSIGNMENT.search(candidate.read_text(errors="replace")):
            raise ValueError(f"Possible credential assignment; manual review required: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if candidate.resolve() != target.resolve():
        shutil.copy2(candidate, target)
    assert sha(target) == expected
    return {"archive_path": str(target.relative_to(PACKAGE)), "original_path": str(source),
            "sha256": expected, "verification": scope, "bytes": target.stat().st_size}


def snapshot():
    META.mkdir(parents=True, exist_ok=True)
    logs = sorted((PACKAGE / "data/timed_margin_compare/logs").glob("*.json"))
    assert len(logs) == 24
    records = [(p.stem, json.loads(p.read_text())) for p in logs]
    expected = defaultdict(set)
    for name, record in records:
        for path, value in record["provenance"]["files_sha256"].items():
            expected[path].add(value)
    reference_keys = set(records[0][1]["provenance"]["files_sha256"])
    assert all(set(d["provenance"]["files_sha256"]) == reference_keys for _, d in records)
    assert all(len(values) == 1 and None not in values for values in expected.values())
    files = []
    for path, values in sorted(expected.items()):
        relative = safe_relative(path)
        files.append(copy_verified(ORIGINAL_ROOT / relative, str(relative), next(iter(values)),
                                   "Matches the recorded files_sha256 in all 24 primary transport logs"))
    session = ORIGINAL_ROOT / "experiments/session_2026-09-18"
    campaign = session / "timed_margin_compare"
    protocols = []
    protocol_hashes = {"launcher_sha256": set(), "wrapper_sha256": set()}
    for name, _ in records:
        source = campaign / "runs" / name / "protocol.json"
        target = META / "primary_protocols" / f"{name}.json"
        candidate = source if source.exists() else target
        if not candidate.exists():
            raise ValueError(f"Primary launcher protocol missing: {name}")
        protocol = json.loads(candidate.read_text())
        assert protocol["run"] == name
        for key in protocol_hashes:
            protocol_hashes[key].add(protocol[key])
        if candidate.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
        protocols.append({"run": name, "original_path": str(source),
                          "archive_path": str(target.relative_to(PACKAGE)), "sha256": sha(target)})
    for basename, key in (("launcher.py", "launcher_sha256"), ("run.sh", "wrapper_sha256")):
        assert len(protocol_hashes[key]) == 1
        files.append(copy_verified(campaign / basename,
                                   f"experiments/session_2026-09-18/timed_margin_compare/{basename}",
                                   next(iter(protocol_hashes[key])),
                                   f"Matches {key} in the separate protocol.json records for all 24 primary runs"))
    # The mask path and description were recorded, but its historical content
    # hash was not. This explicitly distinct current contextual snapshot must
    # not be represented as retrospectively verified run-time bytes.
    masks = {d["provenance"]["settings"]["arm_mask"] for _, d in records}
    assert len(masks) == 1
    source_mask = Path(next(iter(masks)))
    target_mask = PROVENANCE / "context_unverified/arm_mask.npz"
    candidate = source_mask if source_mask.exists() else target_mask
    if not candidate.exists():
        raise ValueError("Referenced arm-mask contextual file unavailable")
    target_mask.parent.mkdir(parents=True, exist_ok=True)
    if candidate.resolve() != target_mask.resolve():
        shutil.copy2(candidate, target_mask)
    mask = {"original_path": str(source_mask), "archive_path": str(target_mask.relative_to(PACKAGE)),
            "sha256_now": sha(target_mask), "bytes": target_mask.stat().st_size,
            "verification": "Current contextual copy only: the primary logs record this path and mask description, not a historical content hash",
            "historical_content_hash_verified": False,
            "recorded_description": records[0][1]["arm_mask"]}
    origin_file = META / "source_zip_origin.json"
    if SOURCE_ZIP.exists():
        origin = {"original_path": str(SOURCE_ZIP), "filename": SOURCE_ZIP.name,
                  "sha256": sha(SOURCE_ZIP), "bytes": SOURCE_ZIP.stat().st_size,
                  "included_in_revision_archives": False,
                  "role": "User-supplied manuscript source; original unchanged; old manuscript and legacy evidence not included in revision archives"}
        write_json(origin_file, origin)
    else:
        origin = json.loads(origin_file.read_text())
    manifest = {"scope": "Read-only archival audit reference, not a standalone runnable controller or robot deployment package",
                "primary_run_count": 24, "verified_code_configuration_files": files,
                "verified_code_configuration_file_count": len(files), "launcher_protocol_records": protocols,
                "current_context_not_historically_hash_verified": [mask], "source_zip_origin": origin,
                "robot_or_model_code_executed": False,
                "warning": "Do not execute archived controller/launcher files; hardware dependencies and safety validation are not supplied by this snapshot."}
    write_json(META / "snapshot_manifest.json", manifest)
    return manifest


def archive_bytes(path, members, origin, purpose):
    assert members and all(not name.startswith("/") and ".." not in Path(name).parts for name in members)
    manifest = {"purpose": purpose, "source_zip_origin": origin,
                "payload_file_count": len(members), "archive_file_count_including_this_manifest": len(members) + 1,
                "payload_bytes": sum(len(data) for data in members.values()),
                "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in sorted(members.items())},
                "manifest_note": "This manifest is excluded from its own hash list; ZIP digest is recorded externally in output/package_manifest.json."}
    prefix = "AEGIS_hardware_revision/" if purpose == "full hardware revision" else ""
    members = dict(members)
    members[prefix + "PACKAGE_MANIFEST.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == manifest["archive_file_count_including_this_manifest"]
        for name, entry in manifest["files"].items():
            assert digest(z.read(name)) == entry["sha256"]
    return {"path": str(path.relative_to(PACKAGE)), "sha256": sha(path), "zip_bytes": path.stat().st_size,
            "payload_file_count": manifest["payload_file_count"], "archive_file_count": len(members),
            "uncompressed_payload_bytes": manifest["payload_bytes"], "crc_and_all_payload_hashes_verified": True}


def build_archives(provenance):
    OUTPUT.mkdir(exist_ok=True)
    required = [PACKAGE / "output/pdf/main.pdf", PACKAGE / "output/pdf/supplementary.pdf",
                PACKAGE / "manuscript/main.tex", PACKAGE / "manuscript/supplementary.tex", PACKAGE / "README_FA.md"]
    assert all(p.is_file() for p in required)
    allowed_roots = {"manuscript", "figures", "data", "analysis", "review", "provenance_code",
                     "semantic_audit", "semantic_auto_audit", "semantic_human_review"}
    excluded_suffixes = {".aux", ".log", ".out", ".pyc", ".zip", ".synctex", ".fls", ".fdb_latexmk"}
    payload = {}
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(PACKAGE)
        # Include the frozen replay supporting the paper, not unrelated smoke
        # tests, native executables, or earlier alternative auto-audits.
        if relative.parts[0] == "semantic_auto_audit" and (
            len(relative.parts) < 2 or relative.parts[1] not in {"run_20260924_203640", "README_FA.md"}
        ):
            continue
        if relative.parts[0] not in allowed_roots and str(relative) not in {"README_FA.md", "output/pdf/main.pdf", "output/pdf/supplementary.pdf"}:
            continue
        if any(part.startswith(".") or part in {"__pycache__", "tmp", "source_received"} for part in relative.parts):
            continue
        if path.suffix in excluded_suffixes or path.name.startswith("qa_"):
            continue
        payload["AEGIS_hardware_revision/" + str(relative)] = path.read_bytes()
    full = archive_bytes(OUTPUT / "AEGIS_hardware_revision.zip", payload, provenance["source_zip_origin"], "full hardware revision")
    source_payload = {}
    for name in ("main.tex", "supplementary.tex"):
        raw = (PACKAGE / "manuscript" / name).read_text()
        transformed = raw.replace("../figures", "figures").replace("../analysis", "analysis")
        source_payload[name] = transformed.encode()
    for directory in (PACKAGE / "manuscript/Definitions", PACKAGE / "figures"):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix not in excluded_suffixes and not path.name.startswith("qa_"):
                source_payload[str(path.relative_to(directory.parent))] = path.read_bytes()
    # Include every referenced TeX analysis fragment, including audited
    # bibliography and new supplementary tables, in the portable source ZIP.
    for path in sorted((PACKAGE / "analysis").rglob("*.tex")):
        relative = path.relative_to(PACKAGE)
        if any(part.startswith(".") or part in {"__pycache__", "tmp"} for part in relative.parts):
            continue
        source_payload[str(relative)] = path.read_bytes()
    source_payload["README_SOURCE.md"] = (PROVENANCE / "README_SOURCE_ZIP.md").read_bytes()
    source_payload["SOURCE_ZIP_ORIGIN.json"] = (META / "source_zip_origin.json").read_bytes()
    latex = archive_bytes(OUTPUT / "AEGIS_LaTeX_source.zip", source_payload, provenance["source_zip_origin"], "portable LaTeX source")
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "builder": "analysis/package_revision.py", "builder_sha256": sha(Path(__file__)),
              "source_zip_origin": provenance["source_zip_origin"], "archives": [full, latex],
              "exclusions": ["source_received", "tmp", "qa PNGs", "compiler auxiliary/log/out files", "all videos", "model weight files", "unrelated alternative-auto-audit smoke tests/binaries", "ZIP files themselves"],
              "LaTeX_archive_only_transformations": ["../figures -> figures", "../analysis -> analysis"],
              "original_manuscript_files_edited_by_builder": False,
              "instruction": "Re-run this builder after any final manuscript, PDF, table or figure update."}
    write_json(OUTPUT / "package_manifest.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-only", action="store_true")
    args = parser.parse_args()
    provenance = snapshot()
    if args.snapshot_only:
        print(json.dumps({"verified_code_configuration_files": len(provenance["verified_code_configuration_files"]),
                          "protocol_records": len(provenance["launcher_protocol_records"]),
                          "unverified_context_files": 1, "zip_created": False}, indent=2))
    else:
        print(json.dumps(build_archives(provenance), indent=2))


if __name__ == "__main__":
    main()
