# Oracle gap analysis after Night 2 (26 Oct 2026)

Working notes for planning (not paper prose). Question from the user: why do we miss faults, how to fix it, how to generalise. Nothing here is implemented or measured yet; the "would catch" columns are hypotheses to test.

## Where each miss comes from

| Layer | Flaw | Evidence |
|---|---|---|
| Oracle (G3) | Checks predict the effect of the agent's own action; nothing audits what a page shows on arrival | BookStack: 0/13; steps on fault pages 3–54 with 1–7 content checks (`phase2_bookstack_results.md`) |
| Oracle (G3) | Checks are guesses about unspecified design (where Save goes, heading wording) | 32/32 BookStack fp are design guesses (21 route, 11 text) |
| Oracle (G3) | No memory of what the agent did (created, viewed, favourited, deleted), so lists cannot be checked against it | BS01–03; Conduit F05, F08 |
| Oracle (G3) | No cross-view checks (same entity in two places, count vs list, link text vs destination) | BS05–08, BS12; Conduit F10 |
| Gate (G2) | Replay tests repeatability, not correctness: a wrong deterministic expectation replays every time | 37/39 confirmed on BookStack |
| Judge | Same model prior, no new evidence | Conduit: dropped 12 real findings; BookStack: kept 1 of 5 env |
| Exploration | Token budget, not time: large pages end runs at 8–9 min, 73 steps | BS12, BS13 never reached by B4 |
| Exploration | G1 discourages revisits; 5 faults fire only on the 2nd arrival | BS02–04, BS15, BS17, BS18 |
| Fault set | 5 of 18 BookStack faults need literals from the benchmark's test specification | BS14–BS18 (`reachable = false`) |
| Ours | Route `*` not a wildcard (I41), no mail driver (I42), login race after reset (I40) | 4 fp, 7 env, 1 lost run |

## Fault scripts checked (`apps/bookstack/faults/injected.js`)
- BS04 phantom book: `href = '/books/book-duplicate'` (no such book).
- BS05–BS07 phantom profile items, BS08 phantom search result: `href = '#'`.
- BS12: text 'Page 1' changed to 'Page 3'; the link still points to page-1.
- BS13: the 'Create Sort Rule' link removed; nothing else on the page changes.

## Generic oracle families (spec-free) and what each would cover

| Family | Rule (no app knowledge) | BookStack | Conduit |
|---|---|---|---|
| O1 link integrity | an entity link must resolve (not `#`, not 404) and the destination title must match the link text | BS04, BS05–08, BS12 | – |
| O2 action ledger | what I created/viewed/favourited/followed/deleted must (or must not) appear in the list for that category | BS01–03 (if the agent did the action), BS15, BS18 | F05, F06, F08 |
| O3 count vs list | a shown count must be ≥ the items listed (one-sided, safe with pagination) | BS05–07 | F05 |
| O4 time sanity | something I touched minutes ago must not read 'days/years ago'; same entity, same age across views | BS09–11 | – |
| O5 revisit diff | with no action of mine in between, a list must not gain or lose items on a revisit | BS02–04, BS15, BS17, BS18 | F09 (page 2 = page 1) |
| O6 filter satisfaction | every result of a filter or search for T must contain T when opened | BS08 | F10 |
| O7 role/ownership | owner-only controls must not show on others' content | – | F07 |
| none | removed control with no other trace | BS13 (needs a spec or a weak 'no create action' heuristic) | F03, F04 (UI-unreachable) |

## Precision fixes for the existing checks
- Route checks only from the clicked link's `href` (fact), never a model guess: removes 21 of 32 BookStack fp.
- Text checks only for grounded needles (typed by the agent or seen earlier); ungrounded wording becomes advisory: removes 11 of 32.
- Consistency findings (O1–O6) are true no matter how the app is designed, so the gate's replay becomes meaningful for them.

## Ceiling
Without a specification, a fault that leaves the app in a consistent, plausible state cannot be told apart from intended behaviour (BS13; any wrong-but-consistent business rule). The reachable target is: every fault that creates an inconsistency the agent can observe. On the current catalogues that is 12 of 13 reachable BookStack faults and all 6 reachable Conduit semantic faults (hypothesis).

## Methodology risk
O1–O6 are designed after seeing the BookStack results, so BookStack stops being held-out. O2/O3/O6 were already motivated by the Conduit misses (F05 count, F10 relational, 25 Oct), but a clean claim needs a third, unseen app.
