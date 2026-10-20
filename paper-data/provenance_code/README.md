# provenance_code (public subset)

- `calibration.json` — the session calibration record used by the controller on 18 September 2026.
- `controller_constants.json` — module-level constants of the four archived controller files read by
  the analyses (`clasp_policy.py`, `aegis_time.py`, `timed_variants.py`, `timed_compare_run.py`) and the
  SHA-256 of each file. The hashes equal those recorded in every primary and pilot run log. `R_HUMAN`, `D_MECH` and `EPI` there are module defaults (0.10, 0.02 and 0.025 m); the deployed values (0.06, 0.012 and 0.012 m, the paper's R, d and β) were set per run and are recorded in `clasp_params` of every run log.

- `safebench/clasp_policy.py`, `safebench/aegis_time.py`, `safebench/timed_variants.py` — three of the
  archived controller files (score-and-hold rule, evidence clock and gate, policy variants), byte-identical to
  the versions whose SHA-256 is recorded in the run logs. They import other controller modules and are
  provided for inspection, not to run the robot.

The rest of the controller source is available from the corresponding author. Analysis scripts that check
the archived code read a source file where it is present and these constants and hashes otherwise.
