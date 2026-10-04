# Paper data — Evidence Age Versus Spatial Margin in Vision–Language-Gated Robotic Transport

Data and analysis code for the hardware study submitted to *Sensors* (MDPI). Everything here comes from
one physical campaign on a Niryo NED3 Pro with a fixed Intel RealSense D435i and an on-device
FastVLM-0.5B hand monitor, recorded on 18 September 2026. The earlier simulation and July hardware
material elsewhere in this repository is not part of this paper's evidence.

## Contents

| Folder | What it holds |
|---|---|
| `data/` | 184 unmodified JSON/JSONL files for the 92 eligible transports: `timed_margin_compare` (24-run primary campaign), `timed_compare_slow` (8-run pilot), `timed_compare` (59 exploratory), `aegis_time` (1 initial pilot). Each run has a decision log and a frame-linked timing sidecar. |
| `analysis/` | Offline analysis scripts, full-precision results, calibration inputs, exclusion reasons and source hashes. `analysis/revision_2026-10-04/` adds the exact permutation tests and the duty-cycle analysis. |
| `figures/` | Figures generated from the run-level results. |
| `semantic_audit/` | The 2158 frames extracted for the monitor audit, with manifest and hashes. |
| `semantic_auto_audit/` | Frozen FastVLM and Qwen2.5-VL replay outputs (model outputs, not labels). |
| `semantic_human_review/` | Both human-review exports (426 frames, 115 rechecks) and the merged review. |

Raw and annotated videos are indexed by path and hash in the run records and are available from the
corresponding author on request. Model checkpoints are available from their original repositories.

## Regenerating the results

Python 3.11+ with NumPy, OpenCV and Matplotlib. The scripts read only these files and do not import
robot-control code.

```bash
cd analysis/revision_2026-10-04
python exact_permutation.py      # Table 3 and Supplementary Section S19
python duty_cycle.py             # Equation 10 comparison, Supplementary Section S18
python build_supp_tables.py
python build_primary_figure_legend.py   # Figure 3
python build_sensitivity_figure.py      # Figure 4 (onset band 0.555-0.587 s)
python buffer_rationale.py              # median AEGIS margin behind the 32 mm Trust32 buffer (S2)
```

The remaining tables and figures are produced by the scripts in `analysis/` and
`analysis/offline_review_2026-10-03/`; each writes a manifest with the SHA-256 of every input.

## Terms that matter

- **Age** is measured from a capture proxy (frame receipt on the robot-side server, mapped to the
  laptop clock), not from sensor exposure. Filenames containing `sensor-time` are historical identifiers.
- **Separation** is command-estimated: the distance from the controller's internal command state to the
  detected obstacle edge. It is not an independently measured physical clearance.
- **Moving** means a non-stop software decision, not measured robot velocity.

Licensed under CC BY 4.0, as stated in the repository `LICENSE`.
