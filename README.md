# Evidence age and spatial margin on a Niryo NED3 Pro: data and analysis

Data, analysis scripts and figures for the hardware study *Evidence Age Versus Spatial Margin in
Vision–Language-Gated Robotic Transport: A Hardware Study* (submitted to *Sensors*, October 2026).

## Start here: `paper-data/`

[`paper-data/`](paper-data/) holds everything the study uses:

- the per-run decision logs and frame-linked timing sidecars of the 92 eligible transports, recorded
  on 18 September 2026;
- the offline analysis scripts and their full-precision results;
- the human-review exports of the monitor audit and the frozen model-replay outputs;
- the session calibration record;
- the controller constants and three archived controller modules.

[`paper-data/README.md`](paper-data/README.md) explains the layout and how to regenerate every
table and figure. To check a download:

```bash
cd paper-data
python verify_release.py      # compares every file with RELEASE_MANIFEST.json
```

## Other folders

`data/`, `figures/`, `scripts/` and `RUN_MANIFEST.md` hold material from earlier development of the
same system: simulation records, earlier hardware runs, calibration reports and a VLM timing
benchmark. They are not part of the evidence for the hardware study. In those earlier runs the
verdict age was measured from the end of inference rather than from frame receipt, so their ages
are not comparable with the study's.

## Licence

Figures, videos, logs and documentation are released under **CC BY 4.0**. See `LICENSE`.

## Contact

- Danial Zafaranchizadeh Moghaddam — danial.za@outlook.com
- Abolfazl Zaraki (corresponding) — a.zaraki@herts.ac.uk
