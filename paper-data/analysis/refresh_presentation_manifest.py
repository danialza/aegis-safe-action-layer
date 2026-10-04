"""Refresh presentation hashes without recomputing or changing trial results."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = ROOT / "analysis/analysis_manifest.json"
    manifest = json.loads(path.read_text())
    # Numerical products must remain byte-identical during a figure-only edit.
    for relative, digest in manifest["output_hashes"].items():
        if relative.startswith("analysis/"):
            assert sha(ROOT / relative) == digest, relative
    manifest["analysis_script_sha256"] = sha(ROOT / "analysis/build_hardware_figures.py")
    for asset in sorted((ROOT / "figures").iterdir()):
        if asset.suffix in {".pdf", ".png"}:
            manifest["output_hashes"][str(asset.relative_to(ROOT))] = sha(asset)
    manifest["presentation_sources"] = {
        str(p.relative_to(ROOT)): sha(p) for p in [
            ROOT / "analysis/build_workflow.py", ROOT / "analysis/build_setup_assets.py",
            ROOT / "analysis/setup_assets_manifest.json", ROOT / "analysis/setup_calibration_record.json",
        ]
    }
    manifest["presentation_revision"] = {
        "numerical_products_changed": False,
        "sensitivity_plot": "Palatino regular-weight serif type; distinct navy, burnt-orange and purple solid/dashed/dotted curves with circle/square/triangle method markers; method key and explanatory notes moved outside image into manuscript caption; neutral conditional-onset band and grey dashed reporting reference; all six 101-point curves unchanged.",
        "primary_plot": "Four stacked monochrome point panels for moving-decision evidence age, command-estimated separation, carry-to-delivery time, and older-evidence fraction; normal and slow cadence groups side by side; circle/square/triangle distinguish methods, filled means and open individual runs, horizontal jitter only; Palatino serif type, no bars, grids, or connecting lines.",
        "restored_context": "Corrected four-stage workflow with confirmed depth-only hold wording, historical apparatus photo, raw primary-camera frame, and current calibration geometry.",
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Presentation hashes refreshed; numerical products unchanged.")


if __name__ == "__main__":
    main()
