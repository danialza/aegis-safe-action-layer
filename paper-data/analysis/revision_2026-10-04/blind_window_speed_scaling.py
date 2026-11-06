"""Scale the measured semantic blind windows to a higher tool speed (arithmetic, not a measurement).

The semantic blind window (semantic_blind_window.py, Supplementary Section S23) gives, for each
policy-cadence cell, the mean moving time on pre-change semantic evidence. The runs moved at
commanded tool speeds of 15-27 mm/s. This script multiplies the cell mean blind moving times
(scope: robot moving with a detected hazard) by an example speed of 250 mm/s to show the travel the
same durations would correspond to at that speed. It assumes that the blind durations would not
change with speed and that motion during them is at the stated speed. Neither assumption was tested;
no run was made at 250 mm/s.
"""
import json, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
SPEED_MM_S = 250.0

src = HERE / "semantic_blind_window_results.json"
cells = json.loads(src.read_text())["cells"]
out = {"note": __doc__, "example_speed_mm_s": SPEED_MM_S, "scope": "moving_with_hazard", "cells": {}}
for name, cell in cells.items():
    c = cell["moving_with_hazard"]
    out["cells"][name] = {"measured_mean_s": c["mean_s"],
                          "measured_mean_mm": c["mean_mm"],
                          "travel_at_example_speed_mm": c["mean_s"] * SPEED_MM_S}
out["sources_sha256"] = {src.name: hashlib.sha256(src.read_bytes()).hexdigest()}
(HERE / "blind_window_speed_scaling_results.json").write_text(json.dumps(out, indent=2) + "\n")
for name, c in out["cells"].items():
    print(f"{name}: {c['measured_mean_s']:.3f} s -> {c['travel_at_example_speed_mm']:.1f} mm at {SPEED_MM_S:.0f} mm/s")
