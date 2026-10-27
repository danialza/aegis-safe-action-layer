"""Checks added in response to the pre-submission audit of 11 October 2026.

All quantities are recomputed from the frozen decision logs, timing sidecars and the timeout-comparison
decision ledger; no input file is modified and no model output is used as a label.

1. Stale permissions: moving decisions issued while a frame that later returned a HUMAN verdict had
   already been captured (capture proxy before the decision) but its verdict was still pending
   (inference end after the decision). Frames the monitor never processed are not covered, so the
   count is a lower bound on motion permitted on evidence that a pending verdict would have revoked.
   Counts are also given per policy and cadence cell, with their moving-decision denominators.
2. HUMAN verdicts among completed inferences, per policy, over the whole run and over the decision
   period (first to last carry decision).
3. Score-hold episodes: maximal runs of consecutive carry decisions whose stop reason is the score
   hold (belief>=P_STOP).
4. Stored anchors on the eligible timeout-comparison decisions, reconstructed from the logged score and
   age as h = P0 + (p - P0) exp(tau / T_d), and the number of decisions whose age lay between their
   anchor-specific hold onset and the limiting timeout; repeated without the decisions held by the
   geometric pre-command check.
5. Separation minus margin at hazard-present moving decisions, and the number of such decisions.
6. Hazard rows at the detector's 100 mm radius clamp, by state and stop reason; for destination holds, the runs and
   the distance from the logged hazard centre to the goal; for the other rows, the runs and their position in the carry.
7. Block timing within each pass of the primary campaign (minutes from a method's normal-cadence
   block to its slow-cadence block).
8. Sensitivity of the limiting timeout T_inf to the prior P0 (and its proportionality to T_d).
9. Commanded tool speed while moving: command-state distance advanced over the intervals that follow a
   moving decision, divided by their duration, per primary run.
"""
import collections, glob, json, math, os
from pathlib import Path
HERE = Path(__file__).resolve().parent
def _find(rel):
    for base in (HERE.parent.parent, HERE.parent / "paper-data"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)

P0, T_D, P_STOP = 0.65, 0.40, 0.50
T_INF = T_D * math.log(P0 / (P0 - P_STOP))
DATA = _find("data")
LEDGER = _find("analysis/offline_review_2026-10-03/shadow_timeout_decisions.jsonl")

def policy(name):
    if name.startswith("AEGIS"):
        return "AEGIS"
    return "Trust32" if name.startswith("Trust32") else "Trust12"

def runs(campaign):
    for f in sorted(glob.glob(str(DATA / campaign / "logs" / "*.json"))):
        name = os.path.basename(f)[:-5]
        log = json.loads(Path(f).read_text())
        side = [json.loads(l) for l in Path(f[:-5] + "_timing.jsonl").read_text().splitlines() if l.strip()]
        yield name, log, side

out = {"note": __doc__, "constants": {"P0": P0, "T_d_s": T_D, "P_stop": P_STOP, "T_inf_s": T_INF}}

stale = collections.Counter(); moving = collections.Counter(); stale_rows = []
stale_cell = collections.Counter(); moving_cell = collections.Counter()
human = collections.Counter(); completed = collections.Counter()
human_dp = collections.Counter(); completed_dp = collections.Counter(); human_runs = collections.Counter()
episodes = {}; sep_minus_margin = collections.defaultdict(list); hazard_moving = collections.Counter()
clamp_rows = collections.Counter(); clamp_runs = set(); block_start = {}
clamp_goal_runs = set(); clamp_goal_dist = []; clamp_carry_runs = set(); clamp_carry = []
for campaign in ("timed_margin_compare", "timed_compare_slow"):
    for name, d, side in runs(campaign):
        pol = policy(name); log = d["log"]
        verdicts = [r for r in side if r.get("type") == "vlm"]
        t_first, t_last = log[0]["t_decision"], log[-1]["t_decision"]
        hum = [v for v in verdicts if v["verdict"] == "human"]
        if campaign == "timed_margin_compare":
            completed[pol] += len(verdicts); human[pol] += len(hum); human_runs[pol] += bool(hum)
            inside = [v for v in verdicts if t_first <= v["t_infer_end"] <= t_last]
            completed_dp[pol] += len(inside); human_dp[pol] += sum(v["verdict"] == "human" for v in inside)
            header = json.loads(next(l for l in Path(str(DATA / campaign / "logs" / (name + "_timing.jsonl"))).read_text().splitlines()))
            block_start[name] = header["wall"]
        n_ep, prev = 0, False
        for i, e in enumerate(log):
            if e["mode"] != "stop":
                moving[(campaign, pol)] += 1
                cell = (campaign, pol, "slow" if "slow" in name else "normal"); moving_cell[cell] += 1
                for v in hum:
                    if v["t_capture"] < e["t_decision"] < v["t_infer_end"]:
                        stale[(campaign, pol)] += 1; stale_cell[cell] += 1
                        stale_rows.append({"run": name, "t_s": e["t"], "hazard_present": e["haz"] is not None})
                        break
                if campaign == "timed_margin_compare" and e["haz"] is not None and e.get("clr") is not None:
                    hazard_moving[pol] += 1
                    sep_minus_margin[pol].append((e["clr"] - e["margin"], name))
            held = e["mode"] == "stop" and (e.get("stop_reason") or "").startswith("belief")
            n_ep += held and not prev; prev = held
            if campaign == "timed_margin_compare" and e["haz"] is not None and abs(e["haz"][2] - 0.10) < 1e-9:
                clamp_runs.add(name); clamp_rows[f"{e['state']}|{e.get('stop_reason')}|moving={e['mode'] != 'stop'}"] += 1
                if e["state"] == "hold_goal":
                    clamp_goal_runs.add(name); clamp_goal_dist.append(math.hypot(e["haz"][0] - d["goal"][0], e["haz"][1] - d["goal"][1]))
                else:
                    clamp_carry_runs.add(name); clamp_carry.append((i, e["t_decision"] - t_first))
        episodes[name] = n_ep

out["stale_permissions"] = {"definition": "moving decision while a later-HUMAN frame was captured and its verdict pending",
                            "moving_decisions": {f"{c}|{p}": n for (c, p), n in moving.items()},
                            "count": {f"{c}|{p}": stale.get((c, p), 0) for (c, p) in moving},
                            "by_cell": {f"{c}|{p}|{r}": {"stale": stale_cell.get((c, p, r), 0), "moving": n}
                                        for (c, p, r), n in sorted(moving_cell.items())},
                            "total_moving": sum(moving.values()), "total_stale": sum(stale.values()), "rows": stale_rows}
out["human_verdicts_primary"] = {p: {"human": human[p], "completed": completed[p], "runs_with_human": human_runs[p],
                                     "human_in_decision_period": human_dp[p], "completed_in_decision_period": completed_dp[p]}
                                 for p in ("AEGIS", "Trust12", "Trust32")}
slow = {k: v for k, v in episodes.items() if k.startswith("AEGIS") and "slow" in k}
out["score_hold_episodes"] = {"per_run": episodes,
                              "primary_slow_AEGIS_range": [min(v for k, v in slow.items() if k.startswith("AEGIS-slow_")), max(v for k, v in slow.items() if k.startswith("AEGIS-slow_"))],
                              "pilot_slow_AEGIS_range": [min(v for k, v in slow.items() if "slowupdates" in k), max(v for k, v in slow.items() if "slowupdates" in k)],
                              "primary_normal_AEGIS_range": [min(v for k, v in episodes.items() if k.startswith("AEGIS-normal")), max(v for k, v in episodes.items() if k.startswith("AEGIS-normal"))],
                              "fixed_buffer_max": max(v for k, v in episodes.items() if k.startswith("Trust"))}

anchors = {}
rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
for campaign in ("timed_margin_compare", "timed_compare_slow"):
    el = [r for r in rows if r["campaign"] == campaign and r["comparisons"]["Trust12+timeout-analytic"]["eligible_object_hazard"]]
    rec = []; rec_ng = []
    for r in el:
        tau = max(0.0, r["age_used_s"]); h = P0 + (r["logged_score"] - P0) * math.exp(tau / T_D)
        onset = T_D * math.log((P0 - h) / (P0 - P_STOP)) if h < P_STOP else 0.0
        rec.append((h, onset, tau))
        if not (r["logged_mode"] == "stop" and r["logged_stop_reason"] == "geometry"):
            rec_ng.append((h, onset, tau))
    anchors[campaign + "|excluding_geometry_holds"] = {
        "eligible": len(rec_ng), "anchor_below_0.01": sum(h < 0.01 for h, _, _ in rec_ng),
        "anchor_0.01_to_0.5": sum(0.01 <= h < P_STOP for h, _, _ in rec_ng),
        "anchor_reset_to_prior": sum(h >= P_STOP for h, _, _ in rec_ng),
        "age_between_onset_and_T_inf": sum(h < P_STOP and o <= t < T_INF for h, o, t in rec_ng)}
    anchors[campaign] = {"eligible": len(rec), "anchor_below_0.01": sum(h < 0.01 for h, _, _ in rec),
                         "anchor_0.01_to_0.5": sum(0.01 <= h < P_STOP for h, _, _ in rec),
                         "anchor_reset_to_prior": sum(h >= P_STOP for h, _, _ in rec),
                         "max_onset_gap_below_0.01_ms": 1000 * max(T_INF - o for h, o, _ in rec if h < 0.01),
                         "age_between_onset_and_T_inf": sum(h < P_STOP and o <= t < T_INF for h, o, t in rec)}
out["anchors"] = anchors

out["separation_minus_margin_primary"] = {p: {"min_mm": 1000 * min(v)[0], "run": min(v)[1], "hazard_present_moving_decisions": hazard_moving[p]}
                                          for p, v in sep_minus_margin.items()}
out["radius_clamp_rows_primary"] = {"radius_m": 0.10, "rows": sum(clamp_rows.values()), "runs": len(clamp_runs), "by_state": dict(clamp_rows),
                                    "destination_holds": {"rows": len(clamp_goal_dist), "runs": sorted(clamp_goal_runs),
                                                          "hazard_centre_to_goal_mm": [1000 * min(clamp_goal_dist), 1000 * max(clamp_goal_dist)]},
                                    "other_rows": {"rows": len(clamp_carry), "runs": sorted(clamp_carry_runs),
                                                   "max_decision_index": max(i for i, _ in clamp_carry),
                                                   "max_s_after_first_decision": max(t for _, t in clamp_carry)}}

order = sorted(block_start, key=block_start.get)
gaps = {}
for p in ("AEGIS", "Trust12", "Trust32"):
    for rep in ("1", "2"):
        normal = min(block_start[f"{p}-normal_to{d}_{rep}"] for d in "AB")
        slow_ = min(block_start[f"{p}-slow_to{d}_{rep}"] for d in "AB")
        gaps[f"{p}|pass{rep}"] = (slow_ - normal) / 60
out["block_order_primary"] = {"run_order": order, "normal_to_slow_minutes": gaps}

out["T_inf_sensitivity_s"] = {"note": "T_inf = T_d ln(P0 / (P0 - P_stop)) at T_d = 0.40 s; proportional to T_d",
                              "by_P0": {f"{p0:.2f}": T_D * math.log(p0 / (p0 - P_STOP)) for p0 in (0.55, 0.60, 0.65, 0.70, 0.75)}}
speed = {}
for name, d, side in runs("timed_margin_compare"):
    L = d["log"]; dist = dur = 0.0
    for e0, e1 in zip(L, L[1:]):
        if e0["mode"] != "stop" and e1["t_decision"] > e0["t_decision"]:
            dist += math.dist(e0["tool"], e1["tool"]); dur += e1["t_decision"] - e0["t_decision"]
    speed[name] = 1000 * dist / dur
vals = sorted(speed.values())
out["commanded_tool_speed_mm_s"] = {"per_run": speed, "min": vals[0], "median": (vals[11] + vals[12]) / 2, "max": vals[-1]}
(HERE / "audit_checks_results.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps({k: v for k, v in out.items() if k not in ("note", "block_order_primary")}, indent=1)[:4000])
print(json.dumps(out["block_order_primary"]["normal_to_slow_minutes"], indent=1))
