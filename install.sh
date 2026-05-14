#!/usr/bin/env bash
# install.sh — Kerf installer
#
# Usage (latest):  curl -fsSL https://kerf.app/install.sh | sh
# Usage (pinned):  curl -fsSL https://github.com/kerf-sh/kerf/releases/download/v0.1.0/kerf-install-v0.1.0.sh | sh
#
# Checks Docker + Postgres, pulls ghcr.io/kerf-sh/kerf:<version>,
# writes ~/.config/kerf/config.toml if absent, then prints next steps.
# Idempotent — safe to re-run for updates.
# Requirements: bash 4+, curl, Docker Engine >= 24
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Version placeholder (stamped by release-artifacts.yml) ─────────────────
KERF_VERSION="${KERF_VERSION:-__KERF_VERSION__}"
# If the placeholder wasn't replaced (e.g. running from a git checkout),
# resolve the latest GitHub release tag.
if [[ "$KERF_VERSION" == "__KERF_VERSION__" ]]; then
  if command -v curl >/dev/null 2>&1; then
    KERF_VERSION=$(curl -fsSL \
      "https://api.github.com/repos/kerf-sh/kerf/releases/latest" \
      2>/dev/null | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')
  fi
  KERF_VERSION="${KERF_VERSION:-latest}"
fi

KERF_IMAGE="ghcr.io/kerf-sh/kerf:${KERF_VERSION}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/kerf"
CONFIG_FILE="$CONFIG_DIR/config.toml"

# ── Colours ────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
  BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; YELLOW=''; GREEN=''; BLUE=''; BOLD=''; RESET=''
fi

info()  { printf "${BLUE}[kerf]${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}[kerf]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[kerf]${RESET} WARNING: %s\n" "$*" >&2; }
fail()  { printf "${RED}[kerf]${RESET} ERROR: %s\n" "$*" >&2; exit 1; }

# ── Platform detection ─────────────────────────────────────────────────────
detect_platform() {
  OS="$(uname -s)"
  ARCH="$(uname -m)"

  case "$OS" in
    Linux*)  PLATFORM="linux" ;;
    Darwin*) PLATFORM="macos" ;;
    *)       fail "Unsupported OS: $OS. Kerf supports Linux and macOS." ;;
  esac

  case "$ARCH" in
    x86_64|amd64) ARCH_LABEL="x86_64" ;;
    arm64|aarch64) ARCH_LABEL="arm64" ;;
    *) fail "Unsupported architecture: $ARCH. Kerf supports x86_64 and arm64." ;;
  esac

  info "Platform: ${PLATFORM}/${ARCH_LABEL}"
}

# ── Prerequisite checks ────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is required but not installed.\n\n  Install Docker Desktop: https://docs.docker.com/get-docker/\n  Then re-run this installer."
  fi

  if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon is not running. Start Docker Desktop (or: sudo systemctl start docker) then re-run."
  fi

  DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "0.0.0")
  info "Docker ${DOCKER_VERSION} — ok"
}

check_postgres() {
  local pg_url="${DATABASE_URL:-postgres://postgres:postgres@localhost:5432/kerf}"
  if command -v psql >/dev/null 2>&1; then
    psql "$pg_url" -c "SELECT 1;" >/dev/null 2>&1 \
      && ok "Postgres reachable at $pg_url" \
      || warn "Postgres not reachable at $pg_url — edit $CONFIG_FILE before starting."
  else
    warn "psql not found — ensure Postgres is running before starting kerf-server."
  fi
}

check_python() {
  if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    [ "$(echo "$PY_VER" | cut -d. -f1)" -ge 3 ] && [ "$PY_MINOR" -ge 11 ] \
      && info "Python ${PY_VER} — ok (kerf-sdk scripting)" \
      || warn "Python ${PY_VER} found; 3.11+ recommended for kerf-sdk."
  else
    warn "python3 not found. Install 3.11+ for kerf-sdk scripting."
  fi
}

check_node() {
  if command -v node >/dev/null 2>&1; then
    NODE_VER=$(node --version 2>/dev/null | sed 's/v//')
    [ "$(echo "$NODE_VER" | cut -d. -f1)" -ge 22 ] \
      && info "Node.js v${NODE_VER} — ok (optional: self-build frontend)" \
      || warn "Node.js v${NODE_VER}; v22+ recommended for frontend self-build."
  else
    info "Node.js not found — optional (Docker deploy doesn't need it)."
  fi
}

# ── Pull Docker image ──────────────────────────────────────────────────────
pull_image() {
  info "Pulling ${KERF_IMAGE} ..."
  docker pull "$KERF_IMAGE" && ok "Image pulled: ${KERF_IMAGE}" \
    || fail "Failed to pull ${KERF_IMAGE}. Login with: docker login ghcr.io"
}

# ── Write default config ───────────────────────────────────────────────────
write_config() {
  mkdir -p "$CONFIG_DIR"
  [[ -f "$CONFIG_FILE" ]] && { info "Config already exists at $CONFIG_FILE — skipping."; return; }

  cat > "$CONFIG_FILE" <<'TOML'
# Kerf config — see https://github.com/kerf-sh/kerf/blob/main/kerf.example.toml
[server]
port = "8080"
env = "local"
cors_origin = "http://localhost:5173"
local_mode = true

[database]
url = "postgres://postgres:postgres@localhost:5432/kerf?sslmode=disable"

[auth]
jwt_secret = "CHANGE_ME"
access_ttl = "15m"
refresh_ttl = "720h"
password_pepper = "CHANGE_ME"

[storage]
backend = "local"
local_path = "~/.local/share/kerf/storage"

[llm]
default_model = "claude-opus-4-7"
  [llm.anthropic]
  api_key = ""

[system_user]
email = "me@kerf.local"
name = "Kerf User"
password = ""
TOML

  ok "Config written to $CONFIG_FILE"
  warn "Edit $CONFIG_FILE: set database.url and llm.anthropic.api_key before starting."
}

# ── Print next steps ───────────────────────────────────────────────────────
print_next_steps() {
  printf "\n${BOLD}Kerf %s installed.${RESET}\n\nNext steps:\n\n" "$KERF_VERSION"
  printf "  1. Edit config if needed:\n       %s\n\n" "$CONFIG_FILE"
  printf "  2. Run migrations:\n"
  printf "       docker run --rm -e KERF_CONFIG=/config/config.toml \\\n"
  printf "         -v \"%s:/config:ro\" %s kerf-server --migrate\n\n" "$CONFIG_DIR" "$KERF_IMAGE"
  printf "  3. Start the server:\n"
  printf "       docker run -d --name kerf -p 8080:8080 \\\n"
  printf "         -e KERF_CONFIG=/config/config.toml \\\n"
  printf "         -v \"%s:/config:ro\" %s\n\n" "$CONFIG_DIR" "$KERF_IMAGE"
  printf "  4. Open http://localhost:8080\n\n"
  printf "  Docs: https://kerf.app/docs\n"
}

# ── Main ───────────────────────────────────────────────────────────────────
main() {
  echo ""
  echo -e "${BOLD}Kerf Installer — ${KERF_VERSION}${RESET}"
  echo "─────────────────────────────────"

  detect_platform
  check_docker
  check_postgres
  check_python
  check_node
  pull_image
  write_config
  print_next_steps
}

main "$@"
