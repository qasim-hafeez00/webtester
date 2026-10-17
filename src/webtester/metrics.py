"""Metrics computed offline from a run's trace (never from in-memory state), so
every condition is measured by the same code."""

from __future__ import annotations

import tomllib
from collections import Counter
from pathlib import Path

from .trace import read_trace


def summarize(trace_path: Path) -> dict:
    events = read_trace(trace_path)
    steps = [e for e in events if e["type"] == "step"]
    start = next((e for e in events if e["type"] == "run_start"), {})
    end = next((e for e in events if e["type"] == "run_end"), {})

    states: set[str] = set()
    routes: set[str] = set()
    actions = 0
    dup_actions = 0
    failed_actions = 0
    action_keys: set[str] = set()
    curve = []  # (step index, minutes, unique states)
    prompt_tok = completion_tok = calls = retries = 0
    checks: Counter = Counter()
    exposed: set[str] = set()
    silent: set[str] = set()
    for i, s in enumerate(steps, 1):
        exposed.update(s.get("faults_exposed") or ())
        silent.update(s.get("faults_triggered_silent") or ())
        states.add(s["state"])
        if s.get("next_state"):
            states.add(s["next_state"])
        routes.add(s["route"])
        for a in s["actions"]:
            actions += 1
            dup_actions += bool(a.get("dup"))
            failed_actions += not a.get("ok", True)
            action_keys.add(a["key"])
        u = s.get("usage") or {}
        prompt_tok += u.get("prompt_tokens", 0)
        completion_tok += u.get("completion_tokens", 0)
        calls += u.get("calls", 0)
        retries += u.get("retries", 0)
        for c in s.get("checks") or ():
            checks[c["status"]] += 1
            checks["proposed"] += 1
        if i % 10 == 0 or i == len(steps):
            curve.append((i, round(s["t"] / 60, 2), len(states)))

    findings = [e["finding"] for e in events if e["type"] == "finding"]
    # Run health: an LLM outage or quota stop makes a time-budgeted run incomparable.
    gaps = [b["t"] - a["t"] for a, b in zip(steps, steps[1:])]
    llm_failures = sum(1 for e in events if e["type"] == "policy_error" and e["error"].startswith("LLM call failed"))
    max_gap = round(max(gaps), 1) if gaps else None
    reasons = end.get("reasons") or []
    uses_llm = (prompt_tok + completion_tok) > 0 or llm_failures > 0
    stalled = uses_llm and (max_gap or 0) > 60  # crawler passes legitimately pause between steps
    gate_expected = bool(start.get("gate"))
    gate_done = next((e for e in events if e["type"] == "gate_done"), None)
    gate_ok = not gate_expected or (gate_done is not None and not any(e["type"] == "gate_error" for e in events))
    healthy = bool(steps) and llm_failures == 0 and not stalled and gate_ok and all(
        r.endswith(("max_minutes", "max_steps", "max_tokens")) for r in reasons)
    by_kind = Counter(f["kind"] for f in findings)
    tokens = prompt_tok + completion_tok
    return {
        "run_id": start.get("run_id"),
        "agent": start.get("agent"),
        "workers": start.get("workers"),
        "faults": start.get("faults"),
        "stop_reason": end.get("reasons"),
        "steps": len(steps),
        "wall_minutes": round(steps[-1]["t"] / 60, 2) if steps else 0,
        "browser_minutes": round(sum(s.get("seconds", 0) for s in steps) / 60, 2),
        "unique_states": len(states),
        "unique_routes": len(routes),
        "actions": actions,
        "unique_actions": len(action_keys),
        "duplicate_action_rate": round(dup_actions / actions, 4) if actions else 0.0,
        "failed_action_rate": round(failed_actions / actions, 4) if actions else 0.0,
        "findings": len(findings),
        "findings_by_kind": dict(by_kind),
        "llm_calls": calls,
        "llm_retries": retries,
        "policy_errors": sum(1 for e in events if e["type"] == "policy_error"),
        "tokens_prompt": prompt_tok,
        "tokens_completion": completion_tok,
        "tokens_total": tokens,
        "tokens_per_step": round(tokens / len(steps), 1) if steps else 0,
        "state_curve": curve,
        "routes": sorted(routes),
        "health": {"ok": healthy, "llm_failures": llm_failures, "max_step_gap_s": max_gap, "stalled": stalled,
                   **({"gate_ok": gate_ok} if gate_expected else {})},
        **_g2_g3(events, checks, gate_done),
        **({"faults_exposed": sorted(exposed), "faults_exposed_n": len(exposed)} if exposed else {}),
        # trigger held but never with a visible change (e.g. a literal-dependent fault without its literal)
        **({"faults_triggered_silent_only": sorted(silent - exposed)} if silent - exposed else {}),
        **({"injector_errors": n_inj} if (n_inj := sum(len(e["errors"]) for e in events
                                                       if e["type"] == "injector_error")) else {}),
    }


def _g2_g3(events: list[dict], checks: Counter, gate_done: dict | None) -> dict:
    """Inferred-oracle check counts (G3) and evidence-gate outcomes (G2), when the run had them."""
    out: dict = {}
    if checks:
        out["checks"] = {k: checks.get(k, 0) for k in ("proposed", "pass", "violated", "inconclusive", "skipped")}
    if gate_done is not None:
        results = [e for e in events if e["type"] == "gate_result"]
        out["gate"] = {k: v for k, v in gate_done.items() if k not in ("t", "type")}
        out["findings_confirmed"] = sum(1 for e in results if e["status"] == "confirmed")
        out["findings_flaky"] = sum(1 for e in results if e["status"] == "flaky")
        judged = [e for e in events if e["type"] == "gate_judge"]
        out["judge_verdicts"] = dict(Counter(e.get("verdict") for e in judged))
    return out


def load_fault_catalog(path: Path) -> dict[str, dict]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return {f["id"].upper(): f for f in raw.get("fault", [])}


def fault_detection(findings: list[dict], enabled: list[str], catalog: dict[str, dict]) -> dict:
    """Which enabled faults were revealed by at least one finding.

    A catalog entry's `detect` table holds the implicit-oracle signature it
    produces: `kind` plus a substring that must appear in the finding signature.
    Faults whose class needs a semantic oracle have no `detect` entry and can
    only be found by inferred oracles (G3) or by manual triage."""
    result = {}
    for fid in enabled:
        spec = catalog.get(fid, {})
        rule = spec.get("detect")
        hit = None
        if rule:
            kinds = rule["kind"] if isinstance(rule["kind"], list) else [rule["kind"]]
            for f in findings:
                if (f["kind"] in kinds and rule.get("contains", "") in f["sig"]
                        and rule.get("page", "") in f.get("page_url", "")):
                    hit = f["sig"]
                    break
        result[fid] = {"class": spec.get("class"), "detected": hit is not None, "by": hit,
                       "implicit_detectable": bool(rule)}
    return result
