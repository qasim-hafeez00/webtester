"""D61: faulty and clean cases for the page-norm extensions (norms.py), one page read each, and the same page
read through NORMS_JS in a real browser (the JavaScript half of each rule)."""

from __future__ import annotations

import asyncio

import pytest

from webtester.norms import (rule_chart, rule_column_totals, rule_controls, rule_limits, rule_lines, rule_playlist,
                             rule_presentation, rule_ranges)


def subj(vs):
    return {(v.rule, v.subject.split("|")[0]) for v in vs}


def test_r06s_tax_against_its_bases():
    assert ("R06s", "tax") in subj(rule_lines(["Subtotal $100.00", "Tax (8%) $9.00", "Total $109.00"]))
    assert not subj(rule_lines(["Subtotal $100.00", "Tax (8%) $8.00", "Total $108.00"]))
    # tax on the discounted subtotal plus shipping is one of the accepted bases
    assert not subj(rule_lines(["Subtotal $100.00", "Discount -$10.00", "Shipping $5.00", "Tax (10%) $9.50"]))


def test_r36r_recurrence_count():
    dated = ["Mon 2025-01-06", "Mon 2025-01-13", "Mon 2025-01-20", "Mon 2025-01-27"]
    assert ("R36r", "recurrence") in subj(rule_lines(["Weekly, 5 times", *dated, "Notes 1"]))
    assert not subj(rule_lines(["Weekly, 4 times", *dated, "Notes 1"]))


def test_r32d_currency_decimals():
    s = subj(rule_lines(["Price $10.5 each", "Fee $3.141", "¥1,200.50"]))
    assert ("R32d", "decimals") in s
    assert not subj(rule_lines(["Price $10.50", "¥1,200", "Rate 12.5%", "€1.234,56"]))


def test_r36_day_count_both_conventions():
    assert ("R36", "days") in subj(rule_lines(["Leave 2025-03-03 - 2025-03-07 (7 days)"]))
    assert not subj(rule_lines(["Leave 2025-03-03 - 2025-03-07 (5 days)", "Stay 2025-03-03 - 2025-03-07 (4 days)",
                                "Leave 2025-03-07 - 2025-03-10 (2 working days)"]))


def test_r26_negative_counters_and_paused_timer():
    assert ("R26", "negative") in subj(rule_lines(["Score: -3"]))
    assert not subj(rule_lines(["Score: 3", "Temperature -3"]))
    assert ("R26", "timer-paused") in subj(rule_ranges({"timer_paused": ["01:02 -> 01:03"]}, set()))
    assert not subj(rule_ranges({"timer_paused": []}, set()))


def test_r10x_text_against_target():
    bad = {"contacts": [{"href": "tel:+15551234567", "text": "+1 555 765 4321"}, {"href": "mailto:a@b.com", "text": "c@d.com"}]}
    good = {"contacts": [{"href": "tel:+15551234567", "text": "+1 (555) 123-4567"}, {"href": "mailto:a@b.com", "text": "Mail us"}]}
    assert {("R10x", "tel-text"), ("R10x", "mailto-text")} <= subj(rule_presentation(bad))
    assert not subj(rule_presentation(good))


def test_r02h_hosts_and_empty_cta():
    raw = {"hosts": [{"href": "http://localhost:3000/x", "text": "Docs", "why": "dev host"}],
           "empty_cta": [{"text": "Buy now", "href": "#"}]}
    assert {("R02h", "host"), ("R02h", "empty")} <= subj(rule_presentation(raw))
    assert not subj(rule_presentation({"hosts": [], "empty_cta": []}))


def test_r12c_counter():
    c = {"label": "Bio", "units": 5, "points": 5, "max": 280, "a": 12, "b": 280, "left": None}
    assert ("R12c", "counter") in subj(rule_presentation({"counters": [c]}))
    ok = [{**c, "a": 5}, {**c, "a": 275}, {**c, "a": None, "b": None, "left": 275}]
    assert not subj(rule_presentation({"counters": ok}))
    assert ("R12c", "left") in subj(rule_presentation({"counters": [{**c, "a": None, "b": None, "left": 270}]}))


def test_r68_duplicate_tags_and_r65_clipped():
    assert ("R68", "duplicate") in subj(rule_presentation({"chips": [{"dup": "maps", "n": 3}]}))
    assert ("R65", "clipped") in subj(rule_presentation({"clipped": ["Quarterly report for"]}))
    assert not subj(rule_presentation({"chips": [], "clipped": []}))


def test_r64_carousel_and_r75_canvas_svg():
    assert ("R64", "carousel") in subj(rule_controls({"carousel": [{"label": "Hero", "slide": 1, "indicator": 0}]}))
    assert not subj(rule_controls({"carousel": [{"label": "Hero", "slide": 1, "indicator": 1}]}))
    s = subj(rule_presentation({"canvas_frozen": ["game"], "svg_outside": ["rect at 900,10"]}))
    assert {("R75", "frozen"), ("R75", "outside")} <= s


def test_r06c_column_totals():
    t = [{"head": ["Item", "Hours", "Rate"], "rows": [["A", "2", "10"], ["B", "3", "10"], ["Total", "6", "10"]]}]
    assert ("R06c", "total") in subj(rule_column_totals(t))
    t[0]["rows"][2][1] = "5"
    assert not subj(rule_column_totals(t))  # 'Rate' is not additive and is never summed


def test_r41_chart_against_table():
    chart = {"chart": [{"label": "Jan", "value": "12"}, {"label": "Feb", "value": "9"}]}
    t = [{"head": ["Month", "Sales"], "rows": [["Jan", "12"], ["Feb", "8"]]}]
    assert ("R41", "chart") in subj(rule_chart(chart, t))
    t[0]["rows"][1][1] = "9"
    assert not subj(rule_chart(chart, t))


def test_r35_stated_limit_and_r74_playlist():
    L = [{"heading": "Your projects", "items": [{"name": n, "text": n} for n in "abcd"]}]
    assert ("R35", "limit") in subj(rule_limits("Free plan: up to 3 projects", L, {}))
    assert not subj(rule_limits("Free plan: up to 5 projects", L, {}))
    assert not subj(rule_limits("Free plan: up to 3 projects", L, {"pager": [{"text": "2"}]}))  # not complete
    P = [{"heading": "Tracks", "items": [{"name": "a", "text": "a 3:00"}, {"name": "b", "text": "b 4:00"}]}]
    assert {("R74", "total-length"), ("R74", "track-count")} <= subj(rule_playlist("3 tracks · 12 min", P, {}))
    assert not subj(rule_playlist("2 tracks · 7 min", P, {}))


FAULTY = """<html><head><title>Fixtures</title></head><body><main>
<h1>Fixtures</h1>
<div class="carousel"><div class="carousel-inner" style="display:flex;width:300px;overflow:hidden">
  <div class="carousel-item" style="min-width:300px;display:none">One</div>
  <div class="carousel-item" style="min-width:300px">Two</div></div>
  <div class="carousel-indicators"><button class="active">1</button><button>2</button></div></div>
<p style="width:60px;overflow:hidden;white-space:nowrap">A long title that does not fit</p>
<a href="http://localhost:3000/docs">Docs</a> <a href="#">Buy now</a>
<label>Bio <input maxlength="280" value="hello"> <span>12/280</span></label>
<a href="/files/report.zip" download>Download report</a>
<svg viewBox="0 0 100 100" width="100" height="100"><rect x="500" y="10" width="10" height="10"></rect>
  <g><rect aria-label="Jan: 12" x="1" y="1" width="5" height="5"></rect><rect aria-label="Feb: 9" x="8" y="1" width="5" height="5"></rect></g></svg>
<ul class="tags"><li class="tag">maps</li><li class="tag">maps</li></ul>
<kbd>N</kbd>
</main></body></html>"""
CLEAN = """<html><head><title>Fixtures</title></head><body><main><h1>Fixtures</h1>
<p style="width:400px">A short title</p><a href="/docs">Docs</a> <a href="/buy">Buy now</a>
<label>Bio <input maxlength="280" value="hello"> <span>5/280</span></label>
<svg viewBox="0 0 100 100" width="100" height="100"><rect x="10" y="10" width="10" height="10"></rect></svg>
<ul class="tags"><li class="tag">maps</li><li class="tag">travel</li></ul></main></body></html>"""


def _read(html: str) -> dict:
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.norms import NORMS_JS

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


def test_norms_js_reads_the_new_facts():
    raw = _read(FAULTY)
    assert raw["carousel"] and raw["carousel"][0]["slide"] != raw["carousel"][0]["indicator"], raw["carousel"]
    assert raw["clipped"], raw["clipped"]
    assert raw["hosts"] and raw["hosts"][0]["why"] == "dev host"
    assert raw["empty_cta"] and raw["empty_cta"][0]["text"] == "Buy now"
    assert raw["counters"] and raw["counters"][0]["a"] == 12
    assert raw["downloads"] and raw["svg_outside"] and len(raw["chart"]) == 2
    assert raw["chips"] and raw["chips"][0]["dup"] == "maps" and raw["kbd"] == ["N"]
    got = subj(rule_presentation(raw)) | subj(rule_controls(raw))
    assert {("R64", "carousel"), ("R65", "clipped"), ("R02h", "host"), ("R02h", "empty"), ("R12c", "counter"),
            ("R75", "outside"), ("R68", "duplicate")} <= got, got


def test_norms_js_clean_page_raises_none_of_them():
    raw = _read(CLEAN)
    got = subj(rule_presentation(raw)) | subj(rule_controls(raw))
    assert not {r for r, _ in got} & {"R64", "R65", "R02h", "R12c", "R75", "R68"}, got


def test_r02m_r02h_skip_addresses_the_testers_typed():
    """D62 (I85, the Conduit pilot): a profile image or an article link the workers typed is the app showing its input."""
    typed = {"https://example.com/pic.jpg", "not-a-url", "See https://example.com for more"}
    raw = {"broken": [{"what": "image", "src": "https://example.com/pic.jpg", "alt": ""},
                      {"what": "image", "src": "http://h/not-a-url", "alt": ""},
                      {"what": "image", "src": "", "alt": ""}],
           "hosts": [{"href": "https://example.com", "text": "link", "why": "example domain"}]}
    assert not subj(rule_presentation(raw, typed))
    assert {("R02m", "image"), ("R02h", "host")} <= subj(rule_presentation(raw))  # not typed: still reported


def test_d62_pilot_false_alarm_shapes_in_a_real_browser():
    """D62 (I87-I89, the BookStack pilot): screen-reader-only text, a control scrolled out of a scrolling box, and the
    name and value parts of one tag chip raise nothing; real clipped text and a real duplicate chip still do."""
    html = """<html><body><main>
      <button class="screen-reader-only" style="position:absolute;width:12px;height:2px;overflow:hidden">Enter section select mode</button>
      <div style="height:60px;overflow:auto"><div style="height:400px"><a href="/x" style="display:block;margin-top:300px">Chapter 1</a></div></div>
      <p style="margin-top:0">Below the box</p>
      <ul><li class="item"><div class="tag-item"><div class="tag-name">Sample Tag</div><div class="tag-value">Sample Tag</div></div></li></ul>
      <div style="width:60px;overflow:hidden;white-space:nowrap"><span style="display:block;width:60px;overflow:hidden">A long label that is cut off</span></div>
      <ul><li class="item"><span class="tag">maps</span><span class="tag">maps</span></li></ul>
    </main></body></html>"""
    raw = _read(html)
    assert not [c for c in raw["covered"] if "Chapter 1" in c["control"]], raw["covered"]
    assert not [t for t in raw["clipped"] if "section select" in t], raw["clipped"]
    assert any("cut off" in t for t in raw["clipped"]), raw["clipped"]
    assert [c["dup"] for c in raw["chips"]] == ["maps"], raw["chips"]
    assert raw["loading"] is False
