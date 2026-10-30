"""Evidence gate (G2): reproduce before report.

After exploration ends, every candidate finding is replayed from the worker's
own step log (worker.StepRecord) in a fresh browser context restored to the
session that worker had, with the app's data reset before every replay:

1. Minimise: replay the last 1 step, then the last `windows[1]` steps, ... up to
   the finding's step, until one replay reproduces the finding. That window is
   the finding's minimal trace. A window size of 0 means the worker's whole log
   from its first step: the only window that rebuilds data the worker created
   earlier (its own account, articles), which the reset wipes (gate v2, I32).
2. Confirm: replay the minimal trace until there are `k` replays in total.
3. Label: confirmed (k/k), flaky (1..k-1 of k), rejected (replays ran to the
   end and none reproduced it), unverified (gate time ran out first, or no replay
   could even run its actions: elements missing on a reset app, e.g. data another
   worker created; harness v3, D46).

"Reproduced" means the same finding signature again: the same implicit signal
(HTTP 5xx, JS error, ...) anywhere in the replay, or for an inferred-oracle
finding the same check failing again after the last step's actions. A v4
consistency finding (D49) is reproduced when a fresh Sweeper, fed the replayed
steps (and the recorded intents), raises the same rule on the same subject: the
memory it needs is rebuilt by the replay itself, so short windows usually miss
and the full-prefix window (0) is what reproduces memory-based rules.

Replays need no LLM: they repeat recorded actions, locating each element by its
position-independent key plus its ordinal among same-key elements. The only LLM
use is the optional judge, a second opinion on reproduced oracle violations
(wrong expectation or real bug?), which never changes the replay label.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from dataclasses import dataclass, replace

from .browser import BrowserSession, Observation
from .consistency import SweepState, Sweeper
from .inferred import CheckResult, check, clicked_active, describe, oracle_signature
from .oracles import Finding, signature
from .worker import RunContext, StepRecord

JUDGE_SYSTEM = """You review a failed check reported by an automated web-app tester. The tester predicted what a \
correct app must show after some actions; the prediction failed, and it failed again every time the actions \
were replayed on a freshly reset app. Decide whether this reveals a BUG in the app, or a WRONG EXPECTATION by \
the tester (it expected other wording, a feature the app does not have, or behaviour a correct app need not \
have). Reply with one JSON object and nothing else:
{"verdict": "bug" | "wrong_expectation" | "unsure", "reason": "<at most 30 words>"}"""

# v4 (D49): consistency findings are not predictions, so the judge is asked about the conflict.
JUDGE_CONSISTENCY = """You review a possible bug reported by an automated web-app tester. It compared what a web \
app showed with itself and with what the tester did, and found the conflict below. It happened again every time \
the tester's actions were replayed on a freshly reset app. Decide whether a CORRECT app could show this (for \
example: the list is only a preview, the item was changed by another user, the wording differs but the meaning \
agrees) or whether it reveals a BUG. Reply with one JSON object and nothing else:
{"verdict": "bug" | "wrong_expectation" | "unsure", "reason": "<at most 30 words>"}
("wrong_expectation" = a correct app can show this.)"""


# C4 (D61): rules whose verdict depends on the current time; their replays run on the recorded step's clock
TIME_RULES = ("R08", "R18", "R72", "R72c", "R36", "R20t")


@dataclass(frozen=True)
class GateConfig:
    k: int = 3
    windows: tuple[int, ...] = (1, 4, 0)  # minimal-trace search: suffix lengths in steps, 0 = full prefix
    max_minutes: float = 20.0
    judge: bool = True
    t1_first: bool = True  # C6 (D60): T1 findings are replayed first, so the time cap never costs them
    ddmin: bool = True  # C5: shrink a confirmed window by dropping prefix steps (at most `ddmin_tries` replays)
    ddmin_tries: int = 4
    engines: tuple = ()  # X9: replay each confirmed finding once more in these engines (firefox, webkit)


def label(reproduced: int, k: int, tried: bool, ran: bool = True) -> str:
    """`ran`: at least one replay ran all its actions. A finding no replay could run is
    unverified, not rejected: the gate has no evidence against it (D46)."""
    if not tried:
        return "unverified"
    if reproduced == 0:
        return "rejected" if ran else "unverified"
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
        start = 0 if n <= 0 else max(0, idx - n + 1)
        if start in seen:
            continue
        seen.add(start)
        out.append(log[start:idx + 1])
    return out


async def replay(browser, cfg, ctl, window: list[StepRecord], finding: Finding, context_kw: dict | None = None,
                 annot=None) -> dict:
    """One replay of `window` on freshly reset data. Returns {reproduced, missing, failed, reason, seconds}."""
    t0 = time.monotonic()
    if ctl is not None:
        await asyncio.to_thread(ctl.reset)
    # v5 (D60): replays read every element (no ranking cap: the original worker's ranking cannot be rebuilt),
    # restore session storage too (C1), and take the context options of an environment axis when given
    rcfg = replace(cfg, max_elements=cfg.max_elements * max(1, getattr(cfg, "observe_pool", 1)), observe_pool=1)
    s = BrowserSession(browser, rcfg, finding.worker)
    await s.start(storage_state=window[0].storage, session_storage=getattr(window[0], "session", None),
                  context_kw=context_kw)
    t_rec = getattr(window[0], "t", 0.0)
    if t_rec and (finding.detail or {}).get("rule") in TIME_RULES:  # C4 (D61): the browser clock of the recorded step
        try:
            await s.page.clock.install(time=datetime.fromtimestamp(t_rec))
        except Exception:  # noqa: BLE001 - an engine without a controllable clock replays in real time
            pass
    missing = failed = 0
    reproduced = False
    sw = Sweeper(SweepState(), finding.worker, cfg.app.account(finding.worker)) \
        if finding.kind == "consistency" else None
    if sw is not None and annot is not None:  # O11: the run's annotations, read only (no LLM call in a replay)
        from .annotate import Annotator

        sw.st.annotator = Annotator(None, annot.cache)
    try:
        await s.goto(window[0].url)
        for i, rec in enumerate(window):
            obs = await s.observe()
            if obs.url != rec.url:
                await s.goto(rec.url)
                obs = await s.observe()
            ran_all = True
            clicked, done = [], []
            if sw is not None:
                plan = [{"do": a["do"], "id": (el.id if (el := locate(obs, a["ekey"], a["nth"])) else None),
                         "value": a["value"]} for a in rec.actions]
                await sw.before(s, obs, plan)
            for a in rec.actions:
                el = locate(obs, a["ekey"], a["nth"])
                if a["do"] == "click":
                    clicked.append(el)
                if a["ekey"] and el is None:
                    href = _href_of_key(a["ekey"])
                    if a["do"] == "click" and href:  # C6: a link gone after the reset: follow its address
                        res = await s.goto(href)
                        done.append({"do": "navigate", "id": None, "value": href, "el": None, "ekey": None, "nth": 0,
                                     "ok": res.ok, "url_after": res.url_after})
                        if res.ok:
                            continue
                    missing += 1
                    ran_all = False
                    break
                res = await s.execute(a["do"], el.id if el else None, a["value"])
                done.append({"do": a["do"], "id": el.id if el else None, "value": a["value"],
                             "el": el.describe() if el else None, "ekey": a["ekey"], "nth": a["nth"],
                             "ok": res.ok, "url_after": res.url_after})
                if not res.ok:
                    failed += 1
                    ran_all = False
                    break
            if sw is not None:
                await sw.actions_done(s)
                sigs = await sw.after(s, obs, done, rec.step, getattr(rec, "intent", None), getattr(rec, "suspect", None))
                reproduced = reproduced or any(x.detail.get("sig") == finding.sig for x in sigs)
            if i == len(window) - 1 and finding.kind == "oracle_violation":
                reproduced = ran_all and await _violated_again(s, finding, rec, obs, clicked_active(clicked))
        if finding.kind not in ("oracle_violation", "consistency"):
            reproduced = any(signature(sig) == finding.sig for sig in s.drain_signals())
    finally:
        await s.close()
    reason = ("reproduced" if reproduced else "missing elements" if missing else "action failed" if failed
              else "ran, not reproduced")
    return {"reproduced": reproduced, "missing": missing, "failed": failed, "reason": reason,
            "seconds": round(time.monotonic() - t0, 1)}


def _href_of_key(ekey: str | None) -> str:
    """The href in an element key (tag|type|role|text|label|href), when the element was an in-app link."""
    parts = (ekey or "").split("|")
    href = parts[5] if len(parts) > 5 and parts[0] == "a" else ""
    return href if href and not href.startswith(("#", "javascript:")) else ""


async def _violated_again(s: BrowserSession, finding: Finding, rec: StepRecord, obs: Observation,
                          active_click: bool = False) -> bool:
    exp = dict(finding.detail["expect"])
    if exp["check"] == "count":  # the element id of the original page means nothing here
        el = locate(obs, exp.get("_ekey"), exp.get("_nth", 0))
        if el is None:
            return False
        exp["id"] = el.id
    r: CheckResult = await check(s, exp, obs, active_click)
    return r.status == "violated" and oracle_signature(exp, rec.url) == finding.sig


def _tier_rank(f: Finding) -> int:
    t = (f.detail or {}).get("tier") or ("implicit" if f.kind not in ("consistency", "oracle_violation") else "T3")
    return {"T1": 0, "implicit": 1, "T2": 2, "T3": 3}.get(t, 2)


async def _ddmin(browser, cfg, ctl, window: list, f: Finding, tries: int, annot=None) -> tuple[list, int]:
    """C5: drop prefix steps (never the finding's own step) while the finding still reproduces; greedy,
    halves first, then single steps, at most `tries` replays. Returns the smaller window and replays used."""
    used, cur = 0, list(window)
    if len(cur) <= 2:
        return cur, 0
    cands = [cur[len(cur) // 2:]] + [cur[:i] + cur[i + 1:] for i in range(len(cur) - 1)]
    for cand in cands:
        if used >= tries or len(cand) >= len(cur):
            continue
        r = await replay(browser, cfg, ctl, cand, f, **({"annot": annot} if annot is not None else {}))
        used += 1
        if r["reproduced"]:
            cur = cand
    return cur, used


async def _engine_check(engines: dict, cfg, ctl, window: list, f: Finding) -> dict:
    """X9: one replay per extra engine. A finding that holds in Chromium only is 'engine-specific' (an EN1
    candidate), not harness-suspect: browser-specific bugs are real (v5 plan X9)."""
    out = {}
    for name, br in engines.items():
        if br is None:
            out[name] = "unavailable"
            continue
        try:
            out[name] = (await replay(br, cfg, ctl, window, f))["reproduced"]
        except Exception as e:  # noqa: BLE001
            out[name] = f"error: {type(e).__name__}"
    return out


def _annot(run: RunContext) -> dict:
    """O11: the run's annotations for a replay, as keyword arguments (none when the run has no annotator)."""
    a = getattr(getattr(run, "sweep", None), "annotator", None)
    return {"annot": a} if a is not None else {}


async def run_gate(browser, cfg, run: RunContext, ctl, llm, gcfg: GateConfig, pw=None) -> dict:
    t_start = time.monotonic()
    deadline = t_start + gcfg.max_minutes * 60
    findings = sorted(run.findings.all(), key=lambda f: (_tier_rank(f) if gcfg.t1_first else 0, f.first_step))
    engines: dict = {}
    for name in gcfg.engines:
        try:
            engines[name] = await getattr(pw, name).launch(headless=True) if pw is not None else None
        except Exception:  # noqa: BLE001 - not installed: reported per finding
            engines[name] = None
    replays = 0
    for f in findings:
        if (f.gate or {}).get("env"):  # R71: confirmed by its own two axis reads (envcheck.py)
            run.trace.event("gate_result", sig=f.sig, kind=f.kind, status=f.status, gate=f.gate)
            continue
        if time.monotonic() > deadline:
            f.status = label(0, gcfg.k, tried=False)
            f.gate = {"reason": "gate time limit"}
            run.trace.event("gate_result", sig=f.sig, kind=f.kind, status=f.status, gate=f.gate)
            continue
        wins = windows_for(run.replay_log.get(f.worker, []), f.first_step, gcfg.windows)
        attempts, hits, minimal = [], 0, None
        for w in wins:
            r = await replay(browser, cfg, ctl, w, f, **_annot(run))
            replays += 1
            attempts.append({"steps": len(w), **r})
            run.trace.event("gate_replay", sig=f.sig, steps=len(w), **r)
            if r["reproduced"]:
                hits, minimal = 1, w
                break
        if minimal is not None:
            for _ in range(gcfg.k - 1):
                r = await replay(browser, cfg, ctl, minimal, f, **_annot(run))
                replays += 1
                attempts.append({"steps": len(minimal), **r})
                run.trace.event("gate_replay", sig=f.sig, steps=len(minimal), **r)
                hits += r["reproduced"]
        ran = any(a.get("reason", "ran, not reproduced") in ("reproduced", "ran, not reproduced") for a in attempts)
        f.status = label(hits, gcfg.k, tried=bool(wins), ran=ran)
        extra = {}
        if f.status == "confirmed" and minimal is not None and gcfg.ddmin and time.monotonic() < deadline:
            small, used = await _ddmin(browser, cfg, ctl, minimal, f, gcfg.ddmin_tries, **_annot(run))
            replays += used
            extra["ddmin_steps"] = len(small)
            minimal = small
        if f.status == "confirmed" and engines and minimal is not None:
            ok = await _engine_check(engines, cfg, ctl, minimal, f)
            replays += sum(1 for v in ok.values() if isinstance(v, bool))
            extra["engines"] = ok
            if ok and all(v is False for v in ok.values()):
                extra["engine_specific"] = "chromium"
        causes = sorted({a["reason"] for a in attempts if a.get("reason") not in ("reproduced", None)})
        f.gate = {"reproduced": hits, "k": gcfg.k, "minimal_steps": len(minimal) if minimal else None,
                  "attempts": attempts, **extra, **({"causes": causes} if causes else {}),
                  **({} if wins else {"reason": "no step record to replay"}),
                  **({"reason": "could not replay"} if wins and not ran else {})}
        run.trace.event("gate_result", sig=f.sig, kind=f.kind, status=f.status, gate=f.gate)

    judge_usage = {"calls": 0, "tokens": 0}
    if gcfg.judge and llm is not None:
        for f in findings:
            # every consistency tier (D55): Night 3's worst rule (I-create) was T1 and never judged; reported only
            judged = f.kind in ("oracle_violation", "consistency")
            if judged and f.status in ("confirmed", "flaky"):
                f.judge = await _judge(llm, f, judge_usage)
                run.trace.event("gate_judge", sig=f.sig, **f.judge)
    for br in engines.values():
        if br is not None:
            await br.close()
    if ctl is not None:
        await asyncio.to_thread(ctl.reset)  # leave the app as the next run expects it
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    out = {"candidates": len(findings), **counts, "replays": replays,
           "minutes": round((time.monotonic() - t_start) / 60, 2), "k": gcfg.k, "windows": list(gcfg.windows),
           "judge_calls": judge_usage["calls"], "judge_tokens": judge_usage["tokens"],
           "engines": list(gcfg.engines), "engine_specific": sum(1 for f in findings if (f.gate or {}).get("engine_specific"))}
    run.trace.event("gate_done", **out)
    return out


async def _judge(llm, f: Finding, usage: dict) -> dict:
    from .llm import LLMError

    steps = "\n".join(f"- {t['do']} {t['el'] or ''} {('= ' + repr(t['value'])) if t.get('value') else ''}".rstrip()
                      for t in f.trail)
    if f.kind == "consistency":
        system = JUDGE_CONSISTENCY
        prompt = (f"Page: {f.page_url}\nTester's last actions:\n{steps or '(none)'}\n"
                  f"Conflict ({f.detail.get('rule')}): {f.message}\nEvidence: {f.detail.get('evidence') or '-'}\n")
    else:
        system = JUDGE_SYSTEM
        prompt = (f"Page where the actions started: {f.page_url}\n"
                  f"Actions:\n{steps or '(none)'}\n"
                  f"Expectation: the app {describe(f.detail['expect'])}\n"
                  f"What happened: {f.detail.get('evidence') or f.message}\n")
    try:
        data, u = await llm.complete_json(system, prompt)
    except LLMError as e:
        return {"verdict": "error", "reason": str(e)[:200]}
    usage["calls"] += u.calls
    usage["tokens"] += u.total
    verdict = str(data.get("verdict", "unsure")).lower().strip()
    if verdict not in ("bug", "wrong_expectation", "unsure"):
        verdict = "unsure"
    return {"verdict": verdict, "reason": str(data.get("reason", ""))[:300], "tokens": u.total}
