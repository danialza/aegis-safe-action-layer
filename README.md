# AEGIS: Age-Aware, Evidence-Guarded Safe-Action Layer on the Niryo NED3 Pro

Companion data repository for the manuscript:

> **AEGIS: An Age-Aware, Evidence-Guarded Safe-Action Layer Fusing RGB-D Sensing with
> Vision–Language Monitoring for Collision-Aware Robotic Manipulation**
> Danial Zafaranchizadeh Moghaddam, Maryam Banitalebi Dehkordi, Hamed Rahimi Nohooji,
> Abolfazl Zaraki — University of Hertfordshire and University of Luxembourg, 2026.

A semantic verdict is stale the moment after it is emitted. AEGIS makes the robot's hold radius
an explicit function of a vision–language belief **and of the age of the verdict that produced
it**, so the margin widens on its own as evidence goes stale and collapses again on a fresh one.
It runs on a low-cost six-axis arm from a single fixed RealSense D435i, with no safety scanner
and no motion capture.

This repo collects the **public reproducibility material** that backs the claims of the paper:

- the publication figures used in the article (`figures/`),
- the per-control-tick logs of every physical run, the calibration reports, the on-device
  vision–language benchmark and the simulation episode records (`data/`),
- the scripts that regenerate the frame-strip figures from those logs (`scripts/`),
- a manifest linking every reported physical number to the run that produced it
  (`RUN_MANIFEST.md`).

The manuscript text, LaTeX source and the published PDF are **not** distributed here. The
article, its DOI and a direct PDF link will be available from the project landing page.

**Project page:** <https://danielz.co.uk/projects/aegis-age-aware-safe-action-layer/>

If you use the public figures, videos, logs or experimental methodology, please cite the
manuscript above and link back to the project page. For full code access, please email the
authors listed below.

---

## Repository layout

```
.
├── figures/            Publication figures (PDF / PNG, exact versions used in the paper)
├── scripts/            Scripts that rebuild the frame-strip figures from the run logs
│   ├── README.md
│   ├── mk_fig5_contrast.py
│   ├── mk_fig6_rgbd.py
│   └── mk_rr_figures.py
├── data/               Run logs, calibration, VLM benchmark, simulation records, video index
│   ├── README.md
│   ├── hardware_runs/
│   ├── calibration/
│   ├── vlm_benchmark/
│   ├── simulation/
│   └── videos/README.md
├── RUN_MANIFEST.md     Every physical number traced to its run, calibration and parameters
├── LICENSE
└── README.md           This file
```

---

## Headline results

| Quantity | Result |
|---|---|
| Per-step unsafe cost, sampling-based planner | 0.138 → 0.0086 (16×), Wilcoxon *p* = 1×10⁻⁶, *n* = 36 paired episodes |
| Task success, same comparison | 65% → 92%, exact McNemar *p* = 0.007 |
| Physical AEGIS runs | minimum moving clearance **+19.7 mm**, never negative |
| Physical trust-latest baseline | one run entered the detected footprint at **−5.6 mm** |
| Physical worst-case baseline | never commanded motion while a hazard was tracked |
| On-device semantic verdict | FastVLM-0.5B, 0.236 s mean, 0.238 s p95, 20 timed queries |
| Image-to-table calibration | 0.92 mm mean fitting residual over nine points |
| Hand-to-freeze reaction | 1.73 s mean, 2.67 s worst, *n* = 5 intrusions, hosted backend |

Every figure above traces to a file under `data/` — see `RUN_MANIFEST.md` for the mapping.
Success rises rather than trading off: the projection removes the boundary- and
obstacle-grazing commands that were also causing the planner to fail.

## Videos

Nineteen clips, about 21 minutes, every one a real run on the physical arm. Attached to the
[v1.0 release](../../releases/tag/v1.0); `data/videos/README.md` indexes them.

## Scope and caveats

The clearance result is established for the constrained grasp site, not the whole arm; a
whole-arm audit found the forearm crossing the hazard sphere in 7 of 120 simulated episodes,
which is why the title says *collision-aware* rather than *collision-free*. Verdict age is
measured from when inference returns rather than when the image was captured, which under-sizes
the enforced radius by up to 29.6 mm of which the 25 mm epistemic buffer absorbs most. The
physical runs were conducted below the sufficient buffer-sizing condition the paper proves, so
the hardware outcome is empirical rather than an instance of the guarantee. Section 5 of the
paper states each of these in full.

## Licence

Figures, videos, logs and documentation are released under **CC BY 4.0**. See `LICENSE`.

## Contact

- Danial Zafaranchizadeh Moghaddam — danial.za@outlook.com
- Abolfazl Zaraki (corresponding) — a.zaraki@herts.ac.uk
