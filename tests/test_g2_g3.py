"""Offline tests for the Phase 2 components: inferred oracles (G3), the evidence
gate (G2), the B4 conditions, labels and the G2/G3 metrics. No browser, no network."""

import asyncio
import json

from webtester.browser import Element, Observation
from webtester.config import Account
from webtester.inferred import (annotate, eval_changes, eval_count, eval_route, eval_text, oracle_signature,
                                sanitize_expectations, violation_signal, CheckResult)
from webtester.oracles import FindingStore, signature


def _obs(url, *els, text=""):
    return Observation(url=url, title="t", elements=list(els), skeleton="body", text=text)


# ---------- G3: inferred oracles ----------
def test_sanitize_expectations_normalises_aliases_and_drops_bad_checks():
    raw = [{"check": "contains", "text": "My Title"},  # alias, default where
           {"check": "absent", "text": "x"},  # text too short
           {"check": "counter", "id": "[7]"},  # default delta
           {"check": "route", "route": "register"},  # not a path
           {"check": "explode"}]
    assert sanitize_expectations(raw) == [{"check": "shows", "text": "My Title", "where": "now"},
                                          {"check": "count", "id": "7", "delta": 1}]
    assert sanitize_expectations({"check": "gone", "text": "hello", "where": "after_reload"}) == \
        [{"check": "not_shows", "text": "hello", "where": "reload"}]
    assert len(sanitize_expectations([{"check": "changes"}] * 5)) == 2  # at most 2 per step
    assert sanitize_expectations([{"check": "shows", "text": "abc", "where": "settings"}]) == []
    assert sanitize_expectations("junk") == [] and sanitize_expectations(None) == []


def test_pure_check_evaluation():
    assert eval_text("shows", "My  Title", "Home\nmy title  here")[0]
    assert not eval_text("shows", "Missing", "Home")[0]
    held, ev = eval_text("not_shows", "deleted comment", "x Deleted   Comment y")
    assert not held and "deleted comment" in ev
    assert eval_count(3, 4, 1)[0] == "pass" and eval_count(3, 3, 1)[0] == "violated"
    assert eval_count(None, 4, 1)[0] == "inconclusive"
    assert eval_route("/register", "http://h/register")[0]
    assert eval_route("/article/*", "http://h/article/my-post-12")[0]
    assert not eval_route("/register", "http://h/")[0]
    assert not eval_changes("http://h/", "Page 1 items", "http://h/", "page 1   items")[0]  # no-op UI
    assert eval_changes("http://h/", "a", "http://h/?page=2", "a")[0]


def test_violation_signature_is_stable_and_deduplicated():
    exp = {"check": "not_shows", "text": "Comment 42 here", "where": "reload"}
    s1 = violation_signal(exp, CheckResult("violated", "found"), "http://h/article/a-1")
    s2 = violation_signal({**exp, "text": "Comment 7 here"}, CheckResult("violated", "found"), "http://h/article/b-2")
    assert signature(s1) == s1.detail["sig"] == signature(s2)  # numbers and slugs abstracted
    assert signature(s1).startswith("oracle_violation|not_shows|/article/*|reload|")
    store = FindingStore()
    new = store.ingest([s1, s2], step=3, worker=2, state="s", trail=[])
    assert len(new) == 1 and new[0].kind == "oracle_violation" and new[0].detail["expect"] == exp
    assert oracle_signature({"check": "shows", "text": "x y", "where": "/profile/worker01"}, "http://h/") == \
        "oracle_violation|shows|/|/profile/*|x y"


def test_annotate_count_check_records_element_identity():
    hearts = [Element(id=str(i), tag="button", text="12") for i in (1, 2)]
    obs = _obs("http://h/", *hearts)
    exp = annotate({"check": "count", "id": "2", "delta": 1}, obs)
    assert exp["_ekey"] == hearts[1].key() and exp["_nth"] == 1 and exp["_label"] == ""
    assert annotate({"check": "changes"}, obs) == {"check": "changes"}


# ---------- B4 prompt and parsing ----------
class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.system = None

    async def complete_json(self, system, user):
        from webtester.llm import Usage

        self.system = system
        return self.reply, Usage(prompt_tokens=10, completion_tokens=5, calls=1)


def test_only_b4_policies_see_the_oracle_prompt_and_return_checks():
    from webtester.policies import LLMPolicy, Memory, ORACLE_PROMPT, SYSTEM_PROMPT

    reply = {"thought": "t", "actions": [{"do": "click", "id": "1"}],
             "expect": [{"check": "shows", "text": "Saved", "where": "reload"}]}
    obs = _obs("http://h/", Element(id="1", tag="button", text="Save"))
    plain, b4 = _FakeLLM(reply), _FakeLLM(reply)
    d_plain = asyncio.run(LLMPolicy(plain, Account("u", "e", "p"), 10).decide(obs, Memory(), 1))
    d_b4 = asyncio.run(LLMPolicy(b4, Account("u", "e", "p"), 10, inferred=True).decide(obs, Memory(), 1))
    assert plain.system == SYSTEM_PROMPT and d_plain.expect == []  # B1/B2/B3 unchanged
    assert b4.system == SYSTEM_PROMPT + ORACLE_PROMPT
    assert d_b4.expect == [{"check": "shows", "text": "Saved", "where": "reload"}]


def test_condition_table_keeps_g1_conditions_and_defines_b4_family():
    from webtester.frontier import Frontier, FrontierV2
    from webtester.runner import AGENTS, FRONTIERS, GATED, INFERRED, LLM_AGENTS

    assert FRONTIERS["b3"] == (Frontier, True) and FRONTIERS["b3local"] == (Frontier, False)
    assert FRONTIERS["b3v2"] == (FrontierV2, True) and FRONTIERS["b3v2local"] == (FrontierV2, False)
    assert "b1" not in FRONTIERS and "b4nog1" not in FRONTIERS  # no frontier: B2 and A-G1
    assert FRONTIERS["b4"] == FRONTIERS["b4nog3"] == (FrontierV2, True)
    assert INFERRED == {"b4", "b4nog1"} and GATED == {"b4", "b4nog1", "b4nog3"}
    assert set(GATED) <= set(LLM_AGENTS) <= set(AGENTS)


# ---------- G2: evidence gate ----------
def test_gate_labels_windows_and_locate():
    from webtester.gate import label, locate, windows_for
    from webtester.worker import StepRecord

    assert label(3, 3, True) == "confirmed" and label(1, 3, True) == "flaky"
    assert label(0, 3, True) == "rejected" and label(0, 3, False) == "unverified"
    log = [StepRecord(s, f"http://h/{s}", {}, [], []) for s in (2, 5, 9, 11)]
    assert [[r.step for r in w] for w in windows_for(log, 9, (1, 4))] == [[9], [2, 5, 9]]
    assert [[r.step for r in w] for w in windows_for(log, 2, (1, 4))] == [[2]]  # clipped duplicates dropped
    assert windows_for(log, 7, (1, 4)) == []
    a, b = Element(id="4", tag="button", text="Delete"), Element(id="9", tag="button", text="Delete")
    obs = _obs("http://h/", a, b)
    assert locate(obs, a.key(), 1) is b and locate(obs, a.key(), 5) is a and locate(obs, "nope", 0) is None


def _gate_ctx(tmp_path, findings):
    from webtester.budget import Budget
    from webtester.config import BudgetConfig
    from webtester.trace import Trace
    from webtester.worker import RunContext, StepRecord

    ctx = RunContext(Budget(BudgetConfig()), Trace(tmp_path / "trace.jsonl", "r"), FindingStore(), record_replay=True)
    ctx.replay_log[1] = [StepRecord(s, "http://h/", {}, [], []) for s in range(1, 8)]
    for sig, kind, step in findings:
        from webtester.browser import Signal

        detail = {"sig": sig, "expect": {"check": "changes"}, "evidence": "same"} if kind == "oracle_violation" else {}
        ctx.findings.ingest([Signal(kind, sig, "http://h/", detail)], step=step, worker=1, state="s", trail=[])
    return ctx


def test_gate_minimises_then_confirms_and_judges(tmp_path, monkeypatch):
    from webtester import gate

    outcomes = {  # finding message -> reproduced per replay, in call order
        "A": [False, True, True, True],  # needs the 4-step window, then 2 more hits -> confirmed
        "B": [True, False, True],  # 1-step window, then 1 of 2 more -> flaky
        "C": [False, False],  # never -> rejected
    }

    async def fake_replay(browser, cfg, ctl, window, finding):
        return {"reproduced": outcomes[finding.message].pop(0), "missing": 0, "seconds": 0.1, "_n": len(window)}

    monkeypatch.setattr(gate, "replay", fake_replay)
    ctx = _gate_ctx(tmp_path, [("A", "http_5xx", 6), ("oracle_violation|changes|/|now|", "oracle_violation", 5),
                               ("C", "console_error", 7)])
    # the oracle finding's message is its sig; map it to scenario B
    outcomes["oracle_violation|changes|/|now|"] = outcomes.pop("B")
    judge = _FakeLLM({"verdict": "wrong_expectation", "reason": "a no-op is fine here"})
    out = asyncio.run(gate.run_gate(None, None, ctx, None, judge, gate.GateConfig(k=3, windows=(1, 4))))
    by = {f.message: f for f in ctx.findings.all()}
    assert by["A"].status == "confirmed" and by["A"].gate["minimal_steps"] == 4 and by["A"].gate["reproduced"] == 3
    assert by["oracle_violation|changes|/|now|"].status == "flaky"
    assert by["oracle_violation|changes|/|now|"].judge["verdict"] == "wrong_expectation"
    assert by["C"].status == "rejected" and by["A"].judge is None  # implicit findings are not judged
    assert out["confirmed"] == out["flaky"] == out["rejected"] == 1 and out["replays"] == 4 + 3 + 2
    assert out["judge_calls"] == 1


def test_gate_time_cap_leaves_findings_unverified(tmp_path, monkeypatch):
    from webtester import gate

    async def never(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("replayed after the deadline")

    monkeypatch.setattr(gate, "replay", never)
    ctx = _gate_ctx(tmp_path, [("A", "http_5xx", 3)])
    out = asyncio.run(gate.run_gate(None, None, ctx, None, None, gate.GateConfig(max_minutes=-1)))
    assert ctx.findings.all()[0].status == "unverified" and out["unverified"] == 1


# ---------- metrics, labels, stats ----------
def _write_trace(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _step(i, t, checks=None):
    s = {"t": t, "type": "step", "worker": 1, "step": i, "state": f"s{i}", "route": "/", "actions": [],
         "usage": {"prompt_tokens": 100, "completion_tokens": 10, "calls": 1, "retries": 0}, "seconds": 1}
    if checks:
        s["checks"] = checks
    return s


def test_summarize_reports_checks_gate_and_gate_health(tmp_path):
    from webtester.metrics import summarize

    base = [{"t": 0, "type": "run_start", "run_id": "r", "agent": "b4", "workers": 1, "faults": [],
             "gate": {"k": 3}},
            _step(1, 1, [{"check": "shows", "status": "pass"}, {"check": "count", "status": "violated"}]),
            _step(2, 2, [{"check": "changes", "status": "skipped"}])]
    end = [{"t": 3, "type": "run_end", "reasons": ["w1:max_tokens"]}]
    gate = [{"t": 2.5, "type": "gate_result", "sig": "x", "status": "confirmed"},
            {"t": 2.6, "type": "gate_result", "sig": "y", "status": "rejected"},
            {"t": 2.7, "type": "gate_judge", "sig": "x", "verdict": "bug"},
            {"t": 2.8, "type": "gate_done", "candidates": 2, "confirmed": 1, "rejected": 1, "judge_tokens": 50}]
    _write_trace(tmp_path / "a.jsonl", base + gate + end)
    s = summarize(tmp_path / "a.jsonl")
    assert s["health"]["ok"] and s["health"]["gate_ok"]
    assert s["checks"] == {"proposed": 3, "pass": 1, "violated": 1, "inconclusive": 0, "skipped": 1}
    assert s["findings_confirmed"] == 1 and s["gate"]["judge_tokens"] == 50 and s["judge_verdicts"] == {"bug": 1}
    _write_trace(tmp_path / "b.jsonl", base + end)  # gate expected but never finished
    assert not summarize(tmp_path / "b.jsonl")["health"]["ok"]
    _write_trace(tmp_path / "c.jsonl", [base[0] | {"gate": None}] + base[1:] + end)  # no gate: unchanged keys
    s = summarize(tmp_path / "c.jsonl")
    assert s["health"]["ok"] and "gate_ok" not in s["health"] and "gate" not in s


def test_label_metrics_precision_and_semantic_recall():
    from webtester.labels import label_metrics

    findings = [
        {"sig": "http_5xx|POST /api/articles/*/comments|500", "kind": "http_5xx", "status": "confirmed"},
        {"sig": "oracle_violation|not_shows|/article/*|reload|c", "kind": "oracle_violation", "status": "confirmed",
         "judge": {"verdict": "bug"}},
        {"sig": "oracle_violation|shows|/|now|z", "kind": "oracle_violation", "status": "confirmed",
         "judge": {"verdict": "wrong_expectation"}},
        {"sig": "oracle_violation|changes|/|now|", "kind": "oracle_violation", "status": "rejected"},
    ]
    summary = {"faults": ["F01", "F06", "F09"],
               "fault_detection": {"F01": {"detected": True}, "F06": {"detected": False}},
               "fault_detection_confirmed": {"F01": {"detected": True}}}
    labels = {"r": {findings[0]["sig"]: {"label": "F01"}, findings[1]["sig"]: {"label": "F06"},
                    findings[2]["sig"]: {"label": "fp"}, findings[3]["sig"]: {"label": "F09"}}}
    m = label_metrics("r", findings, summary, labels)
    assert m["faults_found_all"] == 3 and m["faults_found_confirmed"] == 2  # F09 only in a rejected finding
    assert m["precision_raw"] == 0.75 and abs(m["precision_gated"] - 2 / 3) < 1e-9 and m["precision_judged"] == 1.0
    partial = label_metrics("r", findings, summary, {"r": {findings[0]["sig"]: {"label": "F01"}}})
    assert partial["labels_missing"] == 3 and "precision_raw" not in partial
    assert "faults_found_all" not in label_metrics("x", findings[:1], summary, {})  # no G3 data, no labels


def test_triage_suggestions():
    from webtester.labels import suggest

    catalog = {"F01": {"detect": {"kind": ["http_5xx"], "contains": "/comments"}},
               "F05": {"hint": {"routes": ["/", "/profile/*"], "checks": ["count"]}},
               "F06": {"hint": {"routes": ["/article/*"], "checks": ["not_shows"]}}}
    enabled = ["F01", "F05", "F06"]
    f = {"kind": "http_5xx", "sig": "http_5xx|POST /api/articles/*/comments|500", "page_url": "http://h/", "message": ""}
    assert suggest(f, catalog, enabled) == "F01"
    assert suggest({"kind": "console_error", "sig": "s", "message": "ERROR {}"}, catalog, enabled) == "U5?"
    o = {"kind": "oracle_violation", "sig": "oracle_violation|count|/profile/alice|now|", "message": ""}
    assert suggest(o, catalog, enabled) == "F05?"
    o2 = {"kind": "oracle_violation", "sig": "oracle_violation|route|/settings|now|/", "message": ""}
    assert suggest(o2, catalog, enabled) == "fp?"


def test_compare_shows_g2_g3_rows_only_with_data():
    from webtester.stats import compare

    plain = [{"unique_states": 30 + i, "faults_found": 1, "findings": 2, "steps": 100, "tokens_total": 1000}
             for i in range(3)]
    assert "all oracles" not in compare(plain, plain, "A", "B")
    assert "Precision" not in compare(plain, plain, "A", "B")
    b4 = [dict(r, faults_found_all=3, findings_confirmed=1, precision_raw=0.5) for r in plain]
    table = compare(plain, b4, "B3V2", "B4")
    assert "| Seeded faults found (all oracles, labelled) | 1 [1–1] | 3 [3–3] |" in table  # B3V2 falls back
    assert "Precision" not in table and "gate-confirmed" not in table  # only one side has them
    assert "| Precision, raw candidates | 50% [50%–50%] | 50% [50%–50%] |" in compare(b4, b4, "B4", "A-G1")
