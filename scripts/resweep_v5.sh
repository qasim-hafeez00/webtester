#!/usr/bin/env bash
# D55 development check: replay Night 3's b4 runs (h4rep Conduit, bs4rep BookStack) with the v4 oracles
# (540887e, via scripts/webtester_v4oracles.py) and the v5 oracles, on the faulty and on the clean app,
# no LLM. Outputs per (version, pass, run) in logs/experiments/v5dev/<label>/: the counts (.json) and the
# findings (_findings.json). Resumable: a result already there is kept.
# Usage: bash scripts/resweep_v5.sh            (BookStack, then Conduit; SKIP_BS=1 / SKIP_CONDUIT=1)
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python

sweep() {  # sweep <config> <label> <ver> <pass> <run dir>
  local out="logs/experiments/v5dev/$2" id; id=$(basename "$5")
  mkdir -p "$out"
  local f="$out/$3_$4_$id.json" clean="" src="findings_resweep.json"
  [ "$4" = off ] && { clean="--clean"; src="findings_resweep_clean.json"; }
  grep -q '"by_rule"' "$f" 2>/dev/null && { echo "keep $f"; return; }
  local cli=(-m webtester); [ "$3" = v4 ] && cli=(scripts/webtester_v4oracles.py)
  for try in 1 2; do
    "$PY" "${cli[@]}" --config "$1" resweep "$5" $clean > "$f" 2>&1
    if grep -q '"by_rule"' "$f"; then cp "$5/$src" "$out/$3_$4_${id}_findings.json"; echo "$(date '+%H:%M') done $f"; return; fi
    echo "$(date '+%H:%M') failed $f (try $try)"
  done
}

runs_of() { ls -d runs/*_b4_n4_"$1"* | while read -r d; do
  [ -f "$d/replay.jsonl" ] && [ -f "$d/summary.json" ] || continue
  grep -q "\`$(basename "$d")\` | invalid" logs/experiments/run_registry.md && continue
  echo "$d"; done; }

if [ -z "${SKIP_BS:-}" ]; then
  C=configs/bookstack.toml
  "$PY" -m webtester --config $C app up --faults all || exit 1   # client-side faults: the resweep reads them here
  for r in $(runs_of bs4rep); do for v in v4 v5; do sweep $C bs4rep $v on "$r"; done; done
  for r in $(runs_of bs4rep); do for v in v4 v5; do sweep $C bs4rep $v off "$r"; done; done
  "$PY" -m webtester --config $C app down
fi
if [ -z "${SKIP_CONDUIT:-}" ]; then
  C=configs/realworld.toml
  "$PY" -m webtester --config $C app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10 || exit 1
  for r in $(runs_of h4rep); do for v in v4 v5; do sweep $C h4rep $v on "$r"; done; done
  "$PY" -m webtester --config $C app up --faults ""
  for r in $(runs_of h4rep); do for v in v4 v5; do sweep $C h4rep $v off "$r"; done; done
  "$PY" -m webtester --config $C app down
fi
echo "$(date '+%F %H:%M') resweep v5 done"
