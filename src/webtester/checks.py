"""Check-outcome log (v5 plan section 3, D59): what each rule did on each page it considered.

An unexecuted check is never a pass. Every rule, on every page it looks at, records one outcome:

  detected        it raised a violation
  exercised       its preconditions held, it ran, no violation
  unarmed         its preconditions did not hold (why: 'no-totals', 'first-visit', 'one-cue', ...)
  suppressed      a precision guard skipped it (why: the guard, e.g. 'event-feed', 'volatile')
  capped          a probe budget was used up (why: the budget)
  unobservable    the evidence it needs is not captured (why: e.g. 'capture-off')
  inconclusive    it ran but could not decide (why: e.g. 'load-failed', 'input-rejected')

Rows are aggregated per (worker, rule, route shape, outcome, why) with a count and the first and last
step, so a 300-step run stays a few hundred rows. Written per run as `checks.jsonl` (live runs) or
`checks_resweep[_clean].jsonl` (resweeps). The recall funnel (S4 armed, `evaluate.py`) and the arm rate
per rule and the recall cost of each guard are computed from it offline.

Page-level arming for the pure rules (R01-R06, R08, R12, R18) is decided here from the page facts,
so the rules themselves stay unchanged; rules inside the Sweeper note their own outcomes.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUTCOMES = ("detected", "exercised", "unarmed", "suppressed", "capped", "unobservable", "inconclusive")
ARMED = ("detected", "exercised")  # the check ran with its preconditions met


class CheckLog:
    """Shared by all workers of a run (lives on the SweepState)."""

    def __init__(self) -> None:
        self.rows: dict[tuple, list] = {}  # (worker, rule, route, outcome, why) -> [count, first, last]
        self.armed_routes: set[str] = set()  # R10 (D61): route shapes where some check ran (the frontier reads it)

    def note(self, worker: int, step: int, rule: str, route: str, outcome: str, why: str = "") -> None:
        assert outcome in OUTCOMES, outcome
        k = (worker, rule, route, outcome, why)
        if outcome in ARMED:
            self.armed_routes.add(route)
        r = self.rows.get(k)
        if r is None:
            self.rows[k] = [1, step, step]
        else:
            r[0] += 1
            r[2] = step

    def records(self) -> list[dict]:
        return [{"worker": w, "rule": rule, "route": route, "outcome": o, "why": why, "n": n, "first": a, "last": b}
                for (w, rule, route, o, why), (n, a, b) in sorted(self.rows.items(), key=lambda kv: (kv[0][1], kv[0][2]))]

    def write(self, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            for r in self.records():
                f.write(json.dumps(r) + "\n")

    def summary(self) -> dict:
        """rule -> outcome -> count (small enough for the trace's sweep event)."""
        out: dict[str, Counter] = {}
        for (_, rule, _, o, _), (n, _, _) in self.rows.items():
            out.setdefault(rule, Counter())[o] += n
        return {r: dict(c) for r, c in sorted(out.items())}


def read_checks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def page_arms(facts, typed_markup: bool) -> dict[str, str]:
    """For the pure page rules: rule -> '' when armed, else the reason it is unarmed. Mirrors the
    preconditions inside each rule function in consistency.py (kept next to them in review)."""
    lists = facts.content_lists()
    with_two = [L for L in lists if len(L["items"]) >= 2]
    counts = [c for c in facts.counts if not c.get("nav") and c["n"] <= 500]
    tables = [t for t in facts.tables if t.get("head")]
    arms = {
        "R01": "" if (facts.plain or "").strip() else "no-text",
        "R03": "" if with_two else "no-list",
        "R04": "" if counts and lists else ("no-count" if lists else "no-list"),
        "R04b": "" if facts.showing and facts.main_list() else "no-showing",
        "R06": "" if tables or facts.totals else "no-totals",
        # R12: typed markup can only render when some typed value holds markup; mojibake is always looked for
        "R12": "" if typed_markup or (facts.plain or "").strip() else "no-text",
        "R08": "" if facts.times else "no-times",
        "R18": "" if facts.times else "no-times",
    }
    return arms
