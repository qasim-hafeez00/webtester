# 04 · GraphDroid: Asynchronous LLM-Based Mobile App GUI Testing (ASE 2026)

> **Fact sheet** (research notes from a full read of the author preprint, arXiv 2609.10031). Not submission text.

| | |
|---|---|
| **IEEE ref** | X. Li, J. Cao, Z. Hou, Y. Zhao, Y. Liu, and S.-C. Cheung, "GraphDroid: Asynchronous LLM-based mobile app GUI testing via history-aware exploration and hybrid intent fulfillment," in *Proc. IEEE/ACM Int. Conf. Automated Softw. Eng. (ASE)*, 2026, doi: 10.1145/3832783.3837449. |
| **Venue / rank** | ASE 2026 (CORE A*, verify). The DOI of the version of record is on p.1. |
| **Artifact** | Code and benchmark: 10.5281/zenodo.21512256 (p.11) |
| **Relevance** | Gaps: G1, plus cost (EVAL) |

## Problem
- Pure-LLM GUI testers (GPTDroid, DroidAgent, VisionDroid) have three problems (p.2):
  1. **They lose history.** Old states get condensed into short text, so functionality that was never covered there is forgotten.
  2. **Intent generation is synchronous**, which blocks exploration while the LLM thinks.
  3. **They call the LLM at every step**, which is slow and expensive.
- LLM-augmented tools (LLMDroid, LLM-Explorer) are cheap but **can't complete multi-step functionality** (p.2).

## Method
- **Phase 1, cold start:** depth-limited DFS (d = 3) builds the first UI transition graph (UTG) (p.3).
- **Cluster-based memory** (§2.2):
  - **State abstraction:** two states are the same if max(Jaccard similarity of widget sets, cosine similarity of visual embeddings) > 0.95.
  - **Spectral clustering** of the UTG on "edge + similarity", with clusters of 2–20 states.
  - Each cluster's screenshots and transitions go to the LLM, with already-visited widgets boxed in red.
- **Asynchronous intent generation** (§2.3): per-cluster LLM queries run in parallel *while DFS keeps exploring*. Duplicate intents are removed via Sentence-BERT plus an LLM pass.
- **Hybrid fulfillment** (§2.4):
  - **Simple (1-step) intents** go to DFS, guided by an Exploration Value Score (EVS, in the style of Go-Explore).
  - **Complex intents** go to the UI-TARS-1.5 GUI agent, with a budget of 3× the predicted steps.
- Models: GPT-4.1 plus UI-TARS-1.5.

## Data
- **41 Android apps** (p.6–7):
  - 12 from LLMDroid's benchmark
  - 19 from LLM-Explorer's benchmark
  - 10 top Google Play apps (>50M downloads)
- 29/41 apps could be instrumented for code coverage.
- **Themis benchmark:** 52 reproducible crashes.
- **Settings:** 2 h per app, **3 repetitions**, all tools on GPT-4.1 (p.6–7).
- **Baselines:** DQT (deep RL), GPTDroid, VisionDroid, DroidAgent, LLM-Explorer, LLMDroid.

## Results
- **RQ1** (Table 1, p.7):

  | Tool | Activity coverage | Code coverage | States |
  |---|---|---|---|
  | **GraphDroid** | 36.94% | 20.83% | 73.5 |
  | LLMDroid (best baseline) | 28.36% | 17.19% | 48.7 |

  - Gains over LLMDroid: +30.3% activity, +21.2% code, +50.9% states.
  - Gains over DroidAgent: +49.7% activity, +36.4% code, +87.5% states.
  - The lead holds at state-abstraction thresholds from 0.75 to 0.95 (Table 3).
- **RQ2, bugs:**
  - **19 bugs** (13 crashes + 6 non-crash) out of 21 found by any tool. LLMDroid found 11.
  - 7 bugs were new; 4 have been fixed.
  - Themis: 13/52 crashes, more than any baseline (Fig. 6).
- **RQ3:**
  - **82.3% of intents come from states visited more than 5 steps earlier**, which supports keeping history.
  - Fulfillment rate: 82.4% of simple intents, 72.7% of complex ones.
- **RQ4, cost** (Table 4): **$1.41 per app**, 5.33 s per action. DroidAgent costs $11.97 (8.5×). LLMDroid costs $0.75.
- **RQ6, ablations** (Table 7): every component helps.
  - No cluster partitioning (whole UTG in one prompt): code coverage drops to 15.27%.
  - Synchronous generation: +54% time per action.

## Limitations

**Stated by the authors (p.11):**
- Benchmark and LLM choice.
- Human judgement in classifying bugs and intents.
- LLM stochasticity, handled with 3 runs.

**Spotted myself:**
- **Platform:** Android only, and the code coverage is method-level on just 29 apps.
- **Parallelism**
  - "Asynchronous" means *LLM reasoning in parallel with one device's DFS*. There is **still only one app instance and one explorer**.
  - Parallel devices or browsers are not studied.
- **Oracle**
  - Only crashes plus manually inspected exceptions.
  - **No verification step:** bugs are counted across 3 runs and deduplicated by stack trace.
  - No functional-correctness oracle.
- **Evaluation**
  - Only 3 repetitions, and no significance tests are reported.
  - The fulfillment rate comes from a single-app case study (Renpho).
  - Residual duplicates remain after de-duplication (235 in 3 apps).
- **Generalizability:** web apps (DOM/URL structure, multiple tabs) are untested.

**Future directions:** parallel fulfillment across devices; a semantic oracle; using the UTG to guide verification.

## Relevance to our project
- **G1 design input:**
  - "Keep the full graph, partition it into clusters, query the LLM per cluster" is almost exactly what a shared frontier needs for assigning work to N workers.
  - Clusters could become **work partitions for workers**.
- **Cost design:** the hybrid "cheap traversal for simple intents, LLM for complex ones" supports our model-tiering plan.
- **G1 novelty boundary:** it parallelizes *reasoning*, not *execution*. Our multi-browser shared frontier is a different axis, so we should cite it as complementary.
- **State abstraction:** max(DOM Jaccard, visual cosine) > τ is an alternative to our structural hash. We should report sensitivity to τ, as they do (Table 3).

## Your summary (150–250 words, your own words)
<!-- Write here -->
