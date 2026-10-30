#!/usr/bin/env bash
# v5 live pilots before the v5.0 lock (D62; v5 plan phase 1, O-R1 and I60): b4 and b5 on each development app,
# 2 workers, 5 min, all faults on, every v5 mechanism on (seeding, ranking, scroll, dialogs, discovery, profile step).
# Uses the LLM key, so the user runs it. Do not run it while a resweep is running (both use the app containers).
# Check afterwards: every run healthy; no 'error:' rows in checks.jsonl; states and routes not below the h4pilot /
# bs4pilot runs; write success on forms; gate time. Then: python -m webtester registry
# Usage: bash scripts/pilots_v5.sh            (SKIP_BS=1 / SKIP_CONDUIT=1)
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
L=logs/experiments/v5dev/pilots_v5.log
mkdir -p logs/experiments/v5dev
pilot() {  # pilot <config> <agent> <label>
  $PY -m webtester --config "$1" run --agent "$2" --workers 2 --tokens 190000 --minutes 5 --steps 100000 --label "$3" >> $L 2>&1
  echo "$(date '+%H:%M') $2 $3 exit $?" >> $L
}
if [ -z "${SKIP_CONDUIT:-}" ]; then
  $PY -m webtester --config configs/realworld.toml app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10 >> $L 2>&1 || exit 1
  pilot configs/realworld.toml b4 h5pilot
  pilot configs/realworld.toml b5 h5pilot
  $PY -m webtester --config configs/realworld.toml app down >> $L 2>&1
fi
if [ -z "${SKIP_BS:-}" ]; then
  $PY -m webtester --config configs/bookstack.toml app up --faults all >> $L 2>&1 || exit 1
  pilot configs/bookstack.toml b4 bs5pilot
  pilot configs/bookstack.toml b5 bs5pilot
  $PY -m webtester --config configs/bookstack.toml app down >> $L 2>&1
fi
echo "$(date '+%F %H:%M') pilots v5 done" >> $L
