"""Run repeated experiment runs, alternating agents (so slow drift over the
session, e.g. API latency, hits every condition alike), then rebuild the
run registry.

    python scripts/run_batch.py --agents b0,b1 --reps 4 --minutes 15 --label rep
    python scripts/run_batch.py --agents b1,b3 --workers 2,4,8 --tokens 190000 --reps 5 --label g1
    python scripts/run_batch.py --config configs/bookstack.toml --agents b4 --workers 4 --tokens 190000 --reps 5 --label bs
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="b0,b1")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--start", type=int, default=1, help="number of the first repetition")
    ap.add_argument("--minutes", type=float, default=15)
    ap.add_argument("--workers", default="1", help="comma-separated worker counts, e.g. 2,4,8")
    ap.add_argument("--tokens", type=int, help="equal total token budget per run (Phase 2)")
    ap.add_argument("--label", default="rep")
    ap.add_argument("--config", help="app config, e.g. configs/bookstack.toml (default: Conduit)")
    ap.add_argument("--stop-on-unhealthy", action="store_true",
                    help="stop the batch after the first unhealthy run (e.g. daily quota exhausted)")
    args = ap.parse_args()
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    failures = 0
    workers = [int(w) for w in str(args.workers).split(",") if w.strip()]
    for rep in range(args.start, args.start + args.reps):
        for n in workers:
            for agent in agents:
                label = f"{args.label}{rep}"
                print(f"=== {agent} n={n} {label} ===", flush=True)
                cmd = [sys.executable, "-m", "webtester"] + (["--config", args.config] if args.config else []) + [
                       "run", "--agent", agent, "--minutes", str(args.minutes),
                       "--steps", "100000", "--workers", str(n), "--label", label]
                if args.tokens:
                    cmd += ["--tokens", str(args.tokens)]
                proc = subprocess.run(cmd, cwd=ROOT)
                failures += proc.returncode != 0
                if args.stop_on_unhealthy and not _last_run_healthy(agent, n, label):
                    print(f"unhealthy run ({agent} n={n} {label}), stopping the batch", flush=True)
                    subprocess.run([sys.executable, "-m", "webtester", "registry"], cwd=ROOT)
                    return 1
    subprocess.run([sys.executable, "-m", "webtester", "registry"], cwd=ROOT)
    print(f"batch done, {failures} failed run(s)")
    return 1 if failures else 0


def _last_run_healthy(agent: str, n: int, label: str) -> bool:
    runs = sorted((ROOT / "runs").glob(f"*_{agent}_n{n}_{label}"))
    if not runs or not (runs[-1] / "summary.json").exists():
        return False
    summary = json.loads((runs[-1] / "summary.json").read_text(encoding="utf-8"))
    return bool(summary.get("health", {}).get("ok"))


if __name__ == "__main__":
    sys.exit(main())
