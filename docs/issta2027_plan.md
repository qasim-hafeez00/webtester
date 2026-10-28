# ISSTA 2027 submission plan (planning notes, not submission text)

Written 26 Oct 2026. Every fact below is checked against the source named next to it. The 2027 call for papers is not published yet (its research-papers page says "TBD"), so the rules come from the **ISSTA 2026 call** and must be checked again when the 2027 call is out (expected Nov–Dec 2026).

## 1. Venue facts

| Item | ISSTA 2027 | Source |
|---|---|---|
| Where, when | Singapore, 7–10 Sep 2027; PC co-chairs Dan Hao, Jacques Klein | conf.researchr.org/home/issta-2027 |
| Mandatory abstract | **Fri 8 Jan 2027**, AoE | conf.researchr.org/dates/issta-2027 |
| Full paper | **Mon 11 Jan 2027**, AoE | same |
| Author response | 22–25 Mar 2027 | same |
| Initial notification (incl. early reject) | 20 Apr 2027 | same |
| Major revision due | 20 May 2027 | same |
| Final notification | 17 Jun 2027 | same |
| Camera ready | 22 Jul 2027 | same |

Rules from the 2026 call (assumed for 2027 until its call is out):

| Rule | 2026 wording, summarised | What it means for us |
|---|---|---|
| Length | 18 pages for all text, figures **and appendix**; references unlimited; Data Availability section not counted. Over the limit = **desk reject** | Single column. About 7,500–9,000 words of body text with our tables and figures |
| Template | `\documentclass[acmsmall,screen,review,anonymous]{acmart}` (or ACM Word); numeric or author-year citations | Start the LaTeX skeleton from this exact line; formatting violations may be desk-rejected |
| Review | Double-anonymous. No names or affiliations, clean PDF metadata, own prior work cited in the third person | The repo, run IDs, key names, the course and the supervisor must not appear. Artifact via anonymous.4open.science |
| Data Availability | Required section before the references; anonymised data and code, or why not | We can share everything (harness, traces, labels, app setups); vendored BookStack files are CC BY 4.0 |
| Paper types | Research paper (importance, originality, soundness), Experience paper, Replicability study (tag in the title) | **Research paper** |
| Areas | One primary, optional secondary, from 8 areas | Primary **AI for Analysis and Testing**; secondary **Software Test Generation** |
| Review process | At least 3 reviewers + an area chair. Accept / Major Revision / Reject; a major revision comes with a list of required items, a "contract" | A revision means 4 weeks (20 Apr → 20 May) to run whatever the reviewers ask, so the pipeline must stay runnable after January |
| Generative AI | Allowed, but "must be fully disclosed", per the ACM authorship policy | Disclose: the harness's LLM; Claude for code, analysis and **the D45 labels**. The course rule (no AI prose) stays stricter, and the user writes every sentence |
| Prior/dual publication | Not published or under review elsewhere; plagiarism checks | The 4 Nov course paper must not appear in an archival venue; check that the course does not publish it. arXiv policy: check in the 2027 call |
| Acceptance rate | 2026: 210 of 888, about 24% (organisers' post, second-hand); 24–27% in earlier years | One in four. The paper must survive "is the evaluation convincing?" |

Reviewers of LLM-based testing papers increasingly check against the **SE guidelines for empirical studies involving LLMs** (Baltes et al., arXiv 2508.15503; llm-guidelines.org). Its eight points are: declare the LLM's role; report the model version and configuration; describe the tool architecture; publish prompts and interaction logs; validate with humans; **use an open LLM as a baseline**; use suitable baselines and metrics; and state limitations. We already cover 1–4 and 8. Points 5–7 are open (see §3).

## 2. Where the paper stands (26 Oct)

| Claim | Evidence now | Strength for ISSTA |
|---|---|---|
| G1 shared frontier cuts duplicate work | Duplicates −34% to −48% at equal tokens, p = 0.008, replicated in harness v1, v2 and v3 (Conduit). Sharing, not partitioning, drives it (B3v2 vs B3v2-local) | **Solid but small**: efficiency only. States are not significant inside B4; nothing extra is found (labelled, p = 0.42). Only one app |
| G3 inferred oracles find semantic faults | Conduit: 4 of 6 UI-reachable semantic faults across runs, implicit-only 0 (p = 0.008). **Held-out BookStack: 0 of 13** | **Weak as it stands**: positive only on the app it was designed on. v4's deterministic oracles are the answer, but they are not measured yet |
| G2 evidence gate raises precision | 69% → 74% (Conduit v3); BookStack 18% → 19% (the gate confirms wrong expectations perfectly). KPI ≥ 0.90 not met; recall loss 21% | **Weak.** The honest finding is that replay checks reproducibility, not correctness |
| Real bugs | 3 race defects (500 instead of 404), whitespace values, no email check, U1–U7 on Conduit (a demo app) | Useful, but not reported upstream and not acknowledged by any developer |
| Scale | 2 apps, 1 model (flash-lite), N = 4, n = 5, one laptop | **Below what ISSTA reviewers expect** (WebTestPilot: 4 apps, 100 bugs, several models) |
| Ground truth | Conduit seeded faults; BookStack injected faults; findings labelled by Claude (D45), user's blind 20% re-label pending | **Risky**: LLM-assigned labels will be questioned. Human validation is needed (guideline 5) |

**In short:** the system and the measurement pipeline are in place, and there is about one significant positive result (G1 duplicates) plus one negative held-out result. An ISSTA paper needs v4 to **work on apps it was not designed on**, measured at paper scale. That is November–December's job.

## 3. Experiments still needed

### 3.1 Decision first: what the paper claims (user decides, early Nov, after Night 4)
- **Option A (recommended if v4 holds out on PrestaShop):** the main contribution is *deterministic consistency oracles built from the agent's own run memory, plus an evidence gate*, for spec-free parallel LLM web testing. G1 becomes a supporting efficiency result. The v3 held-out failure becomes the motivating negative result: LLM-proposed checks test the effect of the agent's own action, and miss content that is wrong on arrival.
- **Option B (if v4 does not hold out):** an empirical study. *What do spec-free LLM web testers find, and why do they miss what they miss?* That means the G3 failure funnel across apps, the gate's reproducibility-vs-correctness finding, and parallel races that the gate under-reports. This fits ISSTA's "Empirical and User Studies" area. It is harder to get in, but honest.

### 3.2 Matrix (paper-grade, rented VM, paid API)
| Block | Apps | Conditions | Reps | Runs |
|---|---|---|---|---|
| Main | Conduit (dev), BookStack, PrestaShop, + 1 more benchmark app (Indico or InvoiceNinja) | B0 crawler, B3v2 (no oracles, no gate), B4 v4, B4det (deterministic oracles only), A-G1 (b4nog1); A-G2 is B4's raw candidates, so it costs nothing | **10** | 4 × 5 × 10 = 200 |
| External baseline | same 4 | one spec-free tool: WebCQ (ASE'26, artifact on Zenodo) or Crawljax (the AutoE2E reference). PinATA needs NL test cases, so it is no fair baseline | 10 | 40 |
| Second model | same 4 | B3v2 and B4 v4 with one **open-weight** model (guideline 6) | 5 | 40 |
| Scaling | BookStack | B4 v4 at N = 1, 2, 8 (N = 4 is in Main) | 5 | 15 |
| **Total** | | | | **about 295 runs** |

Cost: each LLM run is capped at 190k tokens, so about 50M tokens in all (check the model's current price before ordering). Time: about 20 minutes per run including gate and reset. That is about 100 machine-hours, or roughly 5 days on 2 VMs, one app per VM (I19).

**Why n = 10:** with n = 5 the smallest Mann-Whitney p is 0.008 and power is low, while many SE papers use 10+ reps for randomised tools. Keep the D19 statistics: exact Mann-Whitney U and Vargha-Delaney Â12.

### 3.3 Other work the evaluation needs
1. **Human ground truth:**
   - the user labels the blind sample, and ideally all B4 findings;
   - a second human rater (a classmate, or the supervisor) labels a 20–30% sample, so that Cohen's κ is between humans;
   - Claude's labels are reported as a third rater.
2. **Upstream bug reports:** file the real bugs on BookStack, PrestaShop and RealWorld (Conduit) issue trackers in **mid-November**. Acknowledgements take weeks, and "N confirmed by developers" is one of the strongest lines an ISSTA paper can have. Reports go out under the user's own account, so the user files them, and anonymity needs care: refer to them in the paper as "reported" and anonymise the links.
3. **Fault realism:**
   - BookStack's faults are client-side injected, and reviewers will ask whether they reflect real bugs. Report the injected-fault results and the real bugs separately.
   - The WebTestPilot benchmark's "23 replicated real GitHub bugs" (fact sheet 01, §5.3.4) are worth checking as an extra real-bug set.
4. **Cost metrics** (offline from the traces, already planned): tokens per confirmed finding, time to first confirmed finding, transition coverage.

## 4. Acceptance KPIs (what has to be true by 15 Dec to submit)

A **go** on 5 Jan needs K1, K2, K3 and K7. Without K1 the paper is Option B.

| # | KPI | Threshold | Now |
|---|---|---|---|
| K1 | Held-out detection | B4 v4 detects **≥ 30% of the reachable injected faults** on each held-out app, vs B0 and B3v2 (p < 0.05). Exact targets are pre-registered in D51 before the PrestaShop runs | 0% (v3) |
| K2 | Precision of what is reported | Gate-confirmed precision **≥ 0.80** pooled over the held-out apps, reported with and without the judge | 19–74% |
| K3 | Real bugs | **≥ 5 previously unknown bugs** in the real apps, **≥ 2 acknowledged** by maintainers | 0 reported |
| K4 | G1 efficiency | Duplicate actions **−30%** at equal tokens on ≥ 3 apps | met on Conduit only |
| K5 | Gate cost and loss | Gate ≤ 25% of run time and tokens; recall loss ≤ 10 points | cost met; loss 21% |
| K6 | Generality | Same direction (Â12 on the same side) with the open model | not run |
| K7 | Baseline | B4 v4 beats the external spec-free baseline on faults found at equal budget | not run |
| K8 | Human labels | Human-human κ ≥ 0.6 on the labelled sample | not run |

## 5. Paper outline and page budget (18 pages, acmsmall)

| Section | Pages | Content (the user writes all of it; Claude supplies numbers, tables, figures and reviews) |
|---|---|---|
| Abstract | — | about 200 words: problem, approach, 3–4 headline numbers |
| 1 Introduction | 2 | The three gaps with cited evidence (PinATA's specificity, WebTestPilot's need for a spec, MAST); contributions as 3–4 bullets; headline results |
| 2 Motivating example | 1 | One real case: a phantom item, or F07's offered-but-refused Edit. Why an LLM-proposed check misses it, and how a consistency rule plus the gate catches it |
| 3 Approach | 4.5 | Overview figure; workers, shared frontier, run memory and state graph; the consistency oracles (rule table with tiers T1–T3); the evidence gate (minimal-suffix replay, k = 3) and judge |
| 4 Evaluation design | 2.5 | RQs; subject table (LOC, stars, faults); conditions and equal-budget rule; metrics; statistics; labelling protocol; run-validity rules |
| 5 Results | 5 | RQ1 effectiveness (seeded/injected and real bugs, dev vs held-out); RQ2 reliability (precision, gate cost and loss); RQ3 parallel exploration (G1); RQ4 ablations; RQ5 generality (second model, N) |
| 6 Discussion | 1 | Lessons: LLM checks test effects, not arrival content; replay proves reproducibility, not correctness; the gate under-reports parallel races |
| 7 Threats | 1 | From ledger §8: development on Conduit, injected faults, one laptop vs VM, labels, the judge |
| 8 Related work | 1.5 | LLM web/GUI testing (WebTestPilot, PinATA, AutoE2E, SpecOps); multi-agent exploration (WebCQ, MAdroid, GraphDroid); oracles (Genie, Kea, Odin, BACScan, InputBlaster) |
| 9 Conclusion | 0.3 | |
| Data Availability | not counted | Anonymous artifact link |
| References | unlimited | |

About 0.5 pages are spare for figures. Detail that does not fit goes into the artifact, not an appendix, because the appendix counts toward the 18 pages.

## 6. Timeline

| Dates | Work | Who |
|---|---|---|
| 26–28 Oct | Resweeps, fix or demote rules, **lock v4**, D51 targets | Claude runs (user's request), Claude fixes |
| 28–31 Oct | Nights 3–4 (Conduit, BookStack, PrestaShop) | user |
| 1–4 Nov | Course paper | user |
| 5–9 Nov | **Framing decision (A or B)** from the PrestaShop result; the user writes a one-page skeleton (title, contributions, RQs); check the 2027 call when it appears | user, Claude reviews |
| 5–15 Nov | Build: 4th app, external baseline, open-model provider (a new code path; key/fallback logic stays untouched), VM setup, offline cost metrics | Claude builds, user approves |
| mid-Nov | File upstream bug reports; recruit the second rater | user |
| 16 Nov–13 Dec | Paper-grade matrix (§3.2) | user runs |
| from 16 Nov | User drafts §3 Approach and §4 Design (stable after the lock) | user |
| 1–20 Dec | Labelling (user, second rater), κ | user + rater |
| 14–24 Dec | Tables, figures, statistics; user drafts §5 Results | Claude analysis, user writes |
| 26 Dec–4 Jan | Full draft; Intro, Related work, Threats; Claude reviews against the ISSTA criteria (importance, originality, soundness, verifiability, presentation) | user, Claude reviews |
| **5 Jan** | **Go/no-go** against §4 | user |
| by **8 Jan** | HotCRP: title, abstract, areas, conflicts | user |
| 9–11 Jan | Anonymise the PDF and its metadata; artifact on anonymous.4open.science; Data Availability; page check (18 pp); GenAI disclosure | user, Claude checks |
| **11 Jan** | Submit (AoE) | user |
| 13 Jan | Fallback: ICST 2027 NIER if no-go | user |
| 22–25 Mar | Author response | user |
| 20 Apr → 20 May | Major revision window: the pipeline must stay runnable | both |

## 7. Writing advice for ISSTA
- **Lead with a measured claim, not the system:** "at equal token budget, X finds Y of Z held-out faults where the best spec-free baseline finds W".
- **Answer every RQ the same way:** setup → table/figure → statistic with effect size → one-sentence answer in bold.
- **Make negative results part of the contribution.** The v3 held-out failure, explained, is more convincing than a hidden one.
- **Show fairness explicitly:** equal tokens, same model, same reset, invalid runs listed with reasons (we already have all of this).
- **Publish reproducibility evidence with the paper:** prompts, model ID, temperature, traces and labels go in the artifact (guidelines 2–4).
- **Avoid novelty overclaims:** no "first parallel web tester" (MARG) and no "first LLM oracle". State what is new: deterministic, spec-free cross-view consistency rules reproduced by a replay gate.
