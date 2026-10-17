#!/bin/sh
# [agentic] Expose the run's enabled seeded faults to the frontend bundle.
set -e
FAULTS_JSON=$(printf '%s' "${FAULTS:-}" | awk -F, '{for(i=1;i<=NF;i++){gsub(/ /,"",$i); if($i!="") printf "%s\"%s\"", (n++?",":""), toupper($i)}}')
echo "window.__FAULTS__ = [${FAULTS_JSON}];" > /usr/share/nginx/html/assets/runtime-config.js
