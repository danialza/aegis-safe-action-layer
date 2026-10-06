"""First-order duty-cycle account of the AEGIS score-hold time (post hoc, no fitted parameter).

Assumptions: verdicts start every P seconds; each becomes available L seconds after its capture
proxy; a hazard is detected throughout with OBJECT verdicts; the anchor is at its limit, so the gate
is a timeout at T_inf = T_d log(P0/(P0-0.5)). Under continuous checking the age of the newest
evidence sweeps from L to P+L and the hold fraction is phi = min(1, max(0, (P+L-T_inf)/P)).
If L >= T_inf, phi = 1: evidence is already too old on arrival.
Sampled variant: the controller decides at discrete ticks, so a hold starts on average half a
moving-decision interval (d_m) after the onset and ends half a hold interval (d_h) after a new
verdict arrives: phi_s = min(1, max(0, (P+L-T_inf-d_m/2+d_h/2)/P)). d_m and d_h are measured.
Observed: interval time assigned to score holds over score-hold plus moving intervals with a hazard,
a valid OBJECT verdict and no other guard. This refinement was identified after inspecting the data.
"""
import glob, json, math, os, re, statistics as st, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent

def _find(*rels):
    """Locate an input in the release layout (paper-data/) or the local package layout."""
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        for rel in rels:
            if (base / rel).exists():
                return base / rel
    raise FileNotFoundError(rels)
LOGS = _find("data/timed_margin_compare/logs")
T_INF = 0.4 * math.log(0.65 / 0.15)

def t_event(events, pat):
    for e in events:
        if pat in e:
            return float(re.match(r"t=(\d+\.\d+)s", e.strip()).group(1))

clamp = lambda x: min(1.0, max(0.0, x))


def analyse_run(f, method, rate):
    """Per-run inputs, predictions and observed hold share; identical for primary and hold-out runs."""
    D = json.load(open(f)); t0 = t_event(D["events"], "carrying")
    car = [e for e in D["log"] if e["t"] >= t0]
    bundles = {}
    for e in car:
        if e.get("ev_t_infer_start") is not None:
            bundles[e.get("ev_seq", e["ev_t_infer_start"])] = (e["ev_t_infer_start"], e["ev_t_infer_end"], e["ev_t_capture"])
    starts = sorted(v[0] for v in bundles.values())
    if len(starts) < 3:
        return None
    ends = sorted(v[1] for v in bundles.values())
    P = st.median(b - a for a, b in zip(starts, starts[1:]))
    L = st.mean(v[1] - v[2] for v in bundles.values())
    hold = move = 0.0; dms = []; dhs = []
    for a, b in zip(car, car[1:]):
        if a.get("vlm") == "object" and a.get("clr") is not None and a.get("ev_status") == "ok":
            if a.get("stop_reason") == "belief>=P_STOP":
                hold += b["t"] - a["t"]; dhs.append(b["t"] - a["t"])
            elif a.get("mode") != "stop":
                move += b["t"] - a["t"]; dms.append(b["t"] - a["t"])
    dm = st.mean(dms) if dms else 0.0; dh = st.mean(dhs) if dhs else None
    return {"run": os.path.basename(f)[:-5], "method": method, "rate": rate, "P_s": P, "L_s": L,
            "predicted_hold_fraction": clamp((P + L - T_INF) / P) if method == "AEGIS" else 0.0,
            "d_move_s": dm, "d_hold_s": dh,
            "predicted_hold_fraction_sampled": clamp((P + L - T_INF - dm / 2 + (dh or 0.0) / 2) / P) if method == "AEGIS" else 0.0,
            "observed_hold_fraction": hold / (hold + move) if hold + move else None,
            "start_intervals_s": [b - a for a, b in zip(starts, starts[1:])],
            "completion_intervals_s": [b - a for a, b in zip(ends, ends[1:])],
            "hold_s": hold, "move_s": move, "source_sha256": hashlib.sha256(Path(f).read_bytes()).hexdigest()}


def _interval_stats(xs):
    """Median, interquartile range and coefficient of variation of verdict start or completion intervals."""
    xs = sorted(xs); q = lambda f: xs[int(f * (len(xs) - 1))]
    return {"n": len(xs), "median": 1000 * st.median(xs), "q25": 1000 * q(.25), "q75": 1000 * q(.75),
            "cv": st.pstdev(xs) / st.mean(xs)}


def main():
    runs = []
    for f in sorted(glob.glob(str(LOGS / "*.json"))):
        m = re.match(r"(AEGIS|Trust12|Trust32)-(normal|slow)", os.path.basename(f))
        runs.append(analyse_run(f, m[1], m[2]))
    cells = {}
    for r in runs:
        cells.setdefault(f'{r["method"]}-{r["rate"]}', []).append(r)
    summary = {k: {"P_ms": 1000 * st.mean(r["P_s"] for r in v), "L_ms": 1000 * st.mean(r["L_s"] for r in v),
                   "P_plus_L_ms": 1000 * st.mean(r["P_s"] + r["L_s"] for r in v),
                   "predicted_hold_fraction": st.mean(r["predicted_hold_fraction"] for r in v),
                   "predicted_hold_fraction_range": [min(r["predicted_hold_fraction"] for r in v), max(r["predicted_hold_fraction"] for r in v)],
                   "predicted_at_cell_means": clamp((st.mean(r["P_s"] for r in v) + st.mean(r["L_s"] for r in v) - T_INF) / st.mean(r["P_s"] for r in v)) if v[0]["method"] == "AEGIS" else 0.0,
                   "d_move_ms": 1000 * st.mean(r["d_move_s"] for r in v), "d_hold_ms": (1000 * st.mean(r["d_hold_s"] for r in v if r["d_hold_s"] is not None)) if any(r["d_hold_s"] is not None for r in v) else None,
                   "predicted_hold_fraction_sampled": st.mean(r["predicted_hold_fraction_sampled"] for r in v),
                   "observed_hold_fraction_equal_run": st.mean(r["observed_hold_fraction"] for r in v),
                   "observed_hold_fraction_range": [min(r["observed_hold_fraction"] for r in v), max(r["observed_hold_fraction"] for r in v)],
               "completion_interval_ms": _interval_stats([x for r in v for x in r["completion_intervals_s"]]),
               "start_interval_ms": _interval_stats([x for r in v for x in r["start_intervals_s"]])}
               for k, v in sorted(cells.items())}
    out = {"T_inf_s": T_INF, "model": __doc__, "cells": summary, "runs": runs}
    (HERE / "duty_cycle_results.json").write_text(json.dumps(out, indent=2) + "\n")
    for k, v in summary.items():
        print(f'{k:15} P={v["P_ms"]:.0f} L={v["L_ms"]:.0f} P+L={v["P_plus_L_ms"]:.0f} pred={v["predicted_hold_fraction"]:.3f} {v["predicted_hold_fraction_range"]} plugin={v["predicted_at_cell_means"]:.3f} dm={v["d_move_ms"]:.0f} dh={v["d_hold_ms"]} pred_s={v["predicted_hold_fraction_sampled"]:.3f} obs={v["observed_hold_fraction_equal_run"]:.3f} range={v["observed_hold_fraction_range"][0]:.3f}-{v["observed_hold_fraction_range"][1]:.3f}')


if __name__ == "__main__":
    main()
