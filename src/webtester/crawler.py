"""B0: deterministic breadth-first crawler with a random form filler (no LLM).

It answers "what does an LLM add at all?". Like Crawljax-style tools it gets a
login recipe and avoids the logout control, because it cannot recover a lost
session by itself. It restores a state by navigating to the URL where the
state was first seen, which loses non-URL state (open modals, filled forms):
that is a known, standard limitation of URL-restoring crawlers.
"""

from __future__ import annotations

import random
import string
import time
from collections import deque

from .browser import BrowserSession, Element, Observation
from .config import RunConfig
from .state import action_key, route_shape, state_id
from .worker import RunContext

FILLABLE = {"input", "textarea"}
NOT_FILLABLE_TYPES = {"checkbox", "radio", "submit", "button", "reset", "file", "image"}


def _fillable(e: Element) -> bool:
    return (e.tag in FILLABLE and e.type not in NOT_FILLABLE_TYPES) or e.tag == "select"


class RandomFiller:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def value(self, e: Element) -> str:
        r = self.rng
        w = "".join(r.choices(string.ascii_lowercase, k=r.randint(4, 9)))
        if e.tag == "select":
            return r.choice(e.options) if e.options else ""
        t = e.type or ("textarea" if e.tag == "textarea" else "text")
        if t == "email" or "email" in e.label.lower():
            return f"{w}@example.com"
        if t == "password":
            return w + "A1!"
        if t == "number":
            return str(r.randint(-10, 10_000))
        if t == "url":
            return f"https://example.com/{w}"
        if t == "textarea":
            return " ".join(w for _ in range(r.randint(3, 12)))
        return r.choice([w, w.title(), f"{w} {w}", ""])


def _actions_for(obs: Observation, sid: str, avoid: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """(kind, element-or-form key, description) for every action available in a state."""
    acts = []
    forms: dict[int, list[Element]] = {}
    for e in obs.elements:
        if e.disabled:
            continue
        txt = (e.text + " " + e.label).lower()
        if any(a in txt for a in avoid):
            continue
        if _fillable(e):
            if e.form >= 0:
                forms.setdefault(e.form, []).append(e)
            else:
                acts.append(("fill_enter", e.key(), e.describe()))
            continue
        if e.form >= 0 and (e.type == "submit" or e.tag == "button"):
            continue  # exercised through its form
        acts.append(("click", e.key(), e.describe()))
    for f, fields in sorted(forms.items()):
        acts.append(("form", f"form#{f}|" + "|".join(x.key() for x in fields), f"form#{f} ({len(fields)} fields)"))
    return acts


async def run_crawler(run: RunContext, session: BrowserSession, cfg: RunConfig, worker: int) -> str:
    rng = random.Random(cfg.seed * 1000 + worker)
    filler = RandomFiller(rng)
    avoid = tuple(t.lower() for t in cfg.app.crawler_avoid_text)
    if cfg.app.login:
        ok = await session.login(cfg.app.account(worker))
        run.trace.event("login", worker=worker, ok=ok)

    queue: deque = deque()
    known: dict[str, str] = {}  # state -> url where first seen

    def register(obs: Observation) -> str:
        sid = state_id(obs.url, obs.skeleton)
        if sid not in known:
            known[sid] = obs.url
            for kind, key, desc in _actions_for(obs, sid, avoid):
                queue.append((sid, kind, key, desc))
        return sid

    await session.goto("/")
    register(await session.observe())
    passes = 1
    while True:
        reason = run.budget.exhausted()
        if reason or run.stop.is_set():
            return reason or "stopped"
        if not queue:
            # Every known action tried once: start another pass with fresh random values.
            passes += 1
            items = []
            for sid, url in known.items():
                items.append((sid, url))
            rng.shuffle(items)
            for sid, url in items:
                await session.goto(url)
                obs = await session.observe()
                for kind, key, desc in _actions_for(obs, sid, avoid):
                    queue.append((sid, kind, key, desc))
            run.trace.event("crawler_pass", worker=worker, passes=passes, queued=len(queue))
            if not queue:
                return "nothing_to_do"

        sid, kind, key, desc = queue.popleft()
        t0 = time.monotonic()
        await session.goto(known[sid])
        obs = await session.observe()
        cur = state_id(obs.url, obs.skeleton)
        run.states_seen.add(cur)
        step = run.next_step()
        done = await _perform(session, obs, cur, kind, key, filler, run)

        signals = session.drain_signals()
        fired = session.drain_exposures()  # injected faults that fired (BookStack, D36)
        seen = run.exposed.setdefault(worker, set())
        seen.update(fired)
        after = await session.observe()
        nsid = register(after)
        if run.graph is not None:  # passive state graph (v4, D49): the crawler records, never uses it
            run.graph.visit(worker, cur, obs.url, step, obs.title)
            run.graph.visit(worker, nsid, after.url, step, after.title)
            run.graph.transition(worker, cur, done, nsid, by="crawler", signals=len(signals))
        new_state = nsid not in run.states_seen
        run.states_seen.add(nsid)
        # The restore navigation is part of the reproduction path (it is not counted as an action).
        trail = [{"step": step, "url": known[sid], "do": "navigate", "el": None, "value": known[sid]}]
        trail += [{"step": step, "url": obs.url, "do": d["do"], "el": d["el"], "value": d["value"]} for d in done]
        new_findings = run.findings.ingest(signals, step=step, worker=worker, state=cur, trail=trail,
                                           exposed=sorted(seen))
        elapsed = time.monotonic() - t0
        run.budget.charge(steps=1, browser_seconds=elapsed)
        run.trace.event(
            "step", worker=worker, step=step, state=cur, new_state=new_state, url=obs.url,
            route=route_shape(obs.url), n_elements=len(obs.elements), thought=f"bfs {kind}: {desc}"[:200],
            actions=done, signals=[{"kind": s.kind, "message": s.message} for s in signals],
            new_findings=[f.sig for f in new_findings], usage=None, seconds=round(elapsed, 3),
            next_state=nsid,
            **({"faults_exposed": fired} if fired else {}),
            **({"faults_triggered_silent": session.silent_triggers[:]} if session.silent_triggers else {}),
        )
        session.silent_triggers.clear()
        if session.injector_errors:
            run.trace.event("injector_error", worker=worker, step=step, errors=session.injector_errors[:20])
            session.injector_errors.clear()
        for f in new_findings:
            run.trace.event("finding", worker=worker, step=step, finding=f.to_dict())


async def _perform(session, obs, cur, kind, key, filler, run) -> list[dict]:
    done = []

    async def do(action: str, el: Element | None, value: str | None):
        akey = action_key(cur, action, el.key() if el else None, value)
        dup = akey in run.actions_seen
        run.actions_seen.add(akey)
        res = await session.execute(action, el.id if el else None, value)
        done.append({"do": action, "id": el.id if el else None, "value": value, "el": el.describe() if el else None,
                     "ekey": el.key() if el else None,
                     "key": akey, "dup": dup, "ok": res.ok, "error": res.error, "url_after": res.url_after,
                     "out_of_scope": res.out_of_scope})
        return res

    if kind == "click":
        el = next((e for e in obs.elements if e.key() == key), None)
        if el:
            await do("click", el, None)
    elif kind == "fill_enter":
        el = next((e for e in obs.elements if e.key() == key), None)
        if el:
            await do("fill", el, filler.value(el))
            await do("press", el, "Enter")
    elif kind == "form":
        fidx = int(key.split("|", 1)[0].removeprefix("form#"))
        fields = [e for e in obs.elements if e.form == fidx and _fillable(e) and not e.disabled]
        for e in fields:
            await do("select" if e.tag == "select" else "fill", e, filler.value(e))
        buttons = [e for e in obs.elements if e.form == fidx and (e.type == "submit" or e.tag == "button") and not e.disabled]
        submit = next((b for b in buttons if b.type == "submit"), buttons[-1] if buttons else None)
        if submit:
            await do("click", submit, None)
        elif fields:
            await do("press", fields[-1], "Enter")
    return done
