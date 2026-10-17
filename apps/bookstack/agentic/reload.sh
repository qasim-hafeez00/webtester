#!/bin/bash
# Restore the unseeded snapshot, then load the benchmark seed (dates = yesterday, as in the
# benchmark's own seed-loader.sh) and the worker accounts. Arguments: mysql connection options.
set -euo pipefail
YESTERDAY=$(date -d 'yesterday' +%Y-%m-%d)
{
    # One reload at a time (setup.sh on `app up` and reset.sh between runs could otherwise
    # interleave: seen 16 Oct as "Duplicate entry '1' for key 'activities.PRIMARY'").
    # The lock is held by this mysql session until it ends.
    echo "DO GET_LOCK('agentic_reload', 600);"
    echo "CALL bookstack.agentic_restore();"
    echo "USE bookstack;"
    echo "START TRANSACTION;"
    sed "s/YYYY-MM-DD/$YESTERDAY/g" /agentic/environment/seed.sql
    cat /agentic/bin/workers.sql
    echo "COMMIT;"
} | mysql "$@"
