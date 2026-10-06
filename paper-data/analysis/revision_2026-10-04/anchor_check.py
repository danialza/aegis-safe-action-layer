"""Stored anchors implied by the logged AEGIS scores, and the hold onsets they imply.

For a hazard-present OBJECT decision with logged score p and proxy age tau, Equation (6) gives the stored
anchor h = P0 + (p - P0) exp(tau / T_d). An OBJECT verdict that follows a HUMAN verdict leaves h near
(1 - eta) h_prev with h_prev close to one, i.e. about 0.048-0.05, whose onset tau_H is about 0.555 s.
This script reports, per primary AEGIS run, the largest implied anchor and whether such post-HUMAN
anchors (h >= 0.045) occur. No parameter is fitted.
"""
import glob, json, math, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
def _find(rel):
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)
P0, TD, P_STOP = 0.65, 0.40, 0.50
tau_H = lambda h: TD * math.log((P0 - h) / (P0 - P_STOP))
def t_event(events, pat):
    for e in events:
        if pat in e:
            m = re.match(r"\s*t=(\d+\.\d+)s", e)
            return float(m.group(1)) if m else None
runs = {}
for f in sorted(glob.glob(str(_find("data/timed_margin_compare/logs") / "AEGIS*.json"))):
    D = json.load(open(f))  # every logged decision is a carry decision, as in the run-level audit
    hs = [P0 + (e["p"] - P0) * math.exp(max(0.0, e["age_used"]) / TD) for e in D["log"]
          if e.get("vlm") == "object" and e.get("clr") is not None and e.get("p") is not None
          and e.get("age_used") is not None and e["p"] < P0 - 1e-9]
    post_human = [h for h in hs if h >= 0.045]
    runs[Path(f).stem] = {"max_implied_anchor": max(hs), "post_HUMAN_anchor_present": bool(post_human),
                          "post_HUMAN_anchor_range": [min(post_human), max(post_human)] if post_human else None,
                          "onset_s_at_max_anchor": tau_H(max(hs))}
out = {"note": __doc__, "onset_first_OBJECT_from_prior_s": tau_H((1 - 0.95) * P0), "onset_anchor_0.05_s": tau_H(0.05),
       "onset_limit_s": TD * math.log(P0 / (P0 - P_STOP)),
       "runs_with_post_HUMAN_anchor": sum(r["post_HUMAN_anchor_present"] for r in runs.values()), "runs": runs}
(HERE / "anchor_check_results.json").write_text(json.dumps(out, indent=2) + "\n")
print(f'{out["runs_with_post_HUMAN_anchor"]} of {len(runs)} primary AEGIS runs; onsets: first {out["onset_first_OBJECT_from_prior_s"]:.4f}, h=0.05 {out["onset_anchor_0.05_s"]:.4f}, limit {out["onset_limit_s"]:.4f}')
for k, v in runs.items(): print(f'  {k:20} max anchor {v["max_implied_anchor"]:.4f}  post-HUMAN range {v["post_HUMAN_anchor_range"]}')
