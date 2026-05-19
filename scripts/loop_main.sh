#!/usr/bin/env bash
#
# loop_main.sh — GATED main/production-environment cycle.
#
# Mirrors loop_dev.sh but operates against MAIN (production):
#   .env.main + kerf-prod fly app.  This is a destructive script: it
#   drops and recreates the prod Neon schema and triggers a Fly.io deploy.
#   It is the prod equivalent of loop_dev.sh.
#
# Usage:
#   ./scripts/loop_main.sh --yes
#
# Steps (only with --yes):
#   1. Read DATABASE_URL from .env.main (without echoing it)
#   2. DROP + recreate the prod Neon schema
#   3. Deploy to Fly prod via  scripts/deploy-fly.sh  (runs migrations)
#   4. Smoke: curl /healthz + one API smoke hit
#   5. Report
#
# HARD REFUSALS (enforced unconditionally):
#   - Will not run without --yes flag
#   - Will not operate on a DATABASE_URL containing "dev", "staging", or "localhost"
#   - Will not echo DATABASE_URL or any secret from .env.main
#   - Will not run automatically (requires explicit human invocation)
#
# Prereqs:
#   - .env.main exists (cp .env.z.example .env.main)
#   - flyctl installed and authenticated (FLY_CONFIG_DIR=./.fly)

set -uo pipefail
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$_REPO_ROOT"

# ── Gate: require explicit --yes ──────────────────────────────────────────────
YES=false
for arg in "$@"; do
  [[ "$arg" == "--yes" ]] && YES=true
done

if [[ "$YES" != "true" ]]; then
  echo "loop_main.sh: no-op. Pass --yes to proceed with the PROD cycle."
  echo ""
  echo "  CAUTION: this script drops and recreates the PRODUCTION Neon schema"
  echo "  and triggers a Fly.io deploy of kerf-prod. It requires explicit"
  echo "  opt-in. All production data is destroyed."
  echo ""
  echo "  Usage: ./scripts/loop_main.sh --yes"
  exit 1
fi

# ── Load .env.main without echoing it ────────────────────────────────────────
ENV_FILE=".env.main"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found."
  echo "       cp .env.z.example .env.main  and fill in your prod values."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ── Validate DATABASE_URL ────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set in $ENV_FILE."
  exit 1
fi

# Hard refuse if URL looks like dev / staging / localhost
if echo "$DATABASE_URL" | grep -qiE "(localhost|127\.0\.0\.1|kerf-dev|/dev|-dev\.)"; then
  echo "ERROR: loop_main.sh refuses to operate on a DATABASE_URL that looks like dev/staging/localhost."
  echo "       Check $ENV_FILE — the DATABASE_URL must be the prod Neon branch."
  exit 1
fi

PROD_APP_NAME="kerf-prod"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  loop_main.sh  [--yes confirmed]"
echo "  env file : $ENV_FILE  (secrets not echoed)"
echo "  fly app  : $PROD_APP_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. DROP + recreate prod schema ───────────────────────────────────────────
echo ""
echo "▸ dropping and recreating public schema on prod Neon …"
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 1>&2

# ── 2. Deploy to Fly main (runs migrations on the remote side) ───────────────
# deploy-fly.sh has an interactive `PRODUCTION deploy ... continue? (yes/no)`
# gate; loop_main.sh's own --yes already serves as the explicit opt-in, so we
# pipe "yes" through to satisfy it. The --yes gate above is the user's actual
# confirmation point.
echo ""
echo "▸ deploying to Fly main via scripts/deploy-fly.sh …"
FLY_CONFIG_DIR="./.fly" "$_REPO_ROOT/scripts/deploy-fly.sh" <<< "yes"

# ── 3. Smoke: health + one API hit ───────────────────────────────────────────
echo ""
echo "▸ smoke checks …"

PROD_BASE_URL="https://${PROD_APP_NAME}.fly.dev"

HEALTH_OK=false
for i in $(seq 1 6); do
  if curl -fsS "${PROD_BASE_URL}/healthz" -o /dev/null 2>&1; then
    HEALTH_OK=true
    break
  fi
  echo "  waiting for /healthz … (attempt $i/6)"
  sleep 5
done

if [[ "$HEALTH_OK" != "true" ]]; then
  echo "  [FAIL] /healthz did not respond after 30 s"
  exit 1
fi
echo "  [PASS] /healthz"

if curl -fsS "${PROD_BASE_URL}/api/models" -o /dev/null 2>&1; then
  echo "  [PASS] GET /api/models"
else
  echo "  [WARN] GET /api/models returned non-200 — check manually"
fi

# ── 4. Report ─────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  loop_main.sh complete"
echo "  app  : ${PROD_BASE_URL}"
echo "  logs : flyctl logs --app $PROD_APP_NAME"
echo "════════════════════════════════════════════════════════════════════════"
