#!/usr/bin/env bash
# Night 3 (harness v4, locked): b3v3 and b4 x 5 on Conduit (label h4rep), then on BookStack (bs4rep),
# interleaved per rep, same budget as Nights 1-2 (4 workers, 190k tokens, 30 min). One app at a time (I19).
# Run through the sleep block: powershell -File scripts/queue_keepawake.ps1 -CmdFile logs/batch_queue_n3_<date>.cmd.txt
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
items() { for r in 1 2 3 4 5; do echo "b3v3 $r $1"; echo "b4 $r $1"; done; }
mapfile -t CONDUIT < <(items h4rep)
mapfile -t BOOKSTACK < <(items bs4rep)

if [ "${SKIP_CONDUIT:-0}" != 1 ]; then
  $PY -m webtester --config configs/bookstack.toml app down || true
  CONFIG=configs/realworld.toml FIRST_WINDOW_NOW=1 MAX_DAYS=3 bash scripts/run_queue.sh "${CONDUIT[@]}" || exit 1
  $PY -m webtester --config configs/realworld.toml app down || true
fi
CONFIG=configs/bookstack.toml FAULTS=all FIRST_WINDOW_NOW=1 MAX_DAYS=3 bash scripts/run_queue.sh "${BOOKSTACK[@]}" || exit 1
echo "$(date '+%F %H:%M') night 3 done"
