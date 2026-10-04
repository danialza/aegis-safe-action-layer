"""How often the permissive monitor parser was exercised in the frozen 2158-frame FastVLM replay.

The deployed parser maps a reply without a readable count to zero hands (OBJECT). Live raw replies
were not logged, so this check uses the frozen replay with the archived prompt and parser. It counts
replies that the strict numeric parser rejects, lists their wording, and joins the sampled ones to
the final human labels. It characterizes the replay only; it does not remove the failure path.
"""
import collections, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
def _find(rel):
    for base in (HERE.parent.parent, HERE.parents[1] / "10_hardware_manuscript_2026-09-24"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)
mon = [json.loads(l) for l in _find("semantic_auto_audit/run_20260924_203640/monitor.jsonl").read_text().splitlines() if l.strip()]
jr = json.loads(_find("semantic_human_review/merged_2026-09-25_v1/joined_records.json").read_text())["records"]
human = {(r["automatic"].get("monitor") or {}).get("id"): r["human"]["label"] for r in jr}
no_digit = [m for m in mon if not any(ch.isdigit() for ch in (m.get("raw_text") or ""))]
wording = collections.Counter(m.get("raw_text") for m in no_digit)
parsed = collections.Counter(m.get("parsed_count") for m in no_digit)
labels = collections.Counter(human[m["id"]] for m in no_digit if m["id"] in human)
out = {"note": __doc__, "replies": len(mon),
       "errors_or_empty": sum(1 for m in mon if m.get("error") or not (m.get("raw_text") or "").strip()),
       "replies_without_numeral": len(no_digit), "their_parsed_count": dict(parsed),
       "their_wording": dict(wording), "sampled_among_them": sum(labels.values()), "human_labels_of_sampled": dict(labels)}
(HERE / "parser_replay_check_results.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "note"}, indent=1, default=str))
