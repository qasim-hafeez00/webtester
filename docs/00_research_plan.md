# Research Plan: Coordinated, Evidence-Gated LLM Exploration for Web Application Testing

Status: v1 foundation, 10 Oct 2026. This is our internal planning document. It is not text for the course submission: the course runs a Turnitin AI-writing check, so the literature review, proposal and paper must be written by the group.

---

## 0. Decisions at a glance

| Decision | Choice | Why |
|---|---|---|
| Course seed | **G2: Agentic AI and MCP for Intelligent Software Engineering** (supervisor: Meemon Khan), as an own-idea variant that needs approval | The seed already lists test generation, multi-agent collaboration and reliability. Our browser tools can be exposed over MCP. |
| Domain focus | **Functional web testing first.** Security is a small optional slice only. | Clear fit for ISSTA and the base paper. The LLM-pentest space is crowded (CVE-Bench, AutoPT, PTFusion, BACAgent, AWE). The ethics story is also simpler. |
| Headline claim | Under a **fixed total budget**, a shared exploration frontier makes parallel LLM testers more efficient, and an evidence gate makes what they report trustworthy | Neither part has been measured in controlled conditions for LLM web testers (see §2) |
| Base paper | **WebTestPilot**, FSE 2026 / PACMSE, DOI 10.1145/3797115 (CORE A*) | It is the closest work, and its oracle inference is the thing our G3 extends |
| Backup base | **Judge**, ACM TOSEM 2026, DOI 10.1145/3736162 (Q1) | Same state-abstraction problem and the same coverage-benchmark lineage |
| Primary venue | **ISSTA 2027** (abstract 8 Jan, paper 11 Jan 2027) | Best topical fit. The deadline falls after the course ends. |
| Fallback venue | **ICST 2027 NIER** (13 Jan 2027, short paper) | Fits early but evidence-backed results |
| Parallelism range | N ∈ {1, 2, 4, 8} on the laptop and **16 on a rented VM**. We do not promise "100s". | This machine has 4 cores and 16 GB of RAM. The result we report is the scaling curve, not a headline browser count. |

---

## 1. The thesis (one paragraph we defend everywhere)

Choosing the next browser action is now commodity technology (browser-use, Jev Use, Playwright MCP). The open problems in autonomous web testing sit above that layer:
**(a)** adding more LLM explorers mostly repeats the same work,
**(b)** without a specification, the agent cannot tell what counts as a bug, and
**(c)** what the agent reports is often wrong.
We build a system that **explores in parallel through a shared abstract-state frontier**, **infers executable oracles from what it observes** (no spec needed), and **reports a bug only after it reproduces in a fresh session**. We then measure each of the three mechanisms separately under equal token and browser-minute budgets.

**Explicitly not claimed:** testing "every input of any website", hundreds of browsers, being first to do parallel web testing (MARG, ASE 2024, did it with reinforcement learning), or being first to verify bug reports.

---

## 2. Novelty map: what exists and where our gap is

Status key: ✅ peer-reviewed and verified · 🟡 venue claimed but not yet checked · 📄 preprint only (cite it, but it does not count toward the 10)

| Work | Status | What it does | What it leaves open (our opening) |
|---|---|---|---|
| WebTestPilot (FSE'26) | ✅ A* | Turns an NL spec into steps with pre/postconditions over symbolized GUI elements. Reports 96% precision and 96% recall on bug-injected apps. | **Needs an NL spec for every test.** It does not explore. Artifact availability is not confirmed. |
| Are Autonomous Web Agents Good Testers? (ISSTA'25) | ✅ | PinATA agent, 3 apps, about 100 test cases | **Specificity ≤ 57%**, so agents flag passing tests as failing. This is the strongest evidence for G2. |
| Judge (TOSEM'26) | ✅ Q1 | State abstraction for web GUI testing (tree-hash merge plus a learned classifier) | Built for RL and model-based tools. Single explorer. |
| Temac (arXiv 2506.00520) | 📄 | LLM agents take over after WebRLED's coverage plateaus. +12.5–60.3% coverage on 6 apps, about $1.7/h. | **Sequential**, with no parallel workers and no verification step. Its 6 apps are our benchmark source. |
| WebRLED (arXiv 2504.19237) | 📄 | Deep RL web explorer, 12 apps plus a top-50 field study | Not LLM-based |
| MARG (ASE'24) | ✅ prior art | Multiple cooperating RL agents test one website | RL, not LLM. No evidence gate. |
| Empirical study of web GUI testing (arXiv 2606.16650) | 📄 | Compares model-based, RL and LLM explorers. Code coverage correlates only weakly with failures found. | **Report both coverage and faults.** Do not use coverage alone. |
| ParaGUI (arXiv 2607.22689) | 📄 | Parallel GUI workers that decompose a *task* | Task completion, not exploratory testing |
| WebTestBench (arXiv 2603.25226) | 📄 public | Checklist generation plus defect detection. Agents do poorly. | A benchmark. Usable as an external held-out set. |
| CATTest / CATJudge (EMNLP'26, per arXiv 2609.00081) | 🟡 public | 102 AI-generated web apps with annotated bugs | **Held-out generalization benchmark** |
| AnyPoC (arXiv 2604.11950), REBUG (arXiv 2608.03598) | 📄 | Proof-of-concept/replay before reporting, in code and in bug-report reproduction | Supports our G2 design. Not applied to exploratory web testing. |
| CVE-Bench (ICML'25), AutoPT (TIFS'25), PTFusion (InfFus'26) | ✅ | LLM web pentesting | Security only. Out of our main scope. |
| Why Do Multi-Agent LLM Systems Fail? (NeurIPS'25 D&B) | ✅ | MAST failure taxonomy. Multi-agent gains are often small. | Motivates **equal-budget** comparisons |

**Our gap in one line:** no peer-reviewed work combines *parallel LLM exploration with explicit coordination*, *spec-free inferred oracles* and *a reproduce-before-report gate*, or measures each one under equal budgets.

**Novelty risk:** this field gets new arXiv papers every month. We run a weekly arXiv check (keywords: parallel GUI testing, LLM web exploration, multi-agent web testing) until submission.

---

## 3. Gaps → research questions → components → KPIs

Each gap maps to one component, one ablation, one RQ with a hypothesis, and one success criterion, as the rubric requires. Targets are **provisional**. We freeze them in a written protocol after the pilot (§7) and do not change them after seeing the main results.

### G1: Parallel LLM explorers duplicate work
- **Evidence:** Temac and WebTestPilot are single-agent or sequential. MARG is RL-based. MAST reports that multi-agent gains are often minimal. The empirical study and Judge show that state abstraction drives exploration quality.
- **Component:** a *shared frontier*, i.e. an abstract state graph plus a queue of unexplored (state, action) pairs with leases. Each worker claims an unexplored transition, runs it, and posts the new states it observes. Duplicate states and actions are removed through a canonical state ID (normalized URL route, a structural hash of the accessibility tree with repeated siblings merged and text stripped, and the session role).
- **RQ1:** At equal total tokens and browser-minutes, does a shared frontier with N workers reach more unique states and code coverage than N independent workers?
- **H1:** Yes, for N ≥ 4. The duplicate-action rate falls substantially, and returns diminish as N grows.
- **Ablation:** shared frontier → independent workers; canonical state ID → raw-URL dedup.
- **Provisional KPI:** at N = 8, **≥ 15% more unique abstract states** and **≥ 30% lower duplicate-action rate** than 8 independent workers. Significance: p < 0.05 and Â12 ≥ 0.71 (large effect).

### G2: Agents report bugs that are not real
- **Evidence:** PinATA specificity ≤ 57% (ISSTA'25). AnyPoC reports that coding agents fail to reject most false bug reports. RippleGUItester lists false-positive classes (hallucinated rendering, actions that never ran, non-determinism).
- **Component:** an *evidence gate*. A candidate finding becomes a minimal action trace, which is replayed k = 3 times in fresh browser contexts with reset app state. The oracle predicate is then checked. Each finding is labelled **confirmed** (reproduces k/k), **flaky** (reproduces in some runs) or **rejected** (never reproduces). Confirmed findings are saved with a Playwright trace.
- **RQ2:** Does the gate raise the precision of reported findings without a large loss of recall on seeded faults?
- **H2:** Precision rises sharply and recall drops only slightly.
- **Ablation:** gate on vs. gate off (raw candidates are reported).
- **Provisional KPI:** **precision ≥ 0.90** with the gate (we expect roughly 0.4–0.6 without it), **recall loss ≤ 10 percentage points**, and **gate cost ≤ 25%** of total tokens.

### G3: Spec-free testing has no semantic oracle (this is where we extend the base paper)
- **Evidence:** WebTestPilot gets its pre/postcondition oracles *from an NL spec*. The empirical study shows that crash-only signals miss many failures. WebTestBench and CATTest report detection bottlenecks.
- **Component:** *inferred oracles*. While exploring, the agent proposes executable expectations from what it observes, for example "after creating an article titled T, T appears on the author's profile list" or "a deleted item no longer appears after reload". These are stored as checkable predicates over page state (the spec-free version of WebTestPilot's conditions) and run alongside implicit oracles (HTTP 5xx, uncaught JS exceptions, console errors).
- **RQ3:** Do inferred oracles find seeded *semantic* faults that implicit oracles miss, and how close do they get to the spec-given (WebTestPilot-style) condition?
- **H3:** Inferred oracles find a substantial share of the semantic faults that implicit oracles miss, and their false alarms are filtered by the G2 gate.
- **Ablation:** implicit-only vs. implicit + inferred vs. spec-given (upper bound).
- **Provisional KPI:** inferred oracles find **≥ 40% of the seeded semantic faults** that implicit-only oracles miss.

---

## 4. System architecture

```
 User: URL + test accounts + scope allowlist
          │
 ┌────────▼─────────┐
 │ Scope/Safety Gate│  domain allowlist, blocked actions (pay/delete-account/email),
 └────────┬─────────┘  per-run budget caps (tokens, browser-minutes)
          │
 ┌────────▼──────────────────────────────┐
 │  SHARED FRONTIER  (G1)   SQLite/WAL    │  states, transitions, leases,
 │  canonical state-ID, (state,action) Q  │  priority = novelty × untried actions
 └──▲───────┬──────────────▲─────────────┘
    │ claim │ post         │
 ┌──┴───────▼──┐ ... ┌─────┴───────┐   N workers = N isolated browser contexts
 │ Explorer W1 │     │ Explorer WN │   cheap LLM; tools: observe (a11y tree), click,
 └──────┬──────┘     └──────┬──────┘   fill(input class), navigate, assert
        │ candidate findings + proposed oracles
 ┌──────▼──────────────────────────────┐
 │ ORACLE STORE (G3)                    │ implicit (5xx, JS error) + inferred predicates
 └──────┬──────────────────────────────┘
 ┌──────▼──────────────────────────────┐
 │ EVIDENCE GATE / VERIFIER (G2)        │ minimize trace → fresh context × k → check
 └──────┬──────────────────────────────┘ stronger LLM only for trace minimization/judgement
 ┌──────▼──────────────────────────────┐
 │ Report + Evaluator                    │ confirmed/flaky/rejected, Playwright traces,
 └──────────────────────────────────────┘ coverage, cost, JSONL logs for every step
```

- **Stack:** Python 3.13, async Playwright (Chromium), SQLite in WAL mode for the frontier (fine up to about 16 workers), and JSONL traces. The same tools are also exposed as an MCP server, which gives seed alignment and a demo. The experiment harness calls Playwright directly so MCP overhead does not distort timings.
- **Models:** tiered. A cheap model drives the explorers, and a stronger model handles oracle inference and verification judgements. Every condition uses the same models, so the comparisons stay fair. Token usage is logged per call.
- **Agentic justification (for the proposal):** the action space is open-ended and depends on state (forms, modals, auth). Oracles have to be inferred at runtime. Workers have to coordinate over shared state. A fixed crawler or a single LLM call cannot do any of these, and that is exactly what baseline B0 shows.
- **The baseline is not the proposed system:** baseline = B1 (one LLM worker, no frontier, no gate, implicit oracles only). Proposed = B4.

---

## 5. Environment, benchmark and ground truth (confirmed now, as the course requires)

| Track | Apps | Ground truth | Phase |
|---|---|---|---|
| Coverage | **RealWorld/Conduit** first. Then add Timeoff and Parabank, and later 4gaBoards, Gadael and Agilefant (the Temac/WebRLED app set). All in Docker. | Server line/branch coverage (nyc/istanbul for Node, JaCoCo for Java), client JS coverage via CDP, and abstract states counted *offline with one fixed abstraction for every condition* | P1: RealWorld only |
| Seeded faults | The same apps, with hand-seeded mutations | Each fault has a documented trigger, an oracle and a class (crash · validation · data/state · authorization · no-op UI). **Target: 10 in P1, about 30 for the paper.** Mostly *semantic* faults, not crash-only ones. | P1: 10 in RealWorld. **Done 11 Oct**: crash ×2, validation ×1, data ×5, authorization ×1, no-op UI ×1. Only 2/10 are visible to implicit oracles. All 10 verified on and off (`apps/realworld/faults/`). Four upstream defects U1–U4 are documented as unseeded ground truth. |
| **Base-paper comparison** | **WebTestPilot benchmark** (public, github.com/code-philia/WebTestPilot): BookStack, Indico, InvoiceNinja, PrestaShop, with 100 injected bugs, in Docker Compose. Start with BookStack. | Their bug labels. They report 0.96 precision and recall *with* specs; we run spec-free. | Phase 2 |
| Feature coverage | **E2EBench** (AutoE2E, ICSE'25) instrumented **Conduit**, plus feature grammars | Feature coverage, as a third coverage measure | Phase 2 |
| Held-out | **CATTest** (public, 102 apps with annotated bugs), plus WebTestBench if time allows | Benchmark labels | Paper phase |
| Optional security slice | OWASP Juice Shop with a canary oracle for 1–2 classes (stored XSS, IDOR) | Planted canary appears, or access is crossed | Stretch only |

Bugs found that we did not seed: two people label each one independently, and we report Cohen's κ.

**Status 16 Oct (base-paper comparison, D31–D37):** BookStack is set up from the WebTestPilot benchmark (`apps/bookstack`), not yet run.
- **Their bugs are not source faults.** They are client-side DOM mutations, armed after a scripted login, one per test case, and fired during the flow that tests them.
- **For exploration:** 27 BookStack scripts = 18 distinct faults. 13 are reachable without a spec. 5 need a literal from their spec. None is a crash.
- **Consequences:** BookStack measures G3 (implicit oracles score 0 by construction) and G1 exposure, on faults we did not write. Their oracles are relational across pages, which our single-page check language cannot express (I22).
- **Comparison with their 0.96 precision/recall:** not like for like (spec-given, per test flow vs spec-free, all faults at once). We report it as context, not as a head-to-head number.

---

## 6. Baselines and experiment matrix

| ID | Condition | Isolates |
|---|---|---|
| B0 | Deterministic BFS crawler plus a random form filler (no LLM) | The value of an LLM at all |
| B1 | One LLM worker (**Phase 1 baseline**) | Single-agent reference |
| B2 | N independent LLM workers | Parallelism without coordination |
| B3 | Shared frontier, gate off | G1 alone |
| B4 | Full system: frontier, inferred oracles and gate | Everything |
| A-G1 / A-G2 / A-G3 | B4 with one component removed at a time | Ablations |
| Spec-given | B4 with WebTestPilot-style NL-spec oracles for a subset of flows | How far below the base paper's upper bound we are |
| External (stretch) | WebRLED/Temac, if their artifacts run | Comparison with the state of the art |

**Fairness rules:** the same models in every condition, equal **total** token budget *and* equal total browser-minutes, and wall-clock reported separately. The app is reset between runs, seeds are fixed, and there are **5 repetitions** per configuration (10 if the variance is high). Statistics: Mann-Whitney U plus Vargha-Delaney Â12, reported as median and IQR.

**Rough size:** 3 apps × {B2, B3} × N ∈ {1, 2, 4, 8, 16} × 5 reps = 150 runs for G1 alone, plus the G2 and G3 runs. The **pilot measures tokens per step**, and we set the per-run budget and model choice from that number before committing money.

---

## 7. KPIs and go/no-go gates

**Engineering KPIs**
- E1: one worker explores RealWorld end-to-end for 15 minutes with no crash and writes a complete JSONL trace (**Phase 1 gate**)
- E2: 8 concurrent workers run stably for 30 minutes on the laptop. 16 workers run on the VM.
- E3: any run can be repeated from config, seed and app snapshot with one command
- E4: every confirmed finding includes a Playwright trace that replays

**Research KPIs:** G1, G2 and G3 above, frozen after the pilot in `docs/protocol.md`.

**Process gates**
| Date (est.) | Gate | If it fails |
|---|---|---|
| ~20 Oct | Phase 1: E1 met, 10 seeded faults, B0 and B1 numbers, approval received | Narrow to RealWorld only and report preliminary numbers |
| ~early Nov | Phase 2: B2–B4 run at N ≤ 8, gap-resolution table filled | Report what is measured. Partial results are acceptable to the course. |
| 30 Nov | Protocol frozen, ≥ 3 apps ready | Drop the CATTest held-out set to "future work" |
| 5 Jan 2027 | **Paper go/no-go:** G1 and G2 KPIs met with significance on ≥ 3 apps | Submit to ICST NIER (4 pages) instead of ISSTA |

---

## 8. Timeline (confirm the exact course dates on Classroom)

| When | Work |
|---|---|
| **10–11 Oct** | Send the approval email (G2 seed). Email the WebTestPilot authors about the artifact. Build the literature corpus (`literature/`). Create the repo. |
| **Status 12 Oct** | **Phase 1 experiments closed.** B0 n=5 vs B1 n=5 on Conduit (all faults on, 15 min): faults found 0 vs 1 (p=0.008), routes 14 vs 8 (p=0.016), duplicate-action rate ~46% for both (ns). `logs/experiments/phase1_results.md`. |
| **Status 11 Oct** | Done ahead of plan: Conduit running in Docker (Postgres, Express/Prisma, AutoE2E-instrumented Angular) with a deterministic seed and 1 s snapshot reset; harness `src/webtester` (B0, B1, B2 via `--workers`); JSONL traces; 10 seeded faults verified. **Blocked on:** a free-tier LLM API key for the first B1 runs. |
| 12 Oct | Get RealWorld running in Docker. Read WebTestPilot and PinATA in full. Write the single-worker loop and JSONL traces. |
| 13 Oct | Implement state ID v0. Build the B0 crawler. Seed the first 5 faults. Read WebCQ, Judge and Temac. |
| 14 Oct | Get B1 running end to end and produce the first B0/B1 numbers. Seed 10 faults in total. You write the summaries. |
| 15–16 Oct | You write the comparison table, gap table, proposal and diagram. Write the README, commit cleanly. |
| **17 Oct** | **Phase 1 submission** |
| Phase 2 (~21 Oct–~4 Nov) | Frontier and N workers, evidence gate, inferred oracles. Experiments at N ≤ 8 on RealWorld plus one app. Course paper (6–8 pages). |
| Phase 3 (~1 week) | Demo and viva |
| Mid-Nov–20 Dec | Paper-grade evaluation: 3–6 apps, N = 16 on the VM, 5 reps, CATTest held-out, statistics, failure analysis |
| 21 Dec–4 Jan | Write the paper and package an anonymized artifact |
| 8 / 11 Jan 2027 | ISSTA abstract / full paper. *Or* ICST NIER on 13 Jan. **Never both at once.** |

---

## 9. Venue strategy (checked 10 Oct 2026)

| Venue | Deadline | Verdict |
|---|---|---|
| **ISSTA 2027** Research | Abstract 8 Jan, paper 11 Jan 2027 (initial notification 20 Apr) | **Primary.** Best fit. Needs the full evaluation. |
| **ICST 2027** NIER | 13 Jan 2027 | **Fallback** for strong pilot results without the full evaluation |
| ICST 2027 Research | 2 Nov 2026 | Too early |
| FSE 2027 Research | 2 Oct 2026 | Already passed |
| ICSE 2027 NIER / AST 2027 | 23 Oct / 30 Oct 2026 | Too early |
| ICSE 2027 workshops (AGENT, LLM4Code, …) | ~13 Nov 2026 | Possible as a 4-page early result, but it **uses up the novelty** before ISSTA. Not recommended. |
| ASE 2027 | Not announced (one tracker says ~late Mar 2027, unverified) | Where we resubmit if ISSTA rejects early. Check for date conflicts. |
| USENIX Security 2027 cycle 2 | 26 Jan 2027 | Only if we pivot to security. Not our plan. |
| ACM TOSEM / IST / JSS | Rolling | Extended journal version later |

Course rule: published papers include the instructor and the supervisor as co-authors.

---

## 10. Risks and fallbacks

| Risk | Fallback |
|---|---|
| The WebTestPilot artifact won't run locally (**it is public**, checked 11 Oct) | Use BookStack only, or reimplement its oracle idea as the "spec-given" condition, or switch the base to Judge (TOSEM, Q1) |
| Setting up and instrumenting several apps takes too long | RealWorld first. Add apps one at a time. CATTest is ready to use. |
| G1 gains are small or not significant | Still publishable as an empirical "when does parallelism pay off?" study (NIER). Report it honestly. |
| Token cost overruns | Pilot first, use tiered models, hard budget caps per run, cache unchanged observations |
| Auth and state pollution between workers | Separate test account per worker, DB snapshot reset between runs |
| The laptop limits N | N ≤ 8 locally. Rent a VM for a few days only for N = 16. |
| Someone publishes the same idea first | Weekly arXiv check. Our equal-budget evaluation stays a contribution even if a similar system appears. |
| Course AI-writing check | Group writes all submitted prose. Claude handles code, experiments, research design and reviews of drafts. |

---

## 11. The "10 papers" list: a correction to the earlier plan

The course requires **10 peer-reviewed papers from 2025–26 that are directly relevant**. Only the **base paper** must be Q1 or A*/A. Limiting all ten to Q1 journals made the earlier list weaker: it pulled in surveys and grey-literature reviews, which the rubric scores as "weakly related" and which give no empirical limitations to cite as evidence for a gap. Top SE work appears at A* conferences, so we mix conferences and journals.

Candidates (each must be verified: venue, year and full text read):
1. **WebTestPilot**, FSE 2026 (base)
2. Are Autonomous Web Agents Good Testers?, ISSTA 2025
3. Judge, TOSEM 2026
4. VUI testing via behavior-model-enhanced LLM agents (Elevate), TOSEM 2026
5. Scenario-Guided LLM-based Mobile App GUI Testing (ScenGen), DOI 10.1145/3816025 (ASE'26 journal-first, so verify the journal)
6. CATTest / CATJudge, EMNLP 2026 (verify it appears in the proceedings)
7. Why Do Multi-Agent LLM Systems Fail?, NeurIPS 2025
8. AutoPT, IEEE TIFS 2025
9. CVE-Bench, ICML 2025
10. MemoDroid, ASE 2025 (verify)
11. Sifting the Noise, ISSTA 2026 (verify)

Cite but do not count: Temac, WebRLED, WebTestBench, WebMAC, ParaGUI, the 2026 empirical study, AnyPoC, REBUG, and MARG (2024).

---

## 12. Constraints (answered 11 Oct 2026)
1. **Solo project.** The work division section says one person owns everything. Scope stays as planned, but the extra apps are the first thing to cut (§10).
2. **Phase 1 is due 17 Oct 2026**, with the aim of finishing early. The timeline in §8 is compressed to fit.
3. **Free start, paid later.** All LLM calls go through one provider-agnostic, OpenAI-compatible client, so changing models is a config change. Development and the pilot use free tiers (for example the Gemini or Groq free tiers, or OpenRouter free models). Local Ollama is a last resort: a 4-core CPU is too slow for agent loops. Once the pilot shows promise, the paper-grade runs move to paid APIs, using the same model in every condition. Free-tier rate limits mean the pilot runs N ≤ 4.
4. **Cloud VM:** rented only after the pilot shows a G1 effect at N ≤ 8 on the laptop.
