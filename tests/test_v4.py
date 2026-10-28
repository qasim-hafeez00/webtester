"""Harness v4 (D49): state graph, run memory and consistency oracles.

Pure tests over hand-made page facts (no browser), plus one browser test of AUDIT_JS on
fixture HTML (headless Chromium, no app needed). The fixtures copy the effects of the
BookStack injected faults (apps/bookstack/faults/injected.js) and of Conduit's seeded
faults, and their correct counterparts, so each rule is tested both ways.
"""

import asyncio

import pytest

from webtester.browser import Observation
from webtester.config import Account
from webtester.consistency import (Facts, SweepState, Sweeper, age_conflict, audit, parse_money, rule_arithmetic,
                                   rule_counts, rule_dead_items, rule_echo, rule_junk, same_name, signal_of, Violation)
from webtester.inferred import eval_route, ground_expectations
from webtester.memory import RunMemory, age_kind, age_minutes, classify, entity_key, list_key
from webtester.stategraph import StateGraph, action_label, is_navigation, mermaid


def L(heading, items, nav=False):
    return {"heading": heading, "nav": nav,
            "items": [{"name": n, "href": h, "abs": ("http://h" + h) if h and h.startswith("/") else "", "text": n}
                      for n, h in items]}


# ---------------------------------------------------------------- state graph
def test_graph_edges_distribution_paths_and_export():
    g = StateGraph()
    for sid, url in (("s1", "http://h/"), ("s2", "http://h/books"), ("s3", "http://h/books/a-1"), ("s4", "http://h/login")):
        g.visit(1, sid, url, 0)
    link = [{"do": "click", "ekey": "a||||Books|/books", "el": '[3] a "Books" href=/books', "value": None}]
    assert is_navigation(link) and not is_navigation([{"do": "click", "ekey": "button||||Save|", "value": None}])
    g.transition(1, "s1", link, "s2")
    g.transition(2, "s1", link, "s2")
    e = g.transition(1, "s2", [{"do": "click", "ekey": "a||||A 1|/books/a-1", "value": None}], "s3")
    assert g.edges[("s1", action_label(link))].dst["s2@/books"] == 2
    assert g.path("s1", "/books/*") == [g.edges[("s1", action_label(link))], e]
    assert g.travel_url("/books") == "http://h/books"
    assert not g.nondeterministic_nav()
    g.transition(3, "s1", link, "s4")  # the same link led elsewhere once
    assert len(g.nondeterministic_nav()) == 1
    g.name_page("/books", "Books list")
    assert not g.unnamed("/books") and g.unnamed("/")
    st = g.stats()
    assert st["pages"] == 4 and st["edges"] == 2 and st["named_pages"] == 1
    assert "Books list" in mermaid(g.to_dict())


def test_action_label_buckets_typed_values():
    a = action_label([{"do": "fill", "ekey": "input|text|||Title|", "value": "x"}])
    b = action_label([{"do": "fill", "ekey": "input|text|||Title|", "value": "another"}])
    c = action_label([{"do": "fill", "ekey": "input|text|||Title|", "value": ""}])
    assert a == b != c


# ---------------------------------------------------------------- memory
def test_verbs_from_controls():
    assert classify('[4] button "Favourite"') == "favourite"
    assert classify('[4] button "Unfavourite"') == "unfavourite"
    assert classify('[9] i  label="ion-heart"') == "favourite"
    assert classify('[2] button "Delete"') == "delete" and classify("ion-trash-a") == "delete"
    assert classify('[1] a "Sign out"') == "logout"
    assert classify('[7] a "New Book" href=/create-book') == "create"
    assert classify('[8] button "Save Book"') == "save"
    assert classify('[3] a "Shelves" href=/shelves') == ""


def test_ages_and_keys():
    assert age_minutes("5 minutes ago") == 5 and age_minutes("2 days ago") == 2880
    assert age_minutes("in 3 days") == -4320 and age_minutes("3 days") is None and age_minutes("just now") == 0
    assert age_kind("Created 2 days ago by Admin") == "created" and age_kind("Updated 1 hour ago") == "updated"
    assert entity_key("http://h/Books/Book-1/?x=1") == "/books/book-1"
    assert entity_key("http://h/#/article/a-1") == "/article/a-1"
    assert list_key("http://h/books?page=2", "Books") != list_key("http://h/books?page=1", "Books")
    assert age_conflict(2880, 14400, 1) and not age_conflict(5, 8, 1) and not age_conflict(2880, 3000, 1)


def test_net_toggle_and_snapshots():
    m = RunMemory()
    m.add_event(worker=1, step=1, verb="favourite", obj="Shelf A", status="verified")
    m.add_event(worker=1, step=2, verb="favourite", obj="Shelf B", status="verified")
    m.add_event(worker=1, step=3, verb="unfavourite", obj="Shelf B", status="verified")
    m.add_event(worker=2, step=4, verb="favourite", obj="Shelf C", status="verified")
    assert set(m.net_toggle(1, "favourite")) == {"shelf a"}
    info, prev = m.snapshot("http://h/favourites", "My Favourites", [("Shelf A", "/shelves/a")], 1, 5)
    assert prev is None and info.personal and info.category == "favourite"
    _, prev = m.snapshot("http://h/favourites", "My Favourites", [], 1, 6)
    assert prev.items == [("Shelf A", "/shelves/a")]


# ---------------------------------------------------------------- page rules
def test_junk_rule_skips_typed_text():
    assert [v.subject for v in rule_junk("Total: NaN items", set())] == ["NaN"]
    assert rule_junk("I typed undefined on purpose", {"undefined"}) == []
    assert rule_junk("Hello {{ user.name }}", set())[0].subject == "unfilled template {{ }}"
    assert rule_junk("All good here", set()) == []
    assert rule_junk("price 0.30000000000000004", set())[0].subject == "floating-point noise"


def test_dead_list_item_bs05_and_clean_lists():
    phantom = Facts("http://h/user/admin", lists=[L("Recently Created Chapters", [
        ("Chapter 1", "/books/b/chapter/c1"), ("Chapter 2", "/books/b/chapter/c2"), ("Custom Chapter Title", "#")])])
    assert [v.rule for v in rule_dead_items(phantom)] == ["R03"]
    js_list = Facts("http://h", lists=[L("Tabs", [("A", "#"), ("B", "#"), ("C", "/c")])])
    more = Facts("http://h", lists=[L("Books", [("A", "/a"), ("B", "/b"), ("Show more", "#")])])
    assert rule_dead_items(js_list) == [] and rule_dead_items(more) == []


def test_count_below_list_bs06_one_sided():
    f = Facts("http://h/user/admin", counts=[{"n": 2, "unit": "Chapters", "text": "2 Chapters"}],
              lists=[L("Recently Created Chapters", [("C1", "/c1"), ("C2", "/c2"), ("Custom Chapter Title", "#")])])
    assert [v.rule for v in rule_counts(f)] == ["R04"]
    f.counts[0]["n"] = 5  # a preview may show fewer than the count
    assert rule_counts(f) == []
    s = Facts("http://h", showing={"a": 1, "b": 10, "n": 23}, lists=[L("Results", [(f"R{i}", f"/r{i}") for i in range(7)])])
    assert [v.rule for v in rule_counts(s)] == ["R04b"]
    # a profile's count block whose heading is the counts themselves is no list of that kind (clean BookStack)
    block = Facts("http://h/user/admin", counts=[{"n": 3, "unit": "Books", "text": "3 Books"}],
                  lists=[L("Created Content 6 Pages 4 Chapters 3 Books 1 Shelf", [(f"I{i}", f"/i{i}") for i in range(5)])])
    assert rule_counts(block) == []


def test_money_and_arithmetic():
    assert parse_money("$1,234.56") == 1234.56 and parse_money("1.234,56 €") == 1234.56
    assert parse_money("(12.00)") == -12.0 and parse_money("3") == 3.0 and parse_money("n/a") is None
    ok = Facts("http://h", tables=[{"head": ["Item", "Qty", "Price", "Total"],
                                    "rows": [["Pen", "2", "$1.50", "$3.00"], ["Ink", "1", "$4.00", "$4.00"]]}],
               totals=[{"label": "Subtotal", "value": "$7.00"}, {"label": "Tax", "value": "$0.70"},
                       {"label": "Total", "value": "$7.70"}])
    assert rule_arithmetic(ok) == []
    bad = Facts("http://h", tables=[{"head": ["Item", "Qty", "Price", "Total"], "rows": [["Pen", "2", "$1.50", "$4.00"]]}],
                totals=[{"label": "Subtotal", "value": "$4.00"}, {"label": "Total", "value": "$9.00"}])
    assert {v.subject for v in rule_arithmetic(bad)} == {"line|Pen", "total"}


def test_echo_and_names():
    assert rule_echo(Facts("http://h", rendered=["<b>x</b>"]))[0].rule == "R12"
    assert rule_echo(Facts("http://h", plain="Ã©tÃ©"))[0].subject == "mojibake"
    assert not same_name("Page 3", "Page 1") and not same_name("Book", "Atlas Book Q7")
    assert same_name("Atlas Q7", "atlas q7") and same_name("Introduction to Sorting", "Introduction to sorting · Wiki")


def test_signal_signature_is_stable():
    s1 = signal_of(Violation("R03", "List|Custom Chapter Title", "m"), "http://h/user/admin")
    s2 = signal_of(Violation("R03", "List|Custom Chapter Title", "other text"), "http://h/user/bob")
    assert s1.kind == "consistency" and s1.detail["sig"] == "consistency|R03|/user/admin|list|custom chapter title"
    assert s1.detail["tier"] == "T1" and s2.detail["sig"] != s1.detail["sig"]
    # the store and the gate key a consistency finding by its detail sig (the gate compares replayed
    # sweeper signals by detail sig; a message-based key never matched and merged distinct subjects)
    from webtester.oracles import FindingStore, signature
    a = signal_of(Violation("R09", "Books|+Atlas", "'Atlas' appeared in 'Books'"), "http://h/books")
    b = signal_of(Violation("R09", "Books|+Zeta", "'Zeta' appeared in 'Books'"), "http://h/books")
    assert signature(a) == a.detail["sig"]
    store = FindingStore()
    store.ingest([a, b], step=1, worker=1, state="", trail=[])
    assert len(store.all()) == 2


# ---------------------------------------------------------------- memory rules (Sweeper, no browser)
def sweeper(worker=1):
    return Sweeper(SweepState(), worker, Account("worker01", "w@x", "p"))


def test_revisit_phantom_bs04_and_explained_create():
    sw = sweeper()
    books = [("Book", "/books/book"), ("Book2", "/books/book2")]
    assert sw._lists(Facts("http://h/books", lists=[L("Books", books)]), 1) == []
    v = sw._lists(Facts("http://h/books", lists=[L("Books", books + [("Book", "/books/book-duplicate")])]), 5)
    assert [x.rule for x in v] == ["R09"] and "appeared" in v[0].message
    sw.mem.add_event(worker=2, step=6, verb="create", obj="Atlas Q7", status="verified")  # another worker's create
    v = sw._lists(Facts("http://h/books", lists=[L("Books", books + [("Book", "/books/book-duplicate"),
                                                                     ("Atlas Q7", "/books/atlas-q7")])]), 7)
    assert v == []  # explained (and the phantom was already reported at step 5)


def test_revisit_after_session_change_and_event_feeds():
    sw = sweeper()
    sw._lists(Facts("http://h/", lists=[L("", [("Global Feed", "/")])]), 6)
    sw.mem.add_event(worker=1, step=54, verb="logout", obj="", status="verified")
    sw.mem.add_event(worker=1, step=62, verb="login", obj="worker01", status="verified")
    assert sw._lists(Facts("http://h/", lists=[L("", [("Your Feed", "/"), ("Global Feed", "/")])]), 62) == []  # Conduit
    # the login step's own snapshot is taken before the page re-renders, after its event was recorded
    sw2 = sweeper()
    sw2.mem.add_event(worker=1, step=5, verb="login", obj="worker01", status="verified")
    sw2._lists(Facts("http://h/", lists=[L("", [("Sign in", "/login")])]), 5)
    assert sw2._lists(Facts("http://h/", lists=[L("", [("Your Feed", "/"), ("Global Feed", "/")])]), 25) == []
    acts = [("Book A", "/books/a"), ("Book B", "/books/b"), ("Page C", "/c")]
    sw._lists(Facts("http://h/", lists=[L("Recent Activity", acts)]), 70)
    v = sw._lists(Facts("http://h/", lists=[L("Recent Activity", [("Shelf", "/shelves/s")] + acts)]), 75)
    assert v == []  # anyone's action adds to an activity feed (clean BookStack)


def test_control_number_is_a_standalone_token():
    pw_api = pytest.importorskip("playwright.async_api")
    import inspect
    import re as re_
    from webtester import consistency
    num_js = re_.search(r"const num = .*?null; \};", inspect.getsource(consistency)).group(0)

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            page = await browser.new_page()
            out = await page.evaluate("(xs) => { " + num_js + " return xs.map(num); }",
                                      ["Follow worker04", "Favorite Article (3)", "♥ 1,204", "v2.5", "12 likes"])
            await browser.close()
            return out

    assert asyncio.run(go()) == [None, 3, 1204, None, 12]  # Conduit: 'worker04' is no count


def test_recency_list_tail_drop_vs_middle_removal_bs02():
    sw = sweeper()
    prev = [("A", "/a"), ("Chapter 2", "/c2"), ("C", "/c"), ("D", "/d")]
    sw._lists(Facts("http://h/", lists=[L("Recently Viewed", prev)]), 1)
    sw.mem.add_event(worker=1, step=2, verb="view", obj="E", target="/e", status="verified")
    ok = sw._lists(Facts("http://h/", lists=[L("Recently Viewed", [("E", "/e"), ("A", "/a"), ("Chapter 2", "/c2"),
                                                                     ("C", "/c")])]), 3)
    assert ok == []  # D dropped off the end because E was viewed
    sw.mem.add_event(worker=1, step=4, verb="view", obj="F", target="/f", status="verified")
    bad = sw._lists(Facts("http://h/", lists=[L("Recently Viewed", [("F", "/f"), ("E", "/e"), ("A", "/a"),
                                                                      ("C", "/c")])]), 5)
    assert [x.subject for x in bad] == ["Recently Viewed|-Chapter 2"]


def test_own_favourite_missing_bs01():
    sw = sweeper()
    sw.mem.add_event(worker=1, step=1, verb="favourite", obj="Shelf", target="/shelves/shelf", status="verified")
    v = sw._lists(Facts("http://h/favourites", lists=[L("My Favourites", [("Book", "/books/book"), ("Page", "/p")])]), 3)
    assert [x.rule for x in v] == ["R07"]
    other = sweeper(2)  # personal list: another worker's favourites do not count
    other.mem.events = sw.mem.events
    assert other._lists(Facts("http://h/favourites", lists=[L("My Favourites", [("Book", "/books/book")])]), 3) == []


def test_ages_across_pages_bs10():
    sw = sweeper()
    f1 = Facts("http://h/books", times=[{"text": "10 days ago", "context": "Updated 10 days ago", "item": "http://h/books/book1"}])
    f2 = Facts("http://h/books/book1", times=[{"text": "2 days ago", "context": "Updated 2 days ago by Admin", "item": ""}])
    assert sw._ages(f1, 1) == []
    assert [v.rule for v in sw._ages(f2, 2)] == ["R08"]


def test_toggle_count_f05_and_rejected_input():
    sw = sweeper()
    obs = Observation("http://h/", "", [], "", "")
    sw.pre = {"click": {"number": 3, "text": "3", "cls": "btn ion-heart", "item": "How to train", "submit": False}}
    sw.post = {"number": 3}
    sw.writes = [{"method": "POST", "path": "/api/articles/a/favorite", "status": 200}]
    e = sw.mem.add_event(worker=1, step=1, verb="favourite", obj="How to train", url="http://h/", due=3)
    v = sw._effects(e, Facts("http://h/"), [{"do": "click", "url_after": "http://h/"}], obs)
    assert [x.rule for x in v] == ["I-toggle"] and e.status == "conflict"
    sw.post = {"number": 4}
    e2 = sw.mem.add_event(worker=1, step=2, verb="favourite", obj="Other", url="http://h/", due=4)
    assert sw._effects(e2, Facts("http://h/"), [], obs) == [] and e2.status == "verified"
    sw.writes = [{"method": "POST", "path": "/books", "status": 422}]
    e3 = sw.mem.add_event(worker=1, step=3, verb="create", obj="", url="http://h/create-book", due=5)
    assert sw._effects(e3, Facts("http://h/create-book"), [], obs) == [] and e3.status == "unknown"


def test_link_text_vs_destination_bs12():
    sw = sweeper()
    sw.last = Facts("http://h/books/book2", lists=[L("Pages", [("Page 3", "/books/book2/page/page-1"), ("Page 2", "/books/book2/page/page-2")])])
    obs = Observation("http://h/books/book2", "", [], "", "")
    done = [{"do": "click", "el": '[5] a "Page 3" href=/books/book2/page/page-1'}]
    v = sw._link_vs_dest(obs, done, Facts("http://h/books/book2/page/page-1", h1="Page 1", title="Page 1"))
    assert [x.rule for x in v] == ["R10"]
    assert sw._link_vs_dest(obs, done, Facts("http://h/books/book2/page/page-1", h1="Page 3")) == []


def test_pagination_noop_f09():
    sw = sweeper()
    items = [("A1", "/a1"), ("A2", "/a2"), ("A3", "/a3")]
    sw.last = Facts("http://h/", lists=[L("Global Feed", items)])
    sw.pre = {"click": {"pager": False}}  # D55 P4: a number outside a pager is a count (Conduit's heart '0')
    assert sw._pagination([{"do": "click", "el": '[11] button "0"'}], Facts("http://h/", lists=[L("Global Feed", items)])) == []
    sw.pre = {"click": {"pager": True}}
    assert [v.rule for v in sw._pagination([{"do": "click", "el": '[30] a "2"'}],
                                           Facts("http://h/", lists=[L("Global Feed", items)]))] == ["R11"]
    assert sw._pagination([{"do": "click", "el": '[30] a "2"'}],
                          Facts("http://h/", lists=[L("Global Feed", [("B1", "/b1"), ("B2", "/b2"), ("B3", "/b3")])])) == []


def test_suspect_needs_both_quotes_on_seen_pages():
    sw = sweeper()
    sw.mem.remember_page(1, "http://h/a", "Created Content: 2 Chapters")
    f = Facts("http://h/b", text="Recently Created Chapters: C1 C2 Custom Chapter Title")
    assert [v.rule for v in sw._suspect({"a": "2 Chapters", "b": "Custom Chapter Title", "why": "3 listed"}, f)] == ["R15"]
    assert sw._suspect({"a": "2 Chapters", "b": "made up quote", "why": "x"}, f) == []


# ---------------------------------------------------------------- grounded LLM checks (R14)
def test_grounded_checks_drop_design_guesses_i43():
    obs = Observation("http://h/books", "", [], "", "Books Create New Book")
    done = [{"do": "click", "el": '[7] a "New Page" href=/books/x/create-page', "value": None}]
    exps = [{"check": "route", "route": "/books/*/page/*"}, {"check": "shows", "text": "Create New Page", "where": "now"},
            {"check": "shows", "text": "Atlas Q7", "where": "reload"}, {"check": "count", "id": "3", "delta": 1}]
    kept = ground_expectations(exps, obs, done, ["Atlas Q7"], [])
    assert [e["check"] for e in kept] == ["route", "shows", "count"]
    assert kept[0]["route"] == "/books/x/create-page" and kept[1]["text"] == "Atlas Q7"
    # I41: the model's '*' is a wildcard ('/tags*' meant the tag search, shape '/tags?search')
    assert eval_route("/tags*", "http://h/tags?search=x")[0] and eval_route("/search*", "http://h/search")[0]
    assert eval_route("/books/*", "http://h/books/b-1")[0] and not eval_route("/shelves", "http://h/books")[0]


# ---------------------------------------------------------------- AUDIT_JS on fixture HTML (browser)
PROFILE = """<html><body><nav><a href="/">Home</a><a href="/books">Books</a><a href="/shelves">Shelves</a></nav>
<main><h1>Admin</h1><div><span>2 Chapters</span><span>Joined 10 days ago</span></div>
<h3>Recently Created Chapters</h3><div class="entity-list">
 <a class="entity-list-item" href="/books/b/chapter/c1"><h4>Chapter 1</h4><span>Updated 3 days ago</span></a>
 <a class="entity-list-item" href="/books/b/chapter/c2"><h4>Chapter 2</h4><span>Updated 3 days ago</span></a>
 <a class="entity-list-item" href="#"><h4>Custom Chapter Title</h4></a></div>
<p>Total: NaN</p><pre>undefined in code is fine</pre></main></body></html>"""


def test_audit_js_reads_lists_counts_times_and_junk():
    pw_api = pytest.importorskip("playwright.async_api")

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            page = await browser.new_page()
            await page.set_content(PROFILE)

            class S:
                pass
            s = S()
            s.page = page
            facts = await audit(s)
            await browser.close()
            return facts

    f = asyncio.run(go())
    lists = {L_["heading"]: L_ for L_ in f.lists}
    chapters = lists["Recently Created Chapters"]
    assert [i["name"] for i in chapters["items"]] == ["Chapter 1", "Chapter 2", "Custom Chapter Title"]
    assert not chapters["nav"] and any(L_["nav"] for L_ in f.lists)
    assert any(c["unit"] == "Chapters" and c["n"] == 2 for c in f.counts)
    assert any(t["text"].startswith("Updated 3 days ago") or "3 days ago" in t["text"] for t in f.times)
    assert f.h1 == "Admin"
    rules = {v.rule for v in rule_dead_items(f) + rule_counts(f) + rule_junk(f.plain, set())}
    assert rules == {"R03", "R04", "R01"}
    assert all(v.subject != "undefined" for v in rule_junk(f.plain, set()))  # text in <pre> is skipped


ARTICLE = """<html><body><div class="feed-toggle"><ul class="nav nav-pills outline-active">
 <li class="nav-item"><a class="nav-link" href="/">Your Feed</a></li>
 <li class="nav-item"><a class="nav-link active" href="/">Global Feed</a></li></ul></div>
<div class="feed"><div class="article-preview"><a class="preview-link" href="/article/a"><h1>Article A</h1></a></div>
<div class="article-preview"><a class="preview-link" href="/article/b"><h1>Article B</h1></a></div></div>
<div class="card"><div class="card-block"><p>first comment body</p></div>
 <div class="card-footer"><a class="comment-author" href="/profile/worker02">worker02</a><span>October 27, 2026</span>
 <span class="mod-options"><i id="t1" class="ion-trash-a" data-wt-id="t1">x</i></span></div></div>
<div class="card"><div class="card-block"><p>second comment body</p></div>
 <div class="card-footer"><a class="comment-author" href="/profile/worker02">worker02</a><span>October 27, 2026</span>
 <span class="mod-options"><i class="ion-trash-a" data-wt-id="t2">x</i></span></div></div></body></html>"""


def test_tab_bar_is_no_list_and_delete_item_is_the_whole_card():
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.consistency import PRE_JS

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            page = await browser.new_page()
            await page.set_content(ARTICLE)

            class S:
                pass
            s = S()
            s.page = page
            facts = await audit(s)
            pre = await page.evaluate(PRE_JS, {"click": "t1", "fill": None})
            await browser.close()
            return facts, pre

    f, pre = asyncio.run(go())
    # D54: Conduit's 'Your Feed | Global Feed' tabs (Bootstrap .nav) made R09 false alarms on every revisit
    assert all(i["name"] not in ("Your Feed", "Global Feed") for L_ in f.content_lists() for i in L_["items"])
    assert any(L_["heading"] == "tab: Global Feed" for L_ in f.content_lists())  # the feed is named by its tab
    # D54: the trash icon sits in .card-footer (author and date, shared by both comments); the item is the card
    assert pre["click"]["item"].startswith("first comment body")
    assert "second comment body" in pre["page"]
