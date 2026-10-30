"""Browser layer: one isolated Playwright context per worker.

Responsibilities:
  * observe(): a compact, LLM-readable list of visible interactive elements
    (each tagged with a short numeric id) plus a text-free structural skeleton
    of the page used for state abstraction;
  * execute(): run one primitive action against an element id;
  * implicit-oracle signals: uncaught page errors, console errors, same-origin
    HTTP 5xx responses and failed requests, buffered until drained;
  * scope gate: requests to origins outside the allowlist are aborted.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Error as PWError, Page

from .config import REPO_ROOT, Account, RunConfig
from .evidence import DRAIN_MSGS_JS, MAX_BODY_BYTES, MAX_NET_RECORDS, MAX_POST_CHARS, MSG_JS

FAULT_MARKER = "[wt-fault] "  # console line an injected fault logs when it first fires (exposure)
NET_TYPES = ("xhr", "fetch", "document")  # requests `settle` waits for
BODY_TYPES = ("xhr", "fetch")  # responses whose JSON body the evidence layer keeps (D58)
QUIET_S, QUIET_MAX_S = 0.3, 3.0

# Page text of a freshly loaded page for inferred checks (reload, /path): innerText plus the values
# of visible text fields, which innerText leaves out (a saved bio shown back in its textarea, D46).
# Not used for 'now' checks, where a field may still hold typed text. Passwords are skipped.
TEXT_JS = r"""() => {
  if (!document.body) return '';
  const vals = [];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const t = (el.getAttribute('type') || '').toLowerCase();
    if (['password', 'hidden', 'checkbox', 'radio', 'submit', 'button', 'file'].includes(t)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const v = el.tagName === 'SELECT' ? (el.selectedOptions[0] ? el.selectedOptions[0].text : '') : el.value;
    if (v && v.trim()) vals.push(v);
  }
  return document.body.innerText + (vals.length ? '\n' + vals.join('\n') : '');
}"""
INNER_TEXT_JS = "() => document.body ? document.body.innerText : ''"

# Runs in the page. Tags visible interactive elements with data-wt-id and
# returns their descriptors, plus a skeleton of the visible DOM in which text
# and attributes are dropped and siblings with identical structure are merged
# (the "merge" idea from Judge, TOSEM'26), so lists of any length collapse.
# D61, once per URL: interaction modalities the harness cannot drive (R6, reported as coverage gaps), signs of a
# development build (O4), and the centre of the main list's first row (hovered so hover-only controls show)
# R4 (D61): the active context a page is in, from a context switcher outside any form: a select whose label,
# name or id names a workspace, team, store, project and the like (its selected option), or a control whose text
# reads 'Workspace: Acme'. Empty when the page has none (most apps put the context in the address).
CONTEXT_JS = r"""() => {
  const rx = /\b(workspace|organi[sz]ation|org|team|tenant|store|shop|project|company|branch|space|board|site)\b/i;
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  for (const s of document.querySelectorAll('select')) {
    if (s.form || !vis(s)) continue;
    const lab = (s.labels && s.labels[0] ? s.labels[0].innerText : '') + ' ' + (s.name || '') + ' ' + (s.id || '') + ' ' +
      (s.getAttribute('aria-label') || '');
    if (rx.test(lab) && s.selectedOptions[0]) return lab.trim().split(/\s+/)[0].toLowerCase() + '=' + s.selectedOptions[0].text.trim().slice(0, 40);
  }
  for (const b of document.querySelectorAll('header button, nav button, header [aria-haspopup], nav [aria-haspopup]')) {
    const m = (b.innerText || '').trim().match(/^([A-Za-z ]{2,20}):\s*(.{1,40})$/);
    if (m && rx.test(m[1]) && vis(b)) return m[1].trim().toLowerCase() + '=' + m[2].trim();
  }
  return '';
}"""
LOOK_JS = r"""() => {
  const n = s => document.querySelectorAll(s).length;
  const modalities = {canvas: n('canvas'), drag: n('[draggable=true]'), context_menu: n('[oncontextmenu], [data-context-menu]'),
    shortcuts: n('[accesskey], kbd'), media: n('video, audio'), long_press: n('[data-long-press], [data-longpress]'),
    file_drop: n('[class*=dropzone], [class*=drop-zone]')};
  const dev = [];
  for (const sc of document.querySelectorAll('script[src]')) {
    const m = /@vite\/client|webpack-dev-server|__webpack_hmr|react-refresh|sockjs-node|livereload|_debugbar/.exec(sc.src);
    if (m) dev.push(m[0]);
  }
  if (document.querySelector('.phpdebugbar, #__next-build-watcher, [data-nextjs-toast]')) dev.push('dev-overlay');
  let best = null;
  for (const l of document.querySelectorAll('tbody, ul, ol, [role=list], [role=grid]')) {
    const rows = [...l.children].filter(r => r.getBoundingClientRect().height > 0);
    if (rows.length >= 2 && (!best || rows.length > best.length)) best = rows;
  }
  let row = null;
  if (best) { const r = best[0].getBoundingClientRect(); if (r.top >= 0 && r.bottom <= innerHeight) row = [r.left + r.width / 2, r.top + r.height / 2]; }
  return {modalities, dev: [...new Set(dev)], row};
}"""

OBSERVE_JS = r"""
(arg) => {
  // v5 (D60): `arg` is {max, pierce} (or a number: v4). Up to `max` candidates are read; the session then
  // ranks them (not yet activated first) and keeps cfg.max_elements. pierce: open shadow roots and
  // same-origin iframes (one level); an iframe element's id is '<frame>.<n>' and its iframe carries data-wt-frame.
  const maxEls = typeof arg === 'number' ? arg : arg.max;
  const pierce = typeof arg === 'object' && !!arg.pierce;
  const visible = (el) => {
    if (el.checkVisibility) { if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false; }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const SEL = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=tab], ' +
              '[role=checkbox], [role=menuitem], [role=switch], [contenteditable=""], [contenteditable=true], [onclick]';
  // Framework click handlers (Angular (click), React onClick) leave no attribute behind, so an
  // <a> without href or an icon <i> is invisible to SEL. Their usual tell is cursor:pointer: take
  // the outermost such element (cursor is inherited) that is not inside an element SEL already
  // takes (D43, I33).
  const pointerCursor = new Map();
  const isPointer = (el) => {
    if (!el) return false;
    if (!pointerCursor.has(el)) pointerCursor.set(el, getComputedStyle(el).cursor === 'pointer');
    return pointerCursor.get(el);
  };
  const byCursor = (el) => isPointer(el) && !isPointer(el.parentElement) && !(el.parentElement && el.parentElement.closest(SEL));
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const els = [];
  let next = 1, frames = 0, candidates = 0;
  const walk = function* (root, frame) {
    for (const el of root.querySelectorAll('*')) {
      if (el.hasAttribute('data-wt-id')) el.removeAttribute('data-wt-id');
      yield [el, frame];
      if (pierce && el.shadowRoot) yield* walk(el.shadowRoot, frame);
      if (pierce && frame === null && el.tagName === 'IFRAME') {
        let doc = null;
        try { doc = el.contentDocument; } catch (e) { doc = null; }
        if (doc && doc.body) { const k = frames++; el.setAttribute('data-wt-frame', String(k)); yield* walk(doc.body, k); }
      }
    }
  };
  for (const [el, frame] of document.body ? walk(document.body, null) : []) {
    const std = el.matches(SEL);
    if (!std && !byCursor(el)) continue;
    if (!visible(el)) continue;
    candidates++;
    if (els.length >= maxEls) continue;
    const id = frame === null ? String(next++) : frame + '.' + String(next++);
    el.setAttribute('data-wt-id', id);
    const tag = el.tagName.toLowerCase();
    let label = '';
    if (el.labels && el.labels.length) label = el.labels[0].innerText;
    label = label || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('name') || '';
    // An icon taken by its cursor has no text; its class names (e.g. 'ion-trash-a') say what it does.
    if (!std && !label && !clean(el.innerText, 1)) label = el.getAttribute('class') || '';
    let options = [];
    if (tag === 'select') options = Array.from(el.options).slice(0, 15).map((o) => clean(o.text, 30));
    const form = el.form || el.closest('form');
    // Already-selected control (current page number, open tab): ARIA state or a Bootstrap-style
    // 'active' class on the element or its parent. Clicking it is not expected to change anything (D46).
    const isActive = (e) => !!e && e !== document.body && (
      (e.getAttribute('aria-current') || 'false') !== 'false' || e.getAttribute('aria-selected') === 'true' ||
      e.getAttribute('aria-pressed') === 'true' || e.classList.contains('active'));
    els.push({
      active: isActive(el) || isActive(el.parentElement),
      id, tag,
      type: (el.getAttribute('type') || '').toLowerCase(),
      role: el.getAttribute('role') || '',
      text: clean(tag === 'input' || tag === 'textarea' || tag === 'select' ? '' : el.innerText, 80),
      label: clean(label, 60),
      href: tag === 'a' ? (el.getAttribute('href') || '') : '',
      value: (tag === 'input' || tag === 'textarea') && el.type !== 'password' ? clean(el.value, 60) : '',
      checked: (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : null,
      disabled: !!el.disabled,
      options,
      form: form ? Array.from((el.ownerDocument || document).querySelectorAll('form')).indexOf(form) : -1,
      cls: (el.getAttribute('class') || '').slice(0, 80),
    });
  }
  const SKIP = new Set(['script', 'style', 'noscript', 'svg', 'link', 'meta', 'template', 'br']);
  const sig = (el, depth) => {
    const tag = el.tagName.toLowerCase();
    if (SKIP.has(tag) || depth > 30) return '';
    if (depth > 0 && !visible(el)) return '';
    let head = tag;
    const role = el.getAttribute('role');
    if (role) head += '[' + role + ']';
    if (tag === 'input') head += ':' + (el.getAttribute('type') || 'text');
    const kids = [];
    const seen = new Set();
    for (const c of el.children) {
      const s = sig(c, depth + 1);
      if (!s || seen.has(s)) continue;
      seen.add(s);
      kids.push(s);
    }
    return kids.length ? head + '(' + kids.join(',') + ')' : head;
  };
  return {
    url: location.href,
    title: document.title,
    elements: els,
    candidates,
    skeleton: document.body ? sig(document.body, 0) : '',
    text: clean(document.body ? document.body.innerText : '', 4000),
  };
}
"""


SCROLL_JS = """async () => {
  const H = () => (document.scrollingElement || document.body).scrollHeight;
  let y = 0;
  for (let i = 0; i < 10 && y < H(); i++) { y += innerHeight; scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); }
  scrollTo(0, 0);
  return y;
}"""
# R9: a cookie wall or newsletter pop-up, closed by a known button text inside a container that says what it is
POPUP_JS = r"""() => {
  const RX = /^(accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree|got it|ok|okay|no,? thanks|not now|close|dismiss|\u00d7|\u2715)$/i;
  const BOX = /cookie|consent|gdpr|onetrust|cc-banner|newsletter|subscribe|popup|promo|chat-widget|intercom/i;
  const out = [];
  for (const b of document.querySelectorAll('button, a[role=button], [role=button], input[type=button]')) {
    const t = (b.innerText || b.value || b.getAttribute('aria-label') || '').trim();
    if (!RX.test(t)) continue;
    let c = b, hit = false;
    for (let i = 0; i < 6 && c && c.getAttribute; i++, c = c.parentElement) {
      const cls = typeof c.className === 'string' ? c.className : '';
      if (BOX.test((c.id || '') + ' ' + cls + ' ' + (c.getAttribute('aria-label') || ''))) { hit = true; break; }
    }
    const r = b.getBoundingClientRect();
    if (hit && r.width > 0 && r.height > 0) { b.click(); out.push(t); if (out.length >= 2) break; }
  }
  return out;
}"""
# R12 (D60, measured only, cfg.coverage_metrics): elements given a click-like listener, and which of them a
# click reached. The listener count misses handlers set by property (onclick=) on elements SEL already takes.
LISTENERS_JS = r"""(() => {
  const CLICKY = new Set(['click', 'mousedown', 'mouseup', 'pointerdown', 'pointerup', 'touchstart', 'keydown']);
  const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    try { if (CLICKY.has(type) && this instanceof Element) this.setAttribute('data-wt-l', '1'); } catch (e) {}
    return orig.call(this, type, fn, opts);
  };
  orig.call(document, 'click', (ev) => {
    for (let n = ev.target; n && n.setAttribute; n = n.parentElement) if (n.hasAttribute('data-wt-l')) n.setAttribute('data-wt-hit', '1');
  }, true);
})();"""
HANDLER_COUNT_JS = "() => [document.querySelectorAll('[data-wt-l]').length, document.querySelectorAll('[data-wt-hit]').length]"
SESSION_STORAGE_JS = "() => ({origin: location.origin, items: Object.fromEntries(Object.entries(sessionStorage))})"
# O4: console lines that dev servers and frameworks print in development builds; not app failures
DEV_NOISE = re.compile(r"\[HMR\]|\[vite\]|\[WDS\]|webpack|Download the React DevTools|development mode|"
                       r"Lit is in dev mode|DevTools failed to load source map|\[Fast Refresh\]", re.I)


@dataclass
class Element:
    id: str
    tag: str
    type: str = ""
    role: str = ""
    text: str = ""
    label: str = ""
    href: str = ""
    value: str = ""
    checked: bool | None = None
    disabled: bool = False
    options: list[str] = field(default_factory=list)
    form: int = -1
    active: bool = False  # already-selected control (D46); not part of key()
    cls: str = ""  # class names (v4: lets memory classify icon controls, e.g. 'ion-heart'); not in key() or describe()

    def key(self) -> str:
        """Position-independent identity, used to recognise 'the same action' across visits."""
        return f"{self.tag}|{self.type}|{self.role}|{self.text[:40]}|{self.label[:40]}|{self.href}"

    def describe(self) -> str:
        kind = self.tag + (f"[{self.type}]" if self.type and self.tag == "input" else "")
        if self.role and self.role not in ("button", "link"):
            kind += f"({self.role})"
        parts = [f"[{self.id}] {kind}"]
        if self.text:
            parts.append(f'"{self.text}"')
        if self.label and self.label != self.text:
            parts.append(f'label="{self.label}"')
        if self.href:
            parts.append(f"href={self.href}")
        if self.value:
            parts.append(f'value="{self.value}"')
        if self.checked is not None:
            parts.append("checked" if self.checked else "unchecked")
        if self.options:
            parts.append("options=" + "|".join(self.options))
        if self.disabled:
            parts.append("disabled")
        if self.active:
            parts.append("active")
        if self.form >= 0:
            parts.append(f"form#{self.form}")
        return " ".join(parts)


@dataclass
class Observation:
    url: str
    title: str
    elements: list[Element]
    skeleton: str
    text: str
    ts: float = field(default_factory=time.time)
    candidates: int = 0  # X1: interactive elements on the page before the cap (dropped = candidates - len(elements))
    context: str = ""  # R4 (D61): the active workspace, team or store of a context switcher ('' = none)

    def element(self, eid: str) -> Element | None:
        return next((e for e in self.elements if e.id == str(eid)), None)


@dataclass
class Signal:
    """A raw implicit-oracle observation (not yet a finding)."""

    kind: str  # page_error | console_error | http_5xx | request_failed
    message: str
    url: str  # page URL when it happened
    detail: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class ActionResult:
    ok: bool
    error: str = ""
    url_before: str = ""
    url_after: str = ""
    out_of_scope: bool = False


class BrowserSession:
    """One worker's isolated browser context (own cookies and storage)."""

    def __init__(self, browser: Browser, cfg: RunConfig, worker: int):
        self.browser = browser
        self.cfg = cfg
        self.worker = worker
        self.origins = cfg.app.origins()
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._signals: list[Signal] = []
        self._exposures: list[str] = []
        self.injector_errors: list[str] = []  # written to the trace by the worker
        self.silent_triggers: list[str] = []  # injected faults whose trigger held but changed nothing
        self.last_in_scope_url = cfg.app.base_url
        self._pending: set = set()  # in-flight xhr/fetch/document requests (settle waits for them, D46)
        self._last_net = 0.0
        self.mutations: list[dict] = []  # same-origin write requests (method != GET) and their status (v4, D49)
        # v5 evidence layer (D58), only with cfg.capture_evidence: network timeline with JSON bodies
        self.evidence = bool(getattr(cfg, "capture_evidence", False))
        self.net: list[dict] = []
        self._net_seq = 0
        self._body_tasks: set = set()
        # v5 (D60): reach and safety bookkeeping, reported in the trace's `session` event
        self.activated: dict[str, set] = {}  # X1: route shape -> element keys acted on (ranked last)
        self._scrolled: set[str] = set()
        self._popup_checked: set[str] = set()
        self.dismissed: list[str] = []  # R9
        self.dialogs: list[dict] = []  # R6
        self.blocked: list[dict] = []  # S1: writes the execution mode refused
        self.owned: set[str] = set()  # S1 reversible: paths of items this worker created
        self.dropped = 0  # X1: elements beyond the cap, summed over observations
        self.settle_times: list[float] = []  # O3: seconds until an intent's effect showed in a fresh view
        self.handlers: dict[str, tuple] = {}  # R12: route shape -> (elements with listeners, of them clicked)
        self._cdp = None  # JS coverage (Chromium CDP Profiler), only with cfg.coverage_metrics
        self.js_coverage: dict | None = None
        # D61: R6 hover, unsupported modalities, O4 build mode, safety counters (group 11)
        self._looked: set[str] = set()
        self.modalities: dict[str, set] = {}  # kind -> route shapes where the page offers it
        self.dev_markers: set[str] = set()
        self.out_of_scope_blocked = 0
        self.seen: dict[str, set] = {}  # X1: route shape -> element keys observed
        self.mode_violations: list[dict] = []

    # ---------- lifecycle ----------
    async def start(self, storage_state: dict | None = None, session_storage: dict | None = None,
                    context_kw: dict | None = None) -> None:
        """`storage_state` (cookies + localStorage) restores a session: used by the evidence gate's replays.
        `session_storage` ({origin, items}, C1) is restored once per tab by an init script. `context_kw`
        overrides context options (M10 axes: timezone_id, locale, viewport)."""
        kw = {"viewport": {"width": 1280, "height": 900}, "locale": "en-US", **(context_kw or {})}
        self.context = await self.browser.new_context(storage_state=storage_state, **kw)
        if session_storage and session_storage.get("items"):
            await self.context.add_init_script(script=(
                f"if (location.origin === {json.dumps(session_storage.get('origin', ''))} && "
                "!sessionStorage.getItem('__wt_ss')) { const d = " + json.dumps(session_storage["items"]) +
                "; for (const k in d) sessionStorage.setItem(k, d[k]); sessionStorage.setItem('__wt_ss', '1'); }"))
        self.context.set_default_timeout(self.cfg.action_timeout_ms)
        if self.cfg.app.fault_script and self.cfg.client_faults:
            await self.context.add_init_script(script=f"window.__WT_FAULTS__ = {json.dumps(list(self.cfg.client_faults))};")
            await self.context.add_init_script(path=str(REPO_ROOT / self.cfg.app.fault_script))
        for path in getattr(self.cfg.app, "init_scripts", ()) or ():
            await self.context.add_init_script(path=str(REPO_ROOT / path))
        if getattr(self.cfg, "coverage_metrics", False):
            await self.context.add_init_script(script=LISTENERS_JS)
        if self.evidence:
            await self.context.add_init_script(script=MSG_JS)
        await self.context.route("**/*", self._route)
        self.page = await self.context.new_page()
        self._wire(self.page)
        if getattr(self.cfg, "coverage_metrics", False):
            try:
                self._cdp = await self.context.new_cdp_session(self.page)
                await self._cdp.send("Profiler.enable")
                await self._cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": False})
            except PWError:
                self._cdp = None  # not Chromium

    async def close(self) -> None:
        if self._cdp is not None:
            try:
                res = await self._cdp.send("Profiler.takePreciseCoverage")
                fns = [f for sc in res.get("result", []) if self.in_scope(sc.get("url") or "") and sc.get("url")
                       for f in sc.get("functions", [])]
                self.js_coverage = {"functions": len(fns),
                                    "executed": sum(1 for f in fns if any(r.get("count", 0) > 0 for r in f.get("ranges", [])))}
            except PWError:
                pass
        if self.context:
            await self.context.close()

    def in_scope(self, url: str) -> bool:
        u = urlsplit(url)
        if u.scheme in ("data", "blob", "about"):
            return True
        return f"{u.scheme}://{u.netloc}" in self.origins

    async def _route(self, route) -> None:
        req = route.request
        if not self.in_scope(req.url):
            self.out_of_scope_blocked += 1
            await route.abort("blockedbyclient")
            return
        why = self.mode_refuses(req.method, req.url)
        if why:
            self.blocked.append({"method": req.method, "path": urlsplit(req.url).path, "why": why})
            await route.abort("blockedbyclient")
            return
        await route.fallback()  # D61: to a handler registered before this one (a served test app), else the network

    def mode_refuses(self, method: str, url: str) -> str:
        """S1, enforced here rather than in the prompt: read-only refuses every write but the login form;
        reversible refuses deletes and updates of items this worker did not create; controlled allows all."""
        mode = getattr(self.cfg, "mode", "controlled")
        if mode == "controlled" or method in ("GET", "HEAD", "OPTIONS"):
            return ""
        path = urlsplit(url).path
        login = self.cfg.app.login.path if self.cfg.app.login else "/login"
        if path.rstrip("/").endswith(login.rstrip("/")) or re.search(r"/(login|session|auth|token)\b", path):
            return ""
        if mode == "read-only":
            return "read-only"
        if mode == "reversible" and method in ("DELETE", "PUT", "PATCH") and not any(o and o in path for o in self.owned):
            return "reversible: not created by this run"
        return ""

    def _wire(self, page: Page) -> None:
        page.on("pageerror", lambda exc: self._signals.append(
            Signal("page_error", str(exc).split("\n")[0][:300], page.url, {"stack": (getattr(exc, "stack", "") or "")[:1500]})))
        page.on("console", self._on_console)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog) -> None:
        """R6: native alert/confirm/prompt are logged and accepted (Playwright would dismiss them silently,
        so a delete behind confirm() never happened); never left blocking."""
        accept = bool(getattr(self.cfg, "accept_dialogs", True))
        self.dialogs.append({"type": dialog.type, "message": dialog.message[:200], "url": self.page.url if self.page else "",
                             "accepted": accept})
        del self.dialogs[:-50]
        asyncio.ensure_future(dialog.accept() if accept else dialog.dismiss())

    def _on_request(self, req) -> None:
        if req.resource_type in NET_TYPES:
            self._pending.add(req)
            self._last_net = time.monotonic()

    def _on_request_done(self, req) -> None:
        if req in self._pending:
            self._pending.discard(req)
            self._last_net = time.monotonic()

    def _on_console(self, msg) -> None:
        text = msg.text
        if text.startswith(FAULT_MARKER):  # ground truth, never a finding
            parts = text[len(FAULT_MARKER):].split()
            if parts[-1:] == ["no-change"]:  # trigger held, nothing visible changed (D36)
                self.silent_triggers.append(parts[0])
            else:
                self._exposures.append(parts[0])
            return
        if text.startswith("[wt-fault-error] "):  # our injector's own error, not the app's (D33 A5)
            self.injector_errors.append(text[:300])
            return
        if msg.type != "error":
            return
        if DEV_NOISE.search(text):
            self.dev_markers.add("console")  # O4: the app runs a development build
        if getattr(self.cfg, "dev_noise", True) and DEV_NOISE.search(text):
            return  # O4: dev-server and framework development-build messages
        # Requests we aborted ourselves (scope gate) are not app failures.
        if "ERR_BLOCKED_BY_CLIENT" in text:
            return
        # Chrome logs every non-2xx response as "Failed to load resource". 4xx is
        # usually correct behaviour (validation, auth), and 5xx / network failures
        # are already captured by the response and requestfailed listeners.
        if text.startswith("Failed to load resource"):
            return
        loc = msg.location or {}
        self._signals.append(Signal("console_error", text[:300], self.page.url if self.page else "", {"source": loc.get("url", "")}))

    def _on_response(self, resp) -> None:
        req = resp.request
        if req.method not in ("GET", "HEAD", "OPTIONS") and req.resource_type in NET_TYPES and self.in_scope(resp.url):
            self.mutations.append({"method": req.method, "path": urlsplit(resp.url).path, "status": resp.status})
            del self.mutations[:-50]
            if self.mode_refuses(req.method, resp.url):  # group 11: a write the mode forbids reached the server
                self.mode_violations.append({"method": req.method, "path": urlsplit(resp.url).path})
        if self.evidence and req.resource_type in NET_TYPES and self.in_scope(resp.url):
            self._record(resp)
        if resp.status >= 500 and self.in_scope(resp.url):
            req = resp.request
            self._signals.append(Signal(
                "http_5xx", f"{req.method} {urlsplit(resp.url).path} -> {resp.status}",
                self.page.url if self.page else "",
                {"method": req.method, "url": resp.url, "status": resp.status, "post": (req.post_data or "")[:500]},
            ))

    def _on_request_failed(self, req) -> None:
        failure = req.failure or ""
        if not self.in_scope(req.url) or "ERR_ABORTED" in failure or "BLOCKED_BY_CLIENT" in failure:
            return  # navigations cancel in-flight requests routinely
        self._signals.append(Signal(
            "request_failed", f"{req.method} {urlsplit(req.url).path}: {failure}",
            self.page.url if self.page else "", {"url": req.url},
        ))

    # ---------- v5 evidence layer (D58) ----------
    def _record(self, resp) -> None:
        req = resp.request
        self._net_seq += 1
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        rec = {"seq": self._net_seq, "t": time.time(), "method": req.method, "url": resp.url,
               "path": urlsplit(resp.url).path, "status": resp.status, "type": req.resource_type, "ctype": ctype,
               "page": self.page.url if self.page else ""}
        if req.method not in ("GET", "HEAD", "OPTIONS"):
            rec["sent"] = (req.post_data or "")[:MAX_POST_CHARS]
        self.net.append(rec)
        del self.net[:-MAX_NET_RECORDS]
        if req.resource_type in BODY_TYPES and "json" in ctype:
            task = asyncio.get_running_loop().create_task(self._grab_body(resp, rec))
            self._body_tasks.add(task)
            task.add_done_callback(self._body_tasks.discard)

    @staticmethod
    async def _grab_body(resp, rec: dict) -> None:
        try:
            raw = await resp.body()
        except Exception:  # noqa: BLE001 (redirects, closed pages, aborted requests carry no body)
            rec["body_error"] = "unavailable"
            return
        if len(raw) > MAX_BODY_BYTES:
            rec["body_error"] = f"too large ({len(raw)} bytes)"
            return
        try:
            rec["body"] = json.loads(raw)
        except ValueError:
            rec["body_error"] = "not JSON"

    async def flush_bodies(self, timeout_s: float = 2.0) -> None:
        """Wait (bounded) for the bodies of responses already seen to be read."""
        if self._body_tasks:
            await asyncio.wait(set(self._body_tasks), timeout=timeout_s)

    def net_mark(self) -> int:
        return self._net_seq

    def net_since(self, mark: int) -> list[dict]:
        return [r for r in self.net if r["seq"] > mark]

    async def drain_messages(self, page: Page | None = None) -> list[dict]:
        """Transient messages (toasts, flashes, alerts) caught since the last drain, oldest first."""
        if not self.evidence:
            return []
        try:
            return await (page or self.page).evaluate(DRAIN_MSGS_JS)
        except PWError:
            return []

    def drain_signals(self) -> list[Signal]:
        out, self._signals = self._signals, []
        return out

    def drain_exposures(self) -> list[str]:
        """Injected faults that fired since the last call (exposure, for analysis only)."""
        out, self._exposures = self._exposures, []
        return out

    # ---------- observation ----------
    async def settle(self) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=2500)
        except PWError:
            pass
        await self.wait_quiet()
        await asyncio.sleep(self.cfg.settle_ms / 1000)

    async def wait_quiet(self, quiet_s: float = QUIET_S, max_s: float = QUIET_MAX_S) -> None:
        """In a single-page app `networkidle` is reached once at load and returns at once after
        a click, so wait until no xhr/fetch/document request has been in flight for `quiet_s`
        (at most `max_s`). Without this, checks ran before the app answered (D46)."""
        await asyncio.sleep(0.05)  # let a click's requests start
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            if not self._pending and time.monotonic() - self._last_net >= quiet_s:
                return
            await asyncio.sleep(0.05)

    async def observe(self) -> Observation:
        await self._first_look()
        pool = max(1, int(getattr(self.cfg, "observe_pool", 1)))
        pierce = bool(getattr(self.cfg, "pierce", False))
        arg = {"max": self.cfg.max_elements * pool, "pierce": pierce} if pool > 1 or pierce else self.cfg.max_elements
        for attempt in range(3):
            try:
                raw = await self.page.evaluate(OBSERVE_JS, arg)
                break
            except PWError:
                if attempt == 2:
                    raise
                await self.settle()  # page navigated mid-evaluation
        blocked = tuple(t.lower() for t in self.cfg.app.blocked_text)
        els = [Element(**{k: v for k, v in e.items() if k in Element.__dataclass_fields__}) for e in raw["elements"]]
        if blocked:
            els = [e for e in els if not any(b in (e.text + " " + e.label).lower() for b in blocked)]
        from .state import route_shape as _rs

        self.seen.setdefault(_rs(raw["url"]), set()).update(e.key() for e in els)  # X1: controls seen per page kind
        els = self._rank(raw["url"], els)
        if getattr(self.cfg, "coverage_metrics", False):
            try:
                n, hit = await self.page.evaluate(HANDLER_COUNT_JS)
                from .state import route_shape

                r = route_shape(raw["url"])
                old = self.handlers.get(r, (0, 0))
                self.handlers[r] = (max(old[0], n), max(old[1], hit))
            except PWError:
                pass
        cand = raw.get("candidates", len(els))
        self.dropped += max(0, cand - len(els))
        try:
            ctx = await self.page.evaluate(CONTEXT_JS) or ""
        except PWError:
            ctx = ""
        return Observation(raw["url"], raw["title"], els, raw["skeleton"], raw["text"], candidates=cand, context=ctx)

    def _rank(self, url: str, els: list[Element]) -> list[Element]:
        """X1: keep cfg.max_elements of the pool: the first 15 in page order (header and navigation), then
        elements not yet acted on in this kind of page, then the rest; shown in page order."""
        cap = self.cfg.max_elements
        if len(els) <= cap:
            return els
        from .state import route_shape

        done = self.activated.get(route_shape(url), set())
        head, rest = els[:15], els[15:]
        rest = [e for e in rest if e.key() not in done] + [e for e in rest if e.key() in done]
        keep = {id(e) for e in head + rest[:cap - len(head)]}
        return [e for e in els if id(e) in keep]

    def note_activated(self, url: str, key: str) -> None:
        from .state import route_shape

        self.activated.setdefault(route_shape(url), set()).add(key)

    async def _first_look(self) -> None:
        """Once per URL: close a cookie wall or newsletter pop-up (R9), then scroll to the end and back so
        lazy content loads (X1)."""
        url = (self.page.url or "").split("#")[0]
        if not url.startswith("http"):
            return
        try:
            if getattr(self.cfg, "dismiss_popups", False) and url not in self._popup_checked:
                self._popup_checked.add(url)
                hit = await self.page.evaluate(POPUP_JS)
                if hit:
                    self.dismissed += [f"{url} {t}" for t in hit]
                    await self.settle()
            if getattr(self.cfg, "scroll_once", False) and url not in self._scrolled:
                self._scrolled.add(url)
                await self.page.evaluate(SCROLL_JS)
                await self.wait_quiet()
            if url not in self._looked:
                self._looked.add(url)
                from .state import route_shape

                look = await self.page.evaluate(LOOK_JS)
                for k, n in look["modalities"].items():
                    if n:
                        self.modalities.setdefault(k, set()).add(route_shape(url))
                self.dev_markers.update(look["dev"])
                if getattr(self.cfg, "hover_rows", False) and look.get("row"):  # R6: hover-only row controls
                    await self.page.mouse.move(look["row"][0], look["row"][1])
                    await asyncio.sleep(0.15)
        except PWError:
            pass

    async def session_storage(self) -> dict:
        """C1: this tab's session storage ({origin, items}), saved with each step record."""
        try:
            return await self.page.evaluate(SESSION_STORAGE_JS)
        except PWError:
            return {}

    async def fresh_text_until(self, url: str, pred, deadline_s: float | None = None) -> str | None:
        """O3: like fresh_text, but re-reads the page every 0.5 s until `pred(text)` holds or the deadline
        passes (a fixed wait gives false alarms on slow apps and wastes time on fast ones). The time it
        took is kept in settle_times."""
        deadline_s = getattr(self.cfg, "poll_deadline_s", 8.0) if deadline_s is None else deadline_s
        page = await self.context.new_page()
        t0 = time.monotonic()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            text = ""
            while True:
                await asyncio.sleep(self.cfg.settle_ms / 1000 if not text else 0.5)
                text = await page.evaluate(TEXT_JS)
                if pred(text) or time.monotonic() - t0 >= deadline_s:
                    self.settle_times.append(round(time.monotonic() - t0, 2))
                    return text
        except PWError:
            return None
        finally:
            await page.close()

    def locator(self, eid: str):
        """The element with this observation id; ids '<frame>.<n>' live in a same-origin iframe (R6)."""
        sel = f'[data-wt-id="{eid}"]'
        if "." in str(eid):
            frame = str(eid).split(".", 1)[0]
            return self.page.frame_locator(f'iframe[data-wt-frame="{frame}"]').locator(sel)
        return self.page.locator(sel)

    def report(self) -> dict:
        """Reach and safety counters for the trace (X1, R6, R9, S1, O3)."""
        st = sorted(self.settle_times)
        h_all = sum(n for n, _ in self.handlers.values())
        h_hit = sum(h for _, h in self.handlers.values())
        cov = {"handler_elements": h_all, "handler_elements_clicked": h_hit} if self.handlers else {}
        return {**cov, **({"js_coverage": self.js_coverage} if self.js_coverage else {}),
                "dropped_elements": self.dropped, "dialogs": len(self.dialogs), "dismissed": self.dismissed[:20],
                "blocked_writes": self.blocked[:50], "settle_s_median": st[len(st) // 2] if st else None,
                "settle_over_3s": sum(1 for x in st if x > 3),
                "modalities": {k: len(v) for k, v in sorted(self.modalities.items())},
                "build_mode": "dev" if self.dev_markers else "prod", "dev_markers": sorted(self.dev_markers),
                "out_of_scope_blocked": self.out_of_scope_blocked, "mode_violations": self.mode_violations[:20],
                "pages_looked": len(self._looked),
                "controls_seen": sum(len(v) for v in self.seen.values()),
                "controls_activated": sum(len(self.activated.get(r, set()) & v) for r, v in self.seen.items())}

    async def storage_state(self) -> dict:
        return await self.context.storage_state()

    async def fresh_text(self, url: str) -> str | None:
        """Visible text of `url` opened in a new tab of this context (same session), for
        inferred-oracle checks: the worker's own page is left untouched. None if it fails."""
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                await page.wait_for_load_state("networkidle", timeout=2500)
            except PWError:
                pass
            await asyncio.sleep(self.cfg.settle_ms / 1000)
            return await page.evaluate(TEXT_JS)
        except PWError:
            return None
        finally:
            await page.close()

    # ---------- actions ----------
    async def goto(self, url_or_path: str) -> ActionResult:
        before = self.page.url
        url = url_or_path if "://" in url_or_path else self.cfg.app.base_url.rstrip("/") + "/" + url_or_path.lstrip("/")
        if not self.in_scope(url):
            return ActionResult(False, "out of scope", before, before, out_of_scope=True)
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except PWError as e:
            return ActionResult(False, _short(e), before, self.page.url)
        await self.settle()
        return await self._after(before)

    async def execute(self, do: str, eid: str | None = None, value: str | None = None) -> ActionResult:
        page = self.page
        before = page.url
        do = (do or "").lower().strip()
        try:
            if do in ("navigate", "goto"):
                return await self.goto(value or "/")
            if do == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=8000)
            elif do == "reload":
                await page.reload(wait_until="domcontentloaded", timeout=15000)
            else:
                if not eid:
                    return ActionResult(False, f"'{do}' needs an element id", before, before)
                loc = self.locator(eid)
                if await loc.count() == 0:
                    return ActionResult(False, f"no element [{eid}] on the current page", before, before)
                if do == "click":
                    try:
                        await loc.click()
                    except PWError:
                        # The click may have landed and navigated (element detached),
                        # or the element is covered by an overlay: check, then force.
                        await self.settle()
                        if page.url != before:
                            return await self._after(before)
                        if await loc.count() == 0:
                            return await self._after(before)
                        await loc.click(force=True)
                elif do in ("fill", "type"):
                    await loc.fill(str(value or ""))
                elif do == "clear":
                    await loc.fill("")
                elif do == "select":
                    try:
                        await loc.select_option(label=str(value))
                    except PWError:
                        await loc.select_option(value=str(value))
                elif do == "check":
                    await loc.check()
                elif do == "uncheck":
                    await loc.uncheck()
                elif do == "press":
                    await loc.press(str(value or "Enter"))
                elif do == "hover":
                    await loc.hover()
                else:
                    return ActionResult(False, f"unknown action '{do}'", before, before)
        except PWError as e:
            await self.settle()
            return ActionResult(False, _short(e), before, page.url)
        await self.settle()
        return await self._after(before)

    async def _after(self, before: str) -> ActionResult:
        now = self.page.url
        if not self.in_scope(now) or now.startswith("chrome-error://"):
            # Left the app (e.g. an external link): return to the last in-scope page.
            try:
                await self.page.goto(self.last_in_scope_url, wait_until="domcontentloaded", timeout=15000)
                await self.settle()
            except PWError:
                pass
            return ActionResult(True, "left scope; returned", before, now, out_of_scope=True)
        self.last_in_scope_url = now
        return ActionResult(True, "", before, now)

    # ---------- auth helper for non-LLM agents ----------
    async def login(self, account: Account) -> bool:
        recipe = self.cfg.app.login
        if not recipe:
            return False
        vals = {"email": account.email, "password": account.password, "username": account.username}
        for attempt in range(2):  # right after a reset the login page can load slowly (I40)
            await self.goto(recipe.path)
            try:
                for label, template in recipe.fields.items():
                    loc = self.page.get_by_placeholder(label).or_(self.page.get_by_label(label)).first
                    await loc.fill(template.format(**vals))
                await self.page.get_by_role("button", name=recipe.submit).first.click()
                break
            except PWError:
                if attempt:
                    raise
                await asyncio.sleep(5)
        await self.settle()
        self.drain_signals()
        return not self.page.url.rstrip("/").endswith(recipe.path.rstrip("/"))


def _short(e: Exception) -> str:
    return str(e).split("\n")[0][:200]
