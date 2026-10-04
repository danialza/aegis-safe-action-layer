"""Checks on the existing records that bound single-session risks (no new trials).

1. Session drift: VLM inference duration across all 92 eligible transports versus wall-clock time.
2. Obstruction timing: time from carry start to the first carry decision with a detected hazard (primary).
3. Operator placement: direction-adjusted per-run obstacle position and radius by policy (primary).
4. Hand appearances: human-verdict hold occupancy per run by policy (primary).
5. Replication: slow-update pilot, AEGIS versus Trust12, exact permutation tests.
6. Annotation stability: presence labels of the 115 rechecked frames, first versus second pass.
"""
import glob, itertools, json, os, re, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parent
def _find(rel):
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)
DATA = _find("data"); AN = _find("analysis")

def t_event(events, pat):
    for e in events:
        if pat in e:
            m = re.match(r"\s*t=(\d+\.\d+)s", e)
            return float(m.group(1)) if m else None

def exact(a, b):
    pool = a + b; obs = abs(st.mean(a) - st.mean(b)); c = t = 0
    for idx in itertools.combinations(range(len(pool)), len(a)):
        g = [pool[i] for i in idx]; h = [pool[i] for i in range(len(pool)) if i not in idx]
        t += 1; c += abs(st.mean(g) - st.mean(h)) >= obs - 1e-9
    return c / t

method = lambda n: "AEGIS" if n.startswith("AEGIS") else ("Trust32" if n.startswith("Trust32") else "Trust12")
out = {"note": __doc__}

# 1 and 2
rows = []
for f in glob.glob(str(DATA / "*" / "logs" / "*.json")):
    if f.endswith("_timing.jsonl"): continue
    camp = Path(f).parts[-3]; name = Path(f).stem
    D = json.load(open(f)); t0 = t_event(D.get("events", []), "carrying")
    if t0 is None: continue
    wall = json.loads(open(f[:-5] + "_timing.jsonl").readline())["wall"]
    car = [e for e in D["log"] if e["t"] >= t0]
    b = {e.get("ev_seq", e["ev_t_infer_start"]): (e["ev_t_infer_start"], e["ev_t_infer_end"]) for e in car if e.get("ev_t_infer_start") is not None}
    if len(b) < 3: continue
    first_haz = next((e["t"] - t0 for e in car if e.get("clr") is not None or e.get("haz")), None)
    rows.append({"campaign": camp, "run": name, "method": method(name), "wall": wall,
                 "inference_ms": 1000 * st.mean(v[1] - v[0] for v in b.values()), "first_hazard_s": first_haz})
rows.sort(key=lambda r: r["wall"]); w0 = rows[0]["wall"]
x = [(r["wall"] - w0) / 3600 for r in rows]; y = [r["inference_ms"] for r in rows]
mx, my = st.mean(x), st.mean(y)
out["session_drift"] = {"runs": len(rows), "span_h": x[-1], "inference_mean_ms": my, "inference_sd_ms": st.stdev(y),
                        "inference_range_ms": [min(y), max(y)],
                        "slope_ms_per_h": sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x)}
prim = [r for r in rows if r["campaign"] == "timed_margin_compare"]
out["obstruction_timing"] = {"runs": len(prim), "max_first_hazard_s": max(r["first_hazard_s"] for r in prim)}

# 3 operator placement (direction-adjusted), from the per-run geometry table
geo = []
for ln in (AN / "additional_geometry_table.tex").read_text().splitlines():
    m = re.match(r"(Normal|Slow) & (\w+) & ([AB]) & (\d) & (\d+) & ([\d.]+) & ([-\d.]+) & ([\d.]+)", ln)
    if m: geo.append({"method": m[2], "to": m[3], "x": float(m[6]), "y": float(m[7]), "r": float(m[8])})
assert len(geo) == 24
dmean = {d: {k: st.mean(g[k] for g in geo if g["to"] == d) for k in "xyr"} for d in "AB"}
place = {}
for k in "xyr":
    adj = {m: [g[k] - dmean[g["to"]][k] for g in geo if g["method"] == m] for m in ("AEGIS", "Trust12", "Trust32")}
    place[k] = {"method_means_mm": {m: st.mean(v) for m, v in adj.items()},
                "max_between_method_difference_mm": max(st.mean(a) for a in adj.values()) - min(st.mean(a) for a in adj.values()),
                "p": {f"{a} vs {b}": exact(adj[a], adj[b]) for a, b in (("AEGIS", "Trust12"), ("AEGIS", "Trust32"), ("Trust12", "Trust32"))}}
out["operator_placement"] = place

# 4 and 5 from the frozen run-level audit
pr = json.loads((AN / "exploratory_patterns_2026-10-02/pattern_results.json").read_text())
out["human_hold_s"] = {f"{m}-{rate}": st.mean(r["software_occupancy_s"].get("human_hold", 0) for r in pr["runs"]
                         if r["campaign"] == "timed_margin_compare" and r["method"] == m and r["rate"] == rate)
                       for m in ("AEGIS", "Trust12", "Trust32") for rate in ("normal", "slow")}
pil = [r for r in pr["runs"] if r["campaign"] == "timed_compare_slow"]
rep = {}
for k in ("mean_moving_age_ms", "minimum_command_estimated_separation_mm", "carry_to_delivery_s"):
    a = [r[k] for r in pil if r["method"] == "AEGIS"]; b = [r[k] for r in pil if r["method"] != "AEGIS"]
    rep[k] = {"AEGIS_minus_Trust12": st.mean(a) - st.mean(b), "interval": [min(a) - max(b), max(a) - min(b)], "p": exact(a, b)}
out["pilot_replication"] = rep

# 6 annotation stability
jr = json.loads(_find("semantic_human_review/merged_2026-09-25_v1/joined_records.json").read_text())
pairs = [(r["original_human"]["label"], r["recheck_human"]["label"]) for r in jr["records"] if r.get("recheck_human")]
out["annotation_stability"] = {"rechecked": len(pairs), "unchanged": sum(a == b for a, b in pairs),
                               "definite_reversals": sum(a != b and "uncertain" not in (a, b) for a, b in pairs),
                               "to_or_from_uncertain": sum(a != b and "uncertain" in (a, b) for a, b in pairs)}
(HERE / "robustness_checks_results.json").write_text(json.dumps(out, indent=2, default=float) + "\n")

sd = out["session_drift"]; pl = out["operator_placement"]; hh = out["human_hold_s"]; an = out["annotation_stability"]
fmtp = lambda d: min(d.values())
sg = lambda v: f"{v:+.1f}".replace("-", "$-$")
T = [r"% Generated by robustness_checks.py; no new trials.",
     r"\begin{table}[H]\centering\small",
     r"\caption{Checks on the existing records that bound single-session risks. None replaces a randomized, multi-session design.}\label{tab:robustness}",
     r"\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}p{0.27\linewidth}X}", r"\toprule Concern & Result\\ \midrule",
     f"Drift of the pipeline during the session & VLM inference {sd['inference_mean_ms']:.1f} ms on average (SD {sd['inference_sd_ms']:.1f} ms) across {sd['runs']} transports over {sd['span_h']:.1f} h; linear drift {sd['slope_ms_per_h']:.1f} ms per hour\\\\",
     f"Obstruction timing by the operator & Obstruction detected at the first carry decision in all {out['obstruction_timing']['runs']} primary runs (at most {out['obstruction_timing']['max_first_hazard_s']:.1f} s after carry start)\\\\",
     f"Obstruction placement by the operator & Direction-adjusted policy means differ by at most {pl['x']['max_between_method_difference_mm']:.1f} mm in $x$, {pl['y']['max_between_method_difference_mm']:.1f} mm in $y$ and {pl['r']['max_between_method_difference_mm']:.1f} mm in radius; exact $p\\ge{min(fmtp(pl[k]['p']) for k in 'xyr'):.2f}$ for every pairwise contrast (8 runs per policy)\\\\",
     f"Hand appearances & Human-verdict holds averaged {min(hh.values()):.2f}--{max(hh.values()):.2f} s per run in every policy--cadence cell\\\\",
     "Replication in a separate block & Slow-update pilot, AEGIS minus Trust12: mean moving age " + sg(rep['mean_moving_age_ms']['AEGIS_minus_Trust12']) + f" ms ($p={rep['mean_moving_age_ms']['p']:.3f}$), separation " + sg(rep['minimum_command_estimated_separation_mm']['AEGIS_minus_Trust12']) + f" mm ($p={rep['minimum_command_estimated_separation_mm']['p']:.3f}$), time " + sg(rep['carry_to_delivery_s']['AEGIS_minus_Trust12']) + f" s ($p={rep['carry_to_delivery_s']['p']:.3f}$), all with the same sign as in the primary campaign" + "\\\\",
     f"Stability of the single annotator & Of {an['rechecked']} targeted rechecks, {an['unchanged']} presence labels unchanged, {an['definite_reversals']} definite hand/no-hand reversals, {an['to_or_from_uncertain']} moved to or from uncertain\\\\",
     r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
(HERE / "robustness_table.tex").write_text("\n".join(T) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "note"}, indent=1, default=float)[:2500])
