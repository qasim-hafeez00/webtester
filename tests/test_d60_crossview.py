"""D60: faulty and clean cases for the passive cross-view rules not covered in test_d60_rules.py."""

from __future__ import annotations

from webtester.browser import Element
from webtester.config import AppConfig
from webtester.consistency import Facts, SweepState, Sweeper
from webtester.crossview import CrossView


def rules(vs):
    return sorted({v.rule for v in vs})


class _Obs:
    def __init__(self, url, elements=()):
        self.url, self.elements = url, list(elements)

    def element(self, eid):
        return next((e for e in self.elements if e.id == eid), None)


def _sw():
    st = SweepState()
    acct = AppConfig(name="t", base_url="http://h", account_template={"username": "w{i}", "email": "w{i}@t",
                                                                       "password": "p"}).account(1)
    sw = Sweeper(st, 1, acct)
    sw.writes, sw.pre, sw.last, sw.pages = [], {}, None, [("/", "")]
    return st, sw, CrossView(st.cross)


def F(url, h1="", lists=(), text="", counts=(), totals=(), tables=(), showing=None):
    return Facts(url, h1=h1, text=text or h1, plain=text or h1, lists=list(lists), counts=list(counts),
                 totals=list(totals), tables=list(tables), showing=showing)


def L(heading, names, base="http://h/i/"):
    return {"heading": heading, "nav": False, "items": [{"name": n, "text": n, "abs": f"{base}{k}", "href": f"/i/{k}"}
                                                        for k, n in enumerate(names)]}


def ev(sw, **kw):
    return sw.mem.add_event(worker=1, **kw)


def test_r20d_declared_price():
    st, sw, cv = _sw()
    raw = {"jsonld": [{"@type": "Product", "name": "Lamp", "offers": {"price": "30.00"}}]}
    assert "R20d" in rules(cv.check(sw, F("http://h/p/1", h1="Lamp", text="Lamp Price $25.00"), raw, _Obs("http://h/p/1"), [], None, 1))
    raw["jsonld"][0]["offers"]["price"] = "25.00"
    assert "R20d" not in rules(cv.check(sw, F("http://h/p/1", h1="Lamp", text="Lamp Price $25.00"), raw, _Obs("http://h/p/1"), [], None, 2))


def test_r21a_prefill():
    st, sw, cv = _sw()
    sw.mem.entity("/books/atlas").names["Atlas Q7"] = (1, 1, "http://h/books/atlas")
    raw = {"fields": [{"label": "Name", "name": "name", "type": "text", "value": "Something else"}]}
    assert "R21a" in rules(cv.check(sw, F("http://h/books/atlas/edit"), raw, _Obs("http://h/books/atlas/edit"), [], None, 5))
    raw["fields"][0]["value"] = "Atlas Q7"
    assert "R21a" not in rules(cv.check(sw, F("http://h/books/atlas/edit"), raw, _Obs("http://h/books/atlas/edit"), [], None, 6))


def test_r47_badge_counts_more_than_listed():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/"), {"nav": [{"text": "Inbox", "href": "http://h/inbox", "badge": 5}]}, _Obs("http://h/"), [], None, 1)
    out = cv.check(sw, F("http://h/inbox", lists=[L("Messages", ["a", "b"])]), {}, _Obs("http://h/inbox"), [], None, 2)
    assert "R47" in rules(out)


def test_r31_referenced_control():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/a"), {}, _Obs("http://h/a", [Element(id="1", tag="button", text="Save Draft")]), [], None, 1)
    out = cv.check(sw, F("http://h/b", text='Click "Save Draft" to keep your work'), {"controls": ["Publish"]},
                   _Obs("http://h/b"), [], None, 2)
    assert "R31" in rules(out)
    out = cv.check(sw, F("http://h/c", text='Click "Save Draft" to keep your work'), {"controls": ["Save Draft"]},
                   _Obs("http://h/c"), [], None, 3)
    assert "R31" not in rules(out)


def test_r73_history_ledger():
    st, sw, cv = _sw()
    for s, name in ((1, "Atlas Q7"), (3, "Borealis Z2")):
        e = ev(sw, step=s, verb="create", obj=name, written=True)
        e.status = "verified"
    out = cv.check(sw, F("http://h/audit", text="Audit log: w1 created Atlas Q7"), {}, _Obs("http://h/audit"), [], None, 6)
    assert "R73" in rules(out)


def test_r68_follow_count_and_self_follow():
    st, sw, cv = _sw()
    cnt = lambda n: [{"n": n, "unit": "followers", "text": f"{n} followers"}]  # noqa: E731
    cv.check(sw, F("http://h/profile/bob", counts=cnt(4)), {}, _Obs("http://h/profile/bob"), [], None, 1)
    e = ev(sw, step=2, verb="follow", obj="bob", written=True)
    out = cv.check(sw, F("http://h/profile/bob", counts=cnt(4)), {}, _Obs("http://h/profile/bob"), [], e, 2)
    assert "R68" in rules(out)
    e2 = ev(sw, step=3, verb="follow", obj="w1", written=True)
    out = cv.check(sw, F("http://h/profile/w1"), {}, _Obs("http://h/profile/w1"), [], e2, 3)
    assert any(v.subject == "self" for v in out)


def test_r22_collection_page_missing_item():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/"), {"nav": [{"text": "Cart", "href": "http://h/cart", "badge": 0}]}, _Obs("http://h/"), [], None, 1)
    ev(sw, step=2, verb="add", obj="Gamma Lamp", written=True)
    out = cv.check(sw, F("http://h/cart", text="Your cart is empty"), {}, _Obs("http://h/cart"), [], None, 3)
    assert "R22" in rules(out)


def test_r34_status_unchanged_after_approve():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/req/1"), {"status": ["pending"]}, _Obs("http://h/req/1"), [], None, 1)
    sw.writes = [{"method": "POST", "path": "/req/1/approve", "status": 200}]
    done = [{"do": "click", "el": '[3] button "Approve"', "ok": True}]
    out = cv.check(sw, F("http://h/req/1"), {"status": ["pending"]}, _Obs("http://h/req/1"), done, None, 2)
    assert "R34" in rules(out)


def test_r35_capacity():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/events/5", text="Concert 3 seats left"), {}, _Obs("http://h/events/5"), [], None, 1)
    e = ev(sw, step=2, verb="add", obj="Concert", url="http://h/events/5", written=True, fields={"Tickets": "1"})
    out = cv.check(sw, F("http://h/events/5", text="Concert 3 seats left"), {}, _Obs("http://h/events/5"), [], e, 2)
    assert "R35" in rules(out)


def test_r32_transfer_conservation():
    st, sw, cv = _sw()
    tab = lambda a, b: [{"head": ["Account", "Balance"], "rows": [["Checking", a], ["Savings", b]]}]  # noqa: E731
    cv.check(sw, F("http://h/accounts", tables=tab("100.00", "50.00")), {}, _Obs("http://h/accounts"), [], None, 1)
    e = ev(sw, step=2, verb="create", obj="", url="http://h/transfer", written=True,
           fields={"Amount": "20", "From account": "Checking", "To account": "Savings"})
    cv.check(sw, F("http://h/transfer/done"), {}, _Obs("http://h/transfer"), [{"do": "click", "el": "Transfer"}], e, 2)
    out = cv.check(sw, F("http://h/accounts", tables=tab("80.00", "50.00")), {}, _Obs("http://h/accounts"), [], None, 3)
    assert "R32" in rules(out)


def test_r70_funnel_ledger():
    st, sw, cv = _sw()
    sw.writes = [{"method": "POST", "path": "/checkout/1", "status": 200}]
    d1 = [{"do": "fill", "value": "Sunflower Street 12", "el": '[1] input label="Address"'}]
    cv.check(sw, F("http://h/checkout/shipping"), {}, _Obs("http://h/checkout/address"), d1, None, 1)
    d2 = [{"do": "fill", "value": "Express courier", "el": '[2] input label="Delivery"'}]
    cv.check(sw, F("http://h/checkout/review"), {}, _Obs("http://h/checkout/shipping"), d2, None, 2)
    out = cv.check(sw, F("http://h/checkout/confirm", h1="Order confirmation", text="Order confirmation Express courier"),
                   {}, _Obs("http://h/checkout/review"), [], None, 3)
    assert "R70" in rules(out)


def test_r30_unexpected_login_page():
    st, sw, cv = _sw()
    sw.pages = [("/books", "Books")]
    out = cv.check(sw, F("http://h/login"), {}, _Obs("http://h/books"), [{"do": "click", "el": '[4] a "Atlas"'}], None, 2)
    assert "R30" in rules(out)
    out = cv.check(sw, F("http://h/login"), {}, _Obs("http://h/books"), [{"do": "click", "el": '[4] a "Log out"'}], None, 3)
    assert "R30" not in rules(out)


def test_r55_bulk_ledger():
    st, sw, cv = _sw()
    sw.writes = [{"method": "POST", "path": "/bulk", "status": 200}]
    sw.bulk_before = {"selected": ["Alpha"], "others": ["Beta", "Gamma"], "delete": True}
    out = cv.check(sw, F("http://h/list", text="Alpha\nGamma\n2 items deleted"), {}, _Obs("http://h/list"), [], None, 2)
    assert {v.subject for v in out if v.rule == "R55"} == {"kept-selected", "removed-unselected", "count"}


def test_r56_route_parity():
    st, sw, cv = _sw()
    e1 = ev(sw, step=1, verb="create", obj="A1", written=True, fields={"Title": "A1", "Notes": "keep me"})
    cv.check(sw, F("http://h/items/1", text="A1 keep me"), {}, _Obs("http://h/items/new"), [], e1, 1)
    e2 = ev(sw, step=2, verb="create", obj="B2", written=True, fields={"Title": "B2", "Notes": "lost note"})
    out = cv.check(sw, F("http://h/items/2", text="B2"), {}, _Obs("http://h/quick-add"), [], e2, 2)
    assert "R56" in rules(out)


def test_r58_clone_children():
    st, sw, cv = _sw()
    sw.last = F("http://h/books/a", lists=[L("Chapters", ["c1", "c2", "c3", "c4"])])
    sw.writes = [{"method": "POST", "path": "/books/a/copy", "status": 200}]
    out = cv.check(sw, F("http://h/books/a-copy", lists=[L("Chapters", ["c1"])]), {}, _Obs("http://h/books/a"),
                   [{"do": "click", "el": '[9] button "Copy"'}], None, 2)
    assert "R58" in rules(out)


def test_r69_cart_quantity_zero():
    st, sw, cv = _sw()
    sw.writes = [{"method": "POST", "path": "/cart", "status": 200}]
    done = [{"do": "fill", "value": "0", "el": '[2] input label="Quantity"'}]
    raw = {"fields": [{"label": "Quantity", "name": "qty", "type": "number", "value": "0"}]}
    assert "R69" in rules(cv.check(sw, F("http://h/cart"), raw, _Obs("http://h/cart"), done, None, 2))


def test_r20_stale_name_after_edit():
    st, sw, cv = _sw()
    e = ev(sw, step=1, verb="edit", obj="New Name", target="/books/x", written=True, url="http://h/books/x/edit",
           fields={'Name value="Old Name"': "New Name"})
    e.status = "verified"
    out = cv.check(sw, F("http://h/books", lists=[{"heading": "Books", "nav": False, "items": [
        {"name": "Old Name", "text": "Old Name", "abs": "http://h/books/x", "href": "/books/x"}]}]), {},
        _Obs("http://h/books"), [], None, 4)
    assert any(v.rule == "R20" and v.subject.startswith("stale") for v in out)


def test_clean_pages_raise_nothing():
    st, sw, cv = _sw()
    pages = [F("http://h/", lists=[L("Books", ["One Book", "Two Book"])], text="Books One Book Two Book"),
             F("http://h/i/0", h1="One Book", text="One Book"),
             F("http://h/i/1", h1="Two Book", text="Two Book")]
    out = []
    for i, f in enumerate(pages, 1):
        out += cv.check(sw, f, {"status": []}, _Obs(f.url), [], None, i)
    assert out == []
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
