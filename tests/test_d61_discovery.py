"""D61: the discovery checks R02s and R20f (runner._discover, runner._check_discovered) against a served site,
and the run-level records safety_of and coverage_of.

The site publishes robots.txt, a sitemap and an RSS feed linked from its home page. With `faulty=True` one
sitemap address answers 404 (R02s) and the feed's newest item links to a page that shows another title (R20f).
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState
from webtester.oracles import FindingStore
from webtester.runner import _check_discovered, _discover, coverage_of, safety_of
from webtester.stategraph import StateGraph


def handler(faulty: bool):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, status: int, body: str, ctype: str = "text/html"):
            b = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            host = f"http://{self.headers['Host']}"
            if self.path == "/":
                self.send(200, '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head>'
                               "<body><h1>Home</h1></body></html>")
            elif self.path == "/robots.txt":
                self.send(200, f"User-agent: *\nAllow: /\nSitemap: {host}/sitemap.xml\n", "text/plain")
            elif self.path == "/sitemap.xml":
                self.send(200, f"<urlset><url><loc>{host}/about</loc></url><url><loc>{host}/old-page</loc></url></urlset>",
                          "application/xml")
            elif self.path == "/feed.xml":
                self.send(200, f"<rss><channel><item><title>Fresh harbour news</title><link>{host}/news/2</link></item>"
                               f"<item><title>Older story</title><link>{host}/news/1</link></item></channel></rss>",
                          "application/rss+xml")
            elif self.path == "/news/2":
                self.send(200, f"<html><body><h1>{'Older story' if faulty else 'Fresh harbour news'}</h1></body></html>")
            elif self.path in ("/about", "/news/1") or (self.path == "/old-page" and not faulty):
                self.send(200, "<html><body><h1>Page</h1></body></html>")
            else:
                self.send(404, "<html><body><h1>Not found</h1></body></html>")

    return H


def run(faulty: bool):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(faulty))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    events = []

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url=base))
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            ctx = SimpleNamespace(findings=FindingStore(), trace=SimpleNamespace(event=lambda t, **k: events.append((t, k))))
            try:
                found, feed = await _discover(s, cfg)
                await _check_discovered(s, cfg, ctx, found, feed)
            finally:
                await s.close()
                await browser.close()
                srv.shutdown()
            return found, ctx.findings

    found, fs = asyncio.run(go())
    return found, fs, events


def test_discovery_checks_find_the_faults():
    found, fs, events = run(True)
    assert "/old-page" in found["sitemap"] and "/news/2" in found["feed"], found
    rules = {f.detail["rule"]: f for f in fs.by_sig.values()}
    assert {"R02s", "R20f"} <= set(rules), list(rules)
    assert all(f.status == "confirmed" and f.gate["source"] == "discovery" for f in rules.values())
    assert "/old-page" in rules["R02s"].message and "Fresh harbour news" in rules["R20f"].message
    assert events[-1] == ("discovery_checks", {"findings": 2})


def test_discovery_checks_quiet_on_the_clean_site():
    found, fs, events = run(False)
    assert found["sitemap"] and not fs.by_sig, [f.message for f in fs.by_sig.values()]


def test_safety_and_coverage_records():
    sw = SweepState()
    m = sw.memory
    for verb, key in (("create", "/b/1"), ("create", "/b/2"), ("delete", "/b/1"), ("delete", "/b/9")):
        m.add_event(worker=1, step=1, verb=verb, target=key, status="verified")
    m.add_event(worker=1, step=2, verb="delete", target="/b/2", status="pending")  # not verified: not counted
    s = safety_of(sw)
    assert s == {"created": 2, "deleted_own": 1, "foreign_deletes": ["/b/9"], "foreign_delete_count": 1,
                 "cleanup_share": 0.5}
    g = StateGraph()
    g.visit(1, "s1", "http://h/", 1)
    g.visit(1, "s2", "http://h/books/1", 2)
    sw.checks.note(1, 1, "R09", "/", "exercised")
    sw.forms["/books/new"] = {"attempted": 2, "accepted": 1, "retried": 1, "retry_accepted": 1}
    cov = coverage_of(SimpleNamespace(graph=g, sweep=sw), None)
    assert cov["routes"] == ["/", "/books/*"] and cov["oracle_arm_coverage"] == 0.5 and cov["rules_armed"] == ["R09"]
    assert cov["forms"]["/books/new"]["retry_accepted"] == 1
    assert coverage_of(SimpleNamespace(graph=None, sweep=None), None)["oracle_arm_coverage"] is None
