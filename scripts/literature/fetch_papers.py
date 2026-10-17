"""Resolve catalog entries to metadata + PDFs and build literature/README.md.

Usage:
    python scripts/literature/fetch_papers.py            # resolve new entries, download missing PDFs, rebuild README
    python scripts/literature/fetch_papers.py --refresh  # re-resolve every entry
    python scripts/literature/fetch_papers.py --readme   # only rebuild README from papers.json

Sources: OpenAlex (venue, year, DOI, citations, open-access links) and the arXiv API
(preprint metadata and PDFs). No API keys and no personal data are sent.
"""
import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalog import CATEGORIES, PAPERS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LIT = ROOT / "literature"
PDF_DIR = LIT / "pdfs"
DB = LIT / "papers.json"
UA = "Mozilla/5.0 (research literature fetcher; academic use)"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

sys.stdout.reconfigure(encoding="utf-8")


def get(url, timeout=60, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else data.decode("utf-8", "replace")


def norm(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower().replace("-", " ")).strip()


def similar(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if len(a) < 25 and b.startswith(a):  # short names such as "MemoDroid"
        return 0.95
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- OpenAlex
META_FIELDS = ("tier", "cat", "gaps", "course10", "rank", "why", "venue_override")
OA_FIELDS = "id,title,publication_year,doi,primary_location,best_oa_location,locations,authorships,cited_by_count,type"


def openalex_by_doi(doi):
    try:
        return json.loads(get(f"https://api.openalex.org/works/doi:{doi}?select={OA_FIELDS}"))
    except Exception:
        return None


def openalex_search(title):
    q = urllib.parse.urlencode({"search": title, "per-page": 15, "select": OA_FIELDS})
    try:
        res = json.loads(get(f"https://api.openalex.org/works?{q}"))["results"]
    except Exception:
        return []
    scored = [(similar(title, w.get("title")), w) for w in res]
    return [w for s, w in sorted(scored, key=lambda x: -x[0]) if s >= 0.88]


def is_arxiv_source(w):
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    return "arxiv" in src.lower() or (w.get("doi") or "").lower().startswith("https://doi.org/10.48550")


def venue_of(w):
    return ((w.get("primary_location") or {}).get("source") or {}).get("display_name")


def pdf_links(w):
    links = []
    for loc in [w.get("best_oa_location")] + (w.get("locations") or []):
        if loc and loc.get("pdf_url"):
            links.append(loc["pdf_url"])
    return links


# ---------------------------------------------------------------- arXiv
def arxiv_query(params):
    time.sleep(3)  # arXiv API etiquette
    xml = get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params))
    out = []
    for e in ET.fromstring(xml).iter(ATOM + "entry"):
        aid = e.findtext(ATOM + "id", "").rsplit("/abs/", 1)[-1]
        if not aid or "api/" in aid:
            continue
        out.append(dict(
            arxiv=re.sub(r"v\d+$", "", aid),
            title=" ".join(e.findtext(ATOM + "title", "").split()),
            year=int(e.findtext(ATOM + "published", "0000")[:4]),
            authors=[a.findtext(ATOM + "name") for a in e.iter(ATOM + "author")],
            journal_ref=e.findtext(ARXIV_NS + "journal_ref"),
            comment=e.findtext(ARXIV_NS + "comment"),
        ))
    return out


def arxiv_by_id(aid):
    r = arxiv_query({"id_list": aid})
    return r[0] if r else None


def arxiv_by_title(title):
    words = " AND ".join(f"ti:{w}" for w in norm(title).split()[:12] if len(w) > 2)
    try:
        cands = arxiv_query({"search_query": words, "max_results": 5})
    except Exception:
        return None
    best = max(cands, key=lambda c: similar(title, c["title"]), default=None)
    return best if best and similar(title, best["title"]) >= 0.88 else None


# ---------------------------------------------------------------- resolve
def resolve(p):
    rec = {k: p.get(k) for k in ("id",) + META_FIELDS[:-1]}
    rec["venue_override"] = p.get("venue")
    rec.update(query_title=p["title"], notes=[])

    published, preprint = None, None
    if p.get("doi"):
        published = openalex_by_doi(p["doi"])
    hits = openalex_search(p["title"]) if not published else []
    for w in hits:
        if not is_arxiv_source(w) and not published:
            published = w
        elif is_arxiv_source(w) and not preprint:
            preprint = w

    ax = arxiv_by_id(p["arxiv"]) if p.get("arxiv") else arxiv_by_title(p["title"])

    best = published or preprint
    rec["title"] = (best or {}).get("title") or (ax or {}).get("title") or p["title"]
    if best and best.get("authorships"):
        names = [a["author"]["display_name"] for a in best["authorships"]]
    else:
        names = (ax or {}).get("authors") or []
    rec["authors"] = names
    rec["year"] = (published or {}).get("publication_year") or (ax or {}).get("year") or (preprint or {}).get("publication_year")
    rec["venue"] = venue_of(published) if published and not is_arxiv_source(published) else None
    rec["doi"] = p.get("doi") or ((published or {}).get("doi") or "").replace("https://doi.org/", "") or None
    rec["arxiv"] = (ax or {}).get("arxiv")
    rec["arxiv_journal_ref"] = (ax or {}).get("journal_ref")
    rec["arxiv_comment"] = (ax or {}).get("comment")
    rec["citations"] = max((published or {}).get("cited_by_count") or 0, (preprint or {}).get("cited_by_count") or 0)
    rec["peer_reviewed_found"] = bool(rec["venue"])
    rec["pdf_candidates"] = ([f"https://arxiv.org/pdf/{rec['arxiv']}"] if rec["arxiv"] else []) \
        + pdf_links(published or {}) + pdf_links(preprint or {})
    if not best and not ax:
        rec["notes"].append("NOT RESOLVED: check title manually")
    return rec


def download(rec):
    dest = PDF_DIR / f"{rec['id']}.pdf"
    if dest.exists() and dest.stat().st_size > 10_000:
        rec["pdf"] = dest.relative_to(LIT).as_posix()
        return
    rec["pdf"] = None
    for url in dict.fromkeys(rec["pdf_candidates"]):
        try:
            data = get(url, timeout=90, raw=True)
        except Exception:
            continue
        if data[:5] == b"%PDF-" and len(data) > 10_000:
            dest.write_bytes(data)
            rec["pdf"] = dest.relative_to(LIT).as_posix()
            rec["pdf_source"] = url
            return
        time.sleep(1)


# ---------------------------------------------------------------- README
def fmt_authors(a):
    return ", ".join(a[:3]) + (" et al." if len(a) > 3 else "") if a else "?"


def link(rec):
    parts = []
    if rec.get("doi"):
        parts.append(f"[DOI](https://doi.org/{rec['doi']})")
    if rec.get("arxiv"):
        parts.append(f"[arXiv](https://arxiv.org/abs/{rec['arxiv']})")
    return " · ".join(parts) or "-"


def build_readme(db):
    recs = [db[p["id"]] for p in PAPERS if p["id"] in db]
    n_pdf = sum(1 for r in recs if r.get("pdf"))
    lines = [
        "# Literature Index",
        "",
        f"Auto-generated by `scripts/literature/fetch_papers.py` on {date.today().isoformat()} from "
        "`scripts/literature/catalog.py`. Edit the catalog, not this file.",
        "",
        f"**{len(recs)} papers** · **{n_pdf} PDFs downloaded** · "
        f"**{sum(1 for r in recs if r['course10'])} eligible for the course list of 10**",
        "",
        "Metadata comes from OpenAlex and arXiv. **Ranks marked (verify) are not yet proven**: before "
        "submission, save a CORE portal screenshot (conferences) or a Scopus/JCR quartile page (journals), "
        "at least for the base paper.",
        "",
        "Legend: **T1** core (read in full) · **T2** closely related · **T3** foundations/methods · "
        "Gaps: **G1** parallel coordination · **G2** evidence gate · **G3** spec-free oracles · "
        "**EVAL** benchmark/metrics · ⭐ base paper · ✅ PDF in `pdfs/` · ❌ PDF needs manual download",
        "",
    ]
    for tier, heading in (("T1", "T1 · Core papers"), ("T2", "T2 · Closely related and competitors"),
                          ("T3", "T3 · Foundations and methodology")):
        lines += [f"## {heading}", "",
                  "| # | Paper | Authors | Year | Venue (as indexed) | Rank | Gaps | Links | PDF | Why it matters |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate([r for r in recs if r["tier"] == tier], 1):
            star = "⭐ " if "BASE" in (r["gaps"] or "") else ""
            c10 = " · *course-10*" if r["course10"] else ""
            venue = r.get("venue_override") or r.get("venue") or ("arXiv" + (f" ({r['arxiv_journal_ref']})" if r.get("arxiv_journal_ref") else "")
                                       if r.get("arxiv") else "?")
            pdf = f"✅ [pdf]({r['pdf']})" if r.get("pdf") else "❌"
            if r.get("pdf") and "arxiv.org" in (r.get("pdf_source") or "") and (r.get("venue") or r.get("venue_override")):
                pdf += " (arXiv version; cite the published one)"
            note = (" ⚠ " + "; ".join(r["notes"])) if r.get("notes") else ""
            lines.append(
                f"| {i} | {star}**{r['title']}**{c10} | {fmt_authors(r['authors'])} | {r.get('year') or '?'} | "
                f"{venue} | {r['rank']} | {r['gaps'] or '-'} | {link(r)} | {pdf} | {r['why']}{note} |")
        lines.append("")
    lines += ["## By topic", ""]
    for cat, label in CATEGORIES.items():
        ids = [r["id"] for r in recs if r["cat"] == cat]
        if ids:
            lines.append(f"- **{label}**: " + ", ".join(f"`{i}`" for i in ids))
    missing = [r for r in recs if not r.get("pdf")]
    if missing:
        lines += ["", "## PDFs to fetch manually (paywalled or blocked)", "",
                  "Use the university library proxy or the authors' pages, and save as `pdfs/<id>.pdf`.", ""]
        lines += [f"- `{r['id']}`: {r['title']} ({link(r)})" for r in missing]
    (LIT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--readme", action="store_true")
    args = ap.parse_args()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    db = json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else {}
    if not args.readme:
        for p in PAPERS:
            if p["id"] in db and not args.refresh:
                rec = db[p["id"]]
                rec.update({k: p.get(k) for k in META_FIELDS[:-1]})
                rec["venue_override"] = p.get("venue")
            else:
                print(f"resolve  {p['id']}", flush=True)
                rec = resolve(p)
            download(rec)
            db[p["id"]] = rec
            print(f"  {'PDF' if rec.get('pdf') else '---'}  {rec.get('year')}  {rec.get('venue') or 'arXiv/?'}  | {rec['title'][:80]}", flush=True)
            DB.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    build_readme(db)
    print(f"done: {len(db)} records, {sum(1 for r in db.values() if r.get('pdf'))} PDFs")


if __name__ == "__main__":
    main()
