# Paper Fact Sheets (ordered by relevance to our research)

These are **research notes**, not submission text. Each sheet covers the six required elements (Problem, Method, Data, Results, Limitations, Relevance) as notes with page references, and ends with an empty section for **your own 150–250-word summary**. The course rule is that summaries must be in your own words, and AI-generated writing gets the submission returned.

How to write each summary in about 10 minutes:
1. Re-read the fact sheet.
2. Close it.
3. Write the paragraph from memory.
4. Check your numbers against the sheet.

| # | Paper | Venue | Read depth | Main gap |
|---|---|---|---|---|
| 01 | [WebTestPilot](01_webtestpilot-fse26.md) ⭐ base | FSE 2026 (A*) | Full | BASE · G2 · G3 |
| 02 | [Are Autonomous Web Agents Good Testers?](02_autonomous-web-agents-testers-issta25.md) | ISSTA 2025 | Full (preprint) | G2 |
| 03 | [WebCQ](03_webcq-ase26.md) | ASE 2026 (A*) | Full | G1 |
| 04 | [GraphDroid](04_graphdroid-ase26.md) | ASE 2026 (A*) | Full | G1 · cost |
| 05 | [MAdroid, multi-user testing](05_madroid-multiuser-icse26.md) | ICSE 2026 (A*) | Full | G1 |
| 06 | [RippleGUItester](06_rippleguitester-pacmse26.md) | PACMSE 2026 | Full | G2 |
| 07 | [AutoE2E](07_autoe2e-icse25.md) | ICSE 2025 (A*) | Full | G3 · EVAL |
| 08 | [MAST](08_mast-neurips25.md) | NeurIPS 2025 D&B (A*) | Full | G1 · G2 |
| 09 | [ScenGen](09_scengen-tosem26.md) | TOSEM 2026 (Q1) | Full | G1 · G2 |
| 10 | [CATTest / CATJudge](10_cattest-emnlp26.md) | EMNLP 2026 (verify) | Full | G2 · G3 · EVAL |
| 11 | [Judge](11_judge-tosem26.md) | TOSEM 2026 (Q1) | ⚠ Abstract only, PDF needed | G1 |
| 12 | [MemoDroid](12_memodroid-ase25.md) | ASE 2025 (A*) | ⚠ Abstract only, PDF needed | G1 |

The course needs at least 10. These 12 give every gap at least 4 supporting papers. Download Judge and MemoDroid through the library before 14 Oct.

## Evidence matrix (raw numbers for the gap table, with sources)

### G1: Parallel or multi-agent exploration repeats work and lacks budget-controlled evidence

| Evidence | Source |
|---|---|
| Cooperative multi-agent RL: +27.1% states over *independent* agents with the same agent count. RL only, live sites, console-log oracle. | 03 WebCQ, §6.2 |
| MARG's tabular coordination degrades at 8–12 agents (communication overhead). | 03 WebCQ, RQ4 |
| "Asynchronous" GraphDroid parallelizes LLM reasoning over **one** device. Multi-browser execution is not studied. | 04 GraphDroid, §2.3 |
| MAdroid's multi-device agents coordinate by turn-taking on one task; scalability past 3 devices is untested. | 05 MAdroid, §5 |
| Multi-agent LLM systems often gain little; step repetition is the top single failure mode (15.7%). | 08 MAST, Fig. 1 |
| A single prompted LLM leads to "redundant exploration". Shared memory plus state dedup helps within one team. | 09 ScenGen, p.8 |
| WebTestPilot runs tests sequentially on purpose to avoid shared-state interference. | 01 WebTestPilot, §5.2.3 |
| State abstraction drives exploration quality (+2.6–14.1% coverage). | 11 Judge |

### G2: LLM testers report bugs that aren't real

| Evidence | Source |
|---|---|
| PinATA specificity 0.47–0.57 across 3 frontier LLMs (passing tests flagged as failing). | 02, Tables 2 and 4 |
| PinATA bug-detection precision 0.26 on WebTestPilot's benchmark. | 01, Table 4 |
| RippleGUItester precision 0.464. **About 61% of FPs come from rendering/timing non-determinism and replay instability.** The authors propose repeated execution as the fix. | 06, §4.3 |
| Frontier-model P-score ≤ 48.6. Without runtime evidence (static review), P = 10.6. | 10, Tables 1 and 3 |
| Verification failures: 17.3% of MAS failures (incomplete 8.2% + incorrect 9.1%). Calls for "multi-level verification". | 08, §4 |
| LLM self-supervision causes 40% of ScenGen's failures (premature termination). | 09, RQ1 |
| WebTestPilot retries an assertion only once (n = 1) and never re-executes in a fresh session. | 01, §4.3.3 |
| Feature inference precision 0.55: LLM inferences hallucinate too. | 07, Table II |

### G3: Oracles depend on specs and checklists; spec-free oracles are missing

| Evidence | Source |
|---|---|
| WebTestPilot needs a complete NL requirement per test, and assumes requirements are complete (stated limitation). | 01, §7 |
| PinATA and ScenGen need given test cases or scenarios. | 02, 09 |
| AutoE2E infers *features* spec-free but generates **no oracles or assertions** (stated future work). | 07, §VI |
| Checklist-based web testing can't keep up with unanticipated features. Even with a project document, R-score ≤ 42.6. | 10, §1 and Table 1 |
| Exploration tools without semantic oracles detect crashes and console errors only. | 03, 04, 09 |

## Benchmarks found during reading (they affect the plan)

| Benchmark | Content | Status | Use for us |
|---|---|---|---|
| **WebTestPilot benchmark** | 4 apps (BookStack, Indico, InvoiceNinja, PrestaShop), 100 NL requirements, 100 injected bugs, Docker Compose | **Public**: github.com/code-philia/WebTestPilot | **Direct comparison with the base paper.** Our spec-free system vs. their spec-given 0.96 precision/recall. |
| **E2EBench** (AutoE2E) | 8 apps **including Conduit**, PetClinic, Dimeshift, with action instrumentation and feature grammars | Public | Feature-coverage metric on our dev app (Conduit) |
| **CATTest** | 102 AI-generated apps with ground-truth bugs, R/P scorer | Public | Held-out generalization set |
| PinATA benchmark | 3 WebArena apps, 113 NL tests | Public (Zenodo) | Optional |
| WebCQ artifact | MARL web tester | Zenodo | Optional coordinated non-LLM baseline |
