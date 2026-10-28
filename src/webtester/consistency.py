"""Consistency oracles (harness v4, G3 v4, D49): does the app agree with itself and with
what the agents did?

The v3 checks asked the model to predict an action's outcome, and wrong guesses about
design (where Save leads, a heading's wording) were 32 of 32 false alarms on BookStack
(I43). v4 separates what the agent *meant to do* (its intent: create X, delete Y, which
it knows) from *how the app shows the result* (which it can only guess), and checks the
intent's effect independently, with facts the harness reads from the pages and with
probes in fresh tabs of the worker's session. Rules need no app knowledge:

  T1 (definite)   R01 rendering junk, R02 broken link, R03 dead list item, R04 count below
                  the items listed, R05 phantom search result, R06 arithmetic, R07 own
                  favourite/follow missing from its list, I-create / I-edit / I-delete /
                  I-toggle / I-logout effects
  T2 (likely)     R04b 'showing a-b of N', R07b observed toggle missing, R08 ages, R09 a list
                  changed on a revisit with no action to explain it, R10 link text vs the
                  page it opens, R11 pagination that does nothing or repeats, R12 echo (typed
                  markup rendered), I-filter, I-submit (silent), I-error (system error after a
                  save), G1 back button, G3 non-deterministic navigation
  T3 (LLM)        R15 a contradiction the model cites, kept only if both quotes are found

Added before the v4 lock (D50, from the technique review of 26 Oct):
  T1              R16 boundary input: an accepted create form, submitted again in a fresh tab with an
                  empty, spaces-only or over-long value (exactly maxlength when the field has one),
                  makes the server answer 5xx or the page throw
  T2              R13 access: an item's page offers Edit but its address refuses this session (while
                  the same kind of edit address opened a form for it elsewhere), or the page hides
                  Edit but the address made from the item's id opens a form filled with its data
                  (BACScan-style, one session, so the gate can replay it);
                  R17 validation: the form accepts an empty name for the new item, or rejects an
                  empty value but accepts one of only spaces;
                  G2 reload invariance: after a navigation with no write, the same URL opened in a
                  fresh tab shows another heading, other list items or other counts, and no recorded
                  action explains it (Genie's independent-view property)

A violation is a `consistency` signal; the FindingStore deduplicates it and the gate
(G2) reproduces it by replaying the worker's actions with a fresh Sweeper, so the same
rule must fire again on a reset app. The per-step cost is one page evaluation plus at
most MAX_PROBES fresh-tab probes and a few link status requests; no LLM tokens.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urljoin, urlsplit

from .browser import INNER_TEXT_JS, NET_TYPES, OBSERVE_JS, Element, Observation, Signal
from .memory import (EVENT_FEED, OFF, PERSONAL, RECENCY, SEARCH_FIELD, TITLE_FIELD, TOGGLES, Event, RunMemory, age_kind,
                     age_minutes, classify, entity_key, list_key, norm)
from .oracles import normalise_message
from .state import route_shape, value_class
from .stategraph import is_navigation
from .evidence import rule_messages, rule_payload

MAX_PROBES = 2  # fresh-tab probes per step per worker
MAX_LINK_CHECKS = 3  # link status requests per step per worker
MAX_ACCESS_PROBES = 6  # R13 edit-address probes per worker per run
MAX_RELOAD_PAGES = 20  # G2 reload checks per worker per run (one per route shape)
MAX_MUTATION_FORMS = 6  # R16/R17 forms per run (all workers); 3 fresh-tab submissions each
MAX_TOGGLE_PROBES = 4  # R19 count controls per run (all workers); 2 clicks each, the second undoes the first
MAX_FEED_PROBES = 4  # R07c author pages per run (all workers)
# a person's page: an item whose only link is its author is not about the item (D55 A5)
_PERSON = re.compile(r"/(user|users|profile|profiles|u|member|members|people|author|authors|account|accounts)/[^/?#]+/?$", re.I)
# a list of what this account follows (D55 A9): 'Your Feed', 'Following'
FOLLOW_FEED = re.compile(r"\b(your|my)\s+feed\b|\bfollowing\b|\bfollowed\b|\bsubscriptions?\b", re.I)
# fields whose markup is meant to render (Markdown or rich-text bodies): no R12 for them (D55 P8)
_RICH_FIELD = re.compile(r"markdown|\bbody\b|content|\bhtml\b|rich|editor|article", re.I)
# a page that lists what a search or tag link asked for (D55 P6): its title is not the link's
_SEARCH_DEST = re.compile(r"[?&](term|search|q|query|tag|tags|filter|keyword)=|/(search|tags?)(/|$)", re.I)
TIER = {"R01": "T1", "R02": "T1", "R03": "T1", "R04": "T1", "R05": "T1", "R06": "T1", "R07": "T1",
        "I-create": "T1", "I-edit": "T1", "I-delete": "T1", "I-toggle": "T1", "I-logout": "T1", "R16": "T1",
        "R19": "T1", "R07b": "T2", "R07c": "T2", "R18": "T2", "R04b": "T2", "R08": "T2", "R09": "T2", "R10": "T2", "R11": "T2", "R12": "T2", "R13": "T2",
        "R17": "T2", "I-filter": "T2", "I-submit": "T2", "I-error": "T2", "G1": "T2", "G2": "T2", "G3": "T2",
        "R15": "T3",
        "R51": "T2", "R57": "T2"}  # v5 evidence layer (D58), only with capture_evidence
LLM_RULES = {"R15"}

# ---------------------------------------------------------------------------- page facts
# Runs in the page. `typed`: values typed in this run that contain markup (R12).
AUDIT_JS = r"""
(typed) => {
  const B = document.body;
  if (!B) return null;
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return false;
    const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none'; };
  // tab bars ('Your Feed | Global Feed', Bootstrap .nav) are controls, not lists of things (27 Oct, D54)
  const NAV = 'nav, header, footer, [role=navigation], [role=menu], [role=menubar], [role=tablist], [role=tab], ' +
              '.nav, .nav-tabs, .nav-pills, .tabs, .pagination, .breadcrumb, .breadcrumbs';
  const HEAD = 'h1, h2, h3, h4, h5, h6, [role=heading]';
  const hrefOf = (a) => a ? (a.getAttribute('href') || '') : null;
  const absOf = (a) => { try { return a && a.getAttribute('href') ? new URL(a.getAttribute('href'), location.href).href : ''; } catch (e) { return ''; } };
  // An item's links, visible only (a hidden placeholder <a hidden href="link"> is no link, D55 P2). The item's
  // own link is the first one that is not to a person: 'Admin created page Page 1' is about Page 1 (D55 A5).
  const USER = /\/(user|users|profile|profiles|u|member|members|people|author|authors|account|accounts)\/[^/?#]+\/?$/i;
  const linksOf = (el) => (el.matches('a[href]') ? [el] : []).concat(Array.from(el.querySelectorAll('a[href]'))).filter(vis);
  const firstLink = (el) => { const ls = linksOf(el); return ls.find((a) => !USER.test(absOf(a))) || ls[0] || null; };
  const nameOf = (el) => {
    const h = Array.from(el.querySelectorAll(HEAD + ', strong, b, .title, .name, [class*=title], [class*=name]'))
      .find((x) => vis(x) && x.innerText.trim());
    const a = firstLink(el);
    return clean((h && h.innerText) || (a && a.innerText) || el.innerText.split('\n')[0], 100);
  };
  // headings inside a link are item names (BookStack's <h4> in each entity link), not list headings (D55 A2)
  const heads = (s) => Array.from(s.querySelectorAll(HEAD)).filter((h) => !h.closest('a') && vis(h));
  const headingFor = (container, firstItem) => {
    for (const c of container.children) {   // a heading inside the container, before the items
      if (c === firstItem) break;
      if (c.matches(HEAD) || heads(c).length) return clean(c.innerText, 80);
    }
    let n = container;
    for (let d = 0; d < 5 && n && n !== B; d++) {
      let s = n.previousElementSibling;
      for (let k = 0; k < 4 && s; k++, s = s.previousElementSibling) {
        if (!vis(s)) continue;
        if (s.matches(HEAD) && !s.closest('a')) return clean(s.innerText, 80);
        const hs = heads(s);
        if (hs.length) return clean(hs[hs.length - 1].innerText, 80);
      }
      n = n.parentElement;
    }
    return '';
  };
  // Repeated siblings with the same tag and a shared class (or the same class set), each holding a link: a
  // list. A shared class, not the exact set: BookStack's results are 'book entity-list-item', 'page
  // entity-list-item', ... and a phantom result has its own type class (D55 A1).
  const lists = [];
  for (const el of B.querySelectorAll('*')) {
    if (el.children.length < 2 || !vis(el)) continue;
    const kids = Array.from(el.children).filter(vis);
    const groups = new Map();
    for (const c of kids) {
      const keys = [c.tagName + '.' + Array.from(c.classList).sort().join('.')].concat(
        Array.from(c.classList).map((x) => c.tagName + ':' + x));
      for (const k of keys) { if (!groups.has(k)) groups.set(k, []); groups.get(k).push(c); }
    }
    let best = null;
    for (const g of groups.values()) if (g.length >= 2 && (!best || g.length > best.length)) best = g;
    if (!best || !best.every((c) => firstLink(c))) continue;
    lists.push({ el, items: best });
  }
  // A list inside one item of another list is part of that item (an activity entry's author and object
  // links), unless the inner lists are long (a wrapper of real lists, e.g. dashboard columns) (D55 A1).
  const inner = (L) => lists.filter((M) => M !== L && L.items.some((c) => c.contains(M.el)));
  const drop = new Set();
  for (const L of lists) {
    const ins = inner(L);
    if (!ins.length) continue;
    const holding = L.items.filter((c) => ins.some((M) => c.contains(M.el))).length;
    const wrapper = holding * 2 >= L.items.length && ins.some((M) => M.items.length >= 4);
    if (wrapper) drop.add(L); else ins.filter((M) => M.items.length <= 3).forEach((M) => drop.add(M));
  }
  const kept = lists.filter((L) => !drop.has(L));
  const out = [];
  // One address can show different lists by tab ('Your Feed', 'Global Feed', '#tag' all at '/'):
  // an unheaded list is named by the selected tab, so a revisit compares the same list (D54).
  const tab = B.querySelector('[role=tablist] [aria-selected=true], .nav-pills .active, .nav-tabs .active, .tabs .active');
  const tabName = tab ? clean(tab.innerText, 60) : '';
  const headOf = new Map();
  for (const L of kept) {
    const heading = headingFor(L.el, L.items[0]) || (tabName && !L.el.closest(NAV) ? 'tab: ' + tabName : '');
    headOf.set(L, heading);
    out.push({
      heading, nav: !!L.el.closest(NAV),
      items: L.items.slice(0, 60).map((c) => { const a = firstLink(c);
        return { name: nameOf(c), href: hrefOf(a), abs: absOf(a), text: clean(c.innerText, 240),
                 link_text: clean(a ? a.innerText : '', 100),
                 links: linksOf(c).map(absOf).filter((u) => u && u !== absOf(a)).slice(0, 4) }; }),
    });
  }
  // Short counted labels: "3 Books", "Comments (2)" ("15 hours ago" is an age, not a count).
  const counts = [];
  for (const el of B.querySelectorAll('span, small, strong, b, div, p, a, li, h2, h3, h4, h5, h6, dt, dd, td, label')) {
    if (el.children.length > 3 || !vis(el)) continue;
    const t = clean(el.innerText, 41);
    if (t.length > 40 || / of /i.test(t) || /\bago$/i.test(t)) continue;
    let m = t.match(/^(\d[\d,]*)\s+([A-Za-z][A-Za-z ]{1,24})$/);
    if (m) { counts.push({ n: +m[1].replace(/,/g, ''), unit: m[2].trim(), text: t, nav: !!el.closest(NAV) }); continue; }
    m = t.match(/^([A-Za-z][A-Za-z ]{1,24}?)\s*\((\d[\d,]*)\)$/);
    if (m) counts.push({ n: +m[2].replace(/,/g, ''), unit: m[1].trim(), text: t, nav: !!el.closest(NAV) });
  }
  const itemOf = (node) => { for (const L of kept) for (const c of L.items) if (c.contains(node)) { const a = firstLink(c);
    const ls = linksOf(c);
    return [absOf(a), clean(a ? a.innerText : '', 60), clean(c.innerText, 160), headOf.get(L) || '',
            ls.length >= 2 && ls.some((x) => USER.test(absOf(x)))]; } return ['', '', '', '', false]; };
  // Relative ages with the words around them ("Created 2 days ago by Admin").
  const times = [];
  const REL = /\b(just now|yesterday|(in\s+)?(\d+|an?|one)\s+(second|sec|minute|min|hour|hr|day|week|month|year)s?(\s+ago)?)\b/i;
  const walker = document.createTreeWalker(B, NodeFilter.SHOW_TEXT);
  let tn, nt = 0;
  while ((tn = walker.nextNode()) && times.length < 80 && nt++ < 20000) {
    const v = tn.nodeValue;
    if (!v || !REL.test(v)) continue;
    const p = tn.parentElement;
    if (!p || !vis(p) || p.closest('pre, code, textarea, script, style')) continue;
    const ctxEl = p.parentElement || p;
    const [item, itemName, itemText, listHeading, byPerson] = itemOf(p);
    times.push({ text: clean(v, 60), context: clean(ctxEl.innerText, 140), item, item_name: itemName,
                 item_text: itemText, list: listHeading, by_person: byPerson });
  }
  const tables = [];
  for (const t of Array.from(B.querySelectorAll('table')).filter(vis).slice(0, 3)) {
    const rows = Array.from(t.rows).slice(0, 60).map((r) => Array.from(r.cells).map((c) => clean(c.innerText, 60)));
    const head = t.tHead && t.tHead.rows.length ? rows[0] : (t.rows[0] && t.rows[0].querySelector('th') ? rows[0] : []);
    tables.push({ head, rows: head.length ? rows.slice(1) : rows });
  }
  const totals = [];
  const TOT = /^(sub-?total|subtotal|total|grand total|order total|amount due|balance due|tax|vat|gst|sales tax|shipping|delivery|postage|discount|coupon|promo(tion)?|fees?)\b/i;
  for (const el of B.querySelectorAll('dt, th, td, span, div, p, li, strong, label')) {
    if (!vis(el) || el.children.length > 2) continue;
    const t = clean(el.innerText, 80);
    if (!TOT.test(t)) continue;
    let m = t.match(/^([A-Za-z][A-Za-z .()%-]{1,30}?)\s*[:\s]\s*([-+(]?\s*[^\d\s-]{0,3}\s*\d[\d.,' ]*\)?)\s*[^\d\s]{0,4}$/);
    if (m) { totals.push({ label: m[1], value: m[2] }); continue; }
    const sib = el.nextElementSibling;
    if (sib && vis(sib) && /\d/.test(sib.innerText) && sib.innerText.length < 30) totals.push({ label: t, value: clean(sib.innerText, 30) });
  }
  const rendered = (typed || []).filter((v) => v && B.innerHTML.includes(v) && !B.innerText.includes(v));
  const toggles = [];
  for (const el of B.querySelectorAll('button, a, [role=button], input[type=submit]')) {
    if (!vis(el)) continue;
    const t = clean(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title'), 40);
    if (t) toggles.push(t);
  }
  const errors = Array.from(B.querySelectorAll('[role=alert], .alert, .error, .errors, .error-messages, .invalid-feedback, .notification, .toast, .flash, [class*=error], [class*=danger], [class*=warning]'))
    .filter(vis).map((e) => clean(e.innerText, 160)).filter((t) => t).slice(0, 8);
  const sInput = Array.from(B.querySelectorAll('input')).find((i) => vis(i) && (i.type === 'search' ||
    /search|query|^q$|find/i.test((i.name || '') + ' ' + (i.placeholder || '') + ' ' + (i.getAttribute('aria-label') || '') + ' ' + (i.id || ''))));
  // Visible text outside code blocks, for the rendering-junk rule.
  const parts = [];
  const tw = document.createTreeWalker(B, NodeFilter.SHOW_TEXT);
  let n2, len = 0;
  while ((n2 = tw.nextNode()) && len < 20000) {
    const p = n2.parentElement;
    if (!p || p.closest('pre, code, textarea, script, style, noscript, [contenteditable=true], .CodeMirror')) continue;
    const v = n2.nodeValue.trim();
    if (!v || !p.offsetParent && getComputedStyle(p).position !== 'fixed') continue;
    parts.push(v); len += v.length;
  }
  // Entity cards: links that hold a heading (a single search result is a card, not yet a list).
  const cards = Array.from(B.querySelectorAll('a')).filter((a) => vis(a) && !a.closest(NAV) && a.querySelector(HEAD))
    .slice(0, 100).map((a) => ({ name: clean(a.querySelector(HEAD).innerText, 100), href: hrefOf(a), text: clean(a.innerText, 200) }));
  // Owner controls (R13): Edit / Delete / Remove outside the navigation, with the link's address.
  const owner = [];
  for (const el of B.querySelectorAll('a, button, [role=button], input[type=submit]')) {
    if (owner.length >= 10) break;
    if (!vis(el) || el.closest(NAV)) continue;
    const t = clean(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title'), 41);
    if (!t || t.length > 40 || !/^(edit|delete|remove)\b/i.test(t)) continue;
    owner.push({ text: t, href: el.matches('a') ? hrefOf(el) : null, abs: el.matches('a') ? absOf(el) : '' });
  }
  const h1 = Array.from(B.querySelectorAll('h1')).find(vis);
  const m = B.innerText.match(/(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d[\d,]*)/i);
  return {
    url: location.href, title: document.title, h1: h1 ? clean(h1.innerText, 120) : '',
    text: B.innerText.slice(0, 20000), plain: parts.join('\n'),
    lists: out, counts: counts.slice(0, 40), times, tables, totals: totals.slice(0, 20), rendered, toggles: toggles.slice(0, 120),
    errors, search: !!sInput, cards, owner,
    showing: m ? { a: +m[1], b: +m[2], n: +m[3].replace(/,/g, '') } : null,
  };
}
"""

# Before a step's actions: mark the step's first clicked element and read what the checks
# need later (its text and number, the item it sits in, its form's validity and prefill).
PRE_JS = r"""
(ids) => {
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  document.querySelectorAll('[data-wt-probe]').forEach((e) => e.removeAttribute('data-wt-probe'));
  const out = { click: null, form_valid: null, prefilled: false, fields_before: {} };
  const el = ids.click ? document.querySelector('[data-wt-id="' + ids.click + '"]') : null;
  const num = (s) => { const m = (s || '').match(/(?<![\w.])-?\d[\d,]*(?![\w])/); return m ? +m[0].replace(/,/g, '') : null; };
  if (el) {
    el.setAttribute('data-wt-probe', '1');
    const ITEM = 'li, tr, article, [class*=item], [class*=card], [class*=comment], [class*=entry], [class*=row]';
    let item = el.closest(ITEM);
    // 'card-footer' matches [class*=card] but is a part of the item: the whole card holds its name (D54)
    while (item && /-(footer|header|body|block|actions|meta|options)\b/.test(item.getAttribute('class') || '')) {
      const up = item.parentElement ? item.parentElement.closest(ITEM) : null;
      if (!up) break;
      item = up;
    }
    const near = el.parentElement ? clean(el.parentElement.innerText, 60) : '';
    // the icon's classes name the control when its text is only a count (Conduit's heart button: <i class="ion-heart"> 0)
    const icons = Array.from(el.querySelectorAll('i, svg, span[class*=icon], [data-icon]'))
      .map((x) => (x.getAttribute('class') || '') + ' ' + (x.getAttribute('data-icon') || '')).join(' ');
    // a page control sits in a pagination container or in a run of page numbers (D55 P4)
    const box = el.closest('li, span, div') || el.parentElement;
    const run = box && box.parentElement ? Array.from(box.parentElement.children)
      .filter((c) => /^\s*(\d{1,3}|›|»|‹|«|next|prev(ious)?)\s*$/i.test(c.innerText || '')).length : 0;
    const own = num(el.innerText);
    out.click = { text: clean(el.innerText || el.value || '', 80), pressed: el.getAttribute('aria-pressed'),
                  cls: ((el.getAttribute('class') || '') + ' ' + icons).slice(0, 160), number: own ?? num(near.length <= 40 ? near : ''),
                  own_number: own !== null, link: el.matches('a[href]') && !/^(#.*|javascript:.*|)$/i.test(el.getAttribute('href') || ''),
                  pager: !!el.closest('.pagination, [class*=paginat], [class*=pager], nav[aria-label*=pag i]') || run >= 2,
                  item: item ? clean(item.innerText, 160) : '', submit: el.type === 'submit' || !!el.closest('form') };
    const f = el.form || el.closest('form');
    if (f) out.form_valid = f.checkValidity();
  }
  const first = ids.fill ? document.querySelector('[data-wt-id="' + ids.fill + '"]') : el;
  const form = first ? (first.form || first.closest('form')) : (el ? (el.form || el.closest('form')) : null);
  if (form) {
    // an account form (password field) and a GET/search form make no create or edit expectation (D55 P1, P7)
    out.form_password = !!form.querySelector('input[type=password]');
    out.form_get = (form.getAttribute('method') || '').toLowerCase() === 'get' || /search/i.test(form.getAttribute('action') || '')
      || !!form.querySelector('input[type=search]');
    for (const i of form.querySelectorAll('input, textarea')) {
      const t = (i.getAttribute('type') || '').toLowerCase();
      if (['password', 'hidden', 'checkbox', 'radio', 'submit', 'button', 'file'].includes(t)) continue;
      if (i.value && i.value.trim()) out.prefilled = true;
    }
  }
  if (el && document.body) out.page = document.body.innerText.slice(0, 20000);  // I-delete counts the name in it
  return out;
}
"""

POST_JS = r"""
() => {
  const el = document.querySelector('[data-wt-probe]');
  if (!el) return null;
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const num = (s) => { const m = (s || '').match(/(?<![\w.])-?\d[\d,]*(?![\w])/); return m ? +m[0].replace(/,/g, '') : null; };
  const near = el.parentElement ? clean(el.parentElement.innerText, 60) : '';
  const own = num(el.innerText);
  return { text: clean(el.innerText || el.value || '', 80), pressed: el.getAttribute('aria-pressed'),
           number: own ?? num(near.length <= 40 ? near : ''), own_number: own !== null };
}
"""

SEARCH_JS = r"""
(token) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const i = Array.from(document.querySelectorAll('input')).find((i) => vis(i) && (i.type === 'search' ||
    /search|query|^q$|find/i.test((i.name || '') + ' ' + (i.placeholder || '') + ' ' + (i.getAttribute('aria-label') || '') + ' ' + (i.id || ''))));
  if (!i) return false;
  i.setAttribute('data-wt-search', '1');
  return true;
}
"""

# A probe tab after it loaded (R13): where it ended and what its visible fields hold.
FORM_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const vals = [];
  for (const el of document.querySelectorAll('input, textarea, [contenteditable=true], [contenteditable=""]')) {
    const t = (el.getAttribute('type') || '').toLowerCase();
    if (['password', 'hidden', 'checkbox', 'radio', 'submit', 'button', 'file', 'search'].includes(t) || !vis(el)) continue;
    const v = (el.matches('input, textarea') ? el.value : el.innerText) || '';
    if (v.trim()) vals.push(v.trim().slice(0, 200));
  }
  return { url: location.href, fields: vals.slice(0, 30) };
}
"""


# R19: the first visible favourite/like control that shows a count, outside the navigation.
TOGGLE_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const num = (s) => { const m = (s || '').match(/(?<![\w.])-?\d[\d,]*(?![\w])/); return m ? +m[0].replace(/,/g, '') : null; };
  const LIKE = /favou?rite|\blike\b|heart|star|upvote|thumbs/i;
  for (const el of document.querySelectorAll('button, a, [role=button]')) {
    if (!vis(el) || el.closest('nav, header, footer, [role=navigation]')) continue;
    const icons = Array.from(el.querySelectorAll('i, svg, span, [data-icon]')).map((x) => (x.getAttribute('class') || '') + ' ' + (x.getAttribute('data-icon') || '')).join(' ');
    const label = (el.innerText || '') + ' ' + (el.getAttribute('class') || '') + ' ' + icons + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '');
    const n = num(el.innerText);
    if (n === null || !LIKE.test(label) || /follow|unfollow/i.test(label)) continue;
    if (el.matches('a[href]') && !/^(#.*|javascript:.*|)$/i.test(el.getAttribute('href') || '')) continue;
    el.setAttribute('data-wt-toggle', '1');
    const item = el.closest('li, tr, article, [class*=item], [class*=card], [class*=preview], [class*=entry]');
    return { number: n, text: clean(el.innerText, 40), verb: /like|upvote|thumbs/i.test(label) && !/favou?rite|heart|star/i.test(label) ? 'like' : 'favourite',
             item: item ? clean(item.innerText, 160) : '' };
  }
  return null;
}
"""

TOGGLE_READ_JS = r"""
() => {
  const el = document.querySelector('[data-wt-toggle="1"]');
  if (!el) return null;
  const m = (el.innerText || '').match(/(?<![\w.])-?\d[\d,]*(?![\w])/);
  return m ? { number: +m[0].replace(/,/g, '') } : null;
}
"""


@dataclass
class Facts:
    url: str
    title: str = ""
    h1: str = ""
    text: str = ""
    plain: str = ""
    lists: list = field(default_factory=list)
    counts: list = field(default_factory=list)
    times: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    totals: list = field(default_factory=list)
    rendered: list = field(default_factory=list)
    toggles: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    search: bool = False
    cards: list = field(default_factory=list)
    showing: dict | None = None
    owner: list = field(default_factory=list)

    @staticmethod
    def of(raw: dict | None, url: str = "") -> "Facts":
        if not raw:
            return Facts(url)
        return Facts(**{k: raw.get(k) for k in Facts.__dataclass_fields__ if k in raw})

    def content_lists(self) -> list[dict]:
        return [L for L in self.lists if not L.get("nav")]

    def main_list(self) -> dict | None:
        cl = self.content_lists()
        return max(cl, key=lambda L: len(L["items"])) if cl else None


async def audit(session, typed: list[str] | None = None, page=None) -> Facts:
    from playwright.async_api import Error as PWError

    page = page or session.page
    try:
        raw = await page.evaluate(AUDIT_JS, [t for t in (typed or []) if "<" in t][:20])
    except PWError:
        return Facts(page.url)
    return Facts.of(raw, page.url)


# ---------------------------------------------------------------------------- pure rules
@dataclass
class Violation:
    rule: str
    subject: str
    message: str
    evidence: str = ""

    @property
    def tier(self) -> str:
        return TIER[self.rule]


def signal_of(v: Violation, url: str) -> Signal:
    subject = normalise_message(norm(v.subject))[:80]
    sig = f"consistency|{v.rule}|{route_shape(url)}|{subject}"
    return Signal("consistency", f"[{v.rule} {v.tier}] {v.message}"[:300], url,
                  {"sig": sig, "rule": v.rule, "tier": v.tier, "evidence": v.evidence[:600]})


_JUNK = [
    (re.compile(r"\bNaN\b"), "NaN"),
    (re.compile(r"\bundefined\b"), "undefined"),
    (re.compile(r"\[object Object\]"), "[object Object]"),
    (re.compile(r"\bInvalid Date\b"), "Invalid Date"),
    (re.compile(r"\{\{\s*[\w.$\[\]'\"]+\s*\}\}"), "unfilled template {{ }}"),
    (re.compile(r"\$\{[\w.]+\}"), "unfilled template ${ }"),
    (re.compile(r"(?<![\w%])%[sd](?![\w])"), "unfilled %s placeholder"),
    (re.compile(r"&(?:amp;)*(?:lt|gt|quot|amp|#\d{2,4});"), "escaped HTML entity shown as text"),
    (re.compile(r"Traceback \(most recent call last\)|SQLSTATE\[|Whoops, looks like something went wrong|"
                r"Fatal error:|Uncaught (?:TypeError|ReferenceError|Error)|NullPointerException|"
                r"Exception in thread|Stack trace:|at [\w.$<>]+ \([^()]*:\d+:\d+\)"), "stack trace or error page"),
    (re.compile(r"\b\d+\.\d*?(?:0{6,}|9{6,})\d\b"), "floating-point noise"),
    (re.compile(r"(?<![\w-])-\d+\s+(?:items?|comments?|likes?|views?|followers?|members?|pages?|books?|articles?|"
                r"products?|results?|replies|votes?|stars?)\b", re.I), "negative count"),
]


def rule_junk(plain: str, typed: set[str]) -> list[Violation]:
    """R01: rendering junk in visible text outside code blocks; text the agents typed is removed first."""
    text = plain or ""
    for t in sorted(typed, key=len, reverse=True):
        if len(t) >= 2:
            text = text.replace(t, " ")
    out, seen = [], set()
    for rx, what in _JUNK:
        m = rx.search(text)
        if m and what not in seen:
            seen.add(what)
            ctx = text[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
            out.append(Violation("R01", what, f"rendering junk: {what}", f"...{ctx}..."))
    return out


_GENERIC = re.compile(r"^(more|show (all|more)|see (all|more)|view (all|more)|load more|all|next|previous|prev|"
                      r"back|edit|view|open|details|read more|«|»|‹|›|\.\.\.|…|\d+)$", re.I)
_DEAD = re.compile(r"^(#.*|javascript:.*|)$", re.I)
# names of controls that JS handles with href="#" ('Add shelf', 'Load more'): not entities
_ACTION_NAME = re.compile(r"^(add|create|new|load|show|hide|toggle|expand|collapse|select|choose|remove|delete|"
                          r"clear|reset|cancel|close|sort|filter|copy|share|print|download|upload|import|export)\b", re.I)


def rule_dead_items(facts: Facts) -> list[Violation]:
    """R03: a list item without a real link while (nearly) all its siblings have one. A 2-item list
    counts too (BookStack's 'Recently Created Shelves' with one shelf and a phantom, BS07, D55 A3):
    the items share their tag and class, so the dead one has its sibling's structure."""
    out = []
    for L in facts.content_lists():
        # an in-page anchor ('#recent-pages') jumps to a section: neither an entity link nor a dead one
        items = [i for i in L["items"] if not re.match(r"^#.+", (i["href"] or "").strip())]
        if len(items) < 2:
            continue
        dead = [i for i in items if i["href"] is not None and _DEAD.match(i["href"].strip())]
        live = len(items) - len(dead)
        if not dead or live < 1 or (len(items) >= 3 and (len(dead) * 3 > len(items) or live < 2)) \
                or (len(items) == 2 and len(dead) != 1):
            continue
        for i in dead:
            if i["name"] and not _GENERIC.match(i["name"].strip()) and not _ACTION_NAME.match(i["name"].strip()):
                out.append(Violation("R03", f"{L['heading']}|{i['name']}",
                                     f"list item {i['name']!r} in {L['heading'] or 'a list'!r} links nowhere "
                                     f"(href {i['href']!r}) while {live} siblings have real links", i["text"]))
    return out


def _unit(s: str) -> str:
    s = norm(s)
    return s[:-1] if s.endswith("s") else s


def rule_counts(facts: Facts) -> list[Violation]:
    """R04: a count shown for a kind of item is below the number of those items listed
    (one-sided, so preview lists and pagination are fine). R04b: 'showing a-b of N'."""
    out = []
    lists = facts.content_lists()
    for c in facts.counts:
        if c.get("nav") or c["n"] > 500:
            continue
        unit = _unit(c["unit"])
        if len(unit) < 3:
            continue
        for L in lists:
            words = {_unit(w) for w in re.findall(r"[A-Za-z]+", L["heading"] or "")}
            own = norm(c["text"]) and norm(c["text"]) in norm(L["heading"] or "")
            if own:
                # the count heads this list ('3 total results found', D55 A4), unless the heading holds several
                # counts or the items are counts: then it is a summary block ('6 Pages 4 Chapters 3 Books', D53)
                if len(re.findall(r"\d[\d,]*", L["heading"] or "")) != 1 or \
                        any(re.match(r"^\d[\d,]*\s+\w", i["name"] or "") for i in L["items"]):
                    continue
            elif unit not in words:
                continue
            # distinct items by name and link: two results both named 'Book...' are two (BookStack search)
            names = {(norm(i["name"]), i.get("href") or "") for i in L["items"] if i["name"]}
            if len(names) > c["n"]:
                out.append(Violation("R04", f"{L['heading']}|{unit}",
                                     f"{c['text']!r} but {len(names)} {c['unit']} are listed under {L['heading']!r}",
                                     "; ".join(sorted(n for n, _ in names))[:300]))
    s = facts.showing
    m = facts.main_list()
    if s and m and s["b"] >= s["a"] and s["b"] <= s["n"]:
        shown = s["b"] - s["a"] + 1
        if shown <= 100 and len(m["items"]) not in (shown,) and abs(len(m["items"]) - shown) >= 1:
            out.append(Violation("R04b", f"showing|{m['heading']}",
                                 f"'showing {s['a']}-{s['b']} of {s['n']}' but {len(m['items'])} items are listed"))
    return out


_NUM = re.compile(r"[-+(]?\s*[^\d\s-]{0,3}\s*\d[\d.,' ]*\d|\d")


def parse_money(s: str) -> float | None:
    """'$1,234.56', '1.234,56 €', '(12.00)', '-3' -> float; None if no number."""
    if not s:
        return None
    m = re.search(r"\d[\d.,' ]*", s)
    if not m:
        return None
    raw = m.group(0).strip().replace("'", "").replace(" ", "")
    neg = "(" in s[:m.start() + 1] or re.search(r"-\s*[^\d\s]{0,3}\s*$", s[:m.start()]) is not None
    if "," in raw and "." in raw:
        dec = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in raw:
        parts = raw.split(",")
        raw = raw.replace(",", ".") if len(parts) == 2 and len(parts[1]) in (1, 2) else raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        v = float(raw.rstrip("."))
    except ValueError:
        return None
    return -v if neg else v


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.011, 0.005 * max(abs(a), abs(b)))


def rule_arithmetic(facts: Facts) -> list[Violation]:
    """R06: qty x unit price = line total in tables; total = subtotal + tax + shipping + fees - discount."""
    out = []
    lines_sum = None
    for t in facts.tables:
        head = [norm(h) for h in t["head"]]
        if not head:
            continue
        qi = next((i for i, h in enumerate(head) if re.search(r"\b(qty|quantity|units?|hours?)\b", h)), None)
        pi = next((i for i, h in enumerate(head) if re.search(r"\b(unit price|price|rate|unit cost|cost)\b", h)
                   and not re.search(r"total", h)), None)
        ti = next((i for i in range(len(head) - 1, -1, -1) if re.search(r"\b(total|amount|line total|sum)\b", head[i])
                   and i not in (qi, pi)), None)
        if qi is None or pi is None or ti is None:
            continue
        s, n = 0.0, 0
        for r in t["rows"]:
            if len(r) <= max(qi, pi, ti):
                continue
            q, p, tot = parse_money(r[qi]), parse_money(r[pi]), parse_money(r[ti])
            if q is None or p is None or tot is None:
                continue
            n += 1
            s += tot
            if not _close(q * p, tot) and not _close(round(q * p, 2), tot):
                out.append(Violation("R06", f"line|{r[0][:40]}",
                                     f"line {r[0][:40]!r}: {r[qi]} x {r[pi]} = {q * p:.2f}, but the line total is {r[ti]}"))
        if n:
            lines_sum = s
    vals: dict[str, float] = {}
    for x in facts.totals:
        lab = norm(x["label"])
        v = parse_money(x["value"])
        if v is None:
            continue
        key = ("subtotal" if re.match(r"sub-?total", lab) else "total" if re.match(r"(grand |order )?total|amount due|balance due", lab)
               else "tax" if re.match(r"tax|vat|gst|sales tax", lab) else "shipping" if re.match(r"shipping|delivery|postage", lab)
               else "discount" if re.match(r"discount|coupon|promo", lab) else "fee" if re.match(r"fee", lab) else None)
        if key and key not in vals:
            vals[key] = v
            if key == "tax" and "incl" in lab:
                vals["tax_incl"] = 1
    if "total" in vals and ("subtotal" in vals or lines_sum is not None):
        sub = vals.get("subtotal", lines_sum)
        tax, ship, fee, disc = vals.get("tax", 0), vals.get("shipping", 0), vals.get("fee", 0), abs(vals.get("discount", 0))
        combos = [sub + tax + ship + fee - disc, sub + ship + fee - disc, sub + tax + fee - disc, sub + tax + ship + fee,
                  sub + ship - disc, sub - disc, sub]
        if not any(_close(c, vals["total"]) for c in combos):
            out.append(Violation("R06", "total", f"total {vals['total']:.2f} does not add up: subtotal {sub:.2f}, "
                                 f"tax {tax:.2f}, shipping {ship:.2f}, fees {fee:.2f}, discount {disc:.2f}"))
    if lines_sum is not None and "subtotal" in vals and not _close(lines_sum, vals["subtotal"]):
        out.append(Violation("R06", "subtotal", f"line totals sum to {lines_sum:.2f}, subtotal shows {vals['subtotal']:.2f}"))
    return out


_MOJIBAKE = re.compile(r"Ã[\u0080-¿©¨¼¶§±]|â€[™œ\u009d“”˜¦]")


def rule_echo(facts: Facts) -> list[Violation]:
    """R12: markup the agent typed is rendered as HTML (not escaped); garbled accents."""
    out = [Violation("R12", f"markup|{v[:40]}", f"typed markup {v[:60]!r} is rendered as HTML, not shown as text")
           for v in facts.rendered]
    m = _MOJIBAKE.search(facts.plain or "")
    if m:
        out.append(Violation("R12", "mojibake", "garbled characters (encoding)",
                             (facts.plain or "")[max(0, m.start() - 40):m.end() + 40]))
    return out


def same_name(a: str, b: str) -> bool:
    """Two names of the same thing: equal, one contains the other (when the shorter is specific:
    2+ words or 8+ characters, so 'Book' is not 'Atlas Book Q7'), or half their words shared."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    ta, tb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
    if short in long_ and (len(short) >= 8 or len(re.findall(r"\w+", short)) >= 2):
        return True
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.5


def shown(obj: str, text: str) -> bool:
    """The typed value is on the page: as typed, or with its markup rendered ('<b>Name</b>' shows as 'Name')."""
    o, t = norm(obj), norm(text)
    if not o:
        return False
    plain = norm(re.sub(r"<[^>]{0,200}>", "", obj))
    return o in t or (len(plain) >= 3 and plain != o and plain in t)


def item_matches(item: dict, name: str, key: str) -> bool:
    return (key and item.get("abs") and entity_key(item["abs"]) == key) or same_name(item.get("name", ""), name) \
        or (name and norm(name) in norm(item.get("text", "")))


def diff_lists(prev: list, now: list) -> tuple[list, list]:
    pk = [(norm(n), h) for n, h in prev]
    nk = [(norm(n), h) for n, h in now]
    added = [x for x in now if (norm(x[0]), x[1]) not in pk]
    removed = [(i, x) for i, x in enumerate(prev) if (norm(x[0]), x[1]) not in nk]
    return added, removed


_PRIOR = re.compile(r'value="([^"]+)"')


def explained(events: list[Event], name: str, href: str) -> bool:
    """Some recorded action (any worker's) is about this item: its link's entity, its name among the
    typed values, or, for an edit, the value a field held before (a renamed shelf's old name, D55 P3)."""
    key = entity_key(href) if href else ""
    for e in events:
        if key and e.target and e.target == key:
            return True
        cands = [e.obj, *e.fields.values()]
        if e.verb in ("edit", "delete"):
            cands += [m.group(1) for k in e.fields for m in [_PRIOR.search(k)] if m]
        if any(c and same_name(c, name) for c in cands):
            return True
    return False


def age_conflict(a: float, b: float, dt_min: float) -> bool:
    """Two ages of the same thing disagree: ratio over 3 and the gap beyond what time passing explains."""
    a, b = max(a, 0.5), max(b, 0.5)
    return abs(math.log(a / b)) > math.log(3) and abs(a - b) > max(60.0, 2 * dt_min)


_SYSTEM_ERR = re.compile(r"something went wrong|unknown error|an error (has )?occurred|unexpected error|internal (server )?error|"
                         r"could not|couldn't|failed to|unable to|try again later|service unavailable|server error", re.I)
_LOGINISH = re.compile(r"log-?in|sign-?in|auth", re.I)
_VALIDATION = re.compile(r"is required|are required|must be|must have|must contain|is invalid|not valid|invalid|"
                         r"already (been )?taken|already exists|too (short|long)|at least \d|at most \d|please (enter|provide|"
                         r"fill|select|choose)|does not match|do not match|can'?t be (blank|empty)|cannot be (blank|empty)|"
                         r"field is|not allowed|format", re.I)
NOT_A_NAME = re.compile(r"e-?mail|password|search|query|phone|tel\b|url|website|date|time|code|zip|postal|number|"
                        r"amount|price|quantity|token|captcha", re.I)
_LOGIN_CONTROL = re.compile(r"^(sign in|log in|login)$", re.I)
_SECRET = re.compile(r"password|passcode|secret", re.I)


# ---------------------------------------------------------------------------- R13: edit addresses
def id_segments(url: str) -> list[str]:
    """The path segments route_shape turns into '*' (the item's ids or slugs), in order."""
    segs = [s for s in urlsplit(url).path.split("/") if s]
    shape = [s for s in route_shape(url).split("?")[0].split("#")[0].split("/") if s]
    return [s for s, k in zip(segs, shape) if k == "*"] if len(segs) == len(shape) else []


def edit_template(page_url: str, edit_url: str) -> tuple[str, str] | None:
    """How an item's edit address is made from its page address: the edit path with the page's id
    segments as {0}, {1}, ... ('/article/how-to-x' + '/editor/how-to-x' -> '/editor/{0}'), and the
    edit page's route shape. None when the edit link uses none of the page's ids (it edits
    something else, e.g. a comment)."""
    p, e = urlsplit(page_url), urlsplit(edit_url)
    if (p.scheme, p.netloc) != (e.scheme, e.netloc):
        return None
    ids = id_segments(page_url)
    esegs = [s for s in e.path.split("/") if s]
    if not ids or not any(s in ids for s in esegs):
        return None
    path = "/" + "/".join("{%d}" % ids.index(s) if s in ids else s for s in esegs)
    return path + (f"?{e.query}" if e.query else ""), route_shape(edit_url)


def apply_template(template: str, page_url: str) -> str | None:
    ids = id_segments(page_url)
    out = template
    for i, v in enumerate(ids):
        out = out.replace("{%d}" % i, v)
    if re.search(r"\{\d+\}", out):
        return None
    u = urlsplit(page_url)
    return f"{u.scheme}://{u.netloc}{out}"


# ---------------------------------------------------------------------------- G2: reload invariance
_VOLATILE_HEAD = re.compile(r"random|suggest|recommend|trending|you may|for you|sponsored|\bads?\b", re.I)


def view_diff(a: Facts, b: Facts, events: list[Event], volatile: set) -> list[Violation]:
    """G2: page `a` as the worker saw it vs `b`, the same URL opened again in a fresh tab right after,
    with no write by this worker in between. Compares the heading, the items of lists with the same
    heading (as sets: order may change) and counts with a unit shown once on both. `events`: what
    any worker did meanwhile (explains changes). A list that changes by more than half is marked
    volatile in `volatile` (rotating content) and skipped from then on."""
    route, out = route_shape(a.url), []
    if a.h1 and b.h1 and not same_name(a.h1, b.h1):
        out.append(Violation("G2", "h1", f"opening {route} again shows the heading {b.h1!r}, not {a.h1!r}"))
    la = {norm(L["heading"]): L for L in a.content_lists() if L["heading"]}
    lb = {norm(L["heading"]): L for L in b.content_lists() if L["heading"]}
    for h in sorted(la.keys() & lb.keys()):
        if (route, h) in volatile or _VOLATILE_HEAD.search(h):
            continue
        A, B = la[h]["items"], lb[h]["items"]
        if len(A) >= 60 or len(B) >= 60:  # AUDIT_JS keeps 60 items: a longer list is cut
            continue
        na = {norm(i["name"]): i for i in A if i["name"]}
        nb = {norm(i["name"]): i for i in B if i["name"]}
        added = [nb[k]["name"] for k in nb.keys() - na.keys() if not explained(events, nb[k]["name"], nb[k].get("abs", ""))]
        removed = [na[k]["name"] for k in na.keys() - nb.keys() if not explained(events, na[k]["name"], na[k].get("abs", ""))]
        if not added and not removed:
            continue
        if (len(added) + len(removed)) * 2 > max(len(na), len(nb)):
            volatile.add((route, h))
            continue
        head = la[h]["heading"]
        for x in sorted(added)[:3]:
            out.append(Violation("G2", f"{head}|+{x}", f"opening {route} again adds {x!r} to {head!r}, and no "
                                 "action explains it"))
        for x in sorted(removed)[:3]:
            out.append(Violation("G2", f"{head}|-{x}", f"opening {route} again drops {x!r} from {head!r}, and no "
                                 "action explains it"))
    if not events:
        def once(f: Facts) -> dict:
            units = [_unit(c["unit"]) for c in f.counts if not c.get("nav")]
            return {_unit(c["unit"]): c for c in f.counts if not c.get("nav") and units.count(_unit(c["unit"])) == 1}
        ca, cb = once(a), once(b)
        for u in sorted(ca.keys() & cb.keys()):
            if ca[u]["n"] != cb[u]["n"] and len(u) >= 3:
                out.append(Violation("G2", f"count|{u}", f"opening {route} again shows {cb[u]['text']!r}, not "
                                     f"{ca[u]['text']!r}"))
    return out


# ---------------------------------------------------------------------------- R16/R17: input mutation
MUTATIONS = ("empty", "blank", "long")
_DESC = {"empty": "an empty value", "blank": "only spaces", "long": "a value of {n} characters"}


def field_label(d: dict) -> str:
    """A filled field's name, from its element key (tag|type|role|text|label|href)."""
    parts = (d.get("ekey") or "").split("|")
    return (parts[4] if len(parts) > 4 and parts[4] else parts[3] if len(parts) > 3 and parts[3] else parts[0])[:40]


def long_value(base: str, n: int) -> str:
    """`n` characters starting with the agent's own value (so the item stays recognisable)."""
    pad = (base or "") + " " + "abcdefghij" * (n // 10 + 1)
    return pad[:n]


def mutation_plan(done: list[dict], obj: str) -> tuple[dict, dict] | None:
    """For a one-step create form: (field that names the new item, field for the long value), or None
    when the step is not a form the harness may submit again: no fills, no final click/press, a
    password field (registration, login: a second submit could switch the worker's account) or a
    search box."""
    fills = [d for d in done if d["do"] in ("fill", "type") and d.get("ekey")]
    last = done[-1] if done else {}
    if not fills or last.get("do") not in ("click", "press") or not last.get("ekey"):
        return None
    if any("|password|" in d["ekey"] or _SECRET.search(d.get("el") or "") or SEARCH_FIELD.search(d.get("el") or "")
           for d in fills):
        return None
    name = next((d for d in fills if obj and d["value"] == obj), None) or \
        next((d for d in fills if TITLE_FIELD.search(field_label(d))), None) or fills[0]
    long_ = next((d for d in fills if d["ekey"].startswith("textarea|")), None) or name
    return name, long_


# ---------------------------------------------------------------------------- the sweeper
class SweepState:
    """Shared by all workers of a run (or of one replay): memory, graph, probe caches."""

    def __init__(self, graph=None):
        self.memory = RunMemory()
        self.graph = graph
        self.link_status: dict[str, int] = {}
        self.search_done: set[str] = set()
        self.nav_reported: set[tuple] = set()
        self.probes = 0
        self.link_checks = 0
        # R13 (per worker, so a gate replay of one worker's log rebuilds what it needs)
        self.edit_templates: dict[tuple, tuple[str, str]] = {}  # (worker, page shape) -> (template, edit shape)
        self.edit_ok: set[tuple] = set()  # (worker, edit shape): an edit address of this kind opened a form
        self.edit_refused: dict[tuple, list] = {}  # (worker, edit shape) -> refusals waiting for edit_ok
        self.access_done: set[tuple] = set()  # (worker, entity key)
        self.access_probes: dict[int, int] = {}
        # G2
        self.reload_done: set[tuple] = set()  # (worker, route shape)
        self.volatile_views: set[tuple] = set()  # (route shape, list heading)
        self.reloads = 0
        # R16/R17
        self.mutated: set[tuple] = set()  # (form route shape, naming field key)
        self.mutation_forms = 0
        self.mutation_submits = 0
        # R07c, R19
        self.feed_done: set[tuple] = set()  # (worker, list key)
        self.feed_probes = 0
        self.toggle_done: set[str] = set()  # route shapes whose count controls were probed
        self.toggle_probes = 0
        self.markup_ok: set[str] = set()  # values typed into Markdown/rich-text fields


INTENT_VERBS = {"create": "create", "add": "create", "new": "create", "post": "create", "publish": "create",
                "register": "create", "write": "create", "comment": "create", "edit": "edit", "update": "edit",
                "change": "edit", "rename": "edit", "save": "save", "submit": "save", "delete": "delete",
                "remove": "delete", "favourite": "favourite", "favorite": "favourite", "star": "favourite",
                "bookmark": "favourite", "like": "like", "unfavourite": "unfavourite", "unfavorite": "unfavourite",
                "unstar": "unfavourite", "unlike": "unlike", "follow": "follow", "subscribe": "follow",
                "unfollow": "unfollow", "unsubscribe": "unfollow", "search": "search", "filter": "filter",
                "logout": "logout", "log out": "logout", "login": "login", "log in": "login", "view": "view",
                "open": "view"}
WRITE_VERBS = ("create", "edit", "delete", "add", *TOGGLES, *OFF)


class Sweeper:
    """One worker's view: hooks before and after each step's actions."""

    def __init__(self, state: SweepState, worker: int, account=None, llm_rules: bool = True):
        self.st = state
        self.mem = state.memory
        self.worker = worker
        self.account = account
        self.llm_rules = llm_rules
        self.pre: dict | None = None
        self.post: dict | None = None
        self.writes: list[dict] = []  # this step's write requests (method, path, status)
        self.last: Facts | None = None
        self.pages: list[tuple[str, str]] = []  # (route, h1) per observation, for the back-button rule
        self.flow_start = ""  # URL where the current create flow began (the 'New ...' click)
        self.account_pages: list[str] = []  # URLs that showed this worker's account name
        self.budget = MAX_PROBES
        self.t_before = time.time()  # when the step's actions began (G2: events since then explain changes)
        self.feed_todo: list[tuple[str, list]] = []  # R07c: follow feeds seen this step
        self.net_mark = 0  # v5 evidence layer (D58): network timeline position when the step began

    # ---------- before and right after the actions ----------
    async def before(self, session, obs: Observation, actions: list[dict]) -> None:
        from playwright.async_api import Error as PWError

        clicks = [a for a in actions if a["do"] == "click" and a.get("id")]
        fills = [a for a in actions if a["do"] in ("fill", "select") and a.get("id")]
        ids = {"click": clicks[-1]["id"] if clicks else None, "fill": fills[0]["id"] if fills else None}
        session.mutations.clear()
        self.t_before = time.time()
        if getattr(session, "evidence", False):  # D58: this step's responses and messages only
            self.net_mark = session.net_mark()
            await session.drain_messages()
        try:
            self.pre = await session.page.evaluate(PRE_JS, ids)
        except PWError:
            self.pre = None

    async def actions_done(self, session) -> None:
        """Read the marked control again and take the step's write requests."""
        from playwright.async_api import Error as PWError

        try:
            self.post = await session.page.evaluate(POST_JS)
        except PWError:
            self.post = None
        self.writes = list(session.mutations)

    # ---------- after the actions ----------
    async def after(self, session, obs: Observation, done: list[dict], step: int, intent: dict | None = None,
                    suspect: dict | None = None) -> list[Signal]:
        mem = self.mem
        self.budget = MAX_PROBES
        if not self.writes and any(d["do"] in ("click", "press") for d in done)                 and any(d["do"] in ("fill", "select", "clear") for d in done):
            await _quiet(session.page, 3000)  # a form was submitted: wait for a slow write response
            self.writes = list(session.mutations)
        typed = [d["value"] for d in done if d["do"] in ("fill", "select") and d.get("value")]
        mem.typed.update(t for t in typed if t and t.strip())
        self.st.markup_ok.update(d["value"] for d in done if d["do"] == "fill" and d.get("value")
                                 and _RICH_FIELD.search(d.get("el") or ""))
        facts = await audit(session, sorted(mem.typed - self.st.markup_ok))
        url = facts.url or session.page.url
        mem.remember_page(self.worker, url, facts.text)
        if self.account and self.account.username and self.account.username.lower() in facts.text.lower():
            self.account_pages = (self.account_pages + [url])[-5:]
        accepted = [m for m in self.writes if 200 <= m["status"] < 400]
        if accepted:
            for e in mem.pending(self.worker):
                if e.verb in WRITE_VERBS and e.step <= step <= e.due:
                    e.written = True
        viol: list[Violation] = []
        viol += rule_junk(facts.plain, mem.typed)
        viol += rule_dead_items(facts)
        viol += rule_counts(facts)
        viol += rule_arithmetic(facts)
        viol += rule_echo(facts)
        ev = self._event(obs, done, step, intent, facts, url)
        viol += self._effects(ev, facts, done, obs)
        viol += await self._verify_pending(session, facts, step)
        viol += self._lists(facts, step)
        viol += self._ages(facts, step)
        viol += self._link_vs_dest(obs, done, facts)
        viol += self._pagination(done, facts)
        viol += self._back(done, facts)
        if self.llm_rules and suspect:
            viol += self._suspect(suspect, facts)
        viol += await self._probes(session, facts)
        viol += await self._feed_check(session)
        viol += await self._toggle_probe(session, facts)
        viol += await self._mutate(session, obs, done, ev, step)
        viol += await self._access(session, facts)
        viol += await self._reload(session, obs, done, facts)
        if getattr(session, "evidence", False):
            viol += await self._evidence(session)
        self.last = facts
        self.pages = (self.pages + [(route_shape(url), facts.h1)])[-6:]
        return [signal_of(v, obs.url if v.rule.startswith("I-") else url) for v in viol]

    async def _evidence(self, session) -> list[Violation]:
        """D58: R57 (2xx answers with an error body) and R51 (success and error messages together)."""
        await session.flush_bodies()
        return rule_payload(session.net_since(self.net_mark)) + rule_messages(await session.drain_messages())

    # ---------- M1: what this step did ----------
    def _event(self, obs: Observation, done: list[dict], step: int, intent: dict | None, facts: Facts,
               url: str) -> Event | None:
        mem, pre = self.mem, self.pre or {}
        if not done or not all(d.get("ok", True) for d in done):
            return None
        click_pre = pre.get("click") or {}
        moved = route_shape(url) != route_shape(obs.url)
        clicks = [d for d in done if d["do"] == "click"]
        fills = [d for d in done if d["do"] in ("fill", "select") and d.get("value")]
        last = clicks[-1] if clicks else None
        el_txt = f"{last.get('el') or ''} {click_pre.get('cls') or ''}" if last else ""
        verb, obj, typ, source = "", "", "", "lexicon"
        if intent and INTENT_VERBS.get(str(intent.get("verb", "")).lower().strip()):
            verb = INTENT_VERBS[str(intent["verb"]).lower().strip()]
            obj, typ, source = str(intent.get("object") or ""), str(intent.get("type") or ""), "intent"
        elif last:
            verb = classify(el_txt)
            if verb in TOGGLES and click_pre.get("pressed") == "true":
                verb = TOGGLES[verb]
        accepted = any(200 <= m["status"] < 400 for m in self.writes)
        if verb in (*TOGGLES, *OFF) and click_pre.get("link") and not accepted:
            verb, obj = "", ""  # a link that only navigates ('Favorited Posts' tab) is no toggle (D55 P9)
        if not verb and done[-1]["do"] == "press" and fills:
            verb = "save"
        search_fill = next((d for d in fills if SEARCH_FIELD.search(d.get("el") or "")), None)
        if search_fill and source == "lexicon" and (not last or classify(el_txt) in ("", "save") or "search" in el_txt.lower()):
            verb, obj = "search", search_fill["value"]
        if last and source == "lexicon" and verb in ("", "create", "save"):
            href = _href_of(last)
            q = {k.lower() for k, _ in parse_qsl(urlsplit(href).query)} if href else set()
            if q & {"tag", "tags", "filter", "category", "categories", "topic", "label"} or \
                    re.search(r"/(tags?|categor(y|ies)|topics?|labels?)/", href or "") or \
                    re.search(r"\btag-pill\b|\btag-default\b|\bchip\b", click_pre.get("cls") or ""):
                verb, obj = "filter", click_pre.get("text") or _el_text(last)
        if verb in ("search", "filter") and source == "intent":
            # the term is what was typed or the link clicked, never the model's words or a checkbox label (D55 P7)
            typed_term = next((d["value"] for d in fills if d["do"] == "fill"), "")
            obj = typed_term or (_el_text(last) if last and click_pre.get("link") else "")
        if verb in ("create", "edit", "save") and pre.get("form_password"):
            # an account form (sign in, sign up, reset, password change) creates no content to look for (D55 P1)
            signin = any("password" in (d.get("el") or "").lower() for d in done if d["do"] in ("fill", "type"))
            verb, obj = ("login" if signin else "account"), ""
        if verb == "create" and not fills:
            if not accepted:
                self.flow_start = obs.url  # 'New Book' opens the form: remember where the flow began
                return None
            verb = "add"  # 'Add to cart' and the like: a write without a form
        if verb == "save":
            verb = "edit" if pre.get("prefilled") or re.search(r"/edit\b|/settings", obs.url) else ("create" if fills else "")
        if not verb and moved and "*" in route_shape(url) and facts.h1:
            ent = mem.entity(entity_key(url))
            ent.names[facts.h1] = (self.worker, step, url)
            return mem.add_event(worker=self.worker, step=step, verb="view", obj=facts.h1, target=entity_key(url),
                                 url=url, status="verified")
        if not verb or verb == "view":
            return None
        fields = {}
        for d in fills:
            lab = re.sub(r"^\[\d+\]\s*", "", d.get("el") or "")[:60]
            if "password" not in lab.lower():
                fields[lab] = d["value"]
        if verb in ("create", "edit"):
            # the object is named by what was typed: the model's own words ('special comment', 'session',
            # 'worker02 settings') are not what the app will show (D55 P1, I49)
            title = next((v for k, v in fields.items() if TITLE_FIELD.search(k) and v.strip()), None)
            named = title or next((v for k, v in fields.items() if len(v.strip()) >= 3 and not NOT_A_NAME.search(k)), "")
            if not (obj and any(norm(obj) and norm(obj) in norm(v) for v in fields.values())):
                obj = named
        target = ""
        if verb == "edit" and "*" in route_shape(obs.url):
            # the item an edit form belongs to: '/shelves/shelf/edit' edits '/shelves/shelf' (D55 P3)
            base = re.sub(r"/(edit|update|settings)/?$", "", urlsplit(obs.url).path)
            if base != urlsplit(obs.url).path:
                target = entity_key(base)
        if verb in ("delete", "add", *TOGGLES, *OFF):
            item = click_pre.get("item") or ""
            if not obj and item and norm(item) != norm(facts.h1):
                obj = " ".join(item.split()[:12])
            elif not obj:
                obj = (self.last.h1 if self.last else "") or facts.h1
                target = entity_key(obs.url)
        e = mem.add_event(worker=self.worker, step=step, verb=verb, obj=obj[:120], typ=typ[:40], url=obs.url,
                          target=target, fields=fields, landing=url, source=source, due=step + 2,
                          written=accepted)
        if verb == "delete":
            # the page right before the click; obs.text stops at 4000 characters (D54)
            before = pre.get("page") or (self.last.text if self.last is not None and self.last.url == obs.url
                                         else (obs.text or ""))
            e.before = norm(before).count(norm(e.obj)[:60]) if e.obj else 0
        if verb == "login":
            e.status = "verified"
        return e

    # ---------- intent effects, right after the step ----------
    def _effects(self, e: Event | None, facts: Facts, done: list[dict], obs: Observation) -> list[Violation]:
        if e is None or e.verb in ("view", "login"):
            return []
        out = []
        pre, click_pre = self.pre or {}, (self.pre or {}).get("click") or {}
        accepted = [m for m in self.writes if 200 <= m["status"] < 400]
        rejected = [m for m in self.writes if 400 <= m["status"] < 500]
        moved = route_shape(facts.url) != route_shape(obs.url)
        new_err = [t for t in facts.errors if _SYSTEM_ERR.search(t) and not (self.last and t in self.last.text)]
        before_text = self.last.text if self.last else ""
        validation = not moved and any(_VALIDATION.search(t) and t not in before_text
                                       for t in facts.errors + [ln for ln in facts.text.splitlines() if len(ln) < 160])
        if e.verb in WRITE_VERBS:
            if (rejected and not accepted) or (e.verb in ("create", "edit") and validation and not new_err):
                e.status, e.note = "unknown", "input rejected" + (f" ({rejected[0]['status']})" if rejected else "")
                return out
            if new_err and (accepted or e.verb in ("create", "edit")):
                out.append(Violation("I-error", f"{e.verb}|{new_err[0][:60]}",
                                     f"{e.verb} {e.obj!r}: the app reports {new_err[0][:120]!r}", new_err[0]))
            if not accepted and not moved:
                search_form = any(SEARCH_FIELD.search(k) for k in e.fields) or pre.get("form_get")
                failed = [m for m in self.writes if m["status"] >= 500]
                if e.verb in ("create", "edit") and e.fields and not search_form and facts.url == obs.url \
                        and pre.get("form_valid") is not False and click_pre.get("submit") \
                        and self.last is not None and norm(facts.text) == norm(self.last.text) and not new_err:
                    what = (f"the write failed ({failed[0]['method']} {failed[0]['path']} -> HTTP {failed[0]['status']})"
                            if failed else "nothing was sent") + " and the page did not change"
                    out.append(Violation("I-submit", f"{e.verb}|{e.obj}", f"{e.verb} {e.obj!r}: a valid form was "
                                         f"submitted, but {what}"))
                e.status, e.note = "unknown", "nothing sent"
                return out
        if (e.verb in TOGGLES or e.verb in OFF) and accepted:
            before, after = click_pre.get("number"), (self.post or {}).get("number")
            if e.verb in ("follow", "unfollow") and not (click_pre.get("own_number") and (self.post or {}).get("own_number")):
                before = after = None  # a follow button shows no count; a number beside it is something else (D55 P9)
            if before is not None and after is not None:
                want = 1 if e.verb in TOGGLES else -1
                if after - before != want:
                    e.status = "conflict"
                    return [Violation("I-toggle", f"{e.verb}|count", f"{e.verb} {e.obj!r}: the count on the control "
                                      f"went {before} -> {after}, expected {want:+d}")]
            e.status = "verified"
        if e.verb == "add" and accepted:
            e.status = "verified"
        if e.verb in ("create", "edit") and e.obj and shown(e.obj, facts.text):
            e.status = "verified"
        if e.verb in ("create", "edit") and not e.target and moved:
            e.target = entity_key(facts.url)
        if e.target and e.verb in ("create", "edit"):
            ent = self.mem.entity(e.target)  # R08 compares the item's shown ages with this (D55 A7)
            ent.touched, ent.last_step = e.t, e.step
        return out

    # ---------- pending effects, checked when due ----------
    async def _verify_pending(self, session, facts: Facts, step: int) -> list[Violation]:
        out = []
        for e in self.mem.pending(self.worker):
            if e.verb in ("create", "edit"):
                if e.obj and shown(e.obj, facts.text):
                    e.status = "verified"
                    continue
                if step < e.due or not e.written:
                    if step >= e.due + 3:
                        e.status = "unknown"
                    continue
                if not e.obj:
                    e.status = "unknown"
                    continue
                places = list(dict.fromkeys(u for u in (e.landing, self.flow_start or e.url) if u))[:2]
                if self.budget < len(places):
                    continue
                found = False
                for u in places:
                    text = await self._fresh_text(session, u)
                    if text is None:
                        found = True  # could not load: no evidence against the app
                        break
                    if shown(e.obj, text):
                        found = True
                        break
                e.status = "verified" if found else "conflict"
                if not found:
                    out.append(Violation(f"I-{e.verb}", e.obj, f"{e.verb} {e.obj!r}: the app accepted the write, but "
                                         f"{e.obj!r} is shown neither on the page it led to nor where the flow started",
                                         f"checked: {', '.join(places)}"))
            elif e.verb == "delete":
                if not e.written:
                    if step >= e.due:
                        e.status = "unknown"
                    continue
                if step <= e.step:
                    continue
                needle = norm(e.obj)[:60]
                if len(needle) < 3:
                    e.status = "unknown"
                    continue
                if self.budget < 1:
                    continue
                # Names repeat (a comment's author and date, a title several users chose), so the
                # deleted thing is gone when the address now leads elsewhere or shows it fewer times.
                self.budget -= 1
                self.st.probes += 1
                opened = await _open(session, e.url)
                if opened is None:
                    gone = True
                else:
                    try:
                        fresh = await audit(session, page=opened[0])
                    finally:
                        await opened[0].close()
                    n = norm(fresh.text).count(needle)
                    gone = (not fresh.url or route_shape(fresh.url) != route_shape(e.url) or n == 0
                            or (e.before > 0 and n < e.before))
                e.status = "verified" if gone else "conflict"
                if not gone:
                    out.append(Violation("I-delete", e.obj, f"deleted {e.obj!r} (the app accepted the write), but it "
                                         f"is still shown when {e.url} is opened again"))
            elif e.verb in ("search", "filter"):
                out += await self._filter_check(session, e, facts)
            elif e.verb == "logout":
                out += await self._logout_check(session, e)
            elif step >= e.due:
                e.status = "unknown"
        return out

    async def _filter_check(self, session, e: Event, facts: Facts) -> list[Violation]:
        e.status = "verified"
        term = norm(re.sub(r"^#", "", e.obj or ""))
        m = facts.main_list()
        if len(term) < 2 or not m:
            return []
        furniture = {norm(i["name"]) for L in (self.last.content_lists() if self.last else []) for i in L["items"]} \
            if e.verb == "search" else set()
        words = [w for w in re.findall(r"\w+", term) if len(w) >= 3] if e.verb == "search" else [term]
        if not words:
            return []

        def has(t: str) -> bool:
            t = norm(t)
            return any(w in t for w in words)

        misses = [i for i in m["items"] if norm(i["name"]) not in furniture and not has(i["text"])]
        for i in misses[:2]:
            if not i.get("abs") or not session.in_scope(i["abs"]) or self.budget < 1:
                continue
            text = await self._fresh_text(session, i["abs"])
            if text is not None and not has(text):
                e.status = "conflict"
                return [Violation("I-filter", f"{e.verb}|{term}", f"{e.verb} for {e.obj!r} lists {i['name']!r}, which "
                                  f"does not contain {e.obj!r}, not even on its own page", i["text"])]
        return []

    async def _logout_check(self, session, e: Event) -> list[Violation]:
        e.status = "verified"
        if not self.account or not self.account.username or not self.account_pages:
            return []
        u = self.account_pages[-1]
        st, text = await self._fetch(session, u)
        name = self.account.username.lower()
        if st is not None and st < 400 and text and name in text.lower() and \
                not re.search(r"log ?in|sign ?in", text[:20000], re.I):
            e.status = "conflict"
            return [Violation("I-logout", u, f"after logout, {u} still shows the account {self.account.username!r}")]
        return []

    # ---------- M3: lists against memory ----------
    def _lists(self, facts: Facts, step: int) -> list[Violation]:
        mem, out = self.mem, []
        for L in facts.content_lists():
            items = [(i["name"], entity_key(i["abs"]) if i.get("abs") else "") for i in L["items"] if i["name"]]
            info, prev = mem.snapshot(facts.url, L["heading"], items, self.worker, step)
            # R07: what this worker turned on must be in the list for it.
            if info.category in ("favourite", "follow") and info.personal:
                on = mem.net_toggle(self.worker, info.category)
                recent_only = len(items) >= 8
                for k, ev in on.items():
                    if ev.status != "verified" or (recent_only and step - ev.step > 10):
                        continue
                    if not any(item_matches(i, ev.obj, ev.target) for i in L["items"]):
                        out.append(Violation("R07", f"{info.category}|{ev.obj}", f"{ev.obj!r} was {info.category}d "
                                             f"(step {ev.step}) but is missing from {L['heading']!r}"))
                for ent in mem.entities.values():
                    tg = ent.toggles.get(info.category)
                    if not tg or not tg[0] or tg[1] != self.worker or step - tg[2] > 15 or recent_only:
                        continue
                    name = next(iter(ent.names), "")
                    if name and not any(item_matches(i, name, ent.key) for i in L["items"]):
                        out.append(Violation("R07b", f"{info.category}|{name}", f"{name!r} shows as {info.category}d on "
                                             f"its page (step {tg[2]}) but is missing from {L['heading']!r}"))
            # R09: a list changed on a revisit with nothing to explain it.
            if prev is None or info.volatile or prev.step == step:
                continue
            added, removed = diff_lists(prev.items, items)
            if not added and not removed:
                continue
            if any(e.verb in ("login", "logout") and e.worker == self.worker and e.step >= prev.step for e in mem.events):
                continue  # the session changed between the two visits: every list may differ
            evs = mem.events_since(prev.event_idx, self.worker if info.personal else None)
            ua = [a for a in added if not explained(evs, a[0], a[1]) and not (info.recency and evs)
                  and not EVENT_FEED.search(L["heading"] or "")]
            ur = []
            for idx, r in removed:
                if EVENT_FEED.search(L["heading"] or ""):
                    continue  # new entries push old ones out of an activity feed (D55 P3; 6 BookStack false alarms)
                if explained([e for e in evs if e.verb in ("delete", "edit", "unfavourite", "unfollow", "unlike")], r[0], r[1]):
                    continue
                tail = all((norm(x[0]), x[1]) not in {(norm(n), h) for n, h in items} for x in prev.items[idx:])
                if info.recency and tail and len(added) >= len(removed):
                    continue
                if not info.recency and evs and len(prev.items) >= 10:
                    continue  # long lists shift between pages when anything changed
                ur.append(r)
            churn = len(ua) + len(ur)
            if churn and churn * 2 > max(len(items), len(prev.items)):
                info.volatile = True
                continue
            for a in ua:
                out.append(Violation("R09", f"{L['heading']}|+{a[0]}", f"{a[0]!r} appeared in {L['heading'] or 'a list'!r} "
                                     f"(revisit at step {step}, last seen step {prev.step}) and no action explains it"))
            for r in ur:
                out.append(Violation("R09", f"{L['heading']}|-{r[0]}", f"{r[0]!r} disappeared from {L['heading'] or 'a list'!r} "
                                     f"(revisit at step {step}, last seen step {prev.step}) and no action explains it"))
        # R07c: a feed of what this account follows, to be checked against the authors' pages (D55 A9)
        for L in facts.content_lists():
            if FOLLOW_FEED.search(L["heading"] or "") and L["items"]:
                k = (self.worker, list_key(facts.url, L["heading"]))
                if k not in self.st.feed_done:
                    self.st.feed_done.add(k)
                    self.feed_todo.append((L["heading"], L["items"][:2]))
        # observed toggle states on this page (the viewer's own favourite/follow state)
        here = entity_key(facts.url)
        for t in facts.toggles:
            v = classify(t)
            if v in OFF and facts.h1:
                ent = mem.entity(here)
                ent.names.setdefault(facts.h1, (self.worker, step, facts.url))
                ent.toggles[OFF[v]] = (True, self.worker, step)
        return out

    def _ages(self, facts: Facts, step: int) -> list[Violation]:
        """R08: ages of the same item across pages, and of items an agent just touched. R18: time order
        of one item: nothing about it is older than its creation, and its 'updated' age is not older
        than an update entry in an activity feed (D55 A6; BookStack BS09-BS11). An activity entry
        ('Admin created page Page 1 15 hours ago') is about its object link, not its author (A5)."""
        mem, out, now = self.mem, [], time.time()
        page = entity_key(facts.url)
        for t in facts.times:
            minutes = age_minutes(t["text"])
            if minutes is None:
                continue
            kind = age_kind(t["context"])
            if kind == "other" and t.get("item_text"):
                kind = age_kind(t["item_text"])
            feed = bool(EVENT_FEED.search(t.get("list") or "")) or bool(t.get("by_person"))
            item = t["item"]
            name = t.get("item_name") or ""
            if item and name and re.search(r"\bby\s+" + re.escape(name), t["context"], re.I):
                item = ""  # 'Created 2 days ago by Admin': the link is the author, not the item
            if item and _PERSON.search(entity_key(item)) and not re.search(r"joined|registered|member since",
                                                                           t["context"], re.I):
                item = ""  # a time next to a person's link (a comment's author) is not the person's age
            if not item and "*" not in route_shape(facts.url):
                continue  # a time on a list page that belongs to no list item: we cannot tell whose it is
            key = entity_key(item) if item else page
            if minutes < 0 and kind in ("created", "updated"):
                out.append(Violation("R08", f"future|{key}", f"{kind} time in the future: {t['context'][:80]!r}"))
                continue
            ent = mem.entities.get(key) or mem.entity(key)
            if ent.touched:
                since = (now - ent.touched) / 60
                last_ev = next((e for e in reversed(mem.events) if e.target == key and e.verb in ("create", "edit")), None)
                # what the run created or changed minutes ago cannot read days old (created: own creates only)
                ok_kind = kind in ("updated", "other") or (kind == "created" and last_ev is not None and last_ev.verb == "create")
                if ok_kind and last_ev and last_ev.status == "verified" and minutes > since + 60 \
                        and age_conflict(minutes, since, 0):
                    out.append(Violation("R08", f"touched|{key}|{kind}", f"{t['context'][:80]!r}, but an agent "
                                         f"{'created' if last_ev.verb == 'create' else 'changed'} it {since:.0f} min ago "
                                         f"(step {last_ev.step})", t.get("item_text") or t["context"]))
            for (k2, p2, f2), (m2, txt2, w2, s2, t2) in list(ent.ages.items()):
                then = m2 + (now - t2) / 60  # that age, as of now
                dt = (now - t2) / 60
                if p2 == page and f2 == feed:
                    continue
                if k2 == kind == "created" and age_conflict(minutes, then, dt):
                    out.append(Violation("R08", f"views|{key}|created", f"the same item shows created {t['text']!r} "
                                         f"here but {txt2!r} on {p2} (step {s2})", t.get("item_text") or t["context"]))
                    break
                if k2 == kind == "updated" and not feed and not f2 and p2 != page and age_conflict(minutes, then, dt):
                    out.append(Violation("R08", f"views|{key}|updated", f"the same item shows updated {t['text']!r} "
                                         f"here but {txt2!r} on {p2} (step {s2})", t["context"]))
                    break
                # R18: older than its own creation
                if k2 == "created" and kind != "created" and (feed or kind == "updated") and minutes > then \
                        and age_conflict(minutes, then, dt):
                    out.append(Violation("R18", f"before-created|{key}", f"{t['text']!r} ({kind}"
                                         f"{', activity' if feed else ''}) is older than the item itself, created "
                                         f"{txt2!r} on {p2} (step {s2})", t.get("item_text") or t["context"]))
                    break
                if kind == "created" and k2 != "created" and (f2 or k2 == "updated") and then > minutes \
                        and age_conflict(minutes, then, dt):
                    out.append(Violation("R18", f"before-created|{key}", f"{txt2!r} ({k2} on {p2}, step {s2}) is "
                                         f"older than the item itself, created {t['text']!r} here",
                                         t.get("item_text") or t["context"]))
                    break
                # R18: the last update is not older than an update the activity feed shows
                if kind == k2 == "updated" and feed != f2:
                    last, entry = (minutes, then) if not feed else (then, minutes)
                    if last > entry and age_conflict(last, entry, dt):
                        out.append(Violation("R18", f"stale-updated|{key}", f"the item reads updated "
                                             f"{(t['text'] if not feed else txt2)!r}, but an activity entry shows an "
                                             f"update {(txt2 if not feed else t['text'])!r}", t.get("item_text") or t["context"]))
                        break
            ent.ages[(kind, page, feed)] = (minutes, t["text"], self.worker, step, now)
        return out

    def _link_vs_dest(self, obs: Observation, done: list[dict], facts: Facts) -> list[Violation]:
        """R10: a list item's name against the heading of the page its link opened."""
        if len(done) != 1 or done[0]["do"] != "click" or not self.last or not facts.h1:
            return []
        href = _href_of(done[0])
        if not href or _DEAD.match(href):
            return []
        dest = urljoin(obs.url, href)
        if route_shape(facts.url) == route_shape(obs.url) or _SEARCH_DEST.search(dest) or _SEARCH_DEST.search(facts.url):
            return []  # a tag or search link opens results, titled 'Search Results' by design (D55 P6)
        for L in self.last.content_lists():
            for i in L["items"]:
                if i.get("abs") and entity_key(i["abs"]) == entity_key(dest) and i["name"] and not _GENERIC.match(i["name"]):
                    names = [i["name"], i.get("link_text") or ""]
                    if not any(n and (same_name(n, facts.h1) or same_name(n, facts.title)) for n in names):
                        return [Violation("R10", f"{i['name']}", f"the link {i['name']!r} in {L['heading'] or 'a list'!r} "
                                          f"opens a page titled {facts.h1!r}")]
                    return []
        return []

    def _pagination(self, done: list[dict], facts: Facts) -> list[Violation]:
        """R11: a page-number / next control that leaves the main list unchanged."""
        if len(done) != 1 or done[0]["do"] != "click" or not self.last:
            return []
        txt = _el_text(done[0])
        if not re.fullmatch(r"\d{1,3}|next|›|»|>|next page|older|newer", txt.strip().lower()):
            return []
        if (self.pre or {}).get("click", {}) and "active" in (done[0].get("el") or ""):
            return []
        if not ((self.pre or {}).get("click") or {}).get("pager"):
            return []  # a number outside a pager is a count (Conduit's favourite button '0', D55 P4)
        a, b = self.last.main_list(), facts.main_list()
        if not a or not b or len(a["items"]) < 3:
            return []
        if [norm(i["name"]) for i in a["items"]] == [norm(i["name"]) for i in b["items"]]:
            return [Violation("R11", f"page|{txt}", f"clicking page control {txt!r} left the list "
                              f"{a['heading'] or ''!r} unchanged ({len(a['items'])} items)")]
        return []

    def _back(self, done: list[dict], facts: Facts) -> list[Violation]:
        """G1: back returns to the page before the last move (not after a form submit)."""
        if len(done) != 1 or done[0]["do"] != "back" or len(self.pages) < 2:
            return []
        want_route, want_h1 = self.pages[-2]
        got = route_shape(facts.url)
        if self.mem.events and self.mem.events[-1].worker == self.worker and self.mem.events[-1].verb in ("create", "edit", "delete"):
            return []
        if got != want_route and not _LOGINISH.search(got):
            return [Violation("G1", f"{want_route}->{got}", f"back went to {got}, not to the previous page {want_route}")]
        return []

    def _suspect(self, s: dict, facts: Facts) -> list[Violation]:
        """R15: a contradiction the model cites, kept only when both quotes are really on pages it saw."""
        a, b = str(s.get("a", "")).strip(), str(s.get("b", "")).strip()
        if len(a) < 3 or len(b) < 3 or norm(a) == norm(b):
            return []
        texts = [facts.text] + [t for _, t in self.mem.page_text.get(self.worker, [])]
        if any(norm(a) in norm(t) for t in texts) and any(norm(b) in norm(t) for t in texts):
            return [Violation("R15", f"{a[:40]}|{b[:40]}", f"cited contradiction: {a[:80]!r} vs {b[:80]!r}: "
                              f"{str(s.get('why', ''))[:120]}")]
        return []

    # ---------- probes in fresh tabs / requests ----------
    async def _probes(self, session, facts: Facts) -> list[Violation]:
        out = []
        checks = 0
        for L in facts.content_lists():
            for i in L["items"]:
                u = i.get("abs") or ""
                if checks >= MAX_LINK_CHECKS or not u or _DEAD.match(i["href"] or "") or not session.in_scope(u):
                    continue
                if re.search(r"log-?out|sign-?out|delete|remove|destroy|toggle|favou?rite|follow|like|export|download|"
                             r"action=|/api/", u, re.I):
                    continue
                k = entity_key(u)
                if k in self.st.link_status:
                    continue
                if any(e.target == k and e.verb in ("edit", "delete") for e in self.mem.events):
                    continue  # renamed (old slug) or deleted by an agent: a 404 is right (D55 P3)
                st, _ = await self._fetch(session, u, body=False)
                checks += 1
                self.st.link_checks += 1
                self.st.link_status[k] = st or 0
                if st is not None and (st in (404, 410) or st >= 500):
                    out.append(Violation("R02", f"{i['name']}|{k}", f"the link {i['name']!r} in "
                                         f"{L['heading'] or 'a list'!r} returns HTTP {st}", u))
        route = route_shape(facts.url)
        if facts.search and route not in self.st.search_done:
            self.st.search_done.add(route)
            out += await self._search_probe(session, facts)
        return out

    async def _search_probe(self, session, facts: Facts) -> list[Violation]:
        """R05: search for a made-up token; any result not on the page before is a phantom."""
        from playwright.async_api import Error as PWError

        token = "zqx" + hashlib.sha1(route_shape(facts.url).encode()).hexdigest()[:6]
        page = await session.context.new_page()
        try:
            await page.goto(facts.url, wait_until="domcontentloaded", timeout=15000)
            await _quiet(page)
            if not await page.evaluate(SEARCH_JS, token):
                return []
            box = page.locator('[data-wt-search="1"]').first
            await box.fill(token)
            await box.press("Enter")
            await _quiet(page, 3000)
            res = await audit(session, page=page)
        except PWError:
            return []
        finally:
            await page.close()
        self.st.probes += 1
        if not re.search(r"result|search|found|match", (res.h1 + " " + res.title + " " + res.text[:400]), re.I):
            return []
        base = {norm(i["name"]) for L in facts.lists for i in L["items"]} | {norm(c["name"]) for c in facts.cards}
        phantoms = []
        for L in res.content_lists():
            if re.search(r"popular|suggest|recommend|trending|you may|related|recent|tag", L["heading"] or "", re.I):
                continue
            for i in L["items"]:
                if norm(i["name"]) not in base and token not in norm(i["text"]) and i["name"]:
                    phantoms.append(i["name"])
        for c in res.cards:
            if c["name"] and norm(c["name"]) not in base and token not in norm(c["text"]) and c["name"] not in phantoms:
                phantoms.append(c["name"])
        if phantoms:
            return [Violation("R05", "phantom", f"a search for the made-up word {token!r} lists "
                              f"{', '.join(repr(p) for p in phantoms[:3])}", res.url)]
        return []

    # ---------- R07c: a follow feed against its authors' pages ----------
    async def _feed_check(self, session) -> list[Violation]:
        """'Your Feed' lists what this account follows: an item whose author's page offers 'Follow' (not
        'Unfollow') to this session contradicts the feed (Conduit F08). One author page per feed list."""
        todo, self.feed_todo = self.feed_todo, []
        st = self.st
        for heading, items in todo:
            for i in items:
                if st.feed_probes >= MAX_FEED_PROBES or self.budget < 1:
                    return []
                authors = [u for u in i.get("links") or [] if _PERSON.search(entity_key(u)) and session.in_scope(u)]
                if not authors:
                    continue
                st.feed_probes += 1
                self.budget -= 1
                self.st.probes += 1
                opened = await _open(session, authors[0])
                if opened is None:
                    continue
                try:
                    fresh = await audit(session, page=opened[0])
                finally:
                    await opened[0].close()
                verbs = [classify(x) for x in fresh.toggles]
                if "follow" in verbs and "unfollow" not in verbs and \
                        not any(_LOGIN_CONTROL.match(x.strip()) for x in fresh.toggles):
                    who = fresh.h1 or entity_key(authors[0])
                    ctl = next(x for x in fresh.toggles if classify(x) == "follow")
                    return [Violation("R07c", f"{heading}|{entity_key(authors[0])}",
                                      f"{heading!r} lists {i['name']!r} by {who!r}, but this account does not follow "
                                      f"{who!r}: their page offers {ctl!r}", authors[0])]
        return []

    # ---------- R19: a count control, clicked in a fresh tab ----------
    async def _toggle_probe(self, session, facts: Facts) -> list[Violation]:
        """A favourite/like control showing a count must change it by one when clicked and the app
        accepts the write; the probe clicks it once more to undo (Conduit F05). One page kind per run."""
        from playwright.async_api import Error as PWError

        st = self.st
        route = route_shape(facts.url)
        if st.toggle_probes >= MAX_TOGGLE_PROBES or self.budget < 1 or route in st.toggle_done or _LOGINISH.search(route):
            return []
        if not any(classify(x) in ("favourite", "like") or re.fullmatch(r"\d[\d,]*", x.strip()) for x in facts.toggles):
            return []
        st.toggle_done.add(route)
        opened = await _open(session, facts.url)
        if opened is None:
            return []
        page, net, _ = opened
        self.budget -= 1
        st.probes += 1
        try:
            cand = await page.evaluate(TOGGLE_JS)
            if not cand:
                return []
            st.toggle_probes += 1
            loc = page.locator('[data-wt-toggle="1"]').first
            net.reset()
            await loc.click()
            await net.quiet(max_s=5.0)
            await asyncio.sleep(session.cfg.settle_ms / 1000)
            after = await page.evaluate(TOGGLE_READ_JS)
            writes, moved = list(net.writes), route_shape(page.url) != route
            if not moved and after is not None:
                net.reset()
                await page.locator('[data-wt-toggle="1"]').first.click()  # undo
                await net.quiet(max_s=5.0)
        except PWError:
            return []
        finally:
            await page.close()
        if moved or after is None or not writes or not all(200 <= s < 400 for s in writes):
            return []  # signed out, refused or navigated: no evidence
        if after["number"] == cand["number"]:
            return [Violation("R19", f"{cand['verb']}|count", f"clicking {cand['text']!r} on {route} (the app accepted "
                              f"the write) left its count at {cand['number']}", f"item: {cand['item'][:120]}")]
        return []

    # ---------- R13: does the app's access agree with its own controls? ----------
    async def _access(self, session, facts: Facts) -> list[Violation]:
        st, w, url = self.st, self.worker, facts.url
        shape = route_shape(url)
        if "*" not in shape or not facts.h1 or self.budget < 1:
            return []
        key = entity_key(url)
        if (w, key) in st.access_done:
            return []
        # The worker's own items are probed past the cap: they give the evidence that releases refusals.
        own = any(e.worker == w and e.verb == "create" and (e.target == key or same_name(e.obj, facts.h1))
                  for e in self.mem.events)
        if st.access_probes.get(w, 0) >= MAX_ACCESS_PROBES and not own:
            return []
        edit = None
        for o in facts.owner:
            if o.get("abs") and re.match(r"edit\b", o["text"], re.I) and not _DEAD.match(o.get("href") or "") \
                    and session.in_scope(o["abs"]):
                t = edit_template(url, o["abs"])
                if t:
                    edit = (o, t)
                    break
        if edit is None:  # hidden: does the address made from this item's ids open its edit form anyway?
            t = st.edit_templates.get((w, shape))
            target = apply_template(t[0], url) if t else None
            if not target or not session.in_scope(target) or target.rstrip("/") == url.rstrip("/"):
                return []
            st.access_done.add((w, key))
            res = await self._probe_form(session, target)
            if res and res["status"] < 400 and res["shape"] == t[1] and any(same_name(v, facts.h1) for v in res["fields"]):
                return [Violation("R13", f"hidden|{t[1]}", f"the page {facts.h1!r} offers no edit control, but {target} "
                                  f"opens its edit form, filled in with its data", f"fields: {res['fields'][:3]}")]
            return []
        o, (template, eshape) = edit
        st.edit_templates.setdefault((w, shape), (template, eshape))
        st.access_done.add((w, key))
        res = await self._probe_form(session, o["abs"])
        if res is None:
            return []
        if res["status"] < 400 and res["shape"] == eshape and any(same_name(v, facts.h1) for v in res["fields"]):
            st.edit_ok.add((w, eshape))
            return st.edit_refused.pop((w, eshape), [])  # refusals seen before this evidence
        logged_out = any(_LOGIN_CONTROL.match(t.strip()) for t in facts.toggles)
        refused = res["status"] in (401, 403) or (res["status"] < 400 and res["shape"] != eshape
                                                   and not _LOGINISH.search(res["shape"]))
        if not refused or logged_out:
            return []  # 404 (gone), a login page (session), or still loading: no evidence
        v = Violation("R13", f"offered|{eshape}", f"the page {facts.h1!r} offers {o['text']!r}, but its address "
                      f"{o['abs']} refuses this session (ended on {res['shape']}, HTTP {res['status']})",
                      "the same kind of edit address opened a filled-in form for this session elsewhere")
        if (w, eshape) in st.edit_ok:
            return [v]
        st.edit_refused.setdefault((w, eshape), []).append(v)
        return []

    async def _probe_form(self, session, url: str) -> dict | None:
        from playwright.async_api import Error as PWError

        self.budget -= 1
        self.st.probes += 1
        self.st.access_probes[self.worker] = self.st.access_probes.get(self.worker, 0) + 1
        opened = await _open(session, url)
        if opened is None:
            return None
        page, _, status = opened
        try:
            raw = await page.evaluate(FORM_JS)
        except PWError:
            return None
        finally:
            await page.close()
        return {"status": status, "url": raw["url"], "shape": route_shape(raw["url"]), "fields": raw["fields"]}

    # ---------- G2: the same URL again, in a fresh tab ----------
    async def _reload(self, session, obs: Observation, done: list[dict], facts: Facts) -> list[Violation]:
        st, w = self.st, self.worker
        if self.budget < 1 or not done or self.writes or not is_navigation(done) or done[-1]["do"] == "back" \
                or not all(d.get("ok", True) for d in done):
            return []
        route = route_shape(facts.url)
        if _LOGINISH.search(route) or (w, route) in st.reload_done or \
                sum(1 for k in st.reload_done if k[0] == w) >= MAX_RELOAD_PAGES:
            return []
        st.reload_done.add((w, route))
        self.budget -= 1
        st.probes += 1
        st.reloads += 1
        opened = await _open(session, facts.url)
        if opened is None:
            return []
        page = opened[0]
        try:
            fresh = await audit(session, page=page)
        finally:
            await page.close()
        if not fresh.url or route_shape(fresh.url) != route:
            return []  # redirected (e.g. the session ended): nothing to compare
        events = [e for e in self.mem.events if e.t >= self.t_before - 1 and e.verb != "view"]
        return view_diff(facts, fresh, events, st.volatile_views)

    # ---------- R16/R17: the accepted form again, with boundary values ----------
    async def _mutate(self, session, obs: Observation, done: list[dict], e: Event | None, step: int) -> list[Violation]:
        st = self.st
        if e is None or e.verb != "create" or not e.written or e.status in ("unknown", "conflict") or \
                st.mutation_forms >= MAX_MUTATION_FORMS:
            return []
        plan = mutation_plan(done, e.obj)
        if plan is None:
            return []
        name, long_ = plan
        key = (route_shape(obs.url), name["ekey"])
        if key in st.mutated:
            return []
        st.mutated.add(key)
        st.mutation_forms += 1
        route, label = route_shape(obs.url), field_label(name)
        results, out = {}, []
        for kind in MUTATIONS:
            target = long_ if kind == "long" else name
            r = await self._submit_variant(session, obs.url, done, target, kind)
            if r is None:
                if kind == "empty":
                    return out  # the form cannot be found again in a fresh tab: give up on it
                continue
            results[kind] = r
            fl = field_label(target)
            if r["server"] or r["errors"]:
                what = r["server"][0] if r["server"] else f"uncaught page error {r['errors'][0]!r}"
                out.append(Violation("R16", f"{kind}|{fl}", f"submitting the form at {route} again with "
                                     f"{_DESC[kind].format(n=r['length'])} in {fl!r}: {what}", r["detail"]))
            if r["outcome"] == "accepted":
                self.mem.typed.update(v for v in r["values"].values() if v.strip())
                self.mem.add_event(worker=self.worker, step=step, verb="create", obj=r["values"].get(field_label(name), ""),
                                   url=obs.url, fields=r["values"], source="mutation", status="verified", written=True)
        em, bl = results.get("empty"), results.get("blank")
        if em and em["outcome"] == "accepted" and not em["server"]:
            out.append(Violation("R17", f"empty|{label}", f"the form at {route} accepted an empty {label!r}, the "
                                 "field that names the new item", em["detail"]))
        elif em and bl and em["outcome"] == "rejected" and bl["outcome"] == "accepted" and not bl["server"]:
            out.append(Violation("R17", f"blank|{label}", f"the form at {route} rejects an empty {label!r} but "
                                 "accepts one of only spaces", bl["detail"]))
        return out

    async def _submit_variant(self, session, form_url: str, done: list[dict], target: dict, kind: str) -> dict | None:
        """Open the form in a fresh tab, fill it as the agent did except `target` (empty, spaces or long;
        other text fields get a short suffix so a unique-name rule does not reject the copy), submit
        it the same way, and report what the app answered."""
        from playwright.async_api import Error as PWError

        opened = await _open(session, form_url)
        if opened is None:
            return None
        page, net, _ = opened
        self.st.probes += 1
        self.st.mutation_submits += 1
        tag = "m" + hashlib.sha1(f"{route_shape(form_url)}|{kind}".encode()).hexdigest()[:3]
        try:
            raw = await page.evaluate(OBSERVE_JS, session.cfg.max_elements)
            els = [Element(**x) for x in raw["elements"]]
            before = await page.evaluate(INNER_TEXT_JS)
            values, length = {}, 0
            *fills, submit = done
            for d in fills:
                if d["do"] not in ("fill", "type", "select") or not d.get("ekey"):
                    continue
                el = _locate(els, d["ekey"], d.get("nth", 0))
                if el is None:
                    return None
                loc = page.locator(f'[data-wt-id="{el.id}"]')
                v = d.get("value") or ""
                if d is target:
                    if kind == "long":
                        cap = await loc.get_attribute("maxlength")
                        n = int(cap) if cap and cap.isdigit() and 0 < int(cap) <= 5000 else \
                            (1000 if d["ekey"].startswith("textarea|") else 300)
                        v = long_value(v, n)
                    else:
                        v = "" if kind == "empty" else "   "
                    length = len(v)
                elif d["do"] != "select" and value_class(v) == "text":
                    v = f"{v}-{tag}"
                elif d["do"] != "select" and value_class(v) == "email":
                    v = v.replace("@", f"+{tag}@", 1)
                if d["do"] == "select":
                    try:
                        await loc.select_option(label=v)
                    except PWError:
                        await loc.select_option(value=v)
                else:
                    await loc.fill(v)
                values[field_label(d)] = v
            el = _locate(els, submit["ekey"], submit.get("nth", 0))
            if el is None:
                return None
            net.reset()
            loc = page.locator(f'[data-wt-id="{el.id}"]')
            if submit["do"] == "press":
                await loc.press(str(submit.get("value") or "Enter"))
            else:
                await loc.click()
            await net.quiet(max_s=5.0)
            await asyncio.sleep(session.cfg.settle_ms / 1000)
            after = await page.evaluate(INNER_TEXT_JS)
            end = page.url
        except PWError:
            return None
        finally:
            await page.close()
        shown = [ln for ln in after.splitlines() if len(ln) < 160 and ln not in before]
        invalid = any(_VALIDATION.search(ln) for ln in shown)
        accepted = any(200 <= s < 400 for s in net.writes) and not invalid
        return {"outcome": "accepted" if accepted else "rejected", "server": net.server, "errors": net.errors,
                "values": values, "length": length,
                "detail": f"{kind}: {length} chars; writes {net.writes[:4]}; ended on {route_shape(end)}"
                          + (f"; shown {shown[0][:80]!r}" if invalid else "")}

    async def _fresh_text(self, session, url: str) -> str | None:
        self.budget -= 1
        self.st.probes += 1
        return await session.fresh_text(url)

    async def _fetch(self, session, url: str, body: bool = True) -> tuple[int | None, str | None]:
        from playwright.async_api import Error as PWError

        try:
            r = await session.context.request.get(url, max_redirects=5, timeout=10000)
            return r.status, (await r.text())[:200000] if body else None
        except PWError:
            return None, None



async def _quiet(page, ms: int = 2500) -> None:
    from playwright.async_api import Error as PWError

    try:
        await page.wait_for_load_state("networkidle", timeout=ms)
    except PWError:
        pass


class _ProbeNet:
    """What a probe tab's requests did. Probe tabs are not wired to the session's signal buffer
    (their errors must not become findings with the worker's trail), so R13/R16/G2 watch them here."""

    def __init__(self, session, page):
        self.session = session
        self.pending: set = set()
        self.last = time.monotonic()
        self.writes: list[int] = []  # statuses of same-origin write requests
        self.server: list[str] = []  # same-origin 5xx responses
        self.errors: list[str] = []  # uncaught page errors
        page.on("request", self._request)
        page.on("requestfinished", self._finished)
        page.on("requestfailed", self._finished)
        page.on("response", self._response)
        page.on("pageerror", lambda exc: self.errors.append(str(exc).split("\n")[0][:200]))

    def _request(self, req) -> None:
        if req.resource_type in NET_TYPES:
            self.pending.add(req)
            self.last = time.monotonic()

    def _finished(self, req) -> None:
        if req in self.pending:
            self.pending.discard(req)
            self.last = time.monotonic()

    def _response(self, resp) -> None:
        if not self.session.in_scope(resp.url):
            return
        req = resp.request
        if req.method not in ("GET", "HEAD", "OPTIONS") and req.resource_type in NET_TYPES:
            self.writes.append(resp.status)
        if resp.status >= 500:
            self.server.append(f"{req.method} {urlsplit(resp.url).path} -> HTTP {resp.status}")

    def reset(self) -> None:
        self.writes, self.server, self.errors = [], [], []

    async def quiet(self, quiet_s: float = 0.3, max_s: float = 4.0) -> None:
        """Like BrowserSession.wait_quiet: no xhr/fetch/document request in flight for `quiet_s`."""
        await asyncio.sleep(0.05)
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            if not self.pending and time.monotonic() - self.last >= quiet_s:
                return
            await asyncio.sleep(0.05)


async def _open(session, url: str):
    """(page, net, HTTP status) of `url` in a new tab of the worker's context, loaded and quiet;
    the caller closes the page. None if it does not load."""
    from playwright.async_api import Error as PWError

    page = await session.context.new_page()
    net = _ProbeNet(session, page)
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await _quiet(page)
        await net.quiet()
        await asyncio.sleep(session.cfg.settle_ms / 1000)
    except PWError:
        await page.close()
        return None
    return page, net, (resp.status if resp else 0)


def _locate(els: list[Element], ekey: str, nth: int) -> Element | None:
    same = [e for e in els if e.key() == ekey]
    if not same:
        return None
    return same[nth] if nth < len(same) else same[0]


def _href_of(d: dict) -> str:
    m = re.search(r"href=(\S+)", d.get("el") or "")
    return m.group(1) if m else ""


def _el_text(d: dict) -> str:
    m = re.search(r'"([^"]*)"', d.get("el") or "")
    return m.group(1) if m else ""
