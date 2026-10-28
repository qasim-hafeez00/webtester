#!/usr/bin/env bash
# v4 pilots before the lock (plan step 4): b3v3 and b4 on each app, 2 workers, 5 min, all faults on.
# Check: states per page (median <= 5), travel without the LLM, tokens per step vs v3, gate time.
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
L=logs/experiments/v4dev/pilots_v4.log
pilot() {  # pilot <config> <faults> <agent> <label>
  $PY -m webtester --config "$1" run --agent "$3" --workers 2 --tokens 190000 --minutes 5 --steps 100000 --label "$4" >> $L 2>&1
  echo "$(date '+%H:%M') $3 $4 exit $?" >> $L
}
$PY -m webtester --config configs/realworld.toml app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10 >> $L 2>&1 || exit 1
pilot configs/realworld.toml all b3v3 h4pilot
pilot configs/realworld.toml all b4 h4pilot
$PY -m webtester --config configs/realworld.toml app down >> $L 2>&1
$PY -m webtester --config configs/bookstack.toml app up --faults all >> $L 2>&1 || exit 1
pilot configs/bookstack.toml all b3v3 bs4pilot
pilot configs/bookstack.toml all b4 bs4pilot
$PY -m webtester --config configs/bookstack.toml app down >> $L 2>&1
echo "$(date '+%F %H:%M') pilots done" >> $L
