"""Condition comparison over repeated runs: median [IQR], exact Mann-Whitney U
(two-sided) and the Vargha-Delaney A12 effect size, as fixed in the research
plan (section 6). No SciPy: with 5-10 runs per condition the exact
permutation distribution is cheap and better than the normal approximation."""

from __future__ import annotations

import itertools
import json
import tomllib
from pathlib import Path
from statistics import median

from .registry import LOG_DIR, NOTES

METRICS = [
    ("unique_states", "Unique states", True),
    ("unique_routes", "Unique routes", True),
    ("duplicate_action_rate", "Duplicate-action rate", False),
    ("faults_found", "Seeded faults found", True),
    # G2/G3 rows: shown only when at least one side has them (B4 conditions, labelled runs)
    ("faults_found_all", "Seeded faults found (all oracles, labelled)", True),
    ("faults_found_confirmed", "Seeded faults found (gate-confirmed)", True),
    ("faults_exposed_n", "Injected faults exposed (fired)", True),
    ("faults_reached", "Seeded faults reached (trigger attempted, offline)", True),
    ("findings", "Findings (all)", True),
    ("findings_confirmed", "Findings (gate-confirmed)", True),
    ("precision_raw", "Precision, raw candidates", True),
    ("precision_gated", "Precision, gate-confirmed", True),
    ("precision_judged", "Precision, confirmed minus judge rejects", True),
    ("steps", "Steps", True),
    ("tokens_total", "Tokens", False),
]
# A run without a G3 row value is measured by its implicit-oracle value (same thing for it).
FALLBACK = {"faults_found_all": "faults_found"}
BASE_METRICS = {"unique_states", "unique_routes", "duplicate_action_rate", "faults_found", "findings", "steps",
                "tokens_total"}


def quartiles(xs: list[float]) -> tuple[float, float, float]:
    s = sorted(xs)
    n = len(s)

    def q(p: float) -> float:  # linear interpolation (same as numpy's default)
        k = (n - 1) * p
        lo, hi = int(k), min(int(k) + 1, n - 1)
        return s[lo] + (s[hi] - s[lo]) * (k - lo)

    return q(0.25), median(s), q(0.75)


def a12(x: list[float], y: list[float]) -> float:
    """Probability that a run from x beats a run from y (ties count half)."""
    wins = sum((xi > yi) + 0.5 * (xi == yi) for xi in x for yi in y)
    return wins / (len(x) * len(y))


def magnitude(a: float) -> str:
    d = abs(a - 0.5)
    return "negligible" if d < 0.06 else "small" if d < 0.14 else "medium" if d < 0.21 else "large"


def mann_whitney_p(x: list[float], y: list[float]) -> float:
    """Exact two-sided p-value of the rank-sum statistic by enumerating all splits."""
    pooled = x + y
    n = len(x)
    ranks = _ranks(pooled)
    observed = sum(ranks[:n])
    mean = n * (len(pooled) + 1) / 2
    obs_dev = abs(observed - mean)
    count = total = 0
    for idx in itertools.combinations(range(len(pooled)), n):
        total += 1
        if abs(sum(ranks[i] for i in idx) - mean) >= obs_dev - 1e-9:
            count += 1
    return count / total


def _ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def load_valid_runs(agent: str, label_contains: str = "", workers: int | None = None) -> list[dict]:
    from .labels import label_metrics, load_labels

    notes = tomllib.loads(NOTES.read_text(encoding="utf-8")) if NOTES.exists() else {}
    labels = load_labels()
    out = []
    for d in sorted((LOG_DIR / "runs").iterdir()):
        s_path = d / "summary.json"
        if not s_path.exists() or notes.get(d.name, {}).get("status") != "valid":
            continue
        s = json.loads(s_path.read_text(encoding="utf-8"))
        if s.get("agent") != agent or label_contains not in d.name:
            continue
        if workers is not None and s.get("workers") != workers:
            continue
        fd = s.get("fault_detection") or {}
        s["faults_found"] = sum(1 for v in fd.values() if v["detected"])
        if "fault_reach" in s:
            s["faults_reached"] = sum(1 for v in s["fault_reach"].values() if v["reached"])
        f_path = d / "findings.json"
        if f_path.exists():
            findings = json.loads(f_path.read_text(encoding="utf-8"))
            s.update(label_metrics(d.name, findings, s, labels))
        s["_run_id"] = d.name
        out.append(s)
    return out


def compare(a_runs: list[dict], b_runs: list[dict], a_name: str, b_name: str) -> str:
    lines = [
        f"| Metric | {a_name} median [IQR] (n={len(a_runs)}) | {b_name} median [IQR] (n={len(b_runs)}) "
        f"| p (MWU, exact) | Â12 ({b_name} > {a_name}) |",
        "|---|---|---|---|---|",
    ]
    for key, label, _higher_better in METRICS:
        if key in FALLBACK and not (has_metric(a_runs, key) or has_metric(b_runs, key)):
            continue
        x, y = _values(a_runs, key), _values(b_runs, key)
        if not x or not y:
            continue
        pct = key.endswith("rate") or key.startswith("precision")
        fmt = (lambda v: f"{v:.0%}") if pct else (lambda v: f"{v:,.0f}" if v >= 100 else f"{v:g}")
        qa, qb = quartiles(x), quartiles(y)
        p = mann_whitney_p(x, y) if len(x) > 1 and len(y) > 1 else float("nan")
        a = a12(y, x)
        na = f" (n={len(x)})" if len(x) != len(a_runs) else ""
        nb = f" (n={len(y)})" if len(y) != len(b_runs) else ""
        lines.append(f"| {label} | {fmt(qa[1])} [{fmt(qa[0])}–{fmt(qa[2])}]{na} | {fmt(qb[1])} [{fmt(qb[0])}–{fmt(qb[2])}]{nb} "
                     f"| {p:.3f} | {a:.2f} ({magnitude(a)}) |")
    return "\n".join(lines)


def _values(runs: list[dict], key: str) -> list[float]:
    """Values of `key` over runs that have it. Base metrics count a missing value as 0 (old
    behaviour); G2/G3 metrics skip runs without them, and FALLBACK rows appear only when
    some run really has the metric."""
    if key in BASE_METRICS:
        return [float(r.get(key, 0) or 0) for r in runs]
    vals = [r.get(key) for r in runs]
    if key in FALLBACK:
        return [float(v if v is not None else r.get(FALLBACK[key], 0) or 0) for v, r in zip(vals, runs)]
    return [float(v) for v in vals if v is not None]


def has_metric(runs: list[dict], key: str) -> bool:
    return any(r.get(key) is not None for r in runs)


def gate_report(runs: list[dict]) -> str:
    """G2 within the same runs (A-G2 = gate off = raw candidates): per run, then medians."""
    lines = ["| Run | Candidates | Confirmed | Flaky | Rejected | Unverified | Precision raw | Precision gated "
             "| Faults raw | Faults confirmed | Gate min | Judge tokens (% of run) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def pct(v):
        return "–" if v is None else f"{v:.0%}"

    for r in runs:
        g = r.get("gate") or {}
        share = g.get("judge_tokens", 0) / r["tokens_total"] if r.get("tokens_total") else 0
        lines.append(f"| `{r['_run_id']}` | {g.get('candidates', '–')} | {g.get('confirmed', 0)} | {g.get('flaky', 0)} "
                     f"| {g.get('rejected', 0)} | {g.get('unverified', 0)} | {pct(r.get('precision_raw'))} "
                     f"| {pct(r.get('precision_gated'))} | {r.get('faults_found_all', r.get('faults_found'))} "
                     f"| {r.get('faults_found_confirmed', '–')} | {g.get('minutes', '–')} "
                     f"| {g.get('judge_tokens', 0)} ({share:.0%}) |")
    missing = sum(r.get("labels_missing", 0) for r in runs)
    if missing:
        lines.append(f"\n{missing} finding(s) unlabelled: precision is left out for those runs "
                     "(python -m webtester triage <run>).")
    return "\n".join(lines)
