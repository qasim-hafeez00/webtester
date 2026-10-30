# Extraction benchmark (v5 plan O6 d, D60)

Hand-labelled pages for measuring the fact extraction every rule depends on (`consistency.AUDIT_JS`, the
`Facts` it returns). Each page is `<name>.html` with `<name>.toml` beside it:

```toml
h1 = "Books"
[[list]]                 # a content list: its heading and the names of its items, in order
heading = "Recently Updated Books"
items = ["Atlas Q7", "Book Two"]
[[count]]                # a count shown with a unit
n = 12
unit = "books"
[[total]]                # a labelled amount
label = "Total"
value = "$40.00"
```

Score: `python scripts/extraction_bench.py` prints precision and recall per fact kind (headings, list items,
counts, totals) over every labelled page. Target size 60 pages (development apps, clean corpus, synthetic);
the three `synthetic_*` pages are the seed. Label pages as a person sees them, not as the code reads them.
