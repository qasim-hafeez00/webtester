"""Run orchestration: one run = one agent condition x N workers on one app state."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from .appctl import AppControl
from .browser import BrowserSession
from .budget import Budget
from .config import REPO_ROOT, RunConfig
from .crawler import run_crawler
from .consistency import SweepState, Sweeper
from .frontier import Frontier, FrontierV2, FrontierV3
from .gate import GateConfig, run_gate
from .llm import LLMClient
from .metrics import fault_detection, load_fault_catalog, reach_from_trace, summarize
from .oracles import FindingStore
from .policies import LLMPolicy, RandomPolicy
from .stategraph import StateGraph
from .trace import Trace
from .worker import RunContext, load_replay_log, run_worker, save_replay_log

AGENTS = {
    "b0": "BFS crawler + random form filler (no LLM)",
    "b1": "LLM explorer (one worker = Phase 1 baseline; N workers = B2, independent)",
    "b3": "LLM explorers with a shared frontier (G1)",
    "b3local": "ablation: frontier per worker, not shared",
    "b3v2": "B3 v2: shared frontier with focus areas, nav filtering and input-class marks (I16)",
    "b3v2local": "ablation of B3 v2: the same frontier per worker, not shared",
    "b3v3": "B3 v3 (v4, D49): B3 v2 + state-graph travel + compact prompt, implicit oracles only",
    "b4": "B4 full system (v4, D49): B3 v3 + memory, intent-verified and consistency oracles, LLM checks (G3) + gate (G2)",
    "b4det": "ablation (v4): B4 without the LLM-based oracles (no checks, no cited contradictions)",
    "b4nog1": "ablation A-G1: B4 without the frontier (independent workers, G3 v4, gate)",
    "b4nog3": "ablation A-G3: B4 without G3 (B3 v3 exploration + gate, implicit oracles only)",
    "random": "uniform random actions (sanity floor, no API key needed)",
}
LLM_AGENTS = ("b1", "b3", "b3local", "b3v2", "b3v2local", "b3v3", "b4", "b4det", "b4nog1", "b4nog3")
# agent -> (frontier class, shared). Agents not listed explore without a frontier.
# Harness v4 (D49): the B4 family explores with FrontierV3 (graph travel, compact prompt), as b3v3.
FRONTIERS = {"b3": (Frontier, True), "b3local": (Frontier, False), "b3v2": (FrontierV2, True),
             "b3v2local": (FrontierV2, False), "b3v3": (FrontierV3, True), "b4": (FrontierV3, True),
             "b4det": (FrontierV3, True), "b4nog3": (FrontierV3, True)}
INFERRED = {"b4", "b4nog1"}  # explorer proposes checks and cited contradictions (G3, LLM-based)
CONSISTENCY = {"b4", "b4det", "b4nog1"}  # memory + intent-verified + consistency oracles (G3 v4)
GATED = {"b4", "b4det", "b4nog1", "b4nog3"}  # evidence gate after exploration (G2); A-G2 = B4's raw candidates


def _git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


async def run(cfg: RunConfig, agent: str, workers: int = 1, reset: bool = True, label: str = "",
              gate: bool | None = None, gate_cfg: GateConfig | None = None) -> Path:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; choose from {', '.join(AGENTS)}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}_{cfg.app.name}_{agent}_n{workers}" + (f"_{label}" if label else "")
    run_dir = (REPO_ROOT / cfg.out_dir / run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    faults: list[str] = []
    reset_s = None
    ctl = AppControl(cfg.app) if cfg.app.compose_dir else None
    if ctl:
        ctl.wait_healthy(30)
        faults = ctl.running_faults()
        if reset:
            reset_s = ctl.reset()
    if cfg.app.fault_script:  # client-side injected faults go into every browser context (D33)
        cfg = replace(cfg, client_faults=tuple(faults))

    trace = Trace(run_dir / "trace.jsonl", run_id)
    llm = LLMClient(cfg.llm) if agent in LLM_AGENTS else None
    frontier_cls, shared = FRONTIERS.get(agent, (None, False))
    shared_frontier = frontier_cls(shared=True) if frontier_cls and shared else None
    gate_on = agent in GATED if gate is None else gate
    gate_cfg = gate_cfg or GateConfig()
    cfg_dict = cfg.to_dict()
    trace.event("run_start", run_id=run_id, agent=agent, workers=workers, faults=faults, reset_seconds=reset_s,
                config=cfg_dict, git=_git_rev(), python=platform.python_version(), host=platform.node(),
                inferred=agent in INFERRED, gate=(gate_cfg.__dict__ if gate_on else None))
    (run_dir / "config.json").write_text(json.dumps(cfg_dict, indent=2), encoding="utf-8")

    ctx = RunContext(Budget(cfg.budget), trace, FindingStore(), record_replay=gate_on)
    ctx.graph = StateGraph()  # recorded in every condition (passive outside b3v3 / the B4 family)
    if isinstance(shared_frontier, FrontierV3):
        shared_frontier.graph = ctx.graph
    if agent in CONSISTENCY:
        ctx.sweep = SweepState(ctx.graph)
    reasons: list[str] = []
    t_explore = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=cfg.headless)
        try:
            sessions = [BrowserSession(browser, cfg, w) for w in range(1, workers + 1)]
            for s in sessions:
                await s.start()
            try:
                tasks = []
                for s in sessions:
                    w = s.worker
                    if agent == "b0":
                        tasks.append(run_crawler(ctx, s, cfg, w))
                    elif agent in LLM_AGENTS:
                        frontier = shared_frontier or (_frontier(frontier_cls, False, ctx.graph) if frontier_cls else None)
                        notes = None
                        if ctx.sweep is not None:
                            ctx.sweepers[w] = Sweeper(ctx.sweep, w, cfg.app.account(w), llm_rules=agent in INFERRED)
                            notes = (lambda w=w: ctx.sweep.memory.notes(w))
                        policy = LLMPolicy(llm, cfg.app.account(w), cfg.budget.max_steps, frontier, w,
                                           inferred=agent in INFERRED, intents=agent in CONSISTENCY, notes=notes)
                        tasks.append(run_worker(ctx, s, policy, w, cfg.budget.max_steps))
                    else:
                        tasks.append(run_worker(ctx, s, RandomPolicy(cfg.seed * 1000 + w), w, cfg.budget.max_steps))
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for w, r in enumerate(results, 1):
                    if isinstance(r, BaseException):
                        trace.event("worker_crash", worker=w, error=f"{type(r).__name__}: {r}"[:2000])
                        reasons.append(f"w{w}:crash")
                    else:
                        reasons.append(f"w{w}:{r}")
            finally:
                for s in sessions:
                    await s.close()
            if ctl and faults:
                # Read before the gate: its replays fire the same faults again.
                try:
                    fired = await asyncio.to_thread(ctl.fired_faults, t_explore, time.time())
                    trace.event("backend_exposure", faults=fired)
                except Exception as e:  # noqa: BLE001 - exposure is analysis only, never fatal
                    trace.event("backend_exposure_error", error=f"{type(e).__name__}: {e}"[:500])
            if gate_on:
                # Exploration is over (its budget is spent). The gate runs outside that budget
                # and reports its own cost (replays, minutes, judge tokens).
                save_replay_log(run_dir / "replay.jsonl", ctx.replay_log)
                try:
                    await run_gate(browser, cfg, ctx, ctl, llm, gate_cfg)
                except Exception as e:  # noqa: BLE001 - a gate failure must not lose the run
                    trace.event("gate_error", error=f"{type(e).__name__}: {e}"[:2000])
        finally:
            await browser.close()

    findings = [f.to_dict() for f in ctx.findings.all()]
    if shared_frontier is not None:
        trace.event("frontier", **shared_frontier.stats())
    ctx.graph.save(run_dir / "graph.json")
    trace.event("graph", **ctx.graph.stats())
    if ctx.sweep is not None:
        _save_memory(run_dir / "memory.jsonl", ctx.sweep)
        trace.event("sweep", probes=ctx.sweep.probes, link_checks=ctx.sweep.link_checks, **_probe_counts(ctx.sweep),
                    events=dict(Counter(f"{e.verb}:{e.status}" for e in ctx.sweep.memory.events)))
    trace.event("run_end", reasons=reasons, budget=ctx.budget.snapshot(),
                llm_usage=(llm.usage.__dict__ if llm else None), cost_usd=(llm.cost_usd() if llm else 0.0))
    trace.close()

    (run_dir / "findings.json").write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = summarize(run_dir / "trace.jsonl")
    catalog_path = REPO_ROOT / (cfg.app.compose_dir or "") / "faults" / "faults.toml"
    if faults and catalog_path.exists():
        catalog = load_fault_catalog(catalog_path)
        fired = set(summary.get("faults_exposed") or ()) if summary.get("exposure_markers") else None
        summary["fault_detection"] = fault_detection(findings, faults, catalog, fired)
        if (reach := reach_from_trace(run_dir / "trace.jsonl", faults, catalog)) is not None:
            summary["fault_reach"] = reach
        if gate_on:
            confirmed = [f for f in findings if f["status"] == "confirmed"]
            summary["fault_detection_confirmed"] = fault_detection(confirmed, faults, catalog, fired)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return run_dir


async def regate(cfg: RunConfig, run_dir: Path, gate_cfg: GateConfig, findings: str = "findings.json") -> dict:
    """Re-run the evidence gate on a finished run from its replay.jsonl, without new exploration.

    Every finding starts again as a candidate. Results go to findings_regate.json and the gate
    events to trace_regate.jsonl; the run's own findings.json, trace and summary stay untouched.
    `findings` names another findings file to gate (e.g. findings_resweep.json, v4 development);
    its results go to <stem>_regate.json and trace_<stem>_regate.jsonl."""
    from .oracles import Finding

    log_path = run_dir / "replay.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"{log_path} missing: only runs made after gate v2 saved their replay log")
    stem = "" if findings == "findings.json" else Path(findings).stem + "_"
    trace = Trace(run_dir / f"trace_{stem}regate.jsonl", run_dir.name)
    ctx = RunContext(Budget(cfg.budget), trace, FindingStore(), record_replay=True)
    ctx.replay_log = load_replay_log(log_path)
    for d in json.loads((run_dir / findings).read_text(encoding="utf-8")):
        ctx.findings.by_sig[d["sig"]] = Finding(**{**d, "status": "candidate", "gate": {}, "judge": None})
    ctl = AppControl(cfg.app) if cfg.app.compose_dir else None
    llm = LLMClient(cfg.llm) if gate_cfg.judge else None
    trace.event("regate_start", gate=gate_cfg.__dict__, git=_git_rev())
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=cfg.headless)
        try:
            out = await run_gate(browser, cfg, ctx, ctl, llm, gate_cfg)
        finally:
            await browser.close()
    trace.close()
    (run_dir / (f"{stem}regate.json" if stem else "findings_regate.json")).write_text(
        json.dumps([f.to_dict() for f in ctx.findings.all()], indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _frontier(cls, shared: bool, graph: StateGraph):
    return cls(shared=shared, graph=graph) if cls is FrontierV3 else cls(shared=shared)


def _save_memory(path: Path, sweep: SweepState) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for e in sweep.memory.events:
            fh.write(json.dumps({k: v for k, v in e.__dict__.items()}, ensure_ascii=False) + "\n")


async def resweep(cfg: RunConfig, run_dir: Path, client_faults: bool = True) -> dict:
    """Development tool (v4, D49): replay every worker's whole recorded log (replay.jsonl) once,
    with the v4 consistency oracles attached, no LLM. One reset at the start; workers replay one
    after another and share one memory, so data a worker created stays for the next one. Old runs
    have no intents, so verbs come from the word lists. Writes findings_resweep.json and returns
    counts per rule. `client_faults=False` replays BookStack without its injected faults (the
    clean app); Conduit's faults are server-side, so start it without faults instead."""
    from .gate import locate

    log = load_replay_log(run_dir / "replay.jsonl")
    ctl = AppControl(cfg.app) if cfg.app.compose_dir else None
    faults = ctl.running_faults() if ctl else []
    if cfg.app.fault_script:
        cfg = replace(cfg, client_faults=tuple(faults) if client_faults else ())
    if ctl:
        await asyncio.to_thread(ctl.reset)
    store = FindingStore()
    state = SweepState(StateGraph())
    replayed = missing = 0
    t0 = time.monotonic()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=cfg.headless)
        try:
            for worker, records in sorted(log.items()):
                s = BrowserSession(browser, cfg, worker)
                await s.start(storage_state=records[0].storage)
                sw = Sweeper(state, worker, cfg.app.account(worker), llm_rules=False)
                try:
                    await s.goto(records[0].url)
                    for rec in records:
                        obs = await s.observe()
                        if obs.url != rec.url:
                            await s.goto(rec.url)
                            obs = await s.observe()
                        plan, done = [], []
                        for a in rec.actions:
                            el = locate(obs, a["ekey"], a["nth"])
                            plan.append({"do": a["do"], "id": el.id if el else None, "value": a["value"]})
                        await sw.before(s, obs, plan)
                        for a, pa in zip(rec.actions, plan):
                            if a["ekey"] and pa["id"] is None:
                                missing += 1
                                break
                            el = obs.element(pa["id"]) if pa["id"] else None
                            res = await s.execute(a["do"], pa["id"], a["value"])
                            done.append({"do": a["do"], "id": pa["id"], "value": a["value"],
                                         "el": el.describe() if el else None, "ekey": a["ekey"], "nth": a["nth"],
                                         "ok": res.ok, "url_after": res.url_after})
                            if not res.ok:
                                break
                        await sw.actions_done(s)
                        replayed += 1
                        sigs = await sw.after(s, obs, done, rec.step, rec.intent)
                        store.ingest(sigs, step=rec.step, worker=worker, state="", trail=[])
                finally:
                    await s.close()
        finally:
            await browser.close()
    found = [f.to_dict() for f in store.all()]
    name = "findings_resweep.json" if client_faults else "findings_resweep_clean.json"
    (run_dir / name).write_text(json.dumps(found, indent=2, ensure_ascii=False), encoding="utf-8")
    by_rule = Counter(f["detail"].get("rule") for f in found)
    return {"run": run_dir.name, "faults": list(cfg.client_faults) if cfg.app.fault_script else faults,
            "steps_replayed": replayed, "missing_elements": missing, "minutes": round((time.monotonic() - t0) / 60, 1),
            "findings": len(found), "by_rule": dict(by_rule), "probes": state.probes, "link_checks": state.link_checks,
            **_probe_counts(state), "events": dict(Counter(f"{e.verb}:{e.status}" for e in state.memory.events)),
            "file": name}


def _probe_counts(state: SweepState) -> dict:
    """Browser work of the probes added before the v4 lock (D50): reported, since it costs time, not tokens."""
    return {"access_probes": sum(state.access_probes.values()), "reloads": state.reloads,
            "mutation_forms": state.mutation_forms, "mutation_submits": state.mutation_submits}


def run_sync(*args, **kwargs) -> Path:
    t0 = time.monotonic()
    out = asyncio.run(run(*args, **kwargs))
    print(f"run finished in {(time.monotonic() - t0) / 60:.1f} min -> {out}")
    return out
