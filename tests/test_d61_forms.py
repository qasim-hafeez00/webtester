"""D61: R1 (input profiles) and the form probes R16i, R26p and R36p against a served item form, once with
faults and once without.

The form (/items/new) has a title, a quantity and a due date typed as text. A title under 10 characters is
rejected with 'Title must be at least 10 characters' in both apps, so R1 must retry the form with a profiled
value and have it accepted. With `faulty=True`:
  - a title with an apostrophe is rejected as invalid (R16i),
  - a quantity of -1 is accepted and shown (R26p),
  - a due date of 30 Feb 2025 is accepted (R36p).
The clean app rejects -1 and 30 Feb with a message, and accepts apostrophes. Steps are driven by hand (no LLM).
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState, Sweeper

PROBE_RULES = {"R16i", "R26p", "R36p"}


def handler(faulty: bool, items: dict):
    def form(msg: str = "", v: dict | None = None) -> str:
        v = v or {}
        return (f"<html><head><title>New item</title></head><body><h1>New item</h1>"
                f"{f'<p class=error>{msg}</p>' if msg else ''}"
                f"<form method=post action=/items><label>Title <input name=title value='{v.get('title', '')}'></label>"
                f"<label>Quantity <input type=number name=qty value='{v.get('qty', '')}'></label>"
                f"<label>Due date <input name=due value='{v.get('due', '')}'></label>"
                f"<button type=submit>Create item</button></form></body></html>")

    def problem(v: dict) -> str:
        if len(v["title"]) < 10:
            return "Title must be at least 10 characters"
        if faulty and "'" in v["title"]:
            return "Title is invalid"
        if not faulty and v["qty"].lstrip().startswith("-"):
            return "Quantity must be at least 0"
        try:
            date.fromisoformat(v["due"])
        except ValueError:
            if not faulty or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["due"]):
                return "Due date is invalid"
        return ""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, status: int, body: str = "", location: str = ""):
            b = body.encode()
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlsplit(self.path)
            m = re.fullmatch(r"/items/(\d+)", u.path)
            if u.path == "/items/new":
                self.send(200, form())
            elif m and int(m.group(1)) in items:
                it = items[int(m.group(1))]
                self.send(200, f"<html><head><title>{it['title']}</title></head><body><h1>{it['title']}</h1>"
                               f"<p>Quantity: {it['qty']}</p><p>Due: {it['due']}</p></body></html>")
            else:
                self.send(404, "<html><body><h1>Not found</h1></body></html>")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            q = parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
            v = {k: (q.get(k) or [""])[0] for k in ("title", "qty", "due")}
            msg = problem(v)
            if msg:
                self.send(200, form(msg, v))
                return
            i = len(items) + 1
            items[i] = v
            self.send(303, location=f"/items/{i}")

    return H


def sweep(faulty: bool):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    items: dict = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(faulty, items))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    async def submit(s, sw, step, title):
        await s.goto("/items/new")
        obs = await s.observe()
        by = {e.label.strip(): e for e in obs.elements if e.label}
        button = next(e for e in obs.elements if e.text.strip() == "Create item")
        vals = [("Title", title), ("Quantity", "2"), ("Due date", "2025-03-01")]
        actions = [{"do": "fill", "id": by[k].id, "value": v, "el": f'[{by[k].id}] input label="{k}"', "ok": True,
                    "ekey": by[k].key(), "nth": 0} for k, v in vals]
        actions.append({"do": "click", "id": button.id, "value": None, "el": f'[{button.id}] button "Create item"',
                        "ok": True, "ekey": button.key(), "nth": 0})
        await sw.before(s, obs, actions)
        for a in actions[:-1]:
            await s.page.locator(f'[data-wt-id="{a["id"]}"]').fill(a["value"])
        await s.page.locator(f'[data-wt-id="{button.id}"]').click()
        await s.page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(0.3)
        await sw.actions_done(s)
        return await sw.after(s, obs, actions, step)

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url=base), settle_ms=300, capture_evidence=True,
                            seed_copies=0, poll_deadline_s=0.5, mode="reversible")
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            st = SweepState()
            sw = Sweeper(st, 1, None)
            sigs = []
            titles = ["Short"] + [f"Notebook number {k}" for k in range(1, 11)]
            try:
                for k, t in enumerate(titles, 1):
                    sigs += await submit(s, sw, k, t)
            finally:
                await s.close()
                await browser.close()
                srv.shutdown()
            return sigs, st, items

    return asyncio.run(go())


@pytest.fixture(scope="module")
def faulty_run():
    return sweep(True)


def test_r1_retries_a_rejected_form_with_profiled_values(faulty_run):
    sigs, st, items = faulty_run
    rec = st.forms["/items/new"]
    assert rec["attempted"] == 11 and rec["retried"] == 1 and rec["retry_accepted"] == 1, rec
    assert any(len(it["title"]) >= 10 and it["title"].startswith("Short") for it in items.values()), items
    assert st.input_classes, st.input_classes


def test_form_probes_find_the_faults(faulty_run):
    sigs, st, items = faulty_run
    got = {x.detail["rule"] for x in sigs}
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
    assert PROBE_RULES <= got, (sorted(PROBE_RULES - got), json.dumps(st.p5.used))
    msgs = " ".join(x.message for x in sigs if x.detail["rule"] in PROBE_RULES)
    for want in ("rejects it with an apostrophe", "-1 was accepted", "30 Feb 2025 was accepted"):
        assert want in msgs, msgs


def test_form_probes_quiet_on_the_clean_app():
    sigs, st, items = sweep(False)
    got = {x.detail["rule"] for x in sigs}
    assert not (PROBE_RULES & got), [x.message for x in sigs if x.detail["rule"] in PROBE_RULES]
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
    armed = {r["rule"] for r in st.checks.records() if r["outcome"] in ("exercised", "detected")}
    assert PROBE_RULES <= armed, sorted(PROBE_RULES - armed)
    assert st.forms["/items/new"]["retry_accepted"] == 1
