#!/usr/bin/env bash
# Wait for the Gemini daily quota reset (midnight Pacific = 12:00 PKT), confirm the
# primary key answers, then run the next batch.
# Usage: scripts/after_reset.sh [--next-reset | --now] "<run_batch args>" ...
#   CONFIG=configs/bookstack.toml FAULTS=all: probe with and start that app (default: Conduit, all faults).
#   --next-reset: today's reset is already used up, wait for tomorrow's.
#   --now: the key has quota now (e.g. a fresh key), do not wait for any reset.
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
CONFIG=${CONFIG:-configs/realworld.toml}
FAULTS=${FAULTS:-F01,F02,F03,F04,F05,F06,F07,F08,F09,F10}
day=today
[ "${1:-}" = "--next-reset" ] && { shift; [ "$(date +%s)" -ge "$(date -d 'today 12:05' +%s)" ] && day=tomorrow; }
target=$(date -d "$day 12:05" +%s); now=$(date +%s)
[ "${1:-}" = "--now" ] && { shift; target=$now; }
[ "$now" -lt "$target" ] && { echo "waiting $(( (target-now)/60 )) min for the quota reset"; sleep $((target-now)); }
for i in $(seq 1 12); do
  out=$($PY -c "
import asyncio
from webtester.config import load_config, load_dotenv, REPO_ROOT
from webtester.llm import LLMClient
load_dotenv(); c = LLMClient(load_config(REPO_ROOT / '$CONFIG').llm)
try:
    asyncio.run(c.complete_json('Reply with JSON.', 'Return {\"ok\": true}')); print('OK')
except Exception as e:
    print('ERR', str(e)[:200])
" 2>&1 | tail -1)
  echo "$(date +%H:%M) probe: $out"
  [ "${out:0:2}" = "OK" ] && break
  sleep 600
done
[ "${out:0:2}" = "OK" ] || { echo "key still unavailable, giving up"; exit 1; }
$PY -m webtester --config "$CONFIG" app status || $PY -m webtester --config "$CONFIG" app up --faults "$FAULTS"
# Never run alongside another run started elsewhere (seen 20 Oct: a second agent ran the same
# items): two runs at once would share the quota and the laptop, and could duplicate an item.
others() { powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match '-m webtester run' }).Count" | tr -d '\r'; }
while [ "$(others)" != "0" ]; do echo "$(date +%H:%M) another run is in progress, waiting"; sleep 120; done
for args in "$@"; do
  echo "=== batch: $args"
  PYTHONUNBUFFERED=1 $PY scripts/run_batch.py $args --stop-on-unhealthy || exit 1
done
