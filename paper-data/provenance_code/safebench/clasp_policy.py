"""CLASP hold-radius for the REAL robot, factored out so it can be unit-tested offline.

This is the same confidence-and-latency-aware margin as `clasp.py`/`clasp_mujoco.py`,
but packaged as a per-tick helper that reads the live FastVLM verdict stream on the
NED3 Pro: each tick it takes the latest verdict label, the verdict sequence number (so
it knows when a NEW verdict arrived), and the wall-clock time, and returns
    (semantic_margin_to_add_to_the_hazard_radius, belief_p, hold_flag)
for the selected policy. `reactive_run.py` inflates the sensed hazard radius by that
margin and freezes when hold_flag is set, so the geometric layer keeps the tool the
belief-appropriate distance from the intruder without any other change.

Three policies share the identical geometry; only the margin differs:
  clasp        belief that decays toward a cautious prior with verdict AGE
  worstcase    always assume a person   (margin always the full human distance)
  trustlatest  trust the latest verdict at face value, however old
"""
from __future__ import annotations

import numpy as np

# ---- constants, identical to clasp.py / clasp_mujoco.py ----
R_HUMAN = 0.10          # protective distance to keep from a (possible) person (m)
D_MECH = 0.020          # mechanical clearance to a confirmed inert object (m)
P_PRIOR = 0.65          # belief for an unknown / just-appeared intruder (cautious)
P_STOP = 0.50           # p above this -> hold (human-likely), do not route
T_DECAY = 0.40          # belief decay time toward the prior (s)
EPI = 0.025             # epistemic buffer (CLASP only): never fully trust one verdict
RELIABILITY = 0.95      # verdict trust when updating the belief

MODES = ("clasp", "worstcase", "trustlatest")


class Belief:
    """P(human) for the tracked intruder: async verdict update + age decay + reset."""

    def __init__(self):
        self.p_hat = P_PRIOR
        self.t_upd = None
        self.last_seq = None

    def on_new_blob(self):
        """A detector track that looks new/changed resets belief to the cautious prior."""
        self.p_hat = P_PRIOR
        self.t_upd = None

    def on_verdict(self, now, is_human):
        target = 1.0 if is_human else 0.0
        self.p_hat = (1 - RELIABILITY) * self.p_hat + RELIABILITY * target
        self.t_upd = now

    def value(self, now):
        if self.t_upd is None:
            return P_PRIOR                       # no verdict yet -> cautious prior
        tau = max(0.0, now - self.t_upd)
        return self.p_hat + (P_PRIOR - self.p_hat) * (1.0 - np.exp(-tau / T_DECAY))


class ClaspRadius:
    """Stateful per-tick helper. Feed it the live verdict; get the margin + hold."""

    def __init__(self, mode="clasp", r_human=R_HUMAN, d_mech=D_MECH, epi=EPI):
        assert mode in MODES, f"mode must be one of {MODES}"
        self.mode = mode
        # Protective distances are design parameters and are scaled to the platform:
        # this arm has a ~22 cm carry and a small (~3 cm) intruder, so the simulation's
        # 10 cm human bubble would block every route. Whatever is used must be reported.
        self.r_human = float(r_human)
        self.d_mech = float(d_mech)
        self.epi = float(epi)
        self.bel = Belief()
        self._blob = None                        # (xy, r) of the last tracked intruder

    def _belief_bookkeeping(self, hs, vlm_label, vlm_seq, now):
        # reset on a new/changed blob (its semantic identity may have changed)
        if hs.get("present"):
            xy = np.asarray(hs["xy"], float); r = float(hs["r"])
            if self._blob is not None:
                pxy, pr = self._blob
                if np.linalg.norm(xy - pxy) > 0.05 or abs(r - pr) > 0.05:
                    self.bel.on_new_blob()
            self._blob = (xy, r)
        # update on a genuinely new verdict (seq advanced)
        if vlm_seq is not None and vlm_seq != self.bel.last_seq and vlm_label is not None:
            self.bel.on_verdict(now, vlm_label == "human")
            self.bel.last_seq = vlm_seq

    def p(self, hs, vlm_label, vlm_seq, now):
        if self.mode == "worstcase":
            return 1.0
        if self.mode == "trustlatest":
            return 1.0 if vlm_label == "human" else 0.0
        self._belief_bookkeeping(hs, vlm_label, vlm_seq, now)
        return float(self.bel.value(now))

    def update(self, hs, vlm_label, vlm_seq, now):
        """-> (margin_m, belief_p, hold). margin is what to ADD to hs['r']; hold means
        freeze (do not route). Returns (0,0,False) when no intruder is present."""
        if not hs.get("present"):
            # still advance the belief clock/verdicts so age is right when it reappears
            if self.mode == "clasp" and vlm_seq is not None and vlm_seq != self.bel.last_seq \
                    and vlm_label is not None:
                self.bel.on_verdict(now, vlm_label == "human"); self.bel.last_seq = vlm_seq
            return 0.0, 0.0, False
        p = self.p(hs, vlm_label, vlm_seq, now)
        epi = self.epi if self.mode == "clasp" else 0.0
        margin = p * (self.r_human - self.d_mech) + epi
        hold = p >= P_STOP
        return float(margin), float(p), bool(hold)
