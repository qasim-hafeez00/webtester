"""Harness v5 (D55): the fixes for Night 3's false alarms (I49) and missed faults.

Browser tests read static snapshots of BookStack 25.2.1 with every injected fault on
(tests/fixtures/bookstack_*_faulty.html, made by tests/fixtures/make_bookstack_fixtures.py) and
the same pages with the fault's effect removed, so every rule is tested on the faulty and the
clean page. Pages are served at http://h/... so their links resolve. Pure tests use hand-made
facts, like tests/test_v4.py.
"""

import asyncio
import re
from pathlib import Path

import pytest

from webtester.browser import Observation
from webtester.config import Account
from webtester.consistency import (TOGGLE_JS, Facts, SweepState, Sweeper, audit, explained, rule_counts,
                                   rule_dead_items, shown)
from webtester.memory import Event

FIX = Path(__file__).parent / "fixtures"
PHANTOM = re.compile(r'<a [^>]*data-entity-id="(custom-id|999)"[^>]*>.*?</a>', re.S)


def page(name: str, clean: bool = False) -> str:
    html = (FIX / f"bookstack_{name}_faulty.html").read_text(encoding="utf-8")
    if clean:
        html = PHANTOM.sub("", html).replace("1 year ago", "15 hours ago").replace("2 days ago", "15 hours ago")
    return html


def L(heading, items):
    return {"heading": heading, "nav": False,
            "items": [{"name": n, "href": h, "abs": ("http://h" + h) if h and h.startswith("/") else "", "text": n,
                       "link_text": n, "links": []} for n, h in items]}


def sweeper(worker=1):
    return Sweeper(SweepState(), worker, Account("worker01", "w@x", "p"))


class FakeSession:
    """What the probes need from a BrowserSession."""

    def __init__(self, ctx, page_):
        self.context, self.page = ctx, page_

        class Cfg:
            settle_ms = 50
            max_elements = 200
        self.cfg = Cfg()

    def in_scope(self, url):
        return url.startswith("http://h/")


def with_pages(pages: dict, fn):
    """Run `fn(session)` with http://h/<path> serving pages[path]."""
    pw_api = pytest.importorskip("playwright.async_api")

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            ctx = await browser.new_context()

            async def serve(route):
                path = "/" + route.request.url.split("http://h/", 1)[1].split("#")[0]
                body = pages.get(path) or pages.get(path.split("?")[0])
                if route.request.method != "GET":
                    await route.fulfill(status=200, body="{}", content_type="application/json")
                elif body is None:
                    await route.fulfill(status=404, body="<html><body><h1>Not Found</h1></body></html>",
                                        content_type="text/html")
                else:
                    await route.fulfill(status=200, body=body, content_type="text/html")
            await ctx.route("http://h/**", serve)
            pg = await ctx.new_page()
            try:
                return await fn(FakeSession(ctx, pg))
            finally:
                await browser.close()

    return asyncio.run(go())


async def facts_of(s, path):
    await s.page.goto("http://h" + path)
    return await audit(s)


# ---------------------------------------------------------------- lists and links on real BookStack pages
def test_profile_activity_feed_is_one_list_of_objects_and_phantoms_bs05_bs07():
    async def fn(s):
        return await facts_of(s, "/user/admin")

    f = with_pages({"/user/admin": page("profile")}, fn)
    feeds = [L_ for L_ in f.content_lists() if L_["heading"] == "Recent Activity"]
    assert len(feeds) == 1 and len(feeds[0]["items"]) >= 10  # D55 A1: one feed, not one 'list' per entry
    assert "Admin" not in {i["name"] for i in feeds[0]["items"]}  # named by the object, not the author (A5)
    dead = {v.subject.split("|")[1] for v in rule_dead_items(f)}
    assert {"Custom Book Title", "Custom Chapter Title", "Shelf 2"} <= dead  # BS05, BS06 and now BS07 (A3)
    clean = with_pages({"/user/admin": page("profile", clean=True)}, fn)
    assert rule_dead_items(clean) == []


def test_search_phantom_joins_the_results_bs08():
    async def fn(s):
        return await facts_of(s, "/search?term=book")

    f = with_pages({"/search": page("search")}, fn)
    rules = {v.rule for v in rule_dead_items(f) + rule_counts(f)}
    assert {"R03", "R04"} <= rules  # 'Some Page' links nowhere; '3 total results found' but 4 listed (A1, A4)
    clean = with_pages({"/search": page("search", clean=True)}, fn)
    assert rule_dead_items(clean) == [] and rule_counts(clean) == []


def test_hidden_placeholder_link_is_no_list_item_i49():
    html = """<html><body><h3>Default Page Template</h3><div class="list">
      <div class="row"><a href="/books/a">Book A</a></div><div class="row"><a href="/books/b">Book B</a></div>
      <div class="row"><span>Select a page</span><a hidden href="link">#,</a></div></div></body></html>"""

    async def fn(s):
        return await facts_of(s, "/settings")

    f = with_pages({"/settings": html}, fn)
    hrefs = [i["href"] for L_ in f.content_lists() for i in L_["items"]]
    assert "link" not in hrefs  # D55 P2: BookStack's page picker anchor (3 R02 false alarms)


# ---------------------------------------------------------------- ages (BS09, BS10, BS11)
def run_ages(paths: list[tuple[str, str]], clean=False):
    async def fn(s):
        sw = Sweeper(SweepState(), 1, Account("worker01", "w@x", "p"))
        out = []
        for i, (path, name) in enumerate(paths):
            out += sw._ages(await facts_of(s, path), i + 1)
        return out

    pages = {path: page(name, clean) for path, name in paths}
    return with_pages(pages, fn)


def test_book1_activity_one_year_old_vs_its_creation_bs09():
    v = run_ages([("/books/book1", "book"), ("/user/admin", "profile")])
    assert any(x.subject.startswith("views|/books/book1|created") or x.rule == "R18" for x in v)
    clean = run_ages([("/books/book1", "book"), ("/user/admin", "profile")], clean=True)
    assert [x for x in clean if "/books/book1" in x.subject] == []


def test_book_page_activity_older_than_its_items_bs10():
    v = run_ages([("/books/book1", "book")])
    # 'Admin created book Book1 2 days ago' in the activity, 'Created 15 hours ago' in Details
    assert any(x.rule in ("R08", "R18") and "/books/book1" in x.subject for x in v)
    assert run_ages([("/books/book1", "book")], clean=True) == []


def test_page_details_vs_dashboard_activity_bs11():
    v = run_ages([("/", "dashboard"), ("/books/book/page/page-template", "page")])
    assert any("page-template" in x.subject for x in v)
    clean = run_ages([("/", "dashboard"), ("/books/book/page/page-template", "page")], clean=True)
    assert [x for x in clean if "page-template" in x.subject] == []


def test_own_new_item_reads_days_old_bs10_created():
    sw = sweeper()
    e = sw.mem.add_event(worker=1, step=1, verb="create", obj="Shelf Q", target="/shelves/shelf-q", status="verified")
    ent = sw.mem.entity("/shelves/shelf-q")
    ent.touched = e.t
    f = Facts("http://h/shelves/shelf-q", times=[{"text": "2 days ago", "context": "Created 2 days ago by Worker 01",
                                                  "item": "http://h/user/worker-01", "item_name": "Worker 01"}])
    assert [v.rule for v in sw._ages(f, 3)] == ["R08"]  # D55 A7
    ok = Facts("http://h/shelves/shelf-q", times=[{"text": "1 minute ago", "context": "Created 1 minute ago by Worker 01",
                                                   "item": "http://h/user/worker-01", "item_name": "Worker 01"}])
    assert sweeper()._ages(ok, 3) == []


# ---------------------------------------------------------------- intents (P1, P7, P9, A8)
def step(sw, done, intent=None, pre=None, writes=(), url="http://h/x", after_url=None, text=""):
    sw.pre = pre or {"click": {}}
    sw.writes = list(writes)
    obs = Observation(url, "", [], "", "")
    facts = Facts(after_url or url, text=text)
    return sw._event(obs, done, 1, intent, facts, after_url or url)


def test_login_intent_is_no_create_i49():
    sw = sweeper()
    done = [{"do": "fill", "el": '[7] input[text] label="Email" form#0', "value": "w@x", "ok": True},
            {"do": "fill", "el": '[8] input[password] label="Password" form#0', "value": "p", "ok": True},
            {"do": "click", "el": '[9] button "Sign in" form#0', "ok": True}]
    e = step(sw, done, {"verb": "create", "object": "session", "type": "auth"},
             {"click": {"submit": True}, "form_password": True}, [{"method": "POST", "path": "/login", "status": 302}])
    assert e.verb == "login" and e.obj == ""


def test_create_object_is_the_typed_value_not_the_intent_words_i49():
    sw = sweeper()
    done = [{"do": "fill", "el": '[15] textarea label="Write a comment..." form#0', "value": "<b>test comment</b> !@#", "ok": True},
            {"do": "click", "el": '[16] button "Post Comment" form#0', "ok": True}]
    e = step(sw, done, {"verb": "create", "object": "special comment"}, {"click": {"submit": True}},
             [{"method": "POST", "path": "/api/articles/a/comments", "status": 200}])
    assert e.obj == "<b>test comment</b> !@#"
    assert shown(e.obj, "worker01 test comment !@# October 27") and shown(e.obj, "<b>test comment</b> !@#")


def test_checkbox_filter_has_no_term_and_nav_link_is_no_toggle():
    sw = sweeper()
    done = [{"do": "check", "el": '[19] input[checkbox] label="Viewed by me"', "ok": True},
            {"do": "click", "el": '[29] button "Update Search" form#3', "ok": True}]
    e = step(sw, done, {"verb": "filter", "object": "Viewed by me"}, {"click": {"submit": True}})
    assert e.obj == ""  # D55 P7: no I-filter on a checkbox label
    nav = [{"do": "click", "el": '[7] a "Favorited Posts" href=/profile/alice/favorites', "ok": True}]
    e2 = step(sw, nav, None, {"click": {"link": True, "cls": "nav-link"}}, url="http://h/profile/alice",
              after_url="http://h/profile/alice/favorites")
    assert e2 is None or e2.verb == "view"  # D55 P9


def test_heart_icon_names_the_control_f05():
    sw = sweeper()
    done = [{"do": "click", "el": '[11] button "0"', "ok": True}]
    e = step(sw, done, None, {"click": {"cls": "btn btn-outline-primary ion-heart", "number": 0, "own_number": True}},
             [{"method": "POST", "path": "/api/articles/a/favorite", "status": 200}])
    assert e.verb == "favourite"  # D55 A8


def test_submit_with_5xx_is_worded_as_a_failed_write():
    sw = sweeper()
    sw.last = Facts("http://h/article/a", text="same page")
    obs = Observation("http://h/article/a", "", [], "", "")
    sw.pre = {"click": {"submit": True}, "form_valid": True}
    sw.writes = [{"method": "POST", "path": "/api/articles/a/comments", "status": 500}]
    e = sw.mem.add_event(worker=1, step=1, verb="create", obj="long", fields={"c": "long"}, url=obs.url, due=3)
    v = sw._effects(e, Facts("http://h/article/a", text="same page"), [{"do": "click"}], obs)
    assert [x.rule for x in v] == ["I-submit"] and "HTTP 500" in v[0].message
    sw.pre = {"click": {"submit": True}, "form_valid": True, "form_get": True}
    sw.writes = []
    e2 = sw.mem.add_event(worker=1, step=2, verb="edit", obj="", fields={"filters[created_before]": "2023-01-01"},
                          url=obs.url, due=4)
    assert sw._effects(e2, Facts("http://h/article/a", text="same page"), [{"do": "click"}], obs) == []  # P7: GET form


# ---------------------------------------------------------------- lists against memory (P3, A3, A4, P6)
def test_activity_feed_removals_and_renames_are_explained():
    sw = sweeper()
    acts = [("Shelf", "/shelves/shelf"), ("Page", "/p"), ("Book", "/b")]
    sw._lists(Facts("http://h/user/admin", lists=[L("Recent Activity", acts)]), 1)
    assert sw._lists(Facts("http://h/user/admin", lists=[L("Recent Activity", acts[1:] + [("New", "/n")])]), 5) == []
    rn = Event(0, 2, 3, "edit", obj="Shelf Q7", fields={'input[text] label="Name" value="Shelf" form#3': "Shelf Q7"})
    assert explained([rn], "Shelf", "")  # renamed from 'Shelf' (D55 P3)


def test_two_item_list_dead_item_and_heading_count():
    f = Facts("http://h/user/admin", lists=[L("Recently Created Shelves", [("Shelf", "/shelves/shelf"), ("Shelf 2", "#")])])
    assert [v.rule for v in rule_dead_items(f)] == ["R03"]
    ok = Facts("http://h/x", lists=[L("Shelves", [("Shelf", "/shelves/shelf"), ("Add shelf", "#")])])
    assert rule_dead_items(ok) == []
    s = Facts("http://h/search", counts=[{"n": 3, "unit": "total results found", "text": "3 total results found"}],
              lists=[L("3 total results found", [("Book...", "/books/book1"), ("Book...", "/books/book2"),
                                                 ("Book", "/books/book"), ("Some Page", "#")])])
    assert [v.rule for v in rule_counts(s)] == ["R04"]


def test_tag_link_to_search_results_is_no_r10():
    sw = sweeper()
    sw.last = Facts("http://h/books/b", lists=[L("Tags", [("env", "/search?term=%5Benv%5D")])])
    obs = Observation("http://h/books/b", "", [], "", "")
    done = [{"do": "click", "el": '[15] a "env" href=/search?term=%5Benv%5D'}]
    assert sw._link_vs_dest(obs, done, Facts("http://h/search?term=%5Benv%5D", h1="Search Results")) == []


# ---------------------------------------------------------------- probes (A9, A10)
CONDUIT_HOME = """<html><body><nav class="navbar"><a href="/">Home</a></nav>
<div class="feed-toggle"><ul class="nav nav-pills"><li class="nav-item"><a class="nav-link active" href="/">Your Feed</a></li></ul></div>
<div class="feed"><div class="article-preview"><div class="article-meta"><a href="/profile/dave">dave</a>
 <button class="btn btn-sm btn-outline-primary pull-xs-right"><i class="ion-heart"></i> 0</button></div>
 <a class="preview-link" href="/article/a"><h1>Article A</h1></a></div>
<div class="article-preview"><div class="article-meta"><a href="/profile/dave">dave</a>
 <button class="btn btn-sm btn-outline-primary"><i class="ion-heart"></i> 2</button></div>
 <a class="preview-link" href="/article/b"><h1>Article B</h1></a></div></div></body></html>"""


def test_toggle_probe_picks_the_count_control_not_follow():
    async def fn(s):
        await s.page.goto("http://h/")
        return await s.page.evaluate(TOGGLE_JS)

    c = with_pages({"/": CONDUIT_HOME}, fn)
    assert c and c["number"] == 0 and c["verb"] == "favourite"


def test_feed_item_by_an_unfollowed_author_f08():
    def author(btn):
        return f"<html><body><h4>dave</h4><button class='btn'>{btn} dave</button></body></html>"

    async def fn(s):
        sw = Sweeper(SweepState(), 1, Account("worker01", "w@x", "p"))
        f = await facts_of(s, "/")
        sw._lists(f, 1)
        return await sw._feed_check(s)

    v = with_pages({"/": CONDUIT_HOME, "/profile/dave": author("Follow")}, fn)
    assert [x.rule for x in v] == ["R07c"]
    assert with_pages({"/": CONDUIT_HOME, "/profile/dave": author("Unfollow")}, fn) == []
