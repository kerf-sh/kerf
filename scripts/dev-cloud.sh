#!/usr/bin/env bash
#
# dev-cloud.sh — run the FULL system locally in CLOUD mode against a
# local Postgres + local API. Same surface as the Fly "dev" deployment
# (real signup/login, Workshop, Library, billing-dormant) but everything
# on your machine.
#
#   API : http://localhost:8080   (kerf-server, CLOUD_ENABLED, no auto-login)
#   Web : http://localhost:5173   (Vite; proxies /api + /auth → :8080)
#
# The browser talks to the API same-origin via the Vite proxy, so no
# CORS config is needed (VITE_API_URL is deliberately left unset).
#
# Cloud mode has NO singleton auto-login — create an account at
# http://localhost:5173/signup the first time.
#
# Usage:
#   ./scripts/dev-cloud.sh
#   DATABASE_URL=postgres://user@host/db ./scripts/dev-cloud.sh   # override DB
#
# Stop: Ctrl-C (both processes shut down).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Local dev DB — role `pc`, db `kerf` (override via env if different).
export DATABASE_URL="${DATABASE_URL:-postgres://pc@localhost:5432/kerf?sslmode=disable}"

# Cloud surface, billing dormant (no Paystack needed locally).
# kerf_core.config.Settings has NO env prefix — these UNPREFIXED names
# are what it actually reads.
export LOCAL_MODE=false
export CLOUD_ENABLED=true
export CLOUD_BETA=true
export CORS_ORIGIN="http://localhost:5173"

echo "▸ DATABASE_URL : ${DATABASE_URL%%\?*}  (cloud mode, billing beta)"
echo "▸ migrating …"
python3 -m kerf_core.db.migrations.runner "$DATABASE_URL"

echo "▸ building config + docs manifest …"
node ./scripts/init-config.mjs
node ./scripts/build-docs-manifest.mjs

echo "▸ starting API (:8080, cloud) + Web (:5173) — Ctrl-C to stop"
npx concurrently -k -n api,web -c magenta,cyan \
  "python3 -m kerf_core --port 8080" \
  "vite --port 5173"
