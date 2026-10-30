"""Environment replay (M10, rule R71; v5 wave W2, D60): what the data means must not change with the
browser's time zone, locale or window width.

After exploration, up to MAX_PAGES item and list pages each worker visited are read in its session twice:
in the run's own context and in a context with one axis changed. Values are compared **normalised**, never as
raw text (fault_families.md R71):

  tz-west / tz-east  (UTC-11, UTC+14)  date-only values must keep their calendar date; list items and counts equal
  locale (de-DE)                        list items (names) and counts equal; labels may be translated
  phone (375 x 812)                     every action control the desktop page had is still reachable (possibly
                                        behind a menu button), and the items and counts are equal
  firefox / webkit (EN1, D61)           the same pages in another engine: list items and counts equal (layout and
                                        pixels are not compared); the engine must be installed (playwright install)

A difference must show on two reads of the axis context (k = 2) to be reported, so a page that rotates its
content is not reported. Findings are consistency signals with rule R71 and the axis in their subject; the
gate does not replay them (its replays use the run's context), so their status is set here: confirmed when
both axis reads differ from the base read.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .browser import BrowserSession, Signal
from .memory import norm
from .norms import find_dates
from .state import route_shape

AXES = {
    "tz-west": {"timezone_id": "Pacific/Pago_Pago"},
    "tz-east": {"timezone_id": "Pacific/Kiritimati"},
    "locale": {"locale": "de-DE"},
    "phone": {"viewport": {"width": 375, "height": 812}, "is_mobile": True, "has_touch": True},
}
ENGINES = ("firefox", "webkit")  # EN1 (D61): axes that need another browser, launched from `pw`
MAX_PAGES = 6
_MENU = re.compile(r"menu|navigation|toggle|hamburger|☰|more", re.I)
_ACTION = re.compile(r"^(save|add|create|new|edit|delete|remove|post|publish|follow|favou?rite|like|submit|search|"
                     r"filter|sort|apply|update|upload|download|export|share|reply|comment)\b", re.I)


def page_values(facts, raw: dict | None = None) -> dict:
    """The normalised values of one page read: list item names per list, counts by unit, calendar dates."""
    lists = {norm(L["heading"]): sorted({norm(i["name"]) for i in L["items"] if i["name"]})
             for L in facts.content_lists() if L.get("heading")}
    counts = {c["unit"].lower(): c["n"] for c in facts.counts if not c.get("nav")}
    dates = sorted({d.isoformat() for ln in (raw or {}).get("lines", []) for d in find_dates(ln)})
    actions = sorted({norm(c) for c in (raw or {}).get("controls", []) if _ACTION.match(c or "")})
    return {"lists": lists, "counts": counts, "dates": dates, "actions": actions, "h1": norm(facts.h1)}


def compare(axis: str, base: dict, other: dict, other_raw: dict | None = None) -> list[str]:
    """What differs between the base read and an axis read, as short descriptions ([] = the same)."""
    diffs = []
    for h, names in base["lists"].items():
        if h in other["lists"] and set(names) != set(other["lists"][h]) and axis != "locale":
            gone = sorted(set(names) - set(other["lists"][h]))[:2]
            if gone:
                diffs.append(f"list {h!r} loses {', '.join(repr(g) for g in gone)}")
    if axis == "locale":  # headings may be translated: compare the sets of all item names
        a = {n for v in base["lists"].values() for n in v}
        b = {n for v in other["lists"].values() for n in v}
        if a and b and len(a - b) > max(1, len(a) // 5):
            diffs.append(f"{len(a - b)} item names change with the locale")
    for u, n in base["counts"].items():
        if u in other["counts"] and other["counts"][u] != n and axis != "locale":
            diffs.append(f"count {u!r} {n} -> {other['counts'][u]}")
    if axis.startswith("tz") and base["dates"] and other["dates"] and set(base["dates"]) != set(other["dates"]) \
            and len(base["dates"]) == len(other["dates"]):
        shifted = sorted(set(base["dates"]) - set(other["dates"]))[:2]
        diffs.append(f"calendar dates shift with the time zone: {', '.join(shifted)}")
    if axis == "phone" and base["actions"]:
        menu = any(_MENU.search(c or "") for c in (other_raw or {}).get("controls", []))
        missing = sorted(set(base["actions"]) - set(other["actions"]))
        if missing and not menu and len(missing) >= 1:
            diffs.append(f"controls missing at phone width: {', '.join(missing[:3])}")
    return diffs


async def run_envcheck(browser, cfg, ctx, axes: tuple, pw=None) -> dict:
    """Compare base and axis reads for the pages each worker visited; ingest R71 findings into the run.
    Engine axes (ENGINES) need the Playwright handle `pw`; an engine that is not installed is skipped and noted."""
    from .consistency import Violation, audit, signal_of
    from .norms import NORMS_JS

    pages: dict[int, list[str]] = {}
    for n in ctx.graph.nodes.values():
        for w in n.workers:
            lst = pages.setdefault(w, [])
            if n.url and n.url not in lst and len(lst) < MAX_PAGES and not re.search(r"log-?in|sign-?in|logout", n.url, re.I):
                lst.append(n.url)
    out = {"axes": list(axes), "pages": sum(len(v) for v in pages.values()), "findings": 0, "skipped": []}
    engines = {}
    for name in (a for a in axes if a in ENGINES):
        try:
            engines[name] = await getattr(pw, name).launch(headless=True) if pw is not None else None
        except Exception as e:  # noqa: BLE001 - not installed: the axis is skipped, never failed
            engines[name] = None
            out["skipped"].append(f"{name}: {type(e).__name__}")
    rcfg = replace(cfg, max_elements=cfg.max_elements, scroll_once=False, dismiss_popups=False)

    async def read(s: BrowserSession, url: str):
        await s.goto(url)
        f = await audit(s)
        try:
            raw = await s.page.evaluate(NORMS_JS)
        except Exception:  # noqa: BLE001
            raw = {}
        return f, raw

    for w, urls in pages.items():
        recs = ctx.replay_log.get(w) or []
        storage = recs[-1].storage if recs else None
        base = BrowserSession(browser, rcfg, w)
        await base.start(storage_state=storage)
        try:
            base_vals = {}
            for u in urls:
                f, raw = await read(base, u)
                base_vals[u] = (page_values(f, raw), f.url)
            for axis in axes:
                kw = AXES.get(axis)
                if axis in ENGINES:
                    if engines.get(axis) is None:
                        continue
                    s = BrowserSession(engines[axis], rcfg, w)
                    await s.start(storage_state=storage)
                elif not kw:
                    continue
                else:
                    s = BrowserSession(browser, rcfg, w)
                    await s.start(storage_state=storage, context_kw=kw)
                try:
                    for u in urls:
                        hits = []
                        for _ in range(2):  # k = 2: rotating content does not differ twice the same way
                            f, raw = await read(s, u)
                            hits.append(compare(axis, base_vals[u][0], page_values(f, raw), raw))
                        same = [d for d in hits[0] if d in hits[1]]
                        if same:
                            v = Violation("R71", f"{axis}|{same[0][:60]}", f"[{axis}] {route_shape(u)}: {same[0]}")
                            sig = signal_of(v, u)
                            ctx.findings.ingest([sig], step=0, worker=w, state="", trail=[])
                            f2 = ctx.findings.by_sig.get(sig.detail["sig"])
                            if f2 is not None:
                                f2.status, f2.gate = "confirmed", {"reproduced": 2, "k": 2, "axis": axis, "env": True}
                            out["findings"] += 1
                finally:
                    await s.close()
        finally:
            await base.close()
    for br in engines.values():
        if br is not None:
            await br.close()
    ctx.trace.event("envcheck", **out)
    return out


__all__ = ["AXES", "compare", "page_values", "run_envcheck", "Signal"]
