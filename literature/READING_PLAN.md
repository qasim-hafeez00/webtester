# Reading Plan

The corpus has 67 papers. They don't all need the same depth. This plan sets which papers to read when, and what to pull out of each, so the reading feeds the gap table and the design directly.

## Three depths

| Depth | Time | What you do | Papers |
|---|---|---|---|
| **Deep** | 2–3 h | Full read. Fill the extraction sheet below. Write your own 150–250-word summary. | The 10 papers chosen for the course |
| **Targeted** | 30–45 min | Abstract, approach figure, evaluation setup, results table, limitations | Other T1 and the key T2 competitors |
| **Skim** | 10 min | Abstract and contribution list only, so you can cite them accurately | Remaining T2 and T3 |

## Order (Phase 1 is due 17 Oct)

**Day 1, 12 Oct (decides the design).** Read deep:
1. `webtestpilot-fse26` (base paper)
2. `autonomous-web-agents-testers-issta25`
3. `webcq-ase26`

These three answer the questions everything else depends on. What exactly does the base paper require as input? How bad are false positives? How does the closest parallel competitor coordinate its agents?

**Day 2, 13 Oct.** Read deep:
1. `judge-tosem26`
2. `scengen-tosem26`
3. `mast-neurips25`

Read targeted: `temac-arxiv25` (benchmark apps and coverage setup), `web-gui-empirical-arxiv26`, `marg-ase24`, `distributed-testar-jss23`.

**Day 3, 14 Oct.** Read deep:
1. `web-form-llm-tosem25`
2. `llmdroid-fse25`
3. `cattest-emnlp26`
4. `multiuser-feature-testing-icse26`

Read targeted: `anypoc-arxiv26`, `gui-invariants-ist24`, `kuitest-icse25`.

**After Phase 1.** Skim the rest of T2 and T3 while building. Read a T2 paper deep only if it threatens novelty.

## Choosing the course list of 10

There are 21 eligible papers (marked *course-10* in README.md). The course asks for **at least** 10, so reviewing 12 is allowed and gives each gap stronger support. Pick papers that together give evidence for all three gaps:
- **G1, coordination:** webcq, graphdroid, judge, scengen, multiuser-feature-testing, memodroid, llmdroid, neural-embeddings-web
- **G2, evidence gate:** autonomous-web-agents-testers, rippleguitester, sifting-noise, mast, cvebench
- **G3, spec-free oracles:** webtestpilot (base), autoe2e, web-form-llm, cattest, bug-aware-gui, elevate-vui, guispector

**Suggested 12:**
1. webtestpilot (base)
2. autonomous-web-agents-testers
3. webcq
4. graphdroid
5. judge
6. scengen
7. multiuser-feature-testing
8. memodroid
9. rippleguitester
10. mast
11. autoe2e
12. cattest

Every pick except CATTest is from an A*/A conference or a Q1 journal. Swap in `autopt-tifs25` if your supervisor wants the security side represented. Before you commit: **check that CATTest appears in the EMNLP 2026 proceedings**, and that the PACMSE papers are the FSE/ISSTA editions the index claims.

Judge, MemoDroid and LLMDroid are behind ACM/IEEE paywalls. Download them through the university library before 13 Oct.

## Extraction sheet (one per deep-read paper)

Fill this in **your own words** in `literature/notes/<id>.md`. These notes later become the course summaries and the paper's related work.

```
Problem:         what failure or limitation of earlier work does it attack?
Setting/inputs:  what does the tool need (spec? test cases? URL only?)
Method:          agents/roles, state representation, memory, oracle
Benchmark:       apps (names, size), faults (seeded? real? how many?)
Baselines:       which tools, same budget?
Metrics:         coverage type, fault metrics, cost metrics
Key numbers:     2–4 headline results
Author-stated limitations:
My limitations:  dataset · method · evaluation · generalizability · missing baselines
Artifact:        code/benchmark public? link, license
Relation to us:  which gap (G1/G2/G3), and what we do differently
Threat to our novelty (0–3) and why:
```

The **"Threat to our novelty"** score is the most important field for the paper. If anything scores 3, tell me immediately, because the plan will have to change.
