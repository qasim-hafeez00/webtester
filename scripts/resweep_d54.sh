#!/usr/bin/env bash
# v4 lock check after D54 (tab bars are navigation; delete item is the whole card): BookStack resweep
# (bsrep, on + clean; faults verified on and off just before), then Conduit again (h3rep, on + clean).
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
V=logs/experiments/v4dev
$PY -m webtester --config configs/bookstack.toml app up --faults all > logs/bookstack_setup/2026-10-27_app_up_d54.log 2>&1 || exit 1
CONFIG=configs/bookstack.toml LABEL=bsrep bash scripts/resweep_dev.sh > $V/bsrep_d54.log 2>&1
$PY -m webtester --config configs/bookstack.toml app down >> $V/bsrep_d54.log 2>&1
CONFIG=configs/realworld.toml LABEL=h3rep bash scripts/resweep_dev.sh > $V/h3rep_d54.log 2>&1
$PY -m webtester --config configs/realworld.toml app down >> $V/h3rep_d54.log 2>&1
echo "$(date '+%F %H:%M') both resweeps done"
