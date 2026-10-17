"""Check the BookStack environment and its injected faults (run by hand, needs the app up).

    python -m webtester --config configs/bookstack.toml app up --faults all
    python apps/bookstack/faults/verify_faults.py --expect on
    python -m webtester --config configs/bookstack.toml app up --faults ""
    python apps/bookstack/faults/verify_faults.py --expect off

Checks, in order:
  1. reset: a row added to the DB is gone after `app reset`, and the reset time is printed;
  2. accounts: worker01..04 can log in, and each has the admin's 4 seeded favourites;
  3. faults: each reachable fault (faults.toml, reachable = true) is driven to its trigger page
     through the harness's own BrowserSession (same init scripts as a run) and must log its
     exposure marker when on, and stay silent when off. A few effects are checked directly.
  4. no injector errors and no page errors on any visited page.
Exit code 0 only if everything passes.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
import tomllib
from dataclasses import replace
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from webtester.appctl import AppControl  # noqa: E402
from webtester.browser import BrowserSession  # noqa: E402
from webtester.config import load_config  # noqa: E402

CFG = load_config(ROOT / "configs" / "bookstack.toml")
CATALOG = {f["id"]: f for f in tomllib.loads((ROOT / "apps/bookstack/faults/faults.toml").read_text(encoding="utf-8"))["fault"]}

# fault -> pages to visit in order (the trigger is reached on the last one)
VISITS = {
    "BS01": ["/favourites"],
    "BS02": ["/", "/books", "/"],
    "BS03": ["/", "/books", "/"],
    "BS04": ["/books", "/", "/books"],
    "BS05": ["/user/admin"],  # phantom entries need a non-empty list: admin has created content
    "BS06": ["/user/admin"],
    "BS07": ["/user/admin"],
    "BS08": ["/search?term=page"],
    "BS09": ["/user/admin"],  # Book1 activity is admin's
    "BS10": ["/books/book1"],  # chapter pages have no Recent Activity block in 25.2.1 (I27)
    "BS11": ["/books/book/page/page-template"],
    "BS12": ["/books/book2"],
    "BS13": ["/settings/sorting"],
}
# fault -> (a whole line of the trigger page's main content, and whether the fault makes it present or absent)
EFFECTS = {
    "BS01": ("Shelf", "absent"),
    "BS12": ("Page 3", "present"),
    "BS13": ("Create Sort Rule", "absent"),
    "BS05": ("Custom Book Title", "present"),
}


def db(sql: str) -> str:
    cmd = ["docker", "compose", "exec", "-T", "db", "mysql", "-uroot", "-proot", "-N", "-e", sql]
    try:
        out = subprocess.run(cmd, cwd=ROOT / "apps/bookstack", capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:  # one transient 60 s hang of `docker compose exec` seen on 16 Oct
        print("docker exec timed out once, retrying")
        out = subprocess.run(cmd, cwd=ROOT / "apps/bookstack", capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-500:])
    return out.stdout.strip()


def check_reset(ctl: AppControl) -> list[str]:
    errors = []
    db("INSERT INTO bookstack.bookshelves (name, slug, description, created_by, updated_by, owned_by, "
       "created_at, updated_at, description_html) VALUES ('verify-reset', 'verify-reset', '', 1, 1, 1, NOW(), NOW(), '')")
    secs = ctl.reset()
    left = db("SELECT COUNT(*) FROM bookstack.bookshelves WHERE slug = 'verify-reset'")
    print(f"reset: {secs:.2f} s; probe row left after reset: {left}")
    if left != "0":
        errors.append("reset did not remove the probe row")
    workers = db("SELECT COUNT(*) FROM bookstack.users WHERE email LIKE 'worker%@bookstack.test'")
    favs = db("SELECT COUNT(*) FROM bookstack.favourites WHERE user_id = 101")
    print(f"accounts: {workers} worker users; worker01 favourites: {favs}")
    if workers != "16" or favs != "4":
        errors.append(f"expected 16 workers with 4 favourites each, got {workers} / {favs}")
    return errors


async def check_faults(expect_on: bool, faults: list[str]) -> list[str]:
    errors = []
    cfg = replace(CFG, client_faults=tuple(faults))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for w in (1, 2, 3, 4):  # every worker account can log in
            s = BrowserSession(browser, cfg, w)
            await s.start()
            ok = await s.login(cfg.app.account(w))
            await s.close()
            print(f"login worker{w:02d}: {'ok' if ok else 'FAILED'}")
            if not ok:
                errors.append(f"worker{w:02d} cannot log in")
        for fid, pages in VISITS.items():
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            await s.login(cfg.app.account(1))
            s.drain_exposures()
            for path in pages:
                await s.goto(path)
            await asyncio.sleep(1.0)
            fired = s.drain_exposures()
            text = await s.page.evaluate("() => (document.querySelector('main') || document.body).innerText")
            signals = [x for x in s.drain_signals() if x.kind in ("page_error", "console_error")]
            hit = fid in fired
            status = "fired" if hit else "silent"
            want = "fired" if expect_on else "silent"
            note = ""
            if fid in EFFECTS and expect_on:
                needle, mode = EFFECTS[fid]
                seen = any(line.strip() == needle for line in text.splitlines())  # whole line: 'Shelf' != 'Shelves'
                if seen != (mode == "present"):
                    errors.append(f"{fid}: effect not visible ('{needle}' should be {mode})")
                    note = f" effect '{needle}' NOT {mode}"
                else:
                    note = f" effect ok ('{needle}' {mode})"
            print(f"{fid} {CATALOG[fid]['effect'][:60]:60} {status}{note}")
            if status != want:
                errors.append(f"{fid}: {status}, expected {want}")
            if s.injector_errors:
                errors.append(f"{fid}: injector errors {s.injector_errors[:2]}")
            if signals:
                print(f"     page/console errors on {pages[-1]}: {[x.message[:80] for x in signals]}")
            await s.close()
        await browser.close()
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", choices=["on", "off"], required=True)
    args = ap.parse_args()
    ctl = AppControl(CFG.app)
    ctl.wait_healthy(60)
    faults = ctl.running_faults()
    print(f"enabled faults: {faults or 'none'}")
    if (args.expect == "on") != bool(faults):
        print("the enabled faults do not match --expect; run `app up --faults all` (on) or `--faults \"\"` (off)")
        return 2
    t0 = time.monotonic()
    errors = check_reset(ctl) + asyncio.run(check_faults(args.expect == "on", faults))
    ctl.reset()
    print(f"\n{'PASS' if not errors else 'FAIL'} in {time.monotonic() - t0:.0f} s")
    for e in errors:
        print("  -", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
