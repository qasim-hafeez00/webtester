"""Implicit oracles: turn raw browser signals into deduplicated candidate findings.

These are the spec-free signals every condition gets (crash-style failures).
Inferred semantic oracles (G3, inferred.py) feed `oracle_violation` signals into
the same store, and the reproduce-before-report gate (G2, gate.py) labels every
candidate collected here.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .browser import Signal
from .state import route_shape

_NUM = re.compile(r"\b\d+\b")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_QUOTED = re.compile(r"(['\"]).*?\1")


def normalise_message(msg: str) -> str:
    msg = _HEX.sub("<h>", msg)
    msg = _NUM.sub("<n>", msg)
    msg = _QUOTED.sub("<s>", msg)
    return msg[:160]


def signature(sig: Signal) -> str:
    if sig.kind in ("oracle_violation", "consistency"):  # v4: consistency|rule|route shape|subject (D49)
        return sig.detail["sig"]
    if sig.kind == "http_5xx":
        method = sig.detail.get("method", "")
        return f"http_5xx|{method} {route_shape(sig.detail.get('url', ''))}|{sig.detail.get('status')}"
    if sig.kind == "request_failed":
        return f"request_failed|{route_shape(sig.detail.get('url', ''))}"
    return f"{sig.kind}|{normalise_message(sig.message)}"


@dataclass
class Finding:
    sig: str
    kind: str
    message: str
    first_step: int
    worker: int
    page_url: str
    state: str
    trail: list[dict]  # the actions leading up to the first occurrence
    occurrences: int = 1
    detail: dict = field(default_factory=dict)
    status: str = "candidate"  # candidate | confirmed | flaky | rejected | unverified (set by the gate, G2)
    gate: dict = field(default_factory=dict)  # replay outcomes (G2)
    judge: dict | None = None  # LLM second opinion on a reproduced oracle violation (G2)
    exposed: list[str] = field(default_factory=list)  # injected faults this worker had triggered so far

    def to_dict(self) -> dict:
        return asdict(self)


class FindingStore:
    def __init__(self, exclude: tuple | set = ()):
        self.by_sig: dict[str, Finding] = {}
        self.exclude = set(exclude)  # D62: rules left out of a locked version's report
        self.withheld: dict[str, Finding] = {}

    def ingest(self, signals: list[Signal], *, step: int, worker: int, state: str, trail: list[dict],
               exposed: list[str] | None = None) -> list[Finding]:
        """Returns the findings that are new in this batch (findings of excluded rules are kept apart, never
        returned, gated or reported)."""
        new = []
        for s in signals:
            key = signature(s)
            held = ((s.detail or {}).get("rule") or s.kind) in self.exclude
            store = self.withheld if held else self.by_sig
            f = store.get(key)
            if f:
                f.occurrences += 1
                continue
            f = Finding(key, s.kind, s.message, step, worker, s.url, state, trail[-8:], detail=s.detail,
                        exposed=list(exposed or []))
            store[key] = f
            if not held:
                new.append(f)
        return new

    def all(self) -> list[Finding]:
        return list(self.by_sig.values())
