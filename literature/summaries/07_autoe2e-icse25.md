# 07 · Feature-Driven End-to-End Test Generation (AutoE2E, ICSE 2025)

> **Fact sheet** (research notes from a full read of arXiv 2408.01894v2). Not submission text.

| | |
|---|---|
| **IEEE ref** | P. Alian, N. Nashid, M. Shahbandeh, T. Shabani, and A. Mesbah, "Feature-driven end-to-end test generation," in *Proc. IEEE/ACM 47th Int. Conf. Softw. Eng. (ICSE)*, 2025, pp. 450–462 (verify pages), doi: 10.1109/ICSE55347.2025.00141. |
| **Venue / rank** | ICSE 2025 (CORE A*, verify) |
| **Artifact** | AutoE2E and **E2EBench** are public (ref. [56] in the paper; find the link in the PDF's data availability section). |
| **Relevance** | Gaps: G3 (spec-free inference from exploration), EVAL (feature-coverage metric, benchmark that includes Conduit) |

## Problem
- Manual E2E tests are expensive. Automatically generated ones (model-based, RL) cover states but are **incoherent**: random action sequences that don't exercise real features (Listing 1, p.3).
- There was no benchmark for measuring whether generated E2E tests cover an app's *features* (p.1).

## Method
- **Formal definitions** (p.2–3):
  - *User operation*: an entity CRUD tuple, or a configuration change.
  - *Feature*: a minimal ordered chain of operations with a visible outcome.
  - **Feature coverage**: the share of the app's features exercised by the test suite (Def. 3).
- **Probabilistic feature inference** (§III-A): assuming features are independent, inference is action-centric, sequential and first-order.
  - Score: F = argmax Σ [log p(F | Aᵢ, Aᵢ₋₁) − log p(F | Aᵢ₋₁)] (Eq. 5).
  - Intuition: an action is evidence for a feature if it makes that feature more likely than before.
- **Pipeline** (Fig. 2):
  1. **BFS exploration** loop.
  2. Per-state context from a screenshot plus the app description.
  3. The LLM ranks candidate features for each action, alone and together with the previous action. Ranks become scores through a geometric distribution with p = 0.5.
  4. **Feature DB** (vector store) plus **Action-Feature DB**. Matches are found by embedding retrieval, then confirmed by an LLM. Scores update as new evidence arrives.
  5. Features scoring above a cutoff become Selenium test cases.
- Stack: Claude 3.5 Sonnet, LangChain, ADA embeddings, MongoDB Atlas vector search.

## Data
- **E2EBench, 8 open-source web apps** (Table I, p.9), each with its number of features:

  | App | Features | Size |
  |---|---|---|
  | PetClinic | 23 | n/a |
  | **Conduit** | 17 | 53K LOC |
  | Taskcafe | 32 | n/a |
  | Dimeshift | 21 | n/a |
  | MantisBT | 27 | n/a |
  | EverTraduora | 41 | n/a |
  | Saleor Storefront | 13 | n/a |
  | Saleor Dashboard | 130 | 1.1M LOC |

- **Ground truth:**
  - The front-end code is **instrumented to log every user action** with a component ID.
  - The authors wrote a **feature grammar** for each feature (Listing 3).
  - Feature coverage is then computed automatically from the logs.

## Results
- **RQ1:** average feature coverage of **79%** (72% over all features pooled) (p.9).
- **RQ2, inference quality** (Table II): precision **0.55**, recall 0.72, F1 0.62. Precision drops to about 0.42 on Taskcafe, Dimeshift and Traduora.
- **RQ3, baselines:**

  | Tool | Feature coverage |
  |---|---|
  | **AutoE2E** | **79%** (+558% over Crawljax, +731% over BrowserGym) |
  | Crawljax | 12.0% |
  | BrowserGym | 9.5% |
  | OpenDevin | 7.9% |
  | AutoGPT | 6.1% |
  | WebCanvas | 0% |

- AutoE2E's tests average **3.8 actions per feature**, versus 2.9 for Crawljax and 1.4 for BrowserGym (Table III). The benchmark average is 3.4.

## Limitations

**Stated by the authors (p.10–11):**
- Exactly one test per feature.
- Assertions are naive (the whole state after each action).
- App selection may not be representative.
- Feature extraction is subjective.
- Different baselines used different LLMs (GPT-4o vs. Claude).

**Spotted myself:**
- **Oracle:** it **generates tests but doesn't find bugs**. There is no fault detection, no seeded faults and no meaningful assertions, so its output is coverage only.
- **Evaluation**
  - Temperature 0 and **a single run**, with no variance reported.
  - Cost and time are not reported.
  - The baselines are general agents that weren't built for testing, which makes the comparison weak.
  - Precision of 0.55 means **about half of the inferred "features" don't exist**. Inference hallucinates, just as oracles do.
- **Method:** single-agent, sequential BFS. Exploration and feature inference cost an LLM call for every action.
- **Generalizability:** the feature grammars were hand-written by the authors, which is subjective.

**Future directions:** assertion and oracle generation (the authors say so); several tests per feature; parallel exploration.

## Relevance to our project
- **G3, spec-free inference:** the closest precedent. It infers *features* from exploration with no spec. We infer *checkable expectations (oracles)* from exploration. AutoE2E stops at generating tests without assertions, and our G3 adds the missing oracle.
- **Benchmark and metric (important):**
  - **E2EBench already contains Conduit (RealWorld)**, with action-level instrumentation and feature grammars.
  - We can **reuse E2EBench's Conduit setup and feature-coverage metric**, which gives a third coverage measure next to code coverage and state coverage.
  - Check that the artifact runs.
- **G2 support:** its feature-inference precision of 0.55 is more evidence that LLM inferences need a verification step.
- **Baseline:** Crawljax is cheap and gets 12% feature coverage. It is a reasonable B0 (non-LLM) reference.

## Your summary (150–250 words, your own words)
<!-- Write here -->
