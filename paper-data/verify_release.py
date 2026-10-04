"""Check every file of this release against RELEASE_MANIFEST.json (SHA-256).

Run from the paper-data folder of a fresh download:  python verify_release.py
Rerunning the analysis scripts rewrites outputs; regenerated figure PDFs then differ only in their
embedded creation date, so compare numbers and tables, not hashes, after a rerun.
"""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / "RELEASE_MANIFEST.json").read_text())
missing, changed = [], []
for rel, digest in manifest["files"].items():
    p = HERE / rel
    if not p.exists():
        missing.append(rel)
    elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        changed.append(rel)
print(f"{len(manifest['files'])} files listed; {len(missing)} missing; {len(changed)} changed")
for rel in (missing + changed)[:20]:
    print("  ", rel)
sys.exit(1 if missing or changed else 0)
