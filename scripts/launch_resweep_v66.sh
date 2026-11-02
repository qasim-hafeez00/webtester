#!/usr/bin/env bash
# D63: the lock measurement on the D63-D63d code (VER v66), started detached from the session (I48)
cd "$(dirname "$0")/.." && VER=v66 bash scripts/resweep_lock.sh > logs/experiments/v5dev/resweep_v66.log 2>&1
