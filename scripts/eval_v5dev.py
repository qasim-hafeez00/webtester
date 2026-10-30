"""D59: the v5 evaluator (`webtester.evaluate`) over the development resweeps in logs/experiments/v5dev/.

Reads <label>/<ver>_<pass>_<run>_findings.json (and <ver>_<pass>_<run>_checks.jsonl when the resweep wrote
one, D59), the labels in v5dev/resweep_labels.toml (key "<label>|<sig>"; on the clean app "<label>|off|<sig>"
first, as in v5dev_compare.py) and the original run folder in runs/ for the summary and step times.
A resweep has no gate, so its findings are all candidates (precision per finding and per distinct issue only).

Usage: python scripts/eval_v5dev.py [--ver v5] [--json out.json] [--md out.md] [--unlabelled]
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from webtester.checks import read_checks  # noqa: E402
from webtester.evaluate import RunData, _trace_parts, evaluate, report_md  # noqa: E402

D = ROOT / "logs/experiments/v5dev"


def load_runs(ver: str) -> list[RunData]:
    """Every resweep of version `ver` in v5dev/, faulty and clean passes, with its labels (also used by
    scripts/lock_check.py)."""
    labels = tomllib.loads((D / "resweep_labels.toml").read_text(encoding="utf-8"))
    runs = []
    for label in ("h4rep", "bs4rep"):
        for f in sorted((D / label).glob(f"{ver}_*_findings.json")):
            _, ps, rid = f.name.split("_", 2)
            rid = rid.removesuffix("_findings.json")
            src = ROOT / "runs" / rid
            summ = json.loads((src / "summary.json").read_text(encoding="utf-8"))
            fs = json.loads(f.read_text(encoding="utf-8"))
            clean = ps == "off"
            lab = {x["sig"]: (labels.get(f"{label}|off|{x['sig']}") if clean else None) or labels.get(f"{label}|{x['sig']}", "")
                   for x in fs}
            st, end, ev = _trace_parts(src / "trace.jsonl")
            steps = ev.pop("_steps", [])
            cfg = json.loads((src / "config.json").read_text(encoding="utf-8")) if (src / "config.json").exists() else {}
            ck = read_checks(D / label / f.name.replace("_findings.json", "_checks.jsonl"))
            runs.append(RunData(rid, summ.get("run_id", rid).split("_")[1], f"{ver} resweep", clean, fs, lab,
                                set() if clean else {x.upper() for x in summ.get("faults") or []},
                                {**summ, "fault_detection": {}}, ck, st, end, ev, cfg, steps, "resweep", src))
    return runs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", default="v5", help="resweep version prefix: v4, v5 (D55) or v59 (D59)")
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--unlabelled", action="store_true", help="list signatures that still need a label (D45)")
    a = ap.parse_args()
    runs = load_runs(a.ver)
    if a.unlabelled:
        todo = sorted({(r.app, "off" if r.clean else "on", x["sig"], x["message"][:140]) for r in runs
                       for x in r.findings if not r.labels.get(x["sig"])})
        for t in todo:
            print(" | ".join(t))
        print(f"{len(todo)} unlabelled signatures")
        return
    rep = evaluate(runs)
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    md = report_md(rep)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
