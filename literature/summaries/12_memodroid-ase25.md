# 12 · Beyond Static GUI Agent: Evolving LLM-based GUI Testing via Dynamic Memory (MemoDroid, ASE 2025)

> ⚠ **ABSTRACT-LEVEL fact sheet.** The PDF is paywalled (IEEE) and not yet in `pdfs/`. Download it through the university library, then fill in the `[TODO-full-read]` items before writing the course summary.

| | |
|---|---|
| **IEEE ref** | M. Chen, Z. Liu, C. Chen, J. Wang, Y. Xue, B. Wu, Y. Huang, L. Wu, *et al.*, "Beyond static GUI agent: Evolving LLM-based GUI testing via dynamic memory," in *Proc. 40th IEEE/ACM Int. Conf. Automated Softw. Eng. (ASE)*, Seoul, 2025, pp. 1603–1615, doi: 10.1109/ASE63991.2025.00135. |
| **Venue / rank** | ASE 2025 (CORE A*, verify) |
| **Artifact** | [TODO-full-read] |
| **Relevance** | Gap: G1 (memory to avoid redundant behaviour); also a comparison for our frontier's "experience sharing" |
| **Naming caution** | An earlier, unrelated "MemoDroid" is a mobile *task automator*. Cite this ASE 2025 testing paper by its full title. |

## Problem (from the abstract)
- LLM-based GUI testers **test each app in isolation and never build up experience**, so they miss deeper exploration and don't trigger bug-prone functionality.

## Method (from the abstract)
- **A three-layer memory**, retrieved at runtime and injected into the LLM prompt:
  - **Episodic memory:** traces of functional-level testing.
  - **Reflective memory:** summaries of issue patterns and **redundant behaviours**.
  - **Strategic memory:** exploration strategies synthesized across apps.
- Built as a **lightweight plugin** that can be added to existing LLM GUI testers.
- [TODO-full-read: storage and retrieval mechanism; LLM; how memories are written and updated; how much is carried across apps.]

## Data (from the abstract)
- Real-world Android apps from **15 categories**, plus a field study on **200 popular apps**.
- **Five LLM-based baseline testers**, each with and without MemoDroid. [TODO-full-read: which ones; probably GPTDroid, DroidAgent, AUITestAgent…]

## Results (from the abstract and the ASE program page)
- Across the 5 baselines, adding MemoDroid increases **activity coverage by 79–96%**, **code coverage by 81–97%**, and **bug detection by 57–198%**.
- Ablations confirm that each memory layer contributes.
- **49 new bugs** in 200 apps: 35 confirmed fixed, 14 acknowledged.
- [TODO-full-read: absolute numbers; time budget; repetitions; cost overhead of memory retrieval.]

## Limitations
- **Stated by the authors:** [TODO-full-read]
- **Candidates to verify yourself:**
  - Large *relative* gains may hide low absolute coverage in the baselines.
  - Cross-app strategic memory raises the risk of train/test leakage across apps. How were the evaluation apps separated?
  - Memory is shared *across time* (sequential runs), not *across concurrent agents*.
  - Bug oracle: probably crashes only.

## Relevance to our project
- **G1:** MemoDroid's reflective memory explicitly targets **redundant behaviour**. That's the same failure our shared frontier attacks, but for one agent over time instead of N agents concurrently.
  - Our frontier works like episodic memory shared live between workers.
  - The novelty boundary to state: *experience reuse across runs* (MemoDroid) vs. *coordination within a run* (ours).
- **Plugin design:** it shows that memory can be added on top of existing testers. We could similarly make the frontier pluggable over any worker policy, which also makes ablations simpler.

## Your summary (150–250 words, your own words)
<!-- Write only after reading the full PDF -->
