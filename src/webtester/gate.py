"""Evidence gate (G2): reproduce before report.

After exploration ends, every candidate finding is replayed from the worker's
own step log (worker.StepRecord) in a fresh browser context restored to the
session that worker had, with the app's data reset before every replay:

1. Minimise: replay the last 1 step, then the last `windows[1]` steps, ... up to
   the finding's step, until one replay reproduces the finding. That window is
   the finding's minimal trace.
2. Confirm: replay the minimal trace until there are `k` replays in total.
3. Label: confirmed (k/k), flaky (1..k-1 of k), rejected (no replay reproduced
   it), unverified (gate time ran out first).

"Reproduced" means the same finding signature again: the same implicit signal
(HTTP 5xx, JS error, ...) anywhere in the replay, or for an inferred-oracle
finding the same check failing again after the last step's actions.

Replays need no LLM: they repeat recorded actions, locating each element by its
position-independent key plus its ordinal among same-key elements. The only LLM
use is the optional judge, a second opinion on reproduced oracle violations
(wrong expectation or real bug?), which never changes the replay label.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .browser import BrowserSession, Observation
from .inferred import CheckResult, check, describe, oracle_signature
from .oracles import Finding, signature
from .worker import RunContext, StepRecord

JUDGE_SYSTEM = """You review a failed check reported by an automated web-app tester. The tester predicted what a \
correct app must show after some actions; the prediction failed, and it failed again every time the actions \
were replayed on a freshly reset app. Decide whether this reveals a BUG in the app, or a WRONG EXPECTATION by \
the tester (it expected other wording, a feature the app does not have, or behaviour a correct app need not \
have). Reply with one JSON object and nothing else:
{"verdict": "bug" | "wrong_expectation" | "unsure", "reason": "<at most 30 words>"}"""


@dataclass(frozen=True)
class GateConfig:
    k: int = 3
    windows: tuple[int, ...] = (1, 4)  # minimal-trace search: suffix lengths in steps
    max_minutes: float = 20.0
    judge: bool = True


def label(reproduced: int, k: int, tried: bool) -> str:
    if not tried:
        return "unverified"
    if reproduced == 0:
        return "rejected"
    return "confirmed" if reproduced >= k else "flaky"


def locate(obs: Observation, ekey: str | None, nth: int):
    if ekey is None:
        return None
    same = [e for e in obs.elements if e.key() == ekey]
    if not same:
        return None
    return same[nth] if nth < len(same) else same[0]


def windows_for(log: list[StepRecord], step: int, sizes: tuple[int, ...]) -> list[list[StepRecord]]:
    """Distinct suffix windows of the worker's log ending at `step`, shortest first."""
    idx = next((i for i, r in enumerate(log) if r.step == step), None)
    if idx is None:
        return []
    out, seen = [], set()
    for n in sizes:
        start = max(0, idx - n + 1)
        if start in seen:
            continue
        seen.add(start)
        out.append(log[start:idx + 1])
    return out


async def replay(browser, cfg, ctl, window: list[StepRecord], finding: Finding) -> dict:
    """One replay of `window` on freshly reset data. Returns {reproduced, missing, seconds}."""
    t0 = time.monotonic()
    if ctl is not None:
        await asyncio.to_thread(ctl.reset)
    s = BrowserSession(browser, cfg, finding.worker)
    await s.start(storage_state=window[0].storage)
    missing = 0
    reproduced = False
    try:
        await s.goto(window[0].url)
        for i, rec in enumerate(window):
            obs = await s.observe()
            if obs.url != rec.url:
                await s.goto(rec.url)
                obs = await s.observe()
            ran_all = True
            for a in rec.actions:
                el = locate(obs, a["ekey"], a["nth"])
                if a["ekey"] and el is None:
                    missing += 1
                    ran_all = False
                    break
                res = await s.execute(a["do"], el.id if el else None, a["value"])
                if not res.ok:
                    ran_all = False
                    break
            if i == len(window) - 1 and finding.kind == "oracle_violation":
                reproduced = ran_all and await _violated_again(s, finding, rec, obs)
        if finding.kind != "oracle_violation":
            reproduced = any(signature(sig) == finding.sig for sig in s.drain_signals())
    finally:
        await s.close()
    return {"reproduced": reproduced, "missing": missing, "seconds": round(time.monotonic() - t0, 1)}


async def _violated_again(s: BrowserSession, finding: Finding, rec: StepRecord, obs: Observation) -> bool:
    exp = dict(finding.detail["expect"])
    if exp["check"] == "count":  # the element id of the original page means nothing here
        el = locate(obs, exp.get("_ekey"), exp.get("_nth", 0))
        if el is None:
            return False
        exp["id"] = el.id
    r: CheckResult = await check(s, exp, obs)
    return r.status == "violated" and oracle_signature(exp, rec.url) == finding.sig


async def run_gate(browser, cfg, run: RunContext, ctl, llm, gcfg: GateConfig) -> dict:
    t_start = time.monotonic()
    deadline = t_start + gcfg.max_minutes * 60
    findings = sorted(run.findings.all(), key=lambda f: f.first_step)
    replays = 0
    for f in findings:
        if time.monotonic() > deadline:
            f.status = label(0, gcfg.k, tried=False)
            f.gate = {"reason": "gate time limit"}
            run.trace.event("gate_result", sig=f.sig, kind=f.kind, status=f.status, gate=f.gate)
            continue
        wins = windows_for(run.replay_log.get(f.worker, []), f.first_step, gcfg.windows)
        attempts, hits, minimal = [], 0, None
        for w in wins:
            r = await replay(browser, cfg, ctl, w, f)
            replays += 1
            attempts.append({"steps": len(w), **r})
            run.trace.event("gate_replay", sig=f.sig, steps=len(w), **r)
            if r["reproduced"]:
                hits, minimal = 1, w
                break
        if minimal is not None:
            for _ in range(gcfg.k - 1):
                r = await replay(browser, cfg, ctl, minimal, f)
                replays += 1
                attempts.append({"steps": len(minimal), **r})
                run.trace.event("gate_replay", sig=f.sig, steps=len(minimal), **r)
                hits += r["reproduced"]
        f.status = label(hits, gcfg.k, tried=bool(wins))
        f.gate = {"reproduced": hits, "k": gcfg.k, "minimal_steps": len(minimal) if minimal else None,
                  "attempts": attempts, **({} if wins else {"reason": "no step record to replay"})}
        run.trace.event("gate_result", sig=f.sig, kind=f.kind, status=f.status, gate=f.gate)

    judge_usage = {"calls": 0, "tokens": 0}
    if gcfg.judge and llm is not None:
        for f in findings:
            if f.kind == "oracle_violation" and f.status in ("confirmed", "flaky"):
                f.judge = await _judge(llm, f, judge_usage)
                run.trace.event("gate_judge", sig=f.sig, **f.judge)
    if ctl is not None:
        await asyncio.to_thread(ctl.reset)  # leave the app as the next run expects it
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    out = {"candidates": len(findings), **counts, "replays": replays,
           "minutes": round((time.monotonic() - t_start) / 60, 2), "k": gcfg.k, "windows": list(gcfg.windows),
           "judge_calls": judge_usage["calls"], "judge_tokens": judge_usage["tokens"]}
    run.trace.event("gate_done", **out)
    return out


async def _judge(llm, f: Finding, usage: dict) -> dict:
    from .llm import LLMError

    steps = "\n".join(f"- {t['do']} {t['el'] or ''} {('= ' + repr(t['value'])) if t.get('value') else ''}".rstrip()
                      for t in f.trail)
    prompt = (f"Page where the actions started: {f.page_url}\n"
              f"Actions:\n{steps or '(none)'}\n"
              f"Expectation: the app {describe(f.detail['expect'])}\n"
              f"What happened: {f.detail.get('evidence') or f.message}\n")
    try:
        data, u = await llm.complete_json(JUDGE_SYSTEM, prompt)
    except LLMError as e:
        return {"verdict": "error", "reason": str(e)[:200]}
    usage["calls"] += u.calls
    usage["tokens"] += u.total
    verdict = str(data.get("verdict", "unsure")).lower().strip()
    if verdict not in ("bug", "wrong_expectation", "unsure"):
        verdict = "unsure"
    return {"verdict": verdict, "reason": str(data.get("reason", ""))[:300], "tokens": u.total}
