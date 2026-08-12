# Physical-run manifest

Generated from the run logs, not transcribed. Every physical number in the paper traces to a
row here. Regenerate with the snippet at the bottom.

Common to the whole 30 July AEGIS session: fixed Intel RealSense D435i, eye-to-hand;
calibration `clasp_hardware/calibration/calibration.json` (8-point free-standing-slab
homography, mean 2.36 mm, max 3.82 mm, one 11.9 mm outlier rejected); detector = colour
difference with workspace gating, depth fusion enabled; semantic backend = FastVLM-0.5B-bf16
via MLX 0.32.0 / mlx-vlm 0.6.5 on Apple M4 Pro; guard = per-step centre-distance test against
rho_eff + r_hold with r_hold 0.07 m moving / 0.035 m stationary; control rate ~7.9 Hz.

`clearance (moving)` is the minimum tool-to-detected-footprint distance over ticks on which
the policy commanded motion; `clearance (all)` includes protective holds, during which the
operator could advance the obstacle onto a stationary tool. The paper reports the moving
figure.

## 30 July AEGIS session

| Run | Policy | R_human/d_mech/beta_epi (m) | Outcome | Ticks | Clearance all (mm) | Clearance moving (mm) | Used in |
|---|---|---|---|---|---|---|---|
| `S1_clasp_1` | clasp | 0.06/0.012/0.012 | delivered | 143 | +59.1 | +61.1 | Table 8 |
| `S1_clasp_2` | clasp | 0.06/0.012/0.012 | delivered | 166 | +18.6 | +19.7 | Figure 7 |
| `S1_clasp_3` | clasp | 0.06/0.012/0.012 | goal_occupied | 1200 | +49.9 | +64.7 | Table 8 |
| `S1_trust_1` | trustlatest | 0.06/0.012/0.012 | delivered | 16 | -- | never moved | Table 8 |
| `S1_trust_2` | trustlatest | 0.06/0.012/0.012 | delivered | 146 | -6.7 | -5.6 | Figure 8 |
| `S1_trust_3` | trustlatest | 0.06/0.012/0.012 | delivered | 110 | -3.7 | +19.8 | Table 8 |
| `S1_trust_4` | trustlatest | 0.06/0.012/0.012 | delivered | 164 | -3.3 | +45.3 | Table 8 |
| `S1_trust_5` | trustlatest | 0.06/0.012/0.012 | delivered | 67 | +6.6 | +90.3 | Table 8 |
| `S1_trust_6` | trustlatest | 0.06/0.012/0.012 | delivered | 57 | +49.3 | +49.3 | Table 8 |
| `S1_trust_7` | trustlatest | 0.06/0.012/0.012 | delivered | 78 | +12.3 | +12.8 | Table 8 |
| `S1_worst_1` | (unset) | --/--/-- | delivered | 43 | +1.4 | never moved | Table 8 |
| `S1_worst_2` | worstcase | 0.06/0.012/0.012 | delivered | 465 | -1.1 | never moved | Table 8 |
| `S1_worst_3` | worstcase | 0.06/0.012/0.012 | no_route | 1200 | -6.2 | never moved | Table 8 |

**Excluded from the analysed set (11 of 13):** `S1_trust_1` — no intruder was detected at any
tick, so the policy was never exercised; `S1_worst_1` — executed with no policy configured
(`clasp_params` absent).

## 22 July trials (Figures 5, 6 and Table 7)

Calibration `2026-07-22_live/calibration/residual_report.json`, 9 points, mean 0.92 mm,
max 1.46 mm.

| Run | Used in | Notes |
|---|---|---|
| `rgbd_obstacle_hand_20260722_151705` | **Figure 5**, clip 18 | one carry, verdict alternated; 6 HUMAN windows, 131 ticks, 16.0 s, 0.0 mm commanded motion; min clearance +5.9 cm |
| `rgbd_flexible_20260722_151226` | **Figure 6**, clip 19 | depth confirmation at t = 25.0 s and 43.8 s; min clearance +2.9 cm |
| `03_static_obstacle` | Table 7 | OBJECT verdict, 3.6 cm detour, 4.0 cm min clearance |
| `05_hand_freeze` | Table 7 | HUMAN verdict, 127 consecutive ticks (16.1 s) at 0.0 mm |

Video timebases are not the tagged 12 fps. Figure 5's source runs at 11.607 fps with a 0.51 s
start offset, Figure 6's at 11.622 fps with 0.64 s; both were fitted against the clock the
recorder burns into each frame. Extracting at the tag places every frame ~4% late.

## Regenerating this table

```python
import json, glob
for f in sorted(glob.glob("vlm-codex/experiments/clasp_hardware/logs/S1_*.json")):
    d = json.load(open(f)); L = d["log"]
    mv = [x["clr"] for x in L if x.get("clr") is not None and x.get("mode") not in (None, "stop")]
    print(f, d.get("clasp_params"), d["result"]["termination_reason"],
          min(mv) * 1000 if mv else "never moved")
```
