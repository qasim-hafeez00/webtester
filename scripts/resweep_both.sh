#!/usr/bin/env bash
# v4 lock check (D53): Conduit resweep (h3rep, on + clean), then BookStack: recreate the container
# (I42 mail setting), verify the injected faults on and off, resweep (bsrep, on + clean).
set -u
# SKIP_CONDUIT=1: BookStack only (27 Oct restart after I47).
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
V=logs/experiments/v4dev
S=logs/bookstack_setup
if [ "${SKIP_CONDUIT:-0}" != 1 ]; then
  CONFIG=configs/realworld.toml LABEL=h3rep bash scripts/resweep_dev.sh >> $V/h3rep_d53.log 2>&1 || exit 1
  $PY -m webtester --config configs/realworld.toml app down >> $V/h3rep_d53.log 2>&1
fi
$PY -m webtester --config configs/bookstack.toml app up --faults all > $S/2026-10-26_app_up_v4.log 2>&1 || exit 1
$PY apps/bookstack/faults/verify_faults.py --expect on > $S/2026-10-26_verify_on_v4.log 2>&1 || { echo "verify on FAILED"; exit 1; }
$PY -m webtester --config configs/bookstack.toml app up --faults "" >> $S/2026-10-26_app_up_v4.log 2>&1 || exit 1
$PY apps/bookstack/faults/verify_faults.py --expect off > $S/2026-10-26_verify_off_v4.log 2>&1 || { echo "verify off FAILED"; exit 1; }
$PY -m webtester --config configs/bookstack.toml app up --faults all >> $S/2026-10-26_app_up_v4.log 2>&1 || exit 1
CONFIG=configs/bookstack.toml LABEL=bsrep bash scripts/resweep_dev.sh > $V/bsrep_d53.log 2>&1
echo "both resweeps done"
