"""Matched comparison pair on one evidence path: AEGIS-sensor-time and Trust-time.

Both variants use the SAME image and VLM path from safebench/aegis_time.py (newest frame, no queue,
no fixed pause after inference, one immutable Evidence bundle per inference), the same evidence
clock (age = t_decision - image time, duplicates never refresh, explicit HOLD on no verdict / VLM
error / invalid time / out-of-order), the same geometric sensing with the stopped-camera hold, the
same human, destination, depth-only and Z guards, the same speed, and the SAME fixed base buffer
`epi` (the submitted trust-latest had no buffer at all; that mismatch is removed here).
They differ in exactly one place, the semantic term of the hold radius:

  AEGIS-sensor-time  p = capture-clock belief (decays toward the prior with the IMAGE age)
                     margin = p * (R_human - d_mech) + epi;  hold when p >= P_STOP
  Trust-time         p = 1 if the latest valid verdict is 'human' else 0 (age not used)
                     margin = p * (R_human - d_mech) + epi;  hold only on a 'human' verdict

Image time: the camera transport provides no sensor/exposure timestamp (checked 2026-09-18: the Pi
server stamps frames on receipt after decode). The image time is therefore the capture proxy,
reported as such (IMAGE_TIME_TYPE); nothing here is sensor time.

The files safebench/aegis_time.py and safebench/aegis_time_run.py (the working AEGIS-time) and the
submitted runner are imported unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os

from safebench.aegis_time import (P_STOP, AegisTimeGate, ClaspTimeRadius, TIME_BASE,
                                  TIME_BASE_NOTE)

IMAGE_TIME_TYPE = TIME_BASE              # "capture_proxy": no sensor timestamp in the transport
IMAGE_TIME_NOTE = TIME_BASE_NOTE

AEGIS = "AEGIS-sensor-time"
TRUST = "Trust-time"
TRUST_SENSOR = "Trust-sensor-time"      # name-symmetric partner of AEGIS-sensor-time; the SAME rule
                                        # and the same capture-proxy time base as Trust-time
VARIANTS = {"aegis": AEGIS, "trust": TRUST, "trust-sensor": TRUST_SENSOR}


class TrustLatestTimeRadius:
    """trust-latest on the shared evidence path: the latest valid verdict at face value, whatever
    its age, plus the same fixed base buffer as AEGIS."""

    def __init__(self, r_human, d_mech, epi):
        self.r_human = float(r_human)
        self.d_mech = float(d_mech)
        self.epi = float(epi)

    def update(self, hs, ev, now):
        if not hs.get("present"):
            return 0.0, 0.0, False
        p = 1.0 if (ev is not None and ev.verdict == "human") else 0.0
        margin = p * (self.r_human - self.d_mech) + self.epi
        return float(margin), p, bool(p >= P_STOP)


class AegisSensorTimeGate(AegisTimeGate):
    """AEGIS on the shared evidence path: capture-clock belief (the AEGIS-time rule)."""
    variant = AEGIS
    age_enters_margin = True


class TrustTimeGate(AegisTimeGate):
    """Trust-time: identical gate (evidence clock, holds, human guard); only the radius differs."""
    variant = TRUST
    age_enters_margin = False

    def __init__(self, r_human, d_mech, epi):
        super().__init__(r_human, d_mech, epi)
        self.radius = TrustLatestTimeRadius(r_human, d_mech, epi)


class TrustSensorTimeGate(TrustTimeGate):
    """Trust-time under the name Trust-sensor-time (no behavioural difference: the transport has no
    sensor timestamp, so both use the capture proxy)."""
    variant = TRUST_SENSOR


def make_gate(variant, r_human, d_mech, epi):
    return {AEGIS: AegisSensorTimeGate, TRUST: TrustTimeGate,
            TRUST_SENSOR: TrustSensorTimeGate}[variant](r_human, d_mech, epi)


# ------------------------------------------------------------------ code / settings provenance
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_FILES = ("safebench/timed_variants.py", "safebench/timed_compare_run.py",
              "safebench/aegis_time.py", "safebench/reactive_run.py", "safebench/reactive_exec.py",
              "safebench/clasp_policy.py", "safebench/rs_stream.py", "safebench/fastvlm_monitor.py",
              "safebench/arm_mask.py", "safebench/table_cam.py", "safebench/ssm_exec.py")
CONFIG_FILES = ("calibration.json", "data/real_runs/cal_session_0722.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(settings, extra_files=()):
    """sha256 of every code/config file the run depends on, of the settings, and of all of it."""
    files = {}
    for rel in tuple(CODE_FILES) + tuple(CONFIG_FILES) + tuple(extra_files):
        p = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
        files[rel] = sha256_file(p) if os.path.exists(p) else None
    s_json = json.dumps(settings, sort_keys=True, default=str)
    s_hash = hashlib.sha256(s_json.encode()).hexdigest()
    combined = hashlib.sha256((json.dumps(files, sort_keys=True) + s_hash).encode()).hexdigest()
    return {"files_sha256": files, "settings": settings, "settings_sha256": s_hash,
            "combined_sha256": combined}
