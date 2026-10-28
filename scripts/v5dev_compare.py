"""D55 development comparison: v4 vs v5 oracles on the same replays of Night 3's b4 runs.

Reads logs/experiments/v5dev/<label>/{v4,v5}_{on,off}_<run>_findings.json (scripts/resweep_v5.sh) and
the labels in logs/experiments/v5dev/resweep_labels.toml (key: "<label>|<sig>", value: label as in
finding_labels.toml; a resweep finding on the clean app takes the label given for that signature
on the faulty app unless the key "<label>|off|<sig>" says otherwise). Prints, per app:
  - findings per run by rule, for v4/v5 x faulty/clean;
  - faults found per run (labels), precision on the faulty app, false alarms per run on the clean app;
  - every signature without a label, to be labelled (D45 rule).
Usage: python scripts/v5dev_compare.py [--unlabelled]
"""

import json
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "logs/experiments/v5dev"
LABELS = D / "resweep_labels.toml"
APPS = {"h4rep": ("Conduit", {"F01", "F02", "F05", "F06", "F07", "F08", "F09", "F10"}),
        "bs4rep": ("BookStack", {f"BS{i:02d}" for i in range(1, 14)})}  # reachable faults (BS14-18 need the spec)


def load(label: str):
    out = defaultdict(dict)  # (ver, pass) -> run -> findings
    for f in sorted((D / label).glob("*_findings.json")):
        ver, ps, run = f.name.split("_", 2)
        out[(ver, ps)][run.removesuffix("_findings.json")] = json.loads(f.read_text(encoding="utf-8"))
    return out


def rule(f: dict) -> str:
    return f["detail"].get("rule") or f["kind"]


def main() -> None:
    labels = tomllib.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    show_unl = "--unlabelled" in sys.argv
    for label, (app, reach) in APPS.items():
        data = load(label)
        if not data:
            continue
        print(f"\n## {app} ({label})")
        runs = sorted({r for d in data.values() for r in d})
        rules = sorted({rule(f) for d in data.values() for fs in d.values() for f in fs})
        head = ["v4 on", "v5 on", "v4 off", "v5 off"]
        print("| Rule | " + " | ".join(head) + " |  (findings per run)")
        print("|---|" + "---:|" * len(head))
        for r in rules:
            cells = []
            for ver, ps in (("v4", "on"), ("v5", "on"), ("v4", "off"), ("v5", "off")):
                d = data.get((ver, ps), {})
                n = sum(1 for fs in d.values() for f in fs if rule(f) == r)
                cells.append(f"{n / max(len(d), 1):.1f}")
            print(f"| {r} | " + " | ".join(cells) + " |")
        unl = Counter()
        for ver, ps in (("v4", "on"), ("v5", "on"), ("v4", "off"), ("v5", "off")):
            d = data.get((ver, ps), {})
            if not d:
                continue
            found, tp, n, fp_clean = [], 0, 0, 0
            for run, fs in d.items():
                hit = set()
                for f in fs:
                    lab = labels.get(f"{label}|{ps}|{f['sig']}") or labels.get(f"{label}|{f['sig']}")
                    if lab is None:
                        unl[(ps, f["sig"], f["message"][:150])] += 1
                        continue
                    n += 1
                    if ps == "on":
                        tp += lab != "fp"
                        if lab.upper() in reach:
                            hit.add(lab.upper())
                    else:
                        fp_clean += lab == "fp"
                found.append(len(hit))
            if ps == "on":
                found.sort()
                med = found[len(found) // 2]
                print(f"{ver} on: faults per run {sorted(found)} (median {med} of {len(reach)} reachable); "
                      f"precision {tp}/{n} = {tp / max(n, 1):.0%} (labelled findings)")
            else:
                print(f"{ver} off: false alarms on the clean app {fp_clean / max(len(d), 1):.2f} per run (labelled)")
        if unl:
            print(f"unlabelled signatures: {len(unl)}")
            if show_unl:
                for (ps, sig, msg), k in sorted(unl.items()):
                    print(f"  [{ps} x{k}] {sig!r}\n      {msg}")


if __name__ == "__main__":
    main()
