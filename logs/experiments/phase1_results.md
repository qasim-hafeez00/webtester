# Phase 1 results: B0 vs B1 (RealWorld/Conduit, 15 min per run, all 10 seeded faults on)

Final, generated 2026-10-12 with `python -m webtester compare b0 b1`. Valid runs only (see [run_registry.md](run_registry.md)). Exact two-sided Mann-Whitney U. Â12 = probability that a B1 run beats a B0 run (0.5 = no difference; ≥0.71 or ≤0.29 = large).

| Metric | B0 median [IQR] (n=5) | B1 median [IQR] (n=5) | p (MWU, exact) | Â12 (B1 > B0) |
|---|---|---|---|---|
| Unique states | 33 [33–33] | 36 [31–36] | 0.500 | 0.64 (medium) |
| Unique routes | 14 [14–14] | 8 [8–9] | 0.016 | 0.02 (large) |
| Duplicate-action rate | 46% [42%–46%] | 47% [44%–54%] | 0.310 | 0.72 (large) |
| Seeded faults found | 0 [0–0] | 1 [1–1] | 0.008 | 1.00 (large) |
| Findings (all) | 2 [2–2] | 1 [1–2] | 0.167 | 0.20 (large) |
| Steps | 431 [427–470] | 137 [133–138] | 0.008 | 0.00 (large) |
| Tokens | 0 [0–0] | 188,435 [186,416–197,568] | 0.008 | 1.00 (large) |

Valid runs: B0 = pilot-allfaults, rep2–rep5; B1 = b1-15min-v2, rep3, rep7, rep8, rep9. Invalid B1 runs (first-b1, b1-15min, rep2, rep4, rep5, rep6) are listed in the registry with reasons.
