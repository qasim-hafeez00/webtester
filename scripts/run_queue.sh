#!/usr/bin/env bash
# Run a fixed queue of counted runs in order, one quota window per day: after each
# reset, run the queue items that have no healthy run yet until one is unhealthy
# (quota hit), then wait for the next reset. Gives up after MAX_DAYS windows.
# Usage: scripts/run_queue.sh "<agent> <rep> [label]" ...   e.g. "b1 5" "b4 1 g23rep"
#   label defaults to g1rep (the G1 runs). FIRST_WINDOW_NOW=1 uses today's quota window
#   for the first batch instead of waiting for the next reset (when today's quota is unused).
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
WORKERS=4 TOKENS=190000 MINUTES=30 LABEL=g1rep MAX_DAYS=${MAX_DAYS:-6}

healthy() {  # healthy <agent> <rep> <label>
  $PY -c "
import json, sys
from pathlib import Path
runs = sorted(Path('runs').glob('*_$1_n${WORKERS}_$3$2'))
ok = any(json.loads((r / 'summary.json').read_text(encoding='utf-8')).get('health', {}).get('ok')
         for r in runs if (r / 'summary.json').exists())
sys.exit(0 if ok else 1)"
}

for day in $(seq 1 "$MAX_DAYS"); do
  batches=()
  for item in "$@"; do
    read -r agent rep label <<< "$item"
    label=${label:-$LABEL}
    healthy "$agent" "$rep" "$label" && continue
    batches+=("--agents $agent --workers $WORKERS --tokens $TOKENS --minutes $MINUTES --reps 1 --start $rep --label $label")
  done
  [ ${#batches[@]} -eq 0 ] && { echo "$(date '+%F %H:%M') queue done"; exit 0; }
  echo "$(date '+%F %H:%M') window $day: ${#batches[@]} run(s) left"
  if [ "$day" = "1" ] && [ "${FIRST_WINDOW_NOW:-0}" = "1" ]; then
    bash scripts/after_reset.sh --now "${batches[@]}"
  else
    bash scripts/after_reset.sh --next-reset "${batches[@]}"
  fi
done
echo "queue not finished after $MAX_DAYS windows"; exit 1
