# Harness v5 plan: every gap, what to add, how to measure it (D58)

Status: 28 Oct 2026. Built from two reviews of `docs/fault_families.md` (ChatGPT and Claude, pasted by the
user on 28 Oct; tagged **[G]** and **[C]** below) and from our own reading of the code and logs (**[O]**).
**D59 (28 Oct, later):** a third review of the source and both docs (pasted by the user, tagged **[X]**) is
taken in section 10; the evaluation framework is section 11; the plan to build a rule for every coverable
family is section 12; the code done with D59 is section 13. `capture_evidence` is **on** in both configs
from D59.
**D60 (28 Oct, evening):** the user asked to build every phase and a rule for every family; section 14 says
what exists now, how far it is tested, and what is still setup, protocol or the user's work.
**D61 (29 Oct):** an audit of every item, family and metric, with every gap built and tested; section 15 replaces
section 14's status column. **D62 (29 Oct):** the road to the v5.0 lock, with owners and commands, is `docs/v5_lock_checklist.md`.
Each item has a verdict: **agree**, **partly** (taken in a changed form), **defer** (after the v5.1 lock),
or **no** (with the reason). This plan replaces the order of work in `fault_families.md` section 9.

## 1. The claim v5 is built for

Not "catch every error". The claim is: **high recall over a defined, observable fault population, with
measured precision and stated exclusions.** Concretely, for each app:

- **oracle-conditioned recall**: faults found / reachable faults in families a spec-free check can see
  (`fault_families.md` statuses covered, partial, coverable);
- **total recall**: faults found / all reachable faults, spec families included (the ceiling stays visible);
- **precision on distinct issues** (rule x page template x entity kind), and per raw finding;
- the **recall funnel** (section 3), so every miss has a stage;
- false alarms per run and per 100 checks on clean apps, with a confidence bound, not a point value.

Both reviewers agree, and we agree: the remaining recall is mostly lost **before** any rule runs (the agent
does not reach the state, cannot make a write succeed, the page facts are not extracted, the gate loses
it), not for want of more families. So v5 works stage by stage. New rules come after the stage that
starves them is fixed.

## 2. Where v5 starts (facts, 28 Oct)

| Part | What exists | File |
|---|---|---|
| Exploration | LLM workers with a shared frontier (G1), harness travel by URL, page naming; B0 crawler | `frontier.py`, `policies.py`, `crawler.py` |
| State | abstract state graph: page = route shape, state = route shape + text-free skeleton; transitions with who acted, data verb, signals | `stategraph.py`, `state.py` |
| Memory | action ledger with outcome status, entities, list snapshots per page | `memory.py` |
| Oracles | 32 deterministic rules (R01-R19, I-*, G1-G3) + R15 (LLM-cited, T3), and R51, R57 since D58; R43, R64, R26 since D59 (`norms.py`); probes capped per step and per run | `consistency.py` (1,940 lines), `norms.py` |
| Check log (D59) | every rule on every page records detected, exercised, unarmed, suppressed (guard), capped, unobservable or inconclusive; `checks.jsonl` per run | `checks.py`, hooks in `consistency.py` |
| Evaluation (D59) | offline: recall (total, conditioned, per family and primitive), precision (finding, distinct issue, tier, rule, gated, judged), funnel, clean-app false alarms with exact intervals, confidence score, comparisons with Holm over a primary family | `evaluate.py`, `stats.py`, `families.py` |
| Evidence | statuses of same-origin writes, 5xx, JS errors, failed requests; network timeline with JSON bodies and sent data, transient messages (R57, R51), behind `capture_evidence` (**on since D59**) | `browser.py`, `evidence.py` |
| Gate | replay from the worker's step log in a fresh context restored with cookies + local storage, data reset before every replay, windows up to the full prefix, k = 3; judge advisory | `gate.py` |
| Offline re-check | `resweep` replays recorded runs with the current oracles, no LLM | `runner.py`, `scripts/resweep_v5.sh` |
| Labels | fault id, `new:` (real, unseeded), `U#` (upstream), `fp`; Claude labels, user blind-checks 20% (D45) | `logs/experiments/finding_labels.toml` |
| Numbers | v5 resweep (complete): BookStack median 6/13 reachable, precision 95%, clean false alarms 0.6/run; Conduit median 6/8 (F08 now found by R07c), precision 99%, clean false alarms 0.4/run. Gate recall loss 21% in v3, 2.5-5% in v4 (Night 3) | `logs/experiments/v5dev/` |

## 3. Instrument the recall funnel first

Every seeded fault, in every run, gets the first stage it failed:

| Stage | Question | How it is measured |
|---|---|---|
| S1 reached | Did a worker reach the page or flow where the fault lives? | state graph vs the fault's route (catalogue field) |
| S2 triggered | Did the fault fire? | exposure markers: BookStack client faults log `[wt-fault]` already; **Conduit's server-side faults need an exposure log line** (new) |
| S3 observed | Is the wrong value or effect in what the harness captured? | facts, network timeline, messages of the step after exposure |
| S4 armed | Did a rule of the fault's family evaluate that page? | **check-outcome log** (below) |
| S5 flagged | Did it raise a violation? | trace signals |
| S6 confirmed | Did the gate reproduce it? | gate report |
| S7 matched | Was it labelled with this fault? | labels |

**Check-outcome log** [G][C], new in `consistency.py`: each rule, on each page it considers, records one
of: `detected`, `exercised` (ran, no violation), `unarmed:one-cue`, `suppressed:<guard>`, `capped`
(probe budget used up), `unobservable` (the evidence it needs is not captured), `inconclusive`. Written
per run as `checks.jsonl`. An unexecuted check is never counted as a pass. This also gives the arm rate per
primitive and the recall cost of each guard (`fault_families.md` 5.2).

Funnel numbers are computed offline by a script from the trace, the gate report, the labels and the
catalogue, for every development run. Rough expectation, to be measured: five stages at 0.7 each give 0.17,
so the stage with the lowest pass rate is where the next week of work goes.

## 4. Gaps, verdicts and what v5 adds

### 4.1 Reach: getting to the state, with data, as the right user

| ID | Gap | Src | Verdict | What v5 adds | Metric | Phase |
|---|---|---|---|---|---|---|
| R1 | Writes never succeed on unfamiliar forms (cross-field rules, unique fields, dependent selects, date pickers, rich-text editors, file types) | G C | agree | **Input profiles** per field from declared attributes (`type`, `min/max/step`, `pattern`, `maxlength`, `required`, `accept`), label words and the app's own validation messages; retry once with the message's hint; unique values by a run-unique suffix; date pickers via the underlying input; rich text via `contenteditable` fill; small generated files for `accept` | **write-success rate per form kind** (accepted / attempted) | 2 |
| R2 | No data, so list rules never arm (pagination, sort, facets, caps need 2+ items or more than a page) | C | agree | **Seeding step**: after the first accepted create of a kind, the harness (not the LLM) replays that create flow to reach 0, 1, 2 and page-size + 1 items, with distinct names; on dev apps also seed by fixture | arm rate of list rules | 2 |
| R3 | Auth and roles: one role per run; admin areas unexplored; M7 needs a second account in the gate | G C | agree | **Accounts per role** in the config (`[[app.accounts]]` with a role name); workers spread over roles; the gate replays with the finding's account and, for M7 rules, a second session (D50 rejected this for R13; revisited here); CAPTCHA, 2FA and SSO handled by a config-provided storage state, not solved | **routes reachable per role** (state graph) | 2 |
| R4 | State abstraction merges states that differ (role, active context, selected record, draft) | G | partly | Add **role and active context** to `state_id` (both cheap and known); refine a state only when an action or rule distinguishes two of its visits; not every dimension (state explosion) | states per run; refinements made | 2 |
| R5 | No coverage ledger: what was not tested is unknown | G C | agree | `coverage.json` per run: routes x URL-state shapes, controls activated / seen, transitions, roles, input classes tried per field kind, **oracle arm coverage** from the check-outcome log | per run | 0-2 |
| R6 | Interaction modalities: hover-only controls, keyboard, context menus, native dialogs, shadow DOM, iframes, virtualised lists | G C | partly | Observe **open shadow roots and same-origin iframes**; record and accept native `alert/confirm/prompt` (logged, never left blocking); hover a row before observing when its controls appear on hover; scroll lists to the end once. Keyboard-only, context menus, long press: stated as **coverage gaps**, not tested | unsupported-modality count per app | 2 |
| R7 | Blind spots beyond the E3 side crawl | C | agree | Seed the frontier from `sitemap.xml`, `robots.txt` allow lines, RSS/Atom links and same-origin GET URLs seen in the network timeline | routes added by seeding | 2 |
| R8 | Destructive actions: avoided (faults missed) or done early (session lost) | C G | agree | **Order**: destructive verbs (delete, logout, close account) only on items the run created, and late in a worker's budget; logout last; data reset already happens between gate replays | session-loss events per run | 2 |
| R9 | Cookie walls, newsletter pop-ups, chat widgets | C | agree, low | Dismiss by known button texts and close icons; logged as `dismissed` | dismissals | 2 |
| R10 | Budget spent evenly; no recall-vs-budget view | C G | agree | Frontier priority adds **under-exercised primitive** and **unarmed rule** terms (from the check-outcome log); recall reported as a curve over steps, tokens and minutes | recall at 25/50/100% budget | 3 |
| R11 | Sequence faults (create, move, filter, inline edit, back) | G | partly | Bounded metamorphic **sequences of length 2-3** generated from the state graph for DB9, HI3, DB12; longer only after a dependency was seen | sequences run | defer (v5.1) |
| R12 | Unfired event handlers (div with onclick) | C | agree, metric | CDP `DOMDebugger.getEventListeners` on visited pages: fraction of elements with listeners that were activated. Measured only (the cursor-pointer heuristic, D43, already takes most) | handler coverage | 3 |
| R13 | When to stop | C | defer | Chromium JS coverage plateau as a stop signal: measured as a metric in v5.1, not used to stop | | defer |
| O-R1 [O] | D55's exploration items still pending: E1 revisit budget, E2 shorter notes, E3 unvisited entity pages | O | agree | Finish and pilot them before the v5.0 lock (BS02-04, BS12, BS15, BS17-18 depend on them) | faults reached (S1) | 1 |

### 4.2 Observe: capturing the evidence

| ID | Gap | Src | Verdict | What v5 adds | Metric | Phase |
|---|---|---|---|---|---|---|
| O1 | Response bodies not kept | C G | agree, **done** | `evidence.py` + `browser.py`: network timeline (all same-origin xhr/fetch/document responses), JSON bodies (200 KB cap), what each write sent; `capture_evidence = true` turns it on | bodies kept / JSON responses | 0 |
| O2 | Toasts and flashes are gone before the audit | C | agree, **done** | MutationObserver init script records text that appears in alert, status, live-region and toast-like elements, from page start; drained per step | messages per step | 0 |
| O3 | Fixed waits: false alarms on slow apps, wasted time on fast ones | C | agree | **Poll to a deadline** for intent-effect checks (`_verify_pending`, fresh-tab views): re-read until the effect appears or 8 s; record settle time per check; flag only after the deadline | settle time distribution; findings that needed > 3 s | 1 |
| O4 | Console and network noise (third-party scripts, dev overlays, hot-reload sockets) | C | partly | Same-origin filter exists (scope gate); add a list of dev-mode noise patterns; record build mode (dev/prod) per app | console signals per run on clean apps | 2 |
| O5 | Client-only apps have no server to cross-check | C | agree | Read local storage / IndexedDB of the app's origin after writes and compare with the DOM (the PBFDroid idea with storage as the model) | apps where it arms | 4 |
| O6 | Extraction is a single point of failure (English cue words, number formats, shadow DOM, pseudo-elements, virtualised lists, entities with no link) | C | agree, scaled | (a) **Number parser** for `1.234,56`, `1,00,000`, `(12.00)`, `1.2k`, Eastern Arabic digits; (b) cue words as data files per language (English first, others listed as a limit); (c) entity keys fall back to the heading + route when there is no link; (d) an **extraction benchmark of ~60 hand-labelled pages** (not 200-300: time) from dev apps, clean apps and synthetic pages, with fact-level precision and recall | fact precision/recall; arm rate per primitive | 2-3 |
| O7 | Free declared specs unused | C | agree | JSON-LD and OpenGraph (price, availability, name) vs the visible values; `<title>` vs `h1`; sitemap URLs resolve; RSS items vs the latest list; OpenAPI/GraphQL introspection read when served (types, enums, ranges as declared constraints) | facts from declared sources | 3-4 |
| O8 | Downloads and file contents (exports, print views) | G | agree | Capture downloads; parse CSV; text of PDFs later (R37) | | 4 |
| O9 | Mail | G | agree, dev only | Mailpit in our own deployments (BookStack mail now goes to the log driver, I42) | | 4 |
| O10 | Backend or provider traces | G | no (core) | Out of the generic core (EN8, EN9); only as an adapter (section 6) | | |
| O11 | LLM to annotate typed facts for the deterministic checks (never to judge) | C | defer | An ablation for v5.1 (`b4det` vs `b4det+annot`); annotations cached per page so gate replays see the same facts | arm-rate gain vs token cost | defer |

### 4.3 Judge: oracle validity and guards

| ID | Gap | Src | Verdict | What v5 adds | Phase |
|---|---|---|---|---|---|
| J1 | 'Universal identities' that are really conventions | G | agree, **done** | `fault_families.md` 5.1 is now an invariant library with classes S (strong), C (conditional), K (needs a contract) and per-entry preconditions | 0 |
| J2 | Global guards may hide real faults | G | agree, **done in the design** | 5.2 revised: volatile nodes kept for temporal rules; one-cue checks logged as unarmed; persistence required only for persistence rules; each guard logs what it suppressed (code in phase 1 with the check-outcome log) | 0-1 |
| J3 | Benign words ('estimated', 'sample data', 'prices exclude tax', 'may take a few minutes') | C | agree | A benign-word list read next to the element; a rule on that element drops one tier | 1 |
| J4 | Tiers set by judgment | C G | agree, **done** | Tier semantics now defined in `fault_families.md` section 3; new rules start at T2; a rule's tier comes from its measured precision on the development apps (D55); two independent rules agreeing on one entity ranks a finding higher | 0 |
| J5 | Environment replay compared raw text | G | agree, **done in the design** | R71 compares normalised values per axis; a fake clock moves only the browser's time | 0 |
| J6 | Fault injection can create false alarms | G | agree | Every M11 probe records: did the request reach the server, did the server answer (status, body), did the response reach the page, what changed after, did the app recover. A lost response and a request refused before the server are different cases | 4 |
| J7 | Mixed specification, implementation and measured status | G | agree, **done** | `fault_families.md` status = 'a check can exist'; the family tracker (section 7) holds built / fixture-tested / seeded-tested / measured recall | 0 |

### 4.4 Confirm: the gate

| ID | Gap | Src | Verdict | What v5 adds | Phase |
|---|---|---|---|---|---|
| C1 | Fresh context loses tab state: storage state restores cookies and local storage, **not session storage** | G O | agree | Save session storage per origin with each step record and restore it by an init script in gate replays | 1 |
| C2 | The agent's own odd data (emoji, `<`, long strings) pollutes later pages | C | agree | Findings whose subject or evidence contains a value the run typed as a probe are labelled `harness:` candidates unless the rule is about that value (R12, FM8); typed values come from a seeded generator | 1 |
| C3 | Harness failures read as app bugs (429, CSRF expiry 419, session timeout, slow answers read as hangs) | C | agree | **Harness-health check** before a finding is kept: a 429/419, a CSRF error text, or an unexpected login page in the step or its replay marks the finding `harness-suspect` (reported apart) | 1 |
| C4 | Flakiness | C G | agree | k/n already reported; add fixed seeds for generated values; freeze the browser clock in replays of time-dependent rules | 1 |
| C5 | Minimal traces | C | agree | ddmin over the step prefix in the gate (in the ISSTA plan already) | 3 |
| C6 [O] | Gate recall loss 21% (ISSTA K5): findings unverified because the gate's time ran out or an element was missing after the reset | O | agree | Report unverified apart (never as rejected); raise the gate's time for findings of T1 rules; replay prefix steps by URL when the element is gone and the step was navigation; measure loss per cause | 1 |

### 4.5 Evaluation

| ID | Gap | Src | Verdict | What v5 adds | Phase |
|---|---|---|---|---|---|
| E1 | Recall stages | C G | agree | The funnel (section 3) | 0-1 |
| E2 | Unexecuted checks counted as passes | G | agree | Check outcomes (section 3) | 1 |
| E3 | Upstream bugs counted as false alarms; unlisted real bugs as false positives; one fault, many findings | C | agree | Label set extended: fault id, `new:`, `U#`, `fp`, **`harness:`**; precision reported on **distinct issues** (rule x page template x entity kind) and per finding; an upstream bug on a clean app is not a false alarm | 1 |
| E4 | Two clean apps bound the false-alarm rate badly (0 in n runs gives only about 3/n, rule of three) | C | agree, scaled | **Clean corpus** of 10-12 apps by the v5.1 lock, used only for false alarms: several RealWorld front-ends (React, Angular, Vue, Svelte) on one API (cheap variety), Parabank, Timeoff, Gadael, 4gaBoards, Agilefant, Juice Shop's non-security pages, one large app. 20-30 is the goal for the paper, not for v5.1 | 3 |
| E5 | Faults written by the rule authors overfit | C G | agree | (a) **Real historical faults**: 8-15 fixed bugs from BookStack's and the RealWorld implementations' histories, run on the pre-fix version, ground truth = the fix; (b) **two variants per family** for synthetic faults, the second written by the user without looking at the rule; (c) faults still written before their rule | 3 |
| E6 | Contamination: public apps known to the LLM; the reviewer chats could recall held-out bug lists | C | agree | Disclosed as a threat; a **rebranded BookStack** (names, strings, colours changed) as a control run; PrestaShop's and CATTest's fault lists stay unread (I50) | 3 |
| E7 | Variance | C | agree | n = 5 per condition (already); mean ± sd; bootstrap over apps for intervals | 5 |
| E8 | Severity | C | partly | A severity field (data loss or money, function, display) in the labels; severity-weighted recall as a secondary number | 3 |
| E9 | Thresholds tuned after seeing results | C G | agree | All tolerances, waits, caps and tiers frozen and listed in D51 before any held-out run | 5 |
| E10 | Explorer and detector not separated | G | agree, exists | `resweep` already runs the detector on recorded trails without the explorer; v5 reports both: detector-only recall on recorded evidence, and end-to-end | 1 |

### 4.6 Safety and cleanup

| ID | Gap | Src | Verdict | What v5 adds | Phase |
|---|---|---|---|---|---|
| S1 | No execution modes | G | agree | `[run] mode = "read-only" \| "reversible" \| "controlled"` enforced by the executor (`browser.execute`), not the prompt: read-only refuses non-GET writes; reversible allows writes only on records the run created (mutation ledger) and checks cleanup; **controlled** (our own deployments only) also allows M11 fault injection, R60 constraint stripping, RC9 storage corruption, SA7 credential changes. Scope gate and blocked texts stay. Development and held-out apps run in `controlled`, since they are ours and reset | 2 |
| S2 | No emergency stop | G | agree | A stop file checked each step; the run ends cleanly with its trace | 2 |

### 4.7 Scope

| ID | Gap | Src | Verdict | What v5 adds |
|---|---|---|---|---|
| A1 | 'All kinds of apps' | G | agree | Claim scoped to **web apps through a browser**. A general core (exploration, state, evidence, generic invariants, metamorphic checks, gate, reports) plus **adapters**, each stating the observations it needs, the checks it adds, how it confirms, and what stays out: accessibility (axe), visual (vision model), API contracts (OpenAPI), security, performance, media, files, external providers, native mobile/desktop (out) |
| A2 | Diff mode against a previous run | C | no | A product feature, not a research need |
| A3 | Inconsistencies in `fault_families.md` (stale 13 app types, tiers undefined, 'universal identities', guards, raw-text replay, mixed statuses) | G | agree, **done** |

### 4.8 Our own observations [O]

| ID | Observation | What v5 does | Phase |
|---|---|---|---|
| O-1 | `consistency.py` is one 1,940-line file; 26 more rules would make it unmanageable | New rules go in their own modules (`evidence.py` is the first), called from the Sweeper; `consistency.py` is split (facts, rules, probes) only after the v5.0 lock, so the v4/v5 resweep comparison stays exact | 1 / after 5.0 |
| O-2 | Every worker has the same role; the configs have one account template | R3 | 2 |
| O-3 | Verbs and cue words are English word lists (`memory.py`), a documented limit | O6 (b): word lists as data, per language | 2 |
| O-4 | Probe caps (6 mutation forms, 4 toggle probes, 6 access probes per run) are fixed by judgment | Cap hits logged as `capped`; caps re-set from the funnel, then frozen (E9) | 1 |
| O-5 | Locale and viewport fixed (`en-US`, 1280 x 900) | M10 replay axes (R71) | 4 |
| O-6 | Conduit's server faults leave no exposure record | Add a log line to each Conduit fault (S2 of the funnel) | 0 |
| O-7 | D55 left-overs. BookStack: R08 on a renamed or permission-saved shelf (0.4/run), R09 'Recently Viewed' read as an item (0.2/run). Conduit: R09 reading the 'Post Comment' button as a list item; I-delete unable to tell apart two comment cards whose only text is author and date | Fix with the v5.0 changes: R09 ignores form controls inside a card; I-delete keys a card by its position among identical cards, or abstains when two cards match | 1 |

## 5. New checks, ordered by the stage they serve

The rules of `fault_families.md` 6.3 are built in waves. A wave starts only when the funnel shows that its
inputs arrive (pages reached, writes accepted, evidence captured).

| Wave | Rules | Needs first | Dev apps where they can be tested |
|---|---|---|---|
| W0 (done) | R57 payload (RT5), R51 success-and-error (FB2) | O1, O2 | Conduit (JSON API), BookStack (flash messages) |
| W1, pre-lock | R62 address replay, R63 address probes, R53 cancel probe, R68 inverse relations, R73 history ledger, R64 control state, R71 time-zone axis only | check-outcome log | Conduit (favourites, follows), BookStack (tags, audit log, delete confirmations) |
| W2 | R20 cross-view registry, R21a/b edit round trip, R57 payload-vs-page (DB11), R50 false failure, R52 rollback (without injection), R55 bulk ledger | R1 input profiles, R2 seeding | Conduit, BookStack, Parabank |
| W3 | R22, R32-R36, R40, R41, identity library (S entries) | R2 seeding, Parabank and Timeoff running | Parabank, Timeoff |
| W4 | M10 other axes (browsers, width, locale, clock), M11 injection (R50 abort probe, R52, CC1 delay), M13 R60, M14 R65/R74/R75, R67 contexts | S1 `controlled` mode, R3 second account | all dev apps; synthetic pages for media and canvas |

## 6. Phases and dates

| Phase | Dates | Content | Exit criterion |
|---|---|---|---|
| **0** | 28-30 Oct | Finish the Conduit resweep (I52) and label it; evidence layer (done, flag off); `fault_families.md` fixes (done); funnel script; Conduit exposure log (O-6); family tracker (section 7) | resweep labelled; funnel numbers for the 10 Night 3 b4 runs |
| **1** | 30 Oct-2 Nov | Check-outcome log and guard suppression log; `capture_evidence` on and resweep with it; O3 poll-to-deadline; C1 session storage; C2, C3 harness-health; C6 gate loss; J3 benign words; E3 label set; O-7 left-overs; D55 E1-E3 pilots; wave W1 | **v5.0 lock**: on both dev apps, recall not below the v5 resweep, precision ≥ 0.90 per finding, clean false alarms ≤ 0.5/run. Night 4 (Conduit, BookStack, PrestaShop held-out per D51); course numbers from v5.0 (submission 4 Nov) |
| **2** | 5-15 Nov | Reach: R1 input profiles, R2 seeding, R3 roles + second session in the gate, R4 state dims, R6 modalities, R7 seeding from sitemap/RSS/network, R8 ordering, R9 pop-ups; S1 modes, S2 stop; O4, O6 (a)-(c) | write-success rate ≥ 0.8 on dev forms; routes per role reported; no loss on dev recall |
| **3** | 10-25 Nov | Evaluation set: clean corpus (E4), real historical faults (E5a), second-variant faults (E5b), rebranded BookStack (E6), extraction benchmark (O6 d), severity (E8); waves W2-W3; R10 budget priority; R12 handler coverage; C5 ddmin | clean false alarms per 100 checks with a bound; funnel per family |
| **4** | 20-30 Nov | Wave W4; O5 storage model; O7 declared sources; O8, O9 | each new rule at its measured tier |
| **5** | 30 Nov | **v5.1 lock** for the paper: thresholds frozen in D51 (E9); then December experiments: held-out apps (PrestaShop, InvoiceNinja, Indico, a CATTest subset with category limits pre-registered), n = 5, bootstrap over apps (E7) | ISSTA KPIs K1-K8 measured |

Dates are targets. If phase 1 slips, the v5.0 lock keeps only what is measured by then, and the rest moves
to v5.1. Nothing unmeasured goes into a locked version.

## 7. Family tracker

`docs/family_tracker.toml` (**built with D59**, generated by `python -m webtester families --write` from
`fault_families.md` and the code): one entry per family with its `status` (as in the file), the rules it names,
which of them are `built` (read from the code, never typed by hand), the rules still `todo` and their `waves`,
its primitives and its development faults. Measured recall and precision per family come from
`python -m webtester evaluate` (`recall.by_family`, `precision.by_rule`) and are copied in per lock. The tally
in `fault_families.md` stays the specification view; the tracker is the implementation view, so a family never
looks covered on paper before it is.

## 8. What is not taken

| Suggestion | Why not |
|---|---|
| Claiming recall over 'all possible errors' | the spec ceiling (`fault_families.md` 7) |
| 200-300 labelled extraction pages | time; 60 pages first, more if the fact recall is the weakest stage |
| 20-30 clean apps before the v5.1 lock | 10-12 first; the paper states the bound it gets |
| Diff mode against an earlier run | a product feature |
| Backend traces, provider reconciliation in the core | need instrumentation; adapters only |
| A vision model for canvas and layout | out of scope (RC6); geometry and hashes (M14) first |

## 9. Code done with this plan (D58)

- `src/webtester/evidence.py` (new): `MSG_JS` (transient-message observer), R57 `rule_payload`, R51
  `rule_messages`.
- `src/webtester/browser.py`: network timeline `net` with JSON bodies (`_record`, `_grab_body`,
  `flush_bodies`, `net_mark`, `net_since`), sent data of writes, `drain_messages`; all inert unless
  `capture_evidence`.
- `src/webtester/config.py`: `RunConfig.capture_evidence = False`.
- `src/webtester/consistency.py`: the Sweeper takes each step's network window and messages and runs R57
  and R51 (`_evidence`); tiers R51, R57 = T2.
- `tests/test_d58_evidence.py`: 9 tests (pure rules; a real browser session with capture on and off).
  Full suite: 102 passed, 4 skipped.
- To turn it on after the Conduit resweep ends: `[run] capture_evidence = true` in both configs, then
  resweep the Night 3 runs with it (phase 1) to measure R57 and R51 before they count. **Turned on with D59**
  (both configs); the resweep with it is still to run.

## 10. Third review (D59, [X])

A review of the source code and of this plan, pasted by the user on 28 Oct. Its framing agrees with section
1 (high recall over an observable fault population, measured precision, the spec ceiling as a stated
limit) and with section 3 (most recall is lost before any rule runs). Items new to this plan get an X id.

| ID | Gap (reviewer's item) | Verdict | What v5 adds | Metric | Phase |
|---|---|---|---|---|---|
| X1 | `OBSERVE_JS` keeps the first `max_elements = 80` in DOM order and never scrolls: controls below the cap are invisible to the LLM and the crawler; no open shadow roots or same-origin iframes (item 1) | agree | Scroll to the end once per new state; **rank elements** before the cap: never activated in this state (action ledger) first, then DOM order; pierce open shadow roots and same-origin iframes (merges R6) | controls seen vs activated per state; elements dropped by the cap | 2 |
| X2 | States that depend on more than the URL (open modal, draft, selected record) are restored by URL only; `StateGraph.path()` exists but is unused for restoring (item 2) | agree | **Stateful travel**: replay the shortest recorded action path from the nearest URL checkpoint, restoring cookies, local storage and session storage (C1) first; URL travel stays the fallback | travel success rate; states reached only by path replay | 2 |
| X3 | Parallel workers share one backend and contaminate each other's data: false R09/G2 alarms and missed bugs (item 3) | partly | Workers already have separate accounts, and G2 explains changes with any worker's events. Add a **per-worker value namespace** (typed values carry `w{i}-` plus the run suffix) and R09 on shared lists explained by any worker's write; for N >= 8, one app instance per worker group restored from a snapshot (VM phase) | false alarms explained by another worker's write (labelled `harness:`) | 2 / VM |
| X4 | All workers are the same explorer; a real multi-agent design specialises roles (item 5) | partly | Roles: **explorer** (LLM), **adversarial prober** (LLM prompt for input classes and boundary flows, with the R16/R17/R63 budgets), **role-switcher** (LLM worker on a second account, R3); **data-seeder** (harness, not LLM: R2), **verifier** (the gate, exists), **triage** (offline clustering, D59 evaluator). New condition **B5** = B4 with roles, same budget: an extension of G1 (does specialisation beat N identical explorers?) | B5 vs B4: faults found, states, write success, duplicate rate | 2-3 |
| X5 | No app profile: every rule runs everywhere, goals and scheduling ignore the workflow primitives (item 6) | agree, guarded | **App profile step (P1)**: after about 10 pages the LLM names the app type and the primitives it saw, each with the page that shows it; `families.rule_packs()` (built, D59) maps them to families and rules. Used for goal flows ('create 2 items then sort') and scheduling (frontier priority for primitives and armed rules not yet exercised, merges R10). **The profile does not switch rules off** until an ablation (all packs vs profile packs) shows a precision gain with no recall loss: a wrong profile would otherwise hide faults | profile accuracy against our own labels; recall and precision with and without pack gating | 2 (mapper done) |
| X6 | Verb lists, cue words, `_VALIDATION`, `_SYSTEM_ERR` are English only (item 7) | agree | = O6 (b): word lists as data files per language; English only, reported as a limit | | 2 |
| X7 | Tuned on two apps; false-alarm bounds from two apps are weak (item 8) | agree | The clean corpus (E4) moves to the **start of phase 2**, before the reach work, so every reach change is checked for false alarms on it | false alarms per 100 checks with an exact bound | 2 |
| X8 | Tiers are not a calibrated confidence (item 9) | agree, measured first | **Confidence score** per finding (D59, `evaluate.confidence_block`): logistic model over rule prior, independent cues on the same entity, replay k/n, judge verdict, implicit kind and occurrences; fitted leave-one-app-out with no target leak; precision-recall curve and average precision. First fit on Night 3 (159 labelled findings): AP 0.67, Brier 0.37, and the top score bin (0.8-1.0) is right 2 times in 10: rule priors do not transfer between Conduit and BookStack. **The score is reported, never used to filter**, until it is refit on the clean corpus and validated on a held-out app | AP, Brier, reliability per bin | 1 (built), 3 (refit) |
| X9 | Self-differential gate: replay in another engine and in a fresh context (item 10) | partly | Fresh-context replay exists (k = 3). Add a **Firefox/WebKit replay** of each confirmed finding; a finding that holds in one engine only is reported as **engine-specific** (an EN1 candidate), not as `harness-suspect`: browser-specific bugs are real. Cost: one replay per confirmed finding per engine | engine agreement rate; gate minutes | 3 |
| X10 | Guard and check-outcome logs must exist before more rules (item 11) | agree, **done** | `checks.py` and hooks (D59); entry rule for a lock: a rule counts only with its check rows | arm rate per rule; suppressions per guard | 1 |
| X11 | `Violation.tier` raises `KeyError` for an unregistered rule (item 12) | agree, **done** | `TIER.get(rule, "T2")`; wave rules register their tiers in their module (`norms.TIERS`); tested | | 1 |
| X12 | One bug firing many findings distorts precision (item 13) | agree, **done** | Distinct issue = rule x page template x entity kind, in the evaluator; findings per issue reported | | 1 |
| X13 | About 75 rules do not fit mid-November (item 14) | partly | The user asked for a rule for every coverable family. Section 12: all are built wave by wave, but **only rules measured by a lock count in that lock**; the high-yield set the reviewer names (R20, R21a/b, R23, R24, R43, R57, R62/R63, R68, R02 extension) is wave W1 | rules built and measured per lock (tracker) | 1-4 |
| X14 | Evaluation metrics (12 groups) and baselines | agree | Section 11 | | 1-5 |

## 11. Evaluation framework (D59)

All numbers are computed offline by `python -m webtester evaluate` (`evaluate.py`) from the run folders,
the labels, the fault catalogs (`reachable` per fault; Conduit F03 and F04 are now marked unreachable, I34,
I37), the family registry and the check log. Conditions and apps are never pooled. Status: **built**
(computed now), **data** (the code exists; its input comes with new runs: check logs, clean corpus,
held-out apps), **planned** (with the phase named).

| Group | Metrics | How | Status |
|---|---|---|---|
| 1 Detection | total recall; oracle-conditioned recall (faults in covered, partial or coverable families); recall per family, per primitive, per app; precision per finding, per distinct issue, per tier, per rule, gate-confirmed and judge-filtered, each with a Clopper-Pearson interval; F0.5 (weights precision); unseeded real bugs (`new:`); findings per distinct issue; mixed issues | labels, catalog, `families.fault_families_of()` | built; per app type and per severity planned (E8, phase 3) |
| 2 False alarms | clean-app false alarms per run, per 100 steps and per 100 armed checks, each with an exact Poisson (Garwood) interval (0 events gives the rule of three); per rule; `harness:` apart; real bugs on a clean app (U#, `new:`) not counted | clean runs, labels, check log | built; per 100 checks needs check logs (data); the corpus is E4 |
| 3 Reports | confirmed / flaky / rejected / unverified rates; gate recall loss per fault and per true finding (Night 3: 2.5% Conduit, 5% BookStack, as in the ledger); minimal trace length | gate results | built; human reproduction of 20 sampled reports, an actionability rubric and triage time: protocol in phase 3 |
| 4 Reach | states, routes, transitions; travels; check arm coverage | summary, graph, check log | built; controls seen vs activated (X1), write success per form kind (R1), input classes per field (R5), routes per role (R3), data depth (R2), JS coverage (CDP), API endpoints vs OpenAPI, handler coverage (R12), unsupported modalities (R6): planned with those items |
| 5 Efficiency | new states per step; duplicate and failed action rates; travel ratio; time to first detection; recall at 25/50/75/100% of the run's time | trace step times | built; dead-end and revisit rates, session-loss events (R8), recall over steps and tokens: phase 2 |
| 6 Funnel | per fault and run: S1 reached, S2 triggered, S3 observed, S4 armed, S5 flagged, S6 confirmed, S7 matched; first stage failed; suppressions and caps on the fault's route | catalog routes, exposure markers, check log, family rules | built; S3 not measured yet (needs a per-fault observation spec); S2 for Conduit's server faults needs O-6; S4 needs check logs (data) |
| 7 Cost | tokens per step and per true distinct issue; browser, wall and gate minutes; LLM retries and policy errors | summary | built; parallel speedup at N = 1, 2, 4, 8 and cross-worker redundancy: experiments in phase 3 (VM for N > 8) |
| 8 Variance | median, IQR, mean, SD, CV per metric; bootstrap interval of the mean; healthy-run share | per-run metrics | built; LLM swap, rebranded BookStack (E6), front-end frameworks (RealWorld variants): runs in phase 3 |
| 9 Generality | dev vs held-out difference of every group 1 and 2 number; leave-one-app-out for the confidence score | the same blocks per app | built; zero-config rate and setup effort (config items per app): phase 3 |
| 10 Oracle level | per-rule precision and measured tier (T1 when n >= 5 and precision >= 0.90), arm rate; judge accuracy against the labels (Night 3: Conduit 42 of 45, BookStack 4 of 10); Cohen's kappa of the user's blind 20% check | labels, check log, `label_check_sample.toml` | built; kappa pending the blind labels; mutation score on real historical faults (E5) planned |
| 11 Safety | destructive-action incidents, out-of-scope requests blocked, cleanup success, mode violations | executor logs | planned with S1, S2 (phase 2) |
| 12 Statistics | exact Mann-Whitney U and A12; **Holm-Bonferroni over a pre-registered primary family** (faults found, precision per distinct issue, unique states); every other metric exploratory and unadjusted; bootstrap intervals over runs and apps | `stats.py` | built |

**Why the primary family is small.** With n = 5 runs per condition the smallest exact two-sided
Mann-Whitney p is 2/252 = 0.0079, so Holm over m metrics can reach 0.05 only when m <= 6 (over all 16
per-run metrics the best adjusted p would be 0.13). Either the primary family stays at 6 metrics or fewer,
or n = 6 per condition (smallest p 0.0022). We keep n = 5 and three primary metrics, fixed now, before any v5
run.

**Baselines.** B0 crawler, random, B1 single LLM agent, B2 (N independent), B3 (shared frontier), B4 (+ G2
gate and G3 oracles), the ablations (A-G1, A-G2 paired, A-G3), and B5 (roles, X4). Published tools where they
run on our apps: WebTestPilot's benchmark is the source of BookStack's faults; another crawler only if it runs
on our apps without porting work (not counted until it does).

**First numbers from the evaluator** (Night 3 b4 and b3v3, 20 valid runs, live findings; a check of the
evaluator, not a v5 result). It reproduces the ledger: Conduit b4 precision 82% raw, 88% gated, 89%
judge-filtered; BookStack 38 / 48 / 49%; BookStack 5 of 13 faults across runs; gate loss 2.5% and 5%. New:
precision per distinct issue is lower than per finding (Conduit 68%, 15 of 22 issues; BookStack 23%, 6 of
26), so the per-finding number flatters both; b4 beats b3v3 on faults found after Holm on both apps (Conduit
p_holm 0.024, BookStack 0.016), while b3v3 has the higher distinct-issue precision on Conduit (A12 0,
p_holm 0.03; it reported only implicit findings).

## 12. A rule for every coverable family (D59)

### 12.1 How the families are organised in code

- `families.py` reads `fault_families.md` (163 families, the statuses of its tally), the primitive table and
  the app-type table. 'Built' is read from the code (the tier table and the implicit kinds), so the tracker
  (`docs/family_tracker.toml`, `python -m webtester families --write`) cannot show a family as built before its
  rule exists. After the three D59 rules: 47 families fully built, 14 partly, 91 with no rule yet, 11 spec or out; 53 rules left to build.
- **Rule packs** per primitive: `rule_packs(app_type)` gives the families and rules for an app type and lists
  the rules it names that do not exist yet. NAV and the implicit signals are always on.
- Each new rule lives in the module of its wave (`norms.py` is the first), registers its tier there (T2),
  reads its page data in one `evaluate`, and notes its outcomes in the check log.

### 12.2 Waves (all 56 unbuilt rules, as of D59)

| Wave | Rules | Needs first | Test apps |
|---|---|---|---|
| W1 (12) | R20 cross-view, R21a prefill, R21b unchanged save, R23 search recall, R24 no-session probe, **R43 anchors (built)**, R53 cancel probe, R62 address replay, R63 address probes, **R64 control state (built)**, R68 inverse relations, R73 history ledger; plus the R02 media extension | check-outcome log (done) | Conduit, BookStack |
| W2 (21) | R12b, R22, R25, **R26 range (built)**, R27, R29, R30, R31, R38, R39, R44, R49, R50, R52, R54, R55, R56, R58, R59, R61, R71 | R1 input profiles, R2 seeding, S1 modes for R50 and R52 | Conduit, BookStack, Parabank, the clean corpus |
| W3 (15) | R32-R37, R40-R42, R45, R47, R48, R69, R70, R72 | Parabank, Timeoff and a shop on the development side; R2 seeding | Parabank, Timeoff, synthetic pages |
| W4 (8) | R28, R46, R60, R65, R66, R67, R74, R75 | R3 second account, S1 controlled mode, M14 page reads | all development apps; synthetic media and canvas pages |
| ext | extensions named in family rows (I-edit/I-delete identity, R49 archive, R40 cycle, R16 uniqueness, R23 metacharacters, R10 contact links, R01/R02 placeholders, R24 back after logout, R22 guest merge, R36 recurrences, R37 import report, R48 storage) | the base rule | as the base rule |

**Done for a rule** (entry to a lock): (1) a fixture test with a faulty and a clean page; (2) check-outcome
rows for every exit (armed, unarmed with the reason, suppressed with the guard); (3) a seeded fault of its
family, written from the family row before the rule (E5 b); (4) zero false alarms on the clean-corpus
resweep, or each one labelled; (5) its precision measured on the development apps (T1 only at n >= 5 and
precision >= 0.90).

**Scope.** Building every wave by 30 Nov is a target, not a promise: the W3 and W4 rules need apps and modes we
do not run yet. A lock lists what is built and what is measured; the tracker shows the rest as designed but
unbuilt, and the paper counts only measured rules (section 6, last line).

### 12.3 Revised order for phases 1 and 2

| Phase | Adds (from sections 10-12) |
|---|---|
| 1 (to 2 Nov) | Done: X10, X11, X12, check log, evaluator, tracker, `capture_evidence` on, R43, R64, R26. Left: resweep of the Night 3 runs with the check log and the new rules (the user runs it), label the new signatures, funnel S4 numbers; then the v5.0 items already listed (O3, C1-C3, C6, J3, O-7, the rest of W1) |
| 2 (5-15 Nov) | Clean corpus first (X7, E4); X1 element ranking and scrolling; X2 stateful travel; X3 worker namespaces; X5 app profile (the live step); X4 roles and B5; then R1-R9 as in section 4.1 |

## 13. Code done with D59

- `src/webtester/checks.py` (new): `CheckLog` (per worker, rule, route, outcome and reason: count, first and
  last step), `page_arms` for the pure page rules.
- `src/webtester/consistency.py`: `DEFAULT_TIER = "T2"` (no `KeyError`); `SweepState.checks` and
  `SweepState.v5_rules`; Sweeper `_ck`, `_arm`, `_settle_checks`; outcome hooks in every rule and guard (I-*
  intents, R02, R05, R07/R07b/R07c, R08 guards, R09 guards, R10, R11, R13, R15, R16/R17, R19, G1, G2, R51,
  R57); `view_diff` reports the guard that dropped each list; `_norms` runs `norms.py`. No existing rule's
  result changed (the 102 earlier tests pass unchanged).
- `src/webtester/norms.py` (new): R43 anchors, R64 control state, R26 declared ranges, all T2; no findings on
  the five BookStack fixture pages.
- `src/webtester/families.py` (new): registry, primitives, app types, fault-to-family map, rule packs, tracker.
- `src/webtester/evaluate.py` (new); `stats.py`: Wilson, Clopper-Pearson, Garwood, Holm, bootstrap, spread;
  `labels.py`: `harness:` labels are not true positives.
- `src/webtester/runner.py`: writes `checks.jsonl` (live runs) and `checks_resweep[_clean].jsonl` (resweeps);
  the trace's `sweep` event carries the check summary.
- `src/webtester/cli.py`: `evaluate` and `families` commands.
- `apps/realworld/faults/faults.toml`: F03 and F04 `reachable = false`.
- `configs/realworld.toml`, `configs/bookstack.toml`: `capture_evidence = true`.
- `docs/family_tracker.toml` (generated).
- `tests/test_d59_eval.py`: 18 tests. Full suite: 120 passed, 4 skipped.

## 14. Implementation status after D60 (28 Oct)

The user asked to build every phase and a rule for every fault family. **Built** = in the code with tests
(unit, fixture or a served synthetic page); **built, untested live** = the code exists but has not run against
Conduit, BookStack or a corpus app (the user runs those, I59); **setup** = files written for an app or service
not started yet (I55); **protocol** = a written procedure with no data yet; **user** = needs the user's decision
or labour. Nothing here is measured: no v5 run exists yet, and the v5.0 lock waits for the resweep and pilots.

### 14.1 Phase 1 (v5.0)

| Item | Status | Where |
|---|---|---|
| Check-outcome log, guard suppressions, X10-X12 | built (D59) | `checks.py`, `consistency.py` |
| O3 poll to a deadline | built | `BrowserSession.fresh_text_until`, I-create/I-edit check |
| C1 session storage in gate replays | built | `StepRecord.session`, `BrowserSession.start(session_storage=)` |
| C2 probe values marked, C3 harness-health check | built | `signal_of(health, probe_values)`, `Sweeper._health` |
| C6 gate: T1 first, causes per finding, a missing link followed by its address | built | `gate.py` |
| J3 benign words lower numeric rules one tier | built | `consistency.BENIGN`, `lexicon/en.toml` |
| E3 `harness:` labels, distinct issues | built (D59) | `evaluate.py`, `labels.py` |
| O-7 left-overs (button text in R09, identical cards in I-delete) | built | `consistency.py` |
| E1 revisit bonus, E3 unvisited item pages, E2 notes cap (`notes_max`) | built, untested live (the pilots decide) | `frontier.py`, `config.py` |
| Wave W1 rules | built | see 14.4 |

### 14.2 Phase 2 (reach)

| Item | Status | Where |
|---|---|---|
| R1 input profiles | built for generated values (`reach.profile_value`) and uploads (R42); the retry of a rejected form with profiled values is **not wired** into the worker yet (the LLM still types every value) | `reach.py` |
| R2 seeding | built: the first accepted create of a form is copied `seed_copies` times | `Sweeper._seed` |
| R3 accounts per role, second session | built: `[[app.accounts]]` with roles, `other_account`, a logged-in second session for R46/R67; the dev configs have one role | `config.py`, `probes5.Probes._second` |
| R4 role and context in the state id | **not built**: the role is constant per worker (each worker keeps one account), so it adds nothing yet; to do when a worker switches accounts | |
| R6 / X1 modalities: shadow roots, same-origin iframes, scroll once, ranking before the cap, native dialogs accepted and logged | built | `browser.py` |
| R7 discovery from robots.txt, sitemaps, feeds | built (network GETs: helper only, not fed during the run) | `reach.parse_discovery`, `runner._discover` |
| R8 destructive ordering | built (enforced in the worker loop, not the prompt) | `reach.defer_reason`, `worker.py` |
| R9 pop-ups | built | `browser.POPUP_JS` |
| S1 execution modes, S2 stop file | built | `BrowserSession.mode_refuses`, `RunContext.stop_requested` |
| O4 dev-server noise | built | `browser.DEV_NOISE` |
| O6 (a) number parser, (b) cue words as data, (c) entity key fallback | (a) built (`norms.parse_number`); (b) built for the v5 rules, the v4 lists stay in code (I56); (c) **not built** | `norms.py`, `lexicon.py` |
| X2 stateful travel | built: recorded navigation paths replayed when a URL does not restore the state | `stategraph.nav_path`, `worker._replay_path` |
| X3 worker namespaces | partly: `reach.namespace` for harness-generated values; LLM-typed values are not rewritten | `reach.py` |
| X4 roles, condition B5 | built | `reach.ROLE_PROMPTS`, `runner.py` (`--agent b5`) |
| X5 app profile, goal flows | built (never switches rules off) | `policies.LLMPolicy._profile`, `families.rule_packs` |

### 14.3 Phases 3-5 (evaluation set, remaining mechanisms, lock)

| Item | Status | Where |
|---|---|---|
| E4 clean corpus | setup: Parabank and Juice Shop compose files and configs; 9 more apps listed with what each needs | `apps/corpus/`, `configs/corpus_*.toml` |
| E5 real historical faults | protocol; candidates not selected yet (needs a search of the issue trackers, I58) | `apps/bookstack/historical/` |
| E5 (b) second-variant faults | user (written without looking at the rules) | |
| E6 rebranded BookStack | setup: client-side rename and recolour, its own config | `apps/bookstack/rebrand/rebrand.js`, `configs/bookstack_rebrand.toml` |
| E8 severity | built: catalog field, recall per severity, severity-weighted recall; severities set by the assistant, to be checked | `faults.toml`, `evaluate.severity_recall` |
| O6 (d) extraction benchmark | built with 3 labelled synthetic pages; first score: list items precision 78%, recall 64% (I57); the 60 real pages are user labour | `tests/extraction/`, `scripts/extraction_bench.py` |
| R10 budget priority | partly: E1/E3 terms and the profile's goal flows; recall over time in the evaluator; no check-log-driven frontier term | `frontier.py`, `evaluate.py` |
| R12 handler coverage, JS coverage | built (measured only, `coverage_metrics`) | `browser.LISTENERS_JS`, CDP Profiler |
| C5 ddmin, X9 cross-engine replay | built (`gate_ddmin`, `gate_engines`) | `gate.py` |
| M10 environment replay (R71) | built (`env_axes`) | `envcheck.py` |
| M11 injection (R50m), J6 records | built (controlled mode) | `probes5.Probes._lost_response` |
| O5 storage model | partly, inside R48 (a browser-only change must survive a reload) | `probes5.py` |
| O7 declared data (JSON-LD, OpenGraph) | built as R20d | `crossview._declared` |
| O8 downloads | CSV exports (R37); PDF text not built | `probes5.py` |
| O9 mail | setup: Mailpit override for BookStack; no rule reads mail yet | `apps/bookstack/docker-compose.mailpit.yml` |
| Evaluation additions | built: harness-suspect and probe-value findings apart, engine-specific findings, reach and safety counters, setup effort per app, per-severity recall | `evaluate.harness_block`, `setup_effort` |
| E9 / D51 freeze | generated freeze list of every cap, tolerance, default and tier; the freeze itself is the user's decision at the lock | `scripts/freeze_list.py`, `docs/d51_freeze.md` |

### 14.4 Rules

Every family that `fault_families.md` marks covered, partial or coverable now has its named rules in the code:
152 families built, 11 spec or out (`docs/family_tracker.toml`; 99 rules with a tier). D60 added 62 rules:
page norms R25, R41, R32 (running balance), R36, R06s, R72, R54, R65, R74, R75, R02m, R01x, R10x; cross-view R20,
R20d, R21a, R40, R47, R31, R73, R68, R22, R34, R35, R32 (transfer), R70, R12b, R56, R30, R27, R29, R38, R38c, R44,
R55, R58, R69, R50; probes R63, R62, R23, R24, R28, R66, R46, R46c, R67, R21b, R53, R49, R52, R48, R39, R37, R42,
R45, R59, R61, R60, R33, R33g, R50m; environment R71. Every one starts at T2 (R56, R59, R61, R38c, R33g, R46c at
T3) and counts in a lock only by section 12.2's rule (fixture test, check rows, a seeded fault of its family,
clean-corpus false alarms, measured precision).

**Tests.** 43 of the 62 have a faulty and a clean case (`tests/test_d60_rules.py`, `test_d60_crossview.py`,
`test_d60_probes.py`; the probes run against a served in-memory app with faults and without). Writing those
tests found 8 bugs, all fixed before this lock: R12b missed a value both escaped and accent-folded; R63 and R37
fetched through the API client, which bypasses the browser's network (no result on routed apps, and unlike the
gate); R39 compared a list's first page with itself (a false alarm on the clean app); R37 required a comma in a
CSV; R32's transfer check and R20's stale-name check could never run (control flow); R46 and R67 spent their
probe slot before checking for a second account. **Not exercised by any test yet (19):** R24, R28, R33, R33g,
R42, R45, R46, R46c, R48, R49, R50, R50m, R52, R54, R59, R60, R61, R66, R67, the probes that need a login, a
second account, an upload or controlled-mode writes.

### 14.5 What the user runs next

1. `bash scripts/resweep_d59.sh`: the Night 3 runs replayed with every v5 rule, check log and evidence on (writes
   `v59_*`; the name stays for continuity). Then the assistant labels the new signatures and runs
   `python scripts/eval_v5dev.py --ver v59`. Resweeps replay the recorded trail exactly: no ranking cap, no seeding, no destructive
   deferral (D60), so they measure the oracles, not the new reach (that needs live runs).
2. One live pilot per dev app with `--agent b4` (and one `b5`), to check the reach changes do not break
   exploration (I60).
3. `app up` for the two corpus apps and the rebranded BookStack (I55).

## 15. Audit after D61 (29 Oct): every item of this plan, the family table and the metric list

The user asked for a check of this plan from start to end, of every fault family, and of every metric the paper
reports, and for everything incomplete to be built and tested. Each id below was checked against the code by name
and by behaviour (a faulty and a clean case where it is a rule). Section 14 is the D60 state; this section
replaces its status column. **Built** = code and tests exist; **measured** = it also has numbers from runs (none
yet for v5, I59); **user** = needs the user's runs, labels or judgment.

### 15.1 Plan items

| Id | Status after D61 | Where |
|---|---|---|
| R1 input profiles | built: values from the field's declared attributes and the app's message; one retry of a rejected form (`MAX_RETRY_FORMS` = 6); write success per form kind | `reach.profile_value`, `Sweeper._retry_form`, `_count_form`; `test_d61_forms.py` |
| R2 seeding | built: the first accepted create copied `seed_copies` times, then once topped up to page size + 1 when the page shows its page size (or `app.page_size`), `MAX_TOPUP` = 25 copies per run | `Sweeper._seed`, `_top_up` |
| R3 accounts per role | built; the dev configs have one role (user) | `config.py`, `probes5._second` |
| R4 role and active context in the state id | built: role (accounts of several roles) and the active context of a context switcher outside forms | `worker._sid`, `browser.CONTEXT_JS` |
| R5 coverage ledger | built: `coverage.json` per run | `runner.coverage_of` |
| R6 modalities | built: shadow roots, iframes, dialogs, row hover; keyboard, context menus, drag and canvases counted per page (reported, not driven) | `browser.py` |
| R7 discovery | built: robots, sitemaps, feeds, and same-origin document GETs from the network timeline fed to the frontier | `runner._discover`, `worker.py` |
| R8 destructive ordering, R9 pop-ups | built | `reach.defer_reason`, `browser.POPUP_JS` |
| R10 budget priority | built: an unarmed-area term from the check log; the profile's least-exercised primitive first in the goal flows; recall curves over steps, minutes, tokens | `frontier.area_work`, `reach.rank_primitives`, `evaluate.efficiency_block` |
| R11 sequences | built: DB9, HI3, DB12 sequences as goal flows when the graph has item or nested pages | `reach.sequence_goals`, `policies.py` |
| R12 handler and JS coverage | built (measured only, `coverage_metrics`) | `browser.py` |
| R13 stop signal | measured only, as the plan says: state plateau per run; a JS-coverage plateau is v5.1 | `evaluate.efficiency_block` |
| O-R1 (E1, E2, E3) | built; the live pilots decide | `frontier.py` |
| O1, O2 | built (D58) | `evidence.py`, `browser.py` |
| O3 poll to a deadline | built | `Sweeper._verify_pending`, `browser.fresh_text_until` |
| O4 dev noise, build mode | built | `browser.DEV_NOISE`, `report()["build_mode"]` |
| O5 client storage as the model | built: local storage and IndexedDB against the list (R48s), 'null' storage (R48c) | `probes5._storage_model`, `IDB_JS` |
| O6 (a) numbers, (b) cue words, (c) item key, (d) extraction benchmark | built; (b) now includes the v4 lists, pinned (I56); (d) has 3 labelled pages, the 60 real ones are user labour | `norms.parse_number`, `lexicon/`, `memory.item_key`, `tests/extraction/` |
| O7 declared specs | built: JSON-LD and OpenGraph against the page, title against h1 (R20d), sitemap and feed links (R02s), the newest feed item on its page (R20f), OpenAPI and GraphQL contracts (R57e) | `crossview._declared`, `runner._check_discovered`, `openapi.py` |
| O8 downloads, CSV, PDF | built (PDF text needs the optional `pypdf`) | `probes5._exports`, `_downloads`, `_pdf` |
| O9 mail | built (R47m with a Mailpit-style API in our deployments) | `probes5._mail`, `apps/bookstack/docker-compose.mailpit.yml` |
| O10 backend traces | not taken (section 8) | |
| O11 LLM annotation | built: condition `b4annot`, cached per route and heading, read-only in replays | `annotate.py`, `gate.py` |
| J1-J5, J7 | done (D58-D60) | `fault_families.md`, `consistency.BENIGN` |
| J6 injection records | built (R50m) | `probes5._lost_response` |
| C1-C3, C5, C6 | built | `gate.py`, `consistency.signal_of` |
| C4 flakiness | built: seeded generated values, time rules replayed on the recorded clock | `reach.run_suffix`, `gate.TIME_RULES` |
| E1, E2 funnel and check outcomes | built; S3 is not measured (needs a per-fault observation spec) | `evaluate.funnel_block`, `checks.py` |
| E3 labels and distinct issues | built | `evaluate.py`, `labels.py` |
| E4 clean corpus | setup for Parabank and Juice Shop, nine more listed; runs are user | `apps/corpus/` |
| E5 (a) historical faults, (b) second variants | protocol; selection and writing are user (I58) | `apps/bookstack/historical/` |
| E6 rebranded BookStack | setup; runs are user | `configs/bookstack_rebrand.toml` |
| E7 variance, E8 severity, E10 detector vs end-to-end | built; severities to check (user) | `evaluate.py` |
| E9 freeze | built: generated list, regenerated at D61 | `scripts/freeze_list.py`, `docs/d51_freeze.md` |
| S1 modes, S2 stop | built, with mode violations, incidents and cleanup share recorded | `browser.mode_refuses`, `runner.safety_of` |
| A1 scope, A3 | stated (A1: web apps through a browser; adapters only described); A3 done | sections 1, 4.7 |
| A2 diff mode | not taken | |
| O-1 module split | after the v5.0 lock, as planned | |
| O-2 to O-7 | built (O-6: `[wt-fault]` lines read by `appctl`) | |
| W2-W4 waves | built (section 14.4 and 15.2) | |
| X1, X2, X4, X5, X8-X12 | built; X5 also has profile accuracy and a profile-gating switch for the ablation (off) | |
| X3 namespaces | partly, by decision (D60): harness values only; one app instance per worker group for N >= 8 needs the VM (phase 3) | `reach.namespace` |
| X6 | = O6 (b), built | |
| X7 corpus first | setup; runs are user | |
| X13 scope | all rules built; only measured rules count in a lock (12.2) | |
| X14 | section 11 and 15.3 | |

### 15.2 Fault families

Every row of `docs/fault_families.md` was read with its named rules and its named extensions. `families.EXTENSIONS`
maps each 'Rxx extension' or 'variant' a row names to the rule id that implements it (written in the row as
"D61: ..."), and the tracker counts a family as built only when every named rule and every extension id exists:
**152 built, 11 spec or out (3 need a specification, 8 are out of scope), 0 rules left** (`docs/family_tracker.toml`).
`tests/test_d61_static.py` checks the registry against the rows and checks that every rule the tracker counts as
built has code that raises it (this found G3, I65). The 11 spec and out families cannot get a spec-free rule by
their definition; nothing else is missing.

### 15.3 Evaluation metrics (the paper's list) and where each is computed

| Group | Metrics | `evaluate.py` |
|---|---|---|
| 1 Detection | total and oracle-conditioned recall, per family, primitive, app and app type; mutation score; precision per finding, distinct issue, tier, rule, gated, judged, with intervals; F0.5 and F1; unseeded bugs; mixed issues; severity-weighted recall | `recall_block`, `precision_block`, `severity_recall`, `f_beta` |
| 2 False alarms | per run, per 100 steps, per 100 armed checks, exact intervals, per rule | `false_alarm_block` |
| 3 Reports | gate rates, gate loss, minimal trace length; human reproduction, actionability rubric, triage time from the user's ratings | `gate_block`, `report_quality_block`, `scripts/report_sample.py` |
| 4 Reach | states, routes, transitions, travels; controls seen and activated; write success per form kind; input classes per field kind; routes per role; data depth (list-rule arm rate); API endpoint coverage (OpenAPI, GraphQL); server coverage when measured; unsupported modalities; build modes | `run_metrics`, `reach_block` |
| 5 Efficiency | new states per step, duplicate and failed actions, travel ratio, time to first detection, recall at 25/50/75/100%, dead-end and revisit rates, session losses, area under the recall curve over steps, minutes and tokens, state plateau | `run_metrics`, `efficiency_block` |
| 6 Funnel | S1-S7 per fault and run, first failed stage, recall lost per guard | `funnel_block`, `guard_loss` |
| 7 Cost | tokens per step, per finding, per true issue, per confirmed true finding; USD; browser, wall and gate minutes; judge tokens; retries; policy errors; cross-worker redundancy; speedup and efficiency over worker counts | `run_metrics`, `cost_block`, `scaling_block` |
| 8 Variance and sensitivity | median, IQR, mean, SD, CV, bootstrap; healthy-run share; LLM, framework and rebrand axes | `spreads`, `sensitivity_block` |
| 9 Generality | dev vs held-out gaps; setup effort; across apps with a bootstrap over apps | `generalization_block`, `setup_effort`, `across_apps` |
| 10 Oracle level | per-rule precision and measured tier, tier calibration, arm rate, per-rule recall, judge accuracy, kappa, engine agreement, profile accuracy | `precision_block`, `tier_calibration`, `rule_recall`, `kappa_block`, `engine_agreement`, `profile_accuracy` |
| 11 Safety | destructive incidents, out-of-scope requests blocked, writes refused, mode violations, cleanup share | `safety_block` |
| 12 Statistics | exact Mann-Whitney and A12, Holm over the primary family, bootstrap | `compare_conditions`, `stats.py` |
| E10 | detector-only (resweep) vs end-to-end (live) | `detector_vs_e2e` |

Every block runs on hand-made runs in `tests/test_d61_reach_eval.py` and on the recorded Night 3 and resweep runs
(`scripts/eval_v5dev.py`). Blocks whose input does not exist yet (worker-count series, held-out apps, ratings,
second engines, LLM swaps) return a `status` naming what they wait for, never a zero.

### 15.4 What is left, and with whom

All of it is user work or needs runs: the D59 resweep and the live pilots (I59, I60); the clean corpus, held-out,
rebrand and scaling runs; the historical faults and second variants (I58); the 60 real extraction pages; the
report ratings; checking the severities and the dev-config labels (I72). The login and second-account probes
(R24, R24b, R28, R46, R46w, R66, R67) are exercised only by the resweep (I59).
