"""Hold-out check of the duty-cycle relation on AEGIS runs that were not used to formulate it.

The relation and its decision-sampling refinement were formulated on the 24-run primary campaign.
Here the identical per-run function (duty_cycle.analyse_run) is applied, unchanged and with no
fitted parameter, to the AEGIS runs of the separate slow-update pilot (minimum period 0.8 s) and of
the exploratory campaign (normal cadence). Runs with fewer than three evidence bundles or without
eligible hazard-present OBJECT intervals are counted and excluded.

Two sampled forms are reported. phi_s(own) uses each held-out run's own decision intervals, which are
realized behaviour of that run. phi_s(fixed) uses the primary-campaign mean intervals for the same
cadence, so the only inputs taken from a held-out run are its update period P and latency L; this is
the pre-specified conditional prediction. The half-interval terms assume that the onset crossing is
uniformly distributed within a decision interval and independent of decision timing.
"""
import glob, json, statistics as st
from pathlib import Path
import duty_cycle as dc

HERE = Path(__file__).resolve().parent
out = {"note": __doc__, "T_inf_s": dc.T_INF, "sets": {}}
for camp, rate in (("timed_compare_slow", "slow"), ("timed_compare", "normal")):
    logs = dc._find(f"data/{camp}/logs")
    runs, skipped = [], []
    for f in sorted(glob.glob(str(logs / "AEGIS*.json"))):
        r = dc.analyse_run(f, "AEGIS", rate)
        if r is None or r["observed_hold_fraction"] is None:
            skipped.append(Path(f).stem); continue
        runs.append(r)
    prim_runs = [r for r in json.loads((HERE / "duty_cycle_results.json").read_text())["runs"]
                 if r["method"] == "AEGIS" and r["rate"] == rate]
    dm_fix = st.mean(r["d_move_s"] for r in prim_runs)
    dh_fix = st.mean(r["d_hold_s"] for r in prim_runs if r["d_hold_s"] is not None)
    for r in runs:
        r["predicted_hold_fraction_sampled_fixed_intervals"] = dc.clamp((r["P_s"] + r["L_s"] - dc.T_INF - dm_fix / 2 + dh_fix / 2) / r["P_s"])
    # Time-weighted pooling: each run contributes in proportion to its eligible hazard-present OBJECT time,
    # so runs with almost no eligible time carry almost no weight and no support threshold is needed.
    T = [r["hold_s"] + r["move_s"] for r in runs]
    pooled = lambda key: sum(r[key] * t for r, t in zip(runs, T)) / sum(T)
    above = [r for r in runs if r["P_s"] + r["L_s"] > dc.T_INF]
    below = [r for r in runs if r["P_s"] + r["L_s"] <= dc.T_INF]
    pool_obs = lambda rs: sum(r["hold_s"] for r in rs) / sum(r["hold_s"] + r["move_s"] for r in rs) if rs else None
    out["sets"][camp] = {
        "cadence": rate, "runs_used": len(runs), "runs_without_eligible_intervals": skipped,
        "eligible_time_s": sum(T),
        "P_ms_mean": 1000 * st.mean(r["P_s"] for r in runs), "L_ms_mean": 1000 * st.mean(r["L_s"] for r in runs),
        "P_plus_L_ms_range": [1000 * min(r["P_s"] + r["L_s"] for r in runs), 1000 * max(r["P_s"] + r["L_s"] for r in runs)],
        "observed_time_weighted": pooled("observed_hold_fraction"),
        "predicted_first_order_time_weighted": pooled("predicted_hold_fraction"),
        "predicted_sampled_time_weighted": pooled("predicted_hold_fraction_sampled"),
        "predicted_sampled_fixed_intervals_time_weighted": pooled("predicted_hold_fraction_sampled_fixed_intervals"),
        "fixed_intervals_from_primary_s": {"d_move": dm_fix, "d_hold": dh_fix},
        "run_level_abs_error_fixed": {
            "runs_with_at_least_10s_eligible": sum(1 for t in T if t >= 10),
            "mean": st.mean(abs(r["predicted_hold_fraction_sampled_fixed_intervals"] - r["observed_hold_fraction"]) for r, t in zip(runs, T) if t >= 10),
            "max": max(abs(r["predicted_hold_fraction_sampled_fixed_intervals"] - r["observed_hold_fraction"]) for r, t in zip(runs, T) if t >= 10)},
        "observed_equal_run_mean": st.mean(r["observed_hold_fraction"] for r in runs),
        "runs_P_plus_L_above_T_inf": len(above), "observed_time_weighted_above": pool_obs(above),
        "runs_P_plus_L_at_or_below_T_inf": len(below), "observed_time_weighted_at_or_below": pool_obs(below),
        "runs": runs}
(HERE / "duty_cycle_holdout_results.json").write_text(json.dumps(out, indent=2) + "\n")
for k, v in out["sets"].items():
    print(f'{k:20} {v["cadence"]:6} runs={v["runs_used"]} (no eligible: {len(v["runs_without_eligible_intervals"])}) time={v["eligible_time_s"]:.1f}s P+L={v["P_plus_L_ms_range"][0]:.0f}-{v["P_plus_L_ms_range"][1]:.0f} '
          f'obs={v["observed_time_weighted"]:.3f} phi={v["predicted_first_order_time_weighted"]:.3f} phi_s={v["predicted_sampled_time_weighted"]:.3f} phi_s_fixed={v["predicted_sampled_fixed_intervals_time_weighted"]:.3f} runerr={v["run_level_abs_error_fixed"]} '
          f'| above T: n={v["runs_P_plus_L_above_T_inf"]} obs={v["observed_time_weighted_above"]} | below: n={v["runs_P_plus_L_at_or_below_T_inf"]} obs={v["observed_time_weighted_at_or_below"]}')

# Comparison table: primary (formulation set) and held-out sets, time-weighted
prim = json.loads((HERE / "duty_cycle_results.json").read_text())["runs"]
def tw(rs, key):
    T = [r["hold_s"] + r["move_s"] for r in rs]
    return sum(r[key] * t for r, t in zip(rs, T)) / sum(T), sum(T)
rows = []
for label, rs, rate in (("Primary, formulation set", [r for r in prim if r["method"] == "AEGIS" and r["rate"] == "normal"], "Normal"),
                        ("Primary, formulation set", [r for r in prim if r["method"] == "AEGIS" and r["rate"] == "slow"], "Slow"),
                        ("Slow-update pilot, held out", out["sets"]["timed_compare_slow"]["runs"], "Slow"),
                        ("Exploratory campaign, held out", out["sets"]["timed_compare"]["runs"], "Normal")):
    key = "predicted_hold_fraction_sampled_fixed_intervals" if "predicted_hold_fraction_sampled_fixed_intervals" in rs[0] else "predicted_hold_fraction_sampled"
    o, T = tw(rs, "observed_hold_fraction"); f1, _ = tw(rs, "predicted_hold_fraction"); fs, _ = tw(rs, key)
    pl = [1000 * (r["P_s"] + r["L_s"]) for r in rs]
    big = [abs(r[key] - r["observed_hold_fraction"]) for r in rs if r["hold_s"] + r["move_s"] >= 10]
    rows.append(f"{label} & {rate} & {len(rs)} & {T:.0f} & {min(pl):.0f}--{max(pl):.0f} & {f1:.3f} & {fs:.3f} & {o:.3f} & {max(big):.3f}\\\\")
tex = [r"% Generated by duty_cycle_holdout.py; time-weighted by eligible hazard-present OBJECT time.",
       r"\begin{table}[H]\centering\small",
       r"\caption{Duty-cycle relation on the runs used to formulate it and on held-out AEGIS runs of the same session. Shares are weighted by each run's eligible hazard-present \textsc{object} time, so runs with little such time carry little weight; nine exploratory runs had no eligible interval. $\phi$: first-order relation; $\phi_s$: with decision-sampling terms, using the mean decision intervals of the primary runs at the same cadence, so that only $P$ and $L$ are taken from each held-out run. Last column: largest absolute run-level error of $\phi_s$ among runs with at least 10 s of eligible time.}\label{tab:duty-holdout}",
       r"\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}Xlrrrrrrr}",
       r"\toprule Set & Cadence & Runs & Time (s) & $P+L$ (ms) & $\phi$ & $\phi_s$ & Observed & Max run error\\ \midrule", *rows,
       r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
(HERE / "duty_cycle_holdout_table.tex").write_text("\n".join(tex) + "\n")
print("\n".join(rows))
