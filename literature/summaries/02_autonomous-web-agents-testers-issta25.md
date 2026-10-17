# 02 · Are Autonomous Web Agents Good Testers? (ISSTA 2025)

> **Fact sheet** (research notes from a full read of the arXiv v1 preprint, "Accepted to ISSTA 2025"). Not submission text. Before citing numbers, **check them against the published PACMSE version**: the ISSTA page lists about 100 tests, while this preprint has 113.

| | |
|---|---|
| **IEEE ref** | A. Chevrot, A. Vernotte, J.-R. Falleri, X. Blanc, and B. Legeard, "Are autonomous web agents good testers?" *Proc. ACM Softw. Eng.*, vol. 2, no. ISSTA, 2025, doi: 10.1145/3728879. |
| **Venue / rank** | ISSTA 2025, published in PACMSE (CORE A, verify) |
| **Artifact** | Benchmark, results and code on Zenodo (p.20). The apps are WebArena Docker images. |
| **Relevance** | Gaps: G2 (primary), EVAL |

## Problem
- Scripted E2E tests are fragile and expensive to maintain (p.1–4).
- Can **autonomous web agents (AWAs)** be turned into **autonomous test agents (ATAs)** that run *manual, natural-language* test cases, including the assertions, and give a pass/fail verdict?
- How ATAs differ from AWAs (p.6): they must follow the steps in strict order, and they must check intermediate assertions along the way.

## Method
- **SeeAct-ATA:** a minimal baseline. The SeeAct prompt gets a tester profile, plus a "test case progress" instruction and an "assertion control" instruction (Listing 3, p.8).
- **PinATA:** three agents (p.8–9).
  - **Orchestrator** plans with feedback and retries.
  - **Actor** does Set-of-Marks grounding, gets coordinates from the LLM and acts through Playwright.
  - **Assertor** uses LLM-as-judge on a **screenshot only**.
  - All three share a long-term global memory.
- LLMs: GPT-4o at temperature 0. Also Claude 3.5 Sonnet and Gemini 2.0 Pro.

## Data
- **3 apps from (Visual)WebArena:** Classifieds, Postmill (Reddit-like), OneStopShop. Each is a Docker image (p.10).
- **113 test cases** (Table 1, p.11):
  - 62 passing tests written by 4 ISTQB-certified professional testers (about 1 h of effort each).
  - **51 failing tests**, made by editing passing tests to check for features that don't exist (e.g. a missing button). Each has an annotated step where it should fail.
- The app is reset before every run (p.13).

## Results
- **Metrics:** verdict alignment with humans (accuracy, specificity = avoiding false alarms, sensitivity = catching failures), plus new step-alignment metrics: AER, HER, SMER (type-III "right verdict, wrong reason") and TruAcc (p.12).
- **GPT-4o** (Table 2, p.14):

  | Agent | TruAcc | Sensitivity | Specificity | SMER |
  |---|---|---|---|---|
  | PinATA | 0.61 | 0.88 | **0.57** | 0.11 |
  | SeeAct-ATA | 0.40 | 0.48 | 0.59 | 0.28 |

- **Across LLMs** (Table 4, p.15): TruAcc 0.58–0.62. Sonnet has the best sensitivity (0.94) and the **worst specificity (0.47)**.
- **26/113 tests** are misjudged by every LLM. A taxonomy of those 26 (p.16–17):
  - Action capacity: 6
  - Action versatility: 6
  - UI observability: 5
  - Assertion verifiability: 4
  - Test-case conformity: 5
- Conclusion (p.20): "specificity not exceeding 57%", i.e. **agents often flag passing tests as failing**.
- Note: the abstract says "up to 94% specificity", which contradicts Tables 2 and 4 and the conclusion. The 94% is actually *sensitivity*. **Cite the tables, not the abstract.**

## Limitations

**Stated by the authors (p.17–18):**
- Correct verdicts for the wrong reason can't be detected on passing tests.
- The ground truth was executed manually.
- Small numbers of apps and tests.
- Only base LLMs, at temperature 0.
- The taxonomy rests on just 26 cases.

**Spotted myself:**
- **Dataset**
  - The "failing" tests are **altered test cases, not buggy apps**: the app is correct and the test asks for a missing feature. That is different from detecting real faults.
  - The apps are WebArena snapshots, not chosen for testing research.
- **Method**
  - The assertor only looks at screenshots (no DOM checks).
  - There is **no step to re-check a failure before reporting it**, and that is exactly what would cut the false alarms the paper measures.
- **Evaluation**
  - It appears to be **one run per test per model**. With non-deterministic agents, there is no variance or repeat-run analysis.
  - No cost or latency numbers.
  - Not compared with a scripted baseline.
- **Generalizability:** test execution is spec-driven (the scripts are given). There is no exploration and no discovery of unknown bugs.

**Future directions:** verifying before giving a verdict; giving the assertor DOM and interaction abilities; better planning so the agent sticks to the test case.

## Relevance to our project
- **Main evidence for G2.** LLM testers produce false alarms: specificity is 0.47–0.57 across 3 frontier LLMs. Our evidence gate (fresh-session replay) attacks this directly, and specificity/precision is our G2 metric.
- **Metric design:** we borrow the "right verdict, wrong step" idea (SMER) to check that a confirmed finding is reported at the step where the fault really is.
- **Baseline:** PinATA is the baseline WebTestPilot beat (precision 0.26). It is also open source, so it can serve as a "no gate" reference.
- **Taxonomy:** its 5 error categories become the starting codes for our failure analysis.

## Your summary (150–250 words, your own words)
<!-- Write here -->
