# Claims → Code → Result (verification manifest)

Every quantitative claim in `paper/safebench.tex` mapped to the code that produces it and
the result file that backs it. **Status** legend:

- ✅ **re-verified 2026-07-23** — code re-run this session, reproduced the paper value.
- 📁 **prior sim campaign** — produced by the original evaluation runs (logs in main-repo
  `results/`); not re-run this session; code present in `simulation/`.
- 🔧 **hardware capture** — recorded on the physical NED3 Pro (2026-07-16..22); not
  offline-reproducible; evidence in `results/hardware_live|calibration|vlm/`.

---

## A. Geometric CMDP safe-action projection layer

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:methods`, `tab:cmdp` | 8 forward-kinematics-coupled constraints, closest admissible command, e-stop on empty set | `simulation/cmdp_wrapper.py` | — (mechanism) | 📁 |
| `sec:results`, `fig:cc_per_safety`, `fig:frontier` | unsafe cost ↓ **3×–29×**, success unchanged (Wilcoxon p<1e-16) | `simulation/run_eval.py`, `run_matrix.py`, `metrics.py`, `policies.py` | main-repo `results/` | 📁 |
| abstract, `sec:results` | **0** tool–obstacle collisions over **>230** hand-avoidance episodes (rule-of-three) | `simulation/run_matrix.py`, `cmdp_wrapper.py`, `metrics.py` | main-repo `results/` | 📁 |
| abstract, safe-exploration | exploring policy **0%** collision-episodes vs unshielded up to **46%** | `simulation/run_matrix.py`, `policies.py`, `cmdp_wrapper.py` | main-repo `results/` | 📁 |

## B. Reactive shortest-path detour (tangent–arc–tangent)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:detour` (eqs. segdisc…guard) | taut-string detour around a disc + route-or-stop guard | `hardware/reactive_exec.py` (offline sim), `reactive_run.py` (hardware) | — (derivation) | — |
| `sec:realrobot` reactive suite | **100%** reached, **100%** zero-contact, react **0.15 s**, min-move 1.7–2.9 cm (5 scenarios × 100 seeds) | `hardware/reactive_exec.py` — `suite 100` | `results/sim/reactive_sim_suite.json` | ✅ |

## C. CLASP — confidence- and latency-aware safety projection (the new mechanism)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:clasp`, `tab:clasp` | static delivered **0 / 100 / 99.6%** (worstcase / trust-latest / CLASP) | `hardware/clasp.py` | `results/sim/clasp_compare.json` → `sudden_static.reached` = 0.0 / 1.0 / 0.996 | ✅ |
| `sec:clasp`, `tab:clasp` | hand reach-in collision-free **100 / 88 / 100%** | `hardware/clasp.py` | `clasp_compare.json` → `human_reach.zero_collision` = 1.0 / 0.88 / 1.0 | ✅ |
| `sec:clasp` | CLASP is the **only** policy simultaneously safe ∧ live | `hardware/clasp.py` | above two rows jointly | ✅ |
| eqs. belief/msem/rhoeff | belief p(τ)=p̂+(P0−p̂)(1−e^{−τ/T_dec}); margin scales d_mech…R_human+β_epi | `hardware/clasp.py` | — (implements eqs.) | ✅ |

## D. Camera intruder detection + RGB-D fusion

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:detection` | workspace-gated bg-diff detector: green-exclude, reject top-connected (arm), world-XY gate, 8 mm inflation | `hardware/reactive_run.py` (`detect_ws`) | `results/hardware_live/03_static_obstacle.json` | 🔧 |
| `sec:detection`, `fig:rr_rgbd` | colour homography + metric depth confirmation (depth-only ⇒ stop-only over 3 frames) | `hardware/reactive_run.py`, `rs_stream.py`, `rpi_rs_server.py` | rgbd live logs | 🔧 |

## E. Semantic VLM monitor (hosted + on-device)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:vlm_real`, `tab:vlm` | Gemma-3-12B hosted: **100%** (20/20), 10/10 recall, 0/10 false-stop, **1.6 s** / 4.1 s p95 | `hardware/vlm_monitor.py`, `vlm_eval.py`, `real_vlm.py` | `results/vlm/SUMMARY.md` | 🔧 |
| `tab:vlmbackends` | Haiku 4.5: 90% (18/20), 2/10 false-stop, 2.7 s | `hardware/vlm_monitor.py` | `results/vlm/SUMMARY.md` | 🔧 |
| abstract, `sec:vlm_real`, `tab:vlmbackends` | **on-device FastVLM-0.5B: 0.24 s** / 0.25 s p95, 100% (20/20), 10/10 recall, 0/10 false-stop | `hardware/fastvlm_monitor.py` | `results/vlm/mlx-community_FastVLM-0.5B-bf16_256.json`, `SUMMARY.md` | 🔧 |
| `tab:vlmbackends` | SmolVLM-256M worse (5%, 0.66 s) — smaller ≠ faster | `hardware/fastvlm_monitor.py` | `results/vlm/mlx-community_SmolVLM-256M-Instruct-4bit_512.json` | 🔧 |

## F. Homography calibration & grasp

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| abstract, `sec:realrobot`, `fig:perception` | 9-point image→robot homography, mean **0.92 mm** / max 1.45 mm residual | `hardware/surface_calibrate.py`, `table_cam.py` | `results/calibration/residual_report.json` (`mean_residual_m`=9.23e-4) | 🔧 |
| `sec:realrobot` | raised-camera 25-point fit **1.18 mm** mean inlier residual | `hardware/wide_surface_calibrate.py` | `expriment codex 22 jul/…/WIDE_CALIBRATION.md` | 🔧 |
| `sec:realrobot` | grasp repeatability **1.8 mm** | `hardware/reactive_run.py`, `real_pick_place.py` | `results/hardware_live/01_baseline.json` | 🔧 |
| session floor | commanded z never below **0.1214 m** (user-set table surface) | enforced in `hardware/reactive_run.py`, `run_loop.py` | `results/calibration/cal_session_0722.json` (`floor_z`) | 🔧 |

## G. Real-robot route-vs-freeze (same policy, verdict decides)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:realrobot`, `fig:rr_contrast`, `tab:realrobot` | object verdict ⇒ **route** 3.6 cm detour, 4.0 cm min clearance, delivered | `hardware/reactive_run.py` | `results/hardware_live/03_static_obstacle.json` | 🔧 |
| `sec:realrobot`, `fig:rr_contrast`, `tab:realrobot` | human verdict ⇒ **freeze** 0.0 mm for ≈35 s, resume, deliver | `hardware/reactive_run.py` | `results/hardware_live/05_hand_freeze.json` | 🔧 |
| `sec:realrobot` | live moving obstacle ⇒ continuous re-plan (6.9 cm hazard move, 69 route ticks) | `hardware/reactive_run.py` | `results/hardware_live/04c_moving_central.json` | 🔧 |
| abstract | **30/30** autonomous carries | `hardware/run_loop.py`, `run_wide_loop.py` | `expriment codex 22 jul/` loop index + wide_runs | 🔧 |

## H. Latency budget (measured on hardware)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `sec:latency`, `tab:latency` | hand→freeze **1.73 s** mean / 2.67 s worst; geometric T_react≈**0.44 s** (actuation-bound) | `hardware/profile_latency.py`, `reactive_run.py` | `results/hardware_live/ssm_hazard_persistent_metrics.json` | 🔧 |
| `sec:latency` | v_max = (Δr − d_step)/T_react derives which layer intercepts which hazard class | `hardware/reactive_exec.py`, `clasp.py` | derivation + measured T_react | 🔧 |

## I. Policy comparison (remains in simulation)

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| abstract, `tab:varied` | varied-height: ACT (self-imitation) **93.3%** vs sampling-replanner **46.7%**, both 0-collision | `simulation/place_act.py`, `place_act_tf.py`, `train_bc.py`, `planner.py`, `dynamic_obstacle.py` | main-repo `results/` | 📁 |
| `sec:results` | fixed-height sudden-obstacle: both policies **≥95%** collision-free | `simulation/dynamic_obstacle.py`, `planner.py`, `place_act.py` | main-repo `results/` | 📁 |
| `tab:place` | per-step RL fails: SAC **0%**, TD3+BC **2.5%** | `simulation/place_rl.py`, `td3bc.py` | main-repo `results/` | 📁 |
| `sec:results` | feasibility oracle attributes residual to imitation gap, not geometry | `simulation/place_paper_eval.py` | main-repo `results/` | 📁 |
| limitation (i-b) | ACT sim-only (8 Hz vs 25 Hz); teach-and-fine-tune infra implemented, not exercised on hw | `simulation/act_teach.py`, `hardware/act_teach.py`, `real_act.py` | — (infra) | 📁 |

## J. Baselines & sim-as-pre-screen

| Paper | Claim | Code | Result | Status |
|---|---|---|---|---|
| `tab:baseline` | CBF baseline: ours **100%** vs CBF **83%** (both 0-collision) | `simulation/cbf_baseline.py`, `cmdp_wrapper.py` | main-repo `results/` | 📁 |
| `sec:results`, ΔSafety/AUC | per-constraint detectors scored by AUC for predicting unsafe events on domain-randomised surrogate | `simulation/delta_safety.py`, `detector_baseline.py`, `domain_random.py` | main-repo `results/` | 📁 |

---

## Summary of verification state

- **New-code claims (CLASP, reactive layer) → re-run and reproduced this session** (✅).
  These are the two claims that did not exist in the original campaign, so they were the
  ones that needed a fresh simulation check. Both matched the paper.
- **One honest correction made:** `tab:clasp` CLASP static delivered was `100%`; the
  250-seed re-run gives **99.6%** (249/250). The paper now reads 99.6%.
- **Older sim claims** (CMDP cost, ACT vs planner, RL, CBF, pre-screen) are unchanged and
  backed by the original campaign logs; code is in `simulation/`.
- **Hardware claims** are recorded evidence, not offline-reproducible.
- No paper number was found to contradict its backing result file after these checks.
