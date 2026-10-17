"""Exploration frontier (G1): a map of abstract states and the element actions
tried in each, used to steer LLM workers away from duplicated work.

One instance shared by all workers of a run gives B3 (shared frontier). One
instance per worker gives the ablation B3-local: the same mechanism without
sharing, which separates "having a map" from "sharing the map".

Coordination is advisory, not enforced: a worker sees which elements are done
or taken and where untouched work is, and the LLM decides. Workers run as
asyncio tasks in one process, so no locking is needed.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from .browser import Element, Observation
from .state import route_shape, value_class


@dataclass
class StateInfo:
    url: str
    route: str
    elements: dict[str, str] = field(default_factory=dict)  # element key -> short description
    visits: int = 0


class Frontier:
    def __init__(self, shared: bool, lease_s: float = 90.0):
        self.shared = shared
        self.lease_s = lease_s
        self.states: dict[str, StateInfo] = {}
        self.tries: Counter = Counter()  # (state, element key) -> times exercised
        self.claims: dict[tuple[str, str], tuple[int, float]] = {}  # -> (worker, lease expiry)
        self.targets: dict[int, tuple[str, float]] = {}  # worker -> (state it was sent to, expiry)
        self.routes: Counter = Counter()

    # ---------- updates ----------
    def visit(self, worker: int, sid: str, obs: Observation) -> None:
        info = self.states.get(sid)
        if info is None:
            info = self.states[sid] = StateInfo(obs.url, route_shape(obs.url))
        info.visits += 1
        for e in obs.elements:
            if not e.disabled:
                info.elements.setdefault(e.key(), e.describe().split("] ", 1)[-1][:60])
        self.routes[info.route] += 1
        tgt = self.targets.get(worker)
        if tgt and tgt[0] == sid:
            del self.targets[worker]  # arrived

    def claim(self, worker: int, sid: str, keys: list[str]) -> None:
        until = time.monotonic() + self.lease_s
        for k in keys:
            self.claims[(sid, k)] = (worker, until)

    def record(self, worker: int, sid: str, key: str, do: str | None = None, value: str | None = None) -> None:
        self.tries[(sid, key)] += 1
        self.claims.pop((sid, key), None)

    # ---------- queries ----------
    def _taken_by_other(self, worker: int, sid: str, key: str) -> bool:
        c = self.claims.get((sid, key))
        return bool(c) and c[0] != worker and c[1] > time.monotonic()

    def _path(self, url: str) -> str:
        u = urlsplit(url)
        return u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")

    def mark(self, worker: int, sid: str, el: Element) -> str:
        k = el.key()
        if self._taken_by_other(worker, sid, k):
            return "[taken]"
        n = self.tries[(sid, k)]
        return f"[done x{n}]" if n else ""

    def untouched(self, worker: int, sid: str) -> int:
        info = self.states.get(sid)
        if not info:
            return 0
        return sum(1 for k in info.elements if not self.tries[(sid, k)] and not self._taken_by_other(worker, sid, k))

    def suggest(self, worker: int, current: str, threshold: int = 2) -> str | None:
        """When the current state is nearly exhausted, point the worker at the
        state with the most untouched elements that no other worker is heading to."""
        if self.untouched(worker, current) > threshold:
            return None
        now = time.monotonic()
        heading = {s for w, (s, until) in self.targets.items() if w != worker and until > now}
        best, best_n = None, threshold
        for sid, info in self.states.items():
            if sid == current or sid in heading:
                continue
            n = self.untouched(worker, sid)
            if n > best_n:
                best, best_n = sid, n
        if best is None:
            return None
        self.targets[worker] = (best, now + self.lease_s)
        info = self.states[best]
        return f"{info.route} has {best_n} untouched elements: navigate to {self._path(info.url)}"

    def stats(self) -> dict:
        tried = sum(1 for v in self.tries.values() if v)
        total = sum(len(i.elements) for i in self.states.values())
        return {"states": len(self.states), "elements": total, "elements_tried": tried}


FILLABLE = {"input", "textarea"}
NON_TEXT_INPUTS = {"checkbox", "radio", "submit", "button", "file", "hidden", "image", "reset"}


class FrontierV2(Frontier):
    """B3 v2, from the v1 pilot (I16): the v1 suggestion never fired because nav-bar
    elements kept every page "unexplored", and workers converged on the same forms.

    1. Global elements (on >= half of the known states, e.g. the nav bar) do not
       count as untouched work.
    2. Each worker owns a focus area: the route with the most untouched work (or a
       linked route nobody has visited) that no other worker owns. It is reassigned
       when the area runs dry or after `rotate_steps` steps, so areas get rotated.
    3. Text fields show which input classes (empty, text, long, special, ...) were
       already typed into them, so repeated form runs try new input classes.
    """

    version = 2

    def __init__(self, shared: bool, lease_s: float = 90.0, rotate_steps: int = 15,
                 global_share: float = 0.5, min_states_for_global: int = 4, dry_threshold: int = 2):
        super().__init__(shared, lease_s)
        self.rotate_steps = rotate_steps
        self.global_share = global_share
        self.min_states_for_global = min_states_for_global
        self.dry_threshold = dry_threshold
        self.key_states: dict[str, set[str]] = defaultdict(set)  # element key -> states it appears in
        self.value_classes: dict[tuple[str, str], set[str]] = defaultdict(set)  # (state, key) -> classes typed
        self.links: dict[str, str] = {}  # route shape -> a path that leads there (from hrefs seen)
        self.route_url: dict[str, str] = {}  # route shape -> last URL seen for it
        self.focus_of: dict[int, tuple[str, int]] = {}  # worker -> (route, steps spent on it)
        self.reassignments = 0

    # ---------- updates ----------
    def visit(self, worker: int, sid: str, obs: Observation) -> None:
        super().visit(worker, sid, obs)
        info = self.states[sid]
        self.route_url[info.route] = obs.url
        origin = urlsplit(obs.url).netloc
        for e in obs.elements:
            if e.disabled:
                continue
            self.key_states[e.key()].add(sid)
            if e.href:
                target = urljoin(obs.url, e.href)
                if urlsplit(target).netloc == origin:
                    self.links.setdefault(route_shape(target), self._path(target))

    def record(self, worker: int, sid: str, key: str, do: str | None = None, value: str | None = None) -> None:
        super().record(worker, sid, key)
        if do in ("fill", "type") and value is not None:
            self.value_classes[(sid, key)].add(value_class(value))

    # ---------- queries ----------
    def is_global(self, key: str) -> bool:
        n = len(self.states)
        return n >= self.min_states_for_global and len(self.key_states.get(key, ())) >= self.global_share * n

    def untouched(self, worker: int, sid: str) -> int:
        info = self.states.get(sid)
        if not info:
            return 0
        return sum(1 for k in info.elements
                   if not self.is_global(k) and not self.tries[(sid, k)] and not self._taken_by_other(worker, sid, k))

    def area(self, route: str) -> str:
        """Focus-area name of a route: sibling routes that differ only in their last segment
        (3 or more, below the top level, e.g. /profile/alice, /profile/bob) form one area.
        Works around the v0 state abstraction keeping alphabetic value segments apart (I11)."""
        parent, _, _ = route.rpartition("/")
        if not parent or "?" in route or "#" in route:
            return route
        siblings = {r for r in (*self.routes, *self.links) if r.rpartition("/")[0] == parent and "?" not in r}
        if len(siblings) >= 3:
            return f"{parent}/*"
        up = self.area(parent)  # sub-pages of a merged area (/profile/alice/favorites) belong to it
        return up if up.endswith("/*") else route

    def _area_routes(self, area: str) -> set[str]:
        return {r for r in (*self.routes, *self.links) if self.area(r) == area}

    def area_visited(self, area: str) -> bool:
        return any(r in self.routes for r in self._area_routes(area))

    def area_work(self, worker: int, area: str) -> int:
        """Untouched non-global elements over the area's states; an unvisited area counts as fresh work."""
        if not self.area_visited(area):
            return 5
        return sum(self.untouched(worker, sid) for sid, i in self.states.items() if self.area(i.route) == area)

    def unvisited_routes(self) -> list[str]:
        return sorted({self.area(r) for r in self.links if not self.area_visited(self.area(r))})

    def mark(self, worker: int, sid: str, el: Element) -> str:
        k = el.key()
        if self._taken_by_other(worker, sid, k):
            return "[taken]"
        if el.tag in FILLABLE and el.type not in NON_TEXT_INPUTS:
            tried = self.value_classes.get((sid, k))
            return f"[tried: {', '.join(sorted(tried))}]" if tried else ""
        n = self.tries[(sid, k)]
        if not n:
            return ""
        return "[nav]" if self.is_global(k) else f"[done x{n}]"

    def focus(self, worker: int, current: str) -> tuple[str, str] | None:
        """The worker's focus area (route, path to it), reassigned when dry or after rotate_steps."""
        cur = self.focus_of.get(worker)
        if cur:
            area, spent = cur
            dry = self.area_visited(area) and self.area_work(worker, area) <= self.dry_threshold
            if not dry and spent < self.rotate_steps:
                self.focus_of[worker] = (area, spent + 1)
                return area, self._area_path(area)
        owned = {a for w, (a, _) in self.focus_of.items() if w != worker} if self.shared else set()
        previous = cur[0] if cur else None
        areas = {self.area(r) for r in (*self.routes, *self.links)}
        candidates = [a for a in areas if a not in owned and a != previous]
        if not candidates:
            return None
        best = max(candidates, key=lambda a: (self.area_work(worker, a), not self.area_visited(a), a))
        if self.area_work(worker, best) <= self.dry_threshold and self.area_visited(best):
            self.focus_of.pop(worker, None)
            return None
        self.focus_of[worker] = (best, 1)
        self.reassignments += 1
        return best, self._area_path(best)

    def _area_path(self, area: str) -> str:
        """A concrete path into the area: the last URL seen there, else a link to it."""
        seen = [r for r in self._area_routes(area) if r in self.route_url]
        if seen:
            return self._path(self.route_url[max(seen, key=lambda r: self.routes[r])])
        return next((self.links[r] for r in sorted(self._area_routes(area)) if r in self.links), area)

    def others_focus(self, worker: int) -> list[str]:
        return [f"{r} (tester {w})" for w, (r, _) in sorted(self.focus_of.items()) if w != worker]

    def stats(self) -> dict:
        return {**super().stats(), "version": 2, "focus_reassignments": self.reassignments,
                "global_elements": sum(1 for k in self.key_states if self.is_global(k))}
