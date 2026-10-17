# Project logs

The running record of what was done, what was decided and why, what broke, and every experiment run. Read the newest progress entry first.

| File | What it holds | Updated |
|---|---|---|
| [progress/](progress/) | One entry per working day: what was done, results, what's next | Daily |
| [decisions.md](decisions.md) | Every design or research decision with its reason (newest last) | When a decision is made |
| [issues.md](issues.md) | Bugs found in our harness or the subject app, and their fixes; open questions | When found or fixed |
| [experiments/run_registry.md](experiments/run_registry.md) | Table of every run with its metrics and validity (auto-generated) | `python -m webtester registry` |
| [experiments/run_notes.toml](experiments/run_notes.toml) | Hand-written status (valid / invalid / smoke) and note per run | After each run |
| [experiments/runs/](experiments/runs/) | Archived `summary.json`, `findings.json` and `config.json` of each run | Auto, with the registry |
| [experiments/finding_labels.toml](experiments/finding_labels.toml) | Hand labels per finding (seeded/injected fault id, U*, `new: ...`, `fp`): ground truth for precision and semantic-fault recall | `python -m webtester triage <run>`, then by hand |
| [experiments/phase1_results.md](experiments/phase1_results.md), [experiments/phase2_g1_results.md](experiments/phase2_g1_results.md) | Final result tables per experiment | When an experiment closes |
| [../docs/paper_ledger.md](../docs/paper_ledger.md) | Every fact, number, decision and threat the paper needs, filed by paper section | With every decision, result or issue |

Related: the research plan is [docs/00_research_plan.md](../docs/00_research_plan.md), the reading notes are in [literature/summaries/](../literature/summaries/), and the subject app is described in [apps/realworld/README.md](../apps/realworld/README.md).

**Rule:** a result is only reported if its run is marked `valid` in `run_notes.toml`. Invalid runs stay in the registry with the reason, so nothing is silently dropped.
