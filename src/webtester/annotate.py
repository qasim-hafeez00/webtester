"""LLM annotation of page facts (v5 plan O11; the ablation condition `b4annot`, D61).

The deterministic rules read list items from the DOM (consistency.AUDIT_JS). Where that extraction finds no
content list on a page, `b4annot` asks the LLM once per route shape and heading to name the items it lists (name,
and price, status or date when shown). The answer is added to the page facts as a list marked `annotated`, so
the same deterministic rules can arm on it; the LLM never judges anything. Answers are cached by that key for
the run and saved with it (annotations.json), and the gate's replays read the cache only, so a replay sees the
facts the run saw and costs no tokens.

Measured as an ablation: arm rate and findings of `b4annot` against `b4det` on the same apps, with the tokens
the annotations cost.
"""

from __future__ import annotations

import json
from pathlib import Path

ANNOT_PROMPT = """You extract data from a web page's visible text for an automated tester. List the items the page \
shows as a list or table (products, articles, tasks, people, rows), with what the page shows for each. Reply with \
one JSON object and nothing else:
{"lists": [{"heading": "<the list's heading or ''>", "items": [{"name": "<item name as shown>", "price": "<as shown \
or ''>", "status": "<as shown or ''>", "date": "<as shown or ''>"}]}]}
Use only text that is on the page. At most 3 lists and 40 items each. If the page lists nothing, reply {"lists": []}."""
MAX_TEXT = 6000


def to_lists(data: dict) -> list[dict]:
    """The LLM's answer as page-fact lists (consistency.Facts.lists shape), marked annotated."""
    out = []
    for L in (data or {}).get("lists") or []:
        if not isinstance(L, dict):
            continue
        items = []
        for i in (L.get("items") or [])[:40]:
            if isinstance(i, dict) and str(i.get("name", "")).strip():
                text = " ".join(str(i.get(k, "")) for k in ("name", "price", "status", "date") if i.get(k))
                items.append({"name": str(i["name"]).strip()[:120], "text": text[:300], "abs": None, "href": None})
        if items:
            out.append({"heading": str(L.get("heading") or "")[:80], "items": items, "nav": False, "annotated": True})
    return out[:3]


class Annotator:
    """Shared by the run's sweepers. `llm` None = cache only (the gate's replays)."""

    def __init__(self, llm=None, cache: dict | None = None):
        self.llm = llm
        self.cache: dict[str, list] = dict(cache or {})
        self.calls = 0
        self.tokens = 0

    async def lists_for(self, key: str, text: str) -> list[dict]:
        if key in self.cache:
            return self.cache[key]
        if self.llm is None:
            return []
        try:
            data, usage = await self.llm.complete_json(ANNOT_PROMPT, (text or "")[:MAX_TEXT])
        except Exception:  # noqa: BLE001 - an annotation that fails leaves the facts as extracted
            data, usage = {}, None
        self.calls += 1
        self.tokens += usage.total if usage is not None else 0
        self.cache[key] = to_lists(data)
        return self.cache[key]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
