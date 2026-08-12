# On-device VLM latency benchmark — 2026-07-17

Question: can a local VLM give the hazard verdict **under 0.5 s** (fast-monitor tier)
instead of the hosted 1.6–2.7 s? Protocol = the same 20 real D435i frames
(`figs/vlm_eval/{safe,hazard}`, 10+10), single-word verdict, warmup excluded.
Machine: Apple Silicon (M-series), MLX/Metal, no CUDA. Harness:
`scratchpad/fastvlm_bench.py`.

## Result

| Backend | Where | Accuracy | Hazard recall | False-stop | Latency mean / p95 |
|---|---|---|---|---|---|
| Gemma-3-12B-IT | OpenRouter (hosted) | 100% (20/20) | 10/10 | 0/10 | 1.6 s / 4.1 s |
| Claude Haiku 4.5 | Anthropic (hosted) | 90% (18/20) | 10/10 | 2/10 | 2.7 s / 4.9 s |
| SmolVLM-256M-4bit | **local** MLX | 5% (1/20) | 0/10 | 9/10 | 0.66 s / 0.68 s |
| **FastVLM-0.5B** | **local** MLX | **100% (20/20)** | **10/10** | **0/10** | **0.24 s / 0.25 s** |

FastVLM identical at 256 px and 512 px input (0.24 s) → latency is vision-encode-bound,
not decode/resolution-bound. Every FastVLM call was under 0.5 s.

## Findings

1. **Sub-0.5 s achieved: FastVLM-0.5B at 0.24 s mean / 0.25 s p95** — 7× faster than
   Gemma, 11× faster than Haiku, with equal (perfect) accuracy on this set, and fully
   **offline / free / no rate limits**.
2. **Prompt matters more than size.** A forced binary label ("answer CLEAR/HAND")
   collapses small VLMs to one class (FastVLM → always "Yes", 50% acc). A concrete
   **count** ("how many human hands? answer a number") is clean: SAFE→0, HAND→1.
   This count IS a human detector → gives the semantic HUMAN-vs-OBJECT split the
   geometric layer needs (a box counts 0 hands → route around; a hand → stop).
3. **Smaller is not faster.** SmolVLM-256M (half the params) was both slower (0.66 s)
   and non-discriminating (said "1"/"One" for empty and hand alike). FastVLM's
   efficient FastViTHD encoder is the reason it is fast — not raw parameter count.

## What it changes for the paper

- New backend row for `tab:vlmbackends`: hosted → **local FastVLM-0.5B, 0.24 s**.
- Narrows the §latency limitation. With reaction ≈ 0.24 s (verdict) + tick + settle
  ≈ 0.5 s total, the required safety bubble for a 0.5 m/s hand shrinks from ~1.4 m
  (Gemma 1.6 s) to ~0.25 m — the semantic layer moves from *quasi-static only* toward
  *slow moving hazards too*.
- Architecture story stays true (async slow-VLM + fast geometric layer) but the
  "slow" layer is now 0.24 s, i.e. an on-device monitor, not a cloud round-trip.

## Files
- Reusable monitor: `vlm-codex/safebench/fastvlm_monitor.py` (SAFE/ABORT, count prompt)
- Per-run JSON: `vlm-codex/data/fastvlm_bench/*.json`
- Harness: session scratchpad `fastvlm_bench.py`, `fastvlm_probe.py`
- Models cached in `~/.cache/huggingface` (FastVLM-0.5B-bf16 ~1 GB; needs `timm`)
