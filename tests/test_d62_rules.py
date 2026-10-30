"""D62: fixture tests for the built rules that had none (lock entry, v5 plan section 12.2 (1)), against two
served apps, once with faults and once without. Steps are driven by hand (no LLM), as the gate's replays do.

Forms app (fetch and classic forms). With `faulty=True`:
  - 'Budget amount' 1,234.5 is saved as 1 (R59),
  - the 40-character limit on a project name is only in the page; the server stores longer names (R60),
  - the form's one-time token is not checked, so a retry after a lost response makes another project (R50m)
    and a double click makes two (R33g; R33 on the order form); the clean app refuses a used token and disables
    the button in flight,
  - team names are unique only byte for byte: a trailing space or another case is a new team (R16u),
  - a task is listed as soon as its draft is saved, so a refused publish step still leaves it listed (R52f),
  - saving a note says 'Something went wrong' though the note was saved (I-error, then R50 when it shows).
Pages app. With `faulty=True`:
  - the CSV export imported back reports one row fewer (R37i),
  - a search for a made-up word lists a document (R05),
  - a document shown as favourited is missing from 'My favourites' (R07b),
  - the favourite button's count does not change when the app accepts the click (R19),
  - the inbox says 'No items yet' while its request failed (R54),
  - a folder can be moved into its own subfolder (R40c),
  - the last onboarding step opens without the earlier ones (R45),
  - a sort kept in local storage is not applied after a reload (R48),
  - an attached file is not shown on the saved document (R42),
  - two tabs editing one document lose the first tab's change with no warning (R46c),
  - a failed title save still shows the new title (R52).
The clean apps must raise none of these, and each rule must have run there too (armed, not skipped).
v4 app (rules locked in v4 with live measurements but no fixture case). With `faulty=True`:
  - an item link in a list answers 404 (R02), a background request gets no answer (request_failed),
  - a delete is accepted but the item stays (I-delete), a search lists an item without the term (I-filter),
  - the second page pushes a history entry on load, so Back stays on it (G1),
  - a deleted item is still listed under 'Shared items' (R49), an edit is accepted but not saved (I-edit).
The login and second-account probes (R24, R24b, R28, R46, R46w, R66, R67) and I-logout stay with the resweep.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import unicodedata
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from webtester.config import AppConfig, RunConfig
from webtester.consistency import SweepState, Sweeper

FORM_RULES = {"R59", "R60", "R50m", "R33g", "R33", "R16u", "R52f", "I-error", "R50"}
PAGE_RULES = {"R37i", "R05", "R07b", "R19", "R54", "R40c", "R45", "R48", "R42", "R46c", "R52"}
V4_RULES = {"R02", "I-delete", "I-filter", "G1", "R49", "I-edit"}
# rules whose arming needs the fault itself (a failed save shown, a message that a write failed)
ARMS_ONLY_ON_FAULT = {"R50", "R52"}


class Base(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status: int, body: str = "", ctype: str = "text/html; charset=utf-8", location: str = "",
             cookie: str = ""):
        b = body.encode()
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def form(self) -> dict:
        q = parse_qs(self.body().decode(), keep_blank_values=True)
        return {k: v[0] for k, v in q.items()}

    def multipart(self) -> dict:
        msg = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + self.body())
        out = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            out[name] = (part.get_filename(), part.get_payload(decode=True) or b"")
        return out


def html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body><nav><a href='/'>Home</a></nav>{body}</body></html>"


# ---------------------------------------------------------------------------------------------- forms app
PROJECT_JS = """<script>
const f = document.getElementById('f'), msg = document.getElementById('msg'), go = document.getElementById('go');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  %s
  try {
    const r = await fetch('/api/projects', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: f.elements['name'].value, budget: f.elements['budget'].value, token: f.elements['token'].value})});
    const d = await r.json();
    if (r.ok) {
      const li = document.createElement('li');
      li.innerHTML = '<a href="/projects/' + d.id + '"></a> <span>Budget ' + d.budget + '</span>';
      li.firstChild.textContent = d.name;
      document.getElementById('list').appendChild(li);
      f.elements['token'].value = d.token; f.elements['name'].value = ''; f.elements['budget'].value = '';
      msg.textContent = 'Project created.';
    } else msg.textContent = d.error;
  } catch (err) { msg.textContent = 'Network error, please try again.'; }
  go.disabled = false;
});
</script>"""
TASK_JS = """<script>
const f = document.getElementById('f'), msg = document.getElementById('msg'), go = f.querySelector('button');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  go.disabled = true;  // one submit sends two writes (R33g must not call that a double submit, D62)
  try {
    const r = await fetch('/api/drafts', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: f.elements['name'].value})});
    if (!r.ok) { msg.textContent = (await r.json()).error; go.disabled = false; return; }
    const d = await r.json();
    const r2 = await fetch('/api/tasks/publish', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: d.id})});
    if (!r2.ok) throw new Error('publish');
    const li = document.createElement('li');
    li.innerHTML = '<a href="/tasks/' + d.id + '"></a>';
    li.firstChild.textContent = d.name;
    document.getElementById('list').appendChild(li);
    f.elements['name'].value = '';
    msg.textContent = 'Task added.';
  } catch (err) { msg.textContent = 'Saving failed, please try again.'; }
  go.disabled = false;
});
</script>"""


class FormsApp:
    def __init__(self, faulty: bool):
        self.faulty = faulty
        self.projects: list[tuple[str, str]] = []
        self.used: set[str] = set()
        self.n_tokens = 0
        self.drafts: dict[int, str] = {}
        self.tasks: list[tuple[int, str]] = []
        self.teams: list[str] = []
        self.notes: list[str] = []
        self.lock = threading.Lock()

    def token(self) -> str:
        with self.lock:
            self.n_tokens += 1
            return f"t{self.n_tokens}"

    def projects_page(self, order: bool = False) -> str:
        items = "".join(f"<li><a href='/projects/{i}'>{n}</a> <span>Budget {b}</span></li>"
                        for i, (n, b) in enumerate(self.projects, 1))
        disable = "" if self.faulty else "go.disabled = true;"
        title, button = ("Orders", "Place order") if order else ("Projects", "Create project")
        return html(title, f"<h1>{title}</h1><form id=f><label>Name <input name=name maxlength=40></label>"
                    "<label>Budget amount <input name=budget></label>"
                    f"<input type=hidden name=token value='{self.token()}'><button id=go type=submit>{button}</button>"
                    f"</form><p id=msg></p><h2>All {title.lower()}</h2><ul id=list>{items}</ul>" + PROJECT_JS % disable)

    def tasks_page(self) -> str:
        items = "".join(f"<li><a href='/tasks/{i}'>{n}</a></li>" for i, n in self.tasks)
        return html("Tasks", "<h1>Tasks</h1><form id=f><label>Task name <input name=name></label>"
                    f"<button type=submit>Add task</button></form><p id=msg></p><h2>All tasks</h2><ul id=list>{items}</ul>"
                    + TASK_JS)

    def team_form(self, msg: str = "", v: str = "") -> str:
        return html("New team", f"<h1>New team</h1>{f'<p class=error>{msg}</p>' if msg else ''}"
                    f"<form method=post action=/teams><label>Team name <input name=team value='{v}'></label>"
                    "<button type=submit>Create team</button></form>")

    def note_form(self, msg: str = "") -> str:
        return html("New note", f"<h1>New note</h1>{f'<p class=error>{msg}</p>' if msg else ''}"
                    "<form method=post action=/notes><label>Title <input name=title></label>"
                    "<button type=submit>Save note</button></form>")

    def api_project(self, d: dict) -> tuple[int, dict]:
        time.sleep(0.3)  # a real save takes a moment: a double click lands while the first is in flight
        name, raw, tok = d.get("name", ""), d.get("budget", ""), d.get("token", "")
        if not name.strip():
            return 422, {"error": "Name is required"}
        if not self.faulty:
            if tok in self.used:
                return 409, {"error": "This form was already submitted"}
            if len(name) > 40:
                return 422, {"error": "Name is too long (at most 40 characters)"}
        try:
            budget = float(raw.split(",")[0] if self.faulty else raw.replace(",", ""))
        except ValueError:
            return 422, {"error": "Budget amount must be a number"}
        with self.lock:
            self.used.add(tok)
            self.projects.append((name, f"{budget:g}"))
            pid = len(self.projects)
        return 201, {"id": pid, "name": name, "budget": f"{budget:g}", "token": self.token()}

    def team_key(self, v: str) -> str:
        return v if self.faulty else unicodedata.normalize("NFC", v.strip()).casefold()

    def handler(self):
        app = self

        class H(Base):
            def do_GET(self):
                u = urlsplit(self.path)
                m = re.fullmatch(r"/(projects|tasks|teams|notes)/(\d+)", u.path)
                if u.path in ("/projects", "/orders"):
                    self.send(200, app.projects_page(order=u.path == "/orders"))
                elif u.path == "/tasks":
                    self.send(200, app.tasks_page())
                elif u.path == "/teams/new":
                    self.send(200, app.team_form())
                elif u.path == "/teams":
                    items = "".join(f"<li><a href='/teams/{i}'>{n}</a></li>" for i, n in enumerate(app.teams, 1))
                    self.send(200, html("Teams", f"<h1>Teams</h1><h2>All teams</h2><ul>{items}</ul>"))
                elif u.path == "/notes/new":
                    self.send(200, app.note_form())
                elif u.path == "/notes":
                    items = "".join(f"<li><a href='/notes/{i}'>{n}</a></li>" for i, n in enumerate(app.notes, 1))
                    self.send(200, html("Notes", f"<h1>Notes</h1><h2>All notes</h2><ul>{items}</ul>"))
                elif m:
                    self.send(200, html(m.group(1), f"<h1>{m.group(1).title()} {m.group(2)}</h1><p>Details.</p>"))
                else:
                    self.send(404, html("Not found", "<h1>Not found</h1>"))

            def do_POST(self):
                u = urlsplit(self.path)
                if u.path.startswith("/api/"):
                    d = json.loads(self.body() or b"{}")
                    if u.path == "/api/projects":
                        st, out = app.api_project(d)
                    elif u.path == "/api/drafts":
                        if not (d.get("name") or "").strip():
                            st, out = 422, {"error": "Task name is required"}
                        else:
                            with app.lock:
                                i = len(app.drafts) + 1
                                app.drafts[i] = d["name"]
                                if app.faulty:  # the draft is listed before the flow is done
                                    app.tasks.append((i, d["name"]))
                            st, out = 201, {"id": i, "name": d["name"]}
                    elif u.path == "/api/tasks/publish":
                        i = int(d.get("id") or 0)
                        if i in app.drafts and not app.faulty:
                            app.tasks.append((i, app.drafts[i]))
                        st, out = 200, {"ok": True}
                    else:
                        st, out = 404, {"error": "no such endpoint"}
                    self.send(st, json.dumps(out), "application/json")
                elif u.path == "/teams":
                    v = self.form().get("team", "")
                    if not v.strip():
                        self.send(422, app.team_form("Team name is required", v))
                    elif app.team_key(v) in {app.team_key(t) for t in app.teams}:
                        self.send(422, app.team_form("That team name has already been taken", v))
                    else:
                        app.teams.append(v)
                        self.send(303, location="/teams")
                elif u.path == "/notes":
                    v = self.form().get("title", "")
                    if not v.strip():
                        self.send(422, app.note_form("Title is required"))
                        return
                    app.notes.append(v)
                    if app.faulty:  # saved, but the page says it failed
                        self.send(200, app.note_form("Something went wrong. The note could not be saved."))
                    else:
                        self.send(303, location="/notes")
                else:
                    self.send(404, html("Not found", "<h1>Not found</h1>"))

        return H


FORM_PLAN = (
    [("/projects", [("Name", f"{w} project"), ("Budget amount", "250")], "Create project")
     for w in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel")]
    + [("/orders", [("Name", f"{w} order"), ("Budget amount", "40")], "Place order")
       for w in ("India", "Juliet", "Kilo", "Lima")]
    + [("/tasks", [("Task name", f"{w} the fence")], "Add task")
       for w in ("Paint", "Mend", "Measure", "Sand", "Stain", "Inspect", "Photograph", "Sketch")]
    + [("/teams/new", [("Team name", t)], "Create team") for t in ("Design team", "Design team", "Sales team")]
    + [("/teams", [], None), ("/notes/new", [("Title", "Weekly summary")], "Save note"), ("/notes", [], None),
       ("/teams", [], None)]
)


# ---------------------------------------------------------------------------------------------- pages app
FAV_JS = """<script>
const fv = document.getElementById('fv');
fv.addEventListener('click', async () => {
  const r = await fetch('/api/docs/3/favourite', {method: 'POST'});
  const d = await r.json();
  %s
});
</script>"""
INBOX_JS = """<div id=box>Loading</div><script>
fetch('/api/inbox').then(async (r) => {
  const box = document.getElementById('box');
  if (!r.ok) { box.innerHTML = '<p>No items yet</p>'; return; }
  const xs = await r.json();
  box.innerHTML = '<h2>Messages</h2><ul>' + xs.map((x, i) => '<li><a href="/inbox/' + (i + 1) + '">' + x + '</a></li>').join('') + '</ul>';
});
</script>"""
BOARD_JS = """<script>
const DEFAULT = ['Zeta card', 'Alpha card', 'Mid card'];
function draw(names) {
  document.getElementById('cards').innerHTML = names.map((n, i) => '<li><a href="/cards/' + (DEFAULT.indexOf(n) + 1) + '">' + n + '</a></li>').join('');
}
let saved = null;
try { saved = JSON.parse(localStorage.getItem('order')); } catch (e) {}
draw(%s);
document.getElementById('sort').addEventListener('click', () => {
  const names = DEFAULT.slice().sort();
  localStorage.setItem('order', JSON.stringify(names));
  draw(names);
});
</script>"""
RENAME_JS = """<script>
const f = document.getElementById('f'), h = document.querySelector('h1'), msg = document.getElementById('msg');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  const old = h.textContent, v = f.elements['title'].value;
  h.textContent = v;  // optimistic
  const r = await fetch('/api/docs/%d', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: v})});
  if (!r.ok) { %s }
});
</script>"""


class PagesApp:
    def __init__(self, faulty: bool):
        self.faulty = faulty
        self.docs = {1: {"title": "Annual report", "body": "Figures for the year.", "v": 1, "file": ""},
                     2: {"title": "Budget memo", "body": "Spending plan.", "v": 1, "file": ""},
                     3: {"title": "Coffee rota", "body": "Who brings coffee.", "v": 1, "file": ""},
                     4: {"title": "Design notes", "body": "Sketches and ideas.", "v": 1, "file": ""}}
        self.fav3 = False
        self.parent = {1: None, 2: 1}
        self.folders = {1: "Root folder", 2: "Child folder"}
        self.lock = threading.Lock()

    def doc_page(self, i: int) -> str:
        d = self.docs[i]
        extra = ""
        if i == 2:
            extra = "<button type=button>Unfavourite</button>"
        elif i == 3:
            on = "Unfavourite" if self.fav3 else "Favourite"
            upd = "" if self.faulty else "fv.textContent = (d.on ? 'Unfavourite' : 'Favourite') + ' (' + d.count + ')';"
            extra = f"<button type=button class=favourite id=fv>{on} ({3 + self.fav3})</button>" + FAV_JS % upd
        if i >= 5:
            extra = (f"<p><a href='/docs/{i}/edit'>Edit</a> <a href='/docs/{i}/rename'>Rename</a></p>"
                     + (f"<p>Attachment: {d['file']}</p>" if d["file"] and not self.faulty else ""))
        return html(d["title"], f"<h1>{d['title']}</h1><p>{d['body']}</p>{extra}")

    def handler(self):
        app = self

        class H(Base):
            def do_GET(self):
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                m = re.fullmatch(r"/docs/(\d+)", u.path)
                f = re.fullmatch(r"/folders/(\d+)(/edit)?", u.path)
                if u.path == "/docs":
                    items = "".join(f"<li><a href='/docs/{i}'>{d['title']}</a></li>" for i, d in app.docs.items())
                    self.send(200, html("Documents", f"<h1>Documents</h1><h2>All documents</h2><ul>{items}</ul>"
                                        "<a href='/docs.csv'>Export CSV</a>"))
                elif u.path == "/docs.csv":
                    rows = "".join(f"{d['title']},{d['body']}\n" for d in app.docs.values())
                    self.send(200, "title,body\n" + rows, "text/csv")
                elif u.path == "/docs/import":
                    self.send(200, html("Import", "<h1>Import documents</h1><form method=post enctype=multipart/form-data "
                                        "action=/docs/import><label>CSV file <input type=file name=file></label>"
                                        "<button type=submit>Import</button></form>"))
                elif u.path == "/docs/new":
                    self.send(200, html("New document", "<h1>New document</h1><form method=post action=/docs "
                                        "enctype=multipart/form-data><label>Title <input name=title></label>"
                                        "<label>Body <textarea name=body></textarea></label>"
                                        "<label>Attachment <input type=file name=file></label>"
                                        "<button type=submit>Create document</button></form>"))
                elif m and int(m.group(1)) in app.docs:
                    self.send(200, app.doc_page(int(m.group(1))))
                elif re.fullmatch(r"/docs/\d+/edit", u.path):
                    i = int(u.path.split("/")[2])
                    d = app.docs[i]
                    self.send(200, html("Edit", f"<h1>Edit {d['title']}</h1><form method=post action=/docs/{i}/edit>"
                                        f"<label>Title <input name=title value='{d['title']}'></label>"
                                        f"<label>Body <textarea name=body>{d['body']}</textarea></label>"
                                        f"<input type=hidden name=v value='{d['v']}'><button type=submit>Save</button></form>"))
                elif re.fullmatch(r"/docs/\d+/rename", u.path):
                    i = int(u.path.split("/")[2])
                    revert = "msg.textContent = 'Saving the title failed.';" + ("" if app.faulty else " h.textContent = old;")
                    self.send(200, html("Rename", f"<h1>{app.docs[i]['title']}</h1><form id=f><label>Title <input "
                                        f"name=title value='{app.docs[i]['title']}'></label><button type=submit>Save title"
                                        "</button></form><p id=msg></p>" + RENAME_JS % (i, revert)))
                elif u.path == "/search":
                    term = (q.get("q") or [""])[0]
                    if not term:
                        self.send(200, html("Search", "<h1>Search</h1><form action=/search><input type=search name=q "
                                            "placeholder='Search documents'><button type=submit>Search</button></form>"))
                        return
                    hits = [(i, d["title"]) for i, d in app.docs.items() if term.lower() in d["title"].lower()]
                    if app.faulty and not hits:
                        hits = [(98, "Archived plan"), (99, "Old roadmap")]
                    items = "".join(f"<li><a href='/docs/{i}'>{t}</a></li>" for i, t in hits)
                    self.send(200, html("Search", f"<h1>Search results</h1><p>{len(hits)} results found</p>"
                                        f"<ul>{items}</ul>"))
                elif u.path == "/favourites":
                    ids = [1, 4] if app.faulty else [1, 2, 4]
                    items = "".join(f"<li><a href='/docs/{i}'>{app.docs[i]['title']}</a></li>" for i in ids)
                    self.send(200, html("Favourites", f"<h1>My favourites</h1><h2>My favourites</h2><ul>{items}</ul>"))
                elif u.path == "/home":
                    self.send(200, html("Home", "<h1>Workspace</h1><p><a href='/inbox'>Open inbox</a></p>"))
                elif u.path == "/inbox":
                    self.send(200, html("Inbox", "<h1>Inbox</h1>" + INBOX_JS))
                elif u.path == "/api/inbox":
                    if app.faulty:
                        self.send(500, json.dumps({"error": "down"}), "application/json")
                    else:
                        self.send(200, json.dumps(["Welcome aboard", "Your weekly digest"]), "application/json")
                elif f and int(f.group(1)) in app.folders:
                    i = int(f.group(1))
                    if f.group(2):
                        opts = "".join(f"<option value='{k}'{' selected' if app.parent.get(i) == k else ''}>{n}</option>"
                                       for k, n in app.folders.items() if k != i)
                        self.send(200, html("Edit folder", f"<h1>Edit {app.folders[i]}</h1><form method=post "
                                            f"action=/folders/{i}><label>Parent folder <select name=parent><option "
                                            f"value=''>(none)</option>{opts}</select></label><button type=submit>Save"
                                            "</button></form>"))
                        return
                    p = app.parent.get(i)
                    crumbs = (f"<nav aria-label='breadcrumb'><a href='/folders/{p}'>{app.folders[p]}</a> / "
                              f"<span>{app.folders[i]}</span></nav>") if p else ""
                    kids = "".join(f"<li><a href='/folders/{k}'>{app.folders[k]}</a></li>" for k, v in app.parent.items()
                                   if v == i)
                    self.send(200, html(app.folders[i], f"{crumbs}<h1>{app.folders[i]}</h1><h2>Subfolders</h2>"
                                        f"<ul>{kids}</ul><p><a href='/folders/{i}/edit'>Edit</a></p>"))
                elif u.path == "/onboarding/profile":
                    self.send(200, html("Profile", "<h1>Your profile</h1><a href='/onboarding/team'>Next</a>"),
                              cookie="onboard=profile; Path=/")
                elif u.path == "/onboarding/team":
                    self.send(200, html("Team", "<h1>Your team</h1><a href='/onboarding/finish'>Next</a>"),
                              cookie="onboard=team; Path=/")
                elif u.path == "/onboarding/finish":
                    if not app.faulty and "onboard=team" not in (self.headers.get("Cookie") or ""):
                        self.send(302, location="/onboarding/profile")
                    else:
                        self.send(200, html("Finish", "<h1>All set</h1><p>Onboarding complete.</p>"))
                elif u.path == "/board":
                    order = "DEFAULT" if app.faulty else "saved || DEFAULT"
                    self.send(200, html("Board", "<h1>Board</h1><h2>Cards</h2><ul id=cards></ul>"
                                        "<button type=button id=sort>Sort by name</button>" + BOARD_JS % order))
                else:
                    self.send(404, html("Not found", "<h1>Not found</h1>"))

            def do_POST(self):
                u = urlsplit(self.path)
                if u.path == "/docs/import":
                    parts = self.multipart()
                    rows = [r for r in (parts.get("file", (None, b""))[1]).decode().splitlines() if r.strip()][1:]
                    n = len(rows) - 1 if app.faulty else len(rows)
                    self.send(200, html("Import", f"<h1>Import documents</h1><p>{n} rows imported.</p>"))
                elif u.path == "/docs":
                    parts = self.multipart()
                    title = parts.get("title", (None, b""))[1].decode()
                    if not title.strip():
                        self.send(422, html("New document", "<h1>New document</h1><p class=error>Title is required</p>"))
                        return
                    with app.lock:
                        i = max(app.docs) + 1
                        app.docs[i] = {"title": title, "body": parts.get("body", (None, b""))[1].decode(), "v": 1,
                                       "file": parts.get("file", (None, b""))[0] or ""}
                    self.send(303, location=f"/docs/{i}")
                elif re.fullmatch(r"/docs/\d+/edit", u.path):
                    i = int(u.path.split("/")[2])
                    v = self.form()
                    d = app.docs[i]
                    if not app.faulty and int(v.get("v") or 0) != d["v"]:
                        self.send(409, html("Conflict", "<h1>Edit</h1><p class=error>This document was changed since you "
                                            "opened it. Reload to see the latest version.</p>"))
                        return
                    d.update(title=v.get("title", d["title"]), body=v.get("body", d["body"]), v=d["v"] + 1)
                    self.send(303, location=f"/docs/{i}")
                elif u.path == "/api/docs/3/favourite":
                    app.fav3 = not app.fav3
                    self.send(200, json.dumps({"on": app.fav3, "count": 3 + app.fav3}), "application/json")
                elif re.fullmatch(r"/folders/\d+", u.path):
                    i = int(u.path.split("/")[2])
                    p = self.form().get("parent") or ""
                    new = int(p) if p.isdigit() else None
                    below, k = set(), new
                    while k is not None:  # the new parent and its ancestors
                        below.add(k)
                        k = app.parent.get(k)
                    if not app.faulty and i in below:
                        self.send(422, html("Edit folder", "<h1>Edit folder</h1><p class=error>Moving a folder into its "
                                            "own subfolder is not allowed</p>"))
                        return
                    app.parent[i] = new
                    self.send(303, location=f"/folders/{i}")
                else:
                    self.send(404, html("Not found", "<h1>Not found</h1>"))

            def do_PUT(self):
                self.body()
                self.send(500, json.dumps({"error": "storage down"}), "application/json")

        return H


PAGE_PLAN = [
    ("/docs", [], None), ("/docs/import", [], None), ("/search", [], None), ("/docs/2", [], None),
    ("/favourites", [], None), ("/docs/3", [], None), ("/home", [], "Open inbox"), ("/folders/2", [], None),
    ("/folders/1", [], None), ("/folders/1", [], None), ("/onboarding/profile", [], None), ("/onboarding/team", [], None),
    ("/onboarding/finish", [], None), ("/board", [], "Sort by name"),
    ("/docs/new", [("Title", "Quarterly plan"), ("Body", "Goals for the quarter.")], "Create document"),
    ("/docs/5", [], None), ("/docs/5", [], None), ("/docs/5/rename", [("Title", "Quarterly plan revised")], "Save title"), ("/docs", [], None),
]


# ---------------------------------------------------------------------------------------------- v4 app
class V4App:
    def __init__(self, faulty: bool):
        self.faulty = faulty
        self.items = {1: "Old invoice", 2: "Paid invoice", 3: "Team photo", 4: "Office plan"}
        self.shared = [2, 3]

    def handler(self):
        app = self

        class H(Base):
            def do_GET(self):
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                m = re.fullmatch(r"/items/(\d+)", u.path)
                if u.path == "/items":
                    rows = "".join(f"<li><a href='/items/{i}'>{n}</a> <form method=post action=/items/{i}/delete "
                                   f"style='display:inline'><button type=submit>Delete</button></form></li>"
                                   for i, n in app.items.items())
                    ping = "<script>fetch('/api/ping');</script>"
                    self.send(200, html("Items", f"<h1>Items</h1><h2>All items</h2><ul>{rows}</ul>{ping}"))
                elif m and int(m.group(1)) in app.items:
                    i = int(m.group(1))
                    if app.faulty and i == 4:
                        self.send(404, html("Not found", "<h1>Not found</h1>"))
                        return
                    trap = "<script>history.pushState({}, '', location.pathname + '#top');</script>" \
                        if app.faulty and i == 2 else ""
                    self.send(200, html(app.items[i], f"<h1>{app.items[i]}</h1><p>Item details.</p>{trap}"
                                        f"<p><a href='/items/{i}/edit'>Edit</a></p><form method=post "
                                        f"action=/items/{i}/delete><button type=submit>Delete</button></form>"))
                elif re.fullmatch(r"/items/\d+/edit", u.path):
                    i = int(u.path.split("/")[2])
                    self.send(200, html("Edit item", f"<h1>Edit item</h1><form method=post action=/items/{i}/edit>"
                                        f"<label>Name <input name=name value='{app.items[i]}'></label>"
                                        "<button type=submit>Save</button></form>"))
                elif u.path == "/shared":
                    keep = app.shared if app.faulty else [i for i in app.shared if i in app.items]
                    names = {**{2: "Paid invoice", 3: "Team photo"}, **app.items}
                    rows = "".join(f"<li><a href='/items/{i}'>{names[i]}</a></li>" for i in keep)
                    self.send(200, html("Shared", f"<h1>Shared</h1><h2>Shared items</h2><ul>{rows}</ul>"))
                elif u.path == "/find":
                    term = (q.get("q") or [""])[0]
                    form = ("<form action=/find><label>Search items <input type=search name=q></label>"
                            "<button type=submit>Search</button></form>")
                    if not term:
                        self.send(200, html("Find", f"<h1>Find items</h1>{form}"))
                        return
                    hits = [(i, n) for i, n in app.items.items() if term.lower() in n.lower()]
                    if app.faulty:
                        hits.append((3, app.items[3]))
                    rows = "".join(f"<li><a href='/items/{i}'>{n}</a></li>" for i, n in hits)
                    self.send(200, html("Find", f"<h1>Search results</h1>{form}<p>{len(hits)} results found</p>"
                                        f"<h2>Results</h2><ul>{rows}</ul>"))
                elif u.path == "/api/ping":
                    if app.faulty:  # the connection closes with no answer
                        self.close_connection = True
                        self.connection.shutdown(2)
                        return
                    self.send(200, "{}", "application/json")
                else:
                    self.send(404, html("Not found", "<h1>Not found</h1>"))

            def do_POST(self):
                path = urlsplit(self.path).path
                m = re.fullmatch(r"/items/(\d+)/(delete|edit)", path)
                v = self.form()
                if m and m.group(2) == "edit":
                    i = int(m.group(1))
                    if not app.faulty:  # the faulty app answers as if it saved
                        app.items[i] = v.get("name", app.items[i])
                    self.send(303, location=f"/items/{i}")
                    return
                if m and not (app.faulty and m.group(1) == "1"):  # the faulty app keeps item 1
                    app.items.pop(int(m.group(1)), None)
                self.send(303, location="/items")

        return H


V4_PLAN = [("/items", [], None), ("/items/1", [], None), ("/items", [], None), ("/items/2", [], None),
           ("", [], "<back>"), ("/find", [("Search items", "invoice")], "Search"), ("/shared", [], None),
           ("/items/2", [], None), ("", [], "Delete"), ("/items", [], None), ("", [], "Delete"), ("/items", [], None),
           ("/items/3/edit", [], None), ("", [("Name", "Team photo 2025")], "Save"), ("/items", [], None),
           ("/find", [], None)]


# ---------------------------------------------------------------------------------------------- driver
def sweep(app, plan):
    pw_api = pytest.importorskip("playwright.async_api")
    from webtester.browser import BrowserSession

    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    implicit: list = []  # the session's own signals (http_5xx, page_error, request_failed)

    # a navigation is the step's own action in a real run, so a page's load requests come after the step's
    # network mark; here `goto` comes first, so reach such a page by clicking a link (as for /inbox). An empty
    # path acts on the page the last step left, as a worker does (the Sweeper's last facts are of that page).
    async def step_once(s, sw, path, step, fills, click):
        if path:
            await s.goto(path)
        obs = await s.observe()
        actions = []
        for label, value in fills:
            el = next(e for e in obs.elements if e.label.strip() == label)
            actions.append({"do": "fill", "id": el.id, "value": value, "el": f'[{el.id}] {el.tag} label="{label}"',
                            "ok": True, "ekey": el.key(), "nth": 0})
        if click == "<back>":
            actions.append({"do": "back", "id": None, "value": None, "el": None, "ok": True, "ekey": None, "nth": 0})
        elif click:
            el = next(e for e in obs.elements if e.text.strip() == click)
            actions.append({"do": "click", "id": el.id, "value": None, "el": f'[{el.id}] {el.tag} "{click}"', "ok": True,
                            "ekey": el.key(), "nth": 0})
        await sw.before(s, obs, actions)
        for a in actions:
            if a["do"] == "back":
                await s.execute("back")
                continue
            loc = s.page.locator(f'[data-wt-id="{a["id"]}"]')
            await (loc.fill(a["value"]) if a["do"] == "fill" else loc.click())
        if actions:
            await s.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(0.6)
        await sw.actions_done(s)
        done = actions or [{"do": "navigate", "id": None, "value": path, "el": None, "ok": True, "ekey": None}]
        out = await sw.after(s, obs, done, step)
        implicit.extend(s.drain_signals())
        return out

    async def go():
        async with pw_api.async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"no chromium: {e}")
            cfg = RunConfig(app=AppConfig(name="t", base_url=base), settle_ms=300, capture_evidence=True,
                            seed_copies=0, poll_deadline_s=0.5)
            s = BrowserSession(browser, cfg, 1)
            await s.start()
            st = SweepState()
            sw = Sweeper(st, 1, None)
            sigs = []
            try:
                for k, (path, fills, click) in enumerate(plan, 1):
                    sigs += await step_once(s, sw, path, k, fills, click)
            finally:
                await s.close()
                await browser.close()
                srv.shutdown()
            return sigs, st, implicit

    return asyncio.run(go())


def _check_faulty(sigs, st, implicit, rules):
    got = {x.detail["rule"] for x in sigs}
    errors = [r for r in st.checks.records() if r["why"].startswith("error:")]
    assert not errors, errors
    assert rules <= got, (sorted(rules - got), json.dumps(st.p5.used))


def _check_clean(sigs, st, implicit, rules):
    got = {x.detail["rule"] for x in sigs}
    assert not (rules & got), [x.message for x in sigs if x.detail["rule"] in rules]
    assert not [r for r in st.checks.records() if r["why"].startswith("error:")]
    armed = {r["rule"] for r in st.checks.records() if r["outcome"] in ("exercised", "detected")}
    want = rules - ARMS_ONLY_ON_FAULT
    assert want <= armed, sorted(want - armed)


def test_d62_form_rules_find_the_faults():
    sigs, st, imp = sweep(FormsApp(True), FORM_PLAN)
    _check_faulty(sigs, st, imp, FORM_RULES)
    msgs = " ".join(x.message for x in sigs)
    for want in ("'1,234.5' was accepted", "with the page's limit removed", "after a lost response",
                 "was rejected as taken", "was refused", "reports 'Something went wrong"):
        assert want in msgs, (want, msgs)


def test_d62_form_rules_quiet_on_the_clean_app():
    _check_clean(*sweep(FormsApp(False), FORM_PLAN), FORM_RULES)


def test_d62_page_rules_find_the_faults():
    sigs, st, imp = sweep(PagesApp(True), PAGE_PLAN)
    _check_faulty(sigs, st, imp, PAGE_RULES)
    msgs = " ".join(x.message for x in sigs)
    for want in ("reports '3 rows imported'", "'Archived plan'", "'Budget memo' shows as favourited", "left its count at 3",
                 "No items yet", "a child of its own child", "opens directly", "is not there after a reload",
                 "is not shown afterwards", "two tabs edited the same item", "though the save failed"):
        assert want in msgs, (want, msgs)


def test_d62_page_rules_quiet_on_the_clean_app():
    _check_clean(*sweep(PagesApp(False), PAGE_PLAN), PAGE_RULES)


def test_d62_v4_rules_find_the_faults():
    sigs, st, imp = sweep(V4App(True), V4_PLAN)
    _check_faulty(sigs, st, imp, V4_RULES)
    assert any(x.kind == "request_failed" and "/api/ping" in x.message for x in imp), [x.message for x in imp]
    msgs = " ".join(x.message for x in sigs)
    for want in ("'Office plan' in 'All items' returns HTTP 404", "deleted 'Old invoice", "back went to",
                 "/shared still lists it", "'Team photo 2025'"):
        assert want in msgs, (want, msgs)


def test_d62_v4_rules_quiet_on_the_clean_app():
    sigs, st, imp = sweep(V4App(False), V4_PLAN)
    _check_clean(sigs, st, imp, V4_RULES)
    assert not [x for x in imp if x.kind == "request_failed"], [x.message for x in imp]


def test_exclude_rules_withholds_findings_but_not_signals(tmp_path):
    """D62: a locked version's left-out rules still run; their findings are kept apart, never reported."""
    from webtester.browser import Signal
    from webtester.config import load_config
    from webtester.oracles import FindingStore

    store = FindingStore(("R30", "R09"))
    sigs = [Signal("consistency", "[R30 T2] session ended", "http://h/", {"rule": "R30", "sig": "consistency|R30|/|x"}),
            Signal("consistency", "[R03 T1] link nowhere", "http://h/", {"rule": "R03", "sig": "consistency|R03|/|y"}),
            Signal("http_5xx", "POST /api -> 500", "http://h/", {"method": "POST", "url": "http://h/api", "status": 500})]
    new = store.ingest(sigs, step=1, worker=1, state="", trail=[])
    assert {f.kind for f in new} == {"consistency", "http_5xx"} and len(new) == 2
    assert [f.detail["rule"] for f in store.all() if f.kind == "consistency"] == ["R03"]
    assert [f.detail["rule"] for f in store.withheld.values()] == ["R30"]
    store.ingest(sigs[:1], step=2, worker=1, state="", trail=[])
    assert next(iter(store.withheld.values())).occurrences == 2
    cfg = tmp_path / "c.toml"
    cfg.write_text('[app]\nname = "t"\nbase_url = "http://h"\n[run]\nexclude_rules = ["R30", "R09"]\n', encoding="utf-8")
    assert load_config(cfg).exclude_rules == ("R30", "R09")
