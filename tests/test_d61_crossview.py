"""D61: faulty and clean cases for the cross-view extensions (crossview.py, D61 block), one short trail each."""

from __future__ import annotations

from webtester.browser import Element
from webtester.config import AppConfig
from webtester.consistency import Facts, SweepState, Sweeper
from webtester.crossview import CrossView, datetimes, message_fidelity


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


def F(url, h1="", lists=(), text="", title="", totals=(), plain=None):
    return Facts(url, title=title, h1=h1, text=text or h1, plain=plain if plain is not None else (text or h1),
                 lists=list(lists), totals=list(totals))


def L(heading, names, base="http://h/i/", texts=None, ids=None):
    texts, ids = texts or names, ids or range(len(names))
    return {"heading": heading, "nav": False, "items": [{"name": n, "text": t, "abs": f"{base}{k}", "href": f"/i/{k}"}
                                                        for k, n, t in zip(ids, names, texts)]}


def ev(sw, **kw):
    return sw.mem.add_event(worker=1, **kw)


def ok(sw):
    sw.writes = [{"method": "POST", "path": "/x", "status": 200}]


def test_datetimes_reads_date_and_time():
    assert datetimes("Gig 2025-05-01 18:30, then 2025-05-02") == [(datetimes("2025-05-01")[0][0], 18 * 60 + 30),
                                                                    (datetimes("2025-05-02")[0][0], None)]


def test_r20t_time_shifted_on_its_own_page():
    for shown, want in (("20:00", True), ("18:00", False)):
        st, sw, cv = _sw()
        cv.check(sw, F("http://h/events", lists=[L("Events", ["Gig"], "http://h/events/", ["Gig 2025-05-01 18:00"])]), {},
                 _Obs("http://h/events"), [], None, 1)
        out = cv.check(sw, F("http://h/events/0", h1="Gig", text=f"Gig 2025-05-01 {shown}"), {}, _Obs("http://h/events/0"),
                       [], None, 2)
        assert ("R20t" in rules(out)) is want, out


def test_r20u_identifier_and_address():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/orders/1", h1="Order one", text="Order one Order #1234"), {}, _Obs("http://h/orders/1"), [], None, 1)
    out = cv.check(sw, F("http://h/orders/2", h1="Order two", text="Order two Order #1234"), {}, _Obs("http://h/orders/2"),
                   [], None, 2)
    assert any(v.rule == "R20u" and v.subject.startswith("ident") for v in out)
    out = cv.check(sw, F("http://h/orders/1", h1="Order three"), {}, _Obs("http://h/orders/1"), [], None, 3)
    assert any(v.rule == "R20u" and v.subject.startswith("address") for v in out)
    # a deleted item answers 'Not found' at its old address: not another item (the I61 false alarm)
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/orders/1", h1="Order one"), {}, _Obs("http://h/orders/1"), [], None, 1)
    assert "R20u" not in rules(cv.check(sw, F("http://h/orders/1", h1="Not found"), {}, _Obs("http://h/orders/1"), [], None, 2))


def test_r21s_saved_choice_shown_as_another():
    for shown, want in (("Low", True), ("High", False)):
        st, sw, cv = _sw()
        ok(sw)
        done = [{"do": "select", "value": "High", "el": '[3] select label="Priority"'}]
        cv.check(sw, F("http://h/items/1"), {}, _Obs("http://h/items/1/edit"), done, None, 1)
        sw.writes = []
        raw = {"fields": [{"label": "Priority", "name": "p", "type": "select", "value": shown}]}
        out = cv.check(sw, F("http://h/items/1/edit"), raw, _Obs("http://h/items/1/edit"), [], None, 3)
        assert ("R21s" in rules(out)) is want, out


def test_r09d_collateral_and_r09r_wrong_row():
    st, sw, cv = _sw()
    sw.last = F("http://h/list", lists=[L("Books", ["Alpha", "Beta", "Gamma"])])
    e = ev(sw, step=2, verb="delete", obj="Alpha", written=True)
    out = cv.check(sw, F("http://h/list", lists=[L("Books", ["Gamma"])]), {}, _Obs("http://h/list"), [], e, 2)
    assert "R09d" in rules(out)
    st, sw, cv = _sw()
    sw.last = F("http://h/list", lists=[L("Books", ["Alpha", "Beta", "Gamma"])])
    sw.row_name = "Alpha"
    e = ev(sw, step=2, verb="delete", obj="", written=True)
    out = cv.check(sw, F("http://h/list", lists=[L("Books", ["Alpha", "Gamma"])]), {}, _Obs("http://h/list"), [], e, 2)
    assert "R09r" in rules(out)
    st, sw, cv = _sw()
    sw.last = F("http://h/list", lists=[L("Books", ["Alpha", "Beta", "Gamma"])])
    sw.row_name = "Alpha"
    e = ev(sw, step=2, verb="delete", obj="Alpha", written=True)
    out = cv.check(sw, F("http://h/list", lists=[L("Books", ["Beta", "Gamma"])]), {}, _Obs("http://h/list"), [], e, 2)
    assert not {"R09d", "R09r"} & set(rules(out)), out


def test_r49a_archived_item_still_active():
    for listed, want in ((["Atlas", "Borealis"], True), (["Borealis"], False)):
        st, sw, cv = _sw()
        sw.last = F("http://h/books/7", h1="Atlas")
        ok(sw)
        cv.check(sw, F("http://h/books/7", h1="Atlas"), {}, _Obs("http://h/books/7"),
                 [{"do": "click", "el": '[5] button "Archive"'}], None, 1)
        sw.writes, sw.last = [], None
        out = cv.check(sw, F("http://h/books", lists=[L("Books", listed, "http://h/books/")]), {}, _Obs("http://h/books"),
                       [], None, 2)
        assert ("R49a" in rules(out)) is want, out


def test_r22v_variant_missing_from_the_cart_line():
    for line, want in (("Lamp × 1", True), ("Lamp (XL) × 1", False)):
        st, sw, cv = _sw()
        e = ev(sw, step=1, verb="add", obj="Lamp", written=True)
        cv.check(sw, F("http://h/p/1", h1="Lamp"), {}, _Obs("http://h/p/1"),
                 [{"do": "select", "value": "XL", "el": '[2] select label="Size"'}], e, 1)
        out = cv.check(sw, F("http://h/cart", lists=[L("Cart", ["Lamp"], texts=[line])]), {}, _Obs("http://h/cart"), [], None, 2)
        assert ("R22v" in rules(out)) is want, out


def test_r22g_guest_items_lost_after_logging_in():
    st, sw, cv = _sw()
    guest = {"nav": [{"text": "Log in", "href": "http://h/login"}]}
    member = {"nav": [{"text": "Log out", "href": "http://h/logout"}]}
    e = ev(sw, step=1, verb="add", obj="Lamp", written=True)
    cv.check(sw, F("http://h/p/1", h1="Lamp"), guest, _Obs("http://h/p/1"), [], e, 1)
    cv.check(sw, F("http://h/"), member, _Obs("http://h/"), [], None, 2)
    out = cv.check(sw, F("http://h/cart", text="Your cart is empty"), member, _Obs("http://h/cart"), [], None, 3)
    assert "R22g" in rules(out)


def test_r34c_write_accepted_on_a_closed_item():
    for prev, want in ((["closed"], True), (["open"], False)):
        st, sw, cv = _sw()
        sw.last = F("http://h/orders/7", h1="Order 7", text="Order 7 closed. This order cannot be edited.")
        sw.prev5 = {"status": prev}
        sw.writes = [{"method": "POST", "path": "/orders/7/edit", "status": 200}]
        out = cv.check(sw, F("http://h/orders/7", h1="Order 7"), {}, _Obs("http://h/orders/7"), [], None, 2)
        assert ("R34c" in rules(out)) is want, out


def test_r34_one_item_under_two_status_tabs():
    for second, want in ((["T1", "T2"], True), (["T2"], False)):
        st, sw, cv = _sw()
        cv.check(sw, F("http://h/tickets?status=open", lists=[L("Tickets", ["T1", "T3"], "http://h/tickets/", ids=[1, 3])]), {},
                 _Obs("http://h/tickets?status=open"), [], None, 1)
        out = cv.check(sw, F("http://h/tickets?status=closed", lists=[L("Tickets", second, "http://h/tickets/", ids=[int(n[1]) for n in second])]), {},
                       _Obs("http://h/tickets?status=closed"), [], None, 2)
        assert (any(v.subject.startswith("two-tabs") for v in out)) is want, out


def test_r36b_double_booking():
    for second, want in (("2025-01-01", True), ("2025-01-02", False)):
        st, sw, cv = _sw()
        ev(sw, step=1, verb="create", obj="", url="http://h/book/new", written=True, fields={"Date": "2025-01-01", "Room": "A"})
        cv.check(sw, F("http://h/bookings"), {}, _Obs("http://h/book/new"), [], None, 1)
        ev(sw, step=2, verb="create", obj="", url="http://h/book/new", written=True, fields={"Date": second, "Room": "A"})
        out = cv.check(sw, F("http://h/bookings"), {}, _Obs("http://h/book/new"), [], None, 2)
        assert ("R36b" in rules(out)) is want, out


def test_r38_date_range_filter():
    u = "http://h/orders?from=2025-01-01&to=2025-01-31"
    for d, want in (("2025-03-05", True), ("2025-01-15", False)):
        st, sw, cv = _sw()
        out = cv.check(sw, F(u, lists=[L("Orders", ["Order A"], texts=[f"Order A {d}"])]), {}, _Obs(u), [], None, 1)
        assert ("R38" in rules(out)) is want, out


def test_r67f_listed_but_forbidden():
    for h1, want in (("403 Forbidden", True), ("Report", False)):
        st, sw, cv = _sw()
        sw.last = F("http://h/docs", lists=[L("Docs", ["Report"], "http://h/docs/")])
        out = cv.check(sw, F("http://h/docs/0", h1=h1), {}, _Obs("http://h/docs"), [{"do": "click", "el": '[4] a "Report"'}],
                       None, 2)
        assert ("R67f" in rules(out)) is want, out


def test_r68t_item_missing_from_its_tag_page():
    for listed, want in ((["Other"], True), (["Trip", "Other"], False)):
        st, sw, cv = _sw()
        e = ev(sw, step=1, verb="create", obj="Trip", written=True, fields={"Tags": "travel"})
        cv.check(sw, F("http://h/i/9", h1="Trip"), {}, _Obs("http://h/new"), [], e, 1)
        out = cv.check(sw, F("http://h/tags/travel", lists=[L("Tagged", listed)]), {}, _Obs("http://h/tags/travel"), [], None, 3)
        assert ("R68t" in rules(out)) is want, out


def test_r48u_redo_after_undo():
    for after, want in ((["a"], True), (["a", "b"], False)):
        st, sw, cv = _sw()
        u = "http://h/list"
        cv.check(sw, F(u, lists=[L("Items", ["a", "b"])]), {}, _Obs(u), [{"do": "click", "el": '[1] button "Delete"'}], None, 1)
        cv.check(sw, F(u, lists=[L("Items", ["a", "b", "c"])]), {}, _Obs(u), [{"do": "click", "el": '[2] button "Undo"'}], None, 2)
        out = cv.check(sw, F(u, lists=[L("Items", after)]), {}, _Obs(u), [{"do": "click", "el": '[3] button "Redo"'}], None, 3)
        assert ("R48u" in rules(out)) is want, out


def test_r29k_advertised_key_did_nothing():
    for same, want in ((True, True), (False, False)):
        st, sw, cv = _sw()
        sw.last = F("http://h/list", text="Inbox")
        sw.prev5 = {"kbd": ["N"]}
        sw.pre_text, sw.post_text, sw.step_requests = "Inbox", "Inbox" if same else "New message", 0
        out = cv.check(sw, F("http://h/list", text="Inbox"), {}, _Obs("http://h/list"), [{"do": "press", "value": "n"}], None, 2)
        assert ("R29k" in rules(out)) is want, out


def test_r47r_opened_notification_still_unread():
    for n, want in ((3, True), (2, False)):
        st, sw, cv = _sw()
        cv.check(sw, F("http://h/notifications"), {"unread": 3}, _Obs("http://h/notifications"), [], None, 1)
        cv.check(sw, F("http://h/notifications/1", h1="Hi"), {}, _Obs("http://h/notifications"),
                 [{"do": "click", "el": '[2] a "Hi"'}], None, 2)
        out = cv.check(sw, F("http://h/notifications"), {"unread": n}, _Obs("http://h/notifications/1"), [], None, 3)
        assert ("R47r" in rules(out)) is want, out


def test_r74_shuffle_keeps_the_set():
    for after, want in ((["c", "a", "x"], True), (["c", "a", "b"], False)):
        st, sw, cv = _sw()
        sw.last = F("http://h/pl/1", lists=[L("Tracks", ["a", "b", "c"])])
        out = cv.check(sw, F("http://h/pl/1", lists=[L("Tracks", after)]), {}, _Obs("http://h/pl/1"),
                       [{"do": "click", "el": '[1] button "Shuffle"'}], None, 2)
        assert ("R74" in rules(out)) is want, out


def test_r30_header_offers_log_in_to_a_named_account():
    st, sw, cv = _sw()
    out = cv.check(sw, F("http://h/"), {"nav": [{"text": "Log in"}, {"text": "w1"}]}, _Obs("http://h/"), [], None, 1)
    assert any(v.rule == "R30" and v.subject == "header" for v in out)
    out = cv.check(sw, F("http://h/"), {"nav": [{"text": "Log in"}, {"text": "Home"}]}, _Obs("http://h/"), [], None, 2)
    assert not any(v.subject == "header" for v in out)


def test_r31_empty_state_without_its_control():
    st, sw, cv = _sw()
    st.cross.controls.add("create project")
    t = "No projects yet. Create your first project to begin."
    assert "R31" in rules(cv.check(sw, F("http://h/projects", text=t), {"controls": []}, _Obs("http://h/projects"), [], None, 1))
    assert "R31" not in rules(cv.check(sw, F("http://h/projects", text=t), {"controls": ["Create project"]},
                                       _Obs("http://h/projects"), [], None, 2))


def test_r61_suggestion_opens_another_item():
    for h1, want in (("Borealis Z2", True), ("Atlas Q7", False)):
        st, sw, cv = _sw()
        sw.prev5 = {"suggestions": ["Atlas Q7"]}
        obs = _Obs("http://h/search", [Element(id="3", tag="a", text="Atlas Q7")])
        out = cv.check(sw, F("http://h/i/1", h1=h1), {}, obs, [{"do": "click", "id": "3", "el": '[3] a "Atlas Q7"'}], None, 2)
        assert ("R61" in rules(out)) is want, out


def _tot(total, sub=None):
    t = [{"label": "Total", "value": total}]
    return t + ([{"label": "Subtotal", "value": sub}] if sub else [])


def test_r69_cart_path_independence_and_quantity():
    st, sw, cv = _sw()
    raw = {"fields": [{"label": "Quantity", "name": "qty", "type": "number", "value": "2"}]}
    cart = lambda tot: F("http://h/cart", lists=[L("Cart", ["Lamp"])], totals=_tot(tot))  # noqa: E731
    cv.check(sw, cart("$20.00"), raw, _Obs("http://h/cart"), [], None, 1)
    assert any(v.subject == "path" for v in cv.check(sw, cart("$24.00"), raw, _Obs("http://h/cart"), [], None, 2))
    assert not cv.check(sw, cart("$20.00"), raw, _Obs("http://h/cart"), [], None, 3)
    ok(sw)
    done = [{"do": "fill", "value": "3", "el": '[2] input label="Quantity"'}]
    assert any(v.subject == "qty" for v in cv.check(sw, cart("$20.00"), raw, _Obs("http://h/cart"), done, None, 4))


def test_r69_coupon_minimum_expired_and_twice():
    st, sw, cv = _sw()
    ok(sw)
    coupon = [{"do": "fill", "value": "SAVE10", "el": '[4] input label="Coupon code"'}]
    sw.last = F("http://h/cart", totals=_tot("$30.00", "$30.00"))
    out = cv.check(sw, F("http://h/cart", text="Minimum order of $50 applies. Code SAVE10 expired.",
                         totals=_tot("$27.00", "$30.00")), {}, _Obs("http://h/cart"), coupon, None, 1)
    assert {"minimum", "expired"} <= {v.subject for v in out}, out
    sw.last = F("http://h/cart", totals=_tot("$27.00", "$30.00"))
    out = cv.check(sw, F("http://h/cart", totals=_tot("$24.30", "$30.00")), {}, _Obs("http://h/cart"), coupon, None, 2)
    assert any(v.subject == "twice" for v in out)
    st, sw, cv = _sw()
    ok(sw)
    sw.last = F("http://h/cart", totals=_tot("$80.00", "$80.00"))
    out = cv.check(sw, F("http://h/cart", text="Minimum order of $50 applies.", totals=_tot("$72.00", "$80.00")), {},
                   _Obs("http://h/cart"), coupon, None, 1)
    assert not out, out


def _r12c(value, shown, raw=None, field="Notes"):
    st, sw, cv = _sw()
    sw.mem.typed.add(value)
    ev(sw, step=1, verb="create", obj="Trip", written=True, fields={field: value})
    out = cv.check(sw, F("http://h/i/1", h1="Trip", text=f"Trip {shown}"), raw or {}, _Obs("http://h/i/1"), [], None, 2)
    return {v.subject.split("|")[0] for v in out if v.rule == "R12c"}


def test_r12c_values_cut_emoji_zeros_spaces():
    long = "A remarkably long description that the app keeps"
    assert _r12c(long, long[:26]) == {"cut"}
    assert _r12c("Paris 🌍 west", "Paris  west") == {"emoji"}
    assert _r12c("007421", "Code 7421", field="Code") == {"zeros"}
    assert _r12c("1234567890123456789", "1234567890123456700", field="Card") == {"rounded"}
    assert _r12c("a  b  c", "", {"fields": [{"label": "Tag", "name": "tag", "type": "text", "value": "a b c"}]},
                 field="Tag") == {"spaces"}
    # shown as typed: nothing
    assert _r12c(long, long) == set() and _r12c("007421", "Code 007421", field="Code") == set()
    assert _r12c("a  b  c", "", {"fields": [{"label": "Tag", "name": "tag", "type": "text", "value": "a  b  c"}]},
                 field="Tag") == set()


def test_r12c_cap_keeps_the_same_two_in_every_process():
    import subprocess
    import sys

    import os

    code = "\n".join([
        "import sys; sys.path.insert(0, 'tests'); from test_d61_crossview import F, _Obs, _sw, ev",
        "st, sw, cv = _sw(); long = 'A remarkably long description that the app keeps'",
        "vals = (long, 'Paris ' + chr(0x1F30D) + ' west', '007421', 'a  b  c')",
        "[sw.mem.typed.add(v) for v in vals]",
        "ev(sw, step=1, verb='create', obj='Trip', written=True, fields=dict(zip('ABCD', vals)))",
        "raw = {'fields': [{'label': 'D', 'name': 'd', 'type': 'text', 'value': 'a b c'}]}",
        "out = cv.check(sw, F('http://h/i/1', h1='Trip', text='Trip ' + long[:26] + ' 7421 Paris  west'), raw,"
        " _Obs('http://h/i/1'), [], None, 2)",
        "print(sorted(v.subject for v in out if v.rule == 'R12c'))"])
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONIOENCODING": "utf-8"}).stdout.strip()
            for seed in (1, 2, 3, 4)}
    assert len(runs) == 1 and runs != {""}, runs


def test_r20_currency_and_r20d_title():
    st, sw, cv = _sw()
    cv.check(sw, F("http://h/shop", lists=[L("Products", ["Desk Lamp", "Oak Chair"], "http://h/p/", ["Desk Lamp $25.00", "Oak Chair $40.00"])]),
             {}, _Obs("http://h/shop"), [], None, 1)
    out = cv.check(sw, F("http://h/p/0", h1="Desk Lamp", text="Desk Lamp €25.00"), {}, _Obs("http://h/p/0"), [], None, 2)
    assert any(v.subject.startswith("currency") for v in out), out
    out = cv.check(sw, F("http://h/p/1", h1="Oak Chair", text="Oak Chair $40.00", title="Desk Lamp - Shop"), {}, _Obs("http://h/p/1"),
                   [], None, 3)
    assert "R20d" in rules(out) and not any(v.subject.startswith("currency") for v in out), out


def test_r51c_message_fidelity():
    st, sw, cv = _sw()
    e = ev(sw, step=1, verb="delete", obj="Atlas Q7", written=True)
    assert rules(message_fidelity(sw, [{"text": "3 items deleted"}], e, [])) == ["R51c"]
    assert rules(message_fidelity(sw, [{"text": "'Borealis Z2' was deleted"}], e, [])) == ["R51c"]
    assert not message_fidelity(sw, [{"text": "'Atlas Q7' was deleted"}], e, [])
    assert not message_fidelity(sw, [{"text": "1 item deleted"}], e, [])


def test_d61_clean_trail_raises_nothing():
    st, sw, cv = _sw()
    shop = F("http://h/shop", lists=[L("Products", ["Lamp", "Chair"], "http://h/p/", ["Lamp $25.00 2025-05-01 18:00",
                                                                                      "Chair $40.00"])])
    pages = [(shop, {}), (F("http://h/p/0", h1="Lamp", text="Lamp $25.00 2025-05-01 18:00", title="Lamp - Shop"), {}),
             (F("http://h/p/1", h1="Chair", text="Chair $40.00 Order #4411"), {}),
             (F("http://h/tickets?status=open", lists=[L("Tickets", ["T1"], "http://h/tickets/", ids=[1])]), {}),
             (F("http://h/tickets?status=closed", lists=[L("Tickets", ["T2"], "http://h/tickets/", ids=[2])]), {}),
             (F("http://h/notifications"), {"unread": 0}),
             (F("http://h/"), {"nav": [{"text": "Log out"}, {"text": "w1"}]})]
    out = []
    for i, (f, raw) in enumerate(pages, 1):
        out += cv.check(sw, f, raw, _Obs(f.url), [], None, i)
    assert out == [], out
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]


def test_r20_skips_menu_links_to_action_pages():
    """D62 (I83, the BookStack pilot): an 'Actions' menu entry linking to /create-book is not an item, so its own page
    ('Create New Book') is not a renamed item; a real item still is."""
    st, sw, cv = _sw()
    menu = {"heading": "Books", "nav": False, "items": [
        {"name": "Actions", "text": "Actions", "abs": "http://h/create-book", "href": "/create-book"},
        {"name": "Atlas", "text": "Atlas", "abs": "http://h/books/7", "href": "/books/7"}]}
    cv.check(sw, F("http://h/books", lists=[menu]), {}, _Obs("http://h/books"), [], None, 1)
    assert "http://h/create-book" not in st.cross.views and "/create-book" not in st.cross.views
    out = cv.check(sw, F("http://h/create-book", h1="Create New Book"), {}, _Obs("http://h/create-book"), [], None, 2)
    assert "R20" not in rules(out), out
    out = cv.check(sw, F("http://h/books/7", h1="Borealis"), {}, _Obs("http://h/books/7"), [], None, 3)
    assert "R20" in rules(out), out


def test_d62_pilot_shapes_r12c_markup_and_r09d_byline():
    """D62 (I90, I91, the Conduit pilot): typed markdown is rendered, not cut; a card's byline read as its own item
    is not a second removed item. The real cases above still fire."""
    md = "Content with markdown and <i>italic</i> and *bold* words in it"
    assert _r12c(md, "Content with markdown and italic and bold words in it") == set()
    st, sw, cv = _sw()
    sw.last = F("http://h/list", lists=[L("Comments", ["Nice post", "worker01October 29, 2026", "Gamma"])])
    e = ev(sw, step=2, verb="delete", obj="Nice post", written=True)
    out = cv.check(sw, F("http://h/list", lists=[L("Comments", ["Gamma"])]), {}, _Obs("http://h/list"), [], e, 2)
    assert "R09d" not in rules(out), out
