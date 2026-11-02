#!/usr/bin/env bash
# D63: replay the D63 live pilots offline with the current code (no LLM), faults on, to check R19r (Conduit F05),
# R22h and the R07 object fix (BookStack) on the real apps. Output: <run>/findings_resweep.json, checks_resweep.jsonl.
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
L=logs/experiments/v5dev/replay_pilots_d63.log
$PY -m webtester --config configs/bookstack.toml app up --faults all >> $L 2>&1 || exit 1
for r in runs/20261102-205620_bookstack_b4_n2_bs5pilotb runs/20261102-212454_bookstack_b5_n2_bs5pilotb; do
  $PY -m webtester --config configs/bookstack.toml resweep "$r" > "$r/resweep_d63.json" 2>&1; echo "$(date '+%H:%M') done $r $?" >> $L
done
$PY -m webtester --config configs/bookstack.toml app down >> $L 2>&1
$PY -m webtester --config configs/realworld.toml app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10 >> $L 2>&1 || exit 1
r=runs/20261102-195913_realworld_b4_n2_h5pilotb
$PY -m webtester --config configs/realworld.toml resweep "$r" > "$r/resweep_d63.json" 2>&1; echo "$(date '+%H:%M') done $r $?" >> $L
$PY -m webtester --config configs/realworld.toml app down >> $L 2>&1
echo "$(date '+%F %H:%M') replays done" >> $L
