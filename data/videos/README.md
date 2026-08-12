# Video supplement

Nineteen clips, about 21 minutes. **Every clip is a real run on the physical Niryo NED3 Pro.**
Nothing is simulated and nothing is re-enacted.

The files are attached to the [v1.0 release](../../releases/tag/v1.0) rather than tracked in
git. Clips whose source recording ends in `_paths` carry a live overlay: blue is the nominal
straight carry, orange the current re-plan, green the executed path, and the red circle is the
sensed hazard drawn at the radius the policy is enforcing at that instant. Clips 03, 06 and 08
were recorded without the overlay.

## Timebase

The recorder tags every file 12 fps but sustains about 11.6. Clips 18 and 19 are re-timed so
that player time equals the robot's own clock — 11.607 fps with a 0.51 s start offset, and
11.622 fps with 0.64 s — both fitted against the clock the recorder burns into each frame.
Extracting frames from the other clips at the tagged rate places them roughly 4% late.

## Index

| # | Clip | Length | What it shows |
|---|---|---|---|
| 00 | Workspace stills | — | The rig photographed and drawn to scale, plus the calibration result. Also in `figures/`. |
| 01 | Nine-point calibration | 1:58 | The arm walks a marker to nine known positions; the image-to-table homography is fitted from those correspondences. |
| 02 | Wide calibration, raised camera | 0:50 | The same procedure over a larger area, used for the long carries. |
| 03 | Baseline clear carry | 0:21 | The task with nothing in the way. Every later clip interrupts this motion. |
| 04 | Verdict OBJECT → route around | 0:50 | An inert box on the carry line. The layer commits to a detour and delivers. |
| 05 | Verdict HUMAN → freeze | 0:52 | The same scene with a hand instead. The arm stops, then resumes on withdrawal. |
| 06 | Moving obstacle | 1:04 | The obstacle is pushed along the path during the carry; the layer re-plans continuously and holds when no route exists. |
| 07 | RGB-D depth confirmation | 1:34 | The colour channel proposes the hazard; the detour is committed once depth independently agrees. |
| 08 | Object and hand in one carry | 1:38 | Both hazard types inside a single transport. |
| 09 | Multi-obstacle fail-safe hold | 1:10 | Several intruders at once; the layer holds rather than squeezing through. |
| 10 | Destination blocked, then resumed | 1:15 | Release is withheld until repeated frames prove the goal clear. |
| 11 | Baseline: worst-case policy | 1:42 | Always assuming a person. The arm does not move while a hazard is tracked. |
| 12 | Baseline: trust-latest, the breach | 1:04 | Trusting the latest verdict at face value; the tool enters the detected footprint. |
| 13 | Baseline: trust-latest, clean run | 0:56 | The same policy on a run where no hand entered, for contrast. |
| 14 | AEGIS: the radius breathing | 1:06 | The hold radius expanding as the verdict ages and collapsing on a fresh one. |
| 15 | Repeat: freeze then route | 1:01 | Repeatability of the paired behaviour. |
| 16 | Repeat: freeze then route | 0:53 | Second repeat. |
| 17 | Thirty autonomous carries | ~15:00 | Folder of 30 clips, one per carry, no human intervention. |
| 18 | One carry, both verdicts | 1:42 | **Source of Figure 5.** Six human windows and six re-routes inside a single uninterrupted carry. |
| 19 | RGB-D: the moment depth agrees | 0:57 | **Source of Figure 6.** The fusion state changing from colour-only to colour-and-depth. |

## Source recordings

| # | Original recording |
|---|---|
| 01 | `00_calibration` |
| 02 | `wide_calibration_25pt` |
| 03 | `01_baseline` |
| 04 | `03_static_obstacle_paths` |
| 05 | `05_hand_freeze_paths` |
| 06 | `04c_moving_central` |
| 07 | `rgbd_live_20260722_150347_paths` |
| 08 | `rgbd_obstacle_hand_20260722_151705` |
| 09 | `multi_live_20260722_01_paths` |
| 10 | `goal_block_20260722_135942` |
| 11 | `S1_worst_2_paths` |
| 12 | `S1_trust_2_paths` |
| 13 | `S1_trust_6_paths` |
| 14 | `S1_clasp_2_paths` |
| 15 | `trustlatest_toA_1_paths` |
| 16 | `trustlatest_toA_2_paths` |
| 17 | `loop_000`–`loop_029` |
| 18 | `rgbd_obstacle_hand_20260722_151705_paths` (re-timed) |
| 19 | `rgbd_flexible_20260722_151226_paths` (re-timed) |

Per-tick logs for the runs behind clips 04, 05, 07, 11–16, 18 and 19 are in
`../hardware_runs/`; `../../RUN_MANIFEST.md` maps each to its calibration and parameters.
