# Hardware-only evidence and reproducibility

Run `python analysis/build_hardware_figures.py` from the manuscript package, using a Python environment with NumPy and Matplotlib. The original analysis used `/Users/danial/.ned3pro-venv/bin/python`. The builder reads the preserved inventory and source logs, verifies hashes, computes run-level summaries, and writes JSON, LaTeX table fragments, and PDF/PNG figures. It never commands a robot or changes a source log/video.

## Selection

- 96 capture-proxy run records screened.
- 92 logs with transport decisions retained: 24 primary runs, 8 slow-update pilot runs, 59 exploratory runs, and 1 initial timing pilot.
- One pickup failure and three already-near-destination/no-carry records are excluded from transport comparisons only. Their identities, results, original paths and hashes remain in `exclusions.json` and `inventory_source.json`. No original is deleted. This is not an end-to-end task-success-rate analysis.
- All 24 primary runs are included. No primary run is excluded based on unfavorable time, separation, or evidence-age outcomes.
- The 92 included JSON/JSONL pairs are byte-identical copies under `data/<campaign>/logs`. Videos are not copied or edited; original locations remain in the logs. The four excluded pairs are not copied into the analysis dataset.
- The script can regenerate plots from the package's local data. In a portable copy without the excluded originals it retains their archived inventory records and hashes, explicitly notes their unavailability, and does not claim to have re-read them.

## Metrics and estimand

The estimand is descriptive transport behavior conditional on successful pickup. All primary cell summaries weight the four runs equally, not in proportion to their decision counts. Means and observed ranges are not confidence intervals. The trials are not assumed to be independently randomized.

1. **Run-minimum command-estimated edge separation:** minimum logged `clr` over decisions with `mode != stop` and a detected hazard. The deployed code uses the internal planar command accumulator before issuing the next command: `distance(tool, hazard_center) - hazard_radius`. It does not measure actual TCP position, the swept path between decisions, physical obstacle ground truth, or whole-arm clearance. Runs without a hazard-bearing moving decision have this metric recorded as null, not zero; none of the 24 primary runs lack the metric.
2. **Carry-to-delivery time:** sidecar event `carrying` to `object delivered at goal`, including holds and final placement, but excluding pickup and the initial pause.
3. **Older-evidence motion:** fraction of non-stop decisions with capture-proxy evidence age strictly above an analysis threshold. Includes movement with no detected hazard. It is decision-weighted within each run, not time-weighted. A separate hazard-conditioned value is saved in JSON. The 0.6 s reference is not a validated safety boundary; the sensitivity figure varies it from 0.2 to 1.2 s.
4. **Rate:** normal has no imposed minimum VLM start period. Slow has a 0.8 s minimum start-to-start period; it is not an added 0.8 s inference latency.

Capture-proxy times do not validate exposure-to-camera-server latency. A logged delivery or zero human-verdict moving decisions does not establish physical collision safety, first-intrusion safety, monitor recall, or whole-arm clearance.

## Outputs

- `hardware_summary.json`: every included run, primary cell means/ranges/SD, and all threshold-sensitivity samples.
- `exclusions.json`: transparent accounting of four non-transport records.
- `analysis_manifest.json`: source, data-copy, builder and output hashes.
- `results_table.tex`: complete primary table with means and observed ranges (requires `booktabs`).
- `supplementary_table.tex`: complete table of all 24 individual primary runs (requires `booktabs`).
- `../figures/hardware_primary_comparison.{pdf,png}`: three stacked monochrome point panels, with normal and slow cadence side by side. Circles/squares/triangles identify methods; filled symbols and labels give means, while four open symbols show individual runs with horizontal jitter only. Palatino serif type is embedded in the figure PDF (STIXGeneral is an explicit portable fallback). No bars, grid lines, or connecting lines are drawn; only the left/bottom axes remain. All plotted values are unchanged.
- `../figures/evidence_age_threshold_sensitivity.{pdf,png}`: run-weighted age-threshold sensitivity, independently for each rate.

There is no use of legacy-clock trials, simulation, synthetic measurements, inferred unrecorded measurements, or altered experimental outcomes in these results.

## Human-reviewed semantic replay (25 September update)

`build_semantic_paper.py` verifies the frozen merged review and its source hashes, then regenerates `semantic_paper_results.json`, three semantic LaTeX tables, and `semantic_paper_manifest.json`. The 426-frame stratified human sample and 115-frame targeted recheck are separate from the 24-run hardware comparison. The resulting counts are 101 positive, 322 negative, and three unresolved labels, not a new prospective or independently blinded validation set. Frozen source exports, manifests, and per-case changes remain under `semantic_human_review/merged_2026-09-25_v1/`.

Run `python analysis/build_semantic_paper.py`, compile both manuscripts, and run `python analysis/check_manuscript.py` and `python analysis/verify_artifacts.py`. In `analysis`, run `python -m unittest test_semantic_paper test_semantic_human_merge test_semantic_human_review test_semantic_human_recheck test_semantic_auto_report test_semantic_auto_audit` and both `node test_semantic_human_ui.js` and `node test_semantic_label_ui.js`. Then package with `python analysis/package_revision.py`; validate the portable ZIP with `python analysis/check_portable_source.py`; repackage to include its validation report.

The finite-population upper bound is conditional on correct human labels and the recorded joint-negative sampling design, not a bound on live safety or annotation bias. No uncertain label is replaced with a model vote.

## Restored visual context

`build_workflow.py` redraws the original four-colour functional organization using the actual deployed equations and carry controller. `build_setup_assets.py` copies the original apparatus photograph without edits, extracts a documented raw primary-video frame without overlays, and plots the active September calibration correspondences. Their inputs and image hashes are in `setup_assets_manifest.json`. The photograph is historical context, not old-result evidence. The calibration diagram is a visualization of fitting inputs, not new ground-truth validation.

The setup builder additionally needs OpenCV. Its archived PNG/JSON inputs support portable regeneration when the original video and manuscript archive are absent. After regenerating presentation assets, run `refresh_presentation_manifest.py` to update hashes; it first requires the numerical analysis products to remain unchanged. Then run `verify_artifacts.py`, compile both manuscripts, run `check_manuscript.py`, and rebuild the ZIPs with `package_revision.py`.
