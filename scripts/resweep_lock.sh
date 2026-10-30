#!/usr/bin/env bash
# D62 lock measurement (copy of resweep_d59.sh with VER, default v62, on the frozen v5.0 candidate): replay Night 3's b4 runs (h4rep Conduit, bs4rep BookStack) with the current code
# (check-outcome log, R43/R64/R26, capture_evidence on: R57/R51), on the faulty and on the clean app, no LLM.
# Outputs per (pass, run) in logs/experiments/v5dev/<label>/: <VER>_<pass>_<run>.json (counts),
# <VER>_<pass>_<run>_findings.json and <VER>_<pass>_<run>_checks.jsonl. Resumable: a result already there is kept.
# Then: python scripts/eval_v5dev.py --ver $VER --unlabelled (signatures to label), python scripts/eval_v5dev.py --ver $VER
# Usage: bash scripts/resweep_lock.sh            (BookStack, then Conduit; SKIP_BS=1 / SKIP_CONDUIT=1)
set -u
VER=${VER:-v62}
# the code this measurement belongs to: one hash over src/webtester (the commit made later must give the same hash)
mkdir -p logs/experiments/v5dev
.venv/Scripts/python -c "import hashlib,pathlib;fs=sorted(p for p in pathlib.Path('src/webtester').rglob('*') if p.is_file() and '__pycache__' not in p.parts);h=hashlib.sha256();[h.update(str(p.as_posix()).encode()+b'\0'+p.read_bytes()) for p in fs];print(h.hexdigest(), len(fs), 'files')" > "logs/experiments/v5dev/${VER}_code.txt"
echo "$(date '+%F %H:%M') $VER code $(cat logs/experiments/v5dev/${VER}_code.txt)"
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
for c in configs/realworld.toml configs/bookstack.toml; do
  grep -q '^capture_evidence = true' "$c" || { echo "capture_evidence is off in $c"; exit 1; }
done

sweep() {  # sweep <config> <label> <pass> <run dir>
  local out="logs/experiments/v5dev/$2" id; id=$(basename "$4")
  mkdir -p "$out"
  local f="$out/${VER}_$3_$id.json" clean="" src="findings_resweep.json" ck="checks_resweep.jsonl"
  [ "$3" = off ] && { clean="--clean"; src="findings_resweep_clean.json"; ck="checks_resweep_clean.jsonl"; }
  grep -q '"by_rule"' "$f" 2>/dev/null && { echo "keep $f"; return; }
  for try in 1 2; do
    "$PY" -m webtester --config "$1" resweep "$4" $clean > "$f" 2>&1
    if grep -q '"by_rule"' "$f"; then
      cp "$4/$src" "$out/${VER}_$3_${id}_findings.json"; cp "$4/$ck" "$out/${VER}_$3_${id}_checks.jsonl"
      echo "$(date '+%H:%M') done $f"; return
    fi
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
  for r in $(runs_of bs4rep); do sweep $C bs4rep on "$r"; done
  for r in $(runs_of bs4rep); do sweep $C bs4rep off "$r"; done
  "$PY" -m webtester --config $C app down
fi
if [ -z "${SKIP_CONDUIT:-}" ]; then
  C=configs/realworld.toml
  "$PY" -m webtester --config $C app up --faults F01,F02,F03,F04,F05,F06,F07,F08,F09,F10 || exit 1
  for r in $(runs_of h4rep); do sweep $C h4rep on "$r"; done
  "$PY" -m webtester --config $C app up --faults ""
  for r in $(runs_of h4rep); do sweep $C h4rep off "$r"; done
  "$PY" -m webtester --config $C app down
fi
echo "$(date '+%F %H:%M') resweep $VER done"
