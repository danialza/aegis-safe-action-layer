"""AEGIS-time: the AEGIS (CLASP) hold radius driven by the age of the IMAGE a semantic verdict
judged, not by the moment the verdict arrived.

The submitted AEGIS (safebench/clasp_policy.py driven by safebench/reactive_run.py) is left
unchanged. This module is used only by safebench/aegis_time_run.py; both variants share the
same camera, calibration, arm mask, detectors, planner, floor, speed and gripper code.

Time base
    Host time.perf_counter() seconds. The capture proxy of an image is the camera packet's
    t_capture_est = t_request - source_age_s (rs_stream.read_packet_v2): the moment the frame
    reached the camera server on the Pi, mapped to the host clock. It EXCLUDES the sensor
    exposure -> Pi interval (not measured) and includes the request's one-way latency. Every age
    below is measured from this proxy; no constant is added anywhere.

Evidence
    One immutable bundle per VLM inference: the verdict together with the frame id and capture
    proxy of the very image it judged, plus the inference start and end times. Published
    atomically; the controller always reads a whole bundle, never a verdict from one image with
    the times of another.

Decision-time age
    age = t_decision - t_capture. The belief's clock starts at the capture proxy, so transfer and
    inference delay are inside the age exactly once, and the arrival of an answer does not reset
    it.

Integrity (explicit HOLD, reason recorded)
    no_verdict    no valid verdict yet
    vlm_error     the latest inference failed
    invalid_time  missing / non-finite / inconsistent times, or a capture proxy in the future
    out_of_order  a result for an image older than the evidence already in force
    sensing_stale the geometric camera frames stopped (latest older than SENSING_STALE_S)
    A repeated frame (same frame id) never refreshes evidence: its age keeps growing from the
    first capture.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from safebench.clasp_policy import P_PRIOR, P_STOP, RELIABILITY, T_DECAY

TIME_BASE = "capture_proxy"
TIME_BASE_NOTE = ("capture proxy = t_request - source_age_s from the camera packet, host "
                  "perf_counter clock: frame arrival at the Pi; excludes sensor exposure -> Pi, "
                  "includes the request's one-way latency")
CLOCK_TOL_S = 0.005       # ordering tolerance between host timestamps (timer resolution)
SEMANTIC_FRESH_S = 1.0    # the destination guard's semantic freshness limit (unchanged value)
SENSING_STALE_S = 0.6     # the tracker's own horizon (reactive_exec.Tracker.state drops a track not
                          # refreshed for 0.6 s): geometric evidence older than this cannot vouch
                          # for an empty path, so the arm holds instead of carrying on blind

OK = "ok"
NO_VERDICT = "no_verdict"
VLM_ERROR = "vlm_error"
INVALID_TIME = "invalid_time"
OUT_OF_ORDER = "out_of_order"
HOLD_STATUSES = frozenset({NO_VERDICT, VLM_ERROR, INVALID_TIME, OUT_OF_ORDER})


@dataclass(frozen=True)
class Evidence:
    """One VLM result and the provenance of the image it judged (immutable)."""
    seq: int
    frame_id: Optional[str]
    t_capture: Optional[float]          # capture proxy of the judged image
    t_infer_start: Optional[float]
    t_infer_end: Optional[float]
    verdict: Optional[str]              # "human" | "object"; None when the inference failed
    hands: int = 0
    error: Optional[str] = None
    t_request: Optional[float] = None
    t_received: Optional[float] = None
    source_age_s: Optional[float] = None

    def record(self, prefix="ev_"):
        return {prefix + k: getattr(self, k) for k in
                ("seq", "frame_id", "t_capture", "t_infer_start", "t_infer_end", "verdict",
                 "hands", "error", "t_request", "t_received", "source_age_s")}


class EvidenceStore:
    """The latest Evidence bundle. One immutable object swapped under a lock, so a reader gets
    the verdict and the times of the same image or nothing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ev = None

    def publish(self, ev):
        with self._lock:
            self._ev = ev

    def latest(self):
        with self._lock:
            return self._ev


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def times_valid(ev, now):
    """The bundle's own times are present, finite, causally ordered and not in the future."""
    if not all(_finite(v) for v in (ev.t_capture, ev.t_infer_start, ev.t_infer_end)):
        return False
    if ev.t_capture > ev.t_infer_start + CLOCK_TOL_S:      # judged before it was captured
        return False
    if ev.t_infer_end < ev.t_infer_start:
        return False
    if ev.t_capture > now + CLOCK_TOL_S or ev.t_infer_end > now + CLOCK_TOL_S:
        return False
    return True


def sensing_age(hs, now):
    """Age of the latest processed camera frame on the capture proxy (inf if unknown)."""
    tc = (hs.get("frame") or {}).get("t_capture_est")
    return float("inf") if not _finite(tc) else now - float(tc)


class EvidenceClock:
    """Judge every new bundle once and keep the evidence in force.

    assess(latest, now) -> (status, evidence_in_force | None, age | None). The status of the most
    recent bundle stays latched until a newer bundle replaces it, so an error or out-of-order
    result keeps the arm held until a valid in-order result arrives. Only status OK yields
    evidence and an age.
    """

    def __init__(self):
        self.status = NO_VERDICT
        self.accepted = None
        self._seen_seq = None
        self.duplicates = 0
        self.rejected = {VLM_ERROR: 0, INVALID_TIME: 0, OUT_OF_ORDER: 0}

    def assess(self, latest, now):
        if latest is not None and latest.seq != self._seen_seq:
            self._seen_seq = latest.seq
            self.status = self._judge(latest, now)
        ev = self.accepted if self.status == OK else None
        return self.status, ev, (None if ev is None else now - ev.t_capture)

    def _judge(self, ev, now):
        if ev.error is not None or ev.verdict not in ("human", "object"):
            self.rejected[VLM_ERROR] += 1
            return VLM_ERROR
        if not times_valid(ev, now):
            self.rejected[INVALID_TIME] += 1
            return INVALID_TIME
        if self.accepted is not None:
            if ev.frame_id is not None and ev.frame_id == self.accepted.frame_id:
                self.duplicates += 1                  # same image: no refresh, status unchanged
                return self.status
            if ev.t_capture < self.accepted.t_capture - CLOCK_TOL_S:
                self.rejected[OUT_OF_ORDER] += 1
                return OUT_OF_ORDER
        self.accepted = ev
        return OK


class CaptureBelief:
    """clasp_policy.Belief with its clock started at the evidence's capture proxy instead of the
    moment the controller first saw the verdict. Update rule and constants are identical."""

    def __init__(self):
        self.p_hat = P_PRIOR
        self.t_obs = None

    def on_new_blob(self):
        self.p_hat = P_PRIOR
        self.t_obs = None

    def on_evidence(self, t_capture, is_human):
        target = 1.0 if is_human else 0.0
        self.p_hat = (1 - RELIABILITY) * self.p_hat + RELIABILITY * target
        self.t_obs = float(t_capture)

    def value(self, now):
        if self.t_obs is None:
            return P_PRIOR
        tau = max(0.0, now - self.t_obs)
        return self.p_hat + (P_PRIOR - self.p_hat) * (1.0 - math.exp(-tau / T_DECAY))


class ClaspTimeRadius:
    """clasp_policy.ClaspRadius (mode 'clasp') fed by Evidence bundles on the capture clock.
    Blob-reset rule, margin formula and hold threshold are unchanged."""

    def __init__(self, r_human, d_mech, epi):
        self.r_human = float(r_human)
        self.d_mech = float(d_mech)
        self.epi = float(epi)
        self.bel = CaptureBelief()
        self._blob = None
        self._absorbed_seq = None

    def update(self, hs, ev, now):
        """ev: the evidence in force or None. -> (margin_m, p, belief_hold)."""
        if hs.get("present"):
            xy = np.asarray(hs["xy"], float)
            r = float(hs["r"])
            if self._blob is not None:
                pxy, pr = self._blob
                if np.linalg.norm(xy - pxy) > 0.05 or abs(r - pr) > 0.05:
                    self.bel.on_new_blob()
            self._blob = (xy, r)
        if ev is not None and ev.seq != self._absorbed_seq:
            self.bel.on_evidence(ev.t_capture, ev.verdict == "human")
            self._absorbed_seq = ev.seq
        if not hs.get("present"):
            return 0.0, 0.0, False
        p = float(self.bel.value(now))
        margin = p * (self.r_human - self.d_mech) + self.epi
        return float(margin), p, bool(p >= P_STOP)


@dataclass(frozen=True)
class GateDecision:
    status: str
    evidence: Optional[Evidence]
    age: Optional[float]               # t_decision - capture proxy of the evidence in force
    margin: float
    p: float
    hold: bool
    reason: Optional[str]              # evidence status | "human" | "belief>=P_STOP" | None
    vlm_label: Optional[str]
    vlm_age: float


class AegisTimeGate:
    """Everything AEGIS-time adds to one control tick: judge the latest bundle, age it at the
    decision time, update the capture-clock belief, and say whether to hold and why."""

    def __init__(self, r_human, d_mech, epi):
        self.clock = EvidenceClock()
        self.radius = ClaspTimeRadius(r_human, d_mech, epi)

    def step(self, hs, latest, now):
        status, ev, age = self.clock.assess(latest, now)
        margin, p, belief_hold = self.radius.update(hs, ev, now)
        if status in HOLD_STATUSES:
            return GateDecision(status, None, None, margin, p, True, status, None, float("inf"))
        if ev.verdict == "human":
            return GateDecision(status, ev, age, margin, p, True, "human", "human", age)
        hold = bool(hs.get("present")) and belief_hold
        return GateDecision(status, ev, age, margin, p, hold,
                            "belief>=P_STOP" if hold else None, ev.verdict, age)


class EvidenceVLMThread(threading.Thread):
    """Judge the NEWEST camera frame and publish one Evidence bundle per inference.

    No queue (the camera server answers with its latest frame only); a frame id already judged
    is never judged again; no fixed pause after an inference: the next cycle starts at once
    unless `min_period` asks for a start-to-start spacing.
    """

    def __init__(self, cam, store, monitor=None, min_period=0.0, timing=None,
                 clock=time.perf_counter, sleep=time.sleep):
        super().__init__(daemon=True)
        if monitor is None:
            from safebench.fastvlm_monitor import FastVLMMonitor
            monitor = FastVLMMonitor()
        self.cam, self.store, self.m = cam, store, monitor
        self.min_period = float(min_period)
        self.timing, self.clock, self.sleep = timing, clock, sleep
        self.seq = 0
        self.last_frame_id = None
        self.duplicate_reads = 0
        self.link_misses = 0
        self.running = True

    def cycle(self):
        """One read -> judge -> publish step. Returns the published Evidence, or None when there
        was nothing new to judge (link miss or the same frame as last time)."""
        frame, _, meta = self.cam.read_packet_v2()
        if frame is None or not meta:
            self.link_misses += 1
            return None
        fid = meta.get("frame_id")
        if fid is not None and fid == self.last_frame_id:
            self.duplicate_reads += 1
            return None
        self.last_frame_id = fid
        t0 = self.clock()
        try:
            v, n, _ = self.m.verdict(frame)
            t1 = self.clock()
            verdict, err = ("human" if v == "ABORT" else "object"), None
        except Exception as exc:                      # the bundle records the failure -> HOLD
            t1 = self.clock()
            verdict, n, err = None, 0, (str(exc) or type(exc).__name__)[:160]
        self.seq += 1
        ev = Evidence(self.seq, fid, meta.get("t_capture_est"), t0, t1, verdict, int(n), err,
                      meta.get("t_request"), meta.get("t_received"), meta.get("source_age_s"))
        self.store.publish(ev)
        if self.timing is not None:
            self.timing.write(dict(ev.record(prefix=""), type="vlm", time_base=TIME_BASE))
        return ev

    def run(self):
        while self.running:
            t_cycle = self.clock()
            if self.cycle() is None:
                self.sleep(0.01)
                continue
            rest = self.min_period - (self.clock() - t_cycle)
            if rest > 0:
                self.sleep(rest)


class DedupCamera:
    """Camera view for the geometric sensing thread: a frame id already delivered is not
    delivered again, so a stalled stream cannot pose as fresh evidence, and frames without
    provenance (the non-packet fallbacks) are not delivered at all."""

    def __init__(self, cam):
        self.cam = cam
        self._last = None
        self.repeats = 0

    def read_packet_v2(self):
        rgb, depth, meta = self.cam.read_packet_v2()
        if rgb is None or not meta:
            return None, None, None
        fid = meta.get("frame_id")
        if fid is not None and fid == self._last:
            self.repeats += 1
            return None, None, None
        self._last = fid
        return rgb, depth, meta

    def read_rgbd(self):
        return None, None

    def read(self):
        return None

    def __getattr__(self, name):
        return getattr(self.cam, name)
