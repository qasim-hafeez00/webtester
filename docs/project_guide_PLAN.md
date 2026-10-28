# Plan: the project guide for the supervisor

Planning notes for `docs/project_guide.md`, not the guide itself.

## 1. What the guide is

- **Reader:** the supervisor, who knows nothing about the project. After reading, they should be able to:
  - explain the idea and why it matters;
  - see where it stands against current papers;
  - read and run the code;
  - judge the results so far and the plan to the end.
- **Form:** one living Markdown file, `docs/project_guide.md`, kept in the repo next to the code it describes. Every update adds to it; nothing is rewritten silently.
- **Authorship:** the guide is **not a course submission**. It shares progress with the supervisor to get advice (user, 27 Oct). Claude writes the whole guide, prose included, and the user reviews it.
  - The [You]/[Facts] marks below now mean "interpretation" and "facts from the logs". Both are written by Claude.
  - **[Gen]** still means reference material generated from the code and logs by a script, so it stays correct after code changes.
  - Course submissions and the paper are still written by the user.
- **Defaults chosen:** one file, `docs/project_guide.md`, in Markdown. §8 is split into `docs/code_reference.md` only if the guide gets too long.

## 2. Rules that keep it updatable

1. **Header block:** "Status as of <date>", harness version, last lock commit, and runs counted so far.
2. **Changelog** at the top: one line per update (date, what changed, which sections).
3. **Stable section numbers.** New work goes into new subsections (for example 9.6 "Night 4"). Existing numbers never change, so earlier references stay valid.
4. **Results are append-only.** Each experiment block names its harness version, condition, label (`h3rep`, `bs4rep` …) and the run IDs. Superseded results stay, marked "superseded by …".
5. **Link, don't copy.** Long material stays where it is and the guide links to it. That covers `logs/decisions.md` (D1–D54), `logs/issues.md` (I1–I48), the run registry, the results files and the literature fact sheets. The guide holds the summary and the "why".
6. **Generated parts are fenced** between `<!-- gen:start name -->` and `<!-- gen:end -->`. A script (`scripts/guide_gen.py`, to build) refills them from the code (`ast`: modules, classes, functions, docstrings, callers) and from `summary.json` and the registry. Updating the code reference is then one command.
7. **Version tags in the code reference:** each module and function carries "added in vN / changed in vN (Dxx)".

## 3. Outline

### Part A: The idea (no code yet)

**0. How to read this guide** [Facts]
- Map of the parts.
- Glossary pointer.
- Reading paths: 20 min (parts A and F), 1 h (plus B and E), full.

**1. One-page summary** [You]
- The problem, the idea, the 3 gaps, what is built, and the headline results with numbers.
- Where it is going: course submission on 4 Nov; ISSTA 2027 (abstract 8 Jan, paper 11 Jan 2027); fallback ICST 2027 NIER.
- Sources: `docs/00_research_plan.md` §1 (thesis), `docs/issta2027_plan.md` §2, the ledger.

**2. Background** [You, with a Facts sheet]
- 2.1 Web application testing:
  - what a functional bug is;
  - why end-to-end testing is hard (state, async UI, data);
  - crawlers (Crawljax style).
- 2.2 The oracle problem:
  - implicit oracles (crashes, 5xx, console errors) versus semantic oracles (wrong content);
  - spec-based versus spec-free.
- 2.3 LLM agents for testing:
  - an agent explores a UI by observe → decide → act;
  - tokens, rate limits, cost.
- 2.4 Parallel exploration:
  - why N agents duplicate work;
  - shared-frontier ideas.
- 2.5 False positives:
  - why agent-reported bugs need evidence;
  - flakiness and reproduction.
- Figure: the observe → decide → act loop, with where the oracles sit.

**3. Literature review: where the field stands** [You write; Claude supplies the comparison table as Facts]
- 3.1 The base paper, WebTestPilot (FSE'26): what it does, its benchmark (4 apps, 100 injected bugs), its numbers, and its limits that we build on.
- 3.2 Other papers, grouped by theme, using the fact sheets `literature/summaries/01–12`:
  - LLM web and GUI testing: autonomous web agents (ISSTA'25), AutoE2E (ICSE'25), WebCQ, ScenGen, CatTest;
  - state models: GraphDroid, Crawljax/ATUSA invariants, APE, WebExplor, LLM-Explorer, AutoDroid;
  - multi-agent and multi-user: MAdroid, MAST (agent failure taxonomy);
  - oracles and judges: Judge (TOSEM'26), PinATA, Huang et al. (ICLR'24, LLMs do not self-correct without outside feedback);
  - regression and memory: RippleGUItester, MemoDroid.
- 3.3 Comparison table [Facts]:
  - columns: paper, venue, parallel?, shared state?, reproduce-before-report?, semantic oracle?, spec needed?, apps, metrics;
  - our row at the bottom.
- 3.4 The gap statement [You]: what no paper does together. Source: research plan §2 (novelty map).

**4. Research questions, goals and hypotheses** [You, built on Facts]
- G1 (parallel duplication) → RQ1; G2 (unreal bugs) → RQ2; G3 (no semantic oracle) → RQ3.
- For each RQ: hypothesis, component, metric, the condition that tests it, and the go/no-go bar.
- Goals and KPIs: research plan §3 and §7; ISSTA KPIs K1–K8.
- Out of scope: security, spec-based testing.

### Part B: The system

**5. Architecture** [Facts plus figures]
- 5.1 Component diagram: CLI → runner → workers (browser + policy + LLM) → shared budget, frontier, memory and state graph → oracles → findings → gate → report and registry.
- 5.2 Data flow of one run: config → app up/reset → N workers in parallel → `trace.jsonl` and `replay.jsonl` → metrics → gate → `summary.json` → registry. Sequence diagram.
- 5.3 Abstract state: what a "state" and a "page" are (`state.py`, `stategraph.py`).
- 5.4 What a finding is: signal → candidate (signature, dedup) → gate label (confirmed, flaky, rejected, unverified) → judge verdict → human label.

**6. The conditions B0–B4** [Facts table plus a short You intro]
- 6.1 One table, one row per condition:
  - conditions: `b0`, `random`, `b1`, `b2`, `b3`, `b3local`, `b3v2`, `b3v2local`, `b3v3`, `b4`, `b4det`, `b4nog1`, `b4nog3`;
  - columns: what it is, which gap it tests, the files involved, the decision that defined it, harness version, and whether it was used in counted runs.
- 6.2 For each condition: what the worker does differently (a diff against the previous one) and an example trace snippet.
- 6.3 The ablation logic: A-G1 = `b4nog1`, A-G3 = `b4nog3`, A-G2 = B4's raw candidates against gated ones (paired); `b3v2local` / `b3local` give the frontier without sharing.

**7. Harness versions v1 → v4** [Facts]
- One subsection per version. Each has:
  - what changed and why, with D-numbers;
  - which issues it fixed, with I-numbers;
  - which runs used it (labels);
  - its lock commit.
- 7.1 v1, Phase 1 and the first G1 work (11–16 Oct).
- 7.2 v2: gate v2, full-prefix window, I36 (D42, D44), `h2rep`.
- 7.3 v3: settle waits, active controls, field values as text, checks prompt v3 (D46), `h3rep` and `bsrep`.
- 7.4 v4:
  - state graph, run memory, consistency oracles R01–R17 and the I-rules, FrontierV3 travel, the gate on signatures;
  - pre-lock fixes D50, D53, D54;
  - locked `540887e`.
- Then a version × condition matrix.

### Part C: The code

**8. Code reference** [Gen plus Facts]
- 8.1 Repository map. Every top-level folder and what lives there:
  - `src/webtester`, `apps/realworld`, `apps/bookstack`, `configs/`, `scripts/`, `tests/`, `logs/`, `docs/`, `literature/`, `runs/`.
- 8.2 Module-by-module, in reading order, for the 25 modules. For each:
  - purpose, lines of code, version history;
  - main classes and functions (name, signature, what it does, who calls it);
  - which conditions use it;
  - its tests.

  | Group | Modules |
  |---|---|
  | Entry | `cli`, `__main__`, `config`, `runner`, `budget`, `trace` |
  | Browser and app | `browser`, `appctl`, `state` |
  | Deciding | `policies`, `llm`, `worker`, `crawler`, `frontier` |
  | v4 knowledge | `stategraph`, `memory` |
  | Oracles | `oracles` (implicit), `inferred` (G3 v1–v3), `consistency` (G3 v4) |
  | Evidence | `gate` (G2) |
  | Analysis | `metrics`, `stats`, `labels`, `registry` |

- 8.3 Deep dives with code excerpts, for the parts that carry the research:
  - the worker loop;
  - FrontierV2/V3 (focus areas, leases, `[done xN]`, travel);
  - the gate (windows 1/4/full, k = 3, signature match, the 20-min cap, the judge);
  - consistency oracles: the rule catalogue R01–R17 and the I-rules, with tiers T1/T2/T3, one example each and the fault it catches.
- 8.4 Scripts: what each one does and when to use it. They are `run_batch.py`, `run_queue.sh`, `after_reset.sh`, `queue_keepawake.ps1`, `night3.sh`, `pilots_v4.sh`, the `resweep_*.sh` scripts and `scripts/literature/`.
- 8.5 Tests: what each test file covers (offline versus live), and how to run them (80 tests).
- 8.6 Configuration: every key in `configs/*.toml` (app, LLM, gate, budget) and its default.

### Part D: Running it

**9. How to run** [Facts plus Gen]
- 9.1 Setup:
  - prerequisites: Python, `.venv`, Playwright, Docker Desktop;
  - `.env` keys (names only, never values);
  - hardware notes: 4 cores, 16 GB, one app at a time (I19).
- 9.2 The apps:
  - Conduit: port 4100, faults F01–F10, reset, `verify_faults.py`;
  - BookStack: port 4200, BS01–BS18, client-side injection, seed-loader.
- 9.3 Commands: all 10 `webtester` subcommands, each with a real example:
  - `app`, `run`, `report`, `registry`, `compare`, `triage`, `gate-report`, `regate`, `resweep`, `graph`.
- 9.4 A full experiment night: queue → keep-awake → health checks → key rotation (D41) → registry → labelling. Source: `docs/phase2_runbook.md`.
- 9.5 Reading a run folder: `config.json`, `trace.jsonl`, `replay.jsonl`, `findings.json`, `summary.json`, `graph.json`. One annotated example.
- 9.6 Common failures and fixes: quota, Docker stopped, sleep, reset hang (from the I-list).

### Part E: Evidence

**10. Experimental method** [You, with Facts]
- Subjects and ground truth: the seeded faults, the fault-class taxonomy, exposure markers and detection rules.
- Budgets and fairness: equal tokens, wall-clock, 4 workers, interleaving (D18, D20).
- Validity rule D20 and invalid runs.
- Statistics: median [IQR], exact Mann-Whitney U (`stats.py`).
- Labelling: D45 and D48, plus a 20% blind sample.

**11. Results so far** [Facts tables; You interpret]
- Append-only blocks, each with its version, runs and source file.

  | Block | Source |
  |---|---|
  | 11.1 Phase 1: B0 vs B1 | `phase1_results.md` |
  | 11.2 G1: B2 vs B3 v1 vs B3 v2 | `phase2_g1_results.md` |
  | 11.3 G2/G3 on Conduit: B4, ablations, gate precision | `phase2_g23_results.md` |
  | 11.4 BookStack: B0, B3v2, B4 | `phase2_bookstack_results.md` |
  | 11.5 Oracle gap analysis: why semantic faults were missed | `oracle_gap_analysis.md` |
  | 11.6 v4 development: resweep false-alarm rates per rule, lock numbers, pilots | progress 26–27 Oct |
  | 11.7 Night 3 (`h4rep`, `bs4rep`) | to fill |
  | 11.8 onward | reserved: Night 4, PrestaShop |

- Each block contains a table, the takeaway in one line, and the threats specific to that block.

**12. Lessons, problems and threats to validity** [You, with Facts]
- What went wrong and what it taught us: quota, sleep, flaky replay, cross-worker gate loss, and false-alarm sources. Source: the I-list.
- Threats: internal, external and construct. Source: ledger §8.

### Part F: The road ahead

**13. Current standing** [Facts, refreshed every update]
- A table of what is done, running and pending, per RQ.
- A one-paragraph honest assessment per gap. [You]

**14. Plan to the end** [Facts plus You]
- Nights 3–4.
- PrestaShop as a held-out app (D51).
- Course submission on 4 Nov.
- The paper-grade matrix (rented VM, paid API).
- Claim decision and go/no-go on 5 Jan.
- ISSTA timeline.
- Risks and fallbacks.
- Source: `docs/issta2027_plan.md`.

**15. Decisions the supervisor is asked about** [You]
- Open questions, for example: the paper framing A or B, budget for the paid API and VM, and whether the 3-gap scope is right.

### Appendices
- A. Glossary [Facts]: state, frontier, focus area, lease, signature, gate window, tier, sweep, resweep, travel, intent, exposure marker, and so on.
- B. Fault catalogues: F01–F10 and BS01–BS18 (what each one breaks, its class, how it is detected). [Gen from `faults.toml`]
- C. Decision index D1–D54: one line each, linked. [Gen]
- D. Issue index I1–I48: one line each, linked. [Gen]
- E. Run registry snapshot. [Gen]
- F. Literature list with links to the PDFs and fact sheets. [Gen from `literature/papers.json`]

## 4. Figures to make
1. Observe → decide → act loop with the oracles (§2).
2. Component diagram (§5.1).
3. Sequence of one run (§5.2).
4. Condition ladder B0 → B4, showing what each step adds (§6).
5. Gate flow: candidate → windows → k replays → label → judge (§8.3).
6. Timeline of harness versions and experiment nights (§7).
7. Result charts: faults per run, duplicates, precision by gate stage (§11).

Mermaid in the Markdown, so the figures stay editable and diff in git.

## 5. Build order and size
1. Skeleton with all headings, the header block and the changelog.
2. `scripts/guide_gen.py`, then generate §8.2, §9.3 and appendices B–F. Code reference: about 600–900 lines.
3. Fact tables: §3.3, §6.1, §7, §11, §13.
4. Figures.
5. Your prose: §1–4, §10, the interpretations in §11, §12 and §13–15.
6. Review pass: does every claim link to a log, run ID or file?

The whole guide comes to about 2,500–3,500 lines. If it gets too long, §8 moves to `docs/code_reference.md` and the guide links to it. Decide after step 2.

## 6. Open choices (yours)
- One file, or a guide plus a separate code reference?
- Will it be shared as Markdown, or exported to PDF or Word for the supervisor?
- Does the course count it as a submission? This decides who writes the [Facts] text.
