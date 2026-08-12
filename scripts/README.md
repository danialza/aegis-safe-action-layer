# Scripts

These rebuild the two frame-strip figures directly from the run logs and their videos, so the
panel times in the paper are the robot's own timestamps rather than eyeballed ones.

| Script | Produces |
|---|---|
| `mk_fig5_contrast.py` | Figure 5 — nine panels from one uninterrupted carry in which the verdict alternates between HUMAN and OBJECT |
| `mk_fig6_rgbd.py` | Figure 6 — six panels of the RGB-D carry, with the panels placed on the ticks where depth confirms the colour detection |
| `mk_rr_figures.py` | Shared panel and row drawing, imported by both |

## Running them

The scripts expect the two source clips beside them, from the
[v1.0 release](../../releases/tag/v1.0), together with the matching logs from
`data/hardware_runs/`. Both map a frame index to the run's own clock with a fitted `(FPS, T0)`
pair — the recorder tags 12 fps, sustains about 11.6, and starts roughly half a second after
the run. Using the tagged rate places every extracted frame about 4% late. If a clip is ever
re-exported, re-fit those two constants against the timestamp burned into the frames before
trusting any panel.

Caption font sizes are solved backwards from the printed point size rather than set by hand, so
changing the number of panels per row keeps the text legible at the placed width.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install opencv-python numpy
python scripts/mk_fig5_contrast.py
```
