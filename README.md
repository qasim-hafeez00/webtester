# webtester: coordinated, evidence-gated LLM exploration for web app testing

Research prototype for AI4015 (Agentic AI, FAST-NUCES, Fall 2026). The research plan is in [docs/00_research_plan.md](docs/00_research_plan.md) and the literature corpus is in [literature/](literature/).

## Layout

| Path | What |
|---|---|
| `src/webtester/` | The agent harness: browser layer, LLM client, state abstraction, oracles, workers, metrics |
| `configs/` | One TOML file per app under test |
| `apps/realworld/` | Conduit subject app (Docker) with 10 seeded faults: see its [README](apps/realworld/README.md) |
| `tests/` | Unit tests (offline) and live tests (`-m live`, need the app running) |
| `runs/` | Run outputs (gitignored): `trace.jsonl`, `findings.json`, `summary.json`, `config.json` |

## Setup (Windows, Python 3.12+, Docker Desktop)

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m playwright install chromium
copy .env.example .env        # then add a free-tier API key (Gemini by default)
.venv\Scripts\python -m webtester app up --build
```

For Gemini, add additional keys as `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, and so
on. The LLM client automatically switches to the next configured key when the
current key is rate-limited or its quota is exhausted.

## Running

After a reboot, start Docker Desktop first, then bring the app back up with the fault set of the experiment (containers do not restart by themselves).

```
python -m webtester app up --faults F01,F02          # app with a fault set (ground truth)
python -m webtester run --agent b1 --minutes 15      # B1: one LLM worker (Phase 1 baseline)
python -m webtester run --agent b0 --minutes 15      # B0: BFS crawler + random form filler
python -m webtester run --agent random --steps 50    # smoke test, no API key needed
python -m webtester run --agent b1 --workers 4       # B2: N independent LLM workers
python -m webtester run --agent b4 --workers 4 --tokens 190000   # B4: G1 + G3 + G2 (gate runs after exploration)
python -m webtester triage runs/<run_id>                       # label findings (precision, semantic faults)
python -m webtester report runs/<run_id>
python -m pytest                                      # all tests
```

Every run resets the app data first (`--no-reset` to skip). The faults enabled in the running backend are recorded in the trace, and `summary.json` scores them against `apps/realworld/faults/faults.toml`.

Switch LLM provider with `--provider groq --model llama-3.3-70b-versatile` or in the TOML. Any OpenAI-compatible endpoint works.

## Conditions

| Id | Condition | Status |
|---|---|---|
| B0 | BFS crawler + random form filler (no LLM) | done |
| B1 | One LLM worker, implicit oracles only (Phase 1 baseline) | done (needs an API key to run) |
| B2 | N independent LLM workers | done (`--workers N`) |
| B3 | Shared frontier (G1), v1: advisory marks + suggestion (`--agent b3`) | done, n = 5 (no effect) |
| B3v2 | Shared frontier v2: focus area per worker, nav filtering, input-class marks (`--agent b3v2`; ablation `b3v2local`) | done, n = 5 on harness v1, v2 and v3; `b3v2local` n = 5 (v1) |
| B4 | B3v2 + inferred oracles (G3) + evidence gate (G2) (`--agent b4`) | done, n = 5 on harness v1, v2 and v3, labelled |
| A-G1 / A-G2 / A-G3 | B4 without the frontier (`b4nog1`) / without the gate (B4's raw candidates, no extra runs) / without inferred oracles (`b4nog3`) | done, n = 5 each on v2 and v3 (A-G1 also v1), labelled |

Harness versions (all conditions re-run on each): v1 (24 Oct), v2 (D42–D44: observation fix, full-prefix gate, exposure markers), **v3 (D46: settle on network idle, active controls, after-reload twin checks, `unverified` gate label; current)**. Results: [phase2_g23_results.md](logs/experiments/phase2_g23_results.md); every fact for the paper: [docs/paper_ledger.md](docs/paper_ledger.md). Findings are labelled in `logs/experiments/finding_labels.toml` (D45: labels by Claude, `by = "claude"`, user blind-checks 20% in `label_check_sample.toml`).

**Status 25 Oct:** Conduit (development app) complete on harness v3. Next: BookStack held-out runs (B0, B3v2, B4 × 5).

Phase 2 run order and commands: [docs/phase2_runbook.md](docs/phase2_runbook.md).

## Subject apps

| App | Role | Faults | Config |
|---|---|---|---|
| RealWorld / Conduit ([apps/realworld](apps/realworld/README.md)) | Development app | 10 seeded by us (server- and client-side), 2 visible to implicit oracles; F03 and F04 UI-unreachable (I34, I37); upstream defects U1–U7 and 5 defects found by the agents | `configs/realworld.toml` (default) |
| BookStack 25.2.1 ([apps/bookstack](apps/bookstack/README.md)) | Second app, from the WebTestPilot benchmark (base paper) | 18 injected client-side faults from 27 benchmark scripts, 13 reachable by exploration, none visible to implicit oracles | `--config configs/bookstack.toml` |
