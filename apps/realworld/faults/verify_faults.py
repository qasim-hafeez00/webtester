"""Check that every seeded fault manifests when enabled and stays dormant when not.

    python -m webtester app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10
    python apps/realworld/faults/verify_faults.py --expect on
    python -m webtester app up
    python apps/realworld/faults/verify_faults.py --expect off

Each check drives the real app (API for backend faults, a browser for
frontend ones) and returns True when the faulty behaviour is observed. The
database is reset to the seeded snapshot afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:4100"
PW = "conduit-test-pw"
HERE = Path(__file__).resolve().parent


def api(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(BASE + "/api" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Token {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200].decode(errors="replace")}


def login(user: str) -> str:
    status, data = api("POST", "/users/login", {"user": {"email": f"{user}@conduit.test", "password": PW}})
    assert status == 200, (status, data)
    return data["user"]["token"]


def first_article(author: str) -> dict:
    _, data = api("GET", f"/articles?author={author}&limit=1")
    return data["articles"][0]


# ---------------- backend faults (API) ----------------
def f01() -> bool:
    tok = login("worker01")
    slug = first_article("alice")["slug"]
    status, _ = api("POST", f"/articles/{slug}/comments", {"comment": {"body": "x" * 300}}, tok)
    return status == 500


def f03() -> bool:
    tag = uuid.uuid4().hex[:8]
    status, _ = api("POST", "/users", {"user": {"username": "", "email": f"blank-{tag}@example.com", "password": "pw-12345"}})
    return status in (200, 201)


def f04() -> bool:
    tok = login("worker03")
    title = f"Tagged {uuid.uuid4().hex[:6]}"
    status, data = api("POST", "/articles", {"article": {"title": title, "description": "d", "body": "b",
                                                         "tagList": ["alpha", "beta"]}}, tok)
    assert status in (200, 201), data
    slug = data["article"]["slug"]
    status, data = api("PUT", f"/articles/{slug}", {"article": {"body": "edited", "tagList": ["alpha", "beta"]}}, tok)
    return sorted(data["article"]["tagList"]) != ["alpha", "beta"]


def f05() -> bool:
    tok = login("worker02")
    art = first_article("bob")
    before = api("GET", f"/articles/{art['slug']}", token=tok)[1]["article"]["favoritesCount"]
    _, data = api("POST", f"/articles/{art['slug']}/favorite", token=tok)
    shown = data["article"]["favoritesCount"]
    api("DELETE", f"/articles/{art['slug']}/favorite", token=tok)
    return shown != before + 1


def f06() -> bool:
    tok = login("worker01")
    slug = first_article("carol")["slug"]
    _, data = api("POST", f"/articles/{slug}/comments", {"comment": {"body": "to be deleted"}}, tok)
    cid = data["comment"]["id"]
    status, _ = api("DELETE", f"/articles/{slug}/comments/{cid}", token=tok)
    _, data = api("GET", f"/articles/{slug}/comments", token=tok)
    return status in (200, 204) and any(c["id"] == cid for c in data["comments"])


def f07_api() -> bool:
    tok = login("worker04")
    slug = first_article("dave")["slug"]
    status, _ = api("DELETE", f"/articles/{slug}", token=tok)
    return status in (200, 204)


def f08() -> bool:
    tok = login("worker05")  # follows nobody
    _, data = api("GET", "/articles/feed", token=tok)
    return data["articlesCount"] > 0


def f10() -> bool:
    _, data = api("GET", "/articles?tag=css&limit=50")
    return any("css" not in a["tagList"] for a in data["articles"])


# ---------------- frontend faults (browser) ----------------
async def ui_login(page, user: str) -> None:
    await page.goto(BASE + "/login")
    await page.get_by_placeholder("Email").fill(f"{user}@conduit.test")
    await page.get_by_placeholder("Password").fill(PW)
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_url(BASE + "/")


async def f02(browser) -> bool:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    await ui_login(page, "worker06")
    await page.goto(BASE + "/editor")
    tag = page.get_by_placeholder("Enter tags")
    await tag.fill("web dev")
    await tag.press("Enter")
    await page.wait_for_timeout(500)
    added = await page.locator(".tag-list").get_by_text("web dev").count()
    await ctx.close()
    return any("Cannot read properties of undefined" in e for e in errors) and added == 0


async def f07_ui(browser) -> bool:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await ui_login(page, "worker07")
    await page.goto(BASE + f"/article/{first_article('alice')['slug']}")
    await page.wait_for_load_state("networkidle")
    shown = await page.get_by_role("button", name="Delete Article").count()
    await ctx.close()
    return shown > 0


async def f09(browser) -> bool:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto(BASE + "/")
    await page.wait_for_load_state("networkidle")
    first = await page.locator("app-article-preview h1").first.inner_text()
    await page.locator(".pagination .page-link", has_text="2").click()
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)
    after = await page.locator("app-article-preview h1").first.inner_text()
    await ctx.close()
    return first == after


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", choices=["on", "off"], required=True)
    args = ap.parse_args()
    expect = args.expect == "on"
    results: dict[str, bool] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        results["F02"] = await f02(browser)
        results["F07(ui)"] = await f07_ui(browser)
        results["F09"] = await f09(browser)
        await browser.close()
    for name, fn in [("F01", f01), ("F03", f03), ("F04", f04), ("F05", f05), ("F06", f06),
                     ("F08", f08), ("F10", f10), ("F07(api)", f07_api)]:
        try:
            results[name] = fn()
        except Exception as e:  # noqa: BLE001
            print(f"{name}: check errored: {e}")
            results[name] = None
    subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-q", "-U", "conduit", "-d", "conduit",
                    "-c", "SELECT agentic_reset()"], cwd=HERE.parent, check=True, capture_output=True)
    ok = True
    for name in sorted(results):
        good = results[name] is expect
        ok &= good
        print(f"{name:9} manifested={results[name]!s:5}  {'OK' if good else 'UNEXPECTED'}")
    print("ALL AS EXPECTED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
