"""Redraw the threshold-sensitivity figure with the general onset band 0.555-0.587 s.

After any OBJECT verdict the stored anchor satisfies h <= 1 - eta = 0.05, so the score-hold onset
lies between tau_H(0.05) = 0.5545 s and T_inf = 0.5865 s. The original figure shaded only the
0.566-0.587 s band (first and repeated OBJECT updates from the prior). Curves and data are unchanged:
the original plotting function is reused with only the band limits and the output folder changed.
"""
import json, types
from pathlib import Path
HERE = Path(__file__).resolve().parent
for base in (HERE.parent.parent / "analysis", HERE.parents[1] / "10_hardware_manuscript_2026-09-24/analysis"):
    if (base / "build_hardware_figures.py").exists():
        SRC = base
        break
OUT = (HERE.parent.parent / "figures") if (HERE.parent.parent / "data").exists() else HERE.parent / "source/figures"
code = (SRC / "build_hardware_figures.py").read_text()
old = "for h in (.0325, 0)]"
assert code.count(old) == 1
code = code.replace(old, "for h in (.05, 0)]")
mod = types.ModuleType("bhf"); mod.__file__ = str(SRC / "build_hardware_figures.py")
exec(compile(code, mod.__file__, "exec"), mod.__dict__)
mod.FIGURES = OUT
summary = json.loads((SRC / "hardware_summary.json").read_text())
mod.plot_sensitivity(summary["threshold_sensitivity"][0]["thresholds_s"], summary["threshold_sensitivity"])
print("written:", OUT / "evidence_age_threshold_sensitivity.pdf")
