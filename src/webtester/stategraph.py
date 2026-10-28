"""Abstract state graph (harness v4, D49): states, actions and transitions seen while exploring.

Built by the harness from what it already computes (no LLM tokens), shared by all
workers of a run. Two levels:

  page  = route shape (state.route_shape): what memory and oracles reason about;
  state = state.state_id (route shape + text-free skeleton): what exploration uses.

An edge is (state, action) -> distribution of next states, where the action is the
step's actions as element keys plus value classes (the same identity as
state.action_key without the state). Each edge keeps who took it (worker, LLM or
harness), whether it changed data (a memory verb) and how many error signals came
with it. Like Crawljax's state-flow graph (Mesbah et al., TSE 2012) it serves three
uses: guidance (harness travel to a known page without an LLM call, compact
prompts), oracles (back button, navigation determinism; consistency.py) and a
record for later analysis (graph.json, Mermaid export, path coverage).
"""

from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .state import route_shape, value_class

DATA_VERBS = {"create", "edit", "delete", "favourite", "unfavourite", "follow", "unfollow", "like", "unlike",
              "submit", "login", "logout"}


def action_label(actions: list[dict]) -> str:
    """Identity of a step's actions without the state: do + element key + value class."""
    parts = []
    for a in actions:
        v = a.get("value")
        vc = value_class(v) if a["do"] in ("fill", "type") and v is not None else (v or "")[:60] \
            if a["do"] in ("select", "press", "navigate") else ""
        parts.append(f"{a['do']}|{a.get('ekey') or ''}|{vc}")
    return " ; ".join(parts)


def is_navigation(actions: list[dict]) -> bool:
    """One link click (an <a> with an href) or one navigate/back: moves without changing data."""
    if len(actions) != 1:
        return False
    a = actions[0]
    if a["do"] in ("navigate", "back"):
        return True
    ekey = a.get("ekey") or ""
    tag, _, _ = ekey.partition("|")
    href = ekey.rsplit("|", 1)[-1] if ekey else ""
    return a["do"] == "click" and tag == "a" and bool(href) and not href.startswith(("#", "javascript:"))


@dataclass
class Node:
    sid: str
    page: str
    url: str
    visits: int = 0
    first_step: int = 0
    workers: set = field(default_factory=set)


@dataclass
class Page:
    route: str
    name: str = ""
    url: str = ""  # last URL seen: harness travel goes here
    heading: str = ""
    states: set = field(default_factory=set)
    visits: int = 0


@dataclass
class Edge:
    src: str
    action: str
    label: str  # short human description of the first action
    dst: Counter = field(default_factory=Counter)
    workers: set = field(default_factory=set)
    by: Counter = field(default_factory=Counter)  # llm | harness | crawler
    verb: str = ""
    nav: bool = False
    signals: int = 0

    @property
    def dst_pages(self) -> set:
        return {d.split("@", 1)[1] for d in self.dst}


class StateGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.pages: dict[str, Page] = {}
        self.edges: dict[tuple[str, str], Edge] = {}
        self.travels = 0

    # ---------- updates ----------
    def visit(self, worker: int, sid: str, url: str, step: int, heading: str = "") -> Node:
        page = route_shape(url)
        n = self.nodes.get(sid)
        if n is None:
            n = self.nodes[sid] = Node(sid, page, url, first_step=step)
        n.visits += 1
        n.workers.add(worker)
        p = self.pages.setdefault(page, Page(page))
        p.url = url
        p.states.add(sid)
        p.visits += 1
        if heading and not p.heading:
            p.heading = heading[:80]
        return n

    def transition(self, worker: int, src: str, actions: list[dict], dst: str, by: str = "llm",
                   verb: str = "", signals: int = 0) -> Edge | None:
        if not actions or src not in self.nodes or dst not in self.nodes:
            return None
        key = (src, action_label(actions))
        e = self.edges.get(key)
        if e is None:
            first = actions[0]
            e = self.edges[key] = Edge(src, key[1], f"{first['do']} {(first.get('el') or first.get('value') or '')}"[:80],
                                       nav=is_navigation(actions))
        e.dst[f"{dst}@{self.nodes[dst].page}"] += 1
        e.workers.add(worker)
        e.by[by] += 1
        e.signals += signals
        if verb and verb in DATA_VERBS:
            e.verb = verb
            e.nav = False
        return e

    def name_page(self, route: str, name: str) -> None:
        p = self.pages.get(route)
        if p is not None and not p.name and name:
            p.name = " ".join(str(name).split())[:40]

    # ---------- queries ----------
    def unnamed(self, route: str) -> bool:
        p = self.pages.get(route)
        return p is not None and not p.name

    def nondeterministic_nav(self) -> list[Edge]:
        """Navigation edges (no data change) that led to different pages on different occasions."""
        return [e for e in self.edges.values() if e.nav and not e.verb and len(e.dst_pages) > 1]

    def travel_url(self, route: str) -> str | None:
        """A URL that reaches `route` directly (harness travel): the last one seen there."""
        p = self.pages.get(route)
        return p.url if p and p.url else None

    def path(self, src: str, dst_page: str, max_len: int = 8) -> list[Edge] | None:
        """Shortest known edge path from state `src` to any state of page `dst_page` (BFS)."""
        if src in self.nodes and self.nodes[src].page == dst_page:
            return []
        out: dict[str, list[Edge]] = {}
        for e in self.edges.values():
            out.setdefault(e.src, []).append(e)
        seen, q = {src}, deque([(src, [])])
        while q:
            s, p = q.popleft()
            if len(p) >= max_len:
                continue
            for e in out.get(s, ()):
                for d in e.dst:
                    sid = d.split("@", 1)[0]
                    if sid in seen:
                        continue
                    if self.nodes[sid].page == dst_page:
                        return p + [e]
                    seen.add(sid)
                    q.append((sid, p + [e]))
        return None

    def stats(self) -> dict:
        by = Counter()
        for e in self.edges.values():
            by.update(e.by)
        return {"states": len(self.nodes), "pages": len(self.pages), "edges": len(self.edges),
                "nav_edges": sum(1 for e in self.edges.values() if e.nav),
                "data_edges": sum(1 for e in self.edges.values() if e.verb),
                "nondeterministic_nav": len(self.nondeterministic_nav()),
                "named_pages": sum(1 for p in self.pages.values() if p.name),
                "states_per_page_median": _median([len(p.states) for p in self.pages.values()]),
                "edges_by": dict(by), "travels": self.travels}

    # ---------- persistence ----------
    def to_dict(self) -> dict:
        return {
            "pages": [{"route": p.route, "name": p.name, "heading": p.heading, "url": p.url,
                       "states": sorted(p.states), "visits": p.visits} for p in self.pages.values()],
            "nodes": [{"sid": n.sid, "page": n.page, "url": n.url, "visits": n.visits, "first_step": n.first_step,
                       "workers": sorted(n.workers)} for n in self.nodes.values()],
            "edges": [{"src": e.src, "action": e.action, "label": e.label, "dst": dict(e.dst),
                       "workers": sorted(e.workers), "by": dict(e.by), "verb": e.verb, "nav": e.nav,
                       "signals": e.signals} for e in self.edges.values()],
            "stats": self.stats(),
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")


def load_graph(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mermaid(graph: dict, max_edges: int = 200) -> str:
    """Page-level Mermaid flowchart of a saved graph (for figures): one node per page,
    one arrow per (page, page) pair with the number of edges and whether data changed."""
    names = {p["route"]: (p["name"] or p["route"]) for p in graph["pages"]}
    ids = {r: f"p{i}" for i, r in enumerate(sorted(names))}
    node_page = {n["sid"]: n["page"] for n in graph["nodes"]}
    pairs: Counter = Counter()
    data: set = set()
    for e in graph["edges"]:
        a = node_page.get(e["src"])
        for d in e["dst"]:
            b = d.split("@", 1)[1]
            if a and b and a != b:
                pairs[(a, b)] += 1
                if e["verb"]:
                    data.add((a, b))
    lines = ["flowchart LR"]
    for r, i in ids.items():
        lines.append(f'  {i}["{names[r]}<br/><small>{r}</small>"]'.replace('"', '"'))
    for (a, b), n in pairs.most_common(max_edges):
        arrow = "==>" if (a, b) in data else "-->"
        lines.append(f"  {ids[a]} {arrow}|{n}| {ids[b]}")
    return "\n".join(lines)


def _median(xs: list[int]) -> float:
    if not xs:
        return 0
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def same_origin_path(url: str) -> str:
    u = urlsplit(url)
    return u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")
