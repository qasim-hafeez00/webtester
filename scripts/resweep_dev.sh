#!/usr/bin/env bash
# Harness v4 development check (D49): replay recorded gated runs with the v4 oracles, no LLM.
# Faults on, then the clean app. BookStack's faults are client-side (--clean drops them);
# Conduit's are server-side, so the app is restarted without faults for the clean pass.
# Resumable: an output that already holds a result is kept; a crashed run is retried once.
# Usage: CONFIG=configs/realworld.toml LABEL=h3rep FAULTS=F01,...,F10 bash scripts/resweep_dev.sh
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
CONFIG=${CONFIG:-configs/realworld.toml}
LABEL=${LABEL:-h3rep}
FAULTS=${FAULTS:-F01,F02,F03,F04,F05,F06,F07,F08,F09,F10}
OUT=logs/experiments/v4dev
mkdir -p "$OUT"
REG=logs/experiments/run_registry.md
runs=$(ls -d runs/*_"$LABEL"* | while read -r d; do
  [ -f "$d/replay.jsonl" ] && [ -f "$d/summary.json" ] || continue
  grep -q "\`$(basename "$d")\` | invalid" "$REG" && continue  # runs invalid under D20 are not resweeped
  echo "$d"
done)
echo "resweeping $(echo "$runs" | wc -w) runs"

sweep() {  # sweep <pass> <run> [--clean]
  local f="$OUT/resweep_$1_$(basename "$2").json"
  grep -q '"by_rule"' "$f" 2>/dev/null && { echo "keep $f"; return; }
  for try in 1 2; do
    $PY -m webtester --config "$CONFIG" resweep "$2" ${3:-} > "$f" 2>&1
    grep -q '"by_rule"' "$f" && { echo "done $f"; return; }
    echo "failed $f (try $try)"
  done
}

server_faults=1
grep -q '^fault_script' "$CONFIG" && server_faults=0
if [ "$server_faults" = 1 ]; then $PY -m webtester --config "$CONFIG" app up --faults "$FAULTS"; fi
for r in $runs; do sweep on "$r"; done
if [ "$server_faults" = 1 ]; then
  $PY -m webtester --config "$CONFIG" app up --faults ""
  for r in $runs; do sweep off "$r" --clean; done
  $PY -m webtester --config "$CONFIG" app up --faults "$FAULTS"
else
  for r in $runs; do sweep off "$r" --clean; done
fi
echo "resweep done"
