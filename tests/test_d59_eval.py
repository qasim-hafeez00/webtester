"""D59: check-outcome log, family registry, evaluation metrics, intervals, and the page-norm rules."""

from __future__ import annotations

import asyncio

import pytest

from webtester.checks import CheckLog, page_arms
from webtester.consistency import TIER, Facts, Violation
from webtester.evaluate import (PRIMARY, RunData, compare_conditions, entity_kind, false_alarm_block, funnel_block,
                                issue_key, label_kind, precision_block, recall_block, run_metrics)
from webtester.families import (app_types, built_rules, families, fault_families_of, primitives, rule_packs, tally,
                                tracker)
from webtester.labels import is_true_positive
from webtester.norms import NORMS_JS, arms, rule_norms
from webtester.stats import clopper_pearson, holm, poisson_rate_ci, wilson


# ---------------------------------------------------------------------------- tiers and the check log
def test_unregistered_rule_reports_t2_not_keyerror():
    assert Violation("R99", "s", "m").tier == "T2"
    assert TIER["R43"] == TIER["R64"] == TIER["R26"] == "T2"


def test_checklog_aggregates_per_rule_route_outcome():
    log = CheckLog()
    for step in (3, 4, 9):
        log.note(1, step, "R09", "/books", "suppressed", "event-feed")
    log.note(1, 5, "R09", "/books", "detected")
    rows = log.records()
    sup = next(r for r in rows if r["outcome"] == "suppressed")
    assert (sup["n"], sup["first"], sup["last"]) == (3, 3, 9)
    assert log.summary() == {"R09": {"suppressed": 3, "detected": 1}}
    with pytest.raises(AssertionError):
        log.note(1, 1, "R09", "/", "passed")  # not an outcome: an unexecuted check is never a pass


def test_page_arms_says_why_a_rule_did_not_run():
    a = page_arms(Facts("http://h/", plain="hello"), typed_markup=False)
    assert a["R01"] == "" and a["R06"] == "no-totals" and a["R03"] == "no-list" and a["R08"] == "no-times"
    f = Facts("http://h/", plain="x", lists=[{"heading": "Books", "items": [{"name": "a"}, {"name": "b"}], "nav": False}],
              totals=[{"label": "Total", "value": "3"}])
    a = page_arms(f, typed_markup=False)
    assert a["R03"] == "" and a["R06"] == "" and a["R04"] == "no-count"


# ---------------------------------------------------------------------------- families
def test_registry_matches_the_tally_of_fault_families_md():
    fams = families()
    assert len(fams) == 163
    t = tally(tracker())
    assert t["by_status"] == {"covered": 26, "partial": 20, "coverable": 106, "spec": 3, "out": 8}
    assert set(primitives()) >= {"CRUD", "LEDG", "QUERY", "NAV"} and len(app_types()) == 16


def test_fault_to_family_map_expands_ranges():
    m = fault_families_of()
    assert "DB7" in m["BS01"] and "DB7" in m["BS08"] and m["F06"] == ["DB3"]


def test_tracker_built_is_read_from_code():
    have = built_rules()
    for row in tracker():
        assert set(row["built"]) <= have
        assert not set(row["todo"]) & have


def test_rule_packs_follow_the_app_type():
    shop, blog = rule_packs("Shop"), rule_packs("Blog, social")
    assert "LEDG" in shop["primitives"] and "LEDG" not in blog["primitives"]
    assert "NAV" in blog["primitives"] and "http_5xx" in blog["rules"]
    assert set(shop["missing"]) <= set(shop["missing"] + shop["rules"]) and "R32" in shop["rules"]  # built in D60


# ---------------------------------------------------------------------------- intervals
def test_exact_intervals():
    lo, hi = clopper_pearson(19, 20)
    assert abs(lo - 0.7513) < 1e-3 and abs(hi - 0.9987) < 1e-3
    assert abs(clopper_pearson(0, 10)[1] - 0.3085) < 1e-3
    assert abs(poisson_rate_ci(0, 10)[1] - 0.3689) < 1e-3  # rule of three: about 3/n
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}


# ---------------------------------------------------------------------------- evaluation
def _f(sig, worker=1, step=1, status="candidate", kind="consistency", tier="T2"):
    rule = sig.split("|")[1]
    return {"sig": sig, "kind": kind, "worker": worker, "first_step": step, "status": status,
            "page_url": "http://h" + sig.split("|")[2], "detail": {"rule": rule, "tier": tier}, "occurrences": 1}


def _run(rid, app, findings, labels, enabled, clean=False, cond="b4", checks=(), steps=100):
    return RunData(rid, app, cond, clean, findings, labels, set(enabled), {"steps": steps, "unique_states": 20},
                   list(checks), {(1, s): s * 6.0 for s in range(1, 200)}, 600.0)


def test_labels_and_issues():
    assert label_kind("BS04") == "seeded" and label_kind("new: x") == "new" and label_kind("U3") == "upstream"
    assert label_kind("harness: own emoji") == "harness" and not is_true_positive("harness: own emoji")
    f = _f("consistency|R09|/books|books|+/books/book-duplicate")
    assert entity_kind(f) == "books" and issue_key(f) == ("R09", "/books", "books")


def test_distinct_issue_precision_and_redundancy():
    fs = [_f("consistency|R09|/books|a|+x"), _f("consistency|R09|/books|a|+y"), _f("consistency|R02|/shelves|s|/x")]
    r = _run("r1", "bookstack", fs, {fs[0]["sig"]: "BS04", fs[1]["sig"]: "fp", fs[2]["sig"]: "fp"}, ["BS04"])
    p = precision_block([r])
    assert p["raw"]["tp"] == 1 and p["raw"]["n"] == 3
    assert p["distinct"]["n"] == 2 and p["distinct"]["tp"] == 1 and p["distinct"]["mixed"] == 1


def test_recall_leaves_out_unreachable_faults():
    fs = [_f("consistency|I-delete|/article/*|c")]
    r = _run("r1", "realworld", fs, {fs[0]["sig"]: "F06"}, ["F03", "F06", "F07"])
    rec = recall_block([r], {"F03": {"reachable": False}, "F06": {}, "F07": {}})
    row = rec["per_run"][0]
    assert row["reachable"] == 2 and row["total_recall"] == 0.5 and row["found"] == ["F06"]


def test_false_alarms_on_clean_runs_with_bounds():
    runs = [_run(f"c{i}", "bookstack", [], {}, [], clean=True) for i in range(4)]
    f = _f("consistency|R09|/|p|-q")
    runs.append(_run("c4", "bookstack", [f, _f("consistency|R01|/|undefined")],
                     {f["sig"]: "fp", "consistency|R01|/|undefined": "U2"}, [], clean=True))
    fa = false_alarm_block(runs)
    assert fa["false_alarms"] == 1 and fa["real_bugs_on_clean_app"] == 1 and fa["per_run"]["rate"] == 0.2
    assert fa["per_run"]["ci95"][1] > 0.2


def test_funnel_names_the_first_failed_stage():
    checks = [{"worker": 1, "rule": "R09", "route": "/books", "outcome": "exercised", "why": "", "n": 3,
               "first": 1, "last": 5}]
    r = _run("r1", "bookstack", [], {}, ["BS04"], checks=checks)
    r.summary.update({"faults_exposed": ["BS04"], "exposure_markers": True, "routes": ["/books"]})
    rows = funnel_block([r], {"BS04": {"trigger": "Arrive on the Books list (/books) twice"}})["rows"]
    row = rows[0]
    assert row["S2_triggered"] and row["S4_armed"] and row["S5_flagged"] is False
    assert row["first_failed"] == "S5_flagged"


def test_comparisons_correct_only_the_primary_family():
    rows = []
    for cond, base in (("b4", 6), ("b3", 1)):
        for i in range(5):
            rows.append({"app": "a", "condition": cond, "clean": False, "faults_found": base + i % 2,
                         "unique_states": 10 + i, "steps": 100 + i})
    res = compare_conditions(rows, "b3")["a: b4 vs b3"]
    assert res["faults_found"]["family"] == "primary" and "p_holm" in res["faults_found"]
    assert res["steps"]["family"] == "exploratory" and "p_holm" not in res["steps"]
    assert "faults_found" in PRIMARY


def test_run_metrics_time_to_first_detection():
    f = _f("consistency|R03|/|x", step=10)
    m = run_metrics(_run("r1", "bookstack", [f], {f["sig"]: "BS05"}, ["BS05"]))
    assert m["ttfd_minutes"] == 1.0 and m["faults_found"] == 1 and m["recall_at_budget"]["25%"] == 1


# ---------------------------------------------------------------------------- page norms
def test_norm_rules_pure():
    raw = {"anchors": [{"href": "#missing", "text": "Jump", "found": False}, {"href": "#ok", "text": "", "found": True}],
           "multi": [{"role": "tablist", "label": "Views", "n": 2, "names": ["A", "B"]}],
           "panels": [{"tab": "A", "hidden": True}], "expanded": [{"control": "Menu", "hidden": False}],
           "aria": [{"label": "Notify", "checked": True, "aria": "false"}],
           "ranges": [{"what": "progressbar", "label": "Upload", "now": 130, "lo": 0, "hi": 100}],
           "ratings": [{"x": "7", "y": "5", "unit": "stars", "ctx": "rated 7 / 5 stars"},
                       {"x": "12", "y": "10", "unit": "", "ctx": "page 12 / 10"}],
           "numbers": [{"label": "Qty", "value": "-2", "min": 0, "max": 99}, {"label": "Age", "value": "500", "min": 0,
                                                                              "max": 120}]}
    got = sorted((v.rule, v.subject) for v in rule_norms(raw, typed={"500"}))
    assert got == [("R26", "field|Qty"), ("R26", "progressbar|Upload"), ("R26", "rating|7/5"), ("R43", "#missing"),
                   ("R64", "aria-checked|Notify"), ("R64", "tablist|Views"), ("R64", "tabpanel|A")]
    a = arms({})
    assert (a["R43"], a["R64"], a["R26"]) == ("no-anchors", "no-stateful-controls", "no-ranged-values")


NORM_PAGE = """<!doctype html><html><body>
<a href="#top">Top</a><a href="#nowhere">Missing</a><a href="#" >JS</a>
<a href="#x" data-toggle="collapse">Script</a><h1 id="top">T</h1>
<div role="tablist"><button role="tab" aria-selected="true" aria-controls="p1">One</button>
<button role="tab" aria-selected="true" aria-controls="p2">Two</button></div>
<div id="p1">panel one</div><div id="p2" hidden>panel two</div>
<button aria-expanded="true" aria-controls="m">Menu</button><ul id="m" style="display:none"><li>x</li></ul>
<div role="progressbar" aria-valuenow="140" aria-valuemin="0" aria-valuemax="100">140%</div>
<p>Rated 6 out of 5 stars</p><p>Page 2 / 10</p>
<label for="q">Quantity</label><input id="q" type="number" min="1" max="9" value="0">
</body></html>"""
CLEAN_PAGE = """<!doctype html><html><body><a href="#top">Top</a><h1 id="top">T</h1>
<div role="tablist"><button role="tab" aria-selected="true" aria-controls="p1">One</button>
<button role="tab" aria-selected="false" aria-controls="p2">Two</button></div>
<div id="p1">panel one</div><div id="p2" hidden>panel two</div>
<progress value="30" max="100"></progress><p>Rated 4.5 out of 5 stars</p>
<input type="number" min="1" max="9" value="3"></body></html>"""


def _read(html: str):
    pw_api = pytest.importorskip("playwright.async_api")

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            page = await browser.new_page()
            await page.set_content(html)
            raw = await page.evaluate(NORMS_JS)
            await browser.close()
            return raw

    return asyncio.run(go())


def test_norms_in_a_real_page():
    got = sorted((v.rule, v.subject) for v in rule_norms(_read(NORM_PAGE), set()))
    assert ("R43", "#nowhere") in got and not any(s in ("#top", "#x") for _, s in got)
    assert ("R64", "tablist|One Two") in got and ("R64", "tabpanel|Two") in got and ("R64", "expanded|Menu") in got
    assert ("R26", "rating|6/5") in got and ("R26", "field|Quantity") in got
    assert any(r == "R26" and s.startswith("progressbar") for r, s in got)
    assert not any(s.startswith("rating|2/10") for _, s in got)


def test_norms_quiet_on_a_correct_page():
    raw = _read(CLEAN_PAGE)
    assert rule_norms(raw, set()) == []
    a = arms(raw)
    assert (a["R43"], a["R64"], a["R26"]) == ("", "", "")
