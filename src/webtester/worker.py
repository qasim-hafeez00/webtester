"""The exploring worker loop: observe -> decide -> act -> collect signals -> log."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .browser import INNER_TEXT_JS, BrowserSession
from .budget import Budget
from .inferred import (annotate, check, clicked_active, ground_expectations, persistence_twins, twin_eligible,
                       violation_signal)
from .oracles import FindingStore
from .policies import Memory
from .reach import defer_reason, network_gets
from .state import action_key, route_shape, state_id
from .trace import Trace

STOP_AFTER = {"click", "press", "navigate", "back", "reload"}  # page may change: later ids are stale
MAX_CONSECUTIVE_POLICY_ERRORS = 5


@dataclass
class RunContext:
    """State shared by all workers of one run (budget, trace, findings, counters).

    Exploration knowledge is NOT shared here: it lives in the frontier (G1),
    which B3 shares between workers and B2 deliberately lacks."""

    budget: Budget
    trace: Trace
    findings: FindingStore
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    step_counter: int = 0
    states_seen: set = field(default_factory=set)
    actions_seen: set = field(default_factory=set)
    # Evidence gate (G2): per worker, what each step started from and did, so a
    # finding can be replayed later in a fresh context. Saved as replay.jsonl so the
    # gate can be re-run on a finished run (`webtester regate`).
    record_replay: bool = False
    replay_log: dict[int, list["StepRecord"]] = field(default_factory=dict)
    exposed: dict[int, set] = field(default_factory=dict)  # worker -> injected faults it has triggered
    # Harness v4 (D49): the abstract state graph, recorded in every condition, and the consistency
    # oracles with their run memory (B4 family). `sweep` is a consistency.SweepState or None.
    graph: object = None
    sweep: object = None
    sweepers: dict = field(default_factory=dict)  # worker -> consistency.Sweeper

    def next_step(self) -> int:
        self.step_counter += 1
        return self.step_counter

    stop_files: tuple = ()  # S2 (D60): paths whose existence ends the run cleanly
    deferred: int = 0  # R8: destructive clicks held back
    stateful_travels: int = 0  # X2: travels done by replaying a recorded navigation path

    def stop_requested(self) -> bool:
        return any(Path(p).exists() for p in self.stop_files)


@dataclass
class StepRecord:
    step: int
    url: str  # page URL when the step started
    storage: dict  # cookies + localStorage when the step started (the session to replay from)
    actions: list[dict]  # {do, ekey, nth, value} for the actions that ran
    expect: list[dict]  # checks evaluated after the actions (annotated)
    intent: dict | None = None  # v4: the model's stated intent (the gate's sweeper reuses it)
    suspect: dict | None = None  # v4: a contradiction the model cited (R15)
    session: dict | None = None  # v5 C1 (D60): session storage {origin, items} when the step started
    t: float = 0.0  # C4 (D61): wall-clock time when the step started (gate replays of time rules use it)


def save_replay_log(path: Path, log: dict[int, list[StepRecord]]) -> None:
    """One JSON line per step record. Holds the local test accounts' session tokens: runs/ is gitignored."""
    with path.open("w", encoding="utf-8") as fh:
        for worker, records in sorted(log.items()):
            for r in records:
                fh.write(json.dumps({"worker": worker, **asdict(r)}, ensure_ascii=False) + "\n")


def load_replay_log(path: Path) -> dict[int, list[StepRecord]]:
    log: dict[int, list[StepRecord]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            log.setdefault(d.pop("worker"), []).append(StepRecord(**d))
    return log


async def run_worker(run: RunContext, session: BrowserSession, policy, worker: int, max_steps: int) -> str:
    mem = Memory()
    await session.goto("/")
    errors = 0
    sweeper = run.sweepers.get(worker)
    graph = run.graph
    edge = None  # (state, actions, verb, signals, by) of the last step: becomes a graph edge on arrival
    while True:
        reason = run.budget.exhausted()
        if not reason and run.stop_requested():
            run.stop.set()
            run.trace.event("stop_file", worker=worker, step=run.step_counter)
        if reason or run.stop.is_set():
            return reason or "stopped"
        t0 = time.monotonic()
        obs = await session.observe()
        sid = _sid(session, obs)
        frontier = getattr(policy, "frontier", None)
        if graph is not None:
            graph.visit(worker, sid, obs.url, run.step_counter, obs.title)
            if edge:
                e = graph.transition(worker, edge[0], edge[1], sid, by=edge[4], verb=edge[2], signals=edge[3])
                if sweeper is not None:
                    sweeper.note_edge(e)  # G3 (D61)
        edge = None
        # v4 travel: a newly assigned focus area elsewhere is reached by URL, without an LLM step.
        if getattr(frontier, "version", 1) >= 3 and hasattr(policy, "prepare"):
            focus = policy.prepare(sid)
            if focus and frontier.area(route_shape(obs.url)) != focus[0] and focus[1].startswith("/"):
                res = await session.goto(focus[1])
                run.trace.event("travel", worker=worker, step=run.step_counter, src=route_shape(obs.url),
                                dst=focus[0], path=focus[1], ok=res.ok)
                if res.ok:
                    graph.travels += 1
                    frontier.visit(worker, sid, obs)
                    src = sid
                    obs = await session.observe()
                    sid = _sid(session, obs)
                    if route_shape(obs.url) != focus[0] and not focus[0].endswith("/*"):
                        # X2: the URL did not restore the state (redirect, modal, selected record): replay a
                        # recorded navigation-only path from here
                        path = graph.nav_path(sid, focus[0]) if graph is not None else None
                        if path and await _replay_path(session, path):
                            run.stateful_travels += 1
                            obs = await session.observe()
                            sid = _sid(session, obs)
                    graph.visit(worker, sid, obs.url, run.step_counter, obs.title)
                    graph.transition(worker, src, [{"do": "navigate", "value": focus[1], "ekey": None}], sid,
                                     by="harness")
        new_state = sid not in run.states_seen
        run.states_seen.add(sid)
        mem.note_visit(obs.url, sid)
        if frontier is not None:
            frontier.visit(worker, sid, obs)
        step = run.next_step()
        t_step = time.time()
        storage = await session.storage_state() if run.record_replay else None
        sess_store = await session.session_storage() if run.record_replay else None

        decision = await policy.decide(obs, mem, step, sid=sid)
        if frontier is not None:
            claimed = [obs.element(a["id"]) for a in decision.actions if a["id"]]
            frontier.claim(worker, sid, [el.key() for el in claimed if el is not None])
        tokens = decision.usage.total if decision.usage else 0
        if decision.error and not decision.actions:
            run.trace.event("policy_error", worker=worker, step=step, error=decision.error)
            run.budget.charge(tokens=tokens, browser_seconds=time.monotonic() - t0)
            if decision.usage is None:  # the LLM could not be reached at all
                errors += 1
                if errors >= MAX_CONSECUTIVE_POLICY_ERRORS:
                    return "policy_unavailable"
                await asyncio.sleep(min(30, 2 * errors))
            else:  # the model answered but unusably: tell it, and carry on
                mem.add(f"s{step}: (your reply had no valid action - use the exact JSON format)")
            continue
        errors = 0
        if decision.page and graph is not None:
            graph.name_page(route_shape(obs.url), decision.page)
        if sweeper is not None:
            await sweeper.before(session, obs, decision.actions)

        done, clicked = [], []
        share = _budget_share(run)
        for a in decision.actions:
            el = obs.element(a["id"]) if a["id"] else None
            why = defer_reason(f"{el.text} {el.label}" if el else "", share, _own_page(run, worker, obs.url),
                               getattr(session.cfg, "defer_destructive", 0)) if a["do"] == "click" and el else ""
            if why:  # R8: the harness, not the prompt, keeps destructive actions late and on own items
                run.deferred += 1
                mem.add(f"s{step}: ({why}: {el.text or el.label})")
                break
            if a["do"] == "click":
                clicked.append(el)
            akey = action_key(sid, a["do"], el.key() if el else None, a["value"])
            dup = akey in run.actions_seen
            run.actions_seen.add(akey)
            res = await session.execute(a["do"], a["id"], a["value"])
            if frontier is not None and el is not None:
                frontier.record(worker, sid, el.key(), do=a["do"], value=a["value"])
            if el is not None and res.ok:
                session.note_activated(obs.url, el.key())
            done.append({
                "do": a["do"], "id": a["id"], "value": a["value"],
                "el": el.describe() if el else None, "key": akey, "dup": dup,
                "ekey": el.key() if el else None, "nth": _nth(obs, el),
                "ok": res.ok, "error": res.error, "url_after": res.url_after, "out_of_scope": res.out_of_scope,
            })
            if not res.ok or a["do"] in STOP_AFTER:
                break
        if sweeper is not None:
            await sweeper.actions_done(session)

        # G3: checks only make sense when every action the model planned actually ran.
        expects = decision.expect
        if sweeper is not None and expects:  # v4: only checks about facts (D49)
            typed_now = [d["value"] for d in done if d["do"] in ("fill", "select") and d["value"]]
            seen = [t for _, t in run.sweep.memory.page_text.get(worker, [])]
            expects = ground_expectations(expects, obs, done, sorted(run.sweep.memory.typed) + typed_now, seen)
        expects = [annotate(e, obs) for e in expects]
        checks, violations = [], []
        if expects:
            ran_all = len(done) == len(decision.actions) and all(d["ok"] for d in done)
            active = clicked_active(clicked[:len(done)])
            results = []
            for e in expects:
                r = await check(session, e, obs, active) if ran_all else None
                results.append(r)
            # Persistence twins (D46): passed "now" checks again after reload, after a data-changing click.
            if ran_all and twin_eligible(clicked):
                typed = [d["value"] for d in done if d["do"] in ("fill", "select") and d["value"]]
                twins = persistence_twins(expects, results, await session.page.evaluate(INNER_TEXT_JS), typed)
                for t in twins:
                    expects.append(t)
                    results.append(await check(session, t, obs))
            for e, r in zip(expects, results):
                checks.append({**e, "status": r.status if r else "skipped", "evidence": r.evidence[:200] if r else ""})
                if r and r.status == "violated":
                    violations.append(violation_signal(e, r, obs.url))
        consistency = []
        if sweeper is not None:
            n_events = len(run.sweep.memory.events)
            consistency = await sweeper.after(session, obs, done, step, decision.intent, decision.suspect)
            if getattr(session.cfg, "network_routes", False) and session.evidence and hasattr(frontier, "add_discovered"):
                frontier.add_discovered({"network": network_gets(session.net_since(sweeper.net_mark))})
            for e in run.sweep.memory.events[n_events:]:
                if e.verb != "view":
                    run.trace.event("memory_event", worker=worker, step=step, verb=e.verb, obj=e.obj, source=e.source,
                                    status=e.status, written=e.written, url=e.url)
        if run.record_replay:
            run.replay_log.setdefault(worker, []).append(StepRecord(
                step, obs.url, storage,
                [{"do": d["do"], "ekey": d["ekey"], "nth": d["nth"], "value": d["value"]} for d in done], expects,
                decision.intent, decision.suspect, sess_store, t_step))

        signals = session.drain_signals() + violations + consistency
        fired = session.drain_exposures()
        seen = run.exposed.setdefault(worker, set())
        seen.update(fired)
        trail = [{"step": step, "url": obs.url, "do": d["do"], "el": d["el"], "value": d["value"]} for d in done]
        new_findings = run.findings.ingest(signals, step=step, worker=worker, state=sid, trail=trail,
                                           exposed=sorted(seen))
        elapsed = time.monotonic() - t0
        run.budget.charge(steps=1, tokens=tokens, browser_seconds=elapsed)

        mem.add(_history_line(step, obs.url, decision.thought, done, signals))
        verb = run.sweep.memory.events[-1].verb if sweeper is not None and run.sweep.memory.events and \
            run.sweep.memory.events[-1].step == step else ""
        edge = (sid, done, verb, len(signals), "llm") if done else None
        run.trace.event(
            "step", worker=worker, step=step, state=sid, new_state=new_state, url=obs.url,
            route=route_shape(obs.url), n_elements=len(obs.elements), thought=decision.thought,
            actions=done, signals=[{"kind": s.kind, "message": s.message} for s in signals],
            new_findings=[f.sig for f in new_findings],
            usage=(decision.usage.__dict__ if decision.usage else None), seconds=round(elapsed, 3),
            suggestion=getattr(policy, "last_suggestion", None),
            **({"checks": checks} if checks else {}),
            **({"intent": decision.intent} if decision.intent else {}),
            **({"suspect": decision.suspect} if decision.suspect else {}),
            **({"page_name": decision.page} if decision.page else {}),
            **({"faults_exposed": fired} if fired else {}),
            **({"faults_triggered_silent": session.silent_triggers[:]} if session.silent_triggers else {}),
        )
        session.silent_triggers.clear()
        if session.injector_errors:  # errors inside our fault injector: kept out of the findings, logged here
            run.trace.event("injector_error", worker=worker, step=step, errors=session.injector_errors[:20])
            session.injector_errors.clear()
        for f in new_findings:
            run.trace.event("finding", worker=worker, step=step, finding=f.to_dict())
        if step >= max_steps:
            return "max_steps"


def _sid(session: BrowserSession, obs) -> str:
    """The abstract state; R4 (D61): with accounts of several roles, the worker's role is part of it, so an
    admin's and a reader's view of one page are two states (each worker keeps one account, so this is constant
    per worker and cheap); so is the active context of a context switcher (workspace, team, store), when the page
    has one."""
    app = session.cfg.app
    roles = {a.get("role", "") for a in getattr(app, "accounts", ()) or ()}
    role = app.account(session.worker).role if len(roles) > 1 else ""
    ctx = getattr(obs, "context", "")
    return state_id(obs.url, obs.skeleton + (f"|role={role}" if role else "") + (f"|ctx={ctx}" if ctx else ""))


def _budget_share(run: RunContext) -> float:
    b = run.budget
    return max(b.steps / max(b.cfg.max_steps, 1), b.tokens / max(b.cfg.max_tokens, 1),
               b.elapsed_min() / max(b.cfg.max_minutes, 1e-9))


def _own_page(run: RunContext, worker: int, url: str) -> bool:
    """R8: the page is an item this worker created (its run memory says so)."""
    if run.sweep is None:
        return False
    from .memory import entity_key

    key = entity_key(url)
    return any(e.worker == worker and e.verb == "create" and (e.target == key or e.landing == url)
               for e in run.sweep.memory.events)


async def _replay_path(session: BrowserSession, path) -> bool:
    """X2: replay recorded navigation edges by element key; False as soon as one cannot be found."""
    from .gate import locate

    for e in path:
        obs = await session.observe()
        for a in e.replay:
            el = locate(obs, a.get("ekey"), a.get("nth") or 0)
            if a.get("ekey") and el is None:
                return False
            res = await session.execute(a["do"], el.id if el else None, a.get("value"))
            if not res.ok:
                return False
    return True


def _nth(obs, el) -> int:
    """Ordinal of `el` among the elements with the same key (replays locate it by key + ordinal)."""
    if el is None:
        return 0
    same = [e for e in obs.elements if e.key() == el.key()]
    return next((i for i, e in enumerate(same) if e is el), 0)


def _history_line(step: int, url: str, thought: str, done: list[dict], signals) -> str:
    acts = "; ".join(
        f"{d['do']} {d['el'] or d['value'] or ''}".strip()[:90]
        + (f" = {d['value']!r}"[:40] if d["do"] in ("fill", "select") else "")
        + ("" if d["ok"] else f" FAILED({d['error'][:60]})")
        for d in done
    ) or "no action"
    end = done[-1]["url_after"] if done else url
    moved = f" -> {route_shape(end)}" if end and route_shape(end) != route_shape(url) else ""
    sig = f" [!] {len(signals)} error signal(s): {signals[0].message[:80]}" if signals else ""
    return f"s{step} @{route_shape(url)}: {acts}{moved}{sig}"

