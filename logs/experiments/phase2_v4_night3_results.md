# Phase 2, harness v4: Night 3 results (labelled)

Harness v4 locked at `540887e` (D49–D54). Night 3, 27–28 Oct: B3V3 (implicit oracles only, v4 harness) vs B4 (full system), N = 4 workers, 190k tokens per run, 30 min cap, 5 reps per condition and app. Conduit = development app (`h4rep`), BookStack = second app (`bs4rep`; it shaped v4's rules, so it is no longer held out; PrestaShop is the held-out test).

20 of 20 valid (run notes in `run_notes.toml`); 4 invalid attempts (key quota, Docker stop; I48). No 429s in any valid run; every worker stopped on its token budget.

**Labels:** all 159 findings labelled by Claude (`by = "claude"`, D45 rule: the defect without which the finding would not have happened, else `fp`). Blind 20% check by the user still pending. Raw outputs: [night3/](night3/) (`compare_*`, `gate_report_*`, `labelled_precision.txt`); recompute with `python scripts/night3_precision.py`.

| App, condition | Findings | Label split |
|---|---:|---|
| Conduit B3V3 | 9 | U5 5, F02 3, F01 1 |
| Conduit B4 | 98 | fp 18, F10 18, F06 18, F01 14, U3 10, F02 8, F09 5, new (whitespace settings) 3, U5 2, F07 2 |
| BookStack B3V3 | 0 | – |
| BookStack B4 | 52 | fp 32, BS05 10, BS06 5, BS10 2, BS04 2, BS03 1 |

How the new v4 finding kinds were labelled (decided against run traces, run memory and, for BookStack, the live app with no faults):
- I-submit on a comment at the step where the POST returned 500 → F01 (a 5xx counts as neither accepted nor rejected, so the rule words it "nothing was sent"); I-submit in the editor with a tag containing a space → F02 (addTag throws, the submit is aborted). Checked for all 9.
- I-delete of a comment that stays → F06 (all 18 are comment deletes on article pages).
- I-create / I-edit whose object is a description, not the typed value ('session', 'special comment', 'worker02 settings') → fp. Exceptions: the whitespace comment (U3) and the blank username (new: whitespace settings), because a correct app would have rejected the input and no finding would exist.
- R02 404 on `/link` (3 runs) → fp: it is the hidden placeholder anchor of BookStack's page picker (`<a hidden href=".../link">`), filled in by JS; no user can click it.
- Old shelf slug 404 after a rename → fp: BookStack 25.x has no slug redirect (checked live with no faults).
- R11 on Conduit's favourite button '0' → fp (the rule took the count for a page number; R11 compares item names only, so F05 cannot be behind it).
- BookStack rep 4, R09 'Page Template' gone from the dashboard list on the worker's 2nd arrival → **BS03**; R09 'Book' appeared and R02 'Book' → `/books/book-duplicate` 404 on the 2nd arrival at Books → **BS04**. Neither was counted by the exposure markers (I44, I49).

## Seeded / injected faults found

| Metric (per run, median [IQR]) | B3V3 | B4 | p (MWU, exact) | Â12 |
|---|---|---|---|---|
| Conduit seeded faults, labelled | 1 [0–1] | **5 [5–5]** | 0.008 | 1.00 |
| Conduit semantic faults (F05–F10) | 0 | **3** [3,3,4,4,3] | – | – |
| BookStack injected faults, labelled | 0 [0–0] | **2 [2–3]** | 0.008 | 1.00 |

Per run: Conduit B4 [5, 5, 5, 6, 4], B3V3 [0, 1, 2, 0, 1]; BookStack B4 [3, 2, 2, 4, 2], B3V3 [0, 0, 0, 0, 0]. Every B4 fault was also gate-confirmed in its run.

Across runs:
- **Conduit B4:** F01 5/5, F02 3/5, F06 5/5, F07 2/5, F09 5/5, F10 5/5. Semantic: 4 of the 6 UI-reachable (F06, F07, F09, F10), 3 per run. F05 and F08 were never found.
- **v3 B4 (Night 1):** 2 semantic faults per run, also 4 of 6 across runs (F06, F07, F08, F09). v4 gains F10 and loses F08.
- **Conduit B3V3:** F01 1/5, F02 3/5; 0 semantic.
- **BookStack B4:** BS05 5/5, BS06 5/5, BS10 1/5, BS03 1/5, BS04 1/5. That is 5 distinct of 18. Of the 11 faults B4 is known to have fired (9 by the markers, plus BS03 and BS04), it found 5.
- **BookStack B3V3 and v3 B4:** found 0, though v3 B4 reached 13 faults.

## Precision

| | Raw | Gate-confirmed | Confirmed minus judge `wrong_expectation` |
|---|---|---|---|
| Conduit B4 v4, pooled | 82% (80/98) | **88% (78/89)** | 89% (75/84) |
| Conduit B4 v4, per run median | 81% | 89% | 89% |
| Conduit B4 v3 (Night 1), pooled | 69% | 74% | 81% |
| BookStack B4 v4, pooled | 38% (20/52) | **48% (19/40)** | 49% (17/35) |
| BookStack B4 v4, per run median | 43% | 50% | 50% |
| BookStack B4 v3 (Night 2), pooled | 18% | 19% (all 7 true ones were `env`, app-defect precision 0) | 55% |

B3V3 precision on Conduit is 100% (9/9; one run had no findings); on BookStack it has no findings.

- **Confirmed false alarms per run (median):** Conduit 2 (v3: 3); BookStack 5.
- **Gate recall loss** (real findings not confirmed): Conduit 2 of 80 (2.5%), BookStack 1 of 20 (5%); v3 Conduit was 21%.
- **The judge** drops 5 confirmed findings per app, 3 real on Conduit and 2 real on BookStack. "Minus judge" therefore barely moves precision.
- **Gate time:** 12.6–22.6 min per run on Conduit, 7.0–21.8 on BookStack (cap 20 min, overrun in 5 of 10 runs).
- **Judge cost:** at most 2% of the run's tokens.

### Precision per rule (B4; all findings tp/n, confirmed tp/n)

| Rule | Conduit | BookStack |
|---|---|---|
| I-filter | 18/18, 18/18 | 0/2, 0/1 |
| I-delete | 18/18, 17/17 | – |
| R17 (whitespace accepted) | 9/9, 9/9 | – |
| I-submit | 9/11, 9/9 | 0/1, 0/1 |
| R16 (long value → 5xx) | 5/5, 5/5 | – |
| R11 (pagination) | 5/6, 5/6 | – |
| R13 (offered action refused) | 2/2, 2/2 | – |
| R03 (dead link among live siblings) | – | 10/10, 10/10 |
| R04 (count vs list) | – | 5/5, 5/5 |
| R08 (same item, two timestamps) | – | 2/2, 2/2 |
| R09 (list changed, no cause) | 0/4, 0/0 | 2/9, 2/4 |
| R02 (link 404) | – | 1/6, 0/3 |
| **I-create** | **1/8, 1/8** | **0/10, 0/9** |
| I-edit | 1/3, 1/3 | 0/2, 0/2 |
| G2, R10, R12, I-toggle | 0/1 (R12), 0/1 (I-toggle) | 0/2 (G2), 0/2 (R10) |
| Implicit (console, 5xx, oracle) | 12/12, 11/11 | 0/1, 0/1 |

### False alarms by cause (50)

| Cause | Conduit | BookStack |
|---|---:|---:|
| I-create/I-edit object is not the typed value: login intents ('session', 'login') | 5 | 9 |
| same, other description objects or stripped markup ('special comment', 'Shelf Test Name! @#%', password reset) | 4 | 3 |
| List changed through other workers (R09), activity rotation, renamed shelf (old slug 404, name dropped) | 4 | 10 |
| R02 probe of the hidden page-picker anchor `/link` | 0 | 4 |
| Rule misreads: favourite count as page number (R11), Markdown HTML (R12), follow count (I-toggle), tag link opens search (R10), filter checkbox read as search term, GET search re-submit as I-submit, relative time advancing (G2) | 3 | 6 |
| Settings submit not reproduced by the gate | 2 | 0 |

The login-intent I-create alone is 5 of Conduit's 11 confirmed false alarms and 9 of BookStack's 21.

**Post-hoc only, not a result:** suppressing it would give gate-confirmed precision of 93% (78/84) on Conduit and 61% (19/31) on BookStack. Any fix would be a post-lock change, needs a new decision, and must be tested on PrestaShop, not on these runs.

## Exploration and cost

| Metric (median) | Conduit B3V3 | Conduit B4 | p | BookStack B3V3 | BookStack B4 | p |
|---|---|---|---|---|---|---|
| Unique states | 27 | 31 | 0.325 | 45 | 37 | 0.143 |
| Duplicate-action rate | 41% | 33% | 0.008 | 23% | 23% | 0.841 |
| Steps | 119 | 89 | 0.008 | 89 | 68 | 0.008 |
| Tokens per run | 197k | 199k | 0.222 | 200k | 202k | 0.016 |
| Injected faults exposed (markers) | – | – | – | 10 | 7 | 0.008 |

B4 spends about a quarter fewer steps of the same token budget: the consistency sweep and per-step memory make prompts larger. On BookStack it fires fewer faults by the markers (7 vs 10), yet finds 2 per run where B3V3 finds 0.

## KPI check (plan §3, provisional KPIs)

| Gap | KPI | Conduit (development) | BookStack (no longer held out) |
|---|---|---|---|
| G2 | gate-confirmed precision ≥ 0.90 | 88% pooled, 89% per-run median: **no**, close (v3: 74%) | 48%: **no** (v3: 19%) |
| G2 | recall loss ≤ 10 points | 2.5%: yes (v3: 21%) | 5%: yes |
| G2 | gate cost ≤ 25% of tokens | judge ≤ 2%: yes (plus 7–23 min of replay) | yes |
| G3 | inferred oracles find ≥ 40% of the semantic faults implicit oracles miss | 4/6 = 67% across runs, 3/6 = 50% per run: **yes, both** (v3: across runs only) | 5/18 = 28% across runs, 2/18 per run: **no** (v3: 0/18) |

G1 is not tested here: B3V3 and B4 both use the v4 frontier, so the duplicate-rate difference is not the G1 effect.

## Caveats

- Labels are Claude's. The user's blind 20% re-label (D45) and Cohen's kappa are still to do.
- BookStack shaped v4's rules (D53, D54), so its v4 numbers are development numbers. PrestaShop (Night 4, targets pre-registered under D51) is the held-out test.
- n = 5 per condition. The exact Mann-Whitney minimum p is 0.008, so p = 0.008 is the strongest result this design can give.
- The BookStack exposure markers miss faults that fire on a page's 2nd arrival (BS03, BS04 found but not marked; I44, I49). "Exposed" therefore undercounts reach.
