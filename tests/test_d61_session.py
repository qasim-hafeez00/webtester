"""D61: the execution-mode and scope counters of the browser session (group 11 safety), and the X5 profile
filter of the sweeper (ablation only)."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState, Sweeper, Violation


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: str):
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send("<html><body><h1>Home</h1><img src='http://203.0.113.9/pixel.png'>"
                   "<form method=post action=/items><input name=t value=x><button>Save</button></form></body></html>")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send("<html><body><h1>Saved</h1></body></html>")


def run(mode: str) -> dict:
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url=f"http://127.0.0.1:{srv.server_address[1]}"), mode=mode)
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            try:
                await s.goto("/")
                await s.page.click("button")
                await asyncio.sleep(0.8)
                return s.report()
            finally:
                await s.close()
                await browser.close()
                srv.shutdown()

    return asyncio.run(go())


def test_read_only_refuses_the_write_and_out_of_scope_is_blocked():
    rep = run("read-only")
    assert [w["why"] for w in rep["blocked_writes"]] == ["read-only"] and rep["mode_violations"] == []
    assert rep["out_of_scope_blocked"] >= 1  # the third-party pixel never left the browser
    rep = run("controlled")
    assert rep["blocked_writes"] == [] and rep["mode_violations"] == []
    assert {"build_mode", "pages_looked", "controls_seen", "controls_activated", "modalities"} <= set(rep)


def test_profile_filter_is_off_unless_asked():
    st = SweepState()
    sw = Sweeper(st, 1, None)
    viol = [Violation("R23", "a", "m"), Violation("R35", "b", "m")]  # R23 (search recall) is in the QUERY pack
    off = SimpleNamespace(cfg=SimpleNamespace(profile_gating=False))
    on = SimpleNamespace(cfg=SimpleNamespace(profile_gating=True))
    assert sw._profile_filter(off, viol) == viol
    assert sw._profile_filter(on, viol) == viol  # no profile yet: nothing dropped
    st.profile_of = lambda: {"primitives": ["QUERY"]}
    kept = sw._profile_filter(on, viol)
    from webtester.families import rule_packs

    allowed = set(rule_packs(prims={"QUERY"})["rules"])
    assert [v.rule for v in kept] == ["R23"] and "R35" not in allowed, allowed
    assert any(r["outcome"] == "suppressed" and r["why"] == "profile" for r in st.checks.records())


def test_r4_active_context_in_the_state_id():
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import CONTEXT_JS
    from webtester.worker import _sid

    pages = {
        "switch": "<header><label>Workspace <select id=ws><option>Acme</option><option selected>Beta</option></select>"
                  "</label></header><h1>Board</h1>",
        "button": "<header><button aria-haspopup=menu>Team: Red</button></header><h1>Board</h1>",
        "form": "<form><label>Project <select><option selected>P1</option></select></label></form><h1>Board</h1>",
        "none": "<h1>Board</h1>",
    }

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            page = await browser.new_page()
            out = {}
            for k, html in pages.items():
                await page.set_content(html)
                out[k] = await page.evaluate(CONTEXT_JS)
            await browser.close()
            return out

    got = asyncio.run(go())
    assert got == {"switch": "workspace=Beta", "button": "team=Red", "form": "", "none": ""}, got
    app = AppConfig(name="t", base_url="http://h")
    sess = SimpleNamespace(cfg=SimpleNamespace(app=app), worker=1)
    obs = lambda ctx: SimpleNamespace(url="http://h/board", skeleton="sk", context=ctx)  # noqa: E731
    assert _sid(sess, obs("workspace=Acme")) != _sid(sess, obs("workspace=Beta"))
    assert _sid(sess, obs("")) == _sid(sess, SimpleNamespace(url="http://h/board", skeleton="sk"))  # no switcher: as before
