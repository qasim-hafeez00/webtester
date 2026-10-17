# 08 · Why Do Multi-Agent LLM Systems Fail? (MAST, NeurIPS 2025 Datasets & Benchmarks)

> **Fact sheet** (research notes from a full read of arXiv 2503.13657v3, the NeurIPS 2025 D&B camera-ready). Not submission text.

| | |
|---|---|
| **IEEE ref** | M. Cemri, M. Z. Pan, S. Yang, L. A. Agrawal, B. Chopra, R. Tiwari, K. Keutzer, A. Parameswaran, D. Klein, K. Ramchandran, M. Zaharia, J. E. Gonzalez, and I. Stoica, "Why do multi-agent LLM systems fail?" in *Adv. Neural Inf. Process. Syst. (NeurIPS), Datasets and Benchmarks Track*, 2025. |
| **Venue / rank** | NeurIPS 2025, D&B track (CORE A*, verify that the D&B track counts for your supervisor) |
| **Artifact** | github.com/multi-agent-systems-failure-taxonomy/MAST · HF dataset mcemri/MAST-Data · `pip install agentdash` |
| **Relevance** | Gaps: G1 (motivates equal-budget evaluation), G2 (verification failures), and our failure-analysis method |

## Problem
- Multi-agent LLM systems (MAS) often perform **only slightly better** than single agents or simple best-of-N sampling (p.1–2).
- 7 state-of-the-art open-source MAS **fail on 41–86.7% of tasks** (p.2).
- Nobody had an empirically grounded explanation of *why* MAS fail (p.2).

## Method
- **Grounded Theory** analysis of 150+ traces (averaging about 15k lines each) from 5 MAS frameworks by 6 experts: open coding, constant comparison, memoing, until saturation (§3.1).
- **3 inter-annotator agreement rounds**, ending at **κ = 0.88** (§3.2).
- **LLM-as-judge annotator** (o1, few-shot): accuracy 0.94, κ = 0.77 against humans. On unseen MAS and benchmarks, κ = 0.79 (Table 2, §3.3–3.4).
- **MAST taxonomy:** 14 failure modes in 3 categories, mapped to pre-execution, execution and post-execution stages (Fig. 1).

## Data
- **MAST-Data:** 1,642 annotated traces from 7 MAS (Table 1, p.3):
  - Frameworks: ChatDev, MetaGPT, HyperAgent, AppWorld, AG2, Magentic-One, OpenManus.
  - Tasks: coding (ProgramDev, SWE-Bench Lite), math (GSM-Plus, OlympiadBench), general agent tasks (GAIA, MMLU).
  - Models: GPT-4/4o, Claude 3.7, Qwen2.5-Coder, CodeLlama.
- **MAST-Data-human:** 21 traces, each annotated by 3 experts.

## Results
Failure shares from Fig. 1:

| Category | Share | Failure modes |
|---|---|---|
| **FC1, System design** | 44.2% | Disobey task spec 11.8% · disobey role 1.5% · **step repetition 15.7%** · loss of history 2.8% · unaware of termination 12.4% |
| **FC2, Inter-agent misalignment** | 32.3% | Conversation reset 2.2% · fail to ask for clarification 6.8% · task derailment 7.4% · information withholding 0.85% · ignoring other agents 1.9% · **reasoning-action mismatch 13.2%** |
| **FC3, Task verification** | 23.5% | Premature termination 6.2% · **no or incomplete verification 8.2%** · **incorrect verification 9.1%** |

- **Insights** (p.7–8):
  1. Failures come from *system design*, not only model limits: changing ChatDev's roles alone gave +9.4% success with the same model.
  2. Communication protocols such as MCP and A2A don't fix misalignment.
  3. **Multi-level verification is needed.** Existing verifiers only do superficial checks (e.g. "the code compiles"). Adding a high-level objective verification step to ChatDev gave **+15.6%**.
- System-specific profiles differ. For example, MetaGPT has 1.56× more verification failures than ChatDev (§5.1).

## Limitations

**Stated by the authors:**
- The taxonomy is not claimed to be exhaustive.
- Some failures come from model limits (hallucination).
- The interventions improve results but don't fix everything.

**Spotted myself:**
- **Dataset:** the domains are coding, math and generic agent tasks. **No GUI, web or testing agents**, so transferring the taxonomy to browser-testing MAS is untested.
- **Method:** most of the 1,642 traces are labelled by an LLM (κ = 0.77). Errors in the judge propagate into the failure statistics.
- **Evaluation**
  - The failure counts per system are not comparable across benchmarks, as the authors say (Fig. 4).
  - The interventions are small case studies, not a controlled ablation.
- **Missing:** cost and efficiency of MAS versus single agents. The "minimal gains" claim is cited rather than re-measured under equal compute.

**Future directions:** structured agent messages; stronger verification; organization-theory-based MAS design.

## Relevance to our project
- **G1 motivation:** MAS gains are often minimal, so **any multi-agent claim must be compared at equal budget** with a single agent and with independent agents. This justifies our fairness protocol (equal tokens and browser-minutes).
- **Failure modes we expect and should design against:**
  - FM-1.3 step repetition: parallel workers re-exploring the same states. **Our shared frontier targets this.**
  - FM-2.4 information withholding and FM-2.5 ignoring input: workers not sharing discovered states.
  - FC3 verification failures (8.2% + 9.1%): reporting a bug without real verification. **Our evidence gate is the "multi-level verification" the authors call for.**
- **Method to borrow:** we use MAST plus the RippleGUItester and PinATA taxonomies as the **coding scheme for our failure analysis**, and measure inter-rater κ if a second annotator is available.

## Your summary (150–250 words, your own words)
<!-- Write here -->
