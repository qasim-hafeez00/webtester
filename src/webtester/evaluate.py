"""v5 evaluation (v5 plan section 11, D59): every number is computed offline from what a run wrote
(trace, findings, gate results, check-outcome log), the labels, the fault catalogs and the family
registry. Nothing here runs the app or an LLM, so every condition is measured by the same code.

Metric groups (plan 11.1-11.12):
   1 detection     total and oracle-conditioned recall, per family / app / primitive; precision per finding,
                   per distinct issue, per tier and rule, gate-confirmed and judge-filtered; F-beta (0.5);
                   unseeded real bugs ('new:'); redundancy (findings per distinct issue)
   2 false alarms  clean-app false alarms per run, per 100 steps and per 100 armed checks, with exact
                   intervals (Garwood; zero events gives the rule of three); per rule; harness-induced apart
   3 report        gate confirmed / flaky / rejected / unverified rates, gate recall loss, minimal trace length
   4 reach         states, routes, transitions, travels, check arm coverage
   5 efficiency    new states per step, duplicate and failed action rates, travel ratio, time to first
                   detection, recall at 25/50/75/100% of the run's time
   6 funnel        per seeded fault: S1 reached, S2 triggered, S3 observed (not measured yet), S4 armed,
                   S5 flagged, S6 confirmed, S7 matched; the first stage that failed; guard suppressions
   7 cost          tokens per step, per finding, per true distinct issue; browser minutes; gate minutes
   8 variance      median, IQR, mean, SD, CV across runs; run health
   9 generality    per-app numbers side by side (the dev/held-out gap is a difference of these)
  10 oracle level  per-rule precision, arm rate and measured tier; Cohen's kappa of the blind check
  12 statistics    exact Mann-Whitney U, A12, Holm-Bonferroni over a metric family, bootstrap intervals
  D61 additions (the review's 12 groups, plan section 11):
   1 recall per app type, F1 next to F0.5, per-rule recall, mutation score (seeded and historical 'H' labels)
   3 report quality from the user's ratings (reproduced, actionability rubric, triage minutes)
   4 controls seen vs activated, write success per form kind, input classes per field kind, routes per role,
     data depth (arm rate of the list rules), API endpoint coverage, server-side coverage when measured,
     unsupported modalities, build mode
   5 dead-end and revisit rates, session losses, recall over steps / tokens / minutes with its area, the state
     plateau (R13, measured only)
   6 recall lost per guard
   7 tokens per finding and per confirmed true finding, USD, gate overhead, cross-worker redundancy, LLM
     retries and policy-error rate, parallel speedup and efficiency across worker counts
   8 sensitivity to the LLM, the rebranded app and the front-end framework
   9 generalization gap (development vs held-out apps), bootstrap over apps
  10 tier calibration, engine agreement (X9), app-profile accuracy (X5)
  11 safety: destructive incidents, out-of-scope requests blocked, cleanup share, mode violations
  E10 detector-only (resweep) against end-to-end recall on the same runs
  (+) confidence   a score per finding from rule prior, independent cues, replay k/n, judge verdict and
                   implicit kind; fitted leave-one-app-out; precision-recall curve, average precision, Brier

Labels: a seeded fault id, 'new: ...' (real, unseeded), 'U#' (upstream, real), 'fp', 'harness: ...'
(a false alarm the harness caused). Distinct issue = rule x page template x entity kind; an issue is
true when any of its findings is (reported with the number of mixed issues).
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .checks import ARMED, read_checks
from .config import REPO_ROOT
from .families import OBSERVABLE, families, fault_families_of, family_rules, primitives
from .labels import LABELS, is_true_positive, label_of, load_labels
from .metrics import load_fault_catalog, route_matches
from .stats import a12, bootstrap_ci, clopper_pearson, holm, mann_whitney_p, poisson_rate_ci, spread
from .trace import read_trace

CATALOGS = {"realworld": REPO_ROOT / "apps/realworld/faults/faults.toml",
            "bookstack": REPO_ROOT / "apps/bookstack/faults/faults.toml"}
APP_ALIAS = {"bookstack-rebrand": "bookstack"}  # E6: the rebranded control has BookStack's faults
BETA = 0.5  # F-beta weights precision over recall (a report a developer must triage costs more than a miss)
FUNNEL = ("S1_reached", "S2_triggered", "S3_observed", "S4_armed", "S5_flagged", "S6_confirmed", "S7_matched")


# ---------------------------------------------------------------------------- loading
@dataclass
class RunData:
    run_id: str
    app: str
    condition: str
    clean: bool  # the app ran without seeded faults: every finding is a candidate false alarm
    findings: list[dict]
    labels: dict[str, str]  # signature -> label
    enabled: set[str]  # seeded faults enabled in the run
    summary: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    step_t: dict = field(default_factory=dict)  # (worker, step) -> seconds since the run began
    duration_s: float = 0.0
    events: dict = field(default_factory=dict)  # D60: trace events by type that the evaluator reads (session, reach, ...)
    config: dict = field(default_factory=dict)  # D60: the run's config.json (setup effort)
    steps: list = field(default_factory=list)  # D61: per step {worker, step, t, state, new, route, tokens, dup, failed}
    source: str = "live"  # E10 (D61): 'live' findings or a 'resweep' of the recorded trail
    run_dir: Path | None = None


@lru_cache(maxsize=1)
def _app_metas() -> dict:
    out = {}
    for p in (REPO_ROOT / "configs").glob("*.toml"):
        try:
            app = tomllib.loads(p.read_text(encoding="utf-8")).get("app") or {}
        except tomllib.TOMLDecodeError:
            continue
        if app.get("name"):
            out[app["name"]] = app
    return out


def app_meta(app: str) -> dict:
    """The app's [app] table from configs/ (fallback for runs whose saved config predates a field)."""
    return _app_metas().get(app, {})


def load_catalog() -> dict[str, dict]:
    out = {}
    for app, p in CATALOGS.items():
        for fid, f in load_fault_catalog(p).items():
            out[fid] = {**f, "app": app}
    return out


def fault_routes(f: dict) -> list[str]:
    """Routes where a fault lives: its `reach` routes, its `hint` routes, '(/path)' in its trigger text."""
    rs = [r for rule in f.get("reach") or [] for r in rule.get("route") or []]
    rs += list((f.get("hint") or {}).get("routes") or [])
    rs += re.findall(r"\((/[^)\s]*)\)", f.get("trigger") or "")
    return sorted(set(rs))


KEPT_EVENTS = ("session", "reach", "discovery", "app_profile", "role", "envcheck", "sweep", "injection_records",
               "stop_file", "coverage", "frontier", "gate_done", "run_end", "policy_error", "travel", "api_spec",
               "discovery_checks", "safety", "run_start")


def _step_times(trace: Path) -> tuple[dict, float]:
    st, end, _ = _trace_parts(trace)
    return st, end


def _trace_parts(trace: Path) -> tuple[dict, float, dict]:
    if not trace.exists():
        return {}, 0.0, {}
    st, end, ev = {}, 0.0, {}
    for e in read_trace(trace):
        if e["type"] == "step":
            st[(e["worker"], e["step"])] = e["t"]
            end = max(end, e["t"])
            acts = e.get("actions") or []
            ev.setdefault("_steps", []).append({
                "worker": e["worker"], "step": e["step"], "t": e["t"], "state": e.get("state"), "new": e.get("new_state"),
                "route": e.get("route"), "tokens": (e.get("usage") or {}).get("prompt_tokens", 0) +
                (e.get("usage") or {}).get("completion_tokens", 0), "dup": any(a.get("dup") for a in acts),
                "failed": any(not a.get("ok", True) for a in acts), "back": any(a.get("do") == "back" for a in acts)})
        elif e["type"] in KEPT_EVENTS:
            ev.setdefault(e["type"], []).append(e)
    return st, end, ev


def load_run(run_dir: Path, condition: str = "", findings: str = "findings.json", clean: bool | None = None,
             labels: dict | None = None, checks: str | None = None) -> RunData:
    """A run directory as written by the runner. `findings` may name a resweep file; its check log is the
    matching `checks*.jsonl`. Labels from finding_labels.toml unless given."""
    summ = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")) if (run_dir / "summary.json").exists() else {}
    fs = json.loads((run_dir / findings).read_text(encoding="utf-8"))
    labels = load_labels(LABELS) if labels is None else labels
    rid = summ.get("run_id") or run_dir.name
    enabled = {x.upper() for x in summ.get("faults") or []}
    if clean is None:
        clean = not enabled
    if clean:
        enabled = set()
    ck = checks or findings.replace("findings", "checks").replace(".json", ".jsonl")
    st, end, ev = _trace_parts(run_dir / "trace.jsonl")
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8")) if (run_dir / "config.json").exists() else {}
    steps = ev.pop("_steps", [])
    return RunData(rid, summ.get("app") or rid.split("_")[1], condition or summ.get("agent", ""), clean, fs,
                   {f["sig"]: label_of(labels, rid, f["sig"]) for f in fs}, enabled, summ, read_checks(run_dir / ck),
                   st, end or 60 * summ.get("wall_minutes", 0), ev, cfg, steps,
                   "resweep" if "resweep" in findings else "live", run_dir)


# ---------------------------------------------------------------------------- labels and issues
def label_kind(label: str) -> str:
    lab = (label or "").strip()
    if not lab:
        return "unlabelled"
    low = lab.lower()
    if low == "fp":
        return "fp"
    if low.startswith("harness"):
        return "harness"
    if low.startswith("new"):
        return "new"
    if re.fullmatch(r"u\d+\??", low):
        return "upstream"
    if re.fullmatch(r"h\d+", low) or low.startswith("hist"):
        return "historical"  # E5 a (D61): a real fixed bug from the app's history
    return "seeded"


def rule_of(f: dict) -> str:
    return (f.get("detail") or {}).get("rule") or f["kind"]


def tier_of(f: dict) -> str:
    return (f.get("detail") or {}).get("tier") or ("implicit" if f["kind"] != "oracle_violation" else "T3")


def route_of(f: dict) -> str:
    parts = f["sig"].split("|")
    return parts[2] if f["kind"] in ("consistency", "oracle_violation") and len(parts) > 2 else \
        next((p for p in parts if p.startswith("/")), "")


def entity_kind(f: dict) -> str:
    """The kind of item a finding is about: the first path segment of a link in its subject, else of its page."""
    subject = "|".join(f["sig"].split("|")[3:])
    m = re.search(r"/([a-z][\w-]*)/", subject + "/")
    if m:
        return m.group(1)
    seg = [s for s in route_of(f).split("?")[0].split("/") if s and s != "*"]
    return seg[0] if seg else "/"


def issue_key(f: dict) -> tuple[str, str, str]:
    return rule_of(f), route_of(f), entity_kind(f)


def found_faults(r: RunData, confirmed: bool = False) -> set[str]:
    fs = [f for f in r.findings if not confirmed or f.get("status") == "confirmed"]
    labelled = {r.labels.get(f["sig"], "").upper() for f in fs}
    key = "fault_detection_confirmed" if confirmed else "fault_detection"
    by_rule = {fid for fid, d in (r.summary.get(key) or {}).items() if d.get("detected")}
    return (labelled | by_rule) & r.enabled


# ---------------------------------------------------------------------------- 1 detection
def _prec(tp: int, n: int) -> dict:
    lo, hi = clopper_pearson(tp, n)
    return {"tp": tp, "n": n, "precision": round(tp / n, 4) if n else None, "ci95": [round(lo, 4), round(hi, 4)]}


def precision_block(runs: list[RunData]) -> dict:
    fs = [(r, f) for r in runs if not r.clean for f in r.findings]
    lab = [(r, f, r.labels.get(f["sig"], "")) for r, f in fs]
    unl = sum(1 for _, _, l in lab if not l)
    judged = [(r, f, l) for r, f, l in lab if l]

    def tp(xs):
        return sum(is_true_positive(l) for _, _, l in xs)

    out = {"unlabelled": unl, "raw": _prec(tp(judged), len(judged))}
    conf = [x for x in judged if x[1].get("status") == "confirmed"]
    if any(f.get("status", "candidate") != "candidate" for _, f in fs):
        out["confirmed"] = _prec(tp(conf), len(conf))
        jf = [x for x in conf if ((x[1].get("judge") or {}).get("verdict")) != "wrong_expectation"]
        out["judge_filtered"] = _prec(tp(jf), len(jf))
    issues: dict[tuple, list] = defaultdict(list)
    for r, f, l in judged:
        issues[(r.app, *issue_key(f))].append(is_true_positive(l))
    out["distinct"] = {**_prec(sum(any(v) for v in issues.values()), len(issues)),
                       "mixed": sum(1 for v in issues.values() if any(v) and not all(v)),
                       "findings_per_issue": round(len(judged) / len(issues), 2) if issues else None}
    by_tier, by_rule = defaultdict(list), defaultdict(list)
    for x in judged:
        by_tier[tier_of(x[1])].append(x)
        by_rule[rule_of(x[1])].append(x)
    out["by_tier"] = {t: _prec(tp(v), len(v)) for t, v in sorted(by_tier.items())}
    out["by_rule"] = {k: {**_prec(tp(v), len(v)), "measured_tier": ("T1" if len(v) >= 5 and tp(v) / len(v) >= 0.9
                                                                    else "T2")}
                      for k, v in sorted(by_rule.items())}
    jv = [((x[1].get("judge") or {}).get("verdict"), is_true_positive(x[2])) for x in judged]
    jv = [(v == "bug", y) for v, y in jv if v in ("bug", "wrong_expectation")]
    if jv:  # the LLM judge against the labels (it never decides; this says how far it could be trusted)
        out["judge_accuracy"] = {**_prec(sum(a == b for a, b in jv), len(jv)),
                                 "says_bug_when_fp": sum(1 for a, b in jv if a and not b),
                                 "says_wrong_when_tp": sum(1 for a, b in jv if not a and b)}
    out["by_label_kind"] = dict(Counter(label_kind(l) for _, _, l in judged))
    out["new_bugs"] = sorted({l for _, _, l in judged if label_kind(l) == "new"})
    return out


def recall_block(runs: list[RunData], catalog: dict) -> dict:
    fam_of = fault_families_of()
    fams = families()
    prim_of: dict[str, set] = defaultdict(set)
    for p, fs in primitives().items():
        for f in fs:
            prim_of[f].add(p)

    def reachable(fid: str) -> bool:
        return bool(catalog.get(fid, {}).get("reachable", True))

    def observable(fid: str) -> bool:
        fs = fam_of.get(fid, [])
        return not fs or any(fams[f]["status"] in OBSERVABLE for f in fs)  # unmapped faults are counted (no free pass)

    per_run, pooled_found, pooled_all = [], defaultdict(set), defaultdict(set)
    for r in runs:
        if r.clean:
            continue
        reach = {f for f in r.enabled if reachable(f)}
        cond = {f for f in reach if observable(f)}
        found = found_faults(r) & reach
        conf = found_faults(r, confirmed=True) & reach
        pooled_found[r.app] |= found
        pooled_all[r.app] |= reach
        per_run.append({"run": r.run_id, "app": r.app, "found": sorted(found), "reachable": len(reach),
                        "enabled": sorted(reach), "app_type": ((r.config or {}).get("app") or {}).get("app_type") or app_meta(r.app).get("app_type", ""),
                        "total_recall": round(len(found) / len(reach), 4) if reach else None,
                        "conditioned_recall": round(len(found & cond) / len(cond), 4) if cond else None,
                        "confirmed_recall": round(len(conf) / len(reach), 4) if reach else None})
    by_family, by_prim = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in per_run:
        rd = next(x for x in runs if x.run_id == r["run"])
        for fid in (f for f in rd.enabled if reachable(f)):
            hit = fid in r["found"]
            for fam in fam_of.get(fid, ["unmapped"]):
                by_family[fam][0] += hit
                by_family[fam][1] += 1
                for p in prim_of.get(fam, {"-"}):
                    by_prim[p][0] += hit
                    by_prim[p][1] += 1
    by_type = defaultdict(lambda: [0, 0])
    for r in per_run:
        by_type[r["app_type"] or "unknown"][0] += len(r["found"])
        by_type[r["app_type"] or "unknown"][1] += r["reachable"]
    return {"per_run": per_run,
            "by_app_type": {k: {"found": v[0], "runs_x_faults": v[1], "recall": round(v[0] / v[1], 4) if v[1] else None}
                            for k, v in sorted(by_type.items())},
            "mutation_score": {a: {"killed": len(pooled_found[a]), "seeded": len(pooled_all[a]),
                                   "score": round(len(pooled_found[a]) / len(pooled_all[a]), 4) if pooled_all[a] else None}
                               for a in pooled_all},
            "across_runs": {a: {"found": sorted(pooled_found[a]), "reachable": len(pooled_all[a])} for a in pooled_all},
            "by_family": {k: {"found": v[0], "runs_x_faults": v[1], "recall": round(v[0] / v[1], 4)}
                          for k, v in sorted(by_family.items())},
            "by_primitive": {k: {"found": v[0], "runs_x_faults": v[1], "recall": round(v[0] / v[1], 4)}
                             for k, v in sorted(by_prim.items())},
            **severity_recall(per_run, catalog)}


SEVERITY_WEIGHT = {"data": 3, "function": 2, "display": 1}  # E8 (D60): data loss or money > function > display


def severity_recall(per_run: list[dict], catalog: dict) -> dict:
    """E8: recall per severity class and severity-weighted recall (catalog field `severity`; unset = function)."""
    by, wf, wt = {}, 0.0, 0.0
    for r in per_run:
        reach = [fid for fid in r.get("enabled", []) if fid in catalog]  # D61: the faults enabled in this run
        for fid in reach:
            sev = catalog[fid].get("severity", "function")
            w = SEVERITY_WEIGHT.get(sev, 2)
            hit = fid in r["found"]
            d = by.setdefault(sev, [0, 0])
            d[0] += hit
            d[1] += 1
            wf += w * hit
            wt += w
    return {"by_severity": {k: {"found": v[0], "runs_x_faults": v[1], "recall": round(v[0] / v[1], 4)} for k, v in by.items()},
            "severity_weighted_recall": round(wf / wt, 4) if wt else None}


def f_beta(p: float | None, r: float | None, beta: float = BETA) -> float | None:
    if not p or not r:
        return None
    b2 = beta * beta
    return round((1 + b2) * p * r / (b2 * p + r), 4)


# ---------------------------------------------------------------------------- 2 false alarms
def false_alarm_block(clean: list[RunData]) -> dict:
    if not clean:
        return {"runs": 0}
    fp = harness = upstream = unl = steps = 0
    armed = 0
    by_rule = Counter()
    for r in clean:
        for f in r.findings:
            k = label_kind(r.labels.get(f["sig"], ""))
            if k in ("upstream", "new", "seeded"):
                upstream += 1  # a real bug on the clean app is not a false alarm (v5 plan E3)
            elif k == "harness":
                harness += 1
            elif k == "unlabelled":
                unl += 1
            else:
                fp += 1
                by_rule[rule_of(f)] += 1
        steps += r.summary.get("steps", 0)
        armed += sum(c["n"] for c in r.checks if c["outcome"] in ARMED)
    n = len(clean)

    def rate(k: int, exposure: float, unit: str) -> dict:
        lo, hi = poisson_rate_ci(k, exposure)
        return {"unit": unit, "rate": round(k / exposure, 4), "ci95": [round(lo, 4), round(hi, 4)]} if exposure else {}

    return {"runs": n, "false_alarms": fp, "harness_induced": harness, "real_bugs_on_clean_app": upstream,
            "unlabelled": unl, "per_run": rate(fp, n, "run"), "per_100_steps": rate(fp, steps / 100, "100 steps"),
            "per_100_checks": rate(fp, armed / 100, "100 armed checks") if armed else "no check log",
            "by_rule": dict(by_rule.most_common())}


# ---------------------------------------------------------------------------- 3 gate, 4-5 reach and efficiency, 7 cost
def harness_block(runs: list[RunData]) -> dict:
    """C2/C3/J3 (D60): findings the harness itself may have caused, reported apart; reach and safety counters
    from the trace (X1, X2, R6-R9, S1, S2, O3, R2, R7, X5, X9)."""
    fs = [f for r in runs for f in r.findings]
    det = lambda k: sum(1 for f in fs if (f.get("detail") or {}).get(k))  # noqa: E731
    sess = [e for r in runs for e in r.events.get("session", [])]
    reach = [e for r in runs for e in r.events.get("reach", [])]
    sweep = [e for r in runs for e in r.events.get("sweep", [])]
    settle = [e["settle_s_median"] for e in sess if e.get("settle_s_median") is not None]
    return {"findings_harness_suspect": det("health"), "findings_about_probe_values": det("probe_value"),
            "findings_benign_lowered": det("benign"),
            "engine_specific": sum(1 for f in fs if (f.get("gate") or {}).get("engine_specific")),
            "dropped_elements": sum(e.get("dropped_elements", 0) for e in sess),
            "dialogs": sum(e.get("dialogs", 0) for e in sess), "popups_dismissed": sum(len(e.get("dismissed") or []) for e in sess),
            "writes_blocked_by_mode": sum(len(e.get("blocked_writes") or []) for e in sess),
            "destructive_deferred": sum(e.get("deferred_destructive", 0) for e in reach),
            "stateful_travels": sum(e.get("stateful_travels", 0) for e in reach),
            "stop_file_events": sum(len(r.events.get("stop_file", [])) for r in runs),
            "settle_s_median_per_run": settle,
            "routes_discovered": sum(e.get("added", 0) for r in runs for e in r.events.get("discovery", [])),
            "app_profiles": [{k: v for k, v in e.items() if k in ("app_type", "primitives")} for r in runs
                             for e in r.events.get("app_profile", [])],
            "roles": sorted({e.get("role") for r in runs for e in r.events.get("role", [])} - {None}),
            "injection_records": sum(len(e.get("records") or []) for r in runs for e in r.events.get("injection_records", [])),
            "seeds": sum((e.get("seeds") or {}).get("accepted", 0) for e in sweep),
            # R12 and JS coverage (measured only, coverage_metrics)
            "handler_coverage": _ratio(sum(e.get("handler_elements_clicked", 0) for e in sess),
                                       sum(e.get("handler_elements", 0) for e in sess)),
            "js_function_coverage": _ratio(sum((e.get("js_coverage") or {}).get("executed", 0) for e in sess),
                                           sum((e.get("js_coverage") or {}).get("functions", 0) for e in sess))}


def _ratio(a: float, b: float) -> float | None:
    return round(a / b, 4) if b else None


def setup_effort(runs: list[RunData]) -> dict:
    """Generality (group 9): per app, how many app-specific config items the run needed beyond a URL and
    credentials (login recipe fields, blocked texts, reset command, fault script, setup service)."""
    out = {}
    for r in runs:
        app = (r.config or {}).get("app") or {}
        if not app:
            continue
        items = sum(1 for k in ("blocked_text", "crawler_avoid_text", "reset_compose_args", "fault_script", "setup_service",
                                "allowed_origins", "accounts") if app.get(k))
        items += len((app.get("login") or {}).get("fields") or {})
        out[r.app] = max(out.get(r.app, 0), items)
    return {"config_items_per_app": out, "zero_config_apps": sorted(a for a, n in out.items() if n == 0)}


def gate_block(runs: list[RunData]) -> dict:
    st = Counter(f.get("status", "candidate") for r in runs if not r.clean for f in r.findings)
    n = sum(st.values())
    if not n or set(st) == {"candidate"}:
        return {"gated": False}
    raw = sum(len(found_faults(r)) for r in runs if not r.clean)
    conf = sum(len(found_faults(r, True)) for r in runs if not r.clean)
    mins = [g["minimal_steps"] for r in runs for f in r.findings if (g := f.get("gate") or {}).get("minimal_steps")]
    tp = [f for r in runs if not r.clean for f in r.findings if is_true_positive(r.labels.get(f["sig"], ""))]
    lost = Counter(f.get("status") for f in tp if f.get("status") != "confirmed")
    return {"gated": True, "statuses": dict(st), "rates": {k: round(v / n, 4) for k, v in st.items()},
            "gate_recall_loss": round(1 - conf / raw, 4) if raw else None,  # seeded faults lost by the gate
            "gate_loss_true_findings": round(sum(lost.values()) / len(tp), 4) if tp else None,  # as in the ledger
            "true_findings_lost_by_status": dict(lost),
            "minimal_trace_steps": spread(mins) if mins else {}}


def run_metrics(r: RunData) -> dict:
    """Per-run scalars (reach, efficiency, cost, detection) used for spreads and condition comparisons."""
    s = r.summary
    steps = s.get("steps", 0)
    tps = [f for f in r.findings if is_true_positive(r.labels.get(f["sig"], ""))]
    t_tp = sorted(r.step_t.get((f.get("worker"), f.get("first_step")), math.inf) for f in tps)
    first_fault_t: dict[str, float] = {}
    for f in r.findings:
        fid = r.labels.get(f["sig"], "").upper()
        if fid in r.enabled:
            t = r.step_t.get((f.get("worker"), f.get("first_step")), math.inf)
            first_fault_t[fid] = min(first_fault_t.get(fid, math.inf), t)
    T = r.duration_s or 1
    issues_tp = {issue_key(f) for f in tps}
    armed = sum(c["n"] for c in r.checks if c["outcome"] in ARMED)
    allck = sum(c["n"] for c in r.checks)
    out = {"run": r.run_id, "app": r.app, "condition": r.condition, "clean": r.clean, "steps": steps,
           "unique_states": s.get("unique_states"), "unique_routes": s.get("unique_routes"),
           "transitions": (s.get("graph") or {}).get("transitions"),
           "duplicate_action_rate": s.get("duplicate_action_rate"), "failed_action_rate": s.get("failed_action_rate"),
           "new_states_per_step": round(s["unique_states"] / steps, 4) if steps and s.get("unique_states") else None,
           "travel_ratio": round(s.get("travels", 0) / steps, 4) if steps else None,
           "tokens_total": s.get("tokens_total"), "tokens_per_step": s.get("tokens_per_step"),
           "browser_minutes": s.get("browser_minutes"), "wall_minutes": s.get("wall_minutes"),
           "gate_minutes": (s.get("gate") or {}).get("minutes"), "health_ok": (s.get("health") or {}).get("ok"),
           "findings": len(r.findings), "distinct_issues": len({issue_key(f) for f in r.findings}),
           "true_distinct_issues": len(issues_tp),
           "tokens_per_true_issue": round(s["tokens_total"] / len(issues_tp)) if issues_tp and s.get("tokens_total") else None,
           "ttfd_minutes": round(t_tp[0] / 60, 2) if t_tp and t_tp[0] < math.inf else None,
           "check_arm_rate": round(armed / allck, 4) if allck else None}
    if not r.clean:
        found = found_faults(r)
        out["faults_found"] = len(found)
        out["recall_at_budget"] = {f"{int(q * 100)}%": sum(1 for fid in found if first_fault_t.get(fid, 0) <= q * T)
                                   for q in (0.25, 0.5, 0.75, 1.0)}
        lab = [r.labels.get(f["sig"], "") for f in r.findings]
        if r.findings and all(lab):
            out["precision_raw"] = round(sum(is_true_positive(x) for x in lab) / len(lab), 4)
            iss = defaultdict(list)
            for f, x in zip(r.findings, lab):
                iss[issue_key(f)].append(is_true_positive(x))
            out["precision_distinct"] = round(sum(any(v) for v in iss.values()) / len(iss), 4)
    return out


# ---------------------------------------------------------------------------- 6 funnel, 10 checks
def funnel_block(runs: list[RunData], catalog: dict) -> dict:
    fam_of = fault_families_of()
    rows, first_fail = [], Counter()
    for r in runs:
        if r.clean:
            continue
        reach = r.summary.get("fault_reach") or {}
        exposed = set(r.summary.get("faults_exposed") or [])
        markers = bool(r.summary.get("exposure_markers")) or bool(exposed)
        for fid in sorted(f for f in r.enabled if catalog.get(f, {}).get("reachable", True)):
            f = catalog.get(fid, {})
            routes = fault_routes(f)
            rules = {x for fam in fam_of.get(fid, []) for x in family_rules(fam)}

            def on_route(route: str) -> bool:
                return not routes or any(route_matches(p, route) for p in routes)

            visited = set(r.summary.get("routes") or [])
            s1 = reach[fid]["reached"] if fid in reach and reach[fid].get("has_rule") else \
                (fid in exposed or any(on_route(x) for x in visited) if routes else None)
            s2 = (fid in exposed) if markers else None
            # S4-S6 need a rule mapped to the fault's families; unmapped faults stay unknown there, not failed
            ck = [c for c in r.checks if c["rule"] in rules and on_route(c["route"])]
            s4 = any(c["outcome"] in ARMED for c in ck) if r.checks and rules else None
            fl = [x for x in r.findings if rule_of(x) in rules and on_route(route_of(x))]
            s5 = bool(fl) if rules else None
            gated = any(x.get("status", "candidate") != "candidate" for x in r.findings)
            s6 = any(x.get("status") == "confirmed" for x in fl) if gated and rules else None
            s7 = fid in found_faults(r)
            stages = dict(zip(FUNNEL, (s1, s2, None, s4, s5, s6, s7)))
            fail = None if s7 else next((k for k in FUNNEL if stages[k] is False), "unknown")
            first_fail[fail or "found"] += 1
            sup = Counter(c["why"] for c in ck if c["outcome"] == "suppressed")
            rows.append({"run": r.run_id, "fault": fid, **stages, "first_failed": fail,
                         "suppressed": dict(sup), "capped": sum(c["n"] for c in ck if c["outcome"] == "capped")})
    conv = {}
    for k in FUNNEL:
        vals = [x[k] for x in rows if x[k] is not None]
        conv[k] = {"passed": sum(vals), "measured": len(vals)}
    return {"stages": conv, "first_failed": dict(first_fail), "rows": rows}


def checks_block(runs: list[RunData]) -> dict:
    by_rule: dict[str, Counter] = defaultdict(Counter)
    guards: Counter = Counter()
    for r in runs:
        for c in r.checks:
            by_rule[c["rule"]][c["outcome"]] += c["n"]
            if c["outcome"] in ("suppressed", "capped", "unarmed", "unobservable", "inconclusive"):
                guards[f"{c['rule']}:{c['outcome']}:{c['why']}"] += c["n"]
    if not by_rule:
        return {"logged": False}
    return {"logged": True,
            "by_rule": {k: {**dict(v), "arm_rate": round(sum(v[o] for o in ARMED) / sum(v.values()), 4)}
                        for k, v in sorted(by_rule.items())},
            "not_armed_reasons": dict(guards.most_common(40))}


# ---------------------------------------------------------------------------- confidence score
FEATURES = ("rule_prior", "cues", "replay", "gated", "judge", "occurrences", "implicit")


def _features(r: RunData, f: dict, prior: dict, tier_prior: dict, own: bool | None = None) -> list[float]:
    """`own`: the row's label when it is a training row; its rule prior then leaves it out (no target leak)."""
    rule = rule_of(f)
    if rule in prior:
        k, n = prior[rule]
        if own is not None:
            k, n = k - own, n - 1
        p = (k + 1) / (n + 2) if n > 0 else tier_prior.get(tier_of(f), 0.5)
    else:
        p = tier_prior.get(tier_of(f), 0.5)
    p = min(max(p, 0.02), 0.98)
    same = {rule_of(x) for x in r.findings if route_of(x) == route_of(f) and entity_kind(x) == entity_kind(f)}
    g = f.get("gate") or {}
    kn = g["reproduced"] / g["k"] if g.get("k") else 0.5
    verdict = (f.get("judge") or {}).get("verdict")
    return [math.log(p / (1 - p)), 1.0 if len(same) >= 2 else 0.0, kn, 1.0 if g.get("k") else 0.0,
            1.0 if verdict == "bug" else -1.0 if verdict == "wrong_expectation" else 0.0,
            math.log1p(f.get("occurrences", 1)), 1.0 if f["kind"] != "consistency" else 0.0]


def _priors(rows: list[tuple[RunData, dict, bool]]) -> tuple[dict, dict]:
    by_rule, by_tier = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for _, f, y in rows:
        for d, k in ((by_rule, rule_of(f)), (by_tier, tier_of(f))):
            d[k][0] += y
            d[k][1] += 1
    # rules as counts (the score smooths them, leaving a training row out of its own prior); tiers smoothed
    return {k: tuple(v) for k, v in by_rule.items()}, {k: (v[0] + 1) / (v[1] + 2) for k, v in by_tier.items()}


def _fit(X: list[list[float]], y: list[int], l2: float = 0.1, it: int = 600, lr: float = 0.1) -> list[float]:
    w = [0.0] * (len(X[0]) + 1)
    n = len(X)
    for _ in range(it):
        g = [0.0] * len(w)
        for x, t in zip(X, y):
            z = w[0] + sum(a * b for a, b in zip(w[1:], x))
            e = 1 / (1 + math.exp(-max(min(z, 30), -30))) - t
            g[0] += e
            for j, xj in enumerate(x, 1):
                g[j] += e * xj
        w = [w[0] - lr * g[0] / n] + [wj - lr * (gj / n + l2 * wj) for wj, gj in zip(w[1:], g[1:])]
    return w


def _score(w: list[float], x: list[float]) -> float:
    z = w[0] + sum(a * b for a, b in zip(w[1:], x))
    return 1 / (1 + math.exp(-max(min(z, 30), -30)))


def confidence_block(runs: list[RunData]) -> dict:
    rows = [(r, f, is_true_positive(l)) for r in runs if not r.clean for f in r.findings
            if (l := r.labels.get(f["sig"], ""))]
    apps = sorted({r.app for r, _, _ in rows})
    if len(rows) < 10:
        return {"fitted": False, "why": "fewer than 10 labelled findings"}
    scored = []
    held_out = len(apps) >= 2
    weights = {}
    for app in apps if held_out else ["all"]:
        train = [x for x in rows if x[0].app != app] if held_out else rows
        test = [x for x in rows if x[0].app == app] if held_out else rows
        prior, tprior = _priors(train)
        X = [_features(r, f, prior, tprior, own=y) for r, f, y in train]
        w = _fit(X, [int(y) for _, _, y in train])
        weights[app] = dict(zip(("bias", *FEATURES), (round(v, 3) for v in w)))
        for r, f, y in test:
            scored.append((_score(w, _features(r, f, prior, tprior)), y, r, f))
    scored.sort(key=lambda t: -t[0])
    P = sum(y for _, y, _, _ in scored)
    curve, tp, ap, prev_r = [], 0, 0.0, 0.0
    faults_all = {(r.run_id, r.labels[f["sig"]].upper()) for _, y, r, f in scored if y and r.labels[f["sig"]].upper() in r.enabled}
    kept_faults = set()
    for i, (s, y, r, f) in enumerate(scored, 1):
        tp += y
        lab = r.labels[f["sig"]].upper()
        if y and lab in r.enabled:
            kept_faults.add((r.run_id, lab))
        prec, rec = tp / i, (tp / P if P else 0)
        ap += prec * (rec - prev_r)
        prev_r = rec
        if i == len(scored) or scored[i][0] != s:
            curve.append({"threshold": round(s, 3), "precision": round(prec, 4), "finding_recall": round(rec, 4),
                          "fault_recall": round(len(kept_faults) / len(faults_all), 4) if faults_all else None})
    brier = sum((s - y) ** 2 for s, y, _, _ in scored) / len(scored)
    bins = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        b = [(s, y) for s, y, _, _ in scored if lo <= s < lo + 0.2 or (lo == 0.8 and s == 1.0)]
        if b:
            bins.append({"bin": f"{lo:.1f}-{lo + 0.2:.1f}", "n": len(b), "mean_score": round(sum(s for s, _ in b) / len(b), 3),
                         "observed": round(sum(y for _, y in b) / len(b), 3)})
    return {"fitted": True, "validation": "leave-one-app-out" if held_out else "in-sample (one app only)",
            "n": len(scored), "positives": P, "average_precision": round(ap, 4), "brier": round(brier, 4),
            "reliability": bins, "weights": weights, "pr_curve": curve[:: max(1, len(curve) // 25)] + curve[-1:]}


# ---------------------------------------------------------------------------- 10 kappa of the blind check
def kappa_block(sample: Path = REPO_ROOT / "logs/experiments/label_check_sample.toml") -> dict:
    if not sample.exists():
        return {"status": "no sample"}
    blind = tomllib.loads(sample.read_text(encoding="utf-8"))
    ours = load_labels(LABELS)
    pairs = [(str(v.get("label", "")).strip(), label_of(ours, rid, sig)) for rid, d in blind.items()
             for sig, v in d.items() if str(v.get("label", "")).strip()]
    if not pairs:
        return {"status": "pending: the user's blind labels are empty", "entries": sum(len(d) for d in blind.values())}
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    po = sum(x == y for x, y in pairs) / len(pairs)
    cats = set(a) | set(b)
    pe = sum((a.count(c) / len(a)) * (b.count(c) / len(b)) for c in cats)
    return {"status": "done", "n": len(pairs), "agreement": round(po, 4),
            "kappa": round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0}


# ---------------------------------------------------------------------------- 8, 12 across runs and conditions
SCALARS = ("faults_found", "precision_raw", "precision_distinct", "findings", "distinct_issues", "unique_states",
           "unique_routes", "steps", "tokens_total", "duplicate_action_rate", "failed_action_rate", "travel_ratio",
           "new_states_per_step", "ttfd_minutes", "tokens_per_true_issue", "check_arm_rate")
# Pre-registered primary family for Holm-Bonferroni (D59). With n = 5 runs per condition the smallest exact
# two-sided Mann-Whitney p is 2/252 = 0.0079, so Holm over m metrics can reach 0.05 only if m <= 6. All other
# metrics are reported with unadjusted p and marked exploratory.
PRIMARY = ("faults_found", "precision_distinct", "unique_states")
HIGHER_BETTER = {"faults_found", "precision_raw", "precision_distinct", "unique_states", "unique_routes", "steps",
                 "new_states_per_step", "check_arm_rate"}


def spreads(per_run: list[dict]) -> dict:
    out = {}
    for k in SCALARS:
        xs = [m[k] for m in per_run if isinstance(m.get(k), (int, float))]
        if xs:
            out[k] = {**spread(xs), "boot95_mean": [round(v, 4) for v in bootstrap_ci(xs)]}
    out["healthy_runs"] = f"{sum(1 for m in per_run if m.get('health_ok') is not False)}/{len(per_run)}"
    return out


def compare_conditions(per_run: list[dict], ref: str) -> dict:
    """Each condition against `ref`, per app: exact Mann-Whitney p, A12, Holm-adjusted over the metric family."""
    out = {}
    for app in sorted({m["app"] for m in per_run}):
        rows = [m for m in per_run if m["app"] == app and not m["clean"]]
        base = [m for m in rows if m["condition"] == ref]
        for cond in sorted({m["condition"] for m in rows} - {ref}):
            other = [m for m in rows if m["condition"] == cond]
            res, ps = {}, {}
            for k in SCALARS:
                x = [m[k] for m in other if isinstance(m.get(k), (int, float))]
                y = [m[k] for m in base if isinstance(m.get(k), (int, float))]
                if len(x) >= 2 and len(y) >= 2:
                    ps[k] = mann_whitney_p(x, y)
                    res[k] = {"n": [len(x), len(y)], "a12": round(a12(x, y), 3), "p": round(ps[k], 4)}
            for k, p in holm({k: v for k, v in ps.items() if k in PRIMARY}).items():
                res[k]["p_holm"] = round(p, 4)
            for k in res:
                res[k]["family"] = "primary" if k in PRIMARY else "exploratory"
            out[f"{app}: {cond} vs {ref}"] = res
    return out


# ---------------------------------------------------------------------------- the report
def evaluate(runs: list[RunData], ref: str | None = None) -> dict:
    catalog = load_catalog()
    faulty = [r for r in runs if not r.clean]
    clean = [r for r in runs if r.clean]
    per_run = [run_metrics(r) for r in runs]
    rep = {"runs": {"faulty": len(faulty), "clean": len(clean), "apps": sorted({r.app for r in runs}),
                    "conditions": sorted({r.condition for r in runs})}}
    by_app = {}  # one block per app and condition: conditions are never pooled
    for app, cond in sorted({(r.app, r.condition) for r in runs}):
        fa = [r for r in faulty if r.app == app and r.condition == cond]
        cl = [r for r in clean if r.app == app and r.condition == cond]
        prec = precision_block(fa)
        rec = recall_block(fa, catalog)
        med = sorted(x["total_recall"] for x in rec["per_run"] if x["total_recall"] is not None)
        mr = med[len(med) // 2] if med else None
        by_app[(app, cond)] = {"precision": prec, "recall": rec, "false_alarms": false_alarm_block(cl),
                       "f_beta": {"beta": BETA, "distinct_precision_x_median_total_recall":
                                  f_beta(prec["distinct"]["precision"], mr),
                                  "f1": f_beta(prec["distinct"]["precision"], mr, 1.0)},
                       "rule_recall": rule_recall(fa, catalog),
                       "reach": reach_block(fa + cl), "efficiency": efficiency_block(fa, catalog),
                       "cost": cost_block(fa + cl), "safety": safety_block(fa + cl),
                       "gate": gate_block(fa), "funnel": funnel_block(fa, catalog), "checks": checks_block(fa + cl),
                       "spread": spreads([m for m in per_run if m["app"] == app and m["condition"] == cond
                                          and not m["clean"]])}
    for (app, cond), b in by_app.items():
        b["funnel"]["recall_lost_per_guard"] = guard_loss(b["funnel"])
    rep["by_app"] = {f"{a} / {c}": v for (a, c), v in by_app.items()}
    rep["harness"] = harness_block(runs)
    rep["tier_calibration"] = tier_calibration(faulty)
    rep["engine_agreement"] = engine_agreement(faulty)
    rep["profile_accuracy"] = profile_accuracy(runs)
    rep["scaling"] = scaling_block(per_run, runs)
    rep["sensitivity"] = sensitivity_block(per_run, runs)
    rep["generalization"] = generalization_block(per_run, runs)
    rep["across_apps"] = across_apps(per_run)
    rep["detector_vs_end_to_end"] = detector_vs_e2e(runs)
    rep["report_quality"] = report_quality_block()
    rep["setup"] = setup_effort(runs)
    rep["confidence"] = confidence_block(faulty)
    rep["kappa"] = kappa_block()
    rep["per_run"] = per_run
    if ref and len({r.condition for r in faulty}) > 1:
        rep["comparisons"] = compare_conditions(per_run, ref)
    return rep


def report_md(rep: dict) -> str:
    """A compact markdown view of the main numbers; the JSON holds everything."""
    L = [f"# Evaluation ({rep['runs']['faulty']} faulty-app runs, {rep['runs']['clean']} clean-app runs; "
         f"conditions {', '.join(rep['runs']['conditions'])})", ""]
    for app, b in rep["by_app"].items():
        p, fa = b["precision"], b["false_alarms"]
        L += [f"## {app}", "", "| Metric | Value | 95% interval |", "|---|---|---|"]

        def row(name, d):
            if d and d.get("n"):
                L.append(f"| {name} | {d['precision']:.0%} ({d['tp']}/{d['n']}) | {d['ci95'][0]:.0%}-{d['ci95'][1]:.0%} |")

        row("Precision, per finding", p["raw"])
        row("Precision, per distinct issue", p["distinct"])
        row("Precision, gate-confirmed", p.get("confirmed"))
        row("Precision, confirmed minus judge rejects", p.get("judge_filtered"))
        if p["distinct"].get("n"):
            L.append(f"| Findings per distinct issue | {p['distinct']['findings_per_issue']} | |")
        rr = b["recall"]["per_run"]
        if rr:
            tr = [x["total_recall"] for x in rr if x["total_recall"] is not None]
            cr = [x["conditioned_recall"] for x in rr if x["conditioned_recall"] is not None]
            L.append(f"| Total recall per run | {', '.join(f'{x:.0%}' for x in tr)} | |")
            L.append(f"| Oracle-conditioned recall per run | {', '.join(f'{x:.0%}' for x in cr)} | |")
        for a, d in b["recall"]["across_runs"].items():
            L.append(f"| Faults found in any run | {len(d['found'])}/{d['reachable']} | |")
        if b["f_beta"]["distinct_precision_x_median_total_recall"]:
            L.append(f"| F{BETA} (distinct precision, median recall) | {b['f_beta']['distinct_precision_x_median_total_recall']} | |")
        if fa.get("runs"):
            pr = fa["per_run"]
            L.append(f"| Clean-app false alarms per run | {pr['rate']} ({fa['false_alarms']} in {fa['runs']} runs) "
                     f"| {pr['ci95'][0]}-{pr['ci95'][1]} |")
            if isinstance(fa["per_100_checks"], dict):
                c = fa["per_100_checks"]
                L.append(f"| Clean-app false alarms per 100 armed checks | {c['rate']} | {c['ci95'][0]}-{c['ci95'][1]} |")
        g = b["gate"]
        if g.get("gated"):
            L.append(f"| Gate recall loss | {g['gate_recall_loss']} | |")
        fu = b["funnel"]
        if fu["rows"]:
            L += ["", "Recall funnel (passed / measured, fault x run):", "",
                  "| " + " | ".join(FUNNEL) + " |", "|" + "---|" * len(FUNNEL),
                  "| " + " | ".join(f"{fu['stages'][k]['passed']}/{fu['stages'][k]['measured']}" for k in FUNNEL) + " |",
                  "", f"First failed stage: {fu['first_failed']}"]
        L.append("")
    c = rep["confidence"]
    if c.get("fitted"):
        L += ["## Confidence score", "", f"{c['validation']}; n = {c['n']}, positives {c['positives']}; "
              f"average precision {c['average_precision']}, Brier {c['brier']}", ""]
    L += [f"Blind-check kappa: {rep['kappa'].get('kappa', rep['kappa'].get('status'))}", ""]
    return "\n".join(L)



# ---------------------------------------------------------------------------- D61: the remaining metric groups
LIST_RULES = ("R04", "R04b", "R05", "R09", "R11", "R25", "R39", "R41", "R47", "R38", "R38c", "R44")  # need data in lists


def rule_recall(runs: list[RunData], catalog: dict) -> dict:
    """Group 10: per rule, seeded faults its findings were labelled with / (run x enabled fault) pairs whose
    families name the rule (the faults the rule is meant to catch)."""
    from .families import family_rules

    fam_of = fault_families_of()
    hit, total = Counter(), Counter()
    for r in runs:
        if r.clean:
            continue
        by_rule = defaultdict(set)
        for f in r.findings:
            lab = r.labels.get(f["sig"], "").upper()
            if lab in r.enabled:
                by_rule[rule_of(f)].add(lab)
        for fid in r.enabled:
            if not catalog.get(fid, {}).get("reachable", True):
                continue
            for rule in {x for fam in fam_of.get(fid, []) for x in family_rules(fam)}:
                total[rule] += 1
                hit[rule] += fid in by_rule.get(rule, set())
    return {k: {"found": hit[k], "of": total[k], "recall": round(hit[k] / total[k], 4)} for k in sorted(total)}


def reach_block(runs: list[RunData]) -> dict:
    """Group 4 from the session, sweep, role, api and step records of the runs."""
    sess = [e for r in runs for e in r.events.get("session", [])]
    sweep = [e for r in runs for e in r.events.get("sweep", [])]
    forms: dict = defaultdict(lambda: Counter())
    classes: dict = defaultdict(set)
    for e in sweep:
        for k, v in (e.get("forms") or {}).items():
            forms[k].update(v)
        for k, v in (e.get("input_classes") or {}).items():
            classes[k].update(v)
    role_of = {(r.run_id, e["worker"]): e["role"] for r in runs for e in r.events.get("role", [])}
    routes_by_role = defaultdict(set)
    for r in runs:
        for st in r.steps:
            routes_by_role[role_of.get((r.run_id, st["worker"]), "default")].add(st["route"])
    armed = Counter()
    for r in runs:
        for c in r.checks:
            if c["rule"] in LIST_RULES:
                armed["armed" if c["outcome"] in ARMED else "not"] += c["n"]
    api = [e for r in runs for e in r.events.get("sweep", []) if (e.get("api") or {}).get("operations")]
    server = [json.loads((r.run_dir / "server_coverage.json").read_text(encoding="utf-8")) for r in runs
              if r.run_dir is not None and (r.run_dir / "server_coverage.json").exists()]
    mods = Counter()
    for e in sess:
        mods.update(e.get("modalities") or {})
    return {"controls_seen": sum(e.get("controls_seen", 0) for e in sess),
            "controls_activated": sum(e.get("controls_activated", 0) for e in sess),
            "controls_activated_share": _ratio(sum(e.get("controls_activated", 0) for e in sess),
                                               sum(e.get("controls_seen", 0) for e in sess)),
            "write_success_by_form": {k: {**dict(v), "rate": _ratio(v["accepted"] + v["retry_accepted"], v["attempted"])}
                                      for k, v in sorted(forms.items())},
            "write_success": _ratio(sum(v["accepted"] + v["retry_accepted"] for v in forms.values()),
                                    sum(v["attempted"] for v in forms.values())),
            "input_classes_by_field_kind": {k: sorted(v) for k, v in sorted(classes.items())},
            "routes_by_role": {k: len(v) for k, v in sorted(routes_by_role.items())},
            "data_depth_list_rule_arm_rate": _ratio(armed["armed"], armed["armed"] + armed["not"]),
            "api_endpoint_coverage": _ratio(sum(len(e["api"]["called"]) for e in api), sum(e["api"]["operations"] for e in api)),
            "server_coverage": [{k: s_.get(k) for k in ("lines", "covered", "share")} for s_ in server] or "not measured",
            "unsupported_modalities_pages": dict(mods),
            "build_modes": sorted({e.get("build_mode") for e in sess if e.get("build_mode")})}


def _auc(points: list[tuple[float, float]]) -> float | None:
    """Area under a step curve of (x in 0..1, y in 0..1), x sorted."""
    if not points:
        return None
    area, px, py = 0.0, 0.0, 0.0
    for x, y in points:
        area += (x - px) * py
        px, py = x, y
    return round(area + (1 - px) * py, 4)


def efficiency_block(runs: list[RunData], catalog: dict) -> dict:
    """Group 5: dead-end and revisit rates, session losses, recall over steps / tokens / minutes (with the area
    under each curve), and the state plateau (the share of the run after which 95% of its states were known)."""
    out = []
    for r in runs:
        st = sorted(r.steps, key=lambda x: x["t"])
        if not st:
            continue
        n = len(st)
        travels = defaultdict(list)  # worker -> global step counter values at which the harness travelled away
        for e in r.events.get("travel", []):
            travels[e.get("worker")].append(e.get("step") or 0)
        dead = 0  # a step whose worker next went Back, or was moved elsewhere by the harness, before acting again
        for w in {x["worker"] for x in st}:
            ws = sorted((x for x in st if x["worker"] == w), key=lambda x: x["step"])
            for a, b in zip(ws, ws[1:]):
                if b["back"] or any(a["step"] <= t < b["step"] for t in travels[w]):
                    dead += 1
        T, cum_tok = (st[-1]["t"] or 1), []
        tok = 0
        for x in st:
            tok += x["tokens"] or 0
            cum_tok.append(tok)
        first = {}
        for f in r.findings:
            fid = r.labels.get(f["sig"], "").upper()
            if fid in r.enabled:
                key = (f.get("worker"), f.get("first_step"))
                i = next((k for k, x in enumerate(st) if (x["worker"], x["step"]) == key), None)
                if i is not None:
                    first[fid] = min(first.get(fid, n), i)
        reach = [f for f in r.enabled if catalog.get(f, {}).get("reachable", True)]
        curves = {}
        for axis, pos in (("steps", lambda i: (i + 1) / n), ("minutes", lambda i: st[i]["t"] / T),
                          ("tokens", lambda i: cum_tok[i] / tok if tok else (i + 1) / n)):
            pts = sorted((pos(i), k / len(reach)) for k, i in enumerate(sorted(first.values()), 1)) if reach else []
            curves[axis] = _auc(pts)
        states = [x for x in st if x["new"]]
        plateau = None
        if states:
            k95 = states[max(0, math.ceil(0.95 * len(states)) - 1)]  # the step by which 95% of the states were known
            plateau = round(k95["t"] / T, 4)
        out.append({"run": r.run_id, "dead_end_rate": round(dead / n, 4), "revisit_rate": round(sum(1 for x in st if not x["new"]) / n, 4),
                    "session_losses": sum(e.get("session_losses", 0) for e in r.events.get("sweep", [])),
                    "recall_auc": curves, "state_plateau_at": plateau})
    return {"per_run": out}


def cost_block(runs: list[RunData]) -> dict:
    """Group 7: tokens per finding and per confirmed true finding, USD, gate overhead, LLM retries and
    policy errors, and cross-worker redundancy (states several workers visited)."""
    rows = []
    for r in runs:
        end = (r.events.get("run_end") or [{}])[-1]
        usage = end.get("llm_usage") or {}
        tokens = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        tp_conf = [f for f in r.findings if f.get("status") == "confirmed" and is_true_positive(r.labels.get(f["sig"], ""))]
        gate = (r.events.get("gate_done") or [{}])[-1]
        by_state = defaultdict(set)
        for x in r.steps:
            by_state[x["state"]].add(x["worker"])
        steps = len(r.steps) or r.summary.get("steps", 0) or 0
        rows.append({"run": r.run_id, "tokens": tokens, "usd": end.get("cost_usd"),
                     "tokens_per_finding": round(tokens / len(r.findings)) if r.findings else None,
                     "tokens_per_confirmed_true": round(tokens / len(tp_conf)) if tp_conf else None,
                     "gate_replays": gate.get("replays"), "gate_minutes": gate.get("minutes"),
                     "judge_tokens": gate.get("judge_tokens"), "llm_retries": usage.get("retries"),
                     "policy_error_rate": round(len(r.events.get("policy_error", [])) / steps, 4) if steps else None,
                     "cross_worker_redundancy": round(sum(1 for v in by_state.values() if len(v) >= 2) / len(by_state), 4)
                     if by_state else None})
    return {"per_run": rows}


def safety_block(runs: list[RunData]) -> dict:
    """Group 11: destructive incidents (deletes of items the run did not create), out-of-scope requests the
    router blocked, writes the mode refused, writes that passed although the mode forbids them, cleanup share."""
    sess = [e for r in runs for e in r.events.get("session", [])]
    saf = [e for r in runs for e in r.events.get("safety", [])]
    shares = [e["cleanup_share"] for e in saf if e.get("cleanup_share") is not None]
    return {"destructive_incidents": sum(e.get("foreign_delete_count", 0) for e in saf),
            "out_of_scope_blocked": sum(e.get("out_of_scope_blocked", 0) for e in sess),
            "writes_refused_by_mode": sum(len(e.get("blocked_writes") or []) for e in sess),
            "mode_violations": sum(len(e.get("mode_violations") or []) for e in sess),
            "cleanup_share_median": sorted(shares)[len(shares) // 2] if shares else None,
            "modes": sorted({(r.config or {}).get("mode", "controlled") for r in runs})}


def guard_loss(funnel: dict) -> dict:
    """Group 6: per guard, the (fault x run) misses that failed at S4 or S5 while the guard suppressed a rule of the
    fault's families on its route (an upper bound of the recall the guard costs)."""
    out = Counter()
    for row in funnel.get("rows", []):
        if row.get("first_failed") in ("S4_armed", "S5_flagged"):
            for g in row.get("suppressed") or {}:
                out[g] += 1
    return dict(out.most_common())


def tier_calibration(runs: list[RunData]) -> dict:
    """Group 10: the tier each rule reports at against the tier its measured precision gives it."""
    prec = precision_block(runs)["by_rule"]
    from .consistency import TIER

    rows = {k: {"assigned": TIER.get(k, "implicit"), "measured": v["measured_tier"], "n": v["n"]} for k, v in prec.items()}
    ok = [v for v in rows.values() if v["assigned"] in ("T1", "T2") and v["n"] >= 5]
    return {"rules": rows, "agree": sum(1 for v in ok if v["assigned"] == v["measured"]), "of": len(ok)}


def engine_agreement(runs: list[RunData]) -> dict:
    """Group 10 / X9: confirmed findings replayed in other engines, and the share that held in every engine."""
    rows = [(f.get("gate") or {}).get("engines") for r in runs for f in r.findings]
    rows = [x for x in rows if x]
    if not rows:
        return {"replayed": 0}
    return {"replayed": len(rows), "held_everywhere": sum(1 for x in rows if all(v for v in x.values())),
            "share": round(sum(1 for x in rows if all(v for v in x.values())) / len(rows), 4)}


def profile_accuracy(runs: list[RunData]) -> dict:
    """X5: the app profile the LLM gave against the app type and primitives in the app's config (our labels)."""
    out = []
    for r in runs:
        app = {**app_meta(r.app), **((r.config or {}).get("app") or {})}
        for e in r.events.get("app_profile", []):
            if not e.get("app_type"):
                continue
            truth = set(app.get("primitives") or [])
            got = set(e.get("primitives") or [])
            out.append({"run": r.run_id, "type_ok": (e["app_type"] == app.get("app_type")) if app.get("app_type") else None,
                        "primitive_precision": round(len(got & truth) / len(got), 4) if got and truth else None,
                        "primitive_recall": round(len(got & truth) / len(truth), 4) if got and truth else None})
    return {"per_run": out} if out else {"status": "no profiles or no truth (app.app_type, app.primitives)"}


def scaling_block(per_run: list[dict], runs: list[RunData]) -> dict:
    """Group 7: parallel speedup and efficiency, per app and condition, across the worker counts present
    (unique states and faults found per run; speedup = mean at N / mean at the smallest N)."""
    nw = {r.run_id: int(r.summary.get("workers") or 1) for r in runs}
    groups = defaultdict(lambda: defaultdict(list))
    for m in per_run:
        if not m["clean"]:
            groups[(m["app"], m["condition"])][nw.get(m["run"], 1)].append(m)
    out = {}
    for (app, cond), by_n in groups.items():
        if len(by_n) < 2:
            continue
        base_n = min(by_n)
        mean = lambda xs, k: sum(x.get(k) or 0 for x in xs) / len(xs)  # noqa: E731
        b = mean(by_n[base_n], "unique_states") or 1
        out[f"{app} / {cond}"] = {n: {"runs": len(v), "unique_states": round(mean(v, "unique_states"), 1),
                                      "faults_found": round(mean(v, "faults_found"), 2),
                                      "speedup": round(mean(v, "unique_states") / b, 3),
                                      "efficiency": round(mean(v, "unique_states") / b / (n / base_n), 3)}
                                  for n, v in sorted(by_n.items())}
    return out or {"status": "one worker count per condition"}


def _axis(r: RunData, axis: str) -> str:
    c = r.config or {}
    if axis == "llm":
        return (c.get("llm") or {}).get("model", "")
    if axis == "framework":
        return (c.get("app") or {}).get("framework", "")
    return (c.get("app") or {}).get("name", r.app)  # 'app': the rebranded app is its own name


def sensitivity_block(per_run: list[dict], runs: list[RunData]) -> dict:
    """Group 8: the primary metrics across the values of one axis (LLM model, front-end framework, the
    rebranded app vs its original), condition by condition; exact Mann-Whitney p, unadjusted (exploratory)."""
    by_id = {r.run_id: r for r in runs}
    out = {}
    for axis in ("llm", "framework", "app"):
        groups = defaultdict(list)
        for m in per_run:
            r = by_id.get(m["run"])
            if r is None or m["clean"]:
                continue
            base = APP_ALIAS.get(m["app"], m["app"]) if axis == "app" else m["app"]
            groups[(base, m["condition"], _axis(r, axis))].append(m)
        keys = defaultdict(list)
        for (base, cond, val) in groups:
            keys[(base, cond)].append(val)
        for (base, cond), vals in keys.items():
            vals = sorted(v for v in vals if v)
            if len(vals) < 2:
                continue
            ref = vals[0]
            for v in vals[1:]:
                res = {}
                for k in PRIMARY:
                    x = [m[k] for m in groups[(base, cond, v)] if isinstance(m.get(k), (int, float))]
                    y = [m[k] for m in groups[(base, cond, ref)] if isinstance(m.get(k), (int, float))]
                    if len(x) >= 2 and len(y) >= 2:
                        res[k] = {"n": [len(x), len(y)], "a12": round(a12(x, y), 3), "p": round(mann_whitney_p(x, y), 4)}
                if res:
                    out[f"{axis}: {base} / {cond}: {v} vs {ref}"] = res
    return out or {"status": "no axis has two values in these runs"}


def generalization_block(per_run: list[dict], runs: list[RunData]) -> dict:
    """Group 9: development vs held-out apps (app.heldout in the config): the difference of the medians of
    recall, distinct-issue precision and findings per run."""
    held = {r.run_id: bool(((r.config or {}).get("app") or {}).get("heldout", app_meta(r.app).get("heldout"))) for r in runs}
    out = {}
    for cond in sorted({m["condition"] for m in per_run}):
        side = {True: [], False: []}
        for m in per_run:
            if m["condition"] == cond and not m["clean"]:
                side[held.get(m["run"], False)].append(m)
        if not side[True] or not side[False]:
            continue
        med = lambda xs, k: (lambda v: v[len(v) // 2] if v else None)(sorted(x[k] for x in xs if isinstance(x.get(k), (int, float))))  # noqa: E731
        out[cond] = {k: {"dev": med(side[False], k), "heldout": med(side[True], k)}
                     for k in ("faults_found", "precision_distinct", "findings")}
        for k, v in out[cond].items():
            v["gap"] = round(v["dev"] - v["heldout"], 4) if v["dev"] is not None and v["heldout"] is not None else None
    return out or {"status": "no held-out runs yet"}


def across_apps(per_run: list[dict]) -> dict:
    """Group 12: per condition, the mean over apps of each app's median, with a bootstrap interval over apps."""
    out = {}
    for cond in sorted({m["condition"] for m in per_run}):
        for k in PRIMARY:
            meds = []
            for app in sorted({m["app"] for m in per_run}):
                v = sorted(m[k] for m in per_run if m["app"] == app and m["condition"] == cond and not m["clean"]
                           and isinstance(m.get(k), (int, float)))
                if v:
                    meds.append(v[len(v) // 2])
            if len(meds) >= 2:
                out.setdefault(cond, {})[k] = {"apps": len(meds), "mean_of_medians": round(sum(meds) / len(meds), 4),
                                               "boot95": [round(x, 4) for x in bootstrap_ci(meds)]}
    return out or {"status": "fewer than two apps per condition"}


def detector_vs_e2e(runs: list[RunData]) -> dict:
    """E10: for runs present both live and resweept, the faults found by each (detector-only = the resweep of
    the recorded trail with the current oracles, end-to-end = what the run reported)."""
    by = defaultdict(dict)
    for r in runs:
        if not r.clean:
            by[r.run_id][r.source] = found_faults(r)
    rows = [{"run": k, "live": len(v["live"]), "resweep": len(v["resweep"]), "both": len(v["live"] & v["resweep"])}
            for k, v in sorted(by.items()) if "live" in v and "resweep" in v]
    return {"runs": rows} if rows else {"status": "no run evaluated both live and resweept"}


REPORT_RATINGS = REPO_ROOT / "logs/experiments/report_quality.toml"
RUBRIC = ("steps_clear", "expected_vs_actual", "evidence", "minimal", "severity_clear")


def report_quality_block(path: Path = REPORT_RATINGS) -> dict:
    """Group 3: the user's ratings of sampled confirmed reports (scripts/report_sample.py writes the sheet):
    reproduced by a person (yes/no), an actionability rubric of five 0-2 items, minutes to triage."""
    if not path.exists():
        return {"status": "no rating sheet (python scripts/report_sample.py)"}
    rows = [v for d in tomllib.loads(path.read_text(encoding="utf-8")).values() for v in d.values() if isinstance(v, dict)]
    rated = [v for v in rows if str(v.get("reproduced", "")).lower() in ("yes", "no")]
    if not rated:
        return {"status": "pending: the sheet has no ratings yet", "sampled": len(rows)}
    rep = sum(1 for v in rated if str(v["reproduced"]).lower() == "yes")
    scores = [sum(int(v.get(k) or 0) for k in RUBRIC) for v in rated]
    mins = sorted(float(v["triage_minutes"]) for v in rated if v.get("triage_minutes") not in (None, ""))
    return {"rated": len(rated), "reproduction": _prec(rep, len(rated)),
            "actionability_mean_of_10": round(sum(scores) / len(scores), 2),
            "triage_minutes_median": mins[len(mins) // 2] if mins else None}
