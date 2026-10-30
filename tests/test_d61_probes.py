"""D61: the probe extensions against a served notes app, once with faults and once without.

The app runs on a local HTTP server (the storage probe opens its own browser contexts, which a page router does
not reach). With `faulty=True`:
  - the 'Download report' link answers 404 (R02d),
  - a search for '%' or '_' returns every note (R23m),
  - with 'null' in local storage the page script throws and the page stays blank (R48c),
  - 'Sync' writes a note to local storage that the list does not show (R48s),
  - a note id that does not exist answers 200 with an empty page (R63 soft 404),
  - a click on the canvas changes nothing (R75),
  - 'Save offline' keeps a note in IndexedDB that the list does not show (R48s, IndexedDB),
  - 'Apply theme' does nothing at all (R29); in the clean app it only writes local storage, which is an effect,
  - the live suggestions show the answer of whichever request came back last (R77),
  - the offer countdown never ends (R72c),
  - a folder still lists the note that was moved out of it (R40m),
  - 'We've sent a confirmation email' with no mail in the catcher (R47m).
The clean app must raise none of these. Steps are driven by hand (no LLM), as the gate's replays do.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState, Sweeper

PROBE_RULES = {"R02d", "R23m", "R48c", "R48s", "R63", "R75", "R77", "R72c", "R40m", "R47m", "R29"}
NOTES = {1: "First note", 2: "Second note", 3: "Third note", 4: "Seaside walk"}

SUGGEST = """<script>
const box = document.querySelector('input[name=q]'), out = document.getElementById('sugg');
let timer = null;
box.addEventListener('input', () => {  // a usual 200 ms debounce
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const q = box.value;
    const r = await fetch('/suggest?q=' + encodeURIComponent(q));
    const names = await r.json();
    if (%s q !== box.value) return;  // the clean app keeps only the answer for what is typed now
    out.innerHTML = names.map(n => '<li role="option">' + n + '</li>').join('');
  }, 200);
});
</script>"""
OFFLINE = """<script>
function saveOffline(extra) {  // R48s on IndexedDB: the notes kept for offline use
  const r = indexedDB.open('notes-db', 1);
  r.onupgradeneeded = () => r.result.createObjectStore('notes', {keyPath: 'id'});
  r.onsuccess = () => { const db = r.result, tx = db.transaction('notes', 'readwrite'), st = tx.objectStore('notes');
    NAMES.concat(extra).forEach((n, i) => st.put({id: i + 1, name: n})); tx.oncomplete = () => db.close(); };
}
</script>"""
COUNTDOWN = """<p id="t">Offer ends in 5 minutes.</p><script>
const end = Date.now() + 5 * 60 * 1000;
setInterval(() => {
  const left = Math.ceil((end - Date.now()) / 60000), live = ' Live ' + new Date().toISOString().slice(11, 19);
  document.getElementById('t').textContent = %s;
}, 500);
</script>"""


def page(body: str, faulty: bool, title: str = "Notes", search: bool = True) -> str:
    read = "saved.theme" if faulty else "(saved || {}).theme"  # JSON.parse('null') is null
    ghost = ', {name: "Ghost note"}' if faulty else ""
    offline = '["Offline ghost"]' if faulty else "[]"
    theme = "void 0" if faulty else "localStorage.setItem('theme', 'dark')"  # R29: storage-only is an effect
    names = ", ".join(json.dumps({"name": n}) for n in NOTES.values())
    draw = "void 0" if faulty else "const g = this.getContext('2d'); g.fillStyle = '#c00'; g.fillRect(0, 0, 40, 40)"
    form = ("<form action='/search'><input type='search' name='q' placeholder='Search notes' autocomplete='off'>"
            "<ul role='listbox' id='sugg'></ul></form>" + SUGGEST % ("false &&" if faulty else "")) if search else ""
    return f"""<html><head><title>{title}</title></head><body>
<div id="app" hidden><nav><a href="/">Notes</a></nav>
{form}
{body}
<button id="sync" onclick='localStorage.setItem("notes", JSON.stringify([{names}{ghost}]))'>Sync</button>
<canvas id="pad" width="80" height="80" onclick="{draw}"></canvas>
<button id="offline" onclick='saveOffline({offline})'>Save offline</button>
<button id="theme" onclick="{theme}">Apply theme</button></div>
<script>const NAMES = {json.dumps(list(NOTES.values()))};</script>{OFFLINE}
<script>
if (!localStorage.getItem('prefs')) localStorage.setItem('prefs', JSON.stringify({{theme: 'light'}}));
const saved = JSON.parse(localStorage.getItem('prefs'));
document.body.dataset.theme = {read};
document.getElementById('app').hidden = false;
</script></body></html>"""


def handler(faulty: bool, mail: dict):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def send(self, status: int, body: str, ctype: str = "text/html"):
            b = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            m = re.fullmatch(r"/notes/([^/]+)", u.path)
            items = lambda ids: "".join(f"<li class='note'><a href='/notes/{i}'>{NOTES[i]}</a></li>" for i in ids)  # noqa: E731
            if u.path == "/":
                self.send(200, page(f"<h1>Notes</h1><h2>All notes</h2><ul class='notes'>{items(NOTES)}</ul>"
                                    "<a href='/report.zip' download>Download report</a>", faulty))
            elif u.path == "/report.zip":
                self.send(404, "missing", "text/plain") if faulty else self.send(200, "PK report", "application/zip")
            elif u.path == "/suggest":
                term = (q.get("q") or [""])[0].lower()
                hits = [n for n in NOTES.values() if term and any(w.lower().startswith(term) for w in n.split())]
                self.send(200, json.dumps(hits), "application/json")
            elif u.path == "/search":
                term = (q.get("q") or [""])[0]
                wild = faulty and term in ("%", "_")
                hits = [i for i, n in NOTES.items() if wild or (term and term.lower() in n.lower())]
                self.send(200, page(f"<h1>Search results</h1><p>{len(hits)} results found</p>"
                                    f"<ul class='hits'>{items(hits)}</ul>", faulty))
            elif u.path == "/offer":
                live = "'Offer ends in 5 minutes.' + live" if faulty else \
                    "left > 0 ? 'Offer ends in ' + left + ' minutes.' + live : 'Offer ended.' + live"
                self.send(200, page("<h1>Spring offer</h1>" + COUNTDOWN % live, faulty, search=False))
            elif u.path == "/folders/a":  # 'Second note' was moved out of this folder
                kept = [1, 2] if faulty else [1]
                self.send(200, page(f"<h1>Folder A</h1><h2>Notes in this folder</h2><ul class='notes'>{items(kept)}</ul>",
                                    faulty, search=False))
            elif u.path == "/join":
                self.send(200, page("<h1>Mailing list</h1><form method=post action=/join><label>Email <input type=email "
                                    "name=email></label><button type=submit>Join list</button></form>", faulty,
                                    search=False))
            elif u.path == "/api/v1/messages":
                msgs = [] if faulty or not mail.get("to") else [
                    {"To": [{"Address": mail["to"]}], "Created": datetime.now(timezone.utc).isoformat()}]
                self.send(200, json.dumps({"messages": msgs}), "application/json")
            elif m and m.group(1).isdigit() and int(m.group(1)) in NOTES:
                n = NOTES[int(m.group(1))]
                self.send(200, page(f"<h1>{n}</h1><p>Written on 2025-05-01. A short note body for the page.</p>", faulty, n))
            elif m and faulty:
                self.send(200, "<html><head><title>Notes</title></head><body><div></div></body></html>")
            else:
                self.send(404, page("<h1>Not found</h1><p>No such note.</p>", faulty))

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(n).decode())
            mail["to"] = (form.get("email") or [""])[0]
            self.send(200, page(f"<h1>Thanks</h1><p>We've sent a confirmation email to {mail['to']}.</p>", faulty,
                                search=False))

    return H


def sweep(faulty: bool):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    mail: dict = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(faulty, mail))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    async def step_once(s, sw, path, step, act=None):
        await s.goto(path)
        obs = await s.observe()
        if act == "join":
            box = next(e for e in obs.elements if e.label.strip() == "Email")
            btn = next(e for e in obs.elements if e.text.strip() == "Join list")
            actions = [{"do": "fill", "id": box.id, "value": "reader@example.test", "el": f'[{box.id}] input label="Email"',
                        "ok": True, "ekey": box.key(), "nth": 0},
                       {"do": "click", "id": btn.id, "value": None, "el": f'[{btn.id}] button "Join list"', "ok": True,
                        "ekey": btn.key(), "nth": 0}]
        else:
            el = next((e for e in obs.elements if act and (e.tag == act or e.text == act)), None)
            actions = [{"do": "click", "id": el.id, "value": None, "el": f'[{el.id}] {el.tag} "{el.text}"', "ok": True,
                        "ekey": None}] if el else []
        await sw.before(s, obs, actions)
        for a in actions:
            loc = s.page.locator(f'[data-wt-id="{a["id"]}"]')
            await (loc.fill(a["value"]) if a["do"] == "fill" else loc.click())
        if actions:
            await s.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(0.3)
        await sw.actions_done(s)
        done = actions or [{"do": "navigate", "id": None, "value": path, "el": None, "ok": True, "ekey": None}]
        return await sw.after(s, obs, done, step)

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url=base, mail_api=base), settle_ms=300, capture_evidence=True,
                            seed_copies=0, poll_deadline_s=0.5)
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            st = SweepState()
            sw = Sweeper(st, 1, None)
            st.cross.moved.append(("/notes/2", base + "/folders/a", "Second note", 0))  # HI3: seen moved at step 0
            sigs = []
            plan = [("/", None)] * 8 + [("/", "Sync"), ("/", "Save offline"), ("/", "Apply theme"), ("/", "canvas"), ("/notes/1", None), ("/notes/1", None),
                                         ("/offer", None), ("/offer", None), ("/join", "join"), ("/join", "join")]
            try:
                for k, (path, act) in enumerate(plan, 1):
                    sigs += await step_once(s, sw, path, k, act)
            finally:
                await s.close()
                await browser.close()
                srv.shutdown()
            return sigs, st

    return asyncio.run(go())


@pytest.fixture(scope="module")
def faulty_run():
    return sweep(True)


def test_d61_probes_find_the_faults(faulty_run):
    sigs, st = faulty_run
    got = {x.detail["rule"] for x in sigs}
    errors = [r for r in st.checks.records() if r["why"].startswith("error:")]
    assert not errors, errors
    assert PROBE_RULES <= got, (sorted(PROBE_RULES - got), json.dumps(st.p5.used))
    soft = [x for x in sigs if x.detail["rule"] == "R63"]
    assert any("answers 200 with an empty page" in x.message for x in soft), [x.message for x in soft]
    stored = " ".join(x.message.lower() for x in sigs if x.detail["rule"] == "R48s")
    assert "ghost note" in stored and "offline ghost" in stored, stored  # local storage and IndexedDB
    race = next(x for x in sigs if x.detail["rule"] == "R77")
    assert "seaside walk" in race.message.lower(), race.message


def test_d61_probes_quiet_on_the_clean_app():
    sigs, st = sweep(False)
    got = {x.detail["rule"] for x in sigs}
    assert not (PROBE_RULES & got), [x.message for x in sigs if x.detail["rule"] in PROBE_RULES]
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
    # every probe here was armed on the clean app too: quiet because the app is right, not because nothing ran
    armed = {r["rule"] for r in st.checks.records() if r["outcome"] in ("exercised", "detected")}
    assert PROBE_RULES <= armed, sorted(PROBE_RULES - armed)
