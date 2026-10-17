#!/bin/bash
# Reset between runs (and before every evidence-gate replay):
#   docker compose exec -T db bash /agentic/bin/reset.sh
# Waits until the first-start setup has finished, then restores snapshot + seed + workers.
set -uo pipefail
n=0
for _ in $(seq 1 120); do
    n=$(mysql -uroot -proot -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='agentic_meta' AND table_name='ready'" 2>/dev/null || echo 0)
    [ "$n" = "1" ] && break
    sleep 1
done
[ "$n" = "1" ] || { echo "setup has not finished (no agentic_meta.ready)" >&2; exit 1; }
bash /agentic/bin/reload.sh -uroot -proot
