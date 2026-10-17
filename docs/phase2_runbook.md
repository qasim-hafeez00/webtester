# Phase 2 runbook: what to run, in order

Status 16 Oct 2026. G1 (B2, B3 v1, B3 v2) is finished at n = 5 ([results](../logs/experiments/phase2_g1_results.md)). Built and unit-tested, but **not yet run against an app**:
- 15 Oct: inferred oracles (G3), the evidence gate (G2), the B4 condition and its ablations (D27–D30).
- 16 Oct: the second app, BookStack with the WebTestPilot benchmark's injected faults (D31–D37, section 7).

All decisions are in [logs/decisions.md](../logs/decisions.md).

All commands are run from the repo root in Git Bash (`.venv/Scripts/python`, or `python` with the venv activated). Every counted run uses the same settings as G1: **4 workers, 190k tokens, 30-min cap, all 10 faults on**.

## 0. Before every session

```bash
docker ps --format "{{.Names}}" | grep -v conduit      # should print nothing: stop other stacks first (I19)
python -m webtester app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10
python -m webtester app status                           # must list all 10 faults
```

Quota: one 4-worker run uses about 120–145 LLM calls; B4 adds at most about 10 judge calls. The free tier gives about 500 calls a day, so plan **3 runs a day** after the 12:00 PKT reset.

## 1. Check the new code against the app (no LLM, about 3 min)

```bash
python -m pytest -m "not live" -q          # 32 offline tests
python -m pytest -m live -q                # 4 live tests, including the B4 pipeline with a scripted LLM
```

`test_b4_checks_gate_and_judge_live` drives the real app: one check that must fail and one that must hold, then the gate replays the failure twice and the scripted judge answers. **If any live test fails, send me the output before running anything else.**

## 2. G1 ablation: B3 v2-local (5 runs, independent of B4, can start now)

```bash
python scripts/run_batch.py --agents b3v2local --workers 4 --tokens 190000 --minutes 30 --reps 5 --start 1 --label g1rep --stop-on-unhealthy
```

If the quota stops the batch, re-run the same command with `--start <next rep>`. Analysis (I do this when you tell me the runs are in):
```bash
python -m webtester compare b3v2local b3v2 --workers 4 --label-contains g1     # sharing vs a private map
python -m webtester compare b1 b3v2local --workers 4 --label-contains g1       # a private map vs none
```

## 3. B4 pilot (1 run, not counted)

```bash
python -m webtester run --agent b4 --workers 4 --tokens 190000 --minutes 30 --steps 100000 --label b4pilot1
python -m webtester triage runs/<run_id>
```

It takes about 15 min of exploration plus the gate (at most 20 min). Then **tell me the run id**. Before freezing D27/D28 I check how many checks were proposed and violated, gate minutes per finding, replay misses, and whether the prompt needs tuning. Counted runs start only after that freeze, the same way B3 v2 was frozen after its pilot.

## 4. Counted G2/G3 runs (after the freeze)

```bash
python scripts/run_batch.py --agents b4,b4nog1 --workers 4 --tokens 190000 --minutes 30 --reps 5 --start 1 --label g23rep --stop-on-unhealthy
```

That is 10 runs (B4 and A-G1 alternating), about 4 days on the free tier. **A-G2 needs no runs**: it is B4's own raw candidates (D29). **A-G3** (`b4nog3`) is optional: B3 v2's five runs already give implicit-only recall with the same exploration. Run it only if you want the gate's precision on implicit findings alone:
```bash
python scripts/run_batch.py --agents b4nog3 --workers 4 --tokens 190000 --minutes 30 --reps 5 --start 1 --label g23rep --stop-on-unhealthy
```

## 5. After every counted run: label its findings

```bash
python -m webtester triage runs/<run_id>
```

This prints each finding with its gate status, judge verdict and a *suggested* label, and appends blank entries to `logs/experiments/finding_labels.toml`. Fill `label =` with a seeded id (`F05`), a known upstream defect (`U1`–`U5`), `new: <what>`, or `fp`. Suggestions are never used as labels (D30). Precision is computed only for fully labelled runs. A few days later, re-label a random 20% blind, for an agreement figure.

Then tell me, and I review the runs, mark `run_notes.toml`, and write the results:
```bash
python -m webtester registry
python -m webtester gate-report b4 --workers 4 --label-contains g23          # G2: raw vs confirmed, per run (A-G2)
python -m webtester compare b3v2 b4 --workers 4 --label-contains g           # G3: semantic faults found
python -m webtester compare b4nog1 b4 --workers 4 --label-contains g23       # A-G1 inside the full system
```

## 6. Not built yet

- **Spec-given upper bound** (WebTestPilot-style specs for a subset of flows): optional for the course paper.

## 7. Second app: BookStack (built 16 Oct, D31–D37; details in [apps/bookstack/README.md](../apps/bookstack/README.md))

Run it **after** the Conduit B4 counted runs, so BookStack never feeds back into the design. Stop Conduit first, since one app at a time keeps the laptop load equal (I19).

**7a. Bring it up and verify (once, about 10 min, no LLM).** The first start pulls `solidnerd/bookstack:25.2.1` and `mysql:8.4`.
```bash
python -m webtester app down                                                   # Conduit off
python -m webtester --config configs/bookstack.toml app up --faults all
docker compose -f apps/bookstack/docker-compose.yml logs seed-loader | tail -5     # must end with "[agentic] ready"
python apps/bookstack/faults/verify_faults.py --expect on                         # must print PASS
python -m webtester --config configs/bookstack.toml app up --faults ""
python apps/bookstack/faults/verify_faults.py --expect off                        # must print PASS
python -m webtester --config configs/bookstack.toml app up --faults all
```
**Send me the full output of both verify runs.** These are the first runs of code written without running it (I24).

**7b. Scripted smoke run (no LLM).** It checks that faults load in harness runs and that exposures reach the trace:
```bash
python -m webtester --config configs/bookstack.toml run --agent random --steps 60 --label bssmoke
```

**7c. Counted runs (same settings as Conduit).** These are the B2 / B3 v2 / B4 replication on a second app:
```bash
python scripts/run_batch.py --config configs/bookstack.toml --agents b1,b3v2,b4 --workers 4 --tokens 190000 --minutes 30 --reps 5 --start 1 --label bsrep --stop-on-unhealthy
```
That is 15 runs, about 5 days on the free tier. Label every run's findings with `python -m webtester --config configs/bookstack.toml triage runs/<id>` (labels are `BS01`–`BS18`, `new: ...` or `fp`). The suggested labels are the faults that worker had already exposed (D36).

Analysis (I run these):
```bash
python -m webtester compare b1 b3v2 --workers 4 --label-contains bsrep      # does G1 replicate?
python -m webtester compare b3v2 b4 --workers 4 --label-contains bsrep      # G3 on faults we did not write
python -m webtester gate-report b4 --workers 4 --label-contains bsrep       # G2 on the second app
```
The "Injected faults exposed" row against "Seeded faults found" separates *never reached* from *reached but not noticed* (D36).

## Expected KPIs (provisional, plan section 3)

| Gap | KPI | Measured by |
|---|---|---|
| G1 | ≥ 15% more states, ≥ 30% fewer duplicate actions at equal tokens | Done at N = 4: +19% states, −34% duplicates (`phase2_g1_results.md`) |
| G2 | Precision ≥ 0.90 gated, recall loss ≤ 10 points, gate cost ≤ 25% of tokens | `gate-report b4` (precision raw vs gated, faults raw vs confirmed, judge tokens %) |
| G3 | Inferred oracles find ≥ 40% of the seeded semantic faults that implicit oracles miss (≥ 4 of F03–F10) | `compare b3v2 b4`, row "Seeded faults found (all oracles, labelled)" |
