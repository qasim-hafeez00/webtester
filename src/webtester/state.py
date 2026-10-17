"""Canonical abstract-state identity (v0).

state_id = hash(route shape, structural skeleton)

* Route shape: path segments that look like values (contain digits, '-', '_',
  '@', '.', '%', or are long) become '*'; query keys are kept, values dropped;
  the fragment is kept only when it looks like a client-side route ('#/...').
* Skeleton: visible DOM structure without text or attributes, with
  identical sibling subtrees merged (computed in the page, see browser.py).
  Logged-in and logged-out pages differ in their navigation bars, so the
  session role is reflected without app-specific knowledge.

Known v0 limitation (documented for the paper): value-like segments without
those characters (e.g. '/profile/alice' vs '/profile/bob') stay distinct.
Experiment metrics recompute states offline with one fixed abstraction for
every condition, so changing this module never changes how conditions compare.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlsplit

_VALUE_LIKE = re.compile(r"[\d\-_@.%]")


def route_shape(url: str) -> str:
    u = urlsplit(url)
    segs = []
    for seg in u.path.split("/"):
        if not seg:
            continue
        segs.append("*" if _VALUE_LIKE.search(seg) or len(seg) > 24 else seg)
    shape = "/" + "/".join(segs)
    if u.query:
        keys = sorted({k for k, _ in parse_qsl(u.query, keep_blank_values=True)})
        shape += "?" + "&".join(keys)
    if u.fragment.startswith("/"):
        shape += "#" + route_shape(u.fragment)
    return shape


def skeleton_hash(skeleton: str) -> str:
    return hashlib.sha1(skeleton.encode("utf-8")).hexdigest()[:10]


def state_id(url: str, skeleton: str) -> str:
    return hashlib.sha1(f"{route_shape(url)}|{skeleton}".encode("utf-8")).hexdigest()[:12]


def action_key(state: str, do: str, element_key: str | None, value: str | None = None) -> str:
    """Identity of 'doing X in state S'. Fill values are bucketed by class, not text,
    so typing two different strings into the same field counts as the same action
    for the duplicate-action metric."""
    vclass = ""
    if do in ("fill", "type") and value is not None:
        vclass = value_class(value)
    elif do in ("select", "press", "navigate", "goto"):
        vclass = (value or "")[:60]
    return f"{state}|{do}|{element_key or ''}|{vclass}"


def value_class(v: str) -> str:
    if v == "":
        return "empty"
    if v.strip() == "":
        return "whitespace"
    if "@" in v and "." in v.split("@")[-1]:
        return "email"
    if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
        return "number"
    if re.search(r"[<>\"'`;]|script", v, re.I):
        return "special"
    if len(v) > 200:
        return "long"
    return "text"
