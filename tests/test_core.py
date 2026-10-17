"""Offline unit tests (no browser, no network)."""

import json

import pytest

from webtester.browser import Element, Signal
from webtester.config import REPO_ROOT, load_config
from webtester.llm import LLMError, api_key_env_names, is_quota_error, parse_json_object
from webtester.metrics import fault_detection
from webtester.oracles import FindingStore, signature
from webtester.policies import sanitize_actions
from webtester.state import action_key, route_shape, state_id, value_class


def test_route_shape_abstracts_value_segments():
    assert route_shape("http://h/article/why-cache-1") == "/article/*"
    assert route_shape("http://h/editor/abc-12") == "/editor/*"
    assert route_shape("http://h/profile/alice/favorites") == "/profile/alice/favorites"  # documented v0 limit
    assert route_shape("http://h/?tag=css&page=2") == "/?page&tag"
    assert route_shape("http://h/#/article/x-1") == "/#/article/*"


def test_state_id_ignores_text_but_not_structure():
    a = state_id("http://h/article/a-1", "body(div(h1,p))")
    b = state_id("http://h/article/b-2", "body(div(h1,p))")
    c = state_id("http://h/article/b-2", "body(div(h1,p,form(input:text)))")
    assert a == b != c


def test_action_key_buckets_fill_values():
    k1 = action_key("s", "fill", "input|email", "a@b.com")
    k2 = action_key("s", "fill", "input|email", "zz@yy.org")
    k3 = action_key("s", "fill", "input|email", "")
    assert k1 == k2 != k3
    assert value_class("<script>") == "special"
    assert value_class("42") == "number"


def test_parse_json_object_tolerates_fences_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"thought": "x", "actions": []} done') == {"thought": "x", "actions": []}
    assert parse_json_object('{"s": "brace } in string"}') == {"s": "brace } in string"}
    with pytest.raises(LLMError):
        parse_json_object("no json here")


def test_api_key_env_names_discovers_numbered_fallbacks(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "primary")
    monkeypatch.setenv("TEST_API_KEY_1", "fallback-1")
    monkeypatch.setenv("TEST_API_KEY_2", "fallback-2")
    monkeypatch.setenv("TEST_API_KEY_4", "ignored-gap")
    assert api_key_env_names("TEST_API_KEY") == (
        "TEST_API_KEY",
        "TEST_API_KEY_1",
        "TEST_API_KEY_2",
    )


def test_is_quota_error_recognises_rate_limit_and_quota_responses():
    from types import SimpleNamespace

    assert is_quota_error(SimpleNamespace(status_code=429))
    assert is_quota_error(SimpleNamespace(status_code=403, args=("quota exceeded",)))
    assert not is_quota_error(SimpleNamespace(status_code=401, args=("invalid key",)))


def test_sanitize_actions_normalises_and_filters():
    raw = [{"do": "type", "id": "[3]", "value": 5}, {"do": "explode", "id": "1"}, {"action": "goto", "value": "/x"},
           "junk"] + [{"do": "click", "id": str(i)} for i in range(10)]
    out = sanitize_actions(raw)
    assert out[0] == {"do": "fill", "id": "3", "value": "5"}
    assert out[1] == {"do": "navigate", "id": None, "value": "/x"}
    assert len(out) == 6
    short = sanitize_actions([{"fill": "6", "value": "x@y.z"}, {"click": "8"}, {"navigate": "/settings"}])
    assert short == [{"do": "fill", "id": "6", "value": "x@y.z"}, {"do": "click", "id": "8", "value": None},
                     {"do": "navigate", "id": None, "value": "/settings"}]


def test_finding_signatures_dedupe_by_route_and_message():
    s1 = Signal("http_5xx", "", "u", {"method": "POST", "url": "http://h/api/articles/a-1/comments", "status": 500})
    s2 = Signal("http_5xx", "", "u", {"method": "POST", "url": "http://h/api/articles/b-7/comments", "status": 500})
    assert signature(s1) == signature(s2)
    store = FindingStore()
    new = store.ingest([s1, s2, Signal("page_error", "TypeError: x of 12 undefined", "u")], step=1, worker=1,
                       state="s", trail=[])
    assert len(new) == 2 and store.by_sig[signature(s1)].occurrences == 2


def test_fault_detection_matches_catalog_rules():
    catalog = {"F01": {"id": "F01", "class": "crash", "detect": {"kind": "http_5xx", "contains": "/comments"}},
               "F02": {"id": "F02", "class": "data"}}
    findings = [{"kind": "http_5xx", "sig": "http_5xx|POST /api/articles/*/comments|500"}]
    res = fault_detection(findings, ["F01", "F02"], catalog)
    assert res["F01"]["detected"] and not res["F02"]["detected"] and not res["F02"]["implicit_detectable"]


def test_element_key_is_position_independent():
    a = Element(id="3", tag="a", text="Home", href="/")
    b = Element(id="9", tag="a", text="Home", href="/")
    assert a.key() == b.key() and a.describe().startswith("[3] a")


def test_realworld_config_loads():
    cfg = load_config(REPO_ROOT / "configs" / "realworld.toml")
    assert cfg.app.account(3).email == "worker03@conduit.test"
    assert cfg.app.origins() == ("http://127.0.0.1:4100",)
    over = cfg.with_overrides(budget_max_steps=7, llm_model="m", headless=None)
    assert over.budget.max_steps == 7 and over.llm.model == "m" and over.headless == cfg.headless
    json.dumps(cfg.to_dict())  # serialisable for the trace


def test_fault_catalog_is_complete_and_matches_code():
    from webtester.metrics import load_fault_catalog

    root = REPO_ROOT / "apps" / "realworld"
    catalog = load_fault_catalog(root / "faults" / "faults.toml")
    assert sorted(catalog) == [f"F{i:02d}" for i in range(1, 11)]
    assert {f["class"] for f in catalog.values()} <= {"crash", "validation", "data", "authorization", "noop-ui"}
    code = "".join(p.read_text(encoding="utf-8") for p in root.rglob("*.ts")
                   if "node_modules" not in p.parts and "dist" not in p.parts)
    for fid in catalog:
        assert f"[FAULT {fid}]" in code, f"{fid} has no code site"
        assert f"fault('{fid}')" in code or f'fault("{fid}")' in code


def test_stats_mann_whitney_and_a12():
    from webtester.stats import a12, mann_whitney_p, quartiles

    x, y = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]
    assert a12(y, x) == 1.0 and a12(x, x) == 0.5
    assert abs(mann_whitney_p(x, y) - 2 / 252) < 1e-12  # exact: only the two extreme splits
    assert mann_whitney_p([1, 2, 3], [1, 2, 3]) == 1.0
    assert quartiles([1, 2, 3, 4, 5]) == (2, 3, 4)


def _obs(url, *els):
    from webtester.browser import Observation
    return Observation(url=url, title="t", elements=list(els), skeleton="body", text="")


def test_frontier_marks_claims_and_suggests():
    from webtester.frontier import Frontier

    a, b, c = (Element(id=str(i), tag="button", text=t) for i, t in enumerate(["A", "B", "C"], 1))
    f = Frontier(shared=True)
    f.visit(1, "home", _obs("http://h/", a, b, c))
    f.visit(2, "home", _obs("http://h/", a, b, c))
    f.claim(1, "home", [a.key()])
    assert f.mark(2, "home", a) == "[taken]" and f.mark(1, "home", a) == ""  # own claim is not "taken"
    f.record(1, "home", a.key())
    assert f.mark(2, "home", a) == "[done x1]"
    # an exhausted state sends the worker to the state with most untouched elements
    d = [Element(id=str(i), tag="a", text=f"L{i}", href=f"/p{i}") for i in range(5)]
    f.visit(1, "list", _obs("http://h/list?page=2", *d))
    for el in (a, b, c):
        f.record(1, "home", el.key())
    tip = f.suggest(2, "home")
    assert tip and "/list?page=2" in tip
    assert f.suggest(3, "home") is None  # worker 2 is already heading there


def test_b1_prompt_unchanged_without_frontier():
    from webtester.config import Account
    from webtester.policies import Memory, build_user_prompt

    p = build_user_prompt(_obs("http://h/", Element(id="1", tag="a", text="Home", href="/")), Memory(),
                          Account("u", "e@x", "pw"), 3, 100000)
    assert p.startswith("Step 3 of at most 100000.\nTest account:")
    assert "COORDINATION" not in p and "Distinct page states you have seen: 0" in p and "[1] a" in p


def test_frontier_v2_ignores_nav_and_assigns_distinct_focus_areas():
    from webtester.frontier import FrontierV2

    nav = [Element(id=f"n{i}", tag="a", text=t, href=h) for i, (t, h) in
           enumerate([("Home", "/"), ("Settings", "/settings"), ("New", "/editor")])]
    f = FrontierV2(shared=True, rotate_steps=3)
    pages = {"home": "http://h/", "set": "http://h/settings", "ed": "http://h/editor", "art": "http://h/article/a-1"}
    for sid, url in pages.items():
        own = [Element(id=f"{sid}{i}", tag="button", text=f"{sid}-{i}") for i in range(4)]
        f.visit(1, sid, _obs(url, *nav, *own))
    assert all(f.is_global(e.key()) for e in nav)
    assert f.untouched(1, "home") == 4  # nav links are not counted as work
    a1, a2 = f.focus(1, "home"), f.focus(2, "home")
    assert a1 and a2 and a1[0] != a2[0]  # workers own different areas
    assert any(a1[0] in o for o in f.others_focus(2))
    # after rotate_steps the worker moves to another area
    for _ in range(3):
        last = f.focus(1, "home")
    assert last[0] != a1[0]


def test_frontier_v2_marks_input_classes_tried():
    from webtester.frontier import FrontierV2

    field = Element(id="1", tag="input", type="text", label="Title")
    f = FrontierV2(shared=True)
    f.visit(1, "ed", _obs("http://h/editor", field))
    assert f.mark(2, "ed", field) == ""
    f.record(1, "ed", field.key(), do="fill", value="hello")
    f.record(1, "ed", field.key(), do="fill", value="")
    assert f.mark(2, "ed", field) == "[tried: empty, text]"


def test_b3v2_prompt_has_focus_area():
    from webtester.config import Account
    from webtester.frontier import FrontierV2
    from webtester.policies import Memory, build_user_prompt

    f = FrontierV2(shared=True)
    obs = _obs("http://h/", Element(id="1", tag="a", text="Settings", href="/settings"))
    f.visit(1, "home", obs)
    focus = f.focus(1, "home")
    p = build_user_prompt(obs, Memory(), Account("u", "e@x", "pw"), 1, 10, f, 1, "home", f"{focus[0]} {focus[1]}")
    assert "YOUR FOCUS AREA: /settings" in p and "Linked routes nobody has visited yet: /settings" in p


def test_frontier_v2_merges_sibling_routes_into_one_area():
    from webtester.frontier import FrontierV2

    links = [Element(id=str(i), tag="a", text=n, href=f"/profile/{n}") for i, n in enumerate(["ann", "bob", "cy"])]
    top = [Element(id=f"t{i}", tag="a", text=n, href=f"/{n}") for i, n in enumerate(["settings", "editor", "login"])]
    f = FrontierV2(shared=True)
    f.visit(1, "home", _obs("http://h/", *links, *top))
    assert f.area("/profile/bob") == "/profile/*"
    assert f.area("/settings") == "/settings"  # top-level routes are never merged
    assert f.area("/profile/ann/favorites") == "/profile/*"  # sub-pages join the merged area
    assert f.unvisited_routes() == ["/editor", "/login", "/profile/*", "/settings"]
    areas = {f.focus(w, "home")[0] for w in (1, 2, 3, 4)}
    assert len(areas) == 4 and "/profile/*" in areas
