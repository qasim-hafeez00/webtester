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
| F04 | data | 8 | 0 | 0 | 0 | UI-unreachable: the editor POSTs a new article instead of updating (U6, I37); the reach rule matched the edit flow, not the update |
| F05 | data | 6 | 0 | 0 | 0 | favorite clicked, no count check proposed |
| F06 | data | 0 | 0 | 0 | 0 | trash icon invisible to the agent (I33) |
| F07 | authorization | 10 (visit rule) | 1 | 1 | 1 | Edit shown to non-author noticed once |
| F08 | data | 0 | 0 | 0 | 0 | 'Your Feed' invisible (I33) |
| F09 | noop-ui | 9 | 4 | 4 | 2 | 2 rejected by the gate (cause not traced) |
| F10 | data | 0 | 0 | 0 | 0 | tag pills invisible (I33) |

"Reached" = the offline `reach` rule matched a step (`metrics.fault_reach`, approximate; F07's rule is a page visit, so it overstates).

**Reading:** of the 8 semantic faults (F03–F10), 4 were never reachable (3 by the observation gap, 1 by UI validation). Of the 4 reached, inferred checks found 2 (F07, F09) and missed 2 (F04, F05) because the explorer never proposed the check that would expose them.

---

# Harness v2 re-runs (25 Oct, label `h2rep`)

Harness v2 = observation v2 (D43, cursor:pointer elements), gate v2 (D42, full-prefix window), exposure markers (D44). Commit `a1795ff` (branch `phase2-harness-v2`). n = 5 valid runs each, N = 4, 190k tokens, 30-min cap, all 10 faults on, `gemini-3.5-flash-lite`. Keys 6 → 7 → 9 → 10 → _OLD (D41); the 3 runs lost to quota exhaustion (429) were re-run and stay listed as invalid. Generated with `compare <a> <b> --workers 4 --label-contains h2rep` and `gate-report`.

**Status:** exploration and exposure rows are final. Fault and precision rows need the hand labels (`finding_labels.toml`: 131 new blank entries from these runs, plus the 113 from 24 Oct).

## Faults fired (exact markers), runs out of 5

| Condition | F01 | F02 | F03 | F04 | F05 | F06 | F07 | F08 | F09 | F10 |
|---|---|---|---|---|---|---|---|---|---|---|
| B3v2 | 3 | 3 | 0 | 0 | 4 | 5 | 4 | 5 | 5 | 5 |
| B4 | 1 | 4 | 0 | 0 | 3 | 5 | 1 | 5 | 5 | 5 |
| A-G1 | 0 | 4 | 0 | 0 | 1 | 5 | 2 | 5 | 5 | 5 |
| A-G3 | 1 | 3 | 0 | 0 | 3 | 5 | 2 | 4 | 5 | 5 |

- F06, F08 and F10 now fire in almost every run (0 of 40 runs before D43).
- F03 never fires: it is UI-unreachable (I34).
- F04 never fires: it is UI-unreachable. The editor always POSTs a new article, even when editing, so the backend `updateArticle` (where F04 sits) is never called (upstream defect U6, I37; verified by a scripted edit on 25 Oct). The earlier guess (blocked by F02) was wrong.

## G1 inside the full system: A-G1 vs B4

| Metric | A-G1 | B4 | p | Â12 (B4 > A-G1) |
|---|---|---|---|---|
| Duplicate-action rate | 56% [54%–57%] | 28% [27%–29%] | 0.008 | 0.00 (large) |
| Unique states | 26 [23–29] | 26 [23–30] | 0.952 | 0.52 |
| Unique routes | 8 [8–8] | 9 [8–9] | 0.524 | 0.70 |
| Steps | 109 [109–110] | 94 [92–96] | 0.008 | 0.00 (large) |

The duplicate-action effect replicates on harness v2. The state and route gains seen with harness v1 (routes 10 vs 8, p = 0.008) do not.

## G3 ablation: A-G3 (no inferred checks) vs B4

| Metric | A-G3 | B4 | p | Â12 (B4 > A-G3) |
|---|---|---|---|---|
| Findings (all) | 2 [2–3] | 12 [10–13] | 0.008 | 1.00 (large) |
| Findings (gate-confirmed) | 2 [1–2] | 10 [7–10] | 0.008 | 1.00 (large) |
| Seeded faults, implicit rules | 1 [0–1] | 1 [1–1] | 0.635 | 0.66 |
| Unique routes | 10 [10–10] | 9 [8–9] | 0.032 | 0.06 (large) |
| Steps | 113 [109–119] | 94 [92–96] | 0.008 | 0.00 (large) |

The inferred checks add about 10 findings per run. Whether they are semantic faults (F05–F10) or wrong expectations needs the labels; that comparison is RQ3.

## Cost of G3 at equal tokens: B3v2 vs B4

| Metric | B3v2 | B4 | p | Â12 (B4 > B3v2) |
|---|---|---|---|---|
| Unique states | 34 [30–35] | 26 [23–30] | 0.087 | 0.16 (large) |
| Steps | 115 [114–117] | 94 [92–96] | 0.008 | 0.00 (large) |
| Duplicate-action rate | 30% [29%–35%] | 28% [27%–29%] | 0.151 | 0.20 |

## Gate v2, per run (candidates → confirmed)

| Condition | Per run | Gate minutes |
|---|---|---|
| B4 | 13→6, 12→10, 13→13, 9→7, 10→10 | 2.7–7.7 |
| A-G1 | 8→7, 10→7, 20→10, 11→7, 11→8 | 2.2–7.9 |
| A-G3 | 2→2, 3→3, 2→1, 1→1, 6→2 | 0.3–2.3 |

The judge used 1% of run tokens. Gate v2 with the full prefix takes up to 7.9 min (v1: up to 4.8).

**F01 and the gate (I36):** the implicit F01 rule (any 500 on `/comments`) over-counts. In B4 rep 1 and A-G1 rep 2 the 500 was not F01 (no backend marker; comments of 58 characters or less), and the gate rejected both, correctly. Real F01 was confirmed 3/3 in B4 rep 3. In A-G3 rep 5 the real F01 was rejected: every window, including the full prefix, hit missing elements, probably a cross-worker dependency.

## Labelled results, harness v2 (labels by Claude, D45; user blind check of 20% pending)

All 254 entries in `finding_labels.toml` are labelled (`by = "claude"`). Rule: the label is the defect without which the finding would not have happened; if the check would also fail on a correct app, it is `fp`. The user re-labels a blind random 20% (`label_check_sample.toml`, 49 entries) for Cohen's kappa.

### G3: inferred checks vs implicit oracles only (B4 vs A-G3), n = 5 each

| Metric | A-G3 | B4 | p | Â12 (B4 > A-G3) |
|---|---|---|---|---|
| True findings per run | 2 [2–3] | 5 [4–6] | 0.040 | 0.92 (large) |
| Gate-confirmed true findings | 2 [1–2] | 5 [3–6] | 0.024 | 0.96 (large) |
| Distinct defects per run (seeded + unseeded) | 2 [2–3] | 4 [3–5] | 0.048 | 0.92 (large) |
| Semantic seeded faults (F05–F10) per run | 0 [0–0] | 1 [1–1] | 0.048 | 0.90 (large) |
| Precision, raw | 100% | 50% [44%–50%] | 0.008 | – |
| Precision, gate-confirmed | 100% | 50% [50%–60%] | 0.008 | – |
| Precision, confirmed minus judge `wrong_expectation` | 100% | 60% [50%–78%] | 0.008 | – |

Defects found over the 5 runs. B4: F01, F02, F07, F08, U1, U3, U5, whitespace profile values (new), email format (new). A-G3: F01, F02, U5, whitespace profile values (new), follow of a missing user (new). Inferred checks find more real defects, and the only semantic seeded faults, at half the precision.

### G1 inside the full system (A-G1 vs B4): no labelled difference
True findings 6 vs 5 (p = 0.968), distinct defects 3 vs 4 (p = 0.135), semantic seeded 1 vs 1 (p = 1.0), precision gate-confirmed 57% vs 50% (p = 0.683). The G1 effect stays at duplicate actions.

### G2 gate and judge (all B4-family h2rep findings)
- Gate per run (`gate-report b4`): precision raw 23–62% → gate-confirmed 43–62%. A-G1: 12–55% → 14–86%.
- Real findings rejected by the gate: B4 1 of 11 rejected, A-G1 5 of 21, A-G3 3 of 5 (mostly cross-worker dependencies and races, which a reset-DB replay cannot rebuild).
- Judge on gate-confirmed inferred-check findings: it called 7 real findings `wrong_expectation`, including all 4 F08 hits (workers follow nobody, so the expected empty feed was right), and passed 16 false ones as `bug`.

### Why G3 misses F05, F06, F10 (failure funnel from traces, no LLM)
At every step that triggers a fault (offline reach rules), B4 and A-G1 runs:

| Fault | Trigger steps | Checks proposed there | What the checks were |
|---|---|---|---|
| F05 favorite count | 11 | 9 | `changes`/`route`; **no `count` check ever** |
| F06 comment delete | 46 | 35 | 33 × `not_shows` the comment **now** (all pass: the UI hides it client-side); 1 × after reload, skipped |
| F10 tag filter | 61 | 41 | `shows` the tag name / `route` / `changes`; none checks the listed articles |
| F08 Your Feed | 20 | 17 | 4 × `shows` "No articles are here... yet." violated = the 4 F08 hits |
| F09 pagination | 21 | 17 | mostly `shows`/`route` that pass; 2 `changes` violated |

The explorer reaches these faults but proposes the wrong check (F05), the right check at the wrong time (F06), or a check the language cannot express (F10: "every listed article has tag X").

### Corrections from the no-LLM checks (25 Oct)
- **F04 is UI-unreachable (I37, U6):** the editor always POSTs a new article, so the update endpoint where F04 sits is never called. The earlier "blocked by F02" was wrong.
- **Whitespace-only profile values:** `PUT /api/user` accepts `"   "` for username, email and password (scripted check).
- **The untraced `PUT /api/user` 500 (B4 rep 2) is U1:** an email collision between two accounts the same worker used. `regate --no-judge` reproduced the original gate result exactly (3/3, minimal 18 steps).
- Two unseeded race defects, exposed only by parallel workers: a comment on a just-deleted article and a follow of a just-renamed user both return 500, not 404.
