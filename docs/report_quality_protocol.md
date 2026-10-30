# Report-quality protocol (D61, evaluation group 3)

What a developer gets from the harness is a finding report: a message, the page, and the steps that led
there (the gate's minimal window). This protocol measures whether such a report is usable. It is run by the
author (a person, not the assistant), after a locked run, on a sample the assistant draws.

1. **Sample.** `python scripts/report_sample.py runs/<run> [runs/<run> ...] --n 20` draws 20 confirmed findings
   at random (fixed seed) into `logs/experiments/report_quality.toml`. Ratings already in the file are kept.
2. **Reproduce.** Reset the app (`python -m webtester app reset`), log in as the finding's worker account, and
   follow the listed steps by hand. Set `reproduced = "yes"` when the reported effect shows, else `"no"`.
3. **Rate actionability**, 0 (no), 1 (partly), 2 (yes), for each of:
   - `steps_clear`: the steps can be followed without guessing;
   - `expected_vs_actual`: the report says what was expected and what happened;
   - `evidence`: the report carries the values or text that show the fault;
   - `minimal`: no step in it is unnecessary;
   - `severity_clear`: a developer can tell how much the fault matters.
4. **Triage time.** `triage_minutes` = minutes from opening the report to a decision (bug / not a bug),
   measured with a clock, before reproducing.
5. **Report.** `python -m webtester evaluate ...` prints `report_quality`: the human reproduction rate with a
   Clopper-Pearson interval, the mean actionability score out of 10, and the median triage time.

Rate the sample before looking at the labels of its findings, so the rating is not shaped by knowing which
are seeded faults.
