"""Evidence layer v5 (D58): what the browser layer records beyond statuses, and the rules that read it.

Off unless the run config sets `capture_evidence = true` ([run] section), so runs and resweeps made
with it off are unchanged. With it on, BrowserSession keeps:
  * a network timeline: every same-origin xhr/fetch/document response (method, path, status, content
    type, time) with the parsed JSON body of xhr/fetch answers (capped) and the body a write sent;
  * transient messages: text that appeared in alert, status, live-region or toast-like elements, caught
    by a MutationObserver from page start, since toasts and flashes are gone before a step's audit.

Rules here are pure functions over those records (unit-tested without a browser):
  R57 payload (RT5 part): a 2xx JSON answer whose body is an error (GraphQL `errors`, `error`, `errors`).
  R51 message fidelity (FB2 part): a success message and an error message within one step.
"""

from __future__ import annotations

import re

from .state import route_shape

MAX_BODY_BYTES = 200_000  # larger JSON bodies are not kept
MAX_NET_RECORDS = 300  # timeline records kept per session
MAX_POST_CHARS = 2000

# Installed as an init script: runs before the page's own scripts, in every document.
MSG_JS = r"""
(() => {
  if (window.__wtMsgs) return;
  window.__wtMsgs = [];
  const SEL = '[role=alert],[role=status],[aria-live]:not([aria-live=off]),.toast,.alert,.flash,.notification,' +
              '.snackbar,.notice,.flash-message,.alert-message';
  const last = new WeakMap();
  const take = (el) => {
    if (!el || !el.closest) return;
    const box = el.closest(SEL);
    if (!box) return;
    const text = (box.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text || text.length > 300 || last.get(box) === text) return;
    last.set(box, text);
    const kind = box.getAttribute('role') || box.getAttribute('aria-live') || (box.getAttribute('class') || '').slice(0, 60);
    window.__wtMsgs.push({ t: Date.now(), text, kind });
    if (window.__wtMsgs.length > 50) window.__wtMsgs.shift();
  };
  new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'characterData') { take(m.target.parentElement); continue; }
      take(m.target.nodeType === 1 ? m.target : m.target.parentElement);
      for (const n of m.addedNodes) if (n.nodeType === 1) take(n);
    }
  }).observe(document, { childList: true, subtree: true, characterData: true });
})();
"""
DRAIN_MSGS_JS = "() => { const m = window.__wtMsgs || []; window.__wtMsgs = []; return m; }"


# ---------------------------------------------------------------------------- R57 payload
def _error_of(body) -> str:
    """The error a JSON body carries, or ''."""
    if not isinstance(body, dict):
        return ""
    errs = body.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0]
        return str(first.get("message", first) if isinstance(first, dict) else first)[:120]
    if isinstance(errs, dict) and errs:
        k = next(iter(errs))
        return f"{k}: {errs[k]}"[:120]
    err = body.get("error")
    if err and err is not True and not isinstance(err, (int, float)):
        return str(err.get("message", err) if isinstance(err, dict) else err)[:120]
    if err is True:
        return str(body.get("message") or "error: true")[:120]
    return ""


def rule_payload(net: list[dict]):
    """R57 (RT5): a 2xx answer whose JSON body is an error: the request failed while the status says
    it succeeded, so the page may show success or nothing. One violation per method and route shape."""
    from .consistency import Violation

    out, seen = [], set()
    for r in net:
        if not 200 <= r.get("status", 0) < 300 or "body" not in r:
            continue
        err = _error_of(r["body"])
        if not err:
            continue
        key = f"{r['method']} {route_shape(r['url'])}"
        if key in seen:
            continue
        seen.add(key)
        out.append(Violation("R57", key, f"{r['method']} {r['path']} answered HTTP {r['status']} with an error "
                             f"body: {err}", f"body: {str(r['body'])[:300]}"))
    return out


# ---------------------------------------------------------------------------- R51 messages
_OK = re.compile(r"\b(saved|created|updated|deleted|removed|added|published|success(?:ful(?:ly)?)?|"
                 r"changes? (?:were |have been )?saved|done)\b", re.I)
_BAD = re.compile(r"\b(error|errors|failed|failure|could ?n[o']t|cannot|unable|invalid|not allowed|denied|"
                  r"went wrong|problem)\b", re.I)
_NEG_OK = re.compile(r"\b(not|n't|never)\s+(?:been\s+)?(saved|created|updated|deleted|removed|added|published)\b", re.I)
MSG_WINDOW_MS = 3000


def kind_of(text: str) -> str:
    """'ok', 'bad', or '' for a message's text; a message with both kinds of words is ambiguous ('')."""
    bad = bool(_BAD.search(text)) or bool(_NEG_OK.search(text))
    ok = bool(_OK.search(text)) and not _NEG_OK.search(text)
    return "" if ok == bad else ("ok" if ok else "bad")


def rule_messages(msgs: list[dict]):
    """R51 (FB2): one step's messages include a success and an error that appeared within
    MSG_WINDOW_MS of each other: the app says both that the action worked and that it failed."""
    from .consistency import Violation

    tagged = [(m, kind_of(m.get("text", ""))) for m in msgs]
    oks = [m for m, k in tagged if k == "ok"]
    bads = [m for m, k in tagged if k == "bad"]
    for a in oks:
        for b in bads:
            if abs(a.get("t", 0) - b.get("t", 0)) <= MSG_WINDOW_MS:
                return [Violation("R51", f"{a['text'][:40]} | {b['text'][:40]}",
                                  f"success and error shown together: '{a['text'][:80]}' and '{b['text'][:80]}'",
                                  f"messages: {[m['text'][:80] for m in msgs][:6]}")]
    return []
