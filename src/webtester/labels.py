"""Finding labels: the human ground truth behind precision (G2) and semantic-fault recall (G3).

Implicit findings map to seeded faults by the catalog's `detect` rules, but
whether an inferred-oracle violation reveals F05 or is a wrong expectation needs
a person. `python -m webtester triage <run>` lists a run's findings with a
suggested label and appends a blank entry per unlabelled finding to
logs/experiments/finding_labels.toml:

    ["<run id>"."<finding signature>"]
    label = "F06"   # a seeded/injected fault id enabled in that run, a known upstream defect
                    # (U1-U7 for Conduit, apps/realworld/README.md), "new: <what>" (a real bug we did not seed), or "fp"

Suggestions (catalog `detect` rules, injected faults the worker had already
triggered, `hint` routes/checks, known upstream patterns) are shown to speed
labelling. They are never used as labels.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .config import REPO_ROOT
from .metrics import fault_detection, load_fault_catalog, route_matches
from .registry import LOG_DIR

LABELS = LOG_DIR / "finding_labels.toml"


def load_labels(path: Path = LABELS) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def label_of(labels: dict, run_id: str, sig: str) -> str:
    return str((labels.get(run_id, {}).get(sig) or {}).get("label", "")).strip()


def is_true_positive(label: str) -> bool:
    return bool(label) and label.lower() != "fp"


def suggest(f: dict, catalog: dict, enabled: list[str]) -> str:
    hit = [fid for fid, d in fault_detection([f], enabled, catalog).items() if d["detected"]]
    if hit:
        return hit[0]
    msg, sig = f.get("message", ""), f.get("sig", "")
    if f["kind"] in ("console_error", "page_error") and ("ERROR {}" in msg or "ERROR {errors" in msg):
        return "U5?"
    if f["kind"] == "http_5xx" and "PUT /api/user" in sig:
        return "U1?"
    if f.get("exposed"):  # injected faults (BookStack): those this worker had already triggered
        return " / ".join(f"{fid}?" for fid in f["exposed"]) + (" / fp?" if f["kind"] == "oracle_violation" else "")
    if f["kind"] == "oracle_violation":
        _, check, route, *_ = sig.split("|")
        cands = []
        for fid in enabled:
            hint = catalog.get(fid, {}).get("hint") or {}
            if check in hint.get("checks", ()) and any(route_matches(r, route) for r in hint.get("routes", ())):
                cands.append(fid)
        return " / ".join(f"{c}?" for c in cands) or "fp?"
    return ""


def label_metrics(run_id: str, findings: list[dict], summary: dict, labels: dict) -> dict:
    """Seeded faults found over all oracles and over gate-confirmed findings, and precision
    (raw candidates, gate-confirmed, confirmed minus judge 'wrong_expectation').
    Precision needs every finding of the run labelled; otherwise it is left out."""
    lab = {f["sig"]: label_of(labels, run_id, f["sig"]) for f in findings}
    enabled = set(summary.get("faults") or [])
    gated = any(f.get("status", "candidate") != "candidate" for f in findings)
    has_g3 = any(f["kind"] == "oracle_violation" for f in findings) or run_id in labels
    out: dict = {"labels_missing": sum(1 for v in lab.values() if not v)}

    def seeded(fs: list[dict], rule_key: str) -> int:
        rules = {fid for fid, d in (summary.get(rule_key) or {}).items() if d["detected"]}
        labelled = {lab[f["sig"]].upper() for f in fs if lab[f["sig"]].upper() in enabled}
        return len((rules | labelled) & enabled)

    confirmed = [f for f in findings if f.get("status") == "confirmed"]
    if has_g3:
        out["faults_found_all"] = seeded(findings, "fault_detection")
    if gated:
        out["faults_found_confirmed"] = seeded(confirmed, "fault_detection_confirmed")
    if findings and not out["labels_missing"]:
        def prec(fs: list[dict]) -> float | None:
            return sum(is_true_positive(lab[f["sig"]]) for f in fs) / len(fs) if fs else None

        out["precision_raw"] = prec(findings)
        if gated:
            out["precision_gated"] = prec(confirmed)
            out["precision_judged"] = prec([f for f in confirmed
                                             if (f.get("judge") or {}).get("verdict") != "wrong_expectation"])
    return out


def _run_dir(arg: str) -> Path:
    p = Path(arg)
    for cand in (p, REPO_ROOT / "runs" / arg, LOG_DIR / "runs" / arg):
        if (cand / "findings.json").exists():
            return cand
    raise SystemExit(f"no findings.json for {arg}")


def triage(arg: str, write: bool = True) -> str:
    d = _run_dir(arg)
    run_id = d.name
    findings = json.loads((d / "findings.json").read_text(encoding="utf-8"))
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    cat_path = REPO_ROOT / (cfg["app"].get("compose_dir") or "") / "faults" / "faults.toml"
    catalog = load_fault_catalog(cat_path) if cat_path.exists() else {}
    enabled = summary.get("faults") or []
    labels = load_labels()
    lines = [f"{run_id}: {len(findings)} finding(s)", ""]
    new_entries = []
    for i, f in enumerate(findings, 1):
        current = label_of(labels, run_id, f["sig"])
        tip = suggest(f, catalog, enabled)
        judge = (f.get("judge") or {}).get("verdict", "")
        lines.append(f"[{i}] {f.get('status', 'candidate'):10} {f['kind']:16} label={current or '-':10} "
                     f"suggest={tip or '-'}" + (f" judge={judge}" if judge else ""))
        lines.append(f"     {f['message'][:200]}")
        lines.append(f"     at {f['page_url']} (worker {f['worker']}, step {f['first_step']}); "
                     f"trail: " + "; ".join(f"{t['do']} {t.get('el') or t.get('value') or ''}"[:60] for t in f["trail"]))
        if f.get("judge"):
            lines.append(f"     judge: {f['judge'].get('reason', '')[:200]}")
        if run_id not in labels or f["sig"] not in labels.get(run_id, {}):
            note = f"suggest: {tip or '-'} | {f.get('status', 'candidate')}" + (f" | judge {judge}" if judge else "")
            new_entries.append(f"[{json.dumps(run_id)}.{json.dumps(f['sig'])}]\nlabel = \"\"  # {note}\n")
    if write and new_entries:
        header = "" if LABELS.exists() else (
            "# Finding labels (ground truth for precision and semantic-fault recall). See src/webtester/labels.py.\n"
            "# label = seeded fault id (F01..), U1-U7 (known upstream defect, apps/realworld/README.md), \"new: <what>\" or \"fp\".\n\n")
        with LABELS.open("a", encoding="utf-8") as fh:
            fh.write(header + "\n".join(new_entries) + "\n")
        lines += ["", f"appended {len(new_entries)} blank label(s) to {LABELS.relative_to(REPO_ROOT)}"]
    return "\n".join(lines)
