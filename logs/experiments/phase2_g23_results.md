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

---

# Harness v3 runs (25 Oct, label `h3rep`, D46): exploration and gate (labels pending)

Harness v3 (D46), commits `7784d6c`/`d6094ef`. n = 5 valid runs each, N = 4, 190k tokens, 30-min cap, all 10 faults on, `gemini-3.5-flash-lite`. Keys: primary → 4 → 5 → 6 → 7 (D41). 25 runs with summaries (20 valid, 5 invalid: 3 quota, 1 primary-key 403/429, 1 stall) plus 4 attempts killed with no summary (I39: process tree ended; probable cause the memory commit limit). Generated with `compare <a> <b> --workers 4 --label-contains h3rep` and `gate-report`.

**Status:** exploration and gate rows final; fault and precision rows need labels (next step, D45 process), then the D47 rule.

## G1 inside the full system: A-G1 vs B4

| Metric | A-G1 | B4 | p | Â12 (B4 > A-G1) |
|---|---|---|---|---|
| Duplicate-action rate | 60% [49%–62%] | 31% [29%–32%] | 0.008 | 0.00 (large) |
| Unique routes | 7 [7–7] | 9 [9–9] | 0.048 | 0.88 (large) |
| Unique states | 22 [18–27] | 28 [27–31] | 0.175 | 0.78 (large) |
| Steps | 102 [102–104] | 91 [90–91] | 0.008 | 0.00 (large) |

The duplicate-action effect replicates a third time (v1, v2, v3). The route gain is back (v1: p = 0.008, v2: p = 0.524, v3: p = 0.048); states not significant.

## G3 ablation: A-G3 vs B4

| Metric | A-G3 | B4 | p | Â12 (B4 > A-G3) |
|---|---|---|---|---|
| Findings (all) | 3 [2–3] | 13 [10–14] | 0.008 | 1.00 (large) |
| Findings (gate-confirmed) | 2 [2–3] | 10 [9–10] | 0.008 | 1.00 (large) |
| Unique states | 34 [31–37] | 28 [27–31] | 0.143 | 0.20 |
| Steps | 114 [112–118] | 91 [90–91] | 0.008 | 0.00 (large) |

## Cost of G3: B3v2 vs B4

| Metric | B3v2 | B4 | p | Â12 (B4 > B3v2) |
|---|---|---|---|---|
| Steps | 115 [113–117] | 91 [90–91] | 0.008 | 0.00 (large) |
| Unique states | 31 [26–31] | 28 [27–31] | 0.849 | 0.44 |
| Duplicate-action rate | 38% [36%–40%] | 31% [29%–32%] | 0.032 | 0.08 (large) |

## What v3 changed for the semantic faults (checks at trigger steps, B4 + A-G1 valid runs)

| Fault | v2 (`h2rep`) | v3 (`h3rep`) |
|---|---|---|
| F06 comment delete | 33 × "gone now" passed, 0 failing checks | 25 × "gone now" passed, **24 automatic after-reload twins failed** + 2 model reload checks failed |
| F05 favorite count | no `count` check | still no `count` check (3 `changes` checks) |
| F10 tag filter | no content check | unchanged (needs a relational check, I22) |

F06-type findings ("deleted comment still shown after reload", `not_shows|/article/*|reload`): **gate-confirmed in 5/5 A-G1 runs and 2/5 B4 runs** (2 more B4 unverified); the judge said bug for 13 of 15 confirmed. To be confirmed by labels (the F06 backend marker fired in every v3 run).

## Gate v3, per run (candidates → confirmed / rejected / unverified)

| Condition | Per run | Gate minutes |
|---|---|---|
| B4 | 7→6/1/0, 10→9/0/1, 13→10/2/1, 18→10/1/7, 14→11/2/1 | 4.0–8.9 |
| A-G1 | 16→13/3/0, 13→12/1/0, 17→15/1/1, 19→8/1/9 (+1 flaky), 15→10/2/3 | 5.0–12.8 |
| A-G3 | 3→2/1/0, 5→3/1/1, 3→3/0/0, 2→1/0/1, 2→2/0/0 | 0.5–2.5 |

`rejected` is now rare (1–3 per run); findings the replay could not rebuild go to `unverified` (D46 fix 7).

## Labelled results, harness v3 (labels by Claude, D45; 157 findings, blind 20% check pending)

All 157 findings of the 15 valid gated `h3rep` runs labelled (`by = "claude"`), same rule as v2: the defect without which the finding would not have happened, else fp. Split: fp 47, F02 40, F06 18, U5 13, new 12, F08 11, F07 4, U2 4, F01 3, F09 2, U6 2, U3 1. v2 labels updated where v3 checks changed the picture (I38) and the follow race renamed to cover unfollow.

### Per run (medians, n = 5)

| Metric | A-G3 (implicit only) | A-G1 (no frontier) | B4 (full system) |
|---|---|---|---|
| True findings | 3 | 11 | 8 |
| Distinct defects (seeded + unseeded) | 3 | 4 | 5 |
| Seeded faults found | 1 | 3 | 3 |
| Semantic seeded faults (F05–F10) | 0 | 2 | 2 |
| Precision, raw | 100% | 69% | 70% |
| Precision, gate-confirmed | 100% | 83% | 67% |
| Precision, confirmed minus judge `wrong_expectation` | 100% | 91% | 100% |
| Confirmed false alarms | 0 | 2 | 3 |

Pooled over 5 runs: B4 62 findings, 43 real (69%); confirmed 46, 34 real (**74%**); minus judge 22/27 (81%), but the judge discards 12 real confirmed findings. A-G1: 65% → 78% → 92%. Gate cost: judge 1.2–1.8% of exploration tokens; gate 4–13 min per run.

### G3 ablation (B4 vs A-G3)

| Metric | A-G3 | B4 | p | Â12 |
|---|---|---|---|---|
| True findings | 3 | 8 | 0.016 | 0.98 |
| Gate-confirmed true findings | 2 | 7 | 0.008 | 1.00 |
| Distinct defects | 3 | 5 | 0.016 | 0.98 |
| Seeded faults | 1 | 3 | 0.008 | 1.00 |
| Semantic seeded faults | 0 | 2 | 0.008 | 1.00 |

Seeded faults found by B4 over 5 runs: F01 (1 run), F02 (4), **F06 (4)**, F07 (2), **F08 (3)**, F09 (2). A-G1: F02 (4), **F06 (5)**, **F08 (5)**. A-G3: F01 (1), F02 (4). Over the 6 UI-reachable semantic faults (F05–F10; F03, F04 are UI-unreachable), B4 found 4 (67%) across runs, 2 (33%) per run; implicit oracles alone found none.

### G1 (B4 vs A-G1), labelled
True findings 8 vs 11 (p = 0.421), distinct defects 5 vs 4 (p = 0.246), semantic 2 vs 2 (p = 1.0). The frontier changes exploration (duplicates, routes), not what is found.

### D47 outcome: v3's check changes are kept for BookStack
B4 v3 vs B4 v2 (labelled): semantic seeded faults per run 2 vs 1 ([3,2,2,2,2] vs [1,1,1,0,1], p = 0.008); confirmed false alarms per run 3 vs 4. The rule (semantic not lower, false alarms at most +2) holds. A-G1 also gained: semantic [2,2,2,2,2] vs [1,1,2,1,0], gate-confirmed precision 83% vs 57%.

### Unseeded defects found by the agents (v2 + v3), confirmed by code reading
- Follow/unfollow of a user who no longer exists returns 500 (`followUser`/`unfollowUser` update without an existence check): 7 race instances (another worker renamed the user 4–46 s earlier).
- Comment on a deleted article returns 500 (`addComment`): 3 instances.
- Favorite of a deleted article returns 500 (`favoriteArticle`): 1 instance.
- Whitespace-only profile values accepted (username, email, password): several runs.
- Email format not validated (sign-up and settings).
Plus upstream U1, U2, U3, U5, U6 hits. The race defects are visible only because several workers act at once, and the gate cannot confirm them on a reset app (they end `unverified`/`rejected`).

### KPI check (plan §3, provisional KPIs; Conduit = development app)

| Gap | KPI | v3 result | Met? |
|---|---|---|---|
| G1 | ≥ 30% lower duplicate-action rate | 31% vs 60% (−48% relative), p = 0.008 | yes (at N = 4, not N = 8) |
| G1 | ≥ 15% more unique states, significant | 28 vs 22 (+27%), p = 0.175 | no (not significant) |
| G2 | gate-confirmed precision ≥ 0.90 | 74% pooled (81% minus judge) | no |
| G2 | recall loss ≤ 10 points | 21% of real findings not confirmed (mostly unverified: cross-worker data and races) | no |
| G2 | gate cost ≤ 25% of tokens | judge 1.2% of tokens (+ 4–13 min of replay) | yes |
| G3 | inferred oracles find ≥ 40% of the semantic faults implicit oracles miss | 4/6 = 67% across runs (2/6 per run); implicit-only 0/6 | yes across runs, no per run |
