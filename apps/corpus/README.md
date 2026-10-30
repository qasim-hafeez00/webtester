# Clean corpus (v5 plan E4, D60)

Apps used **only for false alarms**: no seeded faults, every finding is labelled (`fp`, `harness:`, `new:` for a
real bug, `U#` for a known upstream one). The goal by the v5.1 lock is 10-12 apps; the paper's goal is 20-30.
Each app runs from its own folder here (or the folder named), with a config in `configs/corpus_<name>.toml`.

| App | Type (fault_families.md section 4) | Image or source | Status | What is still needed |
|---|---|---|---|---|
| Parabank | Banking | `parasoft/parabank` | compose + config written | first `app up`; check the login recipe and that a restart resets the data |
| OWASP Juice Shop | Shop | `bkimminich/juice-shop` | compose + config written | first `app up`; check `blocked_text` keeps agents off the challenge pages |
| RealWorld, React front-end | Blog, social | gothinkster/react-redux-realworld-example-app on our Conduit API | planned | a compose service building the front-end against `apps/realworld`'s API |
| RealWorld, Angular front-end | Blog, social | gothinkster/angular-realworld-example-app | planned | as above |
| RealWorld, Vue front-end | Blog, social | gothinkster/vue-realworld-example-app | planned | as above |
| RealWorld, Svelte front-end | Blog, social | sveltejs/realworld | planned | as above |
| Timeoff.management | HR, leave | timeoff-management/application (Dockerfile in repo) | planned | build from source; seed a company and two users |
| Gadael | HR, leave | gadael/gadael | planned | build; seed |
| 4gaBoards | Project boards | RARgames/4gaBoards (compose in repo) | planned | compose from the repo; seed a board |
| Agilefant | Project boards | Agilefant/agilefant (Docker in repo) | planned | build; seed |
| BookStack, rebranded | Wiki, CMS | `configs/bookstack_rebrand.toml` (E6, not a corpus app: the contamination control) | config written | run with `--faults all` as the control, and with no faults as one more clean app |
| one large app | (to choose) | | open | the user picks one (e.g. a Mastodon or Discourse demo stack) |

Rules for corpus runs (fixed now, before any run, v5 plan E9):

- same model, budget and settings as the development apps (`[llm]`, `[budget]`, `[run]` copied from
  `configs/realworld.toml`);
- `mode = "controlled"` (our own containers), `capture_evidence = true`;
- n = 3 runs per app for the false-alarm bound (an app's runs are not pooled with another app's);
- false alarms are reported per run, per 100 steps and per 100 armed checks with exact intervals
  (`python -m webtester evaluate --clean runs/...`).
