"""Restore apparatus context and document the current calibration, offline only.

The photograph is copied unchanged. The camera image is an unannotated decoded
video frame. Plot elements are schematic/calibration metadata, never invented
physical measurements. No experimental log or video is modified.
"""
from pathlib import Path
import hashlib
import json
import shutil

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
SOURCE = ROOT / "source_received/Danial___Safety_Awareness_Robot"
SESSION = ROOT.parent.parent / "vlm-codex/experiments/session_2026-09-18"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    FIG.mkdir(exist_ok=True)
    photo = SOURCE / "figures/fig_setup_photo.png"
    photo_copy = FIG / "laboratory_apparatus.png"
    if photo.exists():
        shutil.copy2(photo, photo_copy)
    assert photo_copy.exists()
    cal_source = SESSION / "calibration/free_slab_calibration.json"
    cal_copy = ROOT / "analysis/setup_calibration_record.json"
    if cal_source.exists():
        shutil.copy2(cal_source, cal_copy)
    cal = json.loads(cal_copy.read_text())
    active = json.loads((ROOT / "provenance_code/calibration.json").read_text())
    assert cal["n"] == active["calibration_quality"]["points"] == 8
    assert abs(cal["mean_residual_m"] - active["calibration_quality"]["mean_residual_m"]) < 1e-12
    run_id = "AEGIS-normal_toB_1"
    run_file = ROOT / f"data/timed_margin_compare/logs/{run_id}.json"
    run = json.loads(run_file.read_text())
    raw = Path(run["raw_video"])
    frame_path = FIG / "primary_camera_frame.png"
    frame_index = 270
    manifest_path = ROOT / "analysis/setup_assets_manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if raw.exists():
        cap = cv2.VideoCapture(str(raw))
        assert cap.isOpened()
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        cap.release()
        assert ok and cv2.imwrite(str(frame_path), frame)
        video_meta = {"source": str(raw), "source_sha256": sha(raw), "source_run": run_id,
                      "zero_based_frame_index": frame_index, "container_fps": fps,
                      "container_frame_count": total,
                      "clock_note": "Frame index identifies an illustration, not a synchronized controller event or exposure timestamp.",
                      "transformation": "Decoded raw frame saved as PNG; no cropping, retouching, or overlay."}
    else:
        assert frame_path.exists() and previous.get("camera_frame")
        video_meta = previous["camera_frame"]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.titlesize": 12, "axes.labelsize": 11,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    uv = np.array(cal["pixel_uv"])
    xy = np.array(cal["world_xy"])
    fig, axs = plt.subplots(1, 2, figsize=(8.4, 3.8))
    ax = axs[0]
    ax.scatter(uv[:, 0], uv[:, 1], s=48, color="#2366a2", zorder=3)
    for k, (u, v) in enumerate(uv, 1):
        ax.annotate(str(k), (u, v), xytext=(5, -11), textcoords="offset points", fontsize=9)
    ax.set(xlim=(110, 510), ylim=(355, 230), xlabel="Image u (pixels)", ylabel="Image v (pixels)",
           title="(a) Retained marker centroids")
    ax = axs[1]
    ax.add_patch(Rectangle((-.14, .22), .28, .08, facecolor="#e7f0f7", edgecolor="#93b5d0",
                           linestyle="--", zorder=0, label="Retained calibration span"))
    ax.plot([-.14, .14], [.21, .31], "--", color="#25834d", lw=1.6,
            label="Nominal A-B segment", zorder=1)
    ax.scatter(xy[:, 1], xy[:, 0], s=42, color="#2366a2", label="8 calibration positions", zorder=3)
    ax.scatter([.14, -.14], [.31, .21], s=96, color="#25834d", marker="*", zorder=4)
    ax.annotate("A", (.14, .31), xytext=(7, 3), textcoords="offset points", color="#156535", fontweight="bold")
    ax.annotate("B", (-.14, .21), xytext=(-15, -4), textcoords="offset points", color="#156535", fontweight="bold")
    ax.scatter([-.14], [.26], marker="x", color="#9b6b2f", s=52, zorder=4, label="Omitted fit observation")
    ax.set(xlim=(-.185, .185), ylim=(.195, .325), xlabel="Base-frame y (m)", ylabel="Base-frame x (m)",
           title="(b) Placement positions and endpoints")
    ax.set_xticks([-.14, 0, .14])
    ax.set_yticks([.21, .26, .31])
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=.18)
    fig.legend(*axs[1].get_legend_handles_labels(), loc="lower center", ncol=2,
               frameon=False, fontsize=9, bbox_to_anchor=(.5, -.005))
    fig.subplots_adjust(left=.085, right=.975, top=.88, bottom=.27, wspace=.36)
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"calibration_geometry.{ext}", dpi=220, facecolor="white")
    plt.close(fig)
    manifest = {
        "apparatus_photo": {"source": str(photo), "sha256": sha(photo_copy),
                            "original_exif_datetime": "2026:07:30 13:11:23",
                            "role": "Representative historical apparatus photograph; not September scene ground truth."},
        "camera_frame": {**video_meta, "png_sha256": sha(frame_path)},
        "calibration_record": {"source": str(cal_source), "sha256": sha(cal_copy),
                               "role": "Recorded September fitting inputs; in-sample fit only, not external validation."},
        "figures": {p.name: sha(p) for p in FIG.glob("calibration_geometry.*")},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
