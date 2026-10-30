"""Page norms (v5 waves W1-W4, D59-D60): what one page says about itself, from one page read per step.

  R43  anchors (NV8)            an in-page link '#x' whose target (id or name x) is not on the page
  R64  control state (PR8)      two tabs or options selected at once; the selected tab's panel hidden; a control
                                that says it is expanded while what it controls is hidden; aria-checked vs checked
  R26  declared range (DV4)     progress bar or meter outside its own min/max; a rating 'x out of y' above y; a
                                number field outside its own limits that nobody typed
  R25  sort invariant (DV6)     an active sort (a selected 'sort' option, aria-sort on a column) the visible keys break
  R41  aggregates (AG1, AG2)    a summary number whose label names a complete list on the same page differs from it
  R32  running balance (LG2/4)  a 'Balance' column that does not step by each row's amount
  R36  intervals (TM1, TM2)     a shown interval whose end is before its start, or whose duration is not end - start
  R06s identities (DV3, PX3)    'x of y (z%)', 'was A now B (-c%)', 'Save $d', progress 'done/total' with its %
  R72  relative time (TM8)      'overdue' with a date ahead, 'upcoming' / 'in n days' with a date behind or off
  R54  loading states (FB5)     a spinner or aria-busy still there 10 s later on the same page (state in the Sweeper)
  R65  geometry (PR5)           a visible action control covered by another element; the page scrolls sideways;
                                text drawn in its background colour
  R74  media state (MD1, MD2)   two players playing at once; a playing player whose time does not advance; a Play
                                label on a playing player (or Pause on a paused one)
  R75  canvas and SVG (RC7/8)   SVG geometry attributes that are not finite numbers; a large canvas left blank
  R02m broken media (AR2)       an image or video that failed to load (not lazy, not a 1x1 pixel)
  R01x placeholders (PR4, PR9)  untranslated message keys ('messages.welcome_title'), lorem ipsum, TODO text
  R10x contact links (NV11)     a mailto: without a valid address, a tel: without digits; the shown address or
                                number differs from the link's target
  D61 (every family row's named extension, each under its own id so the tracker cannot call it built early):
  R02h hosts and empty CTAs (PR9) a link to localhost, another port or example.com; 'Buy now' pointing to '#'
  R12c length fidelity (FM8)    a character counter ('12/280', '268 left') that differs from the field's length
  R06c column totals (AG3)      a 'Total' row that differs from the sum of its column
  R32d currency decimals (LG4)  '$10.5', '$3.141', '¥1,200.50': decimals the currency does not use
  R36r recurrences (TM7)        'weekly, 5 times' followed by another number of dated occurrences
  extensions of built ids: R06s tax rate times its base (DV3); R36 a stated day count (TM1); R26 negative
  scores or lives, a timer moving while paused (RC5); R65 clipped text (PR5); R64 a carousel indicator on
  another slide (PR8); R75 shapes outside the viewBox, a canvas that does not change while it claims to run
  (RC7, RC8); R41 chart labels against the table (AG2); R35 a stated plan limit below the list (CP1); R68 the
  same tag twice on one item (RL2); R74 a playlist's stated track count or length against its tracks (MD2)

Guards common to all: hidden elements are skipped; script-handled anchors (role, data-toggle, aria-controls,
onclick, '#', '#!', '#/') are skipped; aria-multiselectable tab lists are skipped; only the 'claims open but
hidden' direction of aria-expanded is checked; lists with a pager, 'view all' or 'load more' are not complete,
so R41 compares only complete lists; canvases inside forms or named signature/draw/sketch are skipped (blank by
design); covering elements that are fixed or sticky, or an open dialog, do not count (R65). Every rule starts at
T2 until measured (fault_families.md section 3).

The same read returns what the cross-view rules need (crossview.py): breadcrumbs, navigation links with badges,
form fields with their values and attributes, selected filters, status words near the heading, pager links,
file inputs, search suggestions and declared data (JSON-LD, OpenGraph).
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

NORMS_JS = r"""
async () => {
  const vis = el => {
    if (!el || el.hidden) return false;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0;
  };
  const txt = el => ((el && (el.innerText || el.getAttribute('aria-label') || el.textContent)) || '').trim().replace(/\s+/g, ' ').slice(0, 60);
  const lab = el => {
    if (el.labels && el.labels[0]) return txt(el.labels[0]);
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.id || '';
  };
  const num = v => (v === null || v === undefined || v === '' || isNaN(+v)) ? null : +v;
  const out = {anchors: [], multi: [], panels: [], expanded: [], aria: [], ranges: [], ratings: [], numbers: [],
               sort: [], spinners: [], controls: [], covered: [], overflow: false, invisible: [], media: [], svg_bad: [], canvas_blank: [],
               broken: [], contacts: [], breadcrumbs: [], nav: [], fields: [], filters: [], status: [], pager: [],
               files: [], suggestions: [], jsonld: [], og: {}, h1: '', empty: [], dialog_open: false, lines: [],
               clipped: [], carousel: [], hosts: [], empty_cta: [], counters: [], downloads: [], chart: [], kbd: [],
               chips: [], unread: 0, timer_paused: [], canvas_frozen: [], svg_outside: [], title: document.title || ''};
  const h1 = document.querySelector('h1');
  out.h1 = h1 ? txt(h1) : '';
  out.dialog_open = !!document.querySelector('[role=dialog][open], dialog[open], [aria-modal=true]');
  // ---- R43 (D62, I86: a page still being parsed has the skip link but not yet its target further down)
  out.loading = document.readyState === 'loading';
  for (const a of (out.loading ? [] : document.querySelectorAll('a[href^="#"]'))) {
    const h = a.getAttribute('href') || '';
    if (h.length < 2 || h.startsWith('#!') || h.startsWith('#/') || !vis(a)) continue;
    if (a.hasAttribute('onclick') || a.getAttribute('role') || a.hasAttribute('data-toggle') ||
        a.hasAttribute('data-bs-toggle') || a.hasAttribute('aria-controls') || a.closest('[role=tablist],[role=menu]')) continue;
    let id = h.slice(1);
    try { id = decodeURIComponent(id); } catch (e) {}
    out.anchors.push({href: h, text: txt(a), found: !!(document.getElementById(id) || document.getElementsByName(id).length)});
  }
  // ---- R64
  for (const g of document.querySelectorAll('[role=tablist]:not([aria-multiselectable=true]), [role=radiogroup]')) {
    if (!vis(g)) continue;
    const sel = [...g.querySelectorAll(g.getAttribute('role') === 'tablist' ? '[role=tab][aria-selected=true]' : '[role=radio][aria-checked=true]')].filter(vis);
    out.multi.push({role: g.getAttribute('role'), label: txt(g), n: sel.length, names: sel.map(txt).slice(0, 4)});
  }
  for (const t of document.querySelectorAll('[role=tab][aria-selected=true][aria-controls]')) {
    if (!vis(t)) continue;
    const p = document.getElementById(t.getAttribute('aria-controls'));
    if (p) out.panels.push({tab: txt(t), hidden: !vis(p)});
  }
  for (const b of document.querySelectorAll('[aria-expanded=true][aria-controls]')) {
    if (!vis(b)) continue;
    const p = document.getElementById(b.getAttribute('aria-controls'));
    if (p) out.expanded.push({control: txt(b), hidden: !vis(p)});
  }
  for (const c of document.querySelectorAll('input[type=checkbox][aria-checked], input[type=radio][aria-checked]')) {
    if (!vis(c)) continue;
    out.aria.push({label: lab(c), checked: c.checked, aria: c.getAttribute('aria-checked')});
  }
  // ---- R26
  for (const e of document.querySelectorAll('[role=progressbar][aria-valuenow], [role=meter][aria-valuenow], progress, meter')) {
    if (!vis(e)) continue;
    const tag = e.tagName.toLowerCase(), native = tag === 'progress' || tag === 'meter';
    const now = num(native ? e.getAttribute('value') : e.getAttribute('aria-valuenow'));
    const lo = num(tag === 'meter' ? e.getAttribute('min') : tag === 'progress' ? '0' : e.getAttribute('aria-valuemin'));
    const hi = num(native ? (e.getAttribute('max') || '1') : e.getAttribute('aria-valuemax'));
    if (now !== null) out.ranges.push({what: native ? tag : e.getAttribute('role'), label: txt(e) || e.getAttribute('aria-label') || '', now, lo, hi});
  }
  const body = document.body ? document.body.innerText : '';
  const lineOf = (i, len) => {
    const a = body.lastIndexOf('\n', i) + 1, e = body.indexOf('\n', i + len);
    return body.slice(Math.max(a, i - 60), Math.min(e < 0 ? body.length : e, i + len + 30)).replace(/\s+/g, ' ');
  };
  const rx = /(\d+(?:[.,]\d+)?)\s*(?:out of|\/)\s*(\d+(?:[.,]\d+)?)\s*(stars?|points?|rating)?/gi;
  let m, k = 0;
  while ((m = rx.exec(body)) && k < 40) { k++; out.ratings.push({x: m[1], y: m[2], unit: m[3] || '', ctx: lineOf(m.index, m[0].length)}); }
  for (const i of document.querySelectorAll('input[type=number]')) {
    if (!vis(i) || i.value === '') continue;
    out.numbers.push({label: lab(i), value: i.value, min: num(i.getAttribute('min')), max: num(i.getAttribute('max'))});
  }
  // lines of text for the in-page identities, intervals and relative times (Python parses them)
  out.lines = body.split('\n').map(s => s.trim()).filter(s => s.length > 3 && s.length < 200 && /\d/.test(s)).slice(0, 400);
  // ---- R25 sort controls
  for (const s of document.querySelectorAll('select')) {
    if (!vis(s) || !/sort|order/i.test((s.name || '') + ' ' + (s.id || '') + ' ' + lab(s))) continue;
    const o = s.options[s.selectedIndex];
    if (o) out.sort.push({text: (o.text || '').trim(), via: 'select'});
  }
  for (const th of document.querySelectorAll('th[aria-sort=ascending], th[aria-sort=descending]')) {
    const row = th.parentElement, idx = [...row.children].indexOf(th), table = th.closest('table');
    const vals = table ? [...table.querySelectorAll('tbody tr')].map(r => r.children[idx] ? r.children[idx].innerText.trim() : '').slice(0, 60) : [];
    out.sort.push({text: txt(th), via: 'column', dir: th.getAttribute('aria-sort'), values: vals});
  }
  // ---- R54
  for (const e of document.querySelectorAll('[aria-busy=true], .spinner, .loading, .loader, .skeleton, [class*=spinner], [class*=skeleton]')) {
    if (vis(e) && e.getBoundingClientRect().width < innerWidth) out.spinners.push((e.getAttribute('class') || e.tagName).slice(0, 40));
  }
  for (const e of document.querySelectorAll('p, div, li, td, span')) {
    if (e.children.length > 2) continue;
    const t = (e.innerText || '').trim();
    if (t.length < 60 && /^(no (items|results|records|data|entries)( found| yet)?|nothing (here|to show|found)|empty|there are no)/i.test(t) && vis(e)) out.empty.push(t);
    if (out.empty.length > 5) break;
  }
  // ---- R65 geometry
  if (!out.dialog_open) {
    let n = 0;
    for (const b of document.querySelectorAll('button, a[href], [role=button], input[type=submit]')) {
      if (n > 80 || !vis(b)) continue;
      const r = b.getBoundingClientRect();
      if (r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth || r.width < 4 || r.height < 4) continue;
      n++;
      const x = r.left + r.width / 2, y = r.top + r.height / 2;
      // D62 (I88): a control scrolled out of a scrolling box (BookStack's entity picker) is out of view, not covered
      let clippedBy = false;
      for (let a = b.parentElement; a && a !== document.body; a = a.parentElement) {
        const st = getComputedStyle(a);
        if (!/auto|scroll|hidden|clip/.test(st.overflow + st.overflowX + st.overflowY)) continue;
        const ar = a.getBoundingClientRect();
        if (x < ar.left || x > ar.right || y < ar.top || y > ar.bottom) { clippedBy = true; break; }
      }
      if (clippedBy) continue;
      const hit = document.elementFromPoint(x, y);
      if (!hit || b.contains(hit) || hit.contains(b)) continue;
      let c = hit, fixed = false;
      for (let i = 0; i < 8 && c; i++, c = c.parentElement) { const p = getComputedStyle(c).position; if (p === 'fixed' || p === 'sticky') { fixed = true; break; } }
      if (!fixed && !b.closest('[aria-hidden=true]')) out.covered.push({control: txt(b), by: (hit.tagName + '.' + (typeof hit.className === 'string' ? hit.className : '')).slice(0, 60)});
    }
    const de = document.documentElement;
    out.overflow = de.scrollWidth > de.clientWidth + 8 && getComputedStyle(document.body).overflowX !== 'hidden';
    const rgb = s => { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(s || ''); return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null; };
    const bgOf = el => { for (let c = el; c; c = c.parentElement) { const v = rgb(getComputedStyle(c).backgroundColor); if (v && v[3] > 0.9) return v; } return [255, 255, 255, 1]; };
    let k2 = 0;
    for (const el of document.querySelectorAll('p, span, a, li, td, h1, h2, h3, label, button')) {
      if (k2 > 250 || el.children.length || !vis(el)) continue;
      const t = (el.innerText || '').trim();
      if (t.length < 3) continue;
      k2++;
      const fg = rgb(getComputedStyle(el).color), bg = bgOf(el);
      if (fg && fg[3] > 0.5 && Math.abs(fg[0] - bg[0]) + Math.abs(fg[1] - bg[1]) + Math.abs(fg[2] - bg[2]) < 12) out.invisible.push(t.slice(0, 50));
      if (out.invisible.length >= 5) break;
    }
  }
  // ---- D61: R65 clipped text, R64 carousels, R02h hosts and empty calls to action, R12c counters, R02d
  // downloads, R41 chart labels, R29k advertised keys, R68 duplicate chips, R47r unread markers
  for (const el of document.querySelectorAll('p, span, a, li, td, th, h1, h2, h3, h4, label, button, div')) {
    if (out.clipped.length >= 3 || el.children.length || !vis(el)) continue;
    const s = getComputedStyle(el), t = (el.innerText || '').trim();
    if (t.length < 4 || !/hidden|clip/.test(s.overflow + s.overflowX + s.overflowY)) continue;
    if (s.textOverflow === 'ellipsis' || (s.webkitLineClamp && s.webkitLineClamp !== 'none')) continue;
    // D62 (I87): screen-reader-only text is clipped to a pixel on purpose (BookStack 'Enter section select mode')
    const r = el.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2 || /sr-only|screen-reader|visually-hidden|visuallyhidden/i.test(el.className || '')) continue;
    if (el.scrollWidth > el.clientWidth + 4 || el.scrollHeight > el.clientHeight + 4) out.clipped.push(t.slice(0, 50));
  }
  for (const c of document.querySelectorAll('[aria-roledescription=carousel], .carousel, [class*=carousel]')) {
    if (!vis(c) || c.parentElement && c.parentElement.closest('[aria-roledescription=carousel], .carousel')) continue;
    const slides = [...c.querySelectorAll('[aria-roledescription=slide], .carousel-item, [class*=slide]:not([class*=slides]):not([class*=slider])')];
    const dots = [...c.querySelectorAll('.carousel-indicators > *, [class*=indicator] > *, [class*=dots] > *, [role=tablist] > [role=tab]')];
    if (slides.length < 2 || dots.length !== slides.length) continue;
    const cr = c.getBoundingClientRect();
    const shown = slides.findIndex(s => { const r = s.getBoundingClientRect(); return vis(s) && r.left >= cr.left - 2 && r.right <= cr.right + 2; });
    const cur = dots.findIndex(d => d.getAttribute('aria-current') === 'true' || d.classList.contains('active') || d.getAttribute('aria-selected') === 'true');
    if (shown >= 0 && cur >= 0) out.carousel.push({label: txt(c).slice(0, 40), slide: shown, indicator: cur});
  }
  const host = location.hostname, port = location.port;
  for (const a of document.querySelectorAll('a[href]')) {
    if (!vis(a) || out.hosts.length >= 5) continue;
    const h = a.getAttribute('href') || '';
    let u = null;
    try { u = new URL(a.href); } catch (e) { continue; }
    const devHost = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(u.hostname) && !/^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(host);
    const otherPort = u.hostname === host && u.port !== port && /^https?:$/.test(u.protocol);
    const example = /(^|\.)example\.(com|org|net)$/.test(u.hostname);
    if (devHost || otherPort || example) out.hosts.push({href: h.slice(0, 120), text: txt(a), why: devHost ? 'dev host' : otherPort ? 'another port' : 'example domain'});
  }
  const CTA = /^(buy( now)?|order( now)?|sign up|get started|subscribe|download|register|contact us|book now|learn more|start (your )?free trial|try (it )?(for )?free|add to (cart|basket))\b/i;
  for (const a of document.querySelectorAll('a[href="#"], a[href^="javascript:"]')) {
    if (!vis(a) || out.empty_cta.length >= 3) continue;
    if (a.hasAttribute('onclick') || a.getAttribute('role') || a.hasAttribute('data-toggle') || a.hasAttribute('data-bs-toggle') ||
        a.hasAttribute('aria-controls') || a.hasAttribute('aria-haspopup') || a.closest('[role=menu],[role=tablist],nav,.dropdown')) continue;
    if (CTA.test(txt(a))) out.empty_cta.push({text: txt(a), href: (a.getAttribute('href') || '').slice(0, 40)});
  }
  for (const f of document.querySelectorAll('input[maxlength], textarea[maxlength]')) {
    if (!vis(f) || f.maxLength <= 0 || out.counters.length >= 4) continue;
    const box = f.closest('label, .form-group, .field, div') || f.parentElement;
    const t = box ? (box.innerText || '') : '';
    const m = /(\d{1,5})\s*\/\s*(\d{1,5})(?!\d)/.exec(t), r = /(\d{1,5})\s+characters?\s+(left|remaining)/i.exec(t);
    if (m || r) out.counters.push({label: lab(f).slice(0, 40), units: f.value.length, points: [...f.value].length, max: f.maxLength,
                                   a: m ? +m[1] : null, b: m ? +m[2] : null, left: r ? +r[1] : null});
  }
  for (const a of document.querySelectorAll('a[download], a[href]')) {
    if (out.downloads.length >= 3 || !vis(a)) continue;
    const t = txt(a);
    if ((a.hasAttribute('download') || /^download\b/i.test(t)) && !/csv|export/i.test(t + (a.getAttribute('href') || '')))
      out.downloads.push({text: t, href: a.href});
  }
  for (const s of document.querySelectorAll('svg')) {
    for (const e of s.querySelectorAll('[aria-label], title')) {
      const t = (e.tagName.toLowerCase() === 'title' ? e.textContent : e.getAttribute('aria-label')) || '';
      const m = /^\s*([^:,]{1,40}?)\s*[:,]\s*\$?(-?\d[\d.,]*)\s*$/.exec(t);
      if (m) out.chart.push({label: m[1].trim(), value: m[2]});
      if (out.chart.length >= 40) break;
    }
  }
  out.kbd = [...document.querySelectorAll('kbd')].map(k => (k.innerText || '').trim()).filter(t => t && t.length <= 12).slice(0, 20);
  for (const box of document.querySelectorAll('main, article, [role=main], .content, body')) {
    const groups = new Map();
    const CHIP = '.tag, .chip, .pill, [class*=tag-], [class*=chip], [rel=tag]';
    for (const c of box.querySelectorAll(CHIP)) {
      if (!vis(c) || c.children.length > 1) continue;
      // D62 (I89): the name and value parts inside one chip (BookStack '.tag-name' / '.tag-value') are not two chips
      if (c.parentElement && c.parentElement.closest(CHIP)) continue;
      const p = c.parentElement; if (!p) continue;
      if (!groups.has(p)) groups.set(p, []);
      groups.get(p).push((c.innerText || '').trim().toLowerCase());
    }
    for (const names of groups.values()) {
      const dup = names.find((n, i) => n && names.indexOf(n) !== i);
      if (dup && out.chips.length < 3) out.chips.push({dup, n: names.length});
    }
    break;
  }
  out.unread = document.querySelectorAll('.unread, [class*=unread], .is-new, [data-unread=true], [aria-label*=unread i]').length;
  // ---- R26 / RC5: a game timer that moves while the page says it is paused; R75 / RC8: a canvas that
  // does not change while the page offers to pause it (it claims to run). One shared wait, only when needed.
  const timers = [...document.querySelectorAll('[class*=timer], [class*=clock], [class*=countdown], [class*=elapsed], [id*=timer]')]
    .filter(e => vis(e) && /^\d{1,2}:\d{2}(:\d{2})?$/.test((e.innerText || '').trim()));
  const controlTexts = [...document.querySelectorAll('button, [role=button]')].filter(vis).map(b => (b.innerText || b.getAttribute('aria-label') || '').trim());
  const paused = controlTexts.some(t => /^(resume|continue)$/i.test(t)) || /\bpaused\b/i.test(body.slice(0, 5000));
  const running = controlTexts.some(t => /^(pause|stop)$/i.test(t));
  const bigCanvases = [...document.querySelectorAll('canvas')].filter(c => { const r = c.getBoundingClientRect(); return vis(c) && r.width >= 100 && r.height >= 100; });
  const hashOf = c => { try { const d = c.toDataURL(); let h = 0; for (let i = 0; i < d.length; i += 7) h = (h * 31 + d.charCodeAt(i)) | 0; return h; } catch (e) { return null; } };
  const t0Timers = timers.map(e => e.innerText.trim());
  const t0Canvas = running ? bigCanvases.map(hashOf) : [];
  // ---- R75: SVG shapes entirely outside their viewBox
  for (const s of document.querySelectorAll('svg[viewBox]')) {
    const vb = (s.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    if (vb.length !== 4 || vb.some(isNaN) || vb[2] <= 0 || vb[3] <= 0) continue;
    for (const e of s.querySelectorAll('rect, circle, ellipse, text, line, polygon')) {
      let b; try { b = e.getBBox(); } catch (err) { continue; }
      if (b.width === 0 && b.height === 0) continue;
      if (b.x > vb[0] + vb[2] || b.y > vb[1] + vb[3] || b.x + b.width < vb[0] || b.y + b.height < vb[1]) {
        out.svg_outside.push(e.tagName + ' at ' + Math.round(b.x) + ',' + Math.round(b.y)); break;
      }
    }
    if (out.svg_outside.length >= 3) break;
  }
  // ---- R74 media (one second apart)
  const players = [...document.querySelectorAll('audio, video')].filter(p => p.currentSrc || p.src);
  if (players.length || (timers.length && paused) || t0Canvas.some(h => h !== null)) {
    const t0 = players.map(p => p.currentTime);
    await new Promise(r => setTimeout(r, 1200));
    if (paused) timers.forEach((e, i) => { if (e.innerText.trim() !== t0Timers[i]) out.timer_paused.push(t0Timers[i] + ' -> ' + e.innerText.trim()); });
    bigCanvases.forEach((c, i) => { if (t0Canvas[i] !== null && t0Canvas[i] !== undefined && hashOf(c) === t0Canvas[i]) out.canvas_frozen.push((c.id || c.className || 'canvas').toString().slice(0, 40)); });
    players.forEach((p, i) => {
      const box = p.closest('figure, article, section, li, div') || p.parentElement;
      const btn = box ? [...box.querySelectorAll('button, [role=button]')].map(txt).find(t => /^(play|pause)$/i.test(t)) : '';
      out.media.push({kind: p.tagName.toLowerCase(), paused: p.paused, advanced: p.currentTime - t0[i], duration: p.duration,
                      ready: p.readyState, error: p.error ? p.error.code : 0, button: btn || ''});
    });
  }
  // ---- R75
  for (const e of document.querySelectorAll('svg [x], svg [y], svg [cx], svg [cy], svg [r], svg [width], svg [height], svg [d], svg [points]')) {
    for (const a of ['x', 'y', 'cx', 'cy', 'r', 'width', 'height', 'd', 'points']) {
      const v = e.getAttribute(a);
      if (v && /NaN|Infinity|undefined|null/.test(v)) { out.svg_bad.push(e.tagName + ' ' + a + '=' + v.slice(0, 30)); break; }
    }
    if (out.svg_bad.length >= 5) break;
  }
  for (const c of document.querySelectorAll('canvas')) {
    const r = c.getBoundingClientRect();
    if (!vis(c) || r.width < 100 || r.height < 100 || c.closest('form') || /sign|draw|sketch|pad/i.test((c.id || '') + (c.className || ''))) continue;
    try {
      const blank = document.createElement('canvas'); blank.width = c.width; blank.height = c.height;
      if (c.toDataURL() === blank.toDataURL()) out.canvas_blank.push((c.id || c.className || 'canvas').toString().slice(0, 40));
    } catch (e) { /* tainted or WebGL without preserveDrawingBuffer: unknown */ }
  }
  out.controls = [...document.querySelectorAll('button, a[href], [role=button], input[type=submit], [role=tab]')]
    .filter(vis).map(txt).filter(t => t && t.length <= 30).slice(0, 150);
  out.exports = [...document.querySelectorAll('a[href]')].filter(a => vis(a) && !/^javascript:/i.test(a.getAttribute('href') || '') &&
    /\b(export|csv|download (as )?(csv|xlsx|data|pdf)|print( view| version)?|pdf)\b/i.test((a.innerText || '') + ' ' + a.getAttribute('href')))
    .map(a => ({text: txt(a), href: a.href})).slice(0, 3);
  out.imports = [...document.querySelectorAll('input[type=file]')].filter(f => /import|upload (a )?(csv|file)/i.test(
    (document.querySelector('h1') || {}).innerText + ' ' + location.pathname + ' ' + lab(f))).length;
  out.svg_n = document.querySelectorAll('svg').length;
  out.canvas_n = document.querySelectorAll('canvas').length;
  out.img_n = document.querySelectorAll('img').length;
  // ---- R02m
  for (const im of document.querySelectorAll('img')) {
    if (!vis(im) || im.loading === 'lazy' || !im.complete || (im.getAttribute('src') || '').startsWith('data:')) continue;
    if (im.naturalWidth === 0 && im.width > 1 && im.height > 1) out.broken.push({what: 'image', src: (im.getAttribute('src') || '').slice(0, 120), alt: im.alt || ''});
  }
  players.forEach(p => { if (p.error) out.broken.push({what: p.tagName.toLowerCase(), src: (p.currentSrc || p.src).slice(0, 120), alt: ''}); });
  // ---- R10x
  for (const a of document.querySelectorAll('a[href^="mailto:"], a[href^="tel:"]')) out.contacts.push({href: a.getAttribute('href').slice(0, 120), text: txt(a)});
  // ---- for crossview.py
  const bc = document.querySelector('nav[aria-label*=breadcrumb i], .breadcrumb, .breadcrumbs, [class*=breadcrumb]');
  if (bc && vis(bc)) out.breadcrumbs = [...bc.querySelectorAll('a[href]')].map(a => ({text: txt(a), href: a.href})).slice(0, 8);
  for (const a of document.querySelectorAll('nav a[href], header a[href], [role=navigation] a[href]')) {
    if (!vis(a)) continue;
    const badge = a.querySelector('.badge, [class*=badge], [class*=count], sup');
    const n = badge ? num((badge.innerText || '').trim()) : null;
    out.nav.push({text: txt(a), href: a.href, badge: n});
    if (out.nav.length > 60) break;
  }
  for (const f of document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select')) {
    if (!vis(f) || out.fields.length > 40) continue;
    const t = (f.getAttribute('type') || f.tagName).toLowerCase();
    out.fields.push({label: lab(f).slice(0, 60), type: t, name: f.name || '',
                     value: t === 'password' ? '' : (f.tagName === 'SELECT' ? (f.options[f.selectedIndex] || {}).text || '' : (t === 'checkbox' || t === 'radio') ? String(f.checked) : (f.value || '')).slice(0, 200),
                     required: f.required, maxlength: f.maxLength > 0 ? f.maxLength : null, minlength: f.minLength > 0 ? f.minLength : null,
                     min: num(f.getAttribute('min')), max: num(f.getAttribute('max')), step: f.getAttribute('step'),
                     pattern: f.getAttribute('pattern') || '', accept: f.getAttribute('accept') || '', readonly: f.readOnly || false,
                     form: f.form ? [...document.forms].indexOf(f.form) : -1});
    if (t === 'checkbox' && f.checked) out.filters.push(lab(f).slice(0, 40));
  }
  for (const s of document.querySelectorAll('select')) { if (vis(s) && s.selectedIndex > 0) out.filters.push(lab(s).slice(0, 30) + '=' + ((s.options[s.selectedIndex] || {}).text || '')); }
  const STATUS = /^(open|closed|pending|approved|rejected|draft|published|active|inactive|archived|paid|unpaid|overdue|cancell?ed|shipped|delivered|in stock|out of stock|sold out|completed|in progress|resolved|new|on hold|scheduled|expired)$/i;
  for (const e of document.querySelectorAll('.badge, .status, .label, .tag, [class*=status], [class*=state], [class*=pill], span, strong')) {
    const t = (e.innerText || '').trim();
    if (t.length < 25 && STATUS.test(t) && vis(e)) out.status.push(t.toLowerCase());
    if (out.status.length > 10) break;
  }
  const pg = document.querySelector('.pagination, nav[aria-label*=pagin i], [class*=pagination], [class*=pager]');
  if (pg) out.pager = [...pg.querySelectorAll('a[href]')].map(a => ({text: txt(a), href: a.href})).slice(0, 15);
  for (const f of document.querySelectorAll('input[type=file]')) out.files.push({label: lab(f), accept: f.getAttribute('accept') || '', form: f.form ? [...document.forms].indexOf(f.form) : -1});
  for (const o of document.querySelectorAll('[role=listbox] [role=option], .autocomplete li, [class*=suggest] li, datalist option')) {
    const t = (o.innerText || o.value || '').trim();
    if (t) out.suggestions.push(t.slice(0, 80));
    if (out.suggestions.length > 15) break;
  }
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) { try { out.jsonld.push(JSON.parse(s.textContent)); } catch (e) {} if (out.jsonld.length > 3) break; }
  for (const mt of document.querySelectorAll('meta[property^="og:"], meta[property^="product:"]')) out.og[mt.getAttribute('property')] = (mt.getAttribute('content') || '').slice(0, 120);
  return out;
}
"""

TIERS = {r: "T2" for r in ("R43", "R64", "R26", "R25", "R41", "R32", "R36", "R06s", "R72", "R54", "R65", "R74", "R75",
                           "R02m", "R01x", "R10x", "R02h", "R12c", "R06c", "R32d", "R36r")}  # merged into consistency.TIER; every rule starts at T2
RULES = tuple(TIERS)
_RATING_CTX = re.compile(r"\b(rat(ed|ing)|stars?|score|review)", re.I)
_PAGING = re.compile(r"\b(page|step|item|slide|question|result|of \d+ (results|items|pages))\b", re.I)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _f(s: str) -> float | None:
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return None


def parse_number(s: str) -> float | None:
    """O6 (a): '1.234,56', '1,234.56', '1,00,000', '(12.00)', '-3', '1.2k', '2M', Eastern Arabic digits."""
    if not s:
        return None
    s = str(s).translate(_DIGITS)
    m = re.search(r"(\d[\d.,'\s]*)(\s*[kKmM]\b)?", s)
    if not m:
        return None
    raw = m.group(1).strip().replace("'", "").replace(" ", "")
    neg = "(" in s[:m.start() + 1] or re.search(r"[-−]\s*[^\d\s]{0,3}\s*$", s[:m.start()]) is not None
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
    if m.group(2):
        v *= 1000 if m.group(2).strip().lower() == "k" else 1_000_000
    return -v if neg else v


_MONEY = re.compile(r"(?:[$€£¥₹]|USD|EUR|GBP|PKR|Rs\.?)\s*-?\d[\d.,]*|-?\d[\d.,]*\s*(?:[$€£¥₹]|USD|EUR|GBP|PKR)", re.I)


def money_values(text: str) -> list[float]:
    return [v for m in _MONEY.findall(text or "") if (v := parse_number(m)) is not None]


def _close(a: float, b: float, tol: float = 0.011) -> bool:
    return abs(a - b) <= max(tol, 0.005 * max(abs(a), abs(b)))


def arms(raw: dict | None) -> dict[str, str]:
    """Rule -> '' when the page has what the rule reads, else why not (check-outcome log)."""
    raw = raw or {}
    has = lambda *ks: any(raw.get(k) for k in ks)  # noqa: E731
    return {"R43": "" if has("anchors") else ("page-loading" if raw.get("loading") else "no-anchors"),
            "R64": "" if has("multi", "panels", "expanded", "aria") else "no-stateful-controls",
            "R26": "" if has("ranges", "ratings", "numbers") else "no-ranged-values",
            "R25": "" if has("sort") else "no-active-sort",
            "R32": "" if has("lines") else "no-numbers",
            "R36": "" if has("lines") else "no-numbers",
            "R06s": "" if has("lines") else "no-numbers",
            "R72": "" if has("lines") else "no-numbers",
            "R65": "" if not raw.get("dialog_open") else "dialog-open",
            "R74": "" if has("media") else "no-media",
            "R75": "" if raw.get("svg_n") or raw.get("canvas_n") else "no-svg-or-canvas",
            "R02m": "" if raw.get("img_n") or has("media") else "no-media",
            "R01x": "",
            "R10x": "" if has("contacts") else "no-contact-links",
            "R54": "",
            "R41": "" if raw.get("_lists") or has("chart") else "no-list",
            "R02h": "",
            "R12c": "" if has("counters") else "no-character-counter",
            "R06c": "" if raw.get("_tables") else "no-table",
            "R32d": "" if has("lines") else "no-numbers",
            "R36r": "" if has("lines") else "no-numbers"}


# ---------------------------------------------------------------------------- R43, R64, R26 (D59)
def rule_anchors(raw: dict):
    from .consistency import Violation

    seen, out = set(), []
    for a in raw.get("anchors") or ():
        if not a["found"] and a["href"] not in seen:
            seen.add(a["href"])
            out.append(Violation("R43", a["href"], f"the in-page link {a['text'] or a['href']!r} points to "
                                 f"{a['href']!r}, but nothing on the page has that id or name"))
    return out


def rule_controls(raw: dict):
    from .consistency import Violation

    out = []
    for g in raw.get("multi") or ():
        if g["n"] > 1:
            what = "tabs selected" if g["role"] == "tablist" else "options checked"
            out.append(Violation("R64", f"{g['role']}|{g['label'][:40]}", f"{g['n']} {what} at once in "
                                 f"{g['label'] or 'a ' + g['role']!r}: {', '.join(g['names'])}"))
    for p in raw.get("panels") or ():
        if p["hidden"]:
            out.append(Violation("R64", f"tabpanel|{p['tab']}", f"the selected tab {p['tab']!r} shows no panel "
                                 "(its aria-controls target is hidden)"))
    for e in raw.get("expanded") or ():
        if e["hidden"]:
            out.append(Violation("R64", f"expanded|{e['control']}", f"{e['control']!r} says it is expanded "
                                 "(aria-expanded=true), but what it controls is hidden"))
    for c in raw.get("aria") or ():
        if c["aria"] in ("true", "false") and (c["aria"] == "true") != c["checked"]:
            out.append(Violation("R64", f"aria-checked|{c['label']}", f"{c['label'] or 'a control'!r} is "
                                 f"{'checked' if c['checked'] else 'unchecked'} but announces aria-checked={c['aria']}"))
    for c in raw.get("carousel") or ():
        if c["slide"] != c["indicator"]:
            out.append(Violation("R64", f"carousel|{c['label'][:30]}", f"the carousel shows slide {c['slide'] + 1}, but "
                                 f"its indicator marks slide {c['indicator'] + 1}"))
    return out


def rule_ranges(raw: dict, typed: set[str]):
    from .consistency import Violation

    out = []
    for r in raw.get("ranges") or ():
        lo = 0.0 if r["lo"] is None else r["lo"]
        hi = r["hi"]
        if hi is not None and hi > lo and not (lo - 1e-9 <= r["now"] <= hi + 1e-9):
            out.append(Violation("R26", f"{r['what']}|{r['label'][:40]}", f"{r['what']} {r['label']!r} reads "
                                 f"{r['now']:g}, outside its own range {lo:g}-{hi:g}"))
    for g in raw.get("ratings") or ():
        x, y = _f(g["x"]), _f(g["y"])
        if x is None or y is None or y not in (5, 10, 100) or x <= y:
            continue
        if not (g["unit"] or _RATING_CTX.search(g["ctx"])) or _PAGING.search(g["ctx"]):
            continue  # '12 / 10' in a pager or a date is not a rating
        out.append(Violation("R26", f"rating|{g['x']}/{g['y']}", f"a rating of {g['x']} out of {g['y']}", g["ctx"]))
    for n in raw.get("numbers") or ():
        v = _f(n["value"])
        if v is None or n["value"] in typed:
            continue  # what an agent typed and the app has not accepted yet is not the app's value
        if (n["min"] is not None and v < n["min"]) or (n["max"] is not None and v > n["max"]):
            out.append(Violation("R26", f"field|{n['label'][:40]}", f"the field {n['label'] or 'a number field'!r} "
                                 f"shows {n['value']}, outside its own limits {n['min']}-{n['max']}"))
    for t in (raw.get("timer_paused") or [])[:1]:
        out.append(Violation("R26", "timer-paused", f"the page says it is paused, but its timer moved ({t})"))
    return out


# ---------------------------------------------------------------------------- R25
_SORT_SPEC = [  # (pattern on the sort label, key kind, ascending)
    (re.compile(r"price.*(low|asc).*high|lowest price|price ?↑|cheapest", re.I), "money", True),
    (re.compile(r"price.*(high|desc).*low|highest price|price ?↓|most expensive", re.I), "money", False),
    (re.compile(r"\b(a ?(-|to|→) ?z|name.*asc|alphabetical)", re.I), "name", True),
    (re.compile(r"\b(z ?(-|to|→) ?a|name.*desc)", re.I), "name", False),
]


def sort_violations(spec_text: str, keys: list, kind: str, asc: bool) -> int | None:
    """Index of the first key that breaks the order (ties allowed; a pinned first item is skipped)."""
    vals = [k for k in keys if k is not None]
    if len(vals) < 3:
        return None
    start = 1 if len(vals) > 3 else 0  # a pinned or sponsored first item
    for i in range(start + 1, len(vals)):
        a, b = vals[i - 1], vals[i]
        if (asc and b < a) or (not asc and b > a):
            return i
    return None


def rule_sort(raw: dict, main_list: dict | None):
    from .consistency import Violation

    out = []
    for s in raw.get("sort") or ():
        if s["via"] == "column":
            keys = [parse_number(v) if re.search(r"\d", v or "") else (v or "").casefold() for v in s.get("values") or []]
            if len({type(k) for k in keys}) > 1:
                continue
            i = sort_violations(s["text"], keys, "", s.get("dir") == "ascending")
            if i is not None:
                out.append(Violation("R25", f"column|{s['text']}", f"the column {s['text']!r} is marked sorted "
                                     f"{s['dir']}, but row {i + 1} ({s['values'][i]!r}) breaks the order"))
            continue
        spec = next(((k, asc) for rx, k, asc in _SORT_SPEC if rx.search(s["text"])), None)
        if spec is None or not main_list:
            continue
        kind, asc = spec
        items = main_list["items"]
        if kind == "money":
            keys = [(lambda v: v[0] if len(v) == 1 else None)(money_values(i.get("text", ""))) for i in items]
        else:
            keys = [(i.get("name") or "").casefold() for i in items]
        i = sort_violations(s["text"], keys, kind, asc)
        if i is not None:
            out.append(Violation("R25", f"sort|{s['text']}", f"the list is sorted by {s['text']!r}, but item "
                                 f"{items[i]['name']!r} is out of order", "; ".join(str(k) for k in keys[:12])))
    return out


# ---------------------------------------------------------------------------- R41 (same page)
def rule_aggregates(lists: list[dict], counts: list[dict], totals: list[dict], raw: dict):
    from .consistency import Violation, _unit, norm

    out = []
    incomplete = bool(raw.get("pager"))
    for L in lists:
        if incomplete or not L.get("heading") or len(L["items"]) > 50:
            continue
        if any(re.search(r"view all|see all|load more|show more|more\b", i.get("name") or "", re.I) for i in L["items"]):
            continue
        words = {_unit(w) for w in re.findall(r"[A-Za-z]{3,}", L["heading"])}
        for c in counts:
            if c.get("nav") or norm(c["text"]) in norm(L["heading"]):
                continue  # a count in the list's own heading is R04's
            if _unit(c["unit"]) in words and len(words) <= 3 and c["n"] != len(L["items"]) and c["n"] < len(L["items"]) * 3:
                out.append(Violation("R41", f"count|{L['heading']}|{c['unit']}", f"{c['text']!r} on the page, but the "
                                     f"complete list {L['heading']!r} has {len(L['items'])} items"))
        for t in totals:
            if not re.search(r"total", t["label"], re.I) or not (set(re.findall(r"[a-z]{3,}", norm(t["label"]))) & words):
                continue
            amounts = [money_values(i.get("text", "")) for i in L["items"]]
            if all(len(a) == 1 for a in amounts) and amounts:
                s, v = sum(a[0] for a in amounts), parse_number(t["value"])
                if v is not None and not _close(s, v):
                    out.append(Violation("R41", f"sum|{L['heading']}", f"{t['label']} {t['value']} on the page, but the "
                                         f"amounts listed under {L['heading']!r} sum to {s:.2f}"))
    return out


# ---------------------------------------------------------------------------- R32 (in-page tables)
def rule_running_balance(tables: list[dict]):
    from .consistency import Violation, norm

    out = []
    for t in tables:
        head = [norm(h) for h in t.get("head") or []]
        bi = next((i for i, h in enumerate(head) if re.search(r"\bbalance\b", h)), None)
        ai = next((i for i, h in enumerate(head) if re.search(r"\bamount\b", h)), None)
        di = next((i for i, h in enumerate(head) if re.search(r"\b(debit|withdrawal|out)\b", h)), None)
        ci = next((i for i, h in enumerate(head) if re.search(r"\b(credit|deposit|in)\b", h)), None)
        if bi is None or (ai is None and (di is None or ci is None)):
            continue
        rows = []
        for r in t["rows"]:
            if len(r) <= bi:
                continue
            bal = parse_number(r[bi])
            if ai is not None:
                amt = parse_number(r[ai]) if len(r) > ai else None
            else:
                d = parse_number(r[di]) if len(r) > di and re.search(r"\d", r[di]) else 0.0
                c = parse_number(r[ci]) if len(r) > ci and re.search(r"\d", r[ci]) else 0.0
                amt = None if d is None or c is None else (c or 0) - abs(d or 0)
            if bal is not None and amt is not None:
                rows.append((bal, amt, r[0][:40]))
        if len(rows) < 3:
            continue

        def breaks(seq):
            return [i for i in range(1, len(seq)) if not _close(seq[i][0], seq[i - 1][0] + seq[i][1])]

        down, up = breaks(rows), breaks(rows[::-1])
        best = min((down, rows), (up, rows[::-1]), key=lambda x: len(x[0]))
        bad, seq = best
        if bad and len(bad) * 3 <= len(rows):  # most rows agree: the order is known, the break is real
            i = bad[0]
            out.append(Violation("R32", f"balance|{seq[i][2]}", f"the balance column does not step by the row's "
                                 f"amount at {seq[i][2]!r}: {seq[i - 1][0]:.2f} + {seq[i][1]:.2f} != {seq[i][0]:.2f}"))
    return out


# ---------------------------------------------------------------------------- R36, R06s, R72 (text lines)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_RX = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}),? (\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2}) ([A-Z][a-z]{2})[a-z]*\.? (\d{4})\b"), "dmy"),
]


def find_dates(line: str) -> list[date]:
    out = []
    for rx, kind in _DATE_RX:
        for m in rx.finditer(line):
            try:
                if kind == "ymd":
                    out.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
                elif kind == "mdy" and m.group(1).lower() in _MONTHS:
                    out.append((m.start(), date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))))
                elif kind == "dmy" and m.group(2).lower() in _MONTHS:
                    out.append((m.start(), date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))))
            except ValueError:
                continue
    return [d for _, d in sorted(out)]


_TIME_RANGE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\s*[-–—to]+\s*(\d{1,2}):(\d{2})\s*(am|pm)?", re.I)
_DUR = re.compile(r"\(?\b(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?\)?", re.I)
_RANGE_SEP = re.compile(r"\s(?:-|–|—|to|until)\s", re.I)


def _minutes(h: str, m: str, ap: str | None) -> int:
    h_, m_ = int(h), int(m)
    if ap:
        h_ = h_ % 12 + (12 if ap.lower() == "pm" else 0)
    return h_ * 60 + m_


def rule_lines(lines: list[str], today: date | None = None):
    """R36 intervals, R06s identities (class S of fault_families.md 5.1), R72 relative times."""
    from .consistency import Violation

    today = today or date.today()
    out, seen, state = [], set(), {}

    def add(v):
        if v.subject not in seen:
            seen.add(v.subject)
            out.append(v)

    rec = None  # R36r: [stated occurrences, the statement, dated lines seen after it]
    for ln in lines:
        low = ln.lower()
        ds = find_dates(ln)
        # ---- R36r: a recurrence statement and the dated lines that follow it
        if rec is not None:
            if len(ds) == 1 and not _RECUR.search(ln):
                rec[2] += 1
            elif rec[2]:
                _recurrence(rec, add)
                rec = None
        if (m := _RECUR.search(ln)) and not ds:
            if rec is not None and rec[2]:
                _recurrence(rec, add)
            rec = [int(m.group("n") or m.group("n2")), ln, 0]
        # ---- R26 (RC5): a score, life or move count below zero
        if (m := _COUNTER_NEG.search(ln)):
            add(Violation("R26", f"negative|{m.group(1).lower()}", f"{m.group(0)!r}: a {m.group(1).lower()} below zero", ln[:160]))
        # ---- R32d (LG4): decimals the currency does not use
        for m in _DECIMALS.finditer(ln):
            cur, dec = m.group("c") or m.group("c2"), m.group("d") or m.group("d2")
            add(Violation("R32d", f"decimals|{m.group(0)[:20]}", f"{m.group(0).strip()!r} has {len(dec)} decimals; "
                          f"{cur} amounts have {0 if cur in '¥₩' else 2}", ln[:160]))
        # ---- R36 (TM1): a stated day count against the range; both counting conventions are accepted
        if len(ds) == 2 and _RANGE_SEP.search(ln) and ds[1] >= ds[0] and (n := _DAYS.search(ln)):
            k, span = int(n.group(1)), (ds[1] - ds[0]).days
            work = sum(1 for i in range(span + 1) if (ds[0] + timedelta(days=i)).weekday() < 5)
            ok = {span, span + 1} | ({work} if re.search(r"work|business|week ?day", n.group(0), re.I) else set())
            if k not in ok:
                add(Violation("R36", f"days|{ln[:50]}", f"{ds[0]} to {ds[1]} is {span + 1} days counting both ends "
                              f"({span} between), but the page says {n.group(0).strip('() ')!r}", ln[:160]))
        # ---- R06s (DV3): a tax line with its rate, checked at the end against the bases shown
        if (m := _TAX.search(ln)) and (v := money_values(ln[m.end():])):
            state["tax"] = (float(m.group(1)), v[-1], ln)
        for k, rx in (("discount", _DISCOUNT), ("shipping", _SHIPPING)):
            if rx.match(ln) and (v := money_values(ln)):
                state[k] = abs(v[-1])
        if len(ds) == 2 and _RANGE_SEP.search(ln) and ds[1] < ds[0] and not re.search(r"\b(was|previous|from .* ago)\b", low):
            add(Violation("R36", f"range|{ln[:50]}", f"a range ends before it starts: {ln[:120]!r}"))
        # ---- R36: a time range with a stated duration that is not end - start
        m = _TIME_RANGE.search(ln)
        if m:
            a, b = _minutes(m.group(1), m.group(2), m.group(3) or m.group(6)), _minutes(m.group(4), m.group(5), m.group(6))
            span = (b - a) % (24 * 60)
            rest = ln[m.end():]
            d = re.search(r"\b(\d+)\s*h(?:ours?|rs?)?\b(?:\s*(\d+)\s*m(?:in)?)?|\b(\d+)\s*min(?:utes?)?\b", rest, re.I)
            if d:
                dur = int(d.group(1) or 0) * 60 + int(d.group(2) or 0) if d.group(1) else int(d.group(3))
                if dur and abs(dur - span) > 1:
                    add(Violation("R36", f"duration|{ln[:50]}", f"{m.group(0)!r} lasts {span} minutes, but the page says "
                                  f"{d.group(0)!r}", ln[:160]))
        # ---- R06s: 'x of y' next to 'z%'
        m = re.search(r"\b(\d+)\s*(?:of|/)\s*(\d+)\b[^%\d]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%", ln)
        if m and int(m.group(2)) > 0 and not re.search(r"\b(page|step|slide|question)\b", low):
            x, y, z = int(m.group(1)), int(m.group(2)), float(m.group(3))
            if x <= y and abs(100 * x / y - z) > 1.0 and abs(round(100 * x / y) - z) > 0.5:
                add(Violation("R06s", f"share|{m.group(0)[:40]}", f"{m.group(0)!r}: {x} of {y} is {100 * x / y:.1f}%, "
                              f"not {z:g}%", ln[:160]))
        # ---- R06s: was / now with a percentage or a saving
        if re.search(r"\b(was|before|regular|original|list price)\b", low) or "~~" in ln:
            vals = money_values(ln)
            pct = re.search(r"-\s?(\d{1,2}(?:\.\d+)?)\s?%|(\d{1,2}(?:\.\d+)?)\s?% off", ln, re.I)
            save = re.search(r"\bsave\s+((?:[$€£¥₹]|USD|EUR|GBP)\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£¥₹]))", ln, re.I)
            if len(vals) >= 2:
                was, now = max(vals[:2]), min(vals[:2])
                if pct and was > 0:
                    c = float(pct.group(1) or pct.group(2))
                    real = 100 * (was - now) / was
                    if abs(real - c) > 1.0:
                        add(Violation("R06s", f"discount|{ln[:40]}", f"{pct.group(0)!r} off {was:.2f} gives {now:.2f}, which is "
                                      f"{real:.1f}% off", ln[:160]))
                if save and (sv := parse_number(save.group(1))) is not None and not _close(sv, was - now):
                    add(Violation("R06s", f"saving|{ln[:40]}", f"{save.group(0)!r}, but {was:.2f} - {now:.2f} = {was - now:.2f}",
                                  ln[:160]))
        # ---- R06s (PX3): 'spend $X more for free shipping' against the stated threshold and the subtotal
        m = re.search(r"(?:spend|add)\s+((?:[$€£¥₹])\s?\d[\d.,]*)\s+more", ln, re.I)
        if m and state.get("threshold") is not None and state.get("subtotal") is not None:
            want = state["threshold"] - state["subtotal"]
            got = parse_number(m.group(1))
            if got is not None and want > 0 and not _close(got, want):
                add(Violation("R06s", "spend-more", f"{m.group(0)!r}, but the threshold {state['threshold']:.2f} minus the "
                              f"subtotal {state['subtotal']:.2f} is {want:.2f}", ln[:160]))
        t = re.search(r"free (?:shipping|delivery) (?:on orders )?(?:over|above|from)\s+((?:[$€£¥₹])\s?\d[\d.,]*)", ln, re.I)
        if t:
            state["threshold"] = parse_number(t.group(1))
        sub = re.match(r"sub-?total\b.*?((?:[$€£¥₹])\s?\d[\d.,]*)", ln, re.I)
        if sub:
            state["subtotal"] = parse_number(sub.group(1))
        # ---- R06s (RL3): a rating histogram against its count, and the average against the histogram
        h = re.match(r"^([1-5])\s*(?:stars?|\u2605)\s*[:\-]?\s*(\d{1,6})\b", ln, re.I)
        if h:
            state.setdefault("hist", {})[int(h.group(1))] = int(h.group(2))
        c = re.search(r"\b(\d{1,6})\s+(ratings|reviews|votes)\b", low)
        if c:
            state["rating_n"] = int(c.group(1))
        a = re.search(r"\b([0-5](?:[.,]\d)?)\s*(?:out of 5|/\s*5)\b", ln)
        if a:
            state["avg"] = _f(a.group(1))
        # ---- R72: relative status against the shown date
        if ds and re.search(r"\b(overdue|past due|upcoming|due today|due tomorrow|in (\d+) days?)\b", low):
            d0 = ds[0]
            delta = (d0 - today).days
            if re.search(r"\b(overdue|past due)\b", low) and delta > 1:
                add(Violation("R72", f"overdue|{ln[:40]}", f"marked overdue, but its date {d0} is {delta} days ahead", ln[:160]))
            elif re.search(r"\bupcoming\b", low) and delta < -1:
                add(Violation("R72", f"upcoming|{ln[:40]}", f"marked upcoming, but its date {d0} was {-delta} days ago", ln[:160]))
            elif re.search(r"\bdue today\b", low) and abs(delta) > 1:
                add(Violation("R72", f"today|{ln[:40]}", f"marked due today, but its date is {d0}", ln[:160]))
            elif (n := re.search(r"\bin (\d+) days?\b", low)) and abs(int(n.group(1)) - delta) > 1:
                add(Violation("R72", f"in-days|{ln[:40]}", f"says in {n.group(1)} days, but its date {d0} is {delta} days away",
                              ln[:160]))
    if rec is not None and rec[2]:
        _recurrence(rec, add)
    if state.get("tax") and state.get("subtotal") is not None:
        rate, tax, ln = state["tax"]
        sub_, disc, ship = state["subtotal"], state.get("discount", 0.0), state.get("shipping", 0.0)
        bases = {sub_, sub_ - disc, sub_ + ship, sub_ - disc + ship}
        if not any(abs(rate / 100 * b - tax) <= 0.0051 + 1e-9 for b in bases):
            out.append(Violation("R06s", "tax", f"a tax of {rate:g}% shown as {tax:.2f}, but {rate:g}% of the subtotal "
                                 f"{sub_:.2f} is {rate / 100 * sub_:.2f}", ln[:160]))
    hist = state.get("hist") or {}
    if len(hist) == 5:
        total = sum(hist.values())
        if state.get("rating_n") is not None and total != state["rating_n"]:
            out.append(Violation("R06s", "histogram", f"the rating histogram sums to {total}, the page says "
                                 f"{state['rating_n']} ratings"))
        if state.get("avg") is not None and total:
            mean = sum(k * v for k, v in hist.items()) / total
            if abs(mean - state["avg"]) > 0.1:
                out.append(Violation("R06s", "average", f"the ratings listed average {mean:.2f}, the page shows "
                                     f"{state['avg']:g}"))
    return out


_RECUR = re.compile(r"\b(?:daily|weekly|monthly|yearly|every \w+)\b[^\d]{0,20}(?P<n>\d{1,3})\s*(?:times|occurrences)\b|"
                    r"\b(?:repeats|ends after)\s+(?P<n2>\d{1,3})\s*(?:times|occurrences)\b", re.I)
_COUNTER_NEG = re.compile(r"\b(score|lives|life|health|hp|coins|moves|points|level)\s*[:=]?\s*(-\s?\d+)\b", re.I)
_DECIMALS = re.compile(r"(?P<c>[$£])\s?\d{1,3}(?:,\d{3})*\.(?P<d>\d|\d{3,})(?![\d,%])|(?P<c2>[¥₩])\s?\d[\d,]*\.(?P<d2>\d{1,2})(?!\d)")
_DAYS = re.compile(r"\(?\b(\d{1,3})\s+(?:(?:work(?:ing)?|business|week) ?)?days?\b\)?", re.I)
_TAX = re.compile(r"^(?:sales )?(?:tax|vat|gst|hst)\b[^%\d]{0,10}\(?\s*(\d{1,2}(?:\.\d+)?)\s?%\)?", re.I)
_DISCOUNT = re.compile(r"^(discount|coupon|promo|savings?)\b", re.I)
_SHIPPING = re.compile(r"^(shipping|delivery|postage)\b", re.I)


def _recurrence(rec: list, add) -> None:
    from .consistency import Violation

    n, ln, k = rec
    if k >= 2 and k != n:
        add(Violation("R36r", f"recurrence|{ln[:40]}", f"{ln[:80]!r} states {n} occurrences, but {k} dated ones are "
                      "listed after it", ln[:160]))


# ---------------------------------------------------------------------------- R06c, R41 charts, R35 limits, R74 playlists
_TOTAL_ROW = re.compile(r"^(grand )?totals?\b|^sum\b", re.I)
_NOT_ADDITIVE = re.compile(r"avg|average|mean|%|rate|price|unit|per\b|ratio|median|balance|date|#|\bid\b", re.I)


def rule_column_totals(tables: list[dict]):
    """R06c (AG3): a 'Total' row whose cell differs from the sum of the rows above it in that column."""
    from .consistency import Violation

    out = []
    for t in tables:
        rows, head = t.get("rows") or [], t.get("head") or []
        tot = next((r for r in rows if r and _TOTAL_ROW.match((r[0] or "").strip())), None)
        if tot is None:
            continue
        body = [r for r in rows if r is not tot and r and not re.match(r"^(sub-?total|average|avg|mean)\b", (r[0] or "").strip(), re.I)]
        for j in range(1, len(tot)):
            if j < len(head) and _NOT_ADDITIVE.search(head[j] or ""):
                continue
            want = parse_number(tot[j]) if re.search(r"\d", tot[j] or "") else None
            vals = [parse_number(r[j]) for r in body if len(r) > j and re.search(r"\d", r[j] or "")]
            if want is None or len(vals) < 2 or any(v is None for v in vals) or len(vals) < len(body) - 1:
                continue
            if not _close(sum(vals), want):
                col = head[j] if j < len(head) and head[j] else f"column {j + 1}"
                out.append(Violation("R06c", f"total|{col[:30]}", f"the total row shows {tot[j]!r} for {col!r}, but the "
                                     f"rows above sum to {sum(vals):.2f}"))
    return out


def norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def rule_chart(raw: dict, tables: list[dict]):
    """R41 (AG2): a chart's labelled values (aria-label or title 'Jan: 12') against a table with the same labels."""
    from .consistency import Violation

    chart = {norm_label(c["label"]): v for c in raw.get("chart") or () if (v := parse_number(c["value"])) is not None}
    if len(chart) < 2:
        return []
    out = []
    for t in tables:
        cells = {norm_label(r[0]): r[1:] for r in t.get("rows") or [] if r and norm_label(r[0]) in chart}
        if len(cells) < 2:
            continue
        for lab, rest in cells.items():
            nums = [parse_number(x) for x in rest if re.search(r"\d", x or "")]
            if nums and all(n is not None for n in nums) and not any(_close(n, chart[lab]) for n in nums):
                out.append(Violation("R41", f"chart|{lab[:30]}", f"the chart labels {lab!r} with {chart[lab]:g}, its table "
                                     f"shows {', '.join(f'{n:g}' for n in nums[:3])}"))
                break
    return out


_LIMIT = re.compile(r"\b(?:up to|max(?:imum)?(?: of)?|limit(?:ed)? (?:of|to)|you can (?:have|create))\s+(\d{1,4})\s+([a-z]+s)\b", re.I)


def rule_limits(plain: str, lists: list[dict], raw: dict):
    """R35 (CP1): the page states a limit ('Free plan: up to 3 projects') and its own complete list of that
    kind holds more."""
    from .consistency import Violation, _unit

    if raw.get("pager"):
        return []
    for m in _LIMIT.finditer(plain or ""):
        n, unit = int(m.group(1)), _unit(m.group(2))
        for L in lists:
            words = {_unit(w) for w in re.findall(r"[A-Za-z]{3,}", L.get("heading") or "")}
            if unit in words and n < len(L["items"]) <= 50:
                return [Violation("R35", f"limit|{unit}", f"the page says {m.group(0)!r}, but {L['heading']!r} lists "
                                  f"{len(L['items'])}")]
    return []


_TRACKS = re.compile(r"\b(\d{1,4})\s+(?:tracks?|songs?|episodes?|videos?)\b[^\d]{0,6}(?:(\d{1,2})\s*h(?:ours?|r)?\s*)?(\d{1,3})\s*min", re.I)
_DUR_ITEM = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])")


def rule_playlist(plain: str, lists: list[dict], raw: dict):
    """R74 (MD2): a playlist's stated track count or total length against the tracks it lists."""
    from .consistency import Violation

    m = _TRACKS.search(plain or "")
    if not m or raw.get("pager"):
        return []
    best, durs = None, []
    for L in lists:
        d = [_DUR_ITEM.search(i.get("text") or "") for i in L["items"]]
        if len(L["items"]) >= 2 and all(d):
            best, durs = L, d
            break
    if best is None:
        return []
    out = []
    if int(m.group(1)) != len(best["items"]) and len(best["items"]) <= 50:
        out.append(Violation("R74", "track-count", f"the page says {m.group(0)!r}, but {len(best['items'])} are listed"))
    secs = sum((3600 * int(x.group(1)) + 60 * int(x.group(2)) + int(x.group(3))) if x.group(3) else
               (60 * int(x.group(1)) + int(x.group(2))) for x in durs)
    stated = 60 * (int(m.group(2) or 0) * 60 + int(m.group(3)))
    if abs(secs - stated) > 90:
        out.append(Violation("R74", "total-length", f"the page says {m.group(0)!r}, but the tracks listed add up to "
                             f"{secs // 60} min"))
    return out


# ---------------------------------------------------------------------------- R65, R74, R75, R02m, R01x, R10x
def _typed_address(url: str, typed: set[str]) -> bool:
    """D62 (I85): the address is one the testers typed (an image URL in a profile, a link in an article body), or a
    relative value the page resolved against its own origin ('not-a-url'): the app shows what it was given."""
    from urllib.parse import unquote

    u = unquote(url or "").rstrip("/")
    return any(len(t.strip()) >= 4 and (t.strip().rstrip("/") in u or (u and u in t)) for t in typed)


def rule_presentation(raw: dict, typed: set[str] = frozenset()):
    from .consistency import Violation

    out = []
    for c in (raw.get("covered") or [])[:3]:
        if c["control"]:
            out.append(Violation("R65", f"covered|{c['control']}", f"the control {c['control']!r} is covered by another "
                                 f"element ({c['by']}): a click lands on that instead"))
    if raw.get("overflow"):
        out.append(Violation("R65", "overflow", "the page is wider than the window: it scrolls sideways"))
    for t in (raw.get("invisible") or [])[:2]:
        out.append(Violation("R65", f"invisible|{t[:30]}", f"the text {t!r} is drawn in its background colour"))
    for t in (raw.get("clipped") or [])[:2]:
        out.append(Violation("R65", f"clipped|{t[:30]}", f"the text {t!r} is cut off by its box (overflow hidden, no "
                             "ellipsis)"))
    media = raw.get("media") or []
    playing = [m for m in media if not m["paused"]]
    if len(playing) > 1:
        out.append(Violation("R74", "two-playing", f"{len(playing)} media players play at the same time"))
    for m in media:
        if not m["paused"] and m["ready"] >= 3 and m["advanced"] <= 0.05 and m["duration"] not in (None,) and \
                (m["duration"] or 0) > 2 and not math.isinf(m["duration"] or 0):
            out.append(Violation("R74", f"stalled|{m['kind']}", f"a {m['kind']} reports playing, but its time did not "
                                 "advance in one second"))
        if m["button"] and ((m["button"].lower() == "play" and not m["paused"]) or (m["button"].lower() == "pause" and m["paused"]
                                                                                   and m["advanced"] == 0 and m["ready"] >= 1)):
            if m["button"].lower() == "play" and not m["paused"]:
                out.append(Violation("R74", f"label|{m['kind']}", f"the {m['kind']} plays while its button says 'Play'"))
    for b in (raw.get("svg_bad") or [])[:2]:
        out.append(Violation("R75", f"svg|{b.split('=')[0]}", f"an SVG shape has a non-numeric geometry attribute: {b}"))
    for c in (raw.get("canvas_blank") or [])[:1]:
        out.append(Violation("R75", f"canvas|{c}", f"the canvas {c!r} stays blank after the page loaded"))
    for c in (raw.get("canvas_frozen") or [])[:1]:
        out.append(Violation("R75", f"frozen|{c}", f"the page offers to pause, but the canvas {c!r} did not change in a "
                             "second"))
    for b in (raw.get("svg_outside") or [])[:1]:
        out.append(Violation("R75", f"outside|{b.split(' ')[0]}", f"an SVG shape lies entirely outside its viewBox ({b})"))
    for h in [h for h in raw.get("hosts") or () if not _typed_address(h["href"], typed)][:2]:
        out.append(Violation("R02h", f"host|{h['why']}", f"the link {h['text'] or h['href']!r} points to {h['href']!r} "
                             f"({h['why']}): a development or placeholder address"))
    for c in (raw.get("empty_cta") or [])[:1]:
        out.append(Violation("R02h", f"empty|{c['text'][:30]}", f"the call to action {c['text']!r} links to "
                             f"{c['href']!r} and has no handler of its own"))
    for c in raw.get("counters") or ():
        units, points, mx = c["units"], c["points"], c["max"]
        if c["a"] is not None and c["b"] == mx and c["a"] not in (units, points, mx - units, mx - points):
            out.append(Violation("R12c", f"counter|{c['label'][:30]}", f"the counter of {c['label'] or 'a field'!r} shows "
                                 f"{c['a']}/{c['b']}, but the field holds {points} characters"))
        if c["left"] is not None and c["left"] not in (mx - units, mx - points):
            out.append(Violation("R12c", f"left|{c['label'][:30]}", f"{c['label'] or 'a field'!r} says {c['left']} "
                                 f"characters left, but {mx} - {points} = {mx - points}"))
    for c in (raw.get("chips") or [])[:1]:
        out.append(Violation("R68", f"duplicate|{c['dup'][:30]}", f"the tag {c['dup']!r} is shown twice on one item"))
    for b in [b for b in raw.get("broken") or () if b["src"] and not _typed_address(b["src"], typed)][:3]:
        if not re.search(r"pixel|track|beacon|1x1|spacer", b["src"], re.I):
            out.append(Violation("R02m", f"{b['what']}|{b['src'][-60:]}", f"the {b['what']} {b['alt'] or b['src']!r} failed "
                                 "to load", b["src"]))
    for c in raw.get("contacts") or ():
        h = c["href"]
        if h.startswith("mailto:") and not re.match(r"mailto:[^@\s?]+@[^@\s?]+\.[a-z]{2,}", h, re.I):
            out.append(Violation("R10x", f"mailto|{h[:40]}", f"the e-mail link {c['text'] or h!r} has no valid address ({h})"))
        if h.startswith("tel:") and len(re.sub(r"\D", "", h)) < 3:
            out.append(Violation("R10x", f"tel|{h[:40]}", f"the phone link {c['text'] or h!r} has no number ({h})"))
        shown_mail = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", c["text"] or "")
        target = h[7:].split("?")[0].lower()
        if h.startswith("mailto:") and shown_mail and shown_mail.group(0).lower() != target:
            out.append(Violation("R10x", f"mailto-text|{h[:40]}", f"the link shows {shown_mail.group(0)!r} but writes to "
                                 f"{target!r}"))
        td, hd = re.sub(r"\D", "", c["text"] or ""), re.sub(r"\D", "", h)
        if h.startswith("tel:") and len(td) >= 7 and len(hd) >= 7 and td[-7:] != hd[-7:]:
            out.append(Violation("R10x", f"tel-text|{h[:40]}", f"the link shows the number {c['text']!r} but dials {h[4:]!r}"))
    return out


_KEYS = re.compile(r"(?<![\w./@-])([a-z][a-z0-9]*(?:[._][a-z0-9]+){2,})(?![\w./@-])")
_FILEISH = re.compile(r"\.(js|css|png|jpe?g|svg|html?|json|php|py|md|txt|xml|pdf|csv|zip|io|com|org|net|dev|app)$", re.I)
_PLACEHOLDER = re.compile(r"\blorem ipsum\b|\b(TODO|FIXME|TBD)\b:?|\bplaceholder text\b|\{\{\s*\w+\s*\}\}|%\(\w+\)s", re.I)


def rule_placeholders(plain: str, typed: set[str]):
    """R01x: message keys left untranslated ('auth.login.title', 'messages.welcome_title') and placeholder text."""
    from .consistency import Violation

    text = plain or ""
    for t in sorted(typed, key=len, reverse=True):
        if len(t) >= 2:
            text = text.replace(t, " ")
    out = []
    keys = [k for k in _KEYS.findall(text) if not _FILEISH.search(k) and not re.search(r"\d", k.split(".")[0])
            and "." in k and ("_" in k or k.count(".") >= 2) and not re.match(r"^(e\.g|i\.e|etc)\b", k)]
    # D62 (I95): a key needs its namespace ('common.privacy_policy'); a bare 'maintenance_action_run' is an event code
    # (BookStack's audit log lists them by design)
    if keys:
        out.append(Violation("R01x", f"key|{keys[0][:40]}", f"untranslated message key shown: {keys[0]!r}"))
    m = _PLACEHOLDER.search(text)
    if m:
        out.append(Violation("R01x", f"placeholder|{m.group(0)[:20].lower()}", f"placeholder text shown: {m.group(0)!r}",
                             text[max(0, m.start() - 40):m.end() + 40]))
    return out


def rule_norms(raw: dict | None, typed: set[str], facts=None, today: date | None = None) -> list:
    if not raw:
        return []
    out = rule_anchors(raw) + rule_controls(raw) + rule_ranges(raw, typed) + rule_presentation(raw, typed)
    if facts is not None:
        out += rule_sort(raw, facts.main_list())
        out += rule_aggregates(facts.content_lists(), facts.counts, facts.totals, raw)
        out += rule_running_balance(facts.tables)
        out += rule_placeholders(facts.plain, typed)
        out += rule_column_totals(facts.tables)
        out += rule_chart(raw, facts.tables)
        out += rule_limits(facts.plain, facts.content_lists(), raw)
        out += rule_playlist(facts.plain, facts.content_lists(), raw)
    out += rule_lines(raw.get("lines") or [], today)
    return out
