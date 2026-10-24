# Phase 2: G2/G3 and the G1 ablation on Conduit (as of 24 Oct, labels pending)

Conditions (D29, D40): **B4** = B3 v2 frontier + inferred oracles (G3) + evidence gate (G2); **A-G1** (`b4nog1`) = B4 without the shared frontier; **B3v2-local** = B3 v2 with a per-worker frontier. n = 5 valid runs each, N = 4, 190k tokens, 30-min cap, all 10 faults on, `gemini-3.5-flash-lite`. Valid runs and keys: `run_registry.md`, D41.

Generated with `python -m webtester compare <a> <b> --workers 4` and `gate-report`. Exact two-sided Mann-Whitney U, Vargha-Delaney Â12 (D19).

**Status: exploration rows are final; every fault and precision row waits for the hand labels** (`finding_labels.toml`, 113 entries pre-filled with suggestions, `label` still blank). Gate v1 (I32) and the observation gap (I33) apply to every number below.

## G1 inside the full system: A-G1 vs B4

| Metric | A-G1 | B4 | p | Â12 (B4 > A-G1) |
|---|---|---|---|---|
| Unique states | 26 [25–31] | 30 [28–31] | 0.452 | 0.66 (medium) |
| Unique routes | 8 [8–8] | 10 [10–10] | 0.008 | 1.00 (large) |
| Duplicate-action rate | 57% [57%–62%] | 32% [31%–36%] | 0.008 | 0.00 (large) |
| Seeded faults reached (offline) | 4 [3–5] | 6 [5–6] | 0.071 | 0.86 (large) |
| Steps | 113 [113–114] | 98 [98–100] | 0.008 | 0.00 (large) |

## Sharing vs partitioning: B3v2-local vs B3v2

| Metric | B3v2-local | B3v2 | p | Â12 (B3v2 > local) |
|---|---|---|---|---|
| Unique states | 26 [25–29] | 38 [37–41] | 0.024 | 0.96 (large) |
| Unique routes | 8 [8–8] | 10 [9–10] | 0.024 | 0.96 (large) |
| Duplicate-action rate | 51% [49%–52%] | 37% [34%–38%] | 0.016 | 0.04 (large) |
| Steps | 116 [114–123] | 124 [124–125] | 0.056 | 0.88 (large) |

The G1 gain comes from sharing the frontier, not from the focus-area partitioning alone.

## Cost of G3 at equal tokens: B3v2 vs B4

| Metric | B3v2 | B4 | p | Â12 (B4 > B3v2) |
|---|---|---|---|---|
| Unique states | 38 [37–41] | 30 [28–31] | 0.008 | 0.00 (large) |
| Steps | 124 [124–125] | 98 [98–100] | 0.008 | 0.00 (large) |
| Findings (all) | 3 [2–3] | 10 [10–12] | 0.008 | 1.00 (large) |

The check instructions and checks cost about 20% of the steps, and B4 reaches fewer states.

## G2 gate (v1), per run

| Condition | Candidates → confirmed per run | Gate minutes | Judge tokens |
|---|---|---|---|
| B4 | 15→5, 10→7, 12→9, 10→6, 8→6 (1 flaky) | 2.3–4.8 | 0–1% of the run |
| A-G1 | 12→9, 13→9, 12→8, 11→4, 10→6 | 2.2–4.2 | 1% |

Precision (raw / gate-confirmed / confirmed minus judge `wrong_expectation`) waits for labels.

## Fault funnel over the 10 valid B4-family runs (PROVISIONAL: suggested labels)

| Fault | Class | Reached (runs) | Found | Found by an inferred check | Gate-confirmed | Why not found |
|---|---|---|---|---|---|---|
| F01 | crash | 4 | 4 | 3 | 2 | 2 rejected: gate state dependency (I32) |
| F02 | crash | 8 | 8 | 8 | 8 | – |
| F03 | validation | 0 | 0 | 0 | 0 | UI cannot trigger it (I34) |
| F04 | data | 8 | 0 | 0 | 0 | edit+publish done, no check on tags proposed |
| F05 | data | 6 | 0 | 0 | 0 | favorite clicked, no count check proposed |
| F06 | data | 0 | 0 | 0 | 0 | trash icon invisible to the agent (I33) |
| F07 | authorization | 10 (visit rule) | 1 | 1 | 1 | Edit shown to non-author noticed once |
| F08 | data | 0 | 0 | 0 | 0 | 'Your Feed' invisible (I33) |
| F09 | noop-ui | 9 | 4 | 4 | 2 | 2 rejected by the gate (cause not traced) |
| F10 | data | 0 | 0 | 0 | 0 | tag pills invisible (I33) |

"Reached" = the offline `reach` rule matched a step (`metrics.fault_reach`, approximate; F07's rule is a page visit, so it overstates).

**Reading:** of the 8 semantic faults (F03–F10), 4 were never reachable (3 by the observation gap, 1 by UI validation). Of the 4 reached, inferred checks found 2 (F07, F09) and missed 2 (F04, F05) because the explorer never proposed the check that would expose them.
