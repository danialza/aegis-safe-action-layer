"""Compare the detector's representative obstacle radius with the measured footprint of the obstruction.

The detector reports each hazard as an enclosing circle in the table plane. The smallest circle that
encloses a rectangular footprint of length a and width b has radius sqrt(a^2 + b^2) / 2. This script
compares that value, from the obstruction's dimensions measured after the campaign
(obstruction_dimensions.json), with the per-run representative radii of the 24 primary runs
(additional_analyses.json, geometry). It is a consistency check of the detection and image-to-table
mapping against one physical dimension, not a validation of clearance: the camera sees the object
obliquely, so side faces and perspective can enlarge the detected footprint.
"""
import json, math, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent

def _find(rel):
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)

dims_path = HERE / "obstruction_dimensions.json"
geo_path = _find("analysis/additional_analyses.json")
dims = json.loads(dims_path.read_text())["primary_and_pilot_obstruction"]
geo = json.loads(geo_path.read_text())["geometry"]["representative_radius_mm"]
r_enc = math.hypot(dims["footprint_length_mm"], dims["footprint_width_mm"]) / 2
out = {"note": __doc__,
       "footprint_mm": [dims["footprint_length_mm"], dims["footprint_width_mm"]],
       "enclosing_circle_radius_mm": r_enc,
       "detected_representative_radius_mm": geo,
       "detected_minus_enclosing_mm": {"min": geo["min"] - r_enc, "max": geo["max"] - r_enc, "mean": geo["mean"] - r_enc},
       "sources_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (dims_path, geo_path)}}
(HERE / "obstruction_footprint_check_results.json").write_text(json.dumps(out, indent=2) + "\n")
print(f"enclosing radius {r_enc:.2f} mm; detected {geo['min']:.2f}-{geo['max']:.2f} mm (mean {geo['mean']:.2f}); difference {geo['min']-r_enc:+.2f} to {geo['max']-r_enc:+.2f} mm")
