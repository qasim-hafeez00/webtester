#!/usr/bin/env bash
# D63: the lock measurement on the D63-D63c code (VER v65), started detached from the session (I48)
cd "$(dirname "$0")/.." && VER=v65 bash scripts/resweep_lock.sh > logs/experiments/v5dev/resweep_v65.log 2>&1
