# Fault families and oracle coverage (D56, D57)

Status: 28 Oct 2026 (extended the same day with app types, workflow primitives and 44 families; then with
57 families, five mechanisms M10-M14 and an identity library taken from two reviewer chats, D57; what was
not taken is in section 10). A living table: every web fault family named in the published taxonomies below, what a
tester without a specification can check for it, and which harness rule does so today. It chooses the rule
families harness v5 still needs to work on apps in general, not only on Conduit and BookStack.

**Held-out rule.** This table was built from published taxonomies and from our two development apps
(Conduit F01-F10, BookStack BS01-BS18) only. PrestaShop's fault list was not read (I50). The shop families
(collections, arithmetic, ranges, ordering) come from Vijayaraghavan and Kaner's public shopping-cart
taxonomy, which predates and is independent of PrestaShop.

## 1. Sources

| Ref | Source | What it gives | Checked here |
|---|---|---|---|
| **MRT** | Marchetto, Ricca, Tonella. *An empirical validation of a web fault taxonomy and its usage for web testing.* JWE 8(4), 2009, 316-345 | 57 fault classes under 6 web characteristics (A multi-tier, B GUI, C session, D hyperlinks, E protocols, F authentication), validated on 676 real bugs from 68 apps; 74.4% of the bugs are web-specific | Tables 1, 2, 5, 7 read from the paper |
| **MvD** | Mesbah, van Deursen, Roest. *Invariant-based automatic testing of modern web applications.* IEEE TSE 38(1), 2012 (ICSE 2009 version) | Generic DOM invariants (valid DOM, no error messages, accessibility/i18n, secure states) and generic state-machine invariants (no dead clickables, consistent back button) | Section 5 read from the paper |
| **VK** | Vijayaraghavan, Kaner. *Bug taxonomies: use them to generate better tests.* STAR East 2003; *Bugs in your shopping cart: a taxonomy*, QW 2002 | E-commerce taxonomy: 45 categories, 700+ risks (calculation errors, usability, i18n, navigation, client privacy, security, scalability, server/network/host failures, compliance) | Simplified taxonomy and navigation failure modes read from the 2003 paper |
| **GN** | Su et al. *Fully automated functional fuzzing of Android apps for detecting non-crashing logic bugs* (Genie). OOPSLA 2021 | Non-crashing functional bugs: inadvertent function failure, silent user data loss, incorrect display; the independent-view property as an oracle | Abstract |
| **OC** | Ocariza, Bajaj, Pattabiraman, Mesbah. *An empirical study of client-side JavaScript bugs.* ESEM 2013; TSE 2017 | 65% of JavaScript faults are DOM-related (ESEM); 80% of the highest-impact ones (TSE) | Abstracts |
| **XI** | Xiong et al. *An empirical study of functional bugs in Android apps.* ISSTA 2023 | 399 functional bugs: root causes, symptoms, oracles | Scope only (categories not read) |
| **WTP** | WebTestPilot benchmark (our BookStack faults, `apps/bookstack/faults/faults.toml`) | Classes missing-element, data, no-op, navigation | Read |
| **SEG** | Segura, Durán, Troya, Ruiz-Cortés. *Metamorphic relation patterns for query-based systems.* MET 2019 | Relations from relational algebra (filtering, ordering) shared by every query-based system; applied to PrestaShop's search, Gmail and a video app (generic patterns, not PrestaShop's injected faults) | Abstract |
| **MAI** | Mai, Pastore, Goknil, Briand. *Metamorphic security testing for web systems.* ICST 2020 (extended: arXiv 2208.09505) | 22 system-agnostic relations by OWASP class: access control 7, authentication 6, data exposure 5, misconfiguration 3 (76 in the extension) | Table V |
| **LWW / TRU** | Lewis, Whitehead, Wardrip-Fruin. *What went wrong: a taxonomy of video game bugs.* FDG 2010; Truelove, de Almeida, Ahmed. *We'll fix it in post.* 2021 | 20 game bug types (action, value, information, context state, event occurrence, triggered or interrupted event, object persistence, position, bounds, collision, UI, graphics, crash, ...) | Table II of TRU |
| **DLB** | Riganelli, Mobilio, Micucci, Mariani. *A benchmark of data loss bugs for Android apps.* MSR 2019 | 110 real data-loss faults in 48 apps: state lost when the view is destroyed and rebuilt | Abstract |
| **DT** | *It's about time: an empirical study of date and time bugs in open-source Python software.* MSR 2025 | 151 bugs; time-zone mistakes are the largest factor; misread library defaults and edge cases | Abstract |
| **FIN** | Xuan, Zhao, Wang, Li. Bugs in three industrial financial systems. IEICE Trans. | Most common: internal interface 19.0%, algorithm/method 17.7%, logic 15.0% | Abstract |
| **RND** | Furtuna. *Exploiting rounding vulnerabilities.* Hack.lu 2013 (practitioner) | Truncation of two-decimal amounts in internet banking moves money between bank and customer | Talk abstract |
| **EHR** | VA analysis of 100 EHR safety investigations, 2009-2013 (via MedCity News); ECRI Top 10 health IT hazards 2013 | Four categories: unmet display needs, software modifications, interface shortcomings (data of another patient entered into a record), hidden connections; ECRI: data linked to the wrong record | News coverage (secondary) |
| **BAC** | El Hajj Chehade, Hantke, Stock. *403 Forbidden?* IEEE S&P 2025; Son, McKinley, Shmatikov. *Fix Me Up.* NDSS 2017 | Live access-control flaws in 7 of 100 sites; missing checks are the common error | Abstracts |
| **DBK** | Practitioner write-ups on double booking (dev.to, Indie Hackers) and a 2025 reservation-system study | Check-then-act races accept two bookings of one slot; concurrent edits silently overwrite | Blogs (illustrative, not evidence) |
| **CAT** | CATTest (EMNLP 2026), Table 5 only | 9 app categories of our held-out set: information display 11, e-commerce/transaction 10, social 10, web application 11, marketing/landing 10, 3D/visualisation 11, data management 10, game 19, SVG 10 (190 bugs). Individual bugs were not read: CATTest is held out | Table 5 |
| **SET** | Sun, Su, Li, Dong, Pu, Xie, Su. *Understanding and finding system setting-related defects in Android apps* (SetDroid). ISSTA 2021; TSE extension | 1,074 setting defects in 180 apps, about 70.7% non-crash; setting-wise metamorphic fuzzing: behaviour must stay the same when a setting is changed and restored. The precedent for M10 (environment replay) | Abstracts |
| **PBF** | Sun et al. *Property-based fuzzing for finding data manipulation errors in Android apps* (PBFDroid). ESEC/FSE 2023; Kea (ASE 2024) and LDMDroid from the same line | Data-manipulation errors (create, update, delete) checked by agreement between a data model and the UI layout; 30 new bugs in 18 apps, 22 non-crashing. Precedent for M12 (payload vs page) and the relation families. Its properties are written by hand per app; ours must be generic | Abstracts |
| **OWA** | OWASP API Security Top 10 (2023); OWASP WSTG-ATHN-06 (browser cache weaknesses), WSTG-ATHN-09 (weak password change or reset); OWASP Multi-Tenant Security cheat sheet | Object-, property- and function-level authorisation as separate surfaces (API1, API3, API5); sensitive business flows (API6); private pages shown by Back after logout; reset links; tenant isolation | Category pages and secondary summaries |
| **A11Y** | *Ma11y: a mutation framework for web accessibility testing.* ISSTA 2024, pp. 100-111 (UC Irvine SEAL group; authors to check in the ACM DL) | 25 accessibility mutation operators; current checkers miss nearly half of the injected bugs | Abstract |
| **REV** | Two reviewer chats (ChatGPT, Claude), 28 Oct 2026, given this file and asked what it misses | Mechanisms N1-N5 (here M10-M14), about 67 proposed families, an identity library by industry, precision guards. Not evidence: a family whose only source is REV is "our analysis" grade | Read in full; what was taken and dropped is in D57 and section 10 |

## 2. What an oracle without a specification can rely on

A generic tester does not know what the app should do. It can still catch a fault when the app disagrees
with something it can observe. The harness uses eight kinds of evidence; every row in section 3 names the
kind it needs:

1. **implicit**: the app fails on its own terms (HTTP 5xx, uncaught exception, error page);
2. **in-page**: one page contradicts itself (a count below the items listed, a total that does not add up);
3. **cross-view**: two pages show the same thing differently (an item's name, price, count or status). One
   of the two views may be the HTTP response the page was rendered from (M12);
4. **intent-effect**: the app accepted what the agent did but the effect is missing (created item absent,
   delete not done);
5. **metamorphic**: two runs that must agree do not (reload, back, undo, unchanged save, search for a known
   name; the same trail in another time zone, locale, browser or window width, M10);
6. **probe**: the harness asks the app a question in a fresh tab (made-up search word, empty input, an
   edit address with no session);
7. **norm**: a rule that holds for web apps in general (a link opens, a pager moves, a count is not negative);
8. **declared**: the page states part of its own spec and the app breaks it (`maxlength`, `min`, `required`,
   a read-only field, a 'Max 5 MB' hint, a '12/280' counter, 'free shipping over $50', M13).

What none of these can catch is a fault where the app is consistent with itself and only a specification
says it is wrong (a wrong tax rate, wrong reply nesting, a sort label 'Desc' where the spec says 'Asc').
That is the **spec ceiling** (section 5).

## 3. The families

Status: **covered** (a rule exists and has found a seeded fault or passed its fixture test), **partial**
(a rule catches some forms), **coverable** (checkable without a spec, no rule yet; proposed rule named),
**spec** (needs a specification), **out** (outside this harness's scope, with the reason).

This status says whether a spec-free check *can* exist. It is not an implementation or a recall claim.
Whether a rule is built, tested on fixtures, tested on seeded faults, and its measured recall and
precision are tracked per family in the v5 plan (`docs/v5_plan.md`, family tracker, D58).

**Tiers.** Every rule reports at a tier. **T1**: deterministic; gate-confirmed findings are reported as
bugs; a T1 rule must keep precision ≥ 0.90 on the development apps' labelled findings (D55), or it drops
to T2. **T2**: deterministic but with a weaker cue, or not yet measured; reported as bugs with lower
confidence, and the judge's opinion is attached (never decisive, D55). **T3**: depends on LLM output (R15)
or on a single weak cue; reported apart and never counted in the headline precision. Every new rule starts
at T2 until it is measured.

### 3.1 Runtime and server errors

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| RT1 | Server error on a request | MRT A3f5, A3f8, A6f1; VK web-server | implicit | HTTP 5xx signal, I-submit, R16 | covered | F01 |
| RT2 | Uncaught client-side exception | OC; MRT B1f3, B2f1 | implicit | JS error signal | covered | F02 |
| RT3 | Error page or stack trace shown as content | MvD 5.1.2 | implicit | R01 (stack-trace patterns) | covered | |
| RT4 | Background request fails silently | MvD 5.3.1; MRT B6f1 | implicit | network failure signals | covered | |
| RT5 | A request answered 200 whose body is an error (an `error` field, a GraphQL `errors` array, an HTML error page served as JSON) | REV; PBF | implicit (payload) | **R57 payload** (D58, `evidence.py`; needs `capture_evidence`; T2 until measured) | covered | |

### 3.2 Rendering and presentation

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| PR1 | Template or serialisation junk (`undefined`, `NaN`, `{{x}}`, `[object Object]`) | MRT A2f1, B1f1 | norm | R01 | covered | |
| PR2 | Encoding or escaping alters data (`>` saved as `&gt;`, mojibake, accents lost) | MRT A3f9 (36 bugs, 2nd-largest class), A6f7, B5f1; VK i18n | intent-effect | R01 (escaped entity shown); **R12b echo fidelity** | partial | |
| PR3 | Typed markup rendered as markup (XSS-shaped) | MvD 5.1.4 | intent-effect | R12 | covered | |
| PR4 | Untranslated keys, mixed languages | MRT B5f3 | norm | **R01 extension** (translation-key pattern), low priority (D61: **R01x**) | coverable |  |
| PR5 | Visual layout defects (overlap, truncation, blank area) | GN incorrect display | norm (DOM geometry) | **R65 geometry** (M14): a visible control whose centre `elementFromPoint` returns another element (no modal open); page wider than the window; text clipped by `overflow: hidden`; text colour equal to its background. Aesthetic layout judgement stays out | coverable (DOM part) | |
| PR6 | Invalid DOM, accessibility, i18n compliance | MvD 5.1.1, 5.1.3; VK compliance; A11Y | norm | none | out (non-functional; an axe/validator pass could be added; A11Y shows such checkers miss about half of injected bugs, so it would be its own dimension) | |
| PR7 | A control the page needs is missing (create button, submit button) | WTP missing-element | in-page | **R31 referenced control**: the page's own text names a control ('use Create X', an empty state 'no X yet, create one') that it lacks; otherwise spec | coverable, low | BS13 |
| PR8 | A widget's state disagrees with itself: `aria-checked`, `aria-selected` or `aria-expanded` against the shown or saved state; two options of a single-choice group selected; the active tab's panel hidden; a carousel indicator on another slide | MvD 5.1.3; REV | norm | **R64 control state** (M14) | coverable | |
| PR9 | Placeholder or development leftovers: lorem ipsum, TODO, `example.com`, links to `localhost` or another host of the same app, call-to-action links to `#` or `javascript:void(0)` | CAT marketing/landing; REV | norm | **R01 extension** (text patterns), **R02 extension** (hosts, empty targets) (D61: **R01x, R02h**) | coverable |  |

### 3.3 Navigation and addressing

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| NV1 | Broken link, missing resource | MRT D1f1, D2f1, D2f2 | norm | R02 (D61: **R02s**) | covered | (upstream BookStack slug) |
| NV2 | Link opens the wrong page (URL or parameter built wrong) | MRT D3f1, D3f4 | cross-view | R10 | covered | |
| NV3 | Back button breaks the state | MRT A1f2; MvD 5.3.2; VK navigation | metamorphic | G1 | covered | |
| NV4 | Pagination does nothing, repeats or skips | VK navigation | norm | R11, R04b | covered | F09 |
| NV5 | Same action leads to different pages | MvD state machine | metamorphic | G3 | covered | |
| NV6 | Content reachable by no navigation (blind spot) | VK navigation | exploration | exploration E3 (side crawl of unvisited item pages), then R02/R20 | partial | BS12 |
| NV7 | A control does nothing (no request, no change) | MvD 5.3.1; GN function failure | metamorphic | I-submit (forms), R11 (pagers), I-toggle; **R29 dead control** for any action-verb button | partial | F09 |
| NV8 | An in-page link (`#section`) points to no element; a menu entry leads to an empty section | CAT marketing/landing; MRT D1f1 | norm | **R43 anchors** (R02 extension) | coverable | |
| NV9 | The page's own address, opened in a fresh tab of the same session, shows a different list state (the filter, sort, page or tab in the URL not applied, or applied but not shown in the controls) | MvD state machine; REV | metamorphic | **R62 address replay** | coverable | |
| NV10 | Edge addresses (`/items/999999`, `/items/-1`, `/items/abc`, `?page=0`, `?page=9999`) give a 5xx, a page with no data under status 200 ('soft 404'), or another item | MRT D3f4; REV | probe | **R63 address probes**: built from item addresses the run saw | coverable | |
| NV11 | Shown contact text differs from its link target (a phone number against its `tel:`, an address against its `mailto:`) | REV | in-page | **R10 extension** (D61: **R10x**) | coverable, low |  |

### 3.4 Forms and input

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| FM1 | Missing validation (empty, spaces only) | MRT A3f5, A4f1 | probe | R17 | covered | F03 |
| FM2 | Boundary input crashes the server | MRT A3f5 | probe | R16 | covered | F01 |
| FM3 | Validation rejects legal input (apostrophe, accents, long but legal) | VK i18n ("registration fields do not accept international characters") | probe | **R16 variant**: `O'Brien`, `Zoë`, rejected while the plain value was accepted (D61: **R16i**) | coverable |  |
| FM4 | Edit form not filled with the item's current values, or filled with another item's (open A's edit, then B's: B shows A's values) | MRT A4f1; REV | cross-view | **R21a edit prefill** | coverable | |
| FM5 | Saving an edit form unchanged changes the item (a field dropped), or is rejected ('name already taken' by the item itself) | GN silent data loss; MRT A6f7; REV | metamorphic | **R21b unchanged save** | coverable | F04 |
| FM6 | Typed input lost after a rejected submit | VK usability, navigation ("state changed/lost") | metamorphic | **R27 input kept** | coverable | |
| FM7 | Submitting twice creates two items | VK | metamorphic | **R33g** double-submit probe on any create form (D60, controlled mode; T3: many apps allow duplicates); R33 for money and order forms | coverable, low |  |
| FM8 | Saved text silently differs from what was typed: cut at a limit the page did not state, whitespace collapsed, emoji or other astral characters cut or replaced; a character counter ('12/280') that differs from the real length | MRT A3f9; REV | intent-effect, declared | **R12b extension** (long values, emoji, double spaces) with the field's declared `maxlength` and counter (D61: **R12c**) | coverable |  |
| FM9 | A number typed in another format is misread without a message ('1,5' saved as 15, '1,000' as 1, digits from other scripts dropped) | VK i18n; SET | probe, metamorphic | **R59 number format probe**; **R71** locale replay | coverable, low | |
| FM10 | The server does not enforce what the page declares (`maxlength`, `min`, `max`, `step`, `pattern`, `required`, a read-only or disabled field), or rejects a value the page allowed with a message about another field | MRT A3f5, A4f1; OWA API3 (property level); REV | declared | **R60 declared constraints** (M13): submit once past the client check; a finding needs the server to store the forbidden value | coverable | |
| FM11 | A select or dependent input saves something other than what was chosen (label 'Canada', saved 'United States'); a child list keeps the old parent's options; a hidden required field blocks the submit | REV | intent-effect | **I-edit extension** to selects and radios (the shown label after the save) (D61: **R21s**) | coverable |  |

### 3.5 Persistence (create, read, update, delete)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| DB1 | Created item not saved or not shown | MRT A6f2; GN | intent-effect | I-create | covered | |
| DB2 | Edit not saved | MRT A6f7 | intent-effect | I-edit (typed fields); FM5 for the others | covered | |
| DB3 | Delete acknowledged but not done | MRT A6f7 | intent-effect | I-delete | covered | F06 |
| DB4 | Delete or edit hits the wrong or extra items | MRT A6f7 | intent-effect | R09 (removal on a revisit); **I-delete extension**: every other item of the list still there (D61: **R09d**) | partial |  |
| DB5 | The same item shows different attributes in different views (name, price, count, status, description) | MRT A6f4 (26 bugs, 3rd-largest class); GN incorrect display | cross-view | **R20 cross-view attribute registry** (D61: **R20f**) | coverable | BS12; BS15, BS18 (need the spec's data) |
| DB6 | Stale value after an update (cache) | MRT A7f1, A7f4 | cross-view | G2 (reload); **R20** with the write ledger: a view still showing the old value | partial | |
| DB7 | Phantom or missing list items | GN; WTP missing-element, data | in-page, intent-effect | R03, R05, R07, R09 | covered | BS01-BS08 |
| DB8 | Dangling reference after a delete (a product's deleted category shows blank or 404s; a deleted author's posts break) | MRT A6f7; EHR hidden connections | cross-view | R02 when the link is clicked; **R49 references**: after a delete, pages that showed the item are revisited | partial | |
| DB9 | After a sort, filter or page change, an inline edit or delete hits the item that used to be at that row, not the one clicked | MRT A6f7; REV | intent-effect | **I-edit/I-delete extension**: the changed item is the one whose row held the control (key: its link) (D61: **R09r**) | coverable |  |
| DB10 | Two routes for one action give different results or validation (quick-add vs the full form, inline edit vs the edit page, drag vs 'Move to', bulk vs single) | REV (logic flaws cluster where two paths do one job) | metamorphic | **R56 route parity**: the same values through both routes, item pages compared | coverable, low | |
| DB11 | A shown value differs from the response it was rendered from (field swapped, number rounded, a long id rounded past 2^53, a write answered 4xx/5xx while the page shows the new value) | PBF (model vs layout); REV | cross-view (payload) | **R57 payload** (M12) (D61: **R57e**) | coverable |  |
| DB12 | An archived, trashed or soft-deleted item still shows in active lists, search, autocomplete or counts; restoring it loses its children, attachments or position | MRT A6f7; REV | intent-effect | **R49 extension**: archive treated like delete for active views; restore compared with the item before (D61: **R49a**) | coverable |  |
| DB13 | A copy shares state with its original (editing the copy changes the original), or loses the original's children | REV | metamorphic | **R58 clone** | coverable, low | |

### 3.6 Derived values (counts, sums, ranges, times, order)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| DV1 | Count disagrees with the items listed (also 'Showing 11-20 of 95' against the rows shown) | WTP data | in-page | R04, R04b | covered | BS05-BS08 |
| DV2 | Count not updated after an action | VK calculation ("adding an item does not update the total") | intent-effect | I-toggle, R19 | covered | F05 |
| DV3 | Arithmetic: qty x price, subtotal, total | VK calculation | in-page | R06 (terms shown); **R06 extension**: percentage discounts, a shown tax rate times its base (D61: **R06s**) | partial |  |
| DV4 | Out-of-range numbers (negative quantity or price, % over 100, rating over its maximum) | VK calculation ("negative number of items discounts the total") | norm, probe | R01 (negative count); **R26 range**: page invariants plus a negative-quantity probe (D61: **R26p**) | partial |  |
| DV5 | Times and ages wrong | WTP data | cross-view | R08, R18 | covered | BS09-BS11 |
| DV6 | Order wrong (active sort not respected, 'latest' not newest first) | VK usability; WTP data | norm | R18 (time order); **R25 sort invariant** | partial | BS17 (label: spec) |

### 3.7 Search and filters

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| SF1 | Results that do not match | MRT A6f4 | probe, intent-effect | R05, I-filter | covered | F10, BS08 |
| SF2 | Search misses an item that exists | MRT A6f4 | probe | **R23 search recall**: search a known item's exact name | coverable | BS12 |
| SF3 | Filter composition (adding a filter adds results; clearing does not restore) | our analysis (metamorphic) | metamorphic | **R38c** filter composition (D60, T3: relevance search may widen) | coverable, low |  |
| SF4 | Personalised list holds the wrong items | | intent-effect | R07c | covered | F08 |
| SF5 | A facet or tab count ('Shoes (12)', 'Pending (3)') differs from the results it opens | SEG; VK | cross-view | **R38 facet counts** | coverable | |
| SF6 | Pages of a list overlap, skip items, or their union differs from the stated total (also 'load more' and infinite scroll) | SEG ordering | metamorphic | R11 (repeats); **R39 page union** | partial | |
| SF7 | A range filter (price, date, amount) returns items outside the range | SEG filtering | intent-effect | **R38 range filter** (I-filter extension to numbers and dates) | coverable | |
| SF8 | A search with metacharacters (`%`, `_`, `'`, `\`, `*`, `(`) returns everything, an error, or nothing for a name that contains them | MRT A3f5; REV | probe | **R23 variant**: search a known name that holds the character, and the bare character (D61: **R23m**) | coverable |  |
| SF9 | Autocomplete suggestions that do not contain the query, or a chosen suggestion opening another item | REV | intent-effect | **R61 typeahead** | coverable, low | |

### 3.8 Session, authentication, authorisation

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| SA1 | Logout does not end the session | MRT C1f6 | intent-effect | I-logout | covered | |
| SA2 | Session lost mid-flow (logged out without logging out), or the header says 'Log in' while private pages still load | MRT C1f2, C1f4 | metamorphic | **R30 session kept**: a login form appears with no logout in the trail | coverable, low | |
| SA3 | Wrong credentials accepted | MRT F1f2 | probe | **R28 wrong-password probe** | coverable | |
| SA4 | Resource used without permission (edit or delete another user's item) | MRT F1f6 | probe | R13 (same session); **R24 no-session probe** (D61: **R46w**) | partial | F07 |
| SA5 | Roles grant the wrong rights | MRT F1f8; OWA API5 | spec | R13 catches contradictions only; partly reachable with M7: a write the UI offers only to role A, replayed from role B's session, is accepted | spec | |
| SA6 | Private data reachable without the owner's session (cart, account pages) | VK client privacy; MRT C1f5 | probe | **R24 no-session probe** | coverable | |
| SA7 | Credential round trip fails: a new account cannot log in; after a password or email change the old one still works or the new one does not | MAI authentication; OWA WSTG-ATHN-09 | intent-effect | **R66 credential round trip** (sandbox accounts only) | coverable | |
| SA8 | Private content still reachable after a security change: Back after logout shows private pages (browser cache), a reset link works twice (needs a mailbox, WF3) | OWA WSTG-ATHN-06, -09; MRT C1f6 | probe | **R24 extension** (Back after logout) (D61: **R24b**) | coverable, low |  |

### 3.9 Collections and toggles

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| CT1 | Toggle not applied or not shown | GN | intent-effect | I-toggle, R07, R07b, R19 | covered | F05, BS01 |
| CT2 | Item added to a collection (cart, wishlist, compare, bookmarks, watch list) missing from that collection's page, or its badge count wrong | VK shopping cart | intent-effect | R07 (favourite and follow only); **R22 collection ledger** | partial | BS01 |
| CT3 | Undo does not restore | | metamorphic | R19 (second click) | covered | |
| CT4 | Collection lost on navigation | VK navigation | metamorphic | R09 (revisit); **R22** revisit | partial | BS02, BS03 |
| CT5 | A guest's collection (cart, wishlist) merged at login with lines duplicated or lost | VK shopping cart; REV | intent-effect | **R22 extension** (fill as guest, log in, compare) (D61: **R22g**) | coverable, low |  |

### 3.10 Workflows and business rules

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| WF1 | A multi-step flow loses data between steps (wizard, checkout) | VK | metamorphic | G1, FM6 | partial | |
| WF2 | Business rule values (tax rate, discount eligibility, shipping rule, reply nesting, sort label) | VK calculation | spec | DV3 when the page shows every term | spec | BS14, BS17 |
| WF3 | Notification or email not sent | VK ISP | intent-effect | In-app notification centres through **R47 badges**; email only on our own deployments, through a local mail catcher (Mailpit) the harness can read (D61: **R47m**) | coverable, low |  |
| WF4 | A later step of a flow opens by its address with an earlier step skipped (checkout without shipping, a wizard's step 3) | MAI access control; PortSwigger logic flaws; OWA API6 | probe | **R45 step skip** | coverable | |
| WF5 | A review, confirmation or history page differs from what was entered or chosen in earlier steps (quantity, dates, guests, price, address) | VK; REV | intent-effect | **R70 funnel ledger**: the values the worker typed or chose in the flow, compared with each later step | coverable | |
| WF6 | A flow broken off mid-way leaves a half-done state: a payment without an order, a seat or room still held after the booking failed | REV (sagas and compensation) | intent-effect | **R52 extension** with M11: one write of the flow aborted; flag only states the app's own error message denies (D61: **R52f**) | coverable, low |  |

### 3.11 Concurrency

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| CC1 | Race, out-of-order async response (results for 'ab' arriving after 'abc' and shown) | MRT B6f1, C1f2; OC | metamorphic | G2, G3 see the symptoms; M11 can provoke it by delaying the first of two responses (D61: **R77**) | partial |  |
| CC2 | Lost update: two sessions edit one item, one change vanishes with no warning | DBK | probe (two sessions) | **R46c** two-tab lost-update probe on own items (D60, controlled mode; T3: last-write-wins is a legal design) | coverable, low |  |

### 3.12 Environment and non-functional

| ID | Family | Sources | Status |
|---|---|---|---|
| EN1 | Browser incompatibility | MRT A1f1 (49 bugs, the largest class) | coverable: **R71** replays the trail in Firefox and WebKit (Playwright ships both) and compares item text and findings, not pixels; layout-only differences stay out |
| EN2 | Plugins, frames | MRT A1f3, B3 | out |
| EN3 | Server, framework or file-system configuration | MRT A3f4, A3f7, A3f8 | partial: only when it shows as a 5xx or an error page (RT1 HTTP 5xx signal, RT3 R01) |
| EN4 | Protocols, TLS, proxies | MRT E1-E3 | out |
| EN5 | Performance, scale, network, hardware, hosting, upgrades | VK | out |
| EN6 | Security beyond R12/R13/R24 (SQL injection, CSRF, buffer overflow, open redirects, CSV formula injection, mass assignment of fields the page does not show) | VK security; OWA | out: not a security scanner |
| EN7 | A control or content present at desktop width is missing or dead at phone width (menu that does not open, button off screen) | SET (settings as a test axis); REV | coverable: **R71** phone-width replay, then R29 on the controls the desktop trail used |
| EN8 | The app and an external provider disagree (payment provider declined, order shows Paid) | REV (cross-service defect studies, not read) | out: needs a provider sandbox; symptoms inside the app fall under SM2, WF6 |
| EN9 | Back-end events delivered twice or out of order | REV | out: needs back-end instrumentation; what shows in the browser falls under CC1, LG3 |

Groups 3.13-3.22 come from the workflows of the app types in section 4 (banking, invoicing, HR, booking,
project boards, dashboards, games), backed by the sources where one exists. Where only practitioner
write-ups or our own analysis back a family, the Sources cell says so.

### 3.13 Ledgers (money, stock, balances, points, leave days)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| LG1 | A transfer is not conserved (source minus x, destination not plus x; stock moved but not received) | FIN logic; our analysis | intent-effect | **R32 ledger** | coverable | |
| LG2 | A balance differs from its opening value plus its listed transactions; a running-balance column breaks | FIN algorithm; VK calculation | in-page | **R32 ledger** (running balance) | coverable | |
| LG3 | An accepted payment, transfer or order applied twice when resubmitted (back and submit, double click, reload) | PortSwigger logic flaws; DBK | metamorphic | **R33 resubmit** | coverable | |
| LG4 | Rounding and precision: wrong number of decimals, rounded lines that do not add up to the total, float noise | RND; VK calculation | in-page | R01 (float noise), R06 (tolerance); **R32** decimals per currency (D61: **R32d**) | partial |  |
| LG5 | The same amount shown with different currency, unit or decimals in different views; a currency switch not applied everywhere | VK i18n | cross-view | **R20** (amount attributes) | coverable | |
| LG6 | Zero, negative or above-available amounts accepted for a transfer, payment or withdrawal | VK calculation; PortSwigger | probe | **R26 range** probe (D61: **R26p**) | coverable |  |

### 3.14 Lifecycles (orders, requests, invoices, tickets, registrations)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| SM1 | Status not updated after a status action (approve, cancel, mark paid, close) | GN function failure | intent-effect | **R34 lifecycle** | coverable | |
| SM2 | Status differs between views or between accounts (the requester sees Pending, the approver Approved) | EHR unmet display needs | cross-view | **R20**, **R46** (second account) | coverable | |
| SM3 | An action works in a state the app itself calls closed (edit a cancelled order, pay a paid invoice, the page says 'locked') | PortSwigger workflow flaws | probe | **R34** (T2) (D61: **R34c**) | coverable |  |
| SM4 | An item listed under two exclusive status tabs, or under none | our analysis | cross-view | **R34** | coverable | |
| SM5 | Who may move an item to which state (self-approval, separation of duties) | MAI access control | spec | none | spec | |

### 3.15 Capacity (stock, seats, quotas)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| CP1 | More accepted than the page says is available ('only 3 left', seats, quota, a plan limit the page states such as 'Free plan: 3 projects') | VK; DBK | probe, declared | **R35 capacity** | coverable | |
| CP2 | Availability not updated after a purchase, booking or registration | VK calculation | intent-effect | **R35** | coverable | |

### 3.16 Scheduling (dates, intervals, time zones)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| TM1 | End before start accepted; duration shown differs from end minus start (including off-by-one counting: Mon-Fri shown as 4 days when the page counts days) | DT | probe, in-page | **R36 intervals** | coverable | |
| TM2 | One resource booked twice for overlapping times (room, appointment, leave days) | DBK | probe | **R36** (the same slot booked twice, one after the other; true races out of scope) (D61: **R36b**) | coverable |  |
| TM3 | Time-zone shift: the same event's time differs by whole hours between views or after a save | DT (time zones the largest factor) | cross-view | **R20** (time attributes) (D61: **R20t**) | coverable |  |
| TM4 | A calendar places an item on another day than its list or detail page says | our analysis | cross-view | **R20** (D61: **R20t**) | coverable |  |
| TM5 | A date-only value (birthday, due date, all-day event) moves by one day when the browser is in another time zone (stored as midnight UTC) | DT (time zones the largest factor); SET | metamorphic | **R71** time-zone replay (UTC-11 and UTC+14): the same item's date text must not change | coverable | |
| TM6 | Invalid or edge dates mishandled: 30 Feb or 31 Apr accepted; 29 Feb, a month end plus one month, or a daylight-saving day giving an error or a wrong date | DT (edge cases) | probe | **R36 extension** (date probes) (D61: **R36p**) | coverable |  |
| TM7 | A recurrence lists a different number of occurrences than its own rule states ('weekly, 5 times' listing 4) | our analysis (REV) | in-page | **R36 extension** (D61: **R36r**) | coverable, low |  |
| TM8 | A relative label disagrees with the shown date and the current time ('Overdue' on a future date, 'Upcoming' on a past one, 'expires in -2 days'); a timed state (hold, trial, code) does not end at the time the page states | DT; REV | in-page, metamorphic | **R72 relative time** (in-page now; the timed state with Playwright's fake clock, M10) (D61: **R72c**) | coverable |  |

### 3.17 Hierarchies (book > chapter > page, category > product, board > list > card)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| HI1 | Breadcrumb or parent link disagrees with where the item is listed | MRT D3f1 | cross-view | **R40 hierarchy** | coverable | |
| HI2 | A parent's child count differs from the children shown | WTP data | in-page | R04 (same page) | partial | BS05-BS07 |
| HI3 | A move is not reflected in both parents (still in the old, missing from the new) | our analysis | intent-effect | **R40** (D61: **R40m**) | coverable |  |
| HI4 | Children still shown, or orphaned, after their parent is deleted | EHR hidden connections | intent-effect | **R49 references** | coverable | |
| HI5 | A cycle accepted: an item moved into its own descendant, or made its own parent or manager | our analysis (REV) | probe | **R40 extension** (one move probe per tree kind; the probe is undone) (D61: **R40c**) | coverable |  |

### 3.18 Aggregates and reports (dashboards, charts, totals)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| AG1 | A dashboard tile or summary number differs from the count or sum of the list it summarises | CAT data management; MRT A6f4 | cross-view | **R41 aggregates** | coverable | |
| AG2 | A chart or report total differs from its table (when the chart's values are in the DOM text or ARIA labels) | CAT 3D/visualisation | cross-view | **R41** | coverable | |
| AG3 | A 'Total' row differs from the sum of its column (hours, points, amounts, quantities) | VK calculation | in-page | R06 (line totals to subtotal); **R06 extension**: any total row against its column (D61: **R06c**) | partial |  |

### 3.19 Several users (sharing, notifications)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| MU1 | Content one account published is not visible to another account (or to visitors) | GN; EHR interface | probe (second session) | **R46 second account** | coverable | |
| MU2 | A notification badge differs from the unread items; read state not kept | our analysis | cross-view | **R47 badges** (D61: **R47r**) | coverable |  |

### 3.20 Files and exports

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| AR1 | An upload not attached, shown with the wrong name or size, or an ordinary file rejected | MRT A3f4 | intent-effect | **R42 uploads** | coverable | |
| AR2 | A broken image or media file (404, zero size), or a 'Download' link that returns no file | MRT D2f1 | norm | **R02 extension** to `img`/`video` sources and download links (D61: **R02m, R02d**) | coverable |  |
| AR3 | An export, print view or PDF disagrees with the screen (rows, totals) | VK; CAT data management | cross-view | **R37 exports** (CSV first; PDF needs text extraction) | coverable | |
| AR4 | Importing an exported file does not restore the data | our analysis | metamorphic | **R37** round trip (D61: **R37i**) | coverable, low |  |
| AR5 | An import's report differs from what it stored (rows reported imported missing, rejected rows stored, duplicates merged without a word) | REV | intent-effect | **R37 extension** with a generated file of good, bad, duplicate and dangling-reference rows (D61: **R37i**) | coverable, low |  |

### 3.21 Settings

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| ST1 | A saved preference not applied (items per page, default sort, currency, language; a dismissed banner or saved consent choice shown again) | VK usability; SET | intent-effect | **R44 preferences** | coverable | |

### 3.22 Rich clients and games (drag and drop, local state, canvas)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| RC1 | A drag-and-drop reorder or move not kept after a reload; per-column counts not updated | CAT web application | metamorphic | **R48 client state** | coverable | |
| RC2 | Client-side state lost on reload (local-storage apps, unsaved drafts) | DLB (the web analogue of state lost on rotation) | metamorphic | G2 (reload); **R48** (D61: **R48s**) | coverable |  |
| RC3 | Undo then redo does not return to the same state | our analysis | metamorphic | **R48** (D61: **R48u**) | coverable |  |
| RC4 | A keyboard shortcut or pointer interaction ignored (no DOM change; on a canvas, no pixel change, RC8) | TRU action | metamorphic | **R29** variant (D61: **R29k**) | coverable, low |  |
| RC5 | Game or tool values break their own rules (negative score or lives, timer running backwards or while paused, restart not resetting every number, high score below the last score, 'Game over' with lives left) | TRU value, context state, event occurrence | norm | **R26** on numbers shown in the DOM | coverable | |
| RC6 | Canvas or 3D content wrong by the game's or chart's own rules (positions, bounds, collisions, what is drawn) | TRU graphics, position, bounds, collision | needs vision or game semantics | none | out (RC7 and RC8 take the parts the DOM or a screenshot hash can show) | |
| RC7 | SVG geometry broken: `NaN` or negative sizes in attributes, shapes outside their `viewBox`, a chart's bars or labels outside the plot area | TRU bounds; CAT SVG, 3D/visualisation | norm | **R75 canvas and SVG sanity** (M14) | coverable | |
| RC8 | A canvas or WebGL area blank, frozen (same screenshot hash while the app claims to animate), unchanged after input, or its context lost | TRU graphics; CAT game, 3D | norm, metamorphic | **R75** (screenshot hashes of the canvas only; no vision model) | coverable | |
| RC9 | The app does not start when its local storage holds `null`, garbage or an older shape of its own data (white screen) | DLB; REV | probe | **R48 extension** (one corrupted-storage reload per app) (D61: **R48c**) | coverable, low |  |

Groups 3.23-3.30 come from the reviewer chats (REV, D57): the families a check of the 106 above showed
to be missing, kept only where a spec-free check exists. Families the reviewers proposed that were already
here went into existing rows as notes (for example FM4, FM5, SF6, TM1, RC5); new families that fit an
existing group were added there (RT5, PR8-PR9, NV9-NV11, FM8-FM11, DB9-DB13, SF8-SF9, SA7-SA8, CT5,
WF5-WF6, EN7-EN9, TM5-TM8, HI5, AR5, RC7-RC9).

### 3.23 Feedback (what the app says about what it did)

The converse of intent-effect: the app's own message, toast or state contradicts what happened.

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| FB1 | An error shown but the write landed (seen on a revisit); a retry then creates a duplicate | GN function failure; REV | intent-effect | **R50 false failure**; with M11 the response is aborted after the server answered, then R33's resubmit | coverable | |
| FB2 | A message (toast, banner, an in-app assistant's reply) contradicts the action: success and error together, 'Deleted 3' when 1 changed, another item named, a message left over from an earlier action | GN incorrect display; REV | in-page, intent-effect | **R51 message fidelity**: the success-and-error-together form is built (D58, `evidence.py`, transient messages caught by a MutationObserver; T2); the count and name against the write ledger not yet (D61: **R51c**) | partial |  |
| FB3 | An optimistic update kept after its write failed (the page shows the new value, the response was 4xx/5xx or aborted, a reload shows the old one) | OC; REV | cross-view (payload), metamorphic | **R52 rollback** (M11, M12) | coverable | |
| FB4 | A confirmation names another item than the one clicked; Cancel or Esc still performs the action | MvD 5.3.1; REV | metamorphic | **R53 cancel probe** | coverable | |
| FB5 | Loading never ends while the network is idle; an empty state ('No results', 'Nothing here yet') shown where the request behind it failed | MvD 5.3.1; REV | implicit, norm | **R54 loading and empty states** | coverable | |

### 3.24 Bulk actions

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| BK1 | A bulk action changes a different set than the one selected (unselected or hidden rows, a selection kept across a filter or page change, 'select all' meaning the page vs all pages) | MRT A6f7; REV | intent-effect | **R55 bulk ledger**: selected set recorded before, changed set after | coverable | |
| BK2 | The outcome reported differs from the changes made ('20 updated' when 17 changed; a partial failure reported as success) | REV | intent-effect | **R55** | coverable | |

### 3.25 Identifiers

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| UQ1 | Two items share one address or one identifier the app shows as unique (slug, order or invoice number); a rename leaves the app's own links on the old address broken | MRT D3f1; REV | cross-view, norm | **R20 extension**: address to item must be one-to-one in the registry (D61: **R20u**) | coverable |  |
| UQ2 | A uniqueness the app enforces for exact duplicates ('already taken') bypassed by a variant: trailing space, another Unicode normal form, case where the app folds case elsewhere | VK i18n; REV | probe | **R16 variant**, armed only after the app rejected an exact duplicate (D61: **R16u**) | coverable, low |  |
| UQ3 | Digits lost in identifier-like values: leading zeros (zip, phone, account number), long numbers rounded (ids past 2^53 in JavaScript) | MRT A3f9; REV | intent-effect, cross-view (payload) | **R12b extension**; **R57** (D61: **R12c**) | coverable |  |

### 3.26 Context isolation (accounts, workspaces, organisations, patients)

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| CX1 | After logging out as A and in as B in the same browser, A's data shows for B (names, drafts, cart, local storage) | MRT C1f5; VK client privacy | probe (two accounts) | **R67 context sentinels**: each account writes a unique marker; B's pages must not hold A's | coverable | |
| CX2 | After switching workspace, organisation, store, project or patient, the old context's items stay on screen, in autocompletes, counters or after Back, or a write goes to the old context | EHR (data of another patient entered into a record; ECRI wrong record); OWA multi-tenant | probe | **R67** | coverable | |
| CX3 | Items listed, searched or counted for this account that are forbidden when opened (403), or counts that include them | BAC; REV | cross-view | **R67**; **R20** (D61: **R67f**) | coverable |  |

### 3.27 Relations, votes and ratings (many-to-many)

P-TREE covers one-to-many; these are the links between peers.

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| RL1 | The two sides of a relation disagree (A follows B but B's followers lack A; an assignee's 'my items' lacks the item; a tag's page lacks the tagged item), also after the relation is removed on one side or an end is deleted | PBF (model vs layout); GN independent views | cross-view | **R68 inverse relations** (D61: **R68t**) | coverable |  |
| RL2 | A relation added twice or to itself (assigned twice, the same tag twice, following yourself) | REV | probe | **R68** | coverable, low | |
| RL3 | A vote or rating summary disagrees with its parts: average differs from the mean of the ratings listed, a histogram not summing to the count, likes differing from the likers listed, one user's vote counted twice | VK calculation; REV | in-page | **M2 identity library** (section 5.1): **R06s** rating histogram and average (D60) | coverable |  |

### 3.28 Prices and carts

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| PX1 | Cart algebra broken: add A, add B, remove A differs from adding B alone; another adding order changes the total; quantity n then n-1 not giving n-1; quantity 0 not removing the line | VK shopping cart; SEG | metamorphic | **R69 cart algebra** | coverable | |
| PX2 | Removing a coupon or discount does not restore the total; one applied twice (reload, re-entry); a code the page itself calls expired or below its minimum accepted | VK calculation; PortSwigger logic flaws | metamorphic, declared | **R69**; **R34** (state the page states) | coverable | |
| PX3 | A shown saving disagrees with its prices ('-30%' against (was - now)/was, 'Save $X', 'spend $12 more for free shipping' against the threshold the page states) | VK calculation | in-page, declared | **M2 identity library**: **R06s** discount, saving and spend-more identities (D60) | coverable |  |
| PX4 | The chosen variant (size, colour, plan) differs in cart or order; price, stock or image not updated when it changes | VK shopping cart | intent-effect | **R22 extension** (D61: **R22v**) | coverable |  |

### 3.29 History and audit

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| HS1 | A history, activity or audit page omits, repeats or misattributes an action the run performed (wrong actor, item, time order) | EHR; REV | intent-effect | **R73 history ledger**: armed only for action kinds the page has listed before | coverable | |

### 3.30 Media players

| ID | Family | Sources | Evidence | Our rules | Status | Dev faults |
|---|---|---|---|---|---|---|
| MD1 | Player controls disagree with the media element: Play shown while playing, the position not moving while playing or moving while paused, two players playing at once, duration differing between list and player, the end not moving to the next item | REV (HTML media element state) | norm | **R74 media state** (M14: `paused`, `currentTime`, `duration`, `ended`) | coverable | |
| MD2 | Queue algebra broken: add not at the end, shuffle changing the set, shuffle off not restoring the order, the now-playing highlight on another track; a track count or total duration differing from the sum | REV | metamorphic, in-page | **R74** | coverable, low | |

### 3.31 Tally

| Status | Families |
|---|---:|
| covered | 26 |
| partial | 20 |
| coverable (proposed rule or none yet) | 106 |
| spec | 3 |
| out | 8 |
| **total** | **163** |

D61 changes: every extension or variant a row names is now built under its own rule id, named in the row ("D61: ..."; 48 rows), and `families.EXTENSIONS` maps each such phrase to the id that implements it, so the tracker counts an extension only once its id exists. Statuses are unchanged (they move with measurement, v5 plan 12.2).
D60 changes: every family marked covered, partial or coverable now names a rule that exists in the code (`docs/family_tracker.toml`: 152 built, 11 spec or out); FM7, SF3, CC2, RL3 and PX3 got rules (R33g, R38c, R46c, R06s), EN3 names its signals. **The statuses above are unchanged**: a status moves to covered only when its rule has found a seeded fault or passed its fixture test on a development app, which the D59 resweep and the pilots decide (v5 plan 12.2, I59).
D58 changes: RT5 covered (R57), FB2 partial (R51), both behind `capture_evidence`.
D57 changes: 57 families added (55 coverable; EN8 and EN9 out); EN1, PR5 and WF3 moved from out to
coverable (M10, M14, a local mail catcher); RC6 narrowed to what still needs vision.

The 25 covered families account for every seeded fault the harness has found. Of the 21 reachable
development faults (Conduit 8, BookStack 13), 19 are in covered or partial families; BS12 (DB5, cross-view)
and BS13 (PR7, missing control) are in coverable families with no rule yet. The 44 families added after the
workflow analysis of section 4 (37 in groups 3.13-3.22, plus NV8, DB8, SF5-SF7, WF4 and CC2) have no seeded
fault in our two development apps except HI2: Conduit and BookStack have no money, stock, dates to book,
approvals, uploads in use, or drag and drop. Some D57 families do have real workflows in the development
apps, so their rules can be tested there before any new app: RL1 (Conduit favourites and follows, BookStack
tags), DB11 and RT5 (Conduit's JSON API), UQ1 (BookStack slugs), HS1 (BookStack's audit log and
revisions), DB12 (BookStack's recycle bin), HI5 (BookStack moves), FB4 (BookStack delete confirmations),
NV9-NV10, TM5 and EN1 (any app).

## 4. App types, their workflows, and the primitives they share

Every app type below is built from a small set of **workflow primitives**. The rules are written per
primitive, not per industry, which is what lets them carry over: an unseen app exercises some subset of the
primitives, and each primitive brings its families with it.

| Primitive | What it is | Families |
|---|---|---|
| **P-CRUD** | items created, shown, edited, deleted | DB1-DB13, FM1-FM11, PR2, PR3, FB1-FB5, BK1, BK2, UQ1-UQ3 |
| **P-COLL** | an item put into or out of a collection (cart, favourites, follows, enrolments) | CT1-CT5, DV2, SF4, PX1, PX2, PX4 |
| **P-LEDG** | a quantity moved between holders (money, stock, points, leave days) | LG1-LG6, DV3, DV4, PX3 |
| **P-LIFE** | an item moving through states (order, request, invoice, ticket) | SM1-SM5, WF1, WF4-WF6, HS1 |
| **P-CAP** | a limited resource consumed (seats, stock, quota) | CP1, CP2 |
| **P-SCHED** | items placed in time on resources (bookings, leave, due dates) | TM1-TM8, DV5 |
| **P-TREE** | items inside items (book > page, board > card, category > product) | HI1-HI5, DV1 |
| **P-QUERY** | search, filter, sort, paginate | SF1-SF9, DV6, NV4, NV9 |
| **P-AGG** | numbers that summarise other numbers (counts, totals, dashboards, charts) | AG1-AG3, DV1, DV3, RL3 |
| **P-ID** | accounts, sessions, roles, private data | SA1-SA8, MU1 |
| **P-SHARE** | several users on the same data (comments, notifications, shared boards) | MU1, MU2, CC1, CC2, HS1 |
| **P-FILE** | uploads, exports, imports, print views | AR1-AR5 |
| **P-RICH** | client-side state (drag and drop, local storage, undo, canvas, games) | RC1-RC9, NV3 |
| **P-REL** | links between peers, many-to-many (follows, tags, assignees, attendees, members, votes, ratings) | RL1-RL3 |
| **P-CTX** | the active context: account, workspace, organisation, store, patient | CX1-CX3, CT5 |
| **P-MEDIA** | audio and video players, queues, playlists | MD1, MD2 |
| **P-NAV** | pages, links, anchors, controls, window widths and browsers (every app) | NV1-NV11, PR1, PR4-PR9, RT1-RT5, EN1, EN7 |

The table below rates each app type by how central each primitive is to its main workflows (● central,
○ present). The ratings are our judgment from the app type's usual workflows, not measured; the apps named
are those in our plan (`docs/00_research_plan.md`, section 5) or in the literature.

| App type | Apps (plan or literature) | Main workflows | CRUD | COLL | LEDG | LIFE | CAP | SCHED | TREE | QUERY | AGG | ID | SHARE | FILE | RICH | REL | CTX | MEDIA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Blog, social | Conduit; CAT social (10) | post, comment, follow, like, feed | ● | ● | | ○ | | | ○ | ● | ○ | ● | ● | ○ | | ● | | ○ |
| Wiki, CMS | BookStack; CAT information display (11) | write pages, organise books, permissions, revisions | ● | ○ | | ○ | | | ● | ● | ○ | ● | ○ | ● | ○ | ○ | | |
| Shop | PrestaShop (held out), Juice Shop; CAT e-commerce (10) | browse, filter, cart, checkout, order history, reviews | ○ | ● | ● | ● | ● | | ● | ● | ● | ● | ○ | ○ | ○ | ○ | ○ | |
| Banking | Parabank | accounts overview, transfer, bill pay, statements, loans | ○ | | ● | ○ | | ○ | | ● | ● | ● | | ○ | | | ○ | |
| Invoicing, accounting | InvoiceNinja | clients, invoices with line items and tax, payments, balance due, PDF | ● | | ● | ● | | ○ | ○ | ● | ● | ○ | | ● | | | ○ | |
| HR, leave | Timeoff, Gadael | request leave, approve, balances, team calendar, reports | ● | | ● | ● | ○ | ● | ○ | ○ | ● | ● | ● | ○ | ○ | ○ | | |
| Project boards | 4gaBoards, Agilefant; CAT web application (11) | boards, lists, cards, drag between columns, sprints, estimates | ● | ○ | ○ | ● | | ○ | ● | ○ | ● | ○ | ● | ○ | ● | ● | ○ | |
| Events, booking | Indico | events, timetable, rooms, registration, capacity, fees | ● | ○ | ○ | ● | ● | ● | ● | ○ | ○ | ● | ○ | ○ | ○ | ● | ○ | |
| Data management, admin | CAT data management (10) | tables, inline edit, import/export, charts | ● | | | ○ | | | ○ | ● | ● | ○ | | ● | ● | ○ | | |
| Marketing, landing | CAT marketing/landing (10) | sections, anchors, sign-up forms, call-to-action links | | | | | | | | | | | | ○ | ○ | | | ○ |
| Games, 3D, SVG | CAT game (19), 3D/visualisation (11), SVG (10) | play, score, timer, drag shapes, rotate views | | | | ○ | | | | | ○ | | | | ● | | | ○ |
| Health records | (literature only: EHR) | patients, orders, appointments, results | ● | | | ● | ○ | ● | ○ | ● | ○ | ● | ● | ○ | | ○ | ● | |
| Learning (LMS) | (none in plan) | courses, enrolment, assignments, grades, deadlines | ● | ○ | ○ | ● | ○ | ● | ● | ○ | ● | ● | ● | ● | ○ | ● | ○ | ○ |
| Multi-tenant SaaS, admin consoles | (none in plan; OWA) | workspaces, members and roles, seats, plans, settings | ● | ○ | | ○ | ● | | ○ | ○ | ○ | ● | ● | ○ | | ● | ● | |
| Messaging, mail, calendar | (none in plan) | threads, unread counts, send, invitations, recurring events | ● | ○ | | ○ | | ● | ○ | ● | ○ | ● | ● | ○ | ○ | ● | ○ | |
| Music, video streaming | (none in plan) | browse, play, queue, playlists, likes, resume | ○ | ● | | | | | ○ | ● | ○ | ○ | ○ | | ● | ○ | | ● |

Counting the ● marks over the 16 types: CRUD 11, ID 10, QUERY 9, LIFE 7, AGG 7, SHARE 7, REL 6, TREE 5,
SCHED 5, LEDG 4, FILE 4, RICH 4, CAP 3, COLL 3, CTX 2, MEDIA 1 (NAV is in every app). The last three rows
and the REL, CTX and MEDIA columns were added with D57; their ratings are judgment, like the rest. Our two
development apps exercise CRUD, COLL, TREE, QUERY, ID, SHARE, REL and NAV, so the families of LIFE, AGG,
LEDG, SCHED, CAP, FILE, RICH, CTX and MEDIA are untested by us so far.

**What this means for the held-out sets.** In CATTest, 40 of the 102 apps are games, 3D or SVG apps whose
state lives on a canvas or in SVG geometry. The DOM-text oracles can only see RC5 (numbers in the DOM),
the NAV families and implicit errors there. M14 adds what needs no vision model: SVG attribute sanity
(RC7), canvas liveness by screenshot hash (RC8), corrupted storage (RC9), and covered or overflowing
controls (PR5). Bugs that break a game's own rules on a canvas (RC6) stay out. Recall on these categories
will still be low; this is known before any CATTest run and should be pre-registered with D51.

## 5. Mechanisms: few checks, many families

The 106 coverable families do not need 106 rules. They fall into fourteen mechanisms; each is one piece
of code with per-primitive cues. M10-M14 were added with D57.

| Mechanism | Rules | Families | Cost |
|---|---|---|---|
| **M1 cross-view registry**: one item's attributes (name, amount, status, date, time, parent, count) agree in every view | R20, R40, R41, R47, R68, R70 | DB5, DB6, NV6, LG5, SM2, SM4, TM3, TM4, HI1, AG1, AG2, MU2, WF3, SF5, RL1, UQ1, CX3, WF5 | page facts already read |
| **M2 in-page arithmetic**: totals, running balances, column sums, durations, and the identity library (5.1) | R06 extension, R32, R36 (duration), R72 | DV3, AG3, LG2, LG4, TM1, TM7, TM8, RL3, PX3 | none |
| **M3 write effect per primitive**: after an accepted action the derived thing changes | R22, R32, R34, R35, R40, R42, R49, R50, R51, R55, R73 | CT2, CT4, CT5, LG1, SM1, SM3, CP2, HI3, HI4, AR1, AR5, DB4, DB8, DB9, DB12, FB1, FB2, BK1, BK2, PX4, FM11, HS1 | one fresh-tab view |
| **M4 input-domain probes**: values a correct app must reject or accept | R16 variants, R26, R35, R36, R45, R59, R63 | FM3, FM9, DV4, LG6, CP1, TM1, TM2, TM6, WF4, HI5, UQ2, SF8, NV10, RL2 | fresh-tab submits, capped |
| **M5 query relations** (SEG): an added filter gives a subset, a range filter stays in range, pages add up, a sort holds, the page size is kept, the address restores the list | R23, R25, R38, R39, R44, R61, R62 | SF2, SF3, SF5, SF6, SF7, SF9, DV6, ST1, NV9 | one probe per list kind |
| **M6 round trips**: reload, unchanged save, undo/redo, export/import, prefill, cancel, a second route, a copy, a cart's add and remove | R21a, R21b, R37, R48, G2, R53, R56, R58, R69 | FM4, FM5, RC1, RC2, RC3, RC9, AR3, AR4, FB4, DB10, DB13, PX1, PX2 | one probe per item kind |
| **M7 other sessions**: no session, a second account, a context switch with sentinel values | R24, R28, R30, R46, R66, R67 | SA2, SA3, SA4, SA6, SA7, SA8, MU1, SM2, CC2, CX1, CX2 | needs a second login in the gate replay (D50 rejected it for R13; to revisit) |
| **M8 resubmission**: an accepted write sent again | R33 | LG3, FM7, FB1 (retry) | one probe per money or order form |
| **M9 page norms**: anchors, images, referenced controls, DOM-visible game values, placeholders, contact links | R43, R02 extension, R31, R26, R01 extension, R10 extension, R54 | NV8, NV11, AR2, PR7, PR9, RC5, FB5 | none |
| **M10 environment replay** (SET): replay a trail under another time zone, locale, browser engine, phone width, or a fake clock; what the data means must not change | R71, R72 (clock) | TM5, TM8, FM9, EN1, EN7 | one replay per axis, in the gate's replayer (Playwright: `timezone_id`, `locale`, `viewport`, Firefox/WebKit, `page.clock`) |
| **M11 network fault injection**: abort a write's response after the server answered, fail it before, or delay one response behind another | R50, R52 | FB1, FB3, WF6, CC1 | one probe per write form; Playwright routing (`route.fetch` then `route.abort`, `route.abort`, delayed `route.fulfill`) |
| **M12 payload oracle** (PBF): the page agrees with the JSON it was rendered from; REST semantics (after a 201 the item opens, after a delete it 404s, a GET changes nothing) | R57, R52 | RT5, DB11, UQ3, FB3 | bodies kept since D58 (`evidence.py`, `capture_evidence`): same-origin xhr/fetch JSON, 200 KB cap, plus what each write sent. Values are matched by identifiers and observed relations, not by field names alone: a response can be partial or transformed before rendering, and a shown value can come from a cache |
| **M13 declared constraints**: the page's own attributes and text as a partial spec | R60, R12b extension | FM8, FM10, CP1 (plan limits), PX2, PX3 (thresholds) | attributes read with the form; one past-the-client submit per field kind |
| **M14 DOM geometry and media state**: what the DOM can say about layout, widgets, SVG, media and canvas without a vision model | R64, R65, R74, R75 | PR5, PR8, RC7, RC8, MD1, MD2 | a few `evaluate` calls per page; screenshot hashes of canvas elements only |

### 5.1 Invariant library (for M2)

An equation can be universal while the choice of quantities that go into it is not. So every entry has a
**strength**, and the rule arms only when its **preconditions** are visible on the page:

- **S, strong**: arithmetic over terms the page itself presents as parts of one whole (a total and its
  listed components, a percentage and its two numbers). Reported at T2, T1 after measurement.
- **C, conditional**: holds only when the page shows that the categories are exclusive and exhaustive,
  the population is the same, or no adjustment exists. Reported at T2 at most; T3 if a precondition is
  inferred rather than shown.
- **K, needs a contract**: a policy. Never reported from industry convention alone (section 7).

Shared preconditions for every entry: all terms visible together (or on pages of the same entity), the
same unit and currency, no 'estimated', 'approx.', 'sample', 'excl. tax', 'pending' or 'adjustment' word
next to a term, and the page's own rounding (a difference within half a unit of the last digit shown, per
term, is not a violation). Identities the app already covers elsewhere (transfer conservation, running
balance, line totals) are left out. Taken from REV's industry sweep, with the class added after the second
review (D58); dropped entries are in section 10.

| App kind | Invariant | Class | Extra preconditions |
|---|---|---|---|
| Accounting | Σ debits = Σ credits | S | both columns of one journal or trial balance |
| Accounting | ageing buckets sum to the total receivable | C | buckets shown as a partition of that total (no 'unapplied credits' row) |
| Accounting | closing = opening + invoices - payments | C | a statement that lists every movement type it shows |
| Accounting | a refund is at most what was paid | K | overpayment and goodwill refunds exist |
| Accounting | a partly paid invoice is neither 'Paid' nor 'Unpaid' | K | some apps keep 'Unpaid' until fully paid |
| Accounting | a tax report total = Σ invoice tax | C | same period and filter on both pages |
| Orders, trading | filled + remaining = ordered | S | the three on one order |
| Orders, trading | position = Σ fills; value = quantity x price | S | price is the one shown next to the value |
| Orders, trading | bid < ask | C | a live order book that is not crossed by design or auction |
| Inventory | on hand = Σ receipts - Σ issues | C | the movement list is complete for the item (no 'adjustments' type hidden) |
| Inventory | received ≤ ordered; reserved ≤ on hand | C | the app has no over-receipt or back-order state |
| Inventory | an order's total = Σ its lines | S | (R06 already) |
| HR, payroll | gross - deductions = net | S | all deductions listed |
| HR, payroll | a timesheet's days sum to its week total | S | |
| HR, leave | entitlement - taken - pending = remaining | C | the page names these four and no carry-over or adjustment |
| HR | headcount on the chart = the employee list | C | same scope (department, active only) |
| Education | progress % = done / total | S | done and total shown |
| Education | 'Completed' if and only if 100% | C | no optional items |
| Education | a quiz score = the answers marked correct | C | equal weights shown or stated |
| Booking | total = nights x rate + the fees listed | S | every fee listed; taxes either listed or stated as included |
| Booking, events | guests ≤ the capacity shown | S | |
| Events | sold + free = capacity | C | no 'held' or 'blocked' category |
| Events | 'Sold out' with an enabled buy button | S | the button is for the same event and date |
| Social | likes = the likers listed; comment count = the comments | C | the list is complete (no 'and 12 others' or pagination) |
| Q&A | at most one accepted answer | C | the app is single-acceptance (most are) |
| Reviews | the average = the mean of the ratings listed; a histogram sums to its count | C | every rating listed (no weighting, no hidden reviews) |
| Shop prices | '-x%' = (was - now) / was; 'Save $y' = was - now | S | was and now for the same variant |
| Shop prices | 'spend $z more' = threshold - subtotal | S | the threshold is stated on the page |
| Analytics | Σ children = parent in a drill-down | C | additive measure; no 'other', overlap or adjustment row |
| Analytics | funnel stages never rise | C | one cohort and one time window for every stage |
| Analytics | unique ≤ total; Δ% = (now - before) / before | S | same metric |
| Analytics | shares sum to 100 within rounding | C | shares labelled as parts of one total |
| Boards | a sprint's points = Σ its cards; a column's count = its cards | S | all cards visible (no collapsed swimlanes) |
| Boards | a WIP limit shown is not exceeded | K | many apps allow exceeding with a warning |
| Files | a folder's size = Σ its children | C | sizes of every child shown, same unit |
| Files | used storage = Σ files; the quota bar agrees | C | one account's files, no versions or trash counted elsewhere |
| Crowdfunding | % = raised / goal; the bar's width ≈ % | S | |
| Crowdfunding | raised = Σ the donations listed | C | the list is complete |
| Catalogues | price per m² = price / area | S | |

### 5.2 Precision guards shared by the new rules

Many D57 rules have benign look-alikes: search-index lag; pinned, sponsored or personalised items;
display rounding; time zones the user chose; A/B variants; shuffled or 'recommended' orders; live values
(tickers, '5 min ago'); test-mode banners; soft delete or last-write-wins by design. Three guards apply to
all of them, on top of each rule's own. Revised after the second review (D58): a guard must not quietly
remove a real fault from the denominator, so every guard **logs** what it suppressed (rule, page, reason),
and the suppression count per guard is reported with the recall funnel (v5 plan, section 3).

1. **Twice-loaded pages.** Each page kind is loaded twice when first met; nodes whose text changes between
   the two loads are marked **volatile**. Volatile nodes are left out of equality-across-time rules (G2,
   R09, R20 between two visits) only. Rules about one moment (in-page arithmetic, R01) and temporal rules
   (a persisted identifier that changes, a stale result overwriting a newer one, CC1) still read them.
2. **Two cues to arm.** A rule with one cue does not fire, but the check is recorded as **unarmed (one
   cue)**, so its arm rate is measured. A second, independent piece of evidence (the payload, another view)
   can promote it.
3. **Reproduce in an equivalent context.** A candidate is captured when it happens (actions, page,
   network timeline, messages). The gate replays it from the recorded prefix in a fresh context restored
   to the same session (D49), which keeps the preconditions. 'Persists in a fresh tab after a reload' is
   required only for the rules whose meaning is persistence (cross-view, payload vs page, R20), not for
   rules about a moment (R51, FB3, CC1). Known gap: the restored context has cookies and local storage but
   not session storage (v5 plan, C1).

## 6. Proposed rules

All are deterministic and use no LLM tokens. Each is replayable by the gate (it needs only the worker's own
session, no session, or, for M7, a second login). Probes are capped per run like the existing ones.

### 6.1 From the taxonomies (section 3.1-3.12)

| Rule | Families | Check | Precision guards | Tier |
|---|---|---|---|---|
| **R20 cross-view attribute registry** | DB5, DB6, NV6 | For every entity the run sees (key: its link), record the attributes shown with it per view: name, numbers next to a unit or currency, status words. Two views at the same point in the ledger disagree | Only attributes in the item's own card or heading; numbers compared only with the same unit; skip after any write to that entity until a fresh view; truncated names compared by prefix | T2 |
| **R21a edit prefill** | FM4 | An edit form opened for an item holds the values its page shows (name, numbers, selected options) | Only fields whose label names a shown attribute; rich text compared as plain text | T2 |
| **R21b unchanged save** | FM5, DB2 | Once per entity kind: open the item's edit form in a fresh tab, submit it unchanged, compare the item page before and after | Ignore ages and 'updated' times; skip forms with password or file fields; writes recorded as `mutation` in the ledger | T1 |
| **R22 collection ledger** | CT2, CT4, DV2 | An accepted 'add to X' (cart, wishlist, compare, bookmark, watch, save) puts the item on X's page and raises X's badge by the quantity added; 'remove' takes it off | X found by a nav link whose text matches the verb's object; only after a 2xx write | T1 |
| **R23 search recall** | SF2 | Search for the exact name of an item the run saw (not one it just created, to allow index delay); it must be in the results | Names of 2+ words or 6+ characters; skip if the page has no result list; one probe per entity kind | T2 |
| **R24 no-session probe** | SA4, SA6 | Open the worker's own edit addresses and account/cart pages in a context with no cookies; they must lead to a login page or 401/403, not show the data | Pages the app shows publicly (seen while logged out) excluded | T1 |
| **R25 sort invariant** | DV6 | When a sort control is active ('Price: low to high', 'Name A-Z', 'Newest', a sorted column header), the visible keys follow it | Only keys parsed from every item; ties allowed; pinned or sponsored items at the top skipped | T2 |
| **R26 range** | DV4 | Shown quantities, prices and counts are not negative, percentages are 0-100, ratings are within their shown maximum; a quantity field that accepts a negative value and saves it | Minus signs on refunds, credits, discounts and temperature-like units skipped | T2 |
| **R27 input kept** | FM6 | After a rejected submit, the fields the agent filled still hold their values (passwords excepted) | Only when the page shows a validation message | T2 |
| **R28 wrong-password probe** | SA3 | In a fresh context, log in with the worker's name and a wrong password; the app must not log in | Once per run; login form found by its password field | T1 |
| **R29 dead control** | NV7 | A clicked button whose label is an action verb (Save, Add, Apply, Remove, Update) causes no request, no URL change and no DOM change | Disabled controls, toggles already counted, menus that open skipped | T2 |
| **R12b echo fidelity** | PR2 | A value typed with `& < ' é ü 中` is shown exactly as typed after the save | Only the agent's own saved values; rich-text fields skipped (as R12) | T2 |
| **R30 session kept** | SA2 | A page shows a login form though the trail has no logout and the session's cookie was set | Login pages the agent navigated to on purpose skipped | T2 |
| **R31 referenced control** | PR7 | The page text names a control it lacks | Only quoted or capitalised names that match a control label seen on another page of the same app | T2 |
| R06, R01, I-delete extensions | DV3, PR4, DB4 | As in the table rows | As the base rule | as base |

### 6.2 From the workflow primitives (section 3.13-3.22)

| Rule | Families | Check | Precision guards | Tier |
|---|---|---|---|---|
| **R32 ledger** | LG1, LG2, LG4 | After an accepted transfer of amount x from A to B (both shown to this account), A fell by x and B rose by x; a balance equals the opening value plus the listed transactions; a running-balance column steps by each row's amount; amounts carry the currency's usual decimals | Only accounts the worker owns; pending or scheduled transfers skipped; one-cent tolerance per row | T1 (conservation), T2 (others) |
| **R33 resubmit** | LG3, FM7 | Once per money or order form: after an accepted submit, go back and submit the same values again in the same session; a second identical record (transaction, order, payment) without a warning | Only forms whose verb is pay, transfer, order, checkout, book, register; the duplicate must match amount and target | T2 |
| **R34 lifecycle** | SM1, SM3, SM4 | A status action (approve, reject, cancel, close, mark paid, publish) changes the status word shown in every view of the item; an item sits under exactly one exclusive status tab; an action the item's own page calls unavailable ('cancelled', 'locked', 'closed') still succeeds | Status words from a closed list per language; tabs counted exclusive only when their counts add up to an 'All' count | T2 |
| **R35 capacity** | CP1, CP2 | A shown availability ('3 left', '12 seats', 'quota 5') falls by the amount taken after an accepted purchase or booking; asking for more than shown is accepted | Only numbers next to left/available/remaining/seats/stock; other users' activity on shared apps makes it T2 | T2 |
| **R36 intervals** | TM1, TM2 | A form with start and end accepts an end before the start; a shown duration differs from end minus start; the same resource booked twice for the same slot, one booking after the other, both accepted | Only when the field labels say start/end or from/to; overlap only for a resource the app itself marks booked or unavailable in its own view | T2 |
| **R37 exports** | AR3, AR4 | A CSV export of a list has the list's row count and totals; importing it back changes nothing | CSV and print views only (PDF later); filters applied to both | T2 |
| **R38 facets and range filters** | SF5, SF7 | A facet or tab count equals the results it opens; a range filter (price, date, amount) returns only items in the range | Counts and values parsed from every result item; 'from' price variants skipped | T2 |
| **R39 page union** | SF6 | Pages 1..n of a list have no item twice and add up to the stated total | Only lists with a stated total and at most 5 pages | T2 |
| **R40 hierarchy** | HI1, HI3 | An item's breadcrumb parent lists the item; after a move, the old parent no longer lists it and the new one does | Breadcrumbs found by `nav[aria-label*=breadcrumb]` or a chain of links ending in the page heading | T2 |
| **R41 aggregates** | AG1, AG2 | A dashboard tile or summary number whose label names a list ('Open tickets 12', 'Total due $340') equals that list's count or sum | Label must match the list's heading or tab; time-window labels ('this month') require the list's filter to match | T2 |
| **R42 uploads** | AR1 | An accepted upload appears on the item with the file's name and a plausible size, and its link opens | Small generated files (text, PNG); skipped where no file field exists | T2 |
| **R43 anchors** | NV8 | An in-page link `#x` has a target element `id=x` or `name=x` | Links handled by script (`#`, `#!`, routers) skipped | T1 |
| **R44 preferences** | ST1 | After a saved page-size choice, lists show at most that many items; a saved currency or language is used on the next page | Only settings whose control and effect can be read (numbers, currency symbols, the page's `lang`) | T2 |
| **R45 step skip** | WF4 | A later step of a multi-step flow (address seen in the trail) opened in a fresh tab before its earlier steps were done shows the step's form instead of sending the user back | Only flows the worker went through in order once; the probe uses a fresh session state copied from before step 1 | T2 |
| **R46 second account** | MU1, SM2 | Content this worker published is shown to another worker's account; a status shown to the requester matches the approver's view | Needs two sessions in the gate replay (see M7) | T2 |
| **R47 badges** | MU2 | A badge count next to a nav link equals the unread or pending items on the page it opens | Badges parsed only as standalone numbers inside the link | T2 |
| **R48 client state** | RC1, RC2, RC3 | After a drag-and-drop move or a local edit, a reload shows the same order and contents; undo then redo returns to the same DOM text | Only items with text; animations awaited | T2 |
| **R49 references** | DB8, HI4 | After an accepted delete, the pages where the item was listed or linked are revisited; they no longer list it, and no link to it 404s without the app saying it was removed | Revisits capped; activity feeds may keep the name as history | T2 |
| **R26 extension** | LG6, RC5 | Zero, negative or above-balance amounts accepted for a transfer or withdrawal; DOM-visible game values (score, lives, time) out of their own range | As R26 | T2 |
| **R02 extension** | AR2 | `img`/`video`/`audio` sources that 404 or load with zero size | Lazy-loaded media awaited; tracking pixels (1x1) skipped | T1 |

### 6.3 From the reviewer additions (D57)

All guards of section 5.2 apply as well.

| Rule | Families | Check | Precision guards | Tier |
|---|---|---|---|---|
| **R50 false failure** | FB1 | After a write the page called failed, a revisit shows its effect (item created, value changed). Under M11: the server's answer is fetched, then the response is aborted to the page; a retry must not make a second record | Only writes with a typed value the run can find again; the abort probe once per form | T1 |
| **R51 message fidelity** | FB2 | A success and an error message shown together; a count in the message ('3 deleted') differing from the items the write ledger saw change; a message naming another item than the one acted on | Messages found by role `alert`/`status` or toast containers; counts only when the message has one number | T2 |
| **R52 rollback** | FB3, WF6 | The page shows the new value while the write's response was 4xx/5xx or aborted, and a reload shows the old one; after an aborted step of a flow, a related view shows the half-done state the error message denies | Only same-origin writes; WF6 only for flows the worker finished once without the abort | T2 |
| **R53 cancel probe** | FB4 | Open a destructive confirmation, press Cancel (then Esc); the item is unchanged. The confirmation's text, when it names an item, names the one clicked | Once per confirmation kind; browser `confirm()` dialogs dismissed by the harness | T1 |
| **R54 loading and empty states** | FB5 | A spinner, skeleton or `aria-busy` still shown 10 s after the network went idle; an empty-state text shown where the request behind the list failed | Spinners matched by class/role words; long polls excluded | T2 |
| **R55 bulk ledger** | BK1, BK2 | Record the selected rows (by link) before a bulk action; the changed set must equal the selected set, and the message's count the changed count | 'Select all' read as the page unless the app says all pages; only actions with a visible effect per row | T2 |
| **R56 route parity** | DB10 | When an item kind has two create or edit routes, the same values through each give the same item page | Only fields both routes show; ages and authors ignored | T3 |
| **R57 payload** | RT5, DB11, UQ3 | A 200 JSON response with an `error` field or a non-empty GraphQL `errors`; a shown attribute (name, title, count, price, id) differing from the field of the same name in the response the page rendered; a 4xx/5xx write whose new value the page shows | Field names matched to visible labels only; numbers compared after the page's own rounding; responses of the app's origin | T2 |
| **R58 clone** | DB13 | After 'copy' or 'duplicate', editing the copy leaves the original unchanged; the copy has the original's children | Once per item kind; the copy is deleted after | T2 |
| **R59 number format probe** | FM9 | A number typed with a thousands separator or a decimal comma is saved as another number with no message | Number fields only; the probe is undone | T3 |
| **R60 declared constraints** | FM10, FM8 | Submit once with the page's client checks removed (attributes stripped by `evaluate`): a value past `maxlength`, `max`, `pattern`, a blank `required`, a changed read-only field. A finding needs the server to store it | Once per form kind; writes recorded as `mutation`; skipped on login and payment forms | T2 |
| **R61 typeahead** | SF9 | Suggestions for a typed query do not contain it (after case and accent folding); choosing one opens another item | Fuzzy-search apps: skipped when no suggestion contains any query word | T3 |
| **R62 address replay** | NV9 | Open the current list address in a fresh tab of the same session; the list's items and the active controls match | Unstable nodes (5.2) excluded; only addresses with a query string or a hash | T2 |
| **R63 address probes** | NV10 | From item addresses seen in the run: a very large id, a negative id, a non-numeric id, `page=0`, `page=9999`. A 5xx, a 200 page with no item and no 'not found' text, or another item's page | Once per address pattern; apps that show the nearest page for out-of-range `page` accepted when the page says so | T1 (5xx), T2 (others) |
| **R64 control state** | PR8 | `aria-checked`/`aria-selected`/`aria-expanded` disagreeing with the control's visible or saved state; two checked options in one radio group; the selected tab's panel hidden | Only standard roles; animations awaited | T2 |
| **R65 geometry** | PR5 | A visible action control whose centre `elementFromPoint` returns an element outside it; `scrollWidth > clientWidth` on the page body; a text node whose colour equals its background | No modal or menu open; sticky headers given their height | T2 |
| **R66 credential round trip** | SA7 | A freshly registered account logs in; after a password change the old password fails and the new one works | Sandbox accounts only; once per run | T1 |
| **R67 context sentinels** | CX1, CX2, CX3 | Each account or context writes a unique marker (`ctxA-7f3`); after a logout and login as another account, or a context switch, no page, autocomplete or count of the new context holds the old marker; a listed item that answers 403 | Needs M7; history pages of shared items excluded | T1 |
| **R68 inverse relations** | RL1, RL2 | After 'A follows B' (assign, tag, enrol), B's side lists A, and both sides drop it after an unfollow on either; adding the same relation twice or to oneself is refused or shown once | Relation pages found by a link next to the relation control; counts lag allowed for one reload | T2 |
| **R69 cart algebra** | PX1, PX2 | add A, add B, remove A gives the total of B alone; another order gives the same total; quantity 0 removes the line; removing a coupon restores the total | Taxes and shipping fixed between the compared states; prices read with currency | T2 |
| **R70 funnel ledger** | WF5 | Values typed or chosen in a flow (quantity, dates, guests, address, variant) appear unchanged on its review, confirmation and history pages | Values matched by label; formatting differences (dates, currency) normalised | T2 |
| **R71 environment replay** | TM5, EN1, EN7, FM9 | Replay the trail per axis and compare **normalised** values, never raw text: time zone (UTC-11, UTC+14): instants compared in UTC, date-only values must keep their calendar date; locale: numbers and dates parsed with that locale, entity identity and quantities equal, labels may be translated; browser (Firefox, WebKit): item attributes and findings equal, layout ignored; width (375 px): every control the desktop trail used is reachable (possibly behind a menu) and works | The app's own stated time zone or locale is applied first; a browser or width the app says it does not support is skipped | T2 |
| | | Fake clock (R72): Playwright's clock moves the browser's time only; a timed state the server decides is reported only when the page itself counts down in the browser | | |
| **R72 relative time** | TM8 | 'Overdue', 'Upcoming', 'Today', 'in n days' against the shown date and the browser's now; with the fake clock moved past a stated end (hold, trial, code), the state ends | Dates the app marks as in another time zone converted first | T2 |
| **R73 history ledger** | HS1 | Each write the run made appears once in the app's history, activity or audit page with this account as the actor and the right item, in time order | Armed per action kind only after the page has listed that kind once | T2 |
| **R74 media state** | MD1, MD2 | Play/Pause label against `paused`; `currentTime` advancing while playing and still while paused; one element playing at a time; duration equal across list and player; shuffle keeping the set | Live streams (`duration` infinite) skipped; autoplay blocks awaited | T2 |
| **R75 canvas and SVG sanity** | RC7, RC8 | SVG attributes parse to finite numbers and shapes lie inside their `viewBox`; a canvas is not blank, changes after input and over time when the page animates, and keeps its WebGL context | Hashes of the canvas element only; static charts are not expected to animate | T2 |
| Extensions | DB9, DB12, HI5, UQ1, UQ2, FM8, FM11, SF8, NV11, PR9, SA8, CT5, PX4, TM6, TM7, AR5, RC9 | As named in each family's row: I-edit/I-delete identity, R49 archive, R40 cycle, R20 address one-to-one, R16 uniqueness variants, R12b length and digits, I-edit selects, R23 metacharacters, R10 contact links, R01/R02 placeholders, R24 Back after logout, R22 guest merge and variants, R36 dates and recurrences, R37 import report, R48 corrupted storage | As the base rule | as base |

## 7. The spec ceiling

Some faults show nothing a generic tester can contradict. BookStack's BS14 (reply nesting) and BS17
(sort label) are of this kind, and so is any wrong business-rule value the app shows consistently
everywhere (a wrong tax rate, interest, fee, leave allowance or working-day count). Those families (SA5, SM5,
WF2) stay out of the recall denominator for a tester without a spec. BS15 and BS18 are a different case:
R20 could catch them if exploration reached the data they need (`reachable = false` in the catalogue: they
need literals only the benchmark's test specification has). Canvas and 3D faults that break a game's or
chart's own rules (RC6) are out of scope, not beyond the ceiling: they need a vision check or game
semantics.

The page itself sometimes states part of its spec (M13, evidence kind 'declared'): a threshold ('free
shipping over $50'), a limit ('Max 5 MB', 'Free plan: 3 projects'), a field constraint. Where it does, a
WF2-like rule becomes checkable (PX3, CP1, FM10), which lowers the ceiling a little. What stays above it:
rollback and refund policies (WF6 flags only what the app's own message denies), subscription and
entitlement policies, who may approve what (SM5: an Approve button shown to the item's own requester is at
most a T3 cue, since admins often may), and grading or eligibility rules.

WebTestPilot's 0.96 precision and recall (`literature/summaries/01_webtestpilot-fse26.md`) is measured per
test flow with the requirement in hand, so it is the spec-ful bar, not a target for this table.

## 8. How generality is measured without touching the held-out apps

A rule that only fired on our two apps is not evidence it works elsewhere. In this order:

1. **Family benchmark (development).** For each coverable family with no seeded fault in our apps, write
   one or two synthetic faults from the family's row text, before writing the rule. BookStack takes
   them through its client-side injector, Conduit through a server-side fault flag. Recall per family is
   then measured on development apps. Faults written by us are easier than real ones; this is reported as a
   threat, not as a held-out result.
2. **Development apps for the missing primitives.** Conduit and BookStack have no ledger, lifecycle,
   schedule, capacity, file or rich-client workflows. Two apps already in the plan's coverage track
   supply them: **Parabank** (banking: LEDG, AGG, QUERY by date) and **Timeoff** (HR leave: LIFE, SCHED,
   LEDG of leave days, two roles for M7). They are used for development only, with faults we seed
   (written before the rules, as in step 1). Several D57 families need no new app: RL, DB11/RT5, UQ1,
   HS1, DB12, HI5, FB4, NV9-NV10 and M10's replays run on Conduit and BookStack (section 3.31). CTX and
   MEDIA have no development app yet; their rules wait for one or rely on synthetic pages only.
3. **Clean-app false alarms.** Every new rule runs in the resweep of the clean apps (`scripts/resweep_v5.sh`
   with `--clean`); a rule whose false alarms per run exceed the D55 bar is demoted or dropped.
4. **Held-out test.** PrestaShop (D51) after the v5 lock, with recall counted over all of its reachable
   faults whatever family they belong to; faults in spec families reported separately. InvoiceNinja and
   Indico (WebTestPilot, not yet opened by us) stay unread so they can serve as further held-out apps;
   CATTest is held out with its category limits pre-registered (section 4).

## 9. Order of work

Superseded as the work plan by `docs/v5_plan.md` (D58), which orders rule work after the recall-funnel
instrumentation and the reach fixes. The ranking below still orders the rules among themselves.

Ranked by the number of app types whose central primitives a mechanism serves (section 4), the number of
families, and false-alarm risk:

1. **M1 cross-view registry** (R20, then R40, R41, R47) and **M6 edit round trip** (R21a, R21b): CRUD, AGG,
   LIFE and TREE are central to 11, 7, 7 and 5 of the 16 app types, and DB5/A3f9 are the largest real-bug
   classes in MRT;
2. **M5 query relations** (R23, R25, R38, R39, R44) and **M2 arithmetic** (R06 extension, R32 running
   balance, durations);
3. **M3 write effects** (R22, R34, R35, R49, R42) and **M4 input probes** (R26, R36, R45, R16 variants);
4. **M7 other sessions** (R24 and R28 first, they need no second login; then the gate change for R30, R46)
   and **M8** (R33);
5. **M9 page norms** (R43, R02 extension, R31) and the small R27, R29, R12b, R01 extensions;
6. exploration E3 (blind spots); the family benchmark with Parabank and Timeoff; resweeps; then the v5 lock.

Rules from step 1 work on Conduit and BookStack today; steps 2-4 need Parabank and Timeoff running to be
tested on real workflows rather than only on synthetic faults.

**D57 additions, placed in this order.** The D57 rules that run on the development apps and cost little go
with step 1-2, before the v5 lock: R57 payload (M12, after the body capture), R62 and R63 address probes,
R53 cancel probe, R68 inverse relations, R73 history ledger, R64 control state, and R71 limited to the
time-zone replay. The rest wait for the apps or the tooling they need and are ISSTA work after the lock:
M11 fault injection (R50, R52), the rest of M10 (browsers, phone width, fake clock), M14 (R65, R74, R75),
context isolation (R67, needs M7), prices and carts (R69, needs a shop dev app other than PrestaShop),
and the M2 identity library (needs Parabank, Timeoff or synthetic pages).

## 10. Reviewer suggestions not taken (D57)

The reviewer chats proposed about 81 families, 5 mechanisms and an identity library. Kept: the 57
families of D57, the mechanisms as M10-M14, the library as 5.1, the guards as 5.2. Dropped or folded in:

| Suggestion | What was done | Why |
|---|---|---|
| Grammar from counts ('1 items') | dropped; '-1 days' goes to R26 | cosmetic, not a functional fault |
| Filter or sort not kept in the URL | dropped; NV9 keeps the case where URL and page disagree | leaving state out of the URL is a design choice |
| Create form not reset after success; a reopened modal keeping input | dropped | often a deliberate draft |
| Currency round trip (USD to EUR to USD drifts) | dropped | rounding at two rates is legitimate |
| Stale footer year; consent cookies set before consent | dropped | not functional, or compliance (PR6) |
| Open redirect; CSV formula injection; mass assignment of fields the page does not show | into EN6 (out) | security scanning, outside this harness's scope |
| Saving one's own item unchanged says 'already taken' | into FM5 | the unchanged-save check (R21b) catches it |
| Editing B shows A's values | into FM4 | the prefill check (R21a) catches it |
| Infinite scroll duplicates | into SF6 | the page-union check |
| 'Showing 11-20 of 95' vs rows shown | into DV1 | a count against the list |
| Hamburger menu dead at phone width | into EN7 | one family for width-dependent controls |
| Carousel dots against the slide | into PR8 | a widget state check |
| Countdown negative or frozen; high score below last score; timer moving while paused | into R26 and RC5 | game and tool values out of their own range |
| Key press with no effect | into RC4 and RC8 | existing input liveness |
| Self-approval shown to the requester | note in section 7 (SM5 stays spec) | admins may self-approve by design |
| Subscription and entitlement consistency | plan limits into CP1; the rest spec (section 7) | the policy is not on the page |
| Partial multi-entity commit | WF6, flagged only against the app's own error message | rollback policy varies |
| Duplicate or reordered back-end events; external provider disagreement | EN9, EN8 (out) | need back-end instrumentation or a provider sandbox |
| Audit trail immutability | dropped; HS1 keeps what the page shows | needs an explicit contract |
| AI assistant claims an action that did not happen | into FB2 (the app's own claim, here in a chat reply) | the same intent-effect check; no LLM front end among our apps |
| Identities: calories ≈ 4P + 4C + 9F; loan PMT formula; age 17 passing an 18+ gate; bid increment; a seller buying their own item; an expired job still taking applications; 'within X km' results | dropped from 5.1 | food labels round; payment conventions vary; the others are policies (spec), or are SF7 range filters already |
| Accessibility adapter (A11Y) | PR6 note | non-functional; a separate dimension if ever added |
| Oracle-strength classes (intrinsic, cross-context, learned) | not taken | the eight evidence kinds of section 2 and the T1-T3 tiers already grade this |
