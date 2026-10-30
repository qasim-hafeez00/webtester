"""v5.0 lock check (D62; v5 plan section 6 phase 1, section 12.2) over the development resweeps in
logs/experiments/v5dev/ (loaded as in scripts/eval_v5dev.py).

Run level, per development app (faulty pass and clean pass of `--ver`, reference resweep `--ref`):
  recall        mutation score and median per-run total recall not below the reference resweep's
  precision     precision per finding >= 0.90 over the faulty pass, with no finding unlabelled
  false alarms  clean false alarms per run <= 0.5, with no clean finding unlabelled
Rule level (section 12.2), for every built rule:
  (1) a fixture test names it; (2) the resweep logged check rows for it, armed at least once;
  (3) one of its families has a seeded fault on a development app; (4) its clean findings are all labelled
  (false alarms counted, not hidden); (5) its faulty findings are all labelled (precision measured).
A rule enters the lock when (1), (2), (4) and (5) hold. (3) is reported, not required: most v5 families have
no development fault yet (tracker), and the plan counts such rules as measured for false alarms only.
The measured tier is T1 at n >= 5 and precision >= 0.90 (evaluate.precision_block).

The 'without' section recomputes the run-level numbers with the rules whose own precision is below the floor
left out, so the decision to drop a rule from v5.0 is made on numbers. The lock itself is the user's decision.

Usage: python scripts/lock_check.py [--ver v59] [--ref v5] [--md out.md] [--json out.json]
"""

import argparse
import json
import re
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_v5dev import load_runs  # noqa: E402
from webtester.checks import ARMED  # noqa: E402
from webtester.evaluate import (false_alarm_block, label_kind, load_catalog, precision_block,  # noqa: E402
                                recall_block, rule_of)
from webtester.families import built_rules  # noqa: E402
from webtester.labels import is_true_positive  # noqa: E402

PRECISION_FLOOR = 0.90  # per finding (phase 1 exit criterion)
FALSE_ALARMS_PER_RUN = 0.5  # clean app
TRACKER = ROOT / "docs/family_tracker.toml"
IMPLICIT = {"http_5xx", "page_error", "request_failed", "console_error"}


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def app_level(runs: list, ref: list) -> dict:
    """The three phase-1 criteria per app, against the reference resweep."""
    catalog = load_catalog()
    out = {}
    for app in sorted({r.app for r in runs}):
        fa = [r for r in runs if r.app == app and not r.clean]
        cl = [r for r in runs if r.app == app and r.clean]
        rf = [r for r in ref if r.app == app and not r.clean]
        prec, rec, fal = precision_block(fa), recall_block(fa, catalog), false_alarm_block(cl)
        ms = rec["mutation_score"].get(app, {})
        med = _median([x["total_recall"] for x in rec["per_run"]])
        rrec = recall_block(rf, catalog) if rf else None
        rms = (rrec or {}).get("mutation_score", {}).get(app, {})
        rmed = _median([x["total_recall"] for x in rrec["per_run"]]) if rrec else None
        p = prec["raw"]["precision"]
        fpr = (fal.get("per_run") or {}).get("rate")
        out[app] = {
            "faulty_runs": len(fa), "clean_runs": len(cl),
            "recall": {"mutation_score": ms, "ref_mutation_score": rms, "median_total": med, "ref_median_total": rmed,
                       "ok": None if rrec is None else ((ms.get("score") or 0) >= (rms.get("score") or 0)
                                                        and (med or 0) >= (rmed or 0))},
            "precision": {**prec["raw"], "unlabelled": prec["unlabelled"],
                          "ok": None if prec["unlabelled"] else (p is not None and p >= PRECISION_FLOOR)},
            "false_alarms": {"n": fal.get("false_alarms"), "per_run": fpr, "ci95": (fal.get("per_run") or {}).get("ci95"),
                             "unlabelled": fal.get("unlabelled", 0), "by_rule": fal.get("by_rule", {}),
                             "ok": None if fal.get("unlabelled") or not cl else fpr <= FALSE_ALARMS_PER_RUN},
            "found": rec["across_runs"].get(app, {}).get("found", []),
        }
        out[app]["ok"] = all(out[app][k]["ok"] for k in ("recall", "precision", "false_alarms"))
    return out


def _tested_rules() -> set[str]:
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "tests").rglob("*.py"))
    return set(re.findall(r"""["']([A-Za-z][\w-]*)["']""", text))


def _seeded_rules() -> set[str]:
    rows = tomllib.loads(TRACKER.read_text(encoding="utf-8")).get("family", {})
    return {r for f in rows.values() if f.get("dev_faults") for r in f.get("rules", [])}


def rule_level(runs: list) -> dict:
    tested, seeded = _tested_rules(), _seeded_rules()
    rules = built_rules() | {rule_of(f) for r in runs for f in r.findings}
    out = {}
    for rule in sorted(rules):
        rows = [c for r in runs for c in r.checks if c.get("rule") == rule]
        armed = sum(c["n"] for c in rows if c["outcome"] in ARMED)
        faulty = [(r, f) for r in runs if not r.clean for f in r.findings if rule_of(f) == rule]
        clean = [(r, f) for r in runs if r.clean for f in r.findings if rule_of(f) == rule]
        lab = [r.labels.get(f["sig"], "") for r, f in faulty]
        clab = [label_kind(r.labels.get(f["sig"], "")) for r, f in clean]
        tp = sum(is_true_positive(x) for x in lab if x)
        n = sum(1 for x in lab if x)
        d = {"fixture_test": rule in tested, "check_rows": len(rows), "armed": armed, "seeded_family": rule in seeded,
             "findings": len(faulty), "tp": tp, "precision": round(tp / n, 4) if n else None,
             "unlabelled": lab.count("") + clab.count("unlabelled"),
             "clean_false_alarms": sum(1 for k in clab if k == "fp"),
             "faults": sorted({x.upper() for x in lab if label_kind(x) == "seeded"})}
        d["tier"] = "T1" if n >= 5 and tp / n >= PRECISION_FLOOR else ("T2" if n else "-")
        # the implicit signals (HTTP 5xx, page errors, failed requests) fire on any page and log no check rows
        miss = [k for k, ok in (("no fixture test", d["fixture_test"]), ("never armed", armed > 0 or rule in IMPLICIT),
                                ("unlabelled findings", d["unlabelled"] == 0)) if not ok]
        d["enters"] = not miss
        d["why_not"] = miss
        out[rule] = d
    return out


def without(runs: list, ref: list, rules: dict, drop: list[str] | None = None) -> dict:
    """The run-level numbers with the rules whose own precision is below the floor left out (only rules with
    findings; a silent rule changes nothing)."""
    if drop is None:  # automatic: every rule under the floor, and every silent rule with clean false alarms
        drop = sorted(k for k, v in rules.items() if v["precision"] is not None and v["precision"] < PRECISION_FLOOR)
        drop += sorted(k for k, v in rules.items() if v["precision"] is None and v["clean_false_alarms"] > 0)
    kept = [replace(r, findings=[f for f in r.findings if rule_of(f) not in drop]) for r in runs]
    return {"dropped": drop, "apps": app_level(kept, ref)}


def report(rep: dict) -> str:
    def yn(v):
        return "n/a" if v is None else ("yes" if v else "**no**")

    L = [f"# v5.0 lock check: {rep['ver']} against {rep['ref']}", ""]
    for title, apps in (("Run level, all rules", rep["apps"]), (f"Run level without {', '.join(rep['without']['dropped']) or 'none'}",
                                                                rep["without"]["apps"])):
        L += [f"## {title}", "", "| app | recall (score, median) vs ref | ok | precision | ok | clean FA/run | ok | lock |",
              "|---|---|---|---|---|---|---|---|"]
        for app, a in apps.items():
            r, p, f = a["recall"], a["precision"], a["false_alarms"]
            L.append(f"| {app} | {r['mutation_score'].get('killed')}/{r['mutation_score'].get('seeded')}, {r['median_total']} vs "
                     f"{r['ref_mutation_score'].get('killed')}/{r['ref_mutation_score'].get('seeded')}, {r['ref_median_total']} | "
                     f"{yn(r['ok'])} | {p['tp']}/{p['n']} = {p['precision']} ({p['unlabelled']} unlabelled) | {yn(p['ok'])} | "
                     f"{f['per_run']} ({f['n']} in {a['clean_runs']}; {f['unlabelled']} unlabelled) | {yn(f['ok'])} | {yn(a['ok'])} |")
        L.append("")
    R = rep["rules"]
    enter = [k for k, v in R.items() if v["enters"]]
    L += ["## Rule level (section 12.2)", "",
          f"{len(enter)} of {len(R)} rules meet (1), (2), (4), (5). Rules with findings or false alarms:", "",
          "| rule | test | armed | seeded family | findings | precision | tier | clean FA | faults | enters |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in R.items():
        if v["findings"] or v["clean_false_alarms"] or v["unlabelled"]:
            L.append(f"| {k} | {yn(v['fixture_test'])} | {v['armed']} | {yn(v['seeded_family'])} | {v['findings']} | "
                     f"{v['precision']} | {v['tier']} | {v['clean_false_alarms']} | {', '.join(v['faults'])} | "
                     f"{'yes' if v['enters'] else 'no: ' + ', '.join(v['why_not'])} |")
    for why in ("no fixture test", "never armed"):
        xs = [k for k, v in R.items() if why in v["why_not"]]
        L += ["", f"**{why}** ({len(xs)}): {', '.join(xs) or '-'}"]
    L += ["", f"Armed and silent (no finding on either pass): "
              f"{', '.join(k for k, v in R.items() if v['enters'] and not v['findings'] and not v['clean_false_alarms']) or '-'}"]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", default="v59")
    ap.add_argument("--ref", default="v5", help="the resweep the recall must not fall below (D55: v5)")
    ap.add_argument("--md")
    ap.add_argument("--json")
    ap.add_argument("--drop", help="comma-separated rules to leave out instead of the automatic set (the user's choice)")
    a = ap.parse_args()
    runs, ref = load_runs(a.ver), load_runs(a.ref)
    if not runs:
        sys.exit(f"no {a.ver} resweep in logs/experiments/v5dev/")
    rules = rule_level(runs)
    rep = {"ver": a.ver, "ref": a.ref, "apps": app_level(runs, ref), "rules": rules, "without": without(runs, ref, rules, a.drop.split(",") if a.drop else None)}
    md = report(rep)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
