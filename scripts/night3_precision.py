"""Night 3 labelled metrics per run and pooled: faults found, precision raw / gated / minus judge,
and B4 precision per rule. Output kept in logs/experiments/night3/labelled_precision.txt.
Usage: python scripts/night3_precision.py"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "src")
from webtester.labels import label_metrics, load_labels, label_of, is_true_positive
from webtester.stats import load_valid_runs
labels = load_labels()
def rule(f):
    if f["kind"] == "consistency": return f["sig"].split("|")[1]
    return f["kind"]
for tag in ("h4rep", "bs4rep"):
    print(f"\n## {tag}")
    pool = defaultdict(lambda: Counter())
    per_rule = defaultdict(Counter)
    faults = defaultdict(set)
    for agent in ("b3v3", "b4"):
        for s in load_valid_runs(agent, tag):
            rid = s["_run_id"]; fs = json.loads(Path(f"logs/experiments/runs/{rid}/findings.json").read_text(encoding="utf-8"))
            m = label_metrics(rid, fs, s, labels)
            labs = [label_of(labels, rid, f["sig"]) for f in fs]
            conf = [(f, l) for f, l in zip(fs, labs) if f.get("status") == "confirmed"]
            judged = [(f, l) for f, l in conf if (f.get("judge") or {}).get("verdict") != "wrong_expectation"]
            for name, sub in (("raw", list(zip(fs, labs))), ("gated", conf), ("judged", judged)):
                pool[agent][name + "_n"] += len(sub); pool[agent][name + "_tp"] += sum(is_true_positive(l) for _, l in sub)
            for f, l in zip(fs, labs):
                if agent == "b4": per_rule[rule(f)]["n"] += 1; per_rule[rule(f)]["tp"] += is_true_positive(l)
                if agent == "b4" and f.get("status") == "confirmed": per_rule[rule(f)]["cn"] += 1; per_rule[rule(f)]["ctp"] += is_true_positive(l)
            enabled = set(s.get("faults") or [])
            found = sorted({l.upper() for l in labs if l.upper() in enabled})
            foundc = sorted({l.upper() for f, l in conf if l.upper() in enabled})
            other = Counter(l if not l.startswith("new:") else "new" for l in labs if l and l.upper() not in enabled and l != "fp")
            for x in found: faults[agent].add(x)
            pr = lambda k: "-" if m.get(k) is None else f"{m[k]:.0%}"
            print(f"{agent:5} {rid[:15]} n={len(fs):2} fp={labs.count('fp'):2} found_all={m.get('faults_found_all','-')} {found} "
                  f"confirmed={m.get('faults_found_confirmed','-')} {foundc} P raw={pr('precision_raw')} gated={pr('precision_gated')} judged={pr('precision_judged')} other={dict(other)}")
        p = pool[agent]
        f = lambda k: f"{p[k+'_tp']}/{p[k+'_n']} = {p[k+'_tp']/p[k+'_n']:.0%}" if p[k+'_n'] else "-"
        print(f"  pooled {agent}: raw {f('raw')}; gated {f('gated')}; judged {f('judged')}; faults over runs {sorted(faults[agent])}")
    print("  b4 per rule (all: tp/n | confirmed: tp/n):")
    for r, c in sorted(per_rule.items(), key=lambda x: -x[1]["n"]):
        print(f"    {r:16} {c['tp']}/{c['n']} | {c['ctp']}/{c['cn']}")
