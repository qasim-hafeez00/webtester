"""Cross-view rules (v5 waves W1-W3, D60): one item, one flow or one control seen across pages and steps.

Passive: they read the page facts (consistency.audit), this step's page read (norms.NORMS_JS), the run memory
(intents, writes) and what this module remembers between steps. No extra requests.

  R20  cross-view registry (DB5, DB6)  an item's name, price or status in a list differs from its own page; after an
                                        edit a list still shows the old name. R20d: declared data (JSON-LD offers,
                                        product meta) differs from the visible price or name
  R21a edit prefill (FM4)              an item's edit form does not hold the name its page shows
  R40  hierarchy (HI1)                 a breadcrumb parent does not list the child
  R47  badges (MU2)                    a navigation badge counts more items than the page it opens lists
  R31  referenced control (PR7)        the page tells the user to use a control it lacks (seen elsewhere in the app)
  R73  history ledger (HS1)            the activity page shows an older write of this run but not a newer one
  R68  inverse relations (RL1, RL2)    a follow does not move the follower count by one; following oneself is accepted
  R22  collection ledger (CT2, CT4)    an accepted 'add to X' leaves X's badge unchanged or the item off X's page
  R34  lifecycle (SM1, SM3)            after 'Approve' the item still shows its old status; status tab counts do not
                                        add up to 'All'
  R35  capacity (CP1, CP2)             availability not lower after an accepted booking; more than available accepted
  R32  conservation (LG1)              after an accepted transfer, the two balances did not move by the amount
  R70  funnel ledger (WF5)             a value typed in a flow is missing from its review or confirmation page
  R12b echo fidelity (PR2)             a typed value with markup or accents is shown escaped, folded or mangled
  R56  route parity (DB10, T3)         two create routes for one kind of item keep different fields
  R30  session kept (SA2)              a login page appears with no logout in the trail
  R27  input kept (FM6)                after a rejected submit, a field the agent filled is empty
  R29  dead control (NV7)              an action button did nothing: no request, no address change, no page change
  R38  facets and ranges (SF5, SF7)    a facet's count differs from the results it opens; a range filter returns
                                        items outside the range
  R44  preferences (ST1)               a saved page size is not kept
  R55  bulk ledger (BK1, BK2)          a bulk action changed other rows than the selected ones, or its message
                                        counts another number
  R58  clone (DB13)                    a copy has fewer children than its original
  R69  cart algebra (PX1, PX2)         quantity 0 keeps the line; removing a coupon does not restore the total
  R50  false failure (FB1)             the app said a write failed, yet its effect shows (set in consistency.py)
  D61, the extensions family rows name, each under its own id:
  R20t times across views (TM3, TM4)   a list's date or time for an item is shifted on its own page (whole hours, a day)
  R20u identifiers (UQ1)               two items show one 'Order #1234'; one address shows two items with no write
  R21s choice kept (FM11)              the edit form shows another option than the one saved
  R09d collateral delete (DB4)         a single delete also removed other rows of the list
  R09r row key (DB9)                   the row that disappeared is not the row whose control was clicked
  R49a archive (DB12)                  an archived item still in an active list; a restore that lost its children
  R22g guest merge (CT5)               items added as a guest lost or doubled after logging in
  R22v variant kept (PX4)              the size or colour chosen is not on the collection line
  R34c closed state (SM3)              a write accepted on an item its own page calls closed or locked
  R36b double booking (TM2)            one slot of one resource booked twice, both accepted
  R67f listed but forbidden (CX3)      an item listed to this account answers 'forbidden' when opened
  R68t tag pages (RL1)                 an item saved with a tag is missing from that tag's page
  R48u undo / redo (RC3)               redo does not return the list to its state before the undo
  R29k advertised keys (RC4)           a key the page advertises (<kbd>) did nothing
  R51c message fidelity (FB2)          'Deleted 3' after one single delete; a message naming another item
  R47r read state (MU2, T3)            an opened notification still counted unread on the next visit
  extensions of built ids: R20 currency, R20d page title (O7), R12b mojibake (PR2), R12c cut, emoji, whitespace
  and leading zeros (FM8, UQ3), R30 a 'Log in' header with the account's name shown (SA2), R31 an empty state
  asking for a control the page lacks (PR7), R34 one item under two status tabs (SM4), R38 date ranges (SF7), R40
  moves recorded for the old-parent probe (HI3), R61 a chosen suggestion opening another item (SF9), R69 path
  independence, quantity kept, minimum and expired coupons, a coupon applied twice (PX1, PX2), R74 shuffle
  changing the set (MD2)

Guards: items written by any worker since the earlier view are skipped (renames and edits explain change);
activity feeds and person pages are left out of R20; only complete lists (no pager, at most 50 items) are
compared for membership; numbers are compared after the page's own rounding; every rule is T2 (R56 T3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl, urlsplit

from .lexicon import alternation, lexicon, words
from .memory import EVENT_FEED, entity_key, item_key, norm
from .norms import money_values, parse_number
from .state import route_shape

TIERS = {r: "T2" for r in ("R20", "R20d", "R21a", "R40", "R47", "R31", "R73", "R68", "R22", "R34", "R35", "R32", "R70",
                           "R12b", "R30", "R27", "R29", "R38", "R44", "R55", "R58", "R69", "R50")}
TIERS["R56"] = "T3"
TIERS["R38c"] = "T3"  # SF3: filter composition (low: relevance search may widen)
TIERS.update({r: "T2" for r in ("R20t", "R20u", "R21s", "R09d", "R09r", "R49a", "R22g", "R22v", "R34c", "R36b", "R67f",
                                "R68t", "R48u", "R29k", "R51c")})
TIERS["R47r"] = "T3"  # MU2: many apps mark read only on an explicit action
RULES = tuple(TIERS)

STATUS_WORDS = tuple(words("status"))  # lexicon/<lang>.toml (O6 b)
_STATUS_RX = re.compile(r"\b(" + "|".join(re.escape(w) for w in STATUS_WORDS) + r")\b", re.I)
LIFECYCLE = dict(lexicon().get("lifecycle", {}))
_LIFE_RX = re.compile(r"^(" + "|".join(sorted(LIFECYCLE, key=len, reverse=True)) + r")\b", re.I)
COLLECTION = re.compile(r"\b(" + alternation("collection") + r")\b", re.I)
_BYLINE = re.compile(r"\S{2,40}?\s*((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|"
                     r"\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago|\d{4}-\d{2}-\d{2})", re.I)
# D62 (I83): links to an action page (a create form, settings) are menu entries, not items ('Actions' -> /create-book)
_ACTION_PATH = re.compile(r"(^|[/_-])(create|new|add|edit|login|logout|register|signup|settings)([/_-]|$)", re.I)
_PERSON = re.compile(r"/(user|users|profile|profiles|u|member|members|people|author|authors|account|accounts)/[^/?#]+/?$", re.I)
_AVAIL = re.compile(r"\b(\d[\d,]*)\s+(left|available|remaining|seats?( left| available)?|spots?( left)?|in stock|places? left)\b",
                    re.I)
_QTY = re.compile(r"qty|quantity|seats?|tickets?|guests?|people|units?|amount of", re.I)
_REVIEW = re.compile(r"\b(confirm(ation|ed)?|review (your|order)|order (summary|number|#|placed)|summary|thank you|"
                     r"booking (confirmed|reference)|receipt)\b", re.I)
_REFER = re.compile(r"(?:click|press|tap|use|select|choose)\s+(?:the\s+)?[\"'“]([A-Z][\w &'-]{1,30})[\"'”]"
                    r"(?:\s+(?:button|link|tab|option))?", re.I)
_ACTION_VERB = re.compile(r"^(save|add|apply|remove|update|submit|delete|create|send|confirm|continue|next|publish|post|"
                          r"upload|import|export|copy|duplicate|approve|reject)\b", re.I)
_BULK = re.compile(r"\b(selected|bulk|all checked)\b|^(delete|archive|move|mark)( as)? (selected|checked)", re.I)
_PAGESIZE = re.compile(r"per page|page size|items per|show(ing)? \d|results per", re.I)
_RANGE_KEYS = {"min_price": ("price", "min"), "max_price": ("price", "max"), "price_min": ("price", "min"),
               "price_max": ("price", "max"), "minprice": ("price", "min"), "maxprice": ("price", "max"),
               "price_from": ("price", "min"), "price_to": ("price", "max")}
_ESCAPED = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("'", "&#39;"), ('"', "&quot;"), ("'", "&#x27;")]
# R55: rows of the list before a bulk action (selected = checked row checkboxes)
BULK_JS = r"""() => {
  const rows = [...document.querySelectorAll('tr, li, [role=row], .row, .card')].filter(r => r.querySelector('input[type=checkbox]'));
  const name = r => (r.innerText || '').trim().split('\n')[0].slice(0, 80);
  return {selected: rows.filter(r => r.querySelector('input[type=checkbox]').checked).map(name).filter(Boolean),
          others: rows.filter(r => !r.querySelector('input[type=checkbox]').checked).map(name).filter(Boolean)};
}"""
# R09r (D61): the list row that holds a control, read before the click (its link text, else its first line)
ROW_JS = r"""(eid) => {
  const el = document.querySelector(`[data-wt-id="${eid}"]`);
  const row = el && el.closest('tr, li, [role=row], .card, article, .list-item, [class*=row]');
  if (!row || row === document.body) return '';
  const a = row.querySelector('a[href]');
  return ((a && a.innerText) || row.innerText || '').trim().split('\n')[0].slice(0, 80);
}"""
_FOLD = str.maketrans("áàâäãåéèêëíìîïóòôöõúùûüñçÁÀÂÄÃÅÉÈÊËÍÌÎÏÓÒÔÖÕÚÙÛÜÑÇ", "aaaaaaeeeeiiiiooooouuuuncAAAAAAEEEEIIIIOOOOOUUUUNC")
# D61
_GONE = re.compile(r"not found|\b404\b|doesn'?t exist|does not exist|no such|page not found|has been deleted", re.I)
_CUR = re.compile(r"[$€£¥₹]|\b(?:USD|EUR|GBP|PKR|JPY|INR)\b")
_TIME = re.compile(r"^\D{0,6}(\d{1,2}):(\d{2})\s*(am|pm)?", re.I)
_IDENT = re.compile(r"\b(order|invoice|ticket|booking|reservation|case|receipt|ref(?:erence)?)\s*(?:#|no\.?|number|id)\s*:?\s*"
                    r"([A-Z]{0,4}-?\d{3,})\b", re.I)
_ARCHIVE = re.compile(r"^(archive|move to (the )?(archive|trash|bin)|trash)\b", re.I)
_RESTORE = re.compile(r"^(restore|unarchive|un-archive|recover|untrash)\b", re.I)
_ACTIVE = re.compile(r"archiv|trash|\bbin\b|deleted|recycle", re.I)
_LOGIN_LINK = re.compile(r"^(log ?in|sign ?in)$", re.I)
_LOGOUT_LINK = re.compile(r"^(log ?out|sign ?out)$", re.I)
_VARIANT = re.compile(r"size|colou?r|variant|option|style|plan|edition|flavou?r|model", re.I)
_CLOSED = {"closed", "cancelled", "paid", "completed", "archived", "expired", "rejected", "delivered", "resolved", "shipped"}
_LOCKED = re.compile(r"\b(can ?not|can't|no longer)\s+be\s+(edited|changed|modified|updated|cancell?ed|paid|deleted)\b|"
                     r"\bis\s+(locked|read-only|closed for (edits|changes))\b", re.I)
_SLOT = re.compile(r"date|time|start|end|from|until|slot|day|check-?in|check-?out|when", re.I)
_BOOKING = re.compile(r"book|reserv|appointment|leave|room|slot|schedul|rent|hire|seat", re.I)
_CAPACITY = re.compile(r"\b(seats?|spots?|places?|capacity|tickets?|remaining|left|available)\b", re.I)
_DATE_KEYS = {"from": "min", "to": "max", "start": "min", "end": "max", "date_from": "min", "date_to": "max",
              "start_date": "min", "end_date": "max", "after": "min", "before": "max", "since": "min", "until": "max",
              "from_date": "min", "to_date": "max"}
_EMPTY_ASK = re.compile(r"\bno (\w+)(?: \w+)? (?:yet|found|here)\b.{0,60}?\b(create|add|start|make) (one|your first|a new|some)\b",
                        re.I)
_MAKER = re.compile(r"^(\+ ?)?(create|add|new|start|make)\b", re.I)
_FORBIDDEN = re.compile(r"\b(forbidden|not authori[sz]ed|access denied|permission denied|you (do not|don't) have "
                        r"(permission|access)|403)\b", re.I)
_TAGF = re.compile(r"\b(tags?|labels?|categor(y|ies)|topics?|assign(ee|ed)?)\b", re.I)
_CART = re.compile(r"cart|basket|\bbag\b|checkout", re.I)
_MINIMUM = re.compile(r"minimum (?:order|spend|purchase)(?: amount| value)?(?: of)?\s*((?:[$€£])\s?\d[\d.,]*)", re.I)
_NOTIF = re.compile(r"notif|inbox|alerts|messages", re.I)
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")
_MSG_N = re.compile(r"\b(\d+)\s+(?:items?|records?|rows?|entries|files?|[a-z]+s)\s+(?:were\s+|have been\s+)?"
                    r"(deleted|removed|updated|archived|moved|saved|created)\b", re.I)
_MSG_NAME = re.compile(r"[\"'“‘]([^\"'”’]{3,60})[\"'”’]\s+(?:was|has been|is)\s+(deleted|removed|updated|saved|created|archived)",
                       re.I)


def datetimes(text: str) -> list[tuple]:
    """(date, minutes after midnight or None) for each date in `text`, with a time right after it."""
    from .norms import _DATE_RX, _MONTHS

    out = []
    for rx, kind in _DATE_RX:
        for m in rx.finditer(text or ""):
            try:
                if kind == "ymd":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "mdy" and m.group(1).lower() in _MONTHS:
                    d = date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
                elif kind == "dmy" and m.group(2).lower() in _MONTHS:
                    d = date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
                else:
                    continue
            except ValueError:
                continue
            t = _TIME.match(text[m.end():m.end() + 14])
            mins = None
            if t:
                h = int(t.group(1)) % 12 + (12 if (t.group(3) or "").lower() == "pm" else 0) if t.group(3) else int(t.group(1))
                mins = h * 60 + int(t.group(2))
            out.append((m.start(), d, mins))
    return [(d, mi) for _, d, mi in sorted(out)]


def _label_of(d: dict) -> str:
    return norm(re.sub(r'^\[\d+\]\s*\w+(\[\w+\])?\s*', "", d.get("el") or "").strip(' "'))


def _nav_texts(raw: dict) -> list[str]:
    return [(n.get("text") or "").strip() for n in raw.get("nav") or []]


def _names(facts) -> list[str]:
    m = facts.main_list() if facts is not None else None
    return [i["name"] for i in m["items"] if i.get("name")] if m else []


@dataclass
class CrossState:
    """Shared by all workers of a run (SweepState.cross)."""

    views: dict = field(default_factory=dict)  # entity key -> {route: (name, money, status, step)}
    parents: dict = field(default_factory=dict)  # child key -> (parent key, child name, step)
    badges: dict = field(default_factory=dict)  # href path -> (n, step, worker)
    controls: set = field(default_factory=set)  # control labels seen anywhere in the app
    collections: dict = field(default_factory=dict)  # href path -> collection word
    page_status: dict = field(default_factory=dict)  # url -> status words last seen there
    rel_counts: dict = field(default_factory=dict)  # entity key -> (followers n, step)
    avail: dict = field(default_factory=dict)  # entity key -> (n, step)
    balances: dict = field(default_factory=dict)  # account name -> (value, step)
    flows: dict = field(default_factory=dict)  # worker -> {"root", "steps", "values"}
    page_size: dict = field(default_factory=dict)  # worker -> (n, step)
    creates: dict = field(default_factory=dict)  # form route -> (landing kind, labels shown, labels not shown)
    coupon: dict = field(default_factory=dict)  # worker -> total before a coupon
    reported: set = field(default_factory=set)
    # D61
    extra: dict = field(default_factory=dict)  # entity key -> {route: (currency, datetimes, step)}
    idents: dict = field(default_factory=dict)  # shown identifier ('order #1234') -> (entity key, step)
    addr: dict = field(default_factory=dict)  # item address -> (h1, step)
    choices: dict = field(default_factory=dict)  # (form route, field label) -> (value, step, entity key)
    archived: dict = field(default_factory=dict)  # item name -> (entity key, step, children shown)
    restored: dict = field(default_factory=dict)  # item name -> step
    guest: dict = field(default_factory=dict)  # worker -> [names added while logged out]
    guest_login: dict = field(default_factory=dict)  # worker -> step of the login after guest adds
    variants: dict = field(default_factory=dict)  # (worker, item name) -> [chosen option labels]
    tabs: dict = field(default_factory=dict)  # (list path, status word) -> (item keys, step)
    bookings: dict = field(default_factory=dict)  # (form route, item key, slot) -> event idx
    seen_events: int = 0
    parent_href: dict = field(default_factory=dict)  # child key -> parent href
    moved: list = field(default_factory=list)  # (child key, old parent href, child name, step) for probes5 R40m
    tagged: dict = field(default_factory=dict)  # tag -> [(item name, step, item key)]
    carts: dict = field(default_factory=dict)  # cart lines signature -> (total, step)
    codes: dict = field(default_factory=dict)  # (worker, code) -> times applied with the total going down
    unread: dict = field(default_factory=dict)  # notifications url -> (unread count, step, opened since)
    hist: dict = field(default_factory=dict)  # worker -> [(step, main list names, clicked label)]


def _who_when(name: str) -> bool:
    """A name made only of one name token and a date or time (a card's byline, 'worker01October 29, 2026')."""
    return bool(_BYLINE.fullmatch(name.strip()))


def _written_since(mem, key: str, names: list[str], step: int) -> bool:
    from .consistency import same_name

    for e in mem.events:
        if e.step < step or e.verb not in ("create", "edit", "delete", "add", "favourite", "unfavourite"):
            continue
        if (key and e.target == key) or any(n and e.obj and same_name(e.obj, n) for n in names):
            return True
        if e.verb == "edit" and any(n and any(n.lower() in str(v).lower() for v in e.fields.values()) for n in names):
            return True
    return False


def _status_of(text: str) -> str:
    m = _STATUS_RX.search(text or "")
    return m.group(1).lower().replace("canceled", "cancelled") if m else ""


def _page_money(facts) -> float | None:
    """The price nearest the heading: the first amount within 400 characters after it."""
    t = facts.text or ""
    i = t.find(facts.h1) if facts.h1 else -1
    if i < 0:
        return None
    vals = money_values(t[i:i + 400])
    return vals[0] if vals else None


def _complete(L: dict, raw: dict | None) -> bool:
    return not (raw or {}).get("pager") and len(L["items"]) <= 50 and not any(
        re.search(r"view all|see all|load more|show more", i.get("name") or "", re.I) for i in L["items"])


def _path(u: str) -> str:
    s = urlsplit(u)
    return s.path.rstrip("/") or "/"


class CrossView:
    def __init__(self, st: CrossState):
        self.st = st

    def check(self, sw, facts, raw: dict | None, obs, done: list[dict], ev, step: int) -> list:
        """All passive cross-view rules for this step; `sw` is the worker's Sweeper (memory, check log)."""
        from .consistency import Violation

        raw = raw or {}
        out: list[Violation] = []
        for name in ("_registry", "_prefill", "_hierarchy", "_badges", "_referenced", "_history", "_relations",
                     "_collections", "_lifecycle", "_capacity", "_conservation", "_funnel", "_echo", "_parity",
                     "_session", "_input_kept", "_dead", "_facets", "_prefs", "_bulk", "_clone", "_cart", "_declared",
                     "_times", "_idents", "_choice", "_collateral", "_archive", "_guest", "_closed", "_status_tabs",
                     "_booking", "_dates", "_forbidden", "_tag_pages", "_undo", "_keys", "_unread", "_shuffle", "_header",
                     "_empty_state", "_suggestion", "_cart_algebra", "_fidelity"):
            try:
                out += getattr(self, name)(sw, facts, raw, obs, done, ev, step)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:  # a rule must never stop a run
                sw._ck(name.strip("_"), "inconclusive", f"error:{type(e).__name__}")
        for e in obs.elements:
            lab = (e.text or e.label or "").strip()
            if 2 <= len(lab) <= 30 and e.tag in ("button", "a", "input"):
                self.st.controls.add(norm(lab))
        return out

    # ---------------------------------------------------------------- R20, R20d
    def _registry(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, same_name

        st, mem, out = self.st, sw.mem, []
        route = route_shape(facts.url)
        for L in facts.content_lists():
            if EVENT_FEED.search(L.get("heading") or "") or re.search(r"recent|activity|history", L.get("heading") or "", re.I):
                continue
            for i in L["items"]:
                if not i.get("abs") or not i.get("name") or _PERSON.search(entity_key(i["abs"])) or \
                        _ACTION_PATH.search(urlsplit(i["abs"]).path):
                    continue
                vals = money_values(i.get("text", ""))
                st.views.setdefault(entity_key(i["abs"]), {})[route] = (
                    i["name"], vals[0] if len(vals) == 1 else None, _status_of(i.get("text", "")), step)
                c = _CUR.search(i.get("text", ""))
                st.extra.setdefault(entity_key(i["abs"]), {})[route] = (c.group(0) if c and len(vals) == 1 else None,
                                                                        datetimes(i.get("text", "")), step)
        # DB6: a list still showing the name an edit replaced (the old value is in the field's description)
        from .consistency import _PRIOR

        for e in mem.events:
            if e.verb != "edit" or e.status != "verified" or not e.target or e.step >= step - 1 or not e.obj:
                continue
            old = next((m.group(1) for k in e.fields for m in [_PRIOR.search(k)] if m), "")
            if not old or same_name(old, e.obj):
                continue
            for r, (name, _, _, s_step) in st.views.get(e.target, {}).items():
                if s_step > e.step + 1 and same_name(name, old) and not same_name(name, e.obj)                         and (e.idx, r) not in st.reported:
                    st.reported.add((e.idx, r))
                    out.append(Violation("R20", f"stale|{e.target}", f"{r} still lists {name!r} after it was renamed "
                                         f"to {e.obj!r} (step {e.step})"))
        key = entity_key(facts.url)
        if "*" not in route or not facts.h1 or _PERSON.search(key) or _GONE.search(facts.h1 + " " + (facts.title or "")):
            sw._ck("R20", "unarmed", "not-an-item-page")
            return out
        recs = {r: v for r, v in st.views.get(key, {}).items() if r != route}
        if not recs:
            sw._ck("R20", "unarmed", "one-view")
            return out
        sw._arm("R20")
        money, status = _page_money(facts), (raw.get("status") or [""])[0]
        for r, (name, m, s, s_step) in recs.items():
            if _written_since(mem, key, [name, facts.h1], s_step):
                sw._ck("R20", "suppressed", "written-since")
                continue
            if not same_name(name, facts.h1) and not norm(facts.h1).startswith(norm(name).rstrip(". …")[:20]) and \
                    not norm(name).startswith(norm(facts.h1)[:20]):
                out.append(Violation("R20", f"name|{key}", f"{r} lists this item as {name!r}, its own page is titled "
                                     f"{facts.h1!r}"))
            if m is not None and money is not None and abs(m - money) > max(0.011, 0.01 * max(m, money)):
                out.append(Violation("R20", f"price|{key}", f"{r} shows {m:.2f} for {name!r}, its own page shows {money:.2f}"))
            if s and status and s != status:
                out.append(Violation("R20", f"status|{key}", f"{r} shows {name!r} as {s!r}, its own page as {status!r}"))
            cur_l = (st.extra.get(key, {}).get(r) or (None,))[0]
            here_cur = _CUR.search((facts.text or "")[(facts.text or "").find(facts.h1):][:400] if facts.h1 else "")
            if cur_l and here_cur and m is not None and money is not None and cur_l != here_cur.group(0):
                out.append(Violation("R20", f"currency|{key}", f"{r} shows {name!r} in {cur_l}, its own page in "
                                     f"{here_cur.group(0)}"))
        # O7: a page title naming another known item (a single-page app that did not update its title)
        title = (facts.title or "").strip()
        if title and not same_name(title, facts.h1) and norm(facts.h1) not in norm(title):
            for k2, views in st.views.items():
                if k2 == key:
                    continue
                other = next((v[0] for v in views.values() if len(v[0]) >= 6), "")
                if other and (same_name(other, title) or norm(other) in norm(title)) and not same_name(other, facts.h1):
                    out.append(Violation("R20d", "title", f"the page is titled {title!r}, the name of another item, but "
                                         f"shows {facts.h1!r}"))
                    break
        return out

    def _declared(self, sw, facts, raw, obs, done, ev, step):
        """R20d (O7): JSON-LD offers or product meta against the visible price and name."""
        from .consistency import Violation, same_name

        out, decl = [], []
        for d in raw.get("jsonld") or ():
            for x in (d if isinstance(d, list) else d.get("@graph", [d]) if isinstance(d, dict) else []):
                if isinstance(x, dict) and str(x.get("@type", "")).lower() in ("product", "offer", "event", "book"):
                    offers = x.get("offers") or {}
                    offers = offers[0] if isinstance(offers, list) and offers else offers
                    decl.append((x.get("name"), parse_number(str(offers.get("price", ""))) if isinstance(offers, dict) else None))
        og = raw.get("og") or {}
        if og.get("product:price:amount"):
            decl.append((og.get("og:title"), parse_number(og["product:price:amount"])))
        if not decl:
            sw._ck("R20d", "unarmed", "no-declared-data")
            return out
        sw._arm("R20d")
        money = _page_money(facts)
        for name, price in decl:
            if price is not None and money is not None and abs(price - money) > max(0.011, 0.01 * max(price, money)):
                out.append(Violation("R20d", "price", f"the page declares the price {price:.2f} (structured data) but "
                                     f"shows {money:.2f}"))
            if name and facts.h1 and not same_name(str(name), facts.h1) and len(str(name)) > 3:
                out.append(Violation("R20d", "name", f"the page declares the name {str(name)[:60]!r} but its heading is "
                                     f"{facts.h1!r}"))
        return out

    # ---------------------------------------------------------------- R21a
    def _prefill(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import TITLE_FIELD, Violation, same_name

        path = urlsplit(facts.url).path
        m = re.match(r"(.+?)/(edit|update|settings)/?$", path)
        if not m or not raw.get("fields"):
            return []
        key = entity_key(m.group(1))
        names = list(sw.mem.entities.get(key).names) if key in sw.mem.entities else []
        title = next((f for f in raw["fields"] if TITLE_FIELD.search(f["label"] + " " + f["name"]) and f["type"] in
                      ("text", "input", "textarea")), None)
        if not names or title is None:
            sw._ck("R21a", "unarmed", "no-known-name" if not names else "no-name-field")
            return []
        sw._arm("R21a")
        if _written_since(sw.mem, key, names, step - 1) or any(d["do"] in ("fill", "clear") for d in done):
            return []
        if not title["value"].strip() or not any(same_name(n, title["value"]) for n in names):
            return [Violation("R21a", f"prefill|{route_shape(facts.url)}", f"the edit form of {names[-1]!r} holds "
                              f"{title['value']!r} in {title['label'] or 'its name field'!r}")]
        return []

    # ---------------------------------------------------------------- R40
    def _hierarchy(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, item_matches, shown

        st, out = self.st, []
        bc = [b for b in raw.get("breadcrumbs") or [] if b.get("href")]
        here = entity_key(facts.url)
        if bc and facts.h1 and "*" in route_shape(facts.url):
            links = [b for b in bc if entity_key(b["href"]) != here]
            if links:
                old = st.parents.get(here)
                new = entity_key(links[-1]["href"])
                if old and old[0] != new and st.parent_href.get(here) and \
                        any(e.written and e.step > old[2] for e in sw.mem.events):
                    st.moved.append((here, st.parent_href[here], facts.h1, step))  # HI3: probes5 checks the old parent
                st.parents[here] = (new, facts.h1, step)
                st.parent_href[here] = links[-1]["href"]
        kids = [(c, n, s) for c, (p, n, s) in st.parents.items() if p == here and c != here]
        if not kids:
            sw._ck("R40", "unarmed", "no-known-children")
            return out
        lists = [L for L in facts.content_lists() if _complete(L, raw)]
        if not lists:
            sw._ck("R40", "unarmed", "no-complete-list")
            return out
        sw._arm("R40")
        for c, n, s in kids:
            if _written_since(sw.mem, c, [n], s) or (c, here) in st.reported:
                continue
            if not any(item_matches(i, n, c) for L in lists for i in L["items"]) and not shown(n, facts.text):
                st.reported.add((c, here))
                out.append(Violation("R40", f"child|{c}", f"the breadcrumb of {n!r} names this page as its parent, but "
                                     "this page does not list it"))
        return out

    # ---------------------------------------------------------------- R47
    def _badges(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        st, out = self.st, []
        for n in raw.get("nav") or ():
            if n.get("badge") is not None and 0 <= n["badge"] <= 999:
                st.badges[_path(n["href"])] = (int(n["badge"]), step, sw.worker)
        b = st.badges.get(_path(facts.url))
        m = facts.main_list()
        if not b or b[2] != sw.worker or step - b[1] > 3 or not m:
            sw._ck("R47", "unarmed", "no-badge-for-page")
            return out
        sw._arm("R47")
        if _complete(m, raw) and b[0] > len(m["items"]) and not facts.showing:
            out.append(Violation("R47", f"badge|{_path(facts.url)}", f"the navigation badge says {b[0]}, but the page it "
                                 f"opens lists {len(m['items'])} items"))
        return out

    # ---------------------------------------------------------------- R31
    def _referenced(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        here = {norm(x) for x in raw.get("controls") or []} | {norm(n["text"]) for n in raw.get("nav") or []}
        out = []
        for m in _REFER.finditer(facts.plain or ""):
            name = norm(m.group(1))
            if name in self.st.controls and name not in here and name not in norm(" ".join(raw.get("controls") or [])):
                out.append(Violation("R31", f"control|{name}", f"the page refers to {m.group(1)!r}, but has no such control "
                                     "(the app shows it elsewhere)", m.group(0)))
        if not out:
            sw._ck("R31", "unarmed" if not _REFER.search(facts.plain or "") else "exercised", "no-reference")
        return out[:1]

    # ---------------------------------------------------------------- R73
    def _history(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, shown

        feed = re.search(r"/(audit|activity|activities|history|logs?|timeline|events)\b", urlsplit(facts.url).path, re.I) or \
            any(EVENT_FEED.search(L.get("heading") or "") for L in facts.content_lists())
        if not feed:
            return []
        mine = [e for e in sw.mem.events if e.worker == sw.worker and e.verb in ("create", "edit", "delete") and e.written
                and e.status == "verified" and len(e.obj or "") >= 4 and e.step < step]
        verbs = {"create": r"creat|add", "edit": r"updat|edit|chang|renam", "delete": r"delet|remov"}
        listed = [e for e in mine if shown(e.obj, facts.text)]
        if not listed:
            sw._ck("R73", "unarmed", "no-own-entry-listed")
            return []
        sw._arm("R73")
        oldest = min(e.step for e in listed)
        out = []
        for e in mine:
            if e.step > oldest and not shown(e.obj, facts.text) and re.search(verbs[e.verb], facts.text, re.I) \
                    and (e.idx, "R73") not in self.st.reported:
                self.st.reported.add((e.idx, "R73"))
                out.append(Violation("R73", f"missing|{e.verb}|{e.obj[:40]}", f"the activity page lists this account's "
                                     f"earlier writes but not {e.verb} {e.obj!r} (step {e.step})"))
        return out[:2]

    # ---------------------------------------------------------------- R68
    def _relations(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        out, key = [], entity_key(facts.url)
        n = next((c["n"] for c in facts.counts if re.match(r"followers?|subscribers?|members?|watchers?", c["unit"], re.I)), None)
        prev = self.st.rel_counts.get(key)
        if n is not None:
            self.st.rel_counts[key] = (n, step)
        if ev is not None and ev.verb in ("follow", "unfollow") and ev.written:
            acct = sw.account.username.lower() if sw.account else ""
            if acct and re.search(r"/" + re.escape(acct) + r"/?$", urlsplit(obs.url).path, re.I):
                out.append(Violation("R68", "self", f"{ev.verb} on this account's own page was accepted"))
            if prev is not None and n is not None and prev[1] < step:
                want = 1 if ev.verb == "follow" else -1
                sw._arm("R68")
                if n - prev[0] != want:
                    out.append(Violation("R68", f"count|{key}", f"{ev.verb} was accepted, but the count went "
                                         f"{prev[0]} -> {n} (expected {want:+d})"))
        return out

    # ---------------------------------------------------------------- R22
    def _collections(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, shown

        st, out = self.st, []
        before = {}
        for n in (sw.prev5 or {}).get("nav") or ():
            if COLLECTION.search(n["text"]):
                before[_path(n["href"])] = n.get("badge")
        for n in raw.get("nav") or ():
            m = COLLECTION.search(n["text"])
            if m:
                st.collections[_path(n["href"])] = m.group(1).lower()
        if ev is not None and ev.verb == "add" and ev.written:
            clicked = " ".join((d.get("el") or "") for d in done if d["do"] == "click")
            word = COLLECTION.search(clicked)
            for n in raw.get("nav") or ():
                p = _path(n["href"])
                if word and COLLECTION.search(n["text"]) and word.group(1).lower()[:4] in n["text"].lower() \
                        and before.get(p) is not None and n.get("badge") is not None:
                    sw._arm("R22")
                    if n["badge"] <= before[p]:
                        out.append(Violation("R22", f"badge|{p}", f"'{clicked.strip()[:40]}' was accepted, but the "
                                             f"{n['text']!r} badge went {before[p]} -> {n['badge']}"))
        here = _path(facts.url)
        if here in st.collections:
            for e in sw.mem.events:
                if e.worker == sw.worker and e.verb == "add" and e.written and e.obj and step - e.step <= 10 \
                        and (e.idx, "R22") not in st.reported and len(e.obj) >= 4:
                    sw._arm("R22")
                    st.reported.add((e.idx, "R22"))
                    if not shown(e.obj, facts.text) and not _written_since(sw.mem, e.target, [], e.step + 1):
                        out.append(Violation("R22", f"missing|{e.obj[:40]}", f"{e.obj!r} was added (step {e.step}) but is "
                                             f"not on the {st.collections[here]} page"))
        return out

    # ---------------------------------------------------------------- R34
    def _lifecycle(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        out, url = [], facts.url.split("#")[0]
        status = raw.get("status") or []
        prev = self.st.page_status.get(obs.url.split("#")[0])
        self.st.page_status[url] = status
        clicks = [d for d in done if d["do"] == "click"]
        label = re.sub(r"^\[\d+\]\s*\w+(\[\w+\])?\s*", "", (clicks[-1].get("el") or "")).strip(' "') if clicks else ""
        m = _LIFE_RX.match(label.lower())
        if m and any(200 <= w["status"] < 400 for w in sw.writes) and prev:
            want = LIFECYCLE[m.group(1).lower()]
            sw._arm("R34")
            if url == obs.url.split("#")[0] and want not in status and set(prev) & set(status):
                out.append(Violation("R34", f"status|{want}", f"{label!r} was accepted, but the item still shows "
                                     f"{', '.join(sorted(set(prev) & set(status)))!r}, not {want!r}"))
        # SM3: status tab counts against 'All'
        tabs = {c["unit"].lower(): c["n"] for c in facts.counts if not c.get("nav") and
                (c["unit"].lower() in STATUS_WORDS or c["unit"].lower() == "all")}
        if "all" in tabs and len(tabs) >= 3:
            sw._arm("R34")
            parts = sum(v for k, v in tabs.items() if k != "all")
            if parts != tabs["all"]:
                out.append(Violation("R34", "tabs", f"the status counts add up to {parts}, but 'All' says {tabs['all']}",
                                     ", ".join(f"{k} {v}" for k, v in tabs.items())))
        return out

    # ---------------------------------------------------------------- R35
    def _capacity(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        out, key = [], entity_key(facts.url)
        m = _AVAIL.search(facts.text or "")
        n = parse_number(m.group(1)) if m else None
        prev = self.st.avail.get(key)
        if n is not None:
            self.st.avail[key] = (n, step)
        took = ev is not None and ev.verb in ("add", "create") and ev.written and entity_key(ev.url) == key
        if took and prev is not None:
            q = next((parse_number(v) for k, v in ev.fields.items() if _QTY.search(k)), None) or 1
            sw._arm("R35")
            if q > prev[0]:
                out.append(Violation("R35", f"over|{key}", f"{q:g} were accepted while only {prev[0]:g} were available"))
            elif n is not None and n >= prev[0]:
                out.append(Violation("R35", f"left|{key}", f"taking {q:g} was accepted, but availability went "
                                     f"{prev[0]:g} -> {n:g}"))
        return out

    # ---------------------------------------------------------------- R32 (LG1)
    def _conservation(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        st, out = self.st, []
        for t in facts.tables:
            head = [norm(h) for h in t.get("head") or []]
            bi = next((i for i, h in enumerate(head) if "balance" in h), None)
            if bi is None:
                continue
            for r in t["rows"]:
                if len(r) > bi and r[0] and (v := parse_number(r[bi])) is not None:
                    acct = norm(r[0])[:40]
                    old = st.balances.get(acct)
                    st.balances[acct] = (v, step, old)
        transfer = ev is not None and ev.written and re.search(r"transfer|send money|move funds", " ".join(
            d.get("el") or "" for d in done) + " " + obs.url, re.I)
        if transfer:
            amount = next((parse_number(v) for k, v in ev.fields.items() if re.search(r"amount|sum", k, re.I)), None)
            accts = [norm(v)[:40] for k, v in ev.fields.items() if re.search(r"\bfrom\b|\bto\b|account", k, re.I)]
            if amount is not None and len(accts) >= 2:
                sw.pending_transfers.append((step, amount, accts[0], accts[1]))
        for p in list(sw.pending_transfers):
            s0, amt, a, b = p
            ra, rb = st.balances.get(a), st.balances.get(b)
            if ra and rb and ra[1] > s0 and rb[1] > s0 and ra[2] and rb[2]:
                sw.pending_transfers.remove(p)
                sw._arm("R32")
                da, db = ra[0] - ra[2][0], rb[0] - rb[2][0]
                if abs(da + amt) > 0.011 or abs(db - amt) > 0.011:
                    out.append(Violation("R32", f"transfer|{a}|{b}", f"a transfer of {amt:.2f} from {a!r} to {b!r} moved "
                                         f"the balances by {da:+.2f} and {db:+.2f}"))
        return out

    # ---------------------------------------------------------------- R70
    def _funnel(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import NOT_A_NAME, Violation, shown

        root = (urlsplit(obs.url).path.strip("/").split("/") or [""])[0]
        fl = self.st.flows.get(sw.worker)
        if fl is None or fl["root"] != root and step - fl["last"] > 2:
            fl = self.st.flows[sw.worker] = {"root": root, "steps": 0, "values": {}, "last": step}
        fills = [d for d in done if d["do"] in ("fill", "select") and (d.get("value") or "").strip()]
        if fills and any(200 <= w["status"] < 400 for w in sw.writes) or (fills and route_shape(facts.url) != route_shape(obs.url)):
            fl["steps"] += 1
            fl["last"] = step
            for d in fills:
                lab = re.sub(r"^\[\d+\]\s*", "", d.get("el") or "")
                if "password" not in lab.lower() and "search" not in lab.lower() and len(d["value"]) >= 3 \
                        and not re.search(r"card|cvv|cvc|security code", lab, re.I):
                    fl["values"][lab[:50]] = d["value"]
        if not _REVIEW.search((facts.h1 or "") + " " + (facts.title or "")) or fl["steps"] < 2 or len(fl["values"]) < 2:
            return []
        sw._arm("R70")
        shown_v = {k: v for k, v in fl["values"].items() if shown(v, facts.text)}
        missing = {k: v for k, v in fl["values"].items() if k not in shown_v and not NOT_A_NAME.search(k)}
        self.st.flows.pop(sw.worker, None)
        if shown_v and missing:
            k, v = next(iter(missing.items()))
            return [Violation("R70", f"missing|{k[:40]}", f"the {facts.h1 or 'confirmation'!r} page shows "
                              f"{len(shown_v)} of the values typed in this flow, but not {v!r} ({k})")]
        return []

    # ---------------------------------------------------------------- R12b
    def _echo(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        text, out = facts.text or "", []
        special = [t for t in sw.mem.typed if len(t) >= 4 and re.search(r"[&<>'\"À-￿]", t)]
        if not special:
            sw._ck("R12b", "unarmed", "no-special-values")
            return out
        sw._arm("R12b")
        for t in special[:30]:
            if t in text:
                continue
            esc = t
            for a, b in _ESCAPED:
                esc = esc.replace(a, b)
            folded = t.translate(_FOLD)
            qmark = re.sub(r"[^\x00-\x7f]", "?", t)
            try:
                moji = t.encode("utf-8").decode("latin-1")
            except UnicodeError:
                moji = t
            esc_folded = folded
            for a, b in _ESCAPED:
                esc_folded = esc_folded.replace(a, b)
            for variant, what in ((esc, "HTML-escaped"), (folded, "with its accents stripped"), (qmark, "with '?' for its letters"),
                                  (esc_folded, "escaped and with its accents stripped"), (moji, "as mojibake")):
                if variant != t and len(variant) >= 4 and variant in text and (t, what) not in self.st.reported:
                    self.st.reported.add((t, what))
                    out.append(Violation("R12b", f"{what}|{t[:30]}", f"{t!r} is shown {what}: {variant!r}"))
                    break
        return out[:2]

    # ---------------------------------------------------------------- D61 extensions (see the module docstring)
    def _fidelity_values(self, sw, facts, raw, step):
        """R12c (FM8, UQ3): a typed value cut short, its emoji dropped, its spaces collapsed in the form, its
        leading zeros or long digits lost. Only values the app accepted in a write, never the harness's probes."""
        from .consistency import Violation

        text, out = facts.text or "", []
        written = {str(v) for e in sw.mem.events if e.written for v in e.fields.values()} | \
            {e.obj for e in sw.mem.events if e.written and e.obj}
        # sorted: the per-page cap must keep the same findings in every run and replay (set order varies by process)
        vals = sorted(t for t in written if t and t in sw.mem.typed and t not in sw.st.probe_values and t not in text)
        item = "*" in route_shape(facts.url)
        for t in vals[:40]:
            what = None
            # D62 (I90): markdown or HTML in the value is rendered ('*bold*', '<i>'), so the shown text differs
            if item and len(t) >= 30 and t[:20] in text and not re.search(r"read more|show more|…|\.\.\.", text, re.I) \
                    and not re.search(r"[<>*_`#\[\]]", t):
                k = max(n for n in range(20, len(t)) if t[:n] in text)
                if k < len(t) - 3:
                    what = ("cut", f"{t[:30]!r}… ({len(t)} characters) is shown cut after {k}")
            if what is None and _ASTRAL.search(t):
                bare = _ASTRAL.sub("", t).strip()
                for v in (bare, _ASTRAL.sub("?", t), _ASTRAL.sub("\ufffd", t)):
                    if len(v) >= 3 and v in text:
                        what = ("emoji", f"{t!r} is shown without its emoji: {v!r}")
                        break
            if what is None and re.fullmatch(r"0\d{3,}", t) and re.search(rf"(?<![\d]){int(t)}(?![\d])", text):
                what = ("zeros", f"{t!r} is shown without its leading zeros ({int(t)})")
            if what is None and re.fullmatch(r"\d{16,}", t):
                for tok in re.findall(r"\d{16,}", text):
                    if len(tok) == len(t) and tok[:15] == t[:15] and tok != t:
                        what = ("rounded", f"{t!r} is shown rounded: {tok!r}")
                        break
            if what and (t, what[0]) not in self.st.reported:
                self.st.reported.add((t, what[0]))
                out.append(Violation("R12c", f"{what[0]}|{t[:30]}", what[1]))
        for f in raw.get("fields") or ():
            v = f.get("value") or ""
            for t in vals:
                if "  " in t and v and v == re.sub(r"\s+", " ", t).strip() and (t, "spaces") not in self.st.reported:
                    self.st.reported.add((t, "spaces"))
                    out.append(Violation("R12c", f"spaces|{f['label'][:30]}", f"{t!r} was saved, the form now holds "
                                         f"{v!r} (its spaces collapsed)"))
        return out[:2]

    def _times(self, sw, facts, raw, obs, done, ev, step):
        """R20t (TM3, TM4): an item's date or time in a list against its own page."""
        from .consistency import Violation

        key = entity_key(facts.url)
        if "*" not in route_shape(facts.url) or not facts.h1:
            return []
        here = datetimes((facts.text or "")[:4000])
        recs = {r: v for r, v in self.st.extra.get(key, {}).items() if r != route_shape(facts.url) and v[1]}
        if not here or not recs:
            return []
        sw._arm("R20t")
        out = []
        for r, (_, dts, s_step) in recs.items():
            if len(dts) != 1 or dts[0] in here or _written_since(sw.mem, key, [facts.h1], s_step):
                continue
            d, mi = dts[0]
            for d2, mi2 in here:
                if d2 == d and mi is not None and mi2 is not None and mi != mi2 and (mi - mi2) % 60 == 0 \
                        and abs(mi - mi2) <= 14 * 60:
                    out.append(Violation("R20t", f"hours|{key}", f"{r} shows {facts.h1!r} at {mi // 60:02d}:{mi % 60:02d}, "
                                         f"its own page at {mi2 // 60:02d}:{mi2 % 60:02d} on {d}"))
                    return out
            if mi is None and len(here) == 1 and here[0][1] is None and abs((here[0][0] - d).days) == 1:
                out.append(Violation("R20t", f"day|{key}", f"{r} dates {facts.h1!r} {d}, its own page {here[0][0]}"))
                return out
        return out

    def _idents(self, sw, facts, raw, obs, done, ev, step):
        """R20u (UQ1): one shown identifier on two items; one item address showing another item later."""
        from .consistency import Violation, same_name

        if "*" not in route_shape(facts.url) or not facts.h1 or _GONE.search(facts.h1):
            return []
        key, out = entity_key(facts.url), []
        for m in _IDENT.finditer((facts.text or "")[:800]):
            ident = f"{m.group(1).lower()} {m.group(2).upper()}"
            prev = self.st.idents.get(ident)
            if prev and prev[0] != key and (ident, "R20u") not in self.st.reported:
                self.st.reported.add((ident, "R20u"))
                out.append(Violation("R20u", f"ident|{ident}", f"{ident!r} is shown on two different items "
                                     f"({prev[0]} and {key})"))
            self.st.idents.setdefault(ident, (key, step))
            break
        u = facts.url.split("#")[0]
        prev = self.st.addr.get(u)
        if prev and not same_name(prev[0], facts.h1) and not _written_since(sw.mem, key, [prev[0], facts.h1], prev[1]) \
                and (u, "addr") not in self.st.reported:
            self.st.reported.add((u, "addr"))
            out.append(Violation("R20u", f"address|{route_shape(u)}", f"{u} showed {prev[0]!r} at step {prev[1]} and "
                                 f"{facts.h1!r} now, with no write in between"))
        self.st.addr[u] = (facts.h1, step)
        return out

    def _choice(self, sw, facts, raw, obs, done, ev, step):
        """R21s (FM11): an option chosen in a saved form, shown as another option when the form opens again."""
        from .consistency import Violation

        if any(200 <= w["status"] < 400 for w in sw.writes):
            for d in done:
                if d["do"] == "select" and (d.get("value") or "").strip():
                    self.st.choices[(route_shape(obs.url), _label_of(d))] = (d["value"], step, entity_key(obs.url))
        out = []
        for f in raw.get("fields") or ():
            if f["type"] != "select" or not f.get("label"):
                continue
            lab = norm(f["label"])
            for (route, l2), (val, s, key) in self.st.choices.items():
                if route != route_shape(facts.url) or key != entity_key(facts.url) or s >= step or not l2 or \
                        not (lab in l2 or l2 in lab):
                    continue
                if any(e.step > s and e.verb in ("edit", "save") and e.written for e in sw.mem.events):
                    continue
                sw._arm("R21s")
                if norm(f["value"]) != norm(val) and (route, l2, s) not in self.st.reported:
                    self.st.reported.add((route, l2, s))
                    out.append(Violation("R21s", f"choice|{lab[:30]}", f"{val!r} was chosen for {f['label']!r} and saved "
                                         f"(step {s}); the form now shows {f['value']!r}"))
        return out

    def _collateral(self, sw, facts, raw, obs, done, ev, step):
        """R09d (DB4), R09r (DB9): what a single delete removed from the list it was made on."""
        from .consistency import Violation, same_name

        if ev is None or ev.verb != "delete" or not ev.written or sw.bulk_before or sw.last is None or \
                route_shape(sw.last.url) != route_shape(facts.url):
            return []
        before, after = _names(sw.last), _names(facts)
        if len(before) < 2 or not after:
            return []
        sw._arm("R09d")
        gone = [n for n in before if not any(same_name(n, a) for a in after)]
        out = []
        target = ev.obj or getattr(sw, "row_name", "") or ""
        # D62 (I91): a card's author-and-date line read as its own item ('worker01October 29, 2026', I57) is not a
        # second item; it goes with the card
        others = [n for n in gone if not (target and same_name(n, target))
                  and not _written_since(sw.mem, "", [n], step) and n not in sw.mem.typed and not _who_when(n)]
        if target and len(gone) >= 2 and others:
            out.append(Violation("R09d", f"collateral|{route_shape(facts.url)}", f"deleting {target!r} also removed "
                                 f"{others[0]!r} from the list"))
        row = getattr(sw, "row_name", "") or ""
        if row and len(gone) == 1 and not same_name(gone[0], row) and any(same_name(row, a) for a in after):
            sw._arm("R09r")
            out.append(Violation("R09r", f"row|{route_shape(facts.url)}", f"the delete control of the row {row!r} "
                                 f"removed {gone[0]!r}; {row!r} is still listed"))
        return out

    def _archive(self, sw, facts, raw, obs, done, ev, step):
        """R49a (DB12): an archived item listed in an active list; a restored item with fewer children."""
        from .consistency import Violation, item_matches, same_name

        st, out = self.st, []
        clicks = [d for d in done if d["do"] == "click"]
        label = _label_of(clicks[-1]) if clicks else ""
        ok = any(200 <= w["status"] < 400 for w in sw.writes)
        name = (sw.last.h1 if sw.last is not None and "*" in route_shape(sw.last.url) else "") or (ev.obj if ev else "")
        if ok and name and _ARCHIVE.match(label):
            kids = sum(len(L["items"]) for L in sw.last.content_lists()) if sw.last is not None else 0
            st.archived[name] = (entity_key(sw.last.url) if sw.last is not None else "", step, kids)
        if ok and name and _RESTORE.match(label):
            st.restored[name] = step
        path = urlsplit(facts.url).path
        if not _ACTIVE.search(path) and not _ACTIVE.search(facts.h1 or ""):
            lists = [L for L in facts.content_lists() if _complete(L, raw) and not _ACTIVE.search(L.get("heading") or "")]
            for n, (key, s, _) in list(st.archived.items()):
                if s >= step or n in st.restored or _written_since(sw.mem, key, [n], s + 1):
                    continue
                if any(item_matches(i, n, key) for L in lists for i in L["items"]) and (n, "R49a") not in st.reported:
                    sw._arm("R49a")
                    st.reported.add((n, "R49a"))
                    out.append(Violation("R49a", f"active|{route_shape(facts.url)}", f"{n!r} was archived (step {s}), but "
                                         f"{route_shape(facts.url)} still lists it as active"))
        for n, s in st.restored.items():
            arch = st.archived.get(n)
            if arch and s < step and facts.h1 and same_name(facts.h1, n) and arch[2]:
                kids = sum(len(L["items"]) for L in facts.content_lists())
                if kids < arch[2] - max(1, arch[2] // 5) and (n, "R49a-r") not in st.reported:
                    st.reported.add((n, "R49a-r"))
                    out.append(Violation("R49a", f"restore|{route_shape(facts.url)}", f"{n!r} listed {arch[2]} children "
                                         f"before it was archived, {kids} after its restore"))
        return out

    def _guest(self, sw, facts, raw, obs, done, ev, step):
        """R22g (CT5) guest merge, R22v (PX4) the chosen variant on the collection line."""
        from .consistency import Violation, same_name

        st, out = self.st, []
        nav = _nav_texts(raw)
        guest = any(_LOGIN_LINK.match(t) for t in nav) and not any(_LOGOUT_LINK.match(t) for t in nav)
        if ev is not None and ev.verb == "add" and ev.written:
            name = ev.obj or (sw.last.h1 if sw.last is not None else "")
            if guest and name:
                st.guest.setdefault(sw.worker, []).append(name)
            picks = [d["value"] for d in done if d["do"] == "select" and _VARIANT.search(d.get("el") or "") and d.get("value")]
            if picks and name:
                st.variants[(sw.worker, name)] = picks
        if not guest and st.guest.get(sw.worker) and sw.worker not in st.guest_login and any(_LOGOUT_LINK.match(t) for t in nav):
            st.guest_login[sw.worker] = step
        here = _path(facts.url)
        if here not in st.collections and not _CART.search(here):
            return out
        lines = [i for L in facts.content_lists() for i in L["items"]]
        if sw.worker in st.guest_login and step > st.guest_login[sw.worker]:
            sw._arm("R22g")
            for n in st.guest.pop(sw.worker, []):
                k = sum(1 for i in lines if same_name(i["name"], n))
                if k == 0 and norm(n) not in norm(facts.text or ""):
                    out.append(Violation("R22g", f"lost|{n[:30]}", f"{n!r} was added as a guest, and is gone after logging in"))
                elif k >= 2:
                    out.append(Violation("R22g", f"doubled|{n[:30]}", f"{n!r} was added once as a guest, and is listed {k} "
                                         "times after logging in"))
        for (w, n), picks in list(st.variants.items()):
            if w != sw.worker:
                continue
            line = next((i for i in lines if same_name(i["name"], n) or norm(n) in norm(i.get("text") or "")), None)
            if line is None:
                continue
            sw._arm("R22v")
            st.variants.pop((w, n))
            miss = [v for v in picks if norm(v) not in norm(line.get("text") or "") and norm(v) not in norm(facts.text or "")]
            if miss:
                out.append(Violation("R22v", f"variant|{n[:30]}", f"{miss[0]!r} was chosen for {n!r}, but its line in "
                                     f"{here} does not show it"))
        return out

    def _closed(self, sw, facts, raw, obs, done, ev, step):
        """R34c (SM3): a write accepted on an item whose page called it closed or locked."""
        from .consistency import Violation

        prev = set((sw.prev5 or {}).get("status") or [])
        before = sw.last.text if sw.last is not None else ""
        if not (prev & _CLOSED) or not _LOCKED.search(before or "") or sw.last is None:
            return []
        key = urlsplit(sw.last.url).path.rstrip("/")
        hits = [w for w in sw.writes if 200 <= w["status"] < 400 and w.get("method", "POST") != "GET"
                and key and key.split("/")[-1] in w.get("path", "")]
        if not hits:
            return []
        sw._arm("R34c")
        return [Violation("R34c", f"closed|{route_shape(sw.last.url)}", f"the page called the item "
                          f"{', '.join(sorted(prev & _CLOSED))} and {_LOCKED.search(before).group(0)!r}, yet "
                          f"{hits[0].get('method', 'a write')} {hits[0].get('path', '')} was accepted")]

    def _status_tabs(self, sw, facts, raw, obs, done, ev, step):
        """R34 (SM4): one item listed under two exclusive status tabs."""
        from .consistency import Violation

        u = urlsplit(facts.url)
        word = next((v.lower() for k, v in parse_qsl(u.query) if v.lower() in STATUS_WORDS), "") or \
            (u.path.rstrip("/").split("/")[-1].lower() if u.path.rstrip("/").split("/")[-1].lower() in STATUS_WORDS else "")
        main = facts.main_list()
        if not word or not main:
            return []
        base = u.path if word not in u.path.lower() else u.path.rsplit("/", 1)[0]
        keys = {item_key(i, facts.url, main.get("heading") or "") for i in main["items"] if i.get("name")}
        self.st.tabs[(base, word)] = (keys, step)
        out = []
        for (b2, w2), (k2, s2) in self.st.tabs.items():
            if b2 != base or w2 == word or step - s2 > 6:
                continue
            both = [k for k in keys & k2 if not _written_since(sw.mem, k, [], s2)]
            if both and (base, frozenset((word, w2))) not in self.st.reported:
                sw._arm("R34")
                self.st.reported.add((base, frozenset((word, w2))))
                out.append(Violation("R34", f"two-tabs|{word}|{w2}", f"{both[0]} is listed under both {w2!r} and {word!r}"))
        return out

    def _booking(self, sw, facts, raw, obs, done, ev, step):
        """R36b (TM2): two accepted bookings of one slot of one resource (the agent's or the seeder's)."""
        from .consistency import Violation

        out = []
        for e in sw.mem.events[self.st.seen_events:]:
            if e.verb != "create" or not e.written or not _BOOKING.search(e.url + " " + " ".join(e.fields)):
                continue
            slot = tuple(sorted((k, str(v)) for k, v in e.fields.items() if _SLOT.search(k) and str(v).strip()))
            if not slot:
                continue
            k = (route_shape(e.url), entity_key(e.url) if "*" in route_shape(e.url) else "", slot)
            sw._arm("R36b")
            if k in self.st.bookings and self.st.bookings[k] != e.idx and not _CAPACITY.search(facts.text or ""):
                out.append(Violation("R36b", f"double|{k[0]}", f"the slot {dict(slot)} at {k[0]} was booked twice and both "
                                     "bookings were accepted"))
            self.st.bookings.setdefault(k, e.idx)
        self.st.seen_events = len(sw.mem.events)
        return out[:1]

    def _dates(self, sw, facts, raw, obs, done, ev, step):
        """R38 (SF7): a date-range filter in the address and items dated outside it."""
        from .consistency import Violation
        from .norms import find_dates

        q = dict(parse_qsl(urlsplit(facts.url).query))
        rng = {}
        for k, v in q.items():
            if k.lower() in _DATE_KEYS and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                rng[_DATE_KEYS[k.lower()]] = date.fromisoformat(v)
        main = facts.main_list()
        if not rng or not main:
            return []
        sw._arm("R38")
        for i in main["items"]:
            ds = find_dates(i.get("text") or "")
            if len(ds) == 1 and ((rng.get("min") and ds[0] < rng["min"]) or (rng.get("max") and ds[0] > rng["max"])):
                return [Violation("R38", f"dates|{route_shape(facts.url)}", f"the date filter {rng.get('min')} to "
                                  f"{rng.get('max')} lists {i['name']!r} dated {ds[0]}")]
        return []

    def _forbidden(self, sw, facts, raw, obs, done, ev, step):
        """R67f (CX3): an item this account's list showed, answering 'forbidden' when opened from it."""
        from .consistency import Violation

        if sw.last is None or len(done) != 1 or done[0]["do"] != "click":
            return []
        key = entity_key(facts.url)
        listed = any(i.get("abs") and entity_key(i["abs"]) == key for L in sw.last.content_lists() for i in L["items"])
        if not listed or not _FORBIDDEN.search((facts.h1 or "") + " " + (facts.text or "")[:1500]):
            return []
        sw._arm("R67f")
        return [Violation("R67f", f"forbidden|{route_shape(facts.url)}", f"{route_shape(sw.last.url)} lists {key} for this "
                          "account, but opening it answers that access is forbidden")]

    def _tag_pages(self, sw, facts, raw, obs, done, ev, step):
        """R68t (RL1): an item saved with a tag or assignee, missing from that tag's own page."""
        from .consistency import Violation, item_matches

        if ev is not None and ev.written and ev.verb in ("create", "edit", "save"):
            name = ev.obj or (facts.h1 or "")
            for k, v in ev.fields.items():
                if _TAGF.search(k) and name:
                    for t in re.split(r"[,;]", str(v)):
                        if len(t.strip()) >= 3:
                            self.st.tagged.setdefault(norm(t), []).append((name, step, ev.target))
        seg = norm(urlsplit(facts.url).path.rstrip("/").split("/")[-1].replace("-", " "))
        tag = next((t for t in self.st.tagged if t in (seg, norm(facts.h1 or "").lstrip("#"))), None)
        if tag is None:
            return []
        lists = [L for L in facts.content_lists() if _complete(L, raw)]
        if not lists:
            return []
        sw._arm("R68t")
        out = []
        for name, s, key in self.st.tagged[tag]:
            if s >= step or _written_since(sw.mem, key, [name], s + 1) or (tag, name) in self.st.reported:
                continue
            if not any(item_matches(i, name, key) for L in lists for i in L["items"]):
                self.st.reported.add((tag, name))
                out.append(Violation("R68t", f"tag|{tag[:30]}", f"{name!r} was saved with {tag!r} (step {s}), but the page "
                                     f"of {tag!r} does not list it"))
        return out[:1]

    def _undo(self, sw, facts, raw, obs, done, ev, step):
        """R48u (RC3): redo right after undo must give back the list as it was before the undo."""
        from .consistency import Violation

        clicks = [d for d in done if d["do"] in ("click", "press")]
        lab = (_label_of(clicks[-1]) + " " + str(clicks[-1].get("value") or "")).lower() if clicks else ""
        hist = self.st.hist.setdefault(sw.worker, [])
        names = tuple(norm(n) for n in _names(facts))
        out = []
        if re.search(r"\bredo\b|control\+y|ctrl\+y|shift\+z", lab) and len(hist) >= 2 and \
                re.search(r"\bundo\b|control\+z|ctrl\+z", hist[-1][2]) and hist[-1][1] != hist[-2][1]:
            sw._arm("R48u")
            if names and names != hist[-2][1]:
                out.append(Violation("R48u", f"redo|{route_shape(facts.url)}", "undo then redo did not give back the list "
                                     "as it was before the undo"))
        hist.append((step, names, lab))
        del hist[:-4]
        return out

    def _keys(self, sw, facts, raw, obs, done, ev, step):
        """R29k (RC4): a key the page advertises that changed nothing."""
        from .consistency import Violation

        if len(done) != 1 or done[0]["do"] != "press":
            return []
        key = str(done[0].get("value") or "")
        if not key or re.fullmatch(r"(?i)enter|tab|escape|esc|arrow\w+|page\w+|home|end|space", key):
            return []
        adv = {k.lower() for k in (sw.prev5 or {}).get("kbd") or []}
        if key.lower() not in adv and not re.search(rf"\bpress\s+{re.escape(key)}\b", (sw.last.text if sw.last else ""), re.I):
            return []
        sw._arm("R29k")
        same = sw.pre_text is not None and norm(sw.pre_text) == norm(sw.post_text or "")
        if same and not sw.writes and not sw.step_requests and facts.url == obs.url and \
                not getattr(sw, "storage_changed", False):
            return [Violation("R29k", f"key|{key}", f"the page advertises the key {key!r}; pressing it changed nothing")]
        return []

    def _unread(self, sw, facts, raw, obs, done, ev, step):
        """R47r (MU2, T3): a notification opened from its list is still counted unread on the next visit."""
        from .consistency import Violation

        u = facts.url.split("#")[0]
        if obs.url.split("#")[0] in self.st.unread and facts.url != obs.url and any(d["do"] == "click" for d in done):
            n, s, _ = self.st.unread[obs.url.split("#")[0]]
            self.st.unread[obs.url.split("#")[0]] = (n, s, True)
        if not _NOTIF.search(urlsplit(u).path):
            return []
        n = int(raw.get("unread") or 0)
        prev = self.st.unread.get(u)
        self.st.unread[u] = (n, step, False)
        if prev and prev[2] and prev[0] > 0 and n >= prev[0]:
            sw._arm("R47r")
            return [Violation("R47r", f"unread|{route_shape(u)}", f"a notification was opened from {route_shape(u)}, but "
                              f"{n} are still marked unread (before: {prev[0]})")]
        return []

    def _shuffle(self, sw, facts, raw, obs, done, ev, step):
        """R74 (MD2): shuffle must keep the set of tracks."""
        from .consistency import Violation

        clicks = [d for d in done if d["do"] == "click"]
        if not clicks or not re.match(r"shuffle", _label_of(clicks[-1])) or sw.last is None or \
                route_shape(sw.last.url) != route_shape(facts.url):
            return []
        a, b = {norm(n) for n in _names(sw.last)}, {norm(n) for n in _names(facts)}
        if len(a) >= 3 and b and a != b:
            return [Violation("R74", "shuffle", f"shuffle changed which tracks are listed ({len(a ^ b)} differ)")]
        return []

    def _header(self, sw, facts, raw, obs, done, ev, step):
        """R30 (SA2): the header offers 'Log in' while the page greets this account by name."""
        from .consistency import Violation

        nav = _nav_texts(raw)
        if sw.account is None or not sw.account.username or not any(_LOGIN_LINK.match(t) for t in nav) or \
                any(_LOGOUT_LINK.match(t) for t in nav):
            return []
        name = sw.account.username.lower()
        if any(name == t.lower() or name in t.lower().split() for t in nav):
            sw._arm("R30")
            return [Violation("R30", "header", f"the header offers 'Log in' and also shows the account {sw.account.username!r}")]
        return []

    def _empty_state(self, sw, facts, raw, obs, done, ev, step):
        """R31 (PR7): an empty state that asks to create one, on a page with no control to do it."""
        from .consistency import Violation

        m = _EMPTY_ASK.search(facts.plain or "")
        if not m:
            return []
        here = [c for c in (raw.get("controls") or []) + _nav_texts(raw) if _MAKER.match(c or "")]
        elsewhere = [c for c in self.st.controls if _MAKER.match(c)]
        sw._arm("R31")
        if not here and elsewhere:
            return [Violation("R31", f"empty-state|{m.group(1)[:20]}", f"the page says {m.group(0)!r}, but has no "
                              "control to create one")]
        return []

    def _suggestion(self, sw, facts, raw, obs, done, ev, step):
        """R61 (SF9): a chosen suggestion opening another item than the one it named."""
        from .consistency import Violation, same_name

        sugg = (sw.prev5 or {}).get("suggestions") or []
        if len(done) != 1 or done[0]["do"] != "click" or not sugg or facts.url == obs.url:
            return []
        el = obs.element(done[0]["id"]) if done[0].get("id") else None
        txt = (el.text if el else "") or ""
        pick = next((s_ for s_ in sugg if txt and same_name(s_, txt)), None)
        if pick is None or not facts.h1:
            return []
        sw._arm("R61")
        if not same_name(pick, facts.h1) and norm(pick) not in norm(facts.h1) and norm(facts.h1) not in norm(pick):
            return [Violation("R61", f"opened|{route_shape(facts.url)}", f"the suggestion {pick!r} opened {facts.h1!r}")]
        return []

    def _cart_algebra(self, sw, facts, raw, obs, done, ev, step):
        """R69 (PX1, PX2): the same cart lines must cost the same; a quantity set must stay; a coupon below its
        stated minimum, marked expired, or applied twice must not lower the total."""
        from .consistency import Violation

        if not _CART.search(urlsplit(facts.url).path):
            return []
        out = []
        total = next((parse_number(t["value"]) for t in facts.totals if re.match(r"(grand |order )?total", t["label"], re.I)), None)
        qty = [f for f in raw.get("fields") or [] if _QTY.search(f["label"] + f["name"])]
        names = _names(facts)
        if total is not None and names and len(qty) == len(names):
            sig = tuple(sorted(zip((norm(n) for n in names), (f["value"] for f in qty))))
            prev = self.st.carts.get(sig)
            sw._arm("R69")
            if prev and abs(prev[0] - total) > 0.011 and not sw.writes:
                out.append(Violation("R69", "path", f"the same cart lines cost {prev[0]:.2f} at step {prev[1]} and "
                                     f"{total:.2f} now"))
            self.st.carts.setdefault(sig, (total, step))
        accepted = any(200 <= w["status"] < 400 for w in sw.writes)
        for d in done:
            v = (d.get("value") or "").strip()
            if d["do"] == "fill" and _QTY.search(d.get("el") or "") and v not in ("", "0") and accepted and qty and \
                    not any(f["value"].strip() == v for f in qty):
                out.append(Violation("R69", "qty", f"the quantity {v} was accepted, but no cart line shows it"))
        coupon = next((d for d in done if d["do"] == "fill" and re.search(r"coupon|promo|voucher|discount code",
                                                                             d.get("el") or "", re.I)), None)
        prev_total = next((parse_number(t["value"]) for t in (sw.last.totals if sw.last else [])
                           if re.match(r"(grand |order )?total", t["label"], re.I)), None)
        if coupon and accepted and total is not None and prev_total is not None and total < prev_total - 0.009:
            sub = next((parse_number(t["value"]) for t in facts.totals if re.match(r"sub-?total", t["label"], re.I)), None)
            mn = _MINIMUM.search(facts.text or "")
            if mn and sub is not None and (want := parse_number(mn.group(1))) and sub < want:
                out.append(Violation("R69", "minimum", f"a coupon was applied to a subtotal of {sub:.2f}, below its "
                                     f"stated minimum {mn.group(1)}"))
            if re.search(r"\b(code|coupon|voucher)\b[^.]{0,40}\bexpired\b|\bexpired\b[^.]{0,40}\b(code|coupon|voucher)\b",
                         facts.text or "", re.I):
                out.append(Violation("R69", "expired", "the page calls the coupon expired, yet it lowered the total"))
            k = (sw.worker, norm(coupon["value"]))
            self.st.codes[k] = self.st.codes.get(k, 0) + 1
            if self.st.codes[k] >= 2:
                out.append(Violation("R69", "twice", f"the coupon {coupon['value']!r} lowered the total a second time"))
        return out

    def _fidelity(self, sw, facts, raw, obs, done, ev, step):
        return self._fidelity_values(sw, facts, raw, step)

    # ---------------------------------------------------------------- R56
    def _parity(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, shown

        if ev is None or ev.verb != "create" or not ev.written or route_shape(facts.url) == route_shape(obs.url):
            return []
        kind = route_shape(facts.url)
        labels_shown = {k for k, v in ev.fields.items() if shown(v, facts.text)}
        labels_missing = set(ev.fields) - labels_shown
        form = route_shape(obs.url)
        out = []
        for other, (k2, sh2, miss2) in self.st.creates.items():
            if other == form or k2 != kind:
                continue
            sw._arm("R56")
            diff = {lab for lab in labels_missing if lab in sh2}
            if diff:
                out.append(Violation("R56", f"parity|{form}|{other}", f"items made at {form} do not keep "
                                     f"{sorted(diff)[0]!r}, items made at {other} do"))
        self.st.creates[form] = (kind, labels_shown, labels_missing)
        return out[:1]

    # ---------------------------------------------------------------- R30
    def _session(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import _LOGINISH, Violation

        login_now = bool(_LOGINISH.search(route_shape(facts.url))) or any(
            f["type"] == "password" for f in raw.get("fields") or []) and not re.search(r"register|sign ?up|password", facts.url, re.I)
        was_in = sw.pages and not _LOGINISH.search(sw.pages[-1][0])
        asked = any(d["do"] in ("navigate", "goto", "back", "reload") or re.search(r"log ?out|sign ?out|log ?in|sign ?in",
                                                                                  d.get("el") or "", re.I) for d in done)
        if not login_now or not was_in or asked or sw.account is None:
            return []
        if any(e.verb == "logout" and e.worker == sw.worker for e in sw.mem.events):
            return []
        sw._arm("R30")
        return [Violation("R30", f"logged-out|{route_shape(obs.url)}", f"the session ended without a logout: "
                          f"{route_shape(obs.url)} led to a login page")]

    # ---------------------------------------------------------------- R27
    def _input_kept(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import _VALIDATION, Violation

        fills = [d for d in done if d["do"] in ("fill", "type") and (d.get("value") or "").strip()]
        if not fills or route_shape(facts.url) != route_shape(obs.url) or any(200 <= w["status"] < 400 for w in sw.writes):
            return []
        before = sw.last.text if sw.last else ""
        if not any(_VALIDATION.search(t) and t not in before for t in facts.errors +
                   [ln for ln in (facts.text or "").splitlines() if len(ln) < 160]):
            return []
        fields = raw.get("fields") or []
        sw._arm("R27")
        out = []
        for d in fills:
            lab = norm(re.sub(r'^\[\d+\]\s*\S+\s*', "", d.get("el") or ""))
            f = next((f for f in fields if norm(f["label"]) and norm(f["label"]) in lab), None)
            if f and f["type"] not in ("password", "file") and not f["value"].strip():
                out.append(Violation("R27", f"cleared|{f['label'][:40]}", f"after the form was rejected, "
                                     f"{f['label']!r} is empty again (it held {d['value'][:40]!r})"))
        return out[:2]

    # ---------------------------------------------------------------- R29
    def _dead(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        if len(done) != 1 or done[0]["do"] != "click" or not done[0].get("ok", True):
            return []
        el = obs.element(done[0]["id"]) if done[0].get("id") else None
        if el is None or el.disabled or el.tag not in ("button", "input") and el.role != "button":
            return []
        name = (el.text or el.label or "").strip()
        if not _ACTION_VERB.match(name) or (sw.pre or {}).get("form_valid") is False:
            return []
        sw._arm("R29")
        net = sw.step_requests
        same = sw.pre_text is not None and norm(sw.pre_text) == norm(sw.post_text or "")
        if not sw.writes and not net and facts.url == obs.url and same and not sw.dialogs_this_step and \
                not getattr(sw, "storage_changed", False):
            return [Violation("R29", f"dead|{name[:40]}", f"clicking {name!r} sent no request, changed no address and "
                              "left the page as it was")]
        return []

    # ---------------------------------------------------------------- R38
    def _facets(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        out = []
        if len(done) == 1 and done[0]["do"] == "click" and facts.url != obs.url:
            el = obs.element(done[0]["id"]) if done[0].get("id") else None
            m = re.search(r"\((\d{1,4})\)\s*$|\s(\d{1,4})$", (el.text if el else "") or "")
            main = facts.main_list()
            if m and main and not re.search(r"page|\bnext\b", el.text or "", re.I):
                n = int(m.group(1) or m.group(2))
                got = facts.showing["n"] if facts.showing else (len(main["items"]) if _complete(main, raw) else None)
                sw._arm("R38")
                if got is not None and got != n and not (n == 0 and not main["items"]):
                    out.append(Violation("R38", f"facet|{(el.text or '')[:30]}", f"{el.text!r} promises {n}, the page it "
                                         f"opens has {got}"))
        # SF3 (R38c): adding a filter to the same address must not add results; clearing it restores them
        u = urlsplit(facts.url)
        q = dict(parse_qsl(u.query))
        main = facts.main_list()
        n = facts.showing["n"] if facts.showing else (len(main["items"]) if main and _complete(main, raw) else None)
        if n is not None and not sw.writes:
            seen = self.st.__dict__.setdefault("filter_counts", {})
            for (path, params), (m_, s_) in list(seen.items()):
                if path != u.path or s_ < step - 15:
                    continue
                p0 = dict(params)
                if p0 and set(p0.items()) < set(q.items()) and n > m_:
                    sw._arm("R38c")
                    out.append(Violation("R38c", f"compose|{route_shape(facts.url)}", f"adding a filter "
                                         f"({', '.join(k for k in q if k not in p0)}) raised the results from {m_} to {n}"))
            seen[(u.path, tuple(sorted(q.items())))] = (n, step)
        rng = {_RANGE_KEYS[k.lower()][1]: parse_number(v) for k, v in q.items() if k.lower() in _RANGE_KEYS}
        main = facts.main_list()
        if rng and main:
            sw._arm("R38")
            for i in main["items"]:
                vals = money_values(i.get("text", ""))
                if len(vals) != 1:
                    continue
                v = vals[0]
                if (rng.get("min") is not None and v < rng["min"] - 0.01) or (rng.get("max") is not None and v > rng["max"] + 0.01):
                    out.append(Violation("R38", f"range|{route_shape(facts.url)}", f"the price filter "
                                         f"{rng.get('min')}-{rng.get('max')} lists {i['name']!r} at {v:.2f}"))
                    break
        return out

    # ---------------------------------------------------------------- R44
    def _prefs(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        for d in done:
            if d["do"] == "select" and _PAGESIZE.search(d.get("el") or "") and (n := parse_number(d.get("value") or "")):
                self.st.page_size[sw.worker] = (int(n), step)
        p = self.st.page_size.get(sw.worker)
        main = facts.main_list()
        if not p or not main or step == p[1] or step - p[1] > 5:
            return []
        sw._arm("R44")
        if len(main["items"]) > p[0]:
            return [Violation("R44", f"pagesize|{route_shape(facts.url)}", f"a page size of {p[0]} was chosen at step "
                              f"{p[1]}, but the list shows {len(main['items'])} items")]
        return []

    # ---------------------------------------------------------------- R55
    def _bulk(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation, shown

        sel = sw.bulk_before
        sw.bulk_before = None
        if not sel or not any(200 <= w["status"] < 400 for w in sw.writes):
            return []
        sw._arm("R55")
        chosen, others, deleting = sel["selected"], sel["others"], sel["delete"]
        out = []
        if deleting:
            still = [n for n in chosen if shown(n, facts.text)]
            gone = [n for n in others if not shown(n, facts.text)]
            if still:
                out.append(Violation("R55", "kept-selected", f"a bulk delete was accepted, but selected {still[0]!r} is still listed"))
            if gone and len(gone) < len(others):
                out.append(Violation("R55", "removed-unselected", f"a bulk delete also removed {gone[0]!r}, which was not selected"))
        m = re.search(r"\b(\d+)\s+(items?|records?|rows?|\w+s)\s+(deleted|removed|updated|archived|moved|marked)", facts.text or "", re.I)
        if m and int(m.group(1)) != len(chosen):
            out.append(Violation("R55", "count", f"the message says {m.group(0)!r}, but {len(chosen)} rows were selected"))
        return out

    # ---------------------------------------------------------------- R58
    def _clone(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        clicks = [d for d in done if d["do"] == "click"]
        if not clicks or not re.search(r"\b(copy|duplicate|clone)\b", clicks[-1].get("el") or "", re.I) or \
                not any(200 <= w["status"] < 400 for w in sw.writes) or entity_key(facts.url) == entity_key(obs.url):
            return []
        orig = sw.last if sw.last is not None and sw.last.url == obs.url else None
        if orig is None:
            return []
        sw._arm("R58")
        n0 = sum(len(L["items"]) for L in orig.content_lists())
        n1 = sum(len(L["items"]) for L in facts.content_lists())
        if n0 >= 1 and n1 < n0 - max(1, n0 // 5):
            return [Violation("R58", f"children|{route_shape(facts.url)}", f"the copy lists {n1} children, its original "
                              f"{n0}")]
        return []

    # ---------------------------------------------------------------- R69
    def _cart(self, sw, facts, raw, obs, done, ev, step):
        from .consistency import Violation

        out = []
        accepted = any(200 <= w["status"] < 400 for w in sw.writes)
        total = next((parse_number(t["value"]) for t in facts.totals if re.match(r"(grand |order )?total", t["label"], re.I)), None)
        zero = [d for d in done if d["do"] == "fill" and _QTY.search(d.get("el") or "") and (d.get("value") or "").strip() == "0"]
        if zero and accepted:
            sw._arm("R69")
            if any(_QTY.search(f["label"] + f["name"]) and f["value"].strip() == "0" for f in raw.get("fields") or []):
                out.append(Violation("R69", "qty-zero", "quantity 0 was accepted, but the line is still in the cart"))
        coupon = [d for d in done if d["do"] == "fill" and re.search(r"coupon|promo|voucher|discount code", d.get("el") or "", re.I)]
        prev_total = next((parse_number(t["value"]) for t in (sw.last.totals if sw.last else [])
                           if re.match(r"(grand |order )?total", t["label"], re.I)), None)
        if coupon and accepted and prev_total is not None:
            self.st.coupon[sw.worker] = prev_total
        removed = [d for d in done if d["do"] == "click" and re.search(r"remove|×|delete", d.get("el") or "", re.I)]
        before = self.st.coupon.get(sw.worker)
        if removed and accepted and before is not None and total is not None and \
                not re.search(r"coupon|promo|voucher|discount", facts.text or "", re.I):
            sw._arm("R69")
            self.st.coupon.pop(sw.worker, None)
            if abs(total - before) > 0.011:
                out.append(Violation("R69", "coupon", f"removing the coupon left the total at {total:.2f}; before it was "
                                     f"applied the total was {before:.2f}"))
        return out


def message_fidelity(sw, msgs: list[dict], ev, done: list[dict]) -> list:
    """R51c (FB2): a message counting another number than one single change, or naming another item.
    Called from the Sweeper's evidence step (it drains the transient messages)."""
    from .consistency import Violation, same_name

    if not msgs or ev is None or not ev.written or sw.bulk_before:
        return []
    sw._arm("R51c")
    for m in msgs:
        t = m.get("text") or ""
        n = _MSG_N.search(t)
        if n and int(n.group(1)) > 1:
            return [Violation("R51c", f"count|{n.group(2).lower()}", f"after one {ev.verb} the app says {t[:80]!r}")]
        q = _MSG_NAME.search(t)
        if q and ev.obj and len(ev.obj) >= 3 and not same_name(q.group(1), ev.obj) and norm(ev.obj) not in norm(q.group(1)) \
                and norm(q.group(1)) not in norm(ev.obj):
            return [Violation("R51c", f"name|{ev.verb}", f"after {ev.verb} {ev.obj!r} the app says {t[:80]!r}")]
    return []
