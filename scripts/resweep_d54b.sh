#!/usr/bin/env bash
# v4 lock check after D54b (an unheaded list is named by the selected tab): Conduit (h3rep), then BookStack
# (bsrep), each on + clean. One app at a time (I19).
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
V=logs/experiments/v4dev
CONFIG=configs/realworld.toml LABEL=h3rep bash scripts/resweep_dev.sh > $V/h3rep_d54b.log 2>&1
$PY -m webtester --config configs/realworld.toml app down >> $V/h3rep_d54b.log 2>&1
$PY -m webtester --config configs/bookstack.toml app up --faults all > logs/bookstack_setup/2026-10-27_app_up_d54b.log 2>&1 || exit 1
CONFIG=configs/bookstack.toml LABEL=bsrep bash scripts/resweep_dev.sh > $V/bsrep_d54b.log 2>&1
$PY -m webtester --config configs/bookstack.toml app down >> $V/bsrep_d54b.log 2>&1
echo "$(date '+%F %H:%M') both resweeps done"
