# v5.0 lock checklist (D62)

Everything left before the v5.0 lock, and what moves to v5.1. Owner: **U** = the user (needs the LLM key, a
judgement, or a third-party search), **A** = the assistant (code, replays without an LLM, scripts). Tick an item
here when it is done and name the run, file or D/I number that shows it. Plan: `docs/v5_plan.md` sections 6,
12.2 and 15; procedure: D62.

## 1. Lock criteria (plan section 6, phase 1)

Per development app (Conduit, BookStack), measured by the final resweep (step 2.4) with
`python scripts/lock_check.py --ver v62 --ref v5 --md logs/experiments/v5dev/lock_check_v62.md`:

| Criterion | Threshold | Reference |
|---|---|---|
| Recall | mutation score and median per-run recall not below the D55 v5 resweep | BookStack 8/13, median 0.46; Conduit 7/8, median 0.75 |
| Precision per finding | >= 0.90, no finding unlabelled | v5 resweep: BookStack 0.95, Conduit 0.99 |
| Clean false alarms | <= 0.5 per run, no clean finding unlabelled | v5 resweep: BookStack **0.6** (over), Conduit 0.4 |

A rule enters v5.0 only with (1) a fixture test, (2) check rows from the resweep, armed at least once,
(4) its clean findings labelled, (5) its findings labelled (section 12.2; `lock_check.py` reports (3), a seeded
fault of its family, without requiring it). Rules that fail stay built but are left out of v5.0's numbers.

## 2. Steps to the lock, in order

| # | Step | Owner | Status | Command / evidence |
|---|---|---|---|---|
| 2.1 | Pilot resweep of the 10 Night 3 b4 runs, faulty and clean, every v5 rule on (finds false alarms before the freeze) | A | **done** 29 Oct 23:11 (20 replays) | `bash scripts/resweep_d59.sh` -> `logs/experiments/v5dev/*/v59_*`; log `resweep_d59.log`. Mixed code: R33, R49 and the I-edit and abort rows changed while it ran (D62), so it is a pilot, not the lock measurement |
| 2.2 | Label the pilot's new signatures; fix or drop each rule with clean false alarms; log each change | A, **U checks the labels** | **done** by A (167 labelled; 10 rule causes fixed, I83-I95; R30 open, I94); the user's check of the labels is open | `python scripts/eval_v5dev.py --ver v59 --unlabelled`; labels in `v5dev/resweep_labels.toml` (by = claude, D45 rule; unverified ones fp); lock check on the pilot: `logs/experiments/v5dev/lock_check_v59_pilot.md` |
| 2.3 | Code freeze: commit the v5.0 candidate | U says when | to do; first remove the `#` before `exclude_rules` in both dev configs (D62b) | `git commit` on `phase2-harness-v4` (no AI co-author line) |
| 2.4 | Final resweep on the frozen code | A | **done**: v62 (30 Oct 01:30, hash b1b3c3ab); the exclusion switch then changed the code, so **v63** (04:06, hash **2964342f**, report `v5dev/lock_check_v63.md`) is the lock measurement | `bash scripts/resweep_lock.sh` (VER=v62); it writes a hash of `src/webtester` to `v5dev/v62_code.txt`, and the commit (2.3, may come after) must give the same hash. No tests or other runs alongside (I84) |
| 2.5 | Lock check against the criteria in section 1 | A | **done**: both apps pass with ten rules left out (D62a); the set is the user's decision | `python scripts/lock_check.py --ver v62 --ref v5` |
| 2.6 | Live pilots: b4 and b5, 2 workers, 5 min, per development app, every v5 mechanism on (D55 E1-E3, I60) | **U** | to do | `bash scripts/pilots_v5.sh` (not during a resweep); then `python -m webtester registry` |
| 2.7 | Review the D51 freeze list (every cap, tolerance, default, tier) and write D51 (PrestaShop targets, I50) before any PrestaShop run | **U** decides, A drafts | **drafted** 30 Oct: `docs/d51_preregistration.md` (values marked [U] are the user's; sign it before Night 4) | `docs/d51_freeze.md` (`python scripts/freeze_list.py`) |
| 2.8 | Lock: tag the commit, record it with the numbers | U says when | to do | `git tag v5.0`; a D-number with the commit and the lock-check table |
| 2.9 | Night 4 on v5.0: Conduit, BookStack, PrestaShop held-out per D51 | **U** | after the lock | course numbers from v5.0 (submission 4 Nov) |

## 3. Items handed over on 29 Oct, and where each one stands

| Item | Blocks | Owner | Status |
|---|---|---|---|
| `bash scripts/resweep_d59.sh` | v5.0 | A (asked on 29 Oct) | running as the pilot (2.1); final run 2.4 |
| b4 and b5 live pilot per development app | v5.0 | U | script ready: `scripts/pilots_v5.sh` (2.6) |
| The seven login and second-account probes (R24, R24b, R28, R46, R46w, R66, R67) and I-logout: no fixture test, only the resweep | v5.0 for those rules only | A reads their check rows | they enter v5.0 only if the final resweep arms them and their findings are labelled; otherwise they stay out (I59). `test_every_built_rule_has_a_fixture_test` keeps the list at these eight |
| Clean corpus (Parabank, Juice Shop), held-out apps, rebranded BookStack, scaling runs | v5.1 (phase 3) | U | app setups untested (I55); held-out only after D51 |
| Real historical faults (8-15, E5 a) | v5.1 | U chooses who selects them (I58) | protocol: `apps/bookstack/historical/README.md` |
| The 60 real extraction pages | v5.1 | U labels | I57; `scripts/extraction_bench.py` |
| Report ratings (reproduction, actionability, triage time) | v5.1 | U rates | `docs/report_quality_protocol.md`, `scripts/report_sample.py` |
| Severities of the seeded faults (E8) and the app types, primitives and frameworks in the dev configs (I72) | before numbers are reported (per-type and severity-weighted recall) | **U** checks | `apps/*/faults/faults.toml` (`severity`), `configs/*.toml` (`app_type`, `primitives`, `framework`) |

## 4. Known before the lock

- BookStack's clean false alarms were already 0.6 per run in the D55 v5 resweep; without R09 (2 of the 3)
  they were 0.4 (`lock_check.py --ver v5 --ref v4`). R09 is the first candidate to leave v5.0 if the pilot
  shows the same.
- Done for the lock on 29 Oct (D62): fixture tests for every built rule except the eight above (27 rules
  added, `tests/test_d62_rules.py`); the lock check script; 7 rule bugs found by those tests (I76-I82).
- **Pilot result (29 Oct)**: with every v5 rule both apps fail (BookStack precision 0.57, 10.8 clean false alarms
  per run; Conduit 0.53, 6.0). Without the 16 rules under the precision floor both pass (0.97 and 0.4; 0.99 and 0.2),
  recall equal to the D55 resweep. Ten causes of those false alarms are fixed (I83, I85-I93, I95), so the final
  resweep (2.4) will show which rules still need leaving out. Still unexplained or unverified: R30 (I94), R50m (a
  duplicate comment after a lost response: a design question, labelled fp), R68t, R21b, R09.
- **Decision for the user at the lock**: which rules leave v5.0. `lock_check.py` prints the numbers with every rule
  under the precision floor left out; the rules stay built and are measured again for v5.1 on the clean corpus.
- **Real bugs the pilot found on the unmodified apps** (labelled `new:` by the assistant; please confirm): BookStack
  shows the untranslated key `common.privacy_policy`, answers HTTP 500 for a draft address with a non-numeric id,
  and returns non-matching results for a search for '%'; Conduit shows a blank page when its stored values are
  'null', answers 200 with an empty form for the editor of a missing article, and accepts following oneself.
- R71 (time-zone axis, live runs only) raised 'calendar dates shift with the time zone' on Conduit's home page in a
  live test; Conduit shows timestamps in local time, so a shift near midnight may be correct. Review before Night 4.
- The pilot's faulty-pass replays h4rep3-5 may be disturbed: the live tests reset Conduit at about 22:49 (I84).
  No tests run alongside the final resweep.

## 5. Final measurement (30 Oct, D62a)

| | all rules | without R02h, R02m, R09, R09d, R12c, R21b, R30, R50m, R65, R68t |
|---|---|---|
| BookStack | recall 8/13, precision 0.96, 0.8 clean false alarms per run | 8/13, **0.98**, **0.4** (passes) |
| Conduit | recall 7/8, precision 0.65, 5.2 per run | 7/8, **0.97**, **0.2** (passes) |

Keeping R09 (v4) leaves BookStack at 0.6 per run (one false alarm over). R43 counts as a real BookStack defect (I86,
corrected after a check as a guest). Next: the user decides the set, commits (hash must be b1b3c3ab), runs the live
pilots and writes D51; then the tag.

**v63 (the lock measurement, hash 2964342f):** with the D62a set left out, BookStack 8/13, 0.98, 0.4 per run;
Conduit 7/8, 0.99, 0.2 per run: both pass. The commit must give hash 2964342f (check it with the line in
`scripts/resweep_lock.sh`); configs are not in the hash, so setting `exclude_rules` there does not change it.
