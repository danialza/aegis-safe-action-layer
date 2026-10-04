"""Post-hoc numerical checks of 24 primary hardware runs; no robot imports.

Creates additional_analyses.json, clearly scoped supplementary LaTeX tables,
and a checksum manifest. All trial measurements and source files are read-only.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
from zoneinfo import ZoneInfo

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
DATA = PACKAGE / "data/timed_margin_compare/logs"
CAL_ORIGINAL = PACKAGE.parent.parent / "vlm-codex/experiments/session_2026-09-18/calibration/free_slab_calibration.json"
CAL_COPY = HERE / "calibration_correspondences_source.json"
METHODS = ("AEGIS", "Trust12", "Trust32")
RATES = ("normal", "slow")
CATEGORIES = ("moving_decision", "belief_hold", "geometry_hold", "human_hold", "destination_hold",
              "depth_only_hold", "evidence_hold", "other_hold")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values):
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "min": min(values), "max": max(values),
            "sample_sd": statistics.stdev(values) if len(values) > 1 else None}


def category(record):
    """Recorded final reason, not inferred physiological or mechanical cause.

    The deployed runner resolves precedence before logging: destination guard
    bypasses downstream branches; depth-only can overwrite other final reasons.
    Respect that final logged reason rather than double-counting latent flags.
    """
    if record["mode"] != "stop":
        assert record.get("stop_reason") is None
        return "moving_decision"
    reason = record.get("stop_reason")
    if reason == "goal_occupied":
        return "destination_hold"
    if reason == "depth_only":
        return "depth_only_hold"
    if isinstance(reason, str) and reason.startswith("evidence:"):
        return "evidence_hold"
    return {"human": "human_hold", "belief>=P_STOP": "belief_hold", "geometry": "geometry_hold"}.get(reason, "other_hold")


def fit_homography(uv, xy):
    matrix, _ = cv2.findHomography(np.asarray(uv, np.float32), np.asarray(xy, np.float32), method=0)
    assert matrix is not None
    return matrix


def predict(matrix, uv):
    points = np.column_stack((np.asarray(uv, float), np.ones(len(uv)))) @ matrix.T
    return points[:, :2] / points[:, 2:3]


def calibration():
    if CAL_ORIGINAL.exists():
        if not CAL_COPY.exists() or sha(CAL_COPY) != sha(CAL_ORIGINAL):
            shutil.copy2(CAL_ORIGINAL, CAL_COPY)
    record = json.loads(CAL_COPY.read_text())
    uv = np.asarray(record["pixel_uv"], float)
    xy = np.asarray(record["world_xy"], float)
    assert len(uv) == len(xy) == 8
    matrix = fit_homography(uv, xy)
    fitted = predict(matrix, uv)
    residuals = np.linalg.norm(fitted - xy, axis=1) * 1000
    retained = []
    for i in range(8):
        keep = [j for j in range(8) if j != i]
        predicted = predict(fit_homography(uv[keep], xy[keep]), uv[[i]])[0]
        retained.append({"retained_point": i + 1, "pixel_uv": uv[i].tolist(), "world_xy_m": xy[i].tolist(),
                         "in_sample_residual_mm": float(residuals[i]), "loo_prediction_xy_m": predicted.tolist(),
                         "loo_prediction_error_mm": float(np.linalg.norm(predicted - xy[i]) * 1000)})
    assert abs(statistics.mean(residuals) / 1000 - record["mean_residual_m"]) < 1e-6
    return {"method": "OpenCV findHomography(method=0), float32 inputs as in deployed TableCalib.fit; refit seven retained points and predict the held-out eighth",
            "opencv_version": cv2.__version__, "retained_points": 8,
            "in_sample_mm": describe([float(x) for x in residuals]),
            "leave_one_out_mm": describe([r["loo_prediction_error_mm"] for r in retained]),
            "per_point": retained, "dropped_record": record["dropped_outlier"],
            "ninth_point_pixel_coordinate_available": False,
            "limitations": ["Cross-validation of the retained correspondences, not independent physical ground truth or an uncertainty bound on obstacle clearance.",
                            "The omitted correspondence's pixel coordinate is absent from this retained record; a nine-point refit cannot be reconstructed from it.",
                            "The recorded 3.016 mm omission residual and data-dependent omission do not establish physical slip or another causal explanation; none is invented.",
                            "LOO is conditional on the eight retained points and does not account for the preceding data-dependent point selection."]}


def geometry_for_run(log):
    # Work from actual gate geometry only, not cached destination-guard hazards.
    # Unmatched depth hazards are stop-only fallbacks, not measurements of the
    # same object footprint; keep their count and a broad sensitivity estimate.
    accepted = [r for r in log if r.get("haz") is not None and r.get("ev_verdict") == "object"
                and r.get("state") != "hold_goal" and not r.get("depth_only")]
    seen = set()
    unique = []
    for r in accepted:
        key = r.get("haz_frame_id")
        assert key is not None
        if key not in seen:
            unique.append(r)
            seen.add(key)
    assert unique
    values = np.asarray([r["haz"] for r in unique], float)
    representative = np.median(values, axis=0)
    q25, q75 = np.quantile(values, [.25, .75], axis=0)
    broad = [r["haz"] for r in log if r.get("haz") is not None and r.get("ev_verdict") == "object"
             and r.get("state") != "hold_goal"]
    return {"accepted_decision_rows": len(accepted), "unique_hazard_frames": len(unique),
            "representative_xyz_radius_m": representative.tolist(),
            "within_run_iqr_xyz_radius_mm": ((q75 - q25) * 1000).tolist(),
            "within_run_min_xyz_radius_m": np.min(values, axis=0).tolist(),
            "within_run_max_xyz_radius_m": np.max(values, axis=0).tolist(),
            "broad_object_nongoal_including_depth_median_m": np.median(broad, axis=0).tolist(),
            "all_hazard_rows_median_m": np.median([r["haz"] for r in log if r.get("haz") is not None], axis=0).tolist(),
            "excluded_depth_only_rows": sum(r.get("haz") is not None and r.get("ev_verdict") == "object"
                                             and r.get("state") != "hold_goal" and r.get("depth_only", False) for r in log)}


def exact_sign(differences):
    positives = sum(d > 1e-9 for d in differences)
    negatives = sum(d < -1e-9 for d in differences)
    ties = len(differences) - positives - negatives
    n = positives + negatives
    p = min(1., 2 * sum(math.comb(n, j) for j in range(min(positives, negatives) + 1)) / (2 ** n)) if n else 1.
    return {"positive": positives, "negative": negatives, "ties": ties, "n_non_tied": n,
            "two_sided_exact_sign_reference_p": p}


def write_table(name, caption, label, columns, header, rows, small=True):
    lines = [r"\begin{table}[H]", r"\centering", r"\small" if small else r"\footnotesize",
             r"\caption{" + caption + "}", r"\label{" + label + "}",
             r"\begin{tabular}{" + columns + "}", r"\toprule", header + r" \\", r"\midrule"]
    lines += [" & ".join(str(x) for x in row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (HERE / name).write_text("\n".join(lines) + "\n")


def build():
    inputs = sorted(DATA.glob("*.json")) + sorted(DATA.glob("*.jsonl"))
    assert len(inputs) == 48
    before = {str(p): sha(p) for p in inputs}
    previous = json.loads((HERE / "hardware_summary.json").read_text())
    old_runs = {r["run"]: r for r in previous["all_included_records"] if r["campaign"] == "timed_margin_compare"}
    results = []
    for path in sorted(DATA.glob("*.json")):
        record = json.loads(path.read_text())
        name = path.stem
        old = old_runs[name]
        log = record["log"]
        side = [json.loads(line) for line in path.with_name(name + "_timing.jsonl").read_text().splitlines()]
        header = next(r for r in side if r.get("type") == "header")
        events = [r for r in side if r.get("type") == "event"]
        start = next(r["t"] for r in events if r.get("text", "").startswith("carrying"))
        finish = next(r["t"] for r in reversed(events) if r.get("text") == "object delivered at goal")
        offset = header["wall"] - header["perf"]
        durations = {k: 0. for k in CATEGORIES}
        counts = Counter(category(r) for r in log)
        reason_counts = Counter(str(r.get("stop_reason")) for r in log if r["mode"] == "stop")
        intervals = []
        for i, (r, nxt) in enumerate(zip(log[:-1], log[1:])):
            dt = nxt["t_decision"] - r["t_decision"]
            assert dt > 0
            cat = category(r)
            durations[cat] += dt
            intervals.append({"decision_index": i, "start_perf_s": r["t_decision"],
                              "end_perf_s": nxt["t_decision"], "duration_s": dt, "category": cat,
                              "recorded_stop_reason": r.get("stop_reason")})
        initial_gap = log[0]["t_decision"] - start
        tail_gap = finish - log[-1]["t_decision"]
        assert initial_gap >= 0 and tail_gap >= 0
        duration = finish - start
        reconciliation = initial_gap + sum(durations.values()) + tail_gap
        assert abs(reconciliation - duration) < 1e-7
        assert abs(duration - old["carry_to_delivery_s"]) < 1e-9
        assert counts["other_hold"] == 0
        results.append({"run": name, "method": old["method"], "rate": old["rate"],
                        "direction": old["direction"], "repetition": int(name.rsplit("_", 1)[1]),
                        "source": str(path), "source_sha256": sha(path),
                        "header_perf_s": header["perf"], "header_wall_unix_s": header["wall"],
                        "wall_minus_perf_s": offset,
                        "header_utc": datetime.fromtimestamp(header["wall"], timezone.utc).isoformat(),
                        "header_europe_london": datetime.fromtimestamp(header["wall"], ZoneInfo("Europe/London")).isoformat(),
                        "carrying_utc": datetime.fromtimestamp(start + offset, timezone.utc).isoformat(),
                        "delivery_utc": datetime.fromtimestamp(finish + offset, timezone.utc).isoformat(),
                        "delivery_wall_unix_s": finish + offset,
                        "carry_to_delivery_s": duration,
                        "decision_interval_occupancy_s": durations,
                        "decision_category_counts": dict(counts), "final_stop_reason_counts": dict(reason_counts),
                        "initial_unassigned_gap_s": initial_gap, "final_unassigned_gap_s": tail_gap,
                        "reconciliation_residual_s": reconciliation - duration,
                        "decision_intervals": intervals,
                        "geometry": geometry_for_run(log),
                        "minimum_separation_mm": old["min_command_estimated_edge_separation_mm"]})
    chronology = sorted(results, key=lambda r: r["header_wall_unix_s"])
    assert [r["run"] for r in chronology] == [r["run"] for r in sorted(results, key=lambda r: r["header_perf_s"])]
    for i, r in enumerate(chronology, 1):
        r["chronological_index"] = i
    cells = []
    for rate in RATES:
        for method in METHODS:
            rr = [r for r in results if r["rate"] == rate and r["method"] == method]
            assert len(rr) == 4
            cells.append({"rate": rate, "method": method,
                          "mean_carry_to_delivery_s": statistics.mean(r["carry_to_delivery_s"] for r in rr),
                          "mean_initial_gap_s": statistics.mean(r["initial_unassigned_gap_s"] for r in rr),
                          "mean_final_gap_s": statistics.mean(r["final_unassigned_gap_s"] for r in rr),
                          "mean_occupancy_s": {cat: statistics.mean(r["decision_interval_occupancy_s"][cat] for r in rr) for cat in CATEGORIES},
                          "pooled_decision_counts": dict(sum((Counter(r["decision_category_counts"]) for r in rr), Counter()))})
    points = np.asarray([r["geometry"]["representative_xyz_radius_m"] for r in results])
    broad = np.asarray([r["geometry"]["broad_object_nongoal_including_depth_median_m"] for r in results])
    blocks = []
    for rate in RATES:
        for direction in ("A", "B"):
            for repetition in (1, 2):
                block = {r["method"]: r for r in results if (r["rate"], r["direction"], r["repetition"]) == (rate, direction, repetition)}
                assert set(block) == set(METHODS)
                blocks.append({"rate": rate, "direction": direction, "repetition": repetition,
                               "run_ids": {method: block[method]["run"] for method in METHODS},
                               "separation_difference_AEGIS_minus_Trust12_mm": block["AEGIS"]["minimum_separation_mm"] - block["Trust12"]["minimum_separation_mm"],
                               "separation_difference_AEGIS_minus_Trust32_mm": block["AEGIS"]["minimum_separation_mm"] - block["Trust32"]["minimum_separation_mm"]})
    sign_results = {method: exact_sign([b[f"separation_difference_AEGIS_minus_{method}_mm"] for b in blocks]) for method in ("Trust12", "Trust32")}
    output = {
        "scope": "Post-hoc additional analyses of the unchanged 24 primary hardware transports; no robot code imported or executed",
        "calibration": calibration(),
        "chronology": {"source": "JSONL header wall/perf pair; times derived without filesystem modification times",
                       "display_timezone": "UTC with additional Europe/London conversion; this does not infer camera hardware clock timezone",
                       "first_header_utc": chronology[0]["header_utc"],
                       "last_header_utc": chronology[-1]["header_utc"],
                       "last_delivery_utc": max(r["delivery_utc"] for r in results),
                       "first_header_to_last_header_min": (chronology[-1]["header_wall_unix_s"] - chronology[0]["header_wall_unix_s"]) / 60,
                       "first_header_to_last_delivery_min": (max(r["delivery_wall_unix_s"] for r in results) - chronology[0]["header_wall_unix_s"]) / 60,
                       "order": [r["run"] for r in chronology],
                       "interpretation": "Order was not randomized. Short elapsed session duration does not establish absence of fatigue, lighting drift or operator confounding."},
        "stopped_decision_interval_analysis": {
            "definition": "For each consecutive decision pair, assign t[i+1]-t[i] to the earlier decision's final recorded mode/reason. Intervals are mutually exclusive and cover first-to-last decision only.",
            "precedence": "Use the final logged stop_reason; destination guard bypasses later branches and depth-only can overwrite downstream reasons. Other latent conditions are not counted again.",
            "unassigned_tail": "Delivery minus last decision is left unassigned because it includes execution of the last command, final checks and placement without an intermediate decision label.",
            "limitations": "Software decision-state occupancy, not measured robot standstill or physical stopping time. Movement can continue after a hold request. Durations include processing, sleep and communication waits.",
            "cells": cells},
        "geometry": {
            "definition": "For each run, componentwise median of hazard x,y,r on object-verdict, non-destination-hold, non-depth-only rows, taking the earliest eligible decision per unique hazard frame. Across-run sample SD (ddof=1) gives equal weight to runs.",
            "representative_center_x_mm": describe((points[:, 0] * 1000).tolist()),
            "representative_center_y_mm": describe((points[:, 1] * 1000).tolist()),
            "representative_radius_mm": describe((points[:, 2] * 1000).tolist()),
            "broad_object_non_goal_medians_including_depth_sample_sd_mm": (np.std(broad, axis=0, ddof=1) * 1000).tolist(),
            "broad_radius_min_max_mm": [float(broad[:, 2].min() * 1000), float(broad[:, 2].max() * 1000)],
            "limitations": "A repeatability description of internal tracked geometry, not independent obstacle-placement ground truth. Operator motion, occlusion, track association and frame selection can affect it; estimates are not a camera-accuracy or clearance uncertainty bound."},
        "nominal_matched_blocks": {"definition": "Match method runs by rate, direction and filename repetition suffix, giving eight nominal blocks. These are not randomized independent paired trials.",
                                   "blocks": blocks, "sign_reference": sign_results,
                                   "limitations": "Two-sided binomial sign reference assumes independent equiprobable signs after removing ties. Chronological nonrandomized data do not establish that null model; p values are descriptive assumption-dependent references, not calibrated significance, causal proof or a remedy for low replication."},
        "runs": chronology,
    }
    (HERE / "additional_analyses.json").write_text(json.dumps(output, indent=2) + "\n")
    write_table("additional_stop_table.tex",
                "Software decision-interval occupancy in seconds, averaged over four runs per cell. Each interval is assigned to its earlier decision's final recorded reason. These are not measured robot standstill times. The unassigned tail includes final command execution and placement; totals include the small initial gap and reproduce carry-to-delivery time. Evidence-error and other-hold categories are zero in every cell.",
                "tab:decision-occupancy", "llrrrrrrrr",
                r"Setting & Method & Move & Score & Geom. & Human & Goal & Depth & Tail & Total",
                [[c["rate"].capitalize(), c["method"], *[f"{c['mean_occupancy_s'][k]:.2f}" for k in ("moving_decision", "belief_hold", "geometry_hold", "human_hold", "destination_hold", "depth_only_hold")],
                  f"{c['mean_final_gap_s']:.2f}", f"{c['mean_carry_to_delivery_s']:.2f}"] for c in cells], small=False)
    write_table("additional_chronology_table.tex",
                "Chronology reconstructed from JSONL header wall/performance-clock pairs, not file modification times. Times are UTC on 18 September 2026. The study order was not randomized. The last column is the recorded delivery event, not an independently verified physical release time.",
                "tab:run-chronology", "rlllrrr",
                r"Order & Setting & Method & To & Rep. & Header (UTC) & Delivery (UTC)",
                [[r["chronological_index"], r["rate"].capitalize(), r["method"], r["direction"], r["repetition"],
                  r["header_utc"][11:19], r["delivery_utc"][11:19]] for r in chronology])
    write_table("additional_calibration_table.tex",
                "Retained-point calibration check. Each leave-one-out (LOO) fit uses the other seven retained correspondences. Errors are relative to robot-specified placement coordinates and do not constitute independent physical ground truth. The omitted ninth pixel correspondence is unavailable in the retained record, so it is not reconstructed.",
                "tab:calibration-loo", "rrr rr",
                r"Point & $x$ (m) & $y$ (m) & In-sample (mm) & LOO (mm)",
                [[p["retained_point"], f"{p['world_xy_m'][0]:.2f}", f"{p['world_xy_m'][1]:.2f}",
                  f"{p['in_sample_residual_mm']:.3f}", f"{p['loo_prediction_error_mm']:.3f}"] for p in output["calibration"]["per_point"]])
    write_table("additional_geometry_table.tex",
                "Internal geometry repeatability: per-run componentwise medians over unique hazard frames during object-verdict, non-destination-hold, non-depth-only decisions. The first eligible row is retained for each frame. These are tracked estimates, not independently measured object positions.",
                "tab:geometry-repeatability", "lllrrrrr",
                r"Setting & Method & To & Rep. & Frames & $x$ (mm) & $y$ (mm) & $r$ (mm)",
                [[r["rate"].capitalize(), r["method"], r["direction"], r["repetition"], r["geometry"]["unique_hazard_frames"],
                  *[f"{x * 1000:.2f}" for x in r["geometry"]["representative_xyz_radius_m"]]] for r in chronology], small=False)
    sign_caption = "Separation differences within eight nominal rate--direction--repetition blocks (AEGIS minus reference). "
    sign_caption += "Two-sided exact sign reference values are " + "; ".join(
        f"{sign_results[m]['two_sided_exact_sign_reference_p']:.7f} versus {m} "
        f"({sign_results[m]['positive']} positive, {sign_results[m]['negative']} negative)" for m in ("Trust12", "Trust32")) + ". "
    sign_caption += "These are post-hoc, assumption-dependent binomial references; nonrandomized session data do not establish independent equiprobable signs or causal significance."
    write_table("additional_sign_table.tex", sign_caption,
                "tab:nominal-pairs", "llrrr",
                r"Setting & To & Rep. & AEGIS--Trust12 (mm) & AEGIS--Trust32 (mm)",
                [[b["rate"].capitalize(), b["direction"], b["repetition"],
                  f"{b['separation_difference_AEGIS_minus_Trust12_mm']:.3f}", f"{b['separation_difference_AEGIS_minus_Trust32_mm']:.3f}"] for b in blocks])
    assert all(sha(Path(path)) == digest for path, digest in before.items())
    assert all(abs(c["mean_carry_to_delivery_s"] - next(x for x in previous["primary_cells"] if x["rate"] == c["rate"] and x["method"] == c["method"])["carry_to_delivery_s"]["mean"]) < 1e-9 for c in cells)
    manifest = {"script": str(Path(__file__)), "script_sha256": sha(Path(__file__)),
                "source_log_hashes": before, "source_logs_unchanged": True,
                "calibration_source_original": str(CAL_ORIGINAL), "calibration_source_sha256": sha(CAL_COPY),
                "outputs": {p.name: sha(p) for p in [HERE / "additional_analyses.json", *sorted(HERE.glob("additional_*_table.tex"))]},
                "all_24_primary_runs_retained": True, "all_primary_duration_means_reproduced": True,
                "decision_interval_reconciliation_max_abs_s": max(abs(r["reconciliation_residual_s"]) for r in results)}
    (HERE / "additional_analyses_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"calibration_in_sample_mm": output["calibration"]["in_sample_mm"],
                      "calibration_loo_mm": output["calibration"]["leave_one_out_mm"],
                      "stop_cells": cells, "chronology": output["chronology"],
                      "geometry": output["geometry"], "sign_reference": sign_results}, indent=2))


if __name__ == "__main__":
    build()
