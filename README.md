# AEGIS — Age-Aware, Evidence-Guarded Safe-Action Layer

Companion data and media for the manuscript

> **AEGIS: An Age-Aware, Evidence-Guarded Safe-Action Layer Fusing RGB-D Sensing with
> Vision–Language Monitoring for Collision-Aware Robotic Manipulation**
> Danial Zafaranchizadeh Moghaddam, Maryam Banitalebi Dehkordi, Hamed Rahimi Nohooji, Abolfazl Zaraki

A semantic verdict is stale the moment after it is emitted. AEGIS makes the robot's hold
radius an explicit function of a vision–language belief **and of the age of the verdict that
produced it**, so the margin widens on its own as the evidence goes stale and collapses again
on a fresh one. It runs on a low-cost Niryo NED3 Pro from a single fixed RealSense D435i.

## What is in this repository

| Path | Contents |
|---|---|
| `figures/` | Every figure in the paper, plus the graphical abstract and workspace photos |
| `results/logs/` | Per-control-tick logs for every physical run: tool pose, sensed hazard, verdict, belief, enforced radius, clearance |
| `results/calibration/` | Homography calibration reports with their residuals, per session |
| `results/vlm/` | On-device vision–language benchmark, per-frame latency and verdict |
| `results/simulation/` | Per-episode simulation records (success, cumulative cost, cost rate, violations) |
| `RUN_MANIFEST.md` | Every reported physical number traced to its run ID, calibration, parameters and outcome |
| `NARRATION.md` | Shot-by-shot description of the video supplement, with times read from the control logs |
| `CLAIMS_TO_CODE.md` | Each paper claim mapped to the code that produces it |

**Videos** are attached to the [latest release](../../releases/latest) rather than tracked in
git: 19 clips, ~21 minutes, every one a real run on the physical arm.

## Headline results

| | Result |
|---|---|
| Cost reduction, sampling-based planner | per-step cost rate **0.138 → 0.0086** (16×), Wilcoxon *p* = 1×10⁻⁶, *n* = 36 paired episodes |
| Task success, same comparison | **65% → 92%** (exact McNemar, *p* = 0.007) |
| Physical AEGIS runs | minimum moving clearance **+19.7 mm**, never negative |
| Physical trust-latest baseline | one run entered the detected footprint at **−5.6 mm** |
| Physical worst-case baseline | never commanded motion while a hazard was tracked |
| On-device semantic verdict | FastVLM-0.5B, **0.236 s** mean, 0.238 s p95 over 20 timed queries |
| Image-to-table calibration | 0.92 mm mean fitting residual over nine points (22 July session) |

Every one of these traces to a file in `results/` — see `RUN_MANIFEST.md`.

## How to read a run log

```python
import json
d = json.load(open("results/logs/S1_clasp_2.json"))
d["clasp_params"]          # policy and its constants
d["events"]                # narrated transitions with timestamps
d["log"][0]                # one control tick
# {'t':…, 'tool':[x,y], 'mode':'route', 'state':'carry', 'haz':[x,y,r],
#  'vlm':'object', 'clr':…, 'clasp_p':…, 'clasp_R':…, 'sensor':'rgbd', …}
```

`clr` is the tool-to-detected-footprint distance. **Clearance is reported over ticks on which
the policy commands motion**; including protective holds turns some runs momentarily negative
because the operator advanced the obstacle onto a stationary tool, which is not an incursion
the policy commanded.

## Video timebases

The recorder tags every file 12 fps but sustains ≈11.6. Two clips are re-timed so that player
time equals the robot's clock: the Figure 5 source at 11.607 fps with a 0.51 s start offset,
the Figure 6 source at 11.622 fps with 0.64 s. Extracting frames at the tagged rate places
every frame about 4% late. Constants were fitted against the clock the recorder burns into
each frame.

## Implementation

The safe-action layer, the sensing pipeline and the hardware bridge are kept in a private
repository. They are available to researchers on request — please email the corresponding
author. This repository carries the data, media and provenance needed to check every reported
result.

## Licence

Figures, videos, logs and documentation: **CC BY 4.0**. Please cite the paper if you use them.

## Citation

A BibTeX entry will be added here once the article is published.
