"""Figure 5: one carry, both verdicts, eight moments chosen from the run itself.

Replaces the earlier two-run contrast (03_static_obstacle + 05_hand_freeze) with a single
continuous carry in which the verdict alternates between HUMAN and OBJECT. Showing one run
is the stronger claim: nothing at all differs between the panels except what the monitor
says the intruder is.

Source: paper/figure_sources/fig5_verdict_contrast.{mp4,json}
  (= rgbd_obstacle_hand_20260722_151705_paths, retimed to its measured 11.57 fps so that
   video time equals log time; the panel times below are therefore the robot's own clock.)

The recorder burns its status line into the top 90 px; that strip is cropped and replaced by
our own caption bar so the figure carries one set of labels, not two.

    python paper/figures/mk_fig5_contrast.py
"""
from __future__ import annotations

import importlib.util
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mk", os.path.join(HERE, "mk_rr_figures.py"))
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)
mk.TOP_BAR = 90                      # this session's burned-in header is 90 px, not 88

SRC = os.path.join(HERE, "..", "figure_sources", "fig5_verdict_contrast")

# Frame index -> the run's own clock.  Dividing the frame count by the time-to-delivery (the
# first attempt) is wrong twice over: it assumes the recording starts at log t=0, which it
# does not, and any error in that assumption is absorbed into the rate.  Both constants are
# instead fitted against the clock the recorder burns into each frame, read at two widely
# separated frames and checked at two more.  log_t(i) = i/FPS + T0.
FPS, T0 = 11.607, 0.51


def frame_at(cap, t):
    i = max(0, int(round((t - T0) * FPS)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, img = cap.read()
    return img if ok else None

GREEN, AMBER, RED = mk.GREEN, mk.AMBER, mk.RED
GREY = (170, 170, 170)

# (time, title, sub-caption, colour).  sub=None -> filled from the log's own clearance.
MOMENTS = [
    (14.4, "nominal straight carry",   "no intruder on the line yet",         GREY),
    (21.6, "HUMAN -> protective stop", "commanded tool motion = 0.0 mm",      RED),
    # 26.0 is the logged "path clear"; by 27.0 the resumption is visible as the green
    # executed trail restarting at S, which is what a reader can actually check.  A panel at
    # 26.0 is indistinguishable from (a).
    (27.0, "hand withdrawn -> resumes", "green trail restarts at S",           GREEN),
    (53.9, "OBJECT -> detour, 4 cm",   None,                                  GREEN),
    (70.0, "verifying clear 4/8",      "destination occupied: positive proof", AMBER),
    # 72.9 is the logged re-route, but the overlay still shows the preceding HOLD at that
    # frame; 73.2 is the first frame on which the 7 cm detour is actually drawn.
    (73.2, "OBJECT -> detour, 7 cm",   None,                                  GREEN),
    (79.5, "OBJECT -> detour, 5 cm",   None,                                  GREEN),
    (89.2, "HUMAN -> protective stop", "commanded tool motion = 0.0 mm",      RED),
    (98.7, "placing object",           "delivered at t = 101.9 s",            GREEN),
]

PER_ROW = 3
PLACED_CM = 21.6                     # \linewidth inside adjustwidth: text block + margin
FONT = cv2.FONT_HERSHEY_SIMPLEX

# The caption bar is redrawn here rather than reused from mk.panel because mk's fixed 0.60
# scale prints at whatever size the layout happens to give it.  Font sizes are instead solved
# backwards from the printed point size, which is the only quantity a reader experiences:
# a glyph of h px prints at h * PLACED_CM/2.54*72 / (total image width) points.
ROW_W = PER_ROW * mk.PANEL_W + (PER_ROW - 1) * mk.GAP
PX_PER_PT = ROW_W / (PLACED_CM / 2.54 * 72)
BAR_H = 100


def _scale_for_pt(pt, thick=2):
    """Font scale whose cap height prints at `pt` points at the placed width."""
    want = pt * PX_PER_PT
    s = 0.30
    while s < 3.0 and cv2.getTextSize("Hg", FONT, s + 0.02, thick)[0][1] < want:
        s += 0.02
    return s


def _fit(text, want, thick, avail):
    """Largest scale <= want at which `text` fits in `avail` px."""
    s = want
    while s > 0.30 and cv2.getTextSize(text, FONT, s, thick)[0][0] > avail:
        s -= 0.02
    return s


def panel(img, letter, t, title, sub, colour, tfmt="%.0f"):
    img = img[mk.TOP_BAR:, :]
    img = cv2.resize(img, (mk.PANEL_W, int(img.shape[0] * mk.PANEL_W / img.shape[1])),
                     interpolation=cv2.INTER_AREA)
    out = np.vstack([img, np.full((BAR_H, mk.PANEL_W, 3), 22, np.uint8)])
    y0 = img.shape[0]

    head_s, sub_s = _scale_for_pt(6.4), _scale_for_pt(5.6)

    head = ("(%s)  t = " + tfmt + " s") % (letter, t)
    hs = _fit(head, head_s, 2, 230)
    cv2.putText(out, head, (14, y0 + 36), FONT, hs, (255, 255, 255), 2, cv2.LINE_AA)
    hw = cv2.getTextSize(head, FONT, hs, 2)[0][0]

    ts = _fit(title, head_s, 2, mk.PANEL_W - hw - 46)
    cv2.putText(out, title, (hw + 32, y0 + 36), FONT, ts, colour, 2, cv2.LINE_AA)

    ss = _fit(sub, sub_s, 2, mk.PANEL_W - 28)
    cv2.putText(out, sub, (14, y0 + 78), FONT, ss, (200, 200, 200), 2, cv2.LINE_AA)

    cv2.rectangle(out, (0, 0), (mk.PANEL_W - 1, out.shape[0] - 1), (70, 70, 70), 1)
    return out


def main():
    cap = cv2.VideoCapture(SRC + ".mp4")
    L = json.load(open(SRC + ".json"))["log"]

    panels = []
    for (t, title, sub, col), ltr in zip(MOMENTS, "abcdefghi"):
        img = frame_at(cap, t)
        if img is None:
            raise SystemExit("no frame at t=%.1f" % t)
        if sub is None:
            clr = mk.tick_at(L, t).get("clr")
            sub = ("tool-obstacle clearance = %+.1f cm" % (clr * 100)) if clr is not None \
                  else "no hazard tracked"
        panels.append(panel(img, ltr, t, title, sub, col))
    cap.release()

    rows = [mk.row(panels[i:i + PER_ROW]) for i in range(0, len(panels), PER_ROW)]
    w = max(r.shape[1] for r in rows)
    pad = lambda a: cv2.copyMakeBorder(a, 0, 0, 0, w - a.shape[1], cv2.BORDER_CONSTANT,
                                       value=(255, 255, 255))
    gap = np.full((mk.GAP * 2, w, 3), 255, np.uint8)
    stack = [pad(rows[0])]
    for r in rows[1:]:
        stack += [gap, pad(r)]
    fig = np.vstack(stack)

    out = os.path.join(HERE, "fig_rr_contrast.png")
    cv2.imwrite(out, fig)
    print("fig_rr_contrast.png %dx%d  (%d panels, %d per row)  caption prints at %.1f pt"
          % (fig.shape[1], fig.shape[0], len(panels), PER_ROW,
             cv2.getTextSize("Hg", FONT, _scale_for_pt(6.4), 2)[0][1] / PX_PER_PT))
    print("  placed at %.1f cm -> %.1f cm tall" % (PLACED_CM, PLACED_CM * fig.shape[0] / w))


if __name__ == "__main__":
    main()
