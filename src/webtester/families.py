"""Fault families as data (v5 plan sections 7 and 12, D59), read from `docs/fault_families.md`.

The markdown file stays the one specification; this module parses it so code can use it:

  - `families()`      every family row of section 3: id, name, evidence, rules named, status, dev faults
  - `primitives()`    section 4: workflow primitive -> its families
  - `app_types()`     section 4: app type -> primitives rated central (●) or present (○)
  - `fault_families_of()`  seeded fault id -> the families whose 'Dev faults' cell names it
  - `rule_packs(...)` the app-profile step's mapper: an app type (or a set of primitives) -> the rules to
                      run. NAV and the implicit signals are always on; the packs of the app's primitives add
                      theirs. The live LLM classification that picks the app type is phase 2 (v5 plan P1).
  - `tracker()`       the implementation view per family (built, wave, tier), written by
                      `python -m webtester families --write` to `docs/family_tracker.toml`

'Built' is read from the code (the tier table in consistency.py and the implicit signal kinds), never
typed by hand, so a family cannot look implemented before its rule exists.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

DOC = REPO_ROOT / "docs" / "fault_families.md"
STATUSES = ("covered", "partial", "coverable", "spec", "out")
# statuses a spec-free check can see: the denominator of oracle-conditioned recall (v5 plan section 1)
OBSERVABLE = ("covered", "partial", "coverable")

# rules named in the 'Our rules' cells; implicit signals are named in words
_RULE = re.compile(r"\b(R\d{2}[a-z]?|I-(?:create|edit|delete|toggle|logout|filter|submit|error)|G[1-3])\b")
_IMPLICIT = {"HTTP 5xx signal": "http_5xx", "JS error signal": "page_error", "network failure signals": "request_failed"}
_FAULT = re.compile(r"\b(F|BS)(\d{2})(?:\s*-\s*(?:F|BS)?(\d{2}))?\b")
_FAMILY_ID = re.compile(r"\b([A-Z]{2})(\d{1,2})(?:\s*-\s*(?:[A-Z]{2})?(\d{1,2}))?\b")

# Wave of each rule that is not built yet (v5 plan section 12.2). A rule named in a family row but absent
# here is scheduled in the wave of its mechanism's last row; 'ext' marks extensions of built rules.
WAVES = {
    # W1: high-yield, armable on the development apps now
    "R20": "W1", "R21a": "W1", "R21b": "W1", "R23": "W1", "R24": "W1", "R43": "W1", "R62": "W1", "R63": "W1",
    "R68": "W1", "R64": "W1", "R53": "W1", "R73": "W1",
    # W2: need input profiles (R1) and seeding (R2)
    "R22": "W2", "R25": "W2", "R26": "W2", "R27": "W2", "R29": "W2", "R12b": "W2", "R30": "W2", "R31": "W2",
    "R38": "W2", "R39": "W2", "R44": "W2", "R49": "W2", "R50": "W2", "R52": "W2", "R54": "W2", "R55": "W2",
    "R56": "W2", "R58": "W2", "R59": "W2", "R61": "W2", "R71": "W2",
    # W3: need ledger, lifecycle, capacity, scheduling, tree, aggregate data (Parabank, Timeoff, shop)
    "R32": "W3", "R33": "W3", "R34": "W3", "R35": "W3", "R36": "W3", "R37": "W3", "R40": "W3", "R41": "W3",
    "R42": "W3", "R45": "W3", "R47": "W3", "R48": "W3", "R69": "W3", "R70": "W3", "R72": "W3",
    # W4: need a second session (M7), controlled mode (M11, M13), geometry and media (M14)
    "R28": "W4", "R46": "W4", "R60": "W4", "R65": "W4", "R66": "W4", "R67": "W4", "R74": "W4", "R75": "W4",
}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _expand_faults(cell: str) -> list[str]:
    out = []
    for pre, a, b in _FAULT.findall(cell):
        lo, hi = int(a), int(b) if b else int(a)
        out += [f"{pre}{i:02d}" for i in range(lo, hi + 1)]
    return out


def _expand_families(cell: str, known: set[str]) -> list[str]:
    out = []
    for pre, a, b in _FAMILY_ID.findall(cell):
        lo, hi = int(a), int(b) if b else int(a)
        out += [f"{pre}{i}" for i in range(lo, hi + 1) if f"{pre}{i}" in known]
    return out


@lru_cache(maxsize=4)
def _parse(path: Path = DOC) -> tuple[dict, dict, dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    fams: dict[str, dict] = {}
    group = ""
    for ln in lines:
        m = re.match(r"^### (3\.\d+) (.+)$", ln)
        if m:
            group = f"{m.group(1)} {m.group(2)}"
            continue
        if not ln.startswith("| ") or not group.startswith("3."):
            continue
        c = _cells(ln)
        if len(c) < 4 or not re.fullmatch(r"[A-Z]{2}\d{1,2}", c[0]):
            continue
        if len(c) >= 7:  # ID | Family | Sources | Evidence | Our rules | Status | Dev faults
            status_cell, rules_cell, evidence, dev = c[-2], c[-3], c[-4], c[-1]
        else:  # 3.12: ID | Family | Sources | 'status: rules and reason' in one cell
            status_cell, rules_cell, evidence, dev = c[3], c[3], "", ""
        status = next((s for s in STATUSES if status_cell.lower().startswith(s)), "")
        rules = sorted(set(_RULE.findall(rules_cell)))
        implicit = sorted({k for w, k in _IMPLICIT.items() if w in rules_cell})
        fams[c[0]] = {"id": c[0], "group": group, "name": c[1], "evidence": evidence, "rules_text": rules_cell,
                      "rules": rules, "implicit": implicit, "status": status, "status_text": status_cell[:80],
                      "dev_faults": _expand_faults(dev)}
    known = set(fams)
    prims: dict[str, list[str]] = {}
    types: dict[str, dict[str, str]] = {}
    head: list[str] = []
    for ln in lines:
        if not ln.startswith("|"):
            head = []
            continue
        c = _cells(ln)
        m = re.fullmatch(r"\*\*P-([A-Z]+)\*\*", c[0])
        if m and len(c) == 3:
            prims[m.group(1)] = _expand_families(c[2], known)
            continue
        if c[:2] == ["App type", "Apps (plan or literature)"]:
            head = c
            continue
        if head and len(c) == len(head) and not set(c[0]) <= {"-"}:
            types[c[0]] = {head[i]: c[i] for i in range(3, len(head)) if c[i] in ("●", "○")}
    return fams, prims, types


def families() -> dict[str, dict]:
    return _parse()[0]


def primitives() -> dict[str, list[str]]:
    return _parse()[1]


def app_types() -> dict[str, dict[str, str]]:
    return _parse()[2]


def fault_families_of() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in families().values():
        for fid in f["dev_faults"]:
            out.setdefault(fid, []).append(f["id"])
    return out


# D61: every 'Rxx extension' / 'variant' phrase a checkable row names, and the rule id that implements it. A
# family counts as built only when each phrase in its row is listed here AND its id exists (built_rules), so an
# extension can never look done because its base rule exists (the D60 tracker's blind spot).
EXTENSIONS = {
    "PR4": {"R01 extension": "R01x"}, "PR9": {"R01 extension": "R01x", "R02 extension": "R02h"},
    "NV8": {"R02 extension": "R43"}, "NV11": {"R10 extension": "R10x"}, "FM3": {"R16 variant": "R16i"},
    "FM8": {"R12b extension": "R12c"}, "FM11": {"I-edit extension": "R21s"}, "DB4": {"I-delete extension": "R09d"},
    "DB9": {"I-edit/I-delete extension": "R09r"}, "DB12": {"R49 extension": "R49a"}, "DV3": {"R06 extension": "R06s"},
    "SF7": {"I-filter extension": "R38"}, "SF8": {"R23 variant": "R23m"}, "SA8": {"R24 extension": "R24b"},
    "CT5": {"R22 extension": "R22g"}, "WF6": {"R52 extension": "R52f"}, "TM6": {"R36 extension": "R36p"},
    "TM7": {"R36 extension": "R36r"}, "HI5": {"R40 extension": "R40c"}, "AG3": {"R06 extension": "R06c"},
    "AR2": {"R02 extension": "R02d"}, "AR5": {"R37 extension": "R37i"}, "RC4": {"R29 variant": "R29k"},
    "RC9": {"R48 extension": "R48c"}, "UQ1": {"R20 extension": "R20u"}, "UQ2": {"R16 variant": "R16u"},
    "UQ3": {"R12b extension": "R12c"}, "PX4": {"R22 extension": "R22v"},
}
_EXT = re.compile(r"(R\d{2}[a-z]?|I-edit/I-delete|I-[a-z]+)\**\s+(extension|variant)", re.I)


def extension_phrases(fid: str) -> list[str]:
    """The extension / variant phrases a family row names ('R16 variant', 'I-delete extension')."""
    text = families()[fid].get("rules_text", "")
    return sorted({f"{m.group(1)} {m.group(2).lower()}" for m in _EXT.finditer(text)})


def built_rules() -> set[str]:
    """Rules that exist in the code now: the consistency tier table plus the implicit signal kinds."""
    from .consistency import TIER

    return set(TIER) | set(_IMPLICIT.values())


def family_rules(fid: str) -> list[str]:
    f = families()[fid]
    return f["rules"] + f["implicit"]


def rule_packs(app_type: str | None = None, prims: set[str] | None = None, present: bool = True) -> dict:
    """The app-profile mapper (v5 plan P1). `app_type` as in section 4's table, or `prims` directly.
    `present`: include primitives rated ○ as well as ●. Returns the primitives, their families and the
    rules to run (built ones in `rules`, the rest in `missing`, so a profile shows what it cannot check)."""
    if prims is None:
        rated = app_types().get(app_type or "", {})
        prims = {p for p, r in rated.items() if r == "●" or (present and r == "○")}
    prims = set(prims) | {"NAV"}  # navigation and implicit signals apply to every app
    fams = sorted({f for p in prims for f in primitives().get(p, [])})
    rules = sorted({r for f in fams for r in family_rules(f)} | set(_IMPLICIT.values()))
    have = built_rules()
    return {"primitives": sorted(prims), "families": fams, "rules": [r for r in rules if r in have],
            "missing": [r for r in rules if r not in have]}


def tracker() -> list[dict]:
    """One entry per family: specification status and implementation status, derived, not typed."""
    have = built_rules()
    prim_of: dict[str, list[str]] = {}
    for p, fs in primitives().items():
        for f in fs:
            prim_of.setdefault(f, []).append(p)
    rows = []
    for f in families().values():
        rules = family_rules(f["id"])
        built = [r for r in rules if r in have]
        todo = [r for r in rules if r not in have]
        ext = {ph: EXTENSIONS.get(f["id"], {}).get(ph) for ph in extension_phrases(f["id"])}
        todo += [f"{ph} (no rule)" for ph, rid in ext.items() if rid is None or rid not in have]
        waves = sorted({WAVES.get(r, "ext" if re.sub(r"[a-z]$", "", r) in have else "unscheduled") for r in todo})
        rows.append({"id": f["id"], "name": f["name"][:90], "group": f["group"], "status": f["status"],
                     "primitives": sorted(prim_of.get(f["id"], [])), "rules": rules, "built": built, "todo": todo,
                     "waves": waves, "dev_faults": f["dev_faults"], "extensions": {k: v or "" for k, v in ext.items()},
                     "impl": ("n/a" if f["status"] in ("spec", "out") else "built" if rules and not todo
                              else "part" if built else "none")})
    return rows


def tracker_toml(rows: list[dict]) -> str:
    def q(x: str) -> str:  # a TOML basic string (D62: a family name with a backslash made the file unreadable)
        return '"' + x.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34)) + '"'

    def arr(xs: list[str]) -> str:
        return "[" + ", ".join(q(x) for x in xs) + "]"

    out = ["# Family tracker (v5 plan section 7, D59): generated by `python -m webtester families --write` from",
           "# docs/fault_families.md and the code. Do not edit by hand. `impl`: built (every rule named exists, and",
           "# every extension the row names maps to an existing rule id in families.EXTENSIONS, D61),",
           "# part (some), none, n/a (spec or out). Measured recall/precision per family come from",
           "# `python -m webtester evaluate` and are added per lock, not here.", ""]
    for r in rows:
        out += [f"[family.{r['id']}]", f"name = {q(r['name'])}", f'status = "{r["status"]}"',
                f'impl = "{r["impl"]}"', f"primitives = {arr(r['primitives'])}", f"rules = {arr(r['rules'])}",
                f"built = {arr(r['built'])}", f"todo = {arr(r['todo'])}", f"waves = {arr(r['waves'])}",
                f"dev_faults = {arr(r['dev_faults'])}",
                "extensions = {" + ", ".join(f"{q(k)} = {q(v)}" for k, v in r.get("extensions", {}).items()) + "}", ""]
    return "\n".join(out)


def tally(rows: list[dict]) -> dict:
    from collections import Counter

    return {"families": len(rows), "by_status": dict(Counter(r["status"] for r in rows)),
            "by_impl": dict(Counter(r["impl"] for r in rows)),
            "rules_todo": sorted({x for r in rows for x in r["todo"]}),
            "by_wave": dict(Counter(WAVES.get(x, "ext/unscheduled") for x in {x for r in rows for x in r["todo"]}))}
