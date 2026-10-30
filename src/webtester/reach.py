"""Reach helpers for v5 phase 2 (D60): what lets workers get to more states, with data, safely.

  R1  input profiles     a value for a field from its declared attributes, its label and the app's own
                         validation message (one retry of a rejected form)
  R7  discovery          routes from sitemap.xml, robots.txt, RSS/Atom links and same-origin GETs seen
  R8  destructive order  delete / close-account only on items the run created before a share of the budget,
                         logout only near the end
  X3  namespaces         generated values carry the worker and a run suffix, so workers do not collide
  X5  goal flows         per workflow primitive, the flows that arm its rules (shown after the app profile)
  R11 sequences          two- and three-step action sequences from the state graph as goal flows (D61)
  O7  feeds              feed items and the pages they link to (R02s, R20f in the runner's discovery, D61)

Pure functions where possible; the worker and the Sweeper call them.
"""

from __future__ import annotations

import html
import random
import re
import string
from urllib.parse import urljoin, urlsplit

from .lexicon import alternation

# ---------------------------------------------------------------------------- R8
DESTRUCTIVE = re.compile(r"\b(" + alternation("destructive") + r")\b", re.I)  # lexicon/<lang>.toml (O6 b)
LOGOUT = re.compile(r"\b(" + alternation("logout") + r")\b", re.I)


def destructive_kind(text: str) -> str:
    t = text or ""
    return "logout" if LOGOUT.search(t) else "destructive" if DESTRUCTIVE.search(t) else ""


def defer_reason(text: str, budget_share: float, own_page: bool, threshold: float) -> str:
    """Why a click is deferred now ('' = allowed). Destructive actions on items the run did not create wait
    until `threshold` of the budget is spent; logout waits until 0.9 (a lost session ends exploration)."""
    kind = destructive_kind(text)
    if not kind or threshold <= 0:
        return ""
    if kind == "logout" and budget_share < 0.9:
        return "logout deferred to the end of the budget (R8)"
    if kind == "destructive" and not own_page and budget_share < threshold:
        return "delete deferred: not an item this run created (R8)"
    return ""


# ---------------------------------------------------------------------------- R7
LINK_FEED = re.compile(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*href="([^"]+)"', re.I)
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
ALLOW = re.compile(r"^\s*(?:allow|disallow)\s*:\s*(/\S*)", re.I | re.M)
SITEMAP = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.I | re.M)
FEED_LINK = re.compile(r"<link>\s*([^<\s]+)\s*</link>|<link[^>]+href=\"([^\"]+)\"", re.I)


def parse_discovery(base: str, robots: str = "", sitemap: str = "", page_html: str = "", feed: str = "") -> dict:
    """Paths to seed the frontier with, by source (robots, sitemap, feed). Disallowed paths are kept: a
    tester may visit them (the app is ours), but wildcards and query patterns are dropped."""
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))

    def same(u: str) -> str | None:
        a = urljoin(base, u.strip())
        s = urlsplit(a)
        if f"{s.scheme}://{s.netloc}" != origin or "*" in a or "$" in a:
            return None
        return s.path + (f"?{s.query}" if s.query else "")

    out = {"robots": sorted({p for m in ALLOW.findall(robots or "") if (p := same(m))}),
           "sitemap": sorted({p for m in LOC.findall(sitemap or "") if (p := same(m))})[:200],
           "feed": sorted({p for a, b in FEED_LINK.findall(feed or "") if (p := same(a or b))})[:100],
           "sitemaps": [u for u in SITEMAP.findall(robots or "")],
           "feeds": [urljoin(base, h) for h in LINK_FEED.findall(page_html or "")][:3]}
    return out


_FEED_ITEM = re.compile(r"<(item|entry)\b.*?</\1>", re.S | re.I)
_FEED_TITLE = re.compile(r"<title[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def feed_items(feed: str) -> list[tuple[str, str]]:
    """(title, link) of each RSS item or Atom entry, newest first as the feed lists them."""
    out = []
    for m in _FEED_ITEM.finditer(feed or ""):
        t = _FEED_TITLE.search(m.group(0))
        lk = FEED_LINK.search(m.group(0))
        if t and lk:
            out.append((html.unescape(_TAGS.sub("", t.group(1))).strip(), (lk.group(1) or lk.group(2)).strip()))
    return out


def page_words(page_html: str) -> str:
    """Visible-ish text of an HTML page (tags dropped, entities decoded, spaces collapsed), lower case."""
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page_html or "")
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", body))).strip().lower()


def network_gets(net: list[dict]) -> list[str]:
    """Same-origin document GETs of the network timeline (pages the app itself loaded)."""
    return sorted({r["path"] for r in net if r.get("method") == "GET" and r.get("type") == "document"
                   and 200 <= r.get("status", 0) < 300})


# ---------------------------------------------------------------------------- X3, R1
def namespace(worker: int, run_suffix: str) -> str:
    return f"w{worker}{run_suffix}"


def run_suffix(seed: int, worker: int = 0) -> str:
    rng = random.Random(seed * 7919 + worker)
    return "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(4))


_HINT_MIN = re.compile(r"at least (\d+)", re.I)
_HINT_MAX = re.compile(r"(?:at most|no more than|maximum(?: of)?|up to) (\d+)", re.I)
_HINT_KIND = [("email", re.compile(r"e-?mail", re.I)), ("url", re.compile(r"\burl\b|website|link", re.I)),
              ("number", re.compile(r"number|numeric|digits?|integer", re.I)),
              ("date", re.compile(r"\bdate\b|dd/mm|mm/dd|yyyy", re.I)), ("phone", re.compile(r"phone|tel\b|mobile", re.I)),
              ("password", re.compile(r"password", re.I))]
_TAKEN = re.compile(r"already (been )?taken|already exists|must be unique|is taken|in use", re.I)


def field_kind(attrs: dict, label: str) -> str:
    t = (attrs.get("type") or "").lower()
    if t in ("email", "url", "number", "date", "datetime-local", "time", "tel", "password", "month", "week", "color"):
        return {"tel": "phone", "datetime-local": "date"}.get(t, t)
    for kind, rx in _HINT_KIND:
        if rx.search(label or ""):
            return kind
    return "text"


def profile_value(attrs: dict, label: str, base: str, tag: str, hint: str = "") -> str:
    """R1: a value the field should accept, from what the page declares about it (type, min/max/step,
    minlength/maxlength, pattern-like hints) and the app's own message. `tag` (namespace) keeps it unique."""
    kind = field_kind(attrs, label + " " + hint)
    lo = attrs.get("minlength") or (int(m.group(1)) if (m := _HINT_MIN.search(hint or "")) else None)
    hi = attrs.get("maxlength") or (int(m.group(1)) if (m := _HINT_MAX.search(hint or "")) else None)
    if kind == "email":
        return f"{tag}.{(base or 'user').split('@')[0][:12].lower().replace(' ', '')}@example.test"
    if kind == "url":
        return f"https://example.test/{tag}"
    if kind == "phone":
        return "+15555550123"
    if kind == "password":
        return f"Pw-{tag}-9x!Q"
    if kind == "date":
        return "2026-11-15" if (attrs.get("type") or "") != "time" else "10:30"
    if kind in ("number",):
        mn, mx, st = attrs.get("min"), attrs.get("max"), attrs.get("step")
        v = mn if mn is not None else 1
        if mx is not None and v > mx:
            v = mx
        return str(int(v) if (st in (None, "", "any") or float(st or 1).is_integer()) and float(v).is_integer() else v)
    v = (base or "Item").strip() or "Item"
    if _TAKEN.search(hint or "") or tag not in v:
        v = f"{v} {tag}"
    if lo and len(v) < int(lo):
        v = (v + " " + "abcdefghij" * 10)[:int(lo)]
    if hi and len(v) > int(hi):
        v = v[:int(hi)]
    return v


# ---------------------------------------------------------------------------- X5
GOALS = {
    "CRUD": "create two items of each kind with distinctive names, open each, edit one field, delete one",
    "COLL": "add an item to a collection (cart, favourites, follows), open the collection, remove it again",
    "LEDG": "move a small amount between two of your own holders (transfer, points, leave), then open both",
    "LIFE": "take one item through its states (submit, approve, cancel, close) and open it after each",
    "CAP": "take one unit of a limited resource (seat, stock, quota) and check the remaining count",
    "SCHED": "book or schedule something with a start and an end, then open the calendar or list view",
    "TREE": "create an item inside another (page in a book, card in a list), move it, open both parents",
    "QUERY": "search for an item you created, sort the list, use a filter, go to the next page",
    "AGG": "open a dashboard or summary and the list a number on it summarises",
    "ID": "change a profile setting, log out at the very end, check pages that need a login",
    "SHARE": "comment or share an item, then view it as it would appear to others",
    "FILE": "upload a small file if there is a file field, and use an export or print view",
    "RICH": "drag or reorder something, reload, and check it stayed",
    "REL": "follow, tag or assign one item to another, then open the other side",
    "CTX": "switch the active workspace, store or account, then check no data from the first one shows",
    "MEDIA": "play and pause a media item, and open the queue or playlist",
}


def goal_lines(prims: list[str], n: int = 4) -> list[str]:
    return [f"{p}: {GOALS[p]}" for p in prims if p in GOALS][:n]


def rank_primitives(prims: list[str], checks=None) -> list[str]:
    """R10 (D61): the profile's primitives, least exercised first: by how often the rules of each primitive's own
    pack (its rules minus the navigation pack every app gets) have run with their preconditions met, from the
    check-outcome log. Ties keep the profile's order. Without a log the order is unchanged."""
    if checks is None:
        return list(prims)
    from .checks import ARMED
    from .families import rule_packs

    base = set(rule_packs(prims=set())["rules"])
    summ = checks.summary()
    armed = {p: sum(n for r in set(rule_packs(prims={p})["rules"]) - base for o, n in summ.get(r, {}).items() if o in ARMED)
             for p in prims}
    return sorted(prims, key=lambda p: (armed[p], prims.index(p)))


# R11 (D61): bounded metamorphic sequences (length 2-3) for the families whose faults need an order of actions
SEQUENCES = {
    "DB9": "sort or filter a list that holds your own items, then delete or edit one of them from its row, then check "
           "that the item you chose is the one that changed",
    "HI3": "move one of your own items to another parent, then open the old parent and the new one",
    "DB12": "archive or trash one of your own items, then open the active list and search for it",
}


def sequence_goals(graph, n: int = 2) -> list[str]:
    """Sequences armed by what the state graph has seen: item pages (DB9, DB12) and pages reached from a parent
    page (HI3). The harness generates them; the LLM carries them out as goal flows."""
    if graph is None:
        return []
    routes = {p for p in getattr(graph, "pages", {})}
    items = [r for r in routes if "*" in r]
    nested = [r for r in items if r.count("*") >= 2 or r.count("/") >= 3]
    out = []
    if items:
        out += [f"DB9: {SEQUENCES['DB9']}", f"DB12: {SEQUENCES['DB12']}"]
    if nested:
        out.insert(1, f"HI3: {SEQUENCES['HI3']}")
    return out[:n]


PROFILE_PROMPT = """You are classifying a web application from the pages a tester has seen so far.
App types (choose one, or "other"): {types}.
Workflow primitives (choose all you saw evidence for): {prims}.
Pages seen (route: name or heading):
{pages}

Reply with ONE JSON object: {{"app_type": "<one app type>", "primitives": ["<primitive>", ...],
"evidence": {{"<primitive>": "<route that shows it>"}}}}"""


def parse_profile(data: dict, types: list[str], prims: list[str]) -> dict:
    t = str((data or {}).get("app_type") or "")
    app_type = next((x for x in types if x.lower() == t.lower()), "other")
    got = [str(p).upper().replace("P-", "") for p in (data or {}).get("primitives") or []]
    ev = (data or {}).get("evidence") or {}
    return {"app_type": app_type, "primitives": [p for p in prims if p in got],
            "evidence": {str(k).upper().replace("P-", ""): str(v)[:80] for k, v in ev.items()} if isinstance(ev, dict) else {}}


# ---------------------------------------------------------------------------- X4
ROLE_PROMPTS = {
    "explorer": "",
    "prober": ("\n\nROLE: you are the adversarial prober of the team. Prefer forms and inputs: boundary values "
               "(0, -1, very large, very long), wrong types, empty and whitespace-only fields, special characters, "
               "double submit, Back after submit, and opening an item's address after deleting it."),
    "switcher": ("\n\nROLE: you test as this account's role. Visit what this role can reach, note what it cannot, and "
                 "try the addresses of pages and actions other roles have (settings, admin, edit links)."),
}
DEFAULT_ROLES = ("explorer", "prober", "switcher", "explorer")
