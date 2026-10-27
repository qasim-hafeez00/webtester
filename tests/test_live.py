"""Live integration tests against the running Conduit stack (apps/realworld).

Run with:  python -m pytest -m live
Skipped automatically when the app is not up.
"""

import json
import urllib.request

import pytest

from webtester import runner
from webtester.config import REPO_ROOT, load_config
from webtester.llm import Usage
from webtester.trace import read_trace

CFG = load_config(REPO_ROOT / "configs" / "realworld.toml")


def _app_up() -> bool:
    try:
        with urllib.request.urlopen(CFG.app.base_url + CFG.app.health_path, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


pytestmark = [pytest.mark.live, pytest.mark.skipif(not _app_up(), reason="Conduit not running")]


class ScriptedLLM:
    """Stands in for LLMClient: logs in through the real UI using the element list."""

    def __init__(self, cfg):
        self.usage = Usage()
        self.calls = 0

    async def complete_json(self, system, user):
        self.calls += 1
        lines = user.splitlines()

        def find(fragment):
            for ln in lines:
                if ln.startswith("[") and fragment in ln:
                    return ln[1:ln.index("]")]
            return None

        if "/login" not in user.split("CURRENT PAGE:")[1].splitlines()[0]:
            sign_in = find('"Sign in"')
            data = {"thought": "go to login", "actions": [{"do": "click", "id": sign_in}]} if sign_in \
                else {"thought": "home", "actions": [{"do": "navigate", "value": "/"}]}
        else:
            data = {"thought": "log in", "actions": [
                {"do": "fill", "id": find('label="Email"'), "value": "worker01@conduit.test"},
                {"do": "fill", "id": find('label="Password"'), "value": "conduit-test-pw"},
                {"do": "click", "id": find('button "Sign in"')},
            ]}
        u = Usage(prompt_tokens=len(user) // 4, completion_tokens=40, calls=1)
        self.usage.add(u)
        return data, u

    def cost_usd(self, usage=None):
        return 0.0


def test_b1_loop_with_scripted_llm(monkeypatch):
    monkeypatch.setattr(runner, "LLMClient", ScriptedLLM)
    cfg = CFG.with_overrides(budget_max_steps=4, out_dir="runs/_test")
    out = runner.run_sync(cfg, "b1", workers=1, reset=True, label="pytest")
    events = read_trace(out / "trace.jsonl")
    steps = [e for e in events if e["type"] == "step"]
    assert len(steps) == 4
    assert any(a["do"] == "fill" for s in steps for a in s["actions"])
    # After logging in, the nav bar shows the worker's profile link.
    assert any("/profile/worker01" in (s.get("actions") or [{}])[0].get("url_after", "") or "worker01" in s["thought"]
               for s in steps) or any(s["route"] == "/" and s["n_elements"] > 40 for s in steps[2:])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["tokens_total"] > 0 and summary["llm_calls"] == 4


def test_two_independent_random_workers_share_budget():
    cfg = CFG.with_overrides(budget_max_steps=10, out_dir="runs/_test")
    out = runner.run_sync(cfg, "random", workers=2, reset=True, label="pytest")
    steps = [e for e in read_trace(out / "trace.jsonl") if e["type"] == "step"]
    assert len(steps) in (10, 11)  # both workers draw from one budget
    assert {s["worker"] for s in steps} == {1, 2}


class FocusFollowingLLM(ScriptedLLM):
    """Goes to its focus area, then clicks the first unmarked element there."""

    async def complete_json(self, system, user):
        import re

        self.calls += 1
        current = user.split("CURRENT PAGE: ")[1].split()[0]
        m = re.search(r"YOUR FOCUS AREA: (\S+) \(navigate to (\S+)\)", user)
        if m and m.group(1) != current:
            data = {"thought": f"go to focus {m.group(1)}", "actions": [{"do": "navigate", "value": m.group(2)}]}
        else:
            ids = [ln[1:ln.index("]")] for ln in user.split("Interactive elements:")[1].splitlines()
                   if ln.startswith("[") and not ln.rstrip().endswith("]") and "disabled" not in ln]
            data = {"thought": "explore focus", "actions": [{"do": "click", "id": ids[0]}] if ids
                    else [{"do": "back"}]}
        u = Usage(prompt_tokens=len(user) // 4, completion_tokens=40, calls=1)
        self.usage.add(u)
        return data, u


def test_b3v2_assigns_focus_areas_live(monkeypatch):
    monkeypatch.setattr(runner, "LLMClient", FocusFollowingLLM)
    cfg = CFG.with_overrides(budget_max_steps=40, out_dir="runs/_test")
    out = runner.run_sync(cfg, "b3v2", workers=4, reset=True, label="pytest")
    events = read_trace(out / "trace.jsonl")
    steps = [e for e in events if e["type"] == "step"]
    assert len(steps) >= 40
    focus = {}
    for s in steps[8:]:
        if s.get("suggestion"):
            focus.setdefault(s["worker"], set()).add(s["suggestion"].split()[0])
    assert len(focus) >= 3  # most workers got a focus area
    assert len(set().union(*focus.values())) >= 3  # and not all the same one
    fr = next(e for e in events if e["type"] == "frontier")
    assert fr["version"] == 2 and fr["global_elements"] > 0


class OracleScriptedLLM(ScriptedLLM):
    """Logs in, then navigates home with one check that must fail and one that must hold;
    answers the gate's judge prompt too."""

    async def complete_json(self, system, user):
        from webtester.gate import JUDGE_SYSTEM

        if system == JUDGE_SYSTEM:
            u = Usage(prompt_tokens=50, completion_tokens=10, calls=1)
            self.usage.add(u)
            return {"verdict": "wrong_expectation", "reason": "scripted"}, u
        data, u = await super().complete_json(system, user)
        if "Your Feed" in user or "/profile/worker01" in user:  # logged in: nav bar shows the profile link
            data = {"thought": "check home", "actions": [{"do": "navigate", "value": "/"}],
                    # v4 grounding (D49) keeps only checks on typed or seen text, so the failing
                    # check is a grounded one that a correct page contradicts
                    "expect": [{"check": "not_shows", "text": "conduit"},
                               {"check": "shows", "text": "conduit", "where": "reload"}]}
        return data, u


def test_b4_checks_gate_and_judge_live(monkeypatch):
    from webtester.gate import GateConfig

    monkeypatch.setattr(runner, "LLMClient", OracleScriptedLLM)
    cfg = CFG.with_overrides(budget_max_steps=5, out_dir="runs/_test")
    out = runner.run_sync(cfg, "b4", workers=1, reset=True, label="pytest",
                          gate_cfg=GateConfig(k=2, windows=(1,), max_minutes=5))
    events = read_trace(out / "trace.jsonl")
    checks = [c for e in events if e["type"] == "step" for c in e.get("checks", [])]
    assert any(c["check"] == "not_shows" and c["text"] == "conduit" and c["status"] == "violated" for c in checks)
    assert any(c["text"] == "conduit" and c["status"] == "pass" for c in checks)
    findings = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    oracle = [f for f in findings if f["kind"] == "oracle_violation"]
    assert len(oracle) == 1 and oracle[0]["status"] == "confirmed"  # deterministic, so 2/2 replays
    assert oracle[0]["judge"]["verdict"] == "wrong_expectation"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["health"]["gate_ok"] and summary["gate"]["confirmed"] >= 1
