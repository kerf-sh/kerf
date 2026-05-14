#!/usr/bin/env bash
# Kerf one-line installer.
#
#   curl -fsSL https://kerf.app/install.sh | bash
#
# What it does:
#   1. Detects OS + arch.
#   2. Downloads the latest pre-built binary into ~/.local/bin (or
#      $INSTALL_DIR if set).
#   3. Drops a default config at ~/.config/kerf/config.toml the first
#      time (won't overwrite an existing one).
#   4. Prints next steps.
#
# Env overrides:
#   KERF_VERSION  — tag to install (default: latest)
#   INSTALL_DIR   — where to put the binary (default: ~/.local/bin)
#   CONFIG_DIR    — where to write config.toml (default: ~/.config/kerf)

set -euo pipefail

KERF_VERSION="${KERF_VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/kerf}"
REPO="${KERF_REPO:-kerf-sh/kerf}"

note()  { printf "\033[1;36m%s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m%s\033[0m\n" "$*" >&2; }
fail()  { printf "\033[1;31merror:\033[0m %s\n" "$*" >&2; exit 1; }

# --- detect target ---
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$os" in
  darwin|linux) ;;
  *) fail "unsupported OS: $os (Darwin/Linux only)" ;;
esac

arch="$(uname -m)"
case "$arch" in
  arm64|aarch64) arch="arm64" ;;
  x86_64|amd64)  arch="amd64" ;;
  *) fail "unsupported arch: $arch" ;;
esac

note "kerf installer — target: $os/$arch"

# --- pick release URL ---
if [ "$KERF_VERSION" = "latest" ]; then
  release_url="https://github.com/${REPO}/releases/latest/download/kerf-${os}-${arch}"
else
  release_url="https://github.com/${REPO}/releases/download/${KERF_VERSION}/kerf-${os}-${arch}"
fi

mkdir -p "$INSTALL_DIR"
binary="$INSTALL_DIR/kerf"

note "downloading from $release_url"
if ! curl -fsSL -o "$binary.tmp" "$release_url"; then
  fail "download failed (no release binary at that URL? check KERF_VERSION)"
fi
chmod +x "$binary.tmp"
mv "$binary.tmp" "$binary"

note "installed: $binary"

# --- seed config ---
mkdir -p "$CONFIG_DIR"
config_file="$CONFIG_DIR/config.toml"
if [ -f "$config_file" ]; then
  note "config exists at $config_file (left alone)"
else
  example_url="https://raw.githubusercontent.com/${REPO}/main/kerf.example.toml"
  if curl -fsSL "$example_url" -o "$config_file"; then
    note "wrote default config to $config_file"
  else
    warn "couldn't fetch example config from $example_url — kerf will refuse to start without one"
  fi
fi

# --- PATH check ---
case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *) warn "$INSTALL_DIR is not on your PATH. Add this to your shell rc:
    export PATH=\"$INSTALL_DIR:\$PATH\"" ;;
esac

cat <<EOF

next steps:
  1. createdb kerf                                  # if Postgres isn't already set up
  2. \$EDITOR $config_file                          # set [llm.<provider>].api_key, optionally [auth].optional = true
  3. kerf migrate                                    # apply schema (if you built the migrate cmd separately)
  4. kerf                                            # run the server, then visit http://localhost:8080

questions: https://github.com/${REPO}/issues
EOF
