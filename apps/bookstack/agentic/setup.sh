#!/bin/bash
# Runs in the seed-loader container after BookStack is up (its migrations are done).
# First start: install the snapshot procedures and snapshot the unseeded DB.
# Every start: restore that snapshot and load seed + worker accounts (reload.sh).
set -euo pipefail
MYSQL=(mysql -h db -uroot -proot)

echo "[agentic] waiting for BookStack"
until curl -s http://webapp:8080/ 2>/dev/null | grep -q "Redirecting to"; do
    sleep 3
done

ready=$("${MYSQL[@]}" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='agentic_meta' AND table_name='ready'")
if [ "$ready" = "0" ]; then
    echo "[agentic] first start: installing procedures and taking the snapshot"
    "${MYSQL[@]}" < /agentic/bin/procedures.sql
    "${MYSQL[@]}" -e "CALL bookstack.agentic_snapshot()"
else
    echo "[agentic] snapshot present"
fi

bash /agentic/bin/reload.sh -h db -uroot -proot
"${MYSQL[@]}" -e "CREATE TABLE IF NOT EXISTS agentic_meta.ready (x INT)"
echo "[agentic] ready"
