"""Counterfactual semantic blind window on the recorded decision streams (post hoc, conditional).

Suppose the semantic state of the scene changed at time t_c during a carry, for example by a hand
entering, and that no other input changed. A decision can reflect the change only if its evidence was
captured at or after t_c. Until the first such decision, the controller would therefore have issued
exactly the recorded decisions, so the motion it would have performed on pre-change semantic evidence
can be read from the log: the moving time after t_c (including the remainder of a command already in
progress at t_c) and the commanded tool travel over that time. t_c is placed on a uniform 5 ms grid
from the first carry decision to the last moving decision. The headline scope conditions on the robot
moving with a detected, non-destination hazard at t_c; a second scope uses every t_c.

Assumptions, which this analysis does not test: the change is captured by the next frame the monitor
processes and is recognized (the replay audit flagged every reviewed hand-positive frame); the first
post-change verdict then holds motion, as a HUMAN verdict does under every policy; the change does not
alter earlier decisions through the geometric channel; and t_c is independent of the update phase.
The result is a semantic-channel exposure measure, not a physical-risk or stopping measurement.
"""
import glob, json, math, os, re, statistics as st, itertools, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
STEP = 0.005

def _find(rel):
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)


def method_of(name, d):
    if d["variant"].startswith("AEGIS"):
        return "AEGIS"
    return "Trust32" if abs(d["clasp_params"]["epi"] - 0.032) < 1e-9 else "Trust12"


def q95(xs):
    xs = sorted(xs); return xs[int(0.95 * (len(xs) - 1))]


def analyse(f):
    d = json.load(open(f)); log = sorted(d["log"], key=lambda e: e["t_decision"])
    T = [e["t_decision"] for e in log]; cap = [e.get("ev_t_capture") for e in log]
    mov = [e["mode"] != "stop" for e in log]; tool = [e["tool"] for e in log]
    haz = [e.get("haz") is not None and e.get("state") != "hold_goal" for e in log]
    last = max(i for i, m in enumerate(mov) if m)
    scopes = {"moving_with_hazard": [], "all": []}
    n = int((T[last] - T[0]) / STEP)
    i0 = 0
    for k in range(n):
        tc = T[0] + k * STEP
        while T[i0] < tc:
            i0 += 1
        bt = bd = 0.0
        if i0 > 0 and mov[i0 - 1]:          # command in progress at tc
            frac = (T[i0] - tc) / (T[i0] - T[i0 - 1])
            bt += T[i0] - tc; bd += frac * math.dist(tool[i0 - 1], tool[i0])
        i = i0
        while i < len(T) - 1 and (cap[i] is None or cap[i] < tc):
            if mov[i]:
                bt += T[i + 1] - T[i]; bd += math.dist(tool[i], tool[i + 1])
            i += 1
        scopes["all"].append((bt, bd))
        if i0 > 0 and mov[i0 - 1] and haz[i0 - 1]:
            scopes["moving_with_hazard"].append((bt, bd))
    summ = {}
    for s, r in scopes.items():
        if not r:
            summ[s] = None; continue
        bt = [x[0] for x in r]; bd = [1000 * x[1] for x in r]
        summ[s] = {"change_times": len(r), "mean_s": st.mean(bt), "p95_s": q95(bt), "max_s": max(bt),
                   "mean_mm": st.mean(bd), "p95_mm": q95(bd), "max_mm": max(bd)}
    return {"run": os.path.basename(f)[:-5], "method": method_of(f, d),
            "cadence": "slow" if d.get("vlm_min_period_s") else "normal", "scopes": summ,
            "source_sha256": hashlib.sha256(Path(f).read_bytes()).hexdigest()}


def exact_p(a, b):
    pool = a + b; n = len(a); obs = st.mean(a) - st.mean(b); hits = tot = 0
    for idx in itertools.combinations(range(len(pool)), n):
        g = [pool[i] for i in idx]; h = [pool[i] for i in range(len(pool)) if i not in idx]
        tot += 1; hits += abs(st.mean(g) - st.mean(h)) >= abs(obs) - 1e-9
    return obs, hits / tot


runs = []
for folder, label in (("timed_margin_compare", "Primary"), ("timed_compare_slow", "Slow-update pilot")):
    for f in sorted(glob.glob(str(_find(f"data/{folder}/logs") / "*.json"))):
        r = analyse(f); r["set"] = label; runs.append(r)
cells = {}
for r in runs:
    cells.setdefault((r["set"], r["method"], r["cadence"]), []).append(r)
KEYS = ("mean_s", "p95_s", "max_s", "mean_mm", "p95_mm", "max_mm")
summary = {}
for k, v in cells.items():
    summary[" | ".join(k)] = {s: {**{m: st.mean(r["scopes"][s][m] for r in v) for m in KEYS},
                                  "cell_max_s": max(r["scopes"][s]["max_s"] for r in v),
                                  "cell_max_mm": max(r["scopes"][s]["max_mm"] for r in v), "runs": len(v)}
                              for s in ("moving_with_hazard", "all")}
tests = []
val = lambda s, m, c, key: [r["scopes"]["moving_with_hazard"][key] for r in runs if r["set"] == s and r["method"] == m and r["cadence"] == c]
for s, refs in (("Primary", ("Trust12", "Trust32")), ("Slow-update pilot", ("Trust12",))):
    for c in (("normal", "slow") if s == "Primary" else ("slow",)):
        for ref in refs:
            for key in ("mean_s", "mean_mm"):
                d, p = exact_p(val(s, "AEGIS", c, key), val(s, ref, c, key))
                tests.append({"set": s, "cadence": c, "reference": ref, "metric": key, "AEGIS_minus_ref": d, "p": p})
out = {"note": __doc__, "grid_step_s": STEP, "cells": summary, "exact_tests_run_level": tests, "runs": runs}
(HERE / "semantic_blind_window_results.json").write_text(json.dumps(out, indent=2) + "\n")

lines = []
for (s, m, c), v in cells.items():
    q = summary[" | ".join((s, m, c))]["moving_with_hazard"]
    lines.append(f"{s} & {m} & {c.capitalize()} & {1000*q['mean_s']:.0f} & {1000*q['p95_s']:.0f} & {1000*q['cell_max_s']:.0f} & {q['mean_mm']:.1f} & {q['p95_mm']:.1f} & {q['cell_max_mm']:.1f}\\\\")
tex = [r"% Generated by semantic_blind_window.py; post hoc, conditional on the assumptions in its docstring.",
       r"\begin{table}[H]\centering\small",
       r"\caption{Counterfactual semantic blind window: moving time and commanded tool travel after a hypothetical semantic change, until the first decision that uses evidence captured after the change, computed on the recorded decision streams for change times on a 5 ms grid while the robot was moving with a detected hazard. Mean and 95th percentile are equal-run means of run-level values; maximum is over the four runs. The values assume that the change would be captured by the next processed frame, recognized, and answered by a hold, and that it would not alter earlier decisions; they are not physical-risk or stopping measurements.}\label{tab:blind-window}",
       r"\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}Xllrrrrrr}",
       r"\toprule & & & \multicolumn{3}{c}{Moving time (ms)} & \multicolumn{3}{c}{Travel (mm)}\\ \cmidrule(lr){4-6}\cmidrule(lr){7-9}",
       r"Set & Method & Cadence & Mean & P95 & Max & Mean & P95 & Max\\ \midrule", *lines,
       r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
(HERE / "semantic_blind_window_table.tex").write_text("\n".join(tex) + "\n")
for k, v in summary.items():
    q = v["moving_with_hazard"]; print(k, {m: round(q[m], 3) for m in KEYS}, "cellmax", round(q["cell_max_s"], 3), round(q["cell_max_mm"], 1))
for t in tests:
    print(t)
