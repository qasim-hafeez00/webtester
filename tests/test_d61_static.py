"""D61: checks that need no app. The injected browser scripts parse; no stray control characters in the sources;
the v4 word lists read from the lexicon compile to the v4 patterns; every family extension maps to a built rule;
every rule the tracker counts as built has code that raises it; G3 from the state graph."""

from __future__ import annotations

import asyncio
import importlib
import json
import pkgutil
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import webtester

ROOT = Path(__file__).resolve().parents[1]


def _scripts():
    for m in pkgutil.iter_modules(webtester.__path__):
        if m.name == "__main__":
            continue
        mod = importlib.import_module(f"webtester.{m.name}")
        for k, v in vars(mod).items():
            if k.endswith("_JS") and isinstance(v, str):
                yield f"{m.name}.{k}", v


def test_every_injected_script_parses(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    seen, bad = set(), []
    for name, src in _scripts():
        if src in seen:  # re-exported constants
            continue
        seen.add(src)
        f = tmp_path / (name.replace(".", "_") + ".js")
        f.write_text("const __f = (" + src.strip().rstrip(";") + ");\n", encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if r.returncode:
            bad.append((name, (r.stderr.strip().splitlines() or [""])[-1]))
    assert len(seen) >= 25  # 31 distinct scripts at D61
    assert not bad, bad


def test_no_control_characters_in_sources():
    # I62: a heredoc turned '\b' into a backspace inside a regex; the pattern then never matched
    bad = []
    for root in ("src", "tests", "scripts"):
        for p in (ROOT / root).rglob("*.py"):
            s = p.read_text(encoding="utf-8")
            if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in s):
                bad.append(str(p.relative_to(ROOT)))
    assert not bad, bad


def test_v4_word_lists_compile_to_the_v4_patterns():
    import webtester.consistency as c
    import webtester.memory as m

    want = json.loads((ROOT / "tests" / "fixtures" / "lexicon_v4_pin.json").read_text(encoding="utf-8"))
    got = {"validation": c._VALIDATION, "system_error": c._SYSTEM_ERR, "personal": m.PERSONAL, "recency": m.RECENCY,
           "event_feed": m.EVENT_FEED}
    for k, rx in got.items():
        assert rx.pattern == want["v4"][k], k
        assert rx.flags == want["flags"][k], k
    assert [[v, rx.pattern] for v, rx in m.VERB_RES] == want["verbs"]
    assert [[v, rx.pattern] for v, rx in m.CATEGORY] == want["categories"]
    add = dict(m.CATEGORY)["add"]
    assert add.search("Your cart") and add.search("My bag") and not add.search("cartography")  # I62


def test_every_extension_maps_to_a_built_rule():
    from webtester.families import EXTENSIONS, built_rules, extension_phrases, families, tally, tracker

    have = built_rules()
    for fid, m in EXTENSIONS.items():
        assert fid in families(), fid
        for phrase, rid in m.items():
            assert rid in have, (fid, phrase, rid)
            assert phrase in extension_phrases(fid), (fid, phrase)  # the registry names phrases the row really has
    for fid, f in families().items():
        if f["status"] in ("spec", "out"):
            continue
        for phrase in extension_phrases(fid):
            assert EXTENSIONS.get(fid, {}).get(phrase), (fid, phrase)
    t = tally(tracker())
    assert t["rules_todo"] == [], t["rules_todo"]
    assert set(t["by_impl"]) <= {"built", "n/a"}, t["by_impl"]


def test_every_built_rule_has_code_that_raises_it():
    """The tracker counts a rule as built when it has a tier; this checks that some code raises it."""
    from webtester.families import _IMPLICIT, built_rules

    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "webtester").glob("*.py"))
    dynamic = {"I-create", "I-edit"}  # Violation(f"I-{e.verb}", ...) in consistency._verify_pending
    dynamic |= {"R33", "R33g"}  # rule = "R33" if money else "R33g" in probes5._double_submit
    missing = [r for r in sorted(built_rules() - set(_IMPLICIT.values()) - dynamic)
               if not re.search(r'Violation\(\s*f?"' + re.escape(r) + r'["|]', src)]
    assert not missing, missing
    assert 'Violation(f"I-{e.verb}"' in src and 'rule = "R33" if money else "R33g"' in src


class _E:
    def __init__(self, dst_pages, do="click", verb=""):
        self.src, self.action, self.label, self.verb, self.nav = "s1", "click|a|Reports", "click Reports", verb, True
        self.dst_pages, self.replay = set(dst_pages), [{"do": do}]


def _sw():
    from webtester.consistency import SweepState, Sweeper

    return Sweeper(SweepState(), 1, None)


def test_g3_one_navigation_two_pages():
    sw = _sw()
    sw.note_edge(_E({"/reports"}))
    assert sw.pending_viol == []
    sw.note_edge(_E({"/reports", "/reports/archive"}))
    assert [v.rule for v in sw.pending_viol] == ["G3"]
    sw.note_edge(_E({"/reports", "/reports/archive"}))
    assert len(sw.pending_viol) == 1  # once per edge
    for e in (_E({"/a", "/b"}, do="back"), _E({"/a", "/login"}), _E({"/a", "/b"}, verb="delete"), None):
        s2 = _sw()
        s2.note_edge(e)
        assert s2.pending_viol == [], e
    s3 = _sw()
    s3.st.v5_rules = False  # the D58 rule set (ablation) has no G3
    s3.note_edge(_E({"/a", "/b"}))
    assert s3.pending_viol == []


def test_g3_from_a_real_graph():
    from webtester.stategraph import StateGraph

    g, sw = StateGraph(), _sw()
    act = [{"do": "click", "ekey": "a|Reports|/reports", "el": '[1] a "Reports"', "value": None}]
    for dst, url in (("s2", "http://h/reports"), ("s3", "http://h/reports/old")):
        g.visit(1, "s1", "http://h/", 1)
        g.visit(1, dst, url, 2)
        sw.note_edge(g.transition(1, "s1", act, dst))
    assert [v.rule for v in sw.pending_viol] == ["G3"], sw.pending_viol


def test_a_probe_that_cannot_finish_is_inconclusive_not_exercised():
    """E2 (D61, I61): a probe that took its slot and then aborted, or raised, was logged as exercised."""
    from types import SimpleNamespace

    from playwright.async_api import Error as PWError

    from webtester.consistency import SweepState, Sweeper

    sw = Sweeper(SweepState(), 1, None)
    sw._session = SimpleNamespace(cfg=SimpleNamespace(mode="controlled"))
    sw.v5_budget, sw.step, sw.route = 1, 3, "/books/*"
    pr = sw.pr
    assert pr._may(sw, "R21b", "/books/*") and "R21b" in sw._armed
    assert pr._abort(sw, "R21b", "no-submit") == []
    sw._settle_checks([])
    rows = [(r["rule"], r["outcome"], r["why"]) for r in sw.st.checks.records()]
    assert rows == [("R21b", "inconclusive", "no-submit")], rows

    sw2 = Sweeper(SweepState(), 1, None)
    sw2.step, sw2.route = 4, "/books/*"

    async def boom(sw_, session, facts, obs, done, ev, step):
        assert sw_.pr._may(sw_, "R49", "/books/*")
        raise PWError("Target closed")

    for name in ("_rollback", "_references"):
        setattr(sw2.pr, name, boom if name == "_references" else (lambda *a: asyncio.sleep(0, [])))
    session = SimpleNamespace(cfg=SimpleNamespace(mode="controlled"), page=None)
    sw2.pr._upload_check = lambda *a: []
    sw2.pr._canvas_check = lambda *a: asyncio.sleep(0, [])
    sw2.pr._storage_model = lambda *a: asyncio.sleep(0, [])
    sw2.pr._note_duplicate = lambda *a: None
    asyncio.run(sw2.pr.after(sw2, session, None, None, [], None, 4))
    sw2._settle_checks([])
    rows = [(r["rule"], r["outcome"], r["why"]) for r in sw2.st.checks.records()]
    assert rows == [("R49", "inconclusive", "error:Error")], rows


# D62: lock entry (v5 plan 12.2 (1)): every built rule has a fixture test, except the login and second-account
# checks, which the development resweep exercises (I59)
RESWEEP_ONLY = {"I-logout", "R24", "R24b", "R28", "R46", "R46w", "R66", "R67"}


def test_every_built_rule_has_a_fixture_test():
    from webtester.families import built_rules

    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "tests").rglob("*.py"))
    named = set(re.findall(r"""["']([A-Za-z][\w-]*)["']""", text)) - RESWEEP_ONLY  # named above, not tested
    assert built_rules() - named <= RESWEEP_ONLY, sorted(built_rules() - named - RESWEEP_ONLY)


def test_family_tracker_is_valid_toml():
    import tomllib

    rows = tomllib.loads((ROOT / "docs/family_tracker.toml").read_text(encoding="utf-8"))["family"]
    assert len(rows) >= 150 and all("impl" in r for r in rows.values())
