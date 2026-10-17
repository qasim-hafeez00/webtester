# RealWorld / Conduit: development subject app

A Medium-style blogging app with sign-up and login, articles, comments, tags, favorites, follows, feeds and settings, run fully locally in Docker.

```
docker compose up -d --build          # first time builds the images (~5 min)
open http://127.0.0.1:4100
```

From the repo root, the harness wraps these steps:

```
python -m webtester app up [--faults F01,F02]    # (re)start with a fault set
python -m webtester app reset                    # restore seeded data (~1 s)
python -m webtester app status
```

## Provenance

| Part | Source | Version |
|---|---|---|
| `backend/` | [gothinkster/node-express-realworld-example-app](https://github.com/gothinkster/node-express-realworld-example-app) (Express, Prisma, Postgres; MIT) | commit `30b68e1`, 2024-01-04 |
| `frontend/` | Angular Conduit as instrumented by **AutoE2E / E2EBench** ([parsaalian/autoe2e](https://github.com/parsaalian/autoe2e) `benchmark/realworld`; MIT). The `logToServer` calls are E2EBench's feature-coverage instrumentation. | commit `6f53605`, 2024-10-09 |
| Theme CSS | [realworld-apps/realworld](https://github.com/realworld-apps/realworld) `assets/theme/styles.css`, ionicons 2.0.1 | vendored under `frontend/src/assets/vendor` |

## Patches to upstream (environment fixes, always on)

All patches are marked `[agentic patch Pn]` in the code.

| # | Where | Change | Why |
|---|---|---|---|
| P1 | frontend `api.interceptor.ts` | API base `https://api.realworld.io/api` → same-origin `/api` | The public API is gone. nginx proxies `/api` to the local backend. |
| P2 | frontend `logger.ts` | Feature logger posts only if `window.__FEATURE_LOG_URL__` is set | Without the E2EBench log server it floods the console with errors, which would pollute the console-error oracle. Set the variable to re-enable E2EBench feature coverage. |
| P3 | frontend `index.html` | Removed AutoE2E's start/stop/restart harness buttons and the axios CDN. Theme CSS vendored. Google Fonts dropped. | The harness buttons are evaluation controls, not app features, and an exploring agent would click them. The theme URL is 404. Runs make no external requests. |
| P4 | backend Prisma schema + migration | Default avatar → local `/images/smiley-cyrus.jpeg` | The old default lives on the defunct `api.realworld.io` |
| P5 | backend `auth.controller.ts` | New users are created with `demo: true` | The hosted demo hid non-demo users' articles, tags and comments from everyone else (a spam guard). That breaks the RealWorld spec and would surface as unseeded "bugs". |

Additions (not patches): a deterministic seed (`backend/src/agentic/seed.ts`), the fault switchboard (`backend/src/agentic/faults.ts`, `frontend/src/app/core/agentic-faults.ts`), the DB snapshot/reset functions (`db/agentic-reset.sql`), and the Docker build files (`*/Dockerfile.agentic`, `frontend/docker/`).

## Seeded data

Created once per fresh database volume, then snapshotted. Every run is reset to that snapshot.

- `worker01` … `worker16`: one account per parallel worker. Email `workerNN@conduit.test`, password `conduit-test-pw`. They follow nobody.
- `alice`, `bob`, `carol`, `dave`: content authors (password `conduit-author-pw`). 12 articles in total (3 each), 8 tags, 2 comments per article. alice follows bob and carol; bob follows alice. carol and dave favorite the 3 newest articles.

To reseed from scratch: `docker compose down -v && docker compose up -d`.

## Seeded faults

10 faults: crash ×2, validation ×1, data/state ×5, authorization ×1, no-op UI ×1. The ground truth (trigger, oracle, class, implicit-oracle signature) is in [`faults/faults.toml`](faults/faults.toml). Each fault is compiled in but dormant, and is switched on by the `FAULTS` variable, so one image serves every condition. Code sites are marked `[FAULT Fxx]`.

Only F01 and F02 are visible to implicit oracles (HTTP 5xx and JS errors). The other 8 need a semantic oracle. That is deliberate: the baselines' recall ceiling is 2/10, and closing that gap is RQ3.

`faults/verify_faults.py` checks that every fault manifests when on and stays dormant when off (see its docstring).

## Known pre-existing defects (unseeded)

These are upstream behaviours, not seeded. If an agent reports them, they are true positives for "unseeded bugs" and are labelled as such.

| Id | Behaviour |
|---|---|
| U1 | Settings: changing username or email to one that already exists returns HTTP 500 (no uniqueness check in `updateUser`, Prisma unique-constraint error) |
| U2 | Settings: bio and image cannot be cleared (empty values are ignored by `updateUser`) |
| U3 | Whitespace-only article titles, descriptions, bodies and comments are accepted (`if (!x)` checks without trim) |
| U4 | Articles whose title contains parentheses are unreachable in the UI: the slug keeps `(` `)`, Angular's router parses them as an auxiliary-route segment, the article request fails and the page redirects home (the API serves the slug fine) |
| U5 | Opening an article or profile that does not exist (deleted article, renamed user, mistyped URL) silently redirects home with no message, and the component re-throws the HTTP error, which is logged as an uncaught `ERROR {}` / `ERROR {errors: Object}` |
