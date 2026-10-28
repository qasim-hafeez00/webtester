"""v5 evidence layer (D58): network timeline with JSON bodies, transient messages, R57 and R51.

Pure tests feed hand-made records to the rules. Browser tests run a real BrowserSession against pages
served at http://h/... and check that capture is on only with `capture_evidence`.
"""

import asyncio

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import TIER, SweepState, Sweeper
from webtester.evidence import kind_of, rule_messages, rule_payload


def rec(status, body, method="GET", url="http://h/api/articles/42", seq=1):
    return {"seq": seq, "t": 0, "method": method, "url": url, "path": url.split("http://h", 1)[1],
            "status": status, "type": "fetch", "ctype": "application/json", "body": body}


# ---------------------------------------------------------------------------- R57
def test_graphql_errors_on_200_is_r57():
    v = rule_payload([rec(200, {"data": None, "errors": [{"message": "Cannot query field"}]})])
    assert [x.rule for x in v] == ["R57"] and "Cannot query field" in v[0].message and TIER["R57"] == "T2"


def test_error_field_and_errors_dict_on_2xx_are_r57():
    assert rule_payload([rec(200, {"error": "not found"})])
    assert rule_payload([rec(201, {"errors": {"title": ["can't be blank"]}}, method="POST")])
    assert rule_payload([rec(200, {"error": True, "message": "quota"})])[0].message.endswith("quota")


def test_ordinary_answers_are_not_r57():
    assert not rule_payload([rec(200, {"article": {"title": "x"}})])
    assert not rule_payload([rec(200, {"error": None, "errors": []})])
    assert not rule_payload([rec(200, {"error": 0})])
    assert not rule_payload([rec(422, {"errors": {"title": ["can't be blank"]}}, method="POST")])  # 4xx is honest
    assert not rule_payload([rec(200, [{"errors": "a list body is data"}])])
    assert not rule_payload([{**rec(200, None), "body": None}])
    no_body = rec(200, {}); del no_body["body"]
    assert not rule_payload([no_body])


def test_r57_once_per_method_and_route_shape():
    v = rule_payload([rec(200, {"error": "x"}, url="http://h/api/articles/1", seq=1),
                      rec(200, {"error": "x"}, url="http://h/api/articles/2", seq=2),
                      rec(200, {"error": "x"}, method="PUT", url="http://h/api/articles/2", seq=3)])
    assert len(v) == 2


# ---------------------------------------------------------------------------- R51
def test_message_kinds():
    assert kind_of("Article saved") == "ok"
    assert kind_of("Successfully updated your settings") == "ok"
    assert kind_of("Error: could not save the page") == "bad"
    assert kind_of("Changes not saved: title is required") == "bad"
    assert kind_of("Saved with 0 errors") == ""  # both kinds of words: ambiguous, never used
    assert kind_of("Welcome back") == ""


def test_success_and_error_together_is_r51():
    v = rule_messages([{"t": 1000, "text": "Page saved", "kind": "status"},
                       {"t": 1800, "text": "Something went wrong", "kind": "alert"}])
    assert [x.rule for x in v] == ["R51"] and TIER["R51"] == "T2"


def test_no_r51_for_one_kind_or_far_apart():
    assert not rule_messages([{"t": 0, "text": "Saved"}, {"t": 10, "text": "Created"}])
    assert not rule_messages([{"t": 0, "text": "Invalid email"}, {"t": 10, "text": "Password too short"}])
    assert not rule_messages([{"t": 0, "text": "Error: offline"}, {"t": 60_000, "text": "Saved"}])


# ---------------------------------------------------------------------------- browser
PAGE = """<html><body><h1>Edit</h1><div id="out"></div><script>
fetch('/api/save', {method: 'POST', body: JSON.stringify({title: 'x'})})
  .then(r => r.json()).then(() => {
    const t = document.createElement('div'); t.className = 'toast'; t.textContent = 'Article saved';
    document.body.appendChild(t);
    setTimeout(() => { t.remove();
      const e = document.createElement('div'); e.setAttribute('role', 'alert'); e.textContent = 'Error: could not save';
      document.body.appendChild(e); }, 200);
    setTimeout(() => { document.getElementById('out').textContent = 'done'; }, 400);
  });
</script></body></html>"""


def run_session(capture: bool, fn):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url="http://h"), settle_ms=50, capture_evidence=capture)
            s = BrowserSession(browser, cfg, 1)
            await s.start()

            async def serve(route):
                if route.request.url.endswith("/api/save"):
                    await route.fulfill(status=200, content_type="application/json",
                                        body='{"errors": [{"message": "title taken"}]}')
                else:
                    await route.fulfill(status=200, content_type="text/html", body=PAGE)
            await s.context.route("http://h/**", serve)  # registered last, so it runs before the scope gate
            try:
                return await fn(s)
            finally:
                await s.close()
                await browser.close()

    return asyncio.run(go())


def test_capture_keeps_bodies_sent_data_and_transient_messages():
    async def fn(s):
        mark = s.net_mark()
        await s.goto("/edit")
        await s.page.wait_for_function("document.getElementById('out').textContent === 'done'")
        await s.flush_bodies()
        net = s.net_since(mark)
        msgs = await s.drain_messages()
        await s.page.evaluate("(m) => { window.__wtMsgs.push(...m); }", msgs)  # put back for the sweeper
        sw = Sweeper(SweepState(), 1)
        sw.net_mark = mark
        viol = await sw._evidence(s)  # what Sweeper.after adds with capture on
        return net, msgs, await s.drain_messages(), sorted(v.rule for v in viol)

    net, msgs, again, rules = run_session(True, fn)
    save = next(r for r in net if r["path"] == "/api/save")
    assert save["body"] == {"errors": [{"message": "title taken"}]} and '"title"' in save["sent"]
    assert any(r["type"] == "document" for r in net)
    assert [m["text"] for m in msgs] == ["Article saved", "Error: could not save"]  # the toast was gone by then
    assert again == []  # drained
    assert rules == ["R51", "R57"]


def test_capture_off_records_nothing():
    async def fn(s):
        await s.goto("/edit")
        await s.page.wait_for_function("document.getElementById('out').textContent === 'done'")
        return s.net, await s.drain_messages(), await s.page.evaluate("() => window.__wtMsgs === undefined")

    net, msgs, no_observer = run_session(False, fn)
    assert net == [] and msgs == [] and no_observer
