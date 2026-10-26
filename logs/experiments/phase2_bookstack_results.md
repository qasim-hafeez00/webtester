# Phase 2 results: BookStack (held-out app), harness v3

Night 2, 26 Oct 2026, label `bsrep`. BookStack 25.2.1 with the 18 injected faults of the WebTestPilot benchmark (BS01–BS18, 13 reachable by exploration; D31–D39). Harness v3 frozen (D46), check prompt v3 + persistence twin kept by the D47 rule. Nothing was tuned on BookStack (I22). Same settings as Conduit: N = 4 workers, 190k tokens per run, 30-minute cap, `gemini-3.5-flash-lite`.

Raw outputs: `logs/experiments/bookstack/compare_b0_vs_b3v2_bsrep.txt`, `compare_b3v2_vs_b4_bsrep.txt`, `gate_report_b4_bsrep.txt`. Labels: `finding_labels.toml` (D45, `by = "claude"`); 9 of them (20%, seed 46) in `label_check_sample.toml` for the blind check.

## Runs

15 of 15 valid (B0, B3v2, B4 × 5), plus the pilot (`20261026-002235`, smoke). Two attempts replaced: B0 rep 3 crashed at login after a reset (I40); B4 rep 3 hit key 9's daily quota (D41). Keys: 9 (pilot, 5 LLM runs), then 10.

Every LLM run ended on the token budget after about 8–9.5 minutes (BookStack pages are larger: about 2,750 tokens per step on B4, against the 30-minute cap). B0 has no token budget and ran 30 minutes.

## Main table (medians [IQR], n = 5 each; p = exact Mann–Whitney U)

| Metric | B0 (crawler) | B3v2 (G1) | B4 (G1+G3+G2) | B0 vs B3v2 p | B3v2 vs B4 p |
|---|---|---|---|---|---|
| Unique states | 112 [110–114] | 46 [43–52] | 38 [37–38] | 0.008 | 0.016 |
| Unique routes | 13 [13–13] | 28 [26–30] | 25 [20–25] | 0.008 | 0.079 |
| Duplicate-action rate | 80% | 20% | 22% | 0.008 | 1.000 |
| Steps | 2,042 | 86 | 73 | 0.008 | 0.008 |
| Injected faults exposed (fired, of 18) | 13 [13–13] | 10 [9–10] | 10 [10–10] | 0.008 | 1.000 |
| Injected faults found (labelled, all oracles) | 0 | 0 | 0 | 1.000 | 1.000 |
| Findings | 0 | 0 (1 in 5 runs) | 8 [7–10] | – | 0.008 |

- **No condition found any injected fault.** B0 reached all 13 reachable faults in every run, the LLM conditions 9–11, so this is "reached but not noticed", not "never reached" (D36).
- None of the 18 faults crashes or logs an error (D32), so B0 and B3v2 (implicit oracles only) cannot detect them by design. B4's inferred checks are the only oracle that could, and they did not.
- B0's many "states" are a crawler artefact (2,000 steps, 80% repeated actions, 13 routes); the LLM conditions cover more than twice the routes.

## B4 findings (39 in the 5 runs, labelled)

| Label | Count | Gate confirmed | Notes |
|---|---|---|---|
| env: no mail server configured | 7 | 7 | Password reset (POST /password/email → 500 and 'an unknown error occurred') and Add New User with an invite ('could not create user since invite email failed to send'). BookStack's default SMTP host (`smtp.mailgun.org`) rejects without credentials (I42). A real, reproducible failure of this deployment, not an app defect |
| Injected fault (BS01–BS18) | 0 | 0 | |
| Unseeded app defect (`new: ...`) | 0 | 0 | |
| fp | 32 | 30 | see below |

**Precision** (env findings counted as correct, since the failure is real; app-defect precision is 0 in every case):

| | Raw | Gated | Gated minus judge 'wrong_expectation' |
|---|---|---|---|
| B4 BookStack, pooled | 18% (7/39) | 19% (7/37) | 55% (6/11) |
| B4 Conduit v3, pooled (for reference) | 69% | 74% | 81% |

**False alarms by cause (32):**

| Cause | Count |
|---|---|
| Route guess: Settings opens `/settings/features` | 5 |
| Route guess: 'New Page' opens a draft editor (`/books/*/draft/*`) | 4 (+1 checked before the navigation finished) |
| Route: the model wrote `*` as a wildcard, route shapes compare literally (harness limitation, I41) | 4 |
| Route: a tag search adds `?search` | 3 |
| Route: other wrong guesses (chapter save, chapter copy), login timing | 3 |
| Text: a heading the form or editor does not have ('Create New Page', 'Edit Page', 'Create User', ...) | 6 |
| Text: wording ('Settings successfully saved' vs '...updated') | 3 |
| Text: other (display name 'Worker 04' vs 'worker04', typed filter text, no message at check time) | 3 |

21 of the 32 are route checks, although prompt v3 limits route checks to requested navigation: route checks are 118 of 288 checks (41%) and 30 of 46 violations.

**Gate (G2):** 37 of 39 confirmed, 2 rejected (both fp), 0 unverified. Wrong expectations about deterministic behaviour replay perfectly, so the gate cannot remove them. Gate cost: 2.7–8.0 min per run; judge tokens ≈ 1% of the run.

**Judge:** it marked 25 of the 30 confirmed false alarms `wrong_expectation` and 1 of 5 judged true findings (the two 5xx findings have no judge). On Conduit it removed 12 real findings; here it is the only filter that helps.

## Checks (G3): why nothing was noticed

| | B4 BookStack (5 runs) |
|---|---|
| Checks proposed | 288 (route 118, shows 91, changes 57, not_shows 22, count 0) |
| Violated | 46 (route 30, shows 15, changes 1) |
| Persistence twins | 24, all passed |

Steps taken on a page where an exposed fault's effect was showing, and checks made there (B4, 5 runs):

| Fault | Effect | Steps on the page | With a content check |
|---|---|---|---|
| BS02/BS03 | 'Chapter 2' / 'Page Template' missing from Recently Viewed (dashboard) | 50 / 42 | 6 / 4 |
| BS05–07, BS09 | phantom items or wrong '1 year ago' on a profile | 30 | 1 |
| BS08 | phantom search result 'Some Page' | 54 | 6 |
| BS10/BS11 | relative timestamps read '2 days ago' | 17 / 20 | 5 / 7 |
| BS01 | favourite 'Shelf' missing from My Favourites | 3 | 1 |
| BS04 | phantom book card on the Books list | 7 | 2 |
| BS12, BS13 | (never reached by B4) | 0 | 0 |

The checks the model writes are about the effect of its own action ("after Save, the page shows X"). The BookStack faults are wrong content on arrival: an item missing from a list, a phantom entry, a timestamp off by days. Noticing them needs a check about what a page *should already contain*, which needs memory of earlier pages (what was favourited or viewed) or of the data's real values. Neither the v3 prompt nor the persistence twin produces that kind of check. On Conduit the semantic faults (F06–F09) all break the effect of an action, which is why G3 worked there and not here.

## Against the KPIs (plan section 3)

| Gap | KPI | Conduit v3 (development) | BookStack (held-out) |
|---|---|---|---|
| G1 | ≥ 30% fewer duplicate actions | met | not tested (no B2 / A-G1 runs on BookStack) |
| G2 | gated precision ≥ 0.90 | 74% | 19% (55% after the judge) |
| G2 | recall loss ≤ 10 points | 21% | 0 (nothing real was rejected; 0 true app findings) |
| G2 | gate cost ≤ 25% of tokens | met | met (≈ 1%) |
| G3 | ≥ 40% of semantic faults implicit oracles miss | 4 of 6 across runs | **0 of 13** |

## What this means for the next step (for discussion)

- The held-out result does not replicate G3: inferred action-effect checks found Conduit's semantic faults but none of BookStack's, all of which are reached.
- The persistence twin and the gate behave as designed (twins pass, the gate confirms what replays), but neither helps on display-only faults.
- Measurement items that are ours, not the agent's: route wildcards (I41), the missing mail setting (I42), the slow first login after a reset (I40).
