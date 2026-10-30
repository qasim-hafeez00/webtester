"""D60: the v5 wave rules (norms, cross-view, probes, environment replay) and the phase 1-4 harness parts.

Each rule has a faulty and a clean case. The served mini-app test runs a real Sweeper over real pages and
fails on any check-outcome row with an error (a rule that raised is logged as inconclusive, never silent).
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import TIER, Facts, SweepState, Sweeper
from webtester.crossview import CrossView
from webtester.envcheck import compare, page_values
from webtester.families import built_rules, tally, tracker
from webtester.norms import (parse_number, rule_aggregates, rule_lines, rule_placeholders, rule_presentation,
                             rule_running_balance, rule_sort)
from webtester.reach import defer_reason, parse_discovery, parse_profile, profile_value


def rules(vs):
    return sorted({v.rule for v in vs})


# ---------------------------------------------------------------------------- numbers (O6 a)
def test_number_parser_formats():
    assert parse_number("1.234,56 €") == 1234.56 and parse_number("$1,234.56") == 1234.56
    assert parse_number("1,00,000") == 100000 and parse_number("(12.00)") == -12.0
    assert parse_number("1.2k") == 1200 and parse_number("٣٤٥") == 345


# ---------------------------------------------------------------------------- norms
def _list(heading, items):
    return {"heading": heading, "nav": False, "items": [{"name": n, "text": t, "abs": f"http://h/i/{k}", "href": f"/i/{k}"}
                                                        for k, (n, t) in enumerate(items)]}


def test_r25_sort_invariant():
    raw = {"sort": [{"text": "Price: low to high", "via": "select"}]}
    bad = _list("Products", [("A", "A $5.00"), ("B", "B $9.00"), ("C", "C $3.00"), ("D", "D $12.00")])
    good = _list("Products", [("A", "A $5.00"), ("B", "B $6.00"), ("C", "C $9.00"), ("D", "D $12.00")])
    assert rules(rule_sort(raw, bad)) == ["R25"] and rule_sort(raw, good) == []
    col = {"sort": [{"text": "Name", "via": "column", "dir": "ascending", "values": ["apple", "cherry", "banana"]}]}
    assert rules(rule_sort(col, None)) == ["R25"]


def test_r41_aggregates_on_one_page():
    L = _list("Open tickets", [("t1", ""), ("t2", ""), ("t3", "")])
    counts = [{"n": 5, "unit": "tickets", "text": "5 tickets", "nav": False}]
    assert rules(rule_aggregates([L], counts, [], {})) == ["R41"]
    assert rule_aggregates([L], counts, [], {"pager": [{"text": "2"}]}) == []  # an incomplete list proves nothing
    assert rule_aggregates([L], [{"n": 3, "unit": "tickets", "text": "3 tickets", "nav": False}], [], {}) == []


def test_r32_running_balance():
    t = {"head": ["Date", "Amount", "Balance"], "rows": [["d1", "100.00", "100.00"], ["d2", "-20.00", "80.00"],
                                                          ["d3", "50.00", "130.00"], ["d4", "-10.00", "125.00"]]}
    assert rules(rule_running_balance([t])) == ["R32"]
    t["rows"][3][2] = "120.00"
    assert rule_running_balance([t]) == []


def test_r36_r06s_r72_lines():
    today = date(2026, 10, 28)
    bad = ["Booking Nov 20, 2026 - Nov 15, 2026", "10:00 - 11:30 (2h)", "3 of 4 done (50%)",
           "Was $100.00 now $80.00 -30%", "Invoice 12 overdue 2026-12-20", "Event upcoming 2026-01-05"]
    good = ["Booking Nov 15, 2026 - Nov 20, 2026", "10:00 - 11:30 (1h 30m)", "3 of 4 done (75%)",
            "Was $100.00 now $80.00 -20%", "Invoice 12 overdue 2026-10-01", "Event upcoming 2026-11-05"]
    assert rules(rule_lines(bad, today)) == ["R06s", "R36", "R72"]
    assert len(rule_lines(bad, today)) == 6
    assert rule_lines(good, today) == []


def test_presentation_rules():
    raw = {"covered": [{"control": "Save", "by": "DIV.cookie"}], "overflow": True, "invisible": ["Hidden price"],
           "media": [{"kind": "video", "paused": False, "advanced": 0.0, "duration": 30, "ready": 4, "error": 0, "button": "Play"},
                     {"kind": "audio", "paused": False, "advanced": 1.1, "duration": 30, "ready": 4, "error": 0, "button": ""}],
           "svg_bad": ["rect width=NaN"], "canvas_blank": ["chart"], "broken": [{"what": "image", "src": "/a.png", "alt": "Logo"}],
           "contacts": [{"href": "mailto:", "text": "Mail us"}, {"href": "tel:call", "text": "Call"}]}
    assert rules(rule_presentation(raw)) == ["R02m", "R10x", "R65", "R74", "R75"]
    assert rule_presentation({"contacts": [{"href": "mailto:a@b.co", "text": "x"}, {"href": "tel:+1555", "text": "y"}]}) == []


def test_r01x_placeholders():
    assert rules(rule_placeholders("Welcome messages.welcome_title to the app", set())) == ["R01x"]
    assert rules(rule_placeholders("Lorem ipsum dolor", set())) == ["R01x"]
    assert rule_placeholders("Visit example.com or read e.g. the guide v1.2.3", set()) == []
    assert rule_placeholders("Event maintenance_action_run by Admin", set()) == []  # D62 (I95): an event code
    assert rules(rule_placeholders("Link common.privacy_policy", set())) == ["R01x"]


# ---------------------------------------------------------------------------- cross-view
def _sweeper():
    st = SweepState()
    sw = Sweeper(st, 1, AppConfig(name="t", base_url="http://h", account_template={
        "username": "w{i}", "email": "w{i}@t", "password": "p"}).account(1))
    sw.writes, sw.pre, sw.last, sw.pages = [], {}, None, [("/", "")]
    return st, sw


class _Obs:
    def __init__(self, url, elements=()):
        self.url, self.elements = url, list(elements)

    def element(self, eid):
        return next((e for e in self.elements if e.id == eid), None)


def _facts(url, h1="", lists=(), text="", counts=(), totals=(), showing=None):
    return Facts(url, h1=h1, text=text or h1, plain=text or h1, lists=list(lists), counts=list(counts),
                 totals=list(totals), showing=showing)


def test_r20_name_and_price_across_views():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    lst = {"heading": "Products", "nav": False, "items": [{"name": "Alpha Widget", "text": "Alpha Widget $10.00",
                                                          "abs": "http://h/items/1", "href": "/items/1"}]}
    cv.check(sw, _facts("http://h/", lists=[lst]), {}, _Obs("http://h/"), [], None, 1)
    out = cv.check(sw, _facts("http://h/items/1", h1="Alpha Widget", text="Alpha Widget Price $12.00"), {"status": []},
                   _Obs("http://h/items/1"), [], None, 2)
    assert [v.subject.split("|")[0] for v in out if v.rule == "R20"] == ["price"]
    out = cv.check(sw, _facts("http://h/items/1", h1="Alpha Widget", text="Alpha Widget Price $10.00"), {"status": []},
                   _Obs("http://h/items/1"), [], None, 3)
    assert not [v for v in out if v.rule == "R20"]


def test_r40_breadcrumb_parent_lists_child():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    cv.check(sw, _facts("http://h/books/b1/page/p1", h1="Page One"),
             {"breadcrumbs": [{"text": "Books", "href": "http://h/books"}, {"text": "B1", "href": "http://h/books/b1"}]},
             _Obs("http://h/books/b1/page/p1"), [], None, 1)
    parent = {"heading": "Pages", "nav": False, "items": [{"name": "Other", "text": "Other", "abs": "http://h/x", "href": "/x"}]}
    out = cv.check(sw, _facts("http://h/books/b1", h1="B1", lists=[parent]), {}, _Obs("http://h/books/b1"), [], None, 2)
    assert rules(out) == ["R40"]


def test_r34_status_tabs_and_r12b_echo():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    counts = [{"n": 3, "unit": "open", "text": "Open 3"}, {"n": 2, "unit": "closed", "text": "Closed 2"},
              {"n": 6, "unit": "all", "text": "All 6"}]
    sw.mem.typed.add("Café & Co")
    out = cv.check(sw, _facts("http://h/tickets", counts=counts, text="Tickets Cafe &amp; Co"), {}, _Obs("http://h/tickets"),
                   [], None, 1)
    assert {"R34", "R12b"} <= set(rules(out))


def test_r27_input_kept_and_r29_dead_control():
    from webtester.browser import Element

    st, sw = _sweeper()
    cv = CrossView(st.cross)
    done = [{"do": "fill", "id": "1", "value": "Atlas Q7", "el": '[1] input[text] label="Title"', "ok": True},
            {"do": "click", "id": "2", "el": '[2] button "Save"', "ok": True}]
    sw.last = _facts("http://h/new", text="New item")
    raw = {"fields": [{"label": "Title", "type": "text", "value": "", "name": "title"}]}
    out = cv.check(sw, _facts("http://h/new", text="New item\nTitle is required"), raw, _Obs("http://h/new"), done, None, 2)
    assert "R27" in rules(out)
    save = Element(id="5", tag="button", text="Save")
    sw.pre_text, sw.post_text, sw.step_requests, sw.dialogs_this_step = "page", "page", 0, False
    out = cv.check(sw, _facts("http://h/x"), {}, _Obs("http://h/x", [save]),
                   [{"do": "click", "id": "5", "el": '[5] button "Save"', "ok": True}], None, 3)
    assert "R29" in rules(out)
    sw.step_requests = 1
    out = cv.check(sw, _facts("http://h/x"), {}, _Obs("http://h/x", [save]),
                   [{"do": "click", "id": "5", "el": '[5] button "Save"', "ok": True}], None, 4)
    assert "R29" not in rules(out)


def test_r38_range_filter_and_r44_page_size():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    lst = _list("Results", [("A", "A $5.00"), ("B", "B $50.00")])
    out = cv.check(sw, _facts("http://h/s?min_price=10&max_price=40", lists=[lst]), {}, _Obs("http://h/s"), [], None, 1)
    assert "R38" in rules(out)
    cv.check(sw, _facts("http://h/s"), {}, _Obs("http://h/s"),
             [{"do": "select", "value": "2", "el": '[3] select label="Per page"', "ok": True}], None, 2)
    big = _list("Results", [("A", ""), ("B", ""), ("C", "")])
    out = cv.check(sw, _facts("http://h/s", lists=[big]), {}, _Obs("http://h/s"), [], None, 3)
    assert "R44" in rules(out)


def test_no_cross_view_rule_raises_on_an_empty_page():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    cv.check(sw, _facts("http://h/"), {}, _Obs("http://h/"), [], None, 1)
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]


# ---------------------------------------------------------------------------- reach (R1, R7, R8, X5)
def test_reach_helpers():
    assert defer_reason("Delete book", 0.2, own_page=False, threshold=0.6) and not defer_reason("Delete", 0.2, True, 0.6)
    assert defer_reason("Log out", 0.5, True, 0.6) and not defer_reason("Log out", 0.95, True, 0.6)
    d = parse_discovery("http://h/", robots="User-agent: *\nDisallow: /admin\nSitemap: http://h/sm.xml",
                        sitemap="<loc>http://h/a</loc><loc>http://other/b</loc>", feed="<link>http://h/post/1</link>")
    assert d["robots"] == ["/admin"] and d["sitemap"] == ["/a"] and d["feed"] == ["/post/1"]
    assert profile_value({"type": "email"}, "Email", "x", "w1ab").endswith("@example.test")
    assert profile_value({"maxlength": 5}, "Name", "Longer name", "w1ab") == "Longe"
    assert profile_value({}, "Title", "Atlas", "w1ab", hint="Title has already been taken").endswith("w1ab")
    p = parse_profile({"app_type": "shop", "primitives": ["P-COLL", "LEDG", "nope"]}, ["Shop", "Wiki, CMS"],
                      ["COLL", "LEDG"])
    assert p == {"app_type": "Shop", "primitives": ["COLL", "LEDG"], "evidence": {}}


# ---------------------------------------------------------------------------- M10 comparison
def test_envcheck_compare_normalised():
    base = {"lists": {"books": ["a", "b"]}, "counts": {"books": 2}, "dates": ["2026-11-15"], "actions": ["save"], "h1": "x"}
    tz = {"lists": {"books": ["a", "b"]}, "counts": {"books": 2}, "dates": ["2026-11-14"], "actions": ["save"], "h1": "x"}
    assert compare("tz-west", base, tz) and compare("tz-west", base, base) == []
    phone = {**base, "actions": []}
    assert compare("phone", base, phone, {"controls": []}) and compare("phone", base, phone, {"controls": ["Menu"]}) == []
    assert page_values(Facts("u", h1="T"), {})["h1"] == "t"


# ---------------------------------------------------------------------------- registry
def test_every_built_rule_has_a_tier_and_the_tracker_moves():
    rows = tracker()
    t = tally(rows)
    assert t["by_impl"]["built"] > 42 and len(t["rules_todo"]) < 53
    assert {"R20", "R23", "R63", "R71", "R32"} <= built_rules()
    assert all(TIER[r] in ("T1", "T2", "T3") for r in TIER)


# ---------------------------------------------------------------------------- served mini-app
PAGES = {
    "/": """<html><body><nav><a href="/">Home</a> <a href="/cart">Cart <span class="badge">2</span></a></nav>
<h1>Shop</h1><input type="search" name="q" placeholder="Search">
<select name="sort"><option>Name</option><option selected>Price: low to high</option></select>
<ul class="products"><li class="product"><a href="/items/1">Alpha Widget</a> $20.00</li>
<li class="product"><a href="/items/2">Beta Gadget</a> $10.00</li>
<li class="product"><a href="/items/3">Gamma Thing</a> $15.00</li></ul></body></html>""",
    "/items/1": """<html><body><nav aria-label="breadcrumb"><a href="/">Home</a></nav><h1>Alpha Widget</h1>
<p>Price $25.00</p><a href="#specs">Specs</a></body></html>""",
}


def _serve_and_sweep(steps):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), settle_ms=50, capture_evidence=True,
                            seed_copies=0, poll_deadline_s=0.5)
            s = BrowserSession(browser, cfg, 1)
            await s.start()

            async def serve(route):
                path = route.request.url.split("http://h", 1)[1].split("?")[0] or "/"
                if path in PAGES:
                    await route.fulfill(status=200, content_type="text/html", body=PAGES[path])
                elif path.startswith("/items/9999"):
                    await route.fulfill(status=500, content_type="text/html", body="<h1>Server Error</h1>")
                else:
                    await route.fulfill(status=404, content_type="text/html", body="<h1>Not found</h1>")
            await s.context.route("http://h/**", serve)
            st = SweepState()
            sw = Sweeper(st, 1, None)
            sigs = []
            try:
                for i, path in enumerate(steps, 1):
                    await s.goto(path)
                    obs = await s.observe()
                    done = [{"do": "navigate", "id": None, "value": path, "el": None, "ok": True, "ekey": None}]
                    await sw.before(s, obs, [])
                    await sw.actions_done(s)
                    sigs += await sw.after(s, obs, done, i)
            finally:
                await s.close()
                await browser.close()
            return sigs, st

    return asyncio.run(go())


def test_mini_app_end_to_end():
    sigs, st = _serve_and_sweep(["/", "/items/1"])
    got = {(x.detail["rule"], x.detail["sig"].split("|")[3].split("|")[0]) for x in sigs}
    assert ("R25", "sort") in got  # $20 then $10 under 'Price: low to high'
    assert ("R20", "price") in got  # $20.00 in the list, $25.00 on its page
    assert ("R43", "#specs") in got
    assert ("R63", "5xx") in got  # /items/999999999 answers 500
    errors = [r for r in st.checks.records() if r["why"].startswith("error:")]
    assert not errors, errors


def test_r06s_ratings_and_spend_more():
    bad = ["Free shipping on orders over $50.00", "Subtotal $30.00", "Spend $25.00 more for free shipping",
           "5 stars 10", "4 stars 5", "3 stars 0", "2 stars 0", "1 star 0", "4.9 out of 5", "20 ratings"]
    got = sorted(v.subject for v in rule_lines(bad, date(2026, 10, 28)))
    assert got == ["average", "histogram", "spend-more"]
    good = ["Free shipping on orders over $50.00", "Subtotal $30.00", "Spend $20.00 more for free shipping",
            "5 stars 10", "4 stars 5", "3 stars 0", "2 stars 0", "1 star 0", "4.7 out of 5", "15 ratings"]
    assert rule_lines(good, date(2026, 10, 28)) == []


def test_r38c_filter_composition():
    st, sw = _sweeper()
    cv = CrossView(st.cross)
    few = _list("Results", [("A", ""), ("B", "")])
    many = _list("Results", [("A", ""), ("B", ""), ("C", ""), ("D", "")])
    cv.check(sw, _facts("http://h/s?type=book", lists=[few]), {}, _Obs("http://h/s"), [], None, 1)
    out = cv.check(sw, _facts("http://h/s?type=book&tag=x", lists=[many]), {}, _Obs("http://h/s"), [], None, 2)
    assert "R38c" in rules(out)


# ---------------------------------------------------------------------------- harness parts
def test_execution_modes_refuse_in_the_executor():
    from webtester.browser import BrowserSession

    def sess(mode):
        cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), mode=mode)
        return BrowserSession(None, cfg, 1)

    ro, rv, ct = sess("read-only"), sess("reversible"), sess("controlled")
    assert ro.mode_refuses("POST", "http://h/api/articles") == "read-only"
    assert ro.mode_refuses("POST", "http://h/login") == "" and ro.mode_refuses("GET", "http://h/x") == ""
    assert rv.mode_refuses("DELETE", "http://h/api/articles/other") and rv.mode_refuses("POST", "http://h/api/x") == ""
    rv.owned.add("/api/articles/mine")
    assert rv.mode_refuses("DELETE", "http://h/api/articles/mine") == ""
    assert ct.mode_refuses("DELETE", "http://h/anything") == ""


def test_ranking_keeps_head_then_unvisited_elements():
    from webtester.browser import BrowserSession, Element

    cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), max_elements=20)
    s = BrowserSession(None, cfg, 1)
    els = [Element(id=str(i), tag="a", text=f"e{i}", href=f"/p{i}") for i in range(40)]
    for e in els[15:35]:
        s.note_activated("http://h/list", e.key())
    kept = s._rank("http://h/list", els)
    ids = [int(e.id) for e in kept]
    assert len(kept) == 20 and ids[:15] == list(range(15)) and set(ids[15:]) == set(range(35, 40))


def test_coverage_metrics_and_popup_dismissal_in_a_page():
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    html = """<html><body><div class="cookie-banner"><p>We use cookies</p><button>Accept all</button></div>
<button id="b1">One</button><button id="b2">Two</button>
<script>document.getElementById('b1').addEventListener('click', () => {});
document.getElementById('b2').addEventListener('click', () => {});
document.querySelector('.cookie-banner button').addEventListener('click', e => e.target.parentElement.remove());</script>
</body></html>"""

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), settle_ms=50, coverage_metrics=True)
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            await s.context.route("http://h/**", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
            await s.goto("/")
            obs = await s.observe()
            el = next(e for e in obs.elements if e.text == "One")
            await s.execute("click", el.id)
            await s.observe()
            await s.close()
            rep = s.report()
            await browser.close()
            return rep, obs

    rep, obs = asyncio.run(go())
    assert rep["dismissed"] and not any(e.text == "Accept all" for e in obs.elements)
    assert rep["handler_elements"] >= 2 and rep["handler_elements_clicked"] >= 1
    assert rep["js_coverage"]["functions"] >= 1
