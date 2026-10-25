"""The exploring worker loop: observe -> decide -> act -> collect signals -> log."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .browser import INNER_TEXT_JS, BrowserSession
from .budget import Budget
from .inferred import annotate, check, clicked_active, persistence_twins, twin_eligible, violation_signal
from .oracles import FindingStore
from .policies import Memory
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

    def next_step(self) -> int:
        self.step_counter += 1
        return self.step_counter


@dataclass
class StepRecord:
    step: int
    url: str  # page URL when the step started
    storage: dict  # cookies + localStorage when the step started (the session to replay from)
    actions: list[dict]  # {do, ekey, nth, value} for the actions that ran
    expect: list[dict]  # checks evaluated after the actions (annotated)


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
    while True:
        reason = run.budget.exhausted()
        if reason or run.stop.is_set():
            return reason or "stopped"
        t0 = time.monotonic()
        obs = await session.observe()
        sid = state_id(obs.url, obs.skeleton)
        new_state = sid not in run.states_seen
        run.states_seen.add(sid)
        mem.note_visit(obs.url, sid)
        frontier = getattr(policy, "frontier", None)
        if frontier is not None:
            frontier.visit(worker, sid, obs)
        step = run.next_step()
        storage = await session.storage_state() if run.record_replay else None

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

        done, clicked = [], []
        for a in decision.actions:
            el = obs.element(a["id"]) if a["id"] else None
            if a["do"] == "click":
                clicked.append(el)
            akey = action_key(sid, a["do"], el.key() if el else None, a["value"])
            dup = akey in run.actions_seen
            run.actions_seen.add(akey)
            res = await session.execute(a["do"], a["id"], a["value"])
            if frontier is not None and el is not None:
                frontier.record(worker, sid, el.key(), do=a["do"], value=a["value"])
            done.append({
                "do": a["do"], "id": a["id"], "value": a["value"],
                "el": el.describe() if el else None, "key": akey, "dup": dup,
                "ekey": el.key() if el else None, "nth": _nth(obs, el),
                "ok": res.ok, "error": res.error, "url_after": res.url_after, "out_of_scope": res.out_of_scope,
            })
            if not res.ok or a["do"] in STOP_AFTER:
                break

        # G3: checks only make sense when every action the model planned actually ran.
        expects = [annotate(e, obs) for e in decision.expect]
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
                twins = persistence_twins(expects, results, await session.page.evaluate(INNER_TEXT_JS))
                for t in twins:
                    expects.append(t)
                    results.append(await check(session, t, obs))
            for e, r in zip(expects, results):
                checks.append({**e, "status": r.status if r else "skipped", "evidence": r.evidence[:200] if r else ""})
                if r and r.status == "violated":
                    violations.append(violation_signal(e, r, obs.url))
        if run.record_replay:
            run.replay_log.setdefault(worker, []).append(StepRecord(
                step, obs.url, storage,
                [{"do": d["do"], "ekey": d["ekey"], "nth": d["nth"], "value": d["value"]} for d in done], expects))

        signals = session.drain_signals() + violations
        fired = session.drain_exposures()
        seen = run.exposed.setdefault(worker, set())
        seen.update(fired)
        trail = [{"step": step, "url": obs.url, "do": d["do"], "el": d["el"], "value": d["value"]} for d in done]
        new_findings = run.findings.ingest(signals, step=step, worker=worker, state=sid, trail=trail,
                                           exposed=sorted(seen))
        elapsed = time.monotonic() - t0
        run.budget.charge(steps=1, tokens=tokens, browser_seconds=elapsed)

        mem.add(_history_line(step, obs.url, decision.thought, done, signals))
        run.trace.event(
            "step", worker=worker, step=step, state=sid, new_state=new_state, url=obs.url,
            route=route_shape(obs.url), n_elements=len(obs.elements), thought=decision.thought,
            actions=done, signals=[{"kind": s.kind, "message": s.message} for s in signals],
            new_findings=[f.sig for f in new_findings],
            usage=(decision.usage.__dict__ if decision.usage else None), seconds=round(elapsed, 3),
            suggestion=getattr(policy, "last_suggestion", None),
            **({"checks": checks} if checks else {}),
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

