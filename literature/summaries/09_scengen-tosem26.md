# 09 · Scenario-Guided LLM-based Mobile App GUI Testing (ScenGen, TOSEM 2026)

> **Fact sheet** (research notes from a full read of arXiv 2506.05079v4, the TOSEM accepted version). Not submission text.

| | |
|---|---|
| **IEEE ref** | S. Yu, Y. Ling, C. Fang, Q. Zhou, Y. Zhao, C. Chen, S. Zhu, and Z. Chen, "Scenario-guided LLM-based mobile app GUI testing," *ACM Trans. Softw. Eng. Methodol.*, 2026, doi: 10.1145/3816025. |
| **Venue / rank** | ACM TOSEM (Q1, verify) · also presented as ASE 2026 Journal-First |
| **Artifact** | github.com/iGUITest/ScenGen · sites.google.com/view/scengen (p.6) |
| **Relevance** | Gaps: G1 (shared memory as coordination substrate), G2 (Supervisor verification) |

## Problem
- Automated GUI testers optimise **code coverage**. They don't follow **business-logic scenarios** (login, purchase, send an email) and miss critical functionality (p.2–3).
- Specific difficulties: hidden functions, domain-specific inputs, and long multi-step event chains (§2.2).
- Prompting one LLM with just the scenario leads to "**unstable behavior, redundant exploration, or loss of progress context**" (p.8).

## Method
- **Five agents arranged in an OODA loop** (Fig. 3, p.9):
  - **Observer:** CV widget detection plus OCR and MLLM semantics.
  - **Decider:** LLM scenario-driven action choice, plus widget prediction and localization adjustment.
  - **Executor:** ADB commands.
  - **Supervisor:** verifies state transitions, loading state and test completion, with rollback and correction.
  - **Recorder:** logs to memory and monitors crashes.
- **Shared context memory** (§3.1), in three layers:
  - Long-term: device, app, scenario.
  - Working: goal, action history.
  - Short-term: current and previous GUI.
  - **Equivalent states are detected with perceptual hash plus structural similarity**, and exploring those states again is skipped.
- Model: GPT-4V at temperature 0. Each LLM call gets only the context it needs, rather than the full chat history (§6.2).

## Data
- **10 scenarios × 92 apps = 99 tasks** (Table 1): Email, Music, Note, Photo, Translation, Shopping, Login, Calculation, Weather, Alarm.
- English-only apps from Google Play and Huawei AppGallery.
- Scenarios were defined by 3 researchers following a protocol (p.19).

## Results
- **RQ1** (Table 2):

  | Tool | Coverage rate | Success rate |
  |---|---|---|
  | **ScenGen** | **86.87%** | **84.85%** |
  | AutoDroid | n/a | 80.81% |
  | AppAgent | n/a | 78.79% |
  | Mobile-Agent-v3 | n/a | 75.76% |
  | GPTDroid | n/a | 68.69% |

  - The most common failure is **premature termination**: 40% of failures, where the Supervisor wrongly decides the goal is done (p.21–22).
- **RQ2, bugs** (Table 3): 106 crash bugs in-scenario, versus 89 for ASOT and 43 in-scenario for PIRLTest.
  - **Every bug found by a baseline was also found by ScenGen.**
  - 83% verified or fixed.
  - **Only crash bugs**, taken from runtime logs.
- **RQ3, widget localization:** 80.79% accuracy at first try, 97.96% after self-correction (Table 4).
- **RQ4, decision accuracy:** 96.08% initially, 97.06% after correction (Table 5).
- **RQ5, cost:** about 48.8k tokens and **$0.32 per task**, 4.71 min, averaged over 10 runs (Tables 6–8). Verification stages (state and completion) use the most tokens.

## Limitations

**Stated by the authors (p.30–31):**
- Choice of scenarios and apps.
- LLM instability, handled with 10 repetitions at temperature 0.
- Hallucination, handled by the Supervisor.
- Premature termination when there is no clear visual signal that a task is complete.

**Spotted myself:**
- **Task setting:** needs a scenario per task. It isn't exploratory.
- **Oracle:** crashes only. The Supervisor checks *that the scenario progressed*, not *that the app behaved correctly*, so semantic bugs are invisible.
- **Evaluation**
  - Localization and decision accuracy were judged by 3 humans, and the scenarios were designed by the authors themselves.
  - The baselines are mixed: some general GUI agents that aren't test tools.
  - No statistical tests.
- **Generalizability:** mobile only, a single model (GPT-4V), English apps.
- **Verification** is an LLM checking LLM actions; nothing is re-executed.

**Future directions:** splitting scenarios into sub-goals; lightweight validation loops; event-based (not screenshot) completion signals.

## Relevance to our project
- **G1:** shows that a **shared context memory with state-equivalence deduplication** cuts redundant exploration *within one agent team*. Our shared frontier extends this to N parallel browser workers.
- **G2:** the Supervisor is an LLM self-check. **40% of failures come from the Supervisor's own misjudgement** (premature termination). That is evidence that LLM self-verification isn't enough and that execution-based checks are needed.
- **Design ideas:**
  - The memory layers (long-term / working / short-term) are a template for the *state contract* our Phase 1 deliverable C requires.
  - Perceptual hash plus structural similarity is another candidate state-ID method.
- **Cost reference:** about $0.32 per scenario with GPT-4V, a benchmark for our cost-per-finding metric.

## Your summary (150–250 words, your own words)
<!-- Write here -->
