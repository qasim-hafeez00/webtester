#!/bin/sh
# [agentic] Backend container start: migrate, seed+snapshot once, then serve.
set -e
npx prisma migrate deploy --schema src/prisma/schema.prisma
node dist/agentic/seed.js
echo "FAULTS=${FAULTS:-<none>}"
exec node dist/main.js
