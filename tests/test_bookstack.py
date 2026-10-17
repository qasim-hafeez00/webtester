"""Offline tests for the second subject app (BookStack, WebTestPilot benchmark faults).
No network and no app: the browser test serves a synthetic page from a fake origin."""

import asyncio
import json
import tomllib
from dataclasses import replace

import pytest

from webtester.config import REPO_ROOT, load_config

BS = REPO_ROOT / "apps" / "bookstack"
CFG = load_config(REPO_ROOT / "configs" / "bookstack.toml")


def test_injected_js_is_current_and_adapted():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_injected", BS / "faults" / "build_injected.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    js = mod.build()
    assert (BS / "faults" / "injected.js").read_text(encoding="utf-8") == js  # rebuild after edits
    catalog = tomllib.loads((BS / "faults" / "faults.toml").read_text(encoding="utf-8"))["fault"]
    scripts = [s for f in catalog for s in f["scripts"]]
    assert len(catalog) == 18 and len(scripts) == len(set(scripts)) == 27
    assert sum(f["reachable"] for f in catalog) == 13 and all(f.get("needs") for f in catalog if not f["reachable"])
    assert js.count('console.debug("[wt-fault] ') == 27  # A3, one marker per script
    assert js.count('"visible" : "no-change"') == 27  # A3: visible vs trigger-only
    assert "sessionStorage" not in js and "__flash_ui_active__" not in js  # A2, A1
    for f in catalog:  # A4: each fault is switchable
        assert f'.includes("{f["id"]}")' in js


def test_bookstack_config_mirrors_conduit_llm_settings():
    conduit = load_config(REPO_ROOT / "configs" / "realworld.toml")
    assert CFG.llm == conduit.llm and CFG.budget == conduit.budget
    assert CFG.app.fault_script == "apps/bookstack/faults/injected.js"
    assert CFG.app.account(3).email == "worker03@bookstack.test"


def test_all_expands_to_catalog_and_client_faults_persist(tmp_path, monkeypatch):
    from webtester.appctl import AppControl

    ctl = AppControl(CFG.app)
    assert ctl._expand(["all"]) == [f"BS{i:02d}" for i in range(1, 19)]
    assert ctl._expand(["BS01"]) == ["BS01"]
    monkeypatch.setattr(AppControl, "_client_faults_file", property(lambda self: tmp_path / ".enabled_faults"))
    (tmp_path / ".enabled_faults").write_text("bs02,BS01", encoding="utf-8")
    assert ctl.running_faults() == ["BS01", "BS02"]  # no docker call for client-side faults


PAGE = """<!doctype html><html><body><main>
<h1 id="sorting" class="list-heading">Sorting</h1>
<a class="button outline" href="/settings/sorting/rules/new">Create Sort Rule</a>
</main></body></html>"""


async def _visit(faults):
    from playwright.async_api import async_playwright

    from webtester.browser import BrowserSession

    cfg = replace(CFG, client_faults=tuple(faults),
                  app=replace(CFG.app, base_url="http://bookstack.test", allowed_origins=("http://bookstack.test",)))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        s = BrowserSession(browser, cfg, 1)
        await s.start()
        await s.context.route("http://bookstack.test/**",
                              lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE))
        blank_errors = list(s.drain_signals())  # the context's first page is about:blank
        await s.goto("/settings/sorting")
        await asyncio.sleep(0.5)
        text = await s.page.evaluate("() => document.body.innerText")
        out = (s.drain_exposures(), text, blank_errors + s.drain_signals(), list(s.injector_errors))
        await s.close()
        await browser.close()
    return out


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return bool(p.chromium.executable_path)
    except Exception:
        return False


@pytest.mark.skipif(not _browser_available(), reason="Playwright Chromium not installed")
def test_injected_fault_fires_shows_effect_and_reports_exposure():
    fired, text, errors, inj = asyncio.run(_visit(["BS13"]))
    assert fired == ["BS13"] and "Create Sort Rule" not in text  # the button is gone, counted as visible
    assert errors == [] and inj == []  # no false page errors, no injector errors
    fired, text, errors, inj = asyncio.run(_visit([]))  # faults off: nothing fires
    assert fired == [] and "Create Sort Rule" in text and errors == []
    fired, text, _, _ = asyncio.run(_visit(["BS01"]))  # another fault on: BS13 stays dormant
    assert "BS13" not in fired and "Create Sort Rule" in text


def test_exposure_feeds_findings_metrics_and_suggestions(tmp_path):
    from webtester.browser import Signal
    from webtester.labels import label_metrics, suggest
    from webtester.metrics import summarize
    from webtester.oracles import FindingStore

    store = FindingStore()
    sig = Signal("oracle_violation", "m", "http://h/settings/sorting",
                 {"sig": "oracle_violation|shows|/settings/sorting|now|create sort rule", "expect": {}, "evidence": ""})
    (f,) = store.ingest([sig], step=4, worker=1, state="s", trail=[], exposed=["BS13"])
    assert f.exposed == ["BS13"]
    assert suggest(f.to_dict(), {}, ["BS13"]) == "BS13? / fp?"
    m = label_metrics("r", [f.to_dict()], {"faults": ["BS01", "BS13"]}, {"r": {f.sig: {"label": "bs13"}}})
    assert m["faults_found_all"] == 1 and m["precision_raw"] == 1.0  # labels match enabled ids, any case
    events = [{"t": 0, "type": "run_start", "run_id": "r", "agent": "b4", "workers": 1, "faults": ["BS13"]},
              {"t": 1, "type": "step", "worker": 1, "step": 1, "state": "a", "route": "/", "actions": [],
               "faults_exposed": ["BS13"], "seconds": 1},
              {"t": 2, "type": "injector_error", "worker": 1, "step": 1, "errors": ["[wt-fault-error] x"]},
              {"t": 3, "type": "run_end", "reasons": ["w1:max_steps"]}]
    (tmp_path / "t.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    s = summarize(tmp_path / "t.jsonl")
    assert s["faults_exposed"] == ["BS13"] and s["faults_exposed_n"] == 1 and s["injector_errors"] == 1
