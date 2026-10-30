"""D60: the v5 probes against a served in-memory app, once with faults and once without.

The app (a tiny book list) runs inside Playwright's router: list with pager and CSV export, item pages with
tags, an edit form, a delete button behind confirm(), a search page. With `faulty=True`:
  - an unchanged save drops the item's tags (R21b), the CSV export lists one row fewer (R37),
  - page 2 repeats an item of page 1 (R39), a cancelled delete still deletes (R53),
  - opening the list address again with ?sort=name shows another order (R62), search misses one book (R23).
The clean app must raise none of these. Steps are driven by hand (no LLM), as the gate's replays do.
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState, Sweeper

PROBE_RULES = {"R21b", "R37", "R39", "R53", "R62", "R23"}


class App:
    def __init__(self, faulty: bool):
        self.faulty = faulty
        self.books = {1: {"name": "Atlas Book", "tags": ["maps", "travel"]}, 2: {"name": "Borealis Book", "tags": ["sky"]},
                      3: {"name": "Cygnus Book", "tags": ["birds"]}, 4: {"name": "Draco Book", "tags": ["myth"]}}
        self.sort_calls = 0

    def page(self, body: str, title: str = "Books") -> str:
        return (f"<html><head><title>{title}</title></head><body><nav><a href='/books'>Books</a></nav>"
                f"<form action='/search'><input type='search' name='q' placeholder='Search'></form>{body}</body></html>")

    def list_page(self, q: dict) -> str:
        ids = sorted(self.books)
        if q.get("sort") == ["name"]:
            self.sort_calls += 1
            if self.faulty and self.sort_calls > 1:  # the address does not restore the list
                ids = list(reversed(ids))
        page = int((q.get("page") or ["1"])[0])
        size = 2
        chunk = ids[(page - 1) * size: page * size]
        if self.faulty and page == 2:
            chunk = [ids[0]] + chunk[1:]  # page 2 repeats an item of page 1
        items = "".join(f"<li class='book'><a href='/books/{i}'>{self.books[i]['name']}</a></li>" for i in chunk)
        pager = "".join(f"<a href='/books?page={n}'>{n}</a> " for n in (1, 2))
        return self.page(f"<h1>Books</h1><p>Showing {(page - 1) * size + 1}-{(page - 1) * size + len(chunk)} of "
                         f"{len(ids)}</p><h2>All books</h2><ul class='books'>{items}</ul>"
                         f"<nav class='pagination'>{pager}</nav><a href='/books.csv'>Export CSV</a>")

    def item_page(self, i: int) -> str:
        b = self.books[i]
        tags = "".join(f"<li class='tag'><a href='/tags/{t}'>{t}</a></li>" for t in b["tags"])
        return self.page(f"<h1>{b['name']}</h1><h2>Tags</h2><ul class='tags'>{tags}</ul>"
                         f"<a href='/books/{i}/edit'>Edit</a> <button id='del' onclick=\"if (confirm('Delete "
                         f"&quot;{b['name']}&quot;?') || {str(self.faulty).lower()}) fetch('/books/{i}', "
                         f"{{method: 'DELETE'}})\">Delete</button>", b["name"])

    def edit_page(self, i: int) -> str:
        b = self.books[i]
        return self.page(f"<h1>Edit {b['name']}</h1><form method='post' action='/books/{i}'>"
                         f"<label>Name <input name='name' value='{b['name']}'></label>"
                         f"<input type='hidden' name='tags' value='{','.join(b['tags'])}'>"
                         f"<button type='submit'>Save</button></form>")

    async def route(self, route):
        req = route.request
        u = urlsplit(req.url)
        path, q = u.path, parse_qs(u.query)
        m = re.fullmatch(r"/books/(\d+)(/edit)?", path)
        html, status, ctype = None, 200, "text/html"
        if path == "/books" and req.method == "GET":
            html = self.list_page(q)
        elif path == "/books.csv":
            rows = sorted(self.books)[: -1 if self.faulty else None]
            html, ctype = "name\n" + "\n".join(self.books[i]["name"] for i in rows) + "\n", "text/csv"
        elif path == "/search":
            term = (q.get("q") or [""])[0].lower()
            hits = [i for i, b in self.books.items() if term and term in b["name"].lower()]
            if self.faulty:
                hits = [i for i in hits if i != 2]
            items = "".join(f"<li class='hit'><a href='/books/{i}'>{self.books[i]['name']}</a></li>" for i in hits)
            html = self.page(f"<h1>Search results</h1><p>{len(hits)} results found</p><ul class='hits'>{items}</ul>")
        elif m and req.method == "GET":
            i = int(m.group(1))
            if i not in self.books:
                status, html = 404, self.page("<h1>Not found</h1>")
            else:
                html = self.edit_page(i) if m.group(2) else self.item_page(i)
        elif m and req.method == "POST":
            i = int(m.group(1))
            form = parse_qs(req.post_data or "")
            self.books[i]["name"] = (form.get("name") or [self.books[i]["name"]])[0]
            if self.faulty:
                self.books[i]["tags"] = []  # an unchanged save drops the tags
            await route.fulfill(status=303, headers={"Location": f"/books/{i}"})
            return
        elif m and req.method == "DELETE":
            self.books.pop(int(m.group(1)), None)
            await route.fulfill(status=204)
            return
        else:
            status, html = 404, self.page("<h1>Not found</h1>")
        await route.fulfill(status=status, content_type=ctype, body=html)


def sweep(faulty: bool):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    app = App(faulty)

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), settle_ms=300, capture_evidence=True,
                            seed_copies=0, poll_deadline_s=0.5)
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            await s.context.route("http://h/**", app.route)
            st = SweepState()
            sw = Sweeper(st, 1, None)
            sw.owned_paths.add("/books/1")  # R21b and R53 probe only items the run created (or controlled mode)
            sigs, step = [], 0
            plan = ["/books?sort=name", "/books", "/books/1", "/books/1", "/books/1", "/books/1", "/books", "/books",
                    "/books", "/books/1", "/books/2", "/books/1"]
            try:
                for path in plan:
                    step += 1
                    await s.goto(path)
                    obs = await s.observe()
                    done = [{"do": "navigate", "id": None, "value": path, "el": None, "ok": True, "ekey": None}]
                    await sw.before(s, obs, [])
                    await sw.actions_done(s)
                    sigs += await sw.after(s, obs, done, step)
            finally:
                await s.close()
                await browser.close()
            return sigs, st

    return asyncio.run(go())


def test_probes_find_the_faults():
    sigs, st = sweep(True)
    got = {x.detail["rule"] for x in sigs}
    errors = [r for r in st.checks.records() if r["why"].startswith("error:")]
    assert not errors, errors
    assert PROBE_RULES <= got, (sorted(PROBE_RULES - got), json.dumps(st.p5.used))


def test_probes_quiet_on_the_clean_app():
    sigs, st = sweep(False)
    got = {x.detail["rule"] for x in sigs}
    assert not (PROBE_RULES & got), [x.message for x in sigs if x.detail["rule"] in PROBE_RULES]
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
