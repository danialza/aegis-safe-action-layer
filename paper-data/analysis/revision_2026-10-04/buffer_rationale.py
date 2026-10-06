"""Median AEGIS margin on hazard-present moving decisions with a valid OBJECT verdict, per campaign.

Supports the documented choice of the 32 mm Trust32 buffer, which was fixed before the primary
campaign near the median AEGIS margin of the preceding pilot and exploratory runs.
"""
import glob, json, os, re, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parent
for base in (HERE.parent.parent / "data", HERE.parents[1] / "10_hardware_manuscript_2026-09-24/data"):
    if base.exists():
        DATA = base
        break

def t_event(events, pat):
    for e in events:
        if pat in e:
            m = re.match(r"\s*t=(\d+\.\d+)s", e)
            return float(m.group(1)) if m else None

out = {}
for camp in ("timed_compare_slow", "timed_compare", "timed_margin_compare"):
    vals, runs = [], 0
    for f in sorted(glob.glob(str(DATA / camp / "logs" / "AEGIS*.json"))):
        D = json.load(open(f))  # every logged decision is a carry decision, as in the run-level audit
        if not D.get("log"):
            continue
        runs += 1
        vals += [1000 * e["margin"] for e in D["log"] if e.get("vlm") == "object"
                 and e.get("clr") is not None and e.get("margin") is not None
                 and e.get("ev_status") == "ok" and e.get("mode") != "stop"]
    out[camp] = {"AEGIS_runs": runs, "decisions": len(vals), "median_margin_mm": st.median(vals), "mean_margin_mm": st.mean(vals)}
(HERE / "buffer_rationale_results.json").write_text(json.dumps(out, indent=2) + "\n")
for k, v in out.items():
    print(f'{k:22} runs={v["AEGIS_runs"]:2} n={v["decisions"]:5} median={v["median_margin_mm"]:.1f} mm mean={v["mean_margin_mm"]:.1f} mm')
