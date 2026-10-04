"""Post-hoc semantic/geometry temporal-association audit of the primary 24 runs.

This does not estimate true object appearance, collision risk, or physical motion.
No robot code is imported. All source JSON, JSONL and videos remain unchanged.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "data/timed_margin_compare/logs"
OUT = ROOT / "analysis"
METHODS = ("AEGIS", "Trust12", "Trust32")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def preserved_video_samples(source_hashes):
    """Reuse optional qualitative extraction metadata only with verified inputs.

    Ordinary numerical reruns must not erase an earlier optional video audit.
    A changed log, source video, or derived still invalidates the cached samples;
    rerun with --video-samples to recompute them instead of silently reusing them.
    """
    previous_path = OUT/'first_detection_audit.json'
    if not previous_path.exists():
        return [], 'not_requested_no_previous_report'
    previous = json.loads(previous_path.read_text())
    examples = previous.get('video_examples', [])
    if not examples:
        return [], 'not_requested_no_previous_samples'
    if previous.get('source_sha256') != source_hashes:
        return [], 'not_reused_log_or_sidecar_hashes_changed'
    checked = {}
    for example in examples:
        for key, local in (('raw_video', False), ('narrated_video', False),
                           ('raw_image', True), ('narrated_image', True)):
            if key not in example or key+'_sha256' not in example:
                return [], 'not_reused_incomplete_sample_hash_metadata'
            path = ROOT/example[key] if local else Path(example[key])
            if not path.is_file():
                return [], 'not_reused_missing_video_or_still'
            if str(path) not in checked:
                checked[str(path)] = sha(path)
            if checked[str(path)] != example[key+'_sha256']:
                return [], 'not_reused_video_or_still_hash_changed'
    return examples, 'reused_after_matching_all_log_sidecar_video_and_still_hashes'


def framediff(a, b):
    """Frame numbers corroborate ordering only within the same stream."""
    ap, an = a.rsplit(":", 1); bp, bn = b.rsplit(":", 1)
    return int(bn) - int(an) if ap == bp else None


def hazard_input(row, frames):
    # Goal-hold rows can log a latched hazard, not the current tracker state.
    # Its clr is None exactly when the current hs is absent in that branch.
    if row.get("state") == "hold_goal":
        if row.get("clr") is None:
            return None
        return frames[row["haz_frame_id"]]["detection"]
    return row.get("haz")


def event_from(i, row, frame, reason, previous):
    h = frame["detection"]
    return {"decision_index": i, "decision_time": row["t_decision"],
            "run_elapsed_s": row["t"], "source_proxy": frame["t_capture_est"],
            "source_processed": frame["t_processed"], "source_frame_id": frame["frame_id"],
            "trigger": reason, "current_disc": h, "previous_disc": previous,
            "centre_jump_mm": None if previous is None else 1000*math.dist(h[:2], previous[:2]),
            "radius_jump_mm": None if previous is None else 1000*abs(h[2]-previous[2]),
            "decision_cls": row.get("cls")}


def audit_definition(rows, frames, definition, threshold=.05, use_decision_clock=False,
                     literal_hazard_field=False):
    events, hits = [], []
    previous = None
    current_event = None
    first_source = min((f for f in frames.values() if f.get("detection") is not None),
                       key=lambda f: f["t_processed"])
    if definition == "first_source_detection":
        current_event = {"decision_index": None, "decision_time": first_source["t_processed"],
                         "run_elapsed_s": None, "source_proxy": first_source["t_capture_est"],
                         "source_processed": first_source["t_processed"],
                         "source_frame_id": first_source["frame_id"], "trigger": "first_sensing_detection",
                         "current_disc": first_source["detection"], "previous_disc": None}
        events.append(current_event)
    for i, row in enumerate(rows):
        h = row.get("haz") if literal_hazard_field else hazard_input(row, frames)
        if h and definition != "first_source_detection":
            trigger = None
            if previous is None:
                trigger = "initial_or_reappearance"
            elif definition != "presence_transition_only" and (
                    math.dist(h[:2], previous[:2]) > threshold or abs(h[2]-previous[2]) > threshold):
                trigger = "centre_or_radius_jump"
            if trigger:
                f = frames[row["haz_frame_id"]]
                assert f["detection"] is not None
                if not literal_hazard_field:
                    assert max(abs(a-b) for a, b in zip(h, f["detection"])) < 1e-8
                current_event = event_from(i, row, f, trigger, previous)
                events.append(current_event)
        if h and row["mode"] != "stop" and current_event:
            reference = current_event["decision_time" if use_decision_clock else "source_proxy"]
            if row["t_decision"] >= reference and row["ev_t_capture"] < reference:
                gap = reference-row["ev_t_capture"]
                hits.append({"decision_index": i, "run_elapsed_s": row["t"],
                             "t_decision": row["t_decision"], "mode": row["mode"],
                             "cls": row.get("cls"), "evidence_seq": row["ev_seq"],
                             "evidence_frame_id": row["ev_frame_id"],
                             "evidence_capture_proxy": row["ev_t_capture"],
                             "age_used_s": row["age_used"], "score": row["p"],
                             "command_estimated_separation_mm": 1000*row["clr"],
                             "capture_predates_refresh_by_ms": 1000*gap,
                             "still_predates_with_5ms_tolerance": gap > .005,
                             "source_frame_number_minus_semantic_frame_number":
                                 framediff(row["ev_frame_id"], current_event["source_frame_id"]),
                             "event": current_event})
        if definition == "retained_blob_refresh":
            if h:
                previous = h
        else:
            previous = h
    return {"events": events, "hits": hits, "moving_decisions": len(hits)}


def group(runs, key):
    out = {}
    for cadence in ("normal", "slow"):
        out[cadence] = {}
        for method in METHODS:
            chosen = [r for r in runs if r["cadence"] == cadence and r["method"] == method]
            hits = [h for r in chosen for h in r["definitions"][key]["hits"]]
            n = sum(r["hazard_present_moving_decisions"] for r in chosen)
            out[cadence][method] = {
                "runs": len(chosen), "hazard_present_moving_decisions": n,
                "flagged_moving_decisions": len(hits),
                "runs_with_flagged_decision": sum(bool(r["definitions"][key]["hits"]) for r in chosen),
                "pooled_decision_fraction": len(hits)/n,
                "mean_run_fraction": statistics.mean(
                    len(r["definitions"][key]["hits"])/r["hazard_present_moving_decisions"] for r in chosen),
                "minimum_command_estimated_separation_mm": min(
                    (h["command_estimated_separation_mm"] for h in hits), default=None),
                "min_capture_predates_refresh_ms": min(
                    (h["capture_predates_refresh_by_ms"] for h in hits), default=None),
                "all_frame_numbers_confirm_older": all(
                    h["source_frame_number_minus_semantic_frame_number"] is not None and
                    h["source_frame_number_minus_semantic_frame_number"] > 0 for h in hits),
                "all_survive_5ms_tolerance": all(h["still_predates_with_5ms_tolerance"] for h in hits)}
    return out


def video_samples(runs):
    """Approximate visual checks with paired raw/narrated frame indices.

    The narrator embeds elapsed recorder time rounded to 0.1 s; the raw and
    narrated writers consume the same frame in each recorder iteration. Neither
    file contains the source packet frame ID, so these are not event ground truth.
    """
    import cv2
    dest = ROOT / "tmp/first_detection_audit"
    dest.mkdir(parents=True, exist_ok=True)
    examples = []
    for runname in ("AEGIS-slow_toB_1", "Trust12-slow_toA_1", "Trust32-slow_toB_2"):
        run = next(r for r in runs if r["run"] == runname)
        d = json.loads((LOGS/(runname+".json")).read_text())
        key = "literal_hazard_field_50mm" if runname.startswith('AEGIS') else "geometry_refresh_50mm"
        hits = run["definitions"][key]["hits"]
        target = hits[0]["event"]["run_elapsed_s"]
        narrated = cv2.VideoCapture(d["video"])
        raw = cv2.VideoCapture(d["raw_video"])
        raw_hash, narrated_hash = sha(d['raw_video']), sha(d['video'])
        n = int(narrated.get(cv2.CAP_PROP_FRAME_COUNT)); nr = int(raw.get(cv2.CAP_PROP_FRAME_COUNT))
        assert n == nr

        def read_time(index):
            narrated.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = narrated.read()
            if not ok:
                return None
            crop = frame[69:87, 13:115]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=4, fy=4)
            _, buf = cv2.imencode('.png', gray)
            proc = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '7',
                                   '-c', 'tessedit_char_whitelist=t=0123456789.s'],
                                  input=buf.tobytes(), capture_output=True, check=True)
            text = proc.stdout.decode().strip()
            match = re.search(r'(\d+\.\d+)', text)
            return (float(match.group(1)), text, frame) if match else None

        # Binary-search displayed recorder time; do not assume 12 encoded fps
        # implies that no acquisition iterations were delayed or missed.
        for offset in (-.7, 0.0, .7):
            desired = target+offset
            lo, hi = 0, n-1
            candidates = []
            for _ in range(12):
                mid = (lo+hi)//2
                item = read_time(mid)
                if item is None:
                    break
                displayed, ocr, frame = item
                candidates.append((abs(displayed-desired), mid, displayed, ocr, frame))
                if displayed < desired:
                    lo = mid+1
                else:
                    hi = mid-1
                if lo > hi:
                    break
            if not candidates:
                examples.append({"run": runname, "error": "No readable narrator timestamp"})
                continue
            _, index, displayed, ocr, narrframe = min(candidates, key=lambda v: v[0])
            raw.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, rawframe = raw.read()
            assert ok
            suffix = f"{runname}_{offset:+.1f}s"
            rp = dest/(suffix+"_raw.png"); np = dest/(suffix+"_narrated.png")
            cv2.imwrite(str(rp), rawframe); cv2.imwrite(str(np), narrframe)
            examples.append({"run": runname, "audit_definition": key,
                             "target_run_elapsed_s": desired,
                             "event_run_elapsed_s": target, "video_frame_index": index,
                             "narrator_elapsed_s": displayed, "ocr_text": ocr,
                             "raw_image": str(rp.relative_to(ROOT)),
                             "narrated_image": str(np.relative_to(ROOT)),
                             "raw_video": d["raw_video"], "narrated_video": d["video"],
                             "raw_video_sha256": raw_hash, "narrated_video_sha256": narrated_hash,
                             "raw_image_sha256": sha(rp), "narrated_image_sha256": sha(np),
                             "alignment": "approximate via elapsed overlay; no shared packet frame ID"})
        assert sha(d['raw_video']) == raw_hash and sha(d['video']) == narrated_hash
        raw.release(); narrated.release()
    return examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video-samples', action='store_true',
                    help='Recompute nine optional qualitative raw/narrated still pairs. Without this flag, reuse prior sample metadata only if every associated input/output hash matches.')
    args = ap.parse_args()
    paths = sorted(LOGS.glob('*.json')); assert len(paths) == 24
    hashes = {}
    runs = []
    for path in paths:
        side = path.with_name(path.stem+'_timing.jsonl')
        for p in (path, side):
            hashes[str(p.relative_to(ROOT))] = sha(p)
        d = json.loads(path.read_text()); rows = d['log']
        s = [json.loads(line) for line in side.read_text().splitlines()]
        frames = {r['frame_id']: r for r in s if r.get('type') == 'frame'}
        run = {"run": path.stem, "method": path.stem.split('-')[0],
               "cadence": 'slow' if '-slow_' in path.stem else 'normal',
               "all_moving_decisions": sum(r['mode']!='stop' for r in rows),
               "hazard_present_moving_decisions": sum(r['mode']!='stop' and bool(hazard_input(r, frames)) for r in rows),
               "definitions": {}}
        configs = [('first_source_detection', 'first_source_detection', .05, False, False),
                   ('presence_transition_only', 'presence_transition_only', .05, False, False),
                   ('geometry_refresh_50mm', 'geometry_refresh', .05, False, False),
                   ('retained_blob_refresh_50mm', 'retained_blob_refresh', .05, False, False),
                   ('geometry_refresh_30mm', 'geometry_refresh', .03, False, False),
                   ('geometry_refresh_100mm', 'geometry_refresh', .1, False, False),
                   ('geometry_refresh_decision_clock', 'geometry_refresh', .05, True, False),
                   ('literal_hazard_field_50mm', 'geometry_refresh', .05, False, True)]
        for key, definition, threshold, decision_clock, literal in configs:
            run['definitions'][key] = audit_definition(rows, frames, definition, threshold, decision_clock, literal)
        literal_indices = {h['decision_index'] for h in run['definitions']['literal_hazard_field_50mm']['hits']}
        corrected_indices = {h['decision_index'] for h in run['definitions']['geometry_refresh_50mm']['hits']}
        run['literal_only_flags_removed_after_state_semantics_correction'] = sorted(literal_indices-corrected_indices)
        first = run['definitions']['first_source_detection']['events'][0]
        carry_event = next(r['t'] for r in s if r.get('type') == 'event' and r.get('text', '').startswith('carrying'))
        run['first_sensing_processed_minus_carry_start_s'] = first['source_processed']-carry_event
        runs.append(run)
    groups = {key: group(runs, key) for key in runs[0]['definitions']}
    expected = {'AEGIS': (1, 283, 1), 'Trust12': (13, 210, 4), 'Trust32': (7, 247, 2)}
    for method, exp in expected.items():
        g = groups['literal_hazard_field_50mm']['slow'][method]
        assert (g['flagged_moving_decisions'],g['hazard_present_moving_decisions'],g['runs_with_flagged_decision']) == exp
        assert g['minimum_command_estimated_separation_mm'] > 80
    for method, exp in {'AEGIS':(0,0), 'Trust12':(7,2), 'Trust32':(1,1)}.items():
        g = groups['geometry_refresh_50mm']['slow'][method]
        assert (g['flagged_moving_decisions'],g['runs_with_flagged_decision']) == exp
    if args.video_samples:
        examples, video_status = video_samples(runs), 'recomputed_from_source_videos'
    else:
        examples, video_status = preserved_video_samples(hashes)
    assert all(sha(ROOT/p)==h for p,h in hashes.items())
    result = {
        'status': 'post_hoc_temporal_association_audit_not_physical_intrusion_ground_truth',
        'definition': 'For hazard-present moving carry decisions, accepted semantic capture proxy predates the source-frame proxy of the latest logged hazard reappearance or centre/radius change exceeding 50 mm.',
        'denominator': 'hazard-present moving decisions, not all moving decisions or elapsed physical-motion time',
        'source_frame_join': 'Each geometric refresh is timestamped by its haz_frame_id joined to sensing JSONL, not by inference completion or controller decision time.',
        'hold_goal_reconstruction': 'In hold_goal, clr=None means current tracker absent; otherwise haz_frame_id joins the current source detection. The logged haz field itself is the cached blocking-destination hazard and cannot be used as current geometry.',
        'proposal_replication_warning': 'The proposed slow counts 1/283,13/210,7/247 are replicated only by interpreting every haz field literally, including hold_goal rows where haz is cached destination occupancy rather than current sensing. Reconstructing the latter from clr and haz_frame_id changes the counts to 0/283,7/210,1/247. Do not publish the literal-field counts as current-hazard or first-intrusion exposure.',
        'first_intrusion_warning': 'First sensor detection alone has no flagged motion in slow runs. Refreshes include changes to an existing selected disc and detection recovery; neither proves a new physical intrusion.',
        'controller_reset_warning': 'The controller retains its previous blob across missing detections; the reappearance-inclusive exploratory definition is deliberately broader. Retained-blob sensitivity is reported separately.',
        'uncertainty': 'Proxy timing is not exposure time; frame identifiers corroborate relative ordering but do not prove physical appearance or that the earlier image did not contain the object.',
        'ground_truth': 'No semantic truth, independently tracked robot motion, or physical collision risk is inferred.',
        'hold_rule': {'prior': .65, 'eta': .95, 'T_s': .4, 'threshold': .5,
                      'first_object_anchor': .0325,
                      'first_object_age_crossing_s': .4*math.log((.65-.0325)/(.65-.5)),
                      'repeated_object_limit_age_crossing_s': .4*math.log(.65/(.65-.5)),
                      'formula': 'T*log((P0-h)/(P0-Pstop)) if h<Pstop<P0; the clock starts at capture proxy.',
                      'conditions': 'fixed accepted evidence, present hazard, no relevant reset; unavailable anchor time evaluates to prior; no hazard outputs zero score/margin; accepted HUMAN directly holds regardless of score.',
                      'human_decay_caveat': 'The continuous score can decay after HUMAN, but the persistent HUMAN label independently holds in both AEGIS and Trust; this does not demonstrate a different release response.'},
        'groups': groups, 'runs': runs, 'video_examples': examples,
        'video_examples_status': video_status,
        'source_sha256': hashes, 'source_hashes_unchanged': True}
    (OUT/'first_detection_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    lines = [r'\begin{tabular}{lrrr}',r'\toprule',
             r'Method & Flagged / hazard-moving decisions & Runs & Min. separation (mm)\\',r'\midrule']
    for method in METHODS:
        g=groups['geometry_refresh_50mm']['slow'][method]
        minimum = '--' if g['minimum_command_estimated_separation_mm'] is None else f"{g['minimum_command_estimated_separation_mm']:.1f}"
        lines.append(f"{method} & {g['flagged_moving_decisions']}/{g['hazard_present_moving_decisions']} & "
                     f"{g['runs_with_flagged_decision']}/4 & {minimum}\\\\")
    lines.extend([r'\bottomrule',r'\end{tabular}',
                  '% Post hoc; the flag is evidence predating a logged geometry refresh, not verified first physical intrusion.'])
    (OUT/'first_detection_table.tex').write_text('\n'.join(lines)+'\n')
    summary=[]
    for key in groups:
        summary.append(f"{key}: "+str({m:(g['flagged_moving_decisions'],g['runs_with_flagged_decision']) for m,g in groups[key]['slow'].items()}))
    print('\n'.join(summary))
    print('video samples',len(examples),video_status,'hashes preserved',len(hashes))


if __name__ == '__main__':
    main()
