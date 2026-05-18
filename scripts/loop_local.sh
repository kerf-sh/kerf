#!/usr/bin/env bash
#
# loop_local.sh — DROP+recreate the local Kerf schema, run migrations, seed,
# then run the full test harness (scripts/test_all.sh).
#
# Usage:
#   ./scripts/loop_local.sh
#   DATABASE_URL=postgres://other@host/db ./scripts/loop_local.sh   # override
#
# WARNING: This script DROPS the public schema in the target database before
# recreating it. Only run against a local / throwaway database. It will NEVER
# touch any database whose URL contains "prod", "production", "main", or
# "kerf-prod".
#
# The script does NOT commit automatically. Run manually when you want a clean
# baseline test cycle.

set -euo pipefail
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$_REPO_ROOT"

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL="${DATABASE_URL:-postgres://pc@localhost:5432/kerf?sslmode=disable}"
export DATABASE_URL

# ── Prod-safety guard ─────────────────────────────────────────────────────────
if echo "$DATABASE_URL" | grep -qiE "(prod|production|kerf-prod|main\.neon|\.prod\.)"; then
  echo "ERROR: loop_local.sh refuses to operate on a URL that looks like production."
  echo "       DATABASE_URL=${DATABASE_URL}"
  echo "       Unset DATABASE_URL or point it to a local/dev database."
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  loop_local.sh"
echo "  DB: ${DATABASE_URL%%\?*}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. DROP + recreate schema ─────────────────────────────────────────────────
echo ""
echo "▸ dropping and recreating public schema …"
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 1>&2

# ── 2. Run migrations ─────────────────────────────────────────────────────────
echo ""
echo "▸ running migrations …"
PYTHONPATH="$(printf '%s:' "$_REPO_ROOT"/packages/kerf-*/src | sed 's/:$//')" \
  python3 -m kerf_core.db.migrations.runner "$DATABASE_URL"

# ── 3. Seed ───────────────────────────────────────────────────────────────────
echo ""
if [[ -f "$_REPO_ROOT/scripts/seed_dev.py" ]]; then
  echo "▸ seeding dev data …"
  PYTHONPATH="$(printf '%s:' "$_REPO_ROOT"/packages/kerf-*/src | sed 's/:$//')" \
    python3 "$_REPO_ROOT/scripts/seed_dev.py"
else
  echo "▸ TODO: scripts/seed_dev.py not found — skipping seed step."
fi

# ── 4. Run full test suite ────────────────────────────────────────────────────
echo ""
echo "▸ running test_all.sh …"
"$_REPO_ROOT/scripts/test_all.sh"

echo ""
echo "loop_local.sh complete."
