"""Command line.

  python -m webtester app up [--faults F01,F02] [--build]   start the app under test
  python -m webtester app reset                             restore the seeded data
  python -m webtester app status                            health + enabled faults
  python -m webtester run --agent b1 [--minutes 15] [--steps 300] [--workers 1] [--headed]
  python -m webtester report runs/<run_id>                  print a run's summary
  python -m webtester registry                              update logs/experiments/run_registry.md
  python -m webtester compare b0 b1                         median/IQR, Mann-Whitney U, A12 over valid runs
  python -m webtester triage runs/<run_id>                  list findings, add blank labels to finding_labels.toml
  python -m webtester gate-report b4 --workers 4            G2 per run: raw vs gate-confirmed (A-G2)
  python -m webtester regate runs/<run_id>                  re-run the evidence gate on a finished run
  python -m webtester resweep runs/<run_id> [--clean]       v4 oracles over a gated run's recorded actions (no LLM)
  python -m webtester graph runs/<run_id> [--mermaid out]   state-graph summary, optional Mermaid export
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .appctl import AppControl
from .config import REPO_ROOT, load_config, load_dotenv
from .metrics import summarize
from .runner import AGENTS, run_sync

DEFAULT_CONFIG = REPO_ROOT / "configs" / "realworld.toml"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    ap = argparse.ArgumentParser(prog="webtester")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("app", help="control the app under test")
    a.add_argument("action", choices=["up", "reset", "status", "down"])
    a.add_argument("--faults", default="", help="comma-separated fault ids to enable (up only)")
    a.add_argument("--build", action="store_true")

    r = sub.add_parser("run", help="run one exploration")
    r.add_argument("--agent", choices=sorted(AGENTS), default="b1")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--minutes", type=float)
    r.add_argument("--steps", type=int)
    r.add_argument("--tokens", type=int)
    r.add_argument("--seed", type=int)
    r.add_argument("--provider")
    r.add_argument("--model")
    r.add_argument("--headed", action="store_true")
    r.add_argument("--no-reset", action="store_true")
    r.add_argument("--label", default="")
    r.add_argument("--no-gate", action="store_true", help="skip the evidence gate (B4 conditions run it by default)")
    r.add_argument("--gate-k", type=int, default=3, help="replays per finding (G2)")
    r.add_argument("--gate-minutes", type=float, default=20.0, help="time cap for the whole gate")
    r.add_argument("--no-judge", action="store_true", help="no LLM second opinion on reproduced oracle violations")

    p = sub.add_parser("report", help="summarize a finished run")
    p.add_argument("run_dir")

    sub.add_parser("registry", help="archive run summaries and rebuild the run registry")

    c = sub.add_parser("compare", help="compare two agents over their valid runs")
    c.add_argument("agent_a")
    c.add_argument("agent_b")
    c.add_argument("--label-contains", default="")
    c.add_argument("--workers", type=int, help="only runs with this many workers (e.g. 4 for B2 vs B3)")

    t = sub.add_parser("triage", help="list a run's findings with suggested labels; add blank labels")
    t.add_argument("run")
    t.add_argument("--no-write", action="store_true")

    g = sub.add_parser("gate-report", help="evidence-gate outcomes per valid run (G2, A-G2)")
    g.add_argument("agent")
    g.add_argument("--label-contains", default="")
    g.add_argument("--workers", type=int)

    rg = sub.add_parser("regate", help="re-run the evidence gate on a finished run (needs its replay.jsonl)")
    rg.add_argument("run_dir")
    rg.add_argument("--gate-k", type=int, default=3)
    rg.add_argument("--gate-minutes", type=float, default=20.0)
    rg.add_argument("--no-judge", action="store_true")
    rg.add_argument("--findings", default="findings.json",
                    help="findings file in the run folder to gate, e.g. findings_resweep.json (v4 development)")

    rs = sub.add_parser("resweep", help="replay a gated run's actions with the v4 consistency oracles (no LLM)")
    rs.add_argument("run_dir")
    rs.add_argument("--clean", action="store_true", help="BookStack: replay without the injected client-side faults")

    gp = sub.add_parser("graph", help="summary of a run's abstract state graph (graph.json)")
    gp.add_argument("run_dir")
    gp.add_argument("--mermaid", help="write a page-level Mermaid flowchart to this file")

    args = ap.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "app":
        ctl = AppControl(cfg.app)
        if args.action == "up":
            faults = [f.strip().upper() for f in args.faults.split(",") if f.strip()]
            ctl.up(faults, build=args.build)
            print(f"up at {cfg.app.base_url} with faults: {ctl.running_faults() or 'none'}")
        elif args.action == "reset":
            print(f"reset in {ctl.reset():.2f}s")
        elif args.action == "down":
            ctl._compose("down")
            print("down")
        else:
            ctl.wait_healthy(10)
            print(f"healthy at {cfg.app.base_url}; faults: {ctl.running_faults() or 'none'}")
        return 0

    if args.cmd == "run":
        cfg = cfg.with_overrides(
            budget_max_minutes=args.minutes, budget_max_steps=args.steps, budget_max_tokens=args.tokens,
            seed=args.seed, llm_provider=args.provider, llm_model=args.model,
            headless=False if args.headed else None,
        )
        from .gate import GateConfig

        gate_cfg = GateConfig(k=args.gate_k, max_minutes=args.gate_minutes, judge=not args.no_judge)
        out = run_sync(cfg, args.agent, workers=args.workers, reset=not args.no_reset, label=args.label,
                       gate=False if args.no_gate else None, gate_cfg=gate_cfg)
        _print_summary(json.loads((out / "summary.json").read_text(encoding="utf-8")))
        return 0

    if args.cmd == "registry":
        from .registry import build

        print(f"wrote {build()}")
        return 0

    if args.cmd == "compare":
        from .stats import compare, load_valid_runs

        a = load_valid_runs(args.agent_a, args.label_contains, args.workers)
        b = load_valid_runs(args.agent_b, args.label_contains, args.workers)
        names = {"b1": "B2" if args.workers and args.workers > 1 else "B1", "b4nog1": "A-G1", "b4nog3": "A-G3",
                 "b3v2local": "B3V2-LOCAL"}
        print(compare(a, b, names.get(args.agent_a, args.agent_a.upper()), names.get(args.agent_b, args.agent_b.upper())))
        return 0

    if args.cmd == "triage":
        from .labels import triage

        print(triage(args.run, write=not args.no_write))
        return 0

    if args.cmd == "gate-report":
        from .stats import gate_report, load_valid_runs

        print(gate_report(load_valid_runs(args.agent, args.label_contains, args.workers)))
        return 0

    if args.cmd == "regate":
        import asyncio

        from .gate import GateConfig
        from .runner import regate

        gate_cfg = GateConfig(k=args.gate_k, max_minutes=args.gate_minutes, judge=not args.no_judge)
        print(json.dumps(asyncio.run(regate(cfg, Path(args.run_dir), gate_cfg, args.findings)), indent=2))
        return 0

    if args.cmd == "resweep":
        import asyncio

        from .runner import resweep

        print(json.dumps(asyncio.run(resweep(cfg, Path(args.run_dir), client_faults=not args.clean)), indent=2))
        return 0

    if args.cmd == "graph":
        from .stategraph import load_graph, mermaid

        g = load_graph(Path(args.run_dir) / "graph.json")
        print(json.dumps(g["stats"], indent=2))
        for p in sorted(g["pages"], key=lambda p: -p["visits"])[:40]:
            print(f"  {p['visits']:5}  {p['route']:40} {p['name'] or ''}  ({len(p['states'])} states)")
        if args.mermaid:
            Path(args.mermaid).write_text(mermaid(g), encoding="utf-8")
            print(f"wrote {args.mermaid}")
        return 0

    if args.cmd == "report":
        run_dir = Path(args.run_dir)
        _print_summary(summarize(run_dir / "trace.jsonl"))
        return 0
    return 1


def _print_summary(s: dict) -> None:
    keys = ["run_id", "agent", "workers", "faults", "stop_reason", "steps", "wall_minutes", "unique_states",
            "unique_routes", "actions", "duplicate_action_rate", "failed_action_rate", "findings",
            "findings_by_kind", "llm_calls", "llm_retries", "policy_errors", "tokens_total", "tokens_per_step",
            "checks", "gate", "findings_confirmed", "judge_verdicts"]
    for k in keys:
        if k in s or k in keys[:19]:
            print(f"  {k:24} {s.get(k)}")
    if "fault_detection" in s:
        for fid, d in s["fault_detection"].items():
            print(f"  fault {fid:6} {'DETECTED' if d['detected'] else 'missed':9} ({d['class']})")
