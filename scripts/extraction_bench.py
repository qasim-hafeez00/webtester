"""O6 d (D60): fact-level precision and recall of the page extraction (consistency.AUDIT_JS) on hand-labelled
pages in tests/extraction/ (format in its README). Usage: python scripts/extraction_bench.py [--verbose]"""

import asyncio
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from webtester.consistency import AUDIT_JS, Facts  # noqa: E402
from webtester.memory import norm  # noqa: E402

D = ROOT / "tests/extraction"


def facts_sets(f: Facts) -> dict[str, set]:
    return {"h1": {norm(f.h1)} if f.h1 else set(),
            "list_heading": {norm(L["heading"]) for L in f.content_lists() if L.get("heading")},
            "list_item": {(norm(L.get("heading") or ""), norm(i["name"])) for L in f.content_lists() for i in L["items"] if i["name"]},
            "count": {(c["n"], norm(c["unit"]).rstrip("s")) for c in f.counts if not c.get("nav")},
            "total": {(norm(t["label"]), norm(t["value"])) for t in f.totals}}


def label_sets(lab: dict) -> dict[str, set]:
    return {"h1": {norm(lab["h1"])} if lab.get("h1") else set(),
            "list_heading": {norm(L["heading"]) for L in lab.get("list", [])},
            "list_item": {(norm(L["heading"]), norm(i)) for L in lab.get("list", []) for i in L["items"]},
            "count": {(c["n"], norm(c["unit"]).rstrip("s")) for c in lab.get("count", [])},
            "total": {(norm(t["label"]), norm(t["value"])) for t in lab.get("total", [])}}


async def main(verbose: bool) -> None:
    from playwright.async_api import async_playwright

    tp, fp, fn = Counter(), Counter(), Counter()
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        page = await b.new_page()
        for html in sorted(D.glob("*.html")):
            lab_path = html.with_suffix(".toml")
            if not lab_path.exists():
                continue
            await page.set_content(html.read_text(encoding="utf-8"))
            got = facts_sets(Facts.of(await page.evaluate(AUDIT_JS, []), "http://bench/"))
            want = label_sets(tomllib.loads(lab_path.read_text(encoding="utf-8")))
            for k in want:
                tp[k] += len(got[k] & want[k])
                fp[k] += len(got[k] - want[k])
                fn[k] += len(want[k] - got[k])
                if verbose and (got[k] ^ want[k]):
                    print(f"{html.name} {k}: extra {sorted(got[k] - want[k])[:4]} missing {sorted(want[k] - got[k])[:4]}")
        await b.close()
    print("| Fact | Precision | Recall | Labelled |")
    print("|---|---:|---:|---:|")
    for k in ("h1", "list_heading", "list_item", "count", "total"):
        p = tp[k] / (tp[k] + fp[k]) if tp[k] + fp[k] else None
        r = tp[k] / (tp[k] + fn[k]) if tp[k] + fn[k] else None
        print(f"| {k} | {'-' if p is None else f'{p:.0%}'} | {'-' if r is None else f'{r:.0%}'} | {tp[k] + fn[k]} |")


if __name__ == "__main__":
    asyncio.run(main("--verbose" in sys.argv))
