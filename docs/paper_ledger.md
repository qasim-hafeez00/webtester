# Paper ledger: every fact the paper will need, filed by section

**Notes for synthesis, not submission text.** The course runs a Turnitin AI-writing check, so all paper prose is written by the author. This file only collects verified facts, numbers, decisions and threats, each with its source, so nothing has to be reconstructed later. Update it whenever a decision, result or issue is logged. IDs: D = [logs/decisions.md](../logs/decisions.md), I = [logs/issues.md](../logs/issues.md), runs = [run_registry.md](../logs/experiments/run_registry.md).

Last updated: 2026-10-16 (after the BookStack verification runs).

---

## 1. Problem and gaps (Introduction)
- **Three gaps:** G1 parallel LLM explorers duplicate work, G2 agents report bugs that are not real, G3 spec-free testing has no semantic oracle (D2, plan section 3).
- **Evidence cited for each gap:** plan section 3. PinATA specificity ≤ 57% (ISSTA'25) for G2. WebTestPilot needs an NL spec per test (FSE'26) for G3. MAST: multi-agent gains are often small (NeurIPS'25), for the equal-budget rule.
- **Claimed:** measured, equal-budget evidence for each mechanism. **Not claimed:** first parallel web tester (MARG, ASE'24), hundreds of browsers, testing every input (plan section 1).

## 2. System (Approach)
- **Harness** (`src/webtester`):
  - Async Playwright Chromium, one isolated context per worker.
  - An observation of up to 80 interactive elements plus a text-free DOM skeleton, with identical siblings merged (Judge-style).
  - State ID = hash(route shape, skeleton) (D13).
  - Stateless prompts: the current page plus the last 10 steps, up to 6 actions per reply (D15).
  - Implicit oracles: HTTP 5xx, failed requests, uncaught JS errors, console errors. "Failed to load resource" lines are ignored (D14).
  - JSONL trace of every step, and all metrics are recomputed offline from it.
- **Model:** `gemini-3.5-flash-lite`, temperature 0.2, ≤ 800 output tokens, JSON mode, calls 6.5 s apart. Same model in every condition (D16, D20).
- **G1, shared frontier:**
  - v1 (D23): advisory `[done xN]` / `[taken]` marks plus a suggestion to the least-explored state. **No effect.**
  - v2 (D25): nav-bar elements (on ≥ half the states) are not counted as work; each worker owns a focus area (route, or sibling routes merged), reassigned when dry or after 15 steps; text fields are marked with the input classes already tried.
  - Advisory only: the LLM decides.
- **G3, inferred oracles** (D27): the explorer may add up to 2 executable checks per reply in the same LLM call. Checks: `shows` / `not_shows` (now, reload in a fresh tab, or another path), `count` (± delta), `changes` (no-op), `route`. Code checks them, not an LLM, so every violation can be replayed.
- **G2, evidence gate** (D28):
  - Runs after exploration, outside the exploration budget.
  - Minimal-suffix replay (1 step, then 4) from the worker's recorded steps, in a fresh context restored to the worker's session, with a DB reset before every replay.
  - k = 3 replays. Labels: confirmed 3/3, flaky 1–2, rejected 0, unverified (20-min cap).
  - An LLM judge gives a second opinion on reproduced oracle violations and never changes the label.
- **Conditions** (D29, plan section 6):
  - B0 crawler, B1 one LLM worker, B2 N independent workers, B3 v1/v2 shared frontier, B3v2-local.
  - B4 = B3 v2 + G3 + G2.
  - Ablations: A-G1 `b4nog1`, A-G3 `b4nog3`. A-G2 is B4's raw candidates, paired.

## 3. Subjects and ground truth (Evaluation setup)
- **Conduit** (D8–D12, `apps/realworld/README.md`):
  - Express/Prisma backend with the AutoE2E-instrumented Angular frontend.
  - Deterministic seed and a ~1 s snapshot reset; workers worker01–16.
  - **10 seeded faults:** crash ×2, validation ×1, data ×5, authorization ×1, no-op UI ×1. Only F01 and F02 are visible to implicit oracles (D11).
  - Known upstream defects U1–U5 count as unseeded true positives.
- **BookStack 25.2.1** from the WebTestPilot benchmark (D31–D37, `apps/bookstack/README.md`):
  - 27 benchmark bug scripts = **18 distinct faults** (missing element ×4, data ×14). 13 are reachable by exploration, 5 need a spec literal.
  - Client-side DOM mutations, none of them a crash, so implicit oracles score 0 by construction.
  - Environment adaptations E1–E6 (D34) and injector adaptations A1–A5 (D33).
  - 30 files vendored byte-identical (`VENDORED.sha256`), CC BY 4.0 (I21).
- **Exposure vs detection** (D36, D38): for injected faults, the trace records when a fault *visibly* changed a worker's page (DOM before vs after its effect), separately from whether it was reported. Trigger-only firings (no visible change) are kept apart.
- **Labelling** (D30, D37): every finding of a B4-family run is labelled by hand (seeded id / U / new / fp). Solo author: a blind 20% re-label gives an intra-rater agreement figure (plan: two raters and κ).

## 4. Metrics and statistics
- **Exploration:** unique abstract states, unique routes, duplicate-action rate (same state, element and input class), steps, tokens (`metrics.py`).
- **Faults:**
  - Seeded faults found: implicit rules over all candidates, plus labels.
  - Gate-confirmed only.
  - Exposed (BookStack).
- **Precision:** raw candidates, gate-confirmed, and confirmed minus judge rejects. Only for fully labelled runs.
- **Gate cost:** replays, minutes, judge tokens as a % of the run's tokens (KPI ≤ 25%).
- **Statistics** (D19): median [IQR], exact two-sided Mann-Whitney U, Vargha-Delaney Â12 (|Â12 − 0.5| ≥ 0.21 = large). n = 5 per condition.
- **Run validity** (D17, D20): healthy (no LLM failures, no stall > 60 s, stopped by its budget, gate finished when expected) and no harness bug. Invalid runs stay listed with their reason.

## 5. Budgets and fairness
- **Phase 1:** B0 vs B1 at equal wall-clock, 15 min (D18). B0 uses no tokens.
- **Phase 2:** an equal total token budget of 190k tokens shared by N = 4 workers, with a 30-min safety cap (D24).
- **G3 checks** ride in the same LLM call, so they cost exploration tokens. B4 gets fewer steps for the same budget, which is part of the measured cost.
- **The gate** runs outside the exploration budget, and its cost is reported separately.

## 6. Results so far
- **Phase 1** (`logs/experiments/phase1_results.md`, n = 5 each, 15 min, all faults on): B0 vs B1.

  | Metric | B0 | B1 | p |
  |---|---|---|---|
  | Faults found | 0 | 1 | 0.008 |
  | Routes | 14 | 8 | 0.016 |
  | States | 33 | 36 | 0.50 |
  | Duplicate actions | 46% | 47% | 0.31 |

  B1 found F02 in every valid run and F01 once.
- **G1** (`logs/experiments/phase2_g1_results.md`, n = 5 each, N = 4, 190k tokens):
  - B3 v1 = B2 on every exploration metric.
  - **B3 v2 vs B2:** states 38 vs 32 (p = 0.024, Â12 = 0.96), duplicates 37% vs 56% (p = 0.008), routes 10 vs 9 (ns), seeded faults 2 vs 1 (ns), steps 124 vs 139 (p = 0.008).
  - **B3 v2 vs B3 v1:** states 38 vs 31 (p = 0.008), routes 10 vs 8 (p = 0.048), duplicates 37% vs 51% (p = 0.008).
  - **KPI** (≥ 15% states, ≥ 30% fewer duplicates): met at N = 4 (+19%, −34%).
- **G2, G3:** built 15 Oct. Live pipeline test on Conduit (scripted LLM, 16 Oct): a failed check was replayed and confirmed 2/2 with a minimal trace of 1 step, judge answered, gate 0.14 min, about 4 s per replay including the ~1 s reset. No LLM runs yet.
- **BookStack verification** (16 Oct, `apps/bookstack/README.md`, D38, D39, I24, I27–I30):
  - `verify_faults.py` PASS on and off.
  - The B0 crawler (2 workers, 5 min) **visibly exposed exactly the 13 reachable faults** (BS01–BS13), with 0 findings. Implicit oracles detected 0/18 faults, confirming D32 empirically.
  - BS15 and BS18 triggered with no visible change (their spec literal was absent).
  - Reset 3.1–6.0 s.

## 7. Run accounting (all runs, as of 16 Oct)
- **49 runs logged:** 25 valid (10 Phase 1, 15 G1), 3 pilots, 3 smoke, 18 invalid.
- **Why the 18 were invalid:**
  - 7: Google 403 "project denied access" during free-key rotation (I17).
  - 6: free-tier daily quota, 429 (I13, I18).
  - 2: network outages (I14).
  - 1: a single 61.7 s LLM call, stall rule (I15).
  - 2: early harness bugs (I7).
- **Every lost run was re-run with the same model** (D20). One sensitivity check (B1 rep6) showed that including the invalid run changes no conclusion.

## 8. Threats to validity (collect here, discuss in the paper)
- **Design on the test subject:** B3 v2 (D25) and the G3 prompt examples (D27) were designed by someone who knows Conduit's faults. Mitigation: BookStack faults written by others (D31). Do not tune on BookStack before its runs (I22).
- **Key rotation:** B2 rep 5, B3 v1 rep 5 and B3 v2 reps 1–5 ran with `key_fallback = true`. Same model, so comparable, but the 403 recurred (I17).
- **Machine load:** 21 unrelated containers ran during B3 v2 reps 3–5. The runs were healthy, but there were 504s at the end of rep 4 (I19).
- **Single model, small N:** one cheap model (flash-lite), N = 4 only, n = 5, one laptop (4 cores, 16 GB).
- **Oracle expressiveness:** the single-page check language cannot express the relational consistency the base paper's oracles check (I22).
- **Benchmark fidelity:** client-side injected faults, not source faults; 5 of 18 are unreachable without the spec; the benchmark was revised after the paper (fact sheet 01). Two scripts cannot fire on the page their own test case is about in BookStack 25.2.1 (I27). Some effects need data a fresh worker lacks (I23).
- **Labelling:** a single labeller (D30).
- **State abstraction v0:** keeps `/profile/alice` and `/profile/bob` apart (I11). The same abstraction is used for every condition.
- **Unseeded real bugs found:**
  - U1 (PUT /api/user 500 on a username collision) and U5 (uncaught error on a missing article or profile).
  - A possible new one, I20 (tag `!@#$` → 504/500), not yet reproduced.

## 9. Artifact
- **Repo layout:** `src/webtester` (harness), `apps/realworld`, `apps/bookstack`, `configs/`, `scripts/run_batch.py`, `tests/` (offline and live), `logs/` (progress, decisions, issues, registry, notes, labels).
- **Commands to reproduce:** [docs/phase2_runbook.md](phase2_runbook.md).
- **Not yet done:** the git history has no commits yet (as of 16 Oct). Commit before submission.
