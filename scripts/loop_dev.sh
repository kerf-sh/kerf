#!/usr/bin/env bash
#
# loop_dev.sh — GATED dev-environment cycle.
#
# Usage:
#   ./scripts/loop_dev.sh --yes
#
# Steps (only with --yes):
#   1. Read DATABASE_URL from .env.dev (without echoing it)
#   2. DROP + recreate the dev Neon schema
#   3. Deploy to Fly dev via  scripts/deploy-fly.sh --dev  (runs migrations)
#   4. Smoke: curl /healthz + one API smoke hit
#   5. Report
#
# HARD REFUSALS (enforced unconditionally):
#   - Will not run without --yes flag
#   - Will not touch any URL/app-name containing "prod", "production", or "kerf-prod"
#   - Will not echo DATABASE_URL or any secret from .env.dev to stdout/stderr
#   - Will not run automatically (requires explicit human invocation)
#
# Prereqs:
#   - .env.dev exists (cp .env.z.example .env.dev)
#   - flyctl installed and authenticated (FLY_CONFIG_DIR=./.fly)
#   - .fly/ auth token present (flyctl auth login with FLY_CONFIG_DIR=./.fly)

set -uo pipefail
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$_REPO_ROOT"

# ── Gate: require explicit --yes ──────────────────────────────────────────────
YES=false
for arg in "$@"; do
  [[ "$arg" == "--yes" ]] && YES=true
done

if [[ "$YES" != "true" ]]; then
  echo "loop_dev.sh: no-op. Pass --yes to proceed with the dev cycle."
  echo ""
  echo "  CAUTION: this script drops and recreates the dev Neon schema and"
  echo "  triggers a Fly.io deploy. It requires explicit opt-in."
  echo ""
  echo "  Usage: ./scripts/loop_dev.sh --yes"
  exit 1
fi

# ── Load .env.dev without echoing it ─────────────────────────────────────────
ENV_FILE=".env.dev"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found."
  echo "       cp .env.z.example .env.dev  and fill in your dev values."
  exit 1
fi

# Source quietly; no set -x, no echoing.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ── Prod-safety: validate DATABASE_URL and app name ──────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set in $ENV_FILE."
  exit 1
fi

# Never operate on anything that looks like production — check the URL value
# without printing it.
if echo "$DATABASE_URL" | grep -qiE "(prod|production|kerf-prod|kerf\.sh)"; then
  echo "ERROR: loop_dev.sh refuses to operate on a DATABASE_URL that looks like production."
  echo "       Check $ENV_FILE — the DATABASE_URL must be a dev/staging Neon branch."
  exit 1
fi

# App name for smoke check: kerf-dev (derived from deploy-fly.sh --dev logic)
DEV_APP_NAME="kerf-dev"
if echo "$DEV_APP_NAME" | grep -qiE "(prod|production|kerf-prod)"; then
  echo "ERROR: derived app name looks like production. Refusing."
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  loop_dev.sh  [--yes confirmed]"
echo "  env file : $ENV_FILE  (secrets not echoed)"
echo "  fly app  : $DEV_APP_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. DROP + recreate dev schema ─────────────────────────────────────────────
echo ""
echo "▸ dropping and recreating public schema on dev Neon …"
# Pass via env — psql reads PGPASSWORD / connection string; never print the URL.
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 1>&2

# ── 2. Deploy to Fly dev (runs migrations on the remote side) ─────────────────
echo ""
echo "▸ deploying to Fly dev via scripts/deploy-fly.sh --dev …"
FLY_CONFIG_DIR="./.fly" "$_REPO_ROOT/scripts/deploy-fly.sh" --dev

# ── 3. Smoke: health + one API hit ───────────────────────────────────────────
echo ""
echo "▸ smoke checks …"

DEV_BASE_URL="https://${DEV_APP_NAME}.fly.dev"

# Health check (allow up to 30 s for the deploy to finish booting)
HEALTH_OK=false
for i in $(seq 1 6); do
  if curl -fsS "${DEV_BASE_URL}/healthz" -o /dev/null 2>&1; then
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

# API smoke: list models endpoint (no auth required on dev)
if curl -fsS "${DEV_BASE_URL}/api/models" -o /dev/null 2>&1; then
  echo "  [PASS] GET /api/models"
else
  echo "  [WARN] GET /api/models returned non-200 — check manually"
fi

# ── 4. Report ─────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  loop_dev.sh complete"
echo "  app  : ${DEV_BASE_URL}"
echo "  logs : flyctl logs --app $DEV_APP_NAME"
echo "════════════════════════════════════════════════════════════════════════"
