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
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Error as PWError, Page

from .config import REPO_ROOT, Account, RunConfig

FAULT_MARKER = "[wt-fault] "  # console line an injected fault logs when it first fires (exposure)
NET_TYPES = ("xhr", "fetch", "document")  # requests `settle` waits for
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
OBSERVE_JS = r"""
(maxEls) => {
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
  document.querySelectorAll('[data-wt-id]').forEach((e) => e.removeAttribute('data-wt-id'));
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const els = [];
  let next = 1;
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (els.length >= maxEls) break;
    const std = el.matches(SEL);
    if (!std && !byCursor(el)) continue;
    if (!visible(el)) continue;
    const id = String(next++);
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
      form: form ? Array.from(document.querySelectorAll('form')).indexOf(form) : -1,
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
    skeleton: document.body ? sig(document.body, 0) : '',
    text: clean(document.body ? document.body.innerText : '', 4000),
  };
}
"""


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

    # ---------- lifecycle ----------
    async def start(self, storage_state: dict | None = None) -> None:
        """`storage_state` (cookies + localStorage) restores a session: used by the evidence gate's replays."""
        self.context = await self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US",
                                                      storage_state=storage_state)
        self.context.set_default_timeout(self.cfg.action_timeout_ms)
        if self.cfg.app.fault_script and self.cfg.client_faults:
            await self.context.add_init_script(script=f"window.__WT_FAULTS__ = {json.dumps(list(self.cfg.client_faults))};")
            await self.context.add_init_script(path=str(REPO_ROOT / self.cfg.app.fault_script))
        await self.context.route("**/*", self._route)
        self.page = await self.context.new_page()
        self._wire(self.page)

    async def close(self) -> None:
        if self.context:
            await self.context.close()

    def in_scope(self, url: str) -> bool:
        u = urlsplit(url)
        if u.scheme in ("data", "blob", "about"):
            return True
        return f"{u.scheme}://{u.netloc}" in self.origins

    async def _route(self, route) -> None:
        if self.in_scope(route.request.url):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")

    def _wire(self, page: Page) -> None:
        page.on("pageerror", lambda exc: self._signals.append(
            Signal("page_error", str(exc).split("\n")[0][:300], page.url, {"stack": (getattr(exc, "stack", "") or "")[:1500]})))
        page.on("console", self._on_console)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)

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
        for attempt in range(3):
            try:
                raw = await self.page.evaluate(OBSERVE_JS, self.cfg.max_elements)
                break
            except PWError:
                if attempt == 2:
                    raise
                await self.settle()  # page navigated mid-evaluation
        blocked = tuple(t.lower() for t in self.cfg.app.blocked_text)
        els = [Element(**e) for e in raw["elements"]]
        if blocked:
            els = [e for e in els if not any(b in (e.text + " " + e.label).lower() for b in blocked)]
        return Observation(raw["url"], raw["title"], els, raw["skeleton"], raw["text"])

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
                loc = page.locator(f'[data-wt-id="{eid}"]')
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
