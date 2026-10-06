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

## Checking and regenerating the results

Python 3.11 or later with NumPy, OpenCV and Matplotlib. No script imports robot-control code.

**1. Check the download.** `python verify_release.py` compares every file with `RELEASE_MANIFEST.json`.

**2. Regenerate.** Run from `analysis/`, in this order. This sequence was tested in an independent copy of
this folder: every table fragment and figure PNG was reproduced byte for byte, figure PDFs differed
only in their embedded creation date, and all numerical results were identical.

```bash
cd analysis
python build_hardware_figures.py                       # hardware_summary.json, Tables S4-S5
python exploratory_patterns_2026-10-02/pattern_audit.py  # run-level audit (pattern_results.json)
python offline_review_2026-10-03/stage_age_audit.py      # Table 4, Tables S14-S15
python offline_review_2026-10-03/shadow_timeout.py       # timeout assay, Section 6.6, Table S17
python offline_review_2026-10-03/proxy_sensitivity.py    # clock-offset sensitivity, Table S18
python build_additional_analyses.py                      # Tables S3, S6, S7, S8
python build_motion_freshness_tables.py                  # Table 2, Tables S9 and S13, Figure S2
python first_detection_audit.py                          # geometry-refresh audit, Table S10
python build_semantic_paper.py                           # human-reviewed replay, Tables 5, S11-S12
python build_workflow.py                                 # Figure 1
python build_setup_assets.py                             # Figure S1 (Figure 2 images are copied files)
cd revision_2026-10-04
python exact_permutation.py      # Table 3, Table S21
python duty_cycle.py             # Equation 10, Table S19
python duty_cycle_holdout.py     # hold-out check, Table S20
python robustness_checks.py      # Table S22
python buffer_rationale.py       # 32 mm buffer rationale, Section S2
python age_reuse_model.py        # L + P/2 sweep account, Table S16
python parser_replay_check.py    # permissive-parser use in the replay, Section S13
python anchor_check.py           # post-HUMAN anchors and onsets, Section S16
python build_supp_tables.py
python build_primary_figure_legend.py   # Figure 3 (supersedes the earlier unlabelled version)
python build_sensitivity_figure.py      # Figure 4 (onset band 0.555-0.587 s)
```

Run the two figure scripts in `revision_2026-10-04/` last: earlier scripts also write Figures 3 and 4
in their previous style.

**What is not public.** The controller source code is not public; `provenance_code/` holds the session
calibration record and the controller constants with the SHA-256 of the archived source files. These
match the hashes recorded in all 24 primary and 8 pilot run logs, and the timeout assay rechecks them
for its 12 AEGIS runs; one exploratory log records a different variant-file hash and the initial pilot
records none (Supplementary Section S11). Raw and annotated videos and model
checkpoints are not included, so the photographs and camera frame in Figure 2, the qualitative video
fields of `first_detection_audit.json`, and the model replays in `semantic_auto_audit/` are provided as
recorded outputs rather than regenerated.

**Package-internal scripts.** `check_manuscript.py`, `check_portable_source.py`, `check_remedy8.py`,
`package_revision.py`, `refresh_presentation_manifest.py`, `test_*.py`, and the frame-extraction,
model-replay and annotation-interface scripts (`semantic_frame_audit.py`, `semantic_auto_audit.py`,
`run_semantic_hand_pose_audit.py`, `semantic_human_*.py`) refer to the authors' working folders, raw
media, model checkpoints or earlier outputs. They are kept for provenance and are not expected to run
from this release; `verify_artifacts.py` does run and passes.

## Terms that matter

- **Age** is measured from a capture proxy (frame receipt on the robot-side server, mapped to the
  laptop clock), not from sensor exposure. Filenames containing `sensor-time` are historical identifiers.
- **Separation** is command-estimated: the distance from the controller's internal command state to the
  detected obstacle edge. It is not an independently measured physical clearance.
- **Moving** means a non-stop software decision, not measured robot velocity.

Licensed under CC BY 4.0, as stated in the repository `LICENSE`.
