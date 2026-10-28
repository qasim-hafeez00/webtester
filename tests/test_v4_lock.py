"""Oracles added before the v4 lock (D50): R13 access, R16/R17 input mutation, G2 reload invariance.

Pure tests over page facts, plus one browser test that drives all three probes against a small
fake app served by Playwright routing (headless Chromium, no app container needed).
"""

import asyncio
from urllib.parse import urlsplit

import pytest

from webtester.config import Account
from webtester.consistency import (Facts, SweepState, Sweeper, apply_template, audit, edit_template, field_label,
                                   id_segments, long_value, mutation_plan, view_diff)
from webtester.memory import RunMemory


def L(heading, items, nav=False):
    return {"heading": heading, "nav": nav,
            "items": [{"name": n, "href": h, "abs": ("http://h" + h) if h and h.startswith("/") else "", "text": n}
                      for n, h in items]}


def test_edit_templates_from_the_items_own_ids():
    assert id_segments("http://h/article/how-to-x-1") == ["how-to-x-1"]
    t = edit_template("http://h/article/how-to-x-1", "http://h/editor/how-to-x-1")
    assert t == ("/editor/{0}", "/editor/*")
    assert apply_template(t[0], "http://h/article/welcome-2") == "http://h/editor/welcome-2"
    # BookStack-style nested ids; an edit link that uses none of the page's ids edits something else
    t2 = edit_template("http://h/books/b-1/page/p-2", "http://h/books/b-1/page/p-2/edit")
    assert apply_template(t2[0], "http://h/books/b-9/page/p-8") == "http://h/books/b-9/page/p-8/edit"
    assert edit_template("http://h/article/how-to-x-1", "http://h/comments/7/edit") is None
    assert apply_template("/editor/{0}", "http://h/settings") is None


def test_reload_diff_phantom_count_and_volatile():
    items = [("A", "/a"), ("B", "/b"), ("C", "/c"), ("D", "/d")]
    a = Facts("http://h/books", h1="Books", lists=[L("Books", items)],
              counts=[{"n": 4, "unit": "Books", "text": "4 Books"}])
    same = Facts("http://h/books", h1="Books", lists=[L("Books", list(reversed(items)))],
                 counts=[{"n": 4, "unit": "Books", "text": "4 Books"}])
    assert view_diff(a, same, [], set()) == []  # order may change
    b = Facts("http://h/books", h1="Books", lists=[L("Books", items + [("Phantom", "#")])],
              counts=[{"n": 5, "unit": "Books", "text": "5 Books"}])
    assert sorted(v.subject for v in view_diff(a, b, [], set())) == ["Books|+Phantom", "count|book"]
    ev = RunMemory().add_event(worker=2, step=1, verb="create", obj="Phantom", status="verified")
    assert view_diff(a, b, [ev], set()) == []  # another worker created it meanwhile (counts skipped too)
    vol = set()
    c = Facts("http://h/books", lists=[L("Books", [("W", "/w"), ("X", "/x"), ("Y", "/y"), ("Z", "/z")])])
    assert view_diff(a, c, [], vol) == [] and ("/books", "books") in vol  # rotating content


def test_mutation_plan_skips_password_and_search_forms():
    body = {"do": "fill", "ekey": "textarea||||Write a comment...|", "value": "Nice post", "el": "[3] textarea"}
    post = {"do": "click", "ekey": "button|submit|||Post Comment|", "el": '[4] button "Post Comment"'}
    name, long_ = mutation_plan([body, post], "Nice post")
    assert name is body and long_ is body and field_label(body) == "Write a comment..."
    pw = {"do": "fill", "ekey": "input|password|||Password|", "value": "x", "el": "[2] input[password]"}
    assert mutation_plan([body, pw, post], "Nice post") is None
    search = {"do": "fill", "ekey": "input|text|||Search|", "value": "x", "el": '[2] input label="Search"'}
    assert mutation_plan([search, post], "x") is None
    assert mutation_plan([body], "Nice post") is None  # no submit in the same step
    assert len(long_value("Nice post", 300)) == 300 and long_value("Nice post", 300).startswith("Nice post ")


# The fake app: an article another user wrote that offers Edit but whose editor sends this user
# away (the shape of Conduit F07), the user's own article (its editor works), an article that
# hides Edit while its editor opens anyway, a comment form whose server fails on long input and
# accepts spaces-only, and a list that gains an item when it is opened again.
COMMENT_FORM = """<h1>New comment</h1><form onsubmit="return false">
<textarea aria-label="Body" id="b"></textarea><button type="button" id="go">Post</button></form>
<div id="out"></div><script>
document.getElementById('go').onclick = async () => {
  const r = await fetch('/api/comments', {method: 'POST', body: document.getElementById('b').value});
  document.getElementById('out').innerText = r.status === 422 ? "body can't be blank" : (r.ok ? 'Posted' : 'Error');
};</script>"""


def _fake_app():
    hits = {"list": 0}

    def page(body):
        return {"status": 200, "content_type": "text/html",
                "body": f"<html><body><nav><a href='/'>Home</a></nav><main>{body}</main></body></html>"}

    def editor(title):
        return page(f"<h1>Editor</h1><form><input name='title' value='{title}'><textarea>text</textarea></form>")

    def respond(path, method, data):
        if path == "/":
            return page("<h1>Home</h1>")
        if path == "/article/my-post-1":
            return page("<h1>My Post 1</h1><a class='btn' href='/editor/my-post-1'>Edit Article</a>")
        if path == "/editor/my-post-1":
            return editor("My Post 1")
        if path == "/article/alice-post-2":
            return page("<h1>Alice Post 2</h1><a class='btn' href='/editor/alice-post-2'>Edit Article</a>")
        if path == "/editor/alice-post-2":  # a client-side redirect, as Conduit's router does (a fulfilled
            return page("<script>location.replace('/')</script>")  # 302 would leave Playwright's routing)
        if path == "/article/bob-post-3":
            return page("<h1>Bob Post 3</h1><p>by bob</p>")
        if path == "/editor/bob-post-3":
            return editor("Bob Post 3")
        if path == "/post/new-1":
            return page(COMMENT_FORM)
        if path == "/api/comments" and method == "POST":
            body = data or ""
            if len(body) > 280:
                return {"status": 500, "body": "boom"}
            return {"status": 422 if body == "" else 201, "body": "{}"}
        if path == "/list-1":
            hits["list"] += 1
            names = ["Alpha", "Beta", "Gamma", "Delta"] + (["Phantom"] if hits["list"] > 1 else [])
            lis = "".join(f"<li class='it'><a href='/i/{n.lower()}-1'>{n}</a></li>" for n in names)
            return page(f"<h1>Items</h1><h2>Items</h2><ul>{lis}</ul>")
        return {"status": 404, "content_type": "text/html", "body": "<html><body><h1>Not found</h1></body></html>"}

    async def handler(route):
        req = route.request
        await route.fulfill(**respond(urlsplit(req.url).path, req.method, req.post_data))
    return handler


def test_probes_r13_r16_r17_g2_on_a_fake_app():
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession
    from webtester.config import AppConfig, RunConfig

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            s = BrowserSession(browser, RunConfig(app=AppConfig("fake", "http://app.test"), settle_ms=50), 1)
            await s.start()
            await s.context.route("http://app.test/**", _fake_app())
            sw = Sweeper(SweepState(), 1, Account("worker01", "w@x", "p"))
            out = {}

            async def visit(path):
                await s.goto(path)
                sw.budget = 2
                return await audit(s)

            # R13: a refusal before any evidence is held; the own article's editor works -> released
            out["held"] = await sw._access(s, await visit("/article/alice-post-2"))
            out["released"] = await sw._access(s, await visit("/article/my-post-1"))
            out["hidden"] = await sw._access(s, await visit("/article/bob-post-3"))
            # R16/R17: the comment form again with empty, spaces-only and long bodies
            await s.goto("/post/new-1")
            obs = await s.observe()
            box = next(e for e in obs.elements if e.tag == "textarea")
            btn = next(e for e in obs.elements if e.text == "Post")
            done = [{"do": "fill", "ekey": box.key(), "nth": 0, "value": "hello there", "el": box.describe(), "ok": True},
                    {"do": "click", "ekey": btn.key(), "nth": 0, "value": None, "el": btn.describe(), "ok": True}]
            ev = sw.mem.add_event(worker=1, step=5, verb="create", obj="hello there", url=obs.url, written=True)
            out["mutate"] = await sw._mutate(s, obs, done, ev, 5)
            out["again"] = await sw._mutate(s, obs, done, ev, 6)  # one campaign per form
            # G2: the list gains an item when opened again
            home = await s.observe()
            facts = await visit("/list-1")
            sw.writes = []
            nav = [{"do": "navigate", "value": "/list-1", "ekey": None, "ok": True}]
            out["reload"] = await sw._reload(s, home, nav, facts)
            out["events"] = [e.source for e in sw.mem.events]
            await s.close()
            await browser.close()
            return out

    out = asyncio.run(go())
    assert out["held"] == []
    assert [(v.rule, v.subject) for v in out["released"]] == [("R13", "offered|/editor/*")]
    assert [(v.rule, v.subject) for v in out["hidden"]] == [("R13", "hidden|/editor/*")]
    assert sorted((v.rule, v.subject) for v in out["mutate"]) == [("R16", "long|Body"), ("R17", "blank|Body")]
    assert out["again"] == []
    assert [(v.rule, v.subject) for v in out["reload"]] == [("G2", "Items|+Phantom")]
    assert out["events"].count("mutation") == 1  # the accepted spaces-only copy is in the ledger
