"""D61: the API contract rule (openapi.py), the list annotator (annotate.py), the reach helpers (reach.py) and the
evaluation blocks added for the paper's metric groups (evaluate.py), each on small hand-made inputs."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from webtester.annotate import Annotator, to_lists
from webtester.evaluate import (RunData, _auc, across_apps, cost_block, detector_vs_e2e, efficiency_block,
                                engine_agreement, generalization_block, guard_loss, load_catalog, profile_accuracy,
                                recall_block, report_quality_block, rule_recall, safety_block, scaling_block)
from webtester.memory import item_key
from webtester.openapi import Spec, rule_contract
from webtester.reach import feed_items, field_kind, page_words, profile_value, run_suffix, sequence_goals

DOC = {"openapi": "3.0.0", "servers": [{"url": "http://h/api"}],
       "paths": {"/articles/{slug}": {"get": {"responses": {"200": {"content": {"application/json": {
           "schema": {"$ref": "#/components/schemas/Article"}}}}}}},
                 "/odd": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"oneOf": [
                     {"type": "string"}, {"type": "integer"}]}}}}}}}},
       "components": {"schemas": {"Article": {"type": "object", "required": ["title"], "properties": {
           "title": {"type": "string"}, "status": {"type": "string", "enum": ["draft", "published"]},
           "count": {"type": "integer"}, "tags": {"type": "array", "items": {"type": "string"}},
           "note": {"type": "string", "nullable": True}}}}}}


def _net(body, path="/api/articles/abc", status=200, method="GET"):
    return [{"method": method, "path": path, "status": status, "body": body}]


def test_r57e_contract_issues():
    spec = Spec(DOC)
    ok = {"title": "A", "status": "draft", "count": 3, "tags": ["x"], "note": None}
    assert rule_contract(_net(ok), spec) == []
    for bad, word in (({"title": 5}, "declared string"), ({"status": "draft"}, "required"),
                      ({"title": "A", "status": "deleted"}, "not one of"), ({"title": "A", "count": True}, "declared integer"),
                      ({"title": "A", "tags": ["x", 2]}, "tags[1]")):
        out = rule_contract(_net(bad), spec)
        assert [v.rule for v in out] == ["R57e"] and word in out[0].message, (bad, out)


def test_r57e_scope_and_coverage():
    spec = Spec(DOC)
    called = set()
    assert rule_contract(_net({"title": 5}, status=404), spec, called) == []  # only 2xx bodies are checked
    assert called == {"GET /articles/{slug}"}  # but the operation counts as called
    assert rule_contract(_net({"title": 5}, path="/api/articles/abc/comments"), spec) == []  # another operation
    assert rule_contract(_net({"title": 5}, method="POST"), spec) == []
    assert rule_contract(_net([1], path="/api/odd"), spec) == []  # oneOf: skipped, never guessed
    assert rule_contract(_net({"title": 5}), None) == []


def test_annotator_lists_and_cache(tmp_path):
    lists = to_lists({"lists": [{"heading": "Products", "items": [{"name": "Lamp", "price": "$5"}, {"name": " "}, "x"]},
                                {"heading": "Empty", "items": []}]})
    assert lists == [{"heading": "Products", "items": [{"name": "Lamp", "text": "Lamp $5", "abs": None, "href": None}],
                      "nav": False, "annotated": True}]
    assert to_lists(None) == [] and to_lists({"lists": "nope"}) == []

    class _U:
        total = 40

    class _LLM:
        calls = 0

        async def complete_json(self, system, user):
            _LLM.calls += 1
            return {"lists": [{"heading": "H", "items": [{"name": "Row one"}]}]}, _U()

    a = Annotator(_LLM())
    got = asyncio.run(a.lists_for("/x|H", "page text"))
    again = asyncio.run(a.lists_for("/x|H", "page text"))
    assert got == again and got[0]["items"][0]["name"] == "Row one" and _LLM.calls == 1 and (a.calls, a.tokens) == (1, 40)
    a.save(tmp_path / "annotations.json")
    replay = Annotator(None, Annotator.load(tmp_path / "annotations.json"))  # the gate: cache only, no LLM
    assert asyncio.run(replay.lists_for("/x|H", "")) == got and asyncio.run(replay.lists_for("/y|H", "")) == []
    assert replay.calls == 0

    class _Broken:
        async def complete_json(self, system, user):
            raise RuntimeError("down")

    b = Annotator(_Broken())
    assert asyncio.run(b.lists_for("/z|H", "t")) == [] and b.calls == 1


def test_reach_helpers():
    rss = ("<rss><channel><item><title><![CDATA[Fish &amp; Chips]]></title><link>http://h/a/1</link></item>"
           "<item><title>Second</title><link>http://h/a/2</link></item></channel></rss>")
    assert feed_items(rss) == [("Fish & Chips", "http://h/a/1"), ("Second", "http://h/a/2")]
    atom = '<feed><entry><title>Atom one</title><link href="http://h/b/1"/></entry></feed>'
    assert feed_items(atom) == [("Atom one", "http://h/b/1")]
    assert page_words("<p>Hello&nbsp;<b>World</b></p><script>var x = 'hidden'</script>") == "hello world"
    assert run_suffix(1, 1) == run_suffix(1, 1) != run_suffix(1, 2) and len(run_suffix(3)) == 4
    assert [field_kind({"type": t}, "") for t in ("email", "tel", "datetime-local", "")] == ["email", "phone", "date", "text"]
    assert field_kind({}, "Your website") == "url" and field_kind({}, "Mobile number") == "number"


def test_profile_values_follow_the_page():
    assert profile_value({"type": "email"}, "Email", "Bob Smith", "ab12") == "ab12.bobsmith@example.test"
    assert profile_value({"type": "number", "min": 5, "max": 9, "step": None}, "Qty", "", "t") == "5"
    assert profile_value({"type": "number", "min": None, "max": 0, "step": None}, "Qty", "", "t") == "0"
    assert profile_value({"type": "number", "min": 0.5, "max": None, "step": "0.5"}, "Weight", "", "t") == "0.5"
    v = profile_value({"minlength": 12}, "Title", "Hi", "zz")
    assert len(v) == 12 and v.startswith("Hi zz")
    assert profile_value({"maxlength": 6}, "Code", "Longvalue", "zz") == "Longva"
    assert profile_value({}, "Name", "Atlas", "q1", hint="Name has already been taken") == "Atlas q1"
    assert profile_value({}, "Name", "", "q1", hint="must be at least 10 characters") == "Item q1 ab"


def test_sequence_goals_need_item_pages():
    class G:
        def __init__(self, pages):
            self.pages = dict.fromkeys(pages)

    assert sequence_goals(None) == [] and sequence_goals(G(["/", "/about"])) == []
    two = sequence_goals(G(["/books/*"]))
    assert [x.split(":")[0] for x in two] == ["DB9", "DB12"]
    assert [x.split(":")[0] for x in sequence_goals(G(["/books/*/pages/*"]), n=3)] == ["DB9", "HI3", "DB12"]


def test_item_key_with_and_without_a_link():
    assert item_key({"abs": "http://h/books/7", "name": "Atlas"}, "http://h/books") == "/books/7"
    k = item_key({"abs": None, "name": "Atlas  Book"}, "http://h/shelves/3", "On the shelf")
    assert k == item_key({"name": "atlas book"}, "http://h/shelves/9", "On the shelf")  # same route shape, heading, name
    assert k != item_key({"name": "atlas book"}, "http://h/shelves/9", "Wishlist")


# ---------------------------------------------------------------------------- evaluation blocks
def R(rid="r1", app="realworld", cond="b4", clean=False, findings=(), labels=None, enabled=("F01",), **kw):
    return RunData(rid, app, cond, clean, list(findings), labels or {}, set() if clean else set(enabled), **kw)


def S(step, t, new=True, back=False, tokens=10, state=None, worker=1, route="/"):
    return {"worker": worker, "step": step, "t": t, "state": state or f"s{step}", "new": new, "route": route,
            "tokens": tokens, "dup": False, "failed": False, "back": back}


def test_auc_of_step_curves():
    assert _auc([]) is None
    assert _auc([(0.5, 1.0)]) == 0.5  # found everything half way through
    assert _auc([(0.0, 0.5), (0.5, 1.0)]) == 0.75


def test_efficiency_dead_ends_revisits_and_curves():
    steps = [S(1, 10), S(2, 20), S(3, 30, new=False, back=True), S(4, 40)]
    f = {"sig": "x", "kind": "http_5xx", "worker": 1, "first_step": 2}
    r = R(findings=[f], labels={"x": "F01"}, steps=steps, events={"sweep": [{"session_losses": 2}]})
    row = efficiency_block([r], load_catalog())["per_run"][0]
    assert row["dead_end_rate"] == 0.25 and row["revisit_rate"] == 0.25 and row["session_losses"] == 2
    assert row["recall_auc"]["steps"] == 0.5  # the one enabled fault found at step 2 of 4
    assert row["recall_auc"]["minutes"] == 0.5 and row["recall_auc"]["tokens"] == 0.5
    assert row["state_plateau_at"] == 1.0  # 3 new states: 95% of them are known only once the third arrived (t=40 of 40)
    trav = R(steps=steps[:2] + [S(3, 30)], events={"travel": [{"worker": 1, "step": 1}]})
    assert efficiency_block([trav], {})["per_run"][0]["dead_end_rate"] == round(1 / 3, 4)


def test_cost_and_redundancy():
    f1 = {"sig": "a", "kind": "consistency", "status": "confirmed"}
    f2 = {"sig": "b", "kind": "consistency", "status": "flaky"}
    ev = {"run_end": [{"llm_usage": {"prompt_tokens": 900, "completion_tokens": 100, "retries": 3}, "cost_usd": 0.12}],
          "gate_done": [{"replays": 6, "minutes": 1.5, "judge_tokens": 50}], "policy_error": [{}]}
    steps = [S(1, 1, state="a", worker=1), S(1, 2, state="a", worker=2), S(2, 3, state="b", worker=1), S(2, 4, state="c")]
    row = cost_block([R(findings=[f1, f2], labels={"a": "F01", "b": "fp"}, events=ev, steps=steps)])["per_run"][0]
    assert (row["tokens"], row["usd"], row["tokens_per_finding"], row["tokens_per_confirmed_true"]) == (1000, 0.12, 500, 1000)
    assert (row["gate_replays"], row["gate_minutes"], row["judge_tokens"], row["llm_retries"]) == (6, 1.5, 50, 3)
    assert row["policy_error_rate"] == 0.25 and row["cross_worker_redundancy"] == round(1 / 3, 4)


def test_safety_block():
    ev = {"session": [{"out_of_scope_blocked": 2, "blocked_writes": [1, 2, 3], "mode_violations": [{"path": "/x"}]}],
          "safety": [{"foreign_delete_count": 1, "cleanup_share": 0.8}]}
    out = safety_block([R(events=ev, config={"mode": "reversible"})])
    assert out == {"destructive_incidents": 1, "out_of_scope_blocked": 2, "writes_refused_by_mode": 3, "mode_violations": 1,
                   "cleanup_share_median": 0.8, "modes": ["reversible"]}


def test_recall_by_app_type_mutation_score_and_rule_recall():
    cat = load_catalog()
    f = {"sig": "x", "kind": "http_5xx"}
    runs = [R("r1", findings=[f], labels={"x": "F01"}, enabled=("F01", "F02"), config={"app": {"app_type": "blog"}}),
            R("r2", enabled=("F01", "F02"), config={"app": {"app_type": "blog"}}),
            R("r3", clean=True)]
    rec = recall_block(runs, cat)
    assert rec["by_app_type"]["blog"] == {"found": 1, "runs_x_faults": 4, "recall": 0.25}
    assert rec["mutation_score"]["realworld"] == {"killed": 1, "seeded": 2, "score": 0.5}
    rr = rule_recall(runs, cat)
    assert rr["http_5xx"]["found"] == 1 and rr["http_5xx"]["of"] >= 2  # F01's families name http_5xx; two runs had F01
    assert all(v["found"] <= v["of"] for v in rr.values())


def test_guard_loss_counts_s4_s5_misses_only():
    fun = {"rows": [{"first_failed": "S4_armed", "suppressed": {"event-feed": 2}},
                    {"first_failed": "S5_flagged", "suppressed": {"event-feed": 1, "written-since": 1}},
                    {"first_failed": "S1_reached", "suppressed": {"event-feed": 5}}]}
    assert guard_loss(fun) == {"event-feed": 2, "written-since": 1}


def _m(run, app="realworld", cond="b4", clean=False, **k):
    return {"run": run, "app": app, "condition": cond, "clean": clean, "faults_found": 0, "precision_distinct": 0.5,
            "unique_states": 10, "findings": 4, **k}


def test_scaling_generalization_across_apps():
    runs = [R("a", summary={"workers": 1}), R("b", summary={"workers": 4})]
    sc = scaling_block([_m("a", unique_states=10), _m("b", unique_states=30)], runs)
    assert sc["realworld / b4"][4]["speedup"] == 3.0 and sc["realworld / b4"][4]["efficiency"] == 0.75
    assert "status" in scaling_block([_m("a")], runs[:1])
    runs = [R("d", config={"app": {"heldout": False}}), R("h", app="juiceshop", config={"app": {"heldout": True}})]
    g = generalization_block([_m("d", faults_found=3), _m("h", app="juiceshop", faults_found=1)], runs)
    assert g["b4"]["faults_found"] == {"dev": 3, "heldout": 1, "gap": 2}
    acr = across_apps([_m("a", faults_found=2), _m("b", faults_found=4), _m("c", app="bookstack", faults_found=6)])
    assert acr["b4"]["faults_found"]["apps"] == 2 and acr["b4"]["faults_found"]["mean_of_medians"] == 5.0


def test_detector_engines_profile_and_report_quality(tmp_path):
    f = {"sig": "x", "kind": "http_5xx"}
    live = R("r1", findings=[f], labels={"x": "F01"}, source="live")
    res = R("r1", findings=[], source="resweep")
    assert detector_vs_e2e([live, res]) == {"runs": [{"run": "r1", "live": 1, "resweep": 0, "both": 0}]}
    assert "status" in detector_vs_e2e([live])
    eng = R(findings=[{"sig": "a", "kind": "c", "gate": {"engines": {"firefox": True, "webkit": False}}},
                      {"sig": "b", "kind": "c", "gate": {"engines": {"firefox": True}}}])
    assert engine_agreement([eng]) == {"replayed": 2, "held_everywhere": 1, "share": 0.5}
    prof = R(config={"app": {"app_type": "blog", "primitives": ["CRUD", "COLL"]}},
             events={"app_profile": [{"app_type": "blog", "primitives": ["CRUD", "QUERY"]}]})
    assert profile_accuracy([prof])["per_run"][0] == {"run": "r1", "type_ok": True, "primitive_precision": 0.5,
                                                      "primitive_recall": 0.5}
    sheet = tmp_path / "rq.toml"
    assert "status" in report_quality_block(sheet)
    sheet.write_text('[r1.a]\nreproduced = ""\n', encoding="utf-8")
    assert report_quality_block(sheet)["status"].startswith("pending")
    sheet.write_text('[r1.a]\nreproduced = "yes"\nsteps_clear = 2\nexpected_vs_actual = 2\nevidence = 1\nminimal = 1\n'
                     'severity_clear = 2\ntriage_minutes = 4\n[r1.b]\nreproduced = "no"\nsteps_clear = 1\n'
                     'triage_minutes = 9\n', encoding="utf-8")
    q = report_quality_block(sheet)
    assert q["rated"] == 2 and q["actionability_mean_of_10"] == 4.5 and q["triage_minutes_median"] == 9.0
    assert json.dumps(q)  # serialisable for the report


# ---------------------------------------------------------------------------- O7 GraphQL, R2 top-up, R10 ranking
GQL = {"queryType": {"name": "Query"}, "mutationType": {"name": "Mutation"}, "types": [
    {"kind": "OBJECT", "name": "Query", "fields": [
        {"name": "article", "type": {"kind": "OBJECT", "name": "Article"}},
        {"name": "articles", "type": {"kind": "NON_NULL", "ofType": {"kind": "LIST", "ofType": {"kind": "OBJECT",
                                                                                                "name": "Article"}}}}]},
    {"kind": "OBJECT", "name": "Mutation", "fields": [{"name": "like", "type": {"kind": "SCALAR", "name": "Int"}}]},
    {"kind": "OBJECT", "name": "Article", "fields": [
        {"name": "title", "type": {"kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "String"}}},
        {"name": "likes", "type": {"kind": "SCALAR", "name": "Int"}},
        {"name": "status", "type": {"kind": "ENUM", "name": "Status"}}]},
    {"kind": "ENUM", "name": "Status", "enumValues": [{"name": "DRAFT"}, {"name": "LIVE"}]}]}


def _gq(query, data, status=200, errors=None):
    body = {"data": data, **({"errors": errors} if errors else {})}
    return [{"method": "POST", "path": "/graphql", "status": status, "sent": json.dumps({"query": query}), "body": body}]


def test_r57e_graphql_contract():
    from webtester.openapi import GraphQLSchema

    g = GraphQLSchema(GQL)
    assert sorted(g.ops) == ["mutation like", "query article", "query articles"]
    q = "query A { a: article { title likes ...S } } fragment S on Article { status }"
    assert rule_contract(_gq(q, {"a": {"title": "T", "likes": 3, "status": "LIVE"}}), g) == []
    for data, word in (({"a": {"title": None, "likes": 3, "status": "LIVE"}}, "non-null"),
                       ({"a": {"title": "T", "likes": "3", "status": "LIVE"}}, "declared Int"),
                       ({"a": {"title": "T", "likes": 3, "status": "GONE"}}, "not one of"),
                       ({"a": {"title": "T", "status": "LIVE"}}, "missing")):
        out = rule_contract(_gq(q, data), g)
        assert [v.rule for v in out] == ["R57e"] and word in out[0].message, (data, out)
    called = set()
    assert rule_contract(_gq("{ articles { title } }", {"articles": [{"title": "a"}, {"title": 5}]}), g, called)
    assert called == {"query articles"}
    assert rule_contract(_gq(q, {"a": None}, errors=[{"message": "x"}]), g) == []  # errors: R57's case
    assert rule_contract(_gq("{ article { title @include(if: $x) } }", {"article": {}}), g) == []  # directive: optional
    rest = [{**_gq(q, {"a": {"title": 1}})[0], "path": "/api/other"}]
    assert rule_contract(rest, g) == []  # not the GraphQL endpoint


class _Log:
    def __init__(self, armed):
        self.armed = armed

    def summary(self):
        return {r: {"exercised": n} for r, n in self.armed.items()}


def test_r10_least_exercised_primitive_first():
    from webtester.reach import rank_primitives

    prims = ["QUERY", "COLL", "CRUD"]
    assert rank_primitives(prims, None) == prims
    assert rank_primitives(prims, _Log({"R23": 9, "R38": 4, "I-create": 2})) == ["COLL", "CRUD", "QUERY"]
    assert rank_primitives(prims, _Log({})) == prims  # ties keep the profile's order


def test_r2_tops_a_seeded_list_up_to_one_page_plus_one():
    from webtester.consistency import SweepState, Sweeper, Facts

    st = SweepState()
    sw = Sweeper(st, 1, None)
    kinds = []

    async def stub(session, url, done, target, kind, override=None):
        kinds.append(kind)
        return {"outcome": "accepted", "server": [], "values": {"Title": f"A {kind[4:]}"}}

    sw._submit_variant = stub
    key = ("/items/new", "input||||Title|")
    name = {"do": "fill", "ekey": "input||||Title|", "value": "A"}
    st.seed_plans[key] = ("http://h/items/new", [name, {"do": "click", "ekey": "button||||Save|"}], name, 3,
                          {"A", "A 2", "A 3"})
    lst = {"heading": "Items", "nav": False, "items": [{"name": n, "text": n, "abs": None} for n in ("A", "A 2", "A 3")]}
    facts = Facts("http://h/items", lists=[lst])
    session = SimpleNamespace(cfg=SimpleNamespace(app=SimpleNamespace(page_size=0)))
    sw.page5 = {"fields": [], "pager": []}
    asyncio.run(sw._top_up(session, facts, 5))
    assert kinds == [] and key in st.topup_skipped  # no page size known: nothing made
    sw.page5 = {"fields": [{"type": "select", "label": "Items per page", "value": "5"}], "pager": []}
    asyncio.run(sw._top_up(session, facts, 6))
    assert kinds == ["seed4", "seed5", "seed6"] and key in st.topped and st.topup_made == 3
    assert sum(1 for e in sw.mem.events if e.source == "seed") == 3
    asyncio.run(sw._top_up(session, facts, 7))
    assert len(kinds) == 3  # once per form
    st2 = SweepState()
    sw2 = Sweeper(st2, 1, None)
    sw2._submit_variant = stub
    st2.seed_plans[key] = st.seed_plans[key][:3] + (3, {"A"})
    sw2.page5 = {"fields": [], "pager": []}
    asyncio.run(sw2._top_up(SimpleNamespace(cfg=SimpleNamespace(app=SimpleNamespace(page_size=4))), facts, 1))
    assert key in st2.topped and st2.topup_made == 2  # the config's page size: 4 + 1 - 3 listed
