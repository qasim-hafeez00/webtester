# Harness v5 plan: every gap, what to add, how to measure it (D58)

Status: 28 Oct 2026. Built from two reviews of `docs/fault_families.md` (ChatGPT and Claude, pasted by the
user on 28 Oct; tagged **[G]** and **[C]** below) and from our own reading of the code and logs (**[O]**).
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
| Oracles | 32 deterministic rules (R01-R19, I-*, G1-G3) + R15 (LLM-cited, T3), and R51, R57 since D58; probes capped per step and per run | `consistency.py` (1,940 lines) |
| Evidence | statuses of same-origin writes, 5xx, JS errors, failed requests; **since today, behind `capture_evidence`**: network timeline with JSON bodies and sent data, transient messages (R57, R51) | `browser.py`, `evidence.py` |
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

`docs/family_tracker.toml` (phase 0): one entry per family of `fault_families.md` with `status` (as in the
file), `rule`, `built` (commit), `fixture_test`, `seeded_faults` (ids), `funnel` (last measured stage
counts), `recall`, `precision`, `tier`. The tally in `fault_families.md` stays the specification view; the
tracker is the implementation view, so a family never looks covered on paper before it is.

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
  resweep the Night 3 runs with it (phase 1) to measure R57 and R51 before they count.
