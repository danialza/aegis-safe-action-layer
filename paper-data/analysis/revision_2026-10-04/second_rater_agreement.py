"""Agreement between the second annotator and the merged first-annotator labels on the frozen 426-frame sample.

The second annotator labelled the same frozen manifest once, in an isolated browser profile, with the clarified
definitions used for the first annotator's recheck. Presence agreement is summarized by Cohen's kappa on frames that
both annotators labelled definitely (hand or no_hand); uncertain labels are counted separately. The script also
repeats the FastVLM replay counts with the second annotator's labels as reference and checks the two claims of
Section S13 that depend on the human labels (the joint-negative stratum and the parser's no-numeral replies).
No model output is used as a label, and no input file is modified.
"""
import collections, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
def _find(rel):
    for base in (HERE.parent.parent, HERE.parent / "paper-data"):
        if (base / rel).exists():
            return base / rel
    raise FileNotFoundError(rel)

first = json.loads(_find("semantic_human_review/merged_2026-09-25_v1/joined_records.json").read_text())["records"]
second = json.loads(_find("semantic_human_review/second_rater_426_v1/human_review_426_second_rater.json").read_text())
mon = [json.loads(l) for l in _find("semantic_auto_audit/run_20260924_203640/monitor.jsonl").read_text().splitlines() if l.strip()]
assert second["label_source"] == "human"
A = {r["case_id"]: r for r in first}
B = {r["id"]: r for r in second["labels"]}
assert set(A) == set(B) and len(A) == 426

def kappa(pairs, cats):
    n = len(pairs); po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return po, (po - pe) / (1 - pe)

labs = ("hand", "no_hand", "uncertain")
all_pairs = [(A[c]["human"]["label"], B[c]["label"]) for c in sorted(A)]
definite = [(a, b) for a, b in all_pairs if a != "uncertain" and b != "uncertain"]
po2, k2 = kappa(definite, ("hand", "no_hand"))
po3, k3 = kappa(all_pairs, labs)
differ = [{"case_id": c, "run": A[c]["frame"]["run"], "container_time_s": A[c]["frame"]["container_time_s"],
           "stratum": A[c]["frame"]["stratum"], "first": A[c]["human"]["label"], "second": B[c]["label"],
           "second_cover": B[c]["cover"], "second_visibility": B[c]["visibility"],
           "fastvlm": A[c]["automatic"]["monitor"]["prediction"], "qwen": A[c]["automatic"]["reference"]["presence"]}
          for c in sorted(A) if A[c]["human"]["label"] != B[c]["label"]]
both_pos = [c for c in A if A[c]["human"]["label"] == "hand" and B[c]["label"] == "hand"]
pred = lambda c: A[c]["automatic"]["monitor"]["prediction"]
def replay(lab):
    pos = [c for c in A if lab(c) == "hand"]; neg = [c for c in A if lab(c) == "no_hand"]
    return {"hand_positive": len(pos), "fastvlm_human_on_positive": sum(pred(c) == "HUMAN" for c in pos),
            "hand_negative": len(neg), "fastvlm_human_on_negative": sum(pred(c) == "HUMAN" for c in neg),
            "uncertain": sum(lab(c) == "uncertain" for c in A)}
joint_neg = [c for c in A if A[c]["frame"]["stratum"] == "both_negative"]
no_digit = {m["id"]: m.get("parsed_count") for m in mon if not any(ch.isdigit() for ch in (m.get("raw_text") or ""))}
parser_sampled = [c for c in A if A[c]["automatic"]["monitor"]["id"] in no_digit]
parsed_as = lambda c: no_digit[A[c]["automatic"]["monitor"]["id"]]
times = sorted(r["reviewed_at"] for r in second["labels"])

out = {"note": __doc__,
       "second_annotator": {"prior_model_exposure": second["prior_model_exposure"],
                            "review_manifest_sha256": second["review_manifest_sha256"],
                            "first_reviewed_at": times[0], "last_reviewed_at": times[-1],
                            "labels": dict(collections.Counter(B[c]["label"] for c in A))},
       "first_annotator_merged_labels": dict(collections.Counter(A[c]["human"]["label"] for c in A)),
       "confusion_first_to_second": {f"{a}->{b}": sum(p == (a, b) for p in all_pairs) for a in labs for b in labs},
       "definite_both": len(definite), "definite_agree": sum(a == b for a, b in definite),
       "observed_agreement_definite": po2, "cohen_kappa_definite": k2,
       "observed_agreement_three_category": po3, "cohen_kappa_three_category": k3,
       "frames_with_different_presence_labels": differ,
       "conditions_on_frames_both_labelled_hand": {
           "n": len(both_pos),
           "cover_agree": sum(A[c]["human"]["cover"] == B[c]["cover"] for c in both_pos),
           "visibility_agree": sum(A[c]["human"]["visibility"] == B[c]["visibility"] for c in both_pos),
           "cover_first_to_second": {f"{k[0]}->{k[1]}": v for k, v in collections.Counter((A[c]["human"]["cover"], B[c]["cover"]) for c in both_pos).items()},
           "visibility_first_to_second": {f"{k[0]}->{k[1]}": v for k, v in collections.Counter((A[c]["human"]["visibility"], B[c]["visibility"]) for c in both_pos).items()}},
       "fastvlm_replay_first_labels": replay(lambda c: A[c]["human"]["label"]),
       "fastvlm_replay_second_labels": replay(lambda c: B[c]["label"]),
       "joint_negative_stratum_second_labels": dict(collections.Counter(B[c]["label"] for c in joint_neg)),
       "parser_no_numeral_sampled_second_labels": {
           f"parsed_as_{k}": dict(collections.Counter(B[c]["label"] for c in parser_sampled if parsed_as(c) == k))
           for k in sorted({parsed_as(c) for c in parser_sampled})}}
(HERE / "second_rater_agreement_results.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "note"}, indent=1))
