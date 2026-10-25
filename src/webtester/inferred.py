"""Inferred oracles (G3): spec-free expectations proposed by the explorer itself.

With no specification, the LLM worker that performs an action is also the best
placed to say what a correct app must show afterwards. In the B4 conditions its
reply may carry up to MAX_EXPECT_PER_STEP checks, each an executable predicate
over page state (never free text judged by an LLM):

  shows      {text, where}  the text is on the page
  not_shows  {text, where}  the text is not on the page
  count      {id, delta}    the first number in element [id] changes by delta
  changes    {}             the URL or the visible text changes (no-op UI)
  route      {route}        the browser ends on this route shape

`where` is "now" (the worker's page right after its actions), "reload" (the same
URL opened in a fresh tab of the worker's context: does the change persist?) or
a path (that page in a fresh tab). Fresh tabs share the worker's session but
never disturb its page. On freshly loaded pages (reload, /path) page text includes
the values of visible text fields, which then come from the app, not from typing.

Harness v3 (D46) adds a persistence twin: after a step that clicked a control
(not a link or tab), every passed "now" shows/not_shows check is re-run after
reload, so a change the UI shows but never saved is caught without the model
having to ask. A failed check becomes an `oracle_violation` signal,
which the FindingStore deduplicates like any implicit signal, and which the
evidence gate (G2) replays like any other finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from .browser import INNER_TEXT_JS, Element, Observation, Signal
from .oracles import normalise_message
from .state import route_shape

MAX_EXPECT_PER_STEP = 3  # v2: 2 (D46)
CHECKS = ("shows", "not_shows", "count", "changes", "route")
_ALIASES = {
    "shows": "shows", "show": "shows", "contains": "shows", "visible": "shows", "present": "shows",
    "text_present": "shows", "appears": "shows",
    "not_shows": "not_shows", "not_show": "not_shows", "absent": "not_shows", "not_contains": "not_shows",
    "not_visible": "not_shows", "missing": "not_shows", "gone": "not_shows", "text_absent": "not_shows",
    "count": "count", "counter": "count", "count_change": "count", "number_change": "count",
    "changes": "changes", "changed": "changes", "page_changes": "changes",
    "route": "route", "url": "route", "route_is": "route", "stays": "route",
}
_INT = re.compile(r"-?\d+")
_WS = re.compile(r"\s+")


def norm_text(s: str) -> str:
    return _WS.sub(" ", s or "").strip().lower()


def first_int(s: str | None) -> int | None:
    m = _INT.search(s or "")
    return int(m.group()) if m else None


def sanitize_expectations(raw: object) -> list[dict]:
    """Keep well-formed checks only (at most MAX_EXPECT_PER_STEP), normalising aliases."""
    if isinstance(raw, dict):
        raw = [raw]
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for e in raw:
        if len(out) >= MAX_EXPECT_PER_STEP:
            break
        if not isinstance(e, dict):
            continue
        check = _ALIASES.get(str(e.get("check") or e.get("type") or "").lower().strip())
        if check is None:
            continue
        exp: dict = {"check": check}
        if check in ("shows", "not_shows"):
            text = str(e.get("text") or "").strip()
            if len(text) < 2:
                continue
            exp["text"] = text[:120]
            where = str(e.get("where") or "now").strip()
            if where.lower() in ("now", "here", "current", ""):
                where = "now"
            elif where.lower() in ("reload", "after_reload", "refresh"):
                where = "reload"
            elif not where.startswith("/"):
                continue
            exp["where"] = where[:200]
        elif check == "count":
            eid = e.get("id", e.get("element"))
            if eid in (None, ""):
                continue
            exp["id"] = str(eid).strip("[]# ")
            try:
                exp["delta"] = int(e.get("delta", 1))
            except (TypeError, ValueError):
                continue
            if not -5 <= exp["delta"] <= 5:
                continue
        elif check == "route":
            route = str(e.get("route") or e.get("value") or "").strip()
            if not route.startswith("/"):
                continue
            exp["route"] = route[:200]
        out.append(exp)
    return out


def describe(exp: dict) -> str:
    c = exp["check"]
    if c in ("shows", "not_shows"):
        where = {"now": "now", "reload": "after reload"}.get(exp["where"], f"on {exp['where']}")
        return f"{'shows' if c == 'shows' else 'does not show'} {exp['text']!r} {where}"
    if c == "count":
        return f"number in [{exp['id']}] changes by {exp['delta']:+d}"
    if c == "changes":
        return "page changes"
    return f"ends on route {exp['route']}"


# ---------- pure evaluation (unit-tested) ----------
def eval_text(check: str, needle: str, page_text: str) -> tuple[bool, str]:
    """(holds, evidence) for shows / not_shows over a page's visible text."""
    hay = norm_text(page_text)
    n = norm_text(needle)
    pos = hay.find(n)
    if check == "shows":
        return pos >= 0, "" if pos >= 0 else f"text not found; page starts: {hay[:200]!r}"
    if pos < 0:
        return True, ""
    return False, f"found: ...{hay[max(0, pos - 80):pos + len(n) + 80]}..."


def eval_count(before: int | None, after: int | None, delta: int) -> tuple[str, str]:
    if before is None or after is None:
        return "inconclusive", f"no number (before={before}, after={after})"
    ok = after - before == delta
    return ("pass" if ok else "violated"), f"before={before}, after={after}, expected {delta:+d}"


def eval_route(expected: str, url_after: str) -> tuple[bool, str]:
    want = route_shape(urljoin("http://x/", expected))
    got = route_shape(url_after)
    return want == got, f"on {got}, expected {want}"


def eval_changes(url_before: str, text_before: str, url_after: str, text_after: str) -> tuple[bool, str]:
    same = url_before == url_after and norm_text(text_before)[:4000] == norm_text(text_after)[:4000]
    return not same, "URL and visible text unchanged" if same else ""


@dataclass
class CheckResult:
    status: str  # pass | violated | inconclusive
    evidence: str = ""


def oracle_signature(exp: dict, step_url: str) -> str:
    """Stable identity of a check: the same check at the same route is one finding."""
    c = exp["check"]
    route = route_shape(step_url)
    if c in ("shows", "not_shows"):
        where = exp["where"] if exp["where"] in ("now", "reload") else route_shape(urljoin("http://x/", exp["where"]))
        subject = normalise_message(norm_text(exp["text"]))
    elif c == "count":
        where, subject = "now", normalise_message(norm_text(exp.get("_label", "")))
    elif c == "route":
        where, subject = "now", route_shape(urljoin("http://x/", exp["route"]))
    else:
        where, subject = "now", ""
    return f"oracle_violation|{c}|{route}|{where}|{subject}"


def violation_signal(exp: dict, result: CheckResult, step_url: str) -> Signal:
    return Signal(
        "oracle_violation", f"expected: {describe(exp)} | {result.evidence}"[:300], step_url,
        {"sig": oracle_signature(exp, step_url), "expect": exp, "evidence": result.evidence[:500]},
    )


def annotate(exp: dict, obs: Observation) -> dict:
    """Attach what replays need to find a `count` element again (key, ordinal, label)."""
    if exp["check"] != "count":
        return exp
    el = obs.element(exp["id"])
    if el is None:
        return exp
    same = [e for e in obs.elements if e.key() == el.key()]
    return {**exp, "_ekey": el.key(), "_nth": next(i for i, e in enumerate(same) if e is el),
            "_label": re.sub(r"-?\d+", "", el.text or el.label)[:60]}


def clicked_active(clicked: list[Element | None]) -> bool:
    """True when the step clicked something and every clicked control was already selected
    (current page number, open tab): then 'nothing changed' is the correct outcome (D46)."""
    return bool(clicked) and all(el is not None and el.active for el in clicked)


def twin_eligible(clicked: list[Element | None]) -> bool:
    """A persistence twin follows a click on a control that may change data: not a link or a tab."""
    return any(el is not None and el.tag != "a" and el.role not in ("link", "tab") for el in clicked)


def persistence_twins(expects: list[dict], results: list[CheckResult | None], inner_text: str) -> list[dict]:
    """For each passed shows/not_shows check on the current page, the same check after reload,
    unless the model already asked for it. A `shows` needle found only in a field value (typed,
    maybe never saved) gets no twin: its absence after reload would not be a bug."""
    asked = {(e["check"], norm_text(e.get("text", ""))) for e in expects if e.get("where") == "reload"}
    hay = norm_text(inner_text)
    out = []
    for e, r in zip(expects, results):
        if e["check"] not in ("shows", "not_shows") or e.get("where") != "now" or r is None or r.status != "pass":
            continue
        if (e["check"], norm_text(e["text"])) in asked:
            continue
        if e["check"] == "shows" and norm_text(e["text"]) not in hay:
            continue
        out.append({"check": e["check"], "text": e["text"], "where": "reload", "twin": True})
    return out


# ---------- evaluation against a live session ----------
async def check(session, exp: dict, obs: Observation, active_click: bool = False) -> CheckResult:
    """Evaluate one expectation right after the step's actions. `obs` is the
    observation the actions were chosen from (ids are still valid on the page).
    `active_click`: every click hit an already-selected control (see clicked_active)."""
    from playwright.async_api import Error as PWError

    c = exp["check"]
    if c == "changes" and active_click:
        return CheckResult("inconclusive", "clicked control was already active")
    page = session.page
    try:
        if c in ("shows", "not_shows"):
            if exp["where"] == "now":
                # innerText only: right after the actions, a field still holds what was typed into it
                # (a failed save keeps the form), which would make 'shows <typed text>' pass. Field
                # values count only on freshly loaded pages (reload, /path), where they come from the app.
                text = await page.evaluate(INNER_TEXT_JS)
            else:
                target = page.url if exp["where"] == "reload" else urljoin(session.cfg.app.base_url, exp["where"])
                if not session.in_scope(target):
                    return CheckResult("inconclusive", "out of scope")
                text = await session.fresh_text(target)
                if text is None:
                    return CheckResult("inconclusive", "page did not load")
            ok, ev = eval_text(c, exp["text"], text)
            return CheckResult("pass" if ok else "violated", ev)
        if c == "count":
            el = obs.element(exp["id"])
            loc = page.locator(f'[data-wt-id="{exp["id"]}"]')
            if el is None or await loc.count() == 0:
                return CheckResult("inconclusive", "element gone")
            status, ev = eval_count(first_int(el.text or el.label or el.value),
                                    first_int(await loc.first.inner_text()), exp["delta"])
            return CheckResult(status, ev)
        if c == "changes":  # innerText only, like obs.text: typed field values are not a change
            ok, ev = eval_changes(obs.url, obs.text, page.url, await page.evaluate(INNER_TEXT_JS))
            return CheckResult("pass" if ok else "violated", ev)
        ok, ev = eval_route(exp["route"], page.url)
        return CheckResult("pass" if ok else "violated", ev)
    except PWError as e:
        return CheckResult("inconclusive", str(e).split("\n")[0][:120])
