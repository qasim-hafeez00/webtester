# Phase 2 G1 results: B2 vs B3 v1 vs B3 v2 (RealWorld/Conduit, 4 workers, all 10 seeded faults on)

Final for the G1 comparison, generated 2026-10-15 with `python -m webtester compare <a> <b> --workers 4 --label-contains g1`. Valid runs only (see [run_registry.md](run_registry.md)). Budget per run: 190k tokens shared by the 4 workers, 30-min safety cap (D24); every valid run stopped on its token budget. Model `gemini-3.5-flash-lite` throughout. Exact two-sided Mann-Whitney U. Â12 = probability that the second condition beats the first (0.5 = no difference; ≥0.71 or ≤0.29 = large).

Conditions: **B2** = 4 unmodified B1 workers (`b1`). **B3 v1** = advisory shared frontier (`b3`, D23). **B3 v2** = nav filtering, per-worker focus areas, input-class marks (`b3v2`, D25), frozen after the 14 Oct pilot.

## B2 vs B3 v2

| Metric | B2 median [IQR] (n=5) | B3 v2 median [IQR] (n=5) | p (MWU, exact) | Â12 (B3 v2 > B2) |
|---|---|---|---|---|
| Unique states | 32 [28–33] | 38 [37–41] | 0.024 | 0.96 (large) |
| Unique routes | 9 [8–9] | 10 [9–10] | 0.190 | 0.80 (large) |
| Duplicate-action rate | 56% [55%–57%] | 37% [34%–38%] | 0.008 | 0.00 (large) |
| Seeded faults found | 1 [1–1] | 2 [1–2] | 0.492 | 0.66 (medium) |
| Findings (all) | 2 [1–3] | 3 [2–3] | 0.571 | 0.66 (medium) |
| Steps | 139 [139–144] | 124 [124–125] | 0.008 | 0.00 (large) |
| Tokens | 193,942 [192,605–194,315] | 196,612 [196,608–196,740] | 0.056 | 0.88 (large) |

## B3 v1 vs B3 v2

| Metric | B3 v1 median [IQR] (n=5) | B3 v2 median [IQR] (n=5) | p (MWU, exact) | Â12 (B3 v2 > B3 v1) |
|---|---|---|---|---|
| Unique states | 31 [29–32] | 38 [37–41] | 0.008 | 1.00 (large) |
| Unique routes | 8 [8–9] | 10 [9–10] | 0.048 | 0.92 (large) |
| Duplicate-action rate | 51% [48%–56%] | 37% [34%–38%] | 0.008 | 0.00 (large) |
| Seeded faults found | 1 [1–1] | 2 [1–2] | 0.524 | 0.62 (small) |
| Findings (all) | 1 [1–2] | 3 [2–3] | 0.365 | 0.70 (medium) |
| Steps | 134 [133–135] | 124 [124–125] | 0.008 | 0.00 (large) |
| Tokens | 195,750 [195,146–196,093] | 196,612 [196,608–196,740] | 0.421 | 0.68 (medium) |

## B2 vs B3 v1

| Metric | B2 median [IQR] (n=5) | B3 v1 median [IQR] (n=5) | p (MWU, exact) | Â12 (B3 v1 > B2) |
|---|---|---|---|---|
| Unique states | 32 [28–33] | 31 [29–32] | 0.738 | 0.42 (small) |
| Unique routes | 9 [8–9] | 8 [8–9] | 0.873 | 0.42 (small) |
| Duplicate-action rate | 56% [55%–57%] | 51% [48%–56%] | 0.310 | 0.28 (large) |
| Seeded faults found | 1 [1–1] | 1 [1–1] | 1.000 | 0.58 (small) |
| Findings (all) | 2 [1–3] | 1 [1–2] | 0.762 | 0.42 (small) |
| Steps | 139 [139–144] | 134 [133–135] | 0.016 | 0.04 (large) |
| Tokens | 193,942 [192,605–194,315] | 195,750 [195,146–196,093] | 0.032 | 0.92 (large) |

## What the numbers say

- **B3 v1 = B2.** The advisory frontier changed nothing measurable (I16).
- **B3 v2 > B2 and > B3 v1 on exploration**: about 20% more unique states (significant against both) and about a third fewer duplicate actions (p = 0.008 against both), with **about 10% fewer steps** under the same token budget. The coordination text makes each prompt longer.
- **No significant gain in seeded faults found.** The implicit oracles can only see F01 and F02 (D11). B3 v2 found both in 4 of 5 runs, B2 in 1 of 5 (median 2 vs 1, p = 0.49). With crash-only oracles the ceiling is 2/10, so G1 cannot show a fault-finding gain until G3 exists.

## Threats to keep in mind

- **No `b3v2local` ablation yet.** The gain may come from focus areas and nav filtering alone (a per-worker map) rather than from *sharing* the frontier. The G1 claim ("shared") needs B3 v2-local at n = 5.
- **Designed on the test subject.** B3 v2 was designed from B3 v1 traces on this same app and fault set (D25). A second app is needed before the result is reported as general.
- **Key rotation.** B2 rep 5, B3 v1 rep 5 and B3 v2 reps 1–5 ran with `key_fallback = true`. Same model throughout, so the measurements are comparable, but one attempt hit the 403 project block again (I17).
- **Machine load.** B3 v2 reps 4–5 ran while 21 unrelated Docker containers were up (I19). Both runs are healthy and have normal step counts.
- **N = 4 only, one app, n = 5.**

## Valid runs

- **B2:** `g1rep1`, `g1rep2`, `g1rep3` (14 Oct 01:41), `g1rep4` (14 Oct 12:05), `g1rep5` (14 Oct 17:26).
- **B3 v1:** `g1rep1`, `g1rep2`, `g1rep3` (14 Oct 02:25), `g1rep4` (14 Oct 12:20), `g1rep5` (14 Oct 17:43).
- **B3 v2:** `g1rep1`, `g1rep2` (14 Oct), `g13`, `g14`, `g15` (15 Oct; the labels mean g1 reps 3–5).

Invalid runs (I17 403s, 429s, network outages, wrong budget) are listed in the registry with their reasons.
