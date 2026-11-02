"""I97 (2 Nov): rules for the BookStack faults the v5 pilots reached but no rule reported, faulty and clean.

  - a favourite button in a box of its own: the event names the page's item, not 'Favourite', so R07 can
    look for it in 'My Favourites' (BS01's shape),
  - an item this worker opened a moment ago is missing from 'My Recently Viewed' (R22h; BS02 and BS03's shape).
R19's undo click (Conduit F05's shape) is tested in test_d62_rules.py.
"""

from __future__ import annotations

import threading

import pytest

from test_d62_rules import Base, html, sweep

NAMES = {1: "Annual report", 2: "Budget memo", 3: "Coffee rota", 4: "Design notes"}


class HistoryApp:
    def __init__(self, faulty: bool):
        self.faulty = faulty
        self.views = [4, 3, 1]  # newest first
        self.favs: list[int] = [1, 4]
        self.lock = threading.Lock()

    def handler(self):
        app = self

        class H(Base):
            def do_GET(self):
                path = self.path.split("?")[0]
                with app.lock:
                    if path == "/":
                        shown = [i for i in app.views if not (app.faulty and i == 2)]
                        items = "".join(f"<li><a href='/items/{i}'>{NAMES[i]}</a></li>" for i in shown)
                        links = "".join(f"<li><a href='/items/{i}'>{NAMES[i]}</a></li>" for i in NAMES)
                        self.send(200, html("Dashboard", f"<h1>Dashboard</h1><nav><a href='/favourites'>Favourites</a>"
                                            f"</nav><h2>My Recently Viewed</h2><ul>{items}</ul>"
                                            f"<h2>All items</h2><ul>{links}</ul>"))
                    elif path == "/favourites":
                        shown = [i for i in app.favs if not (app.faulty and i == 3)]
                        items = "".join(f"<li><a href='/items/{i}'>{NAMES[i]}</a></li>" for i in shown)
                        self.send(200, html("Favourites", f"<h1>My Favourites</h1><ul>{items}</ul>"))
                    elif path.startswith("/items/") and path[7:].isdigit() and int(path[7:]) in NAMES:
                        i = int(path[7:])
                        app.views = [i] + [v for v in app.views if v != i]
                        label = "Unfavourite" if i in app.favs else "Favourite"
                        self.send(200, html(NAMES[i], f"<h1>{NAMES[i]}</h1><p>Text of {NAMES[i]}.</p>"
                                            f"<div class=actions><form method=post action='/items/{i}/fav'>"
                                            f"<button type=submit>{label}</button></form></div>"))
                    else:
                        self.send(404, html("Not found", "<h1>Not found</h1>"))

            def do_POST(self):
                self.body()
                path = self.path.split("?")[0]
                with app.lock:
                    if path.startswith("/items/") and path.endswith("/fav"):
                        i = int(path.split("/")[2])
                        app.favs = [v for v in app.favs if v != i] if i in app.favs else app.favs + [i]
                        self.send(303, location=f"/items/{i}")
                    else:
                        self.send(404, html("Not found", "<h1>Not found</h1>"))

        return H


PLAN = [("/", [], None), ("", [], "Budget memo"), ("/items/3", [], None), ("", [], "Favourite"),
        ("/favourites", [], None), ("/", [], None)]


@pytest.mark.parametrize("faulty", [True, False])
def test_i97_favourite_and_recently_viewed(faulty):
    sigs, st, _ = sweep(HistoryApp(faulty), PLAN)
    msgs = [x.message for x in sigs]
    r07 = [m for m in msgs if "[R07 " in m]
    r22h = [m for m in msgs if "[R22h " in m]
    armed = {r["rule"] for r in st.checks.records() if r["outcome"] in ("exercised", "detected")}
    assert {"R07", "R22h"} <= armed, sorted(armed)
    assert not any("'Favourite' was" in m for m in msgs), msgs
    if faulty:
        assert any("'Coffee rota' was favourited" in m for m in r07), msgs
        assert any("'Budget memo' was opened" in m for m in r22h), msgs
    else:
        assert not r07 and not r22h, msgs
