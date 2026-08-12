# AEGIS — video supplement and narration script

Every clip here is a **real run on the physical Niryo NED3 Pro**. Nothing is simulated and
nothing is re-enacted. All timestamps below are **video time in that clip** (mm:ss), already
corrected for the recorder's frame rate, so you can cut and narrate straight from them.

**Total runtime:** ~22 min for clips 01–16, 18 and 19, plus ~15 min for the 30-carry loop folder.

## How to read the on-screen overlay

The clips whose name comes from a `_paths` recording carry a live overlay:

| Colour | Meaning |
|---|---|
| **Blue** | the nominal straight carry the robot *wanted* to take |
| **Orange** | the live re-plan currently being followed |
| **Green** | the path actually executed so far |
| **Red circle** | the sensed hazard, drawn at the radius the policy is enforcing *right now* |
| **S / G** | start and goal of the carry |

The red circle is the one to watch in clips 11–16: its size *is* the safety decision.

Three clips (`03`, `06`, `08`) are raw recordings without the overlay — they were recorded
before the overlay was added or with it disabled. They are noted individually below.

---

## 00 — The workspace (still images, open the video with these)

| File | What it is |
|---|---|
| `00a_workspace_photo.png` | The real laboratory setup, photographed. The NED3 Pro on the workbench, the green task object in front of it, and the Intel RealSense D435i on a tripod *facing* the arm across the table. |
| `00b_workspace_schematic.png` | The same arrangement drawn to scale, side view and top view, with the calibrated region and the two carry corners A and B marked. |
| `00c_homography_result.png` | The calibration result: commanded positions versus where the camera thinks they are, after fitting. |

**Narration:** "This is the whole rig. One low-cost six-axis arm, one fixed RGB-D camera on a
tripod looking across the table, and a workspace of about twenty by twenty centimetres between
them. The camera never moves once it is calibrated. Everything you are about to see is decided
from this single camera."

---

## 01 — Nine-point calibration (1:58)

**What is being tested:** the image-to-table homography — the map that turns a camera pixel
into a position in the robot's own coordinate frame.

**What happens:** the arm grips a coloured marker and, under the safety layer, carries it to
nine commanded positions on a grid. At each stop the system records where the camera *sees*
the marker. Those nine correspondences are then fitted into a single plane-to-plane transform.

**Result:** mean reprojection residual **1.1 mm**, worst **2.4 mm**, across the workspace.

**Narration:** "Before the robot can avoid anything, it has to agree with the camera about
where things are. The arm walks a marker to nine known positions and the system watches where
each one lands in the image. From those nine pairs it fits one transform. Afterwards the
camera can place an object on this table to about a millimetre — and that is what every later
decision is built on."

*Paper: Figure 4, Section 3.2.*

---

## 02 — Twenty-five-point wide calibration (0:50)

**What is being tested:** the same fit over a **larger** workspace, from a raised camera, to
support the long carries in clip 10 and the multi-obstacle runs.

**Result:** 1.18 mm mean inlier residual over 25 points.

**Narration:** "The same procedure again, but over a wider area and from a higher camera angle
— twenty-five points instead of nine. This is the calibration used for the long carries."

---

## 03 — Baseline: a clear carry (0:21) · *no overlay*

**What is being tested:** the task itself, with nothing in the way.

**What happens:** the arm picks the object at one corner of the workspace and carries it in a
straight line to the opposite corner. This is the motion that every later clip interrupts.

**Narration:** "This is the job. Pick the object up here, put it down over there, about
twenty-two centimetres away. With an empty table the robot simply goes straight. Remember this
path — everything that follows is what happens when something gets in the way."

---

## 04 — Verdict OBJECT → the robot routes around it (0:50)

**What is being tested:** the geometric layer's response when the on-device vision–language
monitor reports the intruder is an **inert object**.

**Beats:**

| Time | What happens |
|---|---|
| 0:00–0:24 | pick, then the robot deliberately waits so an obstacle can be placed on the carry line |
| **0:25** | the obstacle is sensed; the straight blue path is blocked; the layer commits to a detour |
| 0:25–0:44 | the green executed path curves around the red hazard circle |
| **0:44** | delivered |

**Result:** the tool leaves the straight line by **3.6 cm** and holds a minimum clearance of
**4.0 cm**, never overlapping the obstacle while moving.

**Narration:** "Now I put a box directly on the path. The monitor looks at the scene and calls
it an object — not a person. Watch the blue line: that is where the robot wanted to go. The red
circle is the safety bubble it is enforcing. Because this is only an object, the bubble stays
small, and the robot has room to curve around it and still finish the job."

*Paper: Table 5. (This clip was the source of Figure 5 before it was rebuilt from the single combined carry, clip 18; it remains the cleanest isolated object-routing example.)*

---

## 05 — Verdict HUMAN → the robot freezes (0:52)

**What is being tested:** the *same code, same scene, same carry* — but now the intruder is a
human hand. Nothing changes except the semantic verdict.

**Beats:**

| Time | What happens |
|---|---|
| 0:00–0:22 | pick and wait |
| **0:23** | the hand enters; the monitor returns HUMAN; the arm stops |
| 0:23–0:38 | **the arm does not move at all** — 0.0 mm of commanded tool motion for about 35 seconds |
| **0:39** | the hand is withdrawn; the carry resumes |
| **0:46** | delivered |

**Narration:** "Same program, same table, same carry. The only thing I change is what is on the
path — this time it is my hand. The monitor calls it human, and the robot does not negotiate:
it stops. Not slows down, stops. Zero millimetres of commanded motion for thirty-five seconds.
The moment I take my hand away, it finishes the job on its own. Routing around a box and
refusing to move for a person are the same policy under two different verdicts — that is the
whole point of the paper."

*Paper: Table 5. This clip and clip 04 are the paired result, and were the source of Figure 5 before it was rebuilt from clip 18.*

---

## 06 — A live, moving obstacle (1:04) · *no overlay*

**What is being tested:** continuous re-planning while the hazard **moves** during the carry.

**Beats:** the obstacle is slid along the path from 0:21 onward; the layer re-plans repeatedly
(re-route at 0:21, 0:31, 0:34, 0:35, 0:52) and holds whenever no route exists. At **0:55** the
operator's hand comes into frame and the monitor pre-empts everything with a protective stop.

**Result:** minimum clearance **3.0 cm**, no overlap while moving.

**Narration:** "Here the obstacle is not standing still — I am pushing it along the path while
the robot is carrying. It re-plans continuously, and when there is no safe way past it simply
waits. Notice at the end: my hand comes into view and human safety immediately overrides the
object logic."

*Paper: Table 5, "live moving object" row.*

---

## 07 — RGB-D: depth confirms the detection (1:34)

**What is being tested:** **sensor fusion.** The colour camera proposes a detection; the depth
channel from the same camera must independently agree before the tool is routed close to it.

**Beats:**

| Time | What happens |
|---|---|
| **0:28** | both modalities agree on the obstacle; the re-route is committed |
| **0:33** | the detour is held around the sensed footprint |
| **1:20** | closest approach of the whole carry — clearance **+2.6 cm**, reduced but never negative |

**Narration:** "Colour alone can be fooled by a shadow or a reflection. So the same camera's
depth channel has to agree before the robot will trust a detection enough to drive near it.
Two independent votes from one sensor. Across all the depth-confirmed runs the clearance never
once went negative."

*Paper: Figure 6.*

---

## 08 — RGB-D: an object *and* a hand in one carry (1:38) · *no overlay*

**What is being tested:** both hazard types inside a **single** carry, with depth active.

**What happens:** over about a hundred seconds the run alternates — the hand enters and the
monitor freezes the arm (five separate times), the hand leaves and the object detour resumes,
the destination is briefly occupied and the endpoint guard refuses to release, then clears.

**Result:** minimum clearance **3.05 cm**, no negative-clearance tick anywhere in the run.

**Narration:** "This is the long version, with everything running at once. One carry, one
scene, and both kinds of hazard taking turns. Every time my hand appears the arm stops; every
time it leaves, the routing takes over again. It also refuses to put the object down while the
drop point is occupied. It took a hundred seconds, and it never once entered the obstacle."

---

## 09 — Three obstacles at once → fail-safe hold (2:54)

**What is being tested:** what the system does when there is **genuinely no safe route**.

**What happens:** up to three tracked obstacles are placed. The layer keeps trying, holds when
no route exists, resumes when the destination clears — and finally terminates with
`no_route`: it **does not deliver**.

**Narration:** "Now I make it impossible. Three obstacles, and the destination blocked too.
This is the case I most want to show you, because the robot does not do anything clever here —
it holds the object and stops. It never forces its way through. A refusal to move is a correct
outcome, not a failure."

> **Narration note:** this run ends in a protective hold, *not* a delivery. Please do not
> describe it as a success — its value is precisely that it fails safe.

*Paper: Table 5, "multi-obstacle" row, "route or safe hold".*

---

## 10 — Destination blocked, then cleared (0:53)

**What is being tested:** the **endpoint guard** — the rule that the robot may not release the
object onto a drop point it cannot prove is clear.

**Beats:** re-route begins at **0:24**; the destination is occupied so the release is refused;
at **0:47** the drop column reads clear in eight consecutive frames and the carry resumes;
delivered at **0:49**.

**Narration:** "The last few centimetres matter as much as the journey. Here the drop point
itself is blocked. The robot carries the object all the way there and then refuses to let go
until it can see, over eight consecutive frames, that the spot is genuinely clear."

---

## 11–16 — The AEGIS comparison (the paper's core experiment)

These six clips are **one controlled experiment**. Same arm, same scene, same 22.4 cm carry,
same detector, same on-device monitor. **The only thing that changes between them is the rule
that decides how big the red circle is.**

Three rules are compared:

| Policy | Rule | What you should see |
|---|---|---|
| **Worst-case** | always assume a person | red circle permanently huge; arm barely moves |
| **Trust-latest** | believe the last verdict, however old | red circle small and *frozen at one size* |
| **AEGIS** (ours) | believe the verdict, but widen as it gets old | red circle **visibly grows and shrinks** |

**Narration for the section opener:** "Everything so far used one fixed safety rule. Now the
same robot runs the same carry three times, and I change only one thing: how it decides how
much space to keep. Watch the red circle in each — it is the entire difference."

### 11 — Worst-case: safe, but it never works (1:42)

**What happens:** the policy ignores the verdict and always applies the full human distance.
It holds at 0:32, 0:38, 0:49, 1:00… essentially any time the hazard is present. It only
finishes at **1:41**, right at the end of the clip, because the obstacle was taken away.

**Narration:** "First rule: always assume the worst — treat anything that appears as if it
were a person. It is perfectly safe. It is also nearly useless: the bubble is so large that
there is never room to get past, so the arm just waits. It only finished this run because I
eventually removed the box."

> **Narration note:** this run *did* deliver, but only after the obstacle was removed. Across
> the two worst-case runs it logged **zero ticks of motion near the hazard**. Do not say
> "it never delivers" — say "it never delivers *while the hazard is there*".

### 12 — Trust-latest: it works, until it doesn't (1:04)

**What happens:** the policy takes the latest verdict at face value. The radius sits pinned at
**30 mm**. At the closest approach the tool goes **inside** the detected obstacle footprint —
a clearance of **−5.6 mm**.

**Narration:** "Second rule: just believe the camera. Whatever it said last, act on it. This
one delivers quickly and looks great — until you measure it. The circle never changes size,
and on this run the gripper passed *inside* the obstacle's own footprint. It was acting on a
verdict that was already out of date."

### 13 — Trust-latest again, this time clean (0:56)

**What happens:** the same rule, but no hand ever enters the frame, so the verdict stays
continuously fresh. The radius never leaves **40–41 mm** and the carry completes cleanly.

**Narration:** "The same rule again — and this time nothing goes wrong. That is exactly why
this failure is dangerous. It does not fail every time. It fails only when the scene changes
during the blind moment between two verdicts."

### 14 — AEGIS: the safety margin breathes (1:06)

**This is the money shot.**

**What happens:** the radius is a function of the verdict *and its age*. With a HUMAN verdict
it expands to **158 mm** and the arm freezes. Nine seconds later a fresh, confident OBJECT
verdict collapses it to **56 mm** and the layer commits to a detour. Across the AEGIS runs the
radius was logged breathing **5.2 → 9.9 cm** and **5.4 → 16.0 cm**.

**Narration:** "Third rule — ours. The robot still believes the camera, but it also asks how
long ago it was told. Watch the red circle now. When the verdict says human, it swells and the
arm stops. When a fresh verdict says object, it collapses and the arm goes. And if no new
verdict arrives, it grows again on its own — the robot becomes more careful as its information
gets older, without anyone telling it to. Across every run, this one never let the margin go
negative."

*Paper: Figure 7, Table 6, physical-robot tier.*

### 15 and 16 — Two more repetitions (1:01, 0:53)

**What is being tested:** that the freeze-then-resume-then-route sequence is **reproducible**,
not one lucky trial.

In both, a HUMAN verdict freezes the arm mid-carry, the verdict returns to OBJECT, the layer
routes around the intruder and delivers.

**Narration:** "And to be clear that none of this was a fortunate one-off — here it is twice
more. Hand in: stop. Hand out: route around and deliver."

---

## 17 — Thirty consecutive autonomous carries (folder, ~15 min)

**What is being tested:** endurance and repeatability with no human intervention.

Thirty separate clips, `loop_000` to `loop_029`, one per carry. **30 out of 30 delivered.**

**Narration:** "Finally, thirty carries back to back with nobody touching anything. Thirty out
of thirty delivered. The safety layer is not something that gets switched on for a demo — it
is running on every single one of these."

*Suggested edit: speed these up 8–10× as a montage under the closing narration rather than
playing them in full.*

---

## 18 — One carry, both verdicts (1:42) · *the source of Figure 5*

**What is being tested:** the whole argument of the paper, inside a **single uninterrupted
carry**. The same tool, the same table, the same goal — and the intruder on the path changes
between a box and a hand several times while the robot is carrying.

**This clip is the source of Figure 5.** Its timebase has been corrected to the recorder's
measured 11.57 fps, so the time you read in the player is the robot's own clock and matches
the panel labels in the paper exactly.

**Beats:**

| Time | What happens |
|---|---|
| 0:14 | the nominal straight carry, nothing on the line — Figure 5(a) |
| **0:22** | hand on the line → verdict **HUMAN** → **frozen**, 0.0 mm — Figure 5(b) |
| **0:27** | hand withdrawn → the carry restarts on its own — Figure 5(c) |
| 0:29–0:35 | hand again → frozen again, 6.0 s |
| **0:54** | a box on the same line → verdict **OBJECT** → **routes around**, 4 cm — Figure 5(d) |
| **1:10** | the destination itself is blocked → release withheld until 8 frames prove it clear — Figure 5(e) |
| 1:13 | routes around again, 7 cm — Figure 5(f) |
| 1:20 | routes around again, 5 cm — Figure 5(g) |
| **1:29** | hand once more → frozen — Figure 5(h) |
| 1:39 | placing — Figure 5(i) |
| 1:42 | delivered |

**Result:** six **HUMAN** windows, 131 control ticks, 16.0 s total, and **0.0 mm of
commanded tool motion in every one of them**. Minimum tool–obstacle clearance during the
carry **5.9 cm**, never negative. Delivered.

**Narration:** "Watch one single carry. I keep changing what is in the way — my hand, then a
box, then my hand again — and I never touch the program. When it is a box, the robot curves
around it. When it is my hand, it stops dead. Same code, same second, same table. The only
input that changes is what the camera is looking at, and the robot's answer changes with it."

*Paper: Figure 5.*

---

## 19 — RGB-D: the moment depth agrees (0:57) · *the source of Figure 6*

**What is being tested:** **sensor fusion**, at the level of the individual control tick. The
colour channel proposes a hazard on its own; the depth channel from the same camera must land
a detection within the matching distance before the two are merged, and only then is the
enforced radius taken as the larger of the two estimates.

**This clip is the source of Figure 6.** Its timebase is corrected to the measured 11.62 fps
with the recorder's 0.64 s start offset removed, so player time is the robot's own clock.

**Beats:**

| Time | What happens |
|---|---|
| 0:06 | picking |
| 0:15 | holding 7 s so the obstacle can be placed |
| **0:22** | the box is on the line; colour proposes it; no depth match yet — Figure 6(a) |
| **0:24** | no admissible route → the layer holds rather than squeezing past — Figure 6(b) |
| **0:25** | **depth matches the colour detection** (agreement 5.4 cm) → detour committed, 3 cm — Figure 6(c) |
| **0:44** | depth confirms again (agreement 5.5 cm), detour 6 cm — Figure 6(d) |
| 0:44 | detour widened to 7 cm as the tracked footprint grows — Figure 6(e) |
| **0:57** | delivered — Figure 6(f) |

**Result:** 43 of 65 control ticks carry a colour-and-depth agreement; minimum tool–obstacle
clearance **+2.9 cm**, never negative.

**Narration:** "One camera, two independent opinions. The colour image sees something on the
path first — but the robot does not commit to a detour on that alone. Watch the moment the
depth channel agrees: only then does the plan change, and the safety bubble is drawn at
whichever of the two estimates is larger. A second before that, with no route it can trust, it
simply waits."

*Paper: Figure 6.*

---

## Suggested cut for a single YouTube video (~10 min)

| # | Clip | Suggested screen time |
|---|---|---|
| 1 | `00a` + `00b` stills | 0:20 |
| 2 | `01` calibration (speed 4×) | 0:30 |
| 3 | `03` baseline carry | 0:20 |
| 4 | `04` object → route | 0:50 |
| 5 | `05` human → freeze | 0:55 |
| 6 | `06` moving obstacle (trim to 0:20–0:60) | 0:40 |
| 7 | `07` RGB-D fusion (trim to 0:25–0:40 and 1:15–1:25) | 0:30 |
| 8 | `09` fail-safe hold (trim) | 0:30 |
| 9 | `10` endpoint guard (trim to 0:44–0:51) | 0:15 |
| 10 | **11 → 12 → 14** the three-policy comparison, back to back | 2:30 |
| 11 | `15`/`16` repeats (short) | 0:30 |
| 12 | `17` loop montage at 10× | 0:40 |

**Closing line:** "One camera, one low-cost arm, and one idea: a safety margin that knows how
old its own evidence is."

---

## Provenance

| Clip | Source recording | Session |
|---|---|---|
| 01 | `00_calibration` | 2026-07-22 live |
| 02 | `wide_calibration_25pt` | 2026-07-22 raised-camera |
| 03 | `01_baseline` | 2026-07-22 live |
| 04 | `03_static_obstacle_paths` | 2026-07-22 live |
| 05 | `05_hand_freeze_paths` | 2026-07-22 live |
| 06 | `04c_moving_central` | 2026-07-22 live |
| 07 | `rgbd_live_20260722_150347_paths` | 2026-07-22 RGB-D |
| 08 | `rgbd_obstacle_hand_20260722_151705` | 2026-07-22 RGB-D |
| 09 | `multi_live_20260722_01_paths` | 2026-07-22 RGB-D |
| 10 | `goal_block_20260722_135942` | 2026-07-22 RGB-D |
| 11 | `S1_worst_2_paths` | AEGIS hardware session |
| 12 | `S1_trust_2_paths` | AEGIS hardware session |
| 13 | `S1_trust_6_paths` | AEGIS hardware session |
| 14 | `S1_clasp_2_paths` | AEGIS hardware session |
| 15 | `trustlatest_toA_1_paths` | AEGIS hardware session |
| 16 | `trustlatest_toA_2_paths` | AEGIS hardware session |
| 17 | `loop_000`–`loop_029` | 2026-07-22 RGB-D |
| 18 | `rgbd_obstacle_hand_20260722_151705_paths` (retimed: 11.607 fps, +0.51 s) | 2026-07-22 RGB-D |
| 19 | `rgbd_flexible_20260722_151226_paths` (retimed: 11.622 fps, +0.64 s) | 2026-07-22 RGB-D |

Every per-tick log that these timings were read from is kept alongside the original
recordings in `vlm-codex/experiments/`.
