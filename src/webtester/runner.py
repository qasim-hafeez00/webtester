"""Run orchestration: one run = one agent condition x N workers on one app state."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from .appctl import AppControl
from .browser import BrowserSession
from .budget import Budget
from .config import REPO_ROOT, RunConfig
from .crawler import run_crawler
from .frontier import Frontier, FrontierV2
from .gate import GateConfig, run_gate
from .llm import LLMClient
from .metrics import fault_detection, load_fault_catalog, reach_from_trace, summarize
from .oracles import FindingStore
from .policies import LLMPolicy, RandomPolicy
from .trace import Trace
from .worker import RunContext, load_replay_log, run_worker, save_replay_log

AGENTS = {
    "b0": "BFS crawler + random form filler (no LLM)",
    "b1": "LLM explorer (one worker = Phase 1 baseline; N workers = B2, independent)",
    "b3": "LLM explorers with a shared frontier (G1)",
    "b3local": "ablation: frontier per worker, not shared",
    "b3v2": "B3 v2: shared frontier with focus areas, nav filtering and input-class marks (I16)",
    "b3v2local": "ablation of B3 v2: the same frontier per worker, not shared",
    "b4": "B4 full system: B3 v2 shared frontier + inferred oracles (G3) + evidence gate (G2)",
    "b4nog1": "ablation A-G1: B4 without the frontier (independent workers, inferred oracles, gate)",
    "b4nog3": "ablation A-G3: B4 without inferred oracles (B3 v2 exploration + gate)",
    "random": "uniform random actions (sanity floor, no API key needed)",
}
LLM_AGENTS = ("b1", "b3", "b3local", "b3v2", "b3v2local", "b4", "b4nog1", "b4nog3")
# agent -> (frontier class, shared). Agents not listed explore without a frontier.
FRONTIERS = {"b3": (Frontier, True), "b3local": (Frontier, False), "b3v2": (FrontierV2, True),
             "b3v2local": (FrontierV2, False), "b4": (FrontierV2, True), "b4nog3": (FrontierV2, True)}
INFERRED = {"b4", "b4nog1"}  # explorer proposes checks (G3)
GATED = {"b4", "b4nog1", "b4nog3"}  # evidence gate after exploration (G2); A-G2 = B4's raw candidates


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
                        frontier = shared_frontier or (frontier_cls(shared=False) if frontier_cls else None)
                        policy = LLMPolicy(llm, cfg.app.account(w), cfg.budget.max_steps, frontier, w,
                                           inferred=agent in INFERRED)
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


async def regate(cfg: RunConfig, run_dir: Path, gate_cfg: GateConfig) -> dict:
    """Re-run the evidence gate on a finished run from its replay.jsonl, without new exploration.

    Every finding starts again as a candidate. Results go to findings_regate.json and the gate
    events to trace_regate.jsonl; the run's own findings.json, trace and summary stay untouched."""
    from .oracles import Finding

    log_path = run_dir / "replay.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"{log_path} missing: only runs made after gate v2 saved their replay log")
    trace = Trace(run_dir / "trace_regate.jsonl", run_dir.name)
    ctx = RunContext(Budget(cfg.budget), trace, FindingStore(), record_replay=True)
    ctx.replay_log = load_replay_log(log_path)
    for d in json.loads((run_dir / "findings.json").read_text(encoding="utf-8")):
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
    (run_dir / "findings_regate.json").write_text(
        json.dumps([f.to_dict() for f in ctx.findings.all()], indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def run_sync(*args, **kwargs) -> Path:
    t0 = time.monotonic()
    out = asyncio.run(run(*args, **kwargs))
    print(f"run finished in {(time.monotonic() - t0) / 60:.1f} min -> {out}")
    return out
