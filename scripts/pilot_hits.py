"""D63: a pilot run's findings matched to fault labels by signature (resweep_labels.toml, finding_labels.toml), plus R19
and R22h check outcomes and the exposure marks. Unmatched signatures need labelling by hand.
Usage: python scripts/pilot_hits.py <run dir> [...]"""
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
labels = {}
for k, v in tomllib.loads((ROOT / "logs/experiments/v5dev/resweep_labels.toml").read_text(encoding="utf-8")).items():
    if isinstance(v, str):
        labels.setdefault(k.split("|", 1)[1], v)
for run, d in tomllib.loads((ROOT / "logs/experiments/finding_labels.toml").read_text(encoding="utf-8")).items():
    for sig, v in (d.items() if isinstance(d, dict) else []):
        lab = v if isinstance(v, str) else (v.get("label") or v.get("fault") if isinstance(v, dict) else None)
        if isinstance(lab, str):
            labels.setdefault(sig, lab)

for r in sys.argv[1:]:
    r = Path(r)
    f = json.loads((r / "findings.json").read_text(encoding="utf-8"))
    f = f if isinstance(f, list) else f.get("findings", f)
    s = json.loads((r / "summary.json").read_text(encoding="utf-8"))
    print(f"== {r.name}  steps {s.get('steps')}  states {s.get('unique_states')}  exposed {s.get('faults_exposed')}")
    hits = Counter()
    for x in f:
        lab = labels.get(x["sig"], "?")
        hits[lab] += 1
        v = (x.get("judge") or {}).get("verdict") if isinstance(x.get("judge"), dict) else x.get("verdict")
        print(f"  {lab:8} {str(v):18} {x['sig'][:110]!s}".replace("\n", " "))
    faults = sorted(k for k in hits if k[:1] in "FB" and k[1:2] in "0123456789S")
    print("  faults by label:", faults, "| unlabelled:", hits.get("?", 0))
    ck = Counter()
    for line in (r / "checks.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["rule"] in ("R19", "R22h", "R07"):
            ck[(e["rule"], e["outcome"], e.get("why", ""))] += e.get("n", 1)
    print("  checks:", dict(ck))
