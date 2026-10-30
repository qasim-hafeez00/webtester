"""Action-selection policies.

LLMPolicy  - the LLM explorer (B1 and every later LLM condition).
RandomPolicy - uniform random actions; a sanity floor and an offline smoke test
               that needs no API key.

A policy sees the current observation and the worker's memory. B1/B2 use the
Phase 1 prompt unchanged; B3 adds a view of the shared frontier, B3-local the
same view over a private frontier. That is the only difference between them,
which is what keeps the ablations clean. The B4 conditions (inferred=True) add
ORACLE_PROMPT to the system prompt and may return checks (G3, inferred.py).
"""

from __future__ import annotations

import json
import random
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .browser import Observation
from .config import Account
from .inferred import sanitize_expectations
from .llm import LLMClient, LLMError, Usage
from .state import route_shape

if TYPE_CHECKING:
    from .frontier import Frontier

MAX_ACTIONS_PER_STEP = 6
VALID_DOS = {"click", "fill", "clear", "select", "check", "uncheck", "press", "hover", "navigate", "back", "reload"}


@dataclass
class Decision:
    actions: list[dict]
    thought: str = ""
    usage: Usage | None = None
    error: str = ""
    done: bool = False
    expect: list[dict] = field(default_factory=list)  # inferred-oracle checks (B4 only)
    intent: dict | None = None  # v4: what the actions are meant to do (B4 family, D49)
    suspect: dict | None = None  # v4: a contradiction the model cites (R15, B4 only)
    page: str = ""  # v4: a 2-4 word name for a page new to the team (frontier v3)


@dataclass
class Memory:
    """What one worker remembers. Kept small so prompts stay bounded."""

    history: list[str] = field(default_factory=list)  # one line per step
    routes: Counter = field(default_factory=Counter)
    states: set = field(default_factory=set)

    def note_visit(self, url: str, state: str) -> None:
        self.routes[route_shape(url)] += 1
        self.states.add(state)

    def add(self, line: str) -> None:
        self.history.append(line)


SYSTEM_PROMPT = """You are an autonomous software tester exploring a web application to find bugs. \
There is no specification: work out what the app is for from what you see.

How to explore:
- Cover the app broadly: visit pages and features you have not seen yet (routes visited are listed).
- Exercise every form: valid input first, then invalid, empty, boundary, very long and special-character input.
- Complete whole user flows (create, view, edit, delete; follow, favorite; settings) and check the results look right.
- Use the given account to log in, or register new accounts. Stay inside this app.
- Do not repeat an action that already happened in the same state unless you are checking something specific.

Reply with ONE JSON object and nothing else:
{"thought": "<at most 25 words: what you are testing and why>",
 "actions": [{"do": "<action>", "id": "<element id>", "value": "<text>"}]}

Actions: click(id), fill(id, value), clear(id), select(id, value=option text), check(id), uncheck(id),
press(id, value=key e.g. Enter), hover(id), navigate(value=path like /settings), back, reload.
Up to 6 actions per reply, e.g. fill several fields and then click submit. Put clicks last: the page
may change after a click, and element ids are only valid for the page shown below."""

# G3: appended to SYSTEM_PROMPT for the B4 conditions only. The examples are generic
# CRUD invariants, not the seeded faults (see logs/decisions.md D27). Harness v3 (D46) asks
# for up to 3 checks from three angles and discourages guessing post-save navigation.
ORACLE_PROMPT = """

CHECKS: there is no specification, so you are also the oracle. When your actions should have a visible effect, add the optional key "expect" to your reply: a list of at most 3 checks of what MUST be true afterwards if the app works correctly. Each check is one of:
- {"check": "shows", "text": "<exact text>", "where": "now"|"reload"|"/path"}: that text is on the page
- {"check": "not_shows", "text": "<exact text>", "where": "now"|"reload"|"/path"}: that text is NOT on the page
- {"check": "count", "id": "<element id>", "delta": 1}: the number shown in that element changes by delta
- {"check": "changes"}: the page (URL or visible text) changes after your actions
- {"check": "route", "route": "/path"}: your actions end on this route (use * for an id segment)
"now" checks the current page right after your actions; "reload" opens the same URL again in a new tab (did the change persist?); "/path" opens that page in a new tab.
When your actions change data (create, edit, delete, save, toggle, follow, like, add or remove), cover three angles:
1. the immediate effect: what the page now shows, or no longer shows;
2. persistence: the same check after "reload", or on the page that lists such items;
3. numbers: if a number on the page should move (a counter, a total, a count on a button), a count check on that element.
Prefer checks on content over route checks: where an app goes after a save is its own design choice, so use a route check only for navigation you asked for (a link you clicked or a path you opened). Only state what any correct app must do, with text you typed or saw on the page. A failed check comes back to you as an error signal: it may be a bug, so investigate it."""

# Harness v4 (D49). The v3 checks above asked for predictions of each action's outcome; on
# BookStack every false alarm was a wrong guess about design (I43). v4 asks for the intent
# instead, and the harness checks its effect independently (consistency.py). INTENT_PROMPT
# goes to every v4 B4-family condition; CHECKS_PROMPT (cited contradictions, grounded
# checks) to b4 and b4nog1 only, not to b4det.
INTENT_PROMPT = """

INTENT: when your actions should change data (create, edit, delete, favourite/like/follow or undo it, add to a list or cart, log out) or search/filter, add "intent": {"verb": "create|edit|delete|favourite|unfavourite|like|unlike|follow|unfollow|add|search|filter|logout", "object": "<the item's name or title, or the search term>", "type": "<kind of item>"}. State an intent only when you expect the action to succeed (valid input). The tester then checks on its own that the effect really happened: the item exists and is listed, its fields were saved, counts moved, other pages agree. You do not need to predict wording or where the app goes.
Give items you create a distinctive name with a short code (e.g. "Atlas Q7"), so they can be found again. Good tests: create then find it again, edit then reopen it, delete then open its address, favourite then open the favourites list, search for something you created, double submit, back after submit, special characters (<b>x</b>, accents, quotes). Lines marked "Tester notes" tell you what was checked; follow up on conflicts."""

CHECKS_PROMPT = """

CONTRADICTIONS (optional): if two things you saw cannot both be true in a correct app (a count that does not match its list, one item with two names or ages, an item listed where it should not be), add "suspect": {"a": "<exact text 1>", "b": "<exact text 2>", "why": "<at most 10 words>"}, both copied exactly from pages you saw. You may also add "expect": at most 2 checks, each {"check": "shows"|"not_shows", "text": "<exact text you typed or saw>", "where": "now"|"reload"|"/path"} or {"check": "count", "id": "<element id>", "delta": 1}. Never guess headings, wording or where the app navigates."""

_LOGIN_CONTROL = re.compile(r"^(sign in|log in|login)$", re.I)


def session_line(obs: Observation) -> str:
    """Say when the worker looks logged out: workers that lost their session kept testing as a
    guest without noticing (D46). Generic tell: a visible 'Sign in' / 'Log in' control."""
    if any(_LOGIN_CONTROL.match((e.text or e.label).strip()) for e in obs.elements):
        return "Session: you appear to be logged OUT (a 'Sign in' / 'Log in' control is shown).\n"
    return ""


def build_user_prompt(obs: Observation, mem: Memory, account: Account, step: int, max_steps: int,
                      frontier: "Frontier | None" = None, worker: int = 0, sid: str = "",
                      suggestion: str | None = None, notes: list[str] | None = None) -> str:
    """Without a frontier this is the Phase 1 (B1) prompt (plus, from harness v3, the session
    line: D46). With one, the
    route list comes from the map, elements carry done/taken marks, and a
    coordination note is added (B3 shared, B3-local per worker)."""
    recent = "\n".join(mem.history[-10:]) or "(none yet)"
    text = obs.text[:1500]
    if frontier is None:
        routes = ", ".join(f"{r} (x{n})" for r, n in mem.routes.most_common(30)) or "none yet"
        els = "\n".join(e.describe() for e in obs.elements) or "(no interactive elements)"
        seen = f"Distinct page states you have seen: {len(mem.states)}. Routes visited: {routes}\n\n"
        coord = ""
    else:
        who = "your team" if frontier.shared else "you"
        compact = getattr(frontier, "version", 1) >= 3
        routes = ", ".join(f"{r} (x{n})" for r, n in frontier.routes.most_common(12 if compact else 30)) or "none yet"
        if compact:  # v4: explored navigation (marked [nav]) collapses into one line of ids and texts
            lines, nav = [], []
            for e in obs.elements:
                m = frontier.mark(worker, sid, e)
                if m == "[nav]":
                    nav.append(f"[{e.id}] {(e.text or e.label)[:24]}")
                else:
                    lines.append((e.describe() + " " + m).rstrip())
            if nav:
                lines.append("Explored navigation (on most pages): " + ", ".join(nav))
            els = "\n".join(lines)
        else:
            els = "\n".join((e.describe() + " " + frontier.mark(worker, sid, e)).rstrip() for e in obs.elements)
        els = els or "(no interactive elements)"
        seen = f"Distinct page states {who} have seen: {len(frontier.states)}. Routes visited by {who}: {routes}\n\n"
        team = ("You are one of several testers exploring this app in parallel; you share one map. "
                "[taken] = another tester is working on that element right now. ") if frontier.shared else ""
        coord = (f"COORDINATION: {team}[done xN] = {who} already exercised that element N times in this page state. "
                 "Prefer unmarked elements; only repeat to check a specific result.\n")
        if getattr(frontier, "version", 1) >= 2:
            coord = _coordination_v2(frontier, worker, who, suggestion)
        elif suggestion:
            coord += f"Least-explored area: {suggestion}. Go there if this page has nothing new left.\n"
        coord += "\n"
    naming = ""
    graph = getattr(frontier, "graph", None)
    if graph is not None and graph.unnamed(route_shape(obs.url)):
        naming = 'NEW PAGE for your team: also add "page": "<2-4 word name for this kind of page>" to your reply.\n'
    tester = ("Tester notes (your recent intents, checked independently):\n" + "\n".join(notes) + "\n\n") if notes else ""
    return (
        f"Step {step} of at most {max_steps}.\n"
        f"Test account: email={account.email} password={account.password} (username {account.username})\n"
        f"{session_line(obs)}"
        f"{seen}"
        f"{coord}"
        f"{naming}"
        f"Your recent steps:\n{recent}\n\n"
        f"{tester}"
        f"CURRENT PAGE: {route_shape(obs.url)}  (url {obs.url})  title={obs.title!r}\n"
        f"Visible text (truncated):\n{text}\n\n"
        f"Interactive elements:\n{els}\n"
    )


def _coordination_v2(frontier: "Frontier", worker: int, who: str, focus: str | None) -> str:
    """B3 v2: a focus area per worker instead of a fallback suggestion, and input-class marks."""
    lines = ["COORDINATION: "]
    if frontier.shared:
        lines[0] += "You are one of several testers exploring this app in parallel; you share one map."
    if focus:
        route, path = focus.split(" ", 1)
        lines.append(f"YOUR FOCUS AREA: {route} (navigate to {path}). Test it in depth: every form with "
                     "input classes not tried yet, every button, every flow that starts here. Leave it only to "
                     "finish a flow or when you get a new focus area.")
        others = frontier.others_focus(worker) if frontier.shared else []
        if others:
            lines.append("Other testers are covering: " + ", ".join(others) + ". Leave those areas to them.")
    unvisited = frontier.unvisited_routes()[:10]
    if unvisited:
        lines.append(f"Linked routes nobody has visited yet: {', '.join(unvisited)}.")
    lines.append(f"Marks: [done xN] = {who} already used that element N times in this page state; "
                 f"[tried: ...] = input classes {who} already typed into that field (classes: empty, whitespace, "
                 "text, long, special, number, email), so type a class not listed; "
                 "[nav] = navigation, only for moving between areas"
                 + ("; [taken] = another tester is on that element right now" if frontier.shared else "") + ".")
    return "\n".join(lines) + "\n"


def sanitize_actions(raw: object) -> list[dict]:
    out = []
    if not isinstance(raw, list):
        return out
    for a in raw:
        if len(out) >= MAX_ACTIONS_PER_STEP:
            break
        if not isinstance(a, dict):
            continue
        do = str(a.get("do") or a.get("action") or "").lower().strip()
        if not do:
            # Shorthand some models use: {"click": "11"} or {"fill": "6", "value": "x"}
            short = next((k for k in a if str(k).lower() in VALID_DOS | {"type", "goto"}), None)
            if short is not None:
                do = str(short).lower()
                a = {**a, "id": a.get("id", a[short]) if do not in ("navigate", "goto") else None,
                     "value": a.get("value", a[short] if do in ("navigate", "goto") else None)}
        if do == "type":
            do = "fill"
        if do == "goto":
            do = "navigate"
        if do not in VALID_DOS:
            continue
        eid = a.get("id", a.get("element"))
        eid = str(eid).strip("[]# ") if eid not in (None, "") else None
        value = a.get("value")
        out.append({"do": do, "id": eid, "value": None if value is None else str(value)})
    return out


SEQUENCE_EVERY = 6  # R11: one prompt in six carries the sequence goals (token cost)


class LLMPolicy:
    name = "llm"

    def __init__(self, llm: LLMClient, account: Account, max_steps: int,
                 frontier: "Frontier | None" = None, worker: int = 0, inferred: bool = False,
                 intents: bool = False, notes=None, role: str = "", profile_after: int = 0, sequences: bool = False):
        """`inferred`: the model may add checks and cited contradictions (v4: b4, b4nog1).
        `intents`: the model states intents that the harness verifies (v4 B4 family, D49).
        `notes`: callable returning the worker's memory lines for the prompt (M5)."""
        self.llm = llm
        self.account = account
        self.max_steps = max_steps
        self.frontier = frontier
        self.worker = worker
        self.inferred = inferred
        self.intents = intents
        self.notes = notes
        if intents:
            self.system_prompt = SYSTEM_PROMPT + INTENT_PROMPT + (CHECKS_PROMPT if inferred else "")
        else:
            self.system_prompt = SYSTEM_PROMPT + ORACLE_PROMPT if inferred else SYSTEM_PROMPT
        # v5 X4 (D60, condition B5): a worker role adds its paragraph to the system prompt
        from .reach import ROLE_PROMPTS

        self.role = role
        self.system_prompt += ROLE_PROMPTS.get(role, "")
        self.profile_after = profile_after  # X5: 0 = no app profile step
        self.sequences = sequences  # R11 (D61): generated action sequences as goal flows, every SEQUENCE_EVERY steps
        self.last_profile: dict | None = None
        self.last_suggestion: str | None = None
        self._prepared = False

    async def _profile(self) -> "Usage | None":
        """X5: once per run (the first worker to get there), after `profile_after` routes, the LLM names the
        app type and the primitives it saw; the profile goes on the shared frontier. It adds goal flows to
        every worker's prompt and is logged; it never switches rules off (v5 plan X5)."""
        f = self.frontier
        if not self.profile_after or f is None or getattr(f, "profile", "absent") is not None \
                or len(f.routes) < self.profile_after:
            return None
        from .families import app_types, primitives
        from .reach import PROFILE_PROMPT, parse_profile

        f.profile = {"pending": True}
        graph = getattr(f, "graph", None)
        pages = "\n".join(f"{r}: {(graph.pages[r].name or graph.pages[r].heading) if graph and r in graph.pages else ''}"
                          for r, _ in f.routes.most_common(30))
        types, prims = sorted(app_types()), sorted(primitives())
        try:
            data, usage = await self.llm.complete_json("You classify web applications. Reply with JSON only.",
                                                       PROFILE_PROMPT.format(types="; ".join(types), prims=", ".join(prims),
                                                                             pages=pages))
        except LLMError as e:
            f.profile = {"error": str(e)[:200]}
            return None
        f.profile = parse_profile(data, types, prims)
        self.last_profile = f.profile
        return usage

    def prepare(self, sid: str) -> tuple[str, str] | None:
        """Frontier v2+: work out this step's focus area once. Returns it when it is newly assigned
        (the harness may then travel there without an LLM step, v4), else None."""
        if self.frontier is None or getattr(self.frontier, "version", 1) < 2:
            return None
        prev = self.frontier.focus_of.get(self.worker)
        focus = self.frontier.focus(self.worker, sid)
        self.last_suggestion = f"{focus[0]} {focus[1]}" if focus else None
        self._prepared = True
        return focus if focus is not None and (prev is None or prev[0] != focus[0]) else None

    async def decide(self, obs: Observation, mem: Memory, step: int, sid: str = "") -> Decision:
        if self._prepared:
            self._prepared = False
        elif self.frontier is not None and getattr(self.frontier, "version", 1) >= 2:
            focus = self.frontier.focus(self.worker, sid)
            self.last_suggestion = f"{focus[0]} {focus[1]}" if focus else None
        else:
            self.last_suggestion = self.frontier.suggest(self.worker, sid) if self.frontier else None
        prof_usage = await self._profile()
        prompt = build_user_prompt(obs, mem, self.account, step, self.max_steps, self.frontier, self.worker, sid,
                                   self.last_suggestion, self.notes() if self.notes else None)
        prof = getattr(self.frontier, "profile", None)
        if prof and prof.get("primitives"):
            from .reach import goal_lines, rank_primitives

            goals = goal_lines(rank_primitives(prof["primitives"], getattr(self.frontier, "checks", None)))
            if goals:
                prompt += "\nGoal flows for this kind of app (" + prof["app_type"] + "):\n- " + "\n- ".join(goals) + "\n"
        if self.sequences and step % SEQUENCE_EVERY == 0:
            from .reach import sequence_goals

            seq = sequence_goals(getattr(self.frontier, "graph", None))
            if seq:
                prompt += "\nOrder-dependent checks worth one try now:\n- " + "\n- ".join(seq) + "\n"
        try:
            data, usage = await self.llm.complete_json(self.system_prompt, prompt)
        except LLMError as e:
            return Decision([], error=str(e)[:300], usage=prof_usage)
        if prof_usage is not None:
            usage.add(prof_usage)
        actions = sanitize_actions(data.get("actions"))
        if not actions and isinstance(data.get("action"), dict):
            actions = sanitize_actions([data["action"]])
        if not actions:
            actions = sanitize_actions([data])  # a bare single action object
        err = "" if actions else "no valid action in reply: " + json.dumps(data, ensure_ascii=False)[:400]
        expect = sanitize_expectations(data.get("expect")) if self.inferred and actions else []
        intent = sanitize_intent(data.get("intent")) if self.intents and actions else None
        suspect = data.get("suspect") if self.inferred and isinstance(data.get("suspect"), dict) else None
        page = str(data.get("page"))[:40] if isinstance(data.get("page"), str) else ""
        return Decision(actions, str(data.get("thought", ""))[:300], usage, err, expect=expect, intent=intent,
                        suspect=suspect, page=page)


def sanitize_intent(raw: object) -> dict | None:
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict) or not raw.get("verb"):
        return None
    return {"verb": str(raw.get("verb"))[:20], "object": str(raw.get("object") or "")[:120],
            "type": str(raw.get("type") or "")[:40]}


class RandomPolicy:
    name = "random"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def random_value(self, typ: str) -> str:
        r = self.rng
        word = "".join(r.choices(string.ascii_lowercase, k=r.randint(3, 10)))
        return {
            "email": f"{word}@example.com",
            "password": word + "A1!",
            "number": str(r.randint(-5, 1000)),
            "url": f"https://example.com/{word}",
        }.get(typ, r.choice([word, f"{word} {word}", "", " ", "<b>x</b>", word * 30]))

    async def decide(self, obs: Observation, mem: Memory, step: int, sid: str = "") -> Decision:
        r = self.rng
        usable = [e for e in obs.elements if not e.disabled]
        if not usable or r.random() < 0.05:
            return Decision([{"do": "back", "id": None, "value": None}], "random back")
        e = r.choice(usable)
        if e.tag in ("input", "textarea") and e.type not in ("checkbox", "radio", "submit", "button"):
            return Decision([{"do": "fill", "id": e.id, "value": self.random_value(e.type)}], "random fill")
        if e.tag == "select" and e.options:
            return Decision([{"do": "select", "id": e.id, "value": r.choice(e.options)}], "random select")
        return Decision([{"do": "click", "id": e.id, "value": None}], "random click")
