"""Snapshot BookStack pages with every injected fault on, as static fixtures for tests/test_v5.py.

Needs BookStack running (`python -m webtester --config configs/bookstack.toml app up`); run from the
repo root: python tests/fixtures/make_bookstack_fixtures.py. The tests derive the clean variants.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from playwright.async_api import async_playwright  # noqa: E402

from webtester.config import REPO_ROOT  # noqa: E402

FAULTS = [f"BS{i:02d}" for i in range(1, 19)]
PAGES = {"profile": "/user/admin", "search": "/search?term=book", "book": "/books/book1",
         "page": "/books/book/page/page-template", "dashboard": "/"}
STRIP = """() => { const c = document.body.cloneNode(true);
  c.querySelectorAll('script, style, svg, noscript, link, meta, template, iframe').forEach(e => e.remove());
  return '<html><body>' + c.innerHTML + '</body></html>'; }"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        await ctx.add_init_script(script=f"window.__WT_FAULTS__ = {json.dumps(FAULTS)};")
        await ctx.add_init_script(path=str(REPO_ROOT / "apps/bookstack/faults/injected.js"))
        pg = await ctx.new_page()
        await pg.goto("http://127.0.0.1:4200/login")
        await pg.fill("input[name=email]", "worker01@bookstack.test")
        await pg.fill("input[name=password]", "password")
        await pg.press("input[name=password]", "Enter")
        await pg.wait_for_load_state("networkidle")
        for name, u in PAGES.items():
            await pg.goto("http://127.0.0.1:4200" + u)
            await pg.wait_for_load_state("networkidle")
            await asyncio.sleep(1.5)
            html = re.sub(r"\s+", " ", await pg.evaluate(STRIP)).replace("http://127.0.0.1:4200", "")
            Path(f"tests/fixtures/bookstack_{name}_faulty.html").write_text(html, encoding="utf-8")
            print(name, len(html), {k: html.count(k) for k in ("1 year ago", "2 days ago", "15 hours ago", "custom-id", '"999"')})
        await b.close()


asyncio.run(main())
