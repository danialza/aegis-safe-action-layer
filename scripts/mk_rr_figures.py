"""Rebuild Figures 6 and 7 (fig_rr_contrast, fig_rr_rgbd) at three panels per row.

The earlier versions packed five panels into one 1542 px row, so each frame was ~308 px
wide and the overlay (nominal path, executed path, sensed hazard disc) was unreadable in
print. Three panels per row at native 640 px doubles the linear resolution.

Frames are taken at instants read from each run's own per-tick log, so the caption times
are the robot's timestamps rather than eyeballed ones.

    python paper/figures/mk_rr_figures.py
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

EXP = os.path.expanduser("~/Ned3 Pro - Mujuco/vlm-codex/experiments")
OUT = os.path.expanduser("~/Ned3 Pro - Mujuco/paper/figures")

# The recorder tags every file 12 fps but does not always sustain it while the control loop
# runs, so the effective rate is calibrated per session against a landmark in that session's
# own log.  July-22 live: the hand's trailing edge in 05_hand_freeze lands at the logged
# "path clear" instant (minus the monitor's lag) at ~12 fps.  RGB-D session: the five logged
# HUMAN verdicts in rgbd_obstacle_hand coincide with visible skin only at ~11.53 fps, and
# 1126 frames / 97.7 s to delivery in rgbd_live gives the same figure.  Using 12 fps for the
# RGB-D videos would place every extracted frame ~4% (up to 3 s) late.
FPS_LIVE, FPS_RGBD = 12.0, 11.53
TOP_BAR = 88                    # the recorder draws its own clock here; crop it off
PANEL_W = 640                   # native frame width - no downscaling
BAR_H = 78                      # caption bar drawn under each panel
GAP = 8                         # gutter between panels

GREEN, BLUE, AMBER, RED = (60, 200, 60), (235, 150, 60), (30, 165, 235), (60, 60, 235)


def load(path):
    d = json.load(open(path))
    return d, d["log"]


def frame_at(cap, t, fps):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(t * fps))))
    ok, img = cap.read()
    if not ok:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n - 2))
        ok, img = cap.read()
    return img if ok else None


def tick_at(L, t):
    return min(L, key=lambda x: abs(x["t"] - t))


def panel(img, letter, t, title, sub, colour):
    """One annotated panel: scene on top, caption bar underneath (never covering it)."""
    img = img[TOP_BAR:, :]
    img = cv2.resize(img, (PANEL_W, int(img.shape[0] * PANEL_W / img.shape[1])),
                     interpolation=cv2.INTER_AREA)
    out = np.vstack([img, np.full((BAR_H, PANEL_W, 3), 22, np.uint8)])
    y0 = img.shape[0]
    cv2.putText(out, "(%s)" % letter, (12, y0 + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(out, "t = %.0f s" % t, (58, y0 + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(out, title, (168, y0 + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.60, colour, 2, cv2.LINE_AA)
    cv2.putText(out, sub, (12, y0 + 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (195, 195, 195), 1, cv2.LINE_AA)
    cv2.rectangle(out, (0, 0), (PANEL_W - 1, out.shape[0] - 1), (70, 70, 70), 1)
    return out


def row(panels):
    h = max(p.shape[0] for p in panels)
    padded = []
    for i, p in enumerate(panels):
        p = cv2.copyMakeBorder(p, 0, h - p.shape[0], 0, 0 if i == len(panels) - 1 else GAP,
                               cv2.BORDER_CONSTANT, value=(255, 255, 255))
        padded.append(p)
    return np.hstack(padded)


def build(video, log, moments, letters, fps):
    cap = cv2.VideoCapture(video)
    _, L = load(log)
    out = []
    for (t, title, sub, col), ltr in zip(moments, letters):
        img = frame_at(cap, t, fps)
        if img is None:
            raise SystemExit("no frame at t=%s in %s" % (t, video))
        if sub is None:
            x = tick_at(L, t)
            clr = x.get("clr")
            sub = ("clearance = %+.1f cm" % (clr * 100)) if clr is not None else "no hazard tracked"
        out.append(panel(img, ltr, t, title, sub, col))
    cap.release()
    return row(out)


def main():
    live = EXP + "/2026-07-22_live"

    # ---- Figure 6: one policy, opposite behaviour under the two verdicts
    top = build(live + "/videos/03_static_obstacle_paths.mp4",
                live + "/logs/03_static_obstacle.json",
                [(25.0, "verdict OBJECT -> re-route", None, GREEN),
                 (33.0, "detour arc around the hazard", None, GREEN),
                 (44.0, "delivered", None, GREEN)],
                "abc", FPS_LIVE)
    bot = build(live + "/videos/05_hand_freeze_paths.mp4",
                live + "/logs/05_hand_freeze.json",
                [(23.0, "verdict HUMAN -> protective stop", "commanded tool motion = 0.0 mm", RED),
                 (33.0, "still frozen, hand present", "commanded tool motion = 0.0 mm", RED),
                 (39.5, "hand withdrawn -> resumes", "carry resumed, delivered at t = 46 s", GREEN)],
                "def", FPS_LIVE)
    w = max(top.shape[1], bot.shape[1])
    pad = lambda a: cv2.copyMakeBorder(a, 0, 0, 0, w - a.shape[1], cv2.BORDER_CONSTANT,
                                       value=(255, 255, 255))
    fig6 = np.vstack([pad(top),
                      np.full((GAP * 2, w, 3), 255, np.uint8),
                      pad(bot)])
    cv2.imwrite(OUT + "/fig_rr_contrast.png", fig6)
    print("fig_rr_contrast.png %dx%d" % (fig6.shape[1], fig6.shape[0]))

    # ---- Figure 7: RGB-D-fused carry with the live overlay.
    # The obstacle+hand run was recorded without the path overlay and its frame timebase
    # could not be reconciled with the control log, so the depth-confirmed routing is shown
    # from the overlay-recorded RGB-D run instead; the route-then-freeze combined carry is
    # reported numerically in the text and Table 7, where it is log-supported.
    rgbd = EXP + "/expriment codex 22 jul"
    fig7 = build(rgbd + "/videos/rgbd_live_20260722_150347_paths.mp4",
                 rgbd + "/logs/rgbd_live_20260722_150347.json",
                 [(29.6, "depth-confirmed object -> re-route", None, GREEN),
                  (34.2, "detour held around the footprint", None, GREEN),
                  (82.8, "closest approach, still positive", None, AMBER)],
                 "abc", FPS_RGBD)
    cv2.imwrite(OUT + "/fig_rr_rgbd.png", fig7)
    print("fig_rr_rgbd.png %dx%d" % (fig7.shape[1], fig7.shape[0]))


if __name__ == "__main__":
    main()
