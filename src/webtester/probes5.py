"""Active probes of v5 (waves W1-W4, D60): checks that open a fresh tab, a context with no session, or a
second account. Each probe kind is capped per run and runs once per page or form kind; at most
MAX_PER_STEP v5 probes per step (separate from the v4 probe budget, so neither starves the other).

  R63  address probes (NV10)          an item address with a huge, negative or junk id, or page=0 / page=9999,
                                        answers 5xx, or shows the same item as the real id
  R62  address replay (NV9)           a list address with a query string, opened again, shows other items or
                                        loses its active filters
  R23  search recall (SF2)            searching the exact name of an item seen earlier does not find it
  R24  no-session probe (SA4, SA6)    this account's edit or account pages show its data with no cookies at all
  R28  wrong password (SA3)           a wrong password logs in (once per run)
  R66  credential round trip (SA7)    an account the run registered cannot log in
  R46  second account (MU1)           an item this worker published cannot be opened by another account
  R67  context sentinels (CX1, CX2)   values this account saved in its own settings show in another account's
  R21b unchanged save (FM5, DB2)      submitting an item's edit form unchanged changes the item (tags lost, ...)
  R53  cancel probe (FB4)             cancelling a delete confirmation still deletes, or the confirmation names
                                        another item
  R49  references (DB8, HI4)          after a delete, a page that listed the item still lists it
  R52  rollback (FB3)                 the page shows a new value though its save failed, and a reload shows the old
  R48  client state (RC1-RC3, O5)     a change kept only in the browser (no request, local storage changed) is
                                        lost on reload
  R39  page union (SF6)               pages of a list repeat an item, or do not add up to the stated total
  R37  exports (AR3)                  an export has fewer rows than the complete list, or fails
  R42  uploads (AR1)                  an uploaded file (the harness attaches a small one) is not shown after saving
  R45  step skip (WF4)                a later step of a flow opens without its earlier steps
  R59  number format (FM9, T3)        '1,234.5' typed into a number field is stored as another number
  R61  typeahead (SF9, T3)            suggestions for a typed query contain none of its words
  controlled mode only (our own deployments, S1):
  R60  declared constraints (FM10)    with the page's own limits stripped, the server stores a value past them
  R33  resubmit (LG3, FM7)            a double submit of a money or order form makes two records, no warning
  R50m lost response (FB1, J6)        the write's response is lost after the server answered; the retry makes a
                                        second record (each probe records what reached the server, J6)
  D61, the extensions family rows name (own ids, so the tracker cannot count them before they exist):
  R16i legal input (FM3)               a name with an apostrophe, hyphen and accent rejected where the plain one passed
  R16u uniqueness bypass (UQ2)         a value the app rejected as taken, accepted with a trailing space or another
                                        Unicode normal form
  R26p out-of-range input (DV4, LG6)   a quantity of -1 (any form) or an amount of 0 (payments, transfers) accepted
  R36p edge dates (TM6)                30 Feb accepted in a text date field; 29 Feb 2024 rejected or moved
  R23m search metacharacters (SF8)     a search for '%' or '_' returns the whole list or a server error
  R24b back after logout (SA8, T3)     Back after logging out shows the private page again
  R46w another account's write (SA4)   another account can save this account's item through its edit form
                                        (controlled mode; reverted)
  R47m mail (WF3, O9)                  the page says a mail was sent, the mail catcher holds none for the address
  R52f half-done flow (WF6)            the last write of a multi-write submit is refused, the app says it failed, and
                                        the record still appears (controlled)
  R77  race (CC1)                      results of a delayed earlier query shown for the later, longer query
  R72c timed state (TM8, T3)           a live countdown does not end when the browser clock passes its end
  R40m move (HI3)                      after a move, the old parent still lists the item
  R40c cycle (HI5)                     an item can be moved under its own child (controlled; reverted)
  R02d downloads (AR2)                 a 'Download' link answers 4xx/5xx or an empty file
  R37i import (AR4, AR5)               importing the app's own export reports another row count, or fails (controlled)
  R48c corrupted storage (RC9)         the app does not start when its local storage holds 'null'
  R48s storage model (O5)              local storage and the list on the page disagree about the items
  extensions of built ids: R63 a junk id answering 200 with an empty page (NV10, soft 404); R46 another account
  sees another status (SM2); R66 after a password change the new password fails or the old one works (SA7); R37
  print views and PDF exports (AR3); R75 a canvas that does not change after a click on it (RC8)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .memory import entity_key, norm
from .state import route_shape

TIERS = {r: "T2" for r in ("R63", "R62", "R23", "R24", "R28", "R66", "R46", "R67", "R21b", "R53", "R49", "R52", "R48",
                           "R39", "R37", "R42", "R45", "R60", "R33", "R50m")}
TIERS.update({"R59": "T3", "R61": "T3", "R33g": "T3", "R46c": "T3"})
TIERS.update({r: "T2" for r in ("R16i", "R16u", "R26p", "R36p", "R23m", "R46w", "R47m", "R52f", "R77", "R40m", "R40c",
                                "R02d", "R37i", "R48c", "R48s")})
TIERS.update({"R24b": "T3", "R72c": "T3"})
RULES = tuple(TIERS)
CAPS = {"R63": 6, "R62": 6, "R23": 4, "R24": 4, "R28": 1, "R66": 2, "R46": 3, "R67": 2, "R21b": 3, "R53": 2, "R49": 4,
        "R52": 4, "R48": 4, "R39": 3, "R37": 3, "R42": 3, "R45": 2, "R59": 2, "R61": 2, "R60": 3, "R33": 2, "R50m": 2,
        "R33g": 2, "R46c": 2,
        "R16i": 3, "R16u": 2, "R26p": 3, "R36p": 2, "R23m": 2, "R24b": 1, "R46w": 2, "R47m": 4, "R52f": 2, "R77": 2,
        "R72c": 2, "R40m": 4, "R40c": 1, "R02d": 3, "R37i": 1, "R48c": 1, "R48s": 4}
MAX_PER_STEP = 1
WRITE_WAIT_S = 8  # I61: how long a probe waits for the answer to the write its submit sends
CONTROLLED = {"R60", "R33", "R50m", "R33g", "R46c", "R46w", "R52f", "R40c", "R37i"}
_DUP = re.compile(r"already (been )?(taken|exists?|in use|registered|used)|must be unique|is not unique|duplicate", re.I)
_NEGATIVE_SHOWN = re.compile(r"(?<![\w.])[-−]\s?1(?![\d.,])")
_PAY = re.compile(r"\b(pay|payment|transfer|withdraw|send money|deposit|donate)\b", re.I)
_DATE_FIELD = re.compile(r"date|birth|due|deadline|\bday\b|start|end|from|until", re.I)
_MAILED = re.compile(r"\b(we('ve| have)? (sent|e-?mailed)|(an? )?(e-?mail|link|code|invitation|confirmation) (has been |was )?sent|"
                     r"check your (e-?mail|inbox|mail))\b", re.I)
_TIMED = re.compile(r"\b(expires?|ends?|valid for|held for|reserved for|hold|trial ends?)\b[^.\n]{0,24}?\bin\s+(\d{1,3})\s+"
                    r"(seconds?|secs?|minutes?|mins?|hours?)\b", re.I)
_PARENT_FIELD = re.compile(r"parent|folder|category|book|chapter|shelf|manager|reports to|move to|belongs to|project", re.I)
LS_NAMES_JS = r"""() => {
  const out = [];
  const walk = (v, d) => { if (d > 4 || out.length > 200) return;
    if (Array.isArray(v)) { v.forEach(x => walk(x, d + 1)); return; }
    if (v && typeof v === 'object') { for (const k of ['name', 'title', 'text', 'label']) if (typeof v[k] === 'string' && v[k].trim()) { out.push(v[k].trim()); break; }
      Object.values(v).forEach(x => (x && typeof x === 'object') && walk(x, d + 1)); } };
  for (let i = 0; i < localStorage.length; i++) { try { walk(JSON.parse(localStorage.getItem(localStorage.key(i))), 0); } catch (e) {} }
  return out.slice(0, 200); }"""
CANVAS_HASH_JS = r"""(eid) => { const c = document.querySelector(`[data-wt-id="${eid}"]`);
  if (!c || c.tagName !== 'CANVAS') return null;
  try { const d = c.toDataURL(); let h = 0; for (let i = 0; i < d.length; i += 7) h = (h * 31 + d.charCodeAt(i)) | 0; return h; } catch (e) { return null; } }"""
B64_FETCH_JS = r"""async (u) => { const r = await fetch(u, {credentials: 'include'}); const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode.apply(null, b.subarray(i, i + 8192));
  return [r.status, btoa(s).slice(0, 4000000), r.headers.get('content-type') || '']; }"""
_NOTFOUND = re.compile(r"not found|404|doesn'?t exist|does not exist|no such|could not find|cannot be found|"
                       r"page you (are|were) looking|invalid (id|identifier)", re.I)
_PRIVATE = re.compile(r"\b(private|draft|only you|unpublished|restricted|members only|no permission|not allowed)\b", re.I)
_MONEY_FORM = re.compile(r"\b(pay|payment|transfer|order|checkout|book|booking|register|place order|purchase|donate)\b", re.I)
_SUBMIT = re.compile(r"^(save|update|submit|publish|apply|confirm|done|ok)\b", re.I)
_DELETE = re.compile(r"^(delete|remove|trash)\b", re.I)
_NUMERIC = re.compile(r"price|amount|qty|quantity|number|count|age|weight|cost|total|stock|capacity", re.I)
_FLOW = re.compile(r"/(step|checkout|wizard|onboarding|booking|register|signup|apply)(/|-|\b)", re.I)
IDB_JS = r"""async (names) => {
  if (!window.indexedDB || !indexedDB.databases) return {sig: '', names: []};
  const out = [], parts = [];
  const walk = (v, d) => { if (d > 4 || out.length > 200) return;
    if (Array.isArray(v)) { v.forEach(x => walk(x, d + 1)); return; }
    if (v && typeof v === 'object') { for (const k of ['name', 'title', 'text', 'label']) if (typeof v[k] === 'string' && v[k].trim()) { out.push(v[k].trim()); break; }
      Object.values(v).forEach(x => (x && typeof x === 'object') && walk(x, d + 1)); } };
  const req = r => new Promise((ok, bad) => { r.onsuccess = () => ok(r.result); r.onerror = () => bad(r.error); });
  let dbs = [];
  try { dbs = (await indexedDB.databases()).slice(0, 3); } catch (e) { return {sig: '', names: []}; }
  for (const info of dbs) {
    let db = null;
    try {
      db = await new Promise((ok, bad) => { const r = indexedDB.open(info.name); r.onsuccess = () => ok(r.result);
        r.onerror = () => bad(r.error); r.onupgradeneeded = () => { r.transaction.abort(); bad('new'); }; });
      for (const s of [...db.objectStoreNames].slice(0, 5)) {
        const rows = await req(db.transaction(s, 'readonly').objectStore(s).getAll(null, 100));
        const j = JSON.stringify(rows); let h = 0; for (let i = 0; i < j.length; i++) h = (h * 31 + j.charCodeAt(i)) | 0;
        parts.push(info.name + '/' + s + ':' + rows.length + ':' + h);
        if (names) walk(rows, 0);
      }
    } catch (e) { parts.push(info.name + ':?'); } finally { if (db) db.close(); }
  }
  return {sig: parts.join('|'), names: out.slice(0, 200)};
}"""
LS_HASH_JS = "() => { const s = JSON.stringify(localStorage); let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return s.length + ':' + h; }"
SUGGEST_JS = r"""() => [...document.querySelectorAll('[role=listbox] [role=option], .autocomplete li, [class*=suggest] li, datalist option, [role=option]')]
  .map(o => (o.innerText || o.value || '').trim()).filter(Boolean).slice(0, 15)"""
STRIP_JS = r"""() => { for (const el of document.querySelectorAll('input, textarea, select')) {
  ['maxlength', 'minlength', 'pattern', 'required', 'min', 'max', 'readonly', 'disabled'].forEach(a => el.removeAttribute(a)); }
  for (const f of document.forms) f.noValidate = true; return true; }"""
DELETE_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const b = [...document.querySelectorAll('button, a, [role=button], input[type=submit]')].find(e => vis(e) &&
    /^(delete|remove|trash)\b/i.test((e.innerText || e.value || e.getAttribute('aria-label') || '').trim()));
  if (!b) return false; b.setAttribute('data-wt-del', '1'); return true; }"""
CANCEL_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const box = [...document.querySelectorAll('[role=dialog], [role=alertdialog], dialog[open], .modal.show, .modal[open], [aria-modal=true]')].find(vis);
  if (!box) return null;
  const c = [...box.querySelectorAll('button, a, [role=button]')].find(e => vis(e) && /^(cancel|no|keep|close|back)\b/i.test((e.innerText || '').trim()));
  const text = (box.innerText || '').trim().slice(0, 300);
  if (c) c.click();
  return {text, cancelled: !!c}; }"""


@dataclass
class ProbeState:
    """Shared by all workers of a run (SweepState.p5)."""

    used: dict = field(default_factory=dict)  # rule -> probes run
    done: set = field(default_factory=set)  # (rule, kind)
    second: dict = field(default_factory=dict)  # worker -> BrowserSession of the other account
    flows: dict = field(default_factory=dict)  # (worker, flow root) -> (storage, routes)
    sentinels: dict = field(default_factory=dict)  # worker -> {route: [values]}
    uploads: list = field(default_factory=list)  # (worker, step, file name, due)
    records: list = field(default_factory=list)  # J6: what each injection probe saw
    dup_forms: list = field(default_factory=list)  # R16u: (worker, form url, done) rejected as taken
    refs_checked: set = field(default_factory=set)  # R49: delete events already checked (D62)
    exported: dict = field(default_factory=dict)  # R37i: an export the app produced {body, rows, list url}
    canvas: dict = field(default_factory=dict)  # R75: worker -> (canvas element id, hash before the click)
    moved_done: set = field(default_factory=set)  # R40m: moves already checked


class Probes:
    def __init__(self, ps: ProbeState):
        self.ps = ps

    def _may(self, sw, rule: str, kind: str) -> bool:
        if (rule, kind) in self.ps.done:
            return False
        if self.ps.used.get(rule, 0) >= CAPS[rule]:
            sw._ck(rule, "capped", "v5-probes")
            return False
        if sw.v5_budget < 1:
            sw._ck(rule, "capped", "step-probes")
            return False
        if rule in CONTROLLED and getattr(sw._session.cfg, "mode", "controlled") != "controlled":
            sw._ck(rule, "unobservable", "mode-not-controlled")
            return False
        self.ps.done.add((rule, kind))
        self.ps.used[rule] = self.ps.used.get(rule, 0) + 1
        sw.v5_budget -= 1
        sw.st.probes += 1
        sw._arm(rule)
        return True

    def _abort(self, sw, rule: str, why: str) -> list:
        """A probe that took its slot but could not finish: logged inconclusive, never exercised (E2: an
        unexecuted check is not a pass). The slot stays used, so a failing probe cannot loop."""
        sw._armed.discard(rule)
        sw._ck(rule, "inconclusive", why)
        return []

    # ---------------------------------------------------------------- hooks
    async def before(self, sw, session, obs, actions: list[dict]) -> None:
        """R42: attach a small generated file to an empty file field of the form being submitted; R48: local
        storage before the actions (R48s: IndexedDB too, D61); R45: the session when a flow starts."""
        from playwright.async_api import Error as PWError

        sw._session = session
        try:
            sw.ls_before = await session.page.evaluate(LS_HASH_JS)
        except PWError:
            sw.ls_before = None
        try:
            sw.idb_before = (await session.page.evaluate(IDB_JS, False))["sig"]
        except (PWError, KeyError, TypeError):
            sw.idb_before = None
        path = urlsplit(obs.url).path
        m = _FLOW.search(path)
        if m:
            k = (sw.worker, m.group(1).lower())
            if k not in self.ps.flows:
                self.ps.flows[k] = (await session.storage_state(), [])
            routes = self.ps.flows[k][1]
            if route_shape(obs.url) not in routes:
                routes.append(route_shape(obs.url))
        clicks = [a for a in actions if a["do"] in ("click", "press")]
        self.ps.canvas.pop(sw.worker, None)
        if clicks and clicks[-1].get("id"):
            el = obs.element(clicks[-1]["id"])
            if el is not None and el.tag == "canvas":
                try:
                    self.ps.canvas[sw.worker] = (clicks[-1]["id"], await session.page.evaluate(CANVAS_HASH_JS, clicks[-1]["id"]))
                except PWError:
                    pass
        if not clicks or self.ps.used.get("R42", 0) >= CAPS["R42"]:
            return
        try:
            files = session.page.locator('input[type=file]')
            n = await files.count()
            for i in range(min(n, 2)):
                f = files.nth(i)
                if await f.evaluate("e => e.files && e.files.length") or not await f.is_visible():
                    continue
                accept = (await f.get_attribute("accept")) or ""
                name = f"wt-upload-{sw.worker}-{len(self.ps.uploads) + 1}"
                if re.search(r"image|png|jpe?g|gif", accept):
                    payload = {"name": name + ".png", "mimeType": "image/png", "buffer": _PNG}
                else:
                    payload = {"name": name + ".txt", "mimeType": "text/plain", "buffer": b"webtester upload probe\n"}
                await f.set_input_files(files=[payload])
                self.ps.uploads.append((sw.worker, sw.step + 1, payload["name"], None))
                self.ps.used["R42"] = self.ps.used.get("R42", 0) + 1
        except PWError:
            return

    async def after(self, sw, session, facts, obs, done: list[dict], ev, step: int) -> list:
        """The probes due this step, in a fixed order; most cost one fresh tab."""
        from playwright.async_api import Error as PWError

        sw._session = session
        sw.v5_budget = MAX_PER_STEP
        out = []
        out += self._upload_check(sw, facts, step)
        out += await self._canvas_check(sw, session, step)
        out += await self._storage_model(sw, session, facts)
        self._note_duplicate(sw, facts, obs, done)
        for name in ("_rollback", "_references", "_client_state", "_credentials", "_address_probes", "_address_replay",
                     "_search_recall", "_no_session", "_wrong_password", "_second_account", "_sentinels", "_unchanged_save",
                     "_cancel", "_page_union", "_exports", "_step_skip", "_number_format", "_typeahead", "_strip",
                     "_double_submit", "_lost_response", "_lost_update",
                     "_back_after_logout", "_old_parent", "_mail", "_legal_input", "_unique", "_out_of_range", "_edge_dates",
                     "_search_meta", "_downloads", "_password_change", "_corrupt_storage", "_race", "_timed",
                     "_foreign_write", "_half_done", "_cycle", "_import"):
            if sw.v5_budget < 1:
                break
            used = dict(self.ps.used)
            try:
                out += await getattr(self, name)(sw, session, facts, obs, done, ev, step)
            except (PWError, KeyError, IndexError, TypeError, ValueError, AttributeError, asyncio.TimeoutError) as e:
                taken = [r for r, n in self.ps.used.items() if n > used.get(r, 0)]
                for r in taken:  # D61: the rule's own row, inconclusive (it was logged exercised before)
                    self._abort(sw, r, f"error:{type(e).__name__}")
                if not taken:
                    sw._ck(name.strip("_"), "inconclusive", f"error:{type(e).__name__}")
        return out

    # ---------------------------------------------------------------- helpers
    async def _fresh(self, session, url: str, context=None):
        """(Facts, HTTP status) of `url` in a new tab of `context` (default: the worker's), or (None, None)."""
        from playwright.async_api import Error as PWError

        from .consistency import _quiet, audit

        ctx = context or session.context
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            await asyncio.sleep(session.cfg.settle_ms / 1000)
            return await audit(session, page=page), (resp.status if resp else 0)
        except PWError:
            return None, None
        finally:
            await page.close()

    async def _second(self, sw, session):
        """A logged-in session of another account (M7), cached per worker; None when the app has none."""
        if sw.worker in self.ps.second:
            return self.ps.second[sw.worker]
        other = session.cfg.app.other_account(sw.worker)
        if other is None or session.cfg.app.login is None:
            self.ps.second[sw.worker] = None
            return None
        from .browser import BrowserSession

        s2 = BrowserSession(session.browser, session.cfg, 900 + sw.worker)
        await s2.start()
        ok = await s2.login(other)
        self.ps.second[sw.worker] = s2 if ok else None
        if not ok:
            await s2.close()
        return self.ps.second[sw.worker]

    # ---------------------------------------------------------------- R42 check
    def _upload_check(self, sw, facts, step: int) -> list:
        from .consistency import Violation

        out = []
        for i, (w, s, name, _) in enumerate(list(self.ps.uploads)):
            if w != sw.worker or step < s:
                continue
            stem = name.rsplit(".", 1)[0]
            if stem in (facts.text or "") or name in (facts.text or ""):
                self.ps.uploads.remove((w, s, name, _))
                sw._arm("R42")
            elif step >= s + 2:
                self.ps.uploads.remove((w, s, name, _))
                if any(e.worker == w and e.step >= s - 1 and e.written for e in sw.mem.events):
                    sw._arm("R42")
                    out.append(Violation("R42", f"upload|{route_shape(facts.url)}", f"the file {name!r} was attached and "
                                         "the form was accepted, but the file is not shown afterwards"))
        return out

    # ---------------------------------------------------------------- R52
    async def _rollback(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation, shown

        failed = [m for m in sw.writes if m["status"] >= 400]
        if ev is None or ev.verb != "edit" or not failed or any(200 <= m["status"] < 400 for m in sw.writes) or not ev.obj:
            return []
        if not shown(ev.obj, facts.text) or shown(ev.obj, sw.pre_text or ""):
            return []
        if not self._may(sw, "R52", route_shape(obs.url)):
            return []
        fresh, _ = await self._fresh(session, facts.url)
        if fresh is not None and not shown(ev.obj, fresh.text):
            return [Violation("R52", f"optimistic|{ev.obj[:40]}", f"the page showed {ev.obj!r} though the save failed "
                              f"(HTTP {failed[0]['status']}); a reload shows the old value")]
        return []

    # ---------------------------------------------------------------- R49
    async def _references(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation, item_matches

        # D62: each verified delete once, within 5 steps (the delete check itself can wait for a probe slot, so
        # 'verified on the step before' missed deletes verified late)
        dels = [e for e in sw.mem.events if e.worker == sw.worker and e.verb == "delete" and e.status == "verified"
                and 0 < step - e.step <= 5 and e.obj and id(e) not in self.ps.refs_checked]
        out = []
        for e in dels[:1]:
            self.ps.refs_checked.add(id(e))
            # D62 (I92): no fallback to the page's address: a comment deleted on an article page is not the article
            key = e.target
            seen: dict[str, int] = {}  # page -> last step it listed the item (D62: newest first; one probe slot a step)
            for info in sw.mem.lists.values():
                for sn in info.snaps:
                    if any((key and h == key) or norm(n) == norm(e.obj) for n, h in sn.items) \
                            and not re.search(r"activit|audit|log|history|recent", info.heading or "", re.I):
                        seen[sn.url] = max(seen.get(sn.url, -1), sn.step)
            pages = sorted(seen, key=lambda u: -seen[u])
            for u in pages[:2]:
                if not self._may(sw, "R49", u):
                    continue
                fresh, _ = await self._fresh(session, u)
                if fresh and any(item_matches(i, e.obj, key) for L in fresh.content_lists() for i in L["items"]):
                    out.append(Violation("R49", f"still-listed|{route_shape(u)}", f"{e.obj!r} was deleted (step {e.step}), "
                                         f"but {route_shape(u)} still lists it"))
        return out

    # ---------------------------------------------------------------- R48 (+ O5)
    async def _client_state(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import Violation

        if sw.writes or sw.step_requests or not done or sw.ls_before is None:
            return []
        try:
            after = await session.page.evaluate(LS_HASH_JS)
        except PWError:
            return []
        if after == sw.ls_before or norm(sw.pre_text or "") == norm(sw.post_text or ""):
            return []
        if not self._may(sw, "R48", route_shape(facts.url)):
            return []
        fresh, _ = await self._fresh(session, facts.url)
        a, b = facts.main_list(), fresh.main_list() if fresh else None
        if a and b and [norm(i["name"]) for i in a["items"]] != [norm(i["name"]) for i in b["items"]]:
            return [Violation("R48", f"lost|{route_shape(facts.url)}", "a change kept in the browser (local storage changed, "
                              "no request) is not there after a reload", f"before: {[i['name'] for i in a['items'][:5]]}")]
        return []

    # ---------------------------------------------------------------- R66
    async def _credentials(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        if ev is None or ev.verb != "account" or not ev.written or not re.search(r"regist|sign ?up|join|create account",
                                                                                  obs.url + " " + (facts.h1 or ""), re.I):
            return []
        email = next((d["value"] for d in done if d["do"] == "fill" and "@" in (d.get("value") or "")), "")
        pw = next((d["value"] for d in done if d["do"] == "fill" and "password" in (d.get("el") or "").lower()), "")
        if not email or not pw or not self._may(sw, "R66", "register"):
            return []
        from .browser import BrowserSession
        from .config import Account

        s2 = BrowserSession(session.browser, session.cfg, 950 + sw.worker)
        await s2.start()
        try:
            ok = await s2.login(Account(username=email.split("@")[0], email=email, password=pw))
        finally:
            await s2.close()
        if not ok:
            return [Violation("R66", "register-login", f"an account registered with {email!r} cannot log in with its "
                              "password")]
        return []

    # ---------------------------------------------------------------- R63
    async def _address_probes(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation, same_name

        route = route_shape(facts.url)
        if "*" not in route and "page=" not in facts.url:
            return []
        u = urlsplit(facts.url)
        segs = u.path.split("/")
        variants = []
        idx = next((i for i in range(len(segs) - 1, -1, -1) if segs[i].isdigit()), None)
        if idx is not None:
            for v in ("999999999", "-1", "abc"):
                s2 = list(segs)
                s2[idx] = v
                variants.append(urlunsplit((u.scheme, u.netloc, "/".join(s2), u.query, "")))
        elif "*" in route and segs[-1]:
            s2 = list(segs)
            s2[-1] = segs[-1] + "-zzqx404"
            variants.append(urlunsplit((u.scheme, u.netloc, "/".join(s2), u.query, "")))
        q = dict(parse_qsl(u.query))
        if "page" in q:
            for v in ("0", "9999"):
                variants.append(urlunsplit((u.scheme, u.netloc, u.path, urlencode({**q, "page": v}), "")))
        if not variants or not self._may(sw, "R63", route):
            return []
        out = []
        for v in variants:  # loaded in tabs (like a user, and like the gate's replays), not by the API client
            fresh, st = await self._fresh(session, v)
            if st is None:
                continue
            if st >= 500:
                out.append(Violation("R63", f"5xx|{route}|{v.rsplit('/', 1)[-1][:20]}", f"{v} answers HTTP {st}"))
            elif st < 300 and idx is not None and fresh and facts.h1 and fresh.h1 and same_name(fresh.h1, facts.h1) \
                    and not _NOTFOUND.search(fresh.text[:5000]):
                out.append(Violation("R63", f"same-item|{route}", f"{v} (another id) shows the same item "
                                     f"{facts.h1!r} as {facts.url}"))
            elif st == 200 and fresh and fresh.url.split("#")[0] == v and not fresh.h1.strip() and not fresh.content_lists() \
                    and not _NOTFOUND.search(fresh.text[:5000]) and len((fresh.text or "").strip()) < 400:
                out.append(Violation("R63", f"soft-404|{route}", f"{v} (no such item) answers 200 with an empty page "
                                     "instead of saying the item does not exist"))
        return out[:2]

    # ---------------------------------------------------------------- R62
    async def _address_replay(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        u = urlsplit(facts.url)
        main = facts.main_list()
        if not (u.query or u.fragment) or not main or len(main["items"]) < 2 or sw.writes:
            return []
        if not self._may(sw, "R62", route_shape(facts.url)):
            return []
        fresh, _ = await self._fresh(session, facts.url)
        if fresh is None or fresh.url.split("#")[0] != facts.url.split("#")[0]:
            return self._abort(sw, "R62", "fresh-read-moved")
        b = fresh.main_list()
        a_names = [norm(i["name"]) for i in main["items"]][:20]
        b_names = [norm(i["name"]) for i in b["items"]][:20] if b else []
        sorted_q = re.search(r"sort|order", u.query, re.I)
        if set(a_names) != set(b_names) or (sorted_q and a_names != b_names):
            heading = main.get("heading") or "the list"
            return [Violation("R62", f"replay|{route_shape(facts.url)}", f"opening {facts.url} again shows another "
                              f"{heading!r}: {len(set(a_names) ^ set(b_names))} items differ")]
        return []

    # ---------------------------------------------------------------- R23
    async def _search_recall(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import SEARCH_JS, Violation, _quiet, audit, same_name

        if not facts.search:
            return []
        cands = []
        for key, views in sw.st.cross.views.items():
            # D62 (I83): only items with an entity address, never a truncated name: list names also come from menus,
            # tabs and cards ('Recently Viewed' -> /shelves/shelf, 'Book...'), which a search rightly does not find.
            # Names the item's own page confirmed go first.
            if "*" not in route_shape(key):
                continue
            ent = sw.mem.entities.get(key)
            titles = list(ent.names) if ent else []
            for r, (name, _, _, s) in views.items():
                if name.rstrip().endswith(("...", "\u2026")):
                    continue
                if step - s >= 3 and (len(name.split()) >= 2 or len(name) >= 6) and len(name) <= 60:
                    recent = any(e.step >= step - 3 and e.obj == name for e in sw.mem.events)
                    if not recent:
                        cands.append((not any(same_name(name, t) for t in titles), route_shape(key), name))
        if not cands:
            sw._ck("R23", "unarmed", "no-known-item")
            return []
        cands = [(k, n) for _, k, n in sorted(cands, key=lambda c: c[0])]  # stable: confirmed names first
        kind = cands[0][0]
        if not self._may(sw, "R23", kind):
            return []
        names = list(dict.fromkeys(n for k, n in cands if k == kind))[:2]  # two names per probe
        for name in names:
            page = await session.context.new_page()
            try:
                await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
                await _quiet(page)
                if not await page.evaluate(SEARCH_JS, "x"):
                    return self._abort(sw, "R23", "no-search-box")
                box = page.locator('[data-wt-search="1"]').first
                await box.fill(name)
                await box.press("Enter")
                await _quiet(page, 3000)
                res = await audit(session, page=page)
            except PWError:
                return self._abort(sw, "R23", "browser-error")
            finally:
                await page.close()
            if not re.search(r"result|search|found|match", res.h1 + " " + res.title + " " + res.text[:400], re.I):
                return self._abort(sw, "R23", "no-results-page")
            if norm(name) not in norm(res.text):
                return [Violation("R23", f"recall|{kind}", f"searching for {name!r}, an item shown earlier, does not find it")]
        return []

    # ---------------------------------------------------------------- R24
    async def _no_session(self, sw, session, facts, obs, done, ev, step):
        from .consistency import _LOGINISH, Violation, same_name

        if sw.account is None or not sw.account.username:
            return []
        own = re.search(r"/(edit|settings|account|profile)\b", urlsplit(facts.url).path, re.I) and \
            sw.account.username.lower() in (facts.text or "").lower()
        if not own or not self._may(sw, "R24", route_shape(facts.url)):
            return []
        ctx = await session.browser.new_context()
        try:
            fresh, st = await self._fresh(session, facts.url, context=ctx)
        finally:
            await ctx.close()
        if fresh is None or st in (401, 403) or _LOGINISH.search(route_shape(fresh.url)) or \
                re.search(r"\b(log ?in|sign ?in)\b", fresh.text[:3000], re.I):
            return []
        if sw.account.username.lower() in fresh.text.lower() or (facts.h1 and fresh.h1 and same_name(facts.h1, fresh.h1)):
            return [Violation("R24", f"no-session|{route_shape(facts.url)}", f"{route_shape(facts.url)} shows this "
                              "account's page to a browser with no session")]
        return []

    # ---------------------------------------------------------------- R28
    async def _wrong_password(self, sw, session, facts, obs, done, ev, step):
        from .browser import BrowserSession
        from .config import Account
        from .consistency import Violation

        if sw.account is None or session.cfg.app.login is None or not self._may(sw, "R28", "login"):
            return []
        s2 = BrowserSession(session.browser, session.cfg, 970 + sw.worker)
        await s2.start()
        try:
            ok = await s2.login(Account(sw.account.username, sw.account.email, sw.account.password + "-wrong"))
            txt = (await s2.page.content())[:20000].lower()
        finally:
            await s2.close()
        if ok and sw.account.username.lower() in txt and not re.search(r"invalid|incorrect|wrong|failed", txt):
            return [Violation("R28", "wrong-password", "a wrong password logged in")]
        return []

    # ---------------------------------------------------------------- R46
    async def _second_account(self, sw, session, facts, obs, done, ev, step):
        from .consistency import _LOGINISH, Violation, same_name

        own = [e for e in sw.mem.events if e.worker == sw.worker and e.verb == "create" and e.status == "verified"
               and e.target and "*" in route_shape(e.target)]
        if not own:
            return []
        e = own[-1]
        url = urljoin(session.cfg.app.base_url, e.target)
        if session.cfg.app.login is None or session.cfg.app.other_account(sw.worker) is None:
            sw._ck("R46", "unobservable", "no-second-account")
            return []
        if not self._may(sw, "R46", route_shape(e.target)):
            return []
        s2 = await self._second(sw, session)
        if s2 is None:
            sw._ck("R46", "unobservable", "no-second-account")
            return []
        fresh, st = await self._fresh(session, url, context=s2.context)
        if fresh is None or _PRIVATE.search((facts.text or "")[:3000]):
            return []
        if st in (403, 404) or _LOGINISH.search(route_shape(fresh.url)) or not (fresh.h1 and same_name(fresh.h1, e.obj)) \
                and _NOTFOUND.search(fresh.text[:3000]):
            return [Violation("R46", f"hidden|{route_shape(e.target)}", f"{e.obj!r}, published by this account, cannot be "
                              f"opened by another account (HTTP {st}, {route_shape(fresh.url)})")]
        from .crossview import _status_of

        mine = set(sw.st.cross.page_status.get(url.split("#")[0]) or [])
        theirs = _status_of((fresh.text or "")[:1500])
        if mine and theirs and theirs not in mine:  # SM2: the requester and another account see other statuses
            return [Violation("R46", f"status|{route_shape(e.target)}", f"{e.obj!r} shows {sorted(mine)[0]!r} to this "
                              f"account and {theirs!r} to another")]
        return []

    # ---------------------------------------------------------------- R67
    async def _sentinels(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        path = urlsplit(obs.url).path
        if re.search(r"/(settings|account|profile)", path, re.I) and any(200 <= m["status"] < 400 for m in sw.writes):
            vals = [d["value"] for d in done if d["do"] == "fill" and len((d.get("value") or "").strip()) >= 6
                    and not re.search(r"password|e-?mail|search", d.get("el") or "", re.I) and "@" not in d["value"]]
            if vals:
                self.ps.sentinels.setdefault(sw.worker, {})[path] = vals
        todo = self.ps.sentinels.get(sw.worker, {})
        if not todo:
            return []
        p, vals = next(iter(todo.items()))
        if session.cfg.app.login is None or session.cfg.app.other_account(sw.worker) is None:
            sw._ck("R67", "unobservable", "no-second-account")
            return []
        if not self._may(sw, "R67", p):
            return []
        todo.pop(p)
        s2 = await self._second(sw, session)
        if s2 is None:
            sw._ck("R67", "unobservable", "no-second-account")
            return []
        fresh, _ = await self._fresh(session, urljoin(session.cfg.app.base_url, p), context=s2.context)
        leaked = [v for v in vals if fresh and v in fresh.text]
        if leaked:
            return [Violation("R67", f"leak|{route_shape(p)}", f"another account's {route_shape(p)} shows {leaked[0]!r}, "
                              "saved by this account in its own settings")]
        return []

    # ---------------------------------------------------------------- R21b
    async def _unchanged_save(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _DEAD, Violation, _quiet

        if "*" not in route_shape(facts.url) or not facts.h1:
            return []
        edit = next((o for o in facts.owner if re.match(r"edit\b", o["text"], re.I) and o.get("abs")
                     and not _DEAD.match(o.get("href") or "")), None)
        own = urlsplit(facts.url).path in sw.owned_paths
        if edit is None or (getattr(session.cfg, "mode", "controlled") != "controlled" and not own):
            return []
        if not self._may(sw, "R21b", route_shape(facts.url)):
            return []
        page = await session.context.new_page()
        try:
            await page.goto(edit["abs"], wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            btn = page.locator("button[type=submit], input[type=submit], button").filter(has_text=_SUBMIT)
            if await btn.count() == 0:
                btn = page.locator("button[type=submit], input[type=submit]")
            if await btn.count() == 0:
                return self._abort(sw, "R21b", "no-submit")
            if not await _click_write(page, btn.first, 3000):
                return self._abort(sw, "R21b", "no-write-seen")
        except PWError:
            return self._abort(sw, "R21b", "browser-error")
        finally:
            await page.close()
        fresh, _ = await self._fresh(session, facts.url)
        if fresh is None:
            return self._abort(sw, "R21b", "no-fresh-read")
        before = {norm(i["name"]) for L in facts.content_lists() for i in L["items"] if i["name"]}
        after = {norm(i["name"]) for L in fresh.content_lists() for i in L["items"] if i["name"]}
        lost = sorted(before - after)
        if fresh.h1 and fresh.h1 != facts.h1:
            return [Violation("R21b", f"heading|{route_shape(facts.url)}", f"saving {facts.h1!r} unchanged renamed it to "
                              f"{fresh.h1!r}")]
        if lost and len(lost) <= max(3, len(before) // 2):
            return [Violation("R21b", f"lost|{route_shape(facts.url)}", f"saving {facts.h1!r} unchanged removed "
                              f"{', '.join(repr(x) for x in lost[:3])} from its page")]
        return []

    # ---------------------------------------------------------------- R53
    async def _cancel(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import Violation, _quiet, same_name

        if urlsplit(facts.url).path not in sw.owned_paths or not facts.h1:
            return []
        if not self._may(sw, "R53", route_shape(facts.url)):
            return []
        page = await session.context.new_page()
        seen = []
        page.on("dialog", lambda d: (seen.append(d.message), asyncio.ensure_future(d.dismiss())))
        info = None
        try:
            await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            if not await page.evaluate(DELETE_JS):
                return self._abort(sw, "R53", "no-delete-control")
            await page.locator('[data-wt-del="1"]').first.click()
            await asyncio.sleep(0.8)
            info = await page.evaluate(CANCEL_JS)
            await page.keyboard.press("Escape")
            await _quiet(page)
        except PWError:
            return self._abort(sw, "R53", "browser-error")
        finally:
            await page.close()
        if not seen and not info:
            return []  # no confirmation: the delete may have run; FB4 is about cancelling
        fresh, st = await self._fresh(session, facts.url)
        out = []
        if fresh is None or st in (404, 410) or not (fresh.h1 and same_name(fresh.h1, facts.h1)):
            out.append(Violation("R53", f"cancel|{route_shape(facts.url)}", f"the delete of {facts.h1!r} was cancelled, "
                                 "but the item is gone"))
        msg = (seen[0] if seen else (info or {}).get("text", "")) or ""
        names = re.findall(r"[\"'“]([^\"'”]{3,60})[\"'”]", msg)
        if names and not any(same_name(n, facts.h1) for n in names):
            out.append(Violation("R53", f"names|{route_shape(facts.url)}", f"the delete confirmation for {facts.h1!r} "
                                 f"names {names[0]!r}"))
        return out

    # ---------------------------------------------------------------- R39
    async def _page_union(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        pager = [p for p in (sw.page5 or {}).get("pager") or [] if re.fullmatch(r"\d{1,2}", p["text"] or "")]
        total = facts.showing["n"] if facts.showing else None
        if len(pager) < 1 or len(pager) > 5 or not facts.main_list():
            return []
        if not self._may(sw, "R39", route_shape(facts.url)):
            return []
        seen, dup, pages = {}, None, {}
        urls = sorted({p["href"] for p in pager} | {facts.url})
        for u in urls:
            fresh, _ = await self._fresh(session, u)
            m = fresh.main_list() if fresh else None
            keys = tuple(entity_key(i["abs"]) if i.get("abs") else norm(i["name"]) for i in (m["items"] if m else []))
            if keys and keys not in pages.values():  # the list address and its 'page=1' are the same page
                pages[u] = keys
        for u, keys in pages.items():
            for k in keys:
                if k in seen and seen[k] != u:
                    dup = dup or k
                seen.setdefault(k, u)
        out = []
        if dup:
            out.append(Violation("R39", f"repeat|{route_shape(facts.url)}", f"{dup!r} appears on two pages of the list"))
        if total is not None and len(pages) == len({p["href"] for p in pager}) and len(seen) != total and len(seen) < 300:
            out.append(Violation("R39", f"union|{route_shape(facts.url)}", f"the pages list {len(seen)} items, the list "
                                 f"says {total}"))
        return out

    # ---------------------------------------------------------------- R37
    async def _exports(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        links = [c for c in (sw.page5 or {}).get("exports") or []]
        main = facts.main_list()
        if not links or not main:
            return []
        href = links[0]["href"]
        if not self._may(sw, "R37", route_shape(href)):
            return []
        st, body = await _page_fetch(session, href)
        if st is None:
            return self._abort(sw, "R37", "fetch-failed")
        if st >= 500:
            return [Violation("R37", f"fail|{route_shape(href)}", f"the export {href} answers HTTP {st}")]
        pager = (sw.page5 or {}).get("pager")
        want = facts.showing["n"] if facts.showing else (len(main["items"]) if not pager and len(main["items"]) <= 50 else None)
        if href.lower().split("?")[0].endswith(".pdf") or (body or "").startswith("%PDF"):
            return await self._pdf(sw, session, href, main, want)
        if body and body.lstrip().startswith("<") and re.search(r"print", href + " " + links[0]["text"], re.I):
            fresh, _ = await self._fresh(session, href)  # a print view: its list against the screen's
            m2 = fresh.main_list() if fresh else None
            if want is not None and m2 is not None and len(m2["items"]) < want:
                return [Violation("R37", f"print|{route_shape(href)}", f"the print view lists {len(m2['items'])} items, the "
                                  f"page {want}")]
            return []
        if body and len(body.splitlines()) > 1 and not body.lstrip().startswith("<"):
            rows = [r for r in body.splitlines() if r.strip()]
            self.ps.exported = {"body": body, "rows": len(rows), "list": facts.url, "want": want}  # R37i
            # the list's size: its stated total when it is paged, else the complete list
            if want is not None and len(rows) - 1 < want:
                return [Violation("R37", f"rows|{route_shape(href)}", f"the export has {len(rows) - 1} rows, the list has "
                                  f"{want}")]
        return []

    # ---------------------------------------------------------------- R45
    async def _step_skip(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        for (w, root), (storage, routes) in list(self.ps.flows.items()):
            if w != sw.worker or len(routes) < 3 or route_shape(facts.url) != routes[-1]:
                continue
            if not self._may(sw, "R45", root):
                continue
            ctx = await session.browser.new_context(storage_state=storage)
            try:
                fresh, _ = await self._fresh(session, facts.url, context=ctx)
            finally:
                await ctx.close()
            if fresh and route_shape(fresh.url) == routes[-1] and fresh.h1 and fresh.h1 == facts.h1:
                return [Violation("R45", f"skip|{root}", f"step {routes[-1]} of the {root} flow opens directly, without "
                                  f"its earlier steps {', '.join(routes[:-1])}")]
        return []

    # ---------------------------------------------------------------- R59, R60 (form variants)
    async def _variant(self, sw, session, obs, done, ev, pick, kind: str):
        from .consistency import mutation_plan

        if ev is None or ev.verb != "create" or not ev.written or ev.status in ("unknown", "conflict"):
            return None
        plan = mutation_plan(done, ev.obj)
        if plan is None:
            return None
        fills = [d for d in done if d["do"] in ("fill", "type") and d.get("ekey")]
        target = next((d for d in fills if pick(d)), None)
        if target is None:
            return None
        return target

    async def _number_format(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        target = await self._variant(sw, session, obs, done, ev, lambda d: _NUMERIC.search(d.get("el") or ""), "numfmt")
        if target is None or not self._may(sw, "R59", route_shape(obs.url)):
            return []
        r = await sw._submit_variant(session, obs.url, done, target, "numfmt")
        if r and r["outcome"] == "accepted" and not r["server"]:
            land = r.get("after", "")
            if re.search(r"(?<![\d.,])(1\.2345|12345|1)(?![\d.,])", land) and not re.search(r"1,?234\.5|1\.234,5", land):
                return [Violation("R59", f"numfmt|{route_shape(obs.url)}", "'1,234.5' was accepted in a number field and "
                                  "saved as another number, with no message")]
        return []

    async def _strip(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        target = await self._variant(sw, session, obs, done, ev, lambda d: d.get("ekey", "").startswith(("input|", "textarea|")),
                                     "strip")
        if target is None or not self._may(sw, "R60", route_shape(obs.url)):
            return []
        r = await sw._submit_variant(session, obs.url, done, target, "strip")
        if r and r["outcome"] == "accepted" and not r["server"] and r.get("limit") and r["length"] > r["limit"] \
                and (r["values"].get(next(iter(r["values"]), ""), "")[:200] in r.get("after", "")):
            return [Violation("R60", f"declared|{route_shape(obs.url)}", f"with the page's limit removed, the server stored "
                              f"{r['length']} characters in a field declared at most {r['limit']}")]
        return []

    # ---------------------------------------------------------------- R61
    async def _typeahead(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import SEARCH_JS, Violation, _quiet

        if not facts.search:
            return []
        names = [n for v in sw.st.cross.views.values() for (n, _, _, _) in v.values() if len(n) >= 6]
        if not names or not self._may(sw, "R61", route_shape(facts.url)):
            return []
        q = re.findall(r"\w{4,}", names[0])
        if not q:
            return self._abort(sw, "R61", "no-query-word")
        query = q[0][:5]
        page = await session.context.new_page()
        try:
            await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            if not await page.evaluate(SEARCH_JS, "x"):
                return self._abort(sw, "R61", "no-search-box")
            await page.locator('[data-wt-search="1"]').first.press_sequentially(query, delay=80)
            await asyncio.sleep(1.0)
            sugg = await page.evaluate(SUGGEST_JS)
        except PWError:
            return self._abort(sw, "R61", "browser-error")
        finally:
            await page.close()
        fold = lambda s: norm(s).translate(str.maketrans("áàâäéèêëíìîïóòôöúùûüñç", "aaaaeeeeiiiioooouuuunc"))  # noqa: E731
        if len(sugg) >= 2 and not any(fold(query) in fold(s) for s in sugg):
            return [Violation("R61", f"typeahead|{route_shape(facts.url)}", f"suggestions for {query!r} contain none of it: "
                              f"{', '.join(repr(s) for s in sugg[:3])}")]
        return []

    # ---------------------------------------------------------------- R33, R50m (controlled)
    async def _double_submit(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import Violation, _open

        if not done or done[-1]["do"] != "click":
            return []
        money = bool(_MONEY_FORM.search(obs.url + " " + " ".join(d.get("el") or "" for d in done)))
        created = ev is not None and ev.verb == "create" and ev.written
        # D62 (I82): 'Place order', 'Pay now', 'Book now' have no verb in the v4 word lists, so a money form counts
        # when its submit filled fields and had a write accepted
        paid = money and any(d["do"] in ("fill", "type", "select") for d in done) and \
            any(m["method"] not in ("GET", "HEAD", "OPTIONS") and 200 <= m["status"] < 400 for m in sw.writes)
        if not (created or paid):
            return []
        rule = "R33" if money else "R33g"  # FM7 on any create form is T3: many apps allow duplicates
        if not self._may(sw, rule, route_shape(obs.url)):
            return []
        opened = await _open(session, obs.url)
        if opened is None:
            return self._abort(sw, rule, "no-tab")
        page, net, _ = opened
        try:
            if not await _refill(page, session, done):
                return self._abort(sw, rule, "refill-failed")
            net.reset()
            submit = await _find_submit(page, done[-1])
            if submit is None:
                return self._abort(sw, rule, "no-submit")
            await submit.click()
            await submit.click(timeout=1000, force=True)
            await net.quiet(max_s=5.0)
            text = await page.evaluate("() => document.body.innerText")
        except PWError:
            return self._abort(sw, rule, "browser-error")
        finally:
            await page.close()
        ok = [s for s in net.writes if 200 <= s < 400]
        # D62: one submit can send several writes (a draft, then a publish), so twice means twice the agent's own
        per = max(1, sum(1 for m in sw.writes if m["method"] not in ("GET", "HEAD", "OPTIONS") and 200 <= m["status"] < 400))
        if len(ok) >= 2 * per and not re.search(r"duplicate|already|twice|in progress|please wait", text, re.I):
            return [Violation(rule, f"double|{route_shape(obs.url)}", f"a double submit of the form at {route_shape(obs.url)} "
                              f"was accepted twice ({len(ok)} writes, {per} per submit) with no warning")]
        return []

    async def _lost_response(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import Violation, _open

        if ev is None or ev.verb != "create" or not ev.written or not done or done[-1]["do"] != "click" or not ev.obj:
            return []
        writes = [m for m in sw.writes if m["method"] == "POST" and 200 <= m["status"] < 400]
        if not writes or not self._may(sw, "R50m", route_shape(obs.url)):
            return []
        path = writes[0]["path"]
        opened = await _open(session, obs.url)
        if opened is None:
            return self._abort(sw, "R50m", "no-tab")
        page, net, _ = opened
        rec = {"rule": "R50m", "form": route_shape(obs.url), "path": path}
        state = {"n": 0}

        async def drop(route):
            if route.request.method == "POST" and urlsplit(route.request.url).path == path and state["n"] == 0:
                state["n"] += 1
                resp = await route.fetch()
                rec["server_status"] = resp.status  # J6: the server answered; only the response is lost
                await route.abort("connectionreset")
            else:
                await route.fallback()
        try:
            await page.route("**/*", drop)
            if not await _refill(page, session, done):
                return self._abort(sw, "R50m", "refill-failed")
            submit = await _find_submit(page, done[-1])
            if submit is None:
                return self._abort(sw, "R50m", "no-submit")
            await submit.click()
            await net.quiet(max_s=5.0)
            rec["after_abort"] = (await page.evaluate("() => document.body.innerText"))[:200]
            submit = await _find_submit(page, done[-1])
            if submit is not None:
                await submit.click()
                await net.quiet(max_s=5.0)
            rec["retry_writes"] = list(net.writes)
        except PWError as e:
            rec["error"] = str(e)[:120]
            return self._abort(sw, "R50m", "browser-error")
        finally:
            self.ps.records.append(rec)
            await page.close()
        if rec.get("server_status", 500) >= 400:
            return self._abort(sw, "R50m", "server-refused")
        fresh, _ = await self._fresh(session, facts.url)
        name = ev.obj
        if fresh is not None:
            copies = norm(fresh.text).count(norm(name)[:40])
            rec["copies"] = copies
            if copies >= 3:  # the original, the lost-response write, the retry
                return [Violation("R50m", f"retry|{route_shape(obs.url)}", f"after a lost response, the retry of "
                                  f"{route_shape(obs.url)} made another record of {name!r}")]
        return []


    # ---------------------------------------------------------------- R46c (CC2, controlled, own items)
    async def _lost_update(self, sw, session, facts, obs, done, ev, step):
        """Two tabs open the same edit form; the first saves a new name, the second then saves another field
        from its stale copy. The first change vanishing with no warning is a lost update (T3: last write
        wins is a legal design)."""
        from playwright.async_api import Error as PWError

        from .consistency import _DEAD, Violation, _quiet

        if urlsplit(facts.url).path not in sw.owned_paths or not facts.h1:
            return []
        edit = next((o for o in facts.owner if re.match(r"edit\b", o["text"], re.I) and o.get("abs")
                     and not _DEAD.match(o.get("href") or "")), None)
        if edit is None or not self._may(sw, "R46c", route_shape(facts.url)):
            return []
        a, b = await session.context.new_page(), await session.context.new_page()
        marker = f"{facts.h1[:40]} lu{sw.worker}"
        try:
            for p in (a, b):
                await p.goto(edit["abs"], wait_until="domcontentloaded", timeout=15000)
                await _quiet(p)
            title = None
            for sel in ("input[name*=title i]", "input[name*=name i]", "input[type=text]"):
                if await a.locator(sel).count():
                    title = sel
                    break
            other = "textarea"
            if title is None or not await b.locator(other).count():
                return self._abort(sw, "R46c", "no-fields")
            await a.locator(title).first.fill(marker)
            await _click_write(a, a.locator("button[type=submit], input[type=submit]").first, 3000)
            await b.locator(other).first.fill("lost update probe body")
            await _click_write(b, b.locator("button[type=submit], input[type=submit]").first, 3000)
            warned = re.search(r"conflict|changed since|modified by|newer version|stale|reload", await b.evaluate(
                "() => document.body.innerText"), re.I)
        except PWError:
            return self._abort(sw, "R46c", "browser-error")
        finally:
            await a.close()
            await b.close()
        fresh, _ = await self._fresh(session, facts.url)
        if fresh and marker not in fresh.text and not warned:
            return [Violation("R46c", f"lost-update|{route_shape(facts.url)}", "two tabs edited the same item; the first "
                              "tab's saved change vanished after the second tab saved, with no warning")]
        return []


    # ---------------------------------------------------------------- D61 probes and checks (module docstring)
    async def _canvas_check(self, sw, session, step):
        """R75 (RC8): a canvas clicked or pressed on that did not change and sent nothing."""
        from .consistency import Violation

        got = self.ps.canvas.pop(sw.worker, None)
        if not got or got[1] is None or sw.writes or sw.step_requests:
            return []
        from playwright.async_api import Error as PWError

        try:
            after = await session.page.evaluate(CANVAS_HASH_JS, got[0])
        except PWError:
            return []
        sw._arm("R75")
        if after is not None and after == got[1]:
            return [Violation("R75", "no-response", "a click on the canvas changed nothing on it and sent no request")]
        return []

    async def _storage_model(self, sw, session, facts):
        """R48s (O5): what local storage and IndexedDB hold about the listed items against the list itself. Read
        only when one of them changed during the step (no write request: a client-only change)."""
        from .consistency import Violation

        from playwright.async_api import Error as PWError

        if sw.writes or (sw.ls_before is None and sw.idb_before is None):
            return []
        try:
            ls_changed = sw.ls_before is not None and await session.page.evaluate(LS_HASH_JS) != sw.ls_before
            idb = await session.page.evaluate(IDB_JS, False) if sw.idb_before is not None else {"sig": None}
            idb_changed = sw.idb_before is not None and idb["sig"] != sw.idb_before
            if not ls_changed and not idb_changed:
                return []
            stored = [norm(x) for x in await session.page.evaluate(LS_NAMES_JS)] if ls_changed else []
            if idb_changed:
                stored += [norm(x) for x in (await session.page.evaluate(IDB_JS, True))["names"]]
        except (PWError, KeyError, TypeError):
            return []
        main = facts.main_list()
        if not main or len(stored) < 2 or (sw.page5 or {}).get("pager"):
            return []
        shown = [norm(i["name"]) for i in main["items"] if i.get("name")]
        both = set(stored) & set(shown)
        if len(both) < max(2, min(len(set(stored)), len(set(shown))) // 2):
            return []  # not the same collection
        sw._arm("R48s")
        miss_page, miss_store = sorted(set(stored) - set(shown)), sorted(set(shown) - set(stored))
        if miss_page or miss_store:
            what = f"{miss_page[0]!r} is stored but not listed" if miss_page else f"{miss_store[0]!r} is listed but not stored"
            return [Violation("R48s", f"model|{route_shape(facts.url)}", f"local storage and the list disagree: {what}")]
        return []

    def _note_duplicate(self, sw, facts, obs, done):
        from .consistency import mutation_plan

        if done and not any(200 <= w["status"] < 400 for w in sw.writes) and _DUP.search(" ".join(facts.errors) + " " +
                                                                                        (sw.post_text or "")[:3000]):
            if mutation_plan(done, "") is not None:
                self.ps.dup_forms.append((sw.worker, obs.url, list(done)))

    async def _back_after_logout(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import audit, _LOGINISH, Violation

        if ev is None or ev.verb != "logout" or sw.account is None or not sw.account.username:
            return []
        if not self._may(sw, "R24b", "logout"):
            return []
        try:
            await session.page.go_back(wait_until="domcontentloaded", timeout=8000)
            back = await audit(session)
            await session.page.go_forward(wait_until="domcontentloaded", timeout=8000)
        except PWError:
            return self._abort(sw, "R24b", "browser-error")
        if not _LOGINISH.search(route_shape(back.url)) and sw.account.username.lower() in (back.text or "").lower() and \
                re.search(r"/(settings|account|profile|edit)\b", urlsplit(back.url).path, re.I):
            return [Violation("R24b", f"back|{route_shape(back.url)}", f"after logging out, Back shows {route_shape(back.url)} "
                              "with this account's data")]
        return []

    async def _old_parent(self, sw, session, facts, obs, done, ev, step):
        from .consistency import item_matches, Violation

        todo = [m for m in sw.st.cross.moved if (m[0], m[3]) not in self.ps.moved_done]
        if not todo or not self._may(sw, "R40m", route_shape(todo[0][1])):
            return []
        child, href, name, s = todo[0]
        self.ps.moved_done.add((child, s))
        fresh, _ = await self._fresh(session, href)
        if fresh and any(item_matches(i, name, child) for L in fresh.content_lists() for i in L["items"]):
            return [Violation("R40m", f"old-parent|{route_shape(href)}", f"{name!r} was moved to another parent, but its "
                              f"old parent {route_shape(href)} still lists it")]
        return []

    async def _mail(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        import datetime as dt
        import json as _json

        api = getattr(session.cfg.app, "mail_api", "")
        if not any(200 <= w["status"] < 400 for w in sw.writes) or not _MAILED.search((facts.text or "")[:4000]):
            return []
        if not api:
            sw._ck("R47m", "unobservable", "no-mail-catcher")
            return []
        to = next((d["value"] for d in done if "@" in (d.get("value") or "")), sw.account.email if sw.account else "")
        if not to or not self._may(sw, "R47m", route_shape(facts.url)):
            return []
        since = sw.t_before - 5
        for _ in range(8):
            try:
                r = await session.context.request.get(api.rstrip("/") + "/api/v1/messages?limit=50", timeout=5000)
                msgs = _json.loads(await r.text()).get("messages") or []
            except Exception:  # noqa: BLE001 - the catcher being down is not an app fault
                return self._abort(sw, "R47m", "mail-api-error")
            for m in msgs:
                addrs = [a.get("Address", "").lower() for a in m.get("To") or []]
                try:
                    t = dt.datetime.fromisoformat(str(m.get("Created", "")).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    t = since
                if to.lower() in addrs and t >= since:
                    return []
            await asyncio.sleep(1.0)
        return [Violation("R47m", f"no-mail|{route_shape(obs.url)}", f"the page says a mail was sent, but the mail catcher "
                          f"holds none for {to!r} after 8 s")]

    async def _variant_probe(self, sw, session, obs, done, ev, rule, kind, pick):
        target = await self._variant(sw, session, obs, done, ev, pick, kind)
        if target is None or not self._may(sw, rule, f"{route_shape(obs.url)}|{kind}"):
            return None, None
        return target, await sw._submit_variant(session, obs.url, done, target, kind)

    async def _legal_input(self, sw, session, facts, obs, done, ev, step):
        from .consistency import field_label, TITLE_FIELD, Violation

        target, r = await self._variant_probe(sw, session, obs, done, ev, "R16i", "intl",
                                              lambda d: TITLE_FIELD.search(field_label(d)) and not _NUMERIC.search(d.get("el") or ""))
        if r is None:
            return []
        if r["server"]:
            return [Violation("R16i", f"5xx|{route_shape(obs.url)}", f"a name with an apostrophe and an accent "
                              f"({r['values'].get(field_label(target), '')!r}) gave {r['server'][0]}")]
        if r["outcome"] == "rejected" and "shown" in r["detail"]:
            return [Violation("R16i", f"rejected|{route_shape(obs.url)}", f"the form at {route_shape(obs.url)} accepted "
                              f"{ev.obj!r} but rejects it with an apostrophe and an accent: {r['detail'][-90:]}")]
        return []

    async def _unique(self, sw, session, facts, obs, done, ev, step):
        from .consistency import field_label, mutation_plan, Violation

        mine = [x for x in self.ps.dup_forms if x[0] == sw.worker]
        if not mine:
            return []
        _, url, d0 = mine[0]
        self.ps.dup_forms.remove(mine[0])
        plan = mutation_plan(d0, "")
        if plan is None or not self._may(sw, "R16u", route_shape(url)):
            return []
        name = plan[0]
        for kind, what in (("uniq", "with a trailing space"), ("uniqnfd", "in another Unicode form or case")):
            r = await sw._submit_variant(session, url, d0, name, kind)
            if r and r["outcome"] == "accepted" and not r["server"]:
                return [Violation("R16u", f"{kind}|{route_shape(url)}", f"{name.get('value')!r} was rejected as taken in "
                                  f"{field_label(name)!r}, but the same value {what} was accepted")]
        return []

    async def _out_of_range(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        target, r = await self._variant_probe(sw, session, obs, done, ev, "R26p", "neg",
                                              lambda d: _NUMERIC.search(d.get("el") or "") and
                                              re.fullmatch(r"\d+([.,]\d+)?", (d.get("value") or "").strip()))
        out = []
        if r and r["outcome"] == "accepted" and not r["server"] and _NEGATIVE_SHOWN.search(r.get("after", "")):
            out.append(Violation("R26p", f"negative|{route_shape(obs.url)}", f"-1 was accepted in {target.get('el') or 'a number field'!r} "
                                 "and is shown, with no message"))
        if target is not None and _PAY.search(obs.url + " " + " ".join(d.get("el") or "" for d in done)) and \
                re.search(r"amount|sum|value", target.get("el") or "", re.I):
            r0 = await sw._submit_variant(session, obs.url, done, target, "zero")
            if r0 and r0["outcome"] == "accepted" and not r0["server"]:
                out.append(Violation("R26p", f"zero|{route_shape(obs.url)}", "a payment or transfer of 0 was accepted with no "
                                     "message"))
        return out

    async def _edge_dates(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        target, r = await self._variant_probe(sw, session, obs, done, ev, "R36p", "dateleap",
                                              lambda d: _DATE_FIELD.search(d.get("el") or "") and
                                              re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", d.get("value") or ""))
        out = []
        if r is not None:
            after = r.get("after", "")
            if r["outcome"] == "rejected" and "shown" in r["detail"]:
                out.append(Violation("R36p", f"leap|{route_shape(obs.url)}", "29 Feb 2024, a real date, was rejected"))
            elif r["outcome"] == "accepted" and re.search(r"2024-03-01|Mar(ch)? 0?1,? 2024|0?1 Mar(ch)? 2024", after) and \
                    not re.search(r"2024-02-29|Feb(ruary)? 29|29 Feb", after):
                out.append(Violation("R36p", f"leap-moved|{route_shape(obs.url)}", "29 Feb 2024 was saved as 1 March"))
        if target is not None and "|date|" not in (target.get("ekey") or ""):
            r2 = await sw._submit_variant(session, obs.url, done, target, "dateinv")
            if r2 and r2["outcome"] == "accepted" and not r2["server"]:
                out.append(Violation("R36p", f"invalid|{route_shape(obs.url)}", "30 Feb 2025 was accepted with no message"))
        return out

    async def _search_meta(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        if not facts.search or not self._may(sw, "R23m", route_shape(facts.url)):
            return []
        names = [n for v in sw.st.cross.views.values() for (n, _, _, _) in v.values()]
        base, _, _ = await _search_count(session, facts.url, "zqxjv")
        for ch in ("%", "_"):
            n, res, st = await _search_count(session, facts.url, ch)
            if st is not None and st >= 500:
                return [Violation("R23m", f"5xx|{ch}", f"searching for {ch!r} answers HTTP {st}")]
            if n is not None and base is not None and n >= 3 and n > base and not any(ch in x for x in names) and \
                    res is not None and not any(ch in i["name"] for L in res.content_lists() for i in L["items"]):
                return [Violation("R23m", f"wildcard|{ch}", f"searching for {ch!r} returns {n} results, none containing it "
                                  "(the character is read as a wildcard)")]
        meta = next((x for x in names if re.search(r"[%_'\\*(]", x) and len(x) >= 4), None)
        if meta:
            n, res, _ = await _search_count(session, facts.url, meta)
            if res is not None and norm(meta) not in norm(res.text):
                return [Violation("R23m", "metachar-name", f"searching for {meta!r}, an item shown earlier, does not find it")]
        return []

    async def _downloads(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        links = (sw.page5 or {}).get("downloads") or []
        if not links or not self._may(sw, "R02d", route_shape(links[0]["href"])):
            return []
        st, body = await _page_fetch(session, links[0]["href"])
        if st is None:
            return self._abort(sw, "R02d", "fetch-failed")
        if st >= 400 or not body:
            return [Violation("R02d", f"download|{route_shape(links[0]['href'])}", f"{links[0]['text']!r} answers "
                              f"{'HTTP ' + str(st) if st >= 400 else 'an empty file'}")]
        return []

    async def _pdf(self, sw, session, href, main, want):
        from .consistency import Violation

        import base64
        import io

        from playwright.async_api import Error as PWError

        try:
            import pypdf  # optional: pip install pypdf
        except ImportError:
            sw._ck("R37", "unobservable", "no-pdf-reader")
            return []
        try:
            st, b64, _ = await session.page.evaluate(B64_FETCH_JS, href)
            text = "\n".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).pages)
        except (PWError, ValueError, Exception):  # noqa: BLE001 - a broken PDF is reported below
            return [Violation("R37", f"pdf|{route_shape(href)}", f"the PDF export {href} cannot be read")]
        names = [i["name"] for i in main["items"] if i.get("name")]
        found = sum(1 for n in names if norm(n) in norm(text))
        if names and want is not None and found < min(len(names), want):
            return [Violation("R37", f"pdf|{route_shape(href)}", f"the PDF export holds {found} of the {len(names)} items "
                              "the page lists")]
        return []

    async def _password_change(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        from .browser import BrowserSession
        from .config import Account

        pws = [d["value"] for d in done if d["do"] == "fill" and "password" in (d.get("el") or "").lower() and d.get("value")]
        if sw.account is None or len(pws) < 2 or not any(200 <= w["status"] < 400 for w in sw.writes) or \
                not re.search(r"settings|account|profile|password", obs.url, re.I) or not self._may(sw, "R66", "change"):
            return []
        new, old = pws[-1], sw.account.password
        if new == old:
            return []
        res = {}
        for label, pw in (("new", new), ("old", old)):
            s2 = BrowserSession(session.browser, session.cfg, 960 + sw.worker)
            await s2.start()
            try:
                res[label] = await s2.login(Account(sw.account.username, sw.account.email, pw))
            finally:
                await s2.close()
        if not res["new"]:
            return [Violation("R66", "change-new", "after a password change the new password does not log in")]
        if res["old"]:
            return [Violation("R66", "change-old", "after a password change the old password still logs in")]
        return []

    async def _corrupt_storage(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        import json as _json

        from playwright.async_api import Error as PWError

        state = await session.storage_state()
        origins = [o for o in state.get("origins") or [] if o.get("localStorage")]
        if not origins or not self._may(sw, "R48c", "app"):
            return []
        bad = {**state, "origins": [{**o, "localStorage": [{"name": kv["name"], "value": "null"} for kv in o["localStorage"]]}
                                    for o in origins]}

        async def load(st_):
            ctx = await session.browser.new_context(storage_state=_json.loads(_json.dumps(st_)))
            page = await ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)[:120]))
            try:
                await page.goto(session.cfg.app.base_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(max(0.8, session.cfg.settle_ms / 1000))
                # D62 (I93, O3): poll to a deadline; a slower start (a refused token, a busy machine) is not a blank page
                t_end = asyncio.get_running_loop().time() + 5.0
                while True:
                    n = len((await page.evaluate("() => document.body ? document.body.innerText : ''")).strip())
                    if n >= 30 or asyncio.get_running_loop().time() > t_end:
                        return n, errs
                    await asyncio.sleep(0.25)
            except PWError:
                return 0, errs
            finally:
                await ctx.close()

        n_ok, _ = await load(state)
        n_bad, errs = await load(bad)
        if n_ok >= 30 and n_bad < 30:
            return [Violation("R48c", "null-storage", "with 'null' in its local storage the app shows a blank page"
                              + (f" ({errs[0]})" if errs else ""))]
        return []

    async def _race(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _quiet, SEARCH_JS, Violation

        if not facts.search:
            return []
        names = [n for v in sw.st.cross.views.values() for (n, _, _, _) in v.values() if len(n) >= 8]
        word = next((w for n in names for w in re.findall(r"[A-Za-z]{6,}", n)), None)
        if not word or not self._may(sw, "R77", route_shape(facts.url)):
            return []
        short, full = word[:2], word[:6]
        seen = {"prefix": 0}

        async def slow(route):
            u = route.request.url.lower()
            if route.request.method == "GET" and short.lower() in u and full.lower() not in u and \
                    route.request.resource_type in ("xhr", "fetch"):
                seen["prefix"] += 1
                await asyncio.sleep(1.5)
            await route.fallback()

        async def results(delay: bool):
            page = await session.context.new_page()
            try:
                if delay:
                    await page.route("**/*", slow)
                await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
                await _quiet(page)
                if not await page.evaluate(SEARCH_JS, "x"):
                    return None
                box = page.locator('[data-wt-search="1"]').first
                if delay:
                    await box.press_sequentially(short, delay=30)
                    await asyncio.sleep(0.35)
                    await box.press_sequentially(full[len(short):], delay=30)
                else:
                    await box.press_sequentially(full, delay=80)
                await asyncio.sleep(2.6)
                return [norm(x) for x in await page.evaluate(SUGGEST_JS)]
            except PWError:
                return None
            finally:
                await page.close()

        late = await results(True)
        if not seen["prefix"]:
            sw._armed.discard("R77")
            sw._ck("R77", "unarmed", "no-live-search")
            return []
        calm = await results(False)
        if late is None or calm is None or set(late) == set(calm):
            return []
        wrong = [x for x in late if full.lower() not in x]
        if wrong:
            return [Violation("R77", f"race|{route_shape(facts.url)}", f"typing {full!r} while the answer for {short!r} was "
                              f"slow shows {wrong[0]!r}, which does not match {full!r}")]
        return []

    async def _timed(self, sw, session, facts, obs, done, ev, step):
        from .consistency import Violation

        from playwright.async_api import Error as PWError

        m = _TIMED.search(facts.text or "")
        if not m or not self._may(sw, "R72c", route_shape(facts.url)):
            return []
        n, unit = int(m.group(2)), m.group(3).lower()
        ms = n * (1000 if unit.startswith("s") else 60000 if unit.startswith("m") else 3600000)
        page = await session.context.new_page()
        try:
            await page.clock.install()
            await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(0.6)
            t0 = await page.evaluate("() => document.body.innerText")
            await asyncio.sleep(2.2)
            t1 = await page.evaluate("() => document.body.innerText")
            if t0 == t1:
                sw._armed.discard("R72c")
                sw._ck("R72c", "unarmed", "static-text")  # no live countdown: the server holds the state
                return []
            await page.clock.fast_forward(ms + 60000)
            await asyncio.sleep(0.8)
            t2 = await page.evaluate("() => document.body.innerText")
        except PWError:
            return self._abort(sw, "R72c", "browser-error")
        finally:
            await page.close()
        m2 = _TIMED.search(t2)
        if m2 and int(m2.group(2)) >= n and m2.group(3)[:3].lower() == unit[:3]:
            return [Violation("R72c", f"timer|{route_shape(facts.url)}", f"{m.group(0)!r}: with the clock moved past that "
                              f"time, the page still says {m2.group(0)!r}")]
        return []

    async def _foreign_write(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _DEAD, _LOGINISH, _quiet, Violation

        if urlsplit(facts.url).path not in sw.owned_paths or not facts.h1:
            return []
        edit = next((o for o in facts.owner if re.match(r"edit\b", o["text"], re.I) and o.get("abs")
                     and not _DEAD.match(o.get("href") or "")), None)
        if edit is None or session.cfg.app.other_account(sw.worker) is None or not self._may(sw, "R46w", route_shape(facts.url)):
            return []
        s2 = await self._second(sw, session)
        if s2 is None:
            return []
        marker = f"{facts.h1[:40]} xw{sw.worker}"
        page = await s2.context.new_page()
        try:
            r = await page.goto(edit["abs"], wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            if (r and r.status >= 400) or _LOGINISH.search(route_shape(page.url)):
                return []
            box = page.locator("input[name*=title i], input[name*=name i]").first
            if not await box.count() or (await box.input_value()).strip() != facts.h1.strip():
                return []
            await box.fill(marker)
            await _click_write(page, page.locator("button[type=submit], input[type=submit]").first, 3000)
        except PWError:
            return self._abort(sw, "R46w", "browser-error")
        finally:
            await page.close()
        sw.st.probe_values.add(marker)
        fresh, _ = await self._fresh(session, facts.url)
        if fresh is None or marker not in (fresh.text or ""):
            return []
        await self._restore_name(session, edit["abs"], facts.h1)
        return [Violation("R46w", f"foreign|{route_shape(facts.url)}", f"another account saved {facts.h1!r}, an item of this "
                          "account, through its edit form (reverted)")]

    async def _restore_name(self, session, edit_url, name):
        from playwright.async_api import Error as PWError

        from .consistency import _quiet

        page = await session.context.new_page()
        try:
            await page.goto(edit_url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            await page.locator("input[name*=title i], input[name*=name i]").first.fill(name)
            await _click_write(page, page.locator("button[type=submit], input[type=submit]").first, 3000)
        except PWError:
            pass
        finally:
            await page.close()

    async def _half_done(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _open, Violation

        if ev is None or ev.verb != "create" or not ev.written or not ev.obj or not done or done[-1]["do"] != "click":
            return []
        paths = list(dict.fromkeys(m["path"] for m in sw.writes if m["method"] != "GET" and 200 <= m["status"] < 400))
        if len(paths) < 2 or not self._may(sw, "R52f", route_shape(obs.url)):
            return []
        last = paths[-1]
        before = norm(facts.text).count(norm(ev.obj)[:40])
        opened = await _open(session, obs.url)
        if opened is None:
            return self._abort(sw, "R52f", "no-tab")
        page, net, _ = opened
        rec = {"rule": "R52f", "form": route_shape(obs.url), "refused": last}

        async def refuse(route):
            if route.request.method != "GET" and urlsplit(route.request.url).path == last:
                await route.abort("failed")  # refused before the server: the flow's last write never lands
            else:
                await route.fallback()
        try:
            await page.route("**/*", refuse)
            if not await _refill(page, session, done):
                return self._abort(sw, "R52f", "refill-failed")
            submit = await _find_submit(page, done[-1])
            if submit is None:
                return self._abort(sw, "R52f", "no-submit")
            await submit.click()
            await net.quiet(max_s=5.0)
            said = (await page.evaluate("() => document.body.innerText"))[:3000]
        except PWError:
            return self._abort(sw, "R52f", "browser-error")
        finally:
            self.ps.records.append(rec)
            await page.close()
        rec["said_failed"] = bool(re.search(r"fail|error|could not|couldn't|try again|went wrong", said, re.I))
        fresh, _ = await self._fresh(session, facts.url)
        if fresh is None:
            return self._abort(sw, "R52f", "no-fresh-read")
        rec["copies"] = norm(fresh.text).count(norm(ev.obj)[:40])
        if rec["said_failed"] and rec["copies"] > before:
            return [Violation("R52f", f"half-done|{route_shape(obs.url)}", f"the last step of {route_shape(obs.url)} was refused "
                              f"({last}) and the app said it failed, yet another {ev.obj!r} is listed")]
        return []

    async def _cycle(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _DEAD, _quiet, same_name, _VALIDATION, Violation

        here = entity_key(facts.url)
        kids = [n for c, (p_, n, _) in sw.st.cross.parents.items() if p_ == here and c != here]
        edit = next((o for o in facts.owner if re.match(r"edit|move\b", o["text"], re.I) and o.get("abs")
                     and not _DEAD.match(o.get("href") or "")), None)
        if not kids or edit is None or not self._may(sw, "R40c", route_shape(facts.url)):
            return []
        page = await session.context.new_page()
        original = chosen = None
        accepted = False
        try:
            await page.goto(edit["abs"], wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            sel = None
            for i in range(await page.locator("select").count()):
                cand = page.locator("select").nth(i)
                lab = await cand.evaluate("e => (e.labels && e.labels[0] ? e.labels[0].innerText : '') + ' ' + e.name + ' ' + e.id")
                if _PARENT_FIELD.search(lab):
                    sel = cand
                    break
            if sel is None:
                return self._abort(sw, "R40c", "no-parent-field")
            opts = await sel.evaluate("e => [...e.options].map(o => o.text.trim())")
            original = await sel.evaluate("e => e.options[e.selectedIndex] ? e.options[e.selectedIndex].text.trim() : ''")
            chosen = next((o for o in opts for k in kids if same_name(o, k)), None)
            if chosen is None:
                return self._abort(sw, "R40c", "child-not-offered")
            await sel.select_option(label=chosen)
            writes = []
            page.on("response", lambda r: writes.append(r.status) if r.request.method != "GET" else None)
            await _click_write(page, page.locator("button[type=submit], input[type=submit]").first, 3000)
            text = await page.evaluate("() => document.body.innerText")
            accepted = any(200 <= w < 400 for w in writes) and not _VALIDATION.search(text[:3000])
        except PWError:
            return self._abort(sw, "R40c", "browser-error")
        finally:
            await page.close()
        if not accepted:
            return []
        page = await session.context.new_page()  # undo the move
        try:
            await page.goto(edit["abs"], wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            for i in range(await page.locator("select").count()):
                cand = page.locator("select").nth(i)
                if chosen in await cand.evaluate("e => [...e.options].map(o => o.text.trim())") and original:
                    await cand.select_option(label=original)
                    await _click_write(page, page.locator("button[type=submit], input[type=submit]").first, 3000)
                    break
        except PWError:
            pass
        finally:
            await page.close()
        return [Violation("R40c", f"cycle|{route_shape(facts.url)}", f"{facts.h1!r} was accepted as a child of its own child "
                          f"{chosen!r} (reverted)")]

    async def _import(self, sw, session, facts, obs, done, ev, step):
        from playwright.async_api import Error as PWError

        from .consistency import _quiet, Violation

        exp = self.ps.exported
        if not (sw.page5 or {}).get("imports") or not exp or not self._may(sw, "R37i", route_shape(facts.url)):
            return []
        page = await session.context.new_page()
        try:
            await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            await page.locator("input[type=file]").first.set_input_files(
                files=[{"name": "wt-roundtrip.csv", "mimeType": "text/csv", "buffer": exp["body"].encode("utf-8")}])
            btn = page.locator("button, input[type=submit]").filter(has_text=re.compile(r"import|upload|submit", re.I))
            await _click_write(page, (btn.first if await btn.count() else page.locator("button[type=submit], input[type=submit]").first), 5000)
            text = await page.evaluate("() => document.body.innerText")
        except PWError:
            return self._abort(sw, "R37i", "browser-error")
        finally:
            await page.close()
        m = re.search(r"\b(\d+)\s+(?:rows?|records?|items?|entries|lines)?\s*(?:were\s+|have been\s+)?(imported|created|added|"
                      r"uploaded)\b", text, re.I)
        if m and int(m.group(1)) != exp["rows"] - 1:
            return [Violation("R37i", f"report|{route_shape(facts.url)}", f"importing the app's own export of {exp['rows'] - 1} "
                              f"rows reports {m.group(0)!r}")]
        if re.search(r"\b(failed|invalid|error|could not)\b", text[:2000], re.I) and not m:
            return [Violation("R37i", f"round-trip|{route_shape(facts.url)}", "the app rejects importing its own export")]
        return []


async def _click_write(page, loc, ms: int = 3000) -> bool:
    """Click a submit control, wait until the write it sends (a form post or a fetch) is answered, then until the
    page is quiet. False when no write was answered within WRITE_WAIT_S. I61 (D61): waiting only for network idle
    could close the tab before a slow form post had started, so nothing was saved and nothing was reverted; and a
    click that starts a navigation can raise after the form was sent, so an answered write counts even then."""
    from playwright.async_api import Error as PWError

    from .consistency import _quiet

    answered: list[int] = []

    def on_response(r):
        if r.request.method not in ("GET", "HEAD", "OPTIONS"):
            answered.append(r.status)

    page.on("response", on_response)
    err = None
    try:
        await loc.click()
    except PWError as e:  # under load a click that starts a navigation can raise after the form was sent (I61)
        err = e
    t_end = asyncio.get_running_loop().time() + WRITE_WAIT_S
    while not answered and asyncio.get_running_loop().time() < t_end:
        await asyncio.sleep(0.1)
    if not answered and err is not None:
        raise err
    try:
        await _quiet(page, ms)
    except PWError:
        pass
    return bool(answered)


async def _page_fetch(session, url: str) -> tuple[int | None, str | None]:
    """GET `url` from inside the worker's page: same origin, its cookies, the browser's own network."""
    from playwright.async_api import Error as PWError

    try:
        st, body = await session.page.evaluate(
            "async (u) => { const r = await fetch(u, {credentials: 'include'}); return [r.status, (await r.text()).slice(0, 500000)]; }",
            url)
        return st, body
    except PWError:
        return None, None


async def _refill(page, session, done: list[dict]) -> bool:
    """Fill the form in `page` as the agent did (by element key), with a short suffix on text values."""
    from playwright.async_api import Error as PWError

    from .browser import OBSERVE_JS, Element
    from .consistency import _locate

    raw = await page.evaluate(OBSERVE_JS, session.cfg.max_elements * 3)
    els = [Element(**{k: v for k, v in x.items() if k in Element.__dataclass_fields__}) for x in raw["elements"]]
    for d in done[:-1]:
        if d["do"] not in ("fill", "type", "select") or not d.get("ekey"):
            continue
        el = _locate(els, d["ekey"], d.get("nth", 0))
        if el is None:
            return False
        loc = page.locator(f'[data-wt-id="{el.id}"]')
        try:
            if d["do"] == "select":
                await loc.select_option(label=d.get("value") or "")
            else:
                await loc.fill(d.get("value") or "")
        except PWError:
            return False
    page._wt_els = els  # noqa: SLF001 (kept for _find_submit)
    return True


async def _find_submit(page, last: dict):
    from .consistency import _locate

    els = getattr(page, "_wt_els", None)
    if not els or not last.get("ekey"):
        return None
    el = _locate(els, last["ekey"], last.get("nth", 0))
    return page.locator(f'[data-wt-id="{el.id}"]') if el else None


# a 1x1 PNG for upload probes of image fields
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                     "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


async def _search_count(session, url: str, query: str):
    """(results shown, facts, http status of the result page) for one search typed into the page's box."""
    from playwright.async_api import Error as PWError

    from .consistency import SEARCH_JS, _quiet, audit

    page = await session.context.new_page()
    status = {"s": None}
    page.on("response", lambda r: status.__setitem__("s", r.status) if r.request.resource_type == "document" else None)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await _quiet(page)
        if not await page.evaluate(SEARCH_JS, "x"):
            return None, None, None
        box = page.locator('[data-wt-search="1"]').first
        await box.fill(query)
        await box.press("Enter")
        await _quiet(page, 3000)
        res = await audit(session, page=page)
    except PWError:
        return None, None, None
    finally:
        await page.close()
    m = res.main_list()
    n = res.showing["n"] if res.showing else (len(m["items"]) if m else 0)
    return n, res, status["s"]
