# BookStack: second subject app (WebTestPilot benchmark)

A wiki/documentation app (shelves → books → chapters → pages, comments, favourites, search, roles, settings), run locally in Docker with the **injected faults of the WebTestPilot benchmark** (FSE'26, our base paper). It exists to test whether results from Conduit hold on an app, and on faults, that we did not design. Decisions: D31–D37 in [logs/decisions.md](../../logs/decisions.md).

```
python -m webtester --config configs/bookstack.toml app up --faults all     # first start ~3-5 min (image pull)
python apps/bookstack/faults/verify_faults.py --expect on                    # environment + fault check
python -m webtester --config configs/bookstack.toml app reset
```
URL: http://127.0.0.1:4200. Accounts: `workerNN@bookstack.test` / `password` (NN = 01..16), and the benchmark's `admin@admin.com` / `password`.

## Provenance

| Part | Source | Version | Changed? |
|---|---|---|---|
| App | `solidnerd/bookstack` Docker image | `25.2.1` (as pinned by the benchmark) | no |
| DB | `mysql` Docker image | `8.4` | no |
| `environment/baseline.sql`, `environment/seed.sql` | [code-philia/WebTestPilot-benchmark](https://github.com/code-philia/WebTestPilot-benchmark) `bookstack/environment/` | commit `b3055bf7` (2026-10-01), submodule of WebTestPilot `26ed5ad8` | **no** (byte-identical, [VENDORED.sha256](VENDORED.sha256)) |
| `faults/wtp/bugs/*.js` (27), `faults/wtp/bug_injector.js` | same repo, `bookstack/bugs/` and `runtime/` | same | **no** (byte-identical) |
| Everything else here | written by us | | |

License: the WebTestPilot repository is CC BY 4.0 (attribution: Teoh et al., "WebTestPilot", FSE 2026, doi 10.1145/3797115). The benchmark sub-repository has no license file of its own (issue I21).

## How the benchmark works, and why we adapted it

In the benchmark, each of the 100 test cases runs in a fresh Compose stack with a browser container: a setup function logs in as the admin, **one** bug script is registered as a Playwright init script, and the tester follows that test's natural-language steps. A bug is a JavaScript condition (`isConditionMet`) plus a DOM mutation (`onConditionMet`), armed only after the scripted login. It fires during the very flow that tests it. That design measures **spec-driven** detection. We explore **without** a spec, with all faults active at once, so:

### Environment adaptations (E1–E6, decision D34)

| # | Change | Why |
|---|---|---|
| E1 | No per-task browser container or CDP proxy. Our harness launches its own browsers. | We run N workers from one process. |
| E2 | `APP_URL=http://127.0.0.1:4200` and port 4200 published on localhost only (was `http://webapp:8080`, internal) | BookStack writes absolute links from APP_URL. Links to an internal host name would leave our scope gate. |
| E3 | `CACHE_DRIVER=array`, `CACHE_STORE=array` | A cached setting would survive the DB reset between runs. |
| E4 | Image used directly (their `app.Dockerfile` only adds `patch` and build tools on top of it) | Nothing in our setup patches the app. |
| E5 | **Worker accounts** `worker01..16` (ids 101–116, Admin role, admin's password hash), each with a copy of the admin's seeded favourites and views ([agentic/workers.sql](agentic/workers.sql)) | One account per worker, as on Conduit (plan section 10). The copies matter: several faults act on per-user state (My Favourites, Recently Viewed). |
| E6 | **Reset** = restore a snapshot of the migrated, unseeded DB, then reload `seed.sql` with dates = yesterday (as their `seed-loader.sh` does), then the worker accounts ([agentic/](agentic/)), under a MySQL named lock. `app up` waits for the seed-loader (D39). Sessions are file-based and not touched. | Like Conduit's `agentic_reset()`: **3.1–6.0 s measured** (Conduit about 1 s), run before every run and every evidence-gate replay. Re-seeding keeps "N hours/days ago" texts the same as in the benchmark. Valid sessions let the gate replay with a worker's cookies. |

### Injector adaptations (A1–A5, decision D33)

[faults/build_injected.py](faults/build_injected.py) merges all 27 scripts into one init script, [faults/injected.js](faults/injected.js), with the benchmark's own merge function (its `prepare_bug_script`). Each script gets its own injector namespace, so all of them coexist. The bug bodies are **not** changed. The builder asserts that each change applies exactly once.

| # | Change | Why |
|---|---|---|
| A1 | Removed the activation flag (`sessionStorage '__flash_ui_active__'`, set after their scripted login) | Exploration has no such moment. Faults are armed from the first page. |
| A2 | `sessionStorage` → `localStorage` for the trigger state | One worker uses several tabs (inferred-oracle reload checks open a new tab), and the evidence gate restores a worker's storage before replaying. With localStorage a fired fault persists for that worker, the way a server-side bug would. |
| A3 | First firing logs `[wt-fault] <id> <script> visible\|no-change` (DOM compared before and after the effect, D38) | Exposure ground truth. The harness records it in the trace and never treats it as a finding. Only `visible` counts as exposed. A trigger that changed nothing (e.g. the 'New Book' fault with no such book) is logged separately. |
| A4 | Each script runs only if its fault id is in `window.__WT_FAULTS__` (set from `app up --faults`) | Same switchboard as Conduit's `FAULTS`. |
| A5 | Arm only on http(s) pages. Every call into injected code goes through a guard that logs `[wt-fault-error]` instead of throwing. | Init scripts also run on `about:blank` and editor iframes, where storage access throws. Our implicit oracles would report such errors as app bugs. The benchmark never watches page errors. |

## Injected faults

27 scripts = **18 distinct faults** (identical or same-effect scripts merged). Full ground truth: [faults/faults.toml](faults/faults.toml).

- **Classes** (the benchmark's own): missing UI element ×4 (BS01–BS03, BS13), data inconsistency ×14.
- **Reachable by exploration: 13** (BS01–BS13). They fire on ordinary pages with the seeded data.
- **Not reachable without the spec: 5** (BS14–BS18). Each needs a literal that only the benchmark's test case types: a book named 'New Book' or 'Updated Book', a sort rule 'New Sort Rule', a comment 'I like this template', or a page 'New Page' in 'Book'. We keep them active and report them, but the primary recall denominator is the 13 reachable faults (D32).
- **None is a crash.** Implicit oracles can detect none of them, only inferred oracles (G3). Detection is labelled by hand (D30). Exposure (a fault fired in a worker's browser) is recorded automatically (D36).

## Known limitations (also in logs/issues.md)

- The faults are client-side DOM mutations, not source-level faults (the benchmark's design). A fault re-applies on later visits to the same URL in a worker's session (A2), but a different worker never sees another worker's fault effect.
- The benchmark's oracles are **relational**: "the list is consistent with the Created Content counts", "in chronological order". Our G3 check language is single-page text, counters, routes and no-op (D27). Lower recall on BookStack than on Conduit is expected, and it is a finding in itself (I22).
- Some effects need data a fresh worker lacks: BS05–BS07 add phantom entries only to non-empty "Recently Created" lists (visible on `/user/admin` or after the worker creates content), and BS09 needs activity on Book1 (I23).
- BS10 fires on book and shelf pages only. In 25.2.1 chapter pages and page views have no Recent Activity block, so two of its three benchmark scripts cannot fire on the page their own test case is about (I27).

## Verification (16 Oct 2026, logs in [logs/bookstack_setup/](../../logs/bookstack_setup/))

- `verify_faults.py`: **PASS on** (13/13 reachable faults fire visibly, 4 effect checks hold) and **PASS off** (none fires). No page or console errors on any visited page.
- B0 crawler smoke run, 2 workers, 5 min (run `20261016-151730_bookstack_b0_n2_bssmoke3`): **visible exposure of exactly BS01–BS13**, BS15/BS18 trigger-only, 0 findings, 0 injector errors.
- Problems found and fixed on the way: I28 (app-up/reset race), I30 (exposure measurement), and two trigger corrections in `faults.toml` (I23, I27).
