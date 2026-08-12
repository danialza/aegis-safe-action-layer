# Data

Everything a reader needs to check a number in the paper without running the robot.

```
data/
├── hardware_runs/     per-control-tick logs, one JSON per physical run
├── calibration/       image-to-table homography fits and their residuals
├── vlm_benchmark/     on-device vision-language monitor, per-frame verdict and latency
├── simulation/        per-episode records from the MuJoCo campaign
└── videos/            index of the video supplement (files live in the release)
```

## `hardware_runs/`

One file per run. `S1_*` are the 30 July policy-comparison session; the remaining files are the
22 July object-versus-hand and RGB-D trials.

```python
import json
d = json.load(open("data/hardware_runs/S1_clasp_2.json"))
d["clasp_params"]   # {'mode': 'clasp', 'r_human': 0.06, 'd_mech': 0.012, 'epi': 0.012}
d["result"]         # termination reason, pick/place success flags
d["events"]         # narrated state transitions with timestamps
d["log"][0]         # one control tick, ~7.9 Hz
```

Per-tick fields:

| Field | Meaning |
|---|---|
| `t` | seconds since the run started |
| `tool` | grasp-site position in the robot base frame, metres |
| `mode` | `full`, `route`, `route_slow` or `stop` |
| `state` | `carry`, `route`, `hold_obj`, `hold_human`, `hold_goal` |
| `haz` | sensed intruder as `[x, y, radius]`, or `null` |
| `vlm` | latest semantic verdict, `object` or `human` |
| `clasp_p` | belief that the intruder is human, after ageing |
| `clasp_R` | enforced hold radius, metres |
| `clr` | tool-to-detected-footprint distance, metres |
| `sensor` | `rgb`, `depth`, `rgbd` (both channels matched) or `none` |
| `depth_delta_m` | depth-to-colour agreement distance when both matched |

**Clearance is reported over ticks on which the policy commands motion.** Including protective
holds turns some runs momentarily negative, because the operator advanced the obstacle onto a
stationary tool; that is not an incursion the policy commanded.

## `calibration/`

`residual_report.json` and `surface_calibration.json` are the 22 July nine-point fits used for
the object-versus-hand trials. `clasp_hardware_calibration.json` is the eight-point
free-standing-slab fit actually loaded by the 30 July policy comparison. All residuals are
**fitting** residuals on the correspondences used to solve the homography; no held-out set was
collected.

## `vlm_benchmark/`

FastVLM-0.5B and a smaller candidate over the same twenty frames, at two input resolutions.
Each `rows` entry carries the true label, the predicted label, the raw model reply and the
per-query time. That twenty-frame set was also used to choose the prompt and the model, so it
is a development set: its accuracy is an upper bound, its latency is not affected.

## `simulation/`

`episodes.csv` is one row per episode — policy, safety layer on or off, success, length,
cumulative cost, cost rate, geometric violation count. `results.csv` is the aggregate per
condition. These back the 16× cost-rate reduction and the 65% → 92% success figures.

## `videos/`

The clips themselves are attached to the [v1.0 release](../../releases/tag/v1.0); see
`videos/README.md` for what each one shows.
