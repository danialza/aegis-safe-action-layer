"""Figure 6: the RGB-D carry, with the depth-confirmation instants taken from the log.

Source: paper/figure_sources/fig6_rgbd_carry.{mp4,json}
  (= rgbd_flexible_20260722_151226_paths, retimed to its measured 11.53 fps so that video
   time equals log time to within the offset handled below.)

`sensor_source` in the log is the fusion verdict of reactive_run.fuse_ws_detections: "rgb"
means the colour channel alone proposed the hazard, "rgbd" means a depth detection fell
within DEPTH_MATCH_DISTANCE_M of it and the radius was taken as the max of the two.  The
transitions to "rgbd" are therefore the moments this figure is about, and they are 22.50 ->
25.02 and 42.61 -> 43.84 -- half a second later than the neighbouring frames, which look
identical but are colour-only.  Panels are placed on the confirmed ticks.

    python paper/figures/mk_fig6_rgbd.py
"""
from __future__ import annotations

import importlib.util
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("f5", os.path.join(HERE, "mk_fig5_contrast.py"))
f5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f5)
mk = f5.mk

SRC = os.path.join(HERE, "..", "figure_sources", "fig6_rgbd_carry")
# log_t(i) = i/FPS + T0, fitted against the clock the recorder burns into each frame (see
# mk_fig5_contrast for why the frames/duration shortcut is wrong).  The recording starts
# 0.64 s after the run does.
FPS, T0 = 11.622, 0.64


def frame_at(cap, t):
    i = max(0, int(round((t - T0) * FPS)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, img = cap.read()
    return img if ok else None

GREEN, AMBER, RED = mk.GREEN, mk.AMBER, mk.RED
BLUE, GREY = (235, 150, 60), (170, 170, 170)

MOMENTS = [
    (22.0, "obstacle placed, path straight", "colour proposes; depth has not matched yet", GREY),
    (23.8, "no admissible route -> hold",    None,                                         AMBER),
    (25.0, "depth confirms colour -> detour", "colour-depth agreement 5.4 cm",             GREEN),
    (43.8, "depth confirms again, 6 cm",      "colour-depth agreement 5.5 cm",             GREEN),
    (44.4, "detour widened to 7 cm",          None,                                        GREEN),
    (57.0, "delivered",                       "minimum clearance over the carry +2.9 cm",  GREEN),
]


def main():
    cap = cv2.VideoCapture(SRC + ".mp4")
    L = json.load(open(SRC + ".json"))["log"]

    panels = []
    for (t, title, sub, col), ltr in zip(MOMENTS, "abcdef"):
        img = frame_at(cap, t)
        if img is None:
            raise SystemExit("no frame at t=%.1f" % t)
        if sub is None:
            tick = mk.tick_at(L, t)
            # the log covers the carry only (22.5-48.6 s); never quote a clearance for a
            # panel outside that window, where the nearest tick is seconds away.
            sub = ("tool-obstacle clearance = %+.1f cm" % (tick["clr"] * 100)
                   if abs(tick["t"] - t) < 0.5 and tick.get("clr") is not None
                   else "outside the logged carry window")
        panels.append(f5.panel(img, ltr, t, title, sub, col, tfmt="%.1f"))
    cap.release()

    per = f5.PER_ROW
    rows = [mk.row(panels[i:i + per]) for i in range(0, len(panels), per)]
    w = max(r.shape[1] for r in rows)
    pad = lambda a: cv2.copyMakeBorder(a, 0, 0, 0, w - a.shape[1], cv2.BORDER_CONSTANT,
                                       value=(255, 255, 255))
    gap = np.full((mk.GAP * 2, w, 3), 255, np.uint8)
    stack = [pad(rows[0])]
    for r in rows[1:]:
        stack += [gap, pad(r)]
    fig = np.vstack(stack)

    cv2.imwrite(os.path.join(HERE, "fig_rr_rgbd.png"), fig)
    print("fig_rr_rgbd.png %dx%d  (%d panels, %d per row)" % (fig.shape[1], fig.shape[0],
                                                              len(panels), per))
    print("  placed at %.1f cm -> %.1f cm tall" % (f5.PLACED_CM,
                                                   f5.PLACED_CM * fig.shape[0] / w))


if __name__ == "__main__":
    main()
