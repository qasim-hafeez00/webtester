"""Structured run memory (harness v4, D49), shared by all workers of a run.

What the agents did and what the app showed, kept so that consistency oracles
(consistency.py) can check the app against itself and against the agents' own
actions, instead of against a guess about the app's design:

  M1 ledger    one event per data-relevant action: verb, object, where, typed fields,
               outcome status (pending -> verified | conflict | unknown)
  M2 entities  one record per item (keyed by its normalised path): names seen,
               status, saved fields, toggle states, ages shown per page
  M3 lists     snapshots of every non-navigation list per (page URL, heading):
               items per visit, with the ledger position at that visit
  M5 notes     a few lines for the worker's prompt: recent intents and their status

Verbs come from the agent's declared intent when it gave one, else from word lists
over the clicked control (English only, a documented limit). Every fact keeps its
source (worker, step, URL) so a finding can cite the observations that conflict.
The memory is derived from what the harness observes, so the gate and `resweep`
rebuild it deterministically by replaying the recorded actions.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

from .lexicon import lexicon
from .state import route_shape

MAX_ENTITIES = 2000
MAX_LISTS = 300

# Order matters: the first pattern that matches the control's text, label or class wins.
# The v4 word lists live in lexicon/<lang>.toml, [v4] (D61, I56: moved verbatim; tests pin the patterns).
_V4 = lexicon()["v4"]
_VERB_RULES = [tuple(x) for x in _V4["verbs"]]
VERB_RES = [(v, re.compile(p, re.I)) for v, p in _VERB_RULES]
TOGGLES = {"favourite": "unfavourite", "follow": "unfollow", "like": "unlike"}
OFF = {v: k for k, v in TOGGLES.items()}
SEARCH_FIELD = re.compile(r"search|query|\bfind\b|^q$|keyword", re.I)
FILTER_KEYS = {"tag", "tags", "filter", "category", "categories", "type", "label", "topic", "author", "status"}
TITLE_FIELD = re.compile(r"\b(title|name|subject|heading|summary)\b", re.I)

# List headings: which lists are about the viewer (compared with that worker's own events only)
# and which are ordered by recency (items legitimately drop off the end).
PERSONAL = re.compile(_V4["personal"], re.I)
RECENCY = re.compile(_V4["recency"], re.I)
# Event feeds: anyone's action anywhere adds an entry, so additions there explain nothing and prove nothing.
EVENT_FEED = re.compile(_V4["event_feed"], re.I)
CATEGORY = [(v, re.compile(p, re.I)) for v, p in _V4["categories"]]  # list heading -> the verb its objects need


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def entity_key(url: str) -> str:
    """Identity of an item: its path (a client-side '#/...' route counts as the path), no query."""
    u = urlsplit(url or "")
    path = u.fragment if u.fragment.startswith("/") else u.path
    return (path.rstrip("/") or "/").lower()


def item_key(item: dict, page_url: str, heading: str = "") -> str:
    """O6 (c), D61: an item's identity: its link when it has one, else the page's route, the list heading and
    the item's name (cards and rows with no link of their own). Used by the v5 rules; the v4 rules keep
    entity_key."""
    if item.get("abs"):
        return entity_key(item["abs"])
    return f"{route_shape(page_url)}#{norm(heading)[:40]}#{norm(item.get('name') or '')[:60]}"


def list_key(url: str, heading: str) -> str:
    """Identity of a list: the page's path with its query (page=2 is another list) and its heading."""
    u = urlsplit(url or "")
    q = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(u.query, keep_blank_values=True)))
    return f"{entity_key(url)}?{q}|{norm(heading)[:60]}"


def classify(text: str) -> str:
    """Verb of a clicked control from its visible text, label or class names ('' if none)."""
    for verb, rx in VERB_RES:
        if rx.search(text or ""):
            return verb
    return ""


def category_of(heading: str) -> str:
    for verb, rx in CATEGORY:
        if rx.search(heading or ""):
            return verb
    return ""


@dataclass
class Event:
    idx: int
    worker: int
    step: int
    verb: str  # create | edit | delete | favourite | unfavourite | follow | unfollow | like | unlike |
    #            view | search | filter | login | logout | submit
    obj: str = ""  # object name (typed title, item text or page heading)
    typ: str = ""  # item type if the agent said so (book, article, ...)
    url: str = ""  # page where the action happened
    target: str = ""  # entity key of the object, when known
    fields: dict = field(default_factory=dict)  # field label -> typed value
    landing: str = ""  # URL after the action
    status: str = "pending"  # pending | verified | conflict | unknown
    source: str = "lexicon"  # intent | lexicon
    due: int = 0  # step by which the effect must be seen
    t: float = field(default_factory=time.time)
    note: str = ""
    written: bool = False  # the app accepted a write request (2xx/3xx) for it
    before: int = 0  # delete: times the object's text was on the page before the action

    def brief(self) -> str:
        obj = f" {self.obj!r}" if self.obj else ""
        return f"s{self.step} {self.verb}{obj} ({self.status}{': ' + self.note if self.note else ''})"


@dataclass
class Entity:
    key: str
    names: dict = field(default_factory=dict)  # name -> (worker, step, url) where seen
    status: str = "alive"  # alive | deleted
    saved: dict = field(default_factory=dict)  # field label -> last saved value
    toggles: dict = field(default_factory=dict)  # verb -> (on: bool, worker, step)
    ages: dict = field(default_factory=dict)  # (kind, page path) -> (minutes, text, worker, step)
    touched: float = 0.0  # wall time of the last event of an agent on it
    last_step: int = 0


@dataclass
class Snapshot:
    items: list  # [(name, href)]
    worker: int
    step: int
    event_idx: int  # ledger length when the snapshot was taken
    url: str
    t: float = field(default_factory=time.time)


@dataclass
class ListInfo:
    key: str
    heading: str
    personal: bool
    recency: bool
    category: str
    snaps: list = field(default_factory=list)  # last snapshots (at most 4)
    volatile: bool = False


class RunMemory:
    def __init__(self):
        self.events: list[Event] = []
        self.entities: OrderedDict[str, Entity] = OrderedDict()
        self.lists: OrderedDict[str, ListInfo] = OrderedDict()
        self.typed: set[str] = set()  # every value typed by any worker (excluded from junk rules)
        self.page_text: dict[int, list[tuple[str, str]]] = {}  # worker -> [(url, text)] recent pages

    # ---------- M1 ----------
    def add_event(self, **kw) -> Event:
        e = Event(len(self.events), **kw)
        self.events.append(e)
        if e.target:
            ent = self.entity(e.target)
            ent.touched = e.t
            ent.last_step = e.step
        return e

    def pending(self, worker: int | None = None) -> list[Event]:
        return [e for e in self.events if e.status == "pending" and (worker is None or e.worker == worker)]

    def events_since(self, idx: int, worker: int | None = None) -> list[Event]:
        return [e for e in self.events[idx:] if worker is None or e.worker == worker]

    def net_toggle(self, worker: int, verb: str) -> dict[str, Event]:
        """Objects this worker turned `verb` on (and not off again), by entity key or name."""
        on: dict[str, Event] = {}
        off = TOGGLES.get(verb, "delete")
        for e in self.events:
            if e.worker != worker or e.verb not in (verb, off) or e.status == "conflict":
                continue
            k = e.target or norm(e.obj)
            if not k:
                continue
            if e.verb == verb:
                on[k] = e
            else:
                on.pop(k, None)
        return on

    def views(self, worker: int) -> list[Event]:
        return [e for e in self.events if e.worker == worker and e.verb == "view"]

    # ---------- M2 ----------
    def entity(self, key: str) -> Entity:
        ent = self.entities.get(key)
        if ent is None:
            ent = self.entities[key] = Entity(key)
            if len(self.entities) > MAX_ENTITIES:
                self.entities.popitem(last=False)
        else:
            self.entities.move_to_end(key)
        return ent

    def known_name(self, name: str) -> bool:
        n = norm(name)
        return any(n == norm(e.obj) for e in self.events) or any(n in map(norm, ent.names) for ent in self.entities.values())

    # ---------- M3 ----------
    def snapshot(self, url: str, heading: str, items: list, worker: int, step: int) -> tuple[ListInfo, Snapshot | None]:
        """Record a list's items; returns (list info, this worker's previous snapshot or None).
        Lists are kept per worker: a revisit compares what one account saw twice (many lists,
        e.g. a dashboard's, differ between accounts without saying so in their heading)."""
        key = f"w{worker}|{list_key(url, heading)}"
        info = self.lists.get(key)
        if info is None:
            info = self.lists[key] = ListInfo(key, heading, bool(PERSONAL.search(heading or "")),
                                              bool(RECENCY.search(heading or "")), category_of(heading))
            if len(self.lists) > MAX_LISTS:
                self.lists.popitem(last=False)
        else:
            self.lists.move_to_end(key)
        prev = info.snaps[-1] if info.snaps else None
        info.snaps.append(Snapshot(items, worker, step, len(self.events), url))
        del info.snaps[:-4]
        return info, prev

    def remember_page(self, worker: int, url: str, text: str) -> None:
        pages = self.page_text.setdefault(worker, [])
        pages.append((url, text[:6000]))
        del pages[:-10]

    # ---------- M5 ----------
    def notes(self, worker: int, n: int = 6) -> list[str]:
        """Prompt lines: this worker's recent intents and their status, oldest first."""
        mine = [e for e in self.events if e.worker == worker and e.verb not in ("view",)]
        lines = [e.brief() for e in mine[-n:]]
        made = [e.obj for e in self.events if e.worker == worker and e.verb == "create" and e.obj
                and e.status != "conflict"][-4:]
        if made:
            lines.append("items you created: " + ", ".join(repr(m) for m in made))
        return lines


# ---------- helpers used by the oracles ----------
_REL = re.compile(r"\b(just now|a moment ago|moments ago|yesterday|today|"
                  r"(?:in\s+)?(\d+|an?|one)\s+(second|sec|minute|min|hour|hr|day|week|month|year)s?(\s+ago)?)\b", re.I)
_UNIT_MIN = {"second": 1 / 60, "sec": 1 / 60, "minute": 1, "min": 1, "hour": 60, "hr": 60, "day": 1440,
             "week": 10080, "month": 43200, "year": 525600}


def age_minutes(text: str) -> float | None:
    """Minutes a relative time stands for ('5 minutes ago' -> 5); negative for future ('in 3 days')."""
    m = _REL.search(text or "")
    if not m:
        return None
    s = m.group(0).lower()
    if s in ("just now", "a moment ago", "moments ago", "today"):
        return 0.0
    if s == "yesterday":
        return 1440.0
    n = m.group(2).lower()
    k = 1 if n in ("a", "an", "one") else int(n)
    minutes = k * _UNIT_MIN[m.group(3).lower()]
    if s.startswith("in ") and not m.group(4):
        return -minutes
    if not m.group(4):
        return None  # "3 days" without 'ago' is a duration, not an age
    return minutes


def age_class(minutes: float) -> int:
    """0 seconds/minutes, 1 hours, 2 days, 3 months, 4 years."""
    if minutes < 60:
        return 0
    if minutes < 1440:
        return 1
    if minutes < 43200:
        return 2
    if minutes < 525600:
        return 3
    return 4


def age_kind(context: str) -> str:
    c = (context or "").lower()
    if re.search(r"creat|added|posted|published|joined|registered", c):
        return "created"
    if re.search(r"updat|edit|modif|changed|saved", c):
        return "updated"
    return "other"
