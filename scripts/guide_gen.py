"""Refill the generated parts of docs/project_guide.md from the code and the logs.

The guide marks each generated block as
    <!-- gen:start NAME -->
    ...
    <!-- gen:end -->
and this script replaces the text between the markers; everything else in the guide is left as it is.

Blocks:
- modules:  one table row per module of src/webtester (lines, purpose)
- code:     per module, every class and function: signature, line, what it does, callers
- cli:      `webtester --help` for every subcommand
- faults:   the seeded fault catalogues of both apps
- decisions, issues: one line per D- and I-entry from logs/
- registry: counted runs per app, condition and label
- literature: the paper list from literature/papers.json

What a function does comes from its docstring, or else from docs/code_notes.toml
("module.Class.func" = "text"). Functions with neither are listed at the end of the run, so a new
function gets a note when the guide is next refreshed.
Usage: python scripts/guide_gen.py [--check]   (--check: report missing notes, write nothing)
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "webtester"
GUIDE = ROOT / "docs" / "project_guide.md"
NOTES = ROOT / "docs" / "code_notes.toml"
PY = sys.executable


def first_line(doc: str | None) -> str:
    return " ".join((doc or "").strip().split("\n\n")[0].split())


def signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in fn.args.posonlyargs + fn.args.args if a.arg not in ("self", "cls")]
    if fn.args.vararg:
        args.append("*" + fn.args.vararg.arg)
    args += [a.arg for a in fn.args.kwonlyargs]
    if fn.args.kwarg:
        args.append("**" + fn.args.kwarg.arg)
    return f"{'async ' if isinstance(fn, ast.AsyncFunctionDef) else ''}{fn.name}({', '.join(args)})"


def parse_modules() -> dict[str, dict]:
    mods = {}
    for f in sorted(PKG.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        items = []  # (qualname, kind, signature, line, docstring)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                items.append((node.name, "function", signature(node), node.lineno, ast.get_docstring(node)))
            elif isinstance(node, ast.ClassDef):
                items.append((node.name, "class", node.name, node.lineno, ast.get_docstring(node)))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        items.append((f"{node.name}.{sub.name}", "method", signature(sub), sub.lineno,
                                      ast.get_docstring(sub)))
        mods[f.stem] = {"lines": src.count("\n") + 1, "doc": ast.get_docstring(tree), "items": items, "src": src}
    return mods


def callers(mods: dict[str, dict]) -> dict[str, set[str]]:
    """Which modules mention each function or class name (a name match, good enough for a reader's map)."""
    names = defaultdict(set)
    for m, info in mods.items():
        for q, kind, *_ in info["items"]:
            names[q.split(".")[-1]].add(m)
    used = defaultdict(set)
    for m, info in mods.items():
        words = set(re.findall(r"\b[A-Za-z_]\w*\b", info["src"]))
        for name in names:
            if name in words and not name.startswith("__"):
                used[name].add(m)
    return used


def block_modules(mods) -> str:
    rows = ["| Module | Lines | Purpose |", "|---|---:|---|"]
    for m, info in mods.items():
        if m.startswith("__"):
            continue
        rows.append(f"| [`{m}.py`](../src/webtester/{m}.py) | {info['lines']} | {first_line(info['doc'])} |")
    return "\n".join(rows)


def block_code(mods, notes, missing) -> str:
    used = callers(mods)
    out = []
    for m, info in mods.items():
        if m.startswith("__") or not info["items"]:
            continue
        out.append(f"#### `{m}.py`\n")
        out.append(first_line(info["doc"]) + "\n")
        out.append("| Name | Line | What it does | Used in |")
        out.append("|---|---:|---|---|")
        for q, kind, sig, line, doc in info["items"]:
            key = f"{m}.{q}"
            what = notes.get(key) or first_line(doc)
            if not what:
                missing.append(key)
                what = "*(no note yet)*"
            short = q.split(".")[-1]
            others = sorted(x for x in used.get(short, ()) if x != m)
            shown = sig if kind != "class" else f"class {q}"
            if kind == "method":
                shown = q.split(".")[0] + "." + sig
            link = f"[{line}](../src/webtester/{m}.py#L{line})"
            out.append(f"| `{shown}` | {link} | {what.replace('|', '/')} | {', '.join(others) or '-'} |")
        out.append("")
    return "\n".join(out)


def block_cli() -> str:
    out = []
    top = subprocess.run([PY, "-m", "webtester", "--help"], cwd=ROOT, capture_output=True, text=True).stdout
    subs = re.search(r"\{([\w,-]+)\}", top).group(1).split(",")
    for s in subs:
        h = subprocess.run([PY, "-m", "webtester", s, "--help"], cwd=ROOT, capture_output=True, text=True).stdout
        out.append(f"<details><summary><code>webtester {s}</code></summary>\n\n```text\n{h.strip()}\n```\n</details>\n")
    return "\n".join(out)


def block_faults() -> str:
    out = []
    for app, path in (("Conduit", "apps/realworld/faults/faults.toml"), ("BookStack", "apps/bookstack/faults/faults.toml")):
        p = ROOT / path
        if not p.exists():
            continue
        cat = tomllib.loads(p.read_text(encoding="utf-8"))
        rows = cat.get("fault", [])
        keys = [k for k in ("id", "class", "layer", "summary", "effect", "trigger", "reachable") if any(k in r for r in rows)]
        out.append(f"**{app}** ([`{path}`](../{path}), {len(rows)} faults)\n")
        out.append("| " + " | ".join(keys) + " |")
        out.append("|" + "---|" * len(keys))
        for r in rows:
            out.append("| " + " | ".join(" ".join(str(r.get(k, "")).split())[:220].replace("|", "/") for k in keys) + " |")
        out.append("")
    return "\n".join(out)


def block_log_index(path: str, prefix: str) -> str:
    rows = [f"| {prefix} | Date | Summary |", "|---|---|---|"]
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        m = re.match(rf"\| ({prefix}\d+) \| ([^|]+) \| (.+?) \|", line)
        if not m:
            continue
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(3))
        text = text.split(". ")[0][:200].replace("|", "/")
        rows.append(f"| {m.group(1)} | {m.group(2).strip()} | {text} |")
    return "\n".join(rows)


def block_registry() -> str:
    reg = (ROOT / "logs/experiments/run_registry.md").read_text(encoding="utf-8")
    cols = ("valid", "unreviewed", "invalid", "pilot", "smoke")
    counts = defaultdict(lambda: dict.fromkeys(cols, 0))
    for line in reg.splitlines():
        m = re.match(r"\| `\d{8}-\d{6}_(\w+?)_(\w+?)_n(\d+)_?([\w-]*)` \| (\w+) \|", line)
        if not m:
            continue
        app, agent, n, label, status = m.groups()
        label = re.sub(r"(rep|pilot)\d+$", r"\1", label) or "(none)"  # g1rep3 -> g1rep: one batch
        counts[(app, label, agent, int(n))][status if status in cols else "smoke"] += 1
    rows = ["| App | Label | Condition | Workers | " + " | ".join(c.capitalize() for c in cols) + " |",
            "|---|---|---|---:|" + "---:|" * len(cols)]
    for (app, label, agent, n), c in sorted(counts.items()):
        rows.append(f"| {app} | `{label}` | `{agent}` | {n} | " + " | ".join(str(c[k]) for k in cols) + " |")
    return "\n".join(rows)


def block_literature() -> str:
    p = ROOT / "literature/papers.json"
    if not p.exists():
        return ""
    papers = json.loads(p.read_text(encoding="utf-8"))
    papers = list(papers.values()) if isinstance(papers, dict) else papers
    papers.sort(key=lambda x: (str(x.get("tier", "")), str(x.get("cat", ""))))
    rows = ["| Tier | Topic | Paper | Venue, year | Gaps | Why it matters to us |", "|---|---|---|---|---|---|"]
    for x in papers:
        title = " ".join(str(x.get("title") or x.get("query_title") or "").split())
        venue = x.get("venue_override") or x.get("venue") or x.get("rank") or ""
        rows.append(f"| {x.get('tier', '')} | {x.get('cat', '')} | {title} | {venue}, {x.get('year', '')} | "
                    f"{x.get('gaps', '')} | {' '.join(str(x.get('why', '')).split()).replace('|', '/')} |")
    return "\n".join(rows)


def main() -> None:
    check = "--check" in sys.argv
    notes = tomllib.loads(NOTES.read_text(encoding="utf-8")) if NOTES.exists() else {}
    notes = {k: v for k, v in notes.items() if isinstance(v, str)}
    mods = parse_modules()
    missing: list[str] = []
    blocks = {"modules": block_modules(mods), "code": block_code(mods, notes, missing)}
    if check:
        print(f"{len(missing)} names without a docstring or note")
        print("\n".join(missing))
        return
    blocks.update(cli=block_cli(), faults=block_faults(),
                  decisions=block_log_index("logs/decisions.md", "D"), issues=block_log_index("logs/issues.md", "I"),
                  registry=block_registry(), literature=block_literature())
    text = GUIDE.read_text(encoding="utf-8")
    for name, body in blocks.items():
        # the body may be empty, and the match never runs into another block's markers
        pat = re.compile(rf"(<!-- gen:start {name} -->\n)(?:(?!<!-- gen:).)*?(<!-- gen:end -->)", re.S)
        text, n = pat.subn(lambda m: m.group(1) + body.rstrip("\n") + "\n" + m.group(2), text)
        if not n:
            print(f"note: no gen block '{name}' in the guide")
    GUIDE.write_text(text, encoding="utf-8")
    print(f"guide refreshed; {len(missing)} names without a note: {', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''}")


if __name__ == "__main__":
    main()
