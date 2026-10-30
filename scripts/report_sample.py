"""D61, evaluation group 3: draw a sample of confirmed findings for the author's report-quality ratings.

Writes logs/experiments/report_quality.toml (never overwrites ratings already there): one entry per sampled
finding with what a developer would get (message, page, the steps of its trail) and empty rating fields:

  reproduced        "yes" / "no": the rater followed the steps by hand on a freshly reset app
  steps_clear, expected_vs_actual, evidence, minimal, severity_clear   0, 1 or 2 each (actionability rubric)
  triage_minutes    minutes from opening the report to deciding bug / not a bug

The protocol is docs/report_quality_protocol.md. `python -m webtester evaluate` reads the ratings
(evaluate.report_quality_block).

Usage: python scripts/report_sample.py RUN_DIR [RUN_DIR ...] [--n 20] [--seed 7]
"""

import argparse
import json
import random
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/experiments/report_quality.toml"
FIELDS = ("reproduced", "steps_clear", "expected_vs_actual", "evidence", "minimal", "severity_clear", "triage_minutes")


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    pool = []
    for d in a.runs:
        p = Path(d) / "findings.json"
        if not p.exists():
            sys.exit(f"{p} missing")
        for f in json.loads(p.read_text(encoding="utf-8")):
            if f.get("status") == "confirmed":
                pool.append((Path(d).name, f))
    have = tomllib.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    random.Random(a.seed).shuffle(pool)
    picked = [(rid, f) for rid, f in pool if f["sig"] not in have.get(rid, {})][: a.n]
    lines = [] if OUT.exists() else ["# Report-quality ratings (D61, evaluation group 3). Protocol: docs/report_quality_protocol.md",
                                     "# Fill the empty fields; leave a finding out by deleting its table.", ""]
    for rid, f in picked:
        steps = [f"{t.get('do')} {t.get('el') or t.get('value') or ''}".strip()[:100] for t in f.get("trail", [])]
        lines += [f"[{_q(rid)}.{_q(f['sig'])}]", f"message = {_q(f['message'][:300])}", f"page = {_q(f.get('page_url', ''))}",
                  f"steps = {json.dumps(steps, ensure_ascii=False)}",
                  *(f'{k} = ""' for k in FIELDS), ""]
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{len(picked)} findings sampled from {len(pool)} confirmed -> {OUT}")


if __name__ == "__main__":
    main()
