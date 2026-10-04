# provenance_code (public subset)

- `calibration.json` — the session calibration record used by the controller on 18 September 2026.
- `controller_constants.json` — module-level constants of the four archived controller files read by
  the analyses (`clasp_policy.py`, `aegis_time.py`, `timed_variants.py`, `timed_compare_run.py`) and the
  SHA-256 of each file. The hashes equal those recorded in every primary and pilot run log.

The controller source code is not public; it is available from the corresponding author. Analysis
scripts that check the archived code read these constants and hashes when the source is absent.
