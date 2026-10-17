# 01 · WebTestPilot (FSE 2026) ⭐ BASE PAPER

> **Fact sheet** (research notes from a full read, with page refs). Not submission text. Write the 150–250-word summary in your own words in the last section.

| | |
|---|---|
| **IEEE ref** | X. Teoh, Y. Lin, D.-M. Nguyen, R. Ren, W. Zhang, and J. S. Dong, "WebTestPilot: Agentic end-to-end web testing against natural language specification by inferring oracles with symbolized GUI elements," *Proc. ACM Softw. Eng.*, vol. 3, no. FSE, Art. FSE087, Jul. 2026, doi: 10.1145/3797115. |
| **Venue / rank** | FSE 2026, published in PACMSE. FSE is CORE A*. Save the ranking screenshot as proof. |
| **Artifact** | Code, benchmark, baselines and scripts: github.com/code-philia/WebTestPilot (p.20). **Benchmark apps are packaged as Docker Compose** (p.12). |
| **Relevance** | Gaps: BASE, G2, G3 |

## Problem
- Specification-based E2E web testing: given a natural-language (NL) requirement, run the flow and decide whether the app behaves correctly (p.2).
- Core issue: when an LLM agent reports an inconsistency, it is unclear whether it is a **real bug or the agent hallucinating** (p.2).
- Two challenges:
  - (1) Deriving *implicit* oracles that need **data, causal and temporal dependencies** across states (p.2).
  - (2) LLM non-determinism. They prompted 5 LLMs 10× each on the same screenshot and got 7 distinct answers (Fig. 1, p.3).
- Critique of PinATA: its memory is precomputed, unstructured and capacity-limited (p.2–3).

## Method
- **Neurosymbolic agent** with three stages (Fig. 8, p.9):
  1. **Input parsing.** The NL requirement becomes steps of (condition, action, expectation) (§4.1).
  2. **Oracle inference.** The LLM infers implicit requirements from the execution trace, declares **symbols** as Pydantic schemas (e.g. `Cart`, `Product`), and writes pre/postcondition assertions in a **Python-based DSL** (Fig. 9) over those symbols (§4.2).
  3. **Oracle execution.** Check the precondition, run the action, check the postcondition. On failure, retry up to *n* times, then report a bug. The paper uses **n = 1** (§4.3.3, p.11).
- **Action grounding:** the UI-Venus-7B grounding model gives coarse coordinates, then Set-of-Mark annotation of a cropped region, then the LLM picks the exact element (§4.3.1).
- **Page reidentification:** nearest previous state by DOM tree edit distance, then an LLM screenshot comparison decides whether it is the same logical page (§4.3.2). Symbols are extracted *on demand* from states with the same page ID.
- Base model: GPT-4.1. Qwen2.5-VL at 3B–72B as alternatives (§5.4.2).

## Data
- **New benchmark:** 4 open-source apps chosen for ≥5k GitHub stars, >50 contributors, >5 years old and real-world use (p.12):
  - BookStack (27 tests, 215k LOC)
  - Indico (25 tests, 573k LOC)
  - InvoiceNinja (25 tests, 1.5M LOC)
  - PrestaShop (23 tests, 2.2M LOC)
  - Total: **100 NL test requirements** from user documentation plus CRUD extrapolation, following ISTQB CTFL v4.0 (Table 2, p.13).
- **100 injected bugs, one per requirement.** They are modelled on a 10% sample of 2,043 closed GitHub "Bug" issues via open coding and thematic analysis (p.13).
  - Four categories: missing UI element, data inconsistency, no-op action, navigation failure.
  - **Crash and purely cosmetic bugs are excluded.**
  - Bugs are **JavaScript functions that modify page state at each transition**, not source-code changes (p.13).
- Ground truth: Playwright assertion scripts per step (Fig. 11).
- Also: 23 replicated real GitHub bugs, and an industrial case study (China Mobile no-code platform, 56 tests) (§5.3.4, §6).

## Results
- **RQ1, flow completion** (Table 3, p.15):
  - WebTestPilot: TC = 0.99, CT = 0.99.
  - LaVague: TC 0.64. NaviQAte: 0.54. PinATA: 0.08.
- **Cost:** median 29 s and about 10k tokens per step. Page reidentification is the bottleneck: 32% of tokens and 39% of time (p.15).
- **Maintainability:** test actions preserved in 39/40 UI-change cases, versus XPath 32/40 and Playwright 29/40 (p.15).
- **RQ2, bug detection** (Table 4, p.16), measured at step level:
  - WebTestPilot: precision 0.96, recall 0.96.
  - PinATA: precision 0.26, recall 0.69.
  - Real bugs: 22/23 detected, versus 15/23 for PinATA.
- **RQ3, robustness** (Table 5, p.18): rewriting the requirements (dropout, noise, summarize, restyle) drops GPT-4.1's TC from 1.00 to 0.70–0.93.
- **RQ4, model size:** 7B is the minimum viable model, and ≥72B is needed to match GPT-4.1 (p.17). Local models mainly fail on DSL misuse (52% symbol errors, 39% DSL errors).
- **Industrial case study:** 8 bugs found, 5 of them data binding. Mean time to detect: 4.9 min (p.19).

## Limitations

**Stated by the authors (p.19):**
- The metrics may underestimate performance, because several paths can reach the same functionality.
- The benchmark may not reflect real-world conditions.
- It **assumes requirements are self-contained and complete**.

**Spotted myself:**
- **Dataset**
  - The bugs are injected JS state mutations that fire at known steps. This is not the same as source-level faults, and the tester effectively knows which flow contains the bug (one bug per test).
  - Crash bugs were excluded on purpose, so we can't tell how it handles them.
- **Method**
  - It needs a complete NL spec for every test and does **no exploration**. It tests only what is written down.
  - Retry n = 1. A failed assertion is not reproduced in a **fresh session** before being reported, so a flaky app or flaky grounding could still produce a false bug.
  - Page reidentification costs an LLM call per state, which won't scale to long exploration.
- **Evaluation**
  - No repeated runs or variance are reported, despite the paper itself pointing out that LLMs are non-deterministic (Fig. 1).
  - Precision is measured at step level, with the requirement in hand.
  - There is no coverage metric (by design).
  - Tests run **sequentially to avoid shared-state interference** (p.14). Parallel execution is not studied at all.
- **Missing baselines:** no non-LLM baseline (e.g. a crawler with implicit oracles). Only PinATA is compared for bug detection.
- **Generalizability:** only 4 apps, all mature CRUD apps, and GPT-4.1 as the main model.

**Future directions:** spec-free oracle inference; cheaper page identity (e.g. structural hashing); verifying reported failures by re-execution; running tests in parallel with state isolation.

## Relevance to our project
- **Base paper.** We reuse its **benchmark** (4 Dockerized apps with 100 injected bugs) as a direct comparison point, alongside our own seeded faults.
- **G3, spec-free oracles:** it infers oracles *from a spec*. We infer them *from exploration with no spec*. Its spec-given setting is our upper bound.
- **G2, evidence gate:** it reports after a single retry. We add k-fold fresh-session replay. Its precision (0.96 *with* a spec) is the bar for our gated, spec-free precision.
- **G1, coordination:** it is single-agent and avoids parallelism on purpose (p.14). We study shared-state parallel workers.
- **Design ideas to borrow:**
  - Page reidentification gives a canonical state ID. We replace its LLM comparison with a structural hash.
  - Symbolized schemas plus a DSL are a good format for our inferred oracles.

## Artifact inspection (16 Oct 2026, our own reading of the code; facts for the paper)
- **Versions read:** `code-philia/WebTestPilot` @ `26ed5ad8` (2026-10-01) and its benchmark submodule `code-philia/WebTestPilot-benchmark` @ `b3055bf7` (2026-10-01).
- **License:** the main repo is CC BY 4.0. The benchmark sub-repo has no license file (I21).
- **The benchmark was revised after the paper:** its README says it is "derived from the original benchmark, with revised test steps and expected results; the `change_*` UI experiments are no longer part of this benchmark". **Numbers measured on this version may differ from the paper's Table 4.**
- **How bugs are injected** (`runtime/init.py`, `runtime/bug_injector.js`):
  - Each bug is a JS pair, `isConditionMet` + `onConditionMet`, merged into an injector template and registered with Playwright `add_init_script`.
  - It is armed only after the test's setup function logs in (a sessionStorage flag).
  - A transition API makes some bugs fire only on the N-th arrival at a page.
  - Once fired, the effect is re-applied on later visits to the same URL in that tab.
  - **One bug is active per test case.** Each test runs in a fresh Compose stack with its own browser container. The agent attaches over CDP.
- **BookStack** (27 test cases, 27 bug scripts):
  - **Duplicates:** 5 scripts are byte-identical (they remove 'Shelf' from My Favourites), and 4 more remove 'Chapter 2' from Recently Viewed.
  - **18 distinct faults.** 5 depend on a literal from their own test spec ('New Book', 'Updated Book', 'New Sort Rule', 'I like this template', page 'new-page').
  - **Classes:** missing element ×4, data inconsistency ×14. There are no no-op or navigation bugs in BookStack.
  - **Oracles:** many expectations are **relational across pages** ("consistent with the Created Content counts", "chronological order", "consistent with previous search results").
- **Environment:** `solidnerd/bookstack:25.2.1` + `mysql:8.4`, a `baseline.sql` schema dump plus `seed.sql` loaded with dates = yesterday, and a single admin account.
- **What this means for our comparison:**
  - Their 0.96/0.96 is per test flow, with the spec in hand and one bug at a time.
  - Spec-free exploration with all faults active is a different task. For example, 5 of the 18 faults can only fire if the spec's literal is typed.
  - Our use (D31–D37) reports exposure and detection on the 13 reachable faults, and treats their numbers as context.

## Your summary (150–250 words, your own words)
<!-- Write here: Problem → Method → Data → Results → Limitations → Relevance -->
